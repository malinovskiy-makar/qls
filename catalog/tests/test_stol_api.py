"""Серверные ответы каталога «Стол» (часть B ночи 18.09.2026).

Прогресс ученика по задаче (ADR 0119): открытие, «Как прошло?», следы
помощи, статус теста; ленты «Похожие» и «Мои»; живые числа карты.
Шлюз качества — в каждом новом ответе.
"""
import json

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from problems.models import ProblemPart
from problems.models_platform import ProblemProgress
from problems.tests.factories import make_problem, make_user


def _parts(problem, labels):
    for i, label in enumerate(labels):
        ProblemPart.objects.create(problem=problem, label=label,
                                   statement='Вариант %s' % label, order=i)


class ProgressTests(TestCase):

    def setUp(self):
        cache.clear()
        self.problem = make_problem('Монополист выбирает выпуск.', solution='Решение длиной больше тридцати знаков.')
        self.user = make_user('stol_student')
        self.client.force_login(self.user)

    def _post(self, problem=None, **data):
        url = reverse('catalog:api_progress', args=[(problem or self.problem).pk])
        return self.client.post(url, json.dumps(data), content_type='application/json')

    def _row(self):
        return ProblemProgress.objects.get(user=self.user, problem=self.problem)

    def test_opening_the_problem_creates_opened(self):
        self.client.get(reverse('catalog:problem_detail', args=[self.problem.pk]))
        self.assertEqual(self._row().status, 'opened')

    def test_guest_opening_creates_nothing(self):
        self.client.logout()
        self.client.get(reverse('catalog:problem_detail', args=[self.problem.pk]))
        self.assertFalse(ProblemProgress.objects.exists())

    def test_guest_gets_401_json(self):
        self.client.logout()
        response = self._post(status='self')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error'], 'login')

    def test_mark_and_unmark(self):
        self.assertEqual(self._post(status='hint').json()['status'], 'solved_hint')
        self.assertEqual(self._post(status=None).json()['status'], 'opened')

    def test_solved_self_after_viewing_the_solution_is_refused(self):
        self._post(solution_viewed=True)
        response = self._post(status='self')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._row().status, 'opened')

    def test_hints_only_grow(self):
        self._post(hints_opened=3)
        self._post(hints_opened=1)
        self.assertEqual(self._row().hints_opened, 3)

    def test_opened_hint_is_remembered(self):
        from problems.models import Hint
        for i in range(2):
            Hint.objects.create(problem=self.problem, text='Подсказка %d' % i, order=i)
        self.client.get(reverse('catalog:api_hint', args=[self.problem.pk, 2]))
        self.assertEqual(self._row().hints_opened, 2)

    def test_flagged_problem_is_404(self):
        hidden = make_problem('Скрытая.', flagged=True)
        self.assertEqual(self._post(problem=hidden, status='self').status_code, 404)

    def test_unknown_status_is_refused(self):
        self.assertEqual(self._post(status='genius').status_code, 400)


class TestProgressTests(TestCase):
    """Тест ставит статус сам (решение владельца 17.09: тест без потока)."""

    def setUp(self):
        cache.clear()
        self.problem = make_problem('Выберите верные.', problem_type='тест: все верные',
                                    answer='аб')
        _parts(self.problem, 'абв')
        self.user = make_user('stol_tester')
        self.client.force_login(self.user)

    def _check(self, labels):
        return self.client.post(reverse('catalog:api_test_check', args=[self.problem.pk]),
                                json.dumps({'labels': labels}), content_type='application/json')

    def _status(self):
        return ProblemProgress.objects.get(user=self.user, problem=self.problem).status

    def test_first_try_is_solved_self(self):
        self._check(['а', 'б'])
        self.assertEqual(self._status(), 'solved_self')

    def test_second_try_is_solved_with_hint(self):
        self._check(['в'])
        self._check(['а', 'б'])
        self.assertEqual(self._status(), 'solved_hint')

    def test_reveal_is_failed(self):
        self.client.post(reverse('catalog:api_test_reveal', args=[self.problem.pk]))
        self.assertEqual(self._status(), 'failed')


class StatusesForPageTests(TestCase):

    def test_one_query_for_a_page_of_rows(self):
        from catalog import progress
        user = make_user('stol_rows')
        problems = [make_problem('Задача %d.' % i) for i in range(5)]
        for p in problems[:2]:
            ProblemProgress.objects.create(user=user, problem=p, status='failed')
        with self.assertNumQueries(1):
            statuses = progress.statuses_for(user, [p.pk for p in problems])
        self.assertEqual(statuses, {problems[0].pk: 'failed', problems[1].pk: 'failed'})

    def test_guest_gets_no_statuses(self):
        from django.contrib.auth.models import AnonymousUser

        from catalog import progress
        self.assertEqual(progress.statuses_for(AnonymousUser(), [1, 2]), {})

