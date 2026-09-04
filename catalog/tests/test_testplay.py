"""Фаза 7.2: тест как игра — эндпоинты, попытки в сессии, всё-или-ничего."""
import json

from django.test import TestCase
from django.urls import reverse

from catalog import testplay
from problems.models import CatalogAttempt, ProblemPart
from problems.tests.factories import make_problem, make_topic, make_user


def _parts(problem, labels, answers=None):
    for i, label in enumerate(labels, start=1):
        ProblemPart.objects.create(problem=problem, label=label,
                                   statement='Вариант %s' % label, order=i,
                                   answer=(answers or {}).get(label, ''))


class TestGameModelTests(TestCase):
    def test_multi_choice_from_glued_answer(self):
        p = make_problem('Выберите все верные.', problem_type='тест: все верные', answer='аб')
        _parts(p, 'абвг')
        game = testplay.game_of(p)
        self.assertTrue(game['multi'])
        self.assertEqual(game['correct'], {'а', 'б'})
        self.assertEqual([o['label'] for o in game['options']], ['а', 'б', 'в', 'г'])
        self.assertEqual(game['rule'], 'верных может быть несколько: отметьте все')

    def test_single_choice_and_true_false_are_single(self):
        one = make_problem('Один верный.', problem_type='тест: один ответ', answer='Б)')
        _parts(one, ['а)', 'б)', 'в)'])
        tf = make_problem('Верно ли утверждение?', problem_type='тест: верно/неверно', answer='б')
        ProblemPart.objects.create(problem=tf, label='а', statement='Верно', order=1)
        ProblemPart.objects.create(problem=tf, label='б', statement='Неверно', order=2)
        for problem, correct in ((one, {'б'}), (tf, {'б'})):
            game = testplay.game_of(problem)
            self.assertFalse(game['multi'])
            self.assertEqual(game['correct'], correct)
            self.assertEqual(game['rule'], 'выберите один')

    def test_no_game_without_options_or_with_labels_outside(self):
        numeric = make_problem('Сколько?', problem_type='тест: числовой ответ', answer='42')
        self.assertIsNone(testplay.game_of(numeric))
        outside = make_problem('Все верные.', problem_type='тест: все верные', answer='бд')
        _parts(outside, 'абвг')
        self.assertIsNone(testplay.game_of(outside))
        plain = make_problem('Обычная задача.', answer='5')
        self.assertIsNone(testplay.game_of(plain))
        two_right_single = make_problem('Один.', problem_type='тест: один ответ', answer='а, б')
        _parts(two_right_single, 'абв')
        self.assertIsNone(testplay.game_of(two_right_single))

    def test_marked_parts_win(self):
        p = make_problem('Все верные.', problem_type='тест: все верные', answer='а')
        _parts(p, 'абв', {'в': 'верно'})
        self.assertEqual(testplay.game_of(p)['correct'], {'в'})


