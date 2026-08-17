# -*- coding: utf-8 -*-
"""
Два экрана проверки (фаза 3, мокап mockup-check.html).

  3.1 Список сдач: выделение полосой и словами, статус одной строкой,
      полноценный зазор вокруг «из», не начавший не приглушён;
  3.2 Проверка одной задачи: три уровня вложенности вместо четырёх, кнопки
      балла одним переключателем, число без рамки, шапка из двух сущностей,
      «глазами ученика» среди переходов, у комментария сказано, кто прочтёт;
  3.3 Один словарь выделения на всю платформу: полоса — состояние, заливка —
      выбор, рамки по периметру нет.

⚠️ ФУНКЦИЮ НЕ ТРОГАЕМ: правило трёх пресетов (минимум / половина /
максимум) и переход «глазами ученика» с раскрытой задачей проверены
прежними сессиями и здесь только перечитываются.
"""
import os
import re
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import (
    Assignment, AssignmentItem, Problem, StudentGroup, Submission,
    TeacherFeedback, User,
)
from teacher import views_groups

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


class CheckBase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('lc-tutor', password='x',
                                             role='teacher')
        cls.group = StudentGroup.objects.create(name='Занятие',
                                                teacher=cls.tutor)
        cls.did = User.objects.create_user('lc-did', password='x',
                                           role='student',
                                           first_name='Пётр',
                                           last_name='Иванов')
        cls.idle = User.objects.create_user('lc-idle', password='x',
                                            role='student',
                                            first_name='Сергей',
                                            last_name='Дмитриев')
        cls.group.students.add(cls.did, cls.idle)

        cls.problem = Problem.objects.create(
            title='Эластичность', statement='Условие', difficulty=3,
            status=Problem.Status.PUBLISHED, problem_type='задача')
        cls.work = Assignment.objects.create(name='Домашка №3',
                                             author=cls.tutor,
                                             group=cls.group)
        cls.item = AssignmentItem.objects.create(
            assignment=cls.work, order=0, catalog_problem=cls.problem,
            points=Decimal('2'))
        cls.work.students.set([cls.did, cls.idle])
        cls.sub = Submission.objects.create(
            assignment=cls.work, student=cls.did, problem=cls.problem,
            problem_item=cls.item, status='submitted',
            submitted_answer='30', solution_text='Приравнял спрос',
            submitted_at=timezone.now())

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def list_page(self):
        response = self.client.get(
            reverse('teacher:group_submissions',
                    args=[self.group.pk, self.work.pk]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def review_page(self):
        response = self.client.get(
            reverse('teacher:group_review_submission',
                    args=[self.group.pk, self.sub.pk]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()


# ══════════════════════════════════════════════════════════════════════════
# 3.1 — список сдач
# ══════════════════════════════════════════════════════════════════════════
class SubmissionListTests(CheckBase):

    def test_highlight_is_a_stripe_not_a_frame(self):
        # ⚠️ Имя класса ищем В РАЗМЕТКЕ ШАБЛОНА, а не на странице: набор
        # деталей вклеен в неё `<style>`-ом, и проверка «класса нет» ловила
        # бы правило набора. По проекту наступали на это семь раз.
        markup = read('teacher', 'templates', 'teacher', 'groups',
                      'submissions_by_student.html')
        self.assertIn('k-mark k-mark--next', markup)
        self.assertNotIn('k-card--calls', markup)
        self.assertIn('k-mark--next', self.list_page())

    def test_the_highlight_is_explained_in_words(self):
        self.assertIn('следующий на проверку', self.list_page())

    def test_exactly_one_card_is_next(self):
        cards = views_groups.student_cards(self.work, self.group)
        self.assertEqual(sum(1 for card in cards if card['is_next']), 1)

    def test_nobody_is_next_when_there_is_nothing_to_check(self):
        """Указание «начните отсюда» там, где начинать нечего, — враньё."""
        TeacherFeedback.objects.create(submission=self.sub,
                                       score=Decimal('2'),
                                       reviewed_by=self.tutor)
        self.sub.status = 'reviewed'
        self.sub.save(update_fields=['status'])
        cards = views_groups.student_cards(self.work, self.group)
        self.assertEqual(sum(1 for card in cards if card['is_next']), 0)

    def test_status_is_one_line_for_everyone(self):
        cards = {card['student'].username: card
                 for card in views_groups.student_cards(self.work, self.group)}
        for card in cards.values():
            self.assertNotIn('\n', card['status_line'])
        self.assertIn('сдано 1 из 1', cards['lc-did']['status_line'])
        self.assertIn('не начата', cards['lc-idle']['status_line'])

    def test_the_line_is_glued_with_dots(self):
        cards = {card['student'].username: card
                 for card in views_groups.student_cards(self.work, self.group)}
        self.assertGreaterEqual(cards['lc-did']['status_line'].count(' · '), 2)

    def test_the_card_prints_only_that_one_line(self):
        html = self.list_page()
        self.assertEqual(html.count('class="stu-meta"'), 2)
        self.assertNotIn('class="stu-state"', html)

    def test_gap_around_the_word_between_numbers(self):
        kit = read('templates', '_kit.html')
        rule = re.search(r'\.k-score__of \{([^}]*)\}', kit).group(1)
        self.assertIn('margin: 0 .3em', rule)

    def test_the_one_who_did_not_start_is_not_dimmed(self):
        markup = read('teacher', 'templates', 'teacher', 'groups',
                      'submissions_by_student.html')
        self.assertNotIn('opacity: .62', markup)

    def test_missing_numbers_are_dashes_not_holes(self):
        """Иначе карточка теряет две колонки и список перестаёт быть списком."""
        html = self.list_page()
        idle = html.split('Дмитриев')[1]
        self.assertEqual(idle.count('k-score__value--none'), 2,
                         'у не начавшего пропали колонки, а не числа')
        # Обе колонки есть у КАЖДОЙ карточки — это и держит список списком.
        self.assertEqual(html.count('class="k-score k-score--pair"'), 4)


# ══════════════════════════════════════════════════════════════════════════
# 3.2 — проверка одной задачи
# ══════════════════════════════════════════════════════════════════════════
class OneTaskReviewTests(CheckBase):

    def test_three_equal_sections_instead_of_nested_cards(self):
        html = self.review_page()
        self.assertNotIn('class="rv-box"', html)
        self.assertNotIn('class="rv-pair"', html)
        self.assertEqual(html.count('class="rv-sect"'), 2)      # ответ, эталон
        self.assertIn('class="rv-sect rv-solution"', html)      # решение

    def test_the_sections_are_named_shortly_and_alike(self):
        html = self.review_page()
        for caption in ('>Ответ<', '>Верный ответ<', '>Решение<'):
            self.assertIn(caption, html, caption)

    def test_the_divider_is_a_thin_line(self):
        markup = read('teacher', 'templates', 'teacher', 'review.html')
        rule = re.search(r'\.rv-sect \{([^}]*)\}', markup).group(1)
        self.assertIn('border-top: 1px solid var(--border-soft)', rule)

    def test_presets_became_one_switch(self):
        html = self.review_page()
        self.assertIn('class="rv-seg"', html)
        markup = read('teacher', 'templates', 'teacher', 'review.html')
        rule = re.search(r'\.rv-seg \{([^}]*)\}', markup).group(1)
        self.assertIn('border: 1px solid var(--border)', rule)
        self.assertIn('overflow: hidden', rule)

    def test_the_chosen_preset_is_filled_with_the_accent(self):
        markup = read('teacher', 'templates', 'teacher', 'review.html')
        rule = re.search(r'\.rv-preset\.is-on \{([^}]*)\}', markup).group(1)
        self.assertIn('background: var(--accent)', rule)

    def test_hover_answers_the_mouse(self):
        """Три белых прямоугольника читались как отключённые."""
        markup = read('teacher', 'templates', 'teacher', 'review.html')
        rule = re.search(r'\.rv-preset:hover \{([^}]*)\}', markup).group(1)
        self.assertIn('var(--accent-tint)', rule)

    def test_the_rule_of_three_presets_is_untouched(self):
        """⚠️ Функцию не трогаем: минимум / половина / максимум."""
        from problems.work_review import score_presets

        values = [preset['value'] for preset in score_presets(Decimal('2'))]
        self.assertEqual(values, ['0', '1', '2'])

    def test_own_score_is_a_number_without_a_box(self):
        html = self.review_page()
        field = re.search(r'<input[^>]*id="score-input"[^>]*>', html).group(0)
        self.assertIn('class="k-num', field)
        self.assertNotIn('class="k-input"', field)

    def test_the_maximum_is_said_once_and_next_to_the_number(self):
        html = self.review_page()
        self.assertIn('из 2', html)
        self.assertNotIn('максимум 2', html)

    def test_the_head_carries_two_things(self):
        html = self.review_page()
        head = html.split('class="rv-grade-head"')[1].split('<label')[0]
        self.assertIn('Оценивание', head)
        self.assertIn('ждёт проверки', head)
        self.assertNotIn('балл не поставлен', head)

    def test_the_set_score_still_shows_in_the_head(self):
        TeacherFeedback.objects.create(submission=self.sub,
                                       score=Decimal('1.5'),
                                       reviewed_by=self.tutor)
        head = self.review_page().split('class="rv-grade-head"')[1] \
            .split('<label')[0]
        self.assertIn('1,5', head)

    def test_student_view_moved_up_to_the_other_transitions(self):
        html = self.review_page()
        nav = html.split('class="rv-nav"')[1].split('</div>')[0]
        self.assertIn('rv-eyes', nav)
        actions = html.split('class="rv-actions"')[1].split('</form>')[0]
        self.assertNotIn('rv-eyes', actions)

    def test_two_actions_are_left_at_the_bottom(self):
        html = self.review_page()
        actions = html.split('class="rv-actions"')[1].split('</div>')[0]
        self.assertEqual(actions.count('<button'), 2)

    def test_the_comment_says_who_will_read_it(self):
        self.assertIn('— увидит только Пётр', self.review_page())


# ══════════════════════════════════════════════════════════════════════════
# 3.3 — один словарь выделения
# ══════════════════════════════════════════════════════════════════════════
class OneHighlightDictionaryTests(TestCase):

    def test_the_perimeter_frame_no_longer_highlights(self):
        kit = read('templates', '_kit.html')
        rule = re.search(r'\.k-card--calls \{([^}]*)\}', kit).group(1)
        self.assertNotIn('var(--accent)', rule)

    def test_the_stripe_carries_the_state(self):
        kit = read('templates', '_kit.html')
        for name, token in (('next', 'accent'), ('correct', 'green'),
                            ('partial', 'amber'), ('empty', 'border')):
            self.assertIn('.k-mark.k-mark--%s' % name, kit, name)
            rule = re.search(
                r'\.k-mark\.k-mark--%s\s*\{([^}]*)\}' % name, kit).group(1)
            self.assertIn('var(--%s)' % token, rule, name)

    def test_the_fill_carries_the_choice(self):
        """Заливка означает «выбрано», и только это."""
        kit = read('templates', '_kit.html')
        rule = re.search(r'\.wk-card\.is-added \{([^}]*)\}', kit).group(1)
        self.assertIn('background: var(--green-tint)', rule)
