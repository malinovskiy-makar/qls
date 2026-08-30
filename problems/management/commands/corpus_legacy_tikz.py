# -*- coding: utf-8 -*-
r"""Фаза 3, вторая половина: графики, нарисованные кодом TikZ/PGFPlots.

`corpus_legacy_figures` возвращает картинки, которые в проекте лежат
файлами. Но часть графиков автор не вкладывал файлом, а рисовал прямо в
`.tex` — окружением `tikzpicture`. Импорт вырезал и их: в блоках задач
таких графиков 263 у 115 задач.

Здесь они компилируются в SVG уже проверенной песочницей
([ADR 0031](../../../docs/adr/0031-tikz-svg-blocked-by-sanitizer.md)):
офлайн, без `\write18`, с таймаутом и своим временным каталогом на
каждую сборку. Хранение и показ — те же, что у растровых картинок:
строка `ProblemFigure`, маркер в тексте, `<img>` ПОСЛЕ санитайзера.

**Две попытки на блок.** Сначала как есть; если latex падает — второй
раз с объявлениями из преамбулы ИСХОДНОГО проекта. Домашние стили
авторов (`style=style1`, `\circled{1}`) иначе не собираются, а таких
блоков заметная доля. Чинится общий случай — разбор преамбулы, — а не
конкретный номер задачи.

По умолчанию — сухой прогон. Запись только с `--apply`.
"""
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from problems.corpus_converter import raw_sources as rs
from problems.corpus_converter import raw_units as ru
from problems.corpus_converter.tikz_render import (
    TikzCompileError, compile_tikz_to_svg, extract_tikz_blocks,
    toolchain_available,
)
from problems.models import Problem, ProblemFigure, SourceReference

RAW = os.path.join('C:', os.sep, 'Users', 'shipu', 'weconomics-data', '_raw2026')
LEGACY = {14: 'archive3', 13: 'matek', 3: 'lsh2025', 16: 'reshalki'}
OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'corpus_legacy_figures')
MARKER = '[[FIGURE:%s]]'


