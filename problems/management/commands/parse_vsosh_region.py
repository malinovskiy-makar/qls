# -*- coding: utf-8 -*-
"""
parse_vsosh_region — разбор PDF «тест с ответами» регионального этапа ВсОШ
в структурный JSON (materials/vsosh_region/<год>/parsed_<год>.json).

Источник — официальные PDF жюри с iloveeconomics.ru: вопросы + правильные
ответы + комментарии в одном документе. Структура файла (2023):
«Задание 1» — 5 данеток (boolean), «Задание 2» — 5 «выберите один» (single),
«Задание 3» — 5 «выберите все верные» (multi), «Задание 4» — 5 расчётных
с явной строкой «Ответ: …» (numeric). Правильный вариант в заданиях 1–3
помечен ПОЛУЖИРНЫМ маркером («2)» набрано Semibold) — текстом ответ не
написан нигде, поэтому парсим span-уровень PyMuPDF, а не голый текст.

Технические сигналы PDF (LaTeX-вёрстка, Libertinus):
- шрифт с 'Math' в имени = формула → оборачиваем в $...$, юникод-математику
  конвертирует problems.vsosh_unimath;
- кегль меньше базового = степень/индекс: выше базовой линии ^{...}, ниже _{...};
- «этажные» дроби разъезжаются на 2–3 строки — восстанавливаем \frac{...}{...}
  только по трём строгим паттернам (см. Rule A/B/C в _reassemble_fractions);
  что не восстановилось — линеаризуется и честно помечается в notes.

Правило «ничего не выдумывать»: вопрос без однозначного жирного маркера /
с непарсибельным числовым ответом уходит в unparsed с причиной.
Дословно совпадающие вопросы разных классов схлопываются в один экземпляр
с grades: [9, 10, ...]; решение берётся самое длинное (у старших классов
жюри дописывает альтернативные способы — они включают короткий вариант).

Запуск: ./venv/bin/python manage.py parse_vsosh_region --year 2023
"""
import json
import re
from fractions import Fraction
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from problems.vsosh_unimath import replace_unicode_math, strip_soft_junk

# Кегли вёрстки: тело 14.3, первый уровень уменьшения (дроби, скрипты) 11.5,
# второй (индекс внутри дроби) 8.6. Порог «маленького» — относительный.
SMALL_RATIO = 0.85
BOLD_FLAG = 16  # бит полужирного в span['flags'] PyMuPDF

GRADES = (9, 10, 11)

# --- Годоспецифика вёрстки -------------------------------------------------
# Два поколения макета:
# «zadanie» (≈2020–2023): секции «Задание N», данетки в №1, numeric в №4.
# «chast»   (2024–2025):  секции «Часть N», без данеток, numeric в №3,
#                         «Часть 4» — задачи второго тура (НЕ тест, стоп).
PROFILES = {
    'zadanie': {
        'section_re': re.compile(r'^Задание (\d)$'),
        'qtypes': {1: 'boolean', 2: 'single', 3: 'multi', 4: 'numeric'},
        'stop_section': None,
    },
    'chast': {
        'section_re': re.compile(r'^Часть (\d)$'),
        'qtypes': {1: 'single', 2: 'multi', 3: 'numeric'},
        'stop_section': 4,
    },
}
YEAR_PROFILES = {
    2022: 'zadanie',
    2023: 'zadanie',
    2024: 'chast',
    2025: 'chast',
}

PDF_URLS = {
    2022: {
        9: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2022/region_2022_test_answers_9_22810.pdf',
        10: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2022/region_2022_test_answers_10_22808.pdf',
        11: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2022/region_2022_test_answers_11_22809.pdf',
    },
    2023: {
        9: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2023/region_2023_test_answers_9_23512.pdf',
        10: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2023/region_2023_test_answers_10_23513.pdf',
        11: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2023/region_2023_test_answers_11_23511.pdf',
    },
    # URL восстановлены из имён скачанных файлов по схеме сайта (сеть с этой
    # машины к iloveeconomics.ru заблокирована — не сверялись с сервером).
    2024: {
        9: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2024/region_2024_resheniya_9_klass_25173.pdf',
        10: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2024/region_2024_resheniya_10_klass_25172.pdf',
        11: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2024/region_2024_resheniya_11_klass_25171.pdf',
    },
    2025: {
        9: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2025/region_2025_resheniya_9_klass_28274.pdf',
        10: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2025/region_2025_resheniya_10_klass_28275.pdf',
        11: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2025/region_2025_resheniya_11_klass_28276.pdf',
    },
}

