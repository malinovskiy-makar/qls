"""Служебные выборки раздела олимпиад.

Здесь живёт то, что нужно сразу нескольким экранам, — чтобы лента дат на
главной и календарь раздела не разошлись однажды в отборе событий.
"""
from collections import Counter
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
    placed = set()
    for month in ACADEMIC_MONTHS:
        year = start_year if month >= 9 else start_year + 1
        in_month = [
            e for e in events
            if e.date_start and e.date_start.month == month
            and e.date_start.year == year
        ]
        placed.update(e.pk for e in in_month)
        months.append({
            'number': month,
            'year': year,
            'name': MONTHS_NOMINATIVE[month - 1],
            'events': in_month,
        })

    undated = [e for e in events if not e.date_start]
    # ⚠️ Событие С ДАТОЙ, которая в двенадцать месяцев сетки не попала.
    # Случай не выдуманный: регистрацию на сезон 2026/27 открывают в
    # августе 2026, то есть ДО сентября, с которого сетка начинается.
    # Без этой корзины оно пропадало бы с экрана молча — а это ровно та
    # дата, к которой школьник должен успеть.
    outside = [
        e for e in events
        if e.date_start and e.pk not in placed
    ]
    return months, undated, outside


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


# ⚠️ РАЗБИВКА ПО 900 — НЕ ПРИДИРКА. SQLite падает с «too many SQL
# variables» на filter(id__in=...) с десятками тысяч ключей, а у крупной
# олимпиады их столько и будет. Ошибка вылезла бы не сегодня, а в день
# первой удачной привязки — то есть в самый неудобный момент.
ID_CHUNK = 900


def problem_stats(olympiad):
    """Распределение сложности и форматов по привязанным задачам банка.

    Возвращает None, если привязок нет вовсе, — тогда панели честно
    говорят «Задания пока не размечены» вместо нулевых полосок.
    """
    from problems.models import OlympiadRef, Problem

    ids = sorted(set(
        OlympiadRef.objects
        .filter(olympiad_slug=olympiad.slug)
        .values_list('problem_id', flat=True)
    ))
    if not ids:
        return None

    difficulty = Counter()
    formats = Counter()
    total = 0
    for start in range(0, len(ids), ID_CHUNK):
        chunk = ids[start:start + ID_CHUNK]
        for level, kind in (Problem.objects.filter(id__in=chunk)
                            .values_list('difficulty', 'problem_type')):
            total += 1
            difficulty[level] += 1
            formats[(kind or '').strip() or 'без пометки'] += 1

    def pct(count):
        return round(100 * count / total) if total else 0

    return {
        'total': total,
        'difficulty': [
            {'level': level, 'count': difficulty.get(level, 0),
             'pct': pct(difficulty.get(level, 0))}
            for level in (1, 2, 3, 4, 5)
        ],
        'unknown_difficulty': difficulty.get(None, 0),
        'formats': [
            {'name': name, 'count': count, 'pct': pct(count)}
            for name, count in formats.most_common(6)
        ],
    }


def pass_score_rows(olympiad, years_back=5):
    """Проходные на заключительный этап: строка на класс, колонка на год.

    Год, по которому данных нет, НЕ пропускается и НЕ интерполируется —
    он возвращается пустой ячейкой. Дыра в данных это тоже сведение:
    сглаженная кривая соврала бы школьнику про год, которого мы не знаем.
    """
    from .models import OlympiadScore

    scores = list(
        olympiad.scores
        .filter(score_type=OlympiadScore.ScoreType.PASS_TO_FINAL)
        .order_by('grade', 'year')
    )
    if not scores:
        return [], []

    years = sorted({s.year for s in scores})[-years_back:]
    grades = sorted({s.grade for s in scores if s.grade is not None})
    by_key = {(s.grade, s.year): s for s in scores}

    rows = []
    for grade in grades:
        cells = []
        for year in years:
            score = by_key.get((grade, year))
            if score is None:
                cells.append({'year': year, 'missing': True})
            else:
                cells.append({
                    'year': year,
                    'missing': False,
                    'value': score.value,
                    'max_value': score.max_value,
                    'pct': round(100 * score.share) if score.share else 0,
                })
        rows.append({'grade': grade, 'cells': cells})
    return rows, years


# Больше трёх колонок в таблицу сравнения не помещается — ни на 960
# пикселях, ни в голове читающего.
COMPARE_LIMIT = 3


def compare_rows(olympiads):
    """Строки таблицы сравнения плюс признак «значения различаются».

    Совпавшая строка приглушается, различающаяся — нет. Смысл экрана
    именно в этом: школьник должен с одного взгляда видеть, что у
    олимпиад одинаково, а что нет.
    """
    from .models import OlympiadBenefit, UniversityProgram

    programs_total = UniversityProgram.objects.count()

    def level(olympiad):
        value = olympiad.level_for()
        if value:
            return '{} уровень'.format(value)
        if olympiad.kind == olympiad.Kind.VSOSH:
            return 'Не в перечне: льгота по закону'
        return 'Уровня нет'

    def admission(olympiad):
        benefits = list(olympiad.benefits.all())
        if not benefits:
            return 'Данных нет'
        bvi = sum(1 for b in benefits
                  if b.benefit_type == OlympiadBenefit.BenefitType.BVI)
        if olympiad.kind == olympiad.Kind.VSOSH:
            return 'Без вступительных испытаний, ЕГЭ подтверждать не нужно'
        return 'Льготы есть' if bvi else 'Только сто баллов или ничего'

    def stage_format(olympiad, index):
        stages = list(olympiad.stages.all())
        if not stages:
            return 'Данных нет'
        return stages[index].get_format_display()

    def benefit_summary(olympiad):
        benefits = [b for b in olympiad.benefits.all()
                    if b.benefit_type == OlympiadBenefit.BenefitType.BVI]
        if not olympiad.benefits.all():
            return 'Данных нет'
        return 'БВИ на {} из {}'.format(len(benefits), programs_total)

    def next_event(olympiad):
        event = olympiad.next_event
        if not event:
            return 'Дат пока нет'
        return '{}: {}'.format(event.get_kind_display(), event.display_date)

    spec = [
        ('Уровень в перечне', level),
        ('Что даёт при поступлении', admission),
        ('Классы', lambda o: o.grades_label or 'Данных нет'),
        ('Число этапов', lambda o: str(o.stages.count())),
        ('Формат отбора', lambda o: stage_format(o, 0)),
        ('Формат финала', lambda o: stage_format(o, -1)),
        ('Командная или личная', lambda o: 'Командная' if o.is_team else 'Личная'),
        ('Города проведения', lambda o: o.cities_summary or 'Данных нет'),
        ('Ближайшее событие', next_event),
        ('Льгота на ключевых программах', benefit_summary),
        ('Задач у нас', lambda o: str(o.problem_count)),
        ('Вариантов у нас', lambda o: str(o.variant_count)),
    ]

    rows = []
    for label, getter in spec:
        values = [getter(o) for o in olympiads]
        rows.append({
            'label': label,
            'values': values,
            'differs': len(set(values)) > 1,
        })
    return rows
