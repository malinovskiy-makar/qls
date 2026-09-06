# -*- coding: utf-8 -*-
"""Обратная связь беты: приём, границы, экран.

⚠️ ГЛАВНОЕ ПРАВИЛО ЭТОГО ЭКРАНА — НЕ ПОТЕРЯТЬ СООБЩЕНИЕ. Отсюда почти все
проверки: гостю можно; битый снимок не отменяет запись; слишком большой
снимок не отменяет запись. Картинка — приятное дополнение, текст жалобы
ценнее.
"""
import io
import shutil
import tempfile

from django.core.cache import cache
from django.test import TestCase, override_settings
from PIL import Image

from problems.feedback_options import options_for, page_key_for
from problems.models import User
from problems.models_platform import Feedback

PASSWORD = 'feedback-probe-2026'


def jpeg_bytes(width=900, height=600):
    buffer = io.BytesIO()
    Image.new('RGB', (width, height), (40, 90, 140)).save(buffer, format='JPEG')
    return buffer.getvalue()


def shot(name='shot.jpg', blob=None):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, blob if blob is not None else jpeg_bytes(),
                              content_type='image/jpeg')


class MediaTempMixin:
    """Свой временный каталог под media — не «/tmp/...» строкой (bandit B108)."""

    @classmethod
    def setUpClass(cls):
        cls._media_dir = tempfile.mkdtemp(prefix='qls_fb_media_')
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_dir)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_dir, ignore_errors=True)


class PageKeyTests(TestCase):
    """Экран определяется по адресу, и порядок правил важен."""

    def test_longer_paths_win(self):
        """«/catalog/problem/» не должен схлопнуться в «/catalog/»."""
        self.assertEqual(page_key_for('/catalog/problem/123/'), 'problem')
        self.assertEqual(page_key_for('/catalog/map/'), 'map')
        self.assertEqual(page_key_for('/catalog/'), 'catalog')
        self.assertEqual(page_key_for('/profile/stats/'), 'stats')
        self.assertEqual(page_key_for('/profile/'), 'profile')

    def test_home_and_unknown(self):
        self.assertEqual(page_key_for('/'), 'home')
        self.assertEqual(page_key_for('/чего-то-нет/'), 'other')

    def test_every_key_has_options(self):
        """Экран без списка вариантов показал бы пустое окно."""
        from problems.feedback_options import ALL_PAGE_KEYS
        for key in ALL_PAGE_KEYS | {'home', 'other'}:
            self.assertTrue(options_for(key), key)


