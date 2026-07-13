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
        # 2021: в конце файла сводная сетка «Правильные ответы» с повтором
        # «Задание N»/«1.1.» и чекбоксами — не контент, разбор прекращаем.
        # У 11 класса заголовок сетки: «Первый тур. Тест. Правильные ответы.»,
        # у 9/10 секция сетки открывается титулом «Региональный этап» в
        # середине страницы (кромочный фильтр его не берёт). Стоп-строка
        # срабатывает только ПОСЛЕ начала контента (см. parse_document) —
        # титул страницы 1 разбору не мешает.
        'stop_line_re': re.compile(
            r'^(Первый тур\. Тест\. )?Правильные ответы\.?$'
            r'|^Региональный этап$'),
    },
    'chast': {
        'section_re': re.compile(r'^Часть (\d)$'),
        'qtypes': {1: 'single', 2: 'multi', 3: 'numeric'},
        'stop_section': 4,
        'stop_line_re': None,
    },
    # 2019: секции «Часть N» со старыми типами и СКВОЗНОЙ одинарной
    # нумерацией вопросов («1.» … «20.»). Защита от ложных срабатываний
    # (строка текста, начинающаяся числом) — номер обязан быть равен
    # предыдущему + 1.
    'chast_flat': {
        'section_re': re.compile(r'^Часть (\d)$'),
        'qtypes': {1: 'boolean', 2: 'single', 3: 'multi', 4: 'numeric'},
        'stop_section': None,
        'stop_line_re': re.compile(
            r'^(Первый тур\. Тест\. )?Правильные ответы\.?$'),
        'qstart_re': re.compile(r'^(\d{1,2})\.\s+'),
        'flat_numbering': True,
    },
}
YEAR_PROFILES = {
    2016: 'chast_flat',
    2017: 'chast_flat',
    2018: 'chast_flat',
    2019: 'chast_flat',
    2020: 'zadanie',
    2021: 'zadanie',
    2022: 'zadanie',
    2023: 'zadanie',
    2024: 'chast',
    2025: 'chast',
}

PDF_URLS = {
    # 2016–2017: все классы писали один общий тест (единый файл)
    2016: {
        g: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2016/region_2016_test_solutions_7150.pdf'
        for g in (9, 10, 11)
    },
    2017: {
        g: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2017/region_2017_test_9-11_klass_s_otvetami_11618.pdf'
        for g in (9, 10, 11)
    },
    # 2018–2019: 10 и 11 классы писали один общий тест (файл 1011)
    2018: {
        9: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2018/region_2018_test_answers_9_16633.pdf',
        10: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2018/region_2018_test_answers_1011_16632.pdf',
        11: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2018/region_2018_test_answers_1011_16632.pdf',
    },
    2019: {
        9: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2019/region_2019_test_answers_9_18471.pdf',
        10: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2019/region_2019_test_answers_1011_18470.pdf',
        11: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2019/region_2019_test_answers_1011_18470.pdf',
    },
    # 2020: 10 и 11 классы писали один общий тест (файл 10-11)
    2020: {
        9: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2020/region_2020_test_answers_9_19904.pdf',
        10: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2020/region_2020_test_answers_10-11_19906.pdf',
        11: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2020/region_2020_test_answers_10-11_19906.pdf',
    },
    2021: {
        9: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2021/region_2021_test_solutions_9_21401.pdf',
        10: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2021/region_2021_test_solutions_10_21400.pdf',
        11: 'https://www.iloveeconomics.ru/sites/default/files/olimp/region/2021/region_2021_test_solutions_11_21399.pdf',
    },
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
               r'( по экономике)?( \(\d{4} г\.\))?$'),
    re.compile(r'^Всероссийской олимпиады школьников$'),
    re.compile(r'^по экономике$'),
    re.compile(r'^Экономика$'),
    re.compile(r'^\d{4}(/\d{4})?( год)?$'),
    re.compile(r'^\d{1,2} (января|февраля|марта) \d{4} года$'),
    re.compile(r'^Региональный этап(, \d{1,2}(-\d{1,2})? класс)?$'),
    re.compile(r'^\d{1,2}([–-]\d{1,2})? класс$'),
    re.compile(r'^Первый тур\. Тест\.?( \d+(-\d+)? класс\.)?$'),
    re.compile(r'^Правильные ответы и комментарии$'),
    re.compile(r'^Ответы, решения и схемы проверки$'),
]
PAGENUM_RE = re.compile(r'^\d{1,2}$')
QSTART_RE = re.compile(r'^(\d)\.(\d)\.\s*')
OPT_RE = re.compile(r'^([1-4])\)\s*')
# 2016 пишет заголовок «Комментарий» отдельной строкой БЕЗ точки — без
# второй альтернативы блок пояснений жюри влипал в последний вариант (№12).
COMMENT_RE = re.compile(r'^Комментарий\.\s*|^Комментарий\s*$')
ANSWER_RE = re.compile(r'^Ответ:\s*')

# Композиты, разорванные переносом В СОБСТВЕННОМ дефисе: от словопереноса
# текстом не отличимы, поэтому перечислены явно — список полон для корпуса
# 2016–2025 (полный скан всех 806 склеек переносов).
COMPOUND_JOINS = {
    ('из', 'за'),
    ('врачей', 'рентгенологов'),
    ('причинно', 'следственной'),
    ('стране', 'экспортере'),
    ('товар', 'комплемент'),
    ('фирмы', 'монополиста'),
}

# Гомоглифы: латиница, визуально неотличимая от кириллицы, внутри русских
# слов («нe», «c капитализацией») — и из PDF-вёрстки, и из текстового слоя.
HOMOGLYPH_TRANS = str.maketrans('aceopxyABCEHKMOPTX',
                                'асеорхуАВСЕНКМОРТХ')
CYR_WORD_RE = re.compile(r'[\w-]*[а-яёА-ЯЁ][\w-]*')
LONE_LAT_RE = re.compile(r'(?<=[а-яёА-ЯЁ,)»] )([caoy])(?= [а-яёА-ЯЁ«(\d])')


def fix_homoglyphs(text):
    """Латинские двойники кириллицы → кириллица: внутри слов, содержащих
    кириллицу, и в одиночных «предлогах» (c/a/o/y) между русскими словами.
    Слова без кириллицы (N-ске — «N» отдельно, U-образный, GDP) не трогаем."""
    def fix_word(m):
        w = m.group(0)
        return w.translate(HOMOGLYPH_TRANS)
    text = CYR_WORD_RE.sub(fix_word, text)
    return LONE_LAT_RE.sub(lambda m: m.group(1).translate(HOMOGLYPH_TRANS),
                           text)
POINTS_RE = re.compile(r'(?:приносит|оценивается в) (\d+) балл')

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
        self.degraded_gid = None  # id группы выключной формулы (для дочистки)

    @property
    def plain(self):
        return ''.join(sp['text'] for sp in self.spans).strip()


def _split_span_by_baseline(sp):
    """Спан → подспаны с единой посимвольной базовой линией.

    MuPDF при склейке спанов «затягивает» origin.y соседних кусков к одному
    значению (полноразмерный « + 5,324 + 133,1» получает y индекса «2», хотя
    посимвольные origin'ы верные: ось «+» на 154.6, числитель на 145.7).
    Без разрезки ярусная кластеризация дробей и скрипт-детекция ломаются."""
    chars = sp.get('chars')
    if not chars:
        return [sp]
    groups = []
    pending_ws = []   # пробелы нейтральны: синтетический пробел MuPDF несёт
    for ch in chars:  # чужой y и не должен рождать собственный «ярус»
        if ch['c'].isspace():
            if groups:
                groups[-1]['chars'].append(ch)
            else:
                pending_ws.append(ch)
            continue
        y = round(ch['origin'][1], 1)
        if groups and abs(groups[-1]['y'] - y) <= 0.5:
            groups[-1]['chars'].append(ch)
        else:
            groups.append({'y': y, 'chars': pending_ws + [ch]})
            pending_ws = []
    if pending_ws:
        if groups:
            groups[-1]['chars'].extend(pending_ws)
        else:
            groups.append({'y': round(pending_ws[0]['origin'][1], 1),
                           'chars': pending_ws})
    out = []
    for g in groups:
        cs = g['chars']
        text = ''.join(c['c'] for c in cs)
        # bbox — по видимым символам: пробел по краям (синтетический,
        # MuPDF) растягивает рамку и ломает геометрию (дробь «не влезает»
        # в свою черту)
        vis = [c for c in cs if not c['c'].isspace()] or cs
        x0 = min(c['bbox'][0] for c in vis)
        x1 = max(c['bbox'][2] for c in vis)
        y0 = min(c['bbox'][1] for c in vis)
        y1 = max(c['bbox'][3] for c in vis)
        sub = {k: v for k, v in sp.items() if k != 'chars'}
        sub['text'] = text
        sub['origin'] = (cs[0]['origin'][0], g['y'])
        sub['bbox'] = (x0, y0, x1, y1)
        sub['chars'] = cs   # для поздней x-разрезки (границы радиканда)
        out.append(sub)
    return out


