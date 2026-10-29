# -*- coding: utf-8 -*-
"""Вход в систему: куда пускать после входа и как не дать подобрать пароль.

Две вещи в одном месте, потому что обе живут на одной форме.

**Куда пускать.** Ученика — в кабинет, преподавателя — в панель,
остальных — в админку.

**Ограничение частоты.** Django из коробки принимает попытки входа
бесконечно: подобрать пароль мешает только его длина. Счётчики и ступени
запрета — в `problems/ratelimit.py`, там же написано, почему ключ
комбинированный (имя + адрес) и почему задержка нарастающая.

⚠️ **ПОКА ЗАПРЕТ ДЕЙСТВУЕТ, ПАРОЛЬ НЕ ПРОВЕРЯЕТСЯ ВОВСЕ.** Это не мелочь:
если бы форма всё равно вызывала `authenticate()`, ограничение считало бы
попытки, но не мешало бы их делать. Поэтому в запертом состоянии форма
даже не собирается связанной — до `clean()` дело не доходит.

⚠️ **СООБЩЕНИЕ ОБ ОТКАЗЕ НЕ НАЗЫВАЕТ ПРИЧИНУ.** Ни «такого пользователя
нет», ни «пароль неверный», ни «этот аккаунт заперт»: любое из них — ответ
на вопрос, существует ли аккаунт. Счётчик двигается одинаково для
существующего и несуществующего имени, поэтому и запрет наступает
одинаково.

⚠️ **Время ответа тоже не выдаёт существование аккаунта** — и это заслуга
Django, а не наша: `ModelBackend` при несуществующем имени всё равно считает
хэш пароля вхолостую (`UserModel().set_password`), чтобы отклик занимал
столько же. Закреплено тестом `problems/tests/test_auth_hardening.py`.
"""
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.hashers import make_password
from django.contrib.auth.views import LoginView, LogoutView  # noqa: F401
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic.edit import FormView

from legal import consent
from problems.models_legal import ConsentRecord
from problems import email_codes, ratelimit, signup_source
from problems.email_codes import Purpose, check_error, minutes, send_error
from problems.forms_accounts import RegisterForm, RegisterWithEmailForm
from problems.models import User
from problems.models_platform import SignupSource, UserProfile
from problems.redirects import safe_next
from problems.usernames import free_username

#: Каким бэкендом считается вход сразу после регистрации. Бэкендов два
#: (`problems/auth_backends.py`), и без явного имени `login()` откажется.
LOGIN_BACKEND = 'django.contrib.auth.backends.ModelBackend'

# Имя счётчика. Своё у каждого входа в систему: когда появятся регистрация
# и восстановление пароля, они возьмут свои имена и свои ступени.
SCOPE = 'login'


