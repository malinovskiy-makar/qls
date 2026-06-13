"""
Исправляет формулы в задачах КСИГМА (Source #23).

PDF-экстракция (PyMuPDF) и OCR «сплющили» математику в обычный текст:
  - индексы потерялись:  Yt = It + Ct        (должно быть Y_t = I_t + C_t)
  - корень — отдельной строкой «√» или «p»:  80\np\nKt+1  →  80√(K_{t+1})
  - Unicode-символы:  − (U+2212), ⩽, ⩾, ·, ±, →, ≻, греческие буквы
  - звёздочка оптимума:  u∗, P ∗  →  u^*, P^*

Что делает команда:
  1. Склеивает разорванные корни (строка из одного «√» или «p»).
  2. Чисто-математические строки (есть =, ≤, √, …; нет русских слов 3+ букв)
     оборачивает в $...$ целиком.
  3. В прозе находит вкрапления математики (P0 = 100, δ = 1, 6√X)
     и оборачивает только их.
  4. Внутри $...$ конвертирует: индексы (v1 → v_1, Kt+1 → K_{t+1}),
     степени ()2 → ()^2), звёздочки (u∗ → u^*), корни (√17 → \\sqrt{17}),
     Unicode-символы и греческие буквы в LaTeX.
  5. Не трогает строки, уже содержащие $ или \\( — в т.ч. цены «200$».

Запуск:
    ./venv/bin/python manage.py fix_ksigma_formulas --dry-run
    ./venv/bin/python manage.py fix_ksigma_formulas
"""

import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart, Source

SOURCE_ID = 23   # КСИГМА — Решалки


# ─────────────────────────────────────────────────────────────────────────────
# Склейка разорванных корней (на уровне всего текста)
# ─────────────────────────────────────────────────────────────────────────────

# Строка, состоящая из одного «√» или «p» (PyMuPDF теряет глиф корня),
# между двумя строками математики → склеиваем в одну строку с «√».
_BROKEN_SQRT_RE = re.compile(
    r'[ \t]*\n[ \t]*[√p][ \t]*\n[ \t]*(?=[A-Za-z0-9(])'
)

# Разорванный нижний индекс после звёздочки: «p∗\n1,» → «p∗1,»
_BROKEN_STAR_SUB_RE = re.compile(r'∗[ \t]*\n[ \t]*(\d)')


