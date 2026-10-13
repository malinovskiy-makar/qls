"""Распакованные сканы работы: какой лист первый, жёлтые пятна, вырез таблицы.

Что внутри zip (разведка 09.10.2026, RECON.md): либо один PDF (2021, 2025),
либо набор JPG (2023), либо JPG плюс PDF (2022), либо два комплекта JPG —
чистый и проверенный (2024). Первый лист («титул») — тот, на котором внизу
таблица баллов жюри; по картинке его отличает сходство с самым первым
файлом (титулы похожи друг на друга, листы с решениями — нет).

⚠️ ОБЛОЖКА С ФИО. У части работ 2021 (4 из 237) первым листом идёт «Уважаемые
участники олимпиады!»: на нём фамилия, имя, отчество и название школы — ровно в
той полосе, где у обычного титула лежит таблица баллов. Такой лист НИКОГДА не
годится для выреза. Ловят его два правила (`is_cover`): (1) верх страницы
(логотип, QR, «класс заданий») почти совпадает с верхом СЛЕДУЮЩЕЙ страницы того же
скана — обложка стоит перед настоящим титулом и делит с ним шапку; (2) только у
2021 года — тёмные чернила в зоне «ФИО» (`COVER_ZONE`: у титула 2021 там пусто, у
обложки три строки и рамка школы; у шаблонов других лет эта зона занята
обычным текстом, поэтому для них правило не применяется). Нет безопасной
страницы — `first_page=None`, работа в модель не идёт. Автоматика не заменяет
глаз: вырезы пробы перед отправкой смотрятся человеком (docs/MOSH_WORKS.md).

PyMuPDF, Pillow и numpy уже в requirements/base.txt.
"""
import os

from PIL import Image, ImageChops

#: Версия разбора первой страницы: поменялась — `download` пересчитает поля.
ANALYSIS_VERSION = 3

#: Полоса таблицы баллов в долях первой страницы (x0, y0, x1, y1): от строки
#: «Таблица заполняется членами жюри» до низа таблицы. Выше — QR, «аудитория —
#: посадочное место» и номер участника, ниже — «Добавляйте олимпиаду…».
BAND = (0.02, 0.50, 0.98, 0.91)

#: Зона, где у обложки 2021 стоят фамилия/имя/отчество и школа, а у титула 2021
#: пусто (у 4 обложек — 2,5–4,2 % тёмных пикселей, у остальных 233 первых
#: страниц — не больше 1,1 %). Только для 2021: у шаблонов 2022–2025 в этой зоне
#: стоит обычный текст титула.
COVER_ZONE = (0.45, 0.38, 0.97, 0.50)
COVER_INK_PCT = 1.5
COVER_INK_YEARS = (2021,)

#: Верх страницы (доля высоты) и порог его сходства со следующей страницей:
#: у обложки и титула 2021 — 0,66–0,81, у остальных страниц — не выше 0,42.
TOP_FRACTION = 0.30
TOP_SIMILARITY = 0.5

#: Сколько первых страниц/файлов просматриваем в поисках титула с таблицей.
HEAD_PAGES = 3

#: Титулом считается лист, чей отпечаток похож на первый файл не меньше этого.
TITLE_SIMILARITY = 0.8

#: Доля жёлтых пикселей (в процентах), выше которой страница «с пятнами».
STICKER_PCT = 0.02
#: Доля жёлтого в полосе таблицы, выше которой баллы считаем закрашенными.
HIDDEN_BAND_PCT = 0.15

IMAGE_EXT = ('.jpg', '.jpeg', '.png')


def list_scan_files(scan_dir):
    """(картинки, pdf) — имена, отсортированные."""
    names = sorted(os.listdir(scan_dir)) if os.path.isdir(scan_dir) else []
    images = [n for n in names if n.lower().endswith(IMAGE_EXT)]
    pdfs = [n for n in names if n.lower().endswith('.pdf')]
    return images, pdfs


def count_pages(scan_dir):
    """Листов в основном виде работы: картинки, а если их нет — страницы PDF.

    JPG и PDF одной работы — это одни и те же листы (в 2022 — два варианта
    одного скана), складывать их нельзя. Битый PDF — 0.
    """
    import fitz

    images, pdfs = list_scan_files(scan_dir)
    if images:
        return len(images)
    total = 0
    for name in pdfs:
        try:
            doc = fitz.open(os.path.join(scan_dir, name))
            total += doc.page_count
            doc.close()
        except Exception:  # noqa: BLE001 — битый PDF внутри zip не роняет прогон
            pass
    return total