def wait_message(seconds):
    """Сколько ждать — по-русски и без подробностей о причине."""
    if seconds >= 60:
        return ('Слишком много попыток входа. Попробуйте через %d мин.'
                % ((seconds + 59) // 60))
    return 'Слишком много попыток входа. Попробуйте через %d с.' % seconds


def admin_login(request, extra_context=None):
    """Вход в админку под тем же счётчиком, что и `/login/`.

    ⚠️ ЗАЧЕМ (24.09.2026). `/admin/login/` — штатная вьюха Django, и лимита
    попыток у неё не было: перебор пароля сотрудника шёл мимо ступеней
    `RoleBasedLoginView`. Имя счётчика ТО ЖЕ (`SCOPE`), иначе нападающий
    чередовал бы два входа и получал вдвое больше попыток.

    Экран админки не меняется: вьюха та же, `admin.site.login`, обёрнута
    снаружи. Удачу и промах различаем по ответу: при успехе Django
    перенаправляет (302), при промахе снова рисует форму (200).
    """
    from django.contrib import admin
    from django.http import HttpResponse

    if request.method != 'POST':
        return admin.site.login(request, extra_context)
    ident = (request.POST.get('username') or '').strip()
    wait = ratelimit.check(SCOPE, request, ident)
    if wait:
        # Пароль не проверяется вовсе — как у основного входа.
        return HttpResponse(wait_message(wait), status=429,
                            content_type='text/plain; charset=utf-8')
    response = admin.site.login(request, extra_context)
    if response.status_code == 302:
        ratelimit.register_success(SCOPE, request, ident)
    else:
        ratelimit.register_failure(SCOPE, request, ident)
    return response


#: Сколько держать в кэше число задач для экрана входа: считать его на каждый
#: заход дорого, а точность до задачи здесь не нужна.
PITCH_CACHE_SECONDS = 60 * 60
MONTHS_GENITIVE = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
                   'августа', 'сентября', 'октября', 'ноября', 'декабря')


def _tour_phrase(today=None):
    """«2 тур 13–22 ноября» из `vp/config.py`, пока тур не прошёл; иначе пусто."""
    from vp import config as vp_config

    kind, value = vp_config.TOUR_DATES.get(vp_config.CURRENT_TOUR, (None, None))
    if not value:
        return ''
    first, last = value[0], value[-1]
    if last < (today or timezone.localdate()):
        return ''
    if first.month == last.month:
        days = '%d–%d %s' % (first.day, last.day, MONTHS_GENITIVE[last.month - 1])
    else:
        days = '%d %s – %d %s' % (first.day, MONTHS_GENITIVE[first.month - 1],
                                  last.day, MONTHS_GENITIVE[last.month - 1])
    return '%d тур %s' % (vp_config.CURRENT_TOUR, days)


def auth_pitch():
    """Левая колонка экрана входа (макет раунда 2): только правдивые цифры.

    Число задач — видимые в каталоге (тот же шлюз, что у каталога), дата тура —
    из `vp/config.py`. Нет данных — строки нет.
    """
    from django.core.cache import cache

    from catalog.filters import base_queryset
    from problems.templatetags.ru import plural_ru

    count = cache.get('auth_pitch_tasks')
    if count is None:
        count = base_queryset('catalog').count()
        cache.set('auth_pitch_tasks', count, PITCH_CACHE_SECONDS)
    tasks = ''
    if count:
        tasks = '%s %s' % ('{:,}'.format(count).replace(',', ' '),
                           plural_ru(count, 'задача,задачи,задач'))
    return {'tasks': tasks, 'tour': _tour_phrase()}


class RoleBasedLoginView(LoginView):
    """Вход с ограничением частоты и разводкой по ролям."""

    template_name = 'registration/login.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # С почтой экран говорит «Почта или логин» и ведёт на сброс по коду.
        context['mail_enabled'] = email_codes.mail_enabled()
        context['pitch'] = auth_pitch()
        return context

    def _ident(self):
        """Имя пользователя из запроса — ключ счётчика, не доказательство."""
        return (self.request.POST.get('username') or '').strip()

    def post(self, request, *args, **kwargs):
        wait = ratelimit.check(SCOPE, request, self._ident())
        if wait:
            # Форма НЕсвязанная: так `AuthenticationForm.clean()` не
            # выполнится и пароль не будет проверен. Экран тот же самый,
            # сообщение — только про ожидание.
            context = self.get_context_data(
                form=self.get_form_class()(request=request))
            context['lock_message'] = wait_message(wait)
            return self.render_to_response(context, status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        # ⚠️ Ключ сессии Django меняет сам (`login()` зовёт `cycle_key()`),
        # своего кода для этого не нужно — закреплено тестом.
        ratelimit.register_success(SCOPE, self.request, self._ident())
        return super().form_valid(form)

    def form_invalid(self, form):
        ratelimit.register_failure(SCOPE, self.request, self._ident())
        return super().form_invalid(form)

    def get_success_url(self):
        # ⚠️ `next` — ПЕРВЫМ, иначе ссылки вида /login/?next=/game/duel/...
        # (анонимный переход по приглашению в дуэль) всегда сбрасывают
        # человека на дефолтный экран роли, а не туда, куда он шёл.
        # `get_redirect_url()` — штатная проверка Django на чужой хост
        # (открытый редирект), поэтому небезопасный next отбрасывается
        # сам, без своей проверки здесь.
        redirect_to = self.get_redirect_url()
        if redirect_to:
            return redirect_to
        user = self.request.user
        if user.role == 'student':
            return '/student/'
        if user.role == 'teacher':
            return '/teacher/'
        return '/admin/'


# ═══════════════════════════════════════════════════════════════════════
# Регистрация
# ═══════════════════════════════════════════════════════════════════════
#
# ⚠️ СВОЙ СЧЁТЧИК, А НЕ ОБЩИЙ СО ВХОДОМ. Регистрацию и вход ограничивают
# разные вещи: у входа считается подбор пароля к КОНКРЕТНОМУ имени, здесь —
# массовое создание аккаунтов с одного адреса. Общий счётчик означал бы,
# что неудачные входы запирают регистрацию, и наоборот.
#
# ⚠️ СЧЁТ ИДЁТ ПО АДРЕСУ И ПО УСПЕХАМ, А НЕ ПО ПРОМАХАМ. У входа промах —
# признак подбора; здесь промах это обычная опечатка в пароле, а вредна как
# раз УДАЧНАЯ регистрация, повторённая двадцать раз.
REGISTER_SCOPE = 'register'


#: Ключ сессии с анкетой регистрации, ждущей кода (только при MAIL_ENABLED).
PENDING_KEY = 'pending_registration'
#: Сколько анкета ждёт кода, прежде чем её придётся заполнить заново.
PENDING_TTL = 30 * 60
#: Куда уходит зарегистрировавшийся, если пришёл без `next`.
DEFAULT_NEXT = '/profile/?welcome=1'
#: Роль профиля до онбординга: выбирает её сам человек на `/welcome/`.
DEFAULT_ROLE = 'student'


class RegisterView(FormView):
    """Регистрация (раунд 2, решение владельца 29.10.2026: «почта + пароль»).

    Роли в форме нет: её спрашивает онбординг (`/welcome/`), а до него профиль
    ученический — `UserProfile.role = student`, как у входа через сервисы.

    Почта выключена (`MAIL_ENABLED=0`): логин и пароль, аккаунт создаётся
    сразу; «Забыли пароль» — через Telegram.

    Почта включена (решение владельца 26.10.2026, docs/MAIL.md): почта и пароль,
    логин придумывает сайт (`problems/usernames.py`). Это ШАГ 1 из
    двух. Аккаунт здесь НЕ создаётся: анкета (с хешем пароля, открытого пароля
    в сессии нет) ложится в сессию, на почту уходит код, а аккаунт создаёт
    шаг 2 — `RegisterConfirmView`, когда почта доказана.

    ⚠️ `next` СЛУШАЕТСЯ, НО ТОЛЬКО СВОЙ (`problems/redirects.py`). Тренажёр ВП
    уводит гостя сюда со своего варианта и ждёт его обратно; `next` переживает
    оба шага. Чужой адрес молча заменяется прежним `/profile/?welcome=1`.
    """

    template_name = 'registration/register.html'
    form_class = RegisterForm
    #: Куда уходит тот, кто пришёл без `next`.
    default_next = DEFAULT_NEXT

    def _next(self):
        """Безопасный адрес возврата из запроса или пусто."""
        return safe_next(self.request)

    def get_form_class(self):
        return RegisterWithEmailForm if email_codes.mail_enabled() else RegisterForm

    def get_initial(self):
        initial = super().get_initial()
        pending = self.request.session.get(PENDING_KEY)
        # «Изменить почту» со второго шага: форма заполнена всем, кроме пароля.
        if (email_codes.mail_enabled() and pending
                and self.request.method == 'GET' and self.request.GET.get('edit')):
            initial.update(email=pending['email'], mail_consent=pending['mail_consent'],
                           role=pending.get('role') or DEFAULT_ROLE, consent=True)
        return initial

    def dispatch(self, request, *args, **kwargs):
        # Вошедшему регистрироваться незачем — уводим в профиль.
        if request.user.is_authenticated:
            return redirect('profile')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['locked_seconds'] = ratelimit.check(REGISTER_SCOPE,
                                                    self.request, None)
        context['next'] = self._next()
        if not context['next'] and self.request.GET.get('edit'):
            context['next'] = (self.request.session.get(PENDING_KEY) or {}).get('next', '')
        context['mail_enabled'] = email_codes.mail_enabled()
        return context

    def post(self, request, *args, **kwargs):
        wait = ratelimit.check(REGISTER_SCOPE, request, None)
        if wait:
            # 429, как на входе: форма даже не собирается связанной.
            form = self.get_form_class()()
            response = self.render_to_response(
                self.get_context_data(form=form, locked_seconds=wait,
                                      rate_limited=True))
            response.status_code = 429
            return response
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        if email_codes.mail_enabled():
            return self._start_confirmation(form)
        # ⚠️ ПОЛЬЗОВАТЕЛЬ, ПРОФИЛЬ И ЗАПИСЬ СОГЛАСИЯ — ОДНОЙ ТРАНЗАКЦИЕЙ
        # (Правовой контур, часть А). Иначе сбой между шагами оставил бы
        # человека с аккаунтом, но без доказательства, что он принял
        # документы, — и экран согласия потом встретил бы его на первом входе.
        with transaction.atomic():
            user = form.save()

            # Профиль ученический до онбординга, там человек выберет роль сам.
            # `UserProfile.save()` подтянет старое поле `User.role`.
            profile_role = form.cleaned_data.get('role') or DEFAULT_ROLE
            UserProfile.objects.update_or_create(
                user=user, defaults={'role': profile_role})
            consent.grant(user, ConsentRecord.Kind.PD, ConsentRecord.Source.REGISTER)

        return finish_signup(self.request, user, profile_role,
                             self._next() or self.default_next)

    def _start_confirmation(self, form):
        """Шаг 1 с почтой: анкета в сессию, код на почту, переход к шагу 2."""
        data = form.cleaned_data
        email = data['email']
        previous = self.request.session.get(PENDING_KEY) or {}
        pending = {
            'email': email,
            # ⚠️ ТОЛЬКО ХЕШ: открытый пароль в сессию (а значит, в Redis и в
            # базу сессий) не попадает никогда.
            'password_hash': make_password(data['password1']),
            'role': data.get('role') or DEFAULT_ROLE,
            'mail_consent': bool(data.get('mail_consent')),
            'next': self._next(),
            'started_at': time.time(),
        }
        result = email_codes.send_code(email, Purpose.REGISTER, request=self.request)
        if result.ok or (result.reason == 'wait' and previous.get('email') == email):
            self.request.session[PENDING_KEY] = pending
            if not result.ok:
                messages.info(self.request, 'Код уже отправлен, проверьте почту.')
            return redirect('register_confirm')
        if result.reason == 'ip_locked':
            # 429, как у нынешнего запрета регистраций с одного адреса.
            response = self.render_to_response(self.get_context_data(
                form=form, locked_seconds=result.wait_seconds, rate_limited=True))
            response.status_code = 429
            return response
        form.add_error(None, send_error(result))
        return self.form_invalid(form)


def finish_signup(request, user, profile_role, target):
    """Общий хвост регистрации: счётчик, вход, источник регистрации, переход."""
    # Считаем УДАЧНУЮ регистрацию: см. комментарий у REGISTER_SCOPE.
    ratelimit.note_failure(REGISTER_SCOPE + ':ip', ratelimit.client_ip(request),
                           multiplier=1)

    login(request, user, backend=LOGIN_BACKEND)   # cycle_key Django делает сам
    consent.remember_in_session(request)

    # Источник регистрации и цель Метрики (ADR 0133) — ПОСЛЕ входа: цель
    # ложится в сессию. Вид — по выбранной роли. ⚠️ `invited` отсюда не
    # приходит: ссылки-приглашения в продукте нет, ученик вводит код
    # занятия уже после регистрации (`student:join_group`).
    kind = (SignupSource.Kind.TEACHER if profile_role == 'tutor'
            else SignupSource.Kind.STUDENT)
    # Раунд 2: при онбординге роль ещё не выбрана — вид уточнит и цель Метрики
    # отправит шаг «Кто вы?» (`signup_source.confirm_role`).
    signup_source.record_signup(request, user, kind,
                                defer_goal=settings.ONBOARDING_ENABLED)
    return redirect(target)


class _Taken(Exception):
    """Логин или почту заняли, пока человек ждал письма."""


class RegisterConfirmView(View):
    """Шаг 2 регистрации с почтой: ввести код, и только тогда создать аккаунт.

    ⚠️ ЗАНЯТОСТЬ ПРОВЕРЯЕТСЯ ЕЩЁ РАЗ, ВНУТРИ ТРАНЗАКЦИИ. Между шагами проходят
    минуты: логин могли занять, почту — подтвердить другим аккаунтом. Проверка
    формы на шаге 1 к этому моменту уже ничего не доказывает.
    """

    template_name = 'registration/register_confirm.html'

    def dispatch(self, request, *args, **kwargs):
        if not email_codes.mail_enabled():
            raise Http404
        if request.user.is_authenticated:
            return redirect('profile')
        pending = request.session.get(PENDING_KEY)
        if not pending:
            return redirect('register')
        if time.time() - pending.get('started_at', 0) > PENDING_TTL:
            request.session.pop(PENDING_KEY, None)
            messages.error(request, 'Время подтверждения вышло, заполните форму ещё раз.')
            return redirect('register')
        self.pending = pending
        return super().dispatch(request, *args, **kwargs)

    def render_page(self, error=''):
        email = self.pending['email']
        return render(self.request, self.template_name, {
            'email': email,
            'error': error,
            'resend_wait': email_codes.resend_wait(email, Purpose.REGISTER),
            'seo_noindex': True,
        })

    def get(self, request):
        return self.render_page()

    def post(self, request):
        email = self.pending['email']
        if request.POST.get('action') == 'resend':
            result = email_codes.send_code(email, Purpose.REGISTER, request=request)
            if result.ok:
                messages.success(request, 'Мы отправили новый код.')
            else:
                messages.error(request, send_error(result))
            return redirect('register_confirm')

        check = email_codes.check_code(email, Purpose.REGISTER, request.POST.get('code', ''))
        if not check.ok:
            return self.render_page(check_error(check))
        try:
            user = self._create_account()
        except _Taken as taken:
            request.session.pop(PENDING_KEY, None)
            messages.error(request, str(taken))
            return redirect('register')
        pending = request.session.pop(PENDING_KEY)
        return finish_signup(request, user, pending.get('role') or DEFAULT_ROLE,
                             pending.get('next') or DEFAULT_NEXT)

    def _create_account(self):
        pending = self.pending
        try:
            with transaction.atomic():
                if email_codes.verified_user_for(pending['email']) is not None:
                    raise _Taken('Эта почта уже привязана к аккаунту. Войдите или '
                                 'восстановите пароль.')
                # Логин придумывает сайт (раунд 2): `econ_` + 6 знаков, свободный.
                user = User(username=free_username(), email=pending['email'],
                            email_verified_at=timezone.now(),
                            password=pending['password_hash'])
                user.save()
                # Профиль ученический до онбординга (роль выбирают там).
                UserProfile.objects.update_or_create(
                    user=user, defaults={'role': pending.get('role') or DEFAULT_ROLE})
                consent.grant(user, ConsentRecord.Kind.PD, ConsentRecord.Source.REGISTER)
                if pending.get('mail_consent'):
                    consent.grant(user, ConsentRecord.Kind.MAIL,
                                  ConsentRecord.Source.REGISTER)
        except IntegrityError:
            # Ту же почту (или тот же случайный логин) записали параллельно, в ту же секунду.
            raise _Taken('Не получилось создать аккаунт. Начните регистрацию заново.')
        return user


# ═══════════════════════════════════════════════════════════════════════
# Сброс пароля кодом из письма (docs/MAIL.md, решение владельца 26.10.2026)
# ═══════════════════════════════════════════════════════════════════════
#
# ⚠️ ОТВЕТ НЕ ВЫДАЁТ, ЕСТЬ ЛИ АККАУНТ С ЭТОЙ ПОЧТОЙ. На любую почту — один и
# тот же текст и тот же переход; на неверный код — одна и та же ошибка. Таймер
# кнопки повтора считается от момента ЗАПРОСА в сессии, а не по письмам в
# базе: иначе он шёл бы только у существующих адресов.
#
# ⚠️ СНАЧАЛА ПАРОЛЬ, ПОТОМ КОД. Валидаторы пароля проверяются раньше кода:
# слишком короткий пароль не должен сжигать код и одну из пяти попыток.
RESET_SCOPE = 'reset'
RESET_SESSION_KEY = 'password_reset'
RESET_SENT_TEXT = 'Если эта почта привязана к аккаунту, мы отправили на неё код.'
RESET_WRONG_TEXT = 'Неверный или устаревший код.'
RESET_LOCKED_TEXT = 'Слишком много попыток. Запросите новый код.'


def _mail_or_404():
    if not email_codes.mail_enabled():
        raise Http404


def _reset_send(request, email):
    """Отправить код сброса, если почта подтверждена у кого-то. Ответ — всегда один."""
    user = email_codes.verified_user_for(email)
    if user is not None:
        email_codes.send_code(email, Purpose.RESET, user=user, request=request)
    request.session[RESET_SESSION_KEY] = {'email': email, 'requested_at': time.time()}


def _reset_wait(request):
    state = request.session.get(RESET_SESSION_KEY) or {}
    left = email_codes.RESEND_AFTER - (time.time() - state.get('requested_at', 0))
    return max(0, int(left + 0.999))


def password_forgot(request):
    """Шаг 1: почта, указанная в аккаунте."""
    _mail_or_404()
    from django import forms

    class ForgotForm(forms.Form):
        email = forms.EmailField(
            label='Почта, указанная в аккаунте', max_length=254,
            error_messages={'required': 'Укажите почту.',
                            'invalid': 'Это не похоже на адрес почты.'})

    form = ForgotForm(request.POST or None)
    error = ''
    status = 200
    if request.method == 'POST' and form.is_valid():
        email = email_codes.normalize_email(form.cleaned_data['email'])
        wait = ratelimit.check(RESET_SCOPE, request, email)
        if wait:
            error, status = ('Слишком много попыток. Попробуйте через %d мин.'
                             % minutes(wait)), 429
        else:
            _reset_send(request, email)
            messages.success(request, RESET_SENT_TEXT)
            return redirect('password_forgot_code')
    return render(request, 'registration/password_forgot.html',
                  {'form': form, 'error': error, 'seo_noindex': True}, status=status)


def password_forgot_code(request):
    """Шаг 2: код из письма и новый пароль дважды."""
    from django.contrib.auth.forms import SetPasswordForm

    _mail_or_404()
    state = request.session.get(RESET_SESSION_KEY)
    if not state:
        return redirect('password_forgot')
    email = state['email']
    user = email_codes.verified_user_for(email)

    if request.method == 'POST' and request.POST.get('action') == 'resend':
        if _reset_wait(request) == 0 and not ratelimit.check(RESET_SCOPE, request, email):
            _reset_send(request, email)
        messages.success(request, RESET_SENT_TEXT)
        return redirect('password_forgot_code')

    # Для похожести пароля на логин нужен пользователь; почты без аккаунта
    # проверяются на пустышке — так и ошибки пароля одинаковы для всех.
    form = SetPasswordForm(user or User(email=email), request.POST or None)
    form.fields['new_password1'].label = 'Новый пароль'
    form.fields['new_password2'].label = 'Новый пароль ещё раз'
    error = ''
    status = 200
    if request.method == 'POST':
        wait = ratelimit.check(RESET_SCOPE, request, email)
        if wait:
            error, status = RESET_LOCKED_TEXT, 429
        elif form.is_valid():
            check = email_codes.check_code(email, Purpose.RESET, request.POST.get('code', ''))
            if check.ok and user is not None:
                form.save()     # set_password + save: прежние сессии гаснут сами
                ratelimit.register_success(RESET_SCOPE, request, email)
                request.session.pop(RESET_SESSION_KEY, None)
                messages.success(request, 'Пароль изменён. Войдите с новым паролем.')
                return redirect('login')
            ratelimit.register_failure(RESET_SCOPE, request, email)
            error = RESET_LOCKED_TEXT if check.reason == 'locked' else RESET_WRONG_TEXT
    return render(request, 'registration/password_forgot_code.html', {
        'form': form, 'error': error, 'resend_wait': _reset_wait(request),
        'seo_noindex': True,
    }, status=status)


# ═══════════════════════════════════════════════════════════════════════
# Страница «Почта» /account/email/ (docs/MAIL.md)
# ═══════════════════════════════════════════════════════════════════════
#
# Через неё вошедший добавляет, меняет или подтверждает почту и включает или
# выключает рассылку. Стена тренажёра ВП ведёт сюда с `?next=/vp/...&src=vp`:
# `next` — куда вернуть (только свой адрес), `src=vp` — источник согласия
# «Стена тренажёра ВП» в записи.
#
# ⚠️ ПОЧТА МЕНЯЕТСЯ ТОЛЬКО ПО КОДУ. Новый адрес ложится в сессию, в базу он
# попадает, когда код из письма сошёлся; занятость адреса проверяется ещё раз
# внутри транзакции.
EMAIL_CHANGE_KEY = 'email_change'
ACCOUNT_EMAIL_DEFAULT_NEXT = '/profile/?tab=data'


def _account_email_url(next_url, src):
    from urllib.parse import urlencode
    query = {k: v for k, v in (('next', next_url), ('src', src)) if v}
    return '/account/email/' + ('?' + urlencode(query) if query else '')


def _consent_source(src):
    return (ConsentRecord.Source.VP_WALL if src == 'vp'
            else ConsentRecord.Source.EMAIL_PAGE)


def _apply_mail_consent(user, wanted, src):
    """Галочка рассылки → запись согласия. Отзыв ничего не удаляет."""
    if wanted:
        consent.grant(user, ConsentRecord.Kind.MAIL, _consent_source(src))
    elif consent.wants_mail(user):
        consent.revoke(user, ConsentRecord.Kind.MAIL)


def account_email(request):
    from django import forms
    from django.contrib.auth.views import redirect_to_login

    _mail_or_404()
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path(), '/login/')
    user = request.user
    target = safe_next(request)
    src = request.POST.get('src') or request.GET.get('src') or ''
    if src not in ('vp', 'onb'):
        src = ''
    pending = request.session.get(EMAIL_CHANGE_KEY)

    class EmailForm(forms.Form):
        email = forms.EmailField(
            label='Почта', max_length=254,
            error_messages={'required': 'Укажите почту.',
                            'invalid': 'Это не похоже на адрес почты.'})
        mail_consent = forms.BooleanField(required=False)

    if request.GET.get('change') and pending:
        # «Изменить почту» на шаге кода: обратно к форме с прежними значениями.
        request.session.pop(EMAIL_CHANGE_KEY, None)
        form = EmailForm(initial={'email': pending['email'],
                                  'mail_consent': pending['mail_consent']})
        target, src = pending.get('next') or '', pending.get('src') or ''
        pending = None
    else:
        form = EmailForm(initial={'email': user.email,
                                  'mail_consent': consent.wants_mail(user)})
    action = request.POST.get('action') if request.method == 'POST' else ''
    error = ''

    if action in ('code', 'resend') and pending:
        email = pending['email']
        here = _account_email_url(pending.get('next'), pending.get('src'))
        if action == 'resend':
            result = email_codes.send_code(email, Purpose.CONFIRM, user=user, request=request)
            if result.ok:
                messages.success(request, 'Мы отправили новый код.')
            else:
                messages.error(request, send_error(result))
            return redirect(here)
        check = email_codes.check_code(email, Purpose.CONFIRM, request.POST.get('code', ''))
        if check.ok:
            try:
                email_codes.attach_verified_email(user, email)
            except email_codes.EmailTaken:
                request.session.pop(EMAIL_CHANGE_KEY, None)
                messages.error(request, email_codes.TAKEN_MESSAGE)
                return redirect(here)
            _apply_mail_consent(user, pending['mail_consent'], pending.get('src'))
            request.session.pop(EMAIL_CHANGE_KEY, None)
            messages.success(request, 'Почта подтверждена.')
            return redirect(pending.get('next') or ACCOUNT_EMAIL_DEFAULT_NEXT)
        error = check_error(check)

    elif action == 'save':
        form = EmailForm(request.POST)
        if form.is_valid():
            email = email_codes.normalize_email(form.cleaned_data['email'])
            wanted = form.cleaned_data['mail_consent']
            if (email_codes.has_verified_email(user)
                    and email == email_codes.normalize_email(user.email)):
                # Почта та же и уже подтверждена: меняется только галочка, без кода.
                _apply_mail_consent(user, wanted, src)
                messages.success(request, 'Сохранено.')
                return redirect(target or ACCOUNT_EMAIL_DEFAULT_NEXT)
            other = email_codes.verified_user_for(email)
            if other is not None and other.pk != user.pk:
                form.add_error('email', 'Эта почта уже привязана к другому аккаунту.')
            else:
                result = email_codes.send_code(email, Purpose.CONFIRM, user=user,
                                               request=request)
                previous = (request.session.get(EMAIL_CHANGE_KEY) or {}).get('email')
                if result.ok or (result.reason == 'wait' and previous == email):
                    request.session[EMAIL_CHANGE_KEY] = {
                        'email': email, 'mail_consent': wanted,
                        'next': target, 'src': src}
                    if not result.ok:
                        messages.info(request, 'Код уже отправлен, проверьте почту.')
                    return redirect(_account_email_url(target, src))
                form.add_error(None, send_error(result))

    if pending:
        target, src = pending.get('next') or '', pending.get('src') or ''
    template, extra = _account_email_look(user, src)
    return render(request, template, dict(extra, **{
        'form': form,
        'pending': pending,
        'error': error,
        'verified': email_codes.has_verified_email(user),
        'current_email': user.email,
        'resend_wait': (email_codes.resend_wait(pending['email'], Purpose.CONFIRM)
                        if pending else 0),
        'next': target,
        'src': src,
        'change_url': _account_email_url(target, src) + ('&' if (target or src) else '?') + 'change=1',
        'seo_noindex': True,
    }))


def _account_email_look(user, src):
    """Вид страницы «Почта»: кабинетный или экран входа (раунд 2).

    Экран входа «Осталась почта» (`registration/need_email.html`) — аккаунту из
    VK ID / Яндекс ID без подтверждённой почты и старому аккаунту с шага
    онбординга «Добавьте почту» (`src=onb`). Логика страницы одна и та же.
    """
    from problems.views_onboarding import needs_service_email

    if needs_service_email(user):
        link = user.social_accounts.filter(created_user=True).order_by('pk').first()
        from problems.social.providers import PROVIDERS
        provider = PROVIDERS.get(link.provider) if link else None
        name = ' '.join(p for p in (user.first_name, user.last_name) if p)
        return 'registration/need_email.html', {
            'service': provider.title if provider else '', 'display_name': name}
    if src == 'onb':
        return 'registration/need_email.html', {'service': ''}
    return 'platform/account_email.html', {}
