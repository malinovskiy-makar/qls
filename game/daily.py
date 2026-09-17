"""
Вызов дня Econ Rush: четыре набора в сутки — по одному на каждый режим.

⚠️ **Создание ЛЕНИВОЕ.** Крона нет и не будет (бесплатный тариф хостинга
засыпает после 15 минут без запросов), поэтому набор строится при первом
обращении в этот день. Чтобы «первое обращение» не превращалось в лотерею,
список собирается ДЕТЕРМИНИРОВАННО: сид = дата + ключ режима. Собери набор
дважды в один день — получишь тот же список. Это закрыто тестом.

Отсечка суток — по Москве (константа в config.py): игроки российские, и
новый вызов обязан наступать по их полуночи, а не по UTC сервера.

На доску попадают только авторизованные: у анонима нет имени, а «аноним №4»
на доске ничего не значит. Играть при этом может кто угодно — игра остаётся
публичной, стены с логином тут нет.
"""
import datetime
import random
from typing import Optional

from django.db import IntegrityError
from django.utils import timezone

from . import config
from .models import GameSet, make_code


def daily_tzinfo():
    """Часовой пояс отсечки суток. Нет базы часовых поясов — фиксированный
    UTC+3: Москва без перехода на летнее время с 2014 года, ошибки не будет."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(config.DAILY_TZ)
    except Exception:
        return datetime.timezone(
            datetime.timedelta(hours=config.DAILY_TZ_FALLBACK_HOURS))


def today():
    """Сегодняшняя дата вызова — по московской полуночи."""
    return timezone.now().astimezone(daily_tzinfo()).date()


def next_reset():
    """Момент смены вызова (ближайшая московская полночь) — для обратного
    отсчёта на странице."""
    tz = daily_tzinfo()
    now_local = timezone.now().astimezone(tz)
    tomorrow = now_local.date() + datetime.timedelta(days=1)
    return datetime.datetime.combine(tomorrow, datetime.time.min, tzinfo=tz)


def daily_seed(day, mode):
    """Сид набора дня. Строка, а не число: random.seed(str) стабилен между
    запусками и платформами (внутри sha512), а самодельный хеш строки —
    нет (PYTHONHASHSEED)."""
    return '{}:{}'.format(day.isoformat(), mode)


def pick_daily_questions(day, mode, candidate_ids):
    """Список вопросов вызова дня — ЧИСТАЯ функция.

    Из тех же кандидатов в тот же день для того же режима всегда получается
    один и тот же список в том же порядке. Кандидаты передаются снаружи,
    чтобы функцию можно было проверить без базы.
    """
    size = config.DAILY_SIZE.get(mode, 10)
    pool = sorted(candidate_ids)          # порядок кандидатов не должен влиять
    if not pool:
        return []
    rng = random.Random(daily_seed(day, mode))
    if len(pool) <= size:
        chosen = list(pool)
    else:
        chosen = rng.sample(pool, size)
    rng.shuffle(chosen)                   # порядок тоже часть набора
    return chosen


def get_daily_set(mode, day=None, create=True):
    # type: (str, Optional[datetime.date], bool) -> Optional[GameSet]
    """Набор вызова дня. Создаётся лениво при первом обращении.

    Гонка двух одновременных первых игроков закрыта уникальным ключом
    (kind, mode, day) в базе: проигравший гонку просто перечитает чужую
    строку. Второй набор на тот же день появиться не может.
    """
    if mode not in config.MODES:
        return None
    day = day or today()
    existing = GameSet.objects.filter(kind='daily', mode=mode, day=day).first()
    if existing or not create:
        return existing

    from .views import _pool_qs
    qtype = config.MODES[mode]['question_type']
    ids = list(_pool_qs().filter(question_type=qtype)
               .values_list('id', flat=True))
    chosen = pick_daily_questions(day, mode, ids)
    if not chosen:
        return None

    tz = daily_tzinfo()
    opens = datetime.datetime.combine(day, datetime.time.min, tzinfo=tz)
    closes = opens + datetime.timedelta(days=1)
    try:
        return GameSet.objects.create(
            code=make_code(), mode=mode, kind='daily',
            title='Вызов дня · {} · {}'.format(
                config.MODES[mode]['title'], day.strftime('%d.%m.%Y')),
            author=None, question_ids=chosen, filter_snapshot={},
            opens_at=opens, closes_at=closes, attempts_allowed=1, day=day)
    except IntegrityError:
        # Гонку выиграл кто-то другой — берём его набор, он тот же самый.
        return GameSet.objects.filter(kind='daily', mode=mode, day=day).first()


# ─── Страница вызова и доска дня (P4, решение владельца 17.09.2026) ──────

# Чем кончился раунд — словами доски дня (макет DailyBoard).
ENDING_TEXT = {'set_done': 'прошёл все вопросы', 'pool_empty': 'прошёл все вопросы',
               'lives': 'кончились жизни', 'time': 'вышло время',
               'quit': 'вышел из раунда'}

# Как называть вопросы режима на карточке: «15 данеток», «8 числовых ответов».
QUESTION_WORDS = {'boolean': ('данетка', 'данетки', 'данеток'),
                  'numeric': ('числовой ответ', 'числовых ответа', 'числовых ответов')}
DEFAULT_WORDS = ('вопрос', 'вопроса', 'вопросов')


def set_line(mode, size=None):
    """«15 данеток · 1 мин». Без размера (набора в тот день не было) — «1 мин».

    ⚠️ Кода набора в строке нет и быть не должно: у вызова дня он игроку не
    нужен, играют по кнопке, а не по коду (решение 17.09.2026).
    """
    from problems.templatetags.ru import pick
    from .views import duration_text
    duration = duration_text(config.MODES[mode]['duration'])
    if size is None:
        return duration
    words = QUESTION_WORDS.get(config.MODES[mode]['question_type'], DEFAULT_WORDS)
    return '%d %s · %s' % (size, pick(size, *words), duration)


def board_url(mode, day):
    """Адрес доски дня: у сегодняшней — без даты, у прошедшей — с датой.

    Доска у вызова одна (P4): страница вызова, итог раунда и старый адрес
    `/game/s/<код>/board/` ведут сюда.
    """
    from django.urls import reverse
    if day == today():
        return reverse('game:daily_board', args=[mode])
    return reverse('game:daily_board_day', args=[mode, day.isoformat()])


def first_day():
    """День первого в базе набора вызова — раньше него доску не листаем."""
    return (GameSet.objects.filter(kind='daily', day__isnull=False)
            .order_by('day').values_list('day', flat=True).first())


def board_rows(gset, me=None, limit=50):
    """Доска набора: топ-N + отдельная строка «моё место», если я вне топа.

    Сортировка: по счёту вниз, при равенстве — кто раньше закончил, тот
    выше. Ничья по времени невозможна практически, но правило должно быть
    задано: одинаковый вход обязан давать одинаковый порядок.

    На доске только авторизованные — см. докстринг модуля.
    """
    results = list(gset.results.filter(user__isnull=False)
                   .select_related('user')
                   .order_by('-score', 'created_at'))
    rows = [{
        'place': i + 1,
        'name': r.user.username,
        'score': r.score,
        'accuracy': r.accuracy,
        'max_combo': r.max_combo,
        'combo': '×' + ('%g' % (r.max_combo or 1)).replace('.', ','),
        'ending': ENDING_TEXT.get(r.ended_reason, ENDING_TEXT['time']),
        'at': r.created_at,
        'is_me': bool(me and r.user_id == me.id),
    } for i, r in enumerate(results)]
    top = rows[:limit]
    my_row = None
    if me is not None:
        mine = [r for r in rows if r['is_me']]
        if mine and mine[0]['place'] > limit:
            my_row = mine[0]
    return top, my_row, len(rows)


# ─── Серия дней (решение владельца 17.09.2026) ───────────────────────────
#
# ⚠️ СЕРИЯ СЧИТАЕТСЯ ИЗ `GameResult`, СВОЕЙ ТАБЛИЦЫ У НЕЁ НЕТ. Счётчик в
# отдельной таблице разошёлся бы с фактом при первой же правке или удалении
# результата руками — тот же довод, что у лидерборда (ADR 0056).
#
# День засчитан, если сыгран ХОТЯ БЫ ОДИН из четырёх вызовов. Дата — день
# НАБОРА (`game_set.day`), а не момент сохранения: раунд, начатый в 23:59 и
# сохранённый в 00:01, относится к дню своего набора.

WEEKDAY_LABELS = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')

# `streak_for` принимает параметр `today` (так его зовёт спецификация),
# и внутри функции он закрывает модульную `today()`. Ссылка на неё — здесь.
_moscow_today = today


def played_pairs(user):
    """Множество пар (день набора, режим) сыгранных пользователем вызовов.

    Один запрос на пользователя. Аноним — пустое множество: у него нет
    имени на доске и серии нет вовсе.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return set()
    from .models import GameResult
    return set(GameResult.objects
               .filter(user=user, game_set__kind='daily',
                       game_set__day__isnull=False)
               .order_by()          # порядок модели добавил бы created_at в DISTINCT
               .values_list('game_set__day', 'game_set__mode')
               .distinct())