# Колонтитулы всех поколений вёрстки: убираем по тексту; голые числа (номера
# страниц) — только если это ТЕКСТОВЫЙ шрифт полного кегля (числители дробей
# набраны Math-шрифтом). Паттерны точечные — целую строку контента не съедят.
HEADER_RES = [
    re.compile(r'^(Тридцатая |XX[IVX]+ )?Всероссийская олимпиада школьников'
               r'( по экономике)?$'),
    re.compile(r'^Всероссийской олимпиады школьников$'),
    re.compile(r'^по экономике$'),
    re.compile(r'^Экономика$'),
    re.compile(r'^\d{4}(/\d{4})?( год)?$'),
    re.compile(r'^\d{1,2} (января|февраля|марта) \d{4} года$'),
    re.compile(r'^Региональный этап(, \d+ класс)?$'),
    re.compile(r'^\d{1,2}(–\d{1,2})? класс$'),
    re.compile(r'^Первый тур\. Тест\.( \d+ класс\.)?$'),
    re.compile(r'^Правильные ответы и комментарии$'),
    re.compile(r'^Ответы, решения и схемы проверки$'),
]
PAGENUM_RE = re.compile(r'^\d{1,2}$')
QSTART_RE = re.compile(r'^(\d)\.(\d)\.\s*')
OPT_RE = re.compile(r'^([1-4])\)\s*')
COMMENT_RE = re.compile(r'^Комментарий\.\s*')
ANSWER_RE = re.compile(r'^Ответ:\s*')
POINTS_RE = re.compile(r'приносит (\d+) балл')

WS_RE = re.compile(r'\s+')


def is_math_span(sp):
    return 'Math' in sp['font']


def span_text(sp):
    return strip_soft_junk(sp['text'])


def line_plain(line):
    """Голый текст строки (для триггеров разметки)."""
    return ''.join(sp['text'] for sp in line['spans']).strip()


class Line:
    """Строка PDF: спаны + геометрия + служебные флаги."""

    def __init__(self, spans, bbox, page_no):
        self.spans = spans
        self.bbox = bbox
        self.page_no = page_no
        self.degraded = False  # остаток этажной дроби, не собранный правилами

    @property
    def plain(self):
        return ''.join(sp['text'] for sp in self.spans).strip()


def extract_lines(doc):
    """Все содержательные строки документа в порядке чтения."""
    body_size = _body_size(doc)
    lines = []
    for page_no, page in enumerate(doc, start=1):
        page_h = page.rect.height
        for block in page.get_text('dict')['blocks']:
            for raw in block.get('lines', []):
                spans = [dict(sp) for sp in raw['spans']
                         if strip_soft_junk(sp['text']).strip() or ' ' in sp['text']]
                if not spans:
                    continue
                text = ''.join(sp['text'] for sp in spans).strip()
                if any(rx.match(text) for rx in HEADER_RES):
                    continue
                # Колонцифра: одинокое число ТЕКСТОВЫМ шрифтом (числители
                # этажных дробей набраны Math-шрифтом — их не трогаем) И
                # у края страницы. Числа в середине — контент (ячейки
                # таблиц, вёрстка 2025 потеряла бы ставки НДФЛ).
                near_edge = (raw['bbox'][1] > 0.85 * page_h
                             or raw['bbox'][3] < 0.10 * page_h)
                if (PAGENUM_RE.match(text) and near_edge
                        and all(not is_math_span(sp) for sp in spans)):
                    continue
                lines.append(Line(spans, raw['bbox'], page_no))
    return lines, body_size


def _body_size(doc):
    """Базовый кегль тела — самый частый размер текстовых спанов."""
    counts = {}
    for page in doc:
        for block in page.get_text('dict')['blocks']:
            for raw in block.get('lines', []):
                for sp in raw['spans']:
                    key = round(sp['size'], 1)
                    counts[key] = counts.get(key, 0) + len(sp['text'])
    return max(counts, key=counts.get)


# ---------------------------------------------------------------------------
# Восстановление этажных дробей
# ---------------------------------------------------------------------------

def _is_small(sp, body):
    return sp['size'] < body * SMALL_RATIO


def _pure_small_math(line, body):
    return all(is_math_span(sp) and _is_small(sp, body) for sp in line.spans)


def _x_overlap(a, b):
    """Доля перекрытия по X относительно более узкой строки."""
    left = max(a.bbox[0], b.bbox[0])
    right = min(a.bbox[2], b.bbox[2])
    if right <= left:
        return 0.0
    narrow = min(a.bbox[2] - a.bbox[0], b.bbox[2] - b.bbox[0])
    return (right - left) / max(narrow, 1e-6)


def _script_mark(sp, base_y):
    """Куда смещён маленький спан: '^' (степень), '_' (индекс) или ''
    (символ меньшего оптического кегля на той же базовой линии — как «⩾»)."""
    dy = sp['origin'][1] - base_y
    if dy < -1.0:
        return '^'
    if dy > 1.0:
        return '_'
    return ''


def _render_math_run(spans, body):
    """Спаны одной формулы → LaTeX-строка (без $), со степенями/индексами."""
    out = ''
    base_size = base_y = None
    for sp in spans:
        txt = replace_unicode_math(span_text(sp))
        small = base_size is not None and sp['size'] < base_size * SMALL_RATIO
        mark = _script_mark(sp, base_y) if small else ''
        if small and mark:
            out += mark + '{' + txt.strip() + '}'
        else:
            if not small:
                base_size, base_y = sp['size'], sp['origin'][1]
            out += txt
    return out.strip()


def _frac_span(num_latex, den_latex, body, y):
    """Псевдоспан с готовым LaTeX (converted=True — конвертер не трогает)."""
    # Хвостовая пунктуация знаменателя («...(1+r_{23}),») выносится из дроби.
    m = re.match(r'^(.*?)([,.;:]*)$', den_latex)
    latex = '\\frac{' + num_latex + '}{' + m.group(1) + '}' + m.group(2)
    return {'text': latex, 'font': 'Math-Converted', 'size': body,
            'origin': (0, y), 'flags': 0, 'converted': True}


