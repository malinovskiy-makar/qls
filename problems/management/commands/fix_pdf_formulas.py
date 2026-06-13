"""
Чинит отображение математики в задачах PDF-источников с русским текстом
(семейство B, рецепт fix_ksigma): оборачивает «голую» математику в $...$
и конвертирует PDF-артефакты в LaTeX (индексы Yt → Y_t, степени )2 → )^2,
Unicode-символы −⩽⩾·±→, греческие буквы, корни √).

Общая логика переиспользуется из fix_ksigma_formulas.py.
КСИГМА-специфичная чистка мусорных глифов (private-use area конкретных PDF)
включается флагом --ksigma-glyphs (по умолчанию ВЫКЛЮЧЕНА).

Безопасность (унаследовано):
  - поля, содержащие «$» (в т.ч. валюту «200$»), пропускаются целиком;
  - строки с уже размеченной математикой (\\(...\\)) не трогаются;
  - в прозе оборачиваются только спаны вокруг математических якорей.

Запуск:
    ./venv/bin/python manage.py fix_pdf_formulas --source-id 4 --dry-run --examples 15
    ./venv/bin/python manage.py fix_pdf_formulas --source-id 4
"""

import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart, Source
from problems.management.commands.fix_ksigma_formulas import (
    clean_artifacts, join_broken_lines, _process_line, convert_span,
)
from problems.management.commands.fix_matek_formulas import append_changed_ids

# Тире/en-dash (–, —) как знак минуса: только в «математическом» контексте —
# слева латиница/цифра/скобка/знак =, справа цифра/скобка/латиница.
# Русские слова (кириллица) в классы не входят → прозу «стрижки – дорого» не трогаем.
# ── Mathematical Alphanumeric Symbols (U+1D400…) → обычные буквы ─────────────
# PDF-экстракция (#19 ОЭШ и др.) даёт math-italic глифы 𝐿, 𝑄, 𝑥 — KaTeX-конвейеру
# нужны ASCII/греческие, иначе не работают правила индексов (𝐹1 → F_1).
# Конвертируем только bold/italic/bold-italic (script/fraktur/double-struck —
# самостоятельные символы, их не трогаем).

def _build_mathalpha_map():
    m = {}
    latin = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    for start in (0x1D400, 0x1D434, 0x1D468):       # bold, italic, bold-italic
        for i, ch in enumerate(latin):
            cp = start + i
            if cp == 0x1D455:                        # дырка: italic h = U+210E
                continue
            m[chr(cp)] = ch
    m['ℎ'] = 'h'
    greek_cap = 'ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΘΣΤΥΦΧΨΩ'          # ϴ → Θ
    greek_sm = 'αβγδεζηθικλμνξοπρςστυφχψω'
    for cap_start, sm_start in ((0x1D6A8, 0x1D6C2),  # bold
                                (0x1D6E2, 0x1D6FC),  # italic
                                (0x1D71C, 0x1D736)): # bold-italic
        for i, ch in enumerate(greek_cap):
            m[chr(cap_start + i)] = ch
        for i, ch in enumerate(greek_sm):
            m[chr(sm_start + i)] = ch
        # хвост блока: ∂ ϵ ϑ ϰ ϕ ϱ ϖ
        for j, ch in enumerate('∂εθκφρπ'):
            m[chr(sm_start + 25 + j)] = ch
    for start in (0x1D7CE, 0x1D7D8, 0x1D7E2, 0x1D7EC, 0x1D7F6):  # цифры
        for d in range(10):
            m[chr(start + d)] = str(d)
    return m


_MATHALPHA_MAP = str.maketrans(_build_mathalpha_map())


def normalize_mathalpha(text: str) -> str:
    return text.translate(_MATHALPHA_MAP)


_GREEK = 'αβγδεζηθλµμνξπρστφχψωΓΔ∆ΘΛΠΣΦΩ'
_DASH_CTX_RE = re.compile(
    r'(?<=[A-Za-z0-9)\]=' + _GREEK + r'])([ \t]*)[–—]([ \t]*)'
    r'(?=[0-9(A-Za-z' + _GREEK + r'])'
)


def normalize_dashes(text: str) -> str:
    """– → − (U+2212) в математическом контексте; дальше конвейер знает −."""
    return _DASH_CTX_RE.sub(r'\g<1>−\g<2>', text)


