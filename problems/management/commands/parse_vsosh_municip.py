# -*- coding: utf-8 -*-
"""
parse_vsosh_municip — разбор материалов МУНИЦИПАЛЬНОГО этапа ВсОШ (Москва)
в структурный JSON (materials/vsosh_municip/<год>/parsed.json).

Три семейства вёрстки (разведка — reports/vsosh_municip/00_recon.md):
- A (2017, 2018, 2020, 2022, 2023): Word→PDF «Решения и критерии». Вопрос —
  полужирный маркер «N.», варианты строками; правильный ответ по годам:
  полужирная строка варианта (2017, 2022), «Таблица ответов» (2018, 2020,
  и дубль-проверка в 2017), полужирный текст буллет-варианта без букв (2023).
- B (2021): экспорт онлайн-платформы — сетка Roboto в файле otvety;
  правильный вариант помечен СИНЕЙ радиокнопкой (вектор), все тексты
  вариантов полужирные (начертание ответ не помечает). Краткий ответ 2021 —
  отдельный Word-PDF resheniya, парсится механикой A.
- C (2019): DOCX. Варианты — элементы word-списка (букв в тексте нет,
  сопоставляются позиции против «Таблицы ответов»), формулы — OLE-объекты
  (в тексте отсутствуют → вопрос честно уходит в unparsed).

Секции одинаковы во всех годах: «Тестовые задания» (5 single),
«Задания с кратким ответом» (numeric; нечисловой/многопунктовый ответ →
качество numeric не гарантируется, вопрос становится open с answer_text),
«Задания с развёрнутым ответом (решением)» (open; есть в 2017–2020).
Данеток (boolean) и «все верные» (multi) в муниципе нет ни в одном году.

Правило «ничего не выдумывать»: неоднозначный ответ/номер/глиф → unparsed
с причиной. Механика span-разбора, LaTeX-восстановления (этажные дроби,
таблицы, кусочные), postprocess и канонизация ответа переиспользуются из
parse_vsosh_region (регион продолжает работать без изменений).

Ловушки муниципа (найдены разведкой):
- 2017: формулы набраны SymbolMT с PUA-кодами (U+F02B «+»…) — статическая
  карта Adobe Symbol → Unicode; непокрытый код → U+FFFD → unparsed.
- 2017/2020: спаны Word-формул идут в потоке чтения не по порядку
  («TC aQ b = +») — строки одной базовой линии пересобираются по x
  с пометкой «формула собрана по координатам — сверить с PDF».
- 2022: спаны Cambria Math с задвоенными глифами («𝑇𝑇𝐶𝐶(6)») —
  схлопываются, только если ВЕСЬ спан попарно задвоен и содержит букву.
- 2023: и варианты теста, и списки в условии — буллеты Symbol (U+F0B7);
  вариантами считаются буллеты ПОСЛЕ последней строки условия, ровно 4.

Запуск: ./venv/bin/python manage.py parse_vsosh_municip --year 2023
        (без --year — все годы 2017–2023)
"""
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from django.core.management.base import BaseCommand, CommandError

from problems.vsosh_unimath import replace_unicode_math, strip_soft_junk
from problems.management.commands.parse_vsosh_region import (
    BOLD_FLAG, Line, PAGENUM_RE, WS_RE,
    _split_span_by_baseline, _body_size, is_math_span, span_text,
    extract_bars, extract_figures, drop_figure_labels,
    extract_tables, apply_tables,
    reassemble_display_math, reassemble_fractions,
    reassemble_intraline_fracs, clear_resolved_degraded,
    render_paragraph, render_plain_latex, postprocess_text,
    canonicalize_answer,
)

STAGE = 'муниципальный'
MATERIALS = Path('materials/vsosh_municip')

# --- Adobe Symbol (PUA F0xx) → Unicode: стандартная таблица шрифта, --------
# не догадки по контенту. Непокрытый код → U+FFFD (вопрос уйдёт в unparsed).
SYMBOL_PUA = {
    0x22: '∀', 0x24: '∃', 0x27: '∍', 0x28: '(', 0x29: ')', 0x2A: '∗',
    0x2B: '+', 0x2C: ',', 0x2D: '−', 0x2E: '.', 0x2F: '/', 0x3C: '<',
    0x3D: '=', 0x3E: '>', 0x40: '≅', 0x5B: '[', 0x5D: ']', 0x5E: '⊥',
    0x7B: '{', 0x7D: '}',
    # греческий алфавит (латинская раскладка Adobe Symbol)
    0x61: 'α', 0x62: 'β', 0x63: 'χ', 0x64: 'δ', 0x65: 'ε', 0x66: 'φ',
    0x67: 'γ', 0x68: 'η', 0x69: 'ι', 0x6B: 'κ', 0x6C: 'λ', 0x6D: 'μ',
    0x6E: 'ν', 0x6F: 'ο', 0x70: 'π', 0x71: 'θ', 0x72: 'ρ', 0x73: 'σ',
    0x74: 'τ', 0x75: 'υ', 0x77: 'ω', 0x78: 'ξ', 0x79: 'ψ', 0x7A: 'ζ',
    0x44: 'Δ', 0x46: 'Φ', 0x47: 'Γ', 0x4C: 'Λ', 0x50: 'Π', 0x51: 'Θ',
    0x53: 'Σ', 0x57: 'Ω', 0x58: 'Ξ', 0x59: 'Ψ',
    0xA2: '′', 0xB2: '″', 0xB0: '°', 0xA4: '⁄',
    0xA3: '≤', 0xA5: '∞', 0xB1: '±', 0xB3: '≥', 0xB4: '×', 0xB5: '∝',
    0xB6: '∂', 0xB7: '•', 0xB8: '÷', 0xB9: '≠', 0xBA: '≡', 0xBB: '≈',
    0xC5: '⊕', 0xCE: '∈', 0xCF: '∉', 0xD6: '√', 0xD7: '⋅', 0xD9: '∧',
    0xDA: '∨', 0xAE: '→', 0xAC: '←', 0xAD: '↑', 0xAF: '↓', 0xDB: '⇔',
    0xDE: '⇒',
    # куски больших скобок систем уравнений (декорация вёрстки,
    # вычищаются в build_question с пометкой)
    0xE6: '⎛', 0xE7: '⎜', 0xE8: '⎝', 0xE9: '⎡', 0xEA: '⎢', 0xEB: '⎣',
    0xEC: '⎧', 0xED: '⎨', 0xEE: '⎩', 0xEF: '⎪',
    0xF6: '⎞', 0xF7: '⎟', 0xF8: '⎠', 0xF9: '⎤', 0xFA: '⎥', 0xFB: '⎦',
    0xFC: '⎫', 0xFD: '⎬', 0xFE: '⎭',
}
BULLET = '•'
# Второй PUA-блок Adobe (corporate use, F8xx) — те же куски больших скобок
SYMBOL_PUA_F8 = {
    0xF8EB: '⎛', 0xF8EC: '⎜', 0xF8ED: '⎝', 0xF8EE: '⎡', 0xF8EF: '⎢',
    0xF8F0: '⎣', 0xF8F1: '⎧', 0xF8F2: '⎨', 0xF8F3: '⎩', 0xF8F4: '⎪',
    0xF8F5: '⎮', 0xF8F6: '⎞', 0xF8F7: '⎟', 0xF8F8: '⎠', 0xF8F9: '⎤',
    0xF8FA: '⎥', 0xF8FB: '⎦', 0xF8FC: '⎫', 0xF8FD: '⎬', 0xF8FE: '⎭',
}
# декоративные куски больших скобок — не контент
BRACE_PIECES_RE = re.compile(r'[⎛-⎮]')


def decode_symbol_pua(text):
    """PUA-коды шрифта Symbol → юникод; непокрытые PUA → U+FFFD."""
    out = []
    for ch in text:
        code = ord(ch)
        if 0xF000 <= code <= 0xF0FF:
            out.append(SYMBOL_PUA.get(code - 0xF000, '�'))
        elif code in SYMBOL_PUA_F8:
            out.append(SYMBOL_PUA_F8[code])
        elif 0xE000 <= code <= 0xF8FF:
            out.append('�')
        else:
            out.append(ch)
    return ''.join(out)