def _pure_math(line):
    return all(is_math_span(sp) for sp in line.spans)


def _y_clusters(spans, tol=3.0):
    """Кластеры базовых линий (ярусы выключной формулы)."""
    ys = sorted(set(round(sp['origin'][1], 1) for sp in spans))
    clusters = []
    for y in ys:
        if clusters and y - clusters[-1][-1] <= tol:
            clusters[-1].append(y)
        else:
            clusters.append([y])
    return clusters


def _reconstruct_display(group, body):
    """Выключная формула с этажными дробями (все части ПОЛНОГО кегля —
    в display-режиме LaTeX дробь не уменьшается). Ярусы: числитель / ось
    (знаки =, <, множители) / знаменатель. Собираем проходом слева направо:
    колонки числитель-над-знаменателем → \\frac, осевые спаны — как есть.
    Не собралось однозначно → None (вызывающий код линеаризует с пометкой)."""
    spans = [sp for line in group for sp in line.spans]
    clusters = _y_clusters(spans)
    if len(clusters) == 2:
        top = [sp for sp in spans if round(sp['origin'][1], 1) in clusters[0]]
        bot = [sp for sp in spans if round(sp['origin'][1], 1) in clusters[1]]
        t0 = min(sp['bbox'][0] for sp in top)
        t1 = max(sp['bbox'][2] for sp in top)
        b0 = min(sp['bbox'][0] for sp in bot)
        b1 = max(sp['bbox'][2] for sp in bot)
        overlap = min(t1, b1) - max(t0, b0)
        if overlap <= 0.5 * min(t1 - t0, b1 - b0):
            return None
        num = _render_math_run(sorted(top, key=lambda s: s['bbox'][0]), body)
        den = _render_math_run(sorted(bot, key=lambda s: s['bbox'][0]), body)
        return '\\frac{' + num + '}{' + den + '}'
    if len(clusters) != 3:
        return None
    num_ys, axis_ys, den_ys = clusters

    def level(sp):
        y = round(sp['origin'][1], 1)
        if y in num_ys:
            return 'num'
        if y in axis_ys:
            return 'axis'
        return 'den'

    out = ''
    col_top, col_bot = [], []
    col_x1 = None
    axis_buf = []   # подряд идущие осевые спаны рендерятся одним раном,
                    # чтобы индексы («C» в «P_C=») распознались по кеглю

    def flush_axis():
        nonlocal out, axis_buf
        if axis_buf:
            out += ' ' + _render_math_run(
                sorted(axis_buf, key=lambda s: s['bbox'][0]), body)
            axis_buf = []

    def flush_col():
        nonlocal out, col_top, col_bot, col_x1
        if not col_top and not col_bot:
            return True
        if not col_top or not col_bot:
            return False  # ярус без пары — структура не дробь
        flush_axis()
        num = _render_math_run(sorted(col_top, key=lambda s: s['bbox'][0]), body)
        den = _render_math_run(sorted(col_bot, key=lambda s: s['bbox'][0]), body)
        m = re.match(r'^(.*?)([,.;:]*)$', den)
        out += ' \\frac{' + num + '}{' + m.group(1) + '}' + m.group(2)
        col_top, col_bot, col_x1 = [], [], None
        return True

    for sp in sorted(spans, key=lambda s: s['bbox'][0]):
        lvl = level(sp)
        if lvl == 'axis':
            if not flush_col():
                return None
            axis_buf.append(sp)
        else:
            flush_axis()
            if col_x1 is not None and sp['bbox'][0] > col_x1 + 2:
                if not flush_col():
                    return None
            (col_top if lvl == 'num' else col_bot).append(sp)
            col_x1 = max(col_x1 or sp['bbox'][2], sp['bbox'][2])
    if not flush_col():
        return None
    flush_axis()
    return re.sub(r'\s+', ' ', out).strip()


def reassemble_display_math(lines, body):
    """Группы подряд идущих коротких чисто-математических строк — выключные
    формулы. Успешная сборка → одна строка с готовым LaTeX; неуспешная —
    строки остаются и помечаются degraded (линеаризация будет честно видна)."""
    if not lines:
        return lines
    column_w = max(l.bbox[2] for l in lines) - min(l.bbox[0] for l in lines)
    result = []
    i = 0
    while i < len(lines):
        j = i
        while (j < len(lines) and _pure_math(lines[j])
               and lines[j].bbox[2] - lines[j].bbox[0] < 0.6 * column_w):
            j += 1
        if j - i >= 2:
            group = lines[i:j]
            latex = _reconstruct_display(group, body)
            if latex is not None:
                frac = {'text': latex, 'font': 'Math-Converted',
                        'size': body, 'origin': (0, group[0].bbox[1]),
                        'flags': 0, 'converted': True}
                result.append(Line([frac], group[0].bbox, group[0].page_no))
            else:
                for l in group:
                    l.degraded = True
                    result.append(l)
            i = j
        else:
            result.append(lines[i])
            i += 1
    return result


