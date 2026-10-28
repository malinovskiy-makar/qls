"""Стена 2 тура: окно на интро (какой экран показывает сервер) и анкета (docs/VP.md).

Таблица экранов — в `vp.views_wall.wall_window`; здесь по одной проверке на строку.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from problems.models_platform import UserProfile
from vp import wall
from vp.models import VPAttempt, VPTelegramLink, VPTelegramToken, VPWall
from vp.tests.helpers import load_demo

User = get_user_model()

TG = dict(TELEGRAM_BOT_TOKEN='000:test-token', TELEGRAM_BOT_USERNAME='test_wall_bot',
          TELEGRAM_WEBHOOK_SECRET='test-secret', VP_WALL_TG_ENABLED=True)
NO_TG = dict(TELEGRAM_BOT_TOKEN='', TELEGRAM_BOT_USERNAME='', TELEGRAM_WEBHOOK_SECRET='')
BOTH = override_settings(VP_WALL_ENABLED=True, MAIL_ENABLED=True, **TG)


class ScreenCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.variant = load_demo('10')

    def setUp(self):
        self.user = User.objects.create_user('ivan_site', password='p12345')
        self.client = Client()
        self.client.force_login(self.user)
        self.intro = reverse('vp:intro', args=[self.variant.slug])

    def page(self, state='1', client=None, **extra):
        query = {'wall': state, **extra} if state else extra
        return (client or self.client).get(self.intro, query).content.decode()

    def contact(self, via='tg'):
        wall.pass_contact(self.user, via)

    def survey_post(self, client=None, slug=None, **answers):
        data = {'grade': '10', 'tour2_status': 'waiting', 'source': 'friend', **answers}
        data = {k: v for k, v in data.items() if v is not None}
        return (client or self.client).post(
            reverse('vp:wall_survey', args=[slug or self.variant.slug]), data)


@BOTH
class ScreenTableTests(ScreenCase):
    def test_contact_default_is_screen_01(self):
        html = self.page()
        self.assertIn('Подключите Telegram, чтобы начать', html)
        self.assertIn('Тренажёр бесплатный. Взамен просим подписку на наш канал', html)
        self.assertIn('Вернитесь сюда – страница обновится сама.', html)
        self.assertIn('После «Старт» в боте обновите эту страницу.', html)
        self.assertIn('Мы храним номер вашего аккаунта в Telegram', html)
        self.assertIn('Подтвердить почтой', html)
        self.assertNotIn('Бот пришлёт разбор', html)

    def test_waiting_is_screen_02_with_polling(self):
        VPTelegramToken.objects.create(user=self.user, token_hash='x' * 64, slug=self.variant.slug)
        html = self.page()
        self.assertIn('<section class="vp-wall-screen" data-screen="waiting" data-poll=', html)
        self.assertRegex(html, r'data-screen="tg"\s+hidden')
        self.assertIn('Ждём подтверждения из Telegram', html)

    def test_waiting_has_the_open_in_app_form_without_new_tab(self):
        VPTelegramToken.objects.create(user=self.user, token_hash='x' * 64, slug=self.variant.slug)
        html = self.page()
        self.assertIn('Не открылось?', html)
        self.assertIn('Открыть в приложении Telegram', html)
        waiting = html.split('data-screen="waiting"', 1)[1]
        form = [f for f in waiting.split('<form')[1:] if 'name="app" value="1"' in f]
        self.assertEqual(len(form), 1)
        self.assertNotIn('target=', form[0].split('>', 1)[0])
        # «Открыть бота ещё раз» по-прежнему в новой вкладке и без app.
        again = [f for f in waiting.split('<form')[1:] if 'Открыть бота ещё раз' in f][0]
        self.assertIn('target="_blank"', again.split('>', 1)[0])
        self.assertNotIn('name="app"', again.split('</form>', 1)[0])

    def test_no_sub_is_screen_03_without_polling(self):
        VPTelegramLink.objects.create(user=self.user, tg_user_id=1, tg_username='ivan_econ',
                                      checked_at=timezone.now(), subscribed=False)
        html = self.page()
        self.assertIn('Осталось подписаться на канал', html)
        self.assertIn('Аккаунт <b class="ym-hide-content">@ivan_econ</b> ещё не подписан', html)
        self.assertNotIn('data-poll', html)

    def test_no_sub_without_nick(self):
        VPTelegramLink.objects.create(user=self.user, tg_user_id=1, checked_at=timezone.now())
        self.assertIn('Ваш аккаунт Telegram ещё не подписан на @weconomics_ru.', self.page())

    def test_error_is_screen_03_with_its_own_message(self):
        VPTelegramLink.objects.create(user=self.user, tg_user_id=1, checked_at=timezone.now(),
                                      last_error='network')
        html = self.page()
        self.assertIn('Не получилось проверить подписку – Telegram не ответил.', html)
        self.assertNotIn('Бот видит ваш аккаунт, но подписки нет', html)

    def test_email_screens(self):
        self.assertIn('Подтвердите почту', self.page('email'))
        self.assertIn('Подтвердите почту', self.page('code'))  # кода не просили → 04
        self.user.email, self.user.email_verified_at = 'a@example.ru', timezone.now()
        self.user.save()
        self.assertIn('Продолжить с почтой', self.page('email'))

    def test_survey_step_beats_any_parameter(self):
        self.contact()
        for state in ('1', 'email', 'code', 'closed'):
            self.assertIn('Три вопроса – и начинаем', self.page(state), state)

    def test_closed_parameter(self):
        self.assertIn('Вход в варианты временно закрыт. Попробуйте через час.', self.page('closed'))

    def test_eyebrow(self):
        self.assertIn('<div class="vp-wall-eyebrow">Демоверсия 2 тура · 10 класс · 70 минут</div>',
                      self.page())

    def test_window_is_rendered_open_only_with_parameter(self):
        self.assertIn(' data-open open>', self.page())
        html = self.page(state='')
        self.assertIn('id="vp-wall"', html)
        self.assertNotIn(' data-open open>', html)

    def test_no_window_with_unfinished_attempt(self):
        with override_settings(VP_WALL_ENABLED=False):
            self.client.post(reverse('vp:start', args=[self.variant.slug]), {'with_timer': '1'})
        self.assertNotIn('id="vp-wall"', self.page())

    def test_no_window_after_wall_is_passed(self):
        self.contact()
        self.survey_post()
        VPAttempt.objects.all().delete()
        self.assertNotIn('id="vp-wall"', self.page())


class PathSwitchTests(ScreenCase):
    @override_settings(VP_WALL_ENABLED=True, MAIL_ENABLED=False, **TG)
    def test_mail_off_hides_mail_links(self):
        self.assertNotIn('Подтвердить почтой', self.page())

    @override_settings(VP_WALL_ENABLED=True, MAIL_ENABLED=True, **NO_TG)
    def test_tg_off_goes_straight_to_email(self):
        html = self.page()
        self.assertIn('Подтвердите почту', html)
        self.assertNotIn('Подключить Telegram', html)
        self.user.email, self.user.email_verified_at = 'a@example.ru', timezone.now()
        self.user.save()
        html = self.page()
        self.assertIn('Продолжить с почтой', html)
        self.assertNotIn('Подключить', html)

    @override_settings(VP_WALL_ENABLED=True, MAIL_ENABLED=False, **NO_TG)
    def test_both_off_closes(self):
        self.assertIn('Вход в варианты временно закрыт', self.page())


@BOTH
class SurveyTests(ScreenCase):
    def test_incomplete_answers_give_error_and_no_attempt(self):
        self.contact()
        response = self.survey_post(source=None)
        self.assertEqual(response['Location'], self.intro + '?wall=1')
        self.assertEqual(VPAttempt.objects.count(), 0)
        self.assertIn('Ответьте на все три вопроса.', self.page())
        self.assertIsNone(VPWall.objects.get(user=self.user).survey_at)

    def test_complete_answers_start_the_attempt_with_chosen_mode(self):
        self.client.post(reverse('vp:start', args=[self.variant.slug]), {'with_timer': '0'})
        self.contact()
        response = self.survey_post()
        attempt = VPAttempt.objects.get()
        self.assertRedirects(response, reverse('vp:take', args=[attempt.public_code]),
                             fetch_redirect_response=False)
        self.assertFalse(attempt.with_timer)
        row = VPWall.objects.get(user=self.user)
        self.assertEqual((row.grade, row.tour2_status, row.source), ('10', 'waiting', 'friend'))

    def test_double_post_makes_one_attempt(self):
        self.contact()
        self.survey_post()
        self.survey_post()
        self.assertEqual(VPAttempt.objects.count(), 1)

    def test_profile_grade_filled_only_when_empty(self):
        UserProfile.objects.update_or_create(user=self.user, defaults={'grade': ''})
        self.contact()
        self.survey_post(grade='11')
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.grade, '11')

        other = User.objects.create_user('masha_site', password='p12345')
        UserProfile.objects.update_or_create(user=other, defaults={'grade': '9'})
        wall.pass_contact(other, 'email')
        client = Client()
        client.force_login(other)
        self.survey_post(client=client, grade='11')
        other.profile.refresh_from_db()
        self.assertEqual(other.profile.grade, '9')

    def test_grade_is_preselected_from_profile(self):
        UserProfile.objects.update_or_create(user=self.user, defaults={'grade': '11'})
        self.contact()
        self.assertIn('name="grade" value="11" required checked', self.page())
        self.assertNotIn('name="tour2_status" value="passed" required checked', self.page())

    def test_second_variant_after_survey_has_no_wall(self):
        self.contact()
        self.survey_post()
        other = load_demo('11')
        response = self.client.post(reverse('vp:start', args=[other.slug]), {'with_timer': '1'})
        attempt = VPAttempt.objects.get(variant=other)
        self.assertRedirects(response, reverse('vp:take', args=[attempt.public_code]),
                             fetch_redirect_response=False)

    def test_survey_is_not_overwritten(self):
        self.contact()
        self.survey_post(grade='10')
        VPAttempt.objects.all().delete()
        self.survey_post(grade='9', source='teacher')
        row = VPWall.objects.get(user=self.user)
        self.assertEqual((row.grade, row.source), ('10', 'friend'))

    def test_timer_line_under_the_button(self):
        self.contact()
        self.assertIn('Таймер на 70 минут запустится сразу. Анкету спрашиваем один раз.', self.page())
        self.client.post(reverse('vp:start', args=[self.variant.slug]), {'with_timer': '0'})
        html = self.page()
        self.assertIn('>Анкету спрашиваем один раз.</p>', html)
        self.assertNotIn('Таймер на 70 минут', html)


@override_settings(VP_WALL_ENABLED=True, MAIL_ENABLED=False, **TG)
class GuestWayTests(TestCase):
    PASSWORD = 'Zx9-kQ7-vB2-mLp-41'

    @classmethod
    def setUpTestData(cls):
        cls.variant = load_demo('10')

    def test_guest_without_timer_all_the_way(self):
        client = Client()
        slug = self.variant.slug
        wall_url = '/vp/%s/?wall=1' % slug
        client.post(reverse('vp:start', args=[slug]), {'with_timer': '0'})
        done = client.post(reverse('register'), {
            'username': 'guest_way', 'password1': self.PASSWORD, 'password2': self.PASSWORD,
            'role': 'student', 'consent': 'on', 'next': wall_url})
        self.assertEqual(done['Location'], wall_url)
        user = User.objects.get(username='guest_way')
        wall.pass_contact(user, 'tg')
        response = client.post(reverse('vp:wall_survey', args=[slug]),
                               {'grade': '10', 'tour2_status': 'passed', 'source': 'telegram'})
        attempt = VPAttempt.objects.get(user=user)
        self.assertRedirects(response, reverse('vp:take', args=[attempt.public_code]),
                             fetch_redirect_response=False)
        self.assertFalse(attempt.with_timer)


class GuestDialogTextTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.variant = load_demo('10')

    @override_settings(MAIL_ENABLED=True)
    def test_mail_on_mentions_email_code(self):
        html = Client().get(reverse('vp:intro', args=[self.variant.slug])).content.decode()
        self.assertIn('логин, почта и пароль – почту подтвердим кодом из письма', html)
        self.assertNotIn('без почты', html)

    @override_settings(MAIL_ENABLED=False)
    def test_mail_off_keeps_old_text(self):
        html = Client().get(reverse('vp:intro', args=[self.variant.slug])).content.decode()
        self.assertIn('логин и пароль, без почты', html)
