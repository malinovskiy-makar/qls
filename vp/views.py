"""Экраны тренажёра «Высшая проба»: список → вход → прохождение → результат.

⚠️ ВХОД НЕ ТРЕБУЕТСЯ НИГДЕ, И ЭТО РЕШЕНИЕ, А НЕ ПРОПУСК: тренажёр открыт любому
посетителю. Вошедшего узнаём по пользователю, гостя — по сессии. Публичны
осознанно: список и вход (только опубликованные варианты), старт попытки и
страница результата (голый балл, без ответов). Всё остальное принадлежит
владельцу попытки: чужой код даёт 404 — как будто такой попытки нет.

⚠️ ВЛАДЕЛЕЦ БЕРЁТСЯ ИЗ `request.user` И СЕССИИ, НИКОГДА ИЗ ДАННЫХ ЗАПРОСА. Адрес
попытки (`public_code`) — не право доступа, а только адрес; его проверяет ровно
одна функция, `_get_attempt` (ADR 0125).

⚠️ ОТВЕТЫ НЕ УХОДЯТ КЛИЕНТУ ДО СДАЧИ. В шаблон прохождения идут строки-словари
только с безопасными полями задания, а не сами задания: эталон, верные номера и
буквы связки змейки страница не видит.
"""
import logging
import secrets
from datetime import timedelta

from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from vp import blocks, scoring
from vp.models import VPAttempt, VPVariant

logger = logging.getLogger(__name__)

# Коды попыток гостя, которые помнит его сессия: по ним он находит свою работу и
# после входа в аккаунт (ключ сессии при входе меняется, данные сессии — нет).
SESSION_ATTEMPTS = 'vp_attempts'
SESSION_ATTEMPTS_LIMIT = 50

# Раздел «Классы» на странице списка: (значение `grade_band`, подпись).
BANDS = (('9-10', '9–10 классы'), ('11', '11 класс'))


# ------------------------------------------------------------------ доступ

def _is_staff(request):
    return request.user.is_authenticated and request.user.is_staff


def _variant_or_404(request, slug):
    """Опубликованный вариант. Черновик видит только персонал — проверить до выпуска."""
    variants = VPVariant.objects.all()
    if not _is_staff(request):
        variants = variants.filter(is_published=True)
    return get_object_or_404(variants, slug=slug)


def _remember(request, code):
    """Кладёт код попытки в сессию (последние `SESSION_ATTEMPTS_LIMIT`)."""
    codes = [c for c in request.session.get(SESSION_ATTEMPTS, []) if c != code]
    codes.append(code)
    request.session[SESSION_ATTEMPTS] = codes[-SESSION_ATTEMPTS_LIMIT:]


def _get_attempt(request, code):
    """Попытка владельца или 404 — ЕДИНСТВЕННОЕ место, где проверяется доступ.

    Владелец попытки — пользователь (если он у попытки есть), иначе тот браузер,
    код попытки которого лежит в сессии или чей ключ сессии записан в попытке.
    Именно 404, а не 403: чужую попытку не должно быть видно даже по факту
    существования.
    """
    attempt = get_object_or_404(
        VPAttempt.objects.select_related('variant'), public_code=code)
    if attempt.user_id is not None:
        if not (request.user.is_authenticated and attempt.user_id == request.user.pk):
            raise Http404
        return attempt
    key = request.session.session_key
    remembered = code in request.session.get(SESSION_ATTEMPTS, [])
    if not (remembered or (key and attempt.session_key == key)):
        raise Http404
    return attempt


def _current_attempt(request, variant):
    """Несданная попытка этого человека по варианту (самая свежая) или None."""
    attempts = VPAttempt.objects.filter(variant=variant, submitted_at__isnull=True)
    if request.user.is_authenticated:
        attempts = attempts.filter(user=request.user)
    else:
        key = request.session.session_key
        mine = Q(public_code__in=request.session.get(SESSION_ATTEMPTS, []))
        if key:
            mine |= Q(session_key=key)
        attempts = attempts.filter(user__isnull=True).filter(mine)
    return attempts.order_by('-started_at', '-id').first()


def _new_code():
    """Код попытки: 12 знаков, с повтором при коллизии."""
    while True:
        code = secrets.token_urlsafe(9)[:12]
        if not VPAttempt.objects.filter(public_code=code).exists():
            return code


# --------------------------------------------------------- список и вход

def index(request):
    """Опубликованные варианты по классам. Публичный экран."""
    variants = VPVariant.objects.all()
    if not _is_staff(request):
        variants = variants.filter(is_published=True)
    variants = list(variants)
    bands = []
    for code, label in BANDS:
        chosen = [v for v in variants if v.grade_band == code]
        if chosen:
            bands.append({'label': label, 'variants': chosen})
    return render(request, 'vp/index.html', {'bands': bands})


def _answered_count(attempt):
    """Сколько заданий отвечено. «Пусто» — по правилу подсчёта баллов."""
    return sum(1 for a in attempt.answers.all() if not scoring.is_blank(a.raw))


def intro(request, slug):
    """Что за вариант, из чего состоит, как считаются баллы, режим и старт.

    Числа — количество заданий по блокам и суммы баллов — считаются из заданий
    варианта в базе, в шаблоне их нет.
    """
    variant = _variant_or_404(request, slug)
    items = list(variant.items.all())
    sections = blocks.sections(items)
    partial = [s for s in sections if s['block'] in ('multi', 'analytic')]
    whole = [s for s in sections if s not in partial]

    example = None
    sample = next((i for s in partial for i in s['items'] if i.penalty), None)
    if sample is not None:
        example = scoring.penalty_example(sample.points)

    attempt = _current_attempt(request, variant)
    return render(request, 'vp/intro.html', {
        'variant': variant,
        'sections': sections,
        'items_count': len(items),
        'whole_ranges': blocks.merged_ranges(whole),
        'partial_ranges': blocks.merged_ranges(partial),
        'penalty_example': example,
        'attempt': attempt,
        'attempt_answered': _answered_count(attempt) if attempt else 0,
    })


@require_POST
def start(request, slug):
    """Начинает попытку. Таймер запускает сервер в момент нажатия.

    Несданная попытка этого же человека не дублируется: нажатие возвращает в неё
    (двойной клик не плодит попыток).
    """
    variant = _variant_or_404(request, slug)
    if not variant.items.exists():
        raise Http404
    attempt = _current_attempt(request, variant)
    if attempt is None:
        with_timer = request.POST.get('with_timer', '1') == '1'
        user = request.user if request.user.is_authenticated else None
        if user is None and not request.session.session_key:
            request.session.create()
        attempt = VPAttempt.objects.create(
            variant=variant,
            user=user,
            session_key='' if user else request.session.session_key,
            with_timer=with_timer,
            expires_at=(timezone.now() + timedelta(seconds=variant.duration_seconds)
                        if with_timer else None),
            max_score=variant.max_score,
            public_code=_new_code(),
        )
    _remember(request, attempt.public_code)
    return redirect('vp:take', code=attempt.public_code)


# ------------------------------------------------------------ прохождение

@never_cache
def take(request, code):
    """Страница прохождения (наполняется в следующей фазе)."""
    attempt = _get_attempt(request, code)
    return render(request, 'vp/take.html', {
        'attempt': attempt, 'variant': attempt.variant, 'seo_noindex': True})