def _split_span_at_x(sp, x):
    """Спан → (левая часть до x, правая от x) по посимвольным рамкам.
    Нужен, когда граница радиканда/дроби проходит внутри спана."""
    chars = sp.get('chars')
    if not chars:
        return (sp, None) if sp['bbox'][2] <= x else (None, sp)
    left = [c for c in chars if (c['bbox'][0] + c['bbox'][2]) / 2 <= x]
    right = [c for c in chars if (c['bbox'][0] + c['bbox'][2]) / 2 > x]
    def build(cs):
        if not cs or not ''.join(c['c'] for c in cs).strip():
            return None
        sub = {k: v for k, v in sp.items() if k != 'chars'}
        vis = [c for c in cs if not c['c'].isspace()] or cs
        sub['text'] = ''.join(c['c'] for c in cs)
        sub['origin'] = (cs[0]['origin'][0], sp['origin'][1])
        sub['bbox'] = (min(c['bbox'][0] for c in vis),
                       min(c['bbox'][1] for c in vis),
                       max(c['bbox'][2] for c in vis),
                       max(c['bbox'][3] for c in vis))
        sub['chars'] = cs
        return sub
    return build(left), build(right)


def extract_bars(doc):
    """Горизонтальные черты (векторная графика) по страницам — кандидаты
    в черты дробей: {page_no: [(x0, x1, y), …]}."""
    bars = {}
    for page_no, page in enumerate(doc, start=1):
        out = []
        for d in page.get_drawings():
            for item in d['items']:
                if item[0] == 'l':
                    p1, p2 = item[1], item[2]
                    if abs(p1.y - p2.y) < 0.6 and abs(p2.x - p1.x) > 3:
                        out.append((min(p1.x, p2.x), max(p1.x, p2.x),
                                    (p1.y + p2.y) / 2))
                elif item[0] == 're':
                    r = item[1]
                    if r.height < 2 and r.width > 3:
                        out.append((r.x0, r.x1, (r.y0 + r.y1) / 2))
        bars[page_no] = out
    return bars


