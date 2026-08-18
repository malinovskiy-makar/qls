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

from . import timefmt

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
        failed=Count('pk', filter=Q(event_type='failed')))
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
        # ⚠️ НЕ `Sum('time_spent_seconds')`: боевой код это поле не пишет,
        # и карточка «время» показывала «0 мин» при десятках попыток.
        # Считаем по расстоянию между событиями — см. `minutes_on_site`.
        'minutes': minutes_on_site(user, period, now),
        'xp': xp,
    }


# Пауза, после которой считаем, что человек ушёл с сайта. Меньше — и
# «подумал над задачей» рвало бы сессию; больше — и одна забытая вкладка
# давала бы сутки на сайте.
SESSION_GAP_MINUTES = 30

# ⚠️ ХВОСТ СЕССИИ. У ПОСЛЕДНЕГО события сессии нет следующего, поэтому
# измерить его длительность нечем — и до сессии 10 оно весило ровно ноль.
# Гипотеза владельца подтвердилась замером (`test_minutes_on_site`):
# десять заходов по одной задаче давали 0 минут, а три отдельных захода,
# добавленные к плотной сессии, не добавляли к счётчику НИЧЕГО.
#
# Начисляем фиксированный хвост КАЖДОЙ сессии, а не только одиночным
# событиям. Это одно правило вместо двух: одиночный заход — просто сессия
# из одного события, и никакого особого случая для него не нужно. Заодно
# чинится незамеченная половина дефекта — у плотной сессии последнее
# действие тоже занимало время и тоже пропадало.
#
# Два, а не пять: число видят и ученик, и родитель, и завысить его хуже,
# чем занизить. Двух минут хватает на «открыл задачу и прочитал условие»,
# и это заведомо нижняя оценка, а не щедрая.
SESSION_TAIL_MINUTES = 2


def minutes_on_site(user, period='month', now=None):
    """Сколько минут человек провёл на сайте за период.

    ⚠️ СЧИТАЕМ ПО РАССТОЯНИЮ МЕЖДУ СОБЫТИЯМИ, А НЕ ПО СЧЁТЧИКУ. Поле
    `LearningEvent.time_spent_seconds` существует и агрегировалось, но
    заполняли его только игра и демо-скрипт: ни домашка
    (`student/views.py::_log_submission_event`), ни контрольная
    (`exam_engine`), ни открытие задачи в каталоге секунд не передают.
    Отсюда и «0 мин при десятках попыток», с которого началась фаза 7.2.

    Чинить запись в трёх боевых точках значило бы завести на клиенте три
    секундомера и доверять им. Расстояние между событиями честнее: оно
    считается по данным, которые уже есть, работает задним числом и не
    зависит от того, закрыл ли ученик вкладку.

    Правило: события одного человека выстраиваются по времени; промежуток
    короче `SESSION_GAP_MINUTES` идёт в зачёт, длиннее — считается уходом.
    Каждой сессии добавляется `SESSION_TAIL_MINUTES` за последнее событие:
    его длительность измерить нечем, но нулём она точно не была.

    ⚠️ РАНЬШЕ ОДИНОКОЕ СОБЫТИЕ ДАВАЛО НОЛЬ, и это было не «честно», а
    неверно: ученик, решающий по задаче за заход, месяцами видел ноль минут.
    Замер (`test_minutes_on_site`): десять заходов = 0 минут, а три захода
    сверх плотной сессии не добавляли ничего. Починено в сессии 10 хвостом
    сессии — см. комментарий у константы.

    ⚠️ ИГРА ВХОДИТ. Это время НА САЙТЕ, а не «учебное время»: тот же
    принцип, что у «Последней активности». В «Решено» и «Долю верных» игра
    по-прежнему не входит.

    ⚠️ Единственное место модуля, где мы перебираем события в питоне.
    Сессии нельзя собрать одним `aggregate`, а тянем мы только один
    проиндексированный столбец.
    """
    stamps = _site_stamps(user, period, now)

    if not stamps:
        # Ни одного события — честный ноль. Хвост начисляется сессии, а
        # сессии тут нет ни одной; иначе «не заходил» весило бы две минуты.
        return 0

    total = sum((piece for _moment, piece in _minute_slices(stamps)),
                timedelta())
    return int(round(total.total_seconds() / 60))


def _minute_slices(stamps):
    """Минуты на сайте, разложенные по МОМЕНТАМ, когда они прошли.

    Возвращает `[(местное время начала куска, длительность)]`.

    ⚠️ ЗАЧЕМ РАЗЛОЖЕНИЕ. «Минут на сайте» и графики «Когда занимаешься»
    обязаны считаться ОДНИМ правилом (ревью 15.08, п. 21). До этого они
    жили по разным: карточка — по расстоянию между событиями, левый график
    — по счётчику `DailySummary.problems_attempted`, правый — по событиям
    вида «решено / неверно». Отсюда наблюдение владельца «левый показывает
    10, правый пуст»: у репетитора десять событий каталога вида «открыл»,
    в сводке они посчитаны попытками, а в правый график не попадают вовсе.
    Два числа об одном и том же, посчитанные тремя способами, — это не
    графики, это три разных вопроса под одним заголовком.

    Правило то же, что у `minutes_on_site`: промежуток короче
    `SESSION_GAP_MINUTES` идёт в зачёт, длиннее — уход; каждой сессии
    добавляется `SESSION_TAIL_MINUTES` за последнее событие.

    ⚠️ КУСОК НЕ ПЕРЕСЕКАЕТ ГРАНИЦУ ЧАСА. Двадцать пять минут, начатые в
    20:50, — это десять минут восьмого часа вечера и пятнадцать девятого;
    записать их целиком в 20 часов значило бы нарисовать на графике час,
    в котором человека уже не было. Заодно это чинит и полночь: кусок
    сам разложится по двум дням недели.
    """
    if not stamps:
        return []
    gap = timedelta(minutes=SESSION_GAP_MINUTES)
    tail = timedelta(minutes=SESSION_TAIL_MINUTES)
    rough = []
    for index, moment in enumerate(stamps):
        following = stamps[index + 1] if index + 1 < len(stamps) else None
        if following is not None and following - moment <= gap:
            rough.append((moment, following - moment))
        else:
            # Событие последнее в своей сессии: дальше либо разрыв, либо
            # конец списка. Хвост даётся именно ему.
            rough.append((moment, tail))
    pieces = []
    for moment, length in rough:
        pieces.extend(_cut_by_hour(moment, length))
    return pieces


def _cut_by_hour(moment, length):
    """Кусок времени → куски, не пересекающие границу часа (в местном поясе)."""
    local = timezone.localtime(moment)
    out = []
    while length > timedelta():
        edge = (local + timedelta(hours=1)).replace(minute=0, second=0,
                                                    microsecond=0)
        step = min(length, edge - local)
        out.append((local, step))
        local, length = edge, length - step
    return out


MINUTE_FORMS = ('минута', 'минуты', 'минут')


def minutes_text(value):
    """«1 минута», «3 минуты», «15 минут» — для подписи на графике.

    ⚠️ СКЛОНЕНИЕ СЧИТАЕТ ПИТОН, А НЕ БРАУЗЕР. Готовая строка уезжает во
    всплывашку графика: правило трёх форм существует в проекте ровно один
    раз (`templatetags.ru.pick`), и заводить его вторую копию на
    JavaScript ради одной подписи значит гарантированно их развести.
    """
    from problems.templatetags.ru import pick

    return '%d %s' % (value, pick(value, *MINUTE_FORMS))


def minutes_by_weekday(user, period='month', now=None):
    """Минуты на сайте по дням недели (0 — понедельник)."""
    names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    buckets = [timedelta()] * 7
    for local, step in _minute_slices(_site_stamps(user, period, now)):
        buckets[local.weekday()] += step
    out = []
    for i in range(7):
        value = int(round(buckets[i].total_seconds() / 60))
        out.append({'label': names[i], 'value': value,
                    'text': minutes_text(value)})
    return out


def minutes_by_hour(user, period='month', now=None):
    """Минуты на сайте по часам суток."""
    buckets = [timedelta()] * 24
    out = []
    for local, step in _minute_slices(_site_stamps(user, period, now)):
        buckets[local.hour] += step
    for hour in range(24):
        value = int(round(buckets[hour].total_seconds() / 60))
        out.append({'hour': hour, 'value': value,
                    'text': minutes_text(value)})
    return out


