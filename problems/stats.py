"""
Слой агрегации: (пользователь, период) → готовые словари для экранов и JSON.

ГЛАВНОЕ ПРАВИЛО МОДУЛЯ: считаем В БАЗЕ, а не в питоне. Ни одна функция здесь
не перебирает события по одному — только `values().annotate()` и `aggregate()`.
У активного ученика за год десятки тысяч событий; цикл по ним на каждое
открытие страницы — это секунды ожидания.

Второе правило: КЭШ. Ключ — (пользователь, период), 5 минут. Статистика за
месяц не меняется от того, что её посмотрели дважды за минуту, а страница
собирается из десятка запросов.

Третье: ИГРА СЧИТАЕТСЯ ОТДЕЛЬНО. Результат в «Пуле» и результат по домашке —
разные вещи, и складывать их в одну шкалу «решено задач» значит выдать
угадайку на скорость за учебную работу. `game_stats()` живёт своей функцией,
и на экране блок игры визуально отделён.
"""
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.utils import timezone

CACHE_SECONDS = 300

# Периоды, которые понимает переключатель на экране.
PERIODS = (
    ('day', 'День'),
    ('week', 'Неделя'),
    ('month', 'Месяц'),
    ('all', 'Всё время'),
)
PERIOD_DAYS = {'day': 1, 'week': 7, 'month': 30}

# Минимум попыток, при котором тема попадает в «сильные/слабые».
# Меньше — не статистика, а случайность: одна угаданная задача сделала бы
# тему «сильной», одна невнимательность — «слабой».
MIN_ATTEMPTS_FOR_RANKING = 5

# Укрупнённые разделы для паутинки. По 21 канонической теме радар нечитаем —
# подписи налезают друг на друга. Группировка по ключевым словам названия:
# отдельного поля «раздел» у Topic нет, заводить его ради одного графика
# значит просить преподавателя разметить 849 тем.
SECTIONS = (
    ('Микроэкономика', ('спрос', 'предложен', 'эластич', 'равновес',
                        'излиш', 'налог', 'потолок', 'дефицит')),
    ('Фирма и рынки', ('издерж', 'фирм', 'конкурен', 'монопол', 'олигопол',
                       'прибыл', 'производ')),
    ('Макроэкономика', ('ввп', 'инфляц', 'безработ', 'мультипликат',
                        'совокуп', 'цикл', 'деньг', 'банк', 'бюджет')),
    ('Международная', ('торгов', 'преимуществ', 'курс', 'валют', 'экспорт',
                       'импорт', 'кпв')),
    ('Прочее', ()),
)


# ===========================================================================
# Период
# ===========================================================================

def period_bounds(period, now=None):
    """(начало, конец) периода. Для «всё время» начало = None."""
    now = now or timezone.now()
    days = PERIOD_DAYS.get(period)
    if days is None:
        return None, now
    return now - timedelta(days=days), now


def _events(user, period, now=None):
    """События пользователя за период. Игра исключена — у неё своя шкала."""
    from .models import LearningEvent

    start, end = period_bounds(period, now)
    queryset = LearningEvent.objects.filter(user=user).exclude(source='game')
    if start is not None:
        queryset = queryset.filter(created_at__gte=start)
    return queryset


def _problem_events(user, period, now=None):
    """Только события ПО ЗАДАЧАМ: служебные отметки «работа сдана» не в счёт."""
    return _events(user, period, now).filter(
        Q(catalog_problem__isnull=False) | Q(custom_problem__isnull=False))


# ===========================================================================
# Сводка
# ===========================================================================

def overview(user, period='month', now=None):
    """Решено, попыток, доля верных, время, опыт + изменение к прошлому.

    Изменение считается к РАВНОМУ по длине предыдущему периоду. Для «всё
    время» сравнивать не с чем — там изменение None, и экран честно ничего
    не рисует вместо стрелки в никуда.
    """
    now = now or timezone.now()
    current = _period_totals(user, period, now)
    days = PERIOD_DAYS.get(period)
    if days is None:
        previous = None
    else:
        shifted = now - timedelta(days=days)
        previous = _period_totals(user, period, shifted)

    result = dict(current)
    result['change'] = {}
    if previous is not None:
        for key in ('solved', 'attempted', 'accuracy', 'minutes', 'xp'):
            result['change'][key] = _delta(current[key], previous[key])
    return result


