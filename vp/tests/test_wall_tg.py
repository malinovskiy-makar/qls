"""Стена 2 тура, путь Telegram: ссылка в бота, бот, проверка подписки, вебхук (docs/VP.md).

Telegram подменён: `vp.telegram.call` — фальшивкой, а `urllib.request.urlopen` в
общем базовом классе бросает AssertionError — любая настоящая сеть в тестах падает.

⚠️ ПРИВЯЗКА — НЕ ВХОД: отдельный класс проверяет, что ни один адрес пути Telegram
не открывает сессию на сайте.
"""
import io
import json
import re
import urllib.error
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from problems import email_codes
from vp import bot, telegram, wall
from vp.models import VPTelegramLink, VPTelegramToken, VPWall
from vp.tests.helpers import load_demo, make_published

User = get_user_model()
TOKEN = '123456:SECRET-bot-token-xyz'
SECRET = 'hook-secret_0123'

WALL_TG = override_settings(
    VP_WALL_ENABLED=True, VP_WALL_TG_ENABLED=True, MAIL_ENABLED=True,
    TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_BOT_USERNAME='test_wall_bot',
    TELEGRAM_WEBHOOK_SECRET=SECRET, TELEGRAM_CHANNEL='@weconomics_ru',
    TELEGRAM_API_BASE='https://api.telegram.org')


class FakeTelegram:
    """Подмена `vp.telegram.call`: пишет вызовы, отвечает по методу."""

    def __init__(self, status='member', fail=False, edit_fails=False):
        self.calls = []
        self.status, self.fail, self.edit_fails = status, fail, edit_fails

    def __call__(self, method, **params):
        self.calls.append((method, params))
        if method == 'getChatMember':
            if self.fail:
                raise telegram.TelegramError('api', 'Bad Request: member list is inaccessible')
            return {'status': self.status}
        if method == 'editMessageText' and self.edit_fails:
            raise telegram.TelegramError('api', 'message can not be edited')
        return {}

    def texts(self):
        return [p['text'] for m, p in self.calls if m in ('sendMessage', 'editMessageText')]

    def count(self, method):
        return sum(1 for m, _ in self.calls if m == method)


@WALL_TG
class TgCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.variant = load_demo('10')

    def setUp(self):
        cache.clear()
        net = mock.patch('urllib.request.urlopen',
                         side_effect=AssertionError('настоящая сеть в тестах'))
        net.start()
        self.addCleanup(net.stop)
        self.fake = FakeTelegram()
        patcher = mock.patch('vp.telegram.call', self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = User.objects.create_user('ivan_site', password='p12345')
        self.client = Client()
        self.client.force_login(self.user)

    def link_code(self, client=None, slug=None):
        response = (client or self.client).post(
            reverse('vp:wall_tg', args=[slug or self.variant.slug]))
        self.assertEqual(response.status_code, 302)
        match = re.fullmatch(r'https://t\.me/test_wall_bot\?start=(.+)', response['Location'])
        self.assertIsNotNone(match, response['Location'])
        return match.group(1)

    def hook(self, update, secret=SECRET, client=None):
        headers = {} if secret is None else {'HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN': secret}
        return (client or Client()).post(reverse('vp:tg_hook'), json.dumps(update),
                                         content_type='application/json', **headers)

    _uid = 0

    def start_update(self, code, tg_id=777, username='ivan_econ'):
        TgCase._uid += 1
        return {'update_id': TgCase._uid, 'message': {
            'message_id': 1, 'text': '/start ' + code,
            'chat': {'id': tg_id, 'type': 'private'},
            'from': {'id': tg_id, 'username': username, 'first_name': 'Иван'}}}

    def check_update(self, tg_id=777):
        TgCase._uid += 1
        return {'update_id': TgCase._uid, 'callback_query': {
            'id': 'cb%d' % TgCase._uid, 'data': 'check', 'from': {'id': tg_id},
            'message': {'message_id': 5, 'chat': {'id': tg_id, 'type': 'private'}}}}

    def state(self, client=None, slug=None):
        return (client or self.client).get(reverse('vp:wall_state'),
                                           {'v': slug or self.variant.slug})


class LinkTests(TgCase):
    def test_link_is_a_t_me_redirect_and_code_is_not_stored(self):
        code = self.link_code()
        self.assertRegex(code, r'^[A-Za-z0-9_-]{1,64}$')
        row = VPTelegramToken.objects.get()
        self.assertNotEqual(row.token_hash, code)
        self.assertNotIn(code, json.dumps(list(VPTelegramToken.objects.values()), default=str))

    def test_second_click_gives_the_same_code_other_variant_a_new_one(self):
        first = self.link_code()
        self.assertEqual(self.link_code(), first)
        self.assertEqual(VPTelegramToken.objects.count(), 1)
        other = load_demo('11')
        self.assertNotEqual(self.link_code(slug=other.slug), first)
        self.assertEqual(VPTelegramToken.objects.count(), 2)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(reverse('vp:wall_tg', args=[self.variant.slug])).status_code, 405)


