"""Таблица лучших попыток тренажёра ВП (решение владельца 22.09.2026).

В таблицу идёт ЛУЧШАЯ из зачётных попыток человека: зачётная — первая попытка
по варианту с таймером (`VPAttempt.is_ranked`, ставится в `views.start`). Повторные
прохождения и работы без таймера — тренировка, в таблицу не идут. Порядок: балл вниз,
при равном балле — меньше потраченного времени, затем раньше сдал, затем меньший id.
Гостей в таблице нет: у их попыток нет пользователя.

С 2 тура таблиц несколько: ОТДЕЛЬНАЯ на каждый тур и класс (решение владельца
24.10.2026: 9, 10 и 11 класс 2 тура). Правило отбора одно на все — это модуль.
Без тура и класса таблица общая, как была у 1 тура.

⚠️ ЭТО ЕДИНСТВЕННОЕ МЕСТО, ГДЕ РЕШАЕТСЯ, ЧТО ТАКОЕ ТАБЛИЦА. Медалей, HTML и слов
здесь нет — их рисует шаблон; места считаются подряд, с единицы, без пропусков.
"""
import math

from vp import config
from vp.models import VPAttempt

#: Сколько строк показывает посадочная.
TOP = 10


def limit_seconds(attempt):
    """Лимит времени попытки на время, секунды.

    ⚠️ Округляем ВВЕРХ: `started_at` ставит база (`auto_now_add`) на доли секунды
    позже, чем считался `expires_at`, и `int()` дал бы «29:59 из 30:00».
    """
    return math.ceil((attempt.expires_at - attempt.started_at).total_seconds())


def spent_seconds(attempt):
    """Потрачено секунд: от старта до сдачи, не больше длительности варианта.

    Автосдача — весь лимит: работа шла до конца, даже если участник ушёл.
    Несданную попытку сюда не передают.
    """
    spent = int((attempt.submitted_at - attempt.started_at).total_seconds())
    if not attempt.with_timer or attempt.expires_at is None:
        return max(0, spent)
    limit = limit_seconds(attempt)
    return max(0, min(limit if attempt.is_auto_submitted else spent, limit))


def ranked_attempts(tour=None, band=None):
    """Сданные зачётные попытки вошедших — всё, из чего строится таблица.

    ⚠️ Только по ОПУБЛИКОВАННЫМ вариантам (24.09.2026): попытки сотрудников на
    черновиках иначе попадали в публичную таблицу. `tour` / `band` — какая таблица.
    """
    attempts = (VPAttempt.objects
                .filter(is_ranked=True, submitted_at__isnull=False, user__isnull=False,
                        variant__is_published=True)
                .select_related('user', 'variant'))
    if tour is not None:
        attempts = attempts.filter(variant__tour=tour)
    if band is not None:
        attempts = attempts.filter(variant__grade_band=band)
    return attempts


def close_lapsed_ranked():
    """Сдать зачётные попытки, время которых вышло, — перед построением таблицы.

    ⚠️ ЗАЧЕМ (24.09.2026). Фоновой задачи нет: просроченная попытка сдавалась,
    только когда её владелец сам открывал страницу ВП. Чужая брошенная зачётная
    попытка так и висела несданной и в таблицу не попадала. Одним запросом
    находим кандидатов (срок прошёл), сдаёт их то же правило автосдачи, что и
    везде (`views._lapsed` с запасом на последний ответ, `views._finalize`).
    """
    from django.utils import timezone

    from vp import views

    for attempt in VPAttempt.objects.filter(is_ranked=True, submitted_at__isnull=True,
                                            expires_at__lt=timezone.now()):
        if views._lapsed(attempt):
            views._finalize(attempt, auto=True)


def _key(attempt):
    """Ключ сортировки: балл вниз, время вверх, раньше сдал, меньший id."""
    return (-(attempt.score or 0), spent_seconds(attempt),
            attempt.submitted_at, attempt.pk)


def rows(tour=None, band=None):
    """Все строки таблицы — по одной на человека, уже с местами.

    Ключи строки: `place`, `user`, `name` (логин, как в Wecon Rush), `band`
    (`variant.grade_band`), `score`, `seconds`, `attempt`.
    """
    close_lapsed_ranked()
    best = {}
    for attempt in ranked_attempts(tour, band):
        key = _key(attempt)
        current = best.get(attempt.user_id)
        if current is None or key < current[0]:
            best[attempt.user_id] = (key, attempt)
    ordered = sorted(best.values(), key=lambda pair: pair[0])
    return [{
        'place': place,
        'user': attempt.user,
        'name': attempt.user.username,
        'band': attempt.variant.grade_band,
        'score': attempt.score,
        'seconds': spent_seconds(attempt),
        'attempt': attempt,
    } for place, (_, attempt) in enumerate(ordered, 1)]


def top(me=None, limit=TOP, tour=None, band=None):
    """Что показывает посадочная.

    Возвращает `(строки топа, моя строка вне топа или None, людей в таблице,
    зачётных сданных попыток)`. Своя строка приходит отдельно только тогда, когда
    она НЕ попала в топ: иначе человек увидел бы себя дважды.
    """
    all_rows = rows(tour, band)
    head = all_rows[:limit]
    mine = None
    if me is not None and getattr(me, 'is_authenticated', False):
        mine = next((r for r in all_rows if r['user'].pk == me.pk), None)
        if mine is not None and mine['place'] <= limit:
            mine = None
    return head, mine, len(all_rows), ranked_attempts(tour, band).count()


def tables(tour=None):
    """Таблицы тура (по умолчанию текущего): `[(класс или None, подпись), …]`.

    У 1 тура таблица одна на все классы (так она жила в сезоне 2026/27), у 2 тура —
    по классу.
    """
    tour = config.CURRENT_TOUR if tour is None else tour
    if tour == 1:
        return [(None, '')]
    return list(config.bands(tour))


def my_rows(user, tour=None):
    """Строки человека во всех таблицах тура: `[(класс, строка), …]`."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return []
    tour = config.CURRENT_TOUR if tour is None else tour
    found = []
    for band, _ in tables(tour):
        row = next((r for r in rows(tour, band) if r['user'].pk == user.pk), None)
        if row is not None:
            found.append((band, row))
    return found


def my_best(user, tour=None):
    """Лучшая зачётная сданная попытка человека в таблицах тура и её место (в таблице
    своего класса), или `(None, None)`. Из нескольких классов — лучшая по тому же
    ключу, что и порядок таблицы."""
    found = my_rows(user, tour)
    if not found:
        return None, None
    _, row = min(found, key=lambda pair: _key(pair[1]['attempt']))
    return row['attempt'], row['place']


def place_of(attempt):
    """Место этой попытки в таблице её тура и класса или `None`, если она в таблицу не идёт.

    Место есть только у той попытки, которая для своего человека ЛУЧШАЯ:
    строка на человека одна, вторая зачётная попытка места не получает.
    """
    if not attempt.is_ranked or attempt.submitted_at is None or attempt.user_id is None:
        return None
    tour = attempt.variant.tour
    band = None if tour == 1 else attempt.variant.grade_band
    row = next((r for r in rows(tour, band) if r['user'].pk == attempt.user_id), None)
    return row['place'] if row and row['attempt'].pk == attempt.pk else None
