"""
Объединённое ревью 15.08, фаза 6 — пересчёт оценки в разборе «глазами
ученика».

Пункт 10 владельца («балл меняется только при обновлении странички») и
найденный при разборе отдельный дефект: плашка результата оставалась
ЗЕЛЁНОЙ со словами «Верно ✓» рядом с чипом «ЧАСТИЧНО».
"""
import json
import os
import re
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import StudentGroup
from problems.part_grading import is_machine_comment, BLANK_COMMENT
from problems.tests.factories import make_problem, make_user
from problems.work_review import state_of, state_word, work_summary

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


class VerdictWordTests(TestCase):
    """Слово вердикта — одна точка на чип и на плашку."""

    def test_words_are_the_ones_on_screen(self):
        self.assertEqual(state_word('correct'), 'верно')
        self.assertEqual(state_word('partial'), 'частично')
        self.assertEqual(state_word('wrong'), 'неверно')

    def test_unknown_state_says_nothing(self):
        self.assertEqual(state_word('какое-то'), '')

    def test_state_follows_the_score(self):
        self.assertEqual(state_of(Decimal('2'), Decimal('2')), 'correct')
        self.assertEqual(state_of(Decimal('1'), Decimal('2')), 'partial')
        self.assertEqual(state_of(Decimal('0'), Decimal('2')), 'wrong')
        self.assertEqual(state_of(Decimal('0'), Decimal('2'), blank=True),
                         'blank')
        self.assertEqual(state_of(None, Decimal('2')), 'pending')

    def test_template_does_not_spell_the_words_itself(self):
        """⚠️ Лесенка `{% if %}` со своими словами и была расхождением."""
        page = read('student', 'templates', 'student', 'work_review.html')
        head = page.split('data-wr-flag')[1][:200]
        self.assertIn('row.verdict', head)


class MachineCommentTests(TestCase):
    def test_known_machine_texts(self):
        for text in ('Верно ✓', 'Неверно.', 'Неверно. Правильный ответ: 5',
                     BLANK_COMMENT, 'а) верно; б) неверно, правильный ответ: 3'):
            self.assertTrue(is_machine_comment(text), text)

    def test_human_words_survive(self):
        for text in ('Молодец, но проверь знак', 'верно рассуждаешь',
                     '', None):
            self.assertFalse(is_machine_comment(text), text)


class Base(TestCase):
    def setUp(self):
        from problems.models import (Assignment, AssignmentItem, Submission,
                                     TeacherFeedback)

        now = timezone.now()
        self.tutor = make_user('rg_tutor', role='teacher')
        self.student = make_user('rg_student', role='student',
                                 first_name='Пётр', last_name='Иванов')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([self.student])
        self.work = Assignment.objects.create(
            name='Домашка', author=self.tutor, group=self.group,
            deadline=now + timedelta(days=1))
        self.work.students.set([self.student])
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'), points=Decimal('1'))
        self.second = AssignmentItem.objects.create(
            assignment=self.work, order=1,
            catalog_problem=make_problem('Второе условие'),
            points=Decimal('2'))
        self.sub = Submission.objects.create(
            student=self.student, assignment=self.work,
            problem_item=self.item, status='reviewed',
            submitted_at=now, submitted_answer='5')
        Submission.objects.create(
            student=self.student, assignment=self.work,
            problem_item=self.second, status='reviewed',
            submitted_at=now, submitted_answer='7')
        # Машина проверила и написала свой вердикт.
        TeacherFeedback.objects.create(submission=self.sub, score=Decimal('1'),
                                       comment='Верно ✓', reviewed_by=None)
        self.client.force_login(self.tutor)

    def _grade(self, score, comment=''):
        response = self.client.post(
            reverse('teacher:api_grade_submission'),
            {'submission': self.sub.pk, 'score': score, 'comment': comment})
        self.assertEqual(response.status_code, 200, response.content)
        return json.loads(response.content.decode())


class AnswerCarriesEverythingTests(Base):
    """Экран пересчитывает себя ПО ОТВЕТУ СЕРВЕРА, а не своим счётом."""

    def test_verdict_and_state_come_back(self):
        data = self._grade('0,5')
        self.assertEqual(data['state'], 'partial')
        self.assertEqual(data['verdict'], 'частично')

    def test_full_score_is_correct(self):
        self.assertEqual(self._grade('1')['verdict'], 'верно')

    def test_zero_is_wrong(self):
        self.assertEqual(self._grade('0')['verdict'], 'неверно')

    def test_score_is_written_the_platform_way(self):
        data = self._grade('0,5')
        self.assertEqual(data['score_text'], '0,5')
        self.assertEqual(data['points_text'], '0,5 / 1 б.')
        self.assertNotIn('0,50', json.dumps(data, ensure_ascii=False))

    def test_work_total_is_recounted(self):
        data = self._grade('0,5')
        self.assertEqual(data['total'], '0,5')
        self.assertEqual(data['total_max'], '3')

    def test_wrong_counter_is_recounted(self):
        self.assertEqual(self._grade('1')['wrong'], 0)
        self.assertEqual(self._grade('0,5')['wrong'], 1)

    def test_pending_is_reported(self):
        """Вторая задача не проверена — результат ещё предварительный."""
        data = self._grade('1')
        self.assertEqual(data['pending'], 1)
        self.assertFalse(data['is_final'])

    def test_totals_match_the_page_itself(self):
        """⚠️ Второго расчёта нет: сверяем ответ с той же `work_summary`."""
        data = self._grade('0,5')
        summary = work_summary(self.work, self.student)
        self.assertEqual(data['total'], summary['scored'])
        self.assertEqual(data['total_max'], summary['max_score'])
        self.assertEqual(data['wrong'], summary['wrong'])


