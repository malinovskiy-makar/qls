# -*- coding: utf-8 -*-
"""Фильтр записи балла для шаблонов. Правила — в `problems/scorefmt.py`.

    {% load score %}
    {{ row.score|ball }}          → «0,5»
    {{ row.max_points|ball_dot }} → «0.5» (только для data-атрибутов и
                                    полей `type="number"`)

⚠️ `{% load %}` НЕ НАСЛЕДУЕТСЯ во включаемый шаблон — партиал, где стоит
`|ball`, обязан загрузить библиотеку сам. Наступали на это в сессии 9
(`_overview.html` падал пятисоткой «Invalid filter»).
"""
from django import template

from problems import scorefmt

register = template.Library()


@register.filter
def ball(value):
    return scorefmt.ball(value)


@register.filter
def ball_dot(value):
    return scorefmt.ball_dot(value)


@register.filter
def exact(value):
    """Число без округления — для допуска сравнения (шесть знаков)."""
    return scorefmt.exact(value)
