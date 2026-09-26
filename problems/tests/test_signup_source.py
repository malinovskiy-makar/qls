# -*- coding: utf-8 -*-
"""Яндекс Метрика и источник регистрации (ADR 0133).

Что держат эти тесты.

**Первое касание.** `FirstTouchMiddleware`: метка из ссылки ложится в
подписанную куку на 90 дней, вторая метку первой не перезаписывает, длина
режется до 100 символов, без метки кука не ставится вовсе.

**Запись при регистрации для трёх видов.** Преподаватель и ученик — через
настоящую форму `/register/`; «по приглашению» — через `record_signup`
напрямую: ссылки-приглашения в продукте ещё нет, и форма такой вид не выдаёт.
Без куки строка всё равно заводится — с пустыми метками и видом регистрации.

**Цель Метрики — ровно один раз** и только при заданном номере счётчика.

**Счётчик на страницах и в CSP** — только при заданном номере; каждый
корневой шаблон подключает обе половины; кабинеты не отдают Метрике
заголовков (в них имена детей).

Таблица «ресурс × роль × действие» (проверка границ доступа):

| Ресурс | Аноним | Ученик / репетитор | Персонал |
|---|---|---|---|
| кука первого касания | ставит себе сам, GET с меткой | так же | так же |
| строка `SignupSource` | заводит только своя регистрация | — | — |
| список в админке | нет, уводит на вход | нет, уводит на вход | читает; добавить и править нельзя |
| значения меток на страницах сайта | не выводятся | не выводятся | — |

Каждая клетка закрыта тестом ниже.
"""
import re
from pathlib import Path
from unittest import mock
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.template import RequestContext, Template
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from config.security_headers import CSP_REPORT_ONLY
from problems import signup_source
from problems.forms_accounts import ProfileForm
from problems.models_platform import SignupSource, UserProfile
from problems.tests.test_production_settings import _production_module

User = get_user_model()

METRIKA_ID = '12345678'
PASSWORD = 'Kx7-veter-bereg-19'
LANDING = '/register/'
COOKIE = signup_source.COOKIE_NAME


def _landing(**params):
    return LANDING + '?' + urlencode(params)


def _register(client, username, role='student'):
    return client.post(reverse('register'), {
        'username': username, 'password1': PASSWORD, 'password2': PASSWORD,
        'role': role, 'consent': 'on'})


def _request(cookie=None):
    """Запрос с сессией и, если дали, с кукой первого касания."""
    request = RequestFactory().get('/')
    SessionMiddleware(lambda r: None).process_request(request)
    if cookie is not None:
        request.COOKIES[COOKIE] = cookie
    return request


def _touch_of(client):
    return signup_source.read_first_touch(_request(client.cookies[COOKIE].value))


