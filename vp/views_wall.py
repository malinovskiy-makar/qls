"""Окно стены 2 тура: почта, Telegram, анкета (docs/VP.md, «Стена 2 тура», ADR 0168).

Правило «пускать ли» — `vp/wall.py`; здесь только действия человека в окне.
Каждое действие — POST и редирект обратно на интро с `?wall=…`: окно работает
и без JS, экран выбирает сервер (`wall_screen`).

⚠️ НИ ОДИН АДРЕС ЗДЕСЬ НЕ ОТКРЫВАЕТ СЕССИЮ ПО TELEGRAM. Вход на сайт через
Telegram запрещён (149-ФЗ в ред. 406-ФЗ, ст. 13.55 КоАП): бот только привязывает
Telegram к аккаунту, который уже вошёл и получил код.

⚠️ СО СТЕНЫ СОГЛАСИЕ НА РАССЫЛКУ ТОЛЬКО ДАЁТСЯ, НИКОГДА НЕ ОТЗЫВАЕТСЯ. Галочка
по желанию и не отмечена заранее; неотмеченная галочка ничего не отбирает.
"""
import hmac
import json
import secrets
import time
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import (Http404, HttpResponseBadRequest, HttpResponseForbidden,
                         HttpResponseRedirect, JsonResponse)
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from legal import consent
from problems import email_codes
from problems.email_codes import Purpose
from problems.models_legal import ConsentRecord
from vp import bot, landing, telegram, tracking, wall
from vp.models import VPTelegramLink, VPTelegramToken, VPWall
from vp.views import _current_attempt, _remember, _start_attempt, _variant_or_404, _wall_url

#: Почта, на которую ушёл код со стены: `{'email', 'mail_consent', 'slug'}`.
SESSION_EMAIL = 'vp_wall_email'
#: Одно сообщение окну после редиректа: `{'text', 'kind', 'email'}`.
SESSION_FLASH = 'vp_wall_flash'


def flash(request, text, kind='error', **extra):
    request.session[SESSION_FLASH] = {'text': text, 'kind': kind, **extra}


def take_flash(request):
    return request.session.pop(SESSION_FLASH, None)


def _grant_mail(user, wanted):
    """Галочка → согласие. Неотмеченная галочка НЕ отзывает прежнее согласие."""
    if wanted:
        consent.grant(user, ConsentRecord.Kind.MAIL, ConsentRecord.Source.VP_WALL)


def _wall_variant(request, slug):
    """Вариант, для которого стена нужна, или 404."""
    variant = _variant_or_404(request, slug)
    if not wall.required(variant):
        raise Http404
    return variant


