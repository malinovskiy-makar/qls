# -*- coding: utf-8 -*-
u"""Лидерборд Wecon Rush: агрегация по ЛИЧНЫМ РЕКОРДАМ.

⚠️ ПОЧЕМУ АГРЕГАЦИЯ, А НЕ ТАБЛИЦА РЕКОРДОВ. Отдельная таблица «лучший
результат игрока» — это второй источник правды о том, что уже записано в
`GameResult`. Она разъедется при первой же правке: удалили забег руками,
откатили миграцию, поменяли правило зачётности — и рекорд остался от
несуществующего результата. Агрегация читает факты и врать не умеет.

Путь роста, когда игроков станут тысячи: та же агрегация раз в минуту
складывается в материализованную таблицу лучших, а API читает её. Модель
данных при этом НЕ МЕНЯЕТСЯ — меняется только источник строк.
Обоснование целиком — docs/adr/0056-game-leaderboard-personal-records.md.

⚠️ В ТАБЛИЦУ ИДУТ ТОЛЬКО ЗАЧЁТНЫЕ ЗАБЕГИ (`ranked=True`). Решает это
`views._rank_run` при сохранении, здесь — только чтение.
"""
import datetime

from django.core.cache import cache
from django.db.models import Max, Min
from django.utils import timezone

from . import config
from .models import GameResult

# Три показателя досок. Ключ → (поле, как агрегируем, «больше — лучше»).
METRICS = {
    'score': ('score', Max, True),
    'correct': ('correct_count', Max, True),
    'speed': ('avg_correct_ms', Min, False),
}
PERIODS = ('week', 'all')
TOP_LIMIT = 20
CACHE_TTL = 60          # секунда в секунду с обновлением экрана не нужна
CACHE_PREFIX = 'rush:lb:v2'


def _window(period):
    u"""Нижняя граница окна или None для «всё время»."""
    if period == 'week':
        return timezone.now() - datetime.timedelta(days=7)
    return None


def base_queryset(mode, period, metric):
    u"""Забеги, из которых считается доска.

    ⚠️ У ДВУХ ДОСОК СВОИ ДОПОЛНИТЕЛЬНЫЕ УСЛОВИЯ, И ЭТО НЕ ПРИДИРКА.
    «Больше всего верных» и «среднее время» берут только забеги БЕЗ
    фильтров: под фильтром по теме легко набрать длинную серию верных на
    знакомом материале, и доска перестала бы сравнивать умение. Доска
    «Скорость» вдобавок требует не меньше SPEED_BOARD_MIN_CORRECT верных —
    среднее по двум ответам это не среднее, а случайность.
    """
    qs = GameResult.objects.filter(mode=mode, ranked=True, user__isnull=False)
    since = _window(period)
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    if metric in ('correct', 'speed'):
        qs = qs.filter(is_unfiltered=True)
    if metric == 'speed':
        qs = qs.filter(avg_correct_ms__isnull=False,
                       correct_count__gte=config.SPEED_BOARD_MIN_CORRECT)
    return qs


def _rows(mode, period, metric, limit=TOP_LIMIT):
    u"""Личные рекорды: по строке на игрока, отсортированные.

    ⚠️ ПРИ РАВЕНСТВЕ ВЫШЕ ТОТ, КТО ДОБИЛСЯ РАНЬШЕ. Без этого правила
    порядок одинаковых результатов зависел бы от базы и менялся сам собой
    между обновлениями страницы — а человек читает это как «меня обогнали».
    """
    field, agg, desc = METRICS[metric]
    rows = (base_queryset(mode, period, metric)
            .values('user')
            .annotate(best=agg(field), achieved=Min('created_at'))
            .order_by(('-' if desc else '') + 'best', 'achieved'))[:limit]
    rows = list(rows)
    if not rows:
        return []
    from problems.models import User
    names = dict(User.objects.filter(id__in=[r['user'] for r in rows])
                 .values_list('id', 'username'))
    out = []
    for i, r in enumerate(rows, 1):
        out.append({
            'place': i,
            # ⚠️ Внутреннего id пользователя в ПУБЛИЧНОЙ выдаче нет: наружу
            # уходит ровно то, что доска и обещает показать. Подсветку «это
            # я» ставит сервер отдельным полем (см. `mark_me`).
            'username': names.get(r['user'], '–'),
            'value': r['best'],
            'achieved_at': r['achieved'].isoformat(timespec='seconds'),
            '_uid': r['user'],       # снимается перед отдачей, см. mark_me
        })
    return out


def mark_me(rows, user):
    u"""Пометить свою строку и снять служебный id перед отдачей наружу.

    ⚠️ Делается ПОСЛЕ кэша и на копии: сами строки кэшируются общими на всех,
    и пометить «это я» внутри кэша значило бы показать одному игроку чужую
    подсветку.
    """
    me_id = user.id if (user and user.is_authenticated) else None
    out = []
    for r in rows:
        row = dict(r)
        row['is_me'] = row.pop('_uid', None) == me_id and me_id is not None
        out.append(row)
    return out


def top(mode, period, metric, limit=TOP_LIMIT):
    u"""Верхушка доски. Кэшируется на минуту: строки у всех одинаковые."""
    key = '%s:%s:%s:%s:%d' % (CACHE_PREFIX, mode, period, metric, limit)
    rows = cache.get(key)
    if rows is None:
        rows = _rows(mode, period, metric, limit)
        cache.set(key, rows, CACHE_TTL)
    return rows