def _site_stamps(user, period, now=None):
    """Отметки времени всех событий человека за период, по возрастанию.

    ⚠️ ВСЕ события, а не только «решено / неверно», и ВКЛЮЧАЯ игру — это
    время НА САЙТЕ. Тот же набор, что у `minutes_on_site`; расходиться им
    нельзя, иначе сумма по графику не сойдётся с карточкой.
    """
    from .models import LearningEvent

    start, end = period_bounds(period, now)
    queryset = LearningEvent.objects.filter(user=user)
    if start is not None:
        queryset = queryset.filter(created_at__gte=start, created_at__lt=end)
    return list(queryset.order_by('created_at')
                .values_list('created_at', flat=True))


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

# ⚠️ МЕТКА ТЕМЫ СЧИТАЕТСЯ ОДНОЙ ФУНКЦИЕЙ ПО ЯВНОМУ ПРАВИЛУ (ревью 17.08,
# п. 5.2). До этой правки она бралась из `StudentTopicProgress.mastery_level`
# — счётчика, который живёт по своим правилам и обновляется своим путём.
# Рядом на той же карточке стояла доля верных, посчитанная за выбранный
# период, и они противоречили друг другу: «Международная торговля —
# уверенно — 40%» соседствовала с «Инфляция — разобрался — 95%», а две темы
# с ОДИНАКОВЫМИ данными (100%, 2 из 2) получали разные метки.
#
# Порог попыток — тот же, что у блока «Сильные и слабые темы»
# (`MIN_ATTEMPTS_FOR_RANKING`): два разных порога «когда данным можно
# верить» на одном экране разъехались бы неизбежно.
TOPIC_LABELS = (
    (85, 'master', 'мастер'),
    (60, 'good', 'разобрался'),
    (0, 'weak', 'стоит подтянуть'),
)


def topic_label(attempted, accuracy):
    """(ключ, слово) для метки темы. Мало попыток — так и говорим."""
    if attempted < MIN_ATTEMPTS_FOR_RANKING:
        return 'thin', 'мало данных'
    for edge, key, word in TOPIC_LABELS:
        if accuracy >= edge:
            return key, word
    return 'weak', 'стоит подтянуть'


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
        # Метка считается ПО ТЕМ ЖЕ ЧИСЛАМ, что стоят рядом на карточке.
        result[-1]['label_kind'], result[-1]['label'] = topic_label(
            attempted, result[-1]['accuracy'])
    return result


# Сколько тем показывать в каждой половине блока «Сильные и слабые темы».
# ⚠️ Было три, стало ПЯТЬ (сессия 9, фаза 3): по три темы из двадцати трёх
# нельзя понять, где ученик просел, — это подпись, а не диагностика.
RANKING_LIMIT = 5


