"""
Чинит отображение математики в задачах ILE / iloveeconomics.ru (Source #2).

ОСОБЫЙ ПРОФИЛЬ — НЕ стандартный fix_pdf_formulas (профили не смешиваются,
общие модули не изменяются; отсюда только read-only импорты констант).

Ключевые отличия ILE (HTML-скрейп сайта) от PDF-источников:

1. Цифра сразу после переменной — чаще всего СТЕПЕНЬ (а не индекс, как в КСИГМА):
     ТС=Q3-4Q2+16Q  →  $TC=Q^3-4Q^2+16Q$      (полиномиальный контекст)
     P = 19 − Q2    →  $P = 19 - Q^2$          (одиночная цифра 2/3 → степень)
   НО есть и индексы — нумерованные рынки/фирмы/потребители:
     Q1=20-p/4? Q2=15-p/4 → $Q_1=…$? $Q_2=…$   (в поле есть и V1, и V2 → индексы)
     ТС1=20Q1             → $TC_1=20Q_1$        (цифры 0/1 → всегда индекс;
                                                 экон. аббревиатуры TC/TR/… → индекс)
2. Пробельные индексы И степени: «Q d =300-8P» → Q_d; «Q 3 -4Q 2 +8Q» → степени.
   Склейка «V c» только для одиночного суффикса; решение степень/индекс — после
   склейки теми же правилами. Висячая «V 1» в конце спана (нумерация «1.» из
   прозы) выносится наружу, если буква V встречается в спане один раз.
3. Кириллические двойники в формулах (ТС=…, Р=80, 5РA+4РB): внутри мат-спана
   А→A В→B Е→E К→K М→M Н→H О→O Р→P С→C Т→T Х→X (только ЗАГЛАВНЫЕ).
4. Дробные степени: 100L1/2 → 100L^{1/2}, 4K3/5L2/5 → 4K^{3/5}L^{2/5}.
5. «*» — умножение (a*P → a\\cdot P), в конце токена — оптимум (Q* → Q^*).
6. Тире –/— → минус в математическом контексте.

Безопасность (как в семействе B):
  - поля, содержащие «$» (валюта или уже размеченная математика), пропускаются
    ЦЕЛИКОМ — это 56% задач ILE;
  - английская проза не трогается; спаны в прозе — только вокруг якорей;
  - новые $...$ не должны содержать кириллицу (двойники транслитерируются,
    прочая кириллица в спан не попадает) — иначе строка откатывается;
  - спаны с несведёнными () и спаны, оборванные на операторе, откатываются;
  - двухзначные суффиксы (Q22 = Q_2², неразличимо) не конвертируются.

Запуск:
    ./venv/bin/python manage.py fix_ile_formulas --dry-run --examples 25
    ./venv/bin/python manage.py fix_ile_formulas
"""

import os
import random
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart, Source
# read-only импорты (общие модули НЕ изменяются)
from problems.management.commands.fix_ksigma_formulas import (
    GREEK_MAP, SYMBOL_MAP, _convert_sqrt_paren, _SQRT_TOKEN_RE, _sqrt_sub,
    _has_math_content, _ITEM_MARKER_RE, _LONG_CYR_RE,
)
from problems.management.commands.fix_pdf_formulas import (
    normalize_dashes, _looks_english_prose,
)

SOURCE_ID = 2
CHANGED_IDS_FILE_B = 'reports/quality_audit/changed_ids_B.txt'


def append_changed_ids_b(ids):
    """Дописывает id изменённых задач в файл сессии B (без дублей)."""
    if not ids:
        return
    os.makedirs(os.path.dirname(CHANGED_IDS_FILE_B), exist_ok=True)
    existing = set()
    if os.path.exists(CHANGED_IDS_FILE_B):
        with open(CHANGED_IDS_FILE_B, encoding='utf-8') as f:
            existing = {ln.strip() for ln in f if ln.strip()}
    new = sorted({str(i) for i in ids} - existing, key=int)
    if new:
        with open(CHANGED_IDS_FILE_B, 'a', encoding='utf-8') as f:
            f.write('\n'.join(new) + '\n')


# ─────────────────────────────────────────────────────────────────────────────
# Кириллические двойники (только заглавные — строчные «а/о/у/с» суть предлоги)
# ─────────────────────────────────────────────────────────────────────────────

CYR_LOOKALIKE = str.maketrans('АВЕКМНОРСТХ', 'ABEKMHOPCTX')
_CYR_LOOKALIKE_SET = frozenset('АВЕКМНОРСТХ')