class FirstTouchTests(TestCase):
    """Кука первого касания: ставится, не перезаписывается, режется."""

    def setUp(self):
        cache.clear()   # счётчик регистраций с одного адреса живёт в кэше

    def test_utm_link_sets_signed_cookie_for_90_days(self):
        response = self.client.get(
            _landing(utm_source='telegram', utm_medium='post', utm_campaign='sept',
                     utm_content='pin', utm_term='эластичность'),
            HTTP_REFERER='https://t.me/weconomics_ru')
        morsel = response.cookies[COOKIE]
        self.assertEqual(int(morsel['max-age']), 90 * 24 * 60 * 60)
        self.assertTrue(morsel['httponly'])
        self.assertEqual(morsel['samesite'], 'Lax')
        touch = _touch_of(self.client)
        self.assertEqual(
            [touch[k] for k in signup_source.UTM_KEYS],
            ['telegram', 'post', 'sept', 'pin', 'эластичность'])
        self.assertEqual(touch['landing_path'], LANDING)
        self.assertEqual(touch['referrer'], 'https://t.me/weconomics_ru')
        self.assertIsNotNone(touch['first_seen_at'])

    def test_first_touch_is_not_overwritten(self):
        self.client.get(_landing(utm_source='telegram'))
        first = self.client.cookies[COOKIE].value
        response = self.client.get(_landing(utm_source='vk', utm_campaign='other'))
        self.assertNotIn(COOKIE, response.cookies, 'вторая метка переписала куку')
        self.assertEqual(self.client.cookies[COOKIE].value, first)
        self.assertEqual(_touch_of(self.client)['utm_source'], 'telegram')

    def test_values_are_clipped_to_100_characters(self):
        self.client.get(_landing(utm_source='s' * 300, utm_campaign='к' * 150),
                        HTTP_REFERER='https://example.org/' + 'r' * 300)
        touch = _touch_of(self.client)
        self.assertEqual(touch['utm_source'], 's' * 100)
        self.assertEqual(touch['utm_campaign'], 'к' * 100)
        self.assertEqual(len(touch['referrer']), 100)
        # В базу при регистрации уходит то же самое, а не исходная строка.
        _register(self.client, 'dlinnaya_metka')
        source = SignupSource.objects.get(user__username='dlinnaya_metka')
        self.assertEqual(source.utm_source, 's' * 100)
        self.assertEqual(len(source.referrer), 100)

    def test_control_characters_are_removed(self):
        """NUL — отдельно: PostgreSQL не принимает его в тексте вовсе."""
        self.client.get(LANDING + '?utm_source=%00tele%0Agram%E2%80%8B')
        self.assertEqual(_touch_of(self.client)['utm_source'], 'telegram')

    def test_no_utm_sets_nothing(self):
        response = self.client.get(LANDING + '?page=2&ref=abc')
        self.assertNotIn(COOKIE, response.cookies)

    def test_empty_utm_is_not_a_touch(self):
        """Пустая метка заняла бы место первого касания навсегда."""
        response = self.client.get(LANDING + '?utm_source=&utm_medium=%20')
        self.assertNotIn(COOKIE, response.cookies)

    def test_post_does_not_touch(self):
        response = self.client.post(LANDING + '?utm_source=telegram', {})
        self.assertNotIn(COOKIE, response.cookies)

    def test_forged_cookie_is_ignored_and_replaced(self):
        self.client.cookies[COOKIE] = 'eyJ1dG1fc291cmNlIjoiZmFrZSJ9:forged:sig'
        self.assertIsNone(_touch_of(self.client))
        response = self.client.get(_landing(utm_source='vk'))
        self.assertIn(COOKIE, response.cookies)
        self.assertEqual(_touch_of(self.client)['utm_source'], 'vk')


