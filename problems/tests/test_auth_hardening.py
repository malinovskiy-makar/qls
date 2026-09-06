# -*- coding: utf-8 -*-
"""Фаза 4: вход в аккаунт до прихода живых репетиторов.

Что проверяется и почему именно это.

**Подбор пароля.** Django из коробки принимает попытки входа бесконечно.
Ступени запрета — в `problems/ratelimit.py`; здесь проверяется, что они
действительно наступают и что во время запрета пароль не проверяется вовсе
(иначе ограничение считало бы попытки, но не мешало бы их делать).

**Не разглашать существование аккаунта.** Ответ на неверный вход обязан
быть одинаков для существующего и несуществующего имени — по тексту, по
коду и по времени. Первые два проверяются напрямую; третье держится тем,
что `ModelBackend` при несуществующем имени всё равно считает хэш вхолостую
(`UserModel().set_password`). Замер времени в набор НЕ ставится: он был бы
плавающим на любой загруженной машине и краснел бы по чужой причине.
Вместо замера проверяется механизм, который эту равность обеспечивает.

**Сессии.** Ключ сессии обязан меняться после входа (иначе подсунутый до
входа идентификатор остаётся рабочим), а смена пароля обязана обрывать
все остальные сессии этого человека.

⚠️ **Регистрации, восстановления пароля и приглашений в проекте НЕТ** —
проверено обходом маршрутов: в `config/urls.py` есть только вход, выход и
смена пароля. Поэтому здесь нет ни тестов на них, ни ограничений частоты
для них: ограничивать нечего. `ratelimit` заведён так, чтобы новый поток
взял своё имя счётчика (`SCOPE`) и получил ступени бесплатно.
"""
import re

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import NoReverseMatch, reverse

from problems import ratelimit
from problems.views_auth import SCOPE

User = get_user_model()

GOOD_PASSWORD = 'nastoyashiy-parol-12345'
WRONG_PASSWORD = 'ne-tot-parol-99999'



def _without_noise(response, typed_name):
    """Тело ответа без того, что законно различается от запроса к запросу.

    ⚠️ Два источника шума, и оба не имеют отношения к разглашению:

    * **CSRF-токен** — он случайный в КАЖДОМ ответе, даже двух подряд для
      одного человека. Сравнение сырых тел падало бы всегда и не значило
      ничего;
    * **введённое имя** — форма возвращает его в поле, чтобы человек не
      набирал заново. Оно пришло от того же, кто его и набрал, — сообщить
      ему его собственный ввод нельзя считать утечкой.

    Всё остальное обязано совпасть побайтово.
    """
    body = response.content.decode('utf-8', 'replace')
    body = re.sub(r'name="csrfmiddlewaretoken" value="[^"]*"',
                  'name="csrfmiddlewaretoken" value="X"', body)
    return body.replace(typed_name, 'ВВЕДЁННОЕ-ИМЯ')


class AuthTestCase(TestCase):
    def setUp(self):
        # ⚠️ Счётчики живут в кэше, а кэш НЕ откатывается транзакцией теста.
        # Без очистки тесты влияют друг на друга, и порядок у них алфавитный.
        cache.clear()
        self.user = User.objects.create_user(
            'realnyy_uchitel', password=GOOD_PASSWORD, role='teacher')
        self.url = reverse('login')

    def try_login(self, username, password, client=None):
        client = client or Client()
        return client.post(self.url,
                           {'username': username, 'password': password})