# Задвоенные глифы Cambria Math в ans-файлах 2022: «TC(Q)» в текстовом слое
# становится «𝑇𝑇𝑇𝑇(𝑄𝑄)» — каждый глиф удвоен, причём ВТОРАЯ буква пары
# потеряна (MC → MMMM, а не MMCC). Восстановить «TC» из «TTTT» нельзя —
# это выдумывание. Поэтому формулы с удвоенными латинскими буквами внутри
# $…$ считаются НЕНАДЁЖНЫМИ: условия/варианты берутся из чистого tasks-файла
# (двухфайловая сборка 2022), решение с задвоением выбрасывается с пометкой.
DOUBLED_LATIN_RE = re.compile(r'([A-Za-z])\1')
MATH_SEG_SCAN_RE = re.compile(r'(?<!\\)\$((?:\\.|[^$\\])*)\$')


def has_doubled_math(text):
    """Есть ли внутри $…$ задвоенные латинские буквы (артефакт Word 2022)."""
    if not text:
        return False
    for seg in MATH_SEG_SCAN_RE.findall(text):
        if DOUBLED_LATIN_RE.search(seg):
            return True
    return False


UNESC_DOLLAR_RE = re.compile(r'(?<!\\)\$')


def _unpaired_dollar(text):
    return bool(text) and len(UNESC_DOLLAR_RE.findall(text)) % 2 == 1


# --- Колонтитулы муниципальных PDF (все годы) -------------------------------
M_HEADER_RES = [
    re.compile(r'^©?\s*ГАОУ ДПО ЦПМ'),
    re.compile(r'^© ГАОУ ДПО ЦПМ'),
    re.compile(r'^письменного согласия ГАОУ ДПО ЦПМ'),
    re.compile(r'^ВСЕРОССИЙСКАЯ ОЛИМПИАДА ШКОЛЬНИКОВ'),
    re.compile(r'^Всероссийская олимпиада школьников'),
    re.compile(r'^ПО ЭКОНОМИКЕ'),
    re.compile(r'^ЭКОНОМИКА\.'),
    re.compile(r'^Экономика\.?\s*$'),
    re.compile(r'^\d{4}\s*[–‒-]\s*\d{4} уч\. ?г\.?\s*$'),
    re.compile(r'^МУНИЦИПАЛЬНЫЙ ЭТАП'),
    re.compile(r'^Муниципальный этап'),
    re.compile(r'^\d{1,2}\s*[–‒-]?\s*\d{0,2}\s*(класс|КЛАСС)(ы|Ы)?\s*$'),
    re.compile(r'^-?\s?\d{1,2}\s?-?$'),
    re.compile(r'^Не забудьте перенести'),
    re.compile(r'^КРИТЕРИИ$'),
]

# --- Секции -----------------------------------------------------------------
SEC_TEST_RE = re.compile(r'^Тестовые задания\s*$')
SEC_SHORT_RE = re.compile(r'^Задани[ея] с кратким ответом\s*$')
SEC_LONG_RE = re.compile(r'^Задани[ея] с развёрнутым ответом')
ANSTABLE_RE = re.compile(r'^Таблица ответов на тестовые задания')
SEC_END_RE = re.compile(r'^(Максимум|Максимальная оценка|Всего) за '
                        r'|^По \d+\s*балл')
# «Ответ на вопрос 1: 33.» в развёрнутых задачах 2020 — это разбор жюри,
# а не канонический ответ: уходит в решение.
LONG_SUBANSWER_RE = re.compile(r'^Ответ(ы)? на вопрос')

QSTART_M_RE = re.compile(r'^(\d{1,2})\.(?:\s+|$)')
OPT_LETTER_RE = re.compile(r'^([а-е])\)\s*')
ANSWER_M_RE = re.compile(r'^Ответ\s*[:.]\s*')
SOLUTION_M_RE = re.compile(r'^(Решение|Комментарий)\s*[:.]?\s*')
POINTS_M_RE = re.compile(r'(\d+)\s*балл')
BALL_PAREN_RE = re.compile(r'\s*\([^()]*балл[^()]*\)')
LETTERS = 'абвгде'

# --- Профили семейства A ----------------------------------------------------
# qnum: маркер вопроса всегда полужирный «N.» (отдельной строкой или в начале
# строки условия). numbering: continuous — сквозная 1..15; per_section —
# в каждой секции с 1. options: letters «а)…» или bullets (Symbol U+F0B7).
# answer: bold — полужирная строка варианта; table — «Таблица ответов»;
# bold+table — оба механизма, расхождение = unparsed.
PROFILES = {
    # tables=False: у 2017 (Word-old, формулы Symbol-спанами) реконструктор
    # таблиц принимает формулы решений за таблицы и съедает соседние строки —
    # реальных таблиц в 2017 нет, отключаем.
    2017: {'numbering': 'continuous', 'options': 'letters',
           'answer': 'bold+table', 'tables': False},
    2018: {'numbering': 'continuous', 'options': 'letters', 'answer': 'table'},
    2020: {'numbering': 'continuous', 'options': 'letters', 'answer': 'table'},
    2021: {'numbering': 'per_section', 'options': 'letters',
           'answer': 'bold'},   # только файл resheniya (краткий ответ)
    # 2022: ans-файлы страдают задвоением глифов Cambria Math (см.
    # has_doubled_math) — условия/варианты пересобираются из чистых
    # tasks-файлов (двухфайловая сборка в parse_year).
    2022: {'numbering': 'per_section', 'options': 'letters', 'answer': 'bold',
           'doubled_math': True},
    2023: {'numbering': 'per_section', 'options': 'bullets', 'answer': 'bold'},
}
# Чистые файлы условий 2022 (без ответов) — для двухфайловой сборки
TASKS_FILES_2022 = {
    '7-8': '*tasks-econ-7-8-*.pdf',
    '9': '*tasks-econ-9-*.pdf',
    '10-11': '*tasks-econ-10-11-*.pdf',
}

# --- Файлы по годам: (метка группы, классы, glob полного файла) -------------
YEAR_FILES = {
    2017: [('7-8', (7, 8), '*_7-8_*.pdf'), ('9', (9,), '*_9_*.pdf'),
           ('10', (10,), '*_10-2_*.pdf'), ('11', (11,), '*_11-2_*.pdf')],
    2018: [('7-8', (7, 8), '*_7-8_kriterii_*.pdf'),
           ('9', (9,), '*_9_kriterii_*.pdf'),
           ('10', (10,), '*_10_kriterii_*.pdf'),
           ('11', (11,), '*_11_kriterii_*.pdf')],
    2019: [('7-8', (7, 8), '*_7-8_kriterii_*.docx'),
           ('9', (9,), '*_9_kriterii_*.docx'),
           ('10', (10,), '*_10_kriterii_*.docx'),
           ('11', (11,), '*_11_kriterii_*.docx')],
    2020: [('7-8', (7, 8), '*_7-8_klassy_s_resheniyami_*.pdf'),
           ('9', (9,), '*_9_klass_s_resheniyami_*.pdf'),
           ('10', (10,), '*_10_klass_s_resheniyami_*.pdf'),
           ('11', (11,), '*_11_klass_s_resheniyami_*.pdf')],
    # 2021: тест — из otvety (сетка с радиокнопками), краткий — из resheniya
    2021: [('7-8', (7, 8), '*_7-8_klassy_otvety_*.pdf'),
           ('9', (9,), '*_9_klass_otvety_*.pdf'),
           ('10-11', (10, 11), '*_10-11_klassy_otvety_*.pdf')],
    2022: [('7-8', (7, 8), '*ans-econ-7-8-*.pdf'),
           ('9', (9,), '*ans-econ-9-*.pdf'),
           ('10-11', (10, 11), '*ans-econ-10-11-*.pdf')],
    2023: [('7-8', (7, 8), '*resheniya_7-8_*.pdf'),
           ('9', (9,), '*resheniya_9_*.pdf'),
           ('10-11', (10, 11), '*resheniya_10-11_*.pdf')],
}
YEARS = sorted(YEAR_FILES)


def find_file(year, pattern):
    root = MATERIALS / str(year) / 'unpacked'
    hits = [p for p in root.rglob(pattern) if '__MACOSX' not in str(p)]
    if len(hits) != 1:
        raise CommandError(f'{year}: по маске {pattern} найдено '
                           f'{len(hits)} файлов, ожидался 1')
    return hits[0]


# ---------------------------------------------------------------------------
# Извлечение строк (семейство A) — клон extract_lines региона со своими
# колонтитулами, декодом Symbol-PUA, схлопыванием задвоенных math-спанов и
# пересборкой строк одной базовой линии по x (Word рвёт порядок чтения формул)
# ---------------------------------------------------------------------------

