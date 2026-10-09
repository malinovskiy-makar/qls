"""Распакованные сканы работы: какой лист первый, жёлтые пятна, вырез таблицы.

Что внутри zip (разведка 09.10.2026, RECON.md): либо один PDF (2021, 2025),
либо набор JPG (2023), либо JPG плюс PDF (2022), либо два комплекта JPG —
чистый и проверенный (2024). Первый лист («титул») — тот, на котором внизу
таблица баллов жюри; по картинке его отличает сходство с самым первым
файлом (титулы похожи друг на друга, листы с решениями — нет).

PyMuPDF, Pillow и numpy уже в requirements/base.txt.
"""
import os

from PIL import Image, ImageChops

#: Полоса таблицы баллов в долях первой страницы (x0, y0, x1, y1): от строки
#: «Таблица заполняется членами жюри» до низа таблицы. Выше — QR, «аудитория —
#: посадочное место» и номер участника, ниже — «Добавляйте олимпиаду…».
BAND = (0.02, 0.50, 0.98, 0.91)

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


# ------------------------------------------------------------ разбор работы

def title_candidates(scan_dir, images):
    """Индексы листов-титулов среди `images` (по сходству с первым файлом)."""
    prints = [fingerprint(open_small(os.path.join(scan_dir, n), 300)) for n in images]
    ref = prints[0]
    return [i for i, p in enumerate(prints) if similarity(ref, p) >= TITLE_SIMILARITY]


def analyze(scan_dir):
    """Какая страница — «первая» для баллов и сколько на ней жёлтого.

    Приоритет у JPG (проверенная копия): если есть и JPG, и PDF — для баллов
    берём JPG, а долю пятен PDF пишем отдельно (`pdf_stickers_pct`).
    Нечего анализировать — {'source_kind': None}.
    """
    images, pdfs = list_scan_files(scan_dir)
    info = {'source_kind': None, 'first_page': None, 'first_page_index': 0,
            'variants': 0, 'stickers_pct': None, 'has_stickers': None,
            'band_stickers_pct': None, 'band_red_pct': None, 'pdf_stickers_pct': None}
    if images:
        info['source_kind'] = 'jpg'
        cands = title_candidates(scan_dir, images)
        info['variants'] = len(cands)
        best, best_red = None, -1.0
        for i in cands:
            img = open_small(os.path.join(scan_dir, images[i]))
            red = red_pct(crop_band(img))
            if red > best_red:
                best, best_red, best_img = i, red, img
        info['first_page'] = images[best]
        info['band_red_pct'] = round(best_red, 4)
        info['stickers_pct'] = round(yellow_pct(best_img), 4)
        info['band_stickers_pct'] = round(yellow_pct(crop_band(best_img)), 4)
        if pdfs:
            info['pdf_stickers_pct'] = round(yellow_pct(pdf_page(os.path.join(scan_dir, pdfs[0]))), 4)
    elif pdfs:
        info['source_kind'] = 'pdf'
        info['variants'] = 1
        img = pdf_page(os.path.join(scan_dir, pdfs[0]), 0, dpi=100)
        info['first_page'] = pdfs[0]
        info['band_red_pct'] = round(red_pct(crop_band(img)), 4)
        info['stickers_pct'] = round(yellow_pct(img), 4)
        info['band_stickers_pct'] = round(yellow_pct(crop_band(img)), 4)
    if info['stickers_pct'] is not None:
        info['has_stickers'] = info['stickers_pct'] > STICKER_PCT
    return info


def first_page_image(scan_dir, first_page, dpi=150):
    """Первая страница для выреза в хорошем разрешении (PIL.Image, RGB)."""
    path = os.path.join(scan_dir, first_page)
    if first_page.lower().endswith('.pdf'):
        return pdf_page(path, 0, dpi=dpi)
    return Image.open(path).convert('RGB')
