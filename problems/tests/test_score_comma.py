"""
Фаза 5 сессии 9 — сводка решений и переход к разбору.

5.2 Запятая в поле балла. Владелец: «нельзя поставить нецелый балл».
Причин было ДВЕ, и обе в нашем коде:
  1. поле было `type="number"`, а браузер не считает запятую допустимой и
     молча стирает набранное «1,5» — при том что кнопка-пресет рядом
     подписана «1,5»;
  2. хуже: начальное значение печатается через `{{ score|floatformat }}`,
     язык проекта русский, и фильтр отдаёт «1,50» — то есть УЖЕ
     поставленный дробный балл не показывался в форме вовсе.

5.3 «Глазами ученика» открывает ту задачу, которую смотрел репетитор.
"""
from decimal import Decimal

from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse

from problems.tests.factories import make_problem, make_user
from teacher.views import normalize_decimal, parse_score


class LocaleTrapTests(TestCase):
    def test_floatformat_speaks_russian(self):
        """Ловушка: `floatformat` отдаёт запятую, а number-поле её отвергает.

        Этот тест не про наш код, а про то, ПОЧЕМУ поле стало текстовым.
        """
        out = Template('{{ v|floatformat:"-2" }}').render(
            Context({'v': Decimal('1.5')}))
        self.assertEqual(out, '1,50')


class ParseScoreTests(TestCase):
    def test_comma_is_a_valid_score(self):
        self.assertEqual(parse_score('1,5'), 1.5)

    def test_dot_still_works(self):
        self.assertEqual(parse_score('1.5'), 1.5)

    def test_spaces_are_forgiven(self):
        self.assertEqual(parse_score(' 2,25 '), 2.25)

    def test_nonbreaking_space_from_paste(self):
        self.assertEqual(parse_score('1 000,5'), 1000.5)

    def test_garbage_is_zero_not_a_crash(self):
        self.assertEqual(parse_score('нет'), 0.0)
        self.assertEqual(parse_score(''), 0.0)
        self.assertEqual(parse_score(None), 0.0)

    def test_normalizer_is_shared(self):
        self.assertEqual(normalize_decimal('1,5'), '1.5')


class ScoreFieldMarkupTests(TestCase):
    """Поле обязано быть текстовым — иначе запятая опять не введётся."""

    def setUp(self):
        from problems.models import (Assignment, AssignmentItem, StudentGroup,
                                     Submission)

        self.tutor = make_user('sc9_tutor', role='teacher')
        self.student = make_user('sc9_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'), points=Decimal('3'))
        self.sub = Submission.objects.create(student=self.student,
                                             assignment=self.work,
                                             problem_item=self.item,
                                             status='submitted')
        self.client.force_login(self.tutor)

    def _review_html(self):
        url = reverse('teacher:group_review_submission',
                      args=[self.group.pk, self.sub.pk])
        return self.client.get(url).content.decode()

    def test_field_is_text_with_decimal_keyboard(self):
        html = self._review_html()
        self.assertIn('inputmode="decimal"', html)
        self.assertNotIn('type="number" step="any" min="0" name="score"', html)

    def test_comma_reaches_the_database(self):
        from problems.models import TeacherFeedback

        url = reverse('teacher:group_review_submission',
                      args=[self.group.pk, self.sub.pk])
        self.client.post(url, {'score': '1,5', 'comment': '', 'go': 'list'})
        feedback = TeacherFeedback.objects.get(submission=self.sub)
        self.assertEqual(float(feedback.score), 1.5)

    def test_saved_fraction_comes_back_to_the_form(self):
        """Раньше сохранённые 1,5 в поле НЕ ПОКАЗЫВАЛИСЬ вовсе."""
        url = reverse('teacher:group_review_submission',
                      args=[self.group.pk, self.sub.pk])
        self.client.post(url, {'score': '1,5', 'comment': '', 'go': 'list'})
        html = self._review_html()
        self.assertIn('value="1,50"', html)

    def test_server_still_clips_by_maximum(self):
        """Обрезка по максимуму — не тронута."""
        from problems.models import TeacherFeedback

        url = reverse('teacher:group_review_submission',
                      args=[self.group.pk, self.sub.pk])
        self.client.post(url, {'score': '99,5', 'comment': '', 'go': 'list'})
        feedback = TeacherFeedback.objects.get(submission=self.sub)
        self.assertEqual(float(feedback.score), 3.0)

    def test_api_accepts_comma_and_answers_with_comma(self):
        """Балл возвращается в поле — значит и обратно едет по-русски."""
        import json

        resp = self.client.post(reverse('teacher:api_grade_submission'),
                                {'submission': self.sub.pk, 'score': '1,5',
                                 'comment': ''})
        payload = json.loads(resp.content.decode())
        self.assertEqual(payload['score'], 1.5)
        self.assertEqual(payload['label'], '1,5')

    def test_api_still_rejects_garbage(self):
        resp = self.client.post(reverse('teacher:api_grade_submission'),
                                {'submission': self.sub.pk, 'score': 'ой',
                                 'comment': ''})
        self.assertEqual(resp.status_code, 400)