class HookGuardTests(TgCase):
    @override_settings(TELEGRAM_WEBHOOK_SECRET='')
    def test_empty_secret_closes_the_hook_for_everyone(self):
        self.assertEqual(self.hook(self.start_update('x'), secret='').status_code, 403)
        self.assertEqual(self.hook(self.start_update('x'), secret=None).status_code, 403)

    def test_missing_or_wrong_secret_is_403_and_does_nothing(self):
        code = self.link_code()
        self.assertEqual(self.hook(self.start_update(code), secret=None).status_code, 403)
        self.assertEqual(self.hook(self.start_update(code), secret='wrong').status_code, 403)
        self.assertEqual(VPTelegramLink.objects.count(), 0)
        self.assertEqual(self.fake.calls, [])

    def test_non_ascii_header_is_403_not_500(self):
        self.assertEqual(self.hook(self.start_update('x'), secret='секрет').status_code, 403)

    def test_repeated_update_id_is_handled_once(self):
        code = self.link_code()
        update = self.start_update(code)
        self.hook(update)
        before = len(self.fake.calls)
        self.assertEqual(self.hook(update).status_code, 200)
        self.assertEqual(len(self.fake.calls), before)


class BotTests(TgCase):
    def test_start_with_subscription_links_and_gives_contact(self):
        code = self.link_code()
        self.assertEqual(self.hook(self.start_update(code)).status_code, 200)
        link = VPTelegramLink.objects.get(user=self.user)
        self.assertEqual((link.tg_user_id, link.tg_username, link.subscribed), (777, 'ivan_econ', True))
        self.assertEqual(VPWall.objects.get(user=self.user).contact_via, 'tg')
        self.assertIsNotNone(VPTelegramToken.objects.get().used_at)
        self.assertIn('Готово: подписка есть, аккаунт «ivan_site» привязан к сайту.', self.fake.texts()[-1])

    def test_same_or_old_code_is_expired(self):
        code = self.link_code()
        self.hook(self.start_update(code))
        self.hook(self.start_update(code))
        self.assertIn('Ссылка устарела', self.fake.texts()[-1])

        other = User.objects.create_user('late', password='p12345')
        client = Client()
        client.force_login(other)
        late = self.link_code(client=client)
        VPTelegramToken.objects.filter(user=other).update(
            created_at=timezone.now() - timedelta(minutes=31))
        self.hook(self.start_update(late, tg_id=888))
        self.assertIn('Ссылка устарела', self.fake.texts()[-1])
        self.assertFalse(VPTelegramLink.objects.filter(user=other).exists())

    def test_left_asks_to_subscribe_then_check_gives_contact(self):
        self.fake.status = 'left'
        self.hook(self.start_update(self.link_code()))
        self.assertTrue(VPTelegramLink.objects.filter(user=self.user).exists())
        self.assertEqual(wall.step(self.user), 'contact')
        method, params = self.fake.calls[-1]
        buttons = [b['text'] for b in params['reply_markup']['inline_keyboard'][0]]
        self.assertEqual(buttons, ['Подписаться', 'Проверить'])
        self.assertIn('Подписки на @weconomics_ru пока нет', params['text'])

        self.fake.status = 'member'
        self.hook(self.check_update())
        self.assertEqual(VPWall.objects.get(user=self.user).contact_via, 'tg')
        self.assertEqual(self.fake.count('answerCallbackQuery'), 1)

    def test_every_check_press_is_answered(self):
        self.fake.status = 'left'
        self.hook(self.start_update(self.link_code()))
        for status, fail in (('left', False), ('member', True), ('member', False)):
            self.fake.status, self.fake.fail = status, fail
            before = self.fake.count('answerCallbackQuery')
            self.hook(self.check_update())
            self.assertEqual(self.fake.count('answerCallbackQuery'), before + 1, status)

    def test_check_edit_failure_falls_back_to_new_message(self):
        self.fake.status = 'left'
        self.hook(self.start_update(self.link_code()))
        self.fake.status, self.fake.edit_fails = 'member', True
        self.hook(self.check_update())
        self.assertEqual(self.fake.calls[-2][0], 'sendMessage')
        self.assertIn('Готово', self.fake.calls[-2][1]['text'])

    def test_telegram_moves_to_the_fresh_code_owner(self):
        self.hook(self.start_update(self.link_code()))
        self.assertEqual(VPWall.objects.get(user=self.user).contact_via, 'tg')
        friend = User.objects.create_user('friend_b', password='p12345')
        client = Client()
        client.force_login(friend)
        self.hook(self.start_update(self.link_code(client=client)))
        self.assertEqual(VPTelegramLink.objects.get(tg_user_id=777).user, friend)
        self.assertEqual(VPWall.objects.get(user=self.user).contact_via, 'tg')
        self.assertIn('теперь он привязан к «friend_b»', self.fake.texts()[-1])

    def test_check_failure_leaves_no_contact_and_says_so(self):
        self.fake.fail = True
        with self.assertLogs('vp.telegram', 'WARNING'):
            self.hook(self.start_update(self.link_code()))
        self.assertEqual(wall.step(self.user), 'contact')
        self.assertIn('Не получилось проверить подписку', self.fake.texts()[-1])
        self.assertEqual(VPTelegramLink.objects.get(user=self.user).last_error, 'api')
        self.assertEqual(self.state().json()['tg'], 'error')

    def test_plain_start_and_group_chats(self):
        self.hook({'update_id': 9001, 'message': {'text': '/start', 'chat': {'id': 5, 'type': 'private'},
                                                  'from': {'id': 5}}})
        self.assertIn('https://weconomics.ai/vp/', self.fake.texts()[-1])
        before = len(self.fake.calls)
        self.hook({'update_id': 9002, 'message': {'text': '/start abc', 'chat': {'id': -5, 'type': 'group'},
                                                  'from': {'id': 5}}})
        self.assertEqual(len(self.fake.calls), before)