@require_POST
def wall_email(request, slug):
    """Почтовый путь стены: `send` → `confirm` (`resend`, `change`) или `use`."""
    if not email_codes.mail_enabled():
        raise Http404
    if not request.user.is_authenticated:
        return redirect_to_login(_wall_url(slug), '/login/')
    variant = _wall_variant(request, slug)
    user = request.user
    if wall.step(user) != 'contact':
        return redirect(_wall_url(variant.slug))
    action = request.POST.get('action', '')
    wanted = request.POST.get('mail_consent') == 'on'
    pending = request.session.get(SESSION_EMAIL)
    if pending and pending.get('slug') != variant.slug:
        pending = None

    if action == 'use':
        # Почта уже подтверждена: один клик, ни одного нового кода.
        if not email_codes.has_verified_email(user):
            return HttpResponseBadRequest('Подтверждённой почты нет.')
        _grant_mail(user, wanted)
        wall.pass_contact(user, 'email')
        tracking.defer(request, 'vp_wall_email_ok', variant=variant.slug, how='use')
        return redirect(_wall_url(variant.slug))

    if action == 'send':
        # ⚠️ Почта — ключ входа: стена её молча НЕ меняет. Другая почта у того, у
        # кого подтверждённая уже есть, — только на странице «Почта», явным кодом.
        if email_codes.has_verified_email(user):
            return HttpResponseBadRequest('Почта уже подтверждена.')
        email = email_codes.normalize_email(request.POST.get('email'))
        try:
            validate_email(email)
        except ValidationError:
            flash(request, 'Это не похоже на адрес почты.', email=email, consent=wanted)
            return redirect(_wall_url(variant.slug, 'email'))
        other = email_codes.verified_user_for(email)
        if other is not None and other.pk != user.pk:
            flash(request, email_codes.TAKEN_MESSAGE, email=email, consent=wanted)
            return redirect(_wall_url(variant.slug, 'email'))
        result = email_codes.send_code(email, Purpose.CONFIRM, user=user, request=request)
        if result.ok or (result.reason == 'wait' and pending and pending['email'] == email):
            request.session[SESSION_EMAIL] = {
                'email': email, 'mail_consent': wanted, 'slug': variant.slug}
            if result.ok:
                tracking.defer(request, 'vp_wall_email_sent', variant=variant.slug)
            else:
                flash(request, 'Код уже отправлен, проверьте почту.', 'info')
            return redirect(_wall_url(variant.slug, 'code'))
        flash(request, email_codes.send_error(result), email=email, consent=wanted)
        return redirect(_wall_url(variant.slug, 'email'))

    if not pending:
        return redirect(_wall_url(variant.slug, 'email'))

    if action == 'change':
        request.session.pop(SESSION_EMAIL, None)
        flash(request, '', 'prefill', email=pending['email'], consent=pending['mail_consent'])
        return redirect(_wall_url(variant.slug, 'email'))

    if action == 'resend':
        result = email_codes.send_code(pending['email'], Purpose.CONFIRM, user=user,
                                       request=request)
        if result.ok:
            flash(request, 'Мы отправили новый код.', 'info')
        else:
            flash(request, email_codes.send_error(result))
        return redirect(_wall_url(variant.slug, 'code'))

    if action == 'confirm':
        check = email_codes.check_code(pending['email'], Purpose.CONFIRM,
                                       request.POST.get('code', ''))
        if not check.ok:
            flash(request, email_codes.check_error(check))
            return redirect(_wall_url(variant.slug, 'code'))
        request.session.pop(SESSION_EMAIL, None)
        try:
            email_codes.attach_verified_email(user, pending['email'])
        except email_codes.EmailTaken:
            flash(request, email_codes.TAKEN_MESSAGE, email=pending['email'])
            return redirect(_wall_url(variant.slug, 'email'))
        _grant_mail(user, pending['mail_consent'])
        wall.pass_contact(user, 'email')
        tracking.defer(request, 'vp_wall_email_ok', variant=variant.slug, how='code')
        return redirect(_wall_url(variant.slug))

    return HttpResponseBadRequest('Неизвестное действие.')


# ------------------------------------------------------------------ окно на интро

def _survey_grade(user, variant):
    """Класс, заранее выбранный в анкете: из анкеты → из профиля → класс варианта."""
    codes = [code for code, _ in VPWall.GRADE_CHOICES]
    saved = VPWall.objects.filter(user=user).values_list('grade', flat=True).first()
    if saved in codes:
        return saved
    profile = getattr(user, 'profile', None)
    if profile is not None and profile.grade in codes:
        return profile.grade
    return variant.grade_band if variant.grade_band in codes else ''