# ------------------------------------------------------------ картинки

def open_small(path, max_side=900):
    """Картинку открыть сразу уменьшенной (JPEG-draft — быстро)."""
    img = Image.open(path)
    try:
        img.draft('RGB', (max_side, max_side))
    except Exception:  # noqa: BLE001 — не JPEG
        pass
    img = img.convert('RGB')
    img.thumbnail((max_side, max_side))
    return img


def pdf_page(path, page=0, dpi=100):
    import fitz

    doc = fitz.open(path)
    try:
        pix = doc[page].get_pixmap(dpi=dpi)
        return Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    finally:
        doc.close()


def pdf_page_count(path):
    import fitz

    doc = fitz.open(path)
    try:
        return doc.page_count
    finally:
        doc.close()


def fingerprint(img):
    """Отпечаток страницы: яркость 48×68, нормированная (для корреляции)."""
    import numpy as np

    arr = np.asarray(img.convert('L').resize((48, 68)), dtype=float).ravel()
    return (arr - arr.mean()) / (arr.std() + 1e-9)


def similarity(a, b):
    import numpy as np

    return float(np.dot(a, b) / len(a))


def _count(mask):
    """Число белых (255) пикселей маски L."""
    return mask.histogram()[255]


def yellow_pct(img):
    """Доля (в процентах) ярко-жёлтых пикселей — закраска маркером."""
    r, g, b = img.split()
    mask = ImageChops.multiply(
        ImageChops.multiply(r.point(lambda v: 255 if v > 190 else 0),
                            g.point(lambda v: 255 if v > 190 else 0)),
        b.point(lambda v: 255 if v < 130 else 0))
    return 100.0 * _count(mask) / (img.width * img.height)


def red_pct(img):
    """Доля красных чернил (отметки и цифры жюри) — признак проверенного листа."""
    r, g, b = img.split()
    mask = ImageChops.multiply(
        ImageChops.multiply(r.point(lambda v: 255 if v > 150 else 0),
                            g.point(lambda v: 255 if v < 110 else 0)),
        b.point(lambda v: 255 if v < 140 else 0))
    return 100.0 * _count(mask) / (img.width * img.height)


def band_box(size, band=BAND):
    w, h = size
    return (round(band[0] * w), round(band[1] * h), round(band[2] * w), round(band[3] * h))


def crop_band(img, band=BAND):
    return img.crop(band_box(img.size, band))


def cover_ink_pct(img):
    """Доля тёмных пикселей в зоне ФИО (`COVER_ZONE`), в процентах."""
    zone = img.convert('L').crop(band_box(img.size, COVER_ZONE))
    mask = zone.point(lambda v: 255 if v < 140 else 0)
    return 100.0 * _count(mask) / max(zone.width * zone.height, 1)


def top_fingerprint(img):
    """Отпечаток верха страницы (логотип, QR, «класс заданий»)."""
    import numpy as np

    w, h = img.size
    arr = np.asarray(img.convert('L').crop((0, 0, w, int(TOP_FRACTION * h))).resize((60, 24)),
                     dtype=float).ravel()
    return (arr - arr.mean()) / (arr.std() + 1e-9)


class PageSeq:
    """Страницы работы по порядку: JPG-файлы или страницы PDF (кэш уменьшенных)."""

    def __init__(self, scan_dir, images, pdfs):
        self.scan_dir, self.images, self.pdfs = scan_dir, images, pdfs
        self.n = len(images) if images else pdf_page_count(os.path.join(scan_dir, pdfs[0]))
        self._cache = {}

    def small(self, i):
        if i not in self._cache:
            if self.images:
                self._cache[i] = open_small(os.path.join(self.scan_dir, self.images[i]), 600)
            else:
                self._cache[i] = pdf_page(os.path.join(self.scan_dir, self.pdfs[0]), i, dpi=50)
        return self._cache[i]


def is_cover(seq, i, year=None):
    """Страница `i` — обложка с личными данными?"""
    img = seq.small(i)
    if year in COVER_INK_YEARS and cover_ink_pct(img) >= COVER_INK_PCT:
        return True
    if i + 1 < seq.n:
        return similarity(top_fingerprint(img), top_fingerprint(seq.small(i + 1))) >= TOP_SIMILARITY
    return False