class StateTests(TgCase):
    def test_states(self):
        self.assertEqual(self.state(client=Client()).status_code, 403)
        self.assertEqual(self.state().json(), {'step': 'contact', 'tg': 'none', 'tg_username': ''})
        code = self.link_code()
        self.assertEqual(self.state().json()['tg'], 'waiting')
        self.fake.status = 'left'
        self.hook(self.start_update(code))
        self.assertEqual(self.state().json(), {'step': 'contact', 'tg': 'no_sub',
                                               'tg_username': 'ivan_econ'})
        hidden = make_published('wall-hidden-t1')
        self.assertEqual(self.state(slug=hidden.slug).status_code, 404)

    def test_check_button_rechecks_and_is_throttled(self):
        self.fake.status = 'left'
        self.hook(self.start_update(self.link_code()))
        url = reverse('vp:wall_check', args=[self.variant.slug])
        self.fake.status = 'member'
        self.assertEqual(self.client.post(url)['Location'],
                         reverse('vp:intro', args=[self.variant.slug]) + '?wall=1')
        self.assertEqual(VPWall.objects.get(user=self.user).contact_via, 'tg')
        cache.clear()
        VPWall.objects.filter(user=self.user).update(contact_via='')
        self.client.post(url)
        calls = self.fake.count('getChatMember')
        self.client.post(url)
        self.assertEqual(self.fake.count('getChatMember'), calls)