# Спан, оборванный на операторе («$Q_1 = 50 -$ Р» — переменная-кириллица
# осталась снаружи): такую строку лучше не трогать вовсе.
_TRAILING_OP_SPAN_RE = re.compile(r'\$[^$]*[=+\-−–*/<>·]\s*\$')

# Английская проза: рецепт fix_ksigma считает «нет кириллицы = математика»
# и оборачивал бы целые английские фразы («It means that IE=0…» → I_t means…).
_EN_WORD_RE = re.compile(r'(?<![A-Za-z])[a-z]{3,}(?![A-Za-z])')
_EN_MATH_OK = {'ln', 'log', 'max', 'min', 'exp', 'mpc', 'mps', 'sin', 'cos', 'tan'}
_EN_STOPWORDS = {
    'the', 'and', 'that', 'with', 'will', 'then', 'than', 'this', 'when',
    'where', 'which', 'are', 'was', 'were', 'has', 'have', 'his', 'her',
    'can', 'not', 'for', 'from', 'into', 'thus', 'hence', 'therefore',
    'because', 'while', 'since', 'let', 'given', 'find', 'answer', 'solution',
}


def _looks_english_prose(line: str) -> bool:
    words = [w for w in _EN_WORD_RE.findall(line) if w not in _EN_MATH_OK]
    if any(w in _EN_STOPWORDS for w in words):
        return True
    return len(words) >= 2


# Маркер подпункта «б) », «Ь) », «(а) » в начале строки — не затягивать в $...$
_EXTRA_MARKER_RE = re.compile(r'^\s*(?:\([A-Za-zА-ЯЁа-яё\d]\)|[A-Za-zА-ЯЁа-яё]\))\s+')

# «•» как знак умножения: «6•80», «5 • 30» → «·» (конвейер знает · → \cdot).
# Буллеты-списки в начале строки не трогаем (слева требуется цифра/скобка).
_BULLET_MUL_RE = re.compile(r'(?<=[\d)])\s*•\s*(?=[\d(A-Za-zА-Яа-яё])')


def process_line_safe(line: str) -> str:
    if _looks_english_prose(line):
        return line
    line_prepared = _BULLET_MUL_RE.sub('·', line)
    m = _EXTRA_MARKER_RE.match(line_prepared)
    if m:
        head, rest = line_prepared[:m.end()], line_prepared[m.end():]
        new = head + _process_line(rest)
    else:
        new = _process_line(line_prepared)
    if new != line and _TRAILING_OP_SPAN_RE.search(new):
        return line
    if new != line and not _spans_parens_ok(new):
        return line
    return new


def _spans_parens_ok(line: str) -> bool:
    """Во всех новых $...$ скобки () и {} должны сходиться
    (иначе «$) = 150$» или «$AC(7)=11_{$» из артефактов pandoc)."""
    segs = line.split('$')
    for i in range(1, len(segs), 2):
        if segs[i].count('(') != segs[i].count(')'):
            return False
        if segs[i].count('{') != segs[i].count('}'):
            return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Английский режим (--lang en, сессия B): КОНСЕРВАТИВНАЯ обёртка спанов.
#   - целые строки никогда не оборачиваются — только спаны вокруг якорей =≤≥→;
#   - алфавит спана: [A-Za-z0-9 +\-*/^_().,] + Unicode-операторы;
#   - спан со словарным английским словом отклоняется (ALL-CAPS аббревиатуры
#     MC/GDP/IS разрешены);
#   - поля с «$» (валюта — в AP повсюду) пропускаются целиком (общий guard).
# ─────────────────────────────────────────────────────────────────────────────

_EN_DICT = frozenset("""
the an and or but if then than that this these those there here is are was were
be been being am do does did done has have had having will would can could
shall should may might must not no nor yes of in on at by to from with without
within into onto over under above below between among through during before
after again once only also very much more most less least own same other
another such both each every few many some any all about against along around
because become becomes per either neither while when where which what who whom
whose why how since until till toward towards according respectively
suppose assume assumes given find finds calculate compute determine explain
identify show shows draw drawn label graph state describe define consider let
buy sell produce consume increase decrease rise fall change earn pay spend
save invest borrow lend make made take takes get gets use used using provide
provides receive receives include includes following result results lead leads
cause causes affect affects equal equals means
price prices cost costs market markets firm firms demand supply curve curves
quantity quantities output profit profits revenue revenues total marginal
average equilibrium consumer consumers producer producers surplus tax taxes
subsidy wage wages labor labour capital good goods service services country
countries trade exchange rate rates interest bank banks money income incomes
percent percentage unit units value values function functions point points
dollar dollars economy economic economics inflation unemployment growth
household households government policy policies level levels amount amounts
number numbers question questions answer answers product products resource
resources worker workers buyer buyers seller sellers
it as he we us go my up she her his him its they them people
thus hence therefore otherwise note that so
""".split())