def strongest_weakest(user, period='all', now=None, limit=RANKING_LIMIT,
                      rows=None):
    """Пять сильных и пять слабых тем.

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
    # ⚠️ ПОЛОВИНЫ НЕ ПЕРЕСЕКАЮТСЯ. Пока показывали по три темы, это не
    # всплывало; на пяти (сессия 9, фаза 3) тема с восемью тем в списке
    # попадала И в «сильные», И в «слабые» — сразу и похвала, и упрёк за
    # одно и то же. Слабые берём из ОСТАТКА после сильных.
    # ⚠️ ПОЛОВИНЫ ДЕЛЯТСЯ ПОПОЛАМ, А НЕ «СНАЧАЛА ПЯТЬ СИЛЬНЫХ» (ревью
    # 15.08, п. 11). Прежнее правило отдавало сильным первые пять, а
    # слабым — что осталось: на двух темах ОБЕ уезжали в «сильные», и тема
    # с долей верных 25% стояла под заголовком «Сильные». Это не «мало
    # данных», это неправда. Берём поровну с двух концов; середина не
    # показывается нигде — она и не сильная, и не слабая.
    # ⚠️ КОЛОНКИ ЗАПОЛНЯЮТСЯ ДО ПЯТИ, КОГДА ТЕМ ХВАТАЕТ (ревью 17.08,
    # п. 5.3). Прежнее `len // 2` при девяти темах давало 4 и 4, а десятую
    # строку не показывало нигде: на экране стояло по четыре темы вместо
    # пяти. Делим с округлением вверх в пользу сильных; пересечения нет по
    # построению — слабые берутся из остатка.
    total = len(by_accuracy)
    strong_count = min(limit, (total + 1) // 2)
    weak_count = min(limit, total - strong_count)
    strong = by_accuracy[:strong_count]
    weak = list(reversed(by_accuracy[total - weak_count:])) if weak_count else []
    # ⚠️ БЛОК НЕ ИСЧЕЗАЕТ, КОГДА ДАННЫХ МАЛО (ревью 15.08, п. 11). Раньше
    # он показывался только при `enough_data`, и на «Месяце» его не было
    # вовсе, а на «Всё время» он появлялся: владелец решил, что блок
    # пропал совсем. Исчезающий блок — это не «нет данных», это «экран
    # каждый раз другой». Объяснение собираем ЗДЕСЬ, чтобы три экрана
    # говорили одними словами.
    ranked = len(rows)
    if ranked == 0:
        note = ('Ни одна тема пока не набрала %d попыток — сравнивать не '
                'с чем.' % MIN_ATTEMPTS_FOR_RANKING)
    elif ranked == 1:
        note = ('Порог в %d попыток набрала пока одна тема — чтобы делить '
                'на сильные и слабые, нужно хотя бы две.'
                % MIN_ATTEMPTS_FOR_RANKING)
    else:
        note = ''
    # Подсказка про период — только когда период вообще ограничен: на
    # «Всё время» советовать «выберите шире» было бы издевательством.
    hint = ('Попробуйте период шире — например, «Всё время».'
            if note and period != 'all' else '')
    return {
        'strong': strong,
        'weak': weak,
        'enough_data': ranked >= 2,
        'ranked': ranked,
        'note': note,
        'hint': hint,
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

# ⚠️ ЛЕГЕНДА МЕРЯЕТ МИНУТЫ, А НЕ «МЕНЬШЕ — БОЛЬШЕ» (ревью 16.08, ф. 4).
# Прежние пять оттенков считались ДОЛЕЙ ОТ ЛИЧНОГО ПИКА: у человека с
# одним решённым днём этот день был «самым тёмным», у человека с сорока —
# тем же цветом красился день на сорок задач. Одинаковый цвет означал
# разное, а легенда честно не могла сказать, сколько это.
MINUTE_STEPS = (15, 40, 90)
MINUTE_LEGEND = ('0', 'до 15', 'до 40', 'до 90', 'больше')

# Слово «день» для строки «12 из 31».
DAY_FORMS = ('день', 'дня', 'дней')


def minutes_level(minutes):
    """Оттенок клетки по минутам. Границы одни на всех, они же в легенде."""
    if not minutes:
        return 0
    for index, edge in enumerate(MINUTE_STEPS):
        if minutes <= edge:
            return index + 1
    return len(MINUTE_STEPS) + 1


def minutes_by_day(user, period='month', now=None):
    """Минуты на сайте по календарным дням.

    ⚠️ ТЕМ ЖЕ ПРАВИЛОМ, ЧТО КАРТОЧКА «МИНУТ НА САЙТЕ» (`_minute_slices`).
    Сетка активности и число в карточке обязаны складываться в одно и то
    же: рядом на одном экране два числа об одном, посчитанные по-разному,
    — это ровно тот дефект, который чинили в графиках «Когда занимаешься».
    """
    buckets = {}
    for local, step in _minute_slices(_site_stamps(user, period, now)):
        key = local.date()
        buckets[key] = buckets.get(key, timedelta()) + step
    return {day: int(round(value.total_seconds() / 60))
            for day, value in buckets.items()}


def _site_events(user, period, now=None):
    """События периода одним заходом: (когда, что, откуда).

    ⚠️ ОДИН ЗАПРОС НА ВЕСЬ БЛОК. Сетке нужны и минуты (по отметкам
    времени), и число решённых задач в каждый день. Двумя запросами это
    выходило на единицу больше потолка страницы — а потолок и заведён,
    чтобы новый блок не проносил с собой лишние походы в базу.
    """
    from .models import LearningEvent

    start, end = period_bounds(period, now)
    queryset = LearningEvent.objects.filter(user=user)
    if start is not None:
        queryset = queryset.filter(created_at__gte=start, created_at__lt=end)
    return list(queryset.order_by('created_at')
                .values_list('created_at', 'event_type', 'source'))


def activity_grid(user, period='month', now=None):
    """Сетка дней «Активность на сайте» — ОДИН блок вместо трёх.

    ⚠️ СЕТКА ПОКРЫВАЕТ РОВНО ПЕРИОД, ВЫБРАННЫЙ НАВЕРХУ СТРАНИЦЫ. Раньше
    календарь всегда показывал год, а переключатель периода стоял рядом и
    ни на что не влиял: человек выбирал «неделю», а видел двенадцать
    месяцев. Заодно это условие делает сумму по сетке равной карточке
    «Минут на сайте» — иначе на одном экране стояли бы два разных итога.

    Возвращает `mode`:
      * `days` — сетка по дням с числом месяца в клетке (день/неделя/месяц);
      * `year` — сжатая сетка по неделям без чисел («всё время»): в год
        365 клеток, и число месяца в каждой прочесть невозможно.
    """
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    rows = _site_events(user, period, now)

    minutes = {}
    for local, step in _minute_slices([row[0] for row in rows]):
        key = local.date()
        minutes[key] = minutes.get(key, timedelta()) + step
    minutes = {day: int(round(value.total_seconds() / 60))
               for day, value in minutes.items()}

    # «Решено» здесь считается ТЕМ ЖЕ набором, что карточка «Решено»:
    # игра в него не входит (у неё своя шкала), в минуты — входит.
    solved = {}
    for created, kind, source in rows:
        if kind == 'solved' and source != 'game':
            day = timezone.localtime(created).date()
            solved[day] = solved.get(day, 0) + 1

    # ⚠️ ГРАНИЦА ПЕРИОДА — ТА ЖЕ, ЧТО У ВСЕХ ОСТАЛЬНЫХ ЧИСЕЛ СТРАНИЦЫ
    # (`period_bounds`). Считать её здесь своим способом («последние 30
    # дней от сегодняшней даты») уже пробовали: сетка показала 381 минуту
    # там, где подпись под ней и карточка «Минут на сайте» показывали 419.
    # Разошлись на кусок первого дня — событий за 30×24 часа назад, но
    # календарно на день раньше.
    mode = 'days' if PERIOD_DAYS.get(period) else 'year'
    since, _ = period_bounds(period, now)
    start = (timezone.localtime(since).date() if since is not None
             else today - timedelta(days=364))

    # Сетка всегда начинается с понедельника: иначе столбец «Пн» держал бы
    # разные дни недели в разных строках.
    first = start - timedelta(days=start.weekday())
    last = today + timedelta(days=6 - today.weekday())

    cells = []
    day = first
    while day <= last:
        inside = start <= day <= today
        count = minutes.get(day, 0) if inside else 0
        cells.append({
            'date': day,
            'number': day.day,
            'minutes': count,
            'solved': solved.get(day, 0) if inside else 0,
            'level': minutes_level(count),
            'inside': inside,
            'is_today': day == today,
        })
        day += timedelta(days=1)

    inside_cells = [c for c in cells if c['inside']]
    worked = [c for c in inside_cells if c['minutes']]
    # ⚠️ ИТОГ БЕРЁМ У КАРТОЧКИ «МИНУТ НА САЙТЕ», А НЕ СКЛАДЫВАЕМ КЛЕТКИ.
    # Клетка округляется до минуты сама по себе, час на графике — сам по
    # себе, и суммы трёх разложений одного и того же времени расходятся на
    # единицы. Число на экране должно быть ОДНО и то же везде, где оно
    # напечатано; клетки и столбики остаются разрезами, а не источниками
    # итога.
    total = minutes_on_site(user, period, now)
    return {
        'mode': mode,
        'cells': cells,
        # Для годового вида клетки идут по столбцам-неделям: сетка та же,
        # меняется только направление раскладки.
        'weeks': (len(cells) + 6) // 7,
        'start': start,
        'end': today,
        'legend': list(MINUTE_LEGEND),
        'facts': _activity_facts(inside_cells, worked, total, period),
    }


def _activity_facts(cells, worked, total, period='month'):
    """Четыре факта справа от сетки. Считаются по тем же клеткам."""
    from problems.templatetags.ru import pick

    days_total = len(cells)
    # ⚠️ «В средний РАБОЧИЙ день», а не «в средний день»: делить на все дни
    # периода значит мешать отдых с занятиями и называть результат
    # усердием. Ноль рабочих дней — прочерк, а не ноль: делить не на что.
    average = int(round(total / len(worked))) if worked else None
    return [
        {'value': '%d из %d' % (len(worked), days_total),
         'label': 'дней с занятиями'},
        # Подпись НЕ повторяет единицу, которая уже стоит в значении:
        # «418 мин · минут за период» — это дважды одно слово.
        {'value': '%d мин' % total,
         'label': 'всего %s' % PERIOD_WORDS.get(period, 'за период'),
         'minutes': total},
        {'value': ('%d мин' % average) if average is not None else '—',
         'label': 'в средний рабочий день'},
        {'value': '%d %s' % (_best_streak(cells),
                             pick(_best_streak(cells), *DAY_FORMS)),
         'label': 'лучшая серия подряд'},
    ]


def _best_streak(cells):
    """Самая длинная череда дней подряд с занятиями внутри периода."""
    best = run = 0
    for cell in cells:
        run = run + 1 if cell['minutes'] else 0
        best = max(best, run)
    return best


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


# Как назвать время суток. Границы обычные разговорные, а не астрономические.
DAY_PARTS = ((5, 'ночью'), (12, 'утром'), (17, 'днём'), (23, 'вечером'))
PERIOD_WORDS = {'day': 'за день', 'week': 'за неделю', 'month': 'за месяц',
                'all': 'за всё время'}
# Ширина окна, которое ищем: три часа — то, что человек называет «вечером»,
# а не одна точка на графике.
BUSY_WINDOW = 3


def _day_part(hour):
    for edge, name in DAY_PARTS:
        if hour < edge:
            return name
    return 'вечером'


def busy_time_hint(by_hour, period='month', total=None):
    """Подпись под сеткой активности — ПРО МИНУТЫ.

    ⚠️ Здесь стояла подпись про долю верных ответов («91% верных из 22
    попыток»). Она отвечала на другой вопрос, чем весь блок вокруг неё:
    блок называется «Активность на сайте» и меряет время, а подпись под
    ним — точность. Тот же вопрос, что у блока, и та же единица.
    """
    # Итог — тот же, что в карточке и в фактах у сетки (см. `activity_grid`).
    if total is None:
        total = sum(row['value'] for row in by_hour)
    if not total:
        return ('Пока не из чего считать: позанимайся немного, и здесь '
                'появится твоё любимое время.')
    best_start, best_sum = 0, -1
    for start in range(len(by_hour) - BUSY_WINDOW + 1):
        window = sum(by_hour[h]['value']
                     for h in range(start, start + BUSY_WINDOW))
        # ⚠️ ПРИ РАВЕНСТВЕ ОКНО НАЧИНАЕТСЯ С НЕПУСТОГО ЧАСА. Занятия в 19 и
        # 20 дают одинаковую сумму окнам 18–21 и 19–22, и первое победило
        # бы просто потому, что перебор идёт слева: на экране выходило
        # «занимаешься с 18:00», хотя в 18 не было ни минуты.
        better = window > best_sum
        if not better and window == best_sum and window:
            better = (not by_hour[best_start]['value']
                      and by_hour[start]['value'])
        if better:
            best_sum, best_start = window, start
    if not best_sum:
        return ('Пока не из чего считать: позанимайся немного, и здесь '
                'появится твоё любимое время.')
    return ('Чаще всего занимаешься %s, %02d:00–%02d:00 — на это время '
            'пришлось %s из %d %s.'
            % (_day_part(best_start + BUSY_WINDOW // 2), best_start,
               best_start + BUSY_WINDOW, minutes_text(best_sum), total,
               PERIOD_WORDS.get(period, 'за период')))


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


def difficulty_split(user, period='month', now=None):
    """Карта сложности: сколько задач каждого уровня взято и сколько верно.

    ⚠️ ЗАМЕНА КОЛЬЦУ «ОТВЕТЫ ЗА ПЕРИОД» (ревью 16.08, п. 5.3–5.5). Кольцо
    показывало «верно / неверно / пропущено» — то же самое, что карточка
    «Доля верных» двумя блоками выше, только круглое. Здесь вопрос другой
    и на него больше негде ответить: на каком уровне сложности человек
    работает и где начинает спотыкаться.

    Сложность берётся из СНИМКА в событии (`LearningEvent.difficulty`) по
    той же причине, что и тема: правка задачи в каталоге не имеет права
    переписывать прошлое.
    """
    rows = (_problem_events(user, period, now)
            .filter(event_type__in=('solved', 'failed'),
                    difficulty__gte=1, difficulty__lte=5)
            .values('difficulty')
            .annotate(attempted=Count('pk'),
                      solved=Count('pk', filter=Q(event_type='solved'))))
    by_level = {r['difficulty']: r for r in rows}
    out = []
    total = weighted = 0
    for level in range(1, 6):
        row = by_level.get(level, {})
        attempted = row.get('attempted', 0)
        solved = row.get('solved', 0)
        total += attempted
        weighted += attempted * level
        out.append({
            'level': level,
            'attempted': attempted,
            'solved': solved,
            # Доля верных — ноль попыток даёт `None`, а не ноль процентов:
            # «0% на пятом уровне» у того, кто пятый уровень не открывал,
            # читается как провал, которого не было.
            'accuracy': (round(solved * 100 / attempted)
                         if attempted else None),
        })
    average = round(weighted / total, 1) if total else None
    return {'levels': out, 'total': total, 'average': average,
            'average_text': ('средняя %s из 5' % _comma(average)
                             if average is not None else '')}


def _comma(value):
    """Число на экране пишется с запятой — как везде в проекте."""
    return ('%g' % value).replace('.', ',')


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
        'miss_topics': game_miss_topics(rows),
    }


# Сколько тем промахов показывать под блоком игры.
GAME_MISS_TOPICS = 3


def game_miss_topics(rows, limit=GAME_MISS_TOPICS):
    """Темы, в которых чаще всего промахиваешься в игре.

    Воронка «поиграл → пошёл разбираться»: у каждой строки ссылка в
    «Разобрать ошибки» и в каталог по этой теме. Без тем строка бесполезна —
    целиться в «Без темы» нечем, поэтому такие события не показываем
    (то же правило, что у `mistake_topics` в сводке забега).
    """
    top = (rows.filter(event_type__in=('solved', 'failed'),
                       topic__isnull=False)
           .values('topic_id', 'topic__name')
           .annotate(attempted=Count('pk'),
                     failed=Count('pk', filter=Q(event_type='failed')))
           .filter(failed__gt=0)
           .order_by('-failed', 'topic__name')[:limit])
    return [{'topic_id': row['topic_id'], 'name': row['topic__name'],
             'failed': row['failed'], 'attempted': row['attempted']}
            for row in top]


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
    # Разбивка по темам за всё время — считаем ОДИН раз на три блока.
    all_topics = topic_breakdown(user, 'all', now)
    # Минуты по часам нужны и графику, и подписи под сеткой — считаем раз.
    hour_minutes = minutes_by_hour(user, period, now)
    # ⚠️ СЕТКА АКТИВНОСТИ ПОДЧИНЯЕТСЯ ПЕРИОДУ (ревью 16.08, ф. 4): прежний
    # календарь всегда показывал год, а переключатель стоял рядом зря.
    activity = activity_grid(user, period, now)

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
        # ⚠️ КОЛЬЦО «ОТВЕТЫ ЗА ПЕРИОД» УБРАНО (ревью 16.08, п. 5.3): оно
        # повторяло карточку «Доля верных» двумя блоками выше, только
        # круглым. На его месте — карта сложности, вопрос без другого
        # места на экране.
        'difficulty': difficulty_split(user, period, now),
        'hardest': hardest_problems(user, 'all', now),
        # ⚠️ ГРАФИКИ «КОГДА ЗАНИМАЕШЬСЯ» ПОКАЗЫВАЮТ МИНУТЫ, А НЕ ПОПЫТКИ
        # (ревью 15.08, п. 21). Попытка — величина эфемерная: открытая
        # задача каталога и решённая контрольная считались одинаково, а
        # два графика рядом брали её из РАЗНЫХ мест и расходились. Минуты
        # считает то же правило, что карточку «Минут на сайте», поэтому
        # сумма по любому из графиков сходится с ней.
        'by_weekday': minutes_by_weekday(user, period, now),
        'by_hour': hour_minutes,
        # ⚠️ ПОДПИСЬ ПОД БЛОКОМ ГОВОРИТ О ТОМ ЖЕ, О ЧЁМ БЛОК (ревью 16.08,
        # ф. 4). Здесь стояла подпись про долю верных ответов: блок мерит
        # время, а строка под ним — точность, и читались они как одно.
        'time_hint': busy_time_hint(hour_minutes, period,
                                    total=activity['facts'][1]['minutes']),
        'sources': source_split(user, period, now),
        'game': game_stats(user, 'all', now),
        'activity': activity,
        # Линия уровня — по-прежнему за всю историю: «рост» из одной точки
        # бессмыслен.
        'level_history': level_history(user, now),
    }
    if use_cache:
        cache.set(key, data, CACHE_SECONDS)
    return data


def solved_between(user, start, end):
    """Сколько ЗАДАЧ И ТЕСТОВ верно решено за отрезок дней [start, end).

    ⚠️ ИГРА В ЭТОТ СЧЁТ НЕ ВХОДИТ (решение владельца от 17.08). Недельная
    цель — это стимул, а стимул, который закрывается тремя партиями «Пули»
    по минуте, толкает не туда. Правило то же, что у карточки «Решено»:
    событие «решено» по задаче каталога или своей задаче репетитора, без
    источника «игра». В «Лучшем дне» игра, наоборот, ВХОДИТ — это рекорд,
    факт о прошлом, а не приглашение; там правило другое намеренно.

    ⚠️ Считаем ПО ЖУРНАЛУ, а не по `DailySummary.problems_solved`: тот
    счётчик наращивается на каждое событие, включая игровые, и отделить их
    в нём уже нечем.
    """
    return _goal_events(user).filter(
        created_at__date__gte=start, created_at__date__lt=end).count()


def _goal_events(user):
    """Базовая выборка правила недельной цели. ОДНА на все её применения."""
    from .models import LearningEvent

    return (LearningEvent.objects
            .filter(user=user, event_type='solved')
            .exclude(source='game')
            .filter(Q(catalog_problem__isnull=False)
                    | Q(custom_problem__isnull=False)))


def solved_by_day(user):
    """{день: сколько верных} по тому же правилу — одним запросом."""
    rows = (_goal_events(user)
            .values('created_at__date')
            .annotate(total=Count('pk')))
    return {row['created_at__date']: row['total'] for row in rows}


def weekly_progress(user, profile=None, now=None):
    """Недельная цель: сколько верных задач и тестов на этой неделе из цели."""
    from .models import StudentProgressProfile

    profile = profile or StudentProgressProfile.objects.filter(
        user=user).first()
    goal = profile.weekly_goal if profile else 20
    today = timezone.localtime(now or timezone.now()).date()
    monday = today - timedelta(days=today.weekday())
    solved = solved_between(user, monday, today + timedelta(days=1))
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

    # ⚠️ СЧИТАЕМ РАБОТЫ, А НЕ СТРОКИ `Submission` (ревью 17.08, п. 2.1).
    # `Submission` заводится на КАЖДУЮ ЗАДАЧУ, и прежний `Count('pk')` давал
    # «Сдано работ 25» там, где заданий в группе одиннадцать. Единица счёта
    # одна на весь экран — `student_work_counts`.
    from .models import Assignment

    works = Assignment.objects.filter(group=group)
    submitted_by = student_work_counts(works, SUBMITTED_STATUSES)
    pending_by = student_work_counts(works, WAITING_STATUSES)

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
        # ⚠️ ДВА ЧИСЛА ДОЛИ ВЕРНЫХ (фаза 8.8): по всему сайту и по работам
        # этого репетитора. Одно число отвечало на вопрос, которого никто не
        # задавал: репетитору нужно знать, как ученик решает У НЕГО, и
        # отдельно — каков он вообще.
        pair = accuracy_pair(student, tutor=group.teacher)
        rows.append({
            'student': student,
            'solved': solved,
            'attempted': attempted,
            'accuracy_all': pair['all'],
            'accuracy_mine': pair['mine'],
            'level_all': level_of(pair['all']),
            'accuracy': round(solved * 100.0 / attempted) if attempted else None,
            'submitted': submitted_by.get(student.pk, 0),
            'pending': pending_by.get(student.pk, 0),
            'avg_score': (round(float(score_by_user[student.pk]), 2)
                          if student.pk in score_by_user else None),
            'last_active': last_seen.get(student.pk),
            # ⚠️ «Последняя активность» — ЛЮБОЕ решение задачи на сайте,
            # ВКЛЮЧАЯ игру (фаза 8.5): `_last_activity` берёт все события
            # без исключений. Человеческая формулировка — из `timefmt`,
            # второй точки форматирования не заводим.
            'last_active_human': timefmt.human_ago(last_seen.get(student.pk)),
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


def _topic_events_for(students, start):
    """События для ТЕПЛОКАРТЫ — все четыре источника, ВКЛЮЧАЯ игру.

    ⚠️ Отличается от `_problem_events_for` двумя вещами, и обе намеренные:
    игра не исключается, и не требуется ссылка на задачу (у вопроса игры её
    нет — есть тема). Для теплокарты важно, трогал ли ученик тему вообще;
    для «Решено» и долей верных игра по-прежнему не считается.
    """
    from .models import LearningEvent

    queryset = LearningEvent.objects.filter(user__in=students)
    if start is not None:
        queryset = queryset.filter(created_at__gte=start)
    return queryset


def _last_activity(students):
    from .models import LearningEvent

    rows = (LearningEvent.objects.filter(user__in=students)
            .values('user_id')
            .annotate(last=Max('created_at')))
    return {r['user_id']: r['last'] for r in rows}


def group_topic_matrix(group, period='all', now=None, limit_topics=None):
    """Тепловая матрица «ученики × темы»: цвет — доля верных.

    Самый полезный экран репетитора: сразу видно, какую тему провалила вся
    группа (столбец красный целиком), а какую — один человек (одна клетка).

    ⚠️ ПОКАЗЫВАЕМ ВСЕ 21 КАНОНИЧЕСКУЮ ТЕМУ (фаза 8.1), а не двенадцать самых
    трогаемых. Тема без попыток — это ответ на вопрос «что задать дальше»,
    и вырезать её значило прятать именно то, ради чего сюда смотрят.
    Таблица прокручивается внутри `.table-wrap`, вбок страницу не тянет.

    ⚠️ ИГРА ВХОДИТ (фаза 8.6). У вопросов Econ Rush есть привязка к
    каноническим темам (денормализована в `GameQuestion.topics`, покрыто
    7 219 вопросов из 8 782), и `game/views.py` резолвит её в
    `LearningEvent.topic`. В доли верных и в «Решено» игра по-прежнему НЕ
    входит — там другой формат ответа и другая цена ошибки.
    """
    start, _ = period_bounds(period, now)
    students = list(group.students.all().order_by('last_name', 'username'))
    if not students:
        return {'students': [], 'topics': [], 'cells': {}, 'columns': []}

    rows = (_topic_events_for(students, start)
            .filter(topic__isnull=False,
                    event_type__in=('solved', 'failed'))
            .values('user_id', 'topic_id', 'topic__name')
            .annotate(attempted=Count('pk'),
                      solved=Count('pk', filter=Q(event_type='solved'))))

    totals = {}
    cells = {}
    # ⚠️ ПО СКОЛЬКИМ УЧЕНИКАМ ПОСЧИТАНА КОЛОНКА (обзор 13.08, п. 16). Строка
    # «по группе» средневзвешенная, и 100% там появляется даже когда у двоих
    # из троих прочерк — формально верно, а читается как «вся группа освоила
    # тему». Число попыток этого не объясняет: важно, сколько ЧЕЛОВЕК вообще
    # трогали тему. Одна строка запроса = одна пара (ученик, тема), поэтому
    # людей достаточно сосчитать здесь же.
    covered = {}
    for row in rows:
        topic = (row['topic_id'], row['topic__name'])
        bucket = totals.setdefault(topic, {'attempted': 0, 'solved': 0})
        bucket['attempted'] += row['attempted']
        bucket['solved'] += row['solved']
        covered[row['topic_id']] = covered.get(row['topic_id'], 0) + 1
        cells[(row['user_id'], row['topic_id'])] = {
            'attempted': row['attempted'],
            'solved': row['solved'],
            'accuracy': round(row['solved'] * 100.0 / row['attempted']),
        }

    # Колонки — ВСЕ канонические темы в каноническом порядке, а не только
    # те, где что-то происходило. Порядок один и тот же на всех экранах,
    # поэтому колонка не «переезжает» между заходами.
    #
    # ⚠️ НЕКАНОНИЧЕСКИЕ ТЕМЫ С ДАННЫМИ ДОБАВЛЯЮТСЯ В КОНЕЦ. В базе тем сильно
    # больше двадцати одной (канон — это верхний уровень), и у части задач
    # стоит тема вне канона. Показать только канон значило бы СПРЯТАТЬ
    # настоящие попытки ученика — а «21 тема всегда» просили ради обратного:
    # чтобы ничего не пропадало.
    columns = []
    seen = set()
    for topic in canonical_topics():
        data = totals.get((topic.pk, topic.name), {'attempted': 0,
                                                   'solved': 0})
        seen.add(topic.pk)
        columns.append({
            'topic_id': topic.pk,
            'name': topic.name,
            'attempted': data['attempted'],
            'covered': covered.get(topic.pk, 0),
            'students': len(students),
            'accuracy': (round(data['solved'] * 100.0 / data['attempted'])
                         if data['attempted'] else None),
            'short': _matrix_label(topic.name),
        })
    extra = [((topic_id, name), data)
             for (topic_id, name), data in totals.items()
             if topic_id not in seen]
    for (topic_id, name), data in sorted(extra, key=lambda kv: -kv[1]['attempted']):
        columns.append({
            'topic_id': topic_id,
            'name': name,
            'attempted': data['attempted'],
            'covered': covered.get(topic_id, 0),
            'students': len(students),
            'accuracy': (round(data['solved'] * 100.0 / data['attempted'])
                         if data['attempted'] else None),
            'short': _matrix_label(name),
        })
    if limit_topics:
        columns = columns[:limit_topics]

    matrix = []
    for student in students:
        matrix.append({
            'student': student,
            'cells': [cells.get((student.pk, column['topic_id']))
                      for column in columns],
        })
    return {'students': students, 'columns': columns, 'matrix': matrix}


# ⚠️ ДЛИНА ПОВЁРНУТОЙ ПОДПИСИ ЗАДАЁТ ВЫСОТУ ВСЕГО БЛОКА (ревью 17.08,
# п. 6.4). Заголовки матрицы стоят вертикально, и самая длинная из двадцати
# трёх решает, насколько высокой будет шапка. Полное название лежит в
# подсказке — она и есть ответ на «какая именно тема».
#
# ⚠️ ЧИТАЕМОСТЬ ПОДПИСЕЙ ВАЖНЕЕ ВЫСОТЫ БЛОКА (решение владельца 17.08).
# Прежние четырнадцать держали шапку низкой, но 23 темы переставали
# различаться с первого взгляда: колонки назывались «Теория…»,
# «Введение в…», «Спрос и…». Матрица — карта пробелов группы, её читают
# взглядом по колонкам, и неразличимые колонки обесценивают блок целиком.
#
# Двадцать два — по замеру: подпись просит около 7,6 px на символ, значит
# потолок высоты шапки 170 px (стоит в `_stats_style.html`, замерено, а не
# на глаз). При этой длине «Теория потребителя…» и «Теория фирмы:…»
# отличаются, а обрезка по границе слова с многоточием остаётся.
MATRIX_LABEL_LIMIT = 22


def _matrix_label(name):
    """Короткая подпись колонки: по границе слова, всегда с многоточием."""
    from .text_clean import shorten

    return shorten(name, MATRIX_LABEL_LIMIT)


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


SUBMITTED_STATUSES = ('submitted', 'reviewed')
WAITING_STATUSES = ('submitted',)


def student_work_counts(assignments, statuses=WAITING_STATUSES):
    """{номер ученика: сколько его РАБОТ в этих состояниях}.

    ⚠️ ЕДИНИЦА СЧЁТА — ПАРА (УЧЕНИК, РАБОТА), и это ЕДИНСТВЕННОЕ место, где
    она определена (ревью 17.08, п. 2.1). Таблица «Ученики» считала строки
    `Submission`, а `Submission` заводится на КАЖДУЮ ЗАДАЧУ: на одном экране
    стояло «Сдано работ 25 (7 ждёт)» у вкладки «Обзор» и «3 работы ждут
    проверки» у вкладки «Задания» — при одиннадцати заданиях в группе.
    Считались разные вещи одним словом «работа».

    `works_waiting` — сумма по этому же счёту, поэтому вкладка, кружок и
    колонка сходятся ПО ПОСТРОЕНИЮ, а не по совпадению. Держится тестом.
    """
    from .models import Submission

    # ⚠️ `order_by()` ОБЯЗАТЕЛЕН, ИНАЧЕ `distinct()` НЕ РАБОТАЕТ. У
    # `Submission` в `Meta.ordering` стоит `-submitted_at`, и Django
    # ДОБАВЛЯЕТ поле сортировки в сам SELECT: получается
    # `SELECT DISTINCT assignment_id, student_id, submitted_at`, то есть
    # строки различаются ещё и МОМЕНТОМ СДАЧИ. Один ученик, сдавший работу
    # из четырёх задач, давал четыре «работы»: кнопка писала «Проверить
    # 4 работы» рядом со «сдали 1 из 3», а колонка «Сдано работ» — 21 при
    # двенадцати заданиях группы. Ошибка тихая: числа сходятся между собой
    # (источник-то один), но все три врут одинаково.
    pairs = (Submission.objects
             .filter(assignment__in=assignments, status__in=statuses)
             .order_by()
             .values('assignment_id', 'student_id')
             .distinct())
    counts = {}
    for pair in pairs:
        counts[pair['student_id']] = counts.get(pair['student_id'], 0) + 1
    return counts


def works_waiting(assignments):
    """Сколько СДАННЫХ РАБОТ ждёт проверки. ЕДИНСТВЕННАЯ точка счёта.

    ⚠️ ЕДИНИЦА СЧЁТА — ПАРА (УЧЕНИК, РАБОТА), а не задание и не задача. Это
    то, что репетитор открывает и закрывает как одно дело.

    Считали в трёх местах и тремя разными способами, отчего на одном экране
    стояли три разных числа про одно и то же: карточка группы говорила
    «6 ждёт проверки» (это были ЗАДАЧИ), вкладка «Задания» — «3 ждут
    проверки» (это были ЗАДАНИЯ), а кнопки внутри — «Проверить 1»,
    «Проверить 1», «Проверить 4» (снова задачи). Четвёртая копия жила на
    удалённой вкладке «Проверка».

    Отсюда же берётся счётчик работы: `works_waiting([assignment])` для
    одного задания, `works_waiting(assignments)` для всей группы. Сумма по
    заданиям сходится с общим числом по построению — держится тестом.
    """
    return sum(student_work_counts(assignments, WAITING_STATUSES).values())


def needs_attention(group, now=None):
    """Кому нужно внимание: нет активности, просел, не сдана, ЖДЁТ ПРОВЕРКИ.

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

    # ⚠️ ФОРМУЛИРОВКИ БЕЗЛИЧНЫЕ (обзор 13.08, п. 15). Было «Анна Соколова —
    # не сдал»: женское имя и мужской род в одной строке. Род ученика
    # платформе не известен и известен не будет — ни имя, ни фамилия его не
    # определяют однозначно, а спрашивать ради строки предупреждения нельзя.
    # Поэтому фраза строится так, чтобы род вообще не требовался: не
    # «не сдал работу», а «работа не сдана».
    flagged = []
    for student in students:
        reasons = []
        levels = []

        def note(text, level):
            reasons.append(text)
            levels.append(level)

        seen = last_seen.get(student.pk)
        if seen is None:
            # Дней считать не от чего: событий нет вовсе.
            note('ни одного захода на сайт', 'info')
        elif seen < quiet_threshold:
            quiet_days = max(1, (now - seen).days)
            note('нет активности %d %s'
                 % (quiet_days, _days_word(quiet_days)), 'info')
        current = month_now.get(student.pk, {}).get('accuracy')
        before = previous.get(student.pk, {}).get('accuracy')
        if current is not None and before is not None and current + 10 <= before:
            note('доля верных упала с %d%% до %d%%' % (before, current), 'warn')
        if student.pk in missed and last_work is not None:
            # Срок этой работы УЖЕ ПРОШЁЛ по условию отбора — это просрочка.
            note('работа «%s» не сдана' % last_work.name, 'high')
        waiting = stale.get(student.pk)
        if waiting is not None:
            days = max(1, (now - waiting).days)
            # Имя в причину не вставляем: список и так сгруппирован по
            # ученику, а склонять фамилию в родительный падеж программно
            # нельзя — «работа Пётр Иванов» читается как ошибка.
            note('работа ждёт вашей проверки %d %s' % (days, _days_word(days)),
                 'high' if days > 7 else 'warn')
        if reasons:
            flagged.append({'student': student, 'reasons': reasons,
                            'level': worst_level(levels),
                            'last_active': seen})
    return flagged