def _decode_spans(spans):
    """Декод PUA-кодов шрифта Symbol."""
    for sp in spans:
        if 'Symbol' in sp['font']:
            sp['text'] = decode_symbol_pua(sp['text'])
    return spans


def _merge_same_baseline(lines):
    """Строки одной страницы с совпадающей базовой линией (±2pt) и
    непересекающимися x-рамками сливаются в одну, спаны сортируются по x0.
    Лечит Word-формулы, где куски «TC», «aQ», «=», «+» идут отдельными
    line-объектами вне порядка чтения. Помечает слитые строки merged_x=True."""
    out = []
    by_page = {}
    for l in lines:
        by_page.setdefault(l.page_no, []).append(l)
    for page_no in sorted(by_page):
        page_lines = by_page[page_no]
        used = [False] * len(page_lines)
        for i, li in enumerate(page_lines):
            if used[i]:
                continue
            group = [li]
            yi = (li.bbox[1] + li.bbox[3]) / 2
            for j in range(i + 1, len(page_lines)):
                if used[j]:
                    continue
                lj = page_lines[j]
                yj = (lj.bbox[1] + lj.bbox[3]) / 2
                if abs(yi - yj) > 2.0:
                    continue
                # вариант из второй колонки («в) 931 т» на одной строке с
                # «а) 969 т») — отдельная строка, не продолжение формулы
                if OPT_LETTER_RE.match(lj.plain):
                    continue
                # не пересекается ли по x с кем-то из группы
                overlap = any(not (lj.bbox[2] <= g.bbox[0] + 1
                                   or lj.bbox[0] >= g.bbox[2] - 1)
                              for g in group)
                if overlap:
                    continue
                group.append(lj)
                used[j] = True
            if len(group) == 1:
                out.append(li)
                continue
            group.sort(key=lambda g: g.bbox[0])
            spans = [sp for g in group for sp in
                     sorted(g.spans, key=lambda s: s['bbox'][0])]
            spans.sort(key=lambda s: s['bbox'][0])
            bbox = (min(g.bbox[0] for g in group),
                    min(g.bbox[1] for g in group),
                    max(g.bbox[2] for g in group),
                    max(g.bbox[3] for g in group))
            nl = Line(spans, bbox, page_no)
            nl.merged_x = True
            out.append(nl)
    return out


def extract_lines_m(doc):
    """Содержательные строки муниципального PDF в порядке чтения."""
    body_size = _body_size(doc)
    lines = []
    for page_no, page in enumerate(doc, start=1):
        page_h = page.rect.height
        for block in page.get_text('rawdict')['blocks']:
            for raw in block.get('lines', []):
                spans = []
                for rsp in raw['spans']:
                    for sp in _split_span_by_baseline(rsp):
                        if strip_soft_junk(sp['text']).strip() or ' ' in sp['text']:
                            spans.append(sp)
                if not spans:
                    continue
                spans = _decode_spans(spans)
                text = ''.join(sp['text'] for sp in spans).strip()
                near_hdr_edge = (raw['bbox'][3] < 0.14 * page_h
                                 or raw['bbox'][1] > 0.86 * page_h)
                if near_hdr_edge and any(rx.match(text) for rx in M_HEADER_RES):
                    continue
                near_edge = (raw['bbox'][1] > 0.86 * page_h
                             or raw['bbox'][3] < 0.10 * page_h)
                if (PAGENUM_RE.match(text) and near_edge
                        and all(not is_math_span(sp) for sp in spans)):
                    continue
                lines.append(Line(spans, raw['bbox'], page_no))
    return _merge_same_baseline(lines), body_size


def _raster_zones(doc):
    """Зоны растровых картинок: {page_no: [(y0, y1)]} — для пометки
    «в оригинале рисунок» (векторные графики ловит extract_figures)."""
    zones = {}
    for page_no, page in enumerate(doc, start=1):
        page_h = page.rect.height
        for xref, *_ in page.get_images():
            for r in page.get_image_rects(xref):
                # мелкие логотипы/линейки не считаем
                if r.width < 60 or r.height < 40:
                    continue
                # картинка на всю ширину у кромки — шапка бланка
                if r.y1 < 0.12 * page_h:
                    continue
                zones.setdefault(page_no, []).append((r.y0, r.y1))
    return zones


# ---------------------------------------------------------------------------
# Таблица ответов («№ 1..5 / Ответ б в г г в»)
# ---------------------------------------------------------------------------

def parse_answer_table(lines, start_idx):
    """Строки после «Таблица ответов…» → {номер: буква} или None.
    Ячейки идут отдельными строками в порядке чтения; после merge_same_baseline
    могут слиться в «№ 1 2 3 4 5» / «Ответ б в г г в» — разбираем токенами.
    Пустые строки пропускаются; первая строка без единого токена таблицы
    после начала сбора — конец таблицы."""
    numbers, letters = [], []
    seen_otvet = False
    for i in range(start_idx, min(start_idx + 14, len(lines))):
        tokens = lines[i].plain.split()
        if not tokens:
            continue
        matched_any = False
        for tok in tokens:
            t = tok.strip().lower().rstrip('.')
            if t in ('№', 'n'):
                matched_any = True
            elif t == 'ответ':
                seen_otvet = True
                matched_any = True
            elif not seen_otvet and t.isdigit():
                numbers.append(int(t))
                matched_any = True
            elif seen_otvet and len(t) == 1 and t in LETTERS:
                letters.append(t)
                matched_any = True
        if seen_otvet and numbers and len(letters) >= len(numbers):
            break
        if not matched_any and (numbers or seen_otvet):
            break
    if numbers and len(letters) == len(numbers):
        return {n: letters[k] for k, n in enumerate(numbers)}
    return None


# ---------------------------------------------------------------------------
# Семейство A: разбор одного Word-PDF класса
# ---------------------------------------------------------------------------

def parse_document_a(doc, grades, group, profile, fname):
    """PDF одного класса → (questions, unparsed): пайплайн строк + ядро."""
    lines, body = extract_lines_m(doc)
    # Таблица ответов читается из СЫРЫХ строк: реконструктор таблиц региона
    # иначе превратит её в $$\begin{array}…$$ до того, как мы возьмём буквы.
    answer_table = None
    for idx, l in enumerate(lines):
        if ANSTABLE_RE.match(l.plain):
            answer_table = parse_answer_table(lines, idx + 1)
            break
    bars = extract_bars(doc)
    figures = extract_figures(doc)
    lines, fig_zones = drop_figure_labels(lines, figures)
    if profile.get('tables', True):
        tables = extract_tables(doc, body)
        lines = apply_tables(lines, tables, body)
        # сконвертированный остаток сетки ответов — не контент
        lines = [l for l in lines
                 if not (l.spans and l.spans[0].get('is_table')
                         and '\\text{Ответ}' in l.spans[0]['text']
                         and '№' in l.spans[0]['text'])]
    lines = reassemble_display_math(lines, body, bars)
    lines = reassemble_fractions(lines, body, bars)
    lines = reassemble_intraline_fracs(lines, body, bars)
    lines = clear_resolved_degraded(lines, body)
    raster = _raster_zones(doc)
    return parse_lines_a(lines, body, grades, group, profile, fname,
                         fig_zones=fig_zones, raster=raster,
                         answer_table=answer_table)