def my_row(user, mode, period, metric):
    u"""Строка «я» — с местом, даже если игрок вне верхушки.

    ⚠️ НИКОГДА НЕ КЛАДЁТСЯ В КЭШ. Строка у каждого своя; попади она в общий
    ключ — один игрок увидел бы чужое место как своё. Ошибка тихая и
    страшная, поэтому здесь всегда живой запрос.
    """
    if not user or not user.is_authenticated:
        return None
    field, agg, desc = METRICS[metric]
    mine = (base_queryset(mode, period, metric).filter(user=user)
            .aggregate(best=agg(field), achieved=Min('created_at')))
    if mine['best'] is None:
        return None
    # Место — сколько игроков строго ЛУЧШЕ. Считаем по той же выборке.
    better = (base_queryset(mode, period, metric)
              .values('user').annotate(best=agg(field)))
    if desc:
        ahead = sum(1 for r in better if r['best'] > mine['best'])
    else:
        ahead = sum(1 for r in better if r['best'] < mine['best'])
    return {
        'place': ahead + 1,
        'is_me': True,
        'username': user.username,
        'value': mine['best'],
        'achieved_at': mine['achieved'].isoformat(timespec='seconds'),
    }


def total_players(mode, period, metric):
    u"""Сколько всего игроков на этой доске — «5 из 37» без этого не сказать."""
    return (base_queryset(mode, period, metric)
            .values('user').distinct().count())


def personal_stats(user, mode):
    u"""Личная статистика игрока по режиму. Видна ТОЛЬКО ему самому.

    Считается по ВСЕМ его забегам этого режима, а не только зачётным:
    человеку интересно, сколько он играл, а не сколько попало в таблицу.
    Место при этом берётся с доски — там правила общие.
    """
    runs = GameResult.objects.filter(user=user, mode=mode,
                                     economy_version=config.ECONOMY_VERSION)
    total = runs.count()
    if not total:
        return {'runs': 0}
    agg = runs.aggregate(best=Max('score'), best_correct=Max('correct_count'),
                         first_best=Min('created_at'))
    best_run = runs.order_by('-score', 'created_at').first()
    correct_sum = sum(runs.values_list('correct_count', flat=True))
    attempts = sum(r.correct_count + r.wrong_count for r in runs)
    speeds = [r.avg_correct_ms for r in runs if r.avg_correct_ms]
    place = my_row(user, mode, 'all', 'score')
    return {
        'runs': total,
        'best_score': agg['best'] or 0,
        'best_score_at': (best_run.created_at.isoformat(timespec='seconds')
                          if best_run else None),
        'best_correct': agg['best_correct'] or 0,
        'accuracy': round(100 * correct_sum / attempts) if attempts else 0,
        'avg_correct_ms': (int(sum(speeds) / len(speeds)) if speeds else None),
        'correct_total': correct_sum,
        'place': place['place'] if place else None,
        'total_players': total_players(mode, 'all', 'score'),
    }


def best_run(user, mode):
    u"""Личный рекорд игрока в режиме или None, если рекорда ещё нет.

    ⚠️ ТОЧНОСТЬ БЕРЁТСЯ У САМОГО РЕКОРДНОГО ЗАБЕГА, а не средняя за всё
    время (её считает `personal_stats`). Табло сравнивает текущий раунд с
    ОДНИМ конкретным забегом, и подмешивать туда среднее значило бы
    показывать рядом два числа из разных вселенных.

    None означает ровно одно: забегов в этом режиме не было. Экран в этом
    случае говорит словами, а не рисует ноль: выдуманное число-заглушка на
    табло хуже честного «первый раунд».
    """
    run = (GameResult.objects
           .filter(user=user, mode=mode,
                   economy_version=config.ECONOMY_VERSION)
           .order_by('-score', 'created_at').first())
    if run is None:
        return None
    attempts = run.correct_count + run.wrong_count
    return {
        'score': run.score,
        'correct': run.correct_count,
        'accuracy': round(100 * run.correct_count / attempts) if attempts else 0,
        'created_at': run.created_at.isoformat(timespec='seconds'),
    }


def duel_stats(user):
    u"""Сводка по дуэлям игрока. Новых таблиц не заводим.

    Считается из `GameSet(kind='duel')` и результатов в них: у дуэли ровно
    две стороны, и «победа» — это чей счёт выше. Ничья считается ничьёй, а
    не округляется в чью-то пользу: два одинаковых счёта в игре на скорость
    случаются чаще, чем кажется.

    ⚠️ ЗАСЧИТЫВАЮТСЯ ТОЛЬКО СЫГРАННЫЕ ОБОИМИ. Дуэль, где соперник так и не
    пришёл, — это не победа: играть было не с кем. Она не попадает ни в
    победы, ни в поражения, ни в знаменатель процента.
    """
    from game.models import GameSet

    sets = (GameSet.objects.filter(kind='duel')
            .filter(results__user=user).distinct()
            .prefetch_related('results__user').order_by('-created'))
    wins = losses = draws = 0
    rivals = {}
    last_rival = None
    played = 0
    for gset in sets:
        rows = [r for r in gset.results.all() if r.user_id]
        mine = next((r for r in rows if r.user_id == user.id), None)
        rival = next((r for r in rows if r.user_id != user.id), None)
        if mine is None or rival is None:
            continue
        played += 1
        if mine.score > rival.score:
            wins += 1
        elif mine.score < rival.score:
            losses += 1
        else:
            draws += 1
        name = rival.user.get_username()
        rivals[name] = rivals.get(name, 0) + 1
        if last_rival is None:
            last_rival = name

    top = max(rivals.items(), key=lambda kv: (kv[1], kv[0])) if rivals \
        else None
    return {
        'played': played,
        'wins': wins,
        'losses': losses,
        'draws': draws,
        'win_percent': round(100 * wins / played) if played else None,
        'top_rival': top[0] if top else None,
        'top_rival_games': top[1] if top else 0,
        'last_rival': last_rival,
    }
