# -*- coding: utf-8 -*-
"""Вход и регистрация через VK ID / Яндекс ID (решения владельца 29.10.2026).

Путь человека:

1. `/auth/<сервис>/start/?next=` — `state` и `code_verifier` в сессию (10 минут),
   переход на сервис;
2. `/auth/<сервис>/callback/` — сервис вернул код. Дальше одно из четырёх:
   * этот аккаунт сервиса уже привязан → вход в свой аккаунт;
   * человек уже вошёл на сайте → привязать сервис к текущему аккаунту;
   * почта от сервиса подтверждена И у нас эта же почта подтверждена кодом у
     пользователя A → привязать к A и войти (автосклейка, решение 29.10.2026);
   * иначе → данные в сессию (`social_pending`, 30 минут, БЕЗ токенов) и экран
     «Почти готово» `/auth/finish/`;
3. `/auth/finish/` — наше согласие, затем новый аккаунт.

⚠️ НЕПОДТВЕРЖДЁННАЯ ПОЧТА ИЗ ПРОФИЛЯ НЕ СКЛЕИВАЕТСЯ. Её мог вписать кто угодно:
склейка по ней отдала бы чужой аккаунт тому, кто завёл в VK такой же адрес.

⚠️ `state` НЕ СОВПАЛ — 400 И НИ ОДНОГО АККАУНТА. Это защита от подложенного
кода: без неё злоумышленник привязал бы СВОЙ VK к чужому вошедшему аккаунту.

⚠️ Логин нового аккаунта — `econ_` + 6 случайных знаков, НЕ из имени: логин
виден в таблицах результатов, а имя ребёнка там светиться не должно.
"""
import logging
import secrets
import string
import time
from urllib.parse import urlencode

from django import forms
from django.conf import settings
from django.contrib.auth import login
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from legal import consent
from problems import email_codes, ratelimit, signup_source
from problems.models import SocialAccount, User
from problems.models_legal import ConsentRecord
from problems.models_platform import SignupSource, UserProfile
from problems.redirects import safe_next
from problems.views_auth import DEFAULT_NEXT, REGISTER_SCOPE, _account_email_url

from . import providers

logger = logging.getLogger(__name__)

#: Бэкенд входа после возврата с сервиса (промпт: явный EmailOrUsernameBackend).
LOGIN_BACKEND = 'problems.auth_backends.EmailOrUsernameBackend'
#: Счётчик частоты возвратов с сервиса — свой, как у входа (`problems/ratelimit.py`).
SCOPE = 'social'

FLOW_KEY = 'social_flow'
FLOW_TTL = 10 * 60
PENDING_KEY = 'social_pending'
PENDING_TTL = 30 * 60

USERNAME_PREFIX = 'econ_'
USERNAME_ALPHABET = string.ascii_lowercase + string.digits


def _fail_text(provider):
    return ('Не получилось войти через %s. Попробуйте ещё раз или войдите почтой'
            % provider.title)


def _error_page(request, text, *, status=400, link=None):
    link = link or (reverse('login'), 'Войти')
    return render(request, 'social/error.html', {
        'text': text, 'link_url': link[0], 'link_label': link[1], 'seo_noindex': True,
    }, status=status)


class NotConfigured(Exception):
    """Флаг включён, а ключа сервиса нет или он заглушка (`demo`)."""

    def __init__(self, provider):
        super().__init__(provider.name)
        self.provider = provider


def _provider_or_404(name):
    """Включённый сервис. Флаг выключен или сервис неизвестен — 404; флаг включён,
    а ключ не настоящий — `NotConfigured` (своя страница вместо чужой ошибки)."""
    provider = providers.get(name)
    if provider is not None:
        return provider
    known = providers.known(name)
    if known is None or not settings.SOCIAL_LOGIN_ENABLED:
        raise Http404
    raise NotConfigured(known)


def _not_configured_page(request, provider):
    """Прямой заход на сервис без ключа: наша страница, а не «400» сервиса."""
    return _error_page(request, 'Вход через %s пока не настроен' % provider.title,
                       status=503)


def _redirect_uri(request, provider):
    return request.build_absolute_uri(reverse('social_callback', args=[provider.name]))


def _role_home(user):
    """Куда вести вошедшего без `next` — как `RoleBasedLoginView`."""
    if user.role == 'teacher':
        return '/teacher/'
    if user.role == 'student':
        return '/student/'
    return '/'


def after_signup_url(target):
    """Новый аккаунт идёт на онбординг (с сохранённым `next`), а без него — как раньше."""
    if settings.ONBOARDING_ENABLED:
        return reverse('onboarding') + ('?' + urlencode({'next': target}) if target else '')
    return target or DEFAULT_NEXT


def _login(request, user, link):
    link.last_login_at = timezone.now()
    link.save(update_fields=['last_login_at'])
    login(request, user, backend=LOGIN_BACKEND)


