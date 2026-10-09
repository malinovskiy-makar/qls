# -*- coding: utf-8 -*-
"""Страницы документов, экран согласия и согласие на помощника."""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.safestring import mark_safe
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from problems import erasure

from . import consent, cookie_consent, documents
from problems.models_legal import ConsentRecord

PROFILE_URL = '/profile/?tab=data'


def _requisites():
    """Реквизиты для страницы /legal/ и экрана согласия."""
    legal = settings.LEGAL
    return {
        'name': legal['operator_name'],
        'status': legal['operator_status'],
        'inn': legal['operator_inn'],
        'telegram': legal['telegram'],
        # Разметка собрана модулем documents с экранированием; заглушка — span.
        'mail': mark_safe(documents.mail_html()),  # noqa: S308
        'date': mark_safe(documents.date_html()),  # noqa: S308
        'version': legal['docs_version'],
    }


# Страницы документов открыты всем осознанно: ссылки на них стоят на форме
# регистрации и в футере каждой страницы, а читать их надо ДО согласия.
def index(request):
    return render(request, 'legal/index.html', {
        'documents': documents.all_documents(),
        'req': _requisites(),
    })


def document(request, slug):
    doc = documents.get_document(slug)
    if doc is None:
        raise Http404('Нет такого документа.')
    return render(request, 'legal/document.html', {
        'doc': doc,
        'body': documents.render(doc),
        'documents': documents.all_documents(),
    })


def _safe_next(request):
    target = request.POST.get('next') or request.GET.get('next') or ''
    if target and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return '/'


@login_required
def accept(request):
    """Блокирующий экран согласия для уже зарегистрированных."""
    target = _safe_next(request)
    if consent.has_current(request.user, ConsentRecord.Kind.PD):
        consent.remember_in_session(request)
        return redirect(target)
    error = ''
    if request.method == 'POST':
        if request.POST.get('agree'):
            consent.grant(request.user, ConsentRecord.Kind.PD, ConsentRecord.Source.GATE)
            consent.remember_in_session(request)
            return redirect(target)
        error = 'Отметьте галочку, чтобы продолжить.'
    return render(request, 'legal/accept.html', {
        'next': target if target != '/' else '',
        'error': error,
        'req': _requisites(),
    })


def _wants_json(request):
    return (request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or 'application/json' in request.headers.get('Accept', ''))


@login_required
@require_POST
def ai_grant(request):
    """Согласие на помощника: кнопка в панели помощника или в профиле."""
    source = (ConsentRecord.Source.PROFILE if request.POST.get('source') == 'profile'
              else ConsentRecord.Source.CHAT)
    record = consent.grant(request.user, ConsentRecord.Kind.AI, source)
    if _wants_json(request):
        return JsonResponse({'ok': True, 'given_at': record.given_at.isoformat()})
    return redirect(PROFILE_URL)


@login_required
@require_POST
def ai_revoke(request):
    """Отзыв согласия на помощника: запись отзывается, диалоги и файлы чата удаляются.

    Сначала отзыв: с этой секунды помощнику ничего не уйдёт. Потом удаление
    (Согласие на помощника, п. 8; общая внутренность с `erase_user`).
    """
    consent.revoke(request.user, ConsentRecord.Kind.AI)
    erasure.erase_chat(request.user)
    if _wants_json(request):
        return JsonResponse({'ok': True})
    return redirect(PROFILE_URL)


@never_cache
def metrika_boot(request):
    """Код счётчика Метрики файлом: окно cookie подгружает его после «Разрешить».

    Без номера счётчика или без куки `weco_consent=all` отдаёт пустой файл:
    адрес Яндекса без согласия не выдаётся никому. Код тот же, что вставляет
    в страницу `_metrika.html` (общий шаблон `_metrika_code.js`); кабинет
    окно сообщает параметром `private=1`, вошедший определяется по сессии.
    """
    js = 'application/javascript; charset=utf-8'
    if not (settings.YANDEX_METRIKA_ID and cookie_consent.analytics_allowed(request)):
        return HttpResponse('/* аналитика не разрешена */', content_type=js)
    return render(request, '_metrika_code.js',
                  {'metrika_private': request.GET.get('private') == '1'},
                  content_type=js)
