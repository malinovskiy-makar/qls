# -*- coding: utf-8 -*-
"""Источник регистрации: откуда пришёл человек, заведший аккаунт (ADR 0133).

Две половины одного вопроса «какая ссылка приводит людей».

**Первое касание.** `FirstTouchMiddleware` на GET-запросе с UTM-меткой
запоминает метки, посадочную страницу, Referer и время в ПОДПИСАННОЙ куке на
90 дней. Кука, а не сессия: человек приходит из поста, уходит и
регистрируется через неделю — гостевая сессия к этому времени уже другая.
Первую метку не перезаписываем никогда: последнюю знает Метрика.

⚠️ КУКА `weco_src` — АНАЛИТИЧЕСКАЯ, СТАВИТСЯ ТОЛЬКО ПРИ `weco_consent=all`
(Политика cookie, раздел 2; часть Б, 09.10.2026). До согласия метки лежат в
СЕССИИ (необходимая кука) и при регистрации всё равно попадают в
`SignupSource`; когда человек нажимает «Разрешить», первый же запрос с
`weco_consent=all` переносит метки из сессии в куку. При «Только необходимые»
уже стоящую куку стирает сервер: она HttpOnly, скрипт её тронуть не может.

**Запись при регистрации.** `record_signup` заводит `SignupSource` на КАЖДЫЙ
новый аккаунт, даже без куки (метки пусты, вид регистрации заполнен).
Там же откладывается цель Метрики: регистрация кончается редиректом, своего
экрана у неё нет, поэтому имя цели ложится в сессию, а выводит её следующая
страница (`templates/_metrika.html` через `pop_goal`) — один раз.

⚠️ ЗНАЧЕНИЯ МЕТОК НА СТРАНИЦЫ САЙТА НЕ ВЫВОДЯТСЯ НИКОГДА. Это строки из
чужой ссылки; читает их только админка, а она экранирует сама.
"""
import base64
import json
import logging
import re
import secrets
import unicodedata
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

UTM_KEYS = ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term')
#: Всё, что едет из куки в `SignupSource`, кроме времени.
TEXT_FIELDS = UTM_KEYS + ('landing_path', 'referrer')
#: Потолок длины любого значения — и в куке, и в базе (поля по 100 символов).
MAX_LENGTH = 100

COOKIE_NAME = 'weco_src'
#: Ключ сессии, где метки первого касания ждут согласия на аналитические куки.
SESSION_KEY = 'first_touch'
COOKIE_SALT = 'problems.signup_source'
COOKIE_MAX_AGE = 90 * 24 * 60 * 60

# Цели Метрики. ⚠️ Имена РОВНО такие же заведены в интерфейсе счётчика:
# переименовать здесь — значит молча потерять цель там.
GOAL_BY_KIND = {
    'teacher': 'signup_teacher',
    'student': 'signup_student',
    'invited': 'signup_invited',
}
GOAL_SESSION_KEY = 'metrika_goal'
_TOKEN_RE = re.compile(r'[0-9a-f]{16}')


def _clip(value):
    """Строка из запроса: без управляющих символов, без пробелов по краям, ≤100.

    ⚠️ УПРАВЛЯЮЩИЕ СИМВОЛЫ ВЫРЕЗАЮТСЯ, А НЕ ПРОСТО ОБРЕЗАЕТСЯ ДЛИНА.
    PostgreSQL не принимает NUL в тексте вовсе: `?utm_source=%00` без этой
    чистки уронил бы регистрацию пятисоткой. Заодно уходят невидимые знаки
    форматирования (нулевой ширины, смена направления письма).
    """
    text = ''.join(ch for ch in str(value or '')
                   if unicodedata.category(ch)[0] != 'C')
    return text.strip()[:MAX_LENGTH].strip()


def capture(request):
    """Метки первого касания из запроса или None, если меток нет.

    Пустая метка (`?utm_source=`) меткой не считается: иначе ничего не
    говорящая ссылка заняла бы место первого касания навсегда.
    """
    data = {key: _clip(request.GET.get(key)) for key in UTM_KEYS}
    if not any(data.values()):
        return None
    data['landing_path'] = _clip(request.path)
    data['referrer'] = _clip(request.META.get('HTTP_REFERER'))
    data['first_seen_at'] = timezone.now().isoformat()
    return data


def _pack(data):
    """Словарь → строка для куки: JSON в URL-безопасном base64.

    ⚠️ BASE64, А НЕ JSON КАК ЕСТЬ. Кириллица в значении куки не проходит
    через заголовок ответа (он в latin-1), а кавычки и запятые Django стал
    бы экранировать по-своему.
    """
    raw = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _unpack(value):
    padded = value + '=' * (-len(value) % 4)
    data = json.loads(base64.urlsafe_b64decode(padded.encode('ascii')).decode('utf-8'))
    if not isinstance(data, dict):
        raise ValueError('не словарь')
    return data


def _parse_time(value):
    try:
        moment = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment, dt_timezone.utc)
    return moment


def _normalize(data):
    """Метки из куки или сессии → словарь `SignupSource` (обрезка и время)."""
    touch = {key: _clip(data.get(key)) for key in TEXT_FIELDS}
    touch['first_seen_at'] = _parse_time(data.get('first_seen_at'))
    return touch


