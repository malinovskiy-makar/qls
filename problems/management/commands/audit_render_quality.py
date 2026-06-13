"""
Аудит качества рендеринга всех задач (ничего не меняет в базе).

Для каждого Problem и его ProblemPart, по полям statement / solution / answer,
проверяет эвристиками три уровня дефектов:

  critical:
    - replacement_char   — символ � (U+FFFD)
    - control_char       — управляющие символы (C0 кроме \\t\\n\\r, DEL)
    - unpaired_dollar    — нечётное число $ (не считая \\$)
    - math_brace         — несбалансированные {} внутри мат-спана
    - env_outside_math   — \\begin{tabular}/\\begin{minipage}/\\begin{center} и любое
                           другое LaTeX-окружение вне мат-спанов (KaTeX auto-render
                           обрабатывает только $/$$/\\(/\\[ — всё прочее видно сырым)
    - bad_env_in_math    — не поддерживаемое KaTeX окружение ВНУТРИ $...$/$$...$$
                           (например $$\\begin{tabular}…$$ — красная ошибка рендера)
    - cases_outside_math — \\begin{cases} вне $...$/$$...$$ (отдельный тип:
                           чинится конвертером fix_tabular_variants)
    - layout_command     — команды вёрстки в тексте: \\textcolor{, \\fcolorbox{,
                           \\colorbox{, \\hrulefill, \\textbackslash
    - comment_line       — строка-комментарий, начинающаяся с % (кроме \\% и
                           %XX hex-кодов URL)
  major:
    - naked_math         — строка с якорем математики (= ≤ ≥ ^ _ √ \\frac, греческие)
                           без $ и \\(
    - leak_marker        — «Решение:» / «Ответ:» / \\solution{ в начале строки statement
    - latex_fragment     — \\begin{} без \\end{}, незакрытый \\textbf{, голый \\item
    - math_italic        — math-italic Unicode (U+1D400–U+1D7FF) вне $
    - escaped_in_text    — \\_, \\&, \\# вне мат-спанов (KaTeX текст не трогает —
                           рендерятся со слэшем)
    - stub_statement     — «задача-огрызок»: statement < 80 символов, нет «?» и
                           глаголов найдите/определите/рассчитайте/вычислите (ru/en);
                           НЕ применяется к тестовым типам (problem_type «тест: …» —
                           короткое утверждение легитимно) и к задачам, у которых
                           суммарный текст подпунктов ≥ 80 символов
  minor (не влияет на «чистоту»):
    - short_statement    — statement задачи < 40 символов
    - truncated          — statement обрывается без знака конца предложения

«Чистая задача» = ноль critical и major по всем полям задачи и её подпунктов.

KaTeX-проверка через node НЕ выполняется: Node.js в системе отсутствует
(зафиксировано в отчёте) — работаем только эвристиками.

Выход: reports/quality_audit/<prefix>.md, <prefix>_issues.json.

Запуск:
    ./venv/bin/python manage.py audit_render_quality
    ./venv/bin/python manage.py audit_render_quality --prefix final
    ./venv/bin/python manage.py audit_render_quality --source-id 2
"""

import json
import os
import re
from collections import defaultdict

from django.core.management.base import BaseCommand

from problems.models import Problem

REPORT_DIR = 'reports/quality_audit'
N_EXAMPLES = 5

# ── эвристики ────────────────────────────────────────────────────────────────

REPLACEMENT_RE = re.compile('�')
CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# Якорь «похоже на математику» (для голых строк)
ANCHOR_RE = re.compile(
    r'[=≤≥⩽⩾√^_]|\\frac\b|\\le\b|\\ge\b'
    r'|[αβγδεζηθλµμνξπρστφχψωΓΔ∆ΘΛΠΣΦΩ]'
)

# math-italic / math-bold / math-digits Unicode
MATH_ITALIC_RE = re.compile('[\U0001D400-\U0001D7FF]')

# Маркеры утёкших решений/ответов в начале строки statement
LEAK_RE = re.compile(
    r'^\s*('
    r'\\solution\{'
    r'|\$\$\s*Решение\s*\$\$'
    r'|\\textbf\{\s*Решение'
    r'|Решение\s*[:.]?\s*$'
    r'|Решение\s*[:.]\s'
    r'|Ответы?\s*:'
    r')',
    re.MULTILINE,
)

BEGIN_RE = re.compile(r'\\begin\{([a-zA-Z*]+)\}')
END_RE = re.compile(r'\\end\{([a-zA-Z*]+)\}')
ITEM_RE = re.compile(r'\\item\b')
TEXTBF_RE = re.compile(r'\\textbf\{')

# Конец предложения для проверки обрыва: буква/запятая/тире в конце — обрыв
TRUNCATED_END_RE = re.compile(r'[А-Яа-яЁёA-Za-z,–—-]\s*$')