def join_broken_lines(text: str) -> str:
    text = _BROKEN_SQRT_RE.sub('√', text)
    text = _BROKEN_STAR_SUB_RE.sub(r'∗\1', text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Конвертация содержимого математического спана в LaTeX
# ─────────────────────────────────────────────────────────────────────────────

GREEK_MAP = {
    'α': r'\alpha ', 'β': r'\beta ', 'γ': r'\gamma ', 'δ': r'\delta ',
    'ε': r'\varepsilon ', 'ζ': r'\zeta ', 'η': r'\eta ', 'θ': r'\theta ',
    'λ': r'\lambda ', 'µ': r'\mu ', 'μ': r'\mu ', 'ν': r'\nu ',
    'ξ': r'\xi ', 'π': r'\pi ', 'ρ': r'\rho ', 'σ': r'\sigma ',
    'τ': r'\tau ', 'φ': r'\varphi ', 'χ': r'\chi ', 'ψ': r'\psi ',
    'ω': r'\omega ',
    'Γ': r'\Gamma ', 'Δ': r'\Delta ', '∆': r'\Delta ', 'Θ': r'\Theta ',
    'Λ': r'\Lambda ', 'Π': r'\Pi ', 'Σ': r'\Sigma ', 'Φ': r'\Phi ',
    'Ω': r'\Omega ',
}

SYMBOL_MAP = {
    '⇐⇒': r'\Leftrightarrow ',
    '−': '-',                # U+2212 MINUS SIGN
    '⩽': r'\le ', '⩾': r'\ge ', '≤': r'\le ', '≥': r'\ge ',
    '≠': r'\ne ', '≈': r'\approx ', '⇡': r'\approx ',
    '·': r'\cdot ', '×': r'\times ', '±': r'\pm ',
    '→': r'\to ', '⇒': r'\Rightarrow ', '⇐': r'\Leftarrow ',
    '≻': r'\succ ', '≺': r'\prec ', '⪰': r'\succeq ', '≽': r'\succeq ',
    '∈': r'\in ', '∞': r'\infty ', '∅': r'\emptyset ',
    '⊆': r'\subseteq ',
    '%': r'\%',
}

_GREEK_CHARS = 'αβγδεζηθλµμνξπρστφχψωΓΔΘΛΠΣΦΩ'

# Индекс t+1: Kt+1 → K_{t+1}; основа — одиночная буква (не конец слова)
_SUB_T1_RE = re.compile(r'(?<![A-Za-z])([A-Za-z])t\+1(?![A-Za-z0-9])')
# Буквенный индекс: Yt → Y_t, Di → D_i, Qd → Q_d (не «const»: основа одиночная)
_SUB_LETTER_RE = re.compile(r'(?<![A-Za-z])([A-Za-z])([ijtds])(?![A-Za-z0-9])')
# Индексы экономических аббревиатур: AC1 → AC_1, MC2 → MC_2
_SUB_ABBR_RE = re.compile(
    r'(?<![A-Za-z])(ATC|AVC|AFC|AC|MC|TC|TR|MR|BR|CS|PS|MU|TU|AR|FC|VC)'
    r'(\d)(?![0-9])'
)
# Цифровой индекс: v1 → v_1, β0 → β_0, p1,2 → p_{1,2}
_SUB_DIGIT_RE = re.compile(
    r'(?<![A-Za-z\\' + _GREEK_CHARS + r'])'
    r'([A-Za-z' + _GREEK_CHARS + r'])(\d+(?:,\d+)*)(?![0-9])'
)
# Степень после скобки: )2 → )^2
_POW_PAREN_RE = re.compile(r'\)(\d)(?![\d.])')
# Звёздочка с индексом: p∗1 → p^*_1
_STAR_SUB_RE = re.compile(r'([A-Za-z])[ ]?∗(\d+)')
# Звёздочка оптимума: u∗ / P ∗ → u^*, P^* (юникодная ∗ — и после цифры/скобки)
_STAR_RE = re.compile(r'([A-Za-z0-9}])[ ]?∗')
# ASCII-звёздочка только сразу после буквы: Q* → Q^*
_STAR_ASCII_RE = re.compile(r'([A-Za-z])\*(?!\*)')
# Шляпка (U+02C6): ˆβ → \hat{β} (после конвертации индексов)
_HAT_RE = re.compile(r'ˆ[ ]?([A-Za-z' + _GREEK_CHARS + r'])')
# Квадрат в многочлене: −p2 + 140p → −p^2 + 140p (до правила индексов)
_POW_POLY_RE = re.compile(r'([A-Za-z])2(?=\s*[+−-]\s*\d+\1(?![A-Za-z0-9]))')
# Токен после √ (индексы уже сконвертированы): √17, √K_{t+1}, √0.5p
# Скобочные группы _{...}/^{...} захватываются целиком
_SQRT_TOKEN_RE = re.compile(
    r'√[ ]?((?:[A-Za-z0-9.]|_\{[^}]*\}|\^\{[^}]*\}|_[A-Za-z0-9]|\^[A-Za-z0-9*])+)'
)


def _sqrt_sub(m):
    tok = m.group(1)
    trail = ''
    while tok and tok[-1] == '.':
        tok = tok[:-1]
        trail += '.'
    return '\\sqrt{' + tok + '}' + trail


def _convert_sqrt_paren(s: str) -> str:
    """√(...) → \\sqrt{(...)токен} — с балансом скобок и хвостовым множителем."""
    out = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == '√':
            j = i + 1
            while j < n and s[j] == ' ':
                j += 1
            if j < n and s[j] == '(':
                depth = 0
                k = j
                while k < n:
                    if s[k] == '(':
                        depth += 1
                    elif s[k] == ')':
                        depth -= 1
                        if depth == 0:
                            break
                    k += 1
                if depth == 0:
                    # захватываем хвост вида Ht / H_t сразу после скобки
                    end = k + 1
                    while end < n and (s[end].isalnum() or s[end] in '_{}^'):
                        end += 1
                    out.append('\\sqrt{' + s[j:end] + '}')
                    i = end
                    continue
        out.append(s[i])
        i += 1
    return ''.join(out)


def convert_span(s: str) -> str:
    """Конвертирует текст математического спана в LaTeX."""
    s = s.replace('⇐⇒', SYMBOL_MAP['⇐⇒'])
    # ⇡ — повреждённый глиф: перед «=» или «(» это π (прибыль), иначе ≈
    s = re.sub(r'⇡(?=[A-Za-z0-9_^{} ]{0,6}[=(])', 'π', s)
    s = _SUB_T1_RE.sub(r'\1_{t+1}', s)
    s = _POW_POLY_RE.sub(r'\1^2', s)
    s = _SUB_ABBR_RE.sub(r'\1_\2', s)
    s = _SUB_LETTER_RE.sub(r'\1_\2', s)
    s = _SUB_DIGIT_RE.sub(
        lambda m: f'{m.group(1)}_{{{m.group(2)}}}' if len(m.group(2)) > 1
        else f'{m.group(1)}_{m.group(2)}',
        s,
    )
    # Кобб-Дуглас: )1−α → )^{1-α}, Kα → K^{α} (до общего правила степеней)
    s = re.sub(r'\)\s?1\s?[−-]\s?α', ')^{1-α}', s)
    s = re.sub(r'([A-Z])α', r'\1^{α}', s)
    s = _POW_PAREN_RE.sub(r')^\1', s)
    s = _STAR_SUB_RE.sub(r'\1^*_{\2}', s)
    s = _STAR_RE.sub(r'\1^*', s)
    s = _STAR_ASCII_RE.sub(r'\1^*', s)
    s = _HAT_RE.sub(r'\\hat{\1}', s)
    s = re.sub(r'(?<![A-Za-z\\])(ln|log|max|min|exp)(?![A-Za-z])', r'\\\1 ', s)
    s = _convert_sqrt_paren(s)
    s = _SQRT_TOKEN_RE.sub(_sqrt_sub, s)
    for ch, repl in GREEK_MAP.items():
        s = s.replace(ch, repl)
    for ch, repl in SYMBOL_MAP.items():
        if ch == '⇐⇒':
            continue
        s = s.replace(ch, repl)
    s = re.sub(r'[ ]{2,}', ' ', s)
    s = re.sub(r' +([_}])', r'\1', s)
    return s.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Поиск математики в строках
# ─────────────────────────────────────────────────────────────────────────────

# Якоря «это математика» (для чисто-математических строк и inline-спанов)
_ANCHOR_RE = re.compile(r'[=⩽⩾≤≥≠≈⇡√∗≻≺⪰≽⇒∈±→·]|[αβγδεζηθλµμνξπρστφχψωΓΔ∆ΘΛΠΣΦΩ]')

# Русское слово из 3+ букв → строка не является чистой математикой
_LONG_CYR_RE = re.compile(r'[а-яёА-ЯЁ]{3,}')

# Маркер подпункта в начале строки: «(a) », «(б) », «1) »
_ITEM_MARKER_RE = re.compile(r'^(\([a-zа-яёA-ZА-ЯЁ\d]\)\s+|[•‣]\s+)')

_CYR_SET = frozenset(
    'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя'
)

# Символы, разрешённые внутри inline-спана (кроме правил для , . ( ) и пробела).
# Кириллицы здесь НЕТ: спан в прозе останавливается на любом русском слове —
# иначе короткие «и», «в», «не» затягиваются внутрь $...$.
_SPAN_CHARS = frozenset(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    '0123456789'
    '+-*/^_=<>[]{}ˆ'
    '−⩽⩾≤≥≠≈⇡√∗≻≺⪰≽⇒⇐∈±→·×∞∅%'
    'αβγδεζηθλµμνξπρστφχψωΓΔ∆ΘΛΠΣΦΩ'
)


def _next_is_cyrillic(line: str, pos: int, direction: int) -> bool:
    """Первый непробельный символ в данном направлении — кириллица?"""
    i = pos
    while 0 <= i < len(line) and line[i] == ' ':
        i += direction
    return 0 <= i < len(line) and line[i] in _CYR_SET


def _find_inline_spans(line: str):
    """Возвращает список (start, end) математических спанов в строке прозы."""
    anchors = [m.start() for m in _ANCHOR_RE.finditer(line)]
    raw = []
    for pos in anchors:
        # ── влево ──
        start = pos
        depth = 0
        while start > 0:
            c = line[start - 1]
            if c == ')':
                depth += 1
            elif c == '(':
                if depth == 0:
                    break
                depth -= 1
            elif c == ',':
                # десятичная запятая (0,5) — продолжаем; иначе стоп
                if not (start - 2 >= 0 and line[start - 2].isdigit()
                        and start < len(line) and line[start].isdigit()):
                    break
            elif c == '.':
                if not (start - 2 >= 0 and line[start - 2].isdigit()
                        and start < len(line) and line[start].isdigit()):
                    break
            elif c == ' ':
                if _next_is_cyrillic(line, start - 2, -1):
                    break
            elif c not in _SPAN_CHARS:
                break
            start -= 1
        # ── вправо ──
        end = pos + 1
        depth = 0
        while end < len(line):
            c = line[end]
            if c == '(':
                # скобка с русским текстом внутри — не математика, стоп
                if _next_is_cyrillic(line, end + 1, +1):
                    break
                depth += 1
            elif c == ')':
                if depth == 0:
                    break
                depth -= 1
            elif c == ',':
                if depth == 0 and not (
                    end + 1 < len(line) and line[end + 1].isdigit()
                    and end - 1 >= 0 and line[end - 1].isdigit()
                ):
                    break
            elif c == '.':
                if not (end + 1 < len(line) and line[end + 1].isdigit()):
                    break
            elif c == ' ':
                if _next_is_cyrillic(line, end + 1, +1):
                    break
            elif c not in _SPAN_CHARS:
                break
            end += 1
        # Спан, обрезанный посреди токена (Scorei,9 → «9 ≥ 60»), не оборачиваем.
        # Обрезка «посреди токена» — это когда граница спана ВПЛОТНУЮ (без
        # пробела) примыкает к букве/цифре/запятой соседнего токена.
        if (start > 0 and line[start] != ' '
                and (line[start - 1].isalnum() or line[start - 1] == ',')):
            continue
        if (end < len(line) and line[end].isalnum()
                and end > 0 and line[end - 1] != ' '):
            continue
        raw.append((start, end))

    # объединяем пересекающиеся
    raw.sort()
    merged = []
    for s, e in raw:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return merged


def _has_math_content(s: str) -> bool:
    """В спане должно быть что-то кроме знаков: буква, цифра или греческая буква."""
    return any(c.isalnum() for c in s)


def _process_line(line: str) -> str:
    if not line.strip():
        return line
    if '$' in line or '\\(' in line or '\\[' in line:
        return line
    if not _ANCHOR_RE.search(line):
        return line

    stripped = line.strip()

    # ── Чисто-математическая строка: оборачиваем целиком ──
    if not _LONG_CYR_RE.search(stripped):
        m = _ITEM_MARKER_RE.match(stripped)
        marker = m.group(0) if m else ''
        body = stripped[len(marker):]
        content = body.rstrip(' .,;:?!')
        trailing = body[len(content):].rstrip()
        if content and _has_math_content(content) and _ANCHOR_RE.search(content):
            return f'{marker}${convert_span(content)}${trailing}'
        return line

    # ── Проза с вкраплениями математики ──
    spans = _find_inline_spans(line)
    if not spans:
        return line

    parts = []
    prev = 0
    for start, end in spans:
        raw = line[start:end]
        core = raw.strip()
        lead_ws = raw[: len(raw) - len(raw.lstrip())]
        trail_ws = raw[len(lead_ws) + len(core):]
        # Ведущие операторы (след обрезанной левой части: «= 0.7») — наружу
        body = core.lstrip('=<>+/·* ')
        lead = lead_ws + core[: len(core) - len(body)]
        content = body.rstrip(' .,;:?!')
        trailing = body[len(content):] + trail_ws
        if content and _has_math_content(content) and _ANCHOR_RE.search(content):
            parts.append(line[prev:start])
            parts.append(f'{lead}${convert_span(content)}${trailing}')
            prev = end
    parts.append(line[prev:])
    return ''.join(parts)


def clean_artifacts(text: str) -> str:
    """Убирает мусорные глифы PDF-экстракции (private-use area и пр.)."""
    # Невидимые фрагменты фигурных скобок систем уравнений (#49796)
    for ch in ('', '', '', '', '￾'):
        text = text.replace(ch, '')
    # Кавычки, превратившиеся в U+FFFF (#49772)
    text = text.replace('￿', '"')
    # Повреждённые глифы шрифта (#49770, #49695): ≤ и ∗
    text = text.replace('', '≤').replace('⇤', '∗')
    return text


def fix_text(text: str):
    """Полная обработка одного текстового поля. Возвращает (новый_текст, примеры)."""
    if not text:
        return text, []
    # Поле с валютным знаком «$» (цены «200$», «$100») не трогаем целиком:
    # новые пары $...$ спарились бы при рендере с валютными знаками.
    if '$' in text:
        return text, []
    text = clean_artifacts(text)
    text = join_broken_lines(text)
    lines = text.split('\n')
    new_lines = []
    examples = []
    for ln in lines:
        new = _process_line(ln)
        new_lines.append(new)
        if new != ln:
            examples.append((ln, new))
    return '\n'.join(new_lines), examples


# ─────────────────────────────────────────────────────────────────────────────
# Management command
# ─────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Исправляет формулы (оборачивает в $...$) в задачах КСИГМА (Source #23)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Показать примеры ДО/ПОСЛЕ без сохранения')
        parser.add_argument('--examples', type=int, default=15,
                            help='Сколько примеров показать (по умолчанию 15)')
        parser.add_argument('--limit', type=int, default=0,
                            help='Ограничить число задач (0 = все)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        max_examples = options['examples']
        limit = options['limit']

        try:
            source = Source.objects.get(pk=SOURCE_ID)
        except Source.DoesNotExist:
            self.stderr.write(f'Source #{SOURCE_ID} не найден.')
            return

        self.stdout.write(f'Источник: {source.name}')
        if dry_run:
            self.stdout.write(self.style.WARNING('── DRY-RUN: изменения не сохраняются ──'))

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
        all_examples = []   # (problem_id, field, before_line, after_line)

        with transaction.atomic():
            for problem in problems:
                fields = {}
                for field in ('statement', 'answer', 'solution'):
                    original = getattr(problem, field) or ''
                    if not original:
                        continue
                    new_text, exs = fix_text(original)
                    if new_text != original:
                        fields[field] = new_text
                        for b, a in exs:
                            all_examples.append((problem.id, field, b, a))

                if fields:
                    changed_problems += 1
                    if not dry_run:
                        Problem.objects.filter(pk=problem.pk).update(**fields)

                for part in problem.parts.all():
                    pfields = {}
                    for field in ('statement', 'answer'):
                        original = getattr(part, field) or ''
                        if not original:
                            continue
                        new_text, exs = fix_text(original)
                        if new_text != original:
                            pfields[field] = new_text
                            for b, a in exs:
                                all_examples.append(
                                    (problem.id, f'part({part.label}).{field}', b, a)
                                )
                    if pfields:
                        changed_parts += 1
                        if not dry_run:
                            ProblemPart.objects.filter(pk=part.pk).update(**pfields)

        # ── Вывод примеров ──
        self.stdout.write(f'\n{"─" * 70}')
        self.stdout.write(f'Примеры изменённых строк (первые {max_examples}):')
        shown = 0
        for pid, field, before, after in all_examples:
            if shown >= max_examples:
                break
            self.stdout.write(f'\n#{pid} [{field}]')
            self.stdout.write(f'  ДО:    {before.strip()[:160]}')
            self.stdout.write(f'  ПОСЛЕ: {after.strip()[:160]}')
            shown += 1

        self.stdout.write(f'\n{"─" * 70}')
        self.stdout.write(f'Изменённых строк всего: {len(all_examples)}')
        self.stdout.write(f'Задач затронуто: {changed_problems}, подпунктов: {changed_parts}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY-RUN: ничего не сохранено.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\nГотово. Сохранено задач: {changed_problems}, подпунктов: {changed_parts}.'
            ))