def _polyline_figure_marks(page):
    """Рамки компактных плотных кластеров коротких сегментов — график,
    нарисованный полилинией (не кривыми Безье). Возвращает список Rect.

    Отсекается: сетка ответов/бланк (сотни сегментов, но РАСТЯНУТЫ на всю
    страницу — не компактны) и редкие сегменты текста (кластер < 15)."""
    import fitz
    centers = []
    for d in page.get_drawings():
        for item in d['items']:
            if item[0] != 'l':
                continue
            p1, p2 = item[1], item[2]
            if ((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2) ** 0.5 < 50:
                centers.append(((p1.x + p2.x) / 2, (p1.y + p2.y) / 2))
    if len(centers) < 15:
        return []
    # жадная пространственная кластеризация центров (порог 34pt)
    clusters = []
    for c in centers:
        for cl in clusters:
            if any((c[0] - q[0]) ** 2 + (c[1] - q[1]) ** 2 < 34 ** 2 for q in cl):
                cl.append(c)
                break
        else:
            clusters.append([c])
    out = []
    for cl in clusters:
        if len(cl) < 15:
            continue
        x0 = min(p[0] for p in cl); x1 = max(p[0] for p in cl)
        y0 = min(p[1] for p in cl); y1 = max(p[1] for p in cl)
        # компактный (график ~150×150; сетка ответов растянута >320)
        if x1 - x0 < 300 and y1 - y0 < 300:
            out.append(fitz.Rect(x0, y0, x1, y1))
    return out


def extract_figures(doc):
    """Зоны рисунков (графики) по страницам: {page_no: [Rect, …]}.

    График выдаёт себя диагональными отрезками (кривые D/S/MR, КПВ) и
    кривыми Безье; линейки таблиц и черты дробей строго горизонтальны/
    вертикальны и сюда не попадают. Зона — объединение рамок таких
    элементов (+поля), если их ≥3 на странице рядом. ВТОРОЙ путь: график,
    нарисованный полилинией (много коротких прямых сегментов вместо кривых
    Безье), — компактный плотный кластер коротких отрезков."""
    import fitz
    figures = {}
    for page_no, page in enumerate(doc, start=1):
        marks = []
        for d in page.get_drawings():
            for item in d['items']:
                r = d['rect']
                if item[0] == 'c':
                    # мелкие безье — углы рамок-маркеров, галочки, логотипы
                    if max(r.width, r.height) > 30:
                        marks.append(r)
                elif item[0] == 'l':
                    p1, p2 = item[1], item[2]
                    if abs(p1.x - p2.x) > 8 and abs(p1.y - p2.y) > 8:
                        marks.append(r)
        # полилинийный график — самостоятельная уверенная зона (плотный
        # компактный кластер коротких сегментов), минует порог ≥3 марок
        poly = _polyline_figure_marks(page)
        if len(marks) < 3 and not poly:
            continue
        # кластеризация: жадное слияние пересекающихся (с полем 12pt) рамок
        zones = [fitz.Rect(r.x0 - 12, r.y0 - 12, r.x1 + 12, r.y1 + 12)
                 for r in poly]
        for r in marks:
            r = fitz.Rect(r.x0 - 12, r.y0 - 12, r.x1 + 12, r.y1 + 12)
            for z in zones:
                if z.intersects(r):
                    z.include_rect(r)
                    break
            else:
                zones.append(r)
        # оси графика — прямые линии, примыкающие к зоне кривых: зона
        # прирастает ими (и их подписями рядом), иначе подписи осей
        # остаются снаружи
        straight = []
        for d in page.get_drawings():
            for item in d['items']:
                if item[0] == 'l':
                    p1, p2 = item[1], item[2]
                    if abs(p1.x - p2.x) > 15 or abs(p1.y - p2.y) > 15:
                        straight.append(d['rect'])
        for _ in range(2):
            for r in straight:
                rr = fitz.Rect(r.x0 - 12, r.y0 - 12, r.x1 + 12, r.y1 + 12)
                for z in zones:
                    if z.intersects(rr):
                        z.include_rect(rr)
                        break
        figures[page_no] = zones
    return figures


def drop_figure_labels(lines, figures):
    """Строки целиком внутри зоны рисунка — подписи осей/кривых (P, Q, D,
    MR, 8, 16 …), в тексте задачи им не место. Возвращает (строки,
    зоны-с-удалёнными-подписями по страницам) — вопрос-владелец рисунка
    парсер пометит по вертикальному соседству с зоной (не по всей странице)."""
    kept = []
    used_zones = {}   # page_no -> [(y0, y1), …] зон, из которых что-то удалено
    label_re = re.compile(r'[а-яёА-ЯЁ]{4,}')
    # короткая подпись оси/деления: 1–4 значимых символа (P, Q, TC, 10, 100),
    # без длинного русского слова — такие метки сидят вплотную СНАРУЖИ рамки
    # кривой (у концов осей), поэтому ловим их в поле ±22pt вокруг зоны
    MARGIN = 22

    def short_axis_label(l):
        plain = l.plain.replace('$', '').strip()
        return plain and len(plain) <= 4 and not label_re.search(plain)

    for l in lines:
        zones = figures.get(l.page_no, [])
        hit = None
        for z in zones:
            inside = (l.bbox[0] >= z.x0 and l.bbox[2] <= z.x1
                      and l.bbox[1] >= z.y0 and l.bbox[3] <= z.y1)
            near = (z.x0 - MARGIN <= (l.bbox[0] + l.bbox[2]) / 2 <= z.x1 + MARGIN
                    and z.y0 - MARGIN <= (l.bbox[1] + l.bbox[3]) / 2 <= z.y1 + MARGIN)
            if inside or (near and short_axis_label(l)):
                hit = z
                break
        # подпись — короткие латинские/цифровые метки; строка с русским
        # словом (заголовок, текст, «Ответ: …») контентная даже в зоне
        if hit is not None and not label_re.search(l.plain):
            used_zones.setdefault(l.page_no, [])
            key = (round(hit.y0, 1), round(hit.y1, 1))
            if key not in used_zones[l.page_no]:
                used_zones[l.page_no].append(key)
        else:
            kept.append(l)
    return kept, used_zones


# ---------------------------------------------------------------------------
# Реконструкция таблиц из геометрии PDF → $$\begin{array}...$$
# ---------------------------------------------------------------------------
# Класс дефекта: таблица (шкала НДФЛ, спрос/предложение, ряд цен по периодам)
# размазана в строку текста. Детекция — по горизонтальным линейкам одинаковой
# ширины/x-охвата (booktabs) + консистентности колонок; реконструкция — строки
# по бандам между линейками, колонки по вертикальным линейкам или по якорям
# (центры ячеек строки с максимумом ячеек). Формат — LaTeX-массив (см.
# reports/vsosh_region/structure_audit.md, Фаза 1). Детектор синхронизирован
# с manage.py audit_vsosh_structure.

TBL_CYR = re.compile(r'[а-яёА-ЯЁ]{3,}')
TBL_SECTION_RE = re.compile(r'^(Часть|Задание)\s+\d|Правильные ответы'
                            r'|Региональн|Первый тур|олимпиад|Ответы, решения')
TBL_ANSGRID_RE = re.compile(r'Образец|Бланк|Конкурс|заполнени'
                            r'|(?:\d\.\d\.\s*){2,}\d\.\d\.')
TBL_NUM_CELL = re.compile(r'^[-−]?\d')
NUM_ONLY_RE = re.compile(r'^[-−]?\d+(?:[.,]\d+)?$')


def _table_rules(page, y0, y1):
    """Горизонтальные (90–490pt) и вертикальные линейки в зоне + x-охват."""
    hr, vr, hx = [], [], []
    for d in page.get_drawings():
        for it in d['items']:
            if it[0] == 'l':
                p1, p2 = it[1], it[2]
                if (abs(p1.y - p2.y) < 0.8 and 90 <= abs(p2.x - p1.x) <= 490
                        and y0 - 5 < p1.y < y1 + 5):
                    hr.append(p1.y)
                    hx.append((min(p1.x, p2.x), max(p1.x, p2.x)))
                elif (abs(p1.x - p2.x) < 0.8 and abs(p2.y - p1.y) > 10
                      and y0 - 5 < min(p1.y, p2.y) < y1 + 5):
                    vr.append(p1.x)
            elif it[0] == 're':
                r = it[1]
                yc = (r.y0 + r.y1) / 2
                if r.height < 2 and 90 <= r.width <= 490 and y0 - 5 < yc < y1 + 5:
                    hr.append(yc)
                    hx.append((r.x0, r.x1))
                elif r.width < 2 and r.height > 10 and y0 - 5 < r.y0 < y1 + 5:
                    vr.append(r.x0)
    xr = (min(x[0] for x in hx), max(x[1] for x in hx)) if hx else None
    return sorted(hr), sorted(set(round(x, 1) for x in vr)), xr


def _table_span_rows(page, y0, y1, xr):
    """Спаны зоны (посимвольно разрезанные), сгруппированные в визуальные
    строки по базовой линии; клип по x-охвату рамки (боковая проза вопроса
    рядом с таблицей отсекается)."""
    spans = []
    for block in page.get_text('rawdict')['blocks']:
        for line in block.get('lines', []):
            for rsp in line['spans']:
                for sp in _split_span_by_baseline(rsp):
                    if not sp['text'].strip():
                        continue
                    if not (y0 - 2 < sp['origin'][1] < y1 + 2):
                        continue
                    cx = (sp['bbox'][0] + sp['bbox'][2]) / 2
                    if xr and not (xr[0] - 3 <= cx <= xr[1] + 3):
                        continue
                    spans.append(sp)
    return spans


def _band_rows(spans, hr):
    """Логические строки: банды между горизонт. линейками; внутри банды —
    кластеры по базовой линии (booktabs держит несколько строк в одном банде)."""
    rows = []
    for i in range(len(hr) - 1):
        band = [s for s in spans if hr[i] - 0.5 < s['origin'][1] < hr[i + 1] + 0.5]
        if not band:
            continue
        ys = sorted(set(round(s['origin'][1], 1) for s in band))
        clusters = []
        for y in ys:
            if clusters and y - clusters[-1][-1] <= 10:
                clusters[-1].append(y)
            else:
                clusters.append([y])
        for cl in clusters:
            rows.append([s for s in band if round(s['origin'][1], 1) in cl])
    return rows


def _merge_row_cells(row):
    """Спаны строки → ячейки (слияние соседних при зазоре < 14pt)."""
    sp = sorted(row, key=lambda s: s['bbox'][0])
    cells = []
    for s in sp:
        if cells and s['bbox'][0] - cells[-1][-1]['bbox'][2] < 14:
            cells[-1].append(s)
        else:
            cells.append([s])
    return cells


def _column_anchors(rows, vr):
    """Опорные x колонок: середины между вертикальными линейками (полная
    рамка) либо центры ячеек строки с максимумом ячеек (booktabs)."""
    if len(vr) >= 3:
        v = sorted(vr)
        return [(v[i] + v[i + 1]) / 2 for i in range(len(v) - 1)]
    best = max(rows, key=lambda r: len(_merge_row_cells(r)))
    return [(c[0]['bbox'][0] + c[-1]['bbox'][2]) / 2
            for c in _merge_row_cells(best)]


def _render_table_cell(spans, body):
    """Спаны ячейки → фрагмент LaTeX для массива: чистое число — голым,
    математика — без $, текст — в \\text{…}."""
    if not spans:
        return ''
    ln = Line(sorted(spans, key=lambda s: s['bbox'][0]), None, 0)
    txt = render_paragraph([ln], body).strip()
    if NUM_ONLY_RE.match(txt.replace('−', '-')):
        return txt.replace('−', '-')
    parts = re.split(r'(?<!\\)(\$(?:\\.|[^$\\])*\$)', txt)
    out = []
    for p in parts:
        if p.startswith('$') and p.endswith('$') and len(p) >= 2:
            out.append(p[1:-1])
        elif p:
            out.append('\\text{' + p.replace('%', '\\%') + '}')
    return ''.join(out).strip()


def reconstruct_table(page, y0, y1, body):
    """Зона таблицы → строка `$$\\begin{array}…$$` или None, если геометрия
    не складывается в таблицу (тогда вызывающий код оставляет текст как есть)."""
    hr, vr, xr = _table_rules(page, y0, y1)
    if len(hr) < 2 or xr is None:
        return None
    spans = _table_span_rows(page, hr[0], hr[-1], xr)
    rows = _band_rows(spans, hr)
    if len(rows) < 2:
        return None
    anchors = _column_anchors(rows, vr)
    ncols = len(anchors)
    if ncols < 2:
        return None

    def col_of(x):
        return min(range(ncols), key=lambda i: abs(anchors[i] - x))

    grid = [[[] for _ in range(ncols)] for _ in rows]
    for ri, row in enumerate(rows):
        for s in row:
            grid[ri][col_of((s['bbox'][0] + s['bbox'][2]) / 2)].append(s)
    latex_rows = [' & '.join(_render_table_cell(c, body) for c in row)
                  for row in grid]
    colspec = '|' + '|'.join(['l'] + ['c'] * (ncols - 1)) + '|'
    return ('$$\\begin{array}{' + colspec + '}\\hline '
            + ' \\\\ \\hline '.join(latex_rows) + ' \\\\ \\hline\\end{array}$$')


def _detect_table_regions(page, page_h):
    """Зоны реальных таблиц на странице (те же фильтры, что в
    audit_vsosh_structure: линейки одной ширины/x-охвата, консистентные
    колонки, строка-заголовок или числовая матрица; формулы/сетки/заголовки
    секций отсеиваются). Возвращает [(y0, y1)]."""
    rules = sorted(_table_rules(page, 0, page_h * 2)[0])
    rules = [r for r in rules if 0.06 * page_h < r < 0.94 * page_h]
    # группы линеек с совпадающим x-охватом
    raw = _table_rules(page, 0, page_h * 2)
    hr_all = [(y, ) for y in rules]
    # пересобираем с x-охватом каждой линейки
    rule_list = []
    for d in page.get_drawings():
        for it in d['items']:
            if it[0] == 'l':
                p1, p2 = it[1], it[2]
                if abs(p1.y - p2.y) < 0.8 and 90 <= abs(p2.x - p1.x) <= 490:
                    rule_list.append((min(p1.x, p2.x), max(p1.x, p2.x), p1.y))
            elif it[0] == 're':
                r = it[1]
                if r.height < 2 and 90 <= r.width <= 490:
                    rule_list.append((r.x0, r.x1, (r.y0 + r.y1) / 2))
    rule_list = [r for r in rule_list if 0.06 * page_h < r[2] < 0.94 * page_h]
    rule_list.sort(key=lambda t: t[2])
    groups = []
    for r in rule_list:
        for g in groups:
            if (abs(g[0][0] - r[0]) < 16 and abs(g[0][1] - r[1]) < 16
                    and r[2] - g[-1][2] < 230):
                g.append(r)
                break
        else:
            groups.append([r])
    out = []
    for g in groups:
        if len(g) < 2:
            continue
        y0 = min(x[2] for x in g)
        y1 = max(x[2] for x in g)
        xr = (min(x[0] for x in g), max(x[1] for x in g))
        rows = _band_rows(_table_span_rows(page, y0, y1, xr), sorted(x[2] for x in g))
        if len(rows) < 2:
            continue
        alltext = ' '.join(sp['text'] for row in rows for sp in row)
        if TBL_SECTION_RE.search(alltext.strip()[:45]) \
                or TBL_ANSGRID_RE.search(alltext):
            continue
        hdr = any(sum(1 for s in row
                      if TBL_CYR.search(s['text']) and s['bbox'][0] > 55) >= 2
                  for row in rows)
        nummat = sum(1 for row in rows
                     if sum(1 for s in row
                            if TBL_NUM_CELL.match(s['text'].strip())) >= 3) >= 2
        if not (hdr or nummat):
            continue
        out.append((y0, y1, xr))
    return out


def extract_tables(doc, body):
    """{page_no: [(y0, y1, xr, latex)]} — реконструированные таблицы по страницам."""
    tables = {}
    for page_no, page in enumerate(doc, start=1):
        for y0, y1, xr in _detect_table_regions(page, page.rect.height):
            latex = reconstruct_table(page, y0, y1, body)
            if latex:
                tables.setdefault(page_no, []).append((y0, y1, xr, latex))
    return tables


def apply_tables(lines, tables, body):
    """Строки внутри зоны таблицы (по y И x-охвату) заменяются одной
    converted-строкой с готовым `$$\\begin{array}…$$`; боковая проза
    (вне x-охвата) сохраняется."""
    if not tables:
        return lines
    inserted = set()
    result = []
    for l in lines:
        regs = tables.get(l.page_no, [])
        hit = None
        for (y0, y1, xr, latex) in regs:
            lcx = (l.bbox[0] + l.bbox[2]) / 2
            if y0 - 3 <= (l.bbox[1] + l.bbox[3]) / 2 <= y1 + 3 \
                    and xr[0] - 3 <= lcx <= xr[1] + 3:
                hit = (y0, y1, xr, latex)
                break
        if hit is None:
            result.append(l)
            continue
        key = (l.page_no, round(hit[0], 1))
        if key not in inserted:
            inserted.add(key)
            frac = {'text': hit[3], 'font': 'Math-Converted', 'size': body,
                    'origin': (hit[2][0], hit[0]), 'flags': 0,
                    'converted': True, 'is_table': True,
                    'bbox': (hit[2][0], hit[0], hit[2][1], hit[1])}
            result.append(Line([frac], (hit[2][0], hit[0], hit[2][1], hit[1]),
                               l.page_no))
        # строка поглощена таблицей — не добавляем
    return result


def extract_lines(doc):
    """Все содержательные строки документа в порядке чтения."""
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
                text = ''.join(sp['text'] for sp in spans).strip()
                # Колонтитулы отсекаются ТОЛЬКО у кромки страницы: вопрос,
                # переходящий границу страниц, получал колонтитул в середину
                # текста (2019 №19), а строка контента, случайно похожая на
                # колонтитул, в середине страницы не пострадает.
                near_hdr_edge = (raw['bbox'][3] < 0.15 * page_h
                                 or raw['bbox'][1] > 0.85 * page_h)
                if near_hdr_edge and any(rx.match(text) for rx in HEADER_RES):
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


def _mode_baseline(spans, min_size):
    """Доминирующая базовая линия: мода origin.y спанов полного кегля.
    Отдельный спан может нести «затянутый» к соседнему индексу y (артефакт
    сборки строк MuPDF: полноразмерный «−20𝑞» получает y индекса «2») —
    мода по всем полноразмерным спанам от этого устойчива."""
    ys = [round(sp['origin'][1], 1) for sp in spans
          if span_text(sp).strip() and not sp.get('converted')
          and sp['size'] >= min_size]
    if not ys:
        return None
    counts = {}
    for y in ys:
        counts[y] = counts.get(y, 0) + 1
    return max(counts, key=lambda y: (counts[y], -ys.index(y)))


def _render_math_run(spans, body):
    """Спаны одной формулы → LaTeX-строка (без $), со степенями/индексами."""
    out = ''
    sized = [sp for sp in spans if span_text(sp).strip()]
    base_size = max((sp['size'] for sp in sized), default=None)
    base_y = (_mode_baseline(spans, base_size * SMALL_RATIO)
              if base_size else None)
    for sp in spans:
        if sp.get('converted'):
            # уже готовый LaTeX (\sqrt{…}, \frac{…}{…}) — вставляем как есть
            out += (' ' if out and not out.endswith(' ') else '') \
                + sp['text'] + ' '
            continue
        txt = replace_unicode_math(span_text(sp))
        small = base_size is not None and sp['size'] < base_size * SMALL_RATIO
        mark = _script_mark(sp, base_y) if small and base_y is not None else ''
        if small and mark:
            out += mark + '{' + txt.strip() + '}'
        else:
            out += txt
    return out.strip()


def _frac_span(num_latex, den_latex, body, y, bbox=None):
    """Псевдоспан с готовым LaTeX (converted=True — конвертер не трогает)."""
    # Хвостовая пунктуация знаменателя («...(1+r_{23}),») выносится из дроби.
    m = re.match(r'^(.*?)([,.;:]*)$', den_latex)
    latex = '\\frac{' + num_latex + '}{' + m.group(1) + '}' + m.group(2)
    return {'text': latex, 'font': 'Math-Converted', 'size': body,
            'origin': (bbox[0] if bbox else 0, y), 'flags': 0,
            'converted': True,
            'bbox': tuple(bbox) if bbox else (0, y, 0, y)}


def _pure_math(line):
    return all(is_math_span(sp) for sp in line.spans)


def _mathish(line, body):
    """Строка формулы, допускающая малые текстовые вкрапления-подписи
    («max», «min», «ж» — индексы, набранные текстовым шрифтом): полноразмерный
    текст дисквалифицирует («где 𝑃max — …» — обычный текст со вставкой)."""
    for sp in line.spans:
        if is_math_span(sp) or sp.get('converted'):
            continue
        txt = sp['text'].strip()
        if not txt:
            continue
        if sp['size'] >= body * SMALL_RATIO or len(txt) > 4:
            return False
    return any(is_math_span(sp) for sp in line.spans)


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


def _bar_between(page_bars, x0, x1, y_top, y_bot):
    """Есть ли черта между ярусами y_top..y_bot, накрывающая [x0, x1]."""
    for bx0, bx1, by in page_bars:
        if (y_top < by < y_bot
                and min(bx1, x1) - max(bx0, x0) >= 0.8 * (x1 - x0)):
            return True
    return False


def _reconstruct_display(group, body, page_bars):
    """Выключная формула с этажными дробями (все части ПОЛНОГО кегля —
    в display-режиме LaTeX дробь не уменьшается). Ярусы: числитель / ось
    (знаки =, <, множители) / знаменатель. Дробью пара ярусов считается
    ТОЛЬКО при наличии черты между ними в векторной графике (кусочные
    функции и системы уравнений — те же два яруса, но без черты).
    Колонки трёхъярусной формулы тоже режутся ПО ЧЕРТАМ: широкая дробь
    с пробелом в числителе не разваливается на псевдоколонки.
    Не собралось однозначно → None (вызывающий код линеаризует с пометкой)."""
    spans = [sp for line in group for sp in line.spans]
    # Ярусы считаем по полноразмерным спанам: скрипт-цифры (степень «²» у
    # знаменателя) висят между ярусами и разваливали кластеризацию — их
    # прикрепляем к ближайшему ярусу.
    full = [sp for sp in spans if sp['size'] >= body * SMALL_RATIO]
    clusters = _y_clusters(full if full else spans)
    if len(clusters) >= 2:
        def nearest_cluster_ys(sp):
            y = round(sp['origin'][1], 1)
            return min(clusters, key=lambda c: min(abs(y - cy) for cy in c))
        for sp in spans:
            y = round(sp['origin'][1], 1)
            if not any(y in c for c in clusters):
                nearest_cluster_ys(sp).append(y)
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
        if not _bar_between(page_bars, max(t0, b0), min(t1, b1),
                            max(clusters[0]), min(clusters[1])):
            return None   # два яруса без черты — не дробь
        num = _render_math_run(sorted(top, key=lambda s: s['bbox'][0]), body)
        den = _render_math_run(sorted(bot, key=lambda s: s['bbox'][0]), body)
        return '\\frac{' + num + '}{' + den + '}'
    if len(clusters) != 3:
        return None
    num_ys, axis_ys, den_ys = clusters
    frac_bars = sorted(
        (b for b in page_bars
         if max(num_ys) < b[2] < min(den_ys)), key=lambda b: b[0])
    if not frac_bars:
        return None

    def level(sp):
        y = round(sp['origin'][1], 1)
        if y in num_ys:
            return 'num'
        if y in axis_ys:
            return 'axis'
        return 'den'

    def owner_bar(sp):
        cx = (sp['bbox'][0] + sp['bbox'][2]) / 2
        for bi, (bx0, bx1, _) in enumerate(frac_bars):
            if bx0 - 2.5 <= cx <= bx1 + 2.5:
                return bi
        return None

    # раскладка: осевые спаны и дроби (по чертам) в порядке x
    items = []   # (x, 'axis', span) | (x, 'frac', bi)
    frac_parts = {bi: {'num': [], 'den': []} for bi in range(len(frac_bars))}
    seen_frac = set()
    for sp in sorted(spans, key=lambda s: s['bbox'][0]):
        lvl = level(sp)
        if lvl == 'axis':
            items.append((sp['bbox'][0], 'axis', sp))
            continue
        bi = owner_bar(sp)
        if bi is None:
            return None   # ярусный спан вне всех черт — структура неясна
        frac_parts[bi][lvl].append(sp)
        if bi not in seen_frac:
            seen_frac.add(bi)
            items.append((frac_bars[bi][0], 'frac', bi))
    out = ''
    axis_buf = []

    def flush_axis():
        nonlocal out, axis_buf
        if axis_buf:
            out += ' ' + _render_math_run(
                sorted(axis_buf, key=lambda s: s['bbox'][0]), body)
            axis_buf = []

    for _, kind, payload in sorted(items, key=lambda t: t[0]):
        if kind == 'axis':
            axis_buf.append(payload)
            continue
        parts = frac_parts[payload]
        if not parts['num'] or not parts['den']:
            return None   # черта без числителя или знаменателя
        flush_axis()
        num = _render_math_run(
            sorted(parts['num'], key=lambda s: s['bbox'][0]), body)
        den = _render_math_run(
            sorted(parts['den'], key=lambda s: s['bbox'][0]), body)
        m = re.match(r'^(.*?)([,.;:]*)$', den)
        out += ' \\frac{' + num + '}{' + m.group(1) + '}' + m.group(2)
    flush_axis()
    return re.sub(r'\s+', ' ', out).strip()


def reassemble_display_math(lines, body, bars):
    """Группы подряд идущих коротких чисто-математических строк — выключные
    формулы. Успешная сборка → одна строка с готовым LaTeX; неуспешная —
    строки остаются и помечаются degraded (линеаризация будет честно видна)."""
    if not lines:
        return lines
    column_w = max(l.bbox[2] for l in lines) - min(l.bbox[0] for l in lines)
    result = []
    gid = 0
    i = 0
    while i < len(lines):
        j = i
        while (j < len(lines) and _mathish(lines[j], body)
               and lines[j].bbox[2] - lines[j].bbox[0] < 0.6 * column_w):
            j += 1
        if j - i >= 2:
            group = lines[i:j]
            latex = _reconstruct_display(group, body,
                                         bars.get(group[0].page_no, []))
            if latex is not None:
                gb = (min(l.bbox[0] for l in group),
                      min(l.bbox[1] for l in group),
                      max(l.bbox[2] for l in group),
                      max(l.bbox[3] for l in group))
                frac = {'text': latex, 'font': 'Math-Converted',
                        'size': body, 'origin': (gb[0], gb[1]),
                        'flags': 0, 'converted': True, 'bbox': gb}
                result.append(Line([frac], gb, group[0].page_no))
            else:
                # группа помечается общим id: если Rule D позже соберёт её
                # дроби/корни от черты, флаг снимется (clear_resolved_degraded)
                for l in group:
                    l.degraded = True
                    l.degraded_gid = gid
                    result.append(l)
                gid += 1
            i = j
        else:
            result.append(lines[i])
            i += 1
    return result


def clear_resolved_degraded(lines, body):
    """Снимает флаг degraded с групп выключных формул, чьи этажные структуры
    Rule D собрал начисто. Остаток «числитель над знаменателем» (два
    неконвертированных math-спана с перекрытием по X и разными базовыми
    линиями) внутри группы означает, что дробь так и не собралась — флаг
    остаётся честным."""
    groups = {}
    for l in lines:
        if l.degraded and l.degraded_gid is not None:
            groups.setdefault(l.degraded_gid, []).append(l)
    for gid, gls in groups.items():
        spans = [sp for l in gls for sp in l.spans
                 if not sp.get('converted') and sp['text'].strip()
                 and (is_math_span(sp) or sp['size'] < body * SMALL_RATIO)]
        remnant = False
        for a in range(len(spans)):
            for b in range(a + 1, len(spans)):
                sa, sb = spans[a], spans[b]
                if abs(sa['origin'][1] - sb['origin'][1]) < 2:
                    continue   # одна базовая линия — не этаж
                ox = (min(sa['bbox'][2], sb['bbox'][2])
                      - max(sa['bbox'][0], sb['bbox'][0]))
                narrow = min(sa['bbox'][2] - sa['bbox'][0],
                             sb['bbox'][2] - sb['bbox'][0])
                if ox > 0.4 * max(narrow, 1e-6):
                    remnant = True
                    break
            if remnant:
                break
        if not remnant:
            for l in gls:
                l.degraded = False
    return lines


def _find_vinculum_radical(page_lines, bx0, bx1, by):
    """Радикал, чья черта — данный отрезок: спан с «√», примыкающий справа
    к началу черты (x1 ≈ bx0) и телом ниже уровня черты. Возвращает
    (line, span) или None. У ДРОБНОЙ черты со √ в знаменателе радикал
    находится ГЛУБЖЕ под чертой и к её началу не примыкает."""
    for l in page_lines:
        if l.bbox[3] < by - 16 or l.bbox[1] > by + 16:
            continue
        for sp in l.spans:
            if sp.get('converted') or '√' not in sp['text']:
                continue
            if (bx0 - 4 <= sp['bbox'][2] <= bx0 + 3
                    and sp['bbox'][3] > by + 1):
                return l, sp
    return None


def reassemble_intraline_fracs(lines, body, bars):
    """Rule D: сборка дробей и радикандов ОТ ЧЕРТЫ. Куски инлайн-дроби
    (скрипт-кегль в строке текста) после посимвольной разрезки живут в
    одной или соседних псевдостроках; без черты их не отличить от пар
    «степень+индекс» одного токена (Q^{D}_{1}). Идём от каждой векторной
    черты страницы (уже — раньше: вложенные структуры собираются первыми):
    черта с примыкающим радикалом — винкулум → \\sqrt{радиканд};
    иначе спаны внутри x-диапазона выше/ниже — числитель и знаменатель.
    Подчёркивания ссылок (нет числителя) и линейки таблиц (нет math-спанов)
    отсеиваются сами."""
    by_page = {}
    for l in lines:
        by_page.setdefault(l.page_no, []).append(l)

    for page_no, page_lines in by_page.items():
        page_bars = sorted(bars.get(page_no, []),
                           key=lambda b: b[1] - b[0])   # вложенные — первыми
        for bx0, bx1, by in page_bars:
            if bx1 - bx0 > 200 or bx1 - bx0 < 4:
                continue   # линейки страниц/таблиц и точечный мусор

            # --- Винкулум корня: √ примыкает к началу черты ---------------
            rad = _find_vinculum_radical(page_lines, bx0, bx1, by)
            if rad is not None:
                rl, rsp = rad
                rad_y = rsp['origin'][1]
                radicand = []   # (line, span) между чертой и базовой линией
                for l in page_lines:
                    if l.bbox[3] < by - 16 or l.bbox[1] > by + 20:
                        continue
                    for sp in list(l.spans):
                        if sp is rsp or sp.get('converted') \
                                or not sp['text'].strip():
                            continue
                        # от черты вниз до базовой линии радикала: сама
                        # база + степени внутри радиканда (K²+L²)
                        if not (by < sp['origin'][1] < rad_y + 3.5):
                            continue
                        sx0, sx1 = sp['bbox'][0], sp['bbox'][2]
                        if sx0 >= bx0 - 2 and sx1 <= bx1 + 2.5:
                            radicand.append((l, sp))
                        elif sx0 < bx1 - 1 < sx1 and sp.get('chars'):
                            # радиканд кончается внутри спана — режем по x
                            left, right = _split_span_at_x(sp, bx1 + 1)
                            if left is not None and right is not None:
                                idx = l.spans.index(sp)
                                l.spans[idx:idx + 1] = [left, right]
                                radicand.append((l, left))
                if not radicand:
                    continue
                inner = _render_math_run(
                    [sp for _, sp in
                     sorted(radicand, key=lambda t: t[1]['bbox'][0])], body)
                if not inner.strip():
                    continue
                conv = {'text': '\\sqrt{' + inner.strip() + '}',
                        'font': 'Math-Converted', 'size': body,
                        'origin': (rsp['bbox'][0], rad_y),
                        'flags': 0, 'converted': True,
                        'bbox': (rsp['bbox'][0],
                                 min(sp['bbox'][1] for _, sp in radicand),
                                 bx1,
                                 max(sp['bbox'][3] for _, sp in radicand))}
                consumed = {id(rsp)} | {id(sp) for _, sp in radicand}
                for l in set([rl] + [l for l, _ in radicand]):
                    l.spans = [sp for sp in l.spans
                               if id(sp) not in consumed]
                rl.spans = sorted(rl.spans + [conv],
                                  key=lambda s: s['bbox'][0])
                continue

            # --- Дробная черта ---------------------------------------------
            num, den = [], []   # (line, span)
            for l in page_lines:
                if l.bbox[3] < by - 20 or l.bbox[1] > by + 20:
                    continue
                for sp in l.spans:
                    if not sp['text'].strip():
                        continue
                    # ярус дроби — math-шрифт, скрипт-кегль или уже собранное
                    # подвыражение (\sqrt{…}); полноразмерный ТЕКСТ (маркер
                    # варианта «1)» со следующей строки) — нет
                    if not (is_math_span(sp) or sp.get('converted')
                            or sp['size'] < body * SMALL_RATIO):
                        continue
                    sx0, sx1 = sp['bbox'][0], sp['bbox'][2]
                    if sx0 < bx0 - 3 or sx1 > bx1 + 2.5:
                        continue
                    y = sp['origin'][1]
                    if sp.get('converted'):
                        # собранное подвыражение (\sqrt{…}, \frac) высокое,
                        # его рамка перекрывает черту — ярус определяем по
                        # БАЗОВОЙ линии (широкое окно; строгий x-охват черты
                        # уже не пустил чужие спаны)
                        if by - 2.2 * body < y < by:
                            num.append((l, sp))
                        elif by < y < by + 2.2 * body:
                            den.append((l, sp))
                        continue
                    if by - 14 < y < by:
                        num.append((l, sp))
                    elif by < y < by + 14:
                        den.append((l, sp))
            if not num or not den:
                continue
            if not any(is_math_span(sp) or sp.get('converted')
                       for _, sp in num + den):
                continue   # числа в ячейках таблицы — не дробь
            num_txt = _render_math_run(
                [sp for _, sp in sorted(num, key=lambda t: t[1]['bbox'][0])], body)
            den_txt = _render_math_run(
                [sp for _, sp in sorted(den, key=lambda t: t[1]['bbox'][0])], body)
            if not num_txt or not den_txt:
                continue
            host_line, first_sp = min(num + den,
                                      key=lambda t: (t[1]['origin'][1],
                                                     t[1]['bbox'][0]))
            frac = _frac_span(num_txt, den_txt, body, by)
            frac['origin'] = (bx0, by)
            frac['bbox'] = (bx0, min(sp['bbox'][1] for _, sp in num),
                            bx1, max(sp['bbox'][3] for _, sp in den))
            consumed = {id(sp) for _, sp in num + den}
            for l in set(l for l, _ in num + den):
                l.spans = [sp for sp in l.spans if id(sp) not in consumed]
            host_line.spans = sorted(host_line.spans + [frac],
                                     key=lambda s: s['bbox'][0])
    # строки, из которых дробь/корень забрали все спаны, выбрасываем
    return [l for l in lines if l.spans]


def reassemble_fractions(lines, body, bars):
    """Три строгих паттерна этажной дроби; остальное — линеаризуется с флагом.

    Rule C: строка перед числителем кончается на «=», после — начинается
            маленьким math-префиксом (знаменатель): «80 = \\frac{100}{1+r}».
    Rule A: две подряд чисто-математические маленькие строки друг под
            другом (перекрытие по X) — числитель над знаменателем.
    Rule B: маленький math-хвост строки + следующая чисто-математическая
            маленькая строка под ним.
    Каждый паттерн подтверждается ЧЕРТОЙ между ярусами в векторной графике
    (кусочные функции — те же два ряда, но без черты). Защита от ложных
    склеек: обе части не короче 3 символов (одинокая «1» — уехавший индекс)."""

    def has_bar(top_line, bot_spans, page_no):
        b0 = min(sp['bbox'][0] for sp in bot_spans)
        b1 = max(sp['bbox'][2] for sp in bot_spans)
        x0 = max(top_line.bbox[0], b0)
        x1 = min(top_line.bbox[2], b1)
        if x1 <= x0:
            return False
        y_top = max(sp['origin'][1] for sp in top_line.spans)
        y_bot = min(sp['origin'][1] for sp in bot_spans)
        return _bar_between(bars.get(page_no, []), x0, x1, y_top, y_bot)

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
                    and _is_small(nxt.spans[0], body)
                    and has_bar(line, [sp for sp in nxt.spans
                                       if is_math_span(sp)
                                       and _is_small(sp, body)],
                                line.page_no)):
                den_spans = []
                rest = list(nxt.spans)
                while rest and is_math_span(rest[0]) and _is_small(rest[0], body):
                    den_spans.append(rest.pop(0))
                frac = _frac_span(_render_math_run(line.spans, body),
                                  _render_math_run(den_spans, body),
                                  body, line.bbox[1], bbox=line.bbox)
                result[-1].spans.append(frac)
                if rest:
                    nxt.spans = rest
                    result[-1].spans.extend(rest)
                i += 2
                continue
            # Rule A: две маленькие math-строки друг под другом
            if (nxt is not None and _pure_small_math(nxt, body)
                    and len(num_txt) >= 3 and len(nxt.plain) >= 3
                    and _x_overlap(line, nxt) > 0.5
                    and has_bar(line, nxt.spans, line.page_no)):
                frac = _frac_span(_render_math_run(line.spans, body),
                                  _render_math_run(nxt.spans, body),
                                  body, line.bbox[1], bbox=line.bbox)
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
            if (head and len(tail_txt) >= 3
                    and has_bar(line, nxt.spans, line.page_no)):
                frac = _frac_span(_render_math_run(tail, body),
                                  _render_math_run(nxt.spans, body),
                                  body, line.bbox[1], bbox=line.bbox)
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
    # Перенос уравнения в PDF повторяет знак на новой строке («Q = ␊ = 60»,
    # «12P − ␊ −140») — склейка строк давала «= =», «− −», «+ +». Схлопываем
    # только ОДИНАКОВЫЙ знак через пробел (унарный минус в скобках a-(-b)
    # не затрагивается — там скобка между знаками).
    txt = re.sub(r'=\s*=', '=', txt)
    txt = re.sub(r'([-−])\s+[-−]', r'\1', txt)
    txt = re.sub(r'\+\s+\+', '+', txt)
    txt = re.sub(r'\\cdot\s+\\cdot\s+', r'\\cdot ', txt)
    txt = WS_RE.sub(' ', txt)
    fixed = DOUBLE_SCRIPT_RE.sub(r'\1\2 {}', txt)
    if fixed != txt:
        txt = fixed
        if issues is not None:
            issues.append('этажная дробь из PDF не собралась — индексы могли '
                          'слипнуться, сверить с оригиналом')
    if NEEDS_DOLLARS_RE.search(txt):
        # Декорация десятичной запятой — ТОЛЬКО внутри $...$: в голом
        # тексте «(0{,}5; 2)» она видна пользователю буквально.
        txt = re.sub(r'(\d),(\d)', r'\1{,}\2', txt)
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
    prev_line_compound = False  # разрыв в дефисе композита: клеим, дефис жив
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
            elif prev_line_hyphen or prev_line_compound:
                glue_next = True  # перенос слова/композита: без пробела
                prev_line_compound = False
            else:
                # межстрочный стык: пробел (в формуле — внутри рана)
                if math_run:
                    math_run += ' '
                elif pieces and not pieces[-1].endswith((' ', '\n')):
                    pieces.append(' ')
        # Базовая линия ЭТОЙ строки — мода y полноразмерных спанов: origin
        # отдельного спана бывает «затянут» к соседнему индексу («−20𝑞»
        # получает y индекса «2»), и бегущая base_y теряла индексы.
        line_max = max((sp['size'] for sp in line.spans
                        if span_text(sp).strip() and not sp.get('converted')),
                       default=None)
        line_base = (_mode_baseline(line.spans, line_max * SMALL_RATIO)
                     if line_max else None)
        for sp in line.spans:
            txt = span_text(sp)
            if not txt:
                continue
            if sp.get('is_table'):
                # готовый блок `$$\begin{array}…$$` — своим абзацем, не
                # оборачивать в $…$ и не сливать с math_run
                flush_math()
                if pieces and not pieces[-1].endswith('\n'):
                    pieces.append('\n\n')
                pieces.append(txt)
                pieces.append('\n\n')
                glue_next = False
                continue
            if sp.get('converted'):
                if base_size is None:
                    base_size = sp['size']
                math_run += (' ' if math_run and not math_run.endswith(' ')
                             else '') + txt
                continue
            small = base_size is not None and sp['size'] < base_size * SMALL_RATIO
            ref_y = line_base if line_base is not None else base_y
            mark = _script_mark(sp, ref_y) if small and ref_y is not None else ''
            if not small:
                base_size = sp['size']
                base_y = ref_y if ref_y is not None else sp['origin'][1]
            if is_math_span(sp):
                conv = replace_unicode_math(txt)
                if small and mark:
                    math_run += mark + '{' + conv.strip() + '}'
                else:
                    math_run += conv
            else:
                if small and mark == '_' and math_run:
                    # текстовый индекс при формуле: «𝑤 min» → w_{\text{min}},
                    # «𝐿 ж» → L_{\text{ж}} (малый ТЕКСТОВЫЙ спан ниже базовой
                    # линии раньше уходил в голый текст)
                    math_run += '_{\\text{' + txt.strip() + '}}'
                    continue
                flush_math()
                if pieces and pieces[-1] and not glue_next \
                        and not pieces[-1].endswith((' ', '\n')) \
                        and not txt.startswith((' ', ',', '.', ';', ':', ')', '?', '!')):
                    pieces.append(' ')
                # литеральный доллар (валюта «2 млн $») → $\$$: KaTeX
                # рендерит его как знак валюты, а голые $ спарились бы
                # в псевдоформулу (проверено в браузере)
                pieces.append(txt.replace('$', '$\\$$'))
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
            # Составное слово, разорванное В ДЕФИСЕ («причинно- ␊
            # следственной»), от словопереноса текстом не отличить —
            # корпус закрыт, известные композиты перечислены явно
            # (полный скан 806 склеек 2016–2025).
            left = last_txt.rstrip().split()[-1].rstrip('-').lower() \
                if last_txt.rstrip().split() else ''
            right = nxt_first.lstrip().split()[0].lower() \
                .strip('.,;:!?»)') if nxt_first.lstrip().split() else ''
            if (left, right) in COMPOUND_JOINS:
                # дефис настоящий: клеим без пробела, дефис остаётся
                prev_line_hyphen = False
                prev_line_compound = True
            else:
                # словоперенос: срезаем дефис у последнего фрагмента
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
# Знаменатель строже: ЧИСТО цифры или ЧИСТО буквы (с опц. скриптом) —
# смешанный «4X» в «5/4X» это (5/4)·X, а не 5/(4X) (вычитка 2018 №18).
DEN_ATOM = r'(?:\d+|[A-Za-z]+)(?:[_^]\{?[A-Za-z0-9]+\}?)?'