class AcceptTests(MediaTempMixin, TestCase):
    """Приём записи."""

    def setUp(self):
        cache.clear()

    def _post(self, **over):
        data = {'kind': 'problem', 'url': '/calc2/',
                'choices': ['График построен неправильно'],
                'viewport': '1440×900', 'theme': 'light'}
        data.update(over)
        return self.client.post('/api/feedback/', data)

    def test_guest_can_write(self):
        """⚠️ ГОСТЮ МОЖНО: у него как раз и ломается вход."""
        response = self._post()
        self.assertEqual(response.status_code, 200)
        entry = Feedback.objects.get()
        self.assertIsNone(entry.user)
        self.assertEqual(entry.page_key, 'calc2')

    def test_logged_in_user_is_remembered(self):
        user = User.objects.create_user(username='fb_user', password=PASSWORD,
                                        role='student')
        self.client.force_login(user)
        self._post()
        self.assertEqual(Feedback.objects.get().user, user)

    def test_page_key_comes_from_the_url_not_from_the_client(self):
        """Клиент не присылает `page_key` вовсе — иначе группировка развалится.

        ⚠️ Варианты здесь текстом, а не галочкой: галочка чужого экрана
        сервером отбрасывается (см. тест ниже), и запись бы не создалась.
        """
        self._post(url='/game/', page_key='подделка', choices=[],
                   other_text='Дуэль не соединилась')
        self.assertEqual(Feedback.objects.get().page_key, 'game')

    def test_unknown_choices_are_dropped(self):
        """В базу попадают только варианты ЭТОГО экрана."""
        self._post(choices=['График построен неправильно', 'выдуманное'])
        self.assertEqual(Feedback.objects.get().choices,
                         ['График построен неправильно'])

    def test_screenshot_is_recompressed(self):
        response = self.client.post('/api/feedback/', {
            'kind': 'problem', 'url': '/calc2/',
            'choices': ['Медленно или подвисает'], 'screenshot': shot()})
        self.assertEqual(response.status_code, 200)
        entry = Feedback.objects.get()
        self.assertTrue(entry.screenshot)
        image = Image.open(entry.screenshot.path)
        self.assertEqual(image.format, 'JPEG')
        self.assertLessEqual(image.width, 1600)

    def test_wide_screenshot_is_narrowed(self):
        response = self.client.post('/api/feedback/', {
            'kind': 'problem', 'url': '/calc2/',
            'choices': ['Медленно или подвисает'],
            'screenshot': shot(blob=jpeg_bytes(2400, 1000))})
        self.assertEqual(response.status_code, 200)
        image = Image.open(Feedback.objects.get().screenshot.path)
        self.assertEqual(image.width, 1600)

    def test_broken_screenshot_does_not_lose_the_message(self):
        """⚠️ ГЛАВНАЯ ПРОВЕРКА: картинка не важнее текста."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        response = self.client.post('/api/feedback/', {
            'kind': 'idea', 'url': '/', 'other_text': 'Хочу оглавление',
            'screenshot': SimpleUploadedFile('x.jpg', b'not an image',
                                             content_type='image/jpeg')})
        self.assertEqual(response.status_code, 200)
        entry = Feedback.objects.get()
        self.assertFalse(entry.screenshot)
        self.assertEqual(entry.other_text, 'Хочу оглавление')

    def test_huge_screenshot_does_not_lose_the_message(self):
        import os
        from django.core.files.uploadedfile import SimpleUploadedFile
        big = SimpleUploadedFile('big.jpg', os.urandom(3_000_000),
                                 content_type='image/jpeg')
        response = self.client.post('/api/feedback/', {
            'kind': 'idea', 'url': '/', 'other_text': 'Всё равно запишите',
            'screenshot': big})
        self.assertEqual(response.status_code, 200)
        entry = Feedback.objects.get()
        self.assertFalse(entry.screenshot)
        self.assertEqual(entry.other_text, 'Всё равно запишите')


class RefuseTests(TestCase):
    """Что не принимается."""

    def setUp(self):
        cache.clear()

    def test_problem_without_anything_is_400(self):
        response = self.client.post('/api/feedback/',
                                    {'kind': 'problem', 'url': '/calc2/'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_idea_without_text_is_400(self):
        response = self.client.post('/api/feedback/',
                                    {'kind': 'idea', 'url': '/'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_problem_with_only_free_text_is_accepted(self):
        """«Другое» без галочек — это тоже жалоба."""
        response = self.client.post('/api/feedback/', {
            'kind': 'problem', 'url': '/calc2/', 'other_text': 'Всё сломалось'})
        self.assertEqual(response.status_code, 200)

    def test_unknown_kind_is_400(self):
        response = self.client.post('/api/feedback/',
                                    {'kind': 'жалоба', 'url': '/'})
        self.assertEqual(response.status_code, 400)

    def test_get_is_405(self):
        self.assertEqual(self.client.get('/api/feedback/').status_code, 405)

    def test_eleventh_in_an_hour_is_throttled(self):
        for index in range(10):
            response = self.client.post('/api/feedback/', {
                'kind': 'idea', 'url': '/', 'other_text': 'мысль %d' % index})
            self.assertEqual(response.status_code, 200, index)
        response = self.client.post('/api/feedback/', {
            'kind': 'idea', 'url': '/', 'other_text': 'одиннадцатая'})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(Feedback.objects.count(), 10)


class ScreenshotAccessTests(MediaTempMixin, TestCase):
    """⚠️ ОТРИЦАТЕЛЬНЫЕ: снимок экрана видит только staff."""

    def setUp(self):
        cache.clear()
        self.client.post('/api/feedback/', {
            'kind': 'problem', 'url': '/calc2/',
            'choices': ['Медленно или подвисает'], 'screenshot': shot()})
        self.entry = Feedback.objects.get()
        self.url = '/admin/problems/feedback/%d/screenshot/' % self.entry.pk

    def test_staff_sees_it(self):
        staff = User.objects.create_user(username='fb_staff', password=PASSWORD,
                                         is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')

    def test_ordinary_user_is_refused(self):
        user = User.objects.create_user(username='fb_plain', password=PASSWORD,
                                        role='student')
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (302, 403))

    def test_guest_is_refused(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (302, 403))


class OnEveryScreenTests(TestCase):
    """Кнопка и кружок есть везде, где есть шапка, плюс вход и регистрация."""

    PAGES = ('/', '/catalog/', '/calc2/', '/game/', '/olympiads/',
             '/textbook/', '/login/', '/register/', '/calendar/')

    def test_button_and_telegram_circle_are_rendered(self):
        for url in self.PAGES:
            html = self.client.get(url).content.decode('utf-8')
            # Проверяем ПРЕФИКС класса: на экранах входа у кнопки есть
            # второй класс `fb-btn--onpage` (там светлый фон, не графит).
            self.assertIn('class="fb-btn', html, url)
            self.assertIn('class="tg-fab"', html, url)
            self.assertIn('t.me/weconomics_ru', html, url)

    def test_csrf_token_is_present_everywhere(self):
        """⚠️ БЕЗ ЭТОГО ОТПРАВКА МОЛЧА ПАДАЕТ С 403.

        Django ставит куку `csrftoken`, только если кто-то на странице
        попросил токен. На страницах без единой формы (лендинг, «Учебник»,
        олимпиады) просить было некому — найдено пробой на `/textbook/`.

        ⚠️ ПРОВЕРЯЕМ ИМЕННО ОТРИСОВАННОЕ ПОЛЕ (`name="csrfmiddlewaretoken"`
        с кавычками), а НЕ подстроку `csrfmiddlewaretoken`. Первая версия
        этого теста ловила слово внутри СВОЕГО ЖЕ селектора в скрипте
        (`input[name=csrfmiddlewaretoken]`) и проходила даже с удалённой
        формой — то есть не проверяла ничего.
        """
        for url in self.PAGES:
            html = self.client.get(url).content.decode('utf-8')
            self.assertIn('name="csrfmiddlewaretoken"', html, url)

    def test_options_are_served_by_the_server(self):
        r"""Список вариантов приходит с сервера, клиент его не дублирует.

        ⚠️ РАЗБИРАЕМ JSON, А НЕ ИЩЕМ ПОДСТРОКУ. `json_script` экранирует
        кириллицу в `\uXXXX`, и поиск строки «График построен неправильно»
        по разметке не нашёл бы ничего, хотя данные на месте.
        """
        import json as _json

        html = self.client.get('/calc2/').content.decode('utf-8')
        self.assertIn('id="fb-options"', html)
        block = html.split('id="fb-options"', 1)[1]
        payload = block.split('>', 1)[1].split('</script>', 1)[0]
        data = _json.loads(payload)
        self.assertEqual(data['page'], 'calc2')
        self.assertIn('График построен неправильно', data['options']['calc2'])

    def test_json_is_escaped_not_marked_safe(self):
        """`json_script` экранирует `<`, `>` и `&` — `mark_safe` не нужен.

        Проверка не на вкус: `mark_safe` над строкой, собранной в питоне, —
        это находка bandit (B703/B308), то есть красный джоб «Безопасность».

        ⚠️ Ищем ВЫЗОВ и ИМПОРТ, а не слово: слово стоит в объяснении рядом,
        и проверка на подстроку краснела бы на собственном комментарии.
        """
        import io
        src = io.open('config/context_processors.py', encoding='utf-8').read()
        self.assertNotIn('mark_safe(', src)
        self.assertNotIn('import mark_safe', src)

    def test_hidden_from_print(self):
        html = self.client.get('/catalog/').content.decode('utf-8')
        self.assertIn('@media print', html)
        block = html.split('@media print', 1)[1][:200]
        self.assertIn('.fb-btn', block)
        self.assertIn('.tg-fab', block)
