"""Служебные выборки раздела олимпиад.

Здесь живёт то, что нужно сразу нескольким экранам, — чтобы лента дат на
главной и календарь раздела не разошлись однажды в отборе событий.
"""
from datetime import date

from .models import Olympiad, OlympiadEvent, current_academic_year

# Учебный год идёт с сентября по август — в этом порядке и рисуется
# годовая сетка календаря.
ACADEMIC_MONTHS = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]

MONTHS_NOMINATIVE = (
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
)
MONTHS_SHORT = (
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
)


def upcoming_events(limit=5, today=None, academic_year=None):
    """Ближайшие события для ленты на главной.

    Сначала подтверждённые, начиная с сегодня, по возрастанию даты. Затем
    неподтверждённые — они идут в КОНЕЦ и рисуются приглушённо: у них нет
    числа, и ставить их вперемешку с настоящими датами значит выдавать
    ориентир за факт.
    """
    today = today or date.today()
    academic_year = academic_year or current_academic_year()
    base = (
        OlympiadEvent.objects
        .filter(olympiad__is_published=True)
        .select_related('olympiad', 'stage')
    )
    confirmed = list(
        base.filter(date_status=OlympiadEvent.DateStatus.CONFIRMED,
                    date_start__gte=today)
        .order_by('date_start')[:limit]
    )
    if len(confirmed) >= limit:
        return confirmed, True
    approximate = list(
        base.filter(academic_year=academic_year)
        .exclude(date_status=OlympiadEvent.DateStatus.CONFIRMED)
        .order_by('olympiad__name_short')[:limit - len(confirmed)]
    )
    return confirmed + approximate, bool(confirmed)


def calendar_months(academic_year=None, slug=None):
    """Годовая сетка календаря: двенадцать месяцев с сентября по август.

    Событие без подтверждённой даты не имеет месяца — раскладывать его по
    сетке было бы враньём. Такие события возвращаются отдельным списком.
    """
    academic_year = academic_year or current_academic_year()
    start_year = int(academic_year.split('/')[0])
    events = (
        OlympiadEvent.objects
        .filter(olympiad__is_published=True, academic_year=academic_year)
        .select_related('olympiad', 'stage')
        .order_by('date_start', 'olympiad__name_short')
    )
    if slug:
        events = events.filter(olympiad__slug=slug)
    events = list(events)

    months = []
    for month in ACADEMIC_MONTHS:
        year = start_year if month >= 9 else start_year + 1
        months.append({
            'number': month,
            'year': year,
            'name': MONTHS_NOMINATIVE[month - 1],
            'events': [
                e for e in events
                if e.date_start and e.date_start.month == month
                and e.date_start.year == year
            ],
        })
    undated = [e for e in events if not e.date_start]
    return months, undated


def events_for_external_calendar(academic_year=None):
    """События олимпиад в виде, пригодном для КАЛЕНДАРЯ ЗАНЯТИЙ.

    ⚠️ Это ЗАГОТОВКА. Сама интеграция с `calendar_stub` не сделана
    намеренно: календарь занятий — работающий экран с живыми данными
    репетиторов, и подключать к нему второй источник событий надо
    отдельной задачей с приёмкой, а не попутно.

    Что здесь есть: список словарей с полями, которые уже понимает
    `problems.CalendarEvent` — `title`, `event_type`, `start_datetime`
    (датой, без времени), `description`. Поле `source_key` своё: по нему
    повторный запуск обновит прежнюю запись вместо создания дубля.

    Что надо будет сделать при подключении (по шагам):
    1. Завести в `problems.CalendarEvent` поле для внешнего ключа
       (`external_key`) с индексом — иначе дубли неизбежны. Это миграция
       в `problems`, и делать её должен тот, кто владеет тем приложением.
    2. Написать команду `sync_olympiad_calendar`, которая берёт этот
       список и делает `update_or_create` по `external_key`.
    3. Решить, ЧЬИ это события: `is_global=True` (видно всем) или
       привязка к группам. Автор обязателен — у `CalendarEvent` поле
       `author` не пустое.
    4. НЕ переносить события без подтверждённой даты: у `CalendarEvent`
       поле `start_datetime` обязательное, и ориентир «обычно в январе»
       туда придётся превратить в конкретное число. Это ровно то враньё,
       которое запрещает `OlympiadEvent.clean()`.
    """
    academic_year = academic_year or current_academic_year()
    rows = []
    for event in (OlympiadEvent.objects
                  .filter(olympiad__is_published=True,
                          academic_year=academic_year,
                          date_status=OlympiadEvent.DateStatus.CONFIRMED)
                  .exclude(date_start=None)
                  .select_related('olympiad', 'stage')
                  .order_by('date_start')):
        rows.append({
            'source_key': 'olympiad-event-{}'.format(event.pk),
            'title': '{} · {}'.format(event.olympiad.name_short,
                                      event.get_kind_display()),
            'event_type': 'olympiad',
            'start_datetime': event.date_start,
            'end_datetime': event.date_end,
            'description': (event.olympiad.official_url or ''),
            'olympiad_slug': event.olympiad.slug,
        })
    return rows


def published_olympiads():
    """Опубликованные олимпиады с подгруженными связями — для списков."""
    return (
        Olympiad.objects.filter(is_published=True)
        .prefetch_related('levels', 'events', 'stages', 'variants')
    )
