"""Воронка «Высшей пробы» по событиям аналитики: посадочная → старт → сдача (ADR 0127).

Считает людей, а не события: человек — посетитель (cookie `weco_vid`, один браузер),
гость тоже человек, а тот, кто открыл посадочную десять раз, — один. События пишет
`vp/tracking.py` через `/api/track/`; здесь только чтение таблицы `Event`.

Два числа на переход: «дошли до шага» (сколько людей его сделало вообще, включая тех, кто
пришёл по прямой ссылке на вариант, минуя посадочную) и «из предыдущего шага» (сколько
из сделавших предыдущий шаг сделали и этот).
"""
from problems.models_platform import Event

STEPS = ('vp_landing_open', 'vp_start', 'vp_submit')


def funnel(since=None, until=None):
    """Словарь: `landing`, `start`, `submit` — людей на шаге; `landing_and_start`,
    `start_and_submit` — людей, сделавших оба шага перехода. `since` — включительно,
    `until` — не включая (моменты времени)."""
    events = Event.objects.filter(name__in=STEPS)
    if since is not None:
        events = events.filter(ts__gte=since)
    if until is not None:
        events = events.filter(ts__lt=until)
    people = {name: set() for name in STEPS}
    for name, visitor in events.values_list('name', 'visitor'):
        people[name].add(visitor)
    landing, start, submit = (people[name] for name in STEPS)
    return {
        'landing': len(landing), 'start': len(start), 'submit': len(submit),
        'landing_and_start': len(landing & start),
        'start_and_submit': len(start & submit),
    }