# Простая слэш-дробь ВНУТРИ математики: «атом / атом» (Y=2M/P -> \frac{2M}{P},
# P_e/40 -> \frac{P_e}{40}, Q^2/2 -> \frac{Q^{2}}{2}). Границы через lookaround,
# а не \b — не должны затрагивать соседние скобки/\frac{...} (\frac{100}{...},
# 10/(5 \cdot 2), (8w-w^{2}+20)/(10-w) осознанно НЕ трогаем — не «простые»).
FRAC_RE = re.compile(r'(?<![A-Za-z0-9\\{}_^])(' + ATOM + r')\s*/\s*('
                     + DEN_ATOM + r')(?![A-Za-z0-9{}_^])')
# Дробь в скобках со степенью снаружи: (A/B)^N -> \left(\frac{A}{B}\right)^{N}
# — обычные скобки малы для \frac внутри, поэтому вместе с дробью растут в
# \left(...\right). Применяется ДО общего FRAC_RE (иначе останется голое ^N
# при обычных скобках).
PAREN_FRAC_POW_RE = re.compile(
    r'\(\s*(' + ATOM + r')\s*/\s*(' + DEN_ATOM
    + r')\s*\)\s*\^\s*\{?([A-Za-z0-9]+)\}?')
# Два и более дефиса/коротких тире подряд (--, ––) -> одно длинное тире.
# Настоящий em dash (—) не входит в класс — не трогаем уже верное тире.
DASH_RUN_RE = re.compile(r'[-‐‑‒–]{2,}')
# Пробел внутри URL от переноса строки: «worldbank. org/…» (2018 №7).
URL_SPACE_RE = re.compile(r'([a-z0-9])\.\s+(ru|org|com|net|edu|gov|info)\b')
# Сегмент математики: от неэкранированного $ до парного ему; \$ внутри
# (валютный доллар «$\$$») съедается как экранированная пара.
MATH_SEGMENT_RE = re.compile(r'((?<!\\)\$(?:\\.|[^$\\])*\$)')
# Радикал из юникод-математики (√KL -> \sqrt KL): без скобок KaTeX возьмёт
# под корень один символ, а в PDF винкулум накрывает весь буквенный ран.
SQRT_RUN_RE = re.compile(r'\\sqrt\s+([A-Za-z]+|\d+)')
# Индекс корня: маленькая цифра перед радикалом распознаётся кегельной
# логикой как степень (^{4}\sqrt{KL}), а в вёрстке это корень 4-й степени.
ROOT_INDEX_RE = re.compile(r'\^\{(\d+)\}\s*\\sqrt\{')
# «Индекс» сразу после \frac{}{} — на деле потерянный ВЕРХНИЙ индекс
# знаменателя: (1+r)² или P₁ˢ в PDF, скрипт стоит между ярусами и метится
# как '_' относительно оси. Настоящих индексов у \frac конвейер не порождает.
FRAC_TRAIL_SUB_RE = re.compile(
    r'(\\frac\{(?:[^{}]|\{[^{}]*\})*\}\{(?:[^{}]|\{[^{}]*\})*)\}\s*'
    r'_\{([A-Za-z0-9]{1,2})\}')

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