def wall_window(request, variant, attempt):
    """Окно стены для интро: словарь для `vp/_wall.html` или None — окна нет.

    Окно есть, когда человек вошёл, стена для варианта нужна, она не пройдена и
    несданной попытки по варианту нет. Экран — по таблице в docs/VP.md: шаг важнее
    параметра `?wall=…`, нет нужных данных — понятный экран, а не ошибка.
    """
    user = request.user
    if not user.is_authenticated or attempt is not None or not wall.required(variant):
        return None
    step = wall.step(user)
    if step == 'done':
        return None
    state = request.GET.get('wall', '')
    paths = wall.paths()
    note = take_flash(request) if state else None
    pending = request.session.get(SESSION_EMAIL)
    if pending and pending.get('slug') != variant.slug:
        pending = None
    verified = email_codes.has_verified_email(user)
    tg = 'none'
    if step == 'survey':
        screen = 'survey'
    elif state == 'closed' or not any(paths.values()):
        screen = 'closed'
    elif paths['email'] and (state in ('email', 'code') or not paths['tg']):
        if state == 'code' and pending:
            screen = 'code'
        else:
            screen = 'known' if verified else 'email'
    else:
        tg = wall.tg_state(user)
        screen = {'no_sub': 'nosub', 'error': 'nosub', 'waiting': 'waiting'}.get(tg, 'tg')
    link = VPTelegramLink.objects.filter(user=user).only('tg_username').first()
    often = _tg_wait_minutes(user) if request.GET.get('tg') == 'often' else 0
    nxt = request.session.get(wall.SESSION_NEXT) or {}
    with_timer = nxt.get('with_timer', True) if nxt.get('slug') == variant.slug else True
    intro_url = reverse('vp:intro', args=[variant.slug])
    channel = settings.TELEGRAM_CHANNEL.lstrip('@')
    return {
        'screen': screen,
        'step': step,
        'open': bool(state),
        'eyebrow': landing.wall_eyebrow(variant),
        'paths': paths,
        'mail_link': paths['email'],
        'tg': tg,
        'tg_username': link.tg_username if link else '',
        'tg_often': often,
        'note': note,
        'verified': verified,
        'email': user.email if verified else '',
        'wants_mail': consent.wants_mail(user),
        'prefill_email': (note or {}).get('email', ''),
        'prefill_consent': bool((note or {}).get('consent')),
        'pending_email': pending['email'] if pending else '',
        'resend_wait': (email_codes.resend_wait(pending['email'], Purpose.CONFIRM)
                        if screen == 'code' else 0),
        'channel': channel,
        'channel_url': 'https://t.me/' + channel,
        'with_timer': with_timer,
        'minutes_word': landing.duration_words(variant),
        'survey': {
            'grades': [(code, code) for code, _ in VPWall.GRADE_CHOICES],
            'statuses': VPWall.TOUR2_CHOICES,
            'sources': VPWall.SOURCE_CHOICES,
            'grade': (note or {}).get('grade') or _survey_grade(user, variant),
            'status': (note or {}).get('tour2_status', ''),
            'source': (note or {}).get('source', ''),
        } if screen == 'survey' else None,
        'urls': {
            'tg_screen': _wall_url(variant.slug),
            'email_screen': _wall_url(variant.slug, 'email'),
            'other_email': '/account/email/?%s' % urlencode(
                {'next': _wall_url(variant.slug, 'email'), 'src': 'vp'}),
            'intro': intro_url,
            'tg': reverse('vp:wall_tg', args=[variant.slug]),
            'check': reverse('vp:wall_check', args=[variant.slug]),
            'state': '%s?%s' % (reverse('vp:wall_state'), urlencode({'v': variant.slug})),
            'survey': reverse('vp:wall_survey', args=[variant.slug]),
        },
    }


# ------------------------------------------------------------------ Telegram

#: Код привязки в сессии: `{'token', 'slug', 'at'}` — повторный клик по тому же
#: варианту в течение `TOKEN_TTL` отдаёт ТОТ ЖЕ код (в базе только отпечаток).
SESSION_TG = 'vp_wall_tg'
#: Не больше стольких новых кодов на человека в час.
TG_TOKENS_PER_HOUR = 10
#: Кнопка «проверить» — не чаще раза в столько секунд на человека.
CHECK_EVERY = 5
#: Вебхук: тело больше этого — 400. Повтор `update_id` отсекает `vp.bot.handle_once`.
HOOK_MAX_BYTES = 64 * 1024


