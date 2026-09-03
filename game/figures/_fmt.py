u"""Форматирование чисел в условиях сюжетов.

Отдельный модуль, а не «по месту в каждом сюжете»: одна и та же дробь
обязана выглядеть одинаково в условии, на чертеже и в разборе. Разъехавшись,
эти три записи выглядят как разные числа — и вопрос про «первый неверный
шаг» превращается в вопрос про опечатку.
"""
from fractions import Fraction

# Знаменатели, которые красиво пишутся десятичной дробью с запятой.
DECIMAL_DENOMS = (2, 4, 5, 8, 10, 20, 25, 50, 100)


def fmt(value):
    u"""Число по-русски: 20 · 0,5 · 3/7 (последнее — только если иначе никак)."""
    f = Fraction(value)
    if f.denominator == 1:
        return str(f.numerator)
    if f.denominator in DECIMAL_DENOMS:
        s = ('%f' % float(f)).rstrip('0').rstrip('.')
        return s.replace('.', ',')
    return u'%d/%d' % (f.numerator, f.denominator)


def coef(value, var='Q'):
    u"""Коэффициент при переменной: 1 не пишем, 0,5 пишем."""
    f = Fraction(value)
    if f == 1:
        return var
    if f == -1:
        return u'−' + var
    return fmt(f) + var


def linear(intercept, slope, var='Q'):
    u"""Уравнение прямой «P = 100 − Q» / «P = 40 + 2Q» / «P = 0,5Q»."""
    a, b = Fraction(intercept), Fraction(slope)
    if b == 0:
        return u'P = %s' % fmt(a)
    body = coef(abs(b), var)
    sign = u' − ' if b < 0 else u' + '
    if a == 0:
        return u'P = %s%s' % (u'−' if b < 0 else '', body)
    return u'P = %s%s%s' % (fmt(a), sign, body)


def money(value, unit):
    return u'%s %s' % (fmt(value), unit)