def _set_avatar(user, url):
    """Аватар от сервиса — только если у профиля своего нет. Любая ошибка — молча."""
    from problems.forms_accounts import AvatarForm

    try:
        profile = user.profile
        if profile.avatar:
            return
        body = providers.download_avatar(url)
        if body is None:
            return
        form = AvatarForm(data={}, files={'avatar': SimpleUploadedFile('avatar', body)})
        if not form.is_valid():
            return
        profile.avatar.save('%d.jpg' % user.pk, ContentFile(form.squared_jpeg().read()),
                            save=True)
    except Exception:  # noqa: BLE001 — аватар по желанию
        logger.warning('Аватар от сервиса не поставлен (user=%s)', user.pk)


# ── 1. Переход на сервис ───────────────────────────────────────────────────

@require_GET
def start(request, provider):
    try:
        provider = _provider_or_404(provider)
    except NotConfigured as missing:
        return _not_configured_page(request, missing.provider)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)          # 86 знаков: PKCE просит 43–128
    request.session[FLOW_KEY] = {
        'provider': provider.name, 'state': state, 'verifier': verifier,
        'next': safe_next(request), 'at': time.time(),
    }
    return redirect(provider.authorize_redirect(_redirect_uri(request, provider),
                                                state, verifier))


# ── 2. Возврат с сервиса ───────────────────────────────────────────────────

@require_GET
def callback(request, provider):
    try:
        provider = _provider_or_404(provider)
    except NotConfigured as missing:
        return _not_configured_page(request, missing.provider)
    wait = ratelimit.check(SCOPE, request, None)
    if wait:
        return _error_page(request, _fail_text(provider), status=429)

    # Поток одноразовый: забираем его из сессии сразу, удачен возврат или нет.
    flow = request.session.pop(FLOW_KEY, None) or {}
    state = request.GET.get('state', '')
    if (flow.get('provider') != provider.name or not state
            or not secrets.compare_digest(str(flow.get('state', '')), state)
            or time.time() - flow.get('at', 0) > FLOW_TTL):
        ratelimit.register_failure(SCOPE, request, None)
        return _error_page(request, _fail_text(provider))
    if request.GET.get('error') or not request.GET.get('code'):
        # Человек нажал «Отмена» у сервиса или сервис отказал.
        return _error_page(request, _fail_text(provider))

    try:
        data = provider.fetch_profile(request.GET, flow['verifier'],
                                      _redirect_uri(request, provider), state)
    except providers.SocialError as error:
        logger.warning('Вход через %s не удался: %s', provider.title, error)
        ratelimit.register_failure(SCOPE, request, None)
        return _error_page(request, _fail_text(provider))

    target = flow.get('next') or ''
    link = (SocialAccount.objects.select_related('user')
            .filter(provider=provider.name, uid=data['uid']).first())

    # Шаг 2: человек уже вошёл — привязываем сервис к его аккаунту.
    if request.user.is_authenticated:
        if link is not None and link.user_id != request.user.pk:
            return _error_page(
                request, 'Этот %s уже привязан к другому аккаунту' % provider.title,
                link=(reverse('profile'), 'В профиль'))
        if link is None:
            try:
                SocialAccount.objects.create(user=request.user, provider=provider.name,
                                             uid=data['uid'])
            except IntegrityError:
                return _error_page(
                    request, 'Этот %s уже привязан к другому аккаунту' % provider.title,
                    link=(reverse('profile'), 'В профиль'))
            _set_avatar(request.user, data.get('avatar_url'))
        return redirect(target or reverse('profile'))

    # Шаг 1: этот аккаунт сервиса уже знаком.
    if link is not None:
        if not link.user.is_active:
            return _error_page(request, _fail_text(provider))
        _login(request, link.user, link)
        return redirect(target or _role_home(link.user))

    # Шаг 3: автосклейка — почта подтверждена и у сервиса, и у нас.
    # ⚠️ Сотрудников и суперпользователей не склеиваем никогда: вход в админку
    # не должен зависеть от того, кто завладел их почтой в VK или Яндексе.
    if data.get('email') and data.get('email_verified'):
        owner = email_codes.verified_user_for(data['email'])
        if (owner is not None and owner.is_active
                and not owner.is_staff and not owner.is_superuser):
            try:
                link = SocialAccount.objects.create(user=owner, provider=provider.name,
                                                    uid=data['uid'])
            except IntegrityError:
                return _error_page(request, _fail_text(provider))
            _login(request, owner, link)
            _set_avatar(owner, data.get('avatar_url'))
            return redirect(target or _role_home(owner))

    # Шаг 4: новый человек — на экран согласия. Токенов тут нет: только данные.
    request.session[PENDING_KEY] = dict(data, provider=provider.name, next=target,
                                        at=time.time())
    return redirect('social_finish')


# ── 3. «Почти готово»: согласие и новый аккаунт ────────────────────────────

class FinishForm(forms.Form):
    """Те же галочки, что на регистрации почтой (`RegisterWithEmailForm`)."""

    consent = forms.BooleanField(
        required=True,
        error_messages={'required': 'Без согласия зарегистрироваться нельзя.'})
    # ⚠️ НИКОГДА НЕ ОТМЕЧЕНА ЗАРАНЕЕ (ст. 18 закона «О рекламе»).
    mail_consent = forms.BooleanField(required=False, initial=False)


