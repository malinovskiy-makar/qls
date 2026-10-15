# -*- coding: utf-8 -*-
"""Часть Б, фаза 1: окно cookie, Метрика по согласию, Вебвизор только гостям.

Что держат эти тесты.

* Без куки `weco_consent` и при `necessary` в HTML публичных страниц нет НИ ОДНОГО
  вхождения `mc.yandex.ru` при заданном номере счётчика (скрипт и noscript-картинка).
* При `all` счётчик есть; Вебвизор включён только у гостя, у вошедшего выключен.
* Кука `weco_src` ставится только при `all`; до согласия метки живут в сессии и
  доезжают до `SignupSource` при регистрации; при `necessary` старую куку стирает сервер.
* Окно cookie стоит во всех корневых шаблонах, в которых есть Метрика (инвариант).
* `/legal/metrika.js` – код для подгрузки после «Разрешить» – без согласия пуст.
"""
import re
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from problems import signup_source
from problems.models_platform import SignupSource
from problems.tests.factories import make_problem, make_topic, make_user

METRIKA_ID = '12345678'
HOST = 'mc.yandex.ru'
CONSENT = 'weco_consent'
PASSWORD = 'Kx7-veter-bereg-19'


@override_settings(YANDEX_METRIKA_ID=METRIKA_ID)
class CounterFollowsConsentTests(TestCase):
    """Номер счётчика задан; всё решает кука выбора."""

    def setUp(self):
        cache.clear()
        topic = make_topic('Олигополия и теория игр', is_canonical=True)
        self.problem = make_problem('Две фирмы выбирают выпуск.', title='Штакельберг',
                                    topic=topic, answer='q1 = 30')

    def _pages(self):
        return {
            'главная': '/',
            'каталог': '/catalog/',
            'страница задачи': reverse('catalog:problem_detail', args=[self.problem.pk]),
            'вход': reverse('login'),
            'регистрация': reverse('register'),
        }

    def test_guest_without_the_cookie_gets_no_yandex_anywhere(self):
        for name, url in self._pages().items():
            with self.subTest(page=name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode('utf-8')
                self.assertEqual(html.count(HOST), 0)
                self.assertNotIn('yastatic', html)
                self.assertNotIn('ym(%s' % METRIKA_ID, html)

    def test_necessary_only_gets_no_yandex_anywhere(self):
        self.client.cookies[CONSENT] = 'necessary'
        for name, url in self._pages().items():
            with self.subTest(page=name):
                html = self.client.get(url).content.decode('utf-8')
                self.assertEqual(html.count(HOST), 0)

    def test_garbage_in_the_cookie_is_no_consent(self):
        for value in ('yes', 'ALL', 'all ', '1', ''):
            with self.subTest(value=value):
                self.client.cookies[CONSENT] = value
                html = self.client.get('/catalog/').content.decode('utf-8')
                self.assertEqual(html.count(HOST), 0)

    def test_all_gives_the_counter_with_webvisor_to_a_guest(self):
        self.client.cookies[CONSENT] = 'all'
        for name, url in self._pages().items():
            with self.subTest(page=name):
                html = self.client.get(url).content.decode('utf-8')
                self.assertIn('https://%s/metrika/tag.js' % HOST, html)
                self.assertIn('https://%s/watch/%s' % (HOST, METRIKA_ID), html)
                init = re.search(r'ym\(%s, "init", \{[^}]*\}\);' % METRIKA_ID, html).group(0)
                self.assertIn('webvisor: true', init)

    def test_all_gives_the_counter_without_webvisor_to_a_logged_in_user(self):
        self.client.force_login(make_user('vv_student'))
        self.client.cookies[CONSENT] = 'all'
        for url in ('/catalog/', self._pages()['страница задачи'], '/game/', '/calc2/'):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode('utf-8')
                init = re.search(r'ym\(%s, "init", \{[^}]*\}\);' % METRIKA_ID, html).group(0)
                self.assertIn('webvisor: false', init)
                self.assertNotIn('webvisor: true', init)

    def test_cabinets_keep_their_own_rules(self):
        self.client.force_login(make_user('vv_cabinet'))
        self.client.cookies[CONSENT] = 'all'
        html = self.client.get('/profile/').content.decode('utf-8')
        init = re.search(r'ym\(%s, "init", \{[^}]*\}\);' % METRIKA_ID, html).group(0)
        self.assertIn('webvisor: false, sendTitle: false', init)

    def test_pending_goal_is_dropped_without_consent_and_sent_with_it(self):
        def register_and_land(username, consent=None):
            self.client = self.client_class()
            if consent:
                self.client.cookies[CONSENT] = consent
            response = self.client.post(reverse('register'), {
                'username': username, 'password1': PASSWORD, 'password2': PASSWORD,
                'role': 'student', 'consent': 'on'})
            self.assertEqual(response.status_code, 302)
            return self.client.get(response['Location']).content.decode('utf-8')

        without = register_and_land('goal_no')
        self.assertNotIn('reachGoalOnce', without)
        # Цель не осталась в сессии: следующая страница после согласия её не выстрелит.
        self.client.cookies[CONSENT] = 'all'
        self.assertNotIn("reachGoalOnce('signup_student'",
                         self.client.get('/catalog/').content.decode('utf-8'))
        with_consent = register_and_land('goal_yes', consent='all')
        self.assertIn("weco.reachGoalOnce('signup_student', '", with_consent)


@override_settings(YANDEX_METRIKA_ID=METRIKA_ID)
class BootScriptTests(TestCase):
    """`/legal/metrika.js`: код счётчика для подгрузки после «Разрешить»."""

    def test_empty_without_consent(self):
        for value in (None, 'necessary'):
            with self.subTest(value=value):
                if value:
                    self.client.cookies[CONSENT] = value
                response = self.client.get('/legal/metrika.js')
                self.assertEqual(response.status_code, 200)
                self.assertIn('javascript', response['Content-Type'])
                self.assertNotIn(HOST, response.content.decode('utf-8'))

    def test_code_with_consent_for_a_guest(self):
        self.client.cookies[CONSENT] = 'all'
        text = self.client.get('/legal/metrika.js').content.decode('utf-8')
        self.assertIn('https://%s/metrika/tag.js' % HOST, text)
        self.assertIn('webvisor: true', text)
        self.assertNotIn('<script', text)

    def test_logged_in_user_gets_no_webvisor(self):
        self.client.force_login(make_user('boot_user'))
        self.client.cookies[CONSENT] = 'all'
        text = self.client.get('/legal/metrika.js').content.decode('utf-8')
        self.assertIn('webvisor: false', text)
        self.assertNotIn('webvisor: true', text)

    def test_cabinet_flag_travels_in_the_query(self):
        self.client.cookies[CONSENT] = 'all'
        text = self.client.get('/legal/metrika.js?private=1').content.decode('utf-8')
        self.assertIn('webvisor: false, sendTitle: false', text)

    def test_not_cached(self):
        self.client.cookies[CONSENT] = 'all'
        self.assertIn('no-store', self.client.get('/legal/metrika.js')['Cache-Control'])

    @override_settings(YANDEX_METRIKA_ID='')
    def test_nothing_without_a_counter_number(self):
        self.client.cookies[CONSENT] = 'all'
        self.assertNotIn(HOST, self.client.get('/legal/metrika.js').content.decode('utf-8'))


class FirstTouchFollowsConsentTests(TestCase):
    """`weco_src` – аналитическая кука: только при `all`; до этого метки в сессии."""

    def setUp(self):
        cache.clear()

    def _landing(self, **extra):
        return self.client.get('/register/?utm_source=telegram&utm_campaign=oct', **extra)

    def test_no_choice_sets_no_cookie_but_keeps_the_touch_in_the_session(self):
        response = self._landing()
        self.assertNotIn(signup_source.COOKIE_NAME, response.cookies)
        self.assertEqual(self.client.session[signup_source.SESSION_KEY]['utm_source'], 'telegram')

    def test_necessary_sets_no_cookie_either(self):
        self.client.cookies[CONSENT] = 'necessary'
        response = self._landing()
        self.assertNotIn(signup_source.COOKIE_NAME, response.cookies)

    def test_all_sets_the_cookie(self):
        self.client.cookies[CONSENT] = 'all'
        response = self._landing()
        self.assertIn(signup_source.COOKIE_NAME, response.cookies)
        self.assertNotIn(signup_source.SESSION_KEY, self.client.session)

    def test_registration_after_a_tagged_visit_without_consent_still_records_the_touch(self):
        self._landing()
        response = self.client.post(reverse('register'), {
            'username': 'tagged_user', 'password1': PASSWORD, 'password2': PASSWORD,
            'role': 'student', 'consent': 'on'})
        self.assertEqual(response.status_code, 302)
        source = SignupSource.objects.get(user__username='tagged_user')
        self.assertEqual((source.utm_source, source.utm_campaign), ('telegram', 'oct'))
        self.assertEqual(source.landing_path, '/register/')

    def test_consent_given_later_moves_the_touch_from_the_session_into_the_cookie(self):
        self._landing()
        self.client.cookies[CONSENT] = 'all'
        response = self.client.get('/catalog/')
        self.assertIn(signup_source.COOKIE_NAME, response.cookies)
        self.assertNotIn(signup_source.SESSION_KEY, self.client.session)
        touch = signup_source.read_first_touch(self.client.get('/').wsgi_request)
        self.assertEqual(touch['utm_source'], 'telegram')

    def test_withdrawing_consent_erases_the_cookie(self):
        self.client.cookies[CONSENT] = 'all'
        self._landing()
        self.assertIn(signup_source.COOKIE_NAME, self.client.cookies)
        self.client.cookies[CONSENT] = 'necessary'
        response = self.client.get('/catalog/')
        morsel = response.cookies[signup_source.COOKIE_NAME]
        self.assertEqual(morsel['max-age'], 0)
        self.assertEqual(morsel.value, '')

    def test_the_session_touch_is_not_overwritten_by_a_second_link(self):
        self._landing()
        self.client.get('/register/?utm_source=vk')
        self.assertEqual(self.client.session[signup_source.SESSION_KEY]['utm_source'], 'telegram')

    def test_a_visit_without_a_tag_does_not_start_a_session(self):
        self.client.get('/catalog/')
        self.assertNotIn(signup_source.SESSION_KEY, self.client.session)


class CookieBarMarkupTests(TestCase):
    """Окно: текст, кнопки одного веса, ссылка, видимость по куке, футер."""

    TEXT = ('Мы используем файлы cookie. Необходимые нужны для работы сайта. '
            'Аналитические помогают понять, как им пользуются – их можно не разрешать.')

    def _bar(self, html):
        match = re.search(r'<div class="ck-bar" id="cookie-bar"[^>]*>', html)
        self.assertIsNotNone(match, 'окна cookie нет в разметке')
        return match.group(0)

    def test_visible_when_there_is_no_choice(self):
        html = self.client.get('/catalog/').content.decode('utf-8')
        self.assertNotIn(' hidden', self._bar(html))

    def test_hidden_but_present_when_the_choice_is_made(self):
        for value in ('all', 'necessary'):
            with self.subTest(value=value):
                self.client.cookies[CONSENT] = value
                html = self.client.get('/catalog/').content.decode('utf-8')
                self.assertIn(' hidden', self._bar(html))

    def test_text_buttons_and_link(self):
        html = self.client.get('/catalog/').content.decode('utf-8')
        self.assertIn(self.TEXT, html)
        self.assertIn('<a href="/legal/cookies/">Подробнее</a>', html)
        # Две кнопки одного веса: один и тот же класс, без «главной».
        buttons = re.findall(r'<button type="button" class="(ck-btn[^"]*)" data-cookie-choice="(all|necessary)">([^<]+)</button>', html)
        self.assertEqual([(b[1], b[2]) for b in buttons],
                         [('all', 'Разрешить'), ('necessary', 'Только необходимые')])
        self.assertEqual({b[0] for b in buttons}, {'ck-btn'})

    def test_the_bar_never_carries_a_yandex_address_or_a_dash(self):
        text = (Path(settings.BASE_DIR) / 'templates' / '_cookie_bar.html').read_text(encoding='utf-8')
        visible = re.sub(r'\{% comment %\}.*?\{% endcomment %\}', '', text, flags=re.S)
        self.assertNotIn('yandex', visible)
        self.assertNotIn('—', visible)   # длинное тире: правило сайта

    def test_footer_has_the_settings_link(self):
        html = self.client.get('/catalog/').content.decode('utf-8')
        self.assertIn('data-cookie-settings>Настройки cookie</button>', html)

    def test_the_script_is_served_and_wired_to_both_buttons_and_the_footer(self):
        js = (Path(settings.BASE_DIR) / 'static' / 'cookie_bar.js').read_text(encoding='utf-8')
        for needle in ('weco_consent', 'data-cookie-choice', 'data-cookie-settings',
                       '/legal/metrika.js', 'dropMetrikaCookies', 'disableYaCounter'):
            self.assertIn(needle, js)
        # Адрес Яндекса в самом файле не нужен: его отдаёт сервер после согласия.
        self.assertNotIn(HOST, js)


class EveryRootTemplateTests(SimpleTestCase):
    """Инвариант: Метрика подключена в N корневых шаблонах, и в каждом её включение
    зависит от согласия (через общие партиалы) и рядом стоит окно cookie."""

    #: Корневых шаблонов с Метрикой в инвентаризации (раздел 3.1).
    INVENTORY_ROOTS = 12

    def _roots(self):
        base = Path(settings.BASE_DIR)
        paths = list(base.glob('templates/**/*.html')) + list(base.glob('*/templates/**/*.html'))
        out = []
        for p in paths:
            rel = p.relative_to(base)
            if rel.parts[0].startswith(('venv', 'node_modules')):
                continue
            text = p.read_text(encoding='utf-8')
            if re.search(r'<!doctype html', text, re.I):
                out.append((rel.as_posix(), text))
        return sorted(out)

    def test_every_counter_root_has_the_bar_and_the_gate(self):
        roots = self._roots()
        with_counter = [r for r, t in roots if "{% include '_metrika.html'" in t]
        with_bar = [r for r, t in roots if "{% include '_cookie_bar.html'" in t]
        self.assertEqual(with_counter, with_bar)
        # 12 из инвентаризации + экран согласия, добавленный частью А.
        self.assertEqual(len(with_counter), self.INVENTORY_ROOTS + 1)
        base = Path(settings.BASE_DIR) / 'templates'
        gate_script = (base / '_metrika.html').read_text(encoding='utf-8')
        gate_noscript = (base / '_metrika_noscript.html').read_text(encoding='utf-8')
        self.assertIn('{% if analytics_allowed %}<script>', gate_script)
        self.assertIn('{% if metrika_id and analytics_allowed %}<noscript>', gate_noscript)
        # Сам адрес Яндекса – только в общем коде и картинке, обе части за воротами.
        self.assertNotIn('mc.yandex.ru', re.sub(r'\{% comment %\}.*?\{% endcomment %\}', '', gate_script, flags=re.S))

    def test_cabinets_pass_the_private_flag_to_the_bar_too(self):
        for rel, text in self._roots():
            m_counter = re.search(r"\{% include '_metrika\.html'([^%]*)%\}", text)
            m_bar = re.search(r"\{% include '_cookie_bar\.html'([^%]*)%\}", text)
            if m_counter:
                self.assertEqual('metrika_private=True' in m_counter.group(1),
                                 'metrika_private=True' in m_bar.group(1), rel)