# Три ступени срочности предупреждения — от них зависит только ЦВЕТ чёрточки
# слева (ревью 17.08, п. 5.1). Смысл: `high` — просрочено или ждёт вас дольше
# недели, `warn` — стоит посмотреть, `info` — просто факт об ученике.
# Порядок в кортеже и есть порядок возрастания срочности.
ATTENTION_LEVELS = ('info', 'warn', 'high')


def worst_level(levels):
    """Самая срочная из ступеней. У строки ученика причин может быть много."""
    found = [ATTENTION_LEVELS.index(level) for level in levels
             if level in ATTENTION_LEVELS]
    return ATTENTION_LEVELS[max(found)] if found else 'info'


# ===========================================================================
# Сессия 7, фаза 8 — как считается статистика
# ===========================================================================
#
# ⚠️ ЧТО ВО ЧТО ВХОДИТ (решения владельца, таблица продублирована в
# CLAUDE_ARCHIVE.md, раздел REVIEW_PROGRESS — здесь она рядом с кодом,
# который её выполняет):
#
#   показатель            | входит                        | НЕ входит
#   ----------------------|-------------------------------|-------------
#   «Решено»              | домашки, контрольные, каталог | ИГРА
#   «Доля верных» (оба)   | домашки, контрольные, каталог | ИГРА
#   «Последняя активность»| всё, ВКЛЮЧАЯ игру             | —
#   теплокарта по темам   | всё, ВКЛЮЧАЯ игру             | —
#
# Игра исключена из долей верных не по забывчивости: в ней другой формат
# ответа и другая цена ошибки, и смешивание портит обе шкалы. В теплокарту
# владения темами она входит — там важно, трогал ли ученик тему вообще.

