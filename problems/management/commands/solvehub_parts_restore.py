"""Вернуть в банк пункты задач SolveHub, потерянные при выгрузке (решение владельца 13.10.2026).

Выгрузка августа 2026 сохраняла только первую запись SolveHub (`problems[0]`),
пункты б), в)… — отдельные записи цепочки `parent_hash` — пропали у 574 задач.
Перекачка 13.10 лежит в `solvehub_v2/problems/{hash}.json`: поле `_parts` — все
записи задачи по порядку цепочки (первая — сама задача).

Две группы — по числу подпунктов в базе ДО починки (`db_parts_now` таблицы
`parts_summary.csv`, снимок 13.10):

* **A** (подпункт а) уже есть): ТОЛЬКО добавить записи 2..N новыми
  `ProblemPart`. Условие, ответ, решение задачи и подпункт а) — ни байта.
* **B** (подпунктов нет): условие → шапка (текст записи 1 до метки а)), все
  записи 1..N — подпункты. Ответ и решение задачи не меняются.

Тексты собираются ТЕМ ЖЕ конвейером, что положил в базу импорт и
`reconvert_new_sources` (`reconvert.solvehub_records`): варианты ответа
дописываются в текст, ссылки на картинки → маркеры `[[FIGURE:…]]` по
`image_map.json`, затем `convert_for_import`. Запись 1 берётся из АВГУСТОВСКОГО
файла (из него построен текст базы), записи 2..N — из перекачки. Модель не
участвует. Задача, не прошедшая хотя бы один стоп-гейт, не трогается и уходит
в `manual_list.csv` (или в `blocked_images.csv`, если не хватает только картинок).

    manage.py solvehub_parts_restore                       # сухой прогон, обе группы
    manage.py solvehub_parts_restore --group A --apply     # запись A, свой снимок
    manage.py solvehub_parts_restore --revert <снимок.json>

Устройство и потери (вид проверки пункта) — `solvehub_v2/sync/DESIGN.md`.
"""
import csv
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog import testplay
from problems import bank_sync
from problems.corpus_converter.images import MD_IMAGE_RE, replace_images, sniff_content_type
from problems.corpus_converter.ingest import convert_for_import, data_root
from problems.corpus_converter.reconvert import solvehub_records, solvehub_resolver
from problems.corpus_converter.solvehub import format_answer, options_block, parse_options
from problems.models import Problem, ProblemFigure, ProblemPart, SourceReference

from ._bank_edit import invalidate_search, revert_and_report, summary

#: Всегда вручную: 17 записей, разбор по правилу не доверяем (решение 13.10).
ALWAYS_MANUAL = {61281}
#: Правка позже создания больше чем на столько — «правили после импорта»
#: (то же правило, что у анализа 13.10, `analyze_v2.py`).
EDIT_GAP_SECONDS = 5

ALPHABETS = (
    'абвгдежзиклмнопрст',
    'abcdefghijklmnopqrst',
)

#: Метка в начале записи-пункта: `б)`, `$б)$`, `(b)`, `**2.(7 баллов)**`,
#: `Задание $2.$`, `**б)**`. Звёздочки снаружи и внутри — жирная метка.
#: Без `^`: `.match(text, pos)` и так привязан к `pos`, а `^` с позицией
#: внутри текста не совпал бы никогда. Перевод строки шаблон не перешагивает.
LABEL_RE = re.compile(
    r'[ \t ]*(?P<pre>\*\*|\*)?[ \t ]*'
    r'(?:(?P<word>Задание|Задача|Пункт|Вопрос|Часть|Part|Question)\s*)?'
    r'(?P<d1>\$\s*)?(?P<op>\()?'
    r'(?P<tok>\d{1,2}|[а-яёa-zА-ЯЁA-Z])(?P<cl>[).])'
    r'(?P<d2>\s*\$)?(?P<post>\*\*|\*)?'
)


