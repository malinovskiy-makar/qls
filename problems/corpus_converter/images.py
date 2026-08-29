# -*- coding: utf-8 -*-
r"""Ссылки на картинки в СЫРОМ материале → маркеры `[[FIGURE:<sha256>]]`.

Зачем маркер, а не `<img>`. Общий санитайзер показа
(`problems/rendering.py`) не пропускает ни `img`, ни `svg`, ни один
атрибут, и остаётся таким
([ADR 0031](../../docs/adr/0031-tikz-svg-blocked-by-sanitizer.md)):
расширить allow-list значило бы дать любому тексту задачи право
подставить произвольный `src`. Поэтому в тексте остаётся маркер —
чистый текст без атрибутов, — а `<img>` подставляется ПОСЛЕ санитайзера
по первичному ключу строки `ProblemFigure` (`problems/figures.py`).
Механика та же, что у собранных из TikZ картинок; отличается только
происхождение байтов.

⚠️ **Заменяется ТОЛЬКО ссылка, для которой файл реально есть на диске.**
Маркер без строки `ProblemFigure` на экране просто исчезает — то есть
картинка пропала бы молча. Неразрешённая ссылка остаётся в тексте как
была: её видно, шлюз честно бракует такую задачу, и она уходит в
очередь ручного разбора. Молчаливая потеря содержимого — P0.

⚠️ Работает по СЫРОМУ тексту, до конвертера. Маркер стадию 1 переживает
без изменений: в нём нет ни дефисов, ни `%`, ни математики — то же
свойство, на котором стоит `tikz_render`.
"""
from __future__ import annotations

import hashlib
import re

#: Markdown-картинка: `![подпись](адрес "заголовок")`. Так их пишет
#: SolveHub — 840 ссылок в 572 задачах.
MD_IMAGE_RE = re.compile(r'!\[[^\]\n]*\]\(\s*<?([^)\s>]+)>?[^)]*\)')

#: LaTeX-картинка: `\includegraphics[width=0.8\textwidth]{ela.png}`.
#: Так их пишут Школково и ЛЭШ.
INCLUDEGRAPHICS_RE = re.compile(
    r'\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}')

_MARKER_TEMPLATE = '[[FIGURE:{}]]'

#: Картинка, обёрнутая в разделители формулы: `$$\includegraphics{…}$$`
#: (живые ЛЭШ #63299, #63309 — так написано в исходном .tex). После
#: замены маркер оказался бы ВНУТРИ формулы, и KaTeX разбирал бы
#: `[[FIGURE:…]]` как математику. Обёртку снимаем: внутри неё нет
#: ничего, кроме картинки.
_MATH_ONLY_MARKER_RE = re.compile(
    r'(?:\$\$|\\\[|\\\(|\$)\s*(\[\[FIGURE:[0-9a-f]{64}\]\])\s*'
    r'(?:\$\$|\\\]|\\\)|\$)')


def image_hash(reference):
    """Хеш ссылки — он же тело маркера.

    Считается от ССЫЛКИ, а не от байтов файла: маркер надо уметь
    поставить, имея только текст, а строку `ProblemFigure` — имея только
    выгрузку. Обе стороны приходят к одному хешу независимо."""
    return hashlib.sha256(
        (reference or '').strip().encode('utf-8')).hexdigest()


def replace_images(text, resolve):
    """`(текст_с_маркерами, [(хеш, ссылка), ...])`.

    `resolve(ссылка)` возвращает истину, если файл есть на диске.
    Неразрешённые ссылки НЕ трогаются. Чистая функция: ни базы, ни
    файлов. Идемпотентна — на тексте с маркерами находит ноль ссылок."""
    if not text:
        return text, []
    found = []

    def take(match):
        reference = match.group(1)
        if not resolve(reference):
            return match.group(0)
        digest = image_hash(reference)
        if not any(d == digest for d, _ in found):
            found.append((digest, reference))
        return _MARKER_TEMPLATE.format(digest)

    out = MD_IMAGE_RE.sub(take, text)
    out = INCLUDEGRAPHICS_RE.sub(take, out)
    out = _MATH_ONLY_MARKER_RE.sub(r'\1', out)
    return out, found


#: Расширение файла → MIME-тип. Нужен только для ОТБОРА файлов при
#: обходе папки; тип показа определяется по байтам (`sniff_content_type`).
CONTENT_TYPES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.bmp': 'image/bmp',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
}

#: Сигнатура в начале файла → MIME-тип. Список закрытый: файл, чьи байты
#: не совпали ни с одной строкой, в базу не попадает и называется в
#: отчёте.
_MAGIC = (
    (b'\x89PNG\r\n\x1a\n', 'image/png'),
    (b'\xff\xd8\xff', 'image/jpeg'),
    (b'GIF87a', 'image/gif'),
    (b'GIF89a', 'image/gif'),
    (b'BM', 'image/bmp'),
)


def sniff_content_type(data):
    """MIME-тип по БАЙТАМ файла, или None.

    По содержимому, а не по расширению, и это не педантизм. У SolveHub
    три картинки скачаны с googleusercontent, и расширения в адресе нет
    вовсе — по имени их пришлось бы либо выбросить, либо угадать. Плюс
    рубеж безопасности: то, что не является картинкой, не будет отдано
    браузеру как картинка, каким бы ни было имя файла."""
    if not data:
        return None
    for signature, content_type in _MAGIC:
        if data.startswith(signature):
            return content_type
    # WEBP: `RIFF<4 байта длины>WEBP`
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return None
