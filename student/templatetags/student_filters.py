import json

from django import template

register = template.Library()


@register.filter
def dict_key(d, key):
    """{{ my_dict|dict_key:some_key }}"""
    return d.get(key)


@register.filter
def tojson(value):
    """Безопасный JSON-encode строки для вставки в JS."""
    return json.dumps(str(value))