def reassemble_fractions(lines, body):
    """Три строгих паттерна этажной дроби; остальное — линеаризуется с флагом.

    Rule C: строка перед числителем кончается на «=», после — начинается
            маленьким math-префиксом (знаменатель): «80 = \\frac{100}{1+r}».
    Rule A: два подряд чисто-математических маленьких ряда, стоящих друг под
            другом (перекрытие по X) — числитель над знаменателем.
    Rule B: маленький math-хвост строки + следующая чисто-математическая
            маленькая строка под ним.
    Защита от ложных склеек: обе части не короче 3 символов (одинокая «1» —
    это уехавший индекс, не числитель)."""
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else None

        if _pure_small_math(line, body):
            num_txt = line.plain
            # Rule C: предыдущая (уже собранная) строка кончается на «=»
            if (result and nxt is not None
                    and _render_math_run(result[-1].spans, body).rstrip().endswith('=')
                    and nxt.spans and is_math_span(nxt.spans[0])
                    and _is_small(nxt.spans[0], body)):
                den_spans = []
                rest = list(nxt.spans)
                while rest and is_math_span(rest[0]) and _is_small(rest[0], body):
                    den_spans.append(rest.pop(0))
                frac = _frac_span(_render_math_run(line.spans, body),
                                  _render_math_run(den_spans, body),
                                  body, line.bbox[1])
                result[-1].spans.append(frac)
                if rest:
                    nxt.spans = rest
                    result[-1].spans.extend(rest)
                i += 2
                continue
            # Rule A: две маленькие math-строки друг под другом
            if (nxt is not None and _pure_small_math(nxt, body)
                    and len(num_txt) >= 3 and len(nxt.plain) >= 3
                    and _x_overlap(line, nxt) > 0.5):
                frac = _frac_span(_render_math_run(line.spans, body),
                                  _render_math_run(nxt.spans, body),
                                  body, line.bbox[1])
                merged = Line([frac], line.bbox, line.page_no)
                result.append(merged)
                i += 2
                continue
            # не собралось — линеаризуем и помечаем
            line.degraded = True
            result.append(line)
            i += 1
            continue

        # Rule B: маленький math-хвост + чисто-математическая строка под ним
        if nxt is not None and _pure_small_math(nxt, body) and len(nxt.plain) >= 3:
            tail = []
            head = list(line.spans)
            while head and is_math_span(head[-1]) and _is_small(head[-1], body):
                tail.insert(0, head.pop(0 - 1))
            tail_txt = ''.join(sp['text'] for sp in tail).strip()
            if head and len(tail_txt) >= 3:
                frac = _frac_span(_render_math_run(tail, body),
                                  _render_math_run(nxt.spans, body),
                                  body, line.bbox[1])
                line.spans = head + [frac]
                result.append(line)
                i += 2
                continue

        result.append(line)
        i += 1
    return result


# ---------------------------------------------------------------------------
# Сборка абзаца из строк: скрипты, границы формул, переносы, $...$
# ---------------------------------------------------------------------------

CYR_LOWER_RE = re.compile(r'^[а-яё]')
HYPHEN_END_RE = re.compile(r'[а-яёА-ЯЁ]-$')
# Формула без букв/команд рендерится как обычный текст — не оборачиваем.
NEEDS_DOLLARS_RE = re.compile(r'[A-Za-z\\^_]')


# Два подряд скрипта ОДНОГО типа (_{1,2}_{2}) — так расползаются инлайн
# этажные дроби; KaTeX падает («Double subscript»). Разные типы (q^{7}_{1})
# легальны — не трогаем. Вставка пустой базы {} делает формулу валидной,
# сохранив честную линеаризацию. Группа с одним уровнем вложения ({,}).
DOUBLE_SCRIPT_RE = re.compile(r'([_^])(\{(?:[^{}]|\{[^{}]*\})*\})\s*(?=\1\{)')


def _finish_math(run, issues=None):
    """Готовый math-ран → фрагмент текста (с $...$ или без)."""
    txt = run.strip()
    if not txt:
        return ''
    txt = re.sub(r'(?<!\\)%', r'\\%', txt)
    txt = re.sub(r'(\d),(\d)', r'\1{,}\2', txt)   # десятичная запятая в KaTeX
    txt = WS_RE.sub(' ', txt)
    fixed = DOUBLE_SCRIPT_RE.sub(r'\1\2 {}', txt)
    if fixed != txt:
        txt = fixed
        if issues is not None:
            issues.append('этажная дробь из PDF не собралась — индексы могли '
                          'слипнуться, сверить с оригиналом')
    if NEEDS_DOLLARS_RE.search(txt):
        return '$' + txt + '$'
    return txt