class Command(BaseCommand):
    help = ('Собрать TikZ-графики легаси-задач из архивов в SVG. '
            'Без --apply — сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--raw', default=RAW)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--limit', type=int, default=0,
                            help='только первые N блоков — ТОЛЬКО для сухого '
                                 'прогона')
        parser.add_argument('--report-dir', default=OUT_DIR)

    def handle(self, *args, **options):
        raw = options['raw']
        do_apply = options['apply']
        if do_apply and options['limit']:
            raise CommandError(
                '--limit вместе с --apply запрещён: усечённый прогон собрал '
                'бы часть графиков и отчитался как за все.')
        if not toolchain_available():
            raise CommandError(
                'latex/dvisvgm не найдены — компиляция невозможна. '
                'Без них команда честно не начинается.')

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
        meta = {p.pk: p for p in Problem.objects.filter(pk__in=ids)
                .only('id', 'content_format', 'human_review')}
        existing = set(ProblemFigure.objects.filter(problem_id__in=ids)
                       .values_list('problem_id', 'tikz_hash'))

        stats = {
            'блоков найдено': 0,
            'задач с блоками': 0,
            'пропущено: формат plain': 0,
            'пропущено: подтверждено человеком': 0,
            'уже было': 0,
            'к сборке': 0,
            'собралось сразу': 0,
            'собралось с преамбулой проекта': 0,
            'не собралось': 0,
        }
        todo = []
        cache = {}
        problems_with = set()

        for pid in ids:
            rec = mapping[str(pid)][0]
            key = (rec['slot'], rec['rel'])
            if key not in cache:
                if len(cache) > 200:
                    cache.clear()
                try:
                    cache[key] = rs.read_text(
                        os.path.join(raw, rec['slot'],
                                     rec['rel'].replace('/', os.sep)))
                except OSError:
                    cache[key] = ''
            text = cache[key]
            if not text:
                continue
            left, right = ru.unit_bounds(text, rec['start'], rec['end'])
            _out, blocks = extract_tikz_blocks(text[left:right])
            if not blocks:
                continue
            problems_with.add(pid)
            problem = meta.get(pid)
            for digest, source in blocks:
                stats['блоков найдено'] += 1
                if problem is None:
                    continue
                if (pid, digest) in existing:
                    stats['уже было'] += 1
                    continue
                if problem.human_review == Problem.HumanReview.APPROVED:
                    stats['пропущено: подтверждено человеком'] += 1
                    continue
                if problem.content_format != 'markdown':
                    stats['пропущено: формат plain'] += 1
                    continue
                # Смещение ИМЕННО этого блока, а не начала задачи: иначе
                # `field_for` всегда сравнивал бы с левой границей и любой
                # график уезжал бы в условие, включая нарисованные в разборе.
                at = text.find(source, left, right)
                field = ru.field_for(text, left, right,
                                     at if at >= 0 else left)
                todo.append((pid, digest, source, field, rec['slot'],
                             rec['rel']))
                existing.add((pid, digest))
        stats['задач с блоками'] = len(problems_with)
        if options['limit']:
            todo = todo[:options['limit']]
        stats['к сборке'] = len(todo)

        built = []
        failures = []
        preambles = {}
        for pid, digest, source, field, slot, rel in todo:
            svg, how, why = self._build(raw, slot, rel, source, preambles)
            if svg is None:
                stats['не собралось'] += 1
                failures.append({'id': pid, 'slot': slot, 'rel': rel,
                                 'why': why})
                continue
            stats[how] += 1
            built.append((pid, digest, source, svg, field))

        report_dir = options['report_dir']
        os.makedirs(report_dir, exist_ok=True)
        with open(os.path.join(report_dir, 'tikz_failures.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump(failures, fh, ensure_ascii=False, indent=1)

        for key, value in stats.items():
            self.stdout.write('%-38s %6d' % (key, value))

        if not do_apply:
            self.stdout.write('')
            self.stdout.write('СУХОЙ ПРОГОН — в базу не записано ничего.')
            self.stdout.write('отказы: %s'
                              % os.path.join(report_dir, 'tikz_failures.json'))
            return

        backup = self._backup(report_dir, built)
        created = self._write(built)
        self.stdout.write('')
        self.stdout.write('ЗАПИСАНО. Создано ProblemFigure: %d' % created)
        self.stdout.write('бэкап текстов: %s' % backup)

    # ------------------------------------------------------------------

    def _build(self, raw, slot, rel, source, preambles):
        """`(svg, ключ_статистики, причина_отказа)`. Две попытки."""
        try:
            return compile_tikz_to_svg(source), 'собралось сразу', None
        except TikzCompileError as exc:
            first = str(exc)[:300]
        key = (slot, os.path.dirname(rel))
        if key not in preambles:
            root = os.path.join(raw, slot)
            tex_dir = os.path.dirname(
                os.path.join(root, rel.replace('/', os.sep)))
            preambles[key] = self._checked_preamble(
                ru.harvest_preamble(ru.project_style_files(root, tex_dir)))
        preamble = preambles[key]
        if not preamble:
            return None, None, first
        try:
            return (compile_tikz_to_svg(source, preamble=preamble),
                    'собралось с преамбулой проекта', None)
        except TikzCompileError as exc:
            return None, None, str(exc)[:300]

    #: Заведомо рабочий блок: на нём проверяется, что преамбула проекта
    #: сама по себе компилируется.
    _PROBE = r'\begin{tikzpicture}\draw (0,0) -- (1,1);\end{tikzpicture}'

    def _checked_preamble(self, preamble):
        """Преамбула, только если она не ломает компиляцию сама.

        Разбор чужой преамбулы — эвристика, и обрезанное объявление
        роняет ВСЁ, что с ним собирается (живой случай — обрезанный
        `\\definecolor`). Поэтому она один раз проверяется на заведомо
        рабочем блоке: не прошла — вторая попытка идёт без неё, то есть
        не хуже первой."""
        if not preamble:
            return ''
        try:
            compile_tikz_to_svg(self._PROBE, preamble=preamble)
        except TikzCompileError:
            return ''
        return preamble

    def _backup(self, report_dir, built):
        fields = {}
        for pid, _d, _s, _svg, field in built:
            fields.setdefault(pid, set()).add(field)
        snapshot = {}
        for problem in Problem.objects.filter(pk__in=list(fields)).only(
                'id', 'statement', 'solution'):
            snapshot[str(problem.pk)] = {
                f: getattr(problem, f) for f in fields[problem.pk]}
        path = os.path.join(report_dir, 'tikz_texts_backup.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'when': timezone.now().isoformat(),
                       'fields': snapshot}, fh, ensure_ascii=False)
        return path

    def _write(self, built):
        created = 0
        by_problem = {}
        for pid, digest, source, svg, field in built:
            by_problem.setdefault(pid, []).append((digest, source, svg, field))
        for pid, items in by_problem.items():
            with transaction.atomic():
                problem = Problem.objects.select_for_update().get(pk=pid)
                touched = {}
                for digest, source, svg, field in items:
                    ProblemFigure.objects.update_or_create(
                        problem_id=pid, tikz_hash=digest,
                        defaults={'tikz_source': source, 'svg': svg,
                                  'image_data': None, 'content_type': '',
                                  'source_field': field})
                    created += 1
                    marker = MARKER % digest
                    current = touched.get(field, getattr(problem, field) or '')
                    if marker not in current:
                        current = (current.rstrip() + '\n\n' + marker
                                   if current.strip() else marker)
                    touched[field] = current
                if touched:
                    for field, value in touched.items():
                        setattr(problem, field, value)
                    problem.save(update_fields=list(touched))
        return created