# Доля верных ниже этого — красный, ниже следующего — жёлтый, выше — зелёный.
# Пороги владельца; едины для шкал прогресса и меток в таблицах.
LEVEL_GOOD = 70
LEVEL_MID = 40


def level_of(percent):
    """Уровень по доле верных: good / mid / bad. Ничего не знает про цвет."""
    if percent is None:
        return 'none'
    if percent >= LEVEL_GOOD:
        return 'good'
    if percent >= LEVEL_MID:
        return 'mid'
    return 'bad'


def canonical_topics():
    """Канонические темы каталога (их 23), в каноническом порядке.

    ⚠️ ПОКАЗЫВАЕМ ВСЕ, А НЕ ТОЛЬКО ТЕ, ГДЕ ЕСТЬ ДАННЫЕ (фаза 8.1). Тема без
    попыток — это не отсутствие строки, а факт: её не проходили. Список из
    трёх строк вместо двадцати трёх выглядит как «вот и весь предмет».
    """
    from problems.management.commands.apply_topic_mapping import CANONICAL
    from .models import Topic

    by_name = {t.name: t for t in Topic.objects.filter(name__in=CANONICAL)}
    return [by_name[name] for name in CANONICAL if name in by_name]


def _graded_ratios(user, tutor=None, kind=None, period='all', now=None):
    """Оценённые задачи ученика → [(topic_id, доля от максимума), …].

    ⚠️ НЕПОЛНЫЙ БАЛЛ ИДЁТ ВЕСОМ (фаза 8.2): 8 из 10 — это вклад 0,8, а не
    «неверно» и не «верно». Двоичное «решил / не решил» на открытых задачах
    было неправдой: половина работы там обычное дело.

    `tutor` — считать только работы этого репетитора (второе число доли
    верных, фаза 8.8). `kind` — 'test' или 'open', иначе всё.
    """
    from decimal import Decimal

    from .assignment_rows import item_max_score
    from .models import Submission

    queryset = (Submission.objects
                .filter(student=user, feedback__score__isnull=False)
                .select_related('feedback', 'problem_item',
                                'problem_item__catalog_problem',
                                'problem_item__custom_problem')
                .prefetch_related('problem_item__catalog_problem__topics'))
    if tutor is not None:
        queryset = queryset.filter(assignment__author=tutor)
    # Период — по моменту СДАЧИ работы: он и есть «когда ученик это решал».
    start, end = period_bounds(period, now)
    if start is not None:
        queryset = queryset.filter(submitted_at__gte=start,
                                   submitted_at__lt=end)

    rows = []
    for sub in queryset:
        item = sub.problem_item
        if item is None:
            continue
        if kind == 'test' and not item.is_test:
            continue
        if kind == 'open' and item.is_test:
            continue
        maximum = item_max_score(item)
        if not maximum:
            continue
        ratio = min(Decimal('1'), Decimal(str(sub.feedback.score)) / maximum)
        rows.append((_first_canonical_topic_id(item), float(ratio)))
    return rows