# Строчные слова 4+ букв, разрешённые внутри мат-спана (квази-переменные)
_EN_MATH_WHITELIST = frozenset(
    'base height area slope ln log min max exp sin cos tan'.split())

_EN_ANCHOR_RE = re.compile(r'[=≤≥⩽⩾→]')
_EN_SPAN_CHARS = frozenset(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    '0123456789 +-*/^_().,=≤≥⩽⩾−→×·⋅√%∆Δ'
)
_EN_TOKEN_RE = re.compile(r'[A-Za-z]+')


def _en_span_rejected(content: str) -> bool:
    """Спан отклоняется, если содержит словарное английское слово
    (не-ALL-CAPS) или не содержит математического содержимого."""
    if not any(c.isalnum() for c in content):
        return True
    if not _EN_ANCHOR_RE.search(content):
        return True
    for tok in _EN_TOKEN_RE.findall(content):
        if not tok.isupper() and tok.lower() in _EN_DICT:
            return True
        # строчное слово 4+ букв вне белого списка — проза, не математика
        if tok.islower() and len(tok) >= 4 and tok not in _EN_MATH_WHITELIST:
            return True
    return False


def _find_inline_spans_en(line: str):
    """(start, end) спанов вокруг якорей =≤≥→ в английской строке."""
    raw = []
    for m in _EN_ANCHOR_RE.finditer(line):
        pos = m.start()
        start = pos
        while start > 0 and line[start - 1] in _EN_SPAN_CHARS:
            start -= 1
        end = pos + 1
        while end < len(line) and line[end] in _EN_SPAN_CHARS:
            end += 1
        # обрезка посреди токена — не оборачиваем
        if start > 0 and line[start] != ' ' and line[start - 1].isalnum():
            continue
        if (end < len(line) and line[end].isalnum()
                and end > 0 and line[end - 1] != ' '):
            continue
        raw.append((start, end))
    raw.sort()
    merged = []
    for s, e in raw:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return merged


def process_line_en(line: str) -> str:
    if not line.strip():
        return line
    if '$' in line or '\\(' in line or '\\[' in line:
        return line
    if not _EN_ANCHOR_RE.search(line):
        return line

    spans = _find_inline_spans_en(line)
    if not spans:
        return line

    parts = []
    prev = 0
    for start, end in spans:
        raw = line[start:end]
        core = raw.strip()
        lead_ws = raw[: len(raw) - len(raw.lstrip())]
        trail_ws = raw[len(lead_ws) + len(core):]
        body = core.lstrip('=<>+/·* ')
        lead = lead_ws + core[: len(core) - len(body)]
        content = body.rstrip(' .,;:?!')
        trailing = body[len(content):] + trail_ws
        if content and not _en_span_rejected(content):
            parts.append(line[prev:start])
            parts.append(f'{lead}${convert_span(content)}${trailing}')
            prev = end
    parts.append(line[prev:])
    new = ''.join(parts)
    if new != line and _TRAILING_OP_SPAN_RE.search(new):
        return line
    if new != line and not _spans_parens_ok(new):
        return line
    return new


def fix_text_en(text: str):
    """Обработка одного поля в английском режиме (--lang en)."""
    if not text:
        return text, []
    if '$' in text:                     # валюта в AP — поле целиком мимо
        return text, []
    if '\\[' in text or '\\begin{' in text:
        return text, []
    text = normalize_mathalpha(text)
    text = normalize_dashes(text)
    text = text.replace('⋅', '·')        # DOT OPERATOR → · (даёт \cdot)
    lines = text.split('\n')
    new_lines = []
    examples = []
    for ln in lines:
        new = process_line_en(ln)
        new_lines.append(new)
        if new != ln:
            examples.append((ln, new))
    return '\n'.join(new_lines), examples


