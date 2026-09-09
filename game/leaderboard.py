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


# Сколько последних забегов показывает график «Последние раунды».
# ⚠️ Число живёт ЗДЕСЬ, а не в клиенте: клиент рисует то, что дали.
HISTORY_LIMIT = 20


def run_history(user, mode):
    u"""Последние забеги игрока в режиме плюс его средние по режиму.

    ⚠️ ТОЛЬКО ПРО СЕБЯ. Параметра «чей» нет и не будет: он немедленно
    превратил бы личную историю в публичную по перебору номеров — то же
    правило, что у `personal_stats`.

    ⚠️ СРЕДНИЕ СЧИТАЮТСЯ ПО ВСЕМ ЗАБЕГАМ РЕЖИМА, а список — по последним
    двадцати. Это разные вопросы: «как я играю обычно» и «как шли последние
    раунды». Считать среднее по двадцати значило бы менять смысл слова
    «обычно» вместе с длиной списка.

    Пустая история — это `runs: []` и `avg: None`, а не нули: нуля забегов
    не бывает «в среднем», и рисовать по нему сравнение нечестно.
    """
    runs = GameResult.objects.filter(user=user, mode=mode,
                                     economy_version=config.ECONOMY_VERSION)
    total = runs.count()
    if not total:
        return {'mode': mode, 'runs': [], 'avg': None, 'total': 0}

    recent = list(runs.order_by('-created_at')[:HISTORY_LIMIT])
    recent.reverse()          # на графике время идёт слева направо
    rows = [{
        'score': r.score,
        'accuracy': r.accuracy,
        'avg_correct_ms': r.avg_correct_ms,
        'created_at': r.created_at.isoformat(timespec='seconds'),
    } for r in recent]

    scores = list(runs.values_list('score', flat=True))
    correct_sum = sum(runs.values_list('correct_count', flat=True))
    attempts = sum(r.correct_count + r.wrong_count for r in runs)
    speeds = [r.avg_correct_ms for r in runs if r.avg_correct_ms]
    return {
        'mode': mode,
        'runs': rows,
        'total': total,
        'avg': {
            'score': round(sum(scores) / total),
            'accuracy': round(100 * correct_sum / attempts) if attempts else 0,
            # None, а не ноль: «в среднем ноль миллисекунд» — не факт, а
            # отсутствие факта, и пунктир по нему лёг бы по нулю.
            'avg_correct_ms': (int(sum(speeds) / len(speeds))
                               if speeds else None),
        },
    }


# Панель «Мои рекорды» смотрит на активность за столько дней.
ACTIVITY_DAYS = 30