def _first_canonical_topic_id(item):
    """Тема позиции. У своей задачи репетитора тем нет — это не ошибка.

    ⚠️ Каноническая тема ГЛАВНЕЕ, но если её нет — берём первую любую, а не
    None. Иначе задача считалась бы в строке «Всего» и не попадала ни в одну
    строку темы, и сумма строк перестала бы сходиться с итогом.
    """
    from problems.management.commands.apply_topic_mapping import CANONICAL

    problem = getattr(item, 'catalog_problem', None)
    if problem is None:
        return None
    topics = list(problem.topics.all())
    for topic in topics:
        if topic.name in CANONICAL:
            return topic.pk
    return topics[0].pk if topics else None


def _catalog_ratios(user, kind=None, period='all', now=None):
    """Задачи каталога: решил — 1, ошибся — 0. Игра сюда НЕ входит."""
    from .models import LearningEvent

    rows = (LearningEvent.objects
            .filter(user=user, source='catalog',
                    event_type__in=('solved', 'failed'),
                    topic__isnull=False))
    start, end = period_bounds(period, now)
    if start is not None:
        rows = rows.filter(created_at__gte=start, created_at__lt=end)
    rows = rows.values('topic_id', 'event_type')
    return [(row['topic_id'], 1.0 if row['event_type'] == 'solved' else 0.0)
            for row in rows]


