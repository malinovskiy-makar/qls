# -*- coding: utf-8 -*-
"""Шесть документов: загрузка Markdown, подстановка реквизитов, превращение в HTML.

⚠️ ТЕКСТЫ ДОКУМЕНТОВ ЛЕЖАТ В `legal/texts/*.md` ДОСЛОВНО, КАК ИХ УТВЕРДИЛ
ВЛАДЕЛЕЦ. Реквизиты подставляются ПРИ ПОКАЗЕ из настроек, а не правкой файлов:
в файлах стоят метки `[ПОЧТА]` и `[ДАТА]`. Пока значение пусто, на месте метки
виден заметный `[не заполнено]`, а не пустота.

⚠️ HTML внутри Markdown выключен (`html: False`): тексты наши, но проверенный
запрет дешевле доверия. Подстановка идёт через приватные символы U+E000/U+E001
ДО разбора и заменяется на экранированный HTML ПОСЛЕ него, поэтому почта из
окружения не может внести в страницу разметку.
"""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.utils.html import escape
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt

TEXTS_DIR = Path(__file__).resolve().parent / 'texts'

MAIL_MARK = 'MAIL'
DATE_MARK = 'DATE'
MISSING = '[не заполнено]'

EMAIL_RE = re.compile(r'^[^@\s<>"\']+@[^@\s<>"\']+\.[^@\s<>"\']+$')


@dataclass(frozen=True)
class Document:
    slug: str       # кусок адреса: /legal/<slug>/
    filename: str   # файл в legal/texts/
    short: str      # короткое имя для списков и футера
    title: str      # заголовок документа (первая строка файла)

    @property
    def path(self):
        return TEXTS_DIR / self.filename


def _title_of(filename):
    for line in (TEXTS_DIR / filename).read_text(encoding='utf-8').splitlines():
        if line.startswith('# '):
            return line[2:].strip()
    return filename


# Порядок = порядок на странице /legal/.
_SPEC = (
    ('privacy', 'privacy.md', 'Политика'),
    ('consent', 'consent.md', 'Согласие'),
    ('consent-ai', 'consent_ai.md', 'Согласие на помощника'),
    ('cookies', 'cookies.md', 'Cookie'),
    ('terms', 'terms.md', 'Соглашение'),
    ('recommendations', 'recommendations.md', 'Рекомендации'),
)


@lru_cache(maxsize=1)
def all_documents():
    return tuple(Document(slug, filename, short, _title_of(filename))
                 for slug, filename, short in _SPEC)


def get_document(slug):
    for doc in all_documents():
        if doc.slug == slug:
            return doc
    return None


@lru_cache(maxsize=1)
def _renderer():
    return MarkdownIt('commonmark', {'html': False}).enable('table')


@lru_cache(maxsize=16)
def _rendered_skeleton(filename, mtime_ns):
    """HTML документа с метками вместо реквизитов (разбирается один раз на правку файла)."""
    source = (TEXTS_DIR / filename).read_text(encoding='utf-8')
    source = source.replace('[ПОЧТА]', MAIL_MARK).replace('[ДАТА]', DATE_MARK)
    html = _renderer().render(source)
    # Широкая таблица прокручивается внутри себя, а не растягивает страницу.
    html = html.replace('<table>', '<div class="lg-table"><table>').replace(
        '</table>', '</table></div>')
    return html


def missing_span():
    return '<span class="lg-missing">%s</span>' % MISSING


def mail_html(email=None):
    """Почта оператора ссылкой, либо заметная заглушка."""
    email = settings.LEGAL.get('contact_email', '') if email is None else email
    email = (email or '').strip()
    if not EMAIL_RE.match(email):
        return missing_span()
    return '<a href="mailto:%s">%s</a>' % (escape(email), escape(email))


def date_html(date=None):
    date = settings.LEGAL.get('docs_date', '') if date is None else date
    date = (date or '').strip()
    return escape(date) if date else missing_span()


def render(document):
    """Готовый HTML документа с подставленными реквизитами."""
    skeleton = _rendered_skeleton(document.filename, document.path.stat().st_mtime_ns)
    html = skeleton.replace(MAIL_MARK, mail_html()).replace(DATE_MARK, date_html())
    return mark_safe(html)  # noqa: S308 — разбор без html, подстановки экранированы