class RateLimitTests(AuthTestCase):
    """Серия неудачных входов упирается в предел."""

    def test_five_failures_lock_the_form(self):
        client = Client()
        for number in range(5):
            response = self.try_login('realnyy_uchitel', WRONG_PASSWORD,
                                      client)
            self.assertEqual(response.status_code, 200,
                             'Попытка %d уже заперта — слишком рано' % number)

        blocked = self.try_login('realnyy_uchitel', WRONG_PASSWORD, client)
        self.assertEqual(blocked.status_code, 429)
        self.assertIn('Слишком много попыток',
                      blocked.content.decode('utf-8', 'replace'))

    def test_lock_does_not_check_the_password(self):
        """Даже ВЕРНЫЙ пароль не пускает, пока запрет действует.

        Это и есть смысл ограничения. Если бы форма всё равно вызывала
        проверку пароля, счётчик считал бы попытки, но перебор шёл бы
        своим чередом.
        """
        client = Client()
        for _ in range(6):
            self.try_login('realnyy_uchitel', WRONG_PASSWORD, client)

        response = self.try_login('realnyy_uchitel', GOOD_PASSWORD, client)
        self.assertEqual(response.status_code, 429)
        self.assertNotIn('_auth_user_id', client.session)

    def test_successful_login_clears_the_name_counter(self):
        client = Client()
        for _ in range(3):
            self.try_login('realnyy_uchitel', WRONG_PASSWORD, client)
        self.assertEqual(ratelimit.failures(SCOPE, 'realnyy_uchitel'), 3)

        self.try_login('realnyy_uchitel', GOOD_PASSWORD, client)
        self.assertEqual(ratelimit.failures(SCOPE, 'realnyy_uchitel'), 0)

    def test_ip_counter_survives_a_successful_login(self):
        """Иначе перебор снимал бы запрет входом в свой же аккаунт."""
        client = Client()
        for _ in range(3):
            self.try_login('realnyy_uchitel', WRONG_PASSWORD, client)
        before = ratelimit.failures(SCOPE + ':ip', '127.0.0.1')
        self.assertGreater(before, 0)

        self.try_login('realnyy_uchitel', GOOD_PASSWORD, client)
        self.assertEqual(ratelimit.failures(SCOPE + ':ip', '127.0.0.1'),
                         before)

    def test_lock_by_name_does_not_depend_on_the_account_existing(self):
        """Несуществующее имя запирается так же — иначе разница видна."""
        client = Client()
        for _ in range(6):
            self.try_login('takogo-net-voobshe', WRONG_PASSWORD, client)
        response = self.try_login('takogo-net-voobshe', WRONG_PASSWORD, client)
        self.assertEqual(response.status_code, 429)

    def test_good_login_still_works(self):
        """Контроль: без промахов вход обязан работать как прежде."""
        client = Client()
        response = self.try_login('realnyy_uchitel', GOOD_PASSWORD, client)
        self.assertEqual(response.status_code, 302)
        self.assertIn('_auth_user_id', client.session)


class NoAccountDisclosureTests(AuthTestCase):
    """Ответ не говорит, существует ли такой аккаунт."""

    def test_answers_are_identical(self):
        existing = self.try_login('realnyy_uchitel', WRONG_PASSWORD)
        cache.clear()
        missing = self.try_login('takogo-net-voobshe', WRONG_PASSWORD)

        self.assertEqual(existing.status_code, missing.status_code)
        self.assertEqual(
            _without_noise(existing, 'realnyy_uchitel'),
            _without_noise(missing, 'takogo-net-voobshe'),
            'Ответы на существующее и несуществующее имя различаются — по '
            'этой разнице составляют список заведённых аккаунтов.')

    def test_page_does_not_name_the_reason(self):
        body = self.try_login('takogo-net-voobshe', WRONG_PASSWORD).content
        text = body.decode('utf-8', 'replace')
        for leak in ('не существует', 'не найден', 'нет такого',
                     'неверный пароль', 'Неверный пароль'):
            self.assertNotIn(leak, text)

    def test_backend_hashes_even_for_a_missing_user(self):
        """Механизм равного времени: он в Django, и он на месте.

        Замерять секунды в тесте бессмысленно — цифра плавает. Проверяем
        то, от чего она зависит: `ModelBackend` при отсутствии пользователя
        всё равно считает хэш.
        """
        import inspect

        from django.contrib.auth.backends import ModelBackend

        source = inspect.getsource(ModelBackend.authenticate)
        self.assertIn('set_password', source,
                      'Django перестал считать хэш вхолостую — равное время '
                      'ответа больше ничем не обеспечено, нужен свой код.')


class SessionTests(AuthTestCase):
    """Ключ сессии после входа и чужие сессии после смены пароля."""

    def test_session_key_rotates_on_login(self):
        client = Client()
        # Заводим сессию ДО входа — именно её и подсовывают жертве.
        client.get(self.url)
        client.session['marker'] = 1
        client.session.save()
        before = client.session.session_key

        self.try_login('realnyy_uchitel', GOOD_PASSWORD, client)
        after = client.session.session_key

        self.assertIsNotNone(after)
        self.assertNotEqual(
            before, after,
            'Ключ сессии не сменился при входе: идентификатор, подсунутый '
            'до входа, остаётся рабочим и после него.')

    def test_password_change_kills_other_sessions(self):
        first = Client()
        second = Client()
        self.assertTrue(first.login(username='realnyy_uchitel',
                                    password=GOOD_PASSWORD))
        self.assertTrue(second.login(username='realnyy_uchitel',
                                     password=GOOD_PASSWORD))

        response = first.post(reverse('password_change'), {
            'old_password': GOOD_PASSWORD,
            'new_password1': 'sovsem-drugoy-parol-77',
            'new_password2': 'sovsem-drugoy-parol-77',
        })
        self.assertEqual(response.status_code, 302, response.content[:400])

        # Тот, кто менял, остаётся внутри.
        self.assertEqual(first.get('/profile/').status_code, 200)
        # А вторая сессия — уже нет.
        other = second.get('/profile/')
        self.assertEqual(
            other.status_code, 302,
            'Вторая сессия пережила смену пароля: угнанный вход не '
            'закрывается сменой пароля.')