def parse_lines_a(lines, body, grades, group, profile, fname,
                  fig_zones=None, raster=None, answer_table=None):
    """Ядро семейства A: state-machine по готовым строкам (тестируемо
    без PDF)."""
    fig_zones = fig_zones or {}
    raster = raster or {}
    if answer_table is None:
        for idx, l in enumerate(lines):
            if ANSTABLE_RE.match(l.plain):
                answer_table = parse_answer_table(lines, idx + 1)
                break
    left_margin = min((l.bbox[0] for l in lines
                       if l.spans and not is_math_span(l.spans[0])), default=0)

    numbering = profile['numbering']
    opt_style = profile['options']
    answer_src = profile['answer']

    questions, unparsed = [], []
    section = None          # 'test' | 'short' | 'long'
    qtype = None
    points_by_section = {}
    state = 'idle'
    cur = None
    buffers = new_buffers()
    next_number = 1
    at_section_start = False

    def flush_question():
        nonlocal cur, buffers
        if cur is None:
            buffers = new_buffers()
            return
        q, reason = build_question_a(cur, buffers, body, left_margin,
                                     grades, group, fname, answer_src,
                                     doubled_math=profile.get('doubled_math',
                                                              False))
        if reason:
            raw = '\n'.join(l.plain for key in
                            ('statement', 'options_flat', 'answer', 'solution')
                            for l in flat(buffers, key))
            unparsed.append({'year': None, 'grade_group': group,
                             'number': cur['number'], 'qtype': cur['qtype'],
                             'reason': reason, 'raw': raw,
                             'src_file': fname, 'src_page': cur['page']})
        else:
            mark_figures(q, buffers, fig_zones, raster)
            questions.append(q)
        cur = None
        buffers = new_buffers()

    i = 0
    while i < len(lines):
        line = lines[i]
        plain = line.plain

        sec = None
        if SEC_TEST_RE.match(plain):
            sec = ('test', 'single')
        elif SEC_SHORT_RE.match(plain):
            sec = ('short', 'numeric')
        elif SEC_LONG_RE.match(plain):
            sec = ('long', 'open')
        if sec:
            flush_question()
            section, qtype = sec
            state = 'preamble'
            at_section_start = True
            if numbering == 'per_section':
                next_number = 1
            i += 1
            continue

        if ANSTABLE_RE.match(plain) and section == 'test':
            flush_question()
            state = 'idle'   # таблица уже разобрана из сырых строк
            i += 1
            continue

        if section is None:
            i += 1
            continue

        m = QSTART_M_RE.match(plain)
        if m and section is not None:
            num = int(m.group(1))
            # первый вопрос секции: до него подпунктов быть не может,
            # принимаем любой полужирный номер (сквозная нумерация файла
            # может начинать секцию с 6, 12 и т.п.)
            ok_num = num == next_number or at_section_start
            stripped, marker_bold = strip_marker_m(line, QSTART_M_RE)
            if ok_num and marker_bold:
                flush_question()
                cur = {'number': num, 'section': section, 'qtype': qtype,
                       'page': line.page_no}
                next_number = num + 1
                at_section_start = False
                if stripped.spans:
                    buffers['statement'].append(stripped)
                state = 'statement'
                i += 1
                continue

        if SEC_END_RE.match(plain):
            flush_question()
            state = 'idle'
            i += 1
            continue

        if cur is not None and section == 'test':
            if opt_style == 'letters':
                mo = OPT_LETTER_RE.match(plain)
                # буква не должна повторяться; порядок прибытия может быть
                # «а в б г» (двухколоночная вёрстка 2017) — сортировка при
                # сборке вопроса
                if (mo and state in ('statement', 'options')
                        and mo.group(1) not in
                        {o['letter'] for o in buffers['options']}):
                    stripped, mb = strip_marker_m(line, OPT_LETTER_RE)
                    bold = mb or line_has_bold(stripped)
                    buffers['options'].append({'lines': [stripped],
                                               'bold': bold,
                                               'letter': mo.group(1)})
                    state = 'options'
                    i += 1
                    continue
            else:  # bullets
                if (line.spans and line.spans[0]['text'].strip() == BULLET
                        and state in ('statement', 'options')):
                    stripped = drop_bullet(line)
                    buffers['options'].append(
                        {'lines': [stripped],
                         'bold': line_has_bold(stripped),
                         'letter': LETTERS[len(buffers['options'])]
                         if len(buffers['options']) < len(LETTERS) else '?'})
                    state = 'options'
                    i += 1
                    continue

        if (cur is not None and section == 'long'
                and LONG_SUBANSWER_RE.match(plain)):
            # «Ответ на вопрос 1: 33.» — разбор жюри, идёт в решение
            buffers['solution'].append(line)
            state = 'solution'
            i += 1
            continue

        ma = ANSWER_M_RE.match(plain)
        if ma and cur is not None and state in ('statement', 'options',
                                                'solution'):
            stripped, _ = strip_marker_m(line, ANSWER_M_RE)
            buffers['answer'] = [stripped] if stripped.spans else []
            state = 'answer'
            i += 1
            continue

        ms = SOLUTION_M_RE.match(plain)
        if ms and cur is not None and state != 'preamble':
            stripped, _ = strip_marker_m(line, SOLUTION_M_RE)
            if state == 'solution':
                # второе «Решение:»/«Комментарий:» — продолжение решения
                if stripped.spans:
                    buffers['solution'].append(stripped)
            else:
                buffers['solution'] = [stripped] if stripped.spans else []
            state = 'solution'
            i += 1
            continue

        if state == 'preamble':
            if section not in points_by_section:
                pm = POINTS_M_RE.search(plain)
                if pm:
                    points_by_section[section] = int(pm.group(1))
        elif state == 'statement' and cur is not None:
            buffers['statement'].append(line)
        elif state == 'options' and buffers['options']:
            # буллет-строка внутри пунктов (продолжение) или новая опция
            buffers['options'][-1]['lines'].append(line)
            if line_has_bold(line):
                buffers['options'][-1]['bold'] = True
        elif state == 'answer':
            buffers['answer'].append(line)
        elif state == 'solution':
            buffers['solution'].append(line)
        i += 1

    flush_question()

    # правильные ответы теста из таблицы
    if answer_src in ('table', 'bold+table'):
        apply_answer_table(questions, unparsed, answer_table, answer_src,
                           group, fname)

    for q in questions:
        q['points'] = points_by_section.get(q['section'])
    return questions, unparsed


def new_buffers():
    return {'statement': [], 'options': [], 'answer': [], 'solution': []}


def flat(buffers, key):
    if key == 'options_flat':
        return [l for opt in buffers['options'] for l in opt['lines']]
    return buffers.get(key, [])


def line_has_bold(line):
    return any(sp['flags'] & BOLD_FLAG and sp['text'].strip()
               for sp in line.spans)


def drop_bullet(line):
    """Срезает ведущий буллет-спан (Symbol «•») и пустой Arial-пробел."""
    spans = list(line.spans)
    while spans and spans[0]['text'].strip() in (BULLET, ''):
        spans.pop(0)
    return Line(spans, line.bbox, line.page_no)


def strip_marker_m(line, marker_re):
    """Как strip_marker региона: срезает маркер, возвращает (строка, bold)."""
    joined = ''.join(sp['text'] for sp in line.spans)
    lead_ws = len(joined) - len(joined.lstrip())
    m = marker_re.match(joined.lstrip())
    cut = lead_ws + m.end()
    bold = False
    new_spans = []
    pos = 0
    for sp in line.spans:
        t = sp['text']
        start, end = pos, pos + len(t)
        pos = end
        if end <= cut:
            if t.strip() and sp['flags'] & BOLD_FLAG:
                bold = True
            continue
        if start >= cut:
            new_spans.append(sp)
            continue
        if t[:cut - start].strip() and sp['flags'] & BOLD_FLAG:
            bold = True
        rest = t[cut - start:]
        if rest.strip() or ' ' in rest:
            sp2 = dict(sp)
            sp2['text'] = rest
            new_spans.append(sp2)
    return Line(new_spans, line.bbox, line.page_no), bold


def mark_figures(q, buffers, fig_zones, raster):
    """Пометка «в оригинале рисунок» по потоку чтения (как на регионе),
    плюс растровые картинки."""
    qlines = [l for key in ('statement', 'options_flat', 'answer', 'solution')
              for l in flat(buffers, key)]
    if not qlines:
        return
    first = min((l.page_no, l.bbox[1]) for l in qlines)
    last = max((l.page_no, l.bbox[3]) for l in qlines)
    owns = False
    for pno, zones in list(fig_zones.items()) + list(raster.items()):
        for zy0, _zy1 in zones:
            if first <= (pno, zy0) and (pno, zy0 - 40) <= last:
                owns = True
                break
        if owns:
            break
    if owns:
        note = 'в оригинале рисунок — в игру не годится, сверить с PDF'
        q['notes'] = (q['notes'] + '; ' + note) if q.get('notes') else note
        q['has_figure'] = True


