# -*- coding: utf-8 -*-
"""Счёт контраста и наложений — ОДНА копия формулы на весь набор проверок.

⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ МОДУЛЬ. Формула яркости WCAG жила копиями в каждом
файле проверок, который меряет цвет. Две копии одной формулы — это ловушка
с отложенным сроком: поправят одну, забудут другую, и половина набора будет
мерить по-старому, оставаясь зелёной. Здесь она одна.

⚠️ ПОЧЕМУ НУЖЕН РАЗБОР `rgba(...)`, А НЕ ТОЛЬКО HEX. Часть подложек палитры
задана полупрозрачной намеренно: подсветка обязана ложиться и на карточку,
и на фон страницы, а жёсткий hex привязан к одной подложке. У самого
`rgba(...)` яркости НЕТ, пока он не лёг на что-то, — поэтому цвет сначала
сплющивается на подложку (`flatten`), и только потом меряется контраст.
Регулярка вида `#[0-9a-fA-F]{6}` на таком значении просто не находит ничего
и роняет проверку до самой проверки — так и падали две проверки янтаря.
"""
import re

__all__ = ['parse', 'alpha_of', 'luminance', 'ratio', 'over', 'flatten',
           'token', 'split_themes']

_HEX6 = re.compile(r'^#([0-9a-fA-F]{6})$')
_HEX3 = re.compile(r'^#([0-9a-fA-F]{3})$')
_FUNC = re.compile(r'^rgba?\(([^)]*)\)$')


def parse(value):
    """Цвет любой записи → (r, g, b). Прозрачность здесь НЕ учитывается."""
    value = str(value).strip()
    hit = _HEX6.match(value)
    if hit:
        raw = hit.group(1)
        return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))
    hit = _HEX3.match(value)
    if hit:
        raw = hit.group(1)
        return tuple(int(part * 2, 16) for part in raw)
    hit = _FUNC.match(value)
    if hit:
        parts = [p.strip() for p in hit.group(1).replace('/', ',').split(',')]
        return tuple(int(round(float(p))) for p in parts[:3])
    raise ValueError('не цвет: %r' % value)


def alpha_of(value):
    """Прозрачность записи: у hex — 1.0, у `rgba(...)` — четвёртое число."""
    value = str(value).strip()
    hit = _FUNC.match(value)
    if hit:
        parts = [p.strip() for p in hit.group(1).replace('/', ',').split(',')]
        if len(parts) >= 4:
            return float(parts[3])
    return 1.0


def luminance(value):
    channels = [c / 255 for c in parse(value)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def ratio(one, two):
    """Контраст WCAG. Оба цвета обязаны быть НЕПРОЗРАЧНЫМИ.

    Полупрозрачное сначала кладут на подложку через `flatten`/`over`.
    """
    first, second = luminance(one), luminance(two)
    top, bottom = max(first, second), min(first, second)
    return (top + 0.05) / (bottom + 0.05)


def over(colour, alpha, below):
    """Цвет с заданной прозрачностью поверх непрозрачного → сплошной."""
    top, base = parse(colour), parse(below)
    return '#%02x%02x%02x' % tuple(
        round(top[i] * alpha + base[i] * (1 - alpha)) for i in range(3))


def flatten(value, below):
    """Значение токена (hex ИЛИ `rgba(...)`) на подложке → сплошной цвет.

    Прозрачность берётся из самой записи, а не подставляется числом рядом:
    иначе поправленный в токенах `.34` разъедется с `.35` в проверке, и
    проверка будет мерить не то, что на экране.
    """
    return over(value, alpha_of(value), below)


def token(css, name):
    """Значение токена `--name` из куска CSS. Понимает hex и `rgba(...)`."""
    hit = re.search(r'--%s:\s*([^;]+);' % re.escape(name.lstrip('-')), css)
    return hit.group(1).strip() if hit else None


def split_themes(css):
    """Файл токенов → (светлая половина, тёмная половина).

    ⚠️ Режем РОВНО по селектору тёмной темы. Поэтому его нельзя цитировать
    в комментариях внутри файла: третья граница разводит половины, и
    проверки падают не на цвете, а на собственном объяснении.
    """
    at = css.index('[data-theme="dark"]')
    return css[:at], css[at:]
