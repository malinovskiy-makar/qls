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

from problems.feedback_options import OTHER_CHOICE, options_for, page_key_for
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

    def test_home_and_textbook_have_their_own_lists(self):
        """С 15.09.2026 у главной и учебника свои варианты, а не общий список."""
        from problems.feedback_options import FEEDBACK_OPTIONS
        self.assertNotEqual(options_for('home'), FEEDBACK_OPTIONS['other'])
        self.assertNotEqual(options_for('textbook'), FEEDBACK_OPTIONS['other'])
        self.assertIn('Непонятно, с чего начать', options_for('home'))
        self.assertIn('Не открывается нужная глава', options_for('textbook'))

    def test_problem_screen_stays_a_catalog_alias(self):
        """Жалобы на саму задачу — в «Плохая задача»; здесь — про экран."""
        self.assertEqual(options_for('problem'), options_for('catalog'))

    def test_catalog_and_game_lists_are_the_owners_wording(self):
        """Формулировки владельца 15.09.2026, словами школьника и по порядку."""
        self.assertEqual(options_for('catalog'), [
            'Поиск не находит нужное',
            'Поиск слишком долгий',
            'Фильтры работают не так',
            'Тест не даёт выбрать вариант',
            'Формулы или картинки отображаются неправильно',
            'Задача открывается долго или не открывается',
        ])
        self.assertEqual(options_for('game'), [
            'Игра зависла, кнопки не нажимаются',
            'Вопрос с ошибкой или без верного ответа',
            'Таймер, очки или жизни считаются странно',
            'Дуэль не соединилась или не стартовала',
            'Звук или анимация мешают',
            'Не понял правила',
        ])


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

        ⚠️ Вариант здесь «Другое» с текстом: галочка чужого экрана сервером
        отбрасывается (см. тест ниже), а «Другое» есть на любом экране.
        """
        self._post(url='/game/', page_key='подделка', choices=[OTHER_CHOICE],
                   other_text='Дуэль не соединилась')
        self.assertEqual(Feedback.objects.get().page_key, 'game')

    def test_unknown_choices_are_dropped(self):
        """В базу попадают только варианты ЭТОГО экрана."""
        self._post(choices=['График построен неправильно', 'выдуманное'])
        self.assertEqual(Feedback.objects.get().choices,
                         ['График построен неправильно'])

    def test_screenshot_note_is_saved_and_trimmed(self):
        """Что стало со снимком — сохраняется; мусор режется до 16 знаков."""
        self._post(screenshot_note='timeout')
        self.assertEqual(Feedback.objects.get().screenshot_note, 'timeout')
        Feedback.objects.all().delete()
        self._post(screenshot_note='x' * 50)
        self.assertEqual(Feedback.objects.get().screenshot_note, 'x' * 16)

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
        big = SimpleUploadedFile('big.jpg', os.urandom(6_000_000),
                                 content_type='image/jpeg')
        response = self.client.post('/api/feedback/', {
            'kind': 'idea', 'url': '/', 'other_text': 'Всё равно запишите',
            'screenshot': big})
        self.assertEqual(response.status_code, 200)
        entry = Feedback.objects.get()
        self.assertFalse(entry.screenshot)
        self.assertEqual(entry.other_text, 'Всё равно запишите')


class ServerShotNoteTests(MediaTempMixin, TestCase):
    """18.09.2026: сервер уменьшает высокий снимок и сам пишет, почему не принял.

    Раньше всё выше 4 000 px и тяжелее 2,5 МБ молча пропадало, а в
    `screenshot_note` оставалось клиентское «ok» — пустой снимок в админке
    выглядел как «браузер снял, а у нас ничего».
    """

    def setUp(self):
        cache.clear()

    def _post(self, blob, note='ok'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post('/api/feedback/', {
            'kind': 'idea', 'url': '/catalog/', 'other_text': 'Снимок длинной страницы',
            'screenshot_note': note,
            'screenshot': SimpleUploadedFile('shot.jpg', blob, content_type='image/jpeg')})

    def test_tall_screenshot_is_downscaled_not_dropped(self):
        self.assertEqual(self._post(jpeg_bytes(1600, 5000)).status_code, 200)
        entry = Feedback.objects.get()
        self.assertTrue(entry.screenshot)
        self.assertLessEqual(Image.open(entry.screenshot.path).height, 4000)

    def test_downscaled_screenshot_keeps_the_client_note(self):
        self._post(jpeg_bytes(1600, 5000), note='ok')
        self.assertEqual(Feedback.objects.get().screenshot_note, 'ok')

    def test_absurdly_tall_screenshot_is_refused_as_tall(self):
        self._post(jpeg_bytes(1600, 13000))
        entry = Feedback.objects.get()
        self.assertFalse(entry.screenshot)
        self.assertEqual(entry.screenshot_note, 'tall')

    def test_four_megabyte_screenshot_is_accepted(self):
        import os
        side = 1150
        noise = Image.frombytes('RGB', (side, side), os.urandom(side * side * 3))
        buffer = io.BytesIO()
        noise.save(buffer, format='PNG')
        blob = buffer.getvalue()
        self.assertTrue(3_500_000 < len(blob) < 5_000_000, len(blob))
        self._post(blob)
        self.assertTrue(Feedback.objects.get().screenshot)

    def test_six_megabyte_file_is_refused_as_big(self):
        import os
        self._post(os.urandom(6_000_000))
        entry = Feedback.objects.get()
        self.assertFalse(entry.screenshot)
        self.assertEqual(entry.screenshot_note, 'big')

    def test_not_an_image_is_refused_as_bad(self):
        self._post(b'not an image')
        entry = Feedback.objects.get()
        self.assertFalse(entry.screenshot)
        self.assertEqual(entry.screenshot_note, 'bad')
        self.assertEqual(entry.other_text, 'Снимок длинной страницы')


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

    def test_one_checkbox_without_text_is_accepted(self):
        """Правило 17.09.2026: одной галочки достаточно, текст не обязателен."""
        response = self.client.post('/api/feedback/', {
            'kind': 'problem', 'url': '/calc2/', 'choices': ['Медленно или подвисает']})
        self.assertEqual(response.status_code, 200)

    def test_other_with_text_is_accepted(self):
        response = self.client.post('/api/feedback/', {
            'kind': 'problem', 'url': '/calc2/', 'choices': [OTHER_CHOICE],
            'other_text': 'Всё сломалось'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Feedback.objects.get().choices, [OTHER_CHOICE])

    def test_other_without_text_is_400(self):
        response = self.client.post('/api/feedback/', {
            'kind': 'problem', 'url': '/calc2/', 'choices': [OTHER_CHOICE]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_text_without_any_checkbox_is_400(self):
        """Хотя бы одна галочка: текст без «Другое» — не жалоба по правилу окна."""
        response = self.client.post('/api/feedback/', {
            'kind': 'problem', 'url': '/calc2/', 'other_text': 'Всё сломалось'})
        self.assertEqual(response.status_code, 400)

    def test_problem_page_checkbox_is_accepted(self):
        """Страница задачи — синоним каталога. Окно показывало общий список,
        сервер ждал список каталога и выбрасывал галочку (до 17.09.2026)."""
        from problems.tests.factories import make_problem
        problem = make_problem('Условие для окна обратной связи.')
        html = self.client.get('/catalog/problem/%d/' % problem.pk).content.decode('utf-8')
        payload = html.split('id="fb-options"', 1)[1].split('>', 1)[1].split('</script>', 1)[0]
        import json as _json
        data = _json.loads(payload)
        shown = data['options'][data['page']]
        response = self.client.post('/api/feedback/', {
            'kind': 'problem', 'url': '/catalog/problem/%d/' % problem.pk, 'choices': [shown[0]]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Feedback.objects.get().choices, [shown[0]])

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

    def test_open_link_on_the_change_page_leads_to_the_image(self):
        """Ссылка «открыть» была ОТНОСИТЕЛЬНОЙ: со страницы записи она вела на
        …/<pk>/change/screenshot/, этот адрес ловил общий шаблон админки, и
        Django отвечал «…не существует. Возможно, он был удалён?» (17.09.2026).
        Переходим ровно так, как браузер: href со страницы + адрес страницы."""
        import re
        from urllib.parse import urljoin
        staff = User.objects.create_user(username='fb_staff3', password=PASSWORD,
                                         is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        change = '/admin/problems/feedback/%d/change/' % self.entry.pk
        html = self.client.get(change).content.decode('utf-8')
        href = re.search(r'<a href="([^"]+)"[^>]*>открыть</a>', html).group(1)
        response = self.client.get(urljoin(change, href))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('image/'), response['Content-Type'])

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

    def test_other_is_the_last_checkbox_and_its_field_starts_hidden(self):
        """Окно строится скриптом: проверяем данные и ветку скрытия поля."""
        import json as _json
        html = self.client.get('/calc2/').content.decode('utf-8')
        payload = html.split('id="fb-options"', 1)[1].split('>', 1)[1].split('</script>', 1)[0]
        self.assertEqual(_json.loads(payload)['other'], OTHER_CHOICE)
        self.assertTrue('.concat([OTHER])' in html, 'пункт «Другое» не добавляется последним')
        self.assertTrue('field.hidden = true;' in html, 'поле текста не скрыто по умолчанию')
        self.assertTrue('field.hidden = !otherBox.checked;' in html, 'поле не открывается по галочке')

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

    def test_telegram_circle_is_a_third_bigger_in_the_same_corner(self):
        """17.09.2026: 40 → 53 px, значок 19 → 25 px; угол прежний."""
        src = io.open('templates/_feedback.html', encoding='utf-8').read()
        rule = src.split('.tg-fab {', 1)[1].split('}', 1)[0]
        self.assertTrue('width: 53px; height: 53px;' in rule, rule)
        self.assertTrue('right: 16px; bottom: 16px;' in rule, rule)
        self.assertTrue('.tg-fab svg { width: 25px; height: 25px; }' in src, 'значок не увеличен')

    def test_hidden_from_print(self):
        html = self.client.get('/catalog/').content.decode('utf-8')
        self.assertIn('@media print', html)
        block = html.split('@media print', 1)[1][:200]
        self.assertIn('.fb-btn', block)
        self.assertIn('.tg-fab', block)


class ScreenshotNoteScriptTests(TestCase):
    """Скрипт окна шлёт причину пустого снимка и ждёт снимок до 6 секунд."""

    def test_script_sends_the_note_and_waits_six_seconds(self):
        src = io.open('templates/_feedback.html', encoding='utf-8').read()
        self.assertTrue("data.append('screenshot_note', shot.note)" in src)
        self.assertTrue("finish(null, 'timeout'); }, 6000)" in src)
        for note in ("'ok'", "'timeout'", "'error'", "'nolib'"):
            self.assertTrue(note in src, note)

    def test_script_shoots_the_visible_frame_not_the_whole_document(self):
        """18.09.2026: кадр собирает shotOptions() — видимая область по прокрутке.

        Весь документ длинного каталога — полотно в тысячи пикселей; проба
        кадра — scripts/feedback_shot_probe.mjs.
        """
        src = io.open('templates/_feedback.html', encoding='utf-8').read()
        self.assertTrue('function shotOptions()' in src)
        self.assertTrue('html2canvas(document.documentElement, shotOptions())' in src)
        self.assertTrue('x: window.scrollX, y: window.scrollY' in src)
        self.assertTrue('width: root.clientWidth, height: root.clientHeight' in src)

    def test_modern_colors_are_flattened_before_the_shot(self):
        """html2canvas 1.4.1 падает на `color(srgb …)` — так Chrome отдаёт
        color-mix() каталога, задачи и игры. Без onclone снимок был только
        у главной страницы."""
        src = io.open('templates/_feedback.html', encoding='utf-8').read()
        self.assertTrue('onclone: flattenModernColors' in src)


class PulseTests(TestCase):
    """18.09.2026: «Всё ли нравится?» — третий вид обратной связи."""

    def setUp(self):
        cache.clear()

    def _post(self, **over):
        data = {'kind': 'pulse', 'url': '/catalog/', 'choices': ['like']}
        data.update(over)
        return self.client.post('/api/feedback/', data)

    def test_like_is_saved_as_pulse(self):
        self.assertEqual(self._post(comment='Удобный поиск').status_code, 200)
        entry = Feedback.objects.get()
        self.assertEqual((entry.kind, entry.choices, entry.comment),
                         ('pulse', ['like'], 'Удобный поиск'))

    def test_dislike_is_saved(self):
        self._post(choices=['dislike'])
        self.assertEqual(Feedback.objects.get().choices, ['dislike'])

    def test_unknown_choice_is_refused(self):
        self.assertEqual(self._post(choices=['meh']).status_code, 400)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_both_choices_at_once_are_refused(self):
        self.assertEqual(self._post(choices=['like', 'dislike']).status_code, 400)

    def test_comment_over_three_hundred_is_refused(self):
        self.assertEqual(self._post(comment='я' * 301).status_code, 400)

    def test_other_text_is_ignored(self):
        self._post(other_text='лишнее')
        self.assertEqual(Feedback.objects.get().other_text, '')

    def test_problem_without_choices_is_still_refused(self):
        response = self.client.post('/api/feedback/', {'kind': 'problem', 'url': '/'})
        self.assertEqual(response.status_code, 400)


class PulseCardTests(TestCase):
    """Плашка есть на рабочих экранах и отсутствует на входе и регистрации."""

    def test_card_is_on_catalog_and_home(self):
        for url in ('/catalog/', '/'):
            html = self.client.get(url).content.decode('utf-8')
            self.assertIn('id="pulse-card-tpl"', html, url)

    def test_card_is_not_on_login_and_register(self):
        for url in ('/login/', '/register/'):
            html = self.client.get(url).content.decode('utf-8')
            self.assertNotIn('id="pulse-card-tpl"', html, url)

    def test_show_rules_live_in_one_function(self):
        src = io.open('templates/_pulse.html', encoding='utf-8').read()
        for rule in ('var MIN_VISITS = 2;', 'var MAX_SHOWS = 2;',
                     'var GAP_MS = 7 * 24 * 3600 * 1000;', 'var AFTER_MS = 60 * 1000;',
                     'var AUTO_SEND_MS = 20 * 1000;'):
            self.assertIn(rule, src)
        self.assertIn("weco.track('pulse_dismiss'", src)