class PlateFollowsTheVerdictTests(Base):
    """Плашка результата — тот же вердикт и тот же цвет, что у чипа."""

    def _html(self):
        """РАЗМЕТКА страницы без стилей.

        ⚠️ Набор вклеен в `<style>` страницы, и имена классов состояния
        встречаются там в правилах: проверка «класса нет» по тексту страницы
        краснела бы всегда. Наступали на это четырежды.
        """
        html = self.client.get(
            reverse('teacher:student_work_review',
                    args=[self.group.pk, self.work.pk,
                          self.student.pk])).content.decode()
        return re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.S)

    def test_partial_plate_is_not_green(self):
        self._grade('0,5')
        html = self._html()
        self.assertIn('fb-state--partial', html)
        self.assertNotIn('fb-state--correct', html)

    def test_full_plate_is_green(self):
        self._grade('1')
        self.assertIn('fb-state--correct', self._html())

    def test_zero_plate_is_red(self):
        self._grade('0')
        self.assertIn('fb-state--wrong', self._html())

    def test_plate_says_the_same_word_as_the_chip(self):
        self._grade('0,5')
        html = self._html()
        block = html.split('id="task-%d"' % self.item.pk)[1].split('</details>')[0]
        self.assertEqual(block.count('частично'), 2, block[:400])

    def test_colour_no_longer_depends_on_who_checked(self):
        """⚠️ Прежнее правило красило зелёным ЛЮБУЮ человеческую проверку."""
        style = read('student', 'templates', 'student', '_work_style.html')
        self.assertNotIn('.fb-block.fb-teacher { background: var(--green-tint)',
                         style)
        self.assertIn('.fb-block.fb-state--correct', style)


class MachineVerdictDoesNotSurviveTests(Base):
    """«Верно ✓» от машины не выдаёт себя за слова преподавателя."""

    def test_edit_field_is_empty_for_a_machine_comment(self):
        summary = work_summary(self.work, self.student)
        row = next(r for r in summary['rows'] if r['sub'].pk == self.sub.pk)
        self.assertEqual(row['comment'], '')

    def test_human_comment_is_kept_for_editing(self):
        self._grade('0,5', comment='Проверь знак')
        summary = work_summary(self.work, self.student)
        row = next(r for r in summary['rows'] if r['sub'].pk == self.sub.pk)
        self.assertEqual(row['comment'], 'Проверь знак')

    def test_saving_a_lower_score_drops_the_machine_verdict(self):
        """Форма шлёт пустой комментарий — «Верно ✓» уходит из базы."""
        from problems.models import TeacherFeedback

        self._grade('0,5')
        feedback = TeacherFeedback.objects.get(submission=self.sub)
        self.assertEqual(feedback.comment, '')
        self.assertNotIn('Верно ✓', self._html_of_work())

    def _html_of_work(self):
        html = self.client.get(
            reverse('teacher:student_work_review',
                    args=[self.group.pk, self.work.pk,
                          self.student.pk])).content.decode()
        return re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.S)


class HooksExistTests(TestCase):
    """Точки обновления на месте — без них скрипту нечего искать."""

    HOOKS = ('data-wr-total', 'data-wr-max', 'data-wr-cap', 'data-wr-wrong',
             'data-wr-flag', 'data-wr-got')

    def test_page_has_every_hook(self):
        page = read('student', 'templates', 'student', 'work_review.html')
        for hook in self.HOOKS:
            self.assertIn(hook, page, hook)

    def test_plate_has_its_hooks(self):
        block = read('student', 'templates', 'student', '_feedback_block.html')
        for hook in ('data-fb-block', 'data-fb-score', 'data-fb-verdict',
                     'data-fb-comment', 'data-fb-source'):
            self.assertIn(hook, block, hook)

    def test_script_touches_all_of_them(self):
        page = read('student', 'templates', 'student', 'work_review.html')
        script = page.split('function repaintTask')[1]
        for hook in ('data-wr-flag', 'data-wr-got', 'data-fb-block',
                     'data-wr-total', 'data-wr-wrong', 'data-prelim'):
            self.assertIn(hook, script, hook)

    def test_script_does_not_count_anything_itself(self):
        """⚠️ Второй расчёт на клиенте разошёлся бы с базой (урок «Штриха»)."""
        page = read('student', 'templates', 'student', 'work_review.html')
        script = page.split('function repaintWork')[1].split('}\n')[0]
        for forbidden in ('+ Number', 'parseFloat', 'reduce('):
            self.assertNotIn(forbidden, script, forbidden)