# ------------------------------------------------------------ разбор работы

def _empty_info():
    return {'analysis_version': ANALYSIS_VERSION, 'source_kind': None, 'first_page': None,
            'first_page_index': 0, 'variants': 0, 'cover_skipped': 0, 'stickers_pct': None,
            'has_stickers': None, 'band_stickers_pct': None, 'band_red_pct': None,
            'pdf_stickers_pct': None}


def _analyze_jpg(seq, info, year):
    """JPG: титулы — листы, похожие на первый безопасный файл; берём проверенный."""
    head = [i for i in range(min(HEAD_PAGES, seq.n)) if not is_cover(seq, i, year)]
    info['cover_skipped'] = min(HEAD_PAGES, seq.n) - len(head)
    if not head:
        return
    ref = fingerprint(seq.small(head[0]))
    cands = [i for i in range(seq.n)
             if similarity(ref, fingerprint(seq.small(i))) >= TITLE_SIMILARITY
             and not is_cover(seq, i, year)]
    if not cands:
        cands = [head[0]]
    info['variants'] = len(cands)
    best, best_red = None, -1.0
    for i in cands:
        red = red_pct(crop_band(seq.small(i)))
        if red > best_red:
            best, best_red = i, red
    img = seq.small(best)
    info['first_page'] = seq.images[best]
    info['band_red_pct'] = round(best_red, 4)
    info['stickers_pct'] = round(yellow_pct(img), 4)
    info['band_stickers_pct'] = round(yellow_pct(crop_band(img)), 4)


def _analyze_pdf(seq, info, year):
    """PDF: первая страница, не признанная обложкой, среди первых HEAD_PAGES."""
    pages = min(HEAD_PAGES, seq.n)
    for i in range(pages):
        if not is_cover(seq, i, year):
            break
        info['cover_skipped'] += 1
    else:
        return
    img = pdf_page(os.path.join(seq.scan_dir, seq.pdfs[0]), i, dpi=100)
    info['first_page'] = seq.pdfs[0]
    info['first_page_index'] = i
    info['variants'] = 1
    info['band_red_pct'] = round(red_pct(crop_band(img)), 4)
    info['stickers_pct'] = round(yellow_pct(img), 4)
    info['band_stickers_pct'] = round(yellow_pct(crop_band(img)), 4)


def analyze(scan_dir, year=None):
    """Какая страница — «первая» для баллов и сколько на ней жёлтого.

    Приоритет у JPG (проверенная копия): если есть и JPG, и PDF — для баллов
    берём JPG, а долю пятен PDF пишем отдельно (`pdf_stickers_pct`).
    Безопасной страницы нет (все первые страницы — обложки) или нечего
    анализировать — `first_page=None`.
    """
    images, pdfs = list_scan_files(scan_dir)
    info = _empty_info()
    if images:
        info['source_kind'] = 'jpg'
        _analyze_jpg(PageSeq(scan_dir, images, []), info, year)
        if pdfs and info['first_page']:
            info['pdf_stickers_pct'] = round(
                yellow_pct(pdf_page(os.path.join(scan_dir, pdfs[0]), 0)), 4)
    elif pdfs:
        info['source_kind'] = 'pdf'
        _analyze_pdf(PageSeq(scan_dir, [], pdfs), info, year)
    if info['stickers_pct'] is not None:
        info['has_stickers'] = info['stickers_pct'] > STICKER_PCT
    return info


class UnsafePage(Exception):
    """Страница, признанная обложкой: в модель не идёт."""


def first_page_image(scan_dir, first_page, dpi=150, page=0, year=None):
    """Первая страница для выреза в хорошем разрешении (PIL.Image, RGB).

    Перед отдачей ещё раз проверяет страницу на обложку: выбранная раньше (по
    прежней версии разбора) или руками, она не должна попасть в вырез.
    """
    images, _pdfs = list_scan_files(scan_dir)
    is_pdf = first_page.lower().endswith('.pdf')
    seq = PageSeq(scan_dir, [], [first_page]) if is_pdf else PageSeq(scan_dir, images, [])
    idx = page if is_pdf else images.index(first_page)
    if is_cover(seq, idx, year):
        raise UnsafePage('страница похожа на обложку с личными данными')
    path = os.path.join(scan_dir, first_page)
    return pdf_page(path, page, dpi=dpi) if is_pdf else Image.open(path).convert('RGB')


