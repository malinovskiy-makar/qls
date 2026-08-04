"""
Часть 0: единый список задач, единая форма ответа, один срок, комментарий.

Эти тесты стерегут ровно то, что было сломано и починено в Части 0.
Каждый — про конкретный видимый дефект, а не про «код работает».
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.assignment_rows import build_rows, item_answer_form
from problems.models import (
    Assignment, AssignmentItem, CustomProblem, CustomProblemOption,
    ProblemComment, ProblemPart, StudentGroup,
)
from problems.tests.factories import (
    make_assignment, make_item, make_problem, make_user,
)


class UnifiedListTests(TestCase):
    """Список задач один, а не два: каталожные и свои идут вперемешку."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = make_user('tutor_rows', role='teacher')
        cls.student = make_user('student_rows', role='student')
        cls.catalog_a = make_problem('Каталожная A')
        cls.catalog_b = make_problem('Каталожная B')
        cls.assignment = make_assignment(cls.tutor, students=[cls.student],
                                         problems=[])
        cls.custom = CustomProblem.objects.create(
            owner=cls.tutor, statement='Своя задача репетитора',
            kind=CustomProblem.Kind.OPEN, correct_answer='42')
        # Порядок намеренно «своя посередине»: если бы список собирался
        # двумя циклами, она уехала бы в конец отдельным блоком.
        make_item(cls.assignment, catalog_problem=cls.catalog_a, order=0)
        make_item(cls.assignment, custom_problem=cls.custom, order=1)
        make_item(cls.assignment, catalog_problem=cls.catalog_b, order=2)

    def test_three_positions_one_list_in_order(self):
        rows = build_rows(self.assignment, self.student)
        self.assertEqual(len(rows), 3)
        self.assertEqual([r['number'] for r in rows], [1, 2, 3])
        self.assertEqual([r['statement'] for r in rows],
                         ['Каталожная A', 'Своя задача репетитора',
                          'Каталожная B'])

    def test_all_rows_have_same_answer_fields(self):
        """У каждой позиции ровно три поля с одинаковыми именами-шаблонами."""
        rows = build_rows(self.assignment, self.student)
        for row in rows:
            item = row['item']
            self.assertEqual(row['answer_name'], 'answer_item_%d' % item.pk)
            self.assertEqual(row['solution_name'], 'text_item_%d' % item.pk)
            self.assertEqual(row['file_name'], 'file_item_%d' % item.pk)

    def test_page_renders_single_list_without_separate_heading(self):
        self.client.force_login(self.student)
        resp = self.client.get(
            reverse('student:assignment_detail', args=[self.assignment.pk]))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # Заголовок отдельного блока «Задачи от преподавателя» больше не
        # существует: он и был вторым списком.
        self.assertNotIn('Задачи от преподавателя', body)
        self.assertEqual(len(resp.context['rows']), 3)
        # Все три поля ответа — на странице.
        for row in resp.context['rows']:
            self.assertIn('name="%s"' % row['answer_name'], body)
            self.assertIn('name="%s"' % row['solution_name'], body)
            self.assertIn('name="%s"' % row['file_name'], body)

    def test_submit_accepts_catalog_and_custom_the_same_way(self):
        self.client.force_login(self.student)
        rows = build_rows(self.assignment, self.student)
        payload = {}
        for row in rows:
            payload[row['answer_name']] = 'ответ %d' % row['number']
            payload[row['solution_name']] = 'ход решения'
        self.client.post(
            reverse('student:submit_assignment', args=[self.assignment.pk]),
            payload)
        for row in build_rows(self.assignment, self.student):
            # 'reviewed' у своей задачи с эталонным ответом — она проверилась
            # автоматически. Главное, что принята КАЖДАЯ позиция.
            self.assertIn(row['sub'].status, ('submitted', 'reviewed'),
                          row['number'])
            self.assertEqual(row['sub'].solution_text, 'ход решения')