_CMD_TAIL_RE = re.compile(r'\\[A-Za-z]+\s*$')


def _escape_unmatched_braces(inner):
    """Литеральные фигурные скобки из PDF → \\{ / \\}.

    Наш конвейер порождает «{» только структурно: после ^, _, } (второй
    аргумент \\frac), ] (индекс корня) или имени команды (\\frac, \\text…).
    Остальные «{» — контент вёрстки (кусочные функции, min{A, B}): без
    экранирования KaTeX прячет их как границы группы (или падает, если
    скобка непарная)."""
    stack, literal = [], set()
    for i, ch in enumerate(inner):
        if i > 0 and inner[i - 1] == '\\':
            continue
        if ch == '{':
            if inner[i:i + 3] == '{,}':   # десятичная запятая — структурная
                stack.append((i, False))
                continue
            prev = inner[:i].rstrip()
            structural = (prev.endswith(('^', '_', '}', ']'))
                          or _CMD_TAIL_RE.search(prev))
            stack.append((i, not structural))
        elif ch == '}':
            if stack:
                j, is_literal = stack.pop()
                if is_literal:
                    literal.update((i, j))
            else:
                literal.add(i)
    literal.update(i for i, _ in stack)   # незакрытые — тоже экранируем
    if not literal:
        return inner
    return ''.join('\\' + ch if i in literal else ch
                   for i, ch in enumerate(inner))


