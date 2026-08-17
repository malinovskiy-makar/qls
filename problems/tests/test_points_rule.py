# -*- coding: utf-8 -*-
"""
Балл позиции: то, что видно на экране, то и записывается (ревью 17.08, ф. 1).

Дефект, ради которого написан файл: конструктор показывал балл по сложности
задачи (тест = 1), а создание работы ставило прежнее значение по умолчанию
(тест = 3). Работа из двух тестов уходила ученику на шесть баллов вместо
двух, и увидеть это можно было только открыв созданную работу.

Правило начисления теперь живёт на шаге «Выдача» и применяется СЕРВЕРОМ —
и при показе состава, и при записи работы. Старшинство одно на весь поток:
ручная правка репетитора → правило → прежнее значение по умолчанию.
"""
import json
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from problems.models import (
    Assignment, AssignmentItem, CustomProblem, Problem, StudentGroup, User,
)
from teacher import picker


class PointsRuleBase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('pr-tutor', password='x',
                                             role='teacher')
        cls.student = User.objects.create_user('pr-student', password='x',
                                               role='student')
        cls.group = StudentGroup.objects.create(name='Группа',
                                                teacher=cls.tutor)
        cls.group.students.add(cls.student)

        cls.test_a = Problem.objects.create(
            title='Тест А', statement='Спрос растёт.', difficulty=2,
            status=Problem.Status.PUBLISHED, problem_type='тест: один ответ')
        cls.test_b = Problem.objects.create(
            title='Тест Б', statement='Предложение падает.', difficulty=4,
            status=Problem.Status.PUBLISHED, problem_type='тест: один ответ')
        cls.easy = Problem.objects.create(
            title='Задача на 3', statement='Условие.', difficulty=3,
            status=Problem.Status.PUBLISHED, problem_type='задача')
        cls.hard = Problem.objects.create(
            title='Задача на 5', statement='Условие.', difficulty=5,
            status=Problem.Status.PUBLISHED, problem_type='задача')
        cls.own = CustomProblem.objects.create(
            owner=cls.tutor, title='Своя', statement='Условие', difficulty=2)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def create_work(self, keys, points='', rule=None, name='Работа'):
        """Создать работу так, как это делает шаг «Выдача»."""
        data = {'name': name, 'groups': [str(self.group.pk)],
                'problem_ids': ','.join(keys), 'problem_points': points}
        if rule is not None:
            data['points_rule'] = rule
        response = self.client.post(reverse('teacher:assignment_create'), data)
        self.assertIn(response.status_code, (302, 200))
        work = Assignment.objects.filter(name=name).first()
        self.assertIsNotNone(work, 'работа не создана')
        return work

    def scores(self, work):
        """Баллы позиций в порядке номеров задач — {ключ: балл}."""
        out = {}
        for item in work.items.all():
            key = ('c%d' % item.custom_problem_id if item.custom_problem_id
                   else str(item.catalog_problem_id))
            out[key] = item.points
        return out


class RuleParsingTests(TestCase):
    """Разбор правила: мусор не имеет права стать ценой позиции."""

    def test_empty_means_by_difficulty(self):
        self.assertEqual(picker.parse_rule(''), {'mode': 'difficulty'})
        self.assertEqual(picker.parse_rule(None), {'mode': 'difficulty'})

    def test_flat_carries_its_number(self):
        self.assertEqual(picker.parse_rule('flat:2'),
                         {'mode': 'flat', 'value': Decimal('2')})

    def test_comma_is_a_decimal_point(self):
        self.assertEqual(picker.parse_rule('flat:1,5')['value'],
                         Decimal('1.5'))

    def test_junk_falls_back_to_difficulty(self):
        for raw in ('flat:абв', 'flat:-3', 'flat:99999', 'что-то', 'flat:'):
            self.assertEqual(picker.parse_rule(raw)['mode'], 'difficulty',
                             'мусор «%s» стал правилом' % raw)

    def test_rule_points_follow_the_mode(self):
        by_diff = {'mode': 'difficulty'}
        self.assertEqual(picker.rule_points(by_diff, True, 4), Decimal('1'))
        self.assertEqual(picker.rule_points(by_diff, False, 4), Decimal('4'))
        flat = {'mode': 'flat', 'value': Decimal('2')}
        self.assertEqual(picker.rule_points(flat, True, 4), Decimal('2'))
        self.assertEqual(picker.rule_points(flat, False, 1), Decimal('2'))