def records_panel(user, mode='all'):
    u"""Всё, чем живёт панель «Мои рекорды». ВИДНА ТОЛЬКО ЕЁ ХОЗЯИНУ.

    ⚠️ НОВЫХ ТАБЛИЦ НЕ ЗАВОДИМ. Всё считается из `GameResult`: разбивки по
    темам и по сложности лежат в нём полями (`topic_breakdown`,
    `difficulty_breakdown`), дуэли считает `duel_stats` по наборам. Вторая
    таблица разъехалась бы с фактом при первом же удалении забега руками —
    тот же довод, что у лидерборда (ADR 0056).

    ⚠️ `mode='all'` — это ВСЕ РЕЖИМЫ, а не «режим по умолчанию». Счёт Пули
    и Классики несравним (запасы времени отличаются вдесятеро), поэтому
    «лучший счёт» по всем режимам не считается вовсе: вместо него таблица
    рекордов по режимам, где каждый сравнивается сам с собой.

    Забегов нет — возвращается `runs: 0` и больше ничего: рисовать нули
    там, где игрок ещё не играл, значит выдумывать числа.
    """
    runs = GameResult.objects.filter(user=user,
                                     economy_version=config.ECONOMY_VERSION)
    if mode != 'all':
        runs = runs.filter(mode=mode)
    rows = list(runs.order_by('created_at'))
    if not rows:
        return {'mode': mode, 'runs': 0}

    attempts = sum(r.correct_count + r.wrong_count for r in rows)
    correct = sum(r.correct_count for r in rows)
    speeds = [r.avg_correct_ms for r in rows if r.avg_correct_ms]
    best = max(rows, key=lambda r: (r.score, r.created_at))

    # ── График всех раундов: точка на раунд плюс рекорд НА ТОТ ДЕНЬ ──
    # Линия рекорда строится нарастающим максимумом по порядку игры: она
    # показывает, когда игрок себя обошёл, а не сегодняшний потолок.
    timeline = []
    running_best = 0
    for r in rows:
        running_best = max(running_best, r.score)
        timeline.append({
            'score': r.score,
            'best': running_best,
            'mode': r.mode,
            'at': r.created_at.isoformat(timespec='seconds'),
        })

    # ── Таблица рекордов по режимам ──
    by_mode = {}
    for r in rows:
        cell = by_mode.setdefault(r.mode, {
            'mode': r.mode,
            'title': config.MODES.get(r.mode, {}).get('title', r.mode),
            'score': 0, 'combo': 1.0, 'correct': 0, 'attempts': 0, 'runs': 0})
        cell['runs'] += 1
        cell['score'] = max(cell['score'], r.score)
        cell['combo'] = max(cell['combo'], r.max_combo or 1.0)
        cell['correct'] += r.correct_count
        cell['attempts'] += r.correct_count + r.wrong_count
    mode_rows = []
    for key in config.MODES:
        cell = by_mode.get(key)
        if not cell:
            continue
        cell['accuracy'] = (round(100 * cell['correct'] / cell['attempts'])
                            if cell['attempts'] else 0)
        mode_rows.append(cell)

    # ── Точность по темам и по сложности за всё время ──
    topics = {}
    for r in rows:
        for cell in (r.topic_breakdown or []):
            name = cell.get('topic')
            if not name:
                continue
            acc = topics.setdefault(name, {'correct': 0, 'wrong': 0})
            acc['correct'] += cell.get('correct', 0)
            acc['wrong'] += cell.get('wrong', 0)
    topic_rows = []
    for name, cell in topics.items():
        tries = cell['correct'] + cell['wrong']
        if not tries:
            continue
        topic_rows.append({'topic': name, 'correct': cell['correct'],
                           'total': tries,
                           'accuracy': round(100 * cell['correct'] / tries)})
    topic_rows.sort(key=lambda t: (t['accuracy'], -t['total']))

    diff = {}
    for r in rows:
        for cell in (r.difficulty_breakdown or []):
            key = cell.get('key')
            if not key:
                continue
            acc = diff.setdefault(key, {'key': key,
                                        'title': cell.get('title', key),
                                        'correct': 0, 'total': 0})
            acc['correct'] += cell.get('correct', 0)
            acc['total'] += cell.get('total', 0)
    diff_rows = [dict(v, accuracy=(round(100 * v['correct'] / v['total'])
                                   if v['total'] else 0))
                 for v in diff.values() if v['total']]

    # ── Активность за 30 дней: сколько раундов в день ──
    since = timezone.now().date() - datetime.timedelta(days=ACTIVITY_DAYS - 1)
    per_day = {}
    for r in rows:
        day = timezone.localtime(r.created_at).date()
        if day >= since:
            per_day[day] = per_day.get(day, 0) + 1
    activity = [{'date': (since + datetime.timedelta(days=i)).isoformat(),
                 'count': per_day.get(since + datetime.timedelta(days=i), 0)}
                for i in range(ACTIVITY_DAYS)]

    # ── Место в таблице и разрыв до соседа сверху ──
    place = None
    board_mode = mode if mode != 'all' else config.DEFAULT_MODE
    row = my_row(user, board_mode, 'all', 'score')
    if row:
        ahead = (base_queryset(board_mode, 'all', 'score')
                 .values('user').annotate(best=Max('score'))
                 .filter(best__gt=row['value']).order_by('best')
                 .values_list('best', flat=True).first())
        place = {
            'mode': board_mode,
            'place': row['place'],
            'value': row['value'],
            'total_players': total_players(board_mode, 'all', 'score'),
            # Разрыв до соседа СВЕРХУ. Первый в таблице — соседа нет, и
            # ноль тут означал бы «догонять некого», а не «догнал».
            'gap': (ahead - row['value']) if ahead is not None else None,
        }

    return {
        'mode': mode,
        'runs': len(rows),
        'ranked_runs': sum(1 for r in rows if r.ranked),
        'best_score': best.score,
        'best_score_at': best.created_at.isoformat(timespec='seconds'),
        'best_score_mode': config.MODES.get(best.mode, {}).get('title',
                                                              best.mode),
        'accuracy': round(100 * correct / attempts) if attempts else 0,
        'avg_correct_ms': int(sum(speeds) / len(speeds)) if speeds else None,
        'timeline': timeline,
        'mode_rows': mode_rows,
        'topic_rows': topic_rows,
        'difficulty_rows': diff_rows,
        'activity': activity,
        'place': place,
        'duels': duel_stats(user),
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
