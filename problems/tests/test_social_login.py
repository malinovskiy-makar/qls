# -*- coding: utf-8 -*-
"""Вход через VK ID / Яндекс ID (фаза 2, решения 29.10.2026).

Сеть подменяется целиком (`unittest.mock`): настоящих запросов к сервисам нет.
Подставной токен `zz_token_marker` проверяет главный инвариант модуля — токен
не попадает ни в сессию, ни в базу.
"""
import dataclasses
import json
from datetime import date
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.core.cache import cache
from django.forms.models import model_to_dict
from django.test import TestCase, override_settings
from django.utils import timezone

from problems.models import SocialAccount, User
from problems.models_legal import ConsentRecord
from problems.models_platform import SignupSource, UserProfile
from problems.social import providers
from problems.tests.factories import make_user

TOKEN = 'zz_token_marker'

SOCIAL_ON = dict(SOCIAL_LOGIN_ENABLED=True,
                 VK_ID_CLIENT_ID='vk-app', VK_ID_CLIENT_SECRET='',
                 YANDEX_CLIENT_ID='ya-app', YANDEX_CLIENT_SECRET='ya-secret',
                 MAIL_ENABLED=True, ONBOARDING_ENABLED=False,
                 SOCIAL_STORE_BIRTHDATE=False)


def vk_user(**over):
    user = {'user_id': 1001, 'first_name': 'Иван', 'last_name': 'Петров',
            'email': 'ivan@mail.ru', 'birthday': '03.02.2010',
            'avatar': 'https://sun9-1.userapi.com/a.jpg'}
    user.update(over)
    return {key: value for key, value in user.items() if value is not None}


class FakeNetwork:
    """Подмена `providers._request`: отвечает как сервис и запоминает запросы."""

    def __init__(self, vk=None, yandex=None, fail=False):
        self.vk = vk or vk_user()
        self.yandex = yandex or {'id': '5005', 'first_name': 'Анна', 'last_name': 'Смирнова',
                                 'default_email': 'anna@yandex.ru', 'birthday': '2010-05-06',
                                 'default_avatar_id': 'abc', 'is_avatar_empty': False}
        self.fail = fail
        self.calls = []

    def __call__(self, url, *, data=None, headers=None):
        self.calls.append((url, dict(data or {}), dict(headers or {})))
        if self.fail:
            raise providers.SocialError('нет связи')
        if url in (providers.VKProvider.TOKEN_URL, providers.YandexProvider.TOKEN_URL):
            return {'access_token': TOKEN, 'refresh_token': TOKEN + '_r', 'id_token': TOKEN}
        if url == providers.VKProvider.USER_INFO_URL:
            return {'user': self.vk}
        if url == providers.YandexProvider.USER_INFO_URL:
            return self.yandex
        raise AssertionError('неожиданный адрес ' + url)


@override_settings(**SOCIAL_ON)
class SocialBase(TestCase):
    def setUp(self):
        cache.clear()

    def start(self, provider='vk', next_url=''):
        url = '/auth/%s/start/' % provider
        response = self.client.get(url, {'next': next_url} if next_url else {})
        self.assertEqual(response.status_code, 302)
        return response['Location'], parse_qs(urlsplit(response['Location']).query)

    def callback(self, provider='vk', network=None, state=None, next_url='', **params):
        _location, query = self.start(provider, next_url)
        network = network or FakeNetwork()
        with mock.patch.object(providers, '_request', network):
            response = self.client.get('/auth/%s/callback/' % provider, dict(
                {'code': 'code-1', 'device_id': 'dev-1',
                 'state': query['state'][0] if state is None else state}, **params))
        return response, network

    def finish(self, **post):
        data = {'consent': 'on'}
        data.update(post)
        return self.client.post('/auth/finish/', data)