# ── детекторы «слепых зон» (сессия E) ────────────────────────────────────────

# Любое \begin{...} вне мат-спанов KaTeX auto-render не обработает.
ENV_OUTSIDE_RE = re.compile(r'\\begin\{([a-zA-Z*]+)\}')

# Окружения, которые KaTeX умеет ВНУТРИ математики; всё прочее внутри
# $...$/$$...$$ даёт красную ошибку рендера (\begin{tabular} в $$ — частый брак #14)
KATEX_MATH_ENVS = {
    'array', 'darray', 'matrix', 'matrix*', 'pmatrix', 'pmatrix*',
    'bmatrix', 'bmatrix*', 'Bmatrix', 'Bmatrix*', 'vmatrix', 'vmatrix*',
    'Vmatrix', 'Vmatrix*', 'smallmatrix', 'cases', 'dcases', 'rcases',
    'drcases', 'aligned', 'gathered', 'split', 'alignedat', 'CD',
    'equation', 'equation*', 'align', 'align*', 'gather', 'gather*',
    'alignat', 'alignat*',
}

# Команды вёрстки, видимые в тексте сырыми
LAYOUT_CMD_RE = re.compile(
    r'\\textcolor\{|\\fcolorbox\{|\\colorbox\{|\\hrulefill|\\textbackslash')

# Строка-комментарий: начинается с % + буква/слэш (исключает \% — слэш стоит
# ПЕРЕД %, и %D0-подобные hex-коды URL)
COMMENT_LINE_RE = re.compile(r'^\s*%\s*[A-Za-zА-Яа-яЁё\\]', re.MULTILINE)

# \_ \& \# вне математики — KaTeX текст не трогает, слэш виден
ESCAPED_IN_TEXT_RE = re.compile(r'\\[_&#]')

# Глаголы-сигналы полноценного условия (для детектора огрызков)
STUB_KEYWORD_RE = re.compile(
    r'\?|найди|определи|рассчита|вычисли|посчита'
    r'|find|determin|calculat|comput',
    re.IGNORECASE)

MATH_SPAN_RE = re.compile(
    r'\\\[(.+?)\\\]'          # \[ ... \]
    r'|\\\((.+?)\\\)'         # \( ... \)
    r'|\$\$(.+?)\$\$'         # $$ ... $$
    r'|\$([^$]+?)\$',         # $ ... $
    re.DOTALL,
)


def dollar_count(text):
    """Число $ без учёта экранированных \\$."""
    return text.replace('\\$', '').count('$')


def extract_math_spans(text):
    """[(содержимое, полный спан), ...] и текст с вырезанными спанами.
    Экранированные \\$ маскируются, чтобы не считаться границей спана."""
    masked = text.replace('\\$', '␦␦')
    spans = []

    def repl(m):
        body = next(g for g in m.groups() if g is not None)
        spans.append((body, m.group(0)))
        return ' '
    outside = MATH_SPAN_RE.sub(repl, masked)
    return spans, outside


def brace_balance(span_body):
    """Баланс {} в мат-спане (экранированные \\{ \\} не считаются)."""
    s = span_body.replace('\\{', '').replace('\\}', '')
    return s.count('{') - s.count('}')


def naked_math_lines(text):
    out = []
    for ln in text.split('\n'):
        if '$' in ln or '\\(' in ln or '\\[' in ln:
            continue
        if ANCHOR_RE.search(ln):
            out.append(ln)
    return out


def unclosed_textbf(text):
    """Есть ли \\textbf{ без закрывающей скобки (скан баланса от каждого)."""
    for m in TEXTBF_RE.finditer(text):
        depth = 1
        i = m.end()
        while i < len(text) and depth:
            c = text[i]
            if c == '{' and text[i - 1] != '\\':
                depth += 1
            elif c == '}' and text[i - 1] != '\\':
                depth -= 1
            i += 1
        if depth:
            return True
    return False