# ── Текст ────────────────────────────────────────────────────────────────
def norm(text):
    """Для сверки «то же ли это»: без пробелов, `$` и `*`; хост картинок
    SolveHub сменился (`solvehub.s3.regru.cloud` → `media.solvehub.app`)."""
    text = (text or '').replace('solvehub.s3.regru.cloud', 'media.solvehub.app')
    return re.sub(r'[\s$* ]+', '', text)


def strip_urls(text):
    return MD_IMAGE_RE.sub('IMG', text or '')


def token_index(tok):
    """Позиция метки в своём ряду: «б» → (0, 1), «c» → (1, 2), «3» → ('d', 2)."""
    t = tok.lower()
    if t.isdigit():
        return 'd', int(t) - 1
    for n, alphabet in enumerate(ALPHABETS):
        if t in alphabet:
            return n, alphabet.index(t)
    return None, None


def first_token(series):
    return '1' if series == 'd' else ALPHABETS[series][0]


def split_label(md):
    """`(метка, текст без метки)` или `(None, md)`. Жирная обёртка, начатая
    до метки и закрытая после баллов, остаётся у текста: `**2.(7 баллов)** …`
    → `2`, `**(7 баллов)** …`."""
    md = (md or '').lstrip()
    m = LABEL_RE.match(md)
    if not m:
        return None, md
    rest = md[m.end():]
    if m.group('pre') and not m.group('post'):
        rest = m.group('pre') + rest.lstrip()
    if m.group('op') and m.group('cl') == '.':
        return None, md
    return m.group('tok'), rest.lstrip()


def find_first_label(md, series, style):
    """Где в записи 1 стоит метка первого пункта — того же ряда и вида, что
    у записи 2. Ровно одно место в начале строки, иначе `None` (вручную)."""
    tok = first_token(series)
    hits = []
    for line in re.finditer(r'(?m)^', md):
        start = line.start()
        m = LABEL_RE.match(md, start)
        if not m or m.group('tok').lower() != tok:
            continue
        if bool(m.group('d1')) != style['d1'] or bool(m.group('word')) != style['word']:
            continue
        hits.append(m)
    return hits[0] if len(hits) == 1 else None


def convert_piece(text, answer='', solution='', resolve=None):
    """Один кусок через конвейер импорта, без поиска а)/б) внутри."""
    figures = []
    if resolve is not None:
        text, found = replace_images(text, resolve)
        figures += found
        solution, found = replace_images(solution, resolve)
        figures += found
    result = convert_for_import(statement=text, answer=answer, solution=solution,
                                existing_parts=[])
    return result['statement_md'], result['answer_md'], result['solution_md'], figures


def record_part(rec, text, resolve):
    """Подпункт из записи SolveHub: текст + варианты (у выбора), ответ, решение."""
    opts = parse_options(rec.get('check_options'))
    answer = format_answer(rec.get('correct_answer'), opts, [])
    block = options_block(rec.get('check_type'), opts)
    src = f'{text}\n\n{block}' if block else text
    return convert_piece(src, answer, rec.get('answer_md') or '', resolve)


def image_urls(*texts):
    return [u for t in texts for u in MD_IMAGE_RE.findall(t or '')
            if not u.startswith('data:')]


def part_digest(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True)
                          .encode('utf-8')).hexdigest()


# ── Данные ───────────────────────────────────────────────────────────────
def load_summary(path):
    with open(path, encoding='utf-8-sig') as fh:
        return {row['hash']: row for row in csv.DictReader(fh)}


def solvehub_source_id(hashes):
    """Источник SolveHub — по связи с задачами, а не по имени (в базе короткое
    тире, в импортёре длинное)."""
    counts = Counter()
    for chunk in bank_sync.chunks(sorted(hashes)):
        counts.update(SourceReference.objects.filter(problem_number__in=chunk)
                      .values_list('source_id', flat=True))
    if not counts:
        raise CommandError('Ни одна задача не нашлась по хэшам SolveHub.')
    (sid, n), *rest = counts.most_common()
    if rest and rest[0][1] * 10 > n:
        raise CommandError('Хэши SolveHub разошлись по источникам: %s' % counts.most_common(3))
    return sid