def accuracy_pair(user, tutor=None, kind=None, period='all', now=None):
    """Два числа доли верных: по всему сайту и по работам этого репетитора.

    ⚠️ ИГРА НЕ ВХОДИТ НИ В ОДНО ИЗ НИХ (поправка владельца к фазе 8.8).
    «По всему сайту» — это каталог плюс домашки и контрольные ВСЕХ
    репетиторов, а не «вообще всё, что человек делал на сайте».
    """
    everywhere = (_graded_ratios(user, kind=kind, period=period, now=now)
                  + _catalog_ratios(user, kind, period=period, now=now))
    mine = (_graded_ratios(user, tutor=tutor, kind=kind, period=period,
                           now=now) if tutor else [])
    return {'all': _percent(everywhere), 'mine': _percent(mine),
            'all_count': len(everywhere), 'mine_count': len(mine)}


def _percent(rows):
    """Среднее по долям → проценты. Пусто — None, а не ноль."""
    if not rows:
        return None
    return int(round(sum(ratio for _, ratio in rows) * 100.0 / len(rows)))


def topic_progress(user, kind=None, tutor=None, period='all', now=None):
    """Прогресс по ВСЕМ 21 темам: доля верных, решено, уровень.

    Строка на каждую каноническую тему, даже пустую. Неполный балл идёт
    весом (см. `_graded_ratios`). Внизу отдельной строкой — «Всего».
    """
    rows = (_graded_ratios(user, tutor=tutor, kind=kind, period=period,
                           now=now)
            + _catalog_ratios(user, kind, period=period, now=now))

    buckets = {}
    for topic_id, ratio in rows:
        if topic_id is None:
            continue
        bucket = buckets.setdefault(topic_id, [])
        bucket.append(ratio)

    def make_row(topic_id, name, topic=None):
        ratios = buckets.get(topic_id, [])
        percent = (int(round(sum(ratios) * 100.0 / len(ratios)))
                   if ratios else None)
        return {
            'topic': topic,
            'name': name,
            'solved': len(ratios),
            # «Верных» дробное: 8 из 10 это 0,8 задачи, а не одна и не ноль.
            'correct': round(sum(ratios), 1) if ratios else 0,
            'percent': percent,
            'level': level_of(percent),
            'empty': not ratios,
        }

    result = []
    seen = set()
    for topic in canonical_topics():
        seen.add(topic.pk)
        result.append(make_row(topic.pk, topic.name, topic))

    # Неканонические темы с данными — в конец (см. `group_topic_matrix`):
    # прятать реальные попытки нельзя, а порядок канона держим неизменным.
    from .models import Topic
    extra_ids = [tid for tid in buckets if tid not in seen]
    if extra_ids:
        extra = {t.pk: t for t in Topic.objects.filter(pk__in=extra_ids)}
        for topic_id in sorted(extra_ids,
                               key=lambda tid: -len(buckets[tid])):
            topic = extra.get(topic_id)
            if topic is not None:
                result.append(make_row(topic.pk, topic.name, topic))

    # ⚠️ «ВСЕГО» СЧИТАЕТСЯ ПО ВСЕМ ЗАДАЧАМ, А НЕ КАК СРЕДНЕЕ ИЗ ПРОЦЕНТОВ
    # ТЕМ (фаза 8.7). Среднее из процентов дало бы теме с одной задачей тот
    # же вес, что теме с сорока.
    everything = [ratio for _, ratio in rows]
    total_percent = (int(round(sum(everything) * 100.0 / len(everything)))
                     if everything else None)
    total = {
        'name': 'Всего', 'solved': len(everything),
        'correct': round(sum(everything), 1) if everything else 0,
        'percent': total_percent, 'level': level_of(total_percent),
        'empty': not everything,
    }
    return {'rows': result, 'total': total}


def topic_progress_pairs(user, tutor=None, period='all', now=None):
    """Прогресс по темам ОДНОЙ таблицей: тема · задачи · тесты.

    Владелец согласовал макет: вместо двух карточек одна под другой (по 23
    строки в каждой, и много пустого места по бокам) — один блок, где у
    строки темы две половины.

    ⚠️ ВТОРОЙ СБОРКИ НЕТ. Обе половины считает та же `topic_progress`, что
    считала карточки: здесь только сшивка по теме. Иначе «задачи» и «тесты»
    начали бы расходиться правилами.

    ⚠️ Строка приглушается, только когда попыток нет В ОБЕИХ половинах:
    пустая половина при заполненной соседке — это факт про одну колонку, а
    не про тему целиком.
    """
    open_data = topic_progress(user, kind='open', tutor=tutor, period=period,
                               now=now)
    test_data = topic_progress(user, kind='test', tutor=tutor, period=period,
                               now=now)
    by_name = {row['name']: row for row in test_data['rows']}

    rows = []
    for left in open_data['rows']:
        right = by_name.get(left['name'])
        rows.append({
            'name': left['name'],
            'topic': left['topic'],
            'open': left,
            'test': right,
            'empty': left['empty'] and (right is None or right['empty']),
        })
    # Неканоническая тема, попавшая только в тесты, потерялась бы молча.
    seen = {row['name'] for row in open_data['rows']}
    for name, right in by_name.items():
        if name not in seen and not right['empty']:
            rows.append({'name': name, 'topic': right['topic'],
                         'open': None, 'test': right, 'empty': False})
    # ⚠️ ДЕЛИТ СТРОКИ СЕРВЕР (ревью 17.08, п. 3.2). Пустые темы уезжают на
    # экране под раскрывашку, и правило «что считать пустым» обязано быть
    # ОДНО: `empty` уже посчитан выше, шаблону остаётся только нарисовать.
    return {'rows': rows,
            'filled': [row for row in rows if not row['empty']],
            'blank': [row for row in rows if row['empty']],
            'total_open': open_data['total'],
            'total_test': test_data['total']}


