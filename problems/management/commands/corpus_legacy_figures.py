# -*- coding: utf-8 -*-
r"""Фаза 3: вернуть легаси-задачам картинки из Overleaf-архивов.

Что было потеряно. В базе у четырёх легаси-источников `\includegraphics`
не встречается НИ РАЗУ на 18 642 задачи: импорт вырезал ссылки на
картинки целиком. В исходных архивах их 5 052. Поэтому 69 карточек
аудита с кодом `MISS` («дан график», «на рисунке ниже») были нечинимы —
восстанавливать было не из чего.

Почему маркер ВСТАВЛЯЕТСЯ, а не заменяет ссылку. У новых источников
ссылка в тексте есть, и `images.replace_images()` меняет её на маркер
на месте. Здесь ссылки нет вовсе, и восстановить исходное место
картинки внутри условия нечем. Маркер добавляется В КОНЕЦ поля — это
осознанная потеря точного места ради того, чтобы картинка вообще была
видна. Если картинка стояла после `\solution`, она уходит в `solution`,
а не в условие: иначе ученику показали бы часть разбора.

Почему только `content_format='markdown'`. Ветка `plain` боевого шаблона
— это `linebreaksbr` без подстановки маркеров: ученик увидел бы
`[[FIGURE:<64 hex>]]` дословно ([ADR 0035](../../../docs/adr/0035-imported-images-live-in-problem-figure.md),
пункт 4). Задачи формата `plain` пропускаются и называются числом, а не
чинятся «заодно» ценой видимого мусора.

Границы задачи в исходнике — структурные, по `\problem` и родственным
разделителям (`problems/corpus_converter/raw_units.py`), а не окном
±N символов: при окне в фрагмент заезжают соседние задачи листочка, и
задача получила бы чужой график.

По умолчанию — сухой прогон. Запись только с `--apply`.
"""
import base64
import io
import json
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape

from problems.corpus_converter import raw_units as ru
from problems.corpus_converter import raw_sources as rs
from problems.corpus_converter.images import image_hash, sniff_content_type
from problems.models import Problem, ProblemFigure, SourceReference

RAW = os.path.join('C:', os.sep, 'Users', 'shipu', 'weconomics-data', '_raw2026')
LEGACY = {14: 'archive3', 13: 'matek', 3: 'lsh2025', 16: 'reshalki'}
OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'corpus_legacy_figures')
#: Тот же потолок, что у новых источников: существует не ради экономии,
#: а чтобы битый файл не уехал в базу молча.
MAX_BYTES = 8 * 1024 * 1024
MARKER = '[[FIGURE:%s]]'


