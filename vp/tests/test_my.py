"""«Мои попытки» `/vp/my/` и блок попыток на интро (сессия 5).

⚠️ Числа в чипах должны совпадать с числом строк по тому же фильтру: расхождение
здесь значит, что фильтр и счётчик считают разное.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from vp.models import VPAttempt
from vp.tests.helpers import make_published

User = get_user_model()


def rows(html):
    """Строки списка попыток без строки-шапки."""
    return [chunk for chunk in html.split('<div class="vp-arow')[1:]
            if not chunk.startswith(' is-head')]


class AccessTests(TestCase):
    def test_guest_is_sent_to_login_with_a_way_back(self):
        response = Client().get(reverse('vp:my'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])
        self.assertIn('next=/vp/my/', response['Location'])

    def test_empty_list_is_honest(self):
        client = Client()
        client.force_login(User.objects.create_user('my_empty', password='p12345'))
        html = client.get(reverse('vp:my')).content.decode()
        self.assertIn('Здесь пока пусто', html)
        self.assertIn('Все · 0', html)


class MyAttemptsTests(TestCase):
    """Шесть попыток: 2 зачётные, 3 тренировки, 1 несданная."""

    def setUp(self):
        self.first = make_published('my-a')
        self.second = make_published('my-b')
        self.third = make_published('my-c')
        self.user = User.objects.create_user('my_owner', password='p12345')
        self.client = Client()
        self.client.force_login(self.user)

        # Зачётная + повтор по первому варианту.
        self.ranked_a = self._run(self.first, timer=True, finish=True)
        self._run(self.first, timer=True, finish=True)
        # Зачётная по второму + тренировка без таймера.
        self.ranked_b = self._run(self.second, timer=True, finish=True)
        self._run(self.second, timer=False, finish=True)
        # Ещё одна тренировка и одна живая несданная.
        self._run(self.third, timer=False, finish=True)
        self.live = self._run(self.third, timer=True, finish=False)

    def _run(self, variant, *, timer, finish):
        self.client.post(reverse('vp:start', args=[variant.slug]),
                         {'with_timer': '1' if timer else '0'})
        attempt = VPAttempt.objects.filter(variant=variant).order_by('-id').first()
        if finish:
            self.client.post(reverse('vp:finish', args=[attempt.public_code]))
            attempt.refresh_from_db()
        return attempt

    def page(self, **params):
        response = self.client.get(reverse('vp:my'), params)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_01_chip_numbers_match_the_number_of_rows(self):
        """Инвариант: 6 = 2 + 3 + 1, и каждый фильтр отдаёт ровно своё число."""
        html = self.page()
        self.assertIn('Все · 6', html)
        self.assertIn('В таблице · 2', html)
        self.assertIn('Тренировка · 3', html)
        self.assertIn('Не сдана · 1', html)

        self.assertEqual(len(rows(html)), 6)
        for code, count in (('all', 6), ('ranked', 2), ('training', 3), ('open', 1)):
            with self.subTest(code):
                self.assertEqual(len(rows(self.page(f=code))), count)

    def test_02_unknown_filter_falls_back_to_all(self):
        self.assertEqual(len(rows(self.page(f='vydumka'))), 6)

    def test_03_the_live_row_leads_to_the_attempt_and_finished_ones_to_the_result(self):
        live_row = [r for r in rows(self.page(f='open'))][0]
        self.assertIn(reverse('vp:take', args=[self.live.public_code]), live_row)
        self.assertIn('не сдана, идёт', live_row)

        done_row = [r for r in rows(self.page(f='ranked'))][0]
        self.assertIn('/vp/r/', done_row)
        self.assertIn('в таблице', done_row)

    def test_04_a_repeat_is_marked_as_one(self):
        training = self.page(f='training')
        self.assertIn('тренировка · повтор', training)

    def test_05_an_expired_attempt_is_submitted_when_the_page_opens(self):
        """Просроченную закрывает сам экран: иначе список врал бы про «не сдана»."""
        past = timezone.now() - timedelta(hours=3)
        VPAttempt.objects.filter(pk=self.live.pk).update(
            started_at=past, expires_at=past + timedelta(seconds=1800))

        html = self.page()
        self.live.refresh_from_db()
        self.assertIsNotNone(self.live.submitted_at)
        self.assertTrue(self.live.is_auto_submitted)
        self.assertIn('Не сдана · 0', html)
        # Попытка была ПЕРВОЙ с таймером по своему варианту, то есть зачётной:
        # автосдача этого не меняет, и строка уходит в «В таблице», а не в «Не сдана».
        self.assertIn('В таблице · 3', html)
        self.assertIn('Тренировка · 3', html)
        self.assertEqual(len(rows(self.page(f='open'))), 0)

    def test_06_only_the_best_ranked_attempt_carries_a_place(self):
        """Строка на человека в таблице одна, значит и место в списке ровно одно."""
        attempt_rows = rows(self.page(f='ranked'))
        self.assertEqual(len(attempt_rows), 2)
        self.assertEqual(sum('-е' in row for row in attempt_rows), 1)

    def test_07_another_persons_attempts_are_not_here(self):
        other = Client()
        other.force_login(User.objects.create_user('my_other', password='p12345'))
        self.assertEqual(len(rows(other.get(reverse('vp:my')).content.decode())), 0)


class IntroAttemptsBlockTests(TestCase):
    def setUp(self):
        self.variant = make_published('my-intro')
        self.user = User.objects.create_user('intro_owner', password='p12345')
        self.client = Client()
        self.client.force_login(self.user)

    def intro(self, client=None):
        return (client or self.client).get(
            reverse('vp:intro', args=[self.variant.slug])).content.decode()

    def _finish(self, timer=True):
        self.client.post(reverse('vp:start', args=[self.variant.slug]),
                         {'with_timer': '1' if timer else '0'})
        attempt = VPAttempt.objects.order_by('-id').first()
        self.client.post(reverse('vp:finish', args=[attempt.public_code]))
        return attempt

    def test_01_no_attempts_no_block(self):
        self.assertNotIn('Ваши попытки по этому варианту', self.intro())

    def test_02_the_block_appears_after_the_first_attempt(self):
        self._finish()
        html = self.intro()
        self.assertIn('Ваши попытки по этому варианту', html)
        self.assertIn(reverse('vp:my'), html)

    def test_03_a_guest_never_sees_the_block(self):
        self._finish()
        self.assertNotIn('Ваши попытки по этому варианту', self.intro(Client()))

    def test_04_the_timer_caption_changes_once_a_ranked_attempt_exists(self):
        self.assertIn('Первая попытка идёт в таблицу лучших попыток.', self.intro())
        self._finish()
        html = self.intro()
        self.assertIn('Первая попытка по варианту уже в таблице; эта будет тренировкой.', html)
        self.assertNotIn('Первая попытка идёт в таблицу лучших попыток.', html)

    def test_05_an_untimed_attempt_does_not_change_the_caption(self):
        self._finish(timer=False)
        self.assertIn('Первая попытка идёт в таблицу лучших попыток.', self.intro())

    def test_06_all_variants_link_is_on_the_intro(self):
        self.assertIn(reverse('vp:variants'), self.intro())