class SignupRecordTests(TestCase):
    """Строка `SignupSource` для трёх видов регистрации."""

    def setUp(self):
        cache.clear()

    def test_teacher_signup_records_first_touch(self):
        self.client.get(_landing(utm_source='telegram', utm_medium='post',
                                 utm_campaign='sept'),
                        HTTP_REFERER='https://t.me/weconomics_ru')
        response = _register(self.client, 'prepod_a', role='tutor')
        self.assertEqual(response.status_code, 302)
        source = SignupSource.objects.get(user__username='prepod_a')
        self.assertEqual(source.signup_kind, SignupSource.Kind.TEACHER)
        self.assertEqual((source.utm_source, source.utm_medium, source.utm_campaign),
                         ('telegram', 'post', 'sept'))
        self.assertEqual(source.landing_path, LANDING)
        self.assertEqual(source.referrer, 'https://t.me/weconomics_ru')
        self.assertIsNotNone(source.first_seen_at)

    def test_student_signup_without_cookie_still_records_kind(self):
        _register(self.client, 'uchenik_b')
        source = SignupSource.objects.get(user__username='uchenik_b')
        self.assertEqual(source.signup_kind, SignupSource.Kind.STUDENT)
        self.assertEqual([getattr(source, k) for k in signup_source.UTM_KEYS], [''] * 5)
        self.assertEqual((source.landing_path, source.referrer), ('', ''))
        self.assertIsNone(source.first_seen_at)

    def test_invited_kind_goes_through_the_same_function(self):
        """Ссылки-приглашения в продукте нет. Появится — позовёт `record_signup`
        с видом `invited`, и метка первого касания доедет так же."""
        self.client.get(_landing(utm_source='teacher_link'))
        user = User.objects.create_user('po_priglasheniyu', password=PASSWORD)
        signup_source.record_signup(_request(self.client.cookies[COOKIE].value), user,
                                    SignupSource.Kind.INVITED)
        source = SignupSource.objects.get(user=user)
        self.assertEqual(source.signup_kind, 'invited')
        self.assertEqual(source.utm_source, 'teacher_link')

    def test_first_record_is_kept(self):
        user = User.objects.create_user('odin_raz', password=PASSWORD)
        signup_source.record_signup(_request(), user, SignupSource.Kind.STUDENT)
        self.client.get(_landing(utm_source='late'))
        signup_source.record_signup(_request(self.client.cookies[COOKIE].value), user,
                                    SignupSource.Kind.TEACHER)
        source = SignupSource.objects.get(user=user)
        self.assertEqual((source.signup_kind, source.utm_source), ('student', ''))

    def test_failure_to_record_does_not_break_signup(self):
        with mock.patch.object(SignupSource.objects, 'get_or_create',
                               side_effect=RuntimeError('нарочно')):
            with self.assertLogs('problems.signup_source', level='ERROR'):
                response = _register(self.client, 'uchenik_c')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='uchenik_c').exists())


@override_settings(YANDEX_METRIKA_ID=METRIKA_ID)
class GoalTests(TestCase):
    """Цель выводит следующая страница — и только один раз."""

    def setUp(self):
        cache.clear()

    def _first_page_after(self, username, role):
        response = _register(self.client, username, role=role)
        return response['Location']

    def test_student_goal_once(self):
        url = self._first_page_after('uchenik_goal', 'student')
        html = self.client.get(url).content.decode()
        self.assertEqual(html.count("weco.reachGoalOnce('signup_student', '"), 1)
        self.assertRegex(html, r"reachGoalOnce\('signup_student', '[0-9a-f]{16}'\)")
        again = self.client.get(url).content.decode()
        self.assertIn('weco.reachGoalOnce = function', again)   # счётчик на месте
        self.assertNotIn("weco.reachGoalOnce('", again)          # а вызова цели нет

    def test_teacher_goal_name(self):
        url = self._first_page_after('prepod_goal', 'tutor')
        html = self.client.get(url).content.decode()
        self.assertIn("weco.reachGoalOnce('signup_teacher', '", html)

    def test_goal_is_taken_only_by_the_counter_template(self):
        """Фрагмент, отрисованный с контекстом запроса раньше страницы, цель
        не съедает: её забирает только шаблон счётчика."""
        request = _request()
        request.session[signup_source.GOAL_SESSION_KEY] = {
            'name': 'signup_student', 'token': 'a' * 16}
        Template('{{ metrika_id }}').render(RequestContext(request, {}))
        self.assertIn(signup_source.GOAL_SESSION_KEY, request.session)
        html = render_to_string('_metrika.html', request=request)
        self.assertIn("weco.reachGoalOnce('signup_student', 'aaaaaaaaaaaaaaaa')", html)
        self.assertNotIn(signup_source.GOAL_SESSION_KEY, request.session)

    def test_foreign_goal_in_session_never_reaches_the_script(self):
        request = _request()
        request.session[signup_source.GOAL_SESSION_KEY] = {
            'name': "x');alert(1);//", 'token': 'a' * 16}
        self.assertIsNone(signup_source.pop_goal(request))
        request.session[signup_source.GOAL_SESSION_KEY] = {
            'name': 'signup_student', 'token': "');alert(1);//aaaa"}
        self.assertIsNone(signup_source.pop_goal(request))