class ScoreReachesTheWorkTests(PointsRuleBase):
    """Главная проверка фазы: экран и запись работы говорят одно и то же."""

    def test_two_tests_cost_two_points_not_six(self):
        """Тот самый дефект: два теста уезжали на 6 баллов вместо 2."""
        work = self.create_work([str(self.test_a.pk), str(self.test_b.pk)],
                                rule='difficulty')
        scores = self.scores(work)
        self.assertEqual(scores[str(self.test_a.pk)], Decimal('1'))
        self.assertEqual(scores[str(self.test_b.pk)], Decimal('1'))
        self.assertEqual(sum(scores.values()), Decimal('2'))

    def test_difficulty_rule_prices_open_problems(self):
        work = self.create_work([str(self.easy.pk), str(self.hard.pk)],
                                rule='difficulty')
        scores = self.scores(work)
        self.assertEqual(scores[str(self.easy.pk)], Decimal('3'))
        self.assertEqual(scores[str(self.hard.pk)], Decimal('5'))
        self.assertEqual(sum(scores.values()), Decimal('8'))

    def test_hand_written_score_wins_over_the_rule(self):
        """Сценарий приёмки: 3 и 5, второй руками 7 → в работе 3 и 7."""
        work = self.create_work(
            [str(self.easy.pk), str(self.hard.pk)],
            points='%d:7' % self.hard.pk, rule='difficulty')
        scores = self.scores(work)
        self.assertEqual(scores[str(self.easy.pk)], Decimal('3'))
        self.assertEqual(scores[str(self.hard.pk)], Decimal('7'))
        self.assertEqual(sum(scores.values()), Decimal('10'))

    def test_flat_rule_spares_the_hand_written_one(self):
        """То же, но правило «одинаково по 2»: 2 и 7, всего 9."""
        work = self.create_work(
            [str(self.easy.pk), str(self.hard.pk)],
            points='%d:7' % self.hard.pk, rule='flat:2')
        scores = self.scores(work)
        self.assertEqual(scores[str(self.easy.pk)], Decimal('2'))
        self.assertEqual(scores[str(self.hard.pk)], Decimal('7'))
        self.assertEqual(sum(scores.values()), Decimal('9'))

    def test_own_problem_obeys_the_rule_too(self):
        work = self.create_work(['c%d' % self.own.pk], rule='flat:4')
        self.assertEqual(self.scores(work)['c%d' % self.own.pk], Decimal('4'))

    def test_exam_uses_the_same_rule(self):
        """Тест в контрольной стоит столько же, сколько в домашке."""
        import datetime

        from django.utils import timezone

        later = (timezone.localtime(timezone.now())
                 + datetime.timedelta(days=3)).strftime('%Y-%m-%dT%H:%M')
        response = self.client.post(
            reverse('teacher:exam_create', args=[self.group.pk]),
            {'name': 'Контрольная', 'kind': 'limit', 'duration': '60',
             'deadline': later, 'show_results': 'on',
             'problem_ids': str(self.test_a.pk), 'problem_points': '',
             'points_rule': 'difficulty'})
        self.assertIn(response.status_code, (302, 200))
        exam = Assignment.objects.filter(name='Контрольная').first()
        self.assertIsNotNone(exam)
        self.assertEqual(exam.items.first().points, Decimal('1'))

    def test_without_a_rule_old_default_stays(self):
        """⚠️ Прежние экраны правила не шлют — их работы не переоцениваются."""
        work = self.create_work([str(self.test_a.pk)], name='Без правила')
        self.assertEqual(self.scores(work)[str(self.test_a.pk)],
                         Decimal('3'))