class NoLoginByTelegramTests(TgCase):
    def test_hook_never_logs_anyone_in(self):
        guest = Client()
        self.hook(self.start_update(self.link_code()), client=guest)
        self.hook(self.check_update(), client=guest)
        self.assertNotIn('_auth_user_id', guest.session)
        self.assertFalse(guest.get(reverse('vp:index')).wsgi_request.user.is_authenticated)

    def test_guest_gets_no_code_and_no_session_user(self):
        guest = Client()
        slug = self.variant.slug
        for name in ('vp:wall_tg', 'vp:wall_check'):
            response = guest.post(reverse(name, args=[slug]))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response['Location'].startswith('/login/'))
        self.assertEqual(guest.get(reverse('vp:wall_state'), {'v': slug}).status_code, 403)
        self.assertEqual(VPTelegramToken.objects.count(), 0)
        self.assertNotIn('_auth_user_id', guest.session)


@WALL_TG
class TokenNeverLeaksTests(TestCase):
    def test_network_error_has_no_token(self):
        with mock.patch('urllib.request.urlopen',
                        side_effect=urllib.error.URLError('down ' + TOKEN)):
            with self.assertRaises(telegram.TelegramError) as caught:
                telegram.call('getMe')
        self.assertEqual(caught.exception.kind, 'network')
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertIsNone(caught.exception.__context__)

    def test_api_error_has_no_token_and_log_is_clean(self):
        body = io.BytesIO(json.dumps({'ok': False, 'description': 'Unauthorized ' + TOKEN}).encode())
        error = urllib.error.HTTPError('https://api.telegram.org/bot%s/getChatMember' % TOKEN,
                                       401, 'Unauthorized', {}, body)
        with mock.patch('urllib.request.urlopen', side_effect=error):
            with self.assertLogs('vp.telegram', 'WARNING') as logs:
                result = telegram.check_subscription(777)
        self.assertEqual(result, (None, 'api'))
        self.assertNotIn(TOKEN, '\n'.join(logs.output))
        with mock.patch('urllib.request.urlopen', side_effect=error):
            with self.assertRaises(telegram.TelegramError) as caught:
                telegram.call('getMe')
        self.assertNotIn(TOKEN, str(caught.exception))

    def test_tg_setup_ping_without_network(self):
        out = io.StringIO()
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('x')):
            with self.assertRaises(CommandError) as caught:
                call_command('tg_setup', '--ping', stdout=out)
        self.assertNotIn(TOKEN, str(caught.exception) + out.getvalue())

    @override_settings(TELEGRAM_WEBHOOK_SECRET='')
    def test_set_webhook_refuses_empty_secret(self):
        with mock.patch('urllib.request.urlopen', side_effect=AssertionError('сеть')):
            with self.assertRaises(CommandError):
                call_command('tg_setup', '--set-webhook', 'https://example.org/vp/tg/hook/')


class DashTests(TestCase):
    def test_bot_texts_and_code_errors_use_short_dash(self):
        texts = list(bot.TEXTS.values())
        for reason in ('limit', 'wait', 'ip_locked', 'send_failed'):
            texts.append(email_codes.send_error(email_codes.SendResult(False, reason, 90)))
        for reason in ('wrong', 'locked', 'expired'):
            texts.append(email_codes.check_error(email_codes.CheckResult(False, reason, 3)))
        texts.append(email_codes.TAKEN_MESSAGE)
        for text in texts:
            self.assertNotIn('—', text)
