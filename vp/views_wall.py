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
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from legal import consent
from problems import email_codes
from problems.email_codes import Purpose
from problems.models_legal import ConsentRecord
from vp import landing, tracking, wall
from vp.models import VPWall
from vp.views import _variant_or_404, _wall_url

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
        'minutes': variant.duration_seconds // 60,
        'grade': _survey_grade(user, variant) if screen == 'survey' else '',
        'urls': {
            'tg_screen': _wall_url(variant.slug),
            'email_screen': _wall_url(variant.slug, 'email'),
            'other_email': '/account/email/?%s' % urlencode(
                {'next': _wall_url(variant.slug, 'email'), 'src': 'vp'}),
            'intro': intro_url,
        },
    }
