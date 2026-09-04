# -*- coding: utf-8 -*-
"""Аккаунт целиком: регистрация, профиль, логин, пароль, аватар.

⚠️ ГЛАВНЫЙ ТЕСТ ЗДЕСЬ — СКВОЗНОЙ (`FullJourneyTests`): он проходит путь так,
как его пройдёт человек, а не проверяет вьюхи поштучно. Именно в стыках
ломается: сменил логин — не смог войти; сменил пароль — вылетел сам; загрузил
аватар — он не показался в шапке.

Границы доступа проверяются ОТРИЦАТЕЛЬНЫМИ тестами: «свой прошёл» без
парного «чужой не прошёл» границей не считается.
"""
import io
import shutil
import tempfile

from django.core.cache import cache
from django.test import TestCase, override_settings
from PIL import Image

from problems.models import User
from problems.models_platform import UserProfile

GOOD_PASSWORD = 'orehovyi-kompot-71'
NEW_PASSWORD = 'drugoi-parol-2026-x'


def png_bytes(width=1200, height=800, colour=(200, 60, 60)):
    """Настоящий PNG в память — не подделка байтами."""
    buffer = io.BytesIO()
    Image.new('RGB', (width, height), colour).save(buffer, format='PNG')
    buffer.seek(0)
    return buffer.read()


def upload(name='ava.png', **kwargs):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, png_bytes(**kwargs), content_type='image/png')


class MediaTempMixin:
    """Свой временный каталог под `MEDIA_ROOT` на время класса тестов.

    ⚠️ НЕ `/tmp/что-то` СТРОКОЙ. Жёсткий путь во временном каталоге —
    находка bandit B108 (её видит джоб «Безопасность» в CI) и настоящая
    неаккуратность: на общей машине такой путь предсказуем, а на Windows
    его вовсе нет. `mkdtemp` даёт свой каталог и убирается за собой.
    """

    @classmethod
    def setUpClass(cls):
        cls._media_dir = tempfile.mkdtemp(prefix='qls_test_media_')
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_dir)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_dir, ignore_errors=True)


class RegistrationTests(TestCase):
    """Регистрация: логин, пароль, роль, согласие."""

    def setUp(self):
        cache.clear()   # счётчик частоты живёт в кэше

    def _post(self, **over):
        data = {
            'username': 'novichok',
            'password1': GOOD_PASSWORD,
            'password2': GOOD_PASSWORD,
            'role': 'student',
            'consent': 'on',
        }
        data.update(over)
        return self.client.post('/register/', data)

    def test_student_registers_and_is_logged_in(self):
        response = self._post()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/profile/?welcome=1')
        user = User.objects.get(username='novichok')
        self.assertEqual(user.role, 'student')
        self.assertEqual(user.profile.role, UserProfile.Role.STUDENT)
        # Вошёл сразу: второй раз вводить пароль незачем.
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_tutor_registration_sets_both_roles(self):
        """Роль профиля `tutor` обязана подтянуть `User.role = teacher`."""
        self._post(username='prepod', role='tutor')
        user = User.objects.get(username='prepod')
        self.assertEqual(user.profile.role, UserProfile.Role.TUTOR)
        self.assertEqual(user.role, 'teacher')

    def test_taken_login_is_named_honestly(self):
        """На регистрации молчать нельзя — иначе непонятно, что не так.

        (На ВХОДЕ, наоборот, причина не называется: там это подсказка
        подбирающему. Разница осознанная.)
        """
        User.objects.create_user(username='zanyat', password=GOOD_PASSWORD)
        response = self._post(username='zanyat')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'занят')
        self.assertEqual(User.objects.filter(username='zanyat').count(), 1)

    def test_taken_login_is_case_insensitive(self):
        User.objects.create_user(username='Zanyat', password=GOOD_PASSWORD)
        response = self._post(username='zanyat')
        self.assertContains(response, 'занят')

    def test_short_password_is_refused(self):
        response = self._post(password1='abc12', password2='abc12')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='novichok').exists())

    def test_common_password_is_refused(self):
        response = self._post(password1='password123', password2='password123')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='novichok').exists())

    def test_passwords_must_match(self):
        response = self._post(password2=NEW_PASSWORD)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='novichok').exists())

    def test_consent_is_required(self):
        data = {'username': 'novichok', 'password1': GOOD_PASSWORD,
                'password2': GOOD_PASSWORD, 'role': 'student'}
        response = self.client.post('/register/', data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='novichok').exists())

    def test_logged_in_user_is_sent_to_profile(self):
        user = User.objects.create_user(username='uzhe', password=GOOD_PASSWORD,
                                        role='student')
        self.client.force_login(user)
        response = self.client.get('/register/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/profile/', response['Location'])

    def test_sixth_registration_from_one_address_is_throttled(self):
        """Пять удачных регистраций подряд — дальше задержка.

        ⚠️ Считаются именно УДАЧНЫЕ: у входа опасен промах (подбор), здесь —
        успех (штамповка аккаунтов).
        """
        for index in range(5):
            response = self._post(username='bot%d' % index)
            self.assertEqual(response.status_code, 302, 'попытка %d' % index)
            # ⚠️ ВЫХОД ОБЯЗАТЕЛЕН. После регистрации человек уже вошёл, а
            # вошедшего `/register/` уводит в профиль — без выхода тест
            # мерил бы редиректы, а не регистрации, и счётчик не рос бы.
            self.client.post('/logout/')
        response = self._post(username='bot5')
        self.assertEqual(response.status_code, 429)
        self.assertFalse(User.objects.filter(username='bot5').exists())

    def test_no_open_redirect_after_registration(self):
        """`next` при регистрации не принимается вовсе."""
        response = self.client.post('/register/', {
            'username': 'novichok', 'password1': GOOD_PASSWORD,
            'password2': GOOD_PASSWORD, 'role': 'student', 'consent': 'on',
            'next': 'https://example.org/evil',
        })
        self.assertEqual(response['Location'], '/profile/?welcome=1')


