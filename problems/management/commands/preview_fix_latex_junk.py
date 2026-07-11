# -*- coding: utf-8 -*-
"""Подготовка к применению fix_latex_junk: dry-run со статистикой + визуальное
превью «до/после» для ревью в браузере. ТОЛЬКО ЧТЕНИЕ — ничего не пишет и не
меняет в базе (сама команда fix_latex_junk запускается тоже без --confirm).

Логика чистки не дублируется — импортируется clean_text из fix_latex_junk.py
(единственный источник истины). Рендер карточек — на CSS-классах и шаблоне
страницы из problems/diagnostics.py (тот же .math-content/.problem-statement/
.parts-list, что на реальной странице задачи, тот же подключённый KaTeX).

Результаты:
  reports/fix_latex_junk/dry_run_stats.md — цифры: всего/по паттернам/по
    источникам/топ-20 по объёму удаления + результаты машинных проверок.
  reports/fix_latex_junk/preview.html — карточки «до» / «после» для 15
    случайных задач (seed=2026) + всех задач из топ-20 + по 3 на паттерн.
"""
import io
import os
import random
import statistics
from collections import Counter, defaultdict

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils.html import escape

from problems.diagnostics import SEED, render_group_header, render_page
from problems.management.commands.fix_latex_junk import (
    SKIP_SHRINK_RATIO, clean_text, has_footnote,
)
from problems.models import Problem

REPORT_DIR = 'reports/fix_latex_junk'
STATS_MD = os.path.join(REPORT_DIR, 'dry_run_stats.md')
PREVIEW_HTML = os.path.join(REPORT_DIR, 'preview.html')
FOOTNOTE_DEFERRED_IDS = os.path.join(REPORT_DIR, 'footnote_deferred_ids.txt')
JUNK_COMMENT_MANUAL_IDS = os.path.join(REPORT_DIR, 'junk_comment_manual_ids.txt')

# footnote сюда не входит — паттерн выключен по умолчанию (см. fix_latex_junk.py),
# в этом прогоне он никогда не попадёт в applied. Учитывается отдельно как очередь.
PATTERN_LABELS = [
    ('pseudo_quotes', 'Псевдокавычки <<>>'),
    ('junk_comment', '%-комментарий'),
    ('inline_bullet', 'Инлайн-буллет •'),
]

RANDOM_SAMPLE_SIZE = 15
TOP_N = 20
PER_PATTERN_SAMPLE = 3
SHRINK_RATIO_THRESHOLD = 0.8

# Контрольные кейсы из прошлого ревью (reports/fix_latex_junk/approval_summary.md):
# #4853 — многословный %-комментарий чистился только на одно слово, оставляя
# битый огрызок «при вмешательстве»; #50125 — топ-1 по «удалению» в прошлом
# прогоне, но менялся ТОЛЬКО безусловной нормализацией пробелов (0 паттернов).
CONTROL_JUNK_COMMENT_ID = 4853
CONTROL_UNCHANGED_ID = 50125


# ── Сбор дифов по всем published-задачам (statement + все подпункты) ───────

class ProblemDiff(object):
    """Полная картина «до/после» по одной задаче: statement + ВСЕ подпункты
    (не только изменённые — чтобы карточка превью показывала задачу целиком,
    как она выглядит на сайте, а не разрозненные фрагменты)."""

    def __init__(self, problem, source_label):
        self.pid = problem.id
        self.title = problem.title
        self.source_label = source_label
        self.statement_before = problem.statement or ''
        self.statement_after = self.statement_before
        self.statement_patterns = []
        self.parts = []  # list of dict(label, before, after, patterns)
        self.changed_fields = []  # list of (field_label, before, after, patterns)

    @property
    def patterns_used(self):
        pats = set(self.statement_patterns)
        for part in self.parts:
            pats.update(part['patterns'])
        return pats

    @property
    def chars_removed(self):
        total = len(self.statement_before) - len(self.statement_after)
        for part in self.parts:
            total += len(part['before']) - len(part['after'])
        return total

    @property
    def touched(self):
        return bool(self.changed_fields)


