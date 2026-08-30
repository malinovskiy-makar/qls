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


#: Разделитель в ключе картинки Школково: `<id сессии>|<имя файла>`.
#: Ровно так устроены ключи `image_map.json` в выгрузке, поэтому ключ и
#: ссылка — одно и то же, и отдельной карты «ссылка → ключ» не нужно.
SHKOLKOVO_KEY_SEPARATOR = '|'


def qualify_shkolkovo_images(text, session_id):
    r"""Дописать к ссылке Школково id сессии, из которой взят этот текст.

    ⚠️ Почему без этого ссылка неразрешима. В выгрузке Школково файл
    называется `<TexSessionId>_<имя>`, а в тексте стоит голое имя
    (`\includegraphics{ela.png}`). Имена НЕ уникальны: `7.png` встречается
    в разных задачах и означает разные файлы. Условие и решение ОДНОЙ
    задачи приходят разными сессиями (`QuestionTexSessionId` и
    `SolutionTexSessionId`), поэтому квалифицировать нужно тем id, из
    которого пришёл именно этот кусок текста.

    ⚠️ Прошлая сессия сравнила префиксы файлов с `Id` задачи, получила
    пересечение ноль и заключила, что картинок Школково нет вовсе
    (см. `reconvert.shkolkovo_records`). Префикс — это `TexSessionId`,
    а не `Id`: по правильному ключу совпадают все 328 префиксов и
    разрешаются 452 ссылки из 454 у 296 задач из 298. Две оставшиеся
    не скачались при выгрузке и честно названы в `failed_images.json`.

    Без id сессии (0/None — так у `GradeCriteriaTexSessionId` почти
    везде) ссылка остаётся как была: разрешить её нечем, а молча стереть
    нельзя (ADR 0035).
    """
    if not text or not session_id:
        return text

    def add_prefix(match):
        reference = match.group(1).strip()
        if SHKOLKOVO_KEY_SEPARATOR in reference:
            return match.group(0)          # уже квалифицирована
        return match.group(0).replace(
            match.group(1),
            f'{session_id}{SHKOLKOVO_KEY_SEPARATOR}{reference}')

    return INCLUDEGRAPHICS_RE.sub(add_prefix, text)


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