# ─────────────────────────────────────────────────────────────────────────────
# Правила степеней/индексов ILE
# ─────────────────────────────────────────────────────────────────────────────

# Экономические аббревиатуры: цифра после них — всегда индекс (TC1 → TC_1)
_ABBR_IDX_RE = re.compile(
    r'(?<![A-Za-z])(ATC|AVC|AFC|AC|MC|TC|TR|MR|CS|PS|MU|TU|AR|FC|VC|TP|MP|AP)'
    r'(\d)(?![0-9])'
)

# Дробная степень: K3/5 → K^{3/5}, L1/2 → L^{1/2}
_FRAC_POW_RE = re.compile(r'(?<![A-Za-z])([A-Za-z])(\d)/(\d)(?![0-9])')

# Одиночный приклеенный суффикс-цифра: V2 (не V22 — двухзначные не трогаем)
_ATT_DIGIT_RE = re.compile(r'(?<![A-Za-z])([A-Za-z])(\d)(?![0-9])')

# Приклеенный буквенный индекс: Qd → Q_d, Sr → S_r (база — заглавная)
_ATT_LETTER_RE = re.compile(r'(?<![A-Za-z])([A-Z])([dsxyijtrw])(?![A-Za-z0-9])')

# Склейка пробельного суффикса: «Q 3» → «Q3», «Q d» → «Qd», «-24C 2» → «-24C2»
_GLUE_DIGIT_RE = re.compile(r'(?<![A-Za-z])([A-Za-z]) (\d)(?![\d.,])')
_GLUE_LETTER_RE = re.compile(r'(?<![A-Za-z])([A-Z]) ([dsxyijtrw])(?![A-Za-zА-Яа-яЁё0-9])')

# Висячая «V d» в конце спана (нумерация прозы «… 1.»)
_TRAIL_SPACED_DIGIT_RE = re.compile(r'([A-Za-z]) (\d{1,2})$')

# Умножение звёздочкой: a*P → a\cdot P; остаток V* → V^*
_STAR_MUL_RE = re.compile(r'(?<=[A-Za-z0-9)])\*(?=\s*[A-Za-z0-9(])')
_STAR_OPT_RE = re.compile(r'(?<=[A-Za-z0-9)])\*')

_PLUSMINUS_RE = re.compile(r'[+\-−]')


def _enum_letters(field_text: str) -> set:
    """Буквы V, для которых поле содержит и V1, и V2 (нумерация объектов) —
    их цифровые суффиксы считаем ИНДЕКСАМИ."""
    t = field_text.translate(CYR_LOOKALIKE)
    out = set()
    for L in set(re.findall(r'(?<![A-Za-z])([A-Za-z])[12](?![0-9])', t)):
        if (re.search(rf'(?<![A-Za-z]){re.escape(L)}1(?![0-9])', t)
                and re.search(rf'(?<![A-Za-z]){re.escape(L)}2(?![0-9])', t)):
            out.add(L)
    return out


def _poly_letters(span: str) -> set:
    """Буквы V в полиномиальном контексте (V^d внутри суммы/разности):
    ≥2 токена V<цифра>, либо токен V<цифра> + одиночная V, при наличии +/−."""
    if not _PLUSMINUS_RE.search(span):
        return set()
    out = set()
    for L in set(re.findall(r'(?<![A-Za-z])([A-Za-z])\d', span)):
        n_digit = len(re.findall(rf'(?<![A-Za-z]){re.escape(L)}\d', span))
        n_alone = len(re.findall(rf'(?<![A-Za-z]){re.escape(L)}(?![A-Za-z0-9])', span))
        if n_digit >= 2 or (n_digit >= 1 and n_alone >= 1):
            out.add(L)
    return out


def _digit_sub_factory(class_map):
    """Решение «степень или индекс» для голого V<цифра> по классификации задачи
    (сессия C); дефолт для некласифицированного: 0/1 → индекс, иначе степень."""
    def _digit_sub(m):
        base, d = m.group(1), m.group(2)
        cls = class_map.get(base)
        if cls == 'index':
            return f'{base}_{d}'
        if cls == 'power':
            return f'{base}^{d}'
        return f'{base}_{d}' if d in '01' else f'{base}^{d}'
    return _digit_sub


