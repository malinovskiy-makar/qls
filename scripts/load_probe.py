# -*- coding: utf-8 -*-
"""Нагрузочная проба: не сертификация, а поиск взрывающихся адресов.

⚠️ ЭТО НЕ ЗАМЕР ПРОИЗВОДИТЕЛЬНОСТИ БОЯ, И ЧИСЛА ОТСЮДА НЕЛЬЗЯ НЕСТИ В
ОТЧЁТ КАК «САЙТ ДЕРЖИТ N». Локальная машина, `runserver` (он многопоточный,
но не gunicorn), SQLite вместо PostgreSQL, отладочные настройки. Цель одна:
найти адрес, который на фоне соседей отвечает в разы дольше, — это почти
всегда запрос в цикле, а не «медленная страница».

Порогов здесь нет намеренно: сравнивать надо адреса между собой, а не с
выдуманным числом.

Запуск: venv313/Scripts/python.exe scripts/load_probe.py [порт] [клиентов] [запросов]
"""
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

PORT = sys.argv[1] if len(sys.argv) > 1 else '8901'
CLIENTS = int(sys.argv[2]) if len(sys.argv) > 2 else 30
ROUNDS = int(sys.argv[3]) if len(sys.argv) > 3 else 10
BASE = 'http://127.0.0.1:%s' % PORT

BOT_STUDENT = ('shot_bot', 'probebot-local-2026')
BOT_TEACHER = ('shot_bot_teacher', 'probebot-local-2026')

# Адрес → под кем ходим. Гость там, где страница публичная.
TARGETS = [
    ('/', None),
    ('/catalog/', None),
    ('/catalog/?q=монополия', None),
    ('/olympiads/', None),
    ('/game/', None),
    ('/calc2/', None),
    ('/textbook/', None),
    ('/profile/stats/', BOT_STUDENT),
    ('/student/', BOT_STUDENT),
    ('/teacher/groups/', BOT_TEACHER),
]


def login_once(creds):
    """Вход ОДИН раз на роль; клиентам раздаётся готовая кука.

    ⚠️ Входить в каждом потоке нельзя: у входа стоит ограничение частоты, и
    тридцать входов подряд с одного адреса упрутся в него. Сессии стали бы
    гостевыми, кабинет отдал бы редирект на вход — и проба замерила бы
    страницу входа, приняв её за кабинет. Ровно на этом уже спотыкались
    в Фазе 0.
    """
    session = requests.Session()
    session.get(BASE + '/login/', timeout=30)
    session.post(BASE + '/login/',
                 data={'username': creds[0], 'password': creds[1],
                       'csrfmiddlewaretoken': session.cookies.get('csrftoken', '')},
                 headers={'Referer': BASE + '/login/'}, timeout=30)
    cookie = session.cookies.get('sessionid')
    assert cookie, 'не вошли ролью %s' % creds[0]
    return cookie


COOKIES = {}


def hammer(url, creds):
    """CLIENTS параллельных клиентов × ROUNDS запросов."""
    times = []
    codes = {}
    if creds is not None and creds[0] not in COOKIES:
        COOKIES[creds[0]] = login_once(creds)

    def one(_):
        session = requests.Session()
        if creds is not None:
            session.cookies.set('sessionid', COOKIES[creds[0]])
        local = []
        for _ in range(ROUNDS):
            start = time.perf_counter()
            try:
                response = session.get(BASE + url, timeout=60)
                code = response.status_code
            except Exception:            # noqa: BLE001
                code = 0
            local.append((time.perf_counter() - start) * 1000)
            codes[code] = codes.get(code, 0) + 1
        return local

    with ThreadPoolExecutor(max_workers=CLIENTS) as pool:
        for chunk in pool.map(one, range(CLIENTS)):
            times.extend(chunk)
    times.sort()
    return times, codes


def percentile(values, share):
    if not values:
        return 0
    index = min(len(values) - 1, int(len(values) * share))
    return values[index]


def preflight():
    """Один спокойный заход по каждому адресу ДО нагрузки.

    Смысл — доказать, что замеряется та страница, что заявлена: кабинет,
    а не редирект на вход. Без этого проба радостно замерила бы форму
    входа тридцатью потоками и доложила прекрасные числа.
    """
    bad = []
    for url, creds in TARGETS:
        if creds is not None and creds[0] not in COOKIES:
            COOKIES[creds[0]] = login_once(creds)
        session = requests.Session()
        if creds is not None:
            session.cookies.set('sessionid', COOKIES[creds[0]])
        response = session.get(BASE + url, timeout=60)
        where = response.url[len(BASE):]
        mark = 'ок'
        if response.status_code != 200 or '/login' in where:
            mark = 'ПЛОХО %s → %s' % (response.status_code, where)
            bad.append(url)
        print('  %-26s %s' % (url[:26], mark))
    if bad:
        raise SystemExit('проба остановлена: %s' % ', '.join(bad))


def alone(url, creds):
    """Три спокойных запроса одним клиентом — медиана.

    Без этой колонки числа под нагрузкой не читаются: 50 секунд могут
    означать и «страница сама по себе тяжёлая», и «страница нормальная, но
    складывается от тридцати клиентов». Это разные болезни.
    """
    session = requests.Session()
    if creds is not None:
        session.cookies.set('sessionid', COOKIES[creds[0]])
    times = []
    for _ in range(3):
        start = time.perf_counter()
        session.get(BASE + url, timeout=60)
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def main():
    print('Проверка адресов до нагрузки:')
    preflight()
    print()
    print('клиентов %d, запросов на клиента %d, всего на адрес %d'
          % (CLIENTS, ROUNDS, CLIENTS * ROUNDS))
    print('%-26s %9s %8s %8s %8s   %s'
          % ('адрес', 'один, мс', 'p50, мс', 'p95, мс', 'макс', 'коды'))
    worst = []
    total_5xx = 0
    for url, creds in TARGETS:
        solo = alone(url, creds)
        times, codes = hammer(url, creds)
        p50 = percentile(times, .50)
        p95 = percentile(times, .95)
        bad = sum(n for c, n in codes.items() if c >= 500 or c == 0)
        total_5xx += bad
        print('%-26s %9.0f %8.0f %8.0f %8.0f   %s'
              % (url[:26], solo, p50, p95, max(times), codes))
        worst.append((p95, solo, url))
    worst.sort(reverse=True)
    print()
    print('ОТВЕТОВ 5xx И ОБРЫВОВ: %d' % total_5xx)
    print('Самые долгие по p95: %s'
          % ', '.join('%s (%.0f мс)' % (u, p) for p, _s, u in worst[:3]))
    median95 = statistics.median([p for p, _s, _u in worst])
    for p, solo, u in worst:
        if median95 and p > median95 * 5:
            # Без эмодзи намеренно: вывод уходит в файл в кодировке консоли
            # Windows, и на «внимание» скрипт падал ровно в этой строке,
            # уже посчитав все числа.
            print('ВНИМАНИЕ: %s — p95 в %.1f раза дольше медианы; '
                  'одним клиентом %.0f мс, то есть %s'
                  % (u, p / median95, solo,
                     'страница тяжёлая сама по себе'
                     if solo > median95 else 'складывается от нагрузки'))
    return 1 if total_5xx else 0


if __name__ == '__main__':
    sys.exit(main())