class NoCounterTests(TestCase):
    """Номера нет (локально, площадка dev) — ни счётчика, ни цели в сессии."""

    def setUp(self):
        cache.clear()

    @override_settings(YANDEX_METRIKA_ID='')
    def test_no_id_no_counter_no_goal(self):
        response = _register(self.client, 'uchenik_nogoal')
        self.assertNotIn(signup_source.GOAL_SESSION_KEY, self.client.session)
        html = self.client.get(response['Location']).content.decode()
        self.assertNotIn('mc.yandex.ru', html)
        # Страница гостя — новым клиентом: вошедшего регистрация уводит в профиль.
        guest = self.client_class().get(LANDING)
        self.assertEqual(guest.status_code, 200)
        self.assertNotIn('mc.yandex.ru', guest.content.decode())


class CounterOnPagesTests(TestCase):
    """Обе половины счётчика на месте; кабинет не отдаёт заголовков."""

    @override_settings(YANDEX_METRIKA_ID=METRIKA_ID)
    def test_public_page_has_both_halves_in_their_places(self):
        html = self.client.get(LANDING).content.decode()
        self.assertIn('ym(%s, "init"' % METRIKA_ID, html)
        self.assertIn('webvisor: true', html)
        self.assertNotIn('sendTitle: false', html)
        # Скрипт — в <head>, картинка noscript — в <body>.
        head, body = html.split('</head>', 1)
        self.assertIn('https://mc.yandex.ru/metrika/tag.js', head)
        self.assertNotIn('mc.yandex.ru/watch/', head)
        self.assertIn('https://mc.yandex.ru/watch/%s' % METRIKA_ID, body)

    @override_settings(YANDEX_METRIKA_ID=METRIKA_ID)
    def test_cabinet_does_not_send_titles(self):
        user = User.objects.create_user('uchenik_kab', password=PASSWORD)
        self.client.force_login(user)
        html = self.client.get('/profile/').content.decode()
        self.assertIn('sendTitle: false', html)


class EveryRootTemplateTests(SimpleTestCase):
    """Каждый шаблон-документ (с doctype) подключает обе половины счётчика.

    Сторож для нового корневого шаблона: без него страница молча выпала бы
    из статистики — как на бою 06.09.2026 выпадало меню без `site_meta`.
    """

    def test_each_document_template_has_the_counter(self):
        base = Path(settings.BASE_DIR)
        paths = list(base.glob('templates/**/*.html')) + list(base.glob('*/templates/**/*.html'))
        roots = [p for p in paths
                 if not p.relative_to(base).parts[0].startswith(('venv', 'node_modules'))
                 and re.search(r'<!doctype html', p.read_text(encoding='utf-8'), re.I)]
        self.assertGreaterEqual(len(roots), 12, 'корневые шаблоны не найдены — маска сломана')
        missing = [str(p.relative_to(base)) for p in roots
                   if "{% include '_metrika.html'" not in p.read_text(encoding='utf-8')
                   or "{% include '_metrika_noscript.html' %}" not in p.read_text(encoding='utf-8')]
        self.assertEqual(missing, [])


class CspTests(TestCase):
    """Адреса Метрики в CSP — только при номере счётчика и без лишнего."""

    @override_settings(YANDEX_METRIKA_ID=METRIKA_ID)
    def test_metrika_sources_when_counter_is_on(self):
        policy = self.client.get('/robots.txt').headers['Content-Security-Policy-Report-Only']
        for directive in (
                "script-src 'self' 'unsafe-inline' https://mc.yandex.ru https://yastatic.net",
                "img-src 'self' data: blob: https://mc.yandex.ru",
                "connect-src 'self' https://mc.yandex.ru",
                'frame-src blob: https://mc.yandex.ru',
                'child-src blob: https://mc.yandex.ru'):
            self.assertIn(directive, policy)
        # frame-ancestors не тронут: фрейм запрещает X-Frame-Options (ADR 0013).
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertTrue(policy.endswith('report-uri /csp-report/'))
        # Весь список справки дал бы ~3 КБ на каждом ответе и 502 у nginx.
        self.assertLess(len(policy), 1024)

    @override_settings(YANDEX_METRIKA_ID='')
    def test_policy_unchanged_without_counter(self):
        policy = self.client.get('/robots.txt').headers['Content-Security-Policy-Report-Only']
        self.assertEqual(policy, CSP_REPORT_ONLY)
        self.assertNotIn('yandex', policy)