def collect_diffs():
    """Повторяет логику самой fix_latex_junk шаг в шаг, включая guard
    SKIP_SHRINK_RATIO — иначе счётчик «задач затронуто» разойдётся с тем,
    что реально сделает --confirm (поле, срезанное guard'ом, не считается
    изменённым и в реальном прогоне остаётся как было). footnote выключен
    (include_footnote не передаём — по умолчанию False), но присутствие
    паттерна по всей базе всё равно фиксируется отдельно (footnote_ids) —
    это очередь на будущий перенос сносок в скобки, а не результат чистки.
    Аналогично junk_comment_manual_ids — задачи, где граница %-комментария
    неопределима (нет \\n после него), паттерн их не трогает вовсе."""
    qs = (
        Problem.objects
        .filter(status=Problem.Status.PUBLISHED)
        .prefetch_related('parts', 'source_references__source')
        .order_by('id')
        .iterator(chunk_size=2000)
    )

    diffs = []
    skipped_by_guard = []  # (pid, field) — попали под SKIP_SHRINK_RATIO, как в самой команде
    footnote_ids = set()
    junk_comment_manual_ids = set()

    for problem in qs:
        refs = list(problem.source_references.all())
        source_label = ', '.join(sorted({r.source.name for r in refs})) if refs else '—'
        diff = ProblemDiff(problem, source_label)

        stmt = problem.statement or ''
        if stmt:
            if has_footnote(stmt):
                footnote_ids.add(problem.id)
            cleaned, applied, needs_manual = clean_text(stmt)
            if needs_manual:
                junk_comment_manual_ids.add(problem.id)
            if cleaned != stmt:
                if len(cleaned) < SKIP_SHRINK_RATIO * len(stmt):
                    skipped_by_guard.append((problem.id, 'statement'))
                else:
                    diff.statement_after = cleaned
                    diff.statement_patterns = applied
                    diff.changed_fields.append(('statement', stmt, cleaned, applied))

        for part in problem.parts.all():
            ps = part.statement or ''
            before, after, patterns = ps, ps, []
            if ps:
                if has_footnote(ps):
                    footnote_ids.add(problem.id)
                cleaned, applied, needs_manual = clean_text(ps)
                if needs_manual:
                    junk_comment_manual_ids.add(problem.id)
                if cleaned != ps:
                    if len(cleaned) < SKIP_SHRINK_RATIO * len(ps):
                        skipped_by_guard.append((problem.id, 'part:{0}'.format(part.label)))
                    else:
                        after = cleaned
                        patterns = applied
                        diff.changed_fields.append(
                            ('part:{0}'.format(part.label), ps, cleaned, applied))
            diff.parts.append({
                'label': part.label, 'before': before, 'after': after, 'patterns': patterns,
            })

        if diff.touched:
            diffs.append(diff)

    return diffs, skipped_by_guard, footnote_ids, junk_comment_manual_ids


# ── Машинные проверки поверх dry-run ────────────────────────────────────────

def run_machine_checks(diffs):
    shrink_warnings = []  # (pid, field, ratio)
    dollar_mismatches = []  # (pid, field, before_count, after_count)

    for diff in diffs:
        for field, before, after, patterns in diff.changed_fields:
            ratio = len(after) / len(before) if before else 1.0
            if ratio < SHRINK_RATIO_THRESHOLD:
                shrink_warnings.append((diff.pid, field, ratio))
            if before.count('$') != after.count('$'):
                dollar_mismatches.append((diff.pid, field, before.count('$'), after.count('$')))

    return shrink_warnings, dollar_mismatches


def run_official_dry_run():
    """Реально запускает fix_latex_junk (без --confirm) и достаёт из его
    собственного вывода число затронутых задач — для сверки с независимым
    подсчётом этой команды."""
    buf = io.StringIO()
    call_command('fix_latex_junk', stdout=buf)
    output = buf.getvalue()
    touched = None
    for line in output.splitlines():
        if line.startswith('Затронуто задач:'):
            touched = int(line.split(':', 1)[1].strip().replace(',', '').replace('\xa0', ''))
    return output, touched


# ── HTML-превью (рендер как на сайте, из problems/diagnostics.py) ──────────

CARD_TEMPLATE = """
<section class="card" data-id="{pid}">
  <header class="card-head">
    <div class="card-head-top">
      <span class="card-id">#{pid}</span>
      <span class="card-source">{source_label}</span>
      <a class="card-link" href="{url}" target="_blank" rel="noopener">{url}</a>
    </div>
    <h2 class="card-title">{title}</h2>
    <div class="card-flags">{pattern_badges}</div>
  </header>
  <div class="card-cols">
    <div class="col">
      <div class="col-label">До (сейчас на сайте)</div>
      <div class="problem-statement">
        <div class="math-content ws-normal">{statement_before_html}</div>
      </div>
      {parts_before_html}
    </div>
    <div class="col">
      <div class="col-label">После чистки</div>
      <div class="problem-statement">
        <div class="math-content ws-normal">{statement_after_html}</div>
      </div>
      {parts_after_html}
    </div>
  </div>
</section>
"""


