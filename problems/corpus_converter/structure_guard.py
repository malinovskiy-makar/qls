# -*- coding: utf-8 -*-
"""Сохранность структуры — P0-пункт 5 плана аудита 2026-08-27.

Инвариант: **непустой исходный блок не имеет права стать пустым на
экране.** Аудит нашёл подтверждённую потерю содержимого (#41924: из
исходного `г) 3.` получился пустой блок «Часть г») и ещё 8 пустых
блоков в 6 карточках.

⚠️ Почему проверка идёт по ВИДИМОМУ тексту, а не по markdown-строке.
В Фазе −1 этой сессии #41924 не воспроизвёлся текстовой проверкой:
конвертер возвращает `'3.'` дословно, потеря выглядит нулевой. Пустым
блок становится ПОЗЖЕ, в markdown-рендере — `markdown-it` читает `3.`
как маркер нумерованного списка без содержимого и выдаёт
`<ol><li></li></ol>`, а `nh3` вдобавок срезает атрибуты, так что и сам
номер «3» до экрана не доходит. Замерено:

    render_markdown('3.')  ->  '<ol>\\n<li></li>\\n</ol>\\n'   видимый текст: ''

Любая проверка на уровне текста тут структурно слепа — считать надо то,
что увидит ученик.

⚠️ Пустой ИСХОДНИК — это не потеря. `#3989` (четыре пустых подпункта),
`#4053` (пустое условие), `#30530` (условие целиком состоит из
TeX-комментария) — материал не потерян конвертером, его не было. Такой
случай получает отдельный код `EMPTY-SRC`: чинить его выдумыванием
текста запрещено, это работа человека с источником.
"""
from __future__ import annotations

import html as html_module
import re

from problems.corpus_converter.tex_lexer import strip_tex_comments_lexed
from problems.rendering import render_markdown

_TAG_RE = re.compile(r'<[^>]+>')

#: Код «непустой исходник стал пустым на экране» — потеря содержимого.
CODE_LOST = 'EMPTY'
#: Код «в исходнике и не было содержимого» — дефект материала, не конвертера.
CODE_NO_SOURCE = 'EMPTY-SRC'


def visible_text(rendered_html):
    """Текст, который реально увидит ученик: без тегов, с раскрытыми
    HTML-сущностями, схлопнутыми пробелами.

    Картинок в допустимых тегах `problems/rendering.py` нет (`nh3`
    пропускает только текстовую разметку), поэтому «видно ли что-то» и
    «есть ли непробельный текст» здесь — одно и то же."""
    without_tags = _TAG_RE.sub(' ', rendered_html or '')
    return ' '.join(html_module.unescape(without_tags).split())


def has_meaningful_source(source_text):
    """Есть ли в исходнике содержимое, кроме TeX-комментариев?

    `#30530` — живой пример, где всё условие это одна строка
    `%прошлый интенсив …`: строка непустая, а содержимого в ней нет."""
    return bool(strip_tex_comments_lexed(source_text or '').strip())


def classify_block(source_text, converted_md):
    """`None` | `EMPTY` | `EMPTY-SRC` для одного блока."""
    if not has_meaningful_source(source_text):
        return CODE_NO_SOURCE
    if not visible_text(render_markdown(converted_md or '')):
        return CODE_LOST
    return None


def check_problem(blocks):
    """`blocks` — список `(имя, исходный_текст, конвертированный_md)`.

    Возвращает `(lost, needs_content)`:
    * `lost` — имена блоков, где содержимое ПОТЕРЯНО (всегда блокирует);
    * `needs_content` — у задачи вообще нет содержимого ни в одном блоке
      (живой `#3989`): публиковать её как решаемую нельзя.

    Пустое условие при непустых подпунктах задачей быть не перестаёт
    (живой `#4053`), поэтому `needs_content` считается по задаче целиком,
    а не по каждому блоку — иначе шлюз блокировал бы годный материал.
    """
    lost = []
    any_content = False
    for name, source_text, converted_md in blocks:
        verdict = classify_block(source_text, converted_md)
        if verdict == CODE_LOST:
            lost.append(name)
        if verdict is None:
            any_content = True
    return lost, (not any_content)