def build_question_a(cur, buffers, body, left_margin, grades, group,
                     fname, answer_src, doubled_math=False):
    """Буферы → словарь вопроса; (None, причина) при неоднозначности.
    answer_src == 'none' — разбор файла условий без ответов (tasks 2022):
    correct остаётся None, отсутствие «Ответ:» не ошибка."""
    qtype = cur['qtype']
    issues = []
    statement = render_paragraph(buffers['statement'], body, issues=issues)
    if not statement:
        return None, 'пустое условие'
    statement = postprocess_text(statement)
    if BRACE_PIECES_RE.search(statement):
        statement = WS_RE.sub(' ', BRACE_PIECES_RE.sub(' ', statement)).strip()
        issues.append('большая скобка (система/кусочная функция) из PDF '
                      'убрана — условие линеаризовано, сверить с оригиналом')

    merged = any(getattr(l, 'merged_x', False)
                 for key in ('statement', 'options_flat', 'answer')
                 for l in flat(buffers, key))
    degraded = any(l.degraded
                   for key in ('statement', 'options_flat', 'solution')
                   for l in flat(buffers, key))

    solution = render_paragraph(buffers['solution'], body,
                                indent_breaks=True, left_margin=left_margin,
                                issues=issues)
    solution = postprocess_text(solution)
    if BRACE_PIECES_RE.search(solution):
        solution = WS_RE.sub(' ', BRACE_PIECES_RE.sub(' ', solution)).strip()
        issues.append('большая скобка системы уравнений из PDF убрана — '
                      'решение линеаризовано, сверить с оригиналом')

    # порядок прибытия вариантов может быть «а в б г» (две колонки 2017) —
    # сортируем по букве
    opt_items = sorted(buffers['options'], key=lambda o: o['letter'])
    opts = [postprocess_text(render_paragraph(o['lines'], body, issues=issues))
            for o in opt_items]
    bold_idx = [i for i, o in enumerate(opt_items) if o['bold']]

    if '�' in statement + ''.join(opts):
        return None, 'нерасшифрованные глифы (U+FFFD) в условии/вариантах'
    letters_got = [o['letter'] for o in opt_items]
    if letters_got != list(LETTERS[:len(letters_got)]):
        return None, f'буквы вариантов с пропуском: {letters_got}'
    if opts and any(not o.strip() for o in opts):
        return None, 'пустой вариант — формула Word не собралась'
    if _unpaired_dollar(statement) or any(_unpaired_dollar(o) for o in opts):
        return None, 'непарный $ в условии/вариантах — формулы не собрались'
    if _unpaired_dollar(solution):
        q_note = ('решение жюри не собралось (непарная математика) — '
                  'не импортируется, сверить с PDF')
        solution = ''
        issues.append(q_note)

    q = {'grades': list(grades), 'grade_group': group,
         'number': str(cur['number']), 'section': cur['section'],
         'qtype': qtype, 'statement': statement, 'options': [],
         'correct': None, 'unit': '', 'answer_text': '',
         'solution': solution, 'points': None,
         'src_file': fname, 'src_page': cur['page']}
    notes = []
    if degraded:
        notes.append('математика линеаризована: этажную дробь из PDF не '
                     'удалось собрать автоматически — сверить с оригиналом')
    if merged:
        notes.append('формула Word собрана по координатам — сверить с PDF')
    notes.extend(dict.fromkeys(issues))
    if notes:
        q['notes'] = '; '.join(notes)

    # Задвоенные глифы Word (2022): решение выбрасываем, условие/варианты
    # помечаем — их пересоберёт двухфайловая сборка из tasks-файла, а без
    # чистой пары вопрос уйдёт в unparsed на финальном фильтре.
    if doubled_math:
        if has_doubled_math(solution):
            q['solution'] = solution = ''
            notes.append('решение жюри с задвоенными глифами Word — '
                         'не импортируется, сверить с PDF')
            q['notes'] = '; '.join(notes)
        if has_doubled_math(statement + ' '.join(opts)):
            q['doubled'] = True

    if qtype == 'single':
        if not 4 <= len(opts) <= 5:
            return None, f'вариантов {len(opts)}, ожидалось 4–5'
        q['options'] = opts
        if answer_src in ('bold', 'bold+table'):
            if answer_src == 'bold' and len(bold_idx) != 1:
                return None, (f'полужирных вариантов {len(bold_idx)}, '
                              'ожидался ровно 1')
            q['correct'] = bold_idx[0] if len(bold_idx) == 1 else None
            q['bold_idx'] = bold_idx      # для сверки с таблицей
        # для 'table' correct назначит apply_answer_table, 'none' — без ответа
        return q, None

    if qtype == 'numeric':
        if buffers['options']:
            return None, 'у вопроса с кратким ответом нашлись варианты'
        answer_raw = render_plain_latex(buffers['answer'], body)
        answer_raw = BALL_PAREN_RE.sub('', answer_raw).strip()
        if answer_src == 'none':
            q['answer_text'] = answer_raw
            return q, None
        if not answer_raw:
            return None, 'строка «Ответ:» не найдена'
        if '�' in answer_raw:
            return None, 'нерасшифрованные глифы (U+FFFD) в ответе'
        if doubled_math and has_doubled_math('$' + answer_raw + '$'):
            return None, 'задвоенные глифы Word в ответе'
        if '�' in solution:
            q['solution'] = ''
            notes.append('решение жюри с нерасшифрованными глифами — '
                         'не импортируется')
            q['notes'] = '; '.join(notes)
        parsed, err = canonicalize_answer(answer_raw)
        if err:
            # честный fallback: ответ жюри есть, но он не число —
            # в игру не годится, в каталог идёт как открытая задача
            q['qtype'] = 'open'
            q['answer_text'] = answer_raw
            notes.append('ответ не канонизируется в число — '
                         'вопрос пойдёт как задача, не в игру')
            q['notes'] = '; '.join(notes)
            return q, None
        q['correct'], q['unit'] = parsed
        q['answer_text'] = answer_raw
        return q, None

    # open (развёрнутые)
    if buffers['options']:
        return None, 'у развёрнутой задачи нашлись варианты'
    answer_raw = render_plain_latex(buffers['answer'], body)
    answer_raw = BALL_PAREN_RE.sub('', answer_raw).strip()
    q['answer_text'] = answer_raw
    if answer_src == 'none':
        return q, None
    if not solution and not answer_raw:
        return None, 'нет ни решения, ни ответа'
    if '�' in solution + answer_raw:
        return None, 'нерасшифрованные глифы (U+FFFD) в решении/ответе'
    return q, None


def apply_answer_table(questions, unparsed, answer_table, answer_src,
                       group, fname):
    """Назначение правильных ответов теста из «Таблицы ответов» (+сверка
    с полужирными, если answer_src == 'bold+table')."""
    test_qs = [q for q in questions if q['section'] == 'test']
    if not test_qs:
        return
    if not answer_table:
        for q in test_qs:
            questions.remove(q)
            unparsed.append({'grade_group': group, 'number': q['number'],
                             'qtype': 'single',
                             'reason': 'таблица ответов не распознана',
                             'raw': q['statement'][:200],
                             'src_file': fname, 'src_page': q['src_page']})
        return
    for q in list(test_qs):
        letter = answer_table.get(int(q['number']))
        reason = None
        if letter is None:
            reason = f'номера {q["number"]} нет в таблице ответов'
        else:
            idx = LETTERS.index(letter)
            if idx >= len(q['options']):
                reason = f'буква «{letter}» вне вариантов'
            elif answer_src == 'bold+table':
                bold_idx = q.get('bold_idx') or []
                if len(bold_idx) == 1 and bold_idx[0] != idx:
                    reason = (f'расхождение: полужирный вариант '
                              f'{LETTERS[bold_idx[0]]}), таблица — {letter})')
                else:
                    q['correct'] = idx
            else:
                q['correct'] = idx
        if reason:
            questions.remove(q)
            unparsed.append({'grade_group': group, 'number': q['number'],
                             'qtype': 'single', 'reason': reason,
                             'raw': q['statement'][:200],
                             'src_file': fname, 'src_page': q['src_page']})
        else:
            q.pop('bold_idx', None)


# ---------------------------------------------------------------------------
# Семейство B: сетка онлайн-платформы 2021 (файл otvety)
# ---------------------------------------------------------------------------

GRID_SKIP_RE = re.compile(
    r'^(№ ?\d|Тестовые задания$|Задания с кратким ответом$|\d+ балл(а|ов)?$'
    r'|Муниципальный этап ВсОШ|экономика, |\d{1,2}:\d{2})')


def _grid_radios(page):
    """Радиокнопки сетки: [(y0, y1, is_blue)] по вертикали."""
    marks = []
    for dr in page.get_drawings():
        r = dr['rect']
        if not (95 <= r.x0 <= 120 and r.width < 16 and r.height < 16):
            continue
        f = dr.get('fill')
        if not f:
            continue
        blue = (abs(f[0] - 0.294) < 0.02 and abs(f[1] - 0.549) < 0.02
                and abs(f[2] - 0.933) < 0.02)
        gray = (abs(f[0] - 0.655) < 0.02 and abs(f[1] - 0.702) < 0.02
                and abs(f[2] - 0.761) < 0.02)
        if not (blue or gray):
            continue
        marks.append((r.y0, r.y1, blue))
    # синий рисуется дважды (кольцо+точка) — схлопнуть по y-центру
    marks.sort(key=lambda m: (m[0] + m[1]) / 2)
    dedup = []
    for m in marks:
        if dedup and abs((m[0] + m[1]) / 2
                         - (dedup[-1][0] + dedup[-1][1]) / 2) < 4:
            if m[2]:
                dedup[-1] = (dedup[-1][0], dedup[-1][1], True)
            continue
        dedup.append(m)
    return dedup