def _read_cookie(request):
    value = request.get_signed_cookie(COOKIE_NAME, default=None, salt=COOKIE_SALT,
                                      max_age=COOKIE_MAX_AGE)
    if not value:
        return None
    try:
        return _unpack(value)
    except ValueError:        # base64, UTF-8 и JSON бросают его наследников
        return None


def _read_session(request):
    """Метки, ждущие согласия, из сессии или None. Сессию без куки не заводит."""
    session = getattr(request, 'session', None)
    if session is None or not session.session_key:
        return None
    data = session.get(SESSION_KEY)
    return data if isinstance(data, dict) else None


def read_first_touch(request):
    """Сохранённое первое касание: подписанная кука, иначе сессия, иначе None.

    Нет куки, подпись не сходится, прошло больше 90 дней, внутри мусор —
    всё это «первого касания нет». Даже подписанное значение проходит те
    же правила обрезки: кука живёт долго, а правила могут поменяться.
    Сессия читается, только когда куки нет: так метки, пришедшие ДО согласия
    на аналитику, доезжают до `SignupSource` при регистрации.
    """
    data = _read_cookie(request)
    if data is None:
        data = _read_session(request)
    return None if data is None else _normalize(data)


def _set_cookie(response, data):
    response.set_signed_cookie(
        COOKIE_NAME, _pack(data), salt=COOKIE_SALT, max_age=COOKIE_MAX_AGE,
        secure=settings.SESSION_COOKIE_SECURE, httponly=True, samesite='Lax')


def remember_first_touch(request, response):
    """Метка первого касания: в куку при согласии, иначе в сессию.

    1. «Только необходимые»: уже стоящую `weco_src` стираем (на любом методе).
    2. Метка пришла, сохранённой ещё нет: при `weco_consent=all` — в куку,
       иначе — в сессию (необходимая кука), пока человек не решил.
    3. Согласие `all` есть, куки нет, а в сессии ждут метки — переносим в куку.
    """
    from legal import cookie_consent

    chosen = cookie_consent.choice(request)
    if chosen == cookie_consent.NECESSARY and COOKIE_NAME in request.COOKIES:
        response.delete_cookie(COOKIE_NAME, samesite='Lax')
    if request.method != 'GET':
        return
    allowed = chosen == cookie_consent.ALL
    data = capture(request)
    if data is not None and read_first_touch(request) is None:
        if allowed:
            _set_cookie(response, data)
        else:
            request.session[SESSION_KEY] = data
        return
    if allowed and COOKIE_NAME not in request.COOKIES:
        waiting = _read_session(request)
        if waiting is not None:
            _set_cookie(response, waiting)
            request.session.pop(SESSION_KEY, None)


class FirstTouchMiddleware:
    """Запоминает первую UTM-метку посетителя (см. докстринг модуля).

    Работает на ОТВЕТЕ и с любым кодом: посадочная страница может уйти
    редиректом (вход, переход на «/» в конце адреса), а метка в `next`
    следующего адреса уже не лежит сверху и была бы потеряна.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        remember_first_touch(request, response)
        return response


def record_signup(request, user, kind):
    """Источник для нового аккаунта и цель Метрики на следующую страницу.

    ⚠️ НЕБЛОКИРУЮЩАЯ, как журнал учебных событий: аналитика не имеет права
    уронить регистрацию. Запись — в точке сохранения (`atomic`), чтобы её
    сбой не испортил внешнюю транзакцию, если такая появится.

    ⚠️ ЗВАТЬ ПОСЛЕ `login()`: цель ложится в сессию, а вход меняет её ключ.
    Данные сессии при этом переезжают, но порядок «сначала вход» не зависит
    от того, как Django устроит это завтра.
    """
    from problems.models_platform import SignupSource

    fields = read_first_touch(request) or {}
    try:
        with transaction.atomic():
            SignupSource.objects.get_or_create(
                user=user, defaults=dict(fields, signup_kind=kind))
    except Exception:
        logger.exception('Источник регистрации не записан (user=%s, kind=%s) — '
                         'регистрация не тронута', user.pk, kind)
    # Цель откладываем, только если счётчик вообще стоит: иначе флаг лежал бы
    # в сессии без дела и выстрелил бы позже, когда номер появится.
    if settings.YANDEX_METRIKA_ID and kind in GOAL_BY_KIND:
        request.session[GOAL_SESSION_KEY] = {'name': GOAL_BY_KIND[kind],
                                             'token': secrets.token_hex(8)}


def pop_goal(request):
    """Отложенная цель — ровно один раз: после вызова её в сессии больше нет.

    Отдаёт `{'name', 'token'}` или None. Имя — только из трёх известных,
    метка — только 16 шестнадцатеричных знаков: оба значения уходят в
    скрипт страницы, и чужого там быть не может даже теоретически.
    `token` нужен скрипту, чтобы не отправить цель второй раз, если браузер
    исполнит ту же страницу снова из кэша (кнопка «Назад»).
    """
    session = getattr(request, 'session', None)
    if session is None:
        return None
    goal = session.pop(GOAL_SESSION_KEY, None)
    if not isinstance(goal, dict):
        return None
    name, token = goal.get('name'), goal.get('token')
    if name not in GOAL_BY_KIND.values() or not isinstance(token, str) \
            or not _TOKEN_RE.fullmatch(token):
        return None
    return {'name': name, 'token': token}