class TestCheckApiTests(TestCase):
    def setUp(self):
        self.p = make_problem('Выберите все верные.', problem_type='тест: все верные', answer='аб')
        _parts(self.p, 'абвг')
        self.check_url = reverse('catalog:api_test_check', args=[self.p.pk])
        self.reveal_url = reverse('catalog:api_test_reveal', args=[self.p.pk])

    def _check(self, labels):
        resp = self.client.post(self.check_url, json.dumps({'labels': labels}),
                                content_type='application/json')
        return resp.status_code, json.loads(resp.content)

    def test_correct_set_in_any_order(self):
        self.assertEqual(self._check(['б', 'а']), (200, {'correct': True, 'attempt': 1}))

    def test_partial_and_extra_are_wrong(self):
        self.assertEqual(self._check(['а']), (200, {'correct': False, 'attempt': 1}))
        self.assertEqual(self._check(['а', 'б', 'в'])[1]['correct'], False)

    def test_count_of_correct_comes_from_the_third_attempt(self):
        first = self._check(['а'])[1]
        self.assertNotIn('correct_count', first)
        second = self._check(['в'])[1]
        self.assertEqual(second['attempt'], 2)
        self.assertEqual(second['correct_count'], 2)   # впереди третья попытка
        third = self._check(['г'])[1]
        self.assertEqual((third['attempt'], third['correct_count']), (3, 2))

    def test_success_resets_the_counter_and_is_recorded_for_users(self):
        user = make_user('игрок')
        self.client.force_login(user)
        self._check(['а']); self._check(['в'])
        status, data = self._check(['а', 'б'])
        self.assertEqual(data, {'correct': True, 'attempt': 3})
        attempt = CatalogAttempt.objects.get(user=user, problem=self.p)
        self.assertEqual((attempt.text, attempt.verdict, attempt.steps, attempt.status),
                         ('', 'ok', [], 'checked'))
        self.assertEqual(attempt.summary, 'тест: решено с 3-й попытки')
        # счётчик сброшен: следующая неудача — снова первая попытка
        self.assertEqual(self._check(['г'])[1]['attempt'], 1)

    def test_guest_success_is_not_recorded(self):
        self.assertEqual(self._check(['а', 'б'])[1]['correct'], True)
        self.assertEqual(CatalogAttempt.objects.count(), 0)

    def test_reveal_gives_labels_and_resets(self):
        self._check(['в']); self._check(['г'])
        resp = self.client.post(self.reveal_url)
        self.assertEqual(json.loads(resp.content), {'correct_labels': ['а', 'б']})
        self.assertEqual(self._check(['г'])[1]['attempt'], 1)

    def test_bad_requests(self):
        self.assertEqual(self._check([])[0], 400)
        self.assertEqual(self._check(['я'])[0], 400)
        self.assertEqual(self.client.get(self.check_url).status_code, 405)
        numeric = make_problem('Сколько?', problem_type='тест: числовой ответ', answer='42')
        resp = self.client.post(reverse('catalog:api_test_check', args=[numeric.pk]),
                                json.dumps({'labels': ['а']}), content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        hidden = make_problem('Скрытый тест.', problem_type='тест: все верные', answer='а', flagged=True)
        _parts(hidden, 'аб')
        resp = self.client.post(reverse('catalog:api_test_check', args=[hidden.pk]),
                                json.dumps({'labels': ['а']}), content_type='application/json')
        self.assertEqual(resp.status_code, 404)


class MoreTestsByTopicTests(TestCase):
    def setUp(self):
        self.topic = make_topic('Монополия и ценовая дискриминация')
        self.p = make_problem('Первый тест.', problem_type='тест: один ответ', answer='а', topic=self.topic)
        _parts(self.p, 'аб')

    def test_random_accepts_filters_and_exclude(self):
        other = make_problem('Второй тест.', problem_type='тест: все верные', answer='а', topic=self.topic)
        _parts(other, 'аб')
        make_problem('Открытая задача той же темы.', topic=self.topic)
        url = reverse('catalog:random_problem') + '?type=test&topic=%d&exclude=%d' % (self.topic.pk, self.p.pk)
        for _ in range(5):
            resp = self.client.get(url)
            self.assertRedirects(resp, reverse('catalog:problem_detail', args=[other.pk]),
                                 fetch_redirect_response=False)

    def test_random_without_match_goes_to_the_catalog(self):
        url = reverse('catalog:random_problem') + '?type=test&topic=%d&exclude=%d' % (self.topic.pk, self.p.pk)
        self.assertRedirects(self.client.get(url), reverse('catalog:problem_list'),
                             fetch_redirect_response=False)

    def test_page_context_has_more_url_only_with_another_test(self):
        page = reverse('catalog:problem_detail', args=[self.p.pk])
        self.assertEqual(self.client.get(page).context['test']['more_url'], '')
        other = make_problem('Второй тест.', problem_type='тест: все верные', answer='а', topic=self.topic)
        _parts(other, 'аб')
        more = self.client.get(page).context['test']['more_url']
        self.assertIn('type=test', more)
        self.assertIn('topic=%d' % self.topic.pk, more)
        self.assertIn('exclude=%d' % self.p.pk, more)