class StateAndPkceTests(SocialBase):
    def test_wrong_state_is_400_and_creates_nothing(self):
        before = User.objects.count()
        response, network = self.callback(state='not-the-state')
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Не получилось войти через VK ID', status_code=400)
        self.assertEqual(User.objects.count(), before)
        self.assertEqual(SocialAccount.objects.count(), 0)
        self.assertEqual(network.calls, [])           # к сервису даже не ходили

    def test_expired_state_is_400(self):
        _location, query = self.start()
        session = self.client.session
        flow = session['social_flow']
        flow['at'] -= 11 * 60
        session['social_flow'] = flow
        session.save()
        with mock.patch.object(providers, '_request', FakeNetwork()):
            response = self.client.get('/auth/vk/callback/',
                                       {'code': 'c', 'state': query['state'][0]})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('social_pending', self.client.session)

    def test_pkce_challenge_matches_the_verifier_sent_on_exchange(self):
        location, query = self.start()
        self.assertTrue(location.startswith('https://id.vk.com/authorize?'))
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['scope'], ['vkid.personal_info email'])
        network = FakeNetwork()
        with mock.patch.object(providers, '_request', network):
            self.client.get('/auth/vk/callback/',
                            {'code': 'code-1', 'device_id': 'dev-1', 'state': query['state'][0]})
        url, sent, _headers = network.calls[0]
        self.assertEqual(url, 'https://id.vk.com/oauth2/auth')
        self.assertEqual(sent['device_id'], 'dev-1')
        self.assertEqual(providers.code_challenge(sent['code_verifier']),
                         query['code_challenge'][0])

    def test_yandex_uses_pkce_and_oauth_header(self):
        location, query = self.start('yandex')
        self.assertTrue(location.startswith('https://oauth.yandex.ru/authorize?'))
        self.assertNotIn('login:birthday', query['scope'][0])    # дату не просим без флага
        response, network = self.callback('yandex')
        self.assertRedirects(response, '/auth/finish/', fetch_redirect_response=False)
        info = [call for call in network.calls if call[0].startswith('https://login.yandex.ru')]
        self.assertEqual(info[0][2]['Authorization'], 'OAuth ' + TOKEN)

    def test_service_error_is_a_clear_page_not_500(self):
        response, _network = self.callback(network=FakeNetwork(fail=True))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Попробуйте ещё раз или войдите почтой', status_code=400)
        self.assertEqual(User.objects.count(), 0)

    def test_user_cancelled_at_the_service(self):
        _location, query = self.start()
        response = self.client.get('/auth/vk/callback/',
                                   {'error': 'access_denied', 'state': query['state'][0]})
        self.assertEqual(response.status_code, 400)


class KnownAccountTests(SocialBase):
    def test_known_uid_logs_into_the_same_account(self):
        owner = make_user('ivan_old')
        SocialAccount.objects.create(user=owner, provider='vk', uid='1001')
        before = User.objects.count()
        response, _network = self.callback(next_url='/catalog/')
        self.assertRedirects(response, '/catalog/', fetch_redirect_response=False)
        self.assertEqual(User.objects.count(), before)
        self.assertEqual(int(self.client.session['_auth_user_id']), owner.pk)
        self.assertIsNotNone(SocialAccount.objects.get(uid='1001').last_login_at)

    def test_logged_in_user_links_the_service(self):
        user = make_user('linker')
        self.client.force_login(user)
        response, _network = self.callback()
        self.assertRedirects(response, '/profile/', fetch_redirect_response=False)
        self.assertTrue(SocialAccount.objects.filter(user=user, uid='1001').exists())

    def test_uid_of_another_account_is_refused(self):
        SocialAccount.objects.create(user=make_user('first_owner'), provider='vk', uid='1001')
        self.client.force_login(make_user('second'))
        response, _network = self.callback()
        self.assertContains(response, 'Этот VK ID уже привязан к другому аккаунту',
                            status_code=400)
        self.assertEqual(SocialAccount.objects.filter(uid='1001').count(), 1)


class AutoMergeTests(SocialBase):
    """Таблица автосклейки (решение 29.10.2026)."""

    def test_verified_here_and_there_logs_into_a(self):
        a = make_user('owner_a', email='ivan@mail.ru', email_verified_at=timezone.now())
        before = User.objects.count()
        response, _network = self.callback()
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response['Location'], '/auth/finish/')
        self.assertEqual(User.objects.count(), before)
        self.assertEqual(SocialAccount.objects.get(uid='1001').user, a)
        self.assertEqual(int(self.client.session['_auth_user_id']), a.pk)

    def test_staff_is_never_merged(self):
        staff = make_user('admin_a', email='ivan@mail.ru', email_verified_at=timezone.now(),
                          is_staff=True)
        response, _network = self.callback()
        self.assertRedirects(response, '/auth/finish/', fetch_redirect_response=False)
        self.assertFalse(SocialAccount.objects.filter(user=staff).exists())

    def test_unverified_email_here_is_not_merged(self):
        a = make_user('owner_b', email='IVAN@mail.ru')         # почта не подтверждена
        response, _network = self.callback()
        self.assertRedirects(response, '/auth/finish/', fetch_redirect_response=False)
        self.assertFalse(SocialAccount.objects.filter(user=a).exists())
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_unverified_email_there_is_not_merged(self):
        make_user('owner_c', email='ivan@mail.ru', email_verified_at=timezone.now())
        vk = providers.PROVIDERS['vk']
        with mock.patch.object(type(vk), 'trust_email', False, create=True), \
                mock.patch.dict(providers.PROVIDERS, {'vk': providers.VKProvider(
                    **{**vk.__dict__, 'trust_email': False})}):
            response, _network = self.callback()
        self.assertRedirects(response, '/auth/finish/', fetch_redirect_response=False)
        self.assertEqual(SocialAccount.objects.count(), 0)

    def test_no_email_goes_to_finish_then_to_the_email_page(self):
        response, _network = self.callback(network=FakeNetwork(vk=vk_user(email=None)))
        self.assertRedirects(response, '/auth/finish/', fetch_redirect_response=False)
        response = self.finish()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/account/email/'))