def cluster_radios(radios, gap=150):
    """Радиокнопки (по y) → кластеры-вопросы: зазор > gap = новый вопрос."""
    clusters = []
    for m in radios:
        if clusters and m[0] - clusters[-1][-1][1] < gap:
            clusters[-1].append(m)
        else:
            clusters.append([m])
    return clusters


def _render_grid_spans(spans):
    """Спаны строки сетки → текст: STIX → $юникод-математика$, Roboto → текст."""
    pieces = []
    math_run = ''
    for sp in sorted(spans, key=lambda s: s['bbox'][0]):
        txt = strip_soft_junk(sp['text'])
        if not txt.strip():
            if math_run:
                math_run += ' '
            elif pieces and not pieces[-1].endswith(' '):
                pieces.append(' ')
            continue
        if sp['font'].startswith('STIX'):
            math_run += replace_unicode_math(txt)
        else:
            if math_run:
                frag = math_run.strip()
                if frag:
                    if re.search(r'[A-Za-z\\^_]', frag):
                        pieces.append(' $' + WS_RE.sub(' ', frag) + '$ ')
                    else:
                        pieces.append(' ' + frag + ' ')
                math_run = ''
            pieces.append(txt.replace('$', '$\\$$'))
    if math_run.strip():
        frag = WS_RE.sub(' ', math_run.strip())
        if re.search(r'[A-Za-z\\^_]', frag):
            pieces.append(' $' + frag + '$')
        else:
            pieces.append(' ' + frag)
    text = ''.join(pieces)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' ([,.;:?!])', r'\1', text)
    return text.strip()


def parse_grid_2021(doc, grades, group, fname):
    """Сетка otvety → (questions, unparsed): 5 тестовых single."""
    questions, unparsed = [], []
    qnum = 0
    for page_no, page in enumerate(doc, start=1):
        radios = _grid_radios(page)
        if not radios:
            continue
        # строки страницы: (y_center, kind, spans)
        rows = []
        d = page.get_text('dict')
        for block in d['blocks']:
            if block.get('type') != 0:
                continue
            for line in block['lines']:
                spans = [sp for sp in line['spans'] if sp['text'].strip()]
                if not spans:
                    continue
                text = ''.join(sp['text'] for sp in spans).strip()
                if GRID_SKIP_RE.match(text):
                    continue
                fonts = {sp['font'] for sp in spans}
                is_opt = any(f == 'Roboto-Bold' and 9.5 <= sp['size'] <= 11
                             for sp in spans for f in [sp['font']])
                is_stmt = any(sp['font'] == 'Roboto-Regular'
                              and sp['size'] < 9 for sp in spans)
                is_stix = all(f.startswith('STIX') for f in fonts)
                y = (line['bbox'][1] + line['bbox'][3]) / 2
                rows.append({'y': y, 'bbox': line['bbox'], 'spans': spans,
                             'opt': is_opt, 'stmt': is_stmt, 'stix': is_stix})
        rows.sort(key=lambda r: (r['y'], r['bbox'][0]))
        # слить куски одной базовой линии (формула + текст)
        merged_rows = []
        for r in rows:
            if merged_rows and abs(merged_rows[-1]['y'] - r['y']) <= 3:
                m = merged_rows[-1]
                m['spans'] = m['spans'] + r['spans']
                m['opt'] = m['opt'] or r['opt']
                m['stmt'] = m['stmt'] or r['stmt']
                m['stix'] = m['stix'] and r['stix']
                continue
            merged_rows.append(dict(r))
        rows = merged_rows

        # кластеры радиокнопок = вопросы (зазор > 150pt)
        clusters = cluster_radios(radios)

        prev_bottom = 0.0
        for cl in clusters:
            qnum += 1
            top = cl[0][0]
            stmt_rows = [r for r in rows
                         if prev_bottom < r['y'] < top - 2 and not r['opt']]
            orphan_stix = [r for r in stmt_rows if r['stix']]
            stmt_rows = [r for r in stmt_rows if not r['stix'] or r in orphan_stix]
            opts = []
            bounds = [c[0] for c in cl] + [cl[-1][1] + 60]
            for k in range(len(cl)):
                opt_rows = [r for r in rows if r['opt']
                            and bounds[k] - 4 <= r['y'] < bounds[k + 1] - 4]
                opts.append(opt_rows)
            prev_bottom = max((r['y'] for rr in opts for r in rr),
                              default=cl[-1][1])

            blue_idx = [k for k, c in enumerate(cl) if c[2]]
            reason = None
            if orphan_stix:
                reason = ('формула экспорта платформы (STIX) стоит отдельной '
                          'строкой — автосборка ненадёжна, сверить с PDF')
            elif len(cl) != 4:
                reason = f'радиокнопок {len(cl)}, ожидалось 4'
            elif len(blue_idx) != 1:
                reason = f'синих радиокнопок {len(blue_idx)}, ожидалась 1'
            elif any(not rr for rr in opts):
                reason = 'вариант без текста'

            stmt = ' '.join(_render_grid_spans(r['spans'])
                            for r in stmt_rows).strip()
            stmt = postprocess_text(WS_RE.sub(' ', stmt))
            option_texts = [postprocess_text(WS_RE.sub(' ', ' '.join(
                _render_grid_spans(r['spans']) for r in rr)).strip())
                for rr in opts]

            if reason is None and not stmt:
                reason = 'пустое условие'
            if reason is None and '�' in stmt + ''.join(option_texts):
                reason = 'нерасшифрованные глифы (U+FFFD)'

            if reason:
                unparsed.append({'grade_group': group, 'number': str(qnum),
                                 'qtype': 'single', 'reason': reason,
                                 'raw': (stmt + '\n' + '\n'.join(option_texts))[:600],
                                 'src_file': fname, 'src_page': page_no})
                continue
            questions.append({'grades': list(grades), 'grade_group': group,
                              'number': str(qnum), 'section': 'test',
                              'qtype': 'single', 'statement': stmt,
                              'options': option_texts,
                              'correct': blue_idx[0], 'unit': '',
                              'answer_text': '', 'solution': '',
                              'points': 4, 'src_file': fname,
                              'src_page': page_no})
    return questions, unparsed


# ---------------------------------------------------------------------------
# Семейство C: DOCX 2019
# ---------------------------------------------------------------------------

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
M_NS = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'


def _xml_from_docx(data: bytes):
    """Разобрать XML из .docx, не раскрывая сущности.

    Что проверено на Python 3.13 (тест `problems/tests/test_xml_entities.py`):

    * ВНЕШНЮЮ сущность (`file:///...`) стандартный ElementTree не тянет
      вовсе — падает с «undefined entity». Чтения чужих файлов и обращений
      в сеть через .docx не бывает;
    * а вот ВНУТРЕННИЕ сущности он раскрывает, и «бомба» из девяти
      вложенных объявлений раздувается без ограничений. Это отказ в
      обслуживании: разбор одного файла съедает память машины.

    Лечится дёшево и без новой зависимости: в OOXML объявления DTD не
    бывают вовсе — Word их не пишет. Значит, файл с `<!DOCTYPE` либо
    подделан, либо повреждён, и разбирать его не надо.
    """
    if b'<!DOCTYPE' in data:
        raise ValueError(
            'в XML из .docx объявлен DOCTYPE — так Word не пишет; '
            'файл не разбираем')
    return ET.fromstring(data)  # nosec B314 — сущности отсечены проверкой выше


def _docx_numfmt_map(z):
    """numId → numFmt нулевого уровня (из numbering.xml)."""
    try:
        root = _xml_from_docx(z.read('word/numbering.xml'))
    except KeyError:
        return {}
    abstract = {}
    for an in root.iter(W + 'abstractNum'):
        aid = an.get(W + 'abstractNumId')
        for lvl in an.iter(W + 'lvl'):
            if lvl.get(W + 'ilvl') == '0':
                fmt = lvl.find(W + 'numFmt')
                abstract[aid] = fmt.get(W + 'val') if fmt is not None else None
                break
    out = {}
    for num in root.iter(W + 'num'):
        nid = num.get(W + 'numId')
        ref = num.find(W + 'abstractNumId')
        if ref is not None:
            out[nid] = abstract.get(ref.get(W + 'val'))
    return out