def convert_span_ile(s: str, class_map: dict) -> str:
    """Конвертирует содержимое мат-спана ILE в LaTeX (классификация — по задаче)."""
    s = s.translate(CYR_LOOKALIKE)
    # склейка пробельных суффиксов
    s = _GLUE_LETTER_RE.sub(r'\1\2', s)
    s = _GLUE_DIGIT_RE.sub(r'\1\2', s)
    # аббревиатуры: всегда индекс
    s = _ABBR_IDX_RE.sub(r'\1_\2', s)
    # дробные степени
    s = _FRAC_POW_RE.sub(r'\1^{\2/\3}', s)
    s = _ATT_DIGIT_RE.sub(_digit_sub_factory(class_map), s)
    s = _ATT_LETTER_RE.sub(r'\1_\2', s)
    # умножение / оптимум
    s = _STAR_MUL_RE.sub(r'\\cdot ', s)
    s = _STAR_OPT_RE.sub(r'^*', s)
    # корни
    s = _convert_sqrt_paren(s)
    s = _SQRT_TOKEN_RE.sub(_sqrt_sub, s)
    # Кобб-Дуглас с альфой
    s = re.sub(r'\)\s?1\s?[−-]\s?α', ')^{1-α}', s)
    s = re.sub(r'([A-Z])α', r'\1^{α}', s)
    for ch, repl in GREEK_MAP.items():
        s = s.replace(ch, repl)
    for ch, repl in SYMBOL_MAP.items():
        if ch == '⇐⇒':
            continue
        s = s.replace(ch, repl)
    s = re.sub(r'[ ]{2,}', ' ', s)
    return s.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Сессия C — контекстный классификатор «степень vs индекс» по ЗАДАЧЕ целиком.
# Правила (подтверждены предметником):
#   ИНДЕКСЫ:  буква с ≥2 разными цифрами (X1 и X2 — товары/рынки), КРОМЕ
#             полиномиального контекста; словесные сигналы нумерации
#             («товар 1», «два рынка», «первая фирма»); цифры 0/1 одиночно.
#   СТЕПЕНИ:  полином (Q3-4Q2+16Q — та же буква, ± рядом, цифры не {1,2,3}
#             с единицей); мультипликативная связка разных букв (X2Y, X1Y2Z3 —
#             в т.ч. с цифрой 1!); одиночная комбинация без индексных
#             сигналов — ПО УМОЛЧАНИЮ СТЕПЕНЬ.
#   НЕЯСНО:   конфликт правил (и нумерация, и связка) — не трогаем.
# ─────────────────────────────────────────────────────────────────────────────

# Уже размеченное X_2 / X^2 / X_{2} / X^{2} → плоское X2 (для анализа).
# СТРОГО: ^{1/2} (дробная степень) не считается «X1»
_MARKUP_VD_RE = re.compile(r'([A-Za-z])[_^](?:\{(\d)\}|(\d)(?![0-9]))')

_WORD_INDEX_RE = re.compile(
    r'(?:товар|рынок|рынк|фирм|стран|групп|регион|завод|потребител|производител'
    r'|компани|банк|город|сектор|отрасл|период|вид)\w*\s*№?\s*\d'
    r'|(?:два|две|двух|три|трёх|трех|четыре|четырёх)\s+'
    r'(?:товар|рынк|фирм|стран|групп|регион|завод|потребител|производител|вид|период)'
    r'|(?:перв|втор|трет|четвёрт|четверт)\w+\s+'
    r'(?:товар|рынк|фирм|стран|групп|регион|завод|потребител|производител|период)',
    re.IGNORECASE,
)

_UTILITY_CTX_RE = re.compile(
    r'полезн|производственн\w+\s+функц|функци\w+\s+производств|Кобб',
    re.IGNORECASE,
)

_ECON_ABBRS = frozenset('ATC AVC AFC AC MC TC TR MR CS PS MU TU AR FC VC TP MP AP'.split())

_VD_TOKEN_RE = re.compile(r'(?<![A-Za-z])([A-Za-z])(\d)(?![0-9])')
# связка: подряд буквы с цифрами без разделителей (X2Y, X1Y2Z3, P2Q)
_CHAIN_RE = re.compile(r'(?<![A-Za-z0-9])((?:[A-Za-z]\d?){2,})(?![A-Za-z0-9])')


def _analysis_text(problem_text: str) -> str:
    t = problem_text.translate(CYR_LOOKALIKE)
    return _MARKUP_VD_RE.sub(
        lambda m: m.group(1) + (m.group(2) or m.group(3)), t)