def check_field(field_name, text, is_statement=False):
    """Список дефектов одного поля: [(severity, type, snippet), ...]."""
    defects = []
    if not text:
        return defects

    # ── critical ──
    if REPLACEMENT_RE.search(text):
        defects.append(('critical', 'replacement_char',
                        _snippet(text, REPLACEMENT_RE)))
    if CONTROL_RE.search(text):
        defects.append(('critical', 'control_char', _snippet(text, CONTROL_RE)))

    odd_dollars = dollar_count(text) % 2 == 1
    if odd_dollars:
        defects.append(('critical', 'unpaired_dollar', text.strip()[:160]))

    spans, outside = extract_math_spans(text)
    if not odd_dollars:                      # при нечётных $ спаны ненадёжны
        for body, full in spans:
            if brace_balance(body) != 0:
                defects.append(('critical', 'math_brace', full[:160]))
                break

        # не поддерживаемое KaTeX окружение внутри мат-спана → красная ошибка
        for body, full in spans:
            bad = [m.group(1) for m in ENV_OUTSIDE_RE.finditer(body)
                   if m.group(1) not in KATEX_MATH_ENVS]
            if bad:
                defects.append(('critical', 'bad_env_in_math',
                                f"{{{bad[0]}}}: " + full.replace('\n', ' ⏎ ')[:140]))
                break

        # окружения вне мат-спанов (KaTeX их не рендерит — сырой LaTeX)
        envs = [m.group(1) for m in ENV_OUTSIDE_RE.finditer(outside)]
        if 'cases' in envs:
            defects.append(('critical', 'cases_outside_math',
                            _snippet(outside, re.compile(r'\\begin\{cases\}'))))
        other = [e for e in envs if e != 'cases']
        if other:
            defects.append(('critical', 'env_outside_math',
                            f"{{{other[0]}}}: " + _snippet(
                                outside,
                                re.compile(r'\\begin\{' + re.escape(other[0]) + r'\}'))))

        if LAYOUT_CMD_RE.search(outside):
            defects.append(('critical', 'layout_command',
                            _snippet(outside, LAYOUT_CMD_RE)))

        if ESCAPED_IN_TEXT_RE.search(outside):
            defects.append(('major', 'escaped_in_text',
                            _snippet(outside, ESCAPED_IN_TEXT_RE)))

    if COMMENT_LINE_RE.search(text):
        defects.append(('critical', 'comment_line',
                        _snippet(text, COMMENT_LINE_RE)))

    # ── major ──
    naked = naked_math_lines(text)
    if naked:
        defects.append(('major', 'naked_math', naked[0].strip()[:160]))

    if is_statement and LEAK_RE.search(text):
        m = LEAK_RE.search(text)
        defects.append(('major', 'leak_marker',
                        text[m.start():m.start() + 160].strip()))

    begins = defaultdict(int)
    for m in BEGIN_RE.finditer(text):
        begins[m.group(1)] += 1
    for m in END_RE.finditer(text):
        begins[m.group(1)] -= 1
    frag = None
    if any(v != 0 for v in begins.values()):
        frag = 'begin/end mismatch: ' + ', '.join(
            f'{k}{v:+d}' for k, v in begins.items() if v != 0)
    elif ITEM_RE.search(text) and not (
            'enumerate' in begins or 'itemize' in begins):
        frag = 'голый \\item: ' + _snippet(text, ITEM_RE)
    elif unclosed_textbf(text):
        frag = 'незакрытый \\textbf{'
    if frag:
        defects.append(('major', 'latex_fragment', frag[:160]))

    if MATH_ITALIC_RE.search(outside):
        defects.append(('major', 'math_italic', _snippet(outside, MATH_ITALIC_RE)))

    return defects


def _snippet(text, regex):
    m = regex.search(text)
    start = max(0, m.start() - 40)
    return text[start:m.start() + 80].replace('\n', ' ⏎ ').strip()[:160]


def audit_problem(problem, parts):
    """Все дефекты задачи: [(severity, type, field, snippet), ...]."""
    defects = []
    for field, text, is_st in (
            ('statement', problem.statement or '', True),
            ('solution', problem.solution or '', False),
            ('answer', problem.answer or '', False)):
        for sev, typ, snip in check_field(field, text, is_statement=is_st):
            defects.append((sev, typ, field, snip))

    for part in parts:
        for field, text in (('statement', part.statement or ''),
                            ('answer', part.answer or ''),
                            ('solution', part.solution or '')):
            for sev, typ, snip in check_field(field, text):
                defects.append((sev, typ, f'part({part.label}).{field}', snip))

    # ── major: задача-огрызок (только statement задачи) ──
    st = (problem.statement or '').strip()
    if (st and len(st) < 80 and not STUB_KEYWORD_RE.search(st)
            and not (problem.problem_type or '').startswith('тест')):
        parts_text = ' '.join((p.statement or '') for p in parts)
        if len(parts_text.strip()) < 80:
            defects.append(('major', 'stub_statement', 'statement', st[:160]))

    # ── minor (только statement задачи) ──
    if st and len(st) < 40:
        defects.append(('minor', 'short_statement', 'statement', st[:160]))
    if st and TRUNCATED_END_RE.search(st):
        defects.append(('minor', 'truncated', 'statement', st[-80:]))

    return defects


