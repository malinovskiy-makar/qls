# -*- coding: utf-8 -*-
"""Вкладка «Аккаунт» профиля `/profile/?tab=data` (ТЗ владельца 22.09.2026).

⚠️ Числа здесь — инварианты, а не «сколько получилось»: шесть списков у нового
ученика, одиннадцать олимпиад, ни одного поля телефона. Тексты вариантов берутся
из модели — если подписи разойдутся с ТЗ, тест это назовёт.
"""
import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from problems.forms_accounts import ProfileForm
from problems.models_platform import UserProfile

User = get_user_model()

FULL = {
    'grade': '10', 'school': 'Школа № 1535', 'city': 'Москва', 'level': 'region',
    'prep_mode': ['self', 'club'], 'hours_week': '3_6', 'source_channel': 'telegram',
    'olympiad_history': ['vsosh_school', 'hse'], 'goal': 'Призёр Высшей пробы',
    'telegram': 'masha_orl',
}


def _person(username, role='student', **profile):
    user = User.objects.create_user(username, password='p12345', role=role)
    fields = dict({'role': role}, **profile)
    UserProfile.objects.update_or_create(user=user, defaults=fields)
    return user


def _client(user):
    client = Client()
    client.force_login(user)
    return client


def _png(width, height, left_colour, right_colour):
    """Картинка из двух половин: по цвету центра видно, что именно вырезали."""
    image = Image.new('RGB', (width, height), right_colour)
    image.paste(Image.new('RGB', (width // 2, height), left_colour), (0, 0))
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    return buffer.getvalue()


class PageTests(TestCase):
    """Что есть и чего нет на странице ученика."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _person('acc_full', **FULL)

    def page(self):
        response = _client(self.user).get('/profile/?tab=data')
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_01_the_tab_is_called_account_and_the_title_stays_profile(self):
        html = self.page()
        self.assertIn('>Аккаунт</a>', html)
        self.assertIn('<h1 class="page-title">Профиль</h1>', html)
        # ⚠️ Ищем РАЗМЕТКУ: имя класса есть ещё и в стилях страницы.
        self.assertNotIn('<div class="page-sub">', html)

    def test_02_removed_things_are_really_gone(self):
        html = self.page()
        for absent in ('Загрузить<', 'Обрежем по центру', 'Им вы входите',
                       'Помогает нам понять', 'name="phone"'):
            self.assertNotIn(absent, html, absent)

    def test_03_new_fields_and_labels_are_in_place(self):
        html = self.page()
        self.assertIn('name="telegram"', html)
        self.assertIn('placeholder="@username"', html)
        for label in ('Имя пользователя', 'Способ подготовки',
                      'Откуда вы узнали о Weconomics', 'Цель на ближайший учебный год'):
            self.assertIn(label, html, label)

    def test_04_goal_is_the_last_field_before_save(self):
        """Цель идёт ПОСЛЕ «откуда узнали»: порядок полей задан ТЗ."""
        html = self.page()
        self.assertGreater(html.index('Цель на ближайший учебный год'),
                           html.index('Откуда вы узнали о Weconomics'))

    def test_05_the_aside_cards_come_before_the_form_in_the_markup(self):
        """Порядок разметки решает, где карточки окажутся на телефоне."""
        html = self.page()
        self.assertLess(html.index('<aside class="pf-aside"'),
                        html.index('<div class="card pf-card pf-card--form">'))

    def test_06_both_cards_link_out_safely(self):
        html = self.page()
        aside = html.split('class="pf-aside"', 1)[1].split('</aside>', 1)[0]
        self.assertIn('https://t.me/weconomics_ru"', aside)
        self.assertNotIn('?direct', aside)
        self.assertIn('docs.google.com/forms/', aside)
        self.assertEqual(aside.count('target="_blank" rel="noopener"'), 2)

    def test_07_email_hint_is_a_tooltip_and_not_a_line_under_the_field(self):
        html = self.page()
        hint = 'Необязательно, не подтверждается, нужно только для связи.'
        self.assertIn('data-hint="%s"' % hint, html)
        # Тот же текст простой строкой под полем больше не стоит.
        self.assertNotIn('<div class="pf-hint">%s</div>' % hint, html)


class EmptyProfileTests(TestCase):
    def test_a_new_student_has_six_untouched_dropdowns(self):
        """Инвариант: шесть списков, и все шесть показывают «Не выбрано»."""
        html = _client(_person('acc_empty')).get('/profile/?tab=data').content.decode()
        self.assertEqual(html.count('pf-dd-value--empty"'), 6)

    def test_a_filled_profile_has_none(self):
        html = _client(_person('acc_done', **FULL)).get('/profile/?tab=data').content.decode()
        self.assertEqual(html.count('pf-dd-value--empty"'), 0)


class ChoicesTests(TestCase):
    """Подписи вариантов — ровно те, что в ТЗ."""

    def test_levels_are_four_short_names_with_descriptions(self):
        self.assertEqual(
            list(UserProfile.Level.choices),
            [('novice', 'Новичок'), ('basic', 'Начинающий'),
             ('region', 'Продолжающий'), ('final', 'Профи')])
        self.assertEqual(UserProfile.LEVEL_HINTS['novice'],
                         'Олимпиадной экономикой пока совсем не занимался')
        self.assertEqual(UserProfile.LEVEL_HINTS['basic'],
                         'Уже дошёл до школьного или муниципального этапа ВсОШ')
        self.assertEqual(UserProfile.LEVEL_HINTS['region'],
                         'Писал региональный этап ВсОШ или выходил на заключительный '
                         'этап перечневой')
        self.assertEqual(UserProfile.LEVEL_HINTS['final'],
                         'Участник финала ВсОШ или призёр перечневой')

    def test_levels_on_the_page_carry_the_empty_option_too(self):
        html = _client(_person('acc_lvl')).get('/profile/?tab=data').content.decode()
        block = html.split('data-field="level"', 1)[1].split('</details>', 1)[0]
        self.assertEqual(block.count('type="radio"'), 5)      # четыре уровня + «Не выбрано»
        self.assertIn('Не выбрано', block)

    def test_olympiad_groups_and_short_labels_describe_the_same_codes(self):
        """Инвариант: 4 + 6 + 1 = 11 кодов, и оба набора говорят об одних и тех же."""
        grouped = [code for _, options in UserProfile.OLYMPIAD_GROUPS for code, _ in options]
        self.assertEqual(len(grouped), 10)
        codes = grouped + [UserProfile.OLYMPIAD_NONE[0]]
        self.assertEqual(codes, [code for code, _ in UserProfile.OLYMPIAD_HISTORY])
        self.assertEqual(len(codes), 11)

    def test_olympiads_on_the_page_are_eleven_checkboxes_in_that_order(self):
        html = _client(_person('acc_ol')).get('/profile/?tab=data').content.decode()
        block = html.split('data-field="olympiad_history"', 1)[1].split('</details>', 1)[0]
        import re
        found = re.findall(r'name="olympiad_history" value="([a-z_]+)"', block)
        self.assertEqual(found, [code for code, _ in UserProfile.OLYMPIAD_HISTORY])

    def test_no_long_dash_in_any_choice_label(self):
        labels = ([text for _, text in UserProfile.OLYMPIAD_HISTORY]
                  + [text for _, options in UserProfile.OLYMPIAD_GROUPS for _, text in options]
                  + [text for _, text in UserProfile.Level.choices]
                  + list(UserProfile.LEVEL_HINTS.values()))
        for text in labels:
            self.assertNotIn('—', text, text)


class TelegramTests(TestCase):
    """Ник нормализуется, а не отбраковывается: люди приносят ссылку целиком."""

    def setUp(self):
        self.user = _person('acc_tg')
        self.client = _client(self.user)

    def _post(self, value):
        return self.client.post('/profile/?tab=data', dict(
            FULL, action='data', username='acc_tg', first_name='', last_name='',
            email='', telegram=value))

    def test_every_shape_of_the_same_nick_lands_the_same_way(self):
        for value in ('@masha_orl', 'masha_orl', 'https://t.me/masha_orl',
                      't.me/masha_orl', 'telegram.me/masha_orl', '  @masha_orl  '):
            with self.subTest(value):
                # ⚠️ ПЕРЕД КАЖДЫМ ШАГОМ СТИРАЕМ НИК. Без этого неудачное
                # сохранение проходило бы незамеченным: в профиле оставался
                # ник с прошлого шага, и проверка сходилась впустую
                # (нашла проверка зубастости 22.09.2026).
                self.user.profile.telegram = ''
                self.user.profile.save(update_fields=['telegram'])

                self._post(value)
                self.user.profile.refresh_from_db()
                self.assertEqual(self.user.profile.telegram, 'masha_orl', value)
                html = self.client.get('/profile/?tab=data').content.decode()
                self.assertIn('value="@masha_orl"', html)

    def test_empty_stays_empty(self):
        self._post('')
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.telegram, '')

    def test_a_bad_nick_is_an_error_and_the_profile_is_untouched(self):
        self._post('masha_orl')
        for bad in ('ab', 'маша_тг'):
            with self.subTest(bad):
                response = self._post(bad)
                self.assertEqual(response.status_code, 200)     # форма вернулась с ошибкой
                self.assertContains(response, 'Ник в Telegram')
                self.user.profile.refresh_from_db()
                self.assertEqual(self.user.profile.telegram, 'masha_orl')


class PhoneIsNotCollectedTests(TestCase):
    def test_an_old_number_survives_a_save_that_tries_to_change_it(self):
        """Инвариант: до = после. Форма телефон не принимает и не стирает."""
        user = _person('acc_phone', phone='+70000000000', **FULL)
        _client(user).post('/profile/?tab=data', dict(
            FULL, action='data', username='acc_phone', first_name='', last_name='',
            email='', phone='+79999999999'))
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.phone, '+70000000000')

    def test_the_form_has_no_phone_field_at_all(self):
        self.assertNotIn('phone', ProfileForm.Meta.fields)


class AvatarCropTests(TestCase):
    """Обрезка по координатам: что выбрали, то и сохранилось."""

    def setUp(self):
        self.user = _person('acc_ava')
        self.client = _client(self.user)

    def _upload(self, data, name='photo.png', **crop):
        payload = {'action': 'avatar',
                   'avatar': SimpleUploadedFile(name, data, content_type='image/png')}
        payload.update({k: str(v) for k, v in crop.items()})
        response = self.client.post('/profile/?tab=data', payload)
        self.user.profile.refresh_from_db()
        return response

    def _saved(self):
        self.user.profile.avatar.open('rb')
        try:
            image = Image.open(self.user.profile.avatar).convert('RGB')
            image.load()
        finally:
            self.user.profile.avatar.close()
        return image

    def _centre(self):
        image = self._saved()
        return image.getpixel((image.width // 2, image.height // 2))

    def test_01_the_chosen_square_is_what_gets_saved(self):
        """Левая половина красная, правая синяя; берём правую — выходит синий."""
        self._upload(_png(400, 200, (255, 0, 0), (0, 0, 255)),
                     crop_x=200, crop_y=0, crop_size=200)
        image = self._saved()
        self.assertEqual(image.size, (256, 256))
        red, green, blue = self._centre()
        self.assertGreater(blue, 200)
        self.assertLess(red, 60)

    def test_02_without_coordinates_the_square_is_taken_from_the_centre(self):
        self._upload(_png(400, 200, (255, 0, 0), (0, 0, 255)))
        image = self._saved()
        left = image.getpixel((10, image.height // 2))
        right = image.getpixel((image.width - 10, image.height // 2))
        self.assertGreater(left[0], 200)          # слева красное
        self.assertGreater(right[2], 200)         # справа синее

    def test_03_a_wild_coordinate_is_pressed_to_the_edge_not_a_500(self):
        response = self._upload(_png(400, 200, (255, 0, 0), (0, 0, 255)),
                                crop_x=10000, crop_y=0, crop_size=200)
        self.assertEqual(response.status_code, 302)
        self.assertGreater(self._centre()[2], 200)     # прижалось к правому краю

    def test_04_a_tiny_square_is_raised_to_the_minimum(self):
        response = self._upload(_png(400, 200, (255, 0, 0), (0, 0, 255)),
                                crop_x=0, crop_y=0, crop_size=5)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._saved().size, (256, 256))

    def test_05_exif_rotation_is_applied_before_the_crop(self):
        """Снимок с телефона: без поворота квадрат вырезался бы не там.

        Картинка 300×100: левая треть красная, остальное зелёное. Ориентация 6
        поворачивает её в 100×300 красным СВЕРХУ. Берём нижний квадрат — он
        обязан быть зелёным; без `exif_transpose` `y` прижался бы к нулю и
        вышло бы красное.
        """
        image = Image.new('RGB', (300, 100), (0, 200, 0))
        image.paste(Image.new('RGB', (100, 100), (255, 0, 0)), (0, 0))
        exif = Image.Exif()
        exif[0x0112] = 6
        buffer = io.BytesIO()
        image.save(buffer, 'JPEG', exif=exif)

        self._upload(buffer.getvalue(), name='phone.jpg', crop_x=0, crop_y=200, crop_size=100)
        red, green, blue = self._centre()
        self.assertGreater(green, 150, (red, green, blue))
        self.assertLess(red, 100, (red, green, blue))


class TutorTests(TestCase):
    def test_a_tutor_sees_the_shared_part_and_students_but_no_student_fields(self):
        html = _client(_person('acc_tutor', role='tutor')).get(
            '/profile/?tab=data').content.decode()
        self.assertIn('name="telegram"', html)
        self.assertIn('Ученики', html)
        self.assertNotIn('name="phone"', html)
        self.assertNotIn('data-field="grade"', html)
        self.assertNotIn('data-field="level"', html)