def _pattern_badges_html(patterns_used):
    if not patterns_used:
        return '<span class="badge badge-clean">без изменений</span>'
    label_map = dict(PATTERN_LABELS)
    return ''.join(
        '<span class="badge badge-{0}">{1}</span>'.format(key, escape(label_map.get(key, key)))
        for key in sorted(patterns_used)
    )


def _render_parts(parts, side):
    # type: (list, str) -> str
    """side — 'before' или 'after'."""
    rows = []
    for part in parts:
        text = part[side]
        if not text:
            continue
        changed = part['before'] != part['after']
        cls = 'part-item part-changed' if changed else 'part-item'
        rows.append(
            '<div class="{cls}"><div class="part-header">'
            '<span class="part-label">{label})</span>'
            '<div class="part-statement math-content ws-normal">{stmt}</div>'
            '</div></div>'.format(cls=cls, label=escape(part['label']), stmt=escape(text))
        )
    if not rows:
        return ''
    return '<div class="parts-intro">Подпункты</div><div class="parts-list">' + ''.join(rows) + '</div>'


def render_before_after_card(diff):
    url = 'http://127.0.0.1:8000/catalog/{0}/'.format(diff.pid)
    title = escape(diff.title) if diff.title else 'Задача #{0}'.format(diff.pid)
    return CARD_TEMPLATE.format(
        pid=diff.pid,
        source_label=escape(diff.source_label),
        url=url,
        title=title,
        pattern_badges=_pattern_badges_html(diff.patterns_used),
        statement_before_html=escape(diff.statement_before),
        statement_after_html=escape(diff.statement_after),
        parts_before_html=_render_parts(diff.parts, 'before'),
        parts_after_html=_render_parts(diff.parts, 'after'),
    )


EXTRA_CSS = """
.badge-footnote, .badge-junk_comment { background: #fbe8e6; color: #c0392b; }
.badge-pseudo_quotes, .badge-inline_bullet { background: #fdf1de; color: #b26b00; }
.part-changed { outline: 2px solid #BE185D33; }
"""


def render_preview_page(sample_diffs, selection_reasons, stats_summary_rows):
    cards_html = []
    for diff in sample_diffs:
        reasons = ', '.join(sorted(selection_reasons[diff.pid]))
        cards_html.append(render_group_header(
            '#{0} — {1}'.format(diff.pid, diff.title or '(без заголовка)'),
            'Почему в выборке: {0}. Удалено символов: {1}.'.format(reasons, diff.chars_removed),
        ))
        cards_html.append(render_before_after_card(diff))

    page = render_page(
        page_title='Превью чистки LaTeX-мусора — {0} карточек'.format(len(sample_diffs)),
        meta_line=(
            'Dry-run fix_latex_junk, seed={0}. {1} случайных + все из топ-{2} по объёму '
            'удаления + по {3} на паттерн (пересечения не дублируются). '
            'В базу ничего не записано.'
        ).format(SEED, RANDOM_SAMPLE_SIZE, TOP_N, PER_PATTERN_SAMPLE),
        summary_rows_html=stats_summary_rows,
        cards_html=''.join(cards_html),
    )
    # добавляем стили для бейджей паттернов перед закрывающим </style>
    page = page.replace('</style>', EXTRA_CSS + '</style>', 1)
    return page


