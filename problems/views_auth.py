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
from django.contrib.auth.views import LoginView, LogoutView  # noqa: F401

from problems import ratelimit

# Имя счётчика. Своё у каждого входа в систему: когда появятся регистрация
# и восстановление пароля, они возьмут свои имена и свои ступени.
SCOPE = 'login'


def wait_message(seconds):
    """Сколько ждать — по-русски и без подробностей о причине."""
    if seconds >= 60:
        return ('Слишком много попыток входа. Попробуйте через %d мин.'
                % ((seconds + 59) // 60))
    return 'Слишком много попыток входа. Попробуйте через %d с.' % seconds


class RoleBasedLoginView(LoginView):
    """Вход с ограничением частоты и разводкой по ролям."""

    template_name = 'registration/login.html'

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