# Условие ветви кусочной, набранное текстом между сегментами: «$X,$ если $Y$»
# — «если»/«при» уходят в математику ветви как \text{…}, чтобы ветвь стала
# цельным сегментом (Form B → потом Form A).
CASES_IF_SPLIT_RE = re.compile(r',\s*\$\s*(если|при)\s*\$')


def _assemble_cases(text):
    """Кусочная функция из литеральной «\\{ ветвь1; ветвь2 .» → \\begin{cases}.

    Признак кусочной (в отличие от множества \\{A, B\\}): открытая «\\{» без
    закрывающей «\\}», ветви через «;», внутри ветви значение и условие через
    запятую. Двухъярусная запись PDF уже уплощена в эту форму (;=ярусы,
    ,=значение/условие) — собираем по разделителям."""
    if '\\{' not in text:
        return text
    # Form B: втянуть «если/при» из текста в математику ветви (только когда
    # рядом кусочная — «\\{» в тексте; в обычной прозе не срабатывает)
    text = CASES_IF_SPLIT_RE.sub(lambda m: r', \text{' + m.group(1) + ' }', text)

    def conv(m):
        seg = m.group(0)[1:-1]            # внутренность $…$
        j = seg.find('\\{')
        if j < 0 or '\\}' in seg[j:]:
            return m.group(0)             # множество или нет скобки
        head, body = seg[:j], seg[j + 2:].strip().rstrip('.')
        if ';' not in body:
            return m.group(0)             # одна ветвь — не кусочная
        branches = []
        for br in body.split(';'):
            br = br.strip()
            if not br:
                continue
            mm = re.match(r'^(.*),\s*(.+)$', br)   # жадно: последняя запятая
            if not mm:
                return m.group(0)         # ветвь без «значение, условие» —
                #                            это множество/список, не кусочная
            branches.append((mm.group(1).strip(), mm.group(2).strip()))
        if len(branches) < 2:
            return m.group(0)
        rows = [v + ' & ' + c for v, c in branches]
        return ('$' + head + '\\begin{cases} '
                + ' \\\\ '.join(rows) + ' \\end{cases}$')

    return MATH_SEGMENT_RE.sub(conv, text)


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
            inner = FRAC_TRAIL_SUB_RE.sub(r'\1^{\2}}', inner)
            inner = _escape_unmatched_braces(inner)
            out.append('$' + inner + '$')
        else:
            part = DASH_RUN_RE.sub('—', part)
            part = fix_homoglyphs(part)
            # пробел внутри URL от переноса строки: «worldbank. org»
            part = URL_SPACE_RE.sub(r'\1.\2', part)
            out.append(part)
    return _assemble_cases(''.join(out))