def render_paragraph(line_list, body, indent_breaks=False, left_margin=None,
                     issues=None):
    """Строки → единый текст: математика в $...$, переносы склеены,
    абзацные отступы (для решений) → пустая строка."""
    pieces = []       # готовые текстовые фрагменты
    math_run = ''     # копящаяся формула
    base_size = base_y = None
    prev_line_hyphen = False
    glue_next = False  # после склейки переноса пробел не вставлять

    def flush_math():
        nonlocal math_run, glue_next
        frag = _finish_math(math_run, issues)
        if frag:
            if (pieces and not glue_next
                    and not pieces[-1].endswith((' ', '\n', '(', '«'))):
                pieces.append(' ')
            pieces.append(frag)
            glue_next = False
        math_run = ''

    for li, line in enumerate(line_list):
        if li > 0:
            if indent_breaks and left_margin is not None and line.spans \
                    and not is_math_span(line.spans[0]) \
                    and not line.spans[0].get('converted') \
                    and line.bbox[0] > left_margin + 8:
                flush_math()
                pieces.append('\n\n')
                prev_line_hyphen = False
            elif prev_line_hyphen:
                glue_next = True  # перенос слова: склейка без пробела
            else:
                # межстрочный стык: пробел (в формуле — внутри рана)
                if math_run:
                    math_run += ' '
                elif pieces and not pieces[-1].endswith((' ', '\n')):
                    pieces.append(' ')
        for sp in line.spans:
            txt = span_text(sp)
            if not txt:
                continue
            if sp.get('converted'):
                if base_size is None:
                    base_size, base_y = sp['size'], sp['origin'][1]
                math_run += (' ' if math_run and not math_run.endswith(' ')
                             else '') + txt
                continue
            small = base_size is not None and sp['size'] < base_size * SMALL_RATIO
            mark = _script_mark(sp, base_y) if small else ''
            if not small:
                base_size, base_y = sp['size'], sp['origin'][1]
            if is_math_span(sp):
                conv = replace_unicode_math(txt)
                if small and mark:
                    math_run += mark + '{' + conv.strip() + '}'
                else:
                    math_run += conv
            else:
                flush_math()
                if pieces and pieces[-1] and not glue_next \
                        and not pieces[-1].endswith((' ', '\n')) \
                        and not txt.startswith((' ', ',', '.', ';', ':', ')', '?', '!')):
                    pieces.append(' ')
                pieces.append(txt)
                glue_next = False
        # перенос слова на стыке строк?
        last_txt = ''
        for sp in reversed(line.spans):
            if span_text(sp):
                last_txt = span_text(sp)
                break
        nxt_first = ''
        if li + 1 < len(line_list):
            for sp in line_list[li + 1].spans:
                if span_text(sp):
                    nxt_first = span_text(sp)
                    break
        prev_line_hyphen = bool(HYPHEN_END_RE.search(last_txt.rstrip())
                                and CYR_LOWER_RE.match(nxt_first.lstrip()))
        if prev_line_hyphen:
            # срезаем дефис у последнего фрагмента
            if math_run:
                math_run = math_run.rstrip()[:-1]
            elif pieces:
                pieces[-1] = pieces[-1].rstrip()[:-1]

    flush_math()
    text = ''.join(pieces)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' ([,.;:?!])', r'\1', text)
    text = re.sub(r'\s*\n\n\s*', '\n\n', text)
    return text.strip()


def render_plain_latex(line_list, body):
    """Как render_paragraph, но математика БЕЗ $...$ (для канонизации ответа)."""
    text = render_paragraph(line_list, body)
    return text.replace('$', '')


# ---------------------------------------------------------------------------
# Канонизация числового ответа
# ---------------------------------------------------------------------------

# «Атом» простой слэш-дроби: число (100), буквенная переменная (Q, P), либо
# переменная РОВНО с одним индексом/степенью — с фигурными скобками или без
# (P_e, P_{e}, Q^2, Q^{2}), либо коэффициент+буквы (2M). Составные выражения
# (5 \cdot 2, 1+r_{12}, w^{2}+20) атомом не являются — туда \frac не лезем.
ATOM = r'[A-Za-z0-9]+(?:[_^]\{?[A-Za-z0-9]+\}?)?'

# Простая слэш-дробь ВНУТРИ математики: «атом / атом» (Y=2M/P -> \frac{2M}{P},
# P_e/40 -> \frac{P_e}{40}, Q^2/2 -> \frac{Q^{2}}{2}). Границы через lookaround,
# а не \b — не должны затрагивать соседние скобки/\frac{...} (\frac{100}{...},
# 10/(5 \cdot 2), (8w-w^{2}+20)/(10-w) осознанно НЕ трогаем — не «простые»).
FRAC_RE = re.compile(r'(?<![A-Za-z0-9\\{}_^])(' + ATOM + r')\s*/\s*(' + ATOM
                     + r')(?![A-Za-z0-9{}_^])')
# Дробь в скобках со степенью снаружи: (A/B)^N -> \left(\frac{A}{B}\right)^{N}
# — обычные скобки малы для \frac внутри, поэтому вместе с дробью растут в
# \left(...\right). Применяется ДО общего FRAC_RE (иначе останется голое ^N
# при обычных скобках).
PAREN_FRAC_POW_RE = re.compile(
    r'\(\s*(' + ATOM + r')\s*/\s*(' + ATOM + r')\s*\)\s*\^\s*\{?([A-Za-z0-9]+)\}?')
# Два и более дефиса/коротких тире подряд (--, ––) -> одно длинное тире.
# Настоящий em dash (—) не входит в класс — не трогаем уже верное тире.
DASH_RUN_RE = re.compile(r'[-‐‑‒–]{2,}')
MATH_SEGMENT_RE = re.compile(r'(\$[^$]*\$)')
# Радикал из юникод-математики (√KL -> \sqrt KL): без скобок KaTeX возьмёт
# под корень один символ, а в PDF винкулум накрывает весь буквенный ран.
SQRT_RUN_RE = re.compile(r'\\sqrt\s+([A-Za-z]+|\d+)')
# Индекс корня: маленькая цифра перед радикалом распознаётся кегельной
# логикой как степень (^{4}\sqrt{KL}), а в вёрстке это корень 4-й степени.
ROOT_INDEX_RE = re.compile(r'\^\{(\d+)\}\s*\\sqrt\{')