def classify_letters(problem_text: str):
    """Классифицирует буквы с цифровыми суффиксами по контексту задачи.
    Возвращает (class_map, evidence): class_map[V] ∈ {'power','index','ambiguous'}."""
    t = _analysis_text(problem_text)
    class_map, evidence = {}, {}

    tokens = _VD_TOKEN_RE.findall(t)          # [(буква, цифра), ...]
    if not tokens:
        return class_map, evidence
    digits_by_letter = {}
    for v, d in tokens:
        digits_by_letter.setdefault(v, set()).add(d)

    # ── полином: та же буква ≥2 раза с ± между (без русской прозы между —
    #    дефис «Q0 - объем» не считается), цифры без 0/1 (V⁰/V¹ не пишут) ──
    poly = set()
    for v, ds in digits_by_letter.items():
        if '0' in ds or '1' in ds:
            continue
        positions = [m.start() for m in re.finditer(
            rf'(?<![A-Za-z]){re.escape(v)}\d(?![0-9])', t)]
        if len(positions) < 2:
            continue
        linked = any(
            (b - a) < 60
            and _PLUSMINUS_RE.search(t[a:b])
            and not re.search(r'[а-яА-ЯёЁ]{3,}', t[a:b])
            for a, b in zip(positions, positions[1:]))
        if linked:
            poly.add(v)

    # ── мультипликативные связки разных букв (X2Y, X1Y2Z3) ──
    chain = set()
    for m in _CHAIN_RE.finditer(t):
        seg = m.group(1)
        toks = re.findall(r'([A-Za-z])(\d?)', seg)
        letters_in_seg = [v for v, _ in toks]
        with_digit = [v for v, d in toks if d]
        if not with_digit or len(letters_in_seg) < 2:
            continue
        if ''.join(letters_in_seg) in _ECON_ABBRS:      # TC1, AVC2 — индексы
            continue
        chain.update(with_digit)

    has_word_signal = bool(_WORD_INDEX_RE.search(t))
    has_utility = bool(_UTILITY_CTX_RE.search(t))

    for v, ds in digits_by_letter.items():
        enum = len(ds - {'0'}) >= 2 and v not in poly
        if v in poly:
            class_map[v] = 'power'
            evidence[v] = f'полином ({v} с цифрами {sorted(ds)}, ± рядом)'
        elif enum and v in chain:
            class_map[v] = 'ambiguous'
            evidence[v] = (f'конфликт: нумерация ({sorted(ds)}) и '
                           f'мультипликативная связка одновременно')
        elif enum:
            class_map[v] = 'index'
            evidence[v] = f'нумерация объектов: {v} с цифрами {sorted(ds)}'
        elif v in chain:
            class_map[v] = 'power'
            evidence[v] = ('мультипликативная связка букв'
                           + (' + контекст полезности/производства'
                              if has_utility else ''))
        elif has_word_signal:
            class_map[v] = 'index'
            evidence[v] = 'словесный сигнал нумерации (товар N/два рынка/…)'
        elif ds <= {'0', '1'}:
            class_map[v] = 'index'
            evidence[v] = 'одиночные 0/1 — x⁰/x¹ не пишут'
        else:
            class_map[v] = 'power'
            evidence[v] = 'одиночная комбинация без индексных сигналов (дефолт)'
    return class_map, evidence


def problem_full_text(problem, parts) -> str:
    """Все текстовые поля задачи одной строкой (для классификации)."""
    chunks = [problem.statement or '', problem.solution or '',
              problem.answer or '']
    for part in parts:
        chunks += [part.statement or '', part.answer or '',
                   getattr(part, 'solution', '') or '']
    return '\n'.join(chunks)


# ─────────────────────────────────────────────────────────────────────────────
# Поиск спанов (адаптация ksigma: + заглавные кириллические двойники)
# ─────────────────────────────────────────────────────────────────────────────

_ANCHOR_RE = re.compile(r'[=⩽⩾≤≥≠≈√→·±]')

_CYR_SET = frozenset(
    'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя'
)

_SPAN_CHARS = frozenset(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    '0123456789'
    '+-*/^_=<>[]{}'
    '−⩽⩾≤≥≠≈√±→·×∞%'
    'αβγδεζηθλµμνξπρστφχψωΓΔ∆ΘΛΠΣΦΩ'
    'АВЕКМНОРСТХ'                       # кириллические двойники (заглавные)
)


def _stop_word_cyr(line: str, pos: int, direction: int) -> bool:
    """Первый непробельный токен в данном направлении — русская проза?
    Слово целиком из заглавных двойников длиной ≤3 (ТС, Р, АС) — НЕ проза."""
    i = pos
    while 0 <= i < len(line) and line[i] == ' ':
        i += direction
    if not (0 <= i < len(line)) or line[i] not in _CYR_SET:
        return False
    # читаем кириллическое слово
    j = i
    word = []
    while 0 <= j < len(line) and line[j] in _CYR_SET:
        word.append(line[j])
        j += direction
    w = ''.join(reversed(word) if direction < 0 else word)
    if len(w) <= 3 and all(c in _CYR_LOOKALIKE_SET for c in w):
        return False
    return True