class Command(BaseCommand):
    help = 'Аудит качества рендеринга задач (только отчёт, ничего не меняет)'

    def add_arguments(self, parser):
        parser.add_argument('--prefix', default='baseline',
                            help='Префикс файлов отчёта (baseline → baseline.md)')
        parser.add_argument('--source-id', type=int, default=None,
                            help='Только один источник')
        parser.add_argument('--visible-only', action='store_true',
                            help='Только видимые в каталоге задачи '
                                 '(published, без флага шлюза)')

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)
        prefix = options['prefix']

        qs = (Problem.objects.all().order_by('id')
              .prefetch_related('parts', 'source_references'))
        if options['source_id']:
            qs = qs.filter(source_references__source_id=options['source_id']).distinct()
        if options['visible_only']:
            qs = qs.filter(status='published', needs_quality_review=False)

        # per-source агрегаты
        src_stats = {}     # sid -> dict
        src_names = {}
        issues = {}        # problem_id -> {source, status, defects}

        total = 0
        clean_total = 0

        for problem in qs.iterator(chunk_size=300):
            total += 1
            refs = list(problem.source_references.all())
            if refs:
                sid = refs[0].source_id
            else:
                sid = 0
            if sid not in src_stats:
                src_stats[sid] = {
                    'problems': 0, 'clean': 0,
                    'by_type': defaultdict(int),
                    'examples': defaultdict(list),
                    'critical_problems': 0, 'major_problems': 0,
                }
            s = src_stats[sid]
            s['problems'] += 1

            defects = audit_problem(problem, problem.parts.all())
            has_crit = any(d[0] == 'critical' for d in defects)
            has_major = any(d[0] == 'major' for d in defects)
            if has_crit:
                s['critical_problems'] += 1
            if has_major:
                s['major_problems'] += 1
            if not has_crit and not has_major:
                s['clean'] += 1
                clean_total += 1

            for sev, typ, field, snip in defects:
                s['by_type'][f'{sev}:{typ}'] += 1
                if len(s['examples'][f'{sev}:{typ}']) < N_EXAMPLES:
                    s['examples'][f'{sev}:{typ}'].append(
                        (problem.id, field, snip))

            if defects:
                issues[problem.id] = {
                    'source': sid,
                    'status': problem.status,
                    'defects': [list(d) for d in defects],
                }

            if total % 5000 == 0:
                self.stdout.write(f'  ...{total} задач обработано')

        # имена источников
        from problems.models import Source
        for src in Source.objects.all():
            src_names[src.id] = src.name
        src_names[0] = '(без источника)'

        # ── JSON ──
        json_path = os.path.join(REPORT_DIR, f'{prefix}_issues.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(issues, f, ensure_ascii=False, indent=0)

        # ── Markdown ──
        pct_total = 100.0 * clean_total / total if total else 0.0
        lines = [
            f'# Аудит рендеринга — {prefix}',
            '',
            'KaTeX-проверка через node НЕ выполнялась: Node.js в системе отсутствует.',
            'Все дефекты найдены эвристиками (см. docstring команды).',
            '',
            f'**Всего задач: {total}. Чистых (0 critical + 0 major): '
            f'{clean_total} ({pct_total:.1f}%).**',
            '',
            '| # | Источник | Задач | Чистых | % | С critical | С major |',
            '|---|----------|-------|--------|---|------------|---------|',
        ]
        chat_lines = []
        for sid in sorted(src_stats):
            s = src_stats[sid]
            pct = 100.0 * s['clean'] / s['problems']
            name = src_names.get(sid, f'#{sid}')
            lines.append(
                f"| {sid} | {name} | {s['problems']} | {s['clean']} "
                f"| {pct:.1f}% | {s['critical_problems']} | {s['major_problems']} |")
            chat_lines.append(
                f"#{sid:>2} {name[:42]:<42} задач={s['problems']:>6} "
                f"чистых={s['clean']:>6} ({pct:5.1f}%) "
                f"crit={s['critical_problems']:>5} major={s['major_problems']:>6}")

        for sid in sorted(src_stats):
            s = src_stats[sid]
            if not s['by_type']:
                continue
            lines.append('')
            lines.append(f"## #{sid} — {src_names.get(sid, '')}")
            lines.append('')
            for key in sorted(s['by_type']):
                lines.append(f"- **{key}**: {s['by_type'][key]}")
            for key in sorted(s['examples']):
                lines.append('')
                lines.append(f'### {key}')
                for pid, field, snip in s['examples'][key]:
                    snip = snip.replace('|', '\\|').replace('\n', ' ⏎ ')
                    lines.append(f"- `#{pid}` [{field}]: `{snip}`")

        md_path = os.path.join(REPORT_DIR, f'{prefix}.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

        for ln in chat_lines:
            self.stdout.write(ln)
        self.stdout.write(self.style.SUCCESS(
            f'\nВсего: {total}, чистых: {clean_total} ({pct_total:.1f}%). '
            f'Отчёты: {md_path}, {json_path}'))