class ProductionTemplatesTests(SimpleTestCase):
    """Боевые настройки задают TEMPLATES заново — processor обязан быть и там."""

    def test_metrika_processor_in_production(self):
        with _production_module() as prod:
            prod_list = list(prod.TEMPLATES[0]['OPTIONS']['context_processors'])
        self.assertIn('config.context_processors.metrika', prod_list)
        self.assertEqual(prod_list, settings.TEMPLATES[0]['OPTIONS']['context_processors'])


class WebvisorMaskingTests(TestCase):
    """Ввод в формах регистрации, входа и профиля Вебвизор не записывает."""

    def _input(self, html, name):
        match = re.search(r'<input[^>]*name="%s"[^>]*>' % name, html)
        self.assertIsNotNone(match, 'нет поля %s' % name)
        return match.group(0)

    def test_register_and_login_inputs_are_masked(self):
        register = self.client.get(LANDING).content.decode()
        for name in ('username', 'password1', 'password2'):
            self.assertIn('ym-disable-keys', self._input(register, name))
        login = self.client.get('/login/').content.decode()
        for name in ('username', 'password'):
            self.assertIn('ym-disable-keys', self._input(login, name))

    def test_profile_fields_and_card_are_masked(self):
        user = User.objects.create_user('uchenik_prof', password=PASSWORD)
        # Профиль к новому пользователю заводит сигнал — берём его, а не второй.
        form = ProfileForm(instance=UserProfile.objects.get_or_create(user=user)[0])
        for name, field in form.fields.items():
            self.assertIn('ym-disable-keys', field.widget.attrs.get('class', ''), name)
        self.client.force_login(user)
        html = self.client.get('/profile/').content.decode()
        self.assertIn('class="card pf-card pf-card--form ym-hide-content"', html)
        self.assertIn('ym-disable-keys', self._input(html, 'first_name'))


class AccessBoundaryTests(TestCase):
    """Кто видит источники регистраций и где метки НЕ показываются."""

    def setUp(self):
        cache.clear()
        self.url = reverse('admin:problems_signupsource_changelist')
        self.student = User.objects.create_user('uchenik_adm', password=PASSWORD)
        SignupSource.objects.create(user=self.student, signup_kind='student',
                                    utm_source='telegram')

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_non_staff_is_sent_to_login(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_staff_reads_but_cannot_add_or_change(self):
        admin = User.objects.create_superuser('adm_metrika', password=PASSWORD)
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'telegram')
        add = self.client.get(reverse('admin:problems_signupsource_add'))
        self.assertEqual(add.status_code, 403)
        row = SignupSource.objects.get(user=self.student)
        change = self.client.post(reverse('admin:problems_signupsource_change', args=[row.pk]),
                                  {'utm_source': 'podmena'})
        self.assertEqual(change.status_code, 403)
        row.refresh_from_db()
        self.assertEqual(row.utm_source, 'telegram')

    def test_utm_values_never_reach_site_pages(self):
        marker = 'utm7marker'
        landing = self.client.get(_landing(utm_source=marker, utm_campaign=marker))
        self.assertNotIn(marker, landing.content.decode())
        response = _register(self.client, 'uchenik_marker')
        page = self.client.get(response['Location'])
        self.assertNotIn(marker, page.content.decode())
        self.assertEqual(SignupSource.objects.get(user__username='uchenik_marker').utm_source,
                         marker)
