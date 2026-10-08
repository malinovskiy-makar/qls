"""Зонд нагрузки «Сайт не встаёт»: ждут ли обычные страницы, пока ИИ думает.

Шлёт настоящие HTTP-запросы в gunicorn: K вопросов к чату разом и несколько
клиентов, которые всё окно дёргают лёгкие страницы. Меряет время лёгких
страниц и выносит вердикт. Сеть — только `http.client` стандартной
библиотеки; база — только в команде `ai_load_probe` (сессия входа).

⚠️ Запросы идут прямо в gunicorn, мимо nginx, поэтому зонд сам ставит то,
что поставил бы nginx: `Host` и `X-Forwarded-Proto: https` (иначе боевые
настройки ответят редиректом на https), а для POST — `Origin` и `Referer`
(проверка CSRF на «защищённом» запросе).

Правила счёта — docs/SERVER.md, «Воркеры и потоки»:
* перцентиль — ближайший ранг, как в отчёте беты (docs/AI_BETA.md);
* PASS — P95 лёгких ≤ max(1,0 с; 3 × опорный P95 при K = 0), ни одного
  ответа лёгких страниц кроме 200 и все K ответов ИИ получены.
"""
import http.client
import json
import math
import threading
import time
import uuid
from urllib.parse import urlsplit

PAGE_PATHS = ('/healthz/', '/', '/catalog/', '/catalog/problem/{id}/')
CHAT_PATH = '/catalog/api/chat/'
CHAT_MESSAGE = 'Как решать?'
FLOOR_SECONDS = 1.0
BASELINE_FACTOR = 3
PAGE_TIMEOUT = 180
AI_TIMEOUT = 300
#: ИИ стартует чуть раньше: к первому запросу страниц места уже заняты.
AI_HEAD_START = 1.0


