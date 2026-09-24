# -*- coding: utf-8 -*-
"""Квота РАЗНЫХ задач на адрес и на аккаунт (24.09.2026, ADR 0129).

⚠️ ЗАЧЕМ. Условия задач открыты намеренно — иначе их не найдут Google и
Яндекс. Но открытые условия можно выкачать подряд, страница за страницей.
Лимит скорости nginx (60 страниц задач в минуту) замедляет, но не держит:
терпеливый скрипт за сутки при 60/мин уносит весь банк. Эта квота считает
не запросы, а РАЗНЫЕ задачи: человек, который возвращается к своим десяти
задачам, её не заметит, выгрузка упрётся.

| Кто | В час | В сутки |
|---|---|---|
| гость (по адресу) | 150 | 600 |
| вошедший (по аккаунту) | 300 | 1000 |

Числа — `SCRAPE_QUOTA_*` в настройках, переопределяются через `.env`.
Задача, уже открытая в этом окне, квоту не тратит и открывается всегда.

**Проверенные поисковые роботы не ограничиваются** — иначе пострадает поиск.
User-Agent говорит «Googlebot / YandexBot / bingbot» → обратный DNS адреса
(`*.googlebot.com`, `*.google.com`, `*.yandex.ru|net|com`, `*.search.msn.com`)
и прямое подтверждение на тот же адрес. Вердикт — в кэше на сутки. DNS
не ответил вовремя или упал — считаем обычным посетителем с обычными
(щедрыми) квотами и перепроверяем через 10 минут. Поддельный «Googlebot»
получает обычные квоты и строку в журнал `security`.

Счётчики — в кэше Django (на бою Redis): отметка «видел задачу» и счётчик
на окно. Для `scrape_report` подозрительные (от 50 разных задач за сутки)
складываются в список дня.
"""
import logging
import socket
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from problems import ratelimit

logger = logging.getLogger('security')

#: Что называет себя поисковым роботом, которого мы пускаем без квоты.
CLAIMS = ('googlebot', 'googleother', 'google-inspectiontool', 'adsbot-google',
          'yandex', 'bingbot')
#: Хвосты имени хоста, которыми подтверждается робот (обратный DNS).
VERIFIED_SUFFIXES = ('.googlebot.com', '.google.com', '.yandex.ru', '.yandex.net',
                     '.yandex.com', '.search.msn.com')
DNS_TIMEOUT = 1.5
VERDICT_SECONDS = 24 * 3600
RETRY_SECONDS = 600
#: От скольки разных задач за сутки субъект попадает в отчёт.
REPORT_FROM = 50

_dns_pool = ThreadPoolExecutor(max_workers=4)


def _claims_search_bot(request):
    agent = (request.META.get('HTTP_USER_AGENT') or '').lower()
    return any(claim in agent for claim in CLAIMS)


def _resolve(ip):
    """(имя хоста, адреса этого имени) — обратный и прямой DNS."""
    host = socket.gethostbyaddr(ip)[0].lower()
    addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    return host, addresses


def is_verified_search_bot(request):
    """Настоящий ли поисковый робот: User-Agent + обратный и прямой DNS."""
    if not _claims_search_bot(request):
        return False
    ip = ratelimit.client_ip(request)
    if not ip:
        return False
    key = 'sg:bot:%s' % ip
    verdict = cache.get(key)
    if verdict is not None:
        return verdict == '1'
    try:
        host, addresses = _dns_pool.submit(_resolve, ip).result(timeout=DNS_TIMEOUT)
    except (FuturesTimeout, OSError, UnicodeError):
        # DNS не ответил — обычный посетитель с обычными квотами (fail-open
        # в сторону квот, а не блокировки), перепроверим позже.
        cache.set(key, '0', RETRY_SECONDS)
        return False
    ok = host.endswith(VERIFIED_SUFFIXES) and ip in addresses
    cache.set(key, '1' if ok else '0', VERDICT_SECONDS)
    if not ok:
        logger.warning('scrape_guard: поддельный поисковый робот ip=%s host=%s ua=%r',
                       ip, host, request.META.get('HTTP_USER_AGENT', '')[:200])
    return ok


def _subject(request):
    """(вид, ключ, [(окно, секунд, предел)]) — кого и как считаем."""
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        return 'user', str(user.pk), [
            ('h', 3600, settings.SCRAPE_QUOTA_USER_HOUR),
            ('d', 86400, settings.SCRAPE_QUOTA_USER_DAY)]
    return 'ip', ratelimit.client_ip(request) or '-', [
        ('h', 3600, settings.SCRAPE_QUOTA_IP_HOUR),
        ('d', 86400, settings.SCRAPE_QUOTA_IP_DAY)]


def _window_label(window):
    now = timezone.localtime(timezone.now())
    return now.strftime('%Y%m%d%H') if window == 'h' else now.strftime('%Y%m%d')


def _bump(key, ttl):
    if cache.add(key, 1, ttl):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, ttl)
        return 1


def _remember_suspect(kind, ident):
    """Субъект дошёл до REPORT_FROM за сутки — в список дня для отчёта.

    Список меняется чтением-записью, а не атомарно: при гонке двух воркеров
    одна строка может потеряться. Для отчёта «кто выкачивает» это приемлемо,
    для самой квоты не важно вовсе — она считает своими счётчиками.
    """
    day = _window_label('d')
    key = 'sg:suspects:%s' % day
    suspects = cache.get(key) or []
    entry = '%s:%s' % (kind, ident)
    if entry not in suspects:
        suspects.append(entry)
        cache.set(key, suspects, 2 * 86400)


def check(request, problem_id):
    """None — можно; иначе причина отказа ('hour' / 'day').

    Засчитывает задачу, если она новая для окна. Уже открытая в окне задача
    проходит всегда и квоту не тратит.
    """
    if not settings.SCRAPE_GUARD_ENABLED or is_verified_search_bot(request):
        return None
    kind, ident, windows = _subject(request)
    for window, seconds, limit in windows:
        label = _window_label(window)
        seen = 'sg:seen:%s:%s:%s:%s:%s' % (kind, ident, window, label, problem_id)
        if cache.get(seen):
            continue
        count_key = 'sg:n:%s:%s:%s:%s' % (kind, ident, window, label)
        if (cache.get(count_key) or 0) >= limit:
            logger.warning('scrape_guard: квота разных задач (%s) %s=%s, задача %s',
                           window, kind, ident, problem_id)
            return 'hour' if window == 'h' else 'day'
    for window, seconds, _limit in windows:
        label = _window_label(window)
        seen = 'sg:seen:%s:%s:%s:%s:%s' % (kind, ident, window, label, problem_id)
        if cache.add(seen, 1, seconds + 3600):
            count = _bump('sg:n:%s:%s:%s:%s' % (kind, ident, window, label), seconds + 3600)
            if window == 'd' and count == REPORT_FROM:
                _remember_suspect(kind, ident)
    return None


def today_report():
    """[(вид, ключ, разных задач сегодня)] — для `scrape_report`, по убыванию."""
    day = _window_label('d')
    rows = []
    for entry in cache.get('sg:suspects:%s' % day) or []:
        kind, _sep, ident = entry.partition(':')
        count = cache.get('sg:n:%s:%s:d:%s' % (kind, ident, day)) or 0
        rows.append((kind, ident, count))
    return sorted(rows, key=lambda row: -row[2])
