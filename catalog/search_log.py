# -*- coding: utf-8 -*-
"""Журнал поисковых запросов каталога и оценка выдачи (18.09.2026, ADR 0117).

Зачем: до беты текст запроса не сохранялся нигде — в событиях только длина,
а сервер нарочно вырезал его из адреса. Без текста качество поиска после
беты не разобрать.

⚠️ СТРОКУ ЗАВОДИТ ТОЛЬКО ПОЛНЫЙ РЕНДЕР (`problem_list`). Контекст каталога
собирается одним кодом и для страницы, и для живого обновления фильтров
(`api_filter_state`); пиши журнал оба — один запрос человека дал бы по
строке на каждое нажатие фильтра. `api_filter_state` пишет только по явному
`log=1` (им пользуется «Стол», нынешний каталог его не шлёт).

⚠️ СКЛЕЙКА: тот же посетитель и та же строка запроса моложе DEDUP_SECONDS —
новая строка не заводится, возвращается номер прежней (перезагрузка,
«назад», «показать ещё»).

Всё в try/except, как у журнала событий: упавший журнал не ломает каталог.
"""
import logging
from datetime import timedelta

from django.utils import timezone

from problems.views_platform import TRACK_COOKIE, _VISITOR_RE

logger = logging.getLogger(__name__)

DEDUP_SECONDS = 30
LOG_PARAM = 'log'
TOP_IDS = 10
QUERY_MAX = 300
RATING_TEXT_MAX = 300


def _visitor(request):
    """Кука посетителя, если она похожа на нашу; иначе пусто."""
    value = request.COOKIES.get(TRACK_COOKIE, '')
    return value if _VISITOR_RE.fullmatch(value) else ''


def _norm(query):
    return query.strip().lower()


def log_search(request, context):
    """Записать поиск из собранного контекста каталога → id строки или None."""
    from problems.models_platform import SearchLog

    if not context.get('searched'):
        return None
    try:
        query = context['query'].strip()[:QUERY_MAX]
        user = request.user if request.user.is_authenticated else None
        visitor = _visitor(request)
        if user or visitor:
            owner = {'user': user} if user else {'visitor': visitor}
            since = timezone.now() - timedelta(seconds=DEDUP_SECONDS)
            for pk, text in (SearchLog.objects.filter(ts__gte=since, **owner)
                             .order_by('-ts').values_list('pk', 'query')):
                if _norm(text) == _norm(query):
                    return pk
        entry = SearchLog.objects.create(
            user=user, visitor=visitor,
            session_key=(request.session.session_key or '')[:40],
            query=query, status=context.get('smart_search_status') or '',
            ms=context.get('smart_search_ms'), total=context.get('total') or 0,
            degraded=bool(context.get('degraded')),
            # Карточки уже прошли шлюз качества: скрытое сюда не попадает.
            top_ids=[card['problem'].pk for card in context['cards'][:TOP_IDS]])
        return entry.pk
    except Exception:   # noqa: BLE001 — журнал не важнее каталога
        logger.exception('Журнал поиска не записан')
        return None


def rate(request, log_id, rating, text):
    """Оценка своей строки журнала → True; чужая или нет такой → False.

    Своя — совпала кука посетителя или вошедший пользователь. Чужую не
    отличаем от несуществующей: номер строки не должен ничего раскрывать.
    Повторная оценка перезаписывает прежнюю.
    """
    from problems.models_platform import SearchLog

    entry = SearchLog.objects.filter(pk=log_id).first()
    if entry is None:
        return False
    visitor = _visitor(request)
    mine = ((visitor and entry.visitor == visitor)
            or (request.user.is_authenticated and entry.user_id == request.user.pk))
    if not mine:
        return False
    entry.rating = rating
    entry.rated_at = timezone.now()
    entry.rating_text = text
    entry.save(update_fields=['rating', 'rated_at', 'rating_text'])
    return True