def fix_text(text: str, ksigma_glyphs: bool = False):
    """Полная обработка одного поля. Возвращает (новый_текст, [(до, после)...])."""
    if not text:
        return text, []
    # Поле с «$» (валюта или уже размеченная математика) не трогаем целиком
    if '$' in text:
        return text, []
    # Поле с многострочной display-математикой (\[...\], \begin{aligned}…):
    # построчная обработка не видит её границ и вставила бы $ внутрь \text{}
    if '\\[' in text or '\\begin{' in text:
        return text, []
    if ksigma_glyphs:
        text = clean_artifacts(text)
    text = normalize_mathalpha(text)
    text = normalize_dashes(text)
    text = join_broken_lines(text)
    lines = text.split('\n')
    new_lines = []
    examples = []
    for ln in lines:
        new = process_line_safe(ln)
        new_lines.append(new)
        if new != ln:
            examples.append((ln, new))
    return '\n'.join(new_lines), examples


class Command(BaseCommand):
    help = 'Чинит формулы PDF-источников (оборачивает в $...$, конвертирует в LaTeX)'

    def add_arguments(self, parser):
        parser.add_argument('--source-id', type=int, required=True)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--examples', type=int, default=15)
        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--ksigma-glyphs', action='store_true',
                            help='Включить чистку мусорных глифов КСИГМА-PDF')
        parser.add_argument('--lang', choices=['ru', 'en'], default='ru',
                            help='en = консервативный английский режим (AP/IEO)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        max_examples = options['examples']
        limit = options['limit']
        glyphs = options['ksigma_glyphs']
        sid = options['source_id']
        lang = options['lang']

        def run_fix(original):
            if lang == 'en':
                return fix_text_en(original)
            return fix_text(original, glyphs)

        try:
            source = Source.objects.get(pk=sid)
        except Source.DoesNotExist:
            self.stderr.write(f'Source #{sid} не найден.')
            return

        self.stdout.write(f'Источник #{sid}: {source.name}')
        if dry_run:
            self.stdout.write(self.style.WARNING('── DRY-RUN ──'))

        problems = (
            Problem.objects
            .filter(source_references__source=source)
            .distinct()
            .prefetch_related('parts')
            .order_by('id')
        )
        if limit:
            problems = problems[:limit]

        changed_problems = 0
        changed_parts = 0
        changed_ids = set()
        all_examples = []

        with transaction.atomic():
            for problem in problems:
                fields = {}
                for field in ('statement', 'answer', 'solution'):
                    original = getattr(problem, field) or ''
                    if not original:
                        continue
                    new_text, exs = run_fix(original)
                    if new_text != original:
                        fields[field] = new_text
                        for b, a in exs:
                            all_examples.append((problem.id, field, b, a))
                if fields:
                    changed_problems += 1
                    changed_ids.add(problem.id)
                    if not dry_run:
                        Problem.objects.filter(pk=problem.pk).update(**fields)

                for part in problem.parts.all():
                    pfields = {}
                    for field in ('statement', 'answer'):
                        original = getattr(part, field) or ''
                        if not original:
                            continue
                        new_text, exs = run_fix(original)
                        if new_text != original:
                            pfields[field] = new_text
                            for b, a in exs:
                                all_examples.append(
                                    (problem.id, f'part({part.label}).{field}', b, a))
                    if pfields:
                        changed_parts += 1
                        changed_ids.add(problem.id)
                        if not dry_run:
                            ProblemPart.objects.filter(pk=part.pk).update(**pfields)

        self.stdout.write(f'\nПримеры (первые {max_examples}):')
        for pid, field, before, after in all_examples[:max_examples]:
            self.stdout.write(f'\n#{pid} [{field}]')
            self.stdout.write(f'  ДО:    {before.strip()[:160]}')
            self.stdout.write(f'  ПОСЛЕ: {after.strip()[:160]}')

        self.stdout.write(f'\nИзменённых строк: {len(all_examples)}; '
                          f'задач: {changed_problems}, подпунктов: {changed_parts}')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN: ничего не сохранено.'))
        else:
            append_changed_ids(changed_ids)
            self.stdout.write(self.style.SUCCESS(
                f'Готово. Сохранено задач: {changed_problems}, '
                f'подпунктов: {changed_parts}.'))