def _find_inline_spans(line: str):
    """(start, end) математических спанов в строке прозы (профиль ILE)."""
    anchors = [m.start() for m in _ANCHOR_RE.finditer(line)]
    raw = []
    for pos in anchors:
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
                if not (start - 2 >= 0 and line[start - 2].isdigit()
                        and start < len(line) and line[start].isdigit()):
                    break
            elif c == '.':
                if not (start - 2 >= 0 and line[start - 2].isdigit()
                        and start < len(line) and line[start].isdigit()):
                    break
            elif c == ' ':
                if _stop_word_cyr(line, start - 2, -1):
                    break
            elif c not in _SPAN_CHARS:
                break
            start -= 1
        end = pos + 1
        depth = 0
        while end < len(line):
            c = line[end]
            if c == '(':
                if _stop_word_cyr(line, end + 1, +1):
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
                if _stop_word_cyr(line, end + 1, +1):
                    break
            elif c not in _SPAN_CHARS:
                break
            end += 1
        # обрезка посреди токена — не оборачиваем
        if (start > 0 and line[start] != ' '
                and (line[start - 1].isalnum() or line[start - 1] == ',')):
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


# Спан, оборванный на операторе: «$Q_1 = 50 -$» — откат строки
_TRAILING_OP_SPAN_RE = re.compile(r'\$[^$]*[=+\-−–*/<>·]\s*\$')
_CYR_IN_SPAN_RE = re.compile(r'\$[^$]*[А-Яа-яЁё][^$]*\$')


def _spans_ok(line: str) -> bool:
    """Инварианты новых $...$: () сходятся, кириллицы нет, не оборван."""
    if _TRAILING_OP_SPAN_RE.search(line):
        return False
    if _CYR_IN_SPAN_RE.search(line):
        return False
    segs = line.split('$')
    for i in range(1, len(segs), 2):
        if segs[i].count('(') != segs[i].count(')'):
            return False
        if segs[i].count('{') != segs[i].count('}'):
            return False
    return True


def _wrap_content(body: str, class_map, next_char: str = ''):
    """Готовит содержимое спана: ведущие операторы и висячая нумерация — наружу.
    Возвращает (lead, content, trailing) или None, если оборачивать нечего."""
    stripped = body.lstrip('=<>+/·* ')
    lead = body[: len(body) - len(stripped)]
    content = stripped.rstrip(' .,;:?!')
    trailing = stripped[len(content):]
    # висячая «V d» в конце (нумерация прозы), если V в спане один раз
    m = _TRAIL_SPACED_DIGIT_RE.search(content)
    if m:
        letter = m.group(1)
        if len(re.findall(rf'(?<![A-Za-z]){re.escape(letter)}(?![A-Za-z])',
                          content)) <= 1:
            trailing = content[m.end(1):] + trailing
            content = content[:m.end(1)]
    # висячая буква-метка следующей формулы («…-1.9p X» перед «:») — наружу
    if next_char == ':':
        m2 = re.search(r' [A-Za-z]$', content)
        if m2:
            trailing = content[m2.start():] + trailing
            content = content[:m2.start()]
    if not content or not _has_math_content(content):
        return None
    if not _ANCHOR_RE.search(content):
        return None
    return lead, content, trailing


def process_line_ile(line: str, class_map: dict) -> str:
    if not line.strip():
        return line
    if '$' in line or '\\(' in line or '\\[' in line:
        return line
    if not _ANCHOR_RE.search(line):
        return line
    if _looks_english_prose(line):
        return line

    stripped = line.strip()

    # ── Чисто-математическая строка (нет русских слов 3+ букв,
    #    кроме заглавных двойников): оборачиваем целиком ──
    no_dbl = stripped.translate(CYR_LOOKALIKE)
    if not _LONG_CYR_RE.search(no_dbl):
        m = _ITEM_MARKER_RE.match(stripped)
        marker = m.group(0) if m else ''
        body = stripped[len(marker):]
        wrapped = _wrap_content(body, class_map)
        if wrapped:
            lead, content, trailing = wrapped
            new = f'{marker}{lead}${convert_span_ile(content, class_map)}${trailing}'
            return new if _spans_ok(new) else line
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
        nxt = line[end] if end < len(line) else ''
        wrapped = _wrap_content(core, class_map, next_char=nxt)
        if wrapped:
            lead, content, trailing = wrapped
            parts.append(line[prev:start])
            parts.append(
                f'{lead_ws}{lead}${convert_span_ile(content, class_map)}$'
                f'{trailing}{trail_ws}')
            prev = end
    parts.append(line[prev:])
    new = ''.join(parts)
    return new if _spans_ok(new) else line