NUMBER_RE = re.compile(r'^-?\d+(?:[.,]\d+)?(?:/\d+)?$')
VAR_EQ_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_{}\\]*\s*=\s*(.+)$')
UNIT_RE = re.compile(r'^(-?\d+(?:[.,]\d+)?(?:/\d+)?)\s*(\\?%|[а-яё.\s]+)$')


def _parses_as_number(s):
    t = s.replace(' ', '').replace(',', '.')
    try:
        if '/' in t:
            num, den = t.split('/')
            Fraction(num) / Fraction(den)
        else:
            Fraction(t)
        return True
    except (ValueError, ZeroDivisionError):
        return False


def _escape_unmatched_braces(inner):
    """Литеральная фигурная скобка из PDF (кусочная функция, cases) остаётся
    в тексте непарной и ломает KaTeX. Скобки LaTeX-групп (^{...}, \\frac{}{})
    парсер порождает парами; непарные — вёрстка — экранируем в \\{ / \\}."""
    stack, orphans = [], []
    for i, ch in enumerate(inner):
        if inner[i - 1] == '\\' and i > 0:
            continue
        if ch == '{':
            stack.append(i)
        elif ch == '}':
            if stack:
                stack.pop()
            else:
                orphans.append(i)
    bad = set(stack) | set(orphans)
    if not bad:
        return inner
    return ''.join('\\' + ch if i in bad else ch for i, ch in enumerate(inner))


def postprocess_text(text):
    """Косметика по уже отрендеренному тексту (statement/solution/options):
    слэш-дроби -> \\frac только внутри $...$, двойные дефисы/тире -> «—»
    только вне $...$ (внутри математики дефис может быть минусом)."""
    if not text:
        return text
    parts = MATH_SEGMENT_RE.split(text)
    out = []
    for part in parts:
        if part.startswith('$') and part.endswith('$') and len(part) >= 2:
            inner = part[1:-1]
            inner = PAREN_FRAC_POW_RE.sub(
                r'\\left(\\frac{\1}{\2}\\right)^{\3}', inner)
            inner = FRAC_RE.sub(r'\\frac{\1}{\2}', inner)
            inner = SQRT_RUN_RE.sub(r'\\sqrt{\1}', inner)
            inner = ROOT_INDEX_RE.sub(r'\\sqrt[\1]{', inner)
            inner = _escape_unmatched_braces(inner)
            out.append('$' + inner + '$')
        else:
            out.append(DASH_RUN_RE.sub('—', part))
    return ''.join(out)


def canonicalize_answer(raw):
    """«Ответ: …» → (correct, unit) или (None, причина).

    «50.» → ('50', ''); «19 % или 0,19.» → ('0,19', '') — безразмерная форма
    предпочтительнее; «𝑄= 2.» → ('2', ''); «120 руб.» → ('120', 'руб.')."""
    text = raw.strip().rstrip('.').strip()
    if not text:
        return None, 'пустой ответ'
    candidates = [c.strip() for c in re.split(r'\s+или\s+', text) if c.strip()]
    parsed = []  # (value, unit)
    for cand in candidates:
        m = VAR_EQ_RE.match(cand)
        if m:
            cand = m.group(1).strip()
        cand = cand.rstrip('.').strip()
        if NUMBER_RE.match(cand.replace(' ', '')):
            parsed.append((cand.replace(' ', ''), ''))
            continue
        m = UNIT_RE.match(cand)
        if m and _parses_as_number(m.group(1)):
            unit = m.group(2).replace('\\%', '%').strip()
            parsed.append((m.group(1), unit))
    if not parsed:
        return None, f'ответ не канонизируется: {text!r}'
    for value, unit in parsed:       # безразмерная форма важнее
        if not unit:
            return (value, ''), None
    return parsed[0], None


# ---------------------------------------------------------------------------
# Сегментация документа на вопросы
# ---------------------------------------------------------------------------