# ------------------------------------------------------------ финграмотность

#: Бланк МОШ по финансовой грамотности (разведка 13.10.2026, 9 работ глазами):
#: 2021–2022 — титул «ECP» первым файлом: номер работы, «вариант», «аудитория» и
#: таблица «Задание | №1 … №5 | Сумма» × строка «Балл» (одна проверка); 2023 —
#: титул «МОШ» с той же таблицей, но ПУСТОЙ (3 из 3), и ОТДЕЛЬНЫЙ файл
#: `…titul…` — обложка «Уважаемые участники олимпиады!» с фамилией, именем,
#: отчеством и школой; 2024–2025 — только листы ответов («Задание 1. 1.1 …»),
#: титула и таблицы баллов нет.
#: Полоса выреза: от «вариант» до низа таблицы (у титула здесь нет ФИО).
FIN_BAND = (0.02, 0.33, 0.98, 0.72)
#: Годы, где на скане есть заполненная таблица баллов по задачам.
FIN_SCORE_YEARS = (2021, 2022)
#: Годы, где титул с таблицей есть, но таблица не заполнена.
FIN_EMPTY_TABLE_YEARS = (2023,)
#: Имя файла обложки с личными данными (2023): такой файл НИКОГДА не берётся.
FIN_COVER_NAME = 'titul'
#: Шапка таблицы финграма — верхняя строка из двух («Задание | №1 … | Сумма»).
FIN_HEADER_FRAC = 0.45


def fin_is_cover_name(name):
    """Файл-обложка с ФИО (по имени): «mosh-fin-titul-000441.jpg» и подобные."""
    return FIN_COVER_NAME in (name or '').lower()


def fin_pages(scan_dir):
    """Листы работы финграма по порядку (естественная сортировка имён), БЕЗ обложек.

    JPG приоритетнее PDF (в 2023 PDF — тот же скан без обложки). Возвращает
    [(имя файла, номер страницы в файле 0..)].
    """
    import re

    def key(name):
        return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', name)]

    images, pdfs = list_scan_files(scan_dir)
    images = sorted((n for n in images if not fin_is_cover_name(n)), key=key)
    if images:
        return [(n, 0) for n in images]
    out = []
    for name in sorted((n for n in pdfs if not fin_is_cover_name(n)), key=key):
        out += [(name, i) for i in range(pdf_page_count(os.path.join(scan_dir, name)))]
    return out


def fin_analyze(scan_dir, year):
    """Финграм: где титул с таблицей баллов (только 2021–2023) → поля index.

    `first_page` — первый лист НЕ-обложка, если у года есть титул; у 2024–2025
    титула нет — `first_page=None`, `form='answer_sheets'`. `form`:
    `title_scores` (таблица заполнена), `title_empty` (2023), `answer_sheets`.
    """
    info = _empty_info()
    pages = fin_pages(scan_dir)
    images, _pdfs = list_scan_files(scan_dir)
    info['source_kind'] = 'jpg' if any(n.lower().endswith(IMAGE_EXT) for n, _ in pages) else (
        'pdf' if pages else None)
    info['cover_skipped'] = sum(1 for n in images if fin_is_cover_name(n))
    if year in FIN_SCORE_YEARS or year in FIN_EMPTY_TABLE_YEARS:
        info['form'] = 'title_scores' if year in FIN_SCORE_YEARS else 'title_empty'
        if pages:
            name, page = pages[0]
            info['first_page'], info['first_page_index'], info['variants'] = name, page, 1
    else:
        info['form'] = 'answer_sheets'
    return info


def fin_title_image(scan_dir, first_page, dpi=150, page=0):
    """Титул финграма для выреза; обложка по имени — UnsafePage (никогда в модель)."""
    if fin_is_cover_name(first_page):
        raise UnsafePage('файл-обложка с личными данными')
    path = os.path.join(scan_dir, first_page)
    if first_page.lower().endswith('.pdf'):
        return pdf_page(path, page, dpi=dpi)
    return Image.open(path).convert('RGB')


# ------------------------------------------------------------ щит выреза