# ─────────────────────────────────────────────────────────────────────────────
# Сессия C — переклассификация уже размеченного и дообёртка пропущенного
# ─────────────────────────────────────────────────────────────────────────────

_SPAN_RE = re.compile(r'\$([^$]+)\$')
# Внутри спана: X_2 / X_{2} (но не X_{t+1}, не X_{1,2}) и X^2 / X^{2}
_IN_SUB_BRACED_RE = re.compile(r'([A-Za-z])_\{(\d)\}')
_IN_SUB_RE = re.compile(r'([A-Za-z])_(\d)(?![0-9])')
_IN_POW_BRACED_RE = re.compile(r'([A-Za-z])\^\{(\d)\}')
_IN_POW_RE = re.compile(r'([A-Za-z])\^(\d)(?![0-9])')


def reclassify_span(span: str, class_map: dict) -> str:
    """Меняет _N ↔ ^N внутри готового спана по классификации задачи;
    голые V<цифра> внутри спана тоже конвертирует."""
    def to_pow(m):
        v, d = m.group(1), m.group(2)
        return f'{v}^{d}' if class_map.get(v) == 'power' else m.group(0)

    def to_sub(m):
        v, d = m.group(1), m.group(2)
        return f'{v}_{d}' if class_map.get(v) == 'index' else m.group(0)

    s = _IN_SUB_BRACED_RE.sub(to_pow, span)
    s = _IN_SUB_RE.sub(to_pow, s)
    s = _IN_POW_BRACED_RE.sub(to_sub, s)
    s = _IN_POW_RE.sub(to_sub, s)
    # голые V<цифра> внутри спана: аббревиатуры/дроби — как раньше
    s = s.translate(CYR_LOOKALIKE)
    s = _ABBR_IDX_RE.sub(r'\1_\2', s)
    s = _FRAC_POW_RE.sub(r'\1^{\2/\3}', s)
    s = _ATT_DIGIT_RE.sub(_digit_sub_factory(class_map), s)
    return s


# Одиночный токен V<цифра> в прозе без якоря («полезность U2», «цена P0»):
# латиница или заглавный двойник, не часть слова/разметки
_STANDALONE_VD_RE = re.compile(
    r'(?<![A-Za-z0-9_^{\\$])([A-Za-zАВЕКМНОРСТХ])(\d)(?![0-9A-Za-zА-Яа-яё])')


_OPERATOR_CHARS = frozenset('=+-−–*/^_<>')


def _wrap_standalone_tokens(seg: str, class_map: dict, confident: set) -> str:
    """Оборачивает одиночные V<цифра> в $...$ — ТОЛЬКО для букв с уверенной
    (не дефолтной) классификацией и ТОЛЬКО вне формул: токен, соседствующий
    с оператором (=+-*/…), — часть формулы, его не трогаем (иначе крадём
    первый член полинома: «ТС=$Q^3$-4Q2…»)."""
    if 'http' in seg or 'www.' in seg:      # URL: %D0%97 — не математика!
        return seg

    def repl(m):
        v = m.group(1).translate(CYR_LOOKALIKE)
        d = m.group(2)
        cls = class_map.get(v)
        if v not in confident or cls not in ('index', 'power'):
            return m.group(0)
        # вплотную «%» (URL-кодировка, проценты) — не трогаем
        if (m.start() > 0 and seg[m.start() - 1] == '%') or \
           (m.end() < len(seg) and seg[m.end()] == '%'):
            return m.group(0)
        # сосед-оператор (через пробелы) слева или справа → часть формулы
        i = m.start() - 1
        while i >= 0 and seg[i] == ' ':
            i -= 1
        if i >= 0 and seg[i] in _OPERATOR_CHARS:
            return m.group(0)
        j = m.end()
        while j < len(seg) and seg[j] == ' ':
            j += 1
        if j < len(seg) and seg[j] in _OPERATOR_CHARS:
            return m.group(0)
        return f'${v}_{d}$' if cls == 'index' else f'${v}^{d}$'
    return _STANDALONE_VD_RE.sub(repl, seg)