def _para_info(p):
    """Абзац DOCX → {text, runs, numid, has_ole, has_math}."""
    runs = []
    for r in p.findall(W + 'r'):
        t = ''.join(n.text or '' for n in r.findall(W + 't'))
        rpr = r.find(W + 'rPr')
        bold = rpr is not None and rpr.find(W + 'b') is not None
        ital = rpr is not None and rpr.find(W + 'i') is not None
        if t:
            runs.append((t, bold, ital))
    text = ''.join(t for t, _, _ in runs)
    numid = None
    ppr = p.find(W + 'pPr')
    if ppr is not None:
        npr = ppr.find(W + 'numPr')
        if npr is not None:
            nid = npr.find(W + 'numId')
            if nid is not None:
                numid = nid.get(W + 'val')
    has_ole = (p.find('.//' + W + 'object') is not None
               or p.find('.//' + W + 'pict') is not None
               or p.find('.//' + W + 'drawing') is not None)
    has_math = p.find('.//' + M_NS + 'oMath') is not None
    return {'text': text, 'runs': runs, 'numid': numid,
            'has_ole': has_ole, 'has_math': has_math}


def _docx_clean(text):
    """Мягкая чистка текста DOCX + postprocess (дефисы, гомоглифы)."""
    text = text.replace('\xa0', ' ')
    text = WS_RE.sub(' ', text).strip()
    return postprocess_text(text)


def parse_docx_2019(path, grades, group, fname):
    """DOCX «критерии» 2019 → (questions, unparsed)."""
    z = zipfile.ZipFile(str(path))
    numfmt = _docx_numfmt_map(z)
    root = _xml_from_docx(z.read('word/document.xml'))
    body = root.find(W + 'body')

    # элементы тела по порядку: абзацы и таблицы
    items = []
    for el in body:
        if el.tag == W + 'p':
            items.append(('p', _para_info(el)))
        elif el.tag == W + 'tbl':
            rows = []
            for tr in el.findall(W + 'tr'):
                cells = []
                for tc in tr.findall(W + 'tc'):
                    cells.append(' '.join(
                        _para_info(p)['text'] for p in tc.findall(W + 'p')).strip())
                rows.append(cells)
            items.append(('tbl', rows))

    questions, unparsed = [], []
    section = None
    qtype = None
    state = 'idle'
    cur = None
    buf = None
    next_number = 1
    at_section_start = False
    answer_table = None
    points_by_section = {}

    def close_question():
        nonlocal cur, buf
        if cur is None:
            return
        q, reason = build_question_docx(cur, buf, grades, group, fname)
        if reason:
            raw = '\n'.join(p['text'] for p in
                            buf['statement'] + [x for o in buf['options']
                                                for x in o]
                            + buf['answer'] + buf['solution'])
            unparsed.append({'grade_group': group, 'number': cur['number'],
                             'qtype': cur['qtype'], 'reason': reason,
                             'raw': raw[:600], 'src_file': fname,
                             'src_page': None})
        else:
            questions.append(q)
        cur = None
        buf = None

    for kind, item in items:
        if kind == 'tbl':
            if section == 'test' and answer_table is None and state == 'anstable':
                # строки: ['№','1'..'5'] и ['Ответ', 'б', ...]
                tbl = {}
                nums, letts = [], []
                for row in item:
                    cells = [c.strip().lower() for c in row]
                    if cells and cells[0] in ('№', 'n'):
                        nums = [int(c) for c in cells[1:] if c.isdigit()]
                    elif cells and cells[0].startswith('ответ'):
                        letts = [c for c in cells[1:]
                                 if len(c) == 1 and c in LETTERS]
                if nums and len(nums) == len(letts):
                    tbl = dict(zip(nums, letts))
                answer_table = tbl or None
                state = 'idle'
            continue

        p = item
        text = p['text'].replace('\xa0', ' ').strip()

        if SEC_TEST_RE.match(text):
            close_question()
            section, qtype = 'test', 'single'
            state = 'preamble'
            at_section_start = True
            continue
        if SEC_SHORT_RE.match(text):
            close_question()
            section, qtype = 'short', 'numeric'
            state = 'preamble'
            at_section_start = True
            continue
        if SEC_LONG_RE.match(text):
            close_question()
            section, qtype = 'long', 'open'
            state = 'preamble'
            at_section_start = True
            continue
        if ANSTABLE_RE.match(text):
            close_question()
            state = 'anstable'
            continue
        if SEC_END_RE.match(text):
            close_question()
            state = 'idle'
            continue
        if section is None or not text and not p['numid']:
            if state == 'preamble' and text:
                pm = POINTS_M_RE.search(text)
                if pm and section not in points_by_section:
                    points_by_section[section] = int(pm.group(1))
            continue

        m = QSTART_M_RE.match(text)
        first_bold = p['runs'][0][1] if p['runs'] else False
        if m and first_bold:
            num = int(m.group(1))
            if num == next_number or at_section_start:
                close_question()
                cur = {'number': str(num), 'section': section, 'qtype': qtype}
                next_number = num + 1
                at_section_start = False
                rest = dict(p)
                rest['text'] = QSTART_M_RE.sub('', text, count=1)
                buf = {'statement': [rest], 'options': [], 'answer': [],
                       'solution': []}
                state = 'statement'
                continue

        if cur is None:
            if state == 'preamble' and text:
                pm = POINTS_M_RE.search(text)
                if pm and section not in points_by_section:
                    points_by_section[section] = int(pm.group(1))
            continue

        if p['numid'] is not None and section == 'test' \
                and state in ('statement', 'options'):
            fmt = numfmt.get(p['numid'])
            buf['options'].append([dict(p, numfmt=fmt)])
            state = 'options'
            continue

        if ANSWER_M_RE.match(text) and state in ('statement', 'options',
                                                 'solution'):
            p2 = dict(p)
            p2['text'] = ANSWER_M_RE.sub('', text, count=1)
            buf['answer'] = [p2]
            state = 'answer'
            continue
        if SOLUTION_M_RE.match(text) and state != 'preamble':
            p2 = dict(p)
            p2['text'] = SOLUTION_M_RE.sub('', text, count=1)
            if state == 'solution':
                buf['solution'].append(p2)
            else:
                buf['solution'] = [p2]
            state = 'solution'
            continue
        # курсивный комментарий сразу после вариантов — решение
        if (state == 'options' and p['runs']
                and all(i for _, _, i in p['runs'])):
            buf['solution'].append(dict(p))
            state = 'solution'
            continue

        if state == 'statement':
            buf['statement'].append(dict(p))
        elif state == 'options' and buf['options']:
            buf['options'][-1].append(dict(p))
        elif state == 'answer':
            buf['answer'].append(dict(p))
        elif state == 'solution':
            buf['solution'].append(dict(p))

    close_question()

    # ответы теста из таблицы
    test_qs = [q for q in questions if q['section'] == 'test']
    for q in list(test_qs):
        reason = None
        if not answer_table:
            reason = 'таблица ответов не распознана'
        else:
            letter = answer_table.get(int(q['number']))
            if letter is None:
                reason = f'номера {q["number"]} нет в таблице ответов'
            else:
                idx = LETTERS.index(letter)
                if idx >= len(q['options']):
                    reason = f'буква «{letter}» вне вариантов'
                else:
                    q['correct'] = idx
        if reason:
            questions.remove(q)
            unparsed.append({'grade_group': group, 'number': q['number'],
                             'qtype': 'single', 'reason': reason,
                             'raw': q['statement'][:200],
                             'src_file': fname, 'src_page': None})

    for q in questions:
        q['points'] = points_by_section.get(q['section'])
    return questions, unparsed


