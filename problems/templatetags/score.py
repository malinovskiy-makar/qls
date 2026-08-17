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


@register.filter
def point_word(value):
    """«балл» / «балла» / «баллов» под это число.

    ⚠️ Делегирует `assignment_rows.point_word` — тому же правилу, по
    которому склоняет `points_text`. Слово, написанное в шаблоне руками,
    давало «3 баллов» на странице задания.
    """
    from problems.assignment_rows import point_word as pick_word

    return pick_word(value)