def _wrap_outside_segments(line: str, class_map: dict) -> str:
    """Оборачивает голую математику в сегментах строки ВНЕ существующих $...$."""
    if line.count('$') % 2 == 1:
        return line                     # непарные $ — не трогаем
    parts = line.split('$')
    for i in range(0, len(parts), 2):   # чётные индексы — вне спанов
        seg = parts[i]
        if not seg.strip() or not _ANCHOR_RE.search(seg):
            continue
        if _looks_english_prose(seg):
            continue
        spans = _find_inline_spans(seg)
        if not spans:
            continue
        out, prev = [], 0
        for start, end in spans:
            raw = seg[start:end]
            core = raw.strip()
            lead_ws = raw[: len(raw) - len(raw.lstrip())]
            trail_ws = raw[len(lead_ws) + len(core):]
            nxt = seg[end] if end < len(seg) else ''
            wrapped = _wrap_content(core, class_map, next_char=nxt)
            if wrapped:
                lead, content, trailing = wrapped
                out.append(seg[prev:start])
                out.append(f'{lead_ws}{lead}${convert_span_ile(content, class_map)}$'
                           f'{trailing}{trail_ws}')
                prev = end
        out.append(seg[prev:])
        parts[i] = ''.join(out)
    new = '$'.join(parts)
    return new if _spans_ok(new) else line


def _standalone_pass(line: str, class_map: dict, confident: set) -> str:
    if not confident or line.count('$') % 2 == 1:
        return line
    parts = line.split('$')
    for i in range(0, len(parts), 2):
        parts[i] = _wrap_standalone_tokens(parts[i], class_map, confident)
    new = '$'.join(parts)
    return new if _spans_ok(new) else line


def fix_field_c(text: str, class_map: dict, backup_text: str, confident: set):
    """Сессия C: обработка одного поля.
    Поля, где $ был уже в бэкапе ДО наших чисток (оригинальная TeX-разметка
    сайта ILE), НЕ трогаем — авторскую разметку не переклассифицируем.
    Возвращает (новый_текст, [(до, после)...])."""
    if not text:
        return text, []
    if '$' in (backup_text or ''):
        return text, []
    text = normalize_dashes(text)
    # разрыв формулы переносом строки: «U=\nX1Y2Z3» → «U= X1Y2Z3»
    text = re.sub(r'=[ \t]*\n[ \t]*(?=[A-Za-z0-9(])', '= ', text)
    lines = text.split('\n')
    new_lines, examples = [], []
    for ln in lines:
        new = ln
        if '$' in new:
            # 1) переклассификация внутри наших спанов
            if new.count('$') % 2 == 0:
                new = _SPAN_RE.sub(
                    lambda m: '$' + reclassify_span(m.group(1), class_map) + '$',
                    new)
                if not _spans_ok(new):
                    new = ln
            # 2) дообёртка голого вне спанов
            new = _wrap_outside_segments(new, class_map)
        else:
            new = process_line_ile(new, class_map)
        # 3) одиночные V<цифра> в прозе (только уверенная классификация)
        new = _standalone_pass(new, class_map, confident)
        new_lines.append(new)
        if new != ln:
            examples.append((ln, new))
    return '\n'.join(new_lines), examples


# ─────────────────────────────────────────────────────────────────────────────

BACKUP_DB = 'backups/db_backup_before_ile.sqlite3'
CHANGED_IDS_FILE_C = 'reports/quality_audit/changed_ids_C.txt'
AMBIGUOUS_FILE = 'reports/quality_audit/ile_ambiguous_ids.txt'


def append_ids_file(path, ids):
    if not ids:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing = set()
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            existing = {ln.strip() for ln in f if ln.strip()}
    new = sorted({str(i) for i in ids} - existing, key=int)
    if new:
        with open(path, 'a', encoding='utf-8') as f:
            f.write('\n'.join(new) + '\n')


def _load_backup(sid):
    """Тексты полей из бэкапа ДО наших чисток: задачи и подпункты источника."""
    import sqlite3
    con = sqlite3.connect(BACKUP_DB)
    probs = {r[0]: {'statement': r[1] or '', 'solution': r[2] or '',
                    'answer': r[3] or ''}
             for r in con.execute(
                 'SELECT p.id, p.statement, p.solution, p.answer '
                 'FROM problems_problem p '
                 'JOIN problems_sourcereference sr ON sr.problem_id = p.id '
                 f'WHERE sr.source_id = {int(sid)}')}
    parts = {r[0]: {'statement': r[1] or '', 'answer': r[2] or '',
                    'solution': r[3] or ''}
             for r in con.execute(
                 'SELECT pp.id, pp.statement, pp.answer, pp.solution '
                 'FROM problems_problempart pp '
                 'JOIN problems_sourcereference sr ON sr.problem_id = pp.problem_id '
                 f'WHERE sr.source_id = {int(sid)}')}
    con.close()
    return probs, parts


