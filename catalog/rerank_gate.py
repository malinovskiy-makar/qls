# -*- coding: utf-8 -*-
"""Кто и когда платит за переранжирование поиска (24.09.2026, ADR 0128).

⚠️ ЗАЧЕМ. Потолок сортировщика — $0,50 в сутки (~205 вызовов). 17–19.09
краулеры (Amazonbot, Google) выбирали его к утру, и живые ученики до конца
суток искали без переранжирования. Проверка User-Agent (19.09) — страховка,
а не барьер: заголовок подделывается, список ботов не бывает полным.

Барьеры здесь, по порядку:

1. **Платит только запрос собственного скрипта страницы** — заголовок
   `X-Weco-Search: 1` (ставят `catalog_filters.js` и `stol.js`). Полная
   загрузка страницы не платит вовсе (статус `deferred`): бот, который ходит
   по ссылкам без JS, заплатить не может, какой бы User-Agent ни назвал.
2. **Есть кука посетителя** (`weco_vid`) и User-Agent не похож на бота
   (пустой — тоже бот, но только здесь, не для страницы) — статус `bot`.
3. **Квоты реально оплаченных вызовов** по московским суткам: посетитель
   40, вошедший 80, адрес 150 (`SMART_SEARCH_QUOTA_*`) — статус `quota`.
   Попадание в общий кэш квоту не тратит.
4. **Потолок в деньгах** (`AI_DAILY_COST_CAPS['search_rerank']`) — статус
   `budget` и одна строка WARNING в лог за сутки.

Счётчики — в кэше Django (на бою Redis, база 0), ключ живёт до конца суток.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from problems import ratelimit

from . import search_log, seo

logger = logging.getLogger(__name__)

#: Заголовок, который ставит собственный скрипт страницы (`X-Weco-Search: 1`).
HEADER = 'HTTP_X_WECO_SEARCH'


def refusal(request):
    """Почему этому запросу платить нельзя ('deferred' / 'bot') или None.

    Порядок важен: полная загрузка страницы («заголовка нет») — самый частый
    случай, и отвечать на него надо, не трогая ни кэш, ни базу.
    """
    if request is None or request.META.get(HEADER) != '1':
        return 'deferred'
    if seo.is_rerank_bot(request):
        return 'bot'
    if not search_log._visitor(request):
        return 'bot'
    return None


def _day():
    """(метка московских суток, секунд до их конца + час запаса)."""
    now = timezone.localtime(timezone.now())
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0,
                                                 microsecond=0)
    return now.strftime('%Y%m%d'), int((tomorrow - now).total_seconds()) + 3600


def _counters(request):
    """[(ключ, предел)] — какие квоты касаются этого запроса.

    Вошедший считается по аккаунту, гость — по куке посетителя; адрес — у
    всех. Кука у вошедшего тоже есть, но квота посетителя к нему не
    применяется: иначе 40 срезало бы его 80.
    """
    day, _ttl = _day()
    rows = []
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        rows.append(('rrq:%s:user:%s' % (day, user.pk),
                     settings.SMART_SEARCH_QUOTA_USER))
    else:
        rows.append(('rrq:%s:vid:%s' % (day, search_log._visitor(request)),
                     settings.SMART_SEARCH_QUOTA_VISITOR))
    rows.append(('rrq:%s:ip:%s' % (day, ratelimit.client_ip(request)),
                 settings.SMART_SEARCH_QUOTA_IP))
    return rows


def over_quota(request):
    """Выбрана ли хоть одна квота этого запроса."""
    rows = _counters(request)
    values = cache.get_many([key for key, _limit in rows])
    return any((values.get(key) or 0) >= limit for key, limit in rows)


def note_paid(request):
    """Засчитать РЕАЛЬНО оплаченный вызов во все квоты запроса."""
    _day_label, ttl = _day()
    for key, _limit in _counters(request):
        if cache.add(key, 1, ttl):
            continue
        try:
            cache.incr(key)
        except ValueError:          # ключ истёк между add и incr
            cache.set(key, 1, ttl)


def budget_refusal():
    """'budget', если суточный потолок выбран, иначе None.

    При первом отказе за сутки — одна строка WARNING: время, сумма, число
    вызовов. Дальше молчим: строка на каждый поиск утопила бы журнал.
    """
    from problems.ai import core
    from problems.models import AiUsageLog

    from .rerank import USAGE_KIND

    if not core.budget_exceeded(USAGE_KIND):
        return None
    day, ttl = _day()
    if cache.add('rrq:%s:budget_warned' % day, 1, ttl):
        start = timezone.localtime(timezone.now()).replace(
            hour=0, minute=0, second=0, microsecond=0)
        calls = AiUsageLog.objects.filter(kind=USAGE_KIND,
                                          created_at__gte=start).count()
        logger.warning(
            'умный поиск: исчерпан суточный потолок $%s в %s — потрачено '
            '$%.4f, вызовов %d; до конца суток поиск без переранжирования',
            core.daily_cost_cap(USAGE_KIND),
            timezone.localtime(timezone.now()).strftime('%H:%M'),
            core.spent_today(USAGE_KIND), calls)
    return 'budget'