class PasswordChangeTests(TestCase):
    """Смена пароля — только новый, дважды (ADR 0073)."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='menyayu',
                                             password=GOOD_PASSWORD,
                                             role='student')
        self.client.force_login(self.user)

    def test_change_without_old_password(self):
        response = self.client.post('/profile/', {
            'action': 'password',
            'new_password1': NEW_PASSWORD,
            'new_password2': NEW_PASSWORD,
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_session_survives_the_change(self):
        """Меняющий пароль не должен вылететь сам."""
        self.client.post('/profile/', {
            'action': 'password', 'new_password1': NEW_PASSWORD,
            'new_password2': NEW_PASSWORD})
        self.assertEqual(self.client.get('/profile/').status_code, 200)

    def test_weak_new_password_is_refused(self):
        response = self.client.post('/profile/', {
            'action': 'password', 'new_password1': 'abc',
            'new_password2': 'abc'})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(GOOD_PASSWORD))

    def test_old_password_field_is_simply_ignored(self):
        """Старая проверка слала `old_password` — форма его не заметит.

        Это важно для `test_auth_hardening`: тот тест шлёт старое поле и
        обязан остаться зелёным.
        """
        response = self.client.post('/profile/', {
            'action': 'password', 'old_password': GOOD_PASSWORD,
            'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})
        self.assertEqual(response.status_code, 302)

    def test_old_address_still_answers(self):
        """`/password/change/` жив редиректом — ради закладок."""
        response = self.client.get('/password/change/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/profile/', response['Location'])


class AvatarTests(MediaTempMixin, TestCase):
    """Аватар: обработка, отдача и границы доступа."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='sfoto',
                                             password=GOOD_PASSWORD,
                                             role='student')
        # Профиль заводит сигнал при создании пользователя — берём готовый.
        self.profile = UserProfile.objects.get(user=self.user)
        self.other = User.objects.create_user(username='drugoi',
                                              password=GOOD_PASSWORD,
                                              role='student')

    def _upload(self, **kwargs):
        self.client.force_login(self.user)
        return self.client.post('/profile/', {'action': 'avatar',
                                              'avatar': upload(**kwargs)})

    def test_upload_is_recompressed_to_square_jpeg(self):
        """Из PNG 1200×800 получается НАШ JPEG 256×256 под нашим именем."""
        self._upload()
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.avatar)
        self.assertTrue(self.profile.avatar.name.endswith('.jpg'),
                        self.profile.avatar.name)
        image = Image.open(self.profile.avatar.path)
        self.assertEqual(image.size, (256, 256))
        self.assertEqual(image.format, 'JPEG')

    def test_uploaded_name_is_not_used(self):
        """Имя из запроса не участвует нигде — иначе это обход каталога."""
        self._upload(name='../../evil.png')
        self.profile.refresh_from_db()
        self.assertNotIn('evil', self.profile.avatar.name)
        self.assertNotIn('..', self.profile.avatar.name)

    def test_owner_sees_own_avatar(self):
        self._upload()
        response = self.client.get('/profile/avatar/%d/' % self.user.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertIn('private', response['Cache-Control'])

    def test_another_logged_in_user_sees_it_too(self):
        """Осознанно: аватар показывается в шапке, в группе, на доске."""
        self._upload()
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get('/profile/avatar/%d/' % self.user.pk).status_code,
            200)

    def test_guest_is_refused(self):
        """⚠️ ОТРИЦАТЕЛЬНЫЙ ТЕСТ ГРАНИЦЫ: лицо ребёнка гостю не отдаём."""
        self._upload()
        self.client.logout()
        response = self.client.get('/profile/avatar/%d/' % self.user.pk)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_missing_avatar_is_404_not_500(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get('/profile/avatar/%d/' % self.other.pk).status_code,
            404)

    def test_unknown_user_is_404(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get('/profile/avatar/999999/').status_code, 404)

    def test_not_an_image_is_refused(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.user)
        fake = SimpleUploadedFile('a.png', b'not an image at all',
                                  content_type='image/png')
        response = self.client.post('/profile/',
                                    {'action': 'avatar', 'avatar': fake})
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.avatar)

    def test_too_big_file_is_refused(self):
        """Больше 3 МБ — отказ.

        ⚠️ КАРТИНКА НАСТОЯЩАЯ, И ЭТО ВАЖНО. Первая версия теста слала 5 МБ
        случайного шума — но такой файл отвергает сам `forms.ImageField`
        («это не картинка»), то есть НАША проверка размера не проверялась
        вовсе. Здесь честный PNG из случайных пикселей: он не сжимается и
        весит несколько мегабайт, оставаясь картинкой.
        """
        import os
        from django.core.files.uploadedfile import SimpleUploadedFile
        buffer = io.BytesIO()
        noisy = Image.frombytes('RGB', (1400, 1400),
                                os.urandom(1400 * 1400 * 3))
        noisy.save(buffer, format='PNG')
        blob = buffer.getvalue()
        self.assertGreater(len(blob), 3 * 1024 * 1024,
                           'картинка вышла меньше предела — тест ничего не мерит')
        self.client.force_login(self.user)
        response = self.client.post('/profile/', {
            'action': 'avatar',
            'avatar': SimpleUploadedFile('big.png', blob,
                                         content_type='image/png')})
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.avatar)

    def test_huge_dimensions_are_refused(self):
        """Пиксельная бомба: маленький файл, огромный размер в памяти."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        buffer = io.BytesIO()
        # Одноцветный PNG 5000×5000 весит десятки килобайт, а в памяти
        # Pillow развернёт его в 75 МБ.
        Image.new('RGB', (5000, 5000), (10, 10, 10)).save(buffer, format='PNG')
        blob = buffer.getvalue()
        self.assertLess(len(blob), 3 * 1024 * 1024, 'файл должен быть мелким')
        self.client.force_login(self.user)
        response = self.client.post('/profile/', {
            'action': 'avatar',
            'avatar': SimpleUploadedFile('bomb.png', blob,
                                         content_type='image/png')})
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.avatar)

    def test_remove_clears_the_field(self):
        self._upload()
        self.client.post('/profile/', {'action': 'avatar_remove'})
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.avatar)

    def test_header_shows_the_avatar(self):
        self._upload()
        html = self.client.get('/catalog/').content.decode('utf-8')
        self.assertIn('/profile/avatar/%d/' % self.user.pk, html)


class ProfileFormTests(TestCase):
    """Данные профиля: логин, уровень, класс."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='dannye',
                                             password=GOOD_PASSWORD,
                                             role='student')
        # Профиль заводит сигнал при создании пользователя — берём готовый.
        self.profile = UserProfile.objects.get(user=self.user)
        self.client.force_login(self.user)

    def _save(self, **over):
        data = {'action': 'data', 'username': 'dannye', 'first_name': 'Иван',
                'last_name': 'Петров', 'email': '', 'grade': '10',
                'school': 'Лицей 1', 'level': 'region'}
        data.update(over)
        return self.client.post('/profile/', data)

    def test_saves_name_grade_and_level(self):
        response = self._save()
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Иван')
        self.assertEqual(self.profile.grade, 10)
        self.assertEqual(self.profile.level, 'region')

    def test_username_can_change(self):
        self._save(username='novoye_imya')
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'novoye_imya')

    def test_username_stays_unique(self):
        User.objects.create_user(username='chuzhoi', password=GOOD_PASSWORD)
        response = self._save(username='chuzhoi')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'dannye')

    def test_role_cannot_be_changed_through_the_form(self):
        """⚠️ ГРАНИЦА: роль меняет права, её из формы не берём вовсе."""
        self._save(role='tutor')
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.role, UserProfile.Role.STUDENT)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, 'student')

    def test_guest_cannot_open_profile(self):
        self.client.logout()
        response = self.client.get('/profile/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_all_four_tabs_open(self):
        for tab in ('data', 'security', 'saved'):
            self.assertEqual(
                self.client.get('/profile/?tab=%s' % tab).status_code, 200, tab)
        self.assertEqual(self.client.get('/profile/stats/').status_code, 200)


class FullJourneyTests(MediaTempMixin, TestCase):
    """Путь целиком — так, как его пройдёт живой человек.

    Регистрация → профиль → заполнил → сменил логин → вышел → вошёл новым
    логином → сменил пароль → вышел → вошёл новым паролем → загрузил аватар.
    Ломается обычно НЕ внутри шага, а на стыке двух.
    """

    def setUp(self):
        cache.clear()

    def test_the_whole_way(self):
        # 1. Регистрация
        response = self.client.post('/register/', {
            'username': 'put', 'password1': GOOD_PASSWORD,
            'password2': GOOD_PASSWORD, 'role': 'student', 'consent': 'on'})
        self.assertEqual(response['Location'], '/profile/?welcome=1')

        # 2. В шапке появилась плашка профиля
        html = self.client.get('/catalog/').content.decode('utf-8')
        self.assertIn('class="nav-user"', html)

        # 3. Заполнил данные и сменил логин
        self.client.post('/profile/', {
            'action': 'data', 'username': 'put2', 'first_name': 'Пётр',
            'last_name': 'Сидоров', 'email': '', 'grade': '11',
            'school': 'Школа 5', 'level': 'basic'})
        user = User.objects.get(pk=User.objects.get(username='put2').pk)
        self.assertEqual(user.first_name, 'Пётр')

        # 4. Вышел и вошёл НОВЫМ логином
        self.client.post('/logout/')
        self.assertTrue(self.client.login(username='put2',
                                          password=GOOD_PASSWORD))

        # 5. Сменил пароль — и остался внутри
        self.client.post('/profile/', {
            'action': 'password', 'new_password1': NEW_PASSWORD,
            'new_password2': NEW_PASSWORD})
        self.assertEqual(self.client.get('/profile/').status_code, 200)

        # 6. Вышел и вошёл НОВЫМ паролем; старый больше не подходит
        self.client.post('/logout/')
        self.assertFalse(self.client.login(username='put2',
                                           password=GOOD_PASSWORD))
        self.assertTrue(self.client.login(username='put2',
                                          password=NEW_PASSWORD))

        # 7. Загрузил аватар — он виден в шапке
        self.client.post('/profile/', {'action': 'avatar',
                                       'avatar': upload()})
        html = self.client.get('/catalog/').content.decode('utf-8')
        self.assertIn('/profile/avatar/%d/' % user.pk, html)
        self.assertEqual(
            self.client.get('/profile/avatar/%d/' % user.pk).status_code, 200)