def canonicalize_answer(raw):
    """«Ответ: …» → (correct, unit) или (None, причина).

    «50.» → ('50', ''); «19 % или 0,19.» → ('0,19', '') — безразмерная форма
    предпочтительнее; «𝑄= 2.» → ('2', ''); «120 руб.» → ('120', 'руб.')."""
    text = raw.strip().rstrip('.').strip()
    # KaTeX-декорация десятичной запятой из math-рана («-0{,}25»)
    text = text.replace('{,}', ',')
    if not text:
        return None, 'пустой ответ'
    candidates = [c.strip() for c in re.split(r'\s+или\s+', text) if c.strip()]
    parsed = []  # (value, unit)
    for cand in candidates:
        m = VAR_EQ_RE.match(cand)
        if m:
            cand = m.group(1).strip()
        # «на 64 %» (вопрос «на сколько процентов…») — предлог не значим,
        # жюри засчитывает ответы «с соответствующими предлогами и без них»
        cand = re.sub(r'^на\s+', '', cand)
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
    qstart_re = profile.get('qstart_re', QSTART_RE)
    flat = profile.get('flat_numbering', False)
    next_flat_number = 1
    lines, body = extract_lines(doc)
    bars = extract_bars(doc)
    figures = extract_figures(doc)
    lines, fig_zones = drop_figure_labels(lines, figures)  # подписи графиков
    tables = extract_tables(doc, body)                 # таблицы → $$array$$
    lines = apply_tables(lines, tables, body)          # до дробей: спаны ушли
    lines = reassemble_display_math(lines, body, bars)  # выключные формулы
    lines = reassemble_fractions(lines, body, bars)  # строчные этажные дроби
    lines = reassemble_intraline_fracs(lines, body, bars)  # дроби и корни
    lines = clear_resolved_degraded(lines, body)  # снять плашку с собранных
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
            # рисунок приписываем вопросу, в чей ПОТОК ЧТЕНИЯ (page, y) попадает
            # верх зоны: от первой до последней строки вопроса (+40pt на конце,
            # график в конце решения). Так владелец графика на стыке страниц
            # (текст выше на предыдущей странице) ловится, а сосед снизу — нет.
            owns_figure = False
            qlines = [l for key in ('statement', 'options_flat', 'solution')
                      for l in _flat(buffers, key)]
            if qlines:
                first = min((l.page_no, l.bbox[1]) for l in qlines)
                last = max((l.page_no, l.bbox[3]) for l in qlines)
                for pno, zones in fig_zones.items():
                    for zy0, zy1 in zones:
                        ztop = (pno, zy0)
                        if first <= ztop and (pno, zy0 - 40) <= last:
                            owns_figure = True
                            break
                    if owns_figure:
                        break
            if owns_figure:
                note = ('в оригинале рисунок — подписи осей/кривых из '
                        'текста исключены, сверить с PDF')
                q['notes'] = (q['notes'] + '; ' + note
                              if q.get('notes') else note)
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

    stop_line_re = profile.get('stop_line_re')
    for line in lines:
        plain = line.plain

        if (stop_line_re is not None and section is not None
                and stop_line_re.match(plain)):
            break

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

        m = qstart_re.match(plain)
        if m and section is not None:
            if flat:
                is_qstart = int(m.group(1)) == next_flat_number
                number = m.group(1)
            else:
                is_qstart = int(m.group(1)) == section
                number = f'{m.group(1)}.{m.group(2)}'
            if is_qstart:
                flush_question()
                if state == 'preamble' and buffers['preamble']:
                    preambles.append({'section': section,
                                      'text': render_paragraph(buffers['preamble'], body)})
                buffers = new_buffers()
                stripped, _ = strip_marker(line, qstart_re)
                cur = {'number': number, 'section': section,
                       'qtype': section_qtypes.get(section)}
                if flat:
                    next_flat_number = int(number) + 1
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
        q['points'] = points_by_section.get(q['section'])
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

    # U+FFFD — глиф, который фиксер ToUnicode не смог расшифровать:
    # текст вопроса неполон, выдумывать нечего — в unparsed.
    if '�' in statement + solution + ''.join(opts):
        return None, 'нерасшифрованные глифы (U+FFFD) — сверить с PDF'

    q = {'grades': [grade], 'number': cur['number'],
         'section': cur['section'], 'qtype': qtype,
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
    if '�' in answer_raw:
        return None, 'нерасшифрованные глифы (U+FFFD) в ответе'
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