def _tg_wait_minutes(user):
    """Через сколько минут можно взять новый код, если лимит часа выбран; 0 — можно."""
    hour_ago = timezone.now() - timedelta(hours=1)
    recent = VPTelegramToken.objects.filter(user=user, created_at__gt=hour_ago)
    if recent.count() < TG_TOKENS_PER_HOUR:
        return 0
    oldest = recent.order_by('created_at').first()
    left = (oldest.created_at + timedelta(hours=1) - timezone.now()).total_seconds()
    return email_codes.minutes(max(1, int(left)))


class TgAppRedirect(HttpResponseRedirect):
    """302 на `tg://…`: стандартный редирект Django схему `tg` не пускает (DisallowedRedirect)."""
    allowed_schemes = ['tg']


@require_POST
def wall_tg(request, slug):
    """«Подключить Telegram»: 302 на `https://t.me/<бот>?start=<код>`. Форма с
    `target="_blank"` — бот открывается в новой вкладке, окно ждёт «Старт».

    С `app=1` («Не открылось? Открыть в приложении Telegram») – тот же код, но 302 на
    `tg://resolve?domain=<бот>&start=<код>`: приложение открывается сразу, без сайта t.me,
    который в России в браузере может не открываться. Эта форма без `target="_blank"`.

    Именно POST: в проекте GET ничего не пишет в базу.
    """
    if not request.user.is_authenticated:
        return redirect_to_login(_wall_url(slug), '/login/')
    variant = _wall_variant(request, slug)
    if not telegram.enabled():
        raise Http404
    user = request.user
    if wall.step(user) != 'contact':
        return redirect(_wall_url(variant.slug))
    kept = request.session.get(SESSION_TG) or {}
    token = ''
    if (kept.get('slug') == variant.slug
            and time.time() - kept.get('at', 0) < wall.TOKEN_TTL.total_seconds()
            and VPTelegramToken.objects.filter(
                user=user, token_hash=bot.token_hash(kept.get('token', '')),
                used_at__isnull=True).exists()):
        token = kept['token']
    if not token:
        if _tg_wait_minutes(user):
            return redirect(_wall_url(variant.slug, tg='often'))
        token = secrets.token_urlsafe(24)
        VPTelegramToken.objects.create(user=user, token_hash=bot.token_hash(token),
                                       slug=variant.slug)
        request.session[SESSION_TG] = {'token': token, 'slug': variant.slug, 'at': time.time()}
        tracking.defer(request, 'vp_wall_tg_click', variant=variant.slug)
    if request.POST.get('app') == '1':
        return TgAppRedirect('tg://resolve?domain=%s&start=%s'
                             % (settings.TELEGRAM_BOT_USERNAME, token))
    return redirect('https://t.me/%s?start=%s' % (settings.TELEGRAM_BOT_USERNAME, token))


@require_POST
def wall_check(request, slug):
    """«Я подписался – проверить» / «Я нажал «Старт» – проверить»: подписка ещё раз."""
    if not request.user.is_authenticated:
        return redirect_to_login(_wall_url(slug), '/login/')
    variant = _wall_variant(request, slug)
    user = request.user
    link = VPTelegramLink.objects.filter(user=user).first()
    if (link is not None and wall.step(user) == 'contact'
            and cache.add('vp:wall:check:%d' % user.pk, 1, CHECK_EVERY)):
        subscribed = bot.check_link(link)
        if subscribed:
            tracking.defer(request, 'vp_wall_tg_ok', variant=variant.slug)
        elif subscribed is False:
            tracking.defer(request, 'vp_wall_tg_nosub', variant=variant.slug)
    return redirect(_wall_url(variant.slug))