def _period_totals(user, period, now):
    from .models import DailySummary

    start, end = period_bounds(period, now)
    events = _problem_events(user, period, now)
    if start is not None:
        events = events.filter(created_at__lt=end)

    counts = events.aggregate(
        solved=Count('pk', filter=Q(event_type='solved')),
        failed=Count('pk', filter=Q(event_type='failed')),
        seconds=Sum('time_spent_seconds'))
    solved = counts['solved'] or 0
    failed = counts['failed'] or 0
    attempted = solved + failed

    summaries = DailySummary.objects.filter(user=user)
    if start is not None:
        summaries = summaries.filter(
            date__gte=timezone.localtime(start).date(),
            date__lt=timezone.localtime(end).date() + timedelta(days=1))
    xp = summaries.aggregate(total=Sum('xp_earned'))['total'] or 0

    return {
        'solved': solved,
        'attempted': attempted,
        # Доля верных считается от ПОПЫТОК (верные + неверные). Пропуск и
        # просто открытая задача точность не портят — тот же принцип, что
        # в сводке Econ Rush.
        'accuracy': round(solved * 100.0 / attempted, 1) if attempted else None,
        'minutes': int(round((counts['seconds'] or 0) / 60)),
        'xp': xp,
    }


def _delta(current, previous):
    """Изменение к прошлому периоду: (разница, направление)."""
    if current is None or previous is None:
        return None
    diff = round(current - previous, 1)
    direction = 'up' if diff > 0 else ('down' if diff < 0 else 'flat')
    # `abs_diff` — чтобы на экране не выходило «↓ -63 мин»: минус и стрелка
    # вниз говорят одно и то же, а вместе читаются как двойное отрицание.
    return {'diff': diff, 'abs_diff': abs(diff), 'direction': direction,
            'previous': previous}


# ===========================================================================
# Темы
# ===========================================================================

def topic_breakdown(user, period='month', now=None):
    """По каждой теме: попыток, верных, доля, владение. Одним запросом."""
    from .models import StudentTopicProgress

    rows = (_problem_events(user, period, now)
            .filter(topic__isnull=False,
                    event_type__in=('solved', 'failed'))
            .values('topic_id', 'topic__name')
            .annotate(attempted=Count('pk'),
                      solved=Count('pk', filter=Q(event_type='solved')))
            .order_by('-attempted'))

    mastery = dict(StudentTopicProgress.objects.filter(student=user)
                   .values_list('topic_id', 'mastery_level'))

    result = []
    for row in rows:
        attempted = row['attempted']
        solved = row['solved']
        result.append({
            'topic_id': row['topic_id'],
            'name': row['topic__name'],
            'attempted': attempted,
            'solved': solved,
            'accuracy': round(solved * 100.0 / attempted) if attempted else 0,
            'mastery': mastery.get(row['topic_id'], 'none'),
        })
    return result


def strongest_weakest(user, period='all', now=None, limit=3, rows=None):
    """Три сильные и три слабые темы.

    В выборку попадают только темы с ≥5 попытками: на трёх задачах «доля
    верных 100%» не значит ничего, а показывать это как сильную сторону —
    вводить в заблуждение и ученика, и родителя.
    """
    # `rows` можно передать готовым: на экране разбивка по темам считается
    # один раз и используется тремя блоками (карта тем, рейтинг, паутинка).
    # Без этого один и тот же запрос уходил бы в базу трижды.
    source = topic_breakdown(user, period, now) if rows is None else rows
    rows = [r for r in source if r['attempted'] >= MIN_ATTEMPTS_FOR_RANKING]
    by_accuracy = sorted(rows, key=lambda r: (-r['accuracy'], -r['attempted']))
    return {
        'strong': by_accuracy[:limit],
        'weak': list(reversed(by_accuracy[-limit:])) if len(rows) > limit
        else [],
        'enough_data': len(rows) >= 2,
        'min_attempts': MIN_ATTEMPTS_FOR_RANKING,
    }


def section_radar(user, period='all', now=None, rows=None):
    """Паутинка по укрупнённым разделам."""
    rows = topic_breakdown(user, period, now) if rows is None else rows
    buckets = {name: {'attempted': 0, 'solved': 0} for name, _ in SECTIONS}
    for row in rows:
        bucket = buckets[_section_of(row['name'])]
        bucket['attempted'] += row['attempted']
        bucket['solved'] += row['solved']
    return [
        {'name': name,
         'accuracy': (round(buckets[name]['solved'] * 100.0
                            / buckets[name]['attempted'])
                      if buckets[name]['attempted'] else 0),
         'attempted': buckets[name]['attempted']}
        for name, _ in SECTIONS
    ]