class FinishScreenTests(SocialBase):
    def test_screen_shows_what_the_service_gave(self):
        self.callback()
        response = self.client.get('/auth/finish/')
        self.assertContains(response, 'Почти готово, Иван')
        self.assertContains(response, 'i•••@mail.ru')
        self.assertNotContains(response, 'ivan@mail.ru')
        self.assertNotContains(response, 'Дата рождения')        # флаг выключен
        self.assertContains(response, 'Это не я')

    def test_without_consent_nothing_is_created(self):
        self.callback()
        before = User.objects.count()
        response = self.client.post('/auth/finish/', {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Без согласия зарегистрироваться нельзя.')
        self.assertEqual(User.objects.count(), before)

    def test_with_consent_a_new_account_is_created(self):
        self.callback(network=FakeNetwork(vk=vk_user(first_name='ivan', last_name='petrov')))
        before = User.objects.count()
        response = self.finish(mail_consent='on')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.count(), before + 1)
        user = User.objects.latest('pk')
        self.assertRegex(user.username, r'^econ_[a-z0-9]{6}$')
        self.assertNotIn('ivan', user.username)
        self.assertNotIn('petrov', user.username)
        self.assertFalse(user.has_usable_password())
        self.assertEqual((user.first_name, user.last_name), ('ivan', 'petrov'))
        self.assertEqual(user.email, 'ivan@mail.ru')
        self.assertIsNotNone(user.email_verified_at)
        self.assertEqual(user.profile.role, UserProfile.Role.STUDENT)
        self.assertTrue(SocialAccount.objects.get(user=user).created_user)
        kinds = set(ConsentRecord.objects.filter(user=user).values_list('kind', flat=True))
        self.assertEqual(kinds, {ConsentRecord.Kind.PD, ConsentRecord.Kind.MAIL})
        self.assertTrue(SignupSource.objects.filter(user=user).exists())
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
        # Почта подтверждена — страница «Почта» не нужна.
        self.assertFalse(response['Location'].startswith('/account/email/'))

    def test_mail_consent_is_optional(self):
        self.callback()
        self.finish()
        user = User.objects.latest('pk')
        self.assertFalse(ConsentRecord.objects.filter(
            user=user, kind=ConsentRecord.Kind.MAIL).exists())

    def test_taken_email_is_not_attached(self):
        self.callback(network=FakeNetwork(vk=vk_user(email='busy@mail.ru')))
        # Пока человек читал экран, почту подтвердил другой аккаунт.
        make_user('busy', email='busy@mail.ru', email_verified_at=timezone.now())
        response = self.finish()
        user = User.objects.latest('pk')
        self.assertIsNone(user.email_verified_at)
        self.assertTrue(response['Location'].startswith('/account/email/'))

    def test_it_is_not_me_clears_the_data(self):
        self.callback()
        response = self.client.get('/auth/finish/', {'cancel': '1'})
        self.assertRedirects(response, '/login/', fetch_redirect_response=False)
        self.assertNotIn('social_pending', self.client.session)

    def test_next_survives_to_the_end(self):
        self.callback(next_url='/vp/variant-1/')
        response = self.finish()
        self.assertEqual(response['Location'], '/vp/variant-1/')

    @override_settings(ONBOARDING_ENABLED=True)
    def test_with_onboarding_the_new_account_goes_to_welcome(self):
        self.callback(next_url='/vp/variant-1/')
        response = self.finish()
        self.assertEqual(response['Location'], '/welcome/?next=%2Fvp%2Fvariant-1%2F')

    def test_foreign_next_is_dropped(self):
        _location, _query = self.start(next_url='https://evil.example/')
        self.assertEqual(self.client.session['social_flow']['next'], '')


class BirthDateTests(SocialBase):
    def test_flag_off_no_birth_date_even_if_the_service_gave_it(self):
        self.callback()
        self.assertIsNone(self.client.session['social_pending']['birth_date'])
        self.finish()
        self.assertIsNone(User.objects.latest('pk').profile.birth_date)

    @override_settings(SOCIAL_STORE_BIRTHDATE=True)
    def test_flag_on_birth_date_is_stored(self):
        self.callback()
        response = self.client.get('/auth/finish/')
        self.assertContains(response, '03.02.2010')
        self.finish()
        self.assertEqual(User.objects.latest('pk').profile.birth_date, date(2010, 2, 3))

    @override_settings(SOCIAL_STORE_BIRTHDATE=True)
    def test_partial_yandex_date_is_dropped(self):
        network = FakeNetwork()
        network.yandex['birthday'] = '0000-05-06'
        self.callback('yandex', network=network)
        self.assertIsNone(self.client.session['social_pending']['birth_date'])


class NoTokensAnywhereTests(SocialBase):
    def _session_dump(self):
        return json.dumps(dict(self.client.session.items()), ensure_ascii=False, default=str)

    def test_token_never_reaches_session_or_database(self):
        self.callback()
        self.assertNotIn(TOKEN, self._session_dump())
        self.finish(mail_consent='on')
        self.assertNotIn(TOKEN, self._session_dump())
        user = User.objects.latest('pk')
        rows = [user, user.profile, *SocialAccount.objects.filter(user=user),
                *ConsentRecord.objects.filter(user=user),
                *SignupSource.objects.filter(user=user)]
        for row in rows:
            dumped = json.dumps(model_to_dict(row), ensure_ascii=False, default=str)
            self.assertNotIn(TOKEN, dumped, type(row).__name__)

    def test_autolink_and_known_login_keep_no_tokens(self):
        make_user('merge_me', email='ivan@mail.ru', email_verified_at=timezone.now())
        self.callback()
        self.assertNotIn(TOKEN, self._session_dump())
        for row in SocialAccount.objects.all():
            self.assertNotIn(TOKEN, json.dumps(model_to_dict(row), default=str))


class AvatarTests(SocialBase):
    def _opener(self):
        opener = mock.MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b'not-an-image'
        return opener

    def test_foreign_domain_is_never_requested(self):
        for url in ('https://evil.example/a.jpg', 'http://sun9-1.userapi.com/a.jpg',
                    'https://userapi.com.evil.example/a.jpg'):
            opener = self._opener()
            with mock.patch.object(providers.urllib.request, 'build_opener',
                                   return_value=opener) as build:
                self.assertIsNone(providers.download_avatar(url))
            build.assert_not_called()
            opener.open.assert_not_called()

    def test_foreign_avatar_is_not_downloaded_on_signup(self):
        opener = self._opener()
        self.callback(network=FakeNetwork(vk=vk_user(avatar='https://evil.example/a.jpg')))
        with mock.patch.object(providers.urllib.request, 'build_opener',
                               return_value=opener) as build:
            self.finish()
        build.assert_not_called()
        self.assertFalse(User.objects.latest('pk').profile.avatar)

    def test_allowed_domain_is_requested_and_bad_bytes_are_ignored(self):
        opener = self._opener()
        with mock.patch.object(providers.urllib.request, 'build_opener',
                               return_value=opener):
            self.assertEqual(providers.download_avatar('https://sun9-1.userapi.com/a.jpg'),
                             b'not-an-image')
        self.callback()
        with mock.patch.object(providers.urllib.request, 'build_opener',
                               return_value=opener):
            response = self.finish()
        self.assertEqual(response.status_code, 302)            # мусор вместо картинки — молча
        self.assertFalse(User.objects.latest('pk').profile.avatar)


class FlagTests(TestCase):
    """Флаг выключен (по умолчанию в тестах) — функции нет вовсе."""

    def test_no_buttons_and_404(self):
        for page in ('/login/', '/register/'):
            self.assertNotContains(self.client.get(page), 'social-btn')
        self.assertEqual(self.client.get('/auth/vk/start/').status_code, 404)
        self.assertEqual(self.client.get('/auth/yandex/callback/').status_code, 404)

    @override_settings(SOCIAL_LOGIN_ENABLED=True, VK_ID_CLIENT_ID='vk-app')
    def test_button_only_for_a_service_with_keys(self):
        for page in ('/login/?next=/vp/x/', '/register/?next=/vp/x/'):
            response = self.client.get(page)
            self.assertContains(response, 'href="/auth/vk/start/?next=/vp/x/"')
            self.assertNotContains(response, '/auth/yandex/start/')
            self.assertContains(response, '>или<')
        self.assertEqual(self.client.get('/auth/yandex/start/').status_code, 404)

    def test_unknown_provider_is_404(self):
        with self.settings(SOCIAL_LOGIN_ENABLED=True, VK_ID_CLIENT_ID='x'):
            self.assertEqual(self.client.get('/auth/google/start/').status_code, 404)