@never_cache
@require_GET
def wall_state(request):
    """JSON для опроса со страницы (экран 02): шаг стены и путь Telegram.

    Вариант — через `_variant_or_404`: по ответу нельзя перебирать скрытые слаги.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login'}, status=403)
    _variant_or_404(request, request.GET.get('v', ''))
    user = request.user
    link = VPTelegramLink.objects.filter(user=user).only('tg_username').first()
    return JsonResponse({'step': wall.step(user), 'tg': wall.tg_state(user),
                         'tg_username': link.tg_username if link else ''})


@csrf_exempt
@require_POST
def tg_hook(request):
    """Вебхук бота. ⚠️ СЕКРЕТ НЕ ЗАДАН — ВСЕГДА 403: пустой секрет открыл бы вебхук всем.

    Заголовок `X-Telegram-Bot-Api-Secret-Token` сравнивается по байтам за постоянное
    время. Ошибка обработки — в лог (без тела) и всё равно 200: иначе Telegram
    засыпал бы повторами.
    """
    secret = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')
    given = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if not secret or not hmac.compare_digest(given.encode('utf-8'), secret.encode('utf-8')):
        return HttpResponseForbidden()
    try:
        length = int(request.META.get('CONTENT_LENGTH') or 0)
    except ValueError:
        length = HOOK_MAX_BYTES + 1
    if length > HOOK_MAX_BYTES or len(request.body) > HOOK_MAX_BYTES:
        return HttpResponseBadRequest()
    try:
        update = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        return HttpResponseBadRequest()
    if not isinstance(update, dict):
        return HttpResponseBadRequest()
    bot.handle_once(update)
    return JsonResponse({'ok': True})


# ------------------------------------------------------------------ анкета

SURVEY_REQUIRED = 'Ответьте на все три вопроса.'


@require_POST
def wall_survey(request, slug):
    """Анкета (экран 06) — и сразу старт варианта.

    Порядок: контакта нет → окно; несданная попытка → в неё (повтор или двойной
    клик не создаёт второй попытки); анкеты не было → сохранить (уже была — НЕ
    перезаписывать); класс в профиле пуст → записать (профиль не создавать);
    затем попытка с режимом из `vp_wall_next` (если там этот вариант) или из формы.
    """
    if not request.user.is_authenticated:
        return redirect_to_login(_wall_url(slug), '/login/')
    variant = _wall_variant(request, slug)
    if not variant.items.exists():
        raise Http404
    user = request.user
    if wall.step(user) == 'contact':
        return redirect(_wall_url(variant.slug))
    attempt = _current_attempt(request, variant)
    if attempt is None:
        if not VPWall.objects.filter(user=user, survey_at__isnull=False).exists():
            answers = {
                'grade': request.POST.get('grade', ''),
                'tour2_status': request.POST.get('tour2_status', ''),
                'source': request.POST.get('source', ''),
            }
            allowed = {'grade': VPWall.GRADE_CHOICES, 'tour2_status': VPWall.TOUR2_CHOICES,
                       'source': VPWall.SOURCE_CHOICES}
            if any(value not in dict(allowed[key]) for key, value in answers.items()):
                flash(request, SURVEY_REQUIRED, **answers)
                return redirect(_wall_url(variant.slug))
            VPWall.objects.filter(user=user, survey_at__isnull=True).update(
                survey_at=timezone.now(), **answers)
            profile = getattr(user, 'profile', None)
            if profile is not None and not profile.grade:
                profile.grade = answers['grade']
                profile.save(update_fields=['grade'])
            tracking.defer(request, 'vp_wall_survey_done', variant=variant.slug,
                           grade=answers['grade'], tour2_status=answers['tour2_status'],
                           source=answers['source'])
        kept = request.session.pop(wall.SESSION_NEXT, None) or {}
        if kept.get('slug') == variant.slug:
            with_timer = bool(kept.get('with_timer', True))
        else:
            with_timer = request.POST.get('with_timer', '1') == '1'
        attempt = _start_attempt(request, variant, with_timer)
    _remember(request, attempt.public_code)
    return redirect('vp:take', code=attempt.public_code)
