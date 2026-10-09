"""Скачанные PDF: путь, проверка целостности, сведения, отрисовка страницы.

PyMuPDF (`fitz`) уже стоит в requirements/base.txt — новых зависимостей нет.
"""
import hashlib
import os


def pdf_relpath(rec):
    """pdf/<subject>/<2019_2020>/<grade>/<degree>_<work_id>.pdf — без ФИО."""
    return os.path.join('pdf', rec['subject'], rec['season'].replace('/', '_'),
                        str(rec['grade']), '%d_%s.pdf' % (rec['degree'], rec['work_id']))


def looks_like_pdf(path):
    """Дешёвая проверка «уже скачан»: есть, не пустой, начинается с %PDF."""
    try:
        if os.path.getsize(path) <= 0:
            return False
        with open(path, 'rb') as fh:
            return fh.read(5) == b'%PDF-'
    except OSError:
        return False


def pdf_info(path):
    """bytes, sha256, pages, has_text_layer. Битый файл — ValueError."""
    import fitz

    if not looks_like_pdf(path):
        raise ValueError('не PDF (нет сигнатуры %PDF)')
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    try:
        doc = fitz.open(path)
    except Exception as error:  # noqa: BLE001 — любой отказ разбора = битый файл
        raise ValueError('PyMuPDF не открывает файл: %s' % error)
    try:
        if doc.page_count < 1:
            raise ValueError('в PDF нет страниц')
        has_text = any(page.get_text().strip() for page in doc)
        pages = doc.page_count
    finally:
        doc.close()
    return {'bytes': os.path.getsize(path), 'sha256': digest.hexdigest(),
            'pages': pages, 'has_text_layer': has_text}


def render_page(path, page=0, dpi=150):
    """Страница PDF → PIL.Image (RGB)."""
    import fitz
    from PIL import Image

    doc = fitz.open(path)
    try:
        pix = doc[page].get_pixmap(dpi=dpi)
        return Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    finally:
        doc.close()


def first_page_text(path):
    import fitz

    doc = fitz.open(path)
    try:
        return doc[0].get_text()
    finally:
        doc.close()


def full_text(path):
    """Текст всех страниц (для онлайн-сезонов с баллами по вопросам)."""
    import fitz

    doc = fitz.open(path)
    try:
        return '\n'.join(page.get_text() for page in doc)
    finally:
        doc.close()


def first_page_words(path):
    """Слова первой страницы с координатами и высота страницы (pt)."""
    import fitz

    doc = fitz.open(path)
    try:
        page = doc[0]
        return page.get_text('words'), page.rect.height
    finally:
        doc.close()
