# -*- coding: utf-8 -*-
"""Поиск автозагрузки внешних хостов в отрендеренном HTML (аудит РКН).

Используется командой `scan_external_hosts` и сторожевым тестом
`catalog/tests/test_no_foreign_autoload.py`. Ищет АВТОЗАГРУЗКУ (src, href
у <link>/<script>/<iframe>, action, data-src, poster, url() в стилях) —
не обычные гиперссылки `<a href>`, которые пользователь кликает сам и
которые в трансграничную передачу не входят.

⚠️ `<a href>` НЕ СЧИТАЕТСЯ автозагрузкой. Тег вокруг атрибута приходится
разбирать явно (не только имя атрибута): у `<a>` то же имя атрибута
(`href`), что и у `<link>`, но семантика разная — первое требует клика
пользователя, второе браузер запрашивает сам при разборе страницы.
"""
import re

OWN_HOSTS = {
    'weconomics.site', 'weconomics.ai', 'dev.weconomics.ai',
    'localhost', '127.0.0.1', 'testserver',
}

# Не сетевые обращения, а строковые идентификаторы — фильтруем как шум.
# www.w3.org — пространство имён `xmlns` у inline SVG, браузер его не
# запрашивает.
NOT_A_REQUEST_HOSTS = {'www.w3.org'}

# Автозагрузка: тег и атрибут, которые браузер запрашивает сам, без клика.
_AUTOLOAD_TAG_ATTR = re.compile(
    r'''<(script|link|img|iframe|source|embed|track|form)\b[^>]*?\s
        (src|href|action|data-src|poster)\s*=\s*["']([^"']+)["']''',
    re.IGNORECASE | re.VERBOSE)

# Обычная гиперссылка — для отдельного учёта, не для вердикта.
_HYPERLINK_RE = re.compile(
    r'''<a\b[^>]*?\shref\s*=\s*["']([^"']+)["']''', re.IGNORECASE)

_URL_FUNC_RE = re.compile(r'''url\(\s*["']?([^"')]+)["']?\s*\)''', re.IGNORECASE)
_ABS_URL_RE = re.compile(r'''https?://[^\s"'()<>\\]+''', re.IGNORECASE)


def host_of(url):
    m = re.match(r'^https?://([^/]+)', url)
    if not m:
        return None
    return m.group(1).split('@')[-1].split(':')[0]


def is_own(host):
    if host is None:
        return True
    return any(host == h or host.endswith('.' + h) for h in OWN_HOSTS)


def _normalise(url):
    if url.startswith('//'):
        url = 'https:' + url
    return url


def autoload_hosts(html):
    """Внешние хосты, которые браузер запрашивает САМ (без клика).

    Возвращает список (host, url, где_нашли) — без дублей `<a href>`.
    """
    findings = []
    seen = set()

    for tag, attr, raw_url in _AUTOLOAD_TAG_ATTR.findall(html):
        url = _normalise(raw_url)
        if not url.startswith('http'):
            continue
        host = host_of(url)
        if is_own(host) or host in NOT_A_REQUEST_HOSTS:
            continue
        key = (host, url)
        if key not in seen:
            seen.add(key)
            findings.append((host, url, '<%s %s>' % (tag, attr)))

    for raw_url in _URL_FUNC_RE.findall(html):
        url = _normalise(raw_url)
        if not url.startswith('http'):
            continue
        host = host_of(url)
        if is_own(host) or host in NOT_A_REQUEST_HOSTS:
            continue
        key = (host, url)
        if key not in seen:
            seen.add(key)
            findings.append((host, url, 'url() в стиле'))

    return findings


def hyperlinks(html):
    """Обычные ссылки `<a href>` на внешние хосты — для отчёта, не для вердикта."""
    findings = []
    seen = set()
    for raw_url in _HYPERLINK_RE.findall(html):
        url = _normalise(raw_url)
        if not url.startswith('http'):
            continue
        host = host_of(url)
        if is_own(host) or host in NOT_A_REQUEST_HOSTS:
            continue
        key = (host, url)
        if key not in seen:
            seen.add(key)
            findings.append((host, url))
    return findings


# Страницы для аудита (фаза 2 «Аудит зарубежных обращений перед подачей
# уведомления в РКН», Notion-штаб). Список синхронизирован между командой
# `scan_external_hosts` и тестом `test_no_foreign_autoload.py`.
AUDIT_PAGES = [
    ('/', 'главная'),
    ('/catalog/', 'каталог'),
    ('/calc2/', 'калькулятор'),
    ('/login/', 'вход'),
    ('/register/', 'регистрация'),
    ('/game/', 'Wecon Rush'),
    ('/olympiads/', 'олимпиады'),
]