class PasswordPolicyTests(TestCase):
    """Требования к паролю: встроенные валидаторы, минимум 10 символов."""

    def test_short_password_is_refused(self):
        from django.core.exceptions import ValidationError
        from django.contrib.auth.password_validation import validate_password

        with self.assertRaises(ValidationError):
            validate_password('devyat123')          # девять символов
        # Контроль: десять символов и не из словаря — проходят.
        validate_password('shhuka-71-more')

    def test_common_and_numeric_passwords_are_refused(self):
        from django.core.exceptions import ValidationError
        from django.contrib.auth.password_validation import validate_password

        for bad in ('password123', '1234567890'):
            with self.subTest(password=bad):
                with self.assertRaises(ValidationError):
                    validate_password(bad)


class NoForeignAuthProvidersTests(TestCase):
    """Иностранных провайдеров входа в проекте нет — и не должно появиться.

    Проверка не по списку установленных пакетов, а по настройкам и адресам:
    скрытая кнопка при установленном провайдере — это уже нарушение.
    """

    FORBIDDEN = ('allauth', 'social_django', 'social_core', 'oauth2_provider',
                 'django_auth_oidc')

    def test_no_provider_apps_installed(self):
        from django.conf import settings

        installed = ' '.join(settings.INSTALLED_APPS).lower()
        for name in self.FORBIDDEN:
            self.assertNotIn(name, installed)

    def test_no_provider_backends(self):
        from django.conf import settings

        backends = ' '.join(getattr(settings, 'AUTHENTICATION_BACKENDS',
                                    ['django.contrib.auth.backends.ModelBackend']))
        self.assertIn('ModelBackend', backends)
        for name in self.FORBIDDEN + ('google', 'apple', 'facebook', 'github'):
            self.assertNotIn(name, backends.lower())

    def test_no_provider_routes(self):
        for name in ('social:begin', 'account_login', 'oauth2_provider:authorize'):
            with self.subTest(name=name):
                with self.assertRaises(NoReverseMatch):
                    reverse(name)


class LoginRedirectsBackToNextTests(TestCase):
    """После входа человек должен попасть туда, откуда его послали
    логиниться, а не на дефолтный экран роли.

    Найдено вручную (сессия 02.09): анонимный переход по ссылке дуэли
    `/game/duel/new/?mode=blitz` уводит на `/login/?next=...`, но после
    успешного входа `RoleBasedLoginView.get_success_url()` игнорировал
    `next` целиком и вёл на `/student/`/`/teacher/`/`/admin/` — дуэль
    так и не создавалась, без единой ошибки на экране."""

    def setUp(self):
        self.student = User.objects.create_user(
            'realnyy_uchenik', password=GOOD_PASSWORD, role='student')

    def test_next_wins_over_role_default(self):
        target = '/game/duel/new/?mode=blitz'
        resp = self.client.post(
            '/login/?next=' + target,
            {'username': 'realnyy_uchenik', 'password': GOOD_PASSWORD})
        self.assertRedirects(resp, target, fetch_redirect_response=False)

    def test_missing_next_still_falls_back_to_role_default(self):
        """Без next — прежнее поведение: студента ведёт в кабинет."""
        resp = self.client.post(
            '/login/',
            {'username': 'realnyy_uchenik', 'password': GOOD_PASSWORD})
        self.assertRedirects(resp, '/student/', fetch_redirect_response=False)

    def test_unsafe_next_is_rejected_not_followed(self):
        """Открытый редирект на чужой домен — не через эту форму.

        `next` на чужой хост обязан быть отброшен (как и в штатном
        Django LoginView), а не использован буквально."""
        resp = self.client.post(
            '/login/?next=https://evil.example.com/phish',
            {'username': 'realnyy_uchenik', 'password': GOOD_PASSWORD})
        self.assertRedirects(resp, '/student/', fetch_redirect_response=False)
