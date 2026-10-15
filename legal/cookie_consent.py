# -*- coding: utf-8 -*-
"""Выбор человека в окне cookie (Правовой контур, часть Б, 09.10.2026).

Кука `weco_consent` со значением `all` или `necessary` живёт год и читается
И сервером, И скриптом страницы (поэтому без HttpOnly): сервер по ней решает,
выводить ли Метрику и ставить ли `weco_src`, скрипт — показывать ли окно.

⚠️ Любое другое значение (или кука стёрта, подделана) равно «выбора нет»:
аналитика выключена, окно показывается. Включает её только точное `all`.

Необходимые куки (`sessionid`, `csrftoken`, `messages`, `weco_vid`,
`weco_consent`) согласия не ждут — это сказано в политике cookie, раздел 1.
"""

COOKIE_NAME = 'weco_consent'
ALL = 'all'
NECESSARY = 'necessary'
CHOICES = (ALL, NECESSARY)
MAX_AGE = 365 * 24 * 60 * 60


def choice(request):
    """`all`, `necessary` или None, если человек ещё не выбирал."""
    value = request.COOKIES.get(COOKIE_NAME)
    return value if value in CHOICES else None


def analytics_allowed(request):
    return choice(request) == ALL
