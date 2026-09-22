"""Стена регистрации: пройти вариант можно только вошедшему (решение 22.09.2026).

Проверка серверная — окно на интро лишь объясняет. Поэтому тесты бьют по `start`
напрямую, а не по разметке окна; разметка проверяется отдельно, как обещание, а
не как защита.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from vp.models import VPAttempt
from vp.tests.helpers import make_published

User = get_user_model()


class StartRequiresLoginTests(TestCase):
    """Кто может завести попытку, а кого разворачивает на регистрацию."""

    @classmethod
    def setUpTestData(cls):
        cls.variant = make_published('gate-v')

    def test_01_guest_is_sent_to_register_and_no_attempt_appears(self):
        """Инвариант: попыток было 0, стало 0. Гостю не заводится ничего."""
        before = VPAttempt.objects.count()
        response = Client().post(reverse('vp:start', args=['gate-v']), {'with_timer': '1'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/register/?next=%2Fvp%2Fgate-v%2F')
        self.assertEqual(VPAttempt.objects.count(), before)
        self.assertEqual(before, 0)

    def test_02_guest_gets_no_session_record_either(self):
        """Ни попытки, ни кода в сессии: возвращаться гостю не к чему."""
        client = Client()
        client.post(reverse('vp:start', args=['gate-v']), {'with_timer': '1'})
        self.assertNotIn('vp_attempts', client.session)

    def test_03_logged_in_person_starts_as_before(self):
        client = Client()
        client.force_login(User.objects.create_user('gate_ok', password='p12345'))
        response = client.post(reverse('vp:start', args=['gate-v']), {'with_timer': '1'})
        attempt = VPAttempt.objects.get()
        self.assertRedirects(response, reverse('vp:take', args=[attempt.public_code]),
                             fetch_redirect_response=False)
        self.assertEqual(attempt.user.username, 'gate_ok')

    def test_04_the_wall_stands_before_the_variant_is_even_looked_up(self):
        """Несуществующий вариант гостю тоже даёт регистрацию, а не 404.

        Так стена не превращается в способ узнать, какие слаги существуют.
        """
        response = Client().post(reverse('vp:start', args=['net-takogo']), {'with_timer': '1'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/register/', response['Location'])


class IntroGateMarkupTests(TestCase):
    """Окно на интро: гостю есть, вошедшему нет."""

    @classmethod
    def setUpTestData(cls):
        cls.variant = make_published('gate-m')

    def test_01_guest_sees_the_dialog_with_both_links(self):
        html = Client().get(reverse('vp:intro', args=['gate-m'])).content.decode()
        self.assertIn('<dialog class="vp-gate" id="vp-gate"', html)
        self.assertIn('/register/?next=%2Fvp%2Fgate-m%2F', html)
        self.assertIn('/login/?next=%2Fvp%2Fgate-m%2F', html)
        self.assertIn('Сначала короткая регистрация', html)
        self.assertIn('Пройти вариант можно только после короткой бесплатной регистрации.', html)

    def test_02_logged_in_person_sees_no_dialog(self):
        client = Client()
        client.force_login(User.objects.create_user('gate_in', password='p12345'))
        html = client.get(reverse('vp:intro', args=['gate-m'])).content.decode()
        self.assertNotIn('id="vp-gate"', html)
        self.assertNotIn('/register/?next=', html)

    def test_03_no_page_promises_that_registration_is_not_needed(self):
        """Обещание «Регистрация не нужна» снято со всех экранов раздела."""
        for url in (reverse('vp:index'), reverse('vp:intro', args=['gate-m'])):
            with self.subTest(url):
                self.assertNotContains(Client().get(url), 'Регистрация не нужна')


class RegisterNextTests(TestCase):
    """`/register/` умеет `next`, но только свой адрес."""

    PASSWORD = 'Zx9-kQ7-vB2-mLp-41'

    def _register(self, client, username, **extra):
        return client.post(reverse('register'), {
            'username': username, 'password1': self.PASSWORD, 'password2': self.PASSWORD,
            'role': 'student', 'consent': 'on', **extra})

    def test_01_get_with_next_puts_a_hidden_field_on_the_form(self):
        response = Client().get(reverse('register'), {'next': '/vp/demo/'})
        self.assertContains(response, '<input type="hidden" name="next" value="/vp/demo/">')

    def test_02_registration_returns_to_the_variant(self):
        response = self._register(Client(), 'next_ok', next='/vp/demo/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/vp/demo/')

    def test_03_a_foreign_address_is_ignored(self):
        """Открытый перенаправитель: чужой хост молча заменяется профилем."""
        response = self._register(Client(), 'next_evil', next='https://evil.example/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/profile/?welcome=1')

    def test_04_without_next_nothing_changes(self):
        response = self._register(Client(), 'next_none')
        self.assertEqual(response['Location'], '/profile/?welcome=1')

    def test_05_no_hidden_field_when_next_is_foreign(self):
        """Небезопасный адрес не доезжает даже до разметки формы."""
        response = Client().get(reverse('register'), {'next': 'https://evil.example/'})
        self.assertNotContains(response, 'name="next"')

    def test_06_the_whole_way_from_the_wall_to_the_variant(self):
        """Сквозной путь: гость нажал «Начать», зарегистрировался, вернулся и стартовал."""
        variant = make_published('gate-way')
        client = Client()
        wall = client.post(reverse('vp:start', args=['gate-way']), {'with_timer': '1'})
        back = wall['Location']
        self.assertEqual(back, '/register/?next=%2Fvp%2Fgate-way%2F')

        done = self._register(client, 'gate_way', next=reverse('vp:intro', args=['gate-way']))
        self.assertEqual(done['Location'], '/vp/gate-way/')

        started = client.post(reverse('vp:start', args=['gate-way']), {'with_timer': '1'})
        attempt = VPAttempt.objects.get(variant=variant)
        self.assertRedirects(started, reverse('vp:take', args=[attempt.public_code]),
                             fetch_redirect_response=False)
        self.assertEqual(attempt.user.username, 'gate_way')
        self.assertTrue(attempt.is_ranked)
