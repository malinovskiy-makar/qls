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