def percentile(values, p):
    """Ближайший ранг: элемент номер ⌈p·n/100⌉ — значение, которое реально было."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(1, math.ceil(p * len(ordered) / 100)) - 1]


def summarize(pages, ai):
    """pages, ai: [{'status', 'seconds', ...}] → сводка числами."""
    page_seconds = [r['seconds'] for r in pages]
    ai_ok = [r for r in ai if r.get('ok')]
    ai_seconds = [r['seconds'] for r in ai]
    return {
        'pages': {'requests': len(pages),
                  'errors': sum(1 for r in pages if r['status'] != 200),
                  'p50': round(percentile(page_seconds, 50), 3),
                  'p95': round(percentile(page_seconds, 95), 3),
                  'max': round(max(page_seconds), 3) if page_seconds else 0.0},
        'ai': {'sent': len(ai), 'ok': len(ai_ok), 'errors': len(ai) - len(ai_ok),
               'p50': round(percentile(ai_seconds, 50), 3),
               'max': round(max(ai_seconds), 3) if ai_seconds else 0.0},
    }


def threshold(baseline_p95):
    """Потолок P95 лёгких страниц: max(1,0 с; 3 × опорный P95)."""
    return max(FLOOR_SECONDS, BASELINE_FACTOR * (baseline_p95 or 0.0))


def verdict(summary, k, baseline_p95):
    """PASS / FAIL и причины словами."""
    reasons = []
    limit = threshold(baseline_p95)
    if summary['pages']['p95'] > limit:
        reasons.append('P95 лёгких %.2f с > %.2f с' % (summary['pages']['p95'], limit))
    if summary['pages']['errors']:
        reasons.append('ошибок лёгких страниц: %d' % summary['pages']['errors'])
    if summary['ai']['ok'] != k:
        reasons.append('ответов ИИ %d из %d' % (summary['ai']['ok'], k))
    return ('FAIL' if reasons else 'PASS'), reasons


# ── Сеть ────────────────────────────────────────────────────────────────

class Target:
    """Куда стучимся: адрес gunicorn и имя сайта для заголовка Host."""

    def __init__(self, base, host):
        parts = urlsplit(base)
        self.netloc = parts.hostname or '127.0.0.1'
        self.port = parts.port or 80
        self.host = host

    def headers(self, cookies=None, extra=None):
        out = {'Host': self.host, 'X-Forwarded-Proto': 'https',
               'User-Agent': 'weco-ai-load-probe/1'}
        if cookies:
            out['Cookie'] = '; '.join('%s=%s' % kv for kv in cookies.items())
        out.update(extra or {})
        return out

    def request(self, method, path, cookies=None, body=None, extra=None, timeout=PAGE_TIMEOUT):
        """→ (статус, тело, set-cookie словарём, секунды). Сбой сети — статус 0."""
        started = time.monotonic()
        conn = http.client.HTTPConnection(self.netloc, self.port, timeout=timeout)
        try:
            conn.request(method, path, body=body, headers=self.headers(cookies, extra))
            response = conn.getresponse()
            data = response.read()
            jar = {}
            for name, value in response.getheaders():
                if name.lower() == 'set-cookie':
                    key, _, rest = value.partition('=')
                    jar[key.strip()] = rest.split(';', 1)[0]
            return response.status, data, jar, time.monotonic() - started
        except (OSError, http.client.HTTPException) as exc:
            return 0, str(exc).encode('utf-8'), {}, time.monotonic() - started
        finally:
            conn.close()


def page_client(target, paths, stop_at, out, lock):
    """Крутит лёгкие страницы до `stop_at`. Кука своя: сессия гостя одна на клиента."""
    jar = {}
    i = 0
    while time.monotonic() < stop_at:
        path = paths[i % len(paths)]
        i += 1
        status, _body, cookies, seconds = target.request('GET', path, cookies=jar)
        jar.update(cookies)
        with lock:
            out.append({'path': path, 'status': status, 'seconds': seconds})


def csrf_token(target, session_cookies, problem_id):
    """csrftoken от сайта: GET страницы задачи с сессией входа."""
    status, _body, cookies, _s = target.request(
        'GET', PAGE_PATHS[3].format(id=problem_id), cookies=session_cookies)
    token = cookies.get('csrftoken')
    if status != 200 or not token:
        raise RuntimeError('не получил csrftoken: GET страницы задачи → %s' % status)
    return token


def ai_client(target, cookies, token, problem_id, out, lock):
    body = json.dumps({'problem_id': problem_id, 'message': CHAT_MESSAGE, 'mode': 'method',
                       'history': [], 'thread': str(uuid.uuid4())}).encode('utf-8')
    origin = 'https://%s' % target.host
    extra = {'Content-Type': 'application/json', 'X-CSRFToken': token, 'Origin': origin,
             'Referer': origin + PAGE_PATHS[3].format(id=problem_id)}
    status, data, _jar, seconds = target.request('POST', CHAT_PATH, cookies=cookies, body=body,
                                                 extra=extra, timeout=AI_TIMEOUT)
    ok, error = False, ''
    try:
        payload = json.loads(data.decode('utf-8'))
        ok = status == 200 and bool(payload.get('reply')) and not payload.get('error')
        error = payload.get('error') or ''
    except ValueError:
        error = data[:120].decode('utf-8', 'replace')
    with lock:
        out.append({'status': status, 'seconds': seconds, 'ok': ok, 'error': error})


def run(target, *, k, problem_id, session_cookies, page_clients=4, window=30.0,
        paths=PAGE_PATHS):
    """Один замер: K вопросов к ИИ разом + лёгкие страницы всё окно."""
    paths = [p.format(id=problem_id) for p in paths]
    pages, ai, lock = [], [], threading.Lock()
    threads = []
    if k:
        token = csrf_token(target, session_cookies, problem_id)
        cookies = dict(session_cookies, csrftoken=token)
        threads += [threading.Thread(target=ai_client, daemon=True,
                                     args=(target, cookies, token, problem_id, ai, lock))
                    for _ in range(k)]
        for t in threads:
            t.start()
        time.sleep(AI_HEAD_START)
    stop_at = time.monotonic() + window
    clients = [threading.Thread(target=page_client, daemon=True,
                                args=(target, paths, stop_at, pages, lock))
               for _ in range(page_clients)]
    for t in clients:
        t.start()
    for t in clients + threads:
        t.join()
    return pages, ai
