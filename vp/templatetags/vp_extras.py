"""Фильтры показа тренажёра ВП. Считать баллы они не умеют — только оформлять."""
import re
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()

_MINUS = '−'  # настоящий минус, а не дефис: рядом с цифрами не «прыгает»


def _decimal(value):
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


@register.filter
def num(value):
    """Число по-русски: целое без хвоста, дробное через запятую («4,5», «2,25»)."""
    number = _decimal(value)
    if number is None:
        return value
    if number == number.to_integral_value():
        text = str(int(number))
    else:
        text = format(number.normalize(), 'f')
    return text.replace('.', ',').replace('-', _MINUS)



@register.filter
def signed(value):
    """Балл со знаком: «+2», «0», «−1» (только оформление)."""
    number = _decimal(value)
    if number is None:
        return value
    text = num(number)
    return f'+{text}' if number > 0 else text


@register.filter
def dec2(value):
    """Два знака после запятой по-русски: «3,00», «−1,50» (только оформление)."""
    number = _decimal(value)
    if number is None:
        return value
    return f'{number:.2f}'.replace('.', ',').replace('-', _MINUS)


def _plural(number, one, few, many):
    if number != number.to_integral_value():
        return few  # «4,5 балла»
    n = abs(int(number))
    if 11 <= n % 100 <= 14:
        return many
    if n % 10 == 1:
        return one
    if 2 <= n % 10 <= 4:
        return few
    return many


@register.filter
def points_each(value):
    """«по 2 балла», «по 1 баллу», «по 4,5 балла», «по 5 баллов»."""
    number = _decimal(value)
    if number is None:
        return ''
    word = _plural(number, 'баллу', 'балла', 'баллов')
    return f'по {num(number)} {word}'


@register.filter
def points_word(value):
    """«3 балла», «1 балл», «4,5 балла» — сумма с единицей."""
    number = _decimal(value)
    if number is None:
        return ''
    return f'{num(number)} {_plural(number, "балл", "балла", "баллов")}'


@register.filter
def mmss(value):
    """Секунды → «30:00». Пусто и не число — пустая строка."""
    try:
        seconds = max(0, int(value))
    except (TypeError, ValueError):
        return ''
    return f'{seconds // 60:02d}:{seconds % 60:02d}'


@register.filter
def gap_parts(text):
    """Текст условия → куски между пропусками («______»).

    Шаблон ставит на место разрыва пустое подчёркнутое поле. Куски идут в
    шаблон как обычный текст и экранируются им самим: `mark_safe` не нужен.
    """
    return re.split(r'_{3,}', text or '')


@register.filter
def plural(value, forms):
    """«44|plural:"задание,задания,заданий"» → «44 задания»."""
    number = _decimal(value)
    if number is None:
        return ''
    one, few, many = [form.strip() for form in forms.split(',')]
    return f'{num(number)} {_plural(number, one, few, many)}'


@register.filter
def minutes(value):
    """1800 → «30 минут»."""
    try:
        total = int(value) // 60
    except (TypeError, ValueError):
        return ''
    return plural(total, 'минута,минуты,минут')


@register.filter
def grade_label(value):
    """'9-10' → «9–10 классы», '11' → «11 класс»."""
    return {'9-10': '9–10 классы', '11': '11 класс'}.get(value, f'{value} кл.')


@register.filter
def grade_chip(value):
    """'9-10' → «9–10», '11' → «11»: класс в узкую колонку таблицы, без слова."""
    return {'9-10': '9–10', '11': '11'}.get(value, str(value))


@register.filter
def plural_word(value, forms):
    """«44|plural_word:"задание,задания,заданий"» → «задания»: слово без числа.

    Нужно там, где число стоит отдельно и крупно (плитки фактов посадочной).
    """
    number = _decimal(value)
    if number is None:
        return ''
    one, few, many = [form.strip() for form in forms.split(',')]
    return _plural(number, one, few, many)