def _section_of(topic_name):
    lowered = (topic_name or '').lower()
    for name, keys in SECTIONS:
        if any(key in lowered for key in keys):
            return name
    return SECTIONS[-1][0]


# ===========================================================================
# Трудные задачи
# ===========================================================================

def hardest_problems(user, period='all', now=None, limit=5):
    """Где ученик споткнулся: больше всего неверных попыток и времени.

    Заголовок на экране нейтральный («стоит вернуться»), потому что это не
    список провалов, а список того, что ещё можно дорешать.
    """
    rows = (_problem_events(user, period, now)
            .filter(catalog_problem__isnull=False)
            .values('catalog_problem_id', 'catalog_problem__title',
                    'catalog_problem__statement')
            .annotate(fails=Count('pk', filter=Q(event_type='failed')),
                      solves=Count('pk', filter=Q(event_type='solved')),
                      seconds=Sum('time_spent_seconds'))
            .filter(fails__gt=0)
            .order_by('-fails', '-seconds')[:limit])

    result = []
    for row in rows:
        title = row['catalog_problem__title'] or ''
        if not title:
            title = (row['catalog_problem__statement'] or '')[:80]
        result.append({
            'problem_id': row['catalog_problem_id'],
            'title': title,
            'fails': row['fails'],
            'solved': row['solves'] > 0,
            'minutes': int(round((row['seconds'] or 0) / 60)),
        })
    return result


# ===========================================================================
# Активность
# ===========================================================================