def mask_email(email):
    """m•••@mail.ru — адрес узнаётся, но целиком на экране не стоит."""
    local, _, domain = (email or '').partition('@')
    if not local or not domain:
        return ''
    return local[0] + '•••@' + domain


def _initials(pending):
    letters = [part[0] for part in (pending.get('first_name'), pending.get('last_name'))
               if part]
    return ''.join(letters).upper() or '?'


def _free_username():
    for _attempt in range(50):
        name = USERNAME_PREFIX + ''.join(secrets.choice(USERNAME_ALPHABET) for _ in range(6))
        if not User.objects.filter(username__iexact=name).exists():
            return name
    raise RuntimeError('не удалось подобрать свободный логин')


def _create_account(pending, form):
    """Пользователь, профиль, привязка и согласия — одной транзакцией."""
    with transaction.atomic():
        user = User(username=_free_username(),
                    first_name=(pending.get('first_name') or '')[:150],
                    last_name=(pending.get('last_name') or '')[:150])
        user.set_unusable_password()
        user.save()
        profile_fields = {'role': UserProfile.Role.STUDENT}
        if settings.SOCIAL_STORE_BIRTHDATE and pending.get('birth_date'):
            profile_fields['birth_date'] = pending['birth_date']
        UserProfile.objects.update_or_create(user=user, defaults=profile_fields)
        SocialAccount.objects.create(user=user, provider=pending['provider'],
                                     uid=pending['uid'], created_user=True,
                                     last_login_at=timezone.now())
        email = pending.get('email')
        if email and pending.get('email_verified'):
            try:
                email_codes.attach_verified_email(user, email)
            except email_codes.EmailTaken:
                # Почта занята другим аккаунтом: не привязываем, человек укажет
                # свою на странице «Почта».
                pass
        consent.grant(user, ConsentRecord.Kind.PD, ConsentRecord.Source.REGISTER)
        # Галочка рассылки есть только при включённой почте — как на регистрации.
        if email_codes.mail_enabled() and form.cleaned_data.get('mail_consent'):
            consent.grant(user, ConsentRecord.Kind.MAIL, ConsentRecord.Source.REGISTER)
    return user


def finish(request):
    if request.user.is_authenticated:
        return redirect('profile')
    pending = request.session.get(PENDING_KEY)
    if not pending or time.time() - pending.get('at', 0) > PENDING_TTL:
        request.session.pop(PENDING_KEY, None)
        return redirect('login')
    provider = providers.PROVIDERS.get(pending.get('provider'))
    if provider is None:
        request.session.pop(PENDING_KEY, None)
        return redirect('login')

    if request.method == 'GET' and request.GET.get('cancel'):
        # «Это не я»: данные чужого аккаунта сервиса в сессии не держим.
        request.session.pop(PENDING_KEY, None)
        return redirect('login')

    status = 200
    form = FinishForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST':
        wait = ratelimit.check(REGISTER_SCOPE, request, None)
        if wait:
            form = FinishForm()
            status = 429
        elif form.is_valid():
            try:
                user = _create_account(pending, form)
            except IntegrityError:
                # Этот аккаунт сервиса успели привязать параллельно.
                request.session.pop(PENDING_KEY, None)
                return _error_page(request, _fail_text(provider))
            request.session.pop(PENDING_KEY, None)
            # Хвост регистрации — как `views_auth.finish_signup`, но вход явным
            # EmailOrUsernameBackend (промпт).
            ratelimit.note_failure(REGISTER_SCOPE + ':ip', ratelimit.client_ip(request),
                                   multiplier=1)
            login(request, user, backend=LOGIN_BACKEND)
            consent.remember_in_session(request)
            signup_source.record_signup(request, user, SignupSource.Kind.STUDENT)
            _set_avatar(user, pending.get('avatar_url'))

            next_url = after_signup_url(pending.get('next') or '')
            # Почта обязательна (решение 26.10.2026) — но требуем её только у
            # аккаунтов, созданных через сервис; старых без почты не блокируем.
            if email_codes.mail_enabled() and not email_codes.has_verified_email(user):
                return redirect(_account_email_url(next_url, ''))
            return redirect(next_url)

    rows = [('Имя', ' '.join(p for p in (pending.get('first_name'),
                                          pending.get('last_name')) if p))]
    if pending.get('email'):
        rows.append(('Почта', mask_email(pending['email'])))
    if settings.SOCIAL_STORE_BIRTHDATE and pending.get('birth_date'):
        y, m, d = pending['birth_date'].split('-')
        rows.append(('Дата рождения', '%s.%s.%s' % (d, m, y)))
    if providers.avatar_url_allowed(pending.get('avatar_url')):
        rows.append(('Фото', 'есть'))
    return render(request, 'social/finish.html', {
        'form': form,
        'first_name': pending.get('first_name') or '',
        'initials': _initials(pending),
        'rows': [row for row in rows if row[1]],
        'provider': provider,
        'mail_enabled': email_codes.mail_enabled(),
        'rate_limited': status == 429,
        'seo_noindex': True,
    }, status=status)
