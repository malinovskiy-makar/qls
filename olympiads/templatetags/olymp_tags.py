"""Мелкие фильтры экранов раздела «Олимпиады» (ночь 30.10)."""
from django import template

register = template.Library()


@register.filter
def nbsp_int(value):
    """2671 → «2 671» с неразрывным пробелом: число не рвётся между строк."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return value
    return '{:,}'.format(number).replace(',', ' ')


@register.filter
def score(value):
    """34.0 → «34», 34.5 → «34,5»; None → пусто."""
    from olympiads.navigator import _fmt
    return _fmt(value)


@register.filter
def get_item(mapping, key):
    """`{{ row.by_grade|get_item:view.grade }}` — словарь по ключу в шаблоне."""
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def prev_number(rows, index):
    """Номер задания перед строкой `index` (счёт с 1): «← Задание 5»."""
    return _number(rows, int(index) - 2)


@register.filter
def next_number(rows, index):
    """Номер задания после строки `index` (счёт с 1): «Задание 7 →»."""
    return _number(rows, int(index))


def _number(rows, position):
    if 0 <= position < len(rows):
        return rows[position]['number']
    return ''