def parse_document(doc, grade, errors, profile):
    """PDF одного класса → (questions, unparsed, preambles)."""
    section_re = profile['section_re']
    section_qtypes = profile['qtypes']
    stop_section = profile['stop_section']
    lines, body = extract_lines(doc)
    lines = reassemble_display_math(lines, body)   # выключные формулы
    lines = reassemble_fractions(lines, body)      # строчные этажные дроби
    left_margin = min((l.bbox[0] for l in lines
                       if l.spans and not is_math_span(l.spans[0])), default=0)

    questions, unparsed, preambles = [], [], []
    section = None
    points_by_section = {}
    state = 'idle'
    cur = None
    buffers = {}

    def new_buffers():
        return {'statement': [], 'options': [], 'answer': [], 'solution': [],
                'preamble': []}

    buffers = new_buffers()

    def flush_question():
        nonlocal cur
        if cur is None:
            return
        q, reason = build_question(cur, buffers, body, left_margin, grade)
        if reason:
            raw = '\n'.join(l.plain for key in
                            ('statement', 'options_flat', 'answer', 'solution')
                            for l in _flat(buffers, key))
            unparsed.append({'grade': grade, 'number': cur['number'],
                             'qtype': cur['qtype'], 'reason': reason,
                             'raw': raw})
        else:
            questions.append(q)
        cur = None

    def strip_marker(line, marker_re):
        """Срезает маркер («1.1.», «2)», «Ответ:») с начала строки.
        Возвращает (строка без маркера, был ли маркер полужирным).
        Смещение конца маркера считается по СКЛЕЙКЕ сырых текстов спанов —
        строго та же система координат, по которой потом режем спаны."""
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
                # спан целиком внутри маркера
                if t.strip() and sp['flags'] & BOLD_FLAG:
                    bold = True
                continue
            if start >= cut:
                new_spans.append(sp)
                continue
            # маркер кончается внутри этого спана
            if t[:cut - start].strip() and sp['flags'] & BOLD_FLAG:
                bold = True
            rest = t[cut - start:]
            if rest.strip():
                sp2 = dict(sp)
                sp2['text'] = rest
                new_spans.append(sp2)
        line = Line(new_spans, line.bbox, line.page_no)
        return line, bold

    for line in lines:
        plain = line.plain

        m = section_re.match(plain)
        if m:
            flush_question()
            if state == 'preamble' and buffers['preamble']:
                preambles.append({'section': section,
                                  'text': render_paragraph(buffers['preamble'], body)})
            section = int(m.group(1))
            if stop_section is not None and section >= stop_section:
                # дальше не тест (развёрнутые задачи) — прекращаем разбор
                section = None
                state = 'idle'
                cur = None
                buffers = new_buffers()
                break
            state = 'preamble'
            buffers = new_buffers()
            continue

        m = QSTART_RE.match(plain)
        if m and section is not None and int(m.group(1)) == section:
            flush_question()
            if state == 'preamble' and buffers['preamble']:
                preambles.append({'section': section,
                                  'text': render_paragraph(buffers['preamble'], body)})
            buffers = new_buffers()
            stripped, _ = strip_marker(line, QSTART_RE)
            cur = {'number': f'{m.group(1)}.{m.group(2)}', 'section': section,
                   'qtype': section_qtypes.get(section)}
            buffers['statement'].append(stripped)
            state = 'statement'
            continue

        m = OPT_RE.match(plain)
        if (m and cur is not None
                and cur['qtype'] in ('boolean', 'single', 'multi')
                and state in ('statement', 'options')
                and int(m.group(1)) == len(buffers['options']) + 1):
            stripped, bold = strip_marker(line, OPT_RE)
            buffers['options'].append({'lines': [stripped], 'bold': bold})
            state = 'options'
            continue

        m = COMMENT_RE.match(plain)
        if m and state != 'preamble' and cur is not None:
            stripped, _ = strip_marker(line, COMMENT_RE)
            buffers['solution'] = [stripped] if stripped.spans else []
            state = 'solution'
            continue

        m = ANSWER_RE.match(plain)
        if (m and cur is not None and cur['qtype'] == 'numeric'
                and state == 'statement'):
            stripped, _ = strip_marker(line, ANSWER_RE)
            buffers['answer'].append(stripped)
            state = 'answer'
            continue

        # обычная строка — в текущий буфер
        if state == 'preamble':
            buffers['preamble'].append(line)
            if not points_by_section.get(section):
                pm = POINTS_RE.search(plain)
                if pm:
                    points_by_section[section] = int(pm.group(1))
        elif state == 'statement' and cur is not None:
            buffers['statement'].append(line)
        elif state == 'options' and buffers['options']:
            buffers['options'][-1]['lines'].append(line)
        elif state == 'answer':
            buffers['answer'].append(line)
        elif state == 'solution':
            buffers['solution'].append(line)

    flush_question()

    for q in questions:
        q['points'] = points_by_section.get(int(q['number'].split('.')[0]))
    return questions, unparsed, preambles


def _flat(buffers, key):
    if key == 'options_flat':
        return [l for opt in buffers['options'] for l in opt['lines']]
    return buffers.get(key, [])