class AnswerControlTests(TestCase):
    """Элемент ввода ответа зависит от вида задачи — набор полей нет."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = make_user('tutor_ctrl', role='teacher')
        cls.student = make_user('student_ctrl', role='student')
        cls.assignment = make_assignment(cls.tutor, students=[cls.student])

    def _catalog(self, ptype, labels=('а', 'б')):
        problem = make_problem('Тестовая', problem_type=ptype)
        for order, label in enumerate(labels):
            ProblemPart.objects.create(problem=problem, label=label,
                                       statement='вариант ' + label,
                                       order=order)
        return make_item(self.assignment, catalog_problem=problem)

    def test_catalog_single_choice_is_radio(self):
        item = self._catalog('тест: один ответ')
        kind, options = item_answer_form(item)
        self.assertEqual(kind, 'radio')
        self.assertEqual([o['value'] for o in options], ['а', 'б'])

    def test_catalog_multi_choice_is_checkbox(self):
        item = self._catalog('тест: все верные')
        self.assertEqual(item_answer_form(item)[0], 'checkbox')

    def test_open_catalog_problem_is_text(self):
        item = make_item(self.assignment,
                         catalog_problem=make_problem('Открытая'))
        kind, options = item_answer_form(item)
        self.assertEqual(kind, 'text')
        self.assertEqual(options, [])

    def test_custom_multiple_is_checkbox(self):
        problem = CustomProblem.objects.create(
            owner=self.tutor, statement='Своя множественная',
            kind=CustomProblem.Kind.MULTIPLE)
        CustomProblemOption.objects.create(problem=problem, text='раз',
                                           is_correct=True, order=0)
        CustomProblemOption.objects.create(problem=problem, text='два',
                                           order=1)
        item = make_item(self.assignment, custom_problem=problem)
        self.assertEqual(item_answer_form(item)[0], 'checkbox')

    def test_checkbox_answers_collected_into_one_field(self):
        """Галочки приходят одним именем — иначе ответ терялся целиком.

        Так и было до Части 0: разметка писала `answer_<pk>_<метка>`, а
        приёмник читал `answer_<pk>` — множественный выбор не доезжал никогда.
        """
        item = self._catalog('тест: все верные', labels=('а', 'б', 'в'))
        item.catalog_problem.answer = 'а, в'
        item.catalog_problem.save()
        self.client.force_login(self.student)
        self.client.post(
            reverse('student:submit_assignment', args=[self.assignment.pk]),
            {'answer_item_%d' % item.pk: ['а', 'в']})
        sub = item.submissions.get(student=self.student)
        self.assertEqual(sub.submitted_answer, 'а, в')


class StudentCommentTests(TestCase):
    """Вопрос ученика: доходит, приватен, чужой ученик его не видит."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = make_user('tutor_cmt', role='teacher')
        cls.student = make_user('student_cmt', role='student')
        cls.other = make_user('other_cmt', role='student')
        cls.group = StudentGroup.objects.create(name='Г', teacher=cls.tutor)
        cls.group.students.set([cls.student, cls.other])
        cls.assignment = make_assignment(
            cls.tutor, students=[cls.student, cls.other],
            problems=[make_problem('Задача с вопросом')], group=cls.group)
        cls.item = cls.assignment.items.first()

    def test_student_question_is_saved_private(self):
        self.client.force_login(self.student)
        resp = self.client.post(
            reverse('teacher:api_comment_create'),
            data={'item_id': self.item.pk, 'text': 'Не понял пункт б'},
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        comment = ProblemComment.objects.get(problem_item=self.item)
        self.assertEqual(comment.visibility, 'private')
        self.assertEqual(comment.author, self.student)

    def test_tutor_sees_it_and_other_student_does_not(self):
        comment = ProblemComment.objects.create(
            assignment=self.assignment, problem_item=self.item,
            author=self.student, text='Приватный вопрос',
            visibility=ProblemComment.Visibility.PRIVATE)
        self.assertIn(comment,
                      ProblemComment.objects.visible_for(self.tutor))
        self.assertIn(comment,
                      ProblemComment.objects.visible_for(self.student))
        self.assertNotIn(comment,
                         ProblemComment.objects.visible_for(self.other))

    def test_comment_block_is_not_a_nested_form(self):
        """Главная причина поломки: <form> внутри <form> браузер выбрасывает.

        Проверяем разметку, а не поведение: питон-тест не запускает парсер
        браузера и вложенность увидит только глазами разработчика — или вот
        этой проверкой.
        """
        self.client.force_login(self.student)
        body = self.client.get(
            reverse('student:assignment_detail',
                    args=[self.assignment.pk])).content.decode()
        self.assertIn('class="pf-comment-form"', body)
        self.assertNotIn('<form class="pf-comment-form"', body)
        # Кнопка «Спросить» не должна быть submit — иначе отправит домашку.
        self.assertIn('type="button" class="pf-btn pf-ask"', body)


class SingleDeadlineTests(TestCase):
    """Один срок вместо двух: контрольная больше не «без срока»."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = make_user('tutor_dl', role='teacher')
        cls.student = make_user('student_dl', role='student')
        cls.now = timezone.now()

    def _work(self, **kwargs):
        assignment = make_assignment(
            self.tutor, students=[self.student],
            problems=[make_problem('З')], **kwargs)
        return assignment

    def test_homework_with_deadline_shows_it(self):
        work = self._work(deadline=self.now + timedelta(days=3))
        self.assertEqual(work.deadline_at, work.deadline)

    def test_exam_window_shows_window_not_no_deadline(self):
        work = self._work(kind=Assignment.Kind.EXAM,
                          exam_mode=Assignment.ExamMode.WINDOW,
                          starts_at=self.now + timedelta(hours=1),
                          ends_at=self.now + timedelta(hours=2))
        from student.views import exam_schedule_label
        label = exam_schedule_label(work)
        self.assertIn('окно', label)
        self.assertNotIn('без срока', label)

    def test_exam_limit_shows_deadline_and_limit(self):
        work = self._work(kind=Assignment.Kind.EXAM,
                          exam_mode=Assignment.ExamMode.LIMIT,
                          deadline=self.now + timedelta(days=2),
                          duration_minutes=90)
        from student.views import exam_schedule_label
        label = exam_schedule_label(work)
        self.assertIn('до ', label)
        self.assertIn('90 мин', label)

    def test_work_without_deadline_is_honest(self):
        work = self._work()
        self.assertIsNone(work.deadline_at)

    def test_dashboard_splits_exams_from_homework(self):
        homework = self._work(deadline=self.now + timedelta(days=3))
        exam = self._work(kind=Assignment.Kind.EXAM,
                          exam_mode=Assignment.ExamMode.WINDOW,
                          starts_at=self.now - timedelta(minutes=5),
                          ends_at=self.now + timedelta(hours=1))
        self.client.force_login(self.student)
        resp = self.client.get(reverse('student:dashboard'))
        active_names = [r['assignment'].pk for r in resp.context['active']]
        exam_names = [r['assignment'].pk for r in resp.context['exams_open']]
        self.assertIn(homework.pk, active_names)
        self.assertNotIn(exam.pk, active_names)
        self.assertIn(exam.pk, exam_names)
        self.assertIn('окно', resp.context['exams_open'][0]['schedule'])

    def test_deadline_at_reads_single_field(self):
        """`due_at` устарел и больше не участвует в ответе на вопрос о сроке."""
        work = self._work()
        work.due_at = self.now + timedelta(days=9)
        work.save()
        self.assertIsNone(work.deadline_at)


class BackfillItemsTests(TestCase):
    """Бэкфилл позиций из старого M2M — идемпотентный."""

    def test_creates_missing_items_once(self):
        from io import StringIO

        from django.core.management import call_command

        tutor = make_user('tutor_bf', role='teacher')
        problems = [make_problem('A'), make_problem('B')]
        assignment = Assignment.objects.create(name='Старая', author=tutor)
        assignment.problems.set(problems)      # только M2M, позиций нет
        self.assertEqual(assignment.items.count(), 0)

        call_command('backfill_assignment_items', stdout=StringIO())
        self.assertEqual(assignment.items.count(), 2)
        self.assertEqual(
            list(assignment.items.order_by('order')
                 .values_list('catalog_problem_id', flat=True)),
            [p.pk for p in problems])

        call_command('backfill_assignment_items', stdout=StringIO())
        self.assertEqual(assignment.items.count(), 2)

    def test_keeps_existing_positions(self):
        tutor = make_user('tutor_bf2', role='teacher')
        kept, added = make_problem('Уже стоит'), make_problem('Только в M2M')
        assignment = Assignment.objects.create(name='Смешанная', author=tutor)
        assignment.problems.set([kept, added])
        AssignmentItem.objects.create(assignment=assignment,
                                      catalog_problem=kept, order=0,
                                      points=7)

        from io import StringIO

        from django.core.management import call_command
        call_command('backfill_assignment_items', stdout=StringIO())

        self.assertEqual(assignment.items.count(), 2)
        original = assignment.items.get(catalog_problem=kept)
        self.assertEqual(original.points, 7)   # балл не затёрт
