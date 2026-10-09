# -*- coding: utf-8 -*-
"""Защита всего, что отправляет данные человека модели: согласие `ai`.

Без действующей записи ТЕКУЩЕЙ редакции сервер отвечает 403 с кодом
`ai_consent_required`, ничего не отправляет наружу и не сохраняет файл.

⚠️ Гостя декоратор не трогает: у гостевого запроса на этих адресах свой
отказ («Войдите…»), и показывать ему вопрос о согласии рано.

⚠️ УМНЫЙ ПОИСК СОГЛАСИЯ НЕ ТРЕБУЕТ (решение владельца 08.10.2026): туда уходит
только текст запроса без сведений о человеке.
"""
from functools import wraps

from django.http import JsonResponse
from django.urls import reverse

from problems.models_legal import ConsentRecord

from . import consent

AI_CONSENT_TEXT = ('Помощник работает на зарубежной модели. '
                   'Чтобы им пользоваться, дайте согласие на передачу данных.')


def ai_consent_missing(user):
    """Нужно ли отказать этому пользователю: вошёл, а согласия на помощника нет."""
    if not consent.enforcement_enabled():
        return False
    if user is None or not user.is_authenticated:
        return False
    return not consent.has_current(user, ConsentRecord.Kind.AI)


def refusal_response():
    return JsonResponse(
        {'error': 'ai_consent_required', 'message': AI_CONSENT_TEXT,
         # Часть скриптов страницы показывает в чате поле `reply`, часть `message`.
         'reply': AI_CONSENT_TEXT,
         'consent_url': reverse('legal:document', args=['consent-ai'])},
        status=403)


def ai_consent_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if ai_consent_missing(request.user):
            return refusal_response()
        return view(request, *args, **kwargs)
    return wrapper