def build_question_docx(cur, buf, grades, group, fname):
    qtype = cur['qtype']
    notes = []

    def paras_text(paras):
        return ' '.join(p['text'] for p in paras)

    stmt_paras = buf['statement']
    opt_groups = buf['options']
    if any(p['has_ole'] or p['has_math'] for p in stmt_paras) \
            or any(p['has_ole'] or p['has_math']
                   for o in opt_groups for p in o):
        return None, ('формула/рисунок OLE в условии или вариантах — '
                      'текст неполон, из DOCX не извлекается')
    statement = _docx_clean(paras_text(stmt_paras))
    if not statement:
        return None, 'пустое условие'

    q = {'grades': list(grades), 'grade_group': group,
         'number': cur['number'], 'section': cur['section'], 'qtype': qtype,
         'statement': statement, 'options': [], 'correct': None,
         'unit': '', 'answer_text': '', 'solution': '', 'points': None,
         'src_file': fname, 'src_page': None}

    sol_paras = buf['solution']
    sol_ole = any(p['has_ole'] or p['has_math'] for p in sol_paras)
    if sol_ole:
        notes.append('решение жюри с формулами (OLE) — из DOCX не '
                     'извлекается, решение не импортируется')
        solution = ''
    else:
        solution = _docx_clean('\n\n'.join(p['text'] for p in sol_paras))
    q['solution'] = solution

    if qtype == 'single':
        if len(opt_groups) != 4:
            return None, f'вариантов {len(opt_groups)}, ожидалось 4'
        fmts = {o[0].get('numfmt') for o in opt_groups}
        if fmts - {'russianLower'}:
            return None, (f'нумерация вариантов {fmts} — не russianLower, '
                          'сопоставление букв ненадёжно')
        q['options'] = [_docx_clean(paras_text(o)) for o in opt_groups]
        if any(not o for o in q['options']):
            return None, 'пустой вариант'
        # correct назначается таблицей ответов после
        if notes:
            q['notes'] = '; '.join(notes)
        return q, None

    if qtype == 'numeric':
        if opt_groups:
            return None, 'у вопроса с кратким ответом нашлись варианты'
        ans_paras = buf['answer']
        if any(p['has_ole'] or p['has_math'] for p in ans_paras):
            return None, 'формула OLE в ответе — из DOCX не извлекается'
        answer_raw = BALL_PAREN_RE.sub('', paras_text(ans_paras)) \
            .replace('\xa0', ' ').strip()
        if not answer_raw:
            return None, 'строка «Ответ:» не найдена'
        parsed, err = canonicalize_answer(answer_raw)
        if err:
            q['qtype'] = 'open'
            q['answer_text'] = _docx_clean(answer_raw)
            notes.append('ответ не канонизируется в число — '
                         'вопрос пойдёт как задача, не в игру')
            q['notes'] = '; '.join(notes)
            return q, None
        q['correct'], q['unit'] = parsed
        q['answer_text'] = answer_raw
        if notes:
            q['notes'] = '; '.join(notes)
        return q, None

    # open
    ans_paras = buf['answer']
    ans_ole = any(p['has_ole'] or p['has_math'] for p in ans_paras)
    if ans_ole:
        return None, 'формула OLE в ответе развёрнутой задачи'
    q['answer_text'] = _docx_clean(
        BALL_PAREN_RE.sub('', paras_text(ans_paras)))
    if not q['solution'] and not q['answer_text']:
        return None, ('нет ни решения, ни ответа'
                      + (' (решение с OLE)' if sol_ole else ''))
    if notes:
        q['notes'] = '; '.join(notes)
    return q, None


# ---------------------------------------------------------------------------
# Слияние одинаковых вопросов разных классов (внутри года)
# ---------------------------------------------------------------------------

def _norm_merge(text):
    """Нормализация для слияния классов: пробелы, регистр, ё→е, хвостовая
    пунктуация (в разных файлах года «вперёд» vs «вперед»)."""
    t = WS_RE.sub(' ', text).strip().lower().replace('ё', 'е')
    return t.rstrip(';.').strip()


def dedup_key_m(q):
    return (_norm_merge(q['statement']), q['qtype'],
            json.dumps([_norm_merge(o) for o in q['options']],
                       ensure_ascii=False),
            json.dumps(q['correct']), q['unit'])


def merge_questions_m(all_questions):
    merged, order = {}, []
    for q in all_questions:
        key = dedup_key_m(q)
        if key in merged:
            tgt = merged[key]
            tgt['grades'] = sorted(set(tgt['grades'] + q['grades']))
            tgt['numbers'][q['grade_group']] = q['number']
            tgt['grade_group'] = tgt['grade_group'] + ', ' + q['grade_group']
            if len(q['solution']) > len(tgt['solution']):
                tgt['solution'] = q['solution']
            if q.get('notes') and not tgt.get('notes'):
                tgt['notes'] = q['notes']
        else:
            q['numbers'] = {q['grade_group']: q['number']}
            merged[key] = q
            order.append(key)
    return [merged[k] for k in order]


# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = ('Разбор материалов муниципального этапа ВсОШ (Москва) в '
            'materials/vsosh_municip/<год>/parsed.json')

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int,
                            help='один год (по умолчанию все 2017–2023)')

    def handle(self, *args, **options):
        import fitz  # PyMuPDF — только локально

        years = [options['year']] if options['year'] else YEARS
        for year in years:
            if year not in YEAR_FILES:
                raise CommandError(f'Год {year} не описан в YEAR_FILES')
            self.parse_year(year, fitz)

    def _merge_2022_tasks(self, fitz, year, group, grades, qs, unp):
        """Двухфайловая сборка 2022: условия/варианты из чистого tasks-файла
        (в ans задвоены глифы Cambria Math), ответы/решения — из ans.
        Вопрос, оставшийся с задвоенным условием без чистой пары, → unparsed."""
        tasks_path = find_file(year, TASKS_FILES_2022[group])
        profile = dict(PROFILES[year])
        profile['answer'] = 'none'
        profile.pop('doubled_math', None)
        doc = fitz.open(str(tasks_path))
        qs_tasks, _ = parse_document_a(doc, grades, group, profile,
                                       tasks_path.name)
        by_key = {(t['section'], t['number']): t for t in qs_tasks}
        kept = []
        for q in qs:
            t = by_key.get((q['section'], q['number']))
            opts_ok = (not q['options'] or not t
                       or len(t['options']) == len(q['options']))
            if t and opts_ok:
                q['statement'] = t['statement']
                if q['options'] and t['options']:
                    q['options'] = t['options']
                q.pop('doubled', None)
                # пометки о сборке формул берём из чистого файла условий
                t_notes = t.get('notes')
                if t_notes and t_notes not in (q.get('notes') or ''):
                    q['notes'] = ((q['notes'] + '; ' + t_notes)
                                  if q.get('notes') else t_notes)
            if q.pop('doubled', False):
                unp.append({'grade_group': group, 'number': q['number'],
                            'qtype': q['qtype'],
                            'reason': 'задвоенные глифы Word в условии — '
                                      'чистой пары в tasks-файле не нашлось',
                            'raw': q['statement'][:300],
                            'src_file': q['src_file'],
                            'src_page': q['src_page']})
                continue
            kept.append(q)
        return kept, unp

    def parse_year(self, year, fitz):
        all_q, all_unp = [], []
        files_used = {}
        for group, grades, pattern in YEAR_FILES[year]:
            path = find_file(year, pattern)
            files_used[group] = path.name
            if year == 2019:
                qs, unp = parse_docx_2019(path, grades, group, path.name)
            elif year == 2021:
                doc = fitz.open(str(path))
                qs, unp = parse_grid_2021(doc, grades, group, path.name)
                # краткий ответ 2021 — из файла resheniya тем же классом
                resh = find_file(year, pattern.replace('otvety', 'resheniya'))
                files_used[group + ' (решения)'] = resh.name
                doc2 = fitz.open(str(resh))
                qs2, unp2 = parse_document_a(
                    doc2, grades, group, PROFILES[2021], resh.name)
                qs += qs2
                unp += unp2
            else:
                doc = fitz.open(str(path))
                qs, unp = parse_document_a(
                    doc, grades, group, PROFILES[year], path.name)
                if year == 2022:
                    qs, unp = self._merge_2022_tasks(
                        fitz, year, group, grades, qs, unp)
            self.stdout.write(f'{year} {group}: вопросов {len(qs)}, '
                              f'unparsed {len(unp)}')
            all_q.extend(qs)
            all_unp.extend(unp)

        merged = merge_questions_m(all_q)
        by_type = {}
        for q in merged:
            by_type[q['qtype']] = by_type.get(q['qtype'], 0) + 1

        result = {
            'year': year,
            'stage': STAGE,
            'files': files_used,
            'questions': merged,
            'unparsed': all_unp,
        }
        out = MATERIALS / str(year) / 'parsed.json'
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                       encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(
            f'{year}: {len(merged)} уникальных (из {len(all_q)}), '
            f'unparsed {len(all_unp)} -> {out}'))
        for t in ('single', 'numeric', 'open'):
            self.stdout.write(f'  {t}: {by_type.get(t, 0)}')