class Command(BaseCommand):
    help = ('Сессия C: степень vs индекс по контексту задачи — '
            'переклассификация _N↔^N в наших спанах + обёртка пропущенного')

    def add_arguments(self, parser):
        parser.add_argument('--source-id', type=int, default=SOURCE_ID)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--examples', type=int, default=25)
        parser.add_argument('--show-ids', default='',
                            help='id задач, которые показать обязательно (через запятую)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        max_examples = options['examples']
        show_ids = {int(x) for x in options['show_ids'].split(',') if x.strip()}
        sid = options['source_id']

        source = Source.objects.get(pk=sid)
        self.stdout.write(f'Источник #{sid}: {source.name}')
        if dry_run:
            self.stdout.write(self.style.WARNING('── DRY-RUN ──'))

        backup_probs, backup_parts = _load_backup(sid)

        problems = (
            Problem.objects
            .filter(source_references__source=source)
            .distinct()
            .prefetch_related('parts')
            .order_by('id')
        )

        changed_problems = 0
        changed_parts = 0
        changed_ids = set()
        ambiguous_ids = []
        all_examples = []

        with transaction.atomic():
            for problem in problems:
                parts = list(problem.parts.all())
                class_map, ev = classify_letters(problem_full_text(problem, parts))
                if 'ambiguous' in class_map.values():
                    ambiguous_ids.append(problem.id)
                    continue
                # Для обёртки одиночных токенов в прозе — только
                # БУКВЕННО-специфичная уверенность (нумерация/полином/связка/
                # одиночные 0/1). Проблемно-широкий «словесный сигнал» и дефолт
                # не годятся: ловили бренд «S7» как S_7.
                confident = {
                    v for v, e in ev.items()
                    if e.startswith(('нумерация', 'полином',
                                     'мультипликативная', 'одиночные'))}

                bp = backup_probs.get(problem.id, {})
                fields = {}
                for field in ('statement', 'answer', 'solution'):
                    original = getattr(problem, field) or ''
                    if not original:
                        continue
                    new_text, exs = fix_field_c(original, class_map,
                                                bp.get(field, ''), confident)
                    if new_text != original:
                        fields[field] = new_text
                        for b, a in exs:
                            all_examples.append((problem.id, field, b, a))
                if fields:
                    changed_problems += 1
                    changed_ids.add(problem.id)
                    if not dry_run:
                        Problem.objects.filter(pk=problem.pk).update(**fields)

                for part in parts:
                    bpp = backup_parts.get(part.id, {})
                    pfields = {}
                    for field in ('statement', 'answer', 'solution'):
                        original = getattr(part, field) or ''
                        if not original:
                            continue
                        new_text, exs = fix_field_c(original, class_map,
                                                    bpp.get(field, ''), confident)
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

        # обязательные примеры (--show-ids) + случайные
        forced = [e for e in all_examples if e[0] in show_ids]
        rest = [e for e in all_examples if e[0] not in show_ids]
        rng = random.Random(42)
        sample = forced + (rng.sample(rest, max(0, max_examples - len(forced)))
                           if len(rest) > max_examples - len(forced) else rest)
        self.stdout.write(f'\nПримеры ({len(sample)} из {len(all_examples)}):')
        for pid, field, before, after in sample:
            self.stdout.write(f'\n#{pid} [{field}]')
            self.stdout.write(f'  ДО:    {before.strip()[:200]}')
            self.stdout.write(f'  ПОСЛЕ: {after.strip()[:200]}')

        self.stdout.write(f'\nИзменённых строк: {len(all_examples)}; '
                          f'задач: {changed_problems}, подпунктов: {changed_parts}; '
                          f'НЕЯСНО (пропущено): {len(ambiguous_ids)}')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN: ничего не сохранено.'))
        else:
            append_ids_file(CHANGED_IDS_FILE_C, changed_ids)
            append_ids_file(AMBIGUOUS_FILE, ambiguous_ids)
            self.stdout.write(self.style.SUCCESS(
                f'Готово. Сохранено задач: {changed_problems}, '
                f'подпунктов: {changed_parts}. '
                f'Неясные id → {AMBIGUOUS_FILE}'))
