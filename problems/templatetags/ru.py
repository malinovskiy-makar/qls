# -*- coding: utf-8 -*-
"""
Русская грамматика в шаблонах: склонение числительных и предлог «о / об».

⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ ФИЛЬТР. Встроенный `pluralize` умеет ДВЕ формы, а в
русском их три. В шаблонах кабинета стояло `{{ n|pluralize:",а,ов" }}` — и
это не «почти работает», а не работает вовсе: `pluralize` с тремя формами
возвращает ПУСТУЮ СТРОКУ при любом числе. На экране стояло «3 ученик»,
«11 задани». Проверено исполнением, держится тестом.

    {% load ru %}
    {{ n|count_ru:"ученик,ученика,учеников" }}   → «3 ученика»
    {{ n|plural_ru:"работа,работы,работ" }}      → «работы» (без числа)
    Полезная информация {{ name|prep_o }} {{ name }}  → «об Иване», «о Петре»
"""
from django import template

register = template.Library()

# Гласные, перед которыми предлог «о» превращается в «об».
# ⚠️ Список ровно из решения владельца: а, э, и, о, у. «е», «ё», «ю», «я»
# сюда НЕ входят — они начинаются с согласного звука «й» («о Елене»).
OB_VOWELS = 'аэиоуАЭИОУ'


def _forms(arg):
    """Три формы слова из строки «одна,две,пять»."""
    parts = [p.strip() for p in (arg or '').split(',')]
    while len(parts) < 3:
        parts.append(parts[-1] if parts else '')
    return parts[:3]


def pick(number, one, few, many):
    """Форма слова по числу. Чистая функция — её же зовут из питона."""
    try:
        number = abs(int(number))
    except (TypeError, ValueError):
        return many
    if number % 100 in (11, 12, 13, 14):
        return many
    last = number % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


@register.filter
def plural_ru(number, arg):
    """Слово в нужной форме, БЕЗ числа: `{{ n|plural_ru:"раз,раза,раз" }}`."""
    return pick(number, *_forms(arg))


@register.filter
def count_ru(number, arg):
    """Число и слово вместе: `{{ n|count_ru:"ученик,ученика,учеников" }}`."""
    return '%s %s' % (number, pick(number, *_forms(arg)))


@register.filter
def prep_o(value):
    """Предлог «о» или «об» перед словом. Пусто на входе — «о».

    Берётся ПЕРВАЯ буква первого слова: подсказка в поле заметок пишется как
    «Полезная информация об Иване Петрове», и решает первая буква имени.
    """
    text = (str(value) if value is not None else '').strip()
    if not text:
        return 'о'
    return 'об' if text[0] in OB_VOWELS else 'о'