def played_days(user):
    """Московские даты, в которые у пользователя есть сыгранный вызов дня."""
    return {day for day, _mode in played_pairs(user)}


def streak_for(user, today=None, pairs=None):
    """Серия дней: `{'current', 'best', 'week', 'played_today'}`.

    `current` — длина цепочки подряд идущих дней, кончающейся сегодня; если
    сегодня ещё не сыграно — вчера: серия не сгорает до полуночи. `best` —
    самая длинная цепочка за всё время. `week` — текущая неделя пн–вс.
    `pairs` — уже прочитанные `played_pairs(user)`, чтобы не ходить в базу
    второй раз.
    """
    day0 = today or _moscow_today()
    days = {d for d, _m in (played_pairs(user) if pairs is None else pairs)}
    one = datetime.timedelta(days=1)

    current = 0
    cursor = day0 if day0 in days else day0 - one
    while cursor in days:
        current += 1
        cursor -= one

    best = run = 0
    prev = None
    for d in sorted(days):
        run = run + 1 if prev is not None and d - prev == one else 1
        best = max(best, run)
        prev = d

    monday = day0 - datetime.timedelta(days=day0.weekday())
    week = []
    for i in range(7):
        d = monday + datetime.timedelta(days=i)
        week.append({'day': d.isoformat(), 'label': WEEKDAY_LABELS[i],
                     'hit': d in days, 'is_today': d == day0})
    return {'current': current, 'best': max(best, current), 'week': week,
            'played_today': day0 in days}


def daily_cell(user):
    """Живая ячейка «Вызов дня» на главной игры.

    Вошедшему — сколько из четырёх вызовов сыграно сегодня и серия дней;
    анониму — только число вызовов. Момент смены вызова отдаёт сервер
    (`next_reset`), клиент лишь рисует остаток.
    """
    day0 = _moscow_today()
    cell = {'total': len(config.MODES),
            'reset_at': next_reset().isoformat(timespec='seconds'),
            'is_authenticated': bool(user is not None
                                     and getattr(user, 'is_authenticated', False))}
    if cell['is_authenticated']:
        pairs = played_pairs(user)
        cell['played'] = len({m for d, m in pairs if d == day0})
        cell['streak'] = streak_for(user, today=day0, pairs=pairs)['current']
    return cell