#: Щит (13.10.2026): в модель уходит только вырез, где видна рамка таблицы баллов
#: и её шапка («Задача | 1 | 2 | 3 | 4 | Сумма»). Признаки — по линиям: после
#: выравнивания наклона ищем вертикали (рамка и столбцы), по их высоте — таблицу,
#: считаем горизонтали внутри и клетки шапки с чернилами. Обложка с ФИО, пустая
#: страница и лист решения линий таблицы не дают; клетчатая бумага даёт их слишком
#: много (больше SHIELD_MAX_LINES).
SHIELD_WIDTH = 900
SHIELD_LINE_CONTRAST = 14
SHIELD_INK_CONTRAST = 12
SHIELD_H_LINES = (3, 12)
SHIELD_V_LINES = (6, 12)
SHIELD_HEADER_CELLS = 3


def _groups(indices, gap):
    out = []
    for i in indices:
        if out and i - out[-1][1] <= gap:
            out[-1][1] = i
        else:
            out.append([i, i])
    return out


def table_shield(crop, header_frac=0.16):
    """Вырез — таблица с рамкой и шапкой? → (ok, reason, metrics).

    `header_frac` — доля высоты таблицы под шапку: у экономики 5–6 строк (0,16), у
    финграма две строки «Задание / Балл» (0,45).
    """
    import numpy as np
    from PIL import ImageFilter

    g = crop.convert('L')
    g = g.resize((SHIELD_WIDTH, max(1, round(g.height * SHIELD_WIDTH / g.width))))
    arr = np.asarray(g, dtype=float)
    contrast = np.asarray(g.filter(ImageFilter.GaussianBlur(10)), dtype=float) - arr
    lines = Image.fromarray(((contrast > SHIELD_LINE_CONTRAST) * 255).astype('uint8'))
    ink = Image.fromarray(((contrast > SHIELD_INK_CONTRAST) * 255).astype('uint8'))
    best, best_score = 0.0, -1.0
    for step in range(-8, 9):
        angle = step * 0.5
        rot = np.asarray(lines.rotate(angle, resample=Image.BILINEAR), dtype=float) / 255.0
        score = float((rot.sum(axis=1) ** 2).sum())
        if score > best_score:
            best, best_score = angle, score
    mask = np.asarray(lines.rotate(best, resample=Image.BILINEAR), dtype=float) > 127
    inkm = np.asarray(ink.rotate(best, resample=Image.BILINEAR), dtype=float) > 127
    h, w = mask.shape
    metrics = {'angle': best, 'n_v': 0, 'n_h': 0, 'header_cells': 0}
    vcols = _groups(np.where(mask.sum(axis=0) >= 0.25 * h)[0], 6)
    metrics['n_v'] = len(vcols)
    if len(vcols) < 2:
        return False, 'no_frame', metrics
    xs = [(a + b) // 2 for a, b in vcols]
    support = mask[:, [max(x - 1, 0) for x in xs]].sum(axis=1) + mask[:, xs].sum(axis=1)
    rows_ok = np.where(support >= 0.6 * len(xs))[0]
    if not len(rows_ok):
        return False, 'no_frame', metrics
    spans = _groups(rows_ok, 8)
    top, bot = max(spans, key=lambda s: s[1] - s[0])
    x0, x1 = xs[0], xs[-1]
    hl = _groups(np.where(mask[top:bot + 1, x0:x1 + 1].sum(axis=1) >= 0.35 * (x1 - x0))[0], 4)
    metrics['n_h'] = len(hl)
    if not (SHIELD_V_LINES[0] <= len(vcols) <= SHIELD_V_LINES[1]):
        return False, 'no_frame', metrics
    if not (SHIELD_H_LINES[0] <= len(hl) <= SHIELD_H_LINES[1]):
        return False, 'no_frame', metrics
    # Шапка — верхняя шестая часть таблицы (заголовок + пять строк).
    y0, y1 = top + 4, top + max(12, int(header_frac * (bot - top)))
    cells = 0
    for a, b in zip(xs, xs[1:]):
        cell = inkm[y0:y1, a + 4:b - 3]
        if cell.size and cell.mean() > 0.01:
            cells += 1
    metrics['header_cells'] = cells
    if cells < SHIELD_HEADER_CELLS:
        return False, 'no_header', metrics
    return True, '', metrics