# ── Команда ──────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = ('Dry-run fix_latex_junk + статистика + HTML-превью «до/после». '
            'Только чтение, в базу ничего не пишет.')

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)

        self.stdout.write('Запускаю официальный dry-run fix_latex_junk...')
        official_output, official_touched = run_official_dry_run()
        self.stdout.write(official_output)

        self.stdout.write('Независимый подсчёт для сверки и статистики...')
        diffs, skipped_by_guard, footnote_ids, junk_comment_manual_ids = collect_diffs()
        by_pid = {d.pid: d for d in diffs}
        total_touched = len(diffs)

        with open(FOOTNOTE_DEFERRED_IDS, 'w', encoding='utf-8') as f:
            for pid in sorted(footnote_ids):
                f.write('{0}\n'.format(pid))
        with open(JUNK_COMMENT_MANUAL_IDS, 'w', encoding='utf-8') as f:
            for pid in sorted(junk_comment_manual_ids):
                f.write('{0}\n'.format(pid))

        # ── статистика по паттернам ──
        pattern_counts = Counter()
        for diff in diffs:
            for field, before, after, patterns in diff.changed_fields:
                for pat in patterns:
                    pattern_counts[pat] += 1

        # ── статистика по источникам ──
        source_counts = Counter()
        for diff in diffs:
            for name in (diff.source_label.split(', ') if diff.source_label != '—' else ['(без источника)']):
                source_counts[name] += 1

        # ── топ-20 по объёму удаления ──
        top20 = sorted(diffs, key=lambda d: -d.chars_removed)[:TOP_N]

        # ── машинные проверки ──
        shrink_warnings, dollar_mismatches = run_machine_checks(diffs)
        count_match = (total_touched == official_touched)

        self._write_stats_md(
            total_touched, official_touched, count_match, pattern_counts,
            source_counts, top20, shrink_warnings, dollar_mismatches, skipped_by_guard,
            footnote_ids, junk_comment_manual_ids,
        )

        # ── выборка для превью ──
        rng_random = random.Random(SEED)
        touched_pids = sorted(by_pid.keys())
        random_sample = rng_random.sample(touched_pids, min(RANDOM_SAMPLE_SIZE, len(touched_pids)))

        selection_reasons = defaultdict(set)
        for pid in random_sample:
            selection_reasons[pid].add('случайная (seed={0})'.format(SEED))
        for diff in top20:
            selection_reasons[diff.pid].add('топ-20 по удалению')

        for pat_key, pat_label in PATTERN_LABELS:
            candidates = sorted(d.pid for d in diffs if pat_key in d.patterns_used)
            rng_pat = random.Random(SEED)
            picked = rng_pat.sample(candidates, min(PER_PATTERN_SAMPLE, len(candidates)))
            for pid in picked:
                selection_reasons[pid].add('паттерн {0}'.format(pat_key))

        # ── контрольные кейсы из прошлого ревью (approval_summary.md) ──
        if CONTROL_JUNK_COMMENT_ID in by_pid:
            selection_reasons[CONTROL_JUNK_COMMENT_ID].add(
                'контрольный кейс — многословный %-комментарий, был битым огрызком')

        reference_unchanged = None
        try:
            ref_problem = (
                Problem.objects
                .prefetch_related('parts', 'source_references__source')
                .get(id=CONTROL_UNCHANGED_ID)
            )
        except Problem.DoesNotExist:
            ref_problem = None
        if ref_problem is not None and ref_problem.id not in by_pid:
            refs = list(ref_problem.source_references.all())
            source_label = ', '.join(sorted({r.source.name for r in refs})) if refs else '—'
            reference_unchanged = ProblemDiff(ref_problem, source_label)
            for part in ref_problem.parts.all():
                ps = part.statement or ''
                reference_unchanged.parts.append(
                    {'label': part.label, 'before': ps, 'after': ps, 'patterns': []})
            selection_reasons[reference_unchanged.pid].add(
                'контрольный кейс — раньше менялся только нормализацией пробелов, теперь не меняется')

        selected_pids = sorted(selection_reasons.keys())
        sample_diffs = [
            by_pid[pid] if pid in by_pid else reference_unchanged
            for pid in selected_pids
        ]

        summary_rows = ''.join(
            '<tr><td>{0}</td><td>{1}</td></tr>'.format(escape(label), pattern_counts.get(key, 0))
            for key, label in PATTERN_LABELS
        )
        summary_rows += '<tr><td>Задач затронуто всего</td><td>{0}</td></tr>'.format(total_touched)
        summary_rows += (
            '<tr><td>footnote отложен (очередь, паттерн выключен)</td>'
            '<td>{0} задач → footnote_deferred_ids.txt</td></tr>'
        ).format(len(footnote_ids))
        summary_rows += (
            '<tr><td>junk_comment на ручной разбор (нет \\n после %)</td>'
            '<td>{0} задач → junk_comment_manual_ids.txt</td></tr>'
        ).format(len(junk_comment_manual_ids))

        page_html = render_preview_page(sample_diffs, selection_reasons, summary_rows)
        with open(PREVIEW_HTML, 'w', encoding='utf-8') as f:
            f.write(page_html)

        self.stdout.write(self.style.SUCCESS(
            'Готово. Задач затронуто: {0} (официальный dry-run сообщил {1}, совпадает: {2}).'.format(
                total_touched, official_touched, count_match,
            )
        ))
        self.stdout.write('В превью карточек: {0}'.format(len(sample_diffs)))
        self.stdout.write('Предупреждений о сжатии < {0:.0%}: {1}'.format(
            SHRINK_RATIO_THRESHOLD, len(shrink_warnings)))
        self.stdout.write('Несовпадений баланса $: {0}'.format(len(dollar_mismatches)))
        self.stdout.write('footnote отложен (очередь): {0} задач'.format(len(footnote_ids)))
        self.stdout.write('junk_comment на ручной разбор: {0} задач'.format(
            len(junk_comment_manual_ids)))
        self.stdout.write('Файлы:')
        self.stdout.write('  {0}'.format(STATS_MD))
        self.stdout.write('  {0}'.format(PREVIEW_HTML))
        self.stdout.write('  {0}'.format(FOOTNOTE_DEFERRED_IDS))
        self.stdout.write('  {0}'.format(JUNK_COMMENT_MANUAL_IDS))

    def _write_stats_md(self, total_touched, official_touched, count_match,
                        pattern_counts, source_counts, top20,
                        shrink_warnings, dollar_mismatches, skipped_by_guard,
                        footnote_ids, junk_comment_manual_ids):
        lines = []
        lines.append('# fix_latex_junk — статистика dry-run\n')
        lines.append('Пул: status=published (statement + все ProblemPart). В базу ничего не '
                      'записано (--confirm не передавался).\n')

        lines.append('## Сводка\n')
        lines.append('- Задач затронуто (независимый подсчёт этой команды): **{0:,}**'.format(
            total_touched).replace(',', ' '))
        lines.append('- Задач затронуто (по выводу самой команды fix_latex_junk): **{0}**'.format(
            official_touched))
        lines.append('- Числа совпадают: **{0}**\n'.format('да' if count_match else 'НЕТ — расхождение!'))
        lines.append('- Полей пропущено встроенным guard\'ом (сжатие > 50%, см. SKIP_SHRINK_RATIO '
                      'в fix_latex_junk.py): **{0}**, из них уникальных задач: **{1}** — эти поля не '
                      'меняются даже при --confirm.\n'.format(
                          len(skipped_by_guard), len({pid for pid, _ in skipped_by_guard})))
        lines.append('- footnote отложен целиком (паттерн выключен по умолчанию): **{0}** задач по '
                      'всей базе → [footnote_deferred_ids.txt](footnote_deferred_ids.txt) — очередь '
                      'на отдельную задачу «перенести сноски в подсказки/скобки».'.format(
                          len(footnote_ids)))
        lines.append('- junk_comment на ручной разбор (нет \\n после % — граница комментария '
                      'неопределима, текст не тронут): **{0}** задач → '
                      '[junk_comment_manual_ids.txt](junk_comment_manual_ids.txt).\n'.format(
                          len(junk_comment_manual_ids)))

        lines.append('## По паттернам (количество применений, не задач)\n')
        lines.append('| Паттерн | Применений |')
        lines.append('|---|---:|')
        for key, label in PATTERN_LABELS:
            lines.append('| {0} | {1} |'.format(label, pattern_counts.get(key, 0)))
        lines.append('')

        lines.append('## По источникам (задач затронуто, с пересечениями по нескольким источникам)\n')
        lines.append('| Источник | Задач |')
        lines.append('|---|---:|')
        for name, cnt in source_counts.most_common():
            lines.append('| {0} | {1} |'.format(name, cnt))
        lines.append('')

        lines.append('## Топ-20 по объёму удаления (символов)\n')
        lines.append('| # | ID | Удалено символов | Паттерны |')
        lines.append('|---:|---:|---:|---|')
        for i, diff in enumerate(top20, 1):
            lines.append('| {0} | [#{1}](http://127.0.0.1:8000/catalog/{1}/) | {2} | {3} |'.format(
                i, diff.pid, diff.chars_removed, ', '.join(sorted(diff.patterns_used)),
            ))
        lines.append('')

        lines.append('## Машинные проверки\n')
        lines.append('**Сжатие текста < {0:.0%} исходника** (кандидаты на пропуск, встроенная защита '
                      'команды — 50%, эта проверка строже, для ручной сверки):\n'.format(
                          SHRINK_RATIO_THRESHOLD))
        if shrink_warnings:
            for pid, field, ratio in shrink_warnings:
                lines.append('- #{0} ({1}): {2:.0%} от исходной длины'.format(pid, field, ratio))
        else:
            lines.append('- Не найдено ни одного случая — все изменения ≥ {0:.0%} исходника.'.format(
                SHRINK_RATIO_THRESHOLD))
        lines.append('')

        lines.append('**Баланс символов `$` (до/после)** — расхождение означает, что чистка задела '
                      'разметку формулы:\n')
        if dollar_mismatches:
            for pid, field, before_n, after_n in dollar_mismatches:
                lines.append('- #{0} ({1}): было {2} символов `$`, стало {3}'.format(
                    pid, field, before_n, after_n))
        else:
            lines.append('- Не найдено ни одного расхождения — баланс `$` сохранён везде.')
        lines.append('')

        with open(STATS_MD, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