class Plan:
    """Итог разбора одной группы: план движка + списки для отчёта."""

    def __init__(self, group):
        self.group = group
        self.result = bank_sync.empty_plan(children=('parts', 'figures'))
        self.applicable, self.manual, self.blocked, self.done = [], [], [], []
        self.examples = []
        self.state = {}       # pid → полное состояние ДО (для отката и сверки)


class Command(BaseCommand):
    help = 'Вернуть потерянные пункты SolveHub (сухой прогон по умолчанию).'

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--dry-run', action='store_true', help='Только отчёт (так и по умолчанию).')
        mode.add_argument('--apply', action='store_true', help='Записать; снимок на каждую группу.')
        mode.add_argument('--revert', metavar='SNAPSHOT', help='Откатить по снимку.')
        parser.add_argument('--group', choices=('A', 'B', 'all'), default='all')
        parser.add_argument('--ids-file', help='Только эти id задач (по одному в строке).')
        parser.add_argument('--limit', type=int, help='Не больше N применимых задач в группе.')
        parser.add_argument('--include-edited', action='store_true',
                            help='Брать и правленные после импорта, если ответ и решение не менялись.')
        parser.add_argument('--data-dir', help='Перекачка (по умолчанию weconomics-data/solvehub_v2).')
        parser.add_argument('--old-dir', help='Августовская выгрузка с image_map.json '
                                              '(по умолчанию weconomics-data/solvehub).')
        parser.add_argument('--report-dir', '--report', dest='report',
                            help='Куда отчёт, списки и снимки '
                                 '(по умолчанию reports/bank_edits/solvehub_parts_restore).')

    # ── Точка входа ──────────────────────────────────────────────────────
    def handle(self, *args, **options):
        if options['revert']:
            return revert_and_report(Path(options['revert']), self.stdout, self.stderr)
        report_dir = Path(options['report'] or Path(settings.BASE_DIR) / 'reports' / 'bank_edits'
                          / 'solvehub_parts_restore')
        report_dir.mkdir(parents=True, exist_ok=True)
        groups = ['A', 'B'] if options['group'] == 'all' else [options['group']]
        before = (Problem.objects.count(), ProblemPart.objects.count(), ProblemFigure.objects.count())
        plans = self.build(groups, options)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        snapshots = {}
        if options['apply']:
            for plan in plans:
                if bank_sync.is_empty(plan.result):
                    continue
                snap = report_dir / ('snapshot_%s_%s.json' % (plan.group, stamp))
                state = report_dir / ('state_before_%s_%s.json' % (plan.group, stamp))
                state.write_text(json.dumps(plan.state, ensure_ascii=False, sort_keys=True),
                                 encoding='utf-8')
                bank_sync.execute(plan.result, ['parts', 'figures'], 'solvehub_parts_restore', snap)
                snapshots[plan.group] = (snap, state)
            if snapshots:
                invalidate_search(self.stderr)
        else:
            after = (Problem.objects.count(), ProblemPart.objects.count(), ProblemFigure.objects.count())
            if before != after:
                raise CommandError('СУХОЙ ПРОГОН НЕ ДОЛЖЕН ПИСАТЬ: было %s, стало %s' % (before, after))
        self.write_reports(plans, report_dir, stamp, options, snapshots)

    # ── Разбор ───────────────────────────────────────────────────────────
    def build(self, groups, options):
        new_dir = Path(options['data_dir'] or os.path.join(data_root(), 'solvehub_v2'))
        old_dir = Path(options['old_dir'] or os.path.join(data_root(), 'solvehub'))
        summary_rows = load_summary(new_dir / 'parts_summary.csv')
        lost = {h: r for h, r in summary_rows.items() if r['lost'] == 'True'}
        sid = solvehub_source_id(summary_rows)
        by_hash = dict(SourceReference.objects.filter(source_id=sid, problem_number__in=list(lost))
                       .values_list('problem_number', 'problem_id'))
        only = None
        if options['ids_file']:
            only = {int(x) for x in Path(options['ids_file']).read_text(encoding='utf-8').split()
                    if x.strip().isdigit()}
        self.old_records = solvehub_records(str(old_dir), only=set(lost))
        self.resolve = solvehub_resolver(str(old_dir))
        self.include_edited = options['include_edited']
        plans = []
        for group in groups:
            plan = Plan(group)
            want_zero = group == 'B'
            hashes = sorted((h for h, r in lost.items() if (r['db_parts_now'] == '0') == want_zero),
                            key=lambda h: (int(lost[h]['problem_id'] or 0), h))
            for h in hashes:
                pid = by_hash.get(h)
                if only is not None and pid not in only:
                    continue
                if options['limit'] is not None and len(plan.applicable) >= options['limit']:
                    break
                self.one(plan, h, pid, lost[h], new_dir, old_dir)
            plans.append(plan)
        return plans

    def one(self, plan, h, pid, row, new_dir, old_dir):
        reasons, missing_images = [], []

        def manual(*why):
            plan.manual.append({'group': plan.group, 'problem_id': pid or row['problem_id'],
                                'hash': h, 'reason': '; '.join(why)})

        if pid is None:
            return manual('задачи с этим хэшем нет в базе (SourceReference)')
        if str(pid) != row['problem_id']:
            return manual('id в базе %s ≠ id в таблице %s' % (pid, row['problem_id']))
        if pid in ALWAYS_MANUAL:
            return manual('всегда вручную (17 записей)')
        try:
            new = json.loads((new_dir / 'problems' / ('%s.json' % h)).read_text(encoding='utf-8'))
            old = json.loads((old_dir / 'problems' / ('%s.json' % h)).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            return manual('файл не прочитан: %s' % exc)
        recs = new.get('_parts') or []
        n = len(recs)

        # а) цепочка parent_hash
        hashes = [r.get('hash') for r in recs]
        chain_ok = (n >= 2 and recs[0].get('hash') == h and not recs[0].get('parent_hash')
                    and len(set(hashes)) == n
                    and all(recs[i].get('parent_hash') == recs[i - 1].get('hash') for i in range(1, n)))
        if not chain_ok:
            reasons.append('цепочка parent_hash невалидна')

        # запись 1 перекачки = августовской (кроме адресов картинок и имени вида проверки)
        first = recs[0] if recs else {}
        if (strip_urls(old.get('md')) != strip_urls(first.get('md'))
                or (old.get('check_options') or '') != (first.get('check_options') or '')
                or strip_urls(old.get('answer_md')) != strip_urls(first.get('answer_md'))):
            reasons.append('запись 1 на SolveHub изменилась после выгрузки августа')
        elif recs and _answer_value(old) != _answer_value(recs[0]):
            reasons.append('ответ записи 1 на SolveHub изменился после выгрузки августа')

        # метки записей 2..N — один ряд, по порядку
        labels, rests, style = [], [], None
        for k, rec in enumerate(recs[1:], start=2):
            tok, rest = split_label(rec.get('md') or '')
            series, idx = token_index(tok) if tok else (None, None)
            m = LABEL_RE.match((rec.get('md') or '').lstrip())
            if tok is None or series is None or idx != k - 1:
                reasons.append('метка записи %d не по порядку: %r' % (k, (rec.get('md') or '')[:25]))
                break
            if style is None:
                style = {'series': series, 'd1': bool(m.group('d1')), 'word': bool(m.group('word'))}
            elif series != style['series']:
                reasons.append('метки записей из разных рядов')
                break
            labels.append(tok)
            rests.append(rest)

        problem = Problem.objects.filter(pk=pid).values(
            'statement', 'answer', 'solution', 'problem_type', 'created_at', 'updated_at').first()
        db_parts = list(ProblemPart.objects.filter(problem_id=pid).order_by('order', 'pk')
                        .values('pk', 'label', 'statement', 'answer', 'solution', 'points', 'order'))
        record = self.old_records.get(h)
        if record is None:
            reasons.append('августовская запись не разобрана конвейером')

        edited = (problem['updated_at'] - problem['created_at']).total_seconds() > EDIT_GAP_SECONDS
        if edited and not self.include_edited:
            reasons.append('правилась после импорта (вручную; --include-edited)')
        if edited and self.include_edited and record is not None and (
                norm(problem['answer']) != norm(record.answer)
                or norm(problem['solution']) != norm(record.solution)):
            reasons.append('правилась после импорта: ответ или решение задачи изменены')

        if reasons:
            return manual(*reasons)

        # Новые подпункты из записей 2..N (общие у обеих групп).
        new_parts = []
        for k, (tok, rest) in enumerate(zip(labels, rests), start=2):
            rec = recs[k - 1]
            for url in image_urls(rest, rec.get('answer_md')):
                if not self.resolve(url):
                    missing_images.append(url)
            text, answer, solution, figs = record_part(rec, rest, self.resolve)
            new_parts.append({'label': tok, 'statement': text, 'answer': answer,
                              'solution': solution, 'figures': figs})

        if plan.group == 'A':
            target = self.plan_a(plan, pid, problem, db_parts, record, new_parts, reasons)
        else:
            target = self.plan_b(plan, pid, problem, db_parts, record, old, recs, style,
                                 new_parts, reasons)
        if reasons:
            return manual(*reasons)
        if target == 'done':
            plan.done.append(pid)
            return None

        statement, fresh, parts = target
        # Стала бы задача «тестом-игрой» (подпункты — варианты ответа)?
        fake_parts = [SimpleNamespace(label=p['label'], statement=p['statement'],
                                      answer=p['answer'], pk=i)
                      for i, p in enumerate(parts)]
        fake = SimpleNamespace(problem_type=problem['problem_type'], answer=problem['answer'],
                               parts=SimpleNamespace(all=lambda: fake_parts))
        try:
            game = testplay.game_of(fake, fake_parts)
        except Exception:  # noqa: BLE001 — сомнение = вручную
            game = 'ошибка'
        if game is not None:
            return manual('с новыми подпунктами задача стала бы тестом-игрой (подпункты = варианты)')

        if missing_images:
            plan.blocked.append({'group': plan.group, 'problem_id': pid, 'hash': h,
                                 'missing': len(set(missing_images)),
                                 'urls': ' '.join(sorted(set(missing_images)))})
            return None

        # План движка.
        state_parts = [{k: (str(v) if k == 'points' and v is not None else v)
                        for k, v in p.items()} for p in db_parts]
        plan.state[str(pid)] = {'statement': problem['statement'], 'answer': problem['answer'],
                                'solution': problem['solution'], 'parts': state_parts,
                                'digest': part_digest([problem['statement'], problem['answer'],
                                                       problem['solution'], state_parts])}
        if statement is not None:
            plan.result['problems'].append({'id': pid, 'old': {'statement': problem['statement']},
                                            'new': {'statement': statement}})
        start = (max(p['order'] for p in db_parts) + 1) if db_parts else 0
        have_figs = set(ProblemFigure.objects.filter(problem_id=pid).values_list('tikz_hash', flat=True))
        for i, part in enumerate(fresh):
            plan.result['children']['parts']['create'].append({
                'problem': pid, 'key': start + i,
                'row': {'label': part['label'], 'statement': part['statement'],
                        'answer': part['answer'], 'solution': part['solution'], 'points': None}})
            for digest, url in part.get('figures', ()):
                if digest in have_figs:
                    continue
                have_figs.add(digest)
                path = self.resolve.path_for(url)
                data = Path(path).read_bytes()
                plan.result['children']['figures']['create'].append({
                    'problem': pid, 'key': digest,
                    'row': {'source_field': 'import', 'tikz_source': url, 'svg': '',
                            'image_data': bank_sync.dump(ProblemFigure._meta.get_field('image_data'), data),
                            'content_type': sniff_content_type(data[:16]) or '', 'part': None}})
        plan.applicable.append({'group': plan.group, 'problem_id': pid, 'hash': h, 'records': n,
                                'parts_new': len(fresh), 'statement_changes': int(statement is not None),
                                'edited': int(edited), 'images': sum(len(p.get('figures', ())) for p in fresh),
                                'problem_type': problem['problem_type']})
        if len(plan.examples) < 3:
            plan.examples.append({'id': pid, 'old_statement': problem['statement'],
                                  'new_statement': statement, 'old_parts': db_parts, 'new_parts': fresh})
        return None

    def plan_a(self, plan, pid, problem, db_parts, record, new_parts, reasons):
        """A: в базе есть а) — добавляем только б), в)…"""
        full = len(db_parts) == 1 + len(new_parts)
        if full and len(db_parts) > 1:
            # Повторный прогон: уже добавленные совпадают с тем, что добавили бы.
            same = all(_same_part(db, new) for db, new in zip(db_parts[1:], new_parts))
            if same:
                return 'done'
        if len(db_parts) != 1:
            reasons.append('в базе %d подпунктов (ждём ровно 1: а))' % len(db_parts))
            return None
        if len(record.parts) != 1:
            reasons.append('импорт делил запись 1 на %d пунктов' % len(record.parts))
            return None
        if norm(db_parts[0]['statement']) != norm(record.parts[0][1]):
            reasons.append('текст подпункта а) в базе ≠ пункту а) SolveHub')
            return None
        return None, new_parts, [db_parts[0]] + new_parts

    def plan_b(self, plan, pid, problem, db_parts, record, old, recs, style, new_parts, reasons):
        """B: подпунктов нет — шапка + все пункты, включая а)."""
        md = old.get('md') or ''
        m = find_first_label(md, style['series'], style)
        if m is None:
            reasons.append('метка первого пункта в записи 1 не найдена однозначно')
            return None
        header_raw = md[:m.start()].rstrip()
        a_tok, a_rest = split_label(md[m.start():])
        header, _a, _s, _f = convert_piece(header_raw, resolve=self.resolve)
        a_text, a_answer, a_solution, a_figs = record_part(old, a_rest, self.resolve)
        parts = [{'label': a_tok, 'statement': a_text, 'answer': a_answer,
                  'solution': a_solution, 'figures': a_figs}] + new_parts
        if db_parts:
            if (len(db_parts) == len(parts) and problem['statement'] == header
                    and all(_same_part(db, new) for db, new in zip(db_parts, parts))):
                return 'done'
            reasons.append('в базе %d подпунктов (ждём 0)' % len(db_parts))
            return None
        if norm(problem['statement']) != norm(record.statement):
            reasons.append('условие в базе ≠ условию из записи 1 SolveHub')
            return None
        # Метку — тем же конвертером: `$а)$` в базе лежит как `$\text{а})$`.
        label_md = convert_piece(md[m.start():m.end()])[0]
        glued = norm(header) + norm(label_md) + norm(a_text)
        if glued != norm(problem['statement']):
            reasons.append('шапка + а) после конвертера не совпадают с условием')
            return None
        return header, parts, parts


    # ── Отчёт ────────────────────────────────────────────────────────────
    def write_reports(self, plans, report_dir, stamp, options, snapshots):
        applied = bool(options['apply'])
        prefix = ('applied_%s_' % stamp) if applied else ''
        out = {'mode': 'apply' if applied else 'dry-run', 'at': stamp, 'groups': {}}
        lines = ['# solvehub_parts_restore — %s' % ('запись (--apply)' if applied else 'сухой прогон'), '']
        if options['ids_file'] or options['limit'] is not None:
            lines += ['⚠️ ОХВАТ СУЖЕН: --ids-file=%s, --limit=%s' % (options['ids_file'], options['limit']), '']
        manual_rows, blocked_rows = [], []
        for plan in plans:
            ops = plan.result['children']
            g = {
                'applicable': len(plan.applicable), 'manual': len(plan.manual),
                'blocked_images': len(plan.blocked), 'already_done': len(plan.done),
                'parts_to_create': len(ops['parts']['create']),
                'statements_to_change': len(plan.result['problems']),
                'figures_to_create': len(ops['figures']['create']),
                'manual_reasons': Counter(_reason_key(m['reason']) for m in plan.manual),
            }
            if plan.group in snapshots:
                g['snapshot'] = str(snapshots[plan.group][0])
                g['state_before'] = str(snapshots[plan.group][1])
            out['groups'][plan.group] = g
            manual_rows += plan.manual
            blocked_rows += plan.blocked
            _write_csv(report_dir / ('%sapplicable_%s.csv' % (prefix, plan.group)), plan.applicable,
                       ['group', 'problem_id', 'hash', 'records', 'parts_new', 'statement_changes',
                        'edited', 'images', 'problem_type'])
            self.stdout.write('Группа %s: применимо %d, вручную %d, ждут картинок %d, уже сделано %d; '
                              'подпунктов добавить %d, условий изменить %d, картинок добавить %d'
                              % (plan.group, g['applicable'], g['manual'], g['blocked_images'],
                                 g['already_done'], g['parts_to_create'], g['statements_to_change'],
                                 g['figures_to_create']))
            for reason, n in g['manual_reasons'].most_common():
                self.stdout.write('    вручную: %s — %d' % (reason, n))
            if plan.group in snapshots:
                self.stdout.write('  Снимок для отката %s: %s' % (plan.group, snapshots[plan.group][0]))
            summary(plan.result, self.stdout)
            lines += ['## Группа %s' % plan.group, '']
            lines += ['- %s: %s' % (k, v) for k, v in g.items() if k != 'manual_reasons']
            lines += ['- вручную, %s: %d' % (r, n) for r, n in g['manual_reasons'].most_common()]
            lines += [''] + bank_sync.report_lines(plan.result, snapshot=g.get('snapshot'), examples=5) + ['']
            for ex in plan.examples:
                lines += ['### Пример #%d' % ex['id'], '', '**Условие было:**', '', '```',
                          ex['old_statement'], '```', '']
                if ex['new_statement'] is not None:
                    lines += ['**Условие станет:**', '', '```', ex['new_statement'], '```', '']
                lines += ['**Подпункты были:** %s' % [p['label'] for p in ex['old_parts']], '']
                for p in ex['new_parts']:
                    lines += ['**+ %s)** %s' % (p['label'], bank_sync.short(p['statement'], 300)),
                              '  ответ: %s' % bank_sync.short(p['answer'], 120),
                              '  решение: %s' % bank_sync.short(p['solution'], 120), '']
        _write_csv(report_dir / ('%smanual_list.csv' % prefix), manual_rows,
                   ['group', 'problem_id', 'hash', 'reason'])
        _write_csv(report_dir / ('%sblocked_images.csv' % prefix), blocked_rows,
                   ['group', 'problem_id', 'hash', 'missing', 'urls'])
        name = ('apply_summary_%s.json' % stamp) if applied else 'dryrun_summary.json'
        (report_dir / name).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
        (report_dir / ('REPORT_%s.md' % stamp)).write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.stdout.write('Отчёт: %s' % (report_dir / ('REPORT_%s.md' % stamp)))


def _reason_key(reason):
    """Причина без подробностей (для счёта): до двоеточия или скобки."""
    return '; '.join(re.split(r'[:(]', part)[0].strip() for part in reason.split('; '))


def _write_csv(path, rows, columns):
    with open(path, 'w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def _answer_value(rec):
    """Ответ записи без имени вида проверки (SolveHub переименовал
    `uncheckable` → `ai_graded`, значение то же)."""
    try:
        data = json.loads(rec.get('correct_answer') or 'null')
    except ValueError:
        return rec.get('correct_answer')
    return data.get('value') if isinstance(data, dict) else data


def _same_part(db, new):
    return (db['label'] == new['label'] and db['statement'] == new['statement']
            and db['answer'] == new['answer'] and db['solution'] == new['solution'])