def activity_calendar(user, days=365, now=None):
    """Данные теплокарты — из ДНЕВНЫХ СВОДОК, а не из событий.

    Ради этого сводки и заведены: год это 365 строк вместо десятков тысяч.
    """
    from .models import DailySummary

    now = now or timezone.now()
    end = timezone.localtime(now).date()
    start = end - timedelta(days=days - 1)
    rows = (DailySummary.objects
            .filter(user=user, date__gte=start, date__lte=end)
            .values('date', 'problems_solved', 'problems_attempted',
                    'xp_earned'))
    by_date = {r['date']: r for r in rows}

    peak = max([r['problems_solved'] for r in rows] or [0])

    # Координаты клеток считает ПИТОН, а рисует шаблон. Так же, как чертежи
    # генераторов Econ Rush: считать в шаблоне нечем, а держать вторую
    # раскладку в JS значит завести второй источник правды о том, где какой
    # день. Сетка как у GitHub: столбец — неделя, строка — день недели.
    CELL, GAP, TOP = 11, 3, 16
    step = CELL + GAP
    # Начинаем с понедельника той недели, в которую попал старт.
    first_monday = start - timedelta(days=start.weekday())

    cells = []
    months = []
    seen_months = set()
    day = start
    while day <= end:
        row = by_date.get(day)
        solved = row['problems_solved'] if row else 0
        column = (day - first_monday).days // 7
        cells.append({
            'date': day,
            'solved': solved,
            'attempted': row['problems_attempted'] if row else 0,
            'xp': row['xp_earned'] if row else 0,
            'level': _heat_level(solved, peak),
            'x': column * step,
            'y': TOP + day.weekday() * step,
        })
        key = (day.year, day.month)
        if key not in seen_months and day.day <= 7:
            seen_months.add(key)
            months.append({'name': MONTHS_SHORT[day.month - 1],
                           'x': column * step})
        day += timedelta(days=1)

    columns = ((end - first_monday).days // 7) + 1
    return {'cells': cells, 'start': start, 'end': end, 'peak': peak,
            'months': months, 'width': columns * step,
            'total_days': sum(1 for c in cells if c['solved'])}


MONTHS_SHORT = ('янв', 'фев', 'мар', 'апр', 'май', 'июн',
                'июл', 'авг', 'сен', 'окт', 'ноя', 'дек')


def _heat_level(solved, peak):
    """Пять оттенков, как в теплокартах GitHub и Strava."""
    if not solved:
        return 0
    if peak <= 1:
        return 4
    share = solved / peak
    if share <= 0.25:
        return 1
    if share <= 0.5:
        return 2
    if share <= 0.75:
        return 3
    return 4


def level_history(user, now=None):
    """Точки роста уровня: (дата, накопленный опыт, уровень)."""
    from .gamification import level_for_xp
    from .models import DailySummary

    rows = (DailySummary.objects.filter(user=user)
            .order_by('date').values('date', 'xp_earned'))
    total = 0
    points = []
    for row in rows:
        total += row['xp_earned']
        points.append({'date': row['date'], 'xp': total,
                       'level': level_for_xp(total)})
    return points


def activity_by_weekday(user, period='all', now=None):
    """Попытки по дням недели (0 — понедельник)."""
    from .models import DailySummary

    start, _ = period_bounds(period, now)
    rows = DailySummary.objects.filter(user=user)
    if start is not None:
        rows = rows.filter(date__gte=timezone.localtime(start).date())
    buckets = [0] * 7
    for row in rows.values('date', 'problems_attempted'):
        buckets[row['date'].weekday()] += row['problems_attempted']
    names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    return [{'label': names[i], 'value': buckets[i]} for i in range(7)]


def activity_by_hour(user, period='all', now=None):
    """Попытки по часам — считает БАЗА (extract hour), не питон."""
    from django.db.models.functions import ExtractHour

    rows = (_problem_events(user, period, now)
            .filter(event_type__in=('solved', 'failed'))
            .annotate(hour=ExtractHour('created_at'))
            .values('hour')
            .annotate(attempted=Count('pk'),
                      solved=Count('pk', filter=Q(event_type='solved'))))
    buckets = {r['hour']: r for r in rows}
    return [{'hour': h,
             'value': buckets.get(h, {}).get('attempted', 0),
             'solved': buckets.get(h, {}).get('solved', 0)}
            for h in range(24)]


def best_time_hint(by_hour):
    """Текстовый вывод под графиками. Формулировка НЕЙТРАЛЬНАЯ, без укоров.

    «Ты решаешь лучше всего по вечерам» — наблюдение. «Ты плохо решаешь по
    утрам» — то же число и упрёк; упрёк из статистики делать нельзя.
    """
    parts = {'утром (6–12)': range(6, 12), 'днём (12–18)': range(12, 18),
             'вечером (18–23)': range(18, 23), 'ночью (23–6)':
                 list(range(23, 24)) + list(range(0, 6))}
    best, best_accuracy, best_total = None, -1, 0
    for label, hours in parts.items():
        total = sum(by_hour[h]['value'] for h in hours)
        solved = sum(by_hour[h]['solved'] for h in hours)
        if total < MIN_ATTEMPTS_FOR_RANKING:
            continue
        accuracy = solved * 100.0 / total
        if accuracy > best_accuracy:
            best, best_accuracy, best_total = label, accuracy, total
    if best is None:
        return ''
    return ('Лучше всего у тебя получается %s — %d%% верных из %d попыток.'
            % (best, round(best_accuracy), best_total))


def source_split(user, period='all', now=None):
    """Откуда задачи: домашки / каталог / контрольные / игра."""
    from .models import LearningEvent

    start, _ = period_bounds(period, now)
    rows = LearningEvent.objects.filter(
        user=user, event_type__in=('solved', 'failed'))
    if start is not None:
        rows = rows.filter(created_at__gte=start)
    rows = (rows.values('source')
            .annotate(attempted=Count('pk'),
                      solved=Count('pk', filter=Q(event_type='solved'))))
    labels = {'homework': 'Домашки', 'catalog': 'Каталог',
              'exam': 'Контрольные', 'game': 'Игра'}
    by_source = {r['source']: r for r in rows}
    return [{'source': key, 'label': label,
             'attempted': by_source.get(key, {}).get('attempted', 0),
             'solved': by_source.get(key, {}).get('solved', 0)}
            for key, label in labels.items()]


def answer_ring(user, period='month', now=None):
    """Кольцо верно / неверно / пропущено."""
    counts = _problem_events(user, period, now).aggregate(
        solved=Count('pk', filter=Q(event_type='solved')),
        failed=Count('pk', filter=Q(event_type='failed')),
        skipped=Count('pk', filter=Q(event_type='skipped')))
    return [
        {'label': 'Верно', 'value': counts['solved'] or 0, 'key': 'solved'},
        {'label': 'Неверно', 'value': counts['failed'] or 0, 'key': 'failed'},
        {'label': 'Пропущено', 'value': counts['skipped'] or 0,
         'key': 'skipped'},
    ]


# ===========================================================================
# Игра — ОТДЕЛЬНО от учебной статистики
# ===========================================================================

def game_stats(user, period='all', now=None):
    """Econ Rush. Своей функцией и своим блоком на экране — намеренно.

    Смешивать результат «Пули» с результатом по домашке нельзя: в игре
    успех это скорость узнавания, в домашке — правильность решения. Одна
    шкала на двоих обесценила бы обе.
    """
    from .models import LearningEvent

    start, _ = period_bounds(period, now)
    rows = LearningEvent.objects.filter(user=user, source='game')
    if start is not None:
        rows = rows.filter(created_at__gte=start)

    counts = rows.aggregate(
        solved=Count('pk', filter=Q(event_type='solved')),
        failed=Count('pk', filter=Q(event_type='failed')))
    solved = counts['solved'] or 0
    failed = counts['failed'] or 0
    attempted = solved + failed

    by_mode = {}
    for row in rows.values('payload'):
        mode = (row['payload'] or {}).get('mode')
        if mode:
            by_mode[mode] = by_mode.get(mode, 0) + 1

    return {
        'attempted': attempted,
        'solved': solved,
        'accuracy': round(solved * 100.0 / attempted) if attempted else None,
        'by_mode': by_mode,
        'has_data': attempted > 0,
    }


# ===========================================================================
# Сборка всего экрана + кэш
# ===========================================================================

def full_stats(user, period='month', now=None, use_cache=True):
    """Всё, что нужно экрану статистики ученика, одним словарём.

    Кэш на 5 минут по ключу (пользователь, период): страница собирается из
    десятка запросов, а цифры за месяц от повторного взгляда не меняются.
    """
    key = 'stats_full_%s_%s' % (user.pk, period)
    if use_cache:
        cached = cache.get(key)
        if cached is not None:
            return cached

    from .gamification import level_progress_percent, xp_to_next_level
    from .models import StudentProgressProfile

    profile, _ = StudentProgressProfile.objects.get_or_create(user=user)
    remaining, next_threshold = xp_to_next_level(profile.xp_total)
    by_hour = activity_by_hour(user, period, now)
    # Разбивка по темам за всё время — считаем ОДИН раз на три блока.
    all_topics = topic_breakdown(user, 'all', now)

    data = {
        'period': period,
        'periods': PERIODS,
        'profile': {
            'level': profile.level,
            'xp': profile.xp_total,
            'xp_to_next': remaining,
            'next_threshold': next_threshold,
            'level_percent': level_progress_percent(profile.xp_total),
            'streak': profile.current_streak,
            'longest_streak': profile.longest_streak,
            'freezes': profile.freezes_available,
            'weekly_goal': profile.weekly_goal,
        },
        'weekly': weekly_progress(user, profile, now),
        'overview': overview(user, period, now),
        'topics': topic_breakdown(user, period, now),
        'ranking': strongest_weakest(user, 'all', now, rows=all_topics),
        'radar': section_radar(user, 'all', now, rows=all_topics),
        'ring': answer_ring(user, period, now),
        'hardest': hardest_problems(user, 'all', now),
        'by_weekday': activity_by_weekday(user, period, now),
        'by_hour': by_hour,
        'time_hint': best_time_hint(by_hour),
        'sources': source_split(user, period, now),
        'game': game_stats(user, 'all', now),
        # Теплокарта и линия уровня всегда за ВСЮ историю, а не за период:
        # календарь за один день и «рост уровня» из одной точки бессмысленны.
        'calendar': activity_calendar(user, 365, now),
        'level_history': level_history(user, now),
    }
    if use_cache:
        cache.set(key, data, CACHE_SECONDS)
    return data


def weekly_progress(user, profile=None, now=None):
    """Кольцо недельной цели: сколько решено на этой неделе из цели."""
    from .models import DailySummary, StudentProgressProfile

    profile = profile or StudentProgressProfile.objects.filter(
        user=user).first()
    goal = profile.weekly_goal if profile else 20
    today = timezone.localtime(now or timezone.now()).date()
    monday = today - timedelta(days=today.weekday())
    solved = DailySummary.objects.filter(
        user=user, date__gte=monday, date__lte=today).aggregate(
        total=Sum('problems_solved'))['total'] or 0
    return {
        'goal': goal,
        'done': solved,
        'percent': min(100, int(round(solved * 100.0 / goal))) if goal else 0,
        'reached': solved >= goal,
    }


def invalidate(user):
    """Сбросить кэш статистики пользователя (после сдачи работы, проверки)."""
    for period, _ in PERIODS:
        cache.delete('stats_full_%s_%s' % (user.pk, period))


# ===========================================================================
# Группа глазами репетитора — БЕЗ геймификации
# ===========================================================================

def group_table(group, period='month', now=None):
    """Таблица учеников группы: решено, доля, сдано, средний балл, активность.

    Ни опыта, ни уровней, ни серий: репетитору нужна диагностика, а не
    мотивационная механика ученика. Смотреть на чужой уровень — праздное
    занятие; смотреть, кто провалил тему, — работа.
    """
    from .models import Submission, TeacherFeedback

    start, _ = period_bounds(period, now)
    students = list(group.students.all().order_by('last_name', 'username'))
    if not students:
        return []

    events = _problem_events_for(students, start).values('user_id').annotate(
        solved=Count('pk', filter=Q(event_type='solved')),
        attempted=Count('pk', filter=Q(event_type__in=('solved', 'failed'))),
        last=Count('pk'))
    by_user = {r['user_id']: r for r in events}

    submissions = (Submission.objects
                   .filter(assignment__group=group, student__in=students)
                   .values('student_id')
                   .annotate(
                       submitted=Count('pk', filter=Q(
                           status__in=('submitted', 'reviewed'))),
                       pending=Count('pk', filter=Q(status='submitted'))))
    subs_by_user = {r['student_id']: r for r in submissions}

    scores = (TeacherFeedback.objects
              .filter(submission__assignment__group=group,
                      submission__student__in=students,
                      score__isnull=False)
              .values('submission__student_id')
              .annotate(avg=Avg('score')))
    score_by_user = {r['submission__student_id']: r['avg'] for r in scores}

    last_seen = _last_activity(students)

    rows = []
    for student in students:
        stats = by_user.get(student.pk, {})
        attempted = stats.get('attempted', 0)
        solved = stats.get('solved', 0)
        subs = subs_by_user.get(student.pk, {})
        rows.append({
            'student': student,
            'solved': solved,
            'attempted': attempted,
            'accuracy': round(solved * 100.0 / attempted) if attempted else None,
            'submitted': subs.get('submitted', 0),
            'pending': subs.get('pending', 0),
            'avg_score': (round(float(score_by_user[student.pk]), 2)
                          if student.pk in score_by_user else None),
            'last_active': last_seen.get(student.pk),
        })
    return rows


def _problem_events_for(students, start):
    from .models import LearningEvent

    queryset = LearningEvent.objects.filter(
        user__in=students).exclude(source='game').filter(
        Q(catalog_problem__isnull=False) | Q(custom_problem__isnull=False))
    if start is not None:
        queryset = queryset.filter(created_at__gte=start)
    return queryset


def _last_activity(students):
    from .models import LearningEvent

    rows = (LearningEvent.objects.filter(user__in=students)
            .values('user_id')
            .annotate(last=Max('created_at')))
    return {r['user_id']: r['last'] for r in rows}


def group_topic_matrix(group, period='all', now=None, limit_topics=12):
    """Тепловая матрица «ученики × темы»: цвет — доля верных.

    Самый полезный экран репетитора: сразу видно, какую тему провалила вся
    группа (столбец красный целиком), а какую — один человек (одна клетка).
    Темы отобраны по числу попыток в группе: показывать все 849 бессмысленно.
    """
    start, _ = period_bounds(period, now)
    students = list(group.students.all().order_by('last_name', 'username'))
    if not students:
        return {'students': [], 'topics': [], 'cells': {}, 'columns': []}

    rows = (_problem_events_for(students, start)
            .filter(topic__isnull=False,
                    event_type__in=('solved', 'failed'))
            .values('user_id', 'topic_id', 'topic__name')
            .annotate(attempted=Count('pk'),
                      solved=Count('pk', filter=Q(event_type='solved'))))

    totals = {}
    cells = {}
    for row in rows:
        topic = (row['topic_id'], row['topic__name'])
        bucket = totals.setdefault(topic, {'attempted': 0, 'solved': 0})
        bucket['attempted'] += row['attempted']
        bucket['solved'] += row['solved']
        cells[(row['user_id'], row['topic_id'])] = {
            'attempted': row['attempted'],
            'solved': row['solved'],
            'accuracy': round(row['solved'] * 100.0 / row['attempted']),
        }

    topics = sorted(totals.items(), key=lambda kv: -kv[1]['attempted'])
    topics = topics[:limit_topics]

    columns = [{
        'topic_id': topic_id,
        'name': name,
        'attempted': data['attempted'],
        'accuracy': round(data['solved'] * 100.0 / data['attempted'])
        if data['attempted'] else 0,
    } for (topic_id, name), data in topics]

    matrix = []
    for student in students:
        matrix.append({
            'student': student,
            'cells': [cells.get((student.pk, column['topic_id']))
                      for column in columns],
        })
    return {'students': students, 'columns': columns, 'matrix': matrix}


# Сколько дней сданная работа может ждать проверки, прежде чем это станет
# поводом для плашки. Три дня — рабочая неделя минус выходные: ученик успел
# забыть, что решал, и обратная связь уже почти бесполезна.
STALE_REVIEW_DAYS = 3


def _days_word(number):
    """1 день, 2 дня, 5 дней."""
    if number % 10 == 1 and number % 100 != 11:
        return 'день'
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return 'дня'
    return 'дней'


def needs_attention(group, now=None):
    """Кому нужно внимание: пропал, просел, не сдал, ЖДЁТ ВАШЕЙ ПРОВЕРКИ.

    ⚠️ Четвёртое условие — про САМОГО РЕПЕТИТОРА, а не про ученика.
    Остальные три говорят «ученик не сделал», а это — «вы не сделали»:
    работа сдана и лежит непроверенной дольше трёх дней. Формулировка
    поэтому тоже про него: «работа Петра ждёт вашей проверки 4 дня».
    Прятать такое в общий список «ученик виноват» было бы нечестно.
    """
    from .models import Assignment, Submission

    now = now or timezone.now()
    students = list(group.students.all())
    if not students:
        return []

    quiet_threshold = now - timedelta(days=14)
    last_seen = _last_activity(students)

    month_now = {r['student'].pk: r for r in group_table(group, 'month', now)}
    previous = {r['student'].pk: r for r in
                group_table(group, 'month', now - timedelta(days=30))}

    # Последняя работа, СРОК КОТОРОЙ УЖЕ ПРОШЁЛ. Без этого условия экран
    # ругался на всю группу за контрольную, которую ещё нельзя было писать:
    # «не сдал» про работу с открытым сроком — не сигнал, а ложная тревога,
    # а от ложных тревог список «требуют внимания» перестают читать.
    last_work = (Assignment.objects
                 .filter(group=group, deadline__isnull=False,
                         deadline__lt=now)
                 .order_by('-deadline').first())
    # Сданное, но не проверенное дольше трёх дней — это к репетитору.
    stale_threshold = now - timedelta(days=STALE_REVIEW_DAYS)
    stale = {}
    for row in (Submission.objects
                .filter(assignment__group=group, status='submitted',
                        submitted_at__isnull=False,
                        submitted_at__lt=stale_threshold)
                .values('student_id')
                .annotate(oldest=Min('submitted_at'))):
        stale[row['student_id']] = row['oldest']

    missed = set()
    if last_work is not None:
        done = set(Submission.objects.filter(
            assignment=last_work, status__in=('submitted', 'reviewed'))
            .values_list('student_id', flat=True))
        missed = {s.pk for s in students if s.pk not in done}

    flagged = []
    for student in students:
        reasons = []
        seen = last_seen.get(student.pk)
        if seen is None or seen < quiet_threshold:
            reasons.append('не заходил больше двух недель')
        current = month_now.get(student.pk, {}).get('accuracy')
        before = previous.get(student.pk, {}).get('accuracy')
        if current is not None and before is not None and current + 10 <= before:
            reasons.append('доля верных упала с %d%% до %d%%'
                           % (before, current))
        if student.pk in missed and last_work is not None:
            reasons.append('не сдал «%s»' % last_work.name)
        waiting = stale.get(student.pk)
        if waiting is not None:
            days = max(1, (now - waiting).days)
            # Имя в причину не вставляем: список и так сгруппирован по
            # ученику, а склонять фамилию в родительный падеж программно
            # нельзя — «работа Пётр Иванов» читается как ошибка.
            reasons.append('работа ждёт вашей проверки %d %s'
                           % (days, _days_word(days)))
        if reasons:
            flagged.append({'student': student, 'reasons': reasons,
                            'last_active': seen})
    return flagged