class Command(BaseCommand):
    help = ('Восстановить картинки легаси-источников из Overleaf-архивов. '
            'Без --apply — сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--raw', default=RAW)
        parser.add_argument('--apply', action='store_true',
                            help='реально записать (по умолчанию сухой прогон)')
        parser.add_argument('--limit', type=int, default=0,
                            help='только первые N задач — ТОЛЬКО для сухого '
                                 'прогона: усечённый разбор нельзя применять')
        parser.add_argument('--report-dir', default=OUT_DIR)
        parser.add_argument('--preview-sample', type=int, default=150,
                            help='сколько задач показать в предпросмотре')
        parser.add_argument('--preview-seed', type=int, default=20260830)

    def handle(self, *args, **options):
        raw = options['raw']
        do_apply = options['apply']
        limit = options['limit']
        if do_apply and limit:
            raise CommandError(
                '--limit вместе с --apply запрещён: усечённый прогон записал '
                'бы часть картинок и отчитался как за все.')

        mapping_path = os.path.join(raw, 'index', 'mapping.json')
        if not os.path.exists(mapping_path):
            raise CommandError('Нет %s — сначала corpus_raw_index.'
                               % mapping_path)
        mapping = json.load(open(mapping_path, encoding='utf-8'))

        src_of = {}
        for pid, sid in SourceReference.objects.values_list('problem_id',
                                                            'source_id'):
            if sid in LEGACY:
                src_of.setdefault(pid, LEGACY[sid])

        ids = sorted(pid for pid in src_of if str(pid) in mapping)
        if limit:
            ids = ids[:limit]

        stats = {
            'задач просмотрено': 0,
            'ссылок в блоке задачи': 0,
            'файл найден': 0,
            'файла нет на диске': 0,
            'тип не картинка (pdf/eps/битый)': 0,
            'слишком большой': 0,
            'картинок к записи': 0,
            'задач получат картинку': 0,
            'уже было': 0,
            'пропущено: формат plain': 0,
            'пропущено: подтверждено человеком': 0,
            'блоков tikz в исходнике': 0,
        }
        planned = []          # (pid, digest, path, ctype, size, field, ref)
        unresolved = []       # ссылки без файла — в очередь ручного разбора
        files = _FileCache(raw)

        existing = set(ProblemFigure.objects.filter(problem_id__in=ids)
                       .values_list('problem_id', 'tikz_hash'))
        meta = {p.pk: p for p in Problem.objects.filter(pk__in=ids)
                .only('id', 'content_format', 'human_review', 'statement',
                      'solution')}

        for pid in ids:
            rec = mapping[str(pid)][0]
            text = files.text(rec['slot'], rec['rel'])
            if not text:
                continue
            stats['задач просмотрено'] += 1
            left, right = ru.unit_bounds(text, rec['start'], rec['end'])
            refs = ru.figures_in_unit(text, left, right)
            stats['блоков tikz в исходнике'] += len(
                ru.tikz_in_unit(text, left, right))
            if not refs:
                continue
            problem = meta.get(pid)
            if problem is None:
                continue
            tex_dir = os.path.dirname(files.path(rec['slot'], rec['rel']))
            root = os.path.join(raw, rec['slot'])
            extra = ru.graphics_dirs(text)
            got = False
            for offset, ref in refs:
                stats['ссылок в блоке задачи'] += 1
                path = ru.resolve_image(ref, tex_dir, root, extra)
                if path is None:
                    stats['файла нет на диске'] += 1
                    unresolved.append({'id': pid, 'ref': ref,
                                       'slot': rec['slot'], 'rel': rec['rel'],
                                       'why': 'файла нет в архиве'})
                    continue
                stats['файл найден'] += 1
                size = os.path.getsize(path)
                if size > MAX_BYTES:
                    stats['слишком большой'] += 1
                    unresolved.append({'id': pid, 'ref': ref,
                                       'slot': rec['slot'], 'rel': rec['rel'],
                                       'why': '%d байт > потолка' % size})
                    continue
                with open(path, 'rb') as fh:
                    head = fh.read(32)
                ctype = sniff_content_type(head)
                if ctype is None:
                    stats['тип не картинка (pdf/eps/битый)'] += 1
                    unresolved.append(
                        {'id': pid, 'ref': ref, 'slot': rec['slot'],
                         'rel': rec['rel'],
                         'why': 'не растровая картинка: %s'
                                % os.path.splitext(path)[1]})
                    continue
                digest = image_hash(os.path.relpath(path, raw))
                if (pid, digest) in existing:
                    stats['уже было'] += 1
                    continue
                if problem.human_review == Problem.HumanReview.APPROVED:
                    stats['пропущено: подтверждено человеком'] += 1
                    continue
                if problem.content_format != 'markdown':
                    stats['пропущено: формат plain'] += 1
                    unresolved.append(
                        {'id': pid, 'ref': ref, 'slot': rec['slot'],
                         'rel': rec['rel'],
                         'why': 'формат plain: маркер был бы виден дословно'})
                    continue
                field = ru.field_for(text, left, right, offset)
                planned.append((pid, digest, path, ctype, size, field, ref))
                existing.add((pid, digest))
                got = True
            if got:
                stats['задач получат картинку'] += 1
        stats['картинок к записи'] = len(planned)

        report_dir = options['report_dir']
        os.makedirs(report_dir, exist_ok=True)
        self._write_report(report_dir, stats, planned, unresolved, raw)
        preview = self._preview(report_dir, planned, raw, files, mapping,
                                options['preview_sample'],
                                options['preview_seed'])

        if not do_apply:
            self._print(stats)
            self.stdout.write('')
            self.stdout.write('СУХОЙ ПРОГОН — в базу не записано ничего.')
            self.stdout.write('предпросмотр: %s' % preview)
            self.stdout.write('отчёт: %s' % report_dir)
            return

        backup = self._backup(report_dir, planned)
        created = self._write(planned)
        self._print(stats)
        self.stdout.write('')
        self.stdout.write('ЗАПИСАНО. Создано ProblemFigure: %d' % created)
        self.stdout.write('бэкап текстов: %s' % backup)
        self.stdout.write('предпросмотр: %s' % preview)
        self.stdout.write('отчёт: %s' % report_dir)

    # ------------------------------------------------------------------

    def _print(self, stats):
        for key, value in stats.items():
            self.stdout.write('%-34s %7d' % (key, value))

    def _backup(self, report_dir, planned):
        """Снимок изменяемых полей ДО записи: без него откатывать нечем."""
        fields = {}
        for pid, _d, _p, _c, _s, field, _r in planned:
            fields.setdefault(pid, set()).add(field)
        snapshot = {}
        for problem in Problem.objects.filter(pk__in=list(fields)).only(
                'id', 'statement', 'solution'):
            snapshot[str(problem.pk)] = {
                f: getattr(problem, f) for f in fields[problem.pk]}
        path = os.path.join(report_dir, 'texts_backup.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'when': timezone.now().isoformat(),
                       'fields': snapshot}, fh, ensure_ascii=False)
        return path

    def _write(self, planned):
        created = 0
        by_problem = {}
        for pid, digest, path, ctype, _size, field, ref in planned:
            by_problem.setdefault(pid, []).append((digest, path, ctype, field,
                                                   ref))
        for pid, items in by_problem.items():
            # Своя транзакция на задачу: на SQLite IntegrityError отравляет
            # родительский savepoint, и одна битая задача утащила бы пачку.
            with transaction.atomic():
                problem = Problem.objects.select_for_update().get(pk=pid)
                touched = {}
                for digest, path, ctype, field, ref in items:
                    with open(path, 'rb') as fh:
                        data = fh.read()
                    if sniff_content_type(data[:32]) != ctype:
                        continue
                    ProblemFigure.objects.update_or_create(
                        problem_id=pid, tikz_hash=digest,
                        defaults={'tikz_source': ref, 'svg': '',
                                  'image_data': data, 'content_type': ctype,
                                  'source_field': field})
                    created += 1
                    marker = MARKER % digest
                    current = touched.get(field, getattr(problem, field) or '')
                    if marker not in current:
                        # Только дописывание. Никакого `.strip()` целиком:
                        # он снял бы и ВЕДУЩИЕ пробелы, то есть изменил
                        # текст сверх маркера. На первом боевом прогоне так
                        # и вышло — у четырёх задач (#42522, #30502, #28355,
                        # #27513) исчезли ведущие переводы строк.
                        current = (current.rstrip() + '\n\n' + marker
                                   if current.strip() else marker)
                    touched[field] = current
                if touched:
                    for field, value in touched.items():
                        setattr(problem, field, value)
                    problem.save(update_fields=list(touched))
        return created

    def _preview(self, report_dir, planned, raw, files, mapping, sample, seed):
        """HTML с парами «условие / картинка, которую ей припишут».

        Проверять глазами надо именно это: приписать задаче ЧУЖОЙ график
        хуже, чем не приписать никакого, — ученик решает не ту задачу и
        не может этого заметить."""
        by_problem = {}
        for pid, digest, path, ctype, size, field, ref in planned:
            by_problem.setdefault(pid, []).append((path, ctype, field, ref))
        ids = sorted(by_problem)
        rnd = random.Random(seed)
        if len(ids) > sample:
            ids = sorted(rnd.sample(ids, sample))
        texts = {p.pk: p for p in Problem.objects.filter(pk__in=ids)
                 .only('id', 'statement', 'solution')}
        out = os.path.join(report_dir, 'preview.html')
        with open(out, 'w', encoding='utf-8') as fh:
            fh.write('<!doctype html><meta charset="utf-8">'
                     '<title>Картинки легаси: предпросмотр</title>'
                     '<style>body{font:15px/1.5 system-ui;margin:24px;'
                     'max-width:1000px}article{border:1px solid #d8d8d8;'
                     'border-radius:8px;padding:16px;margin:18px 0}'
                     'img{max-width:100%;height:auto;border:1px solid #eee;'
                     'margin:6px 0}h2{font-size:15px;margin:0 0 8px}'
                     'pre{white-space:pre-wrap;background:#fafafa;padding:8px;'
                     'font-size:12px;overflow-x:auto}'
                     '.f{color:#666;font-size:12px}</style>')
            fh.write('<h1>Картинки легаси-источников: %d задач из %d</h1>'
                     % (len(ids), len(by_problem)))
            fh.write('<p>Сид выборки %d. Показано условие из базы и '
                     'картинки, которые ему припишет <code>--apply</code>.</p>'
                     % seed)
            for pid in ids:
                problem = texts.get(pid)
                fh.write('<article><h2>#%d</h2>' % pid)
                fh.write('<div>%s</div>'
                         % escape(' '.join((problem.statement or '').split())
                                  [:900]) if problem else '')
                for path, ctype, field, ref in by_problem[pid]:
                    data, shown = _thumbnail(path, ctype)
                    b64 = base64.b64encode(data).decode('ascii')
                    fh.write('<div class="f">поле <b>%s</b>, ссылка '
                             '<code>%s</code></div>'
                             % (escape(field), escape(ref)))
                    fh.write('<img src="data:%s;base64,%s">' % (shown, b64))
                fh.write('</article>')
        return out

    def _write_report(self, report_dir, stats, planned, unresolved, raw):
        with open(os.path.join(report_dir, 'plan.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump([{'id': p, 'hash': d,
                        'path': os.path.relpath(path, raw),
                        'type': c, 'bytes': s, 'field': f, 'ref': r}
                       for p, d, path, c, s, f, r in planned],
                      fh, ensure_ascii=False)
        with open(os.path.join(report_dir, 'unresolved.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump(unresolved, fh, ensure_ascii=False, indent=1)
        with open(os.path.join(report_dir, 'stats.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump(stats, fh, ensure_ascii=False, indent=1)


class _FileCache:
    """Файлы читаются много раз подряд — держим последние в памяти."""

    def __init__(self, raw, size=400):
        self.raw = raw
        self.size = size
        self._cache = {}

    def path(self, slot, rel):
        return os.path.join(self.raw, slot, rel.replace('/', os.sep))

    def text(self, slot, rel):
        key = (slot, rel)
        if key not in self._cache:
            if len(self._cache) >= self.size:
                self._cache.clear()
            try:
                self._cache[key] = rs.read_text(self.path(slot, rel))
            except OSError:
                self._cache[key] = ''
        return self._cache[key]


#: Ширина миниатюры в предпросмотре. Полноразмерные картинки давали
#: HTML на 62 МБ — файл, который владелец физически не откроет, а значит
#: и не проверит. В базу при этом кладётся ОРИГИНАЛ, не миниатюра.
THUMB_WIDTH = 620


def _thumbnail(path, content_type):
    """`(байты, mime)` уменьшенной копии для предпросмотра."""
    try:
        from PIL import Image
    except ImportError:
        with open(path, 'rb') as fh:
            return fh.read(), content_type
    try:
        with Image.open(path) as img:
            if img.width <= THUMB_WIDTH:
                with open(path, 'rb') as fh:
                    return fh.read(), content_type
            img = img.convert('RGB')
            height = max(1, round(img.height * THUMB_WIDTH / img.width))
            img = img.resize((THUMB_WIDTH, height), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=82)
            return buf.getvalue(), 'image/jpeg'
    except Exception:
        # Битую картинку показываем как есть: предпросмотр не должен
        # падать из-за одного файла.
        with open(path, 'rb') as fh:
            return fh.read(), content_type