def build_question(cur, buffers, body, left_margin, grade):
    """Буферы → словарь вопроса; (None, причина) при любой неоднозначности."""
    qtype = cur['qtype']
    if qtype is None:
        return None, f'неизвестное задание {cur["section"]}'

    issues = []
    statement = render_paragraph(buffers['statement'], body, issues=issues)
    if not statement:
        return None, 'пустое условие'
    statement = postprocess_text(statement)

    degraded = any(l.degraded for key in ('statement', 'options_flat', 'solution')
                   for l in _flat(buffers, key))

    solution = render_paragraph(buffers['solution'], body,
                                indent_breaks=True, left_margin=left_margin,
                                issues=issues)
    solution = postprocess_text(solution)

    opts = [postprocess_text(render_paragraph(o['lines'], body, issues=issues))
            for o in buffers['options']]
    bold_idx = [i for i, o in enumerate(buffers['options']) if o['bold']]

    q = {'grades': [grade], 'number': cur['number'], 'qtype': qtype,
         'statement': statement, 'options': [], 'correct': None,
         'unit': '', 'solution': solution, 'points': None}
    notes = []
    if degraded:
        notes.append('математика линеаризована: этажную дробь из PDF '
                     'не удалось собрать автоматически — сверить с оригиналом')
    notes.extend(dict.fromkeys(issues))   # уникальные, порядок сохранён
    if notes:
        q['notes'] = '; '.join(notes)

    if qtype == 'boolean':
        norm = [o.rstrip('.').strip().lower() for o in opts]
        if norm != ['да', 'нет']:
            return None, f'варианты данетки не «Да»/«Нет»: {opts!r}'
        if len(bold_idx) != 1:
            return None, f'жирных маркеров {len(bold_idx)}, ожидался ровно 1'
        q['correct'] = (bold_idx[0] == 0)
        return q, None

    if qtype == 'single':
        if len(opts) != 4:
            return None, f'вариантов {len(opts)}, ожидалось 4'
        if len(bold_idx) != 1:
            return None, f'жирных маркеров {len(bold_idx)}, ожидался ровно 1'
        q['options'] = opts
        q['correct'] = bold_idx[0]
        return q, None

    if qtype == 'multi':
        if len(opts) != 4:
            return None, f'вариантов {len(opts)}, ожидалось 4'
        if not bold_idx:
            return None, 'ни одного жирного маркера'
        q['options'] = opts
        q['correct'] = bold_idx
        return q, None

    # numeric
    if buffers['options']:
        return None, 'у числового вопроса нашлись варианты'
    answer_raw = render_plain_latex(buffers['answer'], body)
    if not answer_raw:
        return None, 'строка «Ответ:» не найдена'
    parsed, err = canonicalize_answer(answer_raw)
    if err:
        return None, err
    q['correct'], q['unit'] = parsed
    return q, None


# ---------------------------------------------------------------------------
# Дедупликация между классами
# ---------------------------------------------------------------------------

def dedup_key(q):
    norm = WS_RE.sub(' ', q['statement']).strip().lower()
    return (norm, q['qtype'], json.dumps(q['options'], ensure_ascii=False),
            json.dumps(q['correct']), q['unit'])


def merge_questions(all_questions):
    merged = {}
    order = []
    for q in all_questions:
        key = dedup_key(q)
        if key in merged:
            tgt = merged[key]
            tgt['grades'] = sorted(set(tgt['grades'] + q['grades']))
            tgt['numbers'][str(q['grades'][0])] = q['number']
            if len(q['solution']) > len(tgt['solution']):
                tgt['solution'] = q['solution']
            if q.get('notes') and not tgt.get('notes'):
                tgt['notes'] = q['notes']
        else:
            q['numbers'] = {str(q['grades'][0]): q['number']}
            merged[key] = q
            order.append(key)
    return [merged[k] for k in order]


class Command(BaseCommand):
    help = 'Разбирает PDF тестов регионального этапа ВсОШ в parsed_<год>.json'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, default=2023)

    def handle(self, *args, **options):
        import fitz  # PyMuPDF — только локально (requirements-local)

        year = options['year']
        folder = Path('materials/vsosh_region') / str(year)
        if not folder.is_dir():
            raise CommandError(f'Нет папки {folder}')
        profile_name = YEAR_PROFILES.get(year)
        if profile_name is None:
            raise CommandError(
                f'Для года {year} не задан профиль вёрстки (YEAR_PROFILES) — '
                'сначала изучить структуру PDF дампером')
        profile = PROFILES[profile_name]

        all_q, all_unparsed, all_preambles = [], [], []
        per_grade_counts = {}
        for grade in GRADES:
            pdf = folder / f'test_answers_{grade}.pdf'
            if not pdf.exists():
                raise CommandError(f'Нет файла {pdf}')
            doc = fitz.open(pdf)
            qs, unp, pre = parse_document(doc, grade, self.stderr, profile)
            per_grade_counts[grade] = len(qs)
            all_q.extend(qs)
            all_unparsed.extend(unp)
            for p in pre:
                p['grade'] = grade
            all_preambles.extend(pre)
            self.stdout.write(f'{pdf.name}: вопросов {len(qs)}, unparsed {len(unp)}')

        merged = merge_questions(all_q)

        # Преамбулы заданий: дедуп по тексту
        pre_merged = {}
        for p in all_preambles:
            key = (p['section'], WS_RE.sub(' ', p['text']))
            pre_merged.setdefault(key, {'section': p['section'],
                                        'text': p['text'], 'grades': []})
            pre_merged[key]['grades'].append(p['grade'])
        preambles = sorted(pre_merged.values(),
                           key=lambda p: (p['section'], p['grades']))

        result = {
            'year': year,
            'stage': 'региональный',
            'tour': 'Первый тур. Тест.',
            'pdf_urls': {str(g): u for g, u in PDF_URLS.get(year, {}).items()},
            'questions': merged,
            'unparsed': all_unparsed,
            'section_preambles': preambles,
        }
        out = folder / f'parsed_{year}.json'
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                       encoding='utf-8')

        by_type = {}
        for q in merged:
            by_type[q['qtype']] = by_type.get(q['qtype'], 0) + 1
        self.stdout.write(self.style.SUCCESS(
            f'Итого: {len(merged)} уникальных вопросов '
            f'(из {len(all_q)} с повторами), unparsed {len(all_unparsed)} '
            f'-> {out}'))
        for t in ('boolean', 'single', 'multi', 'numeric'):
            self.stdout.write(f'  {t}: {by_type.get(t, 0)}')
