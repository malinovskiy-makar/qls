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