class OpenTaskOnReviewTests(TestCase):
    """5.3 — переход «глазами ученика» открывает нужную задачу."""

    def setUp(self):
        from problems.models import (Assignment, AssignmentItem, StudentGroup,
                                     Submission)

        self.tutor = make_user('ot_tutor', role='teacher')
        self.student = make_user('ot_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        self.items, self.subs = [], []
        for n in range(3):
            item = AssignmentItem.objects.create(
                assignment=self.work, order=n,
                catalog_problem=make_problem('Условие %d' % n),
                points=Decimal('5'))
            self.items.append(item)
            self.subs.append(Submission.objects.create(
                student=self.student, assignment=self.work,
                problem_item=item, status='submitted'))
        self.client.force_login(self.tutor)

    def test_link_carries_the_position(self):
        url = reverse('teacher:group_review_submission',
                      args=[self.group.pk, self.subs[2].pk])
        resp = self.client.get(url)
        self.assertIn('?open=%d' % self.items[2].pk,
                      resp.context['work_review_url'])

    def test_that_task_is_open_and_others_are_not(self):
        url = reverse('teacher:student_work_review',
                      args=[self.group.pk, self.work.pk, self.student.pk])
        html = self.client.get(url + '?open=%d' % self.items[2].pk
                               ).content.decode()
        self.assertIn('id="task-%d"' % self.items[2].pk, html)
        # ⚠️ Ищем РАЗМЕТКУ (`data-open-target="1"`), а не имя атрибута:
        # само имя стоит ещё и в селекторе прокрутки, и по нему тест
        # находил бы совпадение всегда.
        self.assertIn('data-open-target="1"', html)
        # Раскрыта ровно одна: репетитор пришёл к конкретной задаче.
        self.assertEqual(html.count('data-open-target="1"'), 1)

    def test_without_the_parameter_everything_stays_folded(self):
        """Прежнее поведение репетитора не тронуто."""
        url = reverse('teacher:student_work_review',
                      args=[self.group.pk, self.work.pk, self.student.pk])
        html = self.client.get(url).content.decode()
        self.assertNotIn('data-open-target="1"', html)

    def test_garbage_in_the_parameter_does_not_crash(self):
        url = reverse('teacher:student_work_review',
                      args=[self.group.pk, self.work.pk, self.student.pk])
        resp = self.client.get(url + '?open=ой')
        self.assertEqual(resp.status_code, 200)


class ScoresAlignmentTests(TestCase):
    """5.1 — два крупных числа выравниваются по верху, а не по центру."""

    def test_scores_live_in_one_row(self):
        import io
        import os

        from django.conf import settings

        path = os.path.join(
            settings.BASE_DIR, 'teacher', 'templates', 'teacher', 'groups',
            'submissions_by_student.html')
        with io.open(path, encoding='utf-8') as handle:
            text = handle.read()
        self.assertIn('stu-scores', text)
        self.assertIn('align-items: flex-start', text)