def group_accuracy(group, tutor=None, kind=None):
    """Средневзвешенное по группе — ПО КОЛИЧЕСТВУ РЕШЁННЫХ ЗАДАЧ (фаза 8.3).

    Среднее из процентов учеников дало бы тому, кто решил три задачи, тот же
    вес, что решившему триста.
    """
    correct = 0.0
    solved = 0
    for student in group.students.all():
        rows = (_graded_ratios(student, tutor=tutor, kind=kind)
                + _catalog_ratios(student, kind))
        correct += sum(ratio for _, ratio in rows)
        solved += len(rows)
    if not solved:
        return None
    return int(round(correct * 100.0 / solved))


# ---------------------------------------------------------------------------
# История работ — ОДНА сборка на карточку ученика и на обзор группы
# ---------------------------------------------------------------------------
# ⚠️ Столбцы «% верных задач», «% верных тестов» и «Оценка» считаются здесь
# один раз. Раньше история работ жила только в карточке ученика
# (`teacher/views.py::_work_history`); обзору группы нужна ТА ЖЕ таблица,
# и второй её сборки быть не должно — расходиться начали бы не экраны, а
# числа, по которым репетитор судит о группе.

def _work_scores(work, students):
    """Баллы по одной работе: (набрано, максимум) по типам + кто когда сдал.

    Возвращает (got, could, submitted_at_by_student). `got`/`could` —
    словари {'open': …, 'test': …}. Считаем ТОЛЬКО оценённые позиции:
    непроверенная задача не «ноль», а «ещё не знаем».
    """
    from decimal import Decimal

    from problems.assignment_rows import item_max_score
    from problems.models import Submission

    got = {'open': Decimal('0'), 'test': Decimal('0')}
    could = {'open': Decimal('0'), 'test': Decimal('0')}
    when = {}
    subs = (Submission.objects
            .filter(assignment=work, student__in=students)
            .select_related('feedback', 'problem_item',
                            'problem_item__catalog_problem',
                            'problem_item__custom_problem'))
    for sub in subs:
        item = sub.problem_item
        if item is None:
            continue
        if sub.submitted_at:
            previous = when.get(sub.student_id)
            if previous is None or sub.submitted_at > previous:
                when[sub.student_id] = sub.submitted_at
        feedback = getattr(sub, 'feedback', None)
        if feedback is None or feedback.score is None:
            continue
        key = 'test' if item.is_test else 'open'
        got[key] += Decimal(str(feedback.score))
        could[key] += item_max_score(item)
    return got, could, when


def work_kinds(work):
    """Что вообще есть В СОСТАВЕ работы: открытые задачи и/или тесты.

    ⚠️ ЗАЧЕМ ОТДЕЛЬНО ОТ БАЛЛОВ (обзор 13.08, п. 34). В истории работ
    столбцы «% верных задач» и «% верных тестов» показывали голый прочерк
    и когда данных ещё нет, и когда таких задач в работе НЕ БЫЛО ВОВСЕ.
    Рядом с «80 %» соседний прочерк читается как «плохо», хотя тестов
    в работе просто не задавали. Это разные ответы, и различить их можно
    только по составу.
    """
    kinds = {'has_open': False, 'has_test': False}
    for item in work.items.select_related('catalog_problem',
                                          'custom_problem'):
        if item.is_test:
            kinds['has_test'] = True
        else:
            kinds['has_open'] = True
    return kinds


def _work_percents(got, could):
    """Три процента строки: по задачам, по тестам и итог. Нет базы → None.

    Рядом с каждым числом отдаём УРОВЕНЬ (`level_of`) — тот же, что красит
    шкалы прогресса. Так история работ берёт цвета из общего правила, а не
    заводит своё: два правила «когда зелёный» разъехались бы на первой
    правке. Прочерку уровень не нужен — «нет данных» не красится вовсе.
    """
    def share(key):
        return (int(round(float(got[key] / could[key]) * 100))
                if could[key] else None)

    total_got = got['open'] + got['test']
    total_could = could['open'] + could['test']
    open_percent = share('open')
    test_percent = share('test')
    mark = (int(round(float(total_got / total_could) * 100))
            if total_could else None)
    return {
        'open_percent': open_percent,
        'open_level': level_of(open_percent),
        'test_percent': test_percent,
        'test_level': level_of(test_percent),
        'mark': mark,
        'mark_level': level_of(mark),
    }


def work_history(student, tutor):
    """История работ ОДНОГО ученика (карточка ученика, фаза 10.5).

    ⚠️ ОЦЕНКА — ПРОЦЕНТ, А НЕ СЫРЫЕ БАЛЛЫ. У разных работ разный максимум, и
    «12» за одну работу и «8» за другую несопоставимы ничем.

    ⚠️ СРОК СПРАШИВАЕМ ТОЛЬКО ЧЕРЕЗ `deadline_at`. Поле `due_at` устарело и
    не читается нигде — два поля уже давали видимый баг «без срока» у работы
    со сроком.
    """
    from problems.models import Assignment

    works = (Assignment.objects.filter(author=tutor, students=student)
             .order_by('-id'))
    rows = []
    for work in works:
        got, could, when = _work_scores(work, [student])
        submitted_at = when.get(student.pk)
        row = {'work': work, 'is_exam': work.is_exam,
               'submitted_at': submitted_at,
               'deadline': work.deadline_at,
               'not_submitted': submitted_at is None}
        row.update(work_kinds(work))
        row.update(_work_percents(got, could))
        rows.append(row)
    return rows


def group_work_history(group):
    """История работ ГРУППЫ (обзор группы, п. 11.5).

    Отличие от карточки ученика ровно одно: вместо даты сдачи — два числа
    «невовремя / не сдано».

    ⚠️ РАБОТА БЕЗ СРОКА В СТОЛБЕЦ «НЕВОВРЕМЯ» НЕ ПОПАДАЕТ ВООБЩЕ — прочерк,
    а не ноль: без срока опоздать нельзя, и ноль тут был бы утверждением о
    том, чего система не знает.
    """
    from problems.models import Assignment

    students = list(group.students.all())
    works = Assignment.objects.filter(group=group).order_by('-id')
    rows = []
    for work in works:
        got, could, when = _work_scores(work, students)
        deadline = work.deadline_at
        issued = set(work.students.values_list('id', flat=True)) or {
            s.pk for s in students}
        watched = [s for s in students if s.pk in issued] or students
        late = None
        if deadline is not None:
            late = sum(1 for s in watched
                       if when.get(s.pk) and when[s.pk] > deadline)
        missing = sum(1 for s in watched if when.get(s.pk) is None)
        # ⚠️ У ИНДИВИДУАЛЬНОГО ЗАНЯТИЯ «невовремя / не сдано» вырождается:
        # два числа из одного человека это «0/1» или «1/0», и читать их
        # труднее, чем сам факт. Отдаём момент сдачи и две пометки —
        # опоздал / не сдал; какой столбец рисовать, решает разметка.
        solo = when.get(watched[0].pk) if len(watched) == 1 else None
        row = {'work': work, 'is_exam': work.is_exam,
               'deadline': deadline, 'late': late, 'missing': missing,
               'people': len(watched),
               'submitted_at': solo,
               'is_late': bool(solo and deadline and solo > deadline),
               'not_submitted': missing == len(watched)}
        row.update(work_kinds(work))
        row.update(_work_percents(got, could))
        rows.append(row)
    return rows