class ComposeShowsWhatWillBeWrittenTests(PointsRuleBase):
    """Состав и записанная работа обязаны сойтись до балла."""

    def rows(self, keys, points='', rule='difficulty'):
        response = self.client.post(reverse('teacher:api_cart_rows'), {
            'keys': ','.join(keys), 'points': points, 'suggest': '1',
            'rule': rule})
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)['rows']

    def test_screen_and_record_agree(self):
        keys = [str(self.test_a.pk), str(self.hard.pk)]
        shown = {row['key']: row['points'] for row in self.rows(keys)}
        work = self.create_work(keys, rule='difficulty')
        written = {key: float(value)
                   for key, value in self.scores(work).items()}
        self.assertEqual(shown, written)

    def test_flat_rule_changes_the_screen(self):
        keys = [str(self.test_a.pk), str(self.hard.pk)]
        shown = {row['key']: row['points']
                 for row in self.rows(keys, rule='flat:2')}
        self.assertEqual(shown, {str(self.test_a.pk): 2.0,
                                 str(self.hard.pk): 2.0})

    def test_manual_mark_is_set_by_the_server(self):
        """Пометка «вручную» ставится по факту правки, а не по совпадению."""
        keys = [str(self.easy.pk), str(self.hard.pk)]
        # Балл задачи «на 3» правлен руками и совпал с подсказкой правила.
        rows = self.rows(keys, points='%d:3' % self.easy.pk)
        marks = {row['key']: row['manual'] for row in rows}
        self.assertTrue(marks[str(self.easy.pk)],
                        'правленое руками не помечено')
        self.assertFalse(marks[str(self.hard.pk)],
                         'нетронутое помечено как ручное')

    def test_tally_counts_by_the_same_rule(self):
        """Полоса собранного считает тем же правилом, что и состав."""
        keys = [str(self.test_a.pk), str(self.test_b.pk)]
        response = self.client.get(reverse('teacher:api_work_tally'), {
            'keys': ','.join(keys), 'points': '', 'rule': 'difficulty'})
        self.assertEqual(json.loads(response.content)['points'], 2.0)
        response = self.client.get(reverse('teacher:api_work_tally'), {
            'keys': ','.join(keys), 'points': '', 'rule': 'flat:3'})
        self.assertEqual(json.loads(response.content)['points'], 6.0)


class StorageNamesTests(TestCase):
    """Имена хранилищ собирает сервер — включая новые два."""

    def test_points_and_rule_are_tied_to_the_lesson(self):
        keys = picker.storage_keys(7)
        self.assertEqual(keys['points'], 'work_points:7')
        self.assertEqual(keys['rule'], 'work_rule:7')
        other = picker.storage_keys(8)
        self.assertNotEqual(keys['points'], other['points'])
        self.assertNotEqual(keys['rule'], other['rule'])

    def test_client_gets_the_names_from_the_server(self):
        """Имя, написанное в шаблоне руками, — та самая мина с пустым ключом."""
        tutor = User.objects.create_user('pr-keys', password='x',
                                         role='teacher')
        client = Client()
        client.force_login(tutor)
        page = client.get(reverse('teacher:work_give')).content.decode()
        self.assertIn('work_points:0', page)
        self.assertIn('work_rule:0', page)


class GiveScreenHasTheRuleTests(PointsRuleBase):
    """Правило спрашивают на «Выдаче», и оно уходит на сервер полем формы."""

    def test_rule_block_is_on_the_give_step(self):
        page = self.client.get(reverse('teacher:work_give')).content.decode()
        self.assertIn('points_rule_mode', page)
        self.assertIn('по сложности задачи', page)
        self.assertIn('name="points_rule"', page)

    def test_other_screens_do_not_ask_for_the_rule(self):
        """⚠️ Панель настроек общая — правило не имеет права всплыть везде."""
        page = self.client.get(reverse('teacher:work_pick')).content.decode()
        self.assertNotIn('points_rule_mode', page)


class CreateItemsAgreesWithComposeTests(PointsRuleBase):
    """`create_items` и `cart_items` считают одним предикатом «это тест»."""

    def test_both_sides_agree_on_what_is_a_test(self):
        keys = [str(self.test_a.pk), str(self.easy.pk), 'c%d' % self.own.pk]
        rule = {'mode': 'difficulty'}
        items, by_item = picker.cart_items(keys, self.tutor, rule=rule)
        shown = {by_item[id(item)]: item.points for item in items}

        work = Assignment.objects.create(name='Сверка', author=self.tutor,
                                         group=self.group)
        picker.create_items(work, self.tutor, keys,
                            [self.test_a.pk, self.easy.pk], [self.own.pk],
                            rule=rule)
        written = self.scores(work)
        self.assertEqual(shown, written)
        self.assertEqual(AssignmentItem.objects.filter(assignment=work).count(),
                         3)
