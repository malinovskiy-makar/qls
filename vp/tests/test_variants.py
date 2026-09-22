"""Экран выбора класса и варианта `/vp/variants/` (сессия 5).

⚠️ Числа здесь — из фикстуры: сколько карточек завели, столько и ждём. Статус
считает `landing.variant_status`, тот же, что на посадочной; гостю статуса нет
вовсе, у него истории не бывает.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from catalog.tests.test_no_slop import visible_text
from vp.models import VPAttempt, VPVariant
from vp.tests.helpers import make_published

User = get_user_model()


def page(client, **params):
    response = client.get(reverse('vp:variants'), params)
    assert response.status_code == 200, response.status_code
    return response.content.decode()


def cards(html):
    """Карточки вариантов на экране — по открывающему тегу, не по имени класса."""
    return html.split('<article class="vp-vcard')[1:]


class VariantsScreenTests(TestCase):
    """Девять опубликованных вариантов: четыре у 9–10, пять у 11."""

    @classmethod
    def setUpTestData(cls):
        cls.nine = []
        for n in range(4):
            variant = make_published(f'var-9-{n}')
            VPVariant.objects.filter(pk=variant.pk).update(
                title=f'Вариант 9–10 №{n}', order=n,
                source_kind='demo' if n == 0 else 'author')
            cls.nine.append(variant)
        cls.eleven = []
        for n in range(5):
            variant = make_published(f'var-11-{n}')
            VPVariant.objects.filter(pk=variant.pk).update(
                title=f'Вариант 11 №{n}', grade_band='11', order=n,
                source_kind='demo' if n == 0 else 'author')
            cls.eleven.append(variant)

    def test_01_the_screen_exists_and_is_public(self):
        self.assertEqual(reverse('vp:variants'), '/vp/variants/')
        self.assertEqual(Client().get('/vp/variants/').status_code, 200)

    def test_02_band_switch_shows_only_that_class(self):
        """Инвариант: 4 карточки у 9–10, 5 у 11."""
        self.assertEqual(len(cards(page(Client(), band='9-10'))), 4)
        self.assertEqual(len(cards(page(Client(), band='11'))), 5)

    def test_03_unknown_band_falls_back_to_the_first_one(self):
        self.assertEqual(len(cards(page(Client(), band='sedmoy'))), 4)
        self.assertEqual(len(cards(page(Client()))), 4)

    def test_04_numbering_of_trial_variants_starts_at_one_inside_the_class(self):
        html = page(Client(), band='11')
        self.assertIn('Демоверсия ВШЭ', html)
        for number in (1, 2, 3, 4):
            self.assertIn(f'Пробный · вариант {number}', html)
        self.assertNotIn('Пробный · вариант 5', html)

    def test_05_guest_sees_the_format_and_no_status(self):
        html = page(Client())
        self.assertIn('44 задания · 30 минут', html)
        for absent in ('Не решали', 'в таблице', 'Начат ·', 'Продолжить'):
            self.assertNotIn(absent, html, absent)
        self.assertIn('понадобится короткая бесплатная регистрация', html)

    def test_06_person_with_a_live_attempt_gets_continue_straight_to_the_page(self):
        client = Client()
        client.force_login(User.objects.create_user('var_live', password='p12345'))
        client.post(reverse('vp:start', args=['var-9-1']), {'with_timer': '1'})
        attempt = VPAttempt.objects.get()

        html = page(client, band='9-10')
        self.assertIn('Начат · 0 из 44', html)
        self.assertIn(reverse('vp:take', args=[attempt.public_code]), html)

    def test_07_a_submitted_ranked_attempt_says_it_is_in_the_board(self):
        client = Client()
        client.force_login(User.objects.create_user('var_done', password='p12345'))
        client.post(reverse('vp:start', args=['var-9-1']), {'with_timer': '1'})
        attempt = VPAttempt.objects.get()
        client.post(reverse('vp:finish', args=[attempt.public_code]))

        html = page(client, band='9-10')
        self.assertIn('в таблице', html)
        self.assertIn('Не решали', html)                 # у остальных трёх карточек

    def test_08_draft_is_visible_to_staff_only(self):
        draft = make_published('var-draft')
        VPVariant.objects.filter(pk=draft.pk).update(
            title='Черновик ВП для проверки', is_published=False)
        self.assertNotIn('Черновик ВП для проверки', page(Client()))

        staff = Client()
        staff.force_login(User.objects.create_user('var_staff', password='p12345', is_staff=True))
        html = page(staff, band='9-10')
        self.assertIn('Черновик ВП для проверки', html)
        self.assertIn('Не опубликован', html)

    def test_09_the_route_is_not_eaten_by_a_variant_with_the_same_slug(self):
        """Вариант со слагом «variants» не должен перехватывать экран списка."""
        trap = make_published('variants')
        VPVariant.objects.filter(pk=trap.pk).update(title='Ловушка слага')
        html = page(Client())
        self.assertIn('Выберите класс и вариант', html)
        self.assertNotIn('<h1 class="vp-h1">Ловушка слага</h1>', html)

    def test_10_no_word_zabeg_on_the_screen(self):
        """Слово раздела — «попытка», «забег» остаётся в Wecon Rush.

        Ищем в ВИДИМОМ тексте: в общих включениях страницы (форма обратной связи)
        слово «забег» законно стоит в комментарии разметки, и человек его не читает.
        """
        self.assertNotIn('забег', visible_text(page(Client())).lower())

    def test_11_footer_links_to_the_rules_and_to_my_attempts(self):
        guest = page(Client())
        self.assertIn('/vp/#rules', guest)
        self.assertNotIn(reverse('vp:my'), guest)        # гостю своих попыток нет

        client = Client()
        client.force_login(User.objects.create_user('var_foot', password='p12345'))
        self.assertIn(reverse('vp:my'), page(client))


class EmptyVariantsScreenTests(TestCase):
    def test_no_variants_is_honest_and_does_not_crash(self):
        html = page(Client())
        self.assertIn('Опубликованных вариантов пока нет', html)
