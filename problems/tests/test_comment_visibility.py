"""
Три варианта видимости комментария (фаза 5 сессии фиксов).

⚠️ ЧТО БЫЛО СЛОМАНО В МОДЕЛИ, А НЕ В ОФОРМЛЕНИИ. Вариантов было два:
«видят все» и «только я и автор». Второй написан ОТ ЛИЦА УЧЕНИКА: когда
комментарий пишет репетитор, «автор» — это он сам, и получалось «только я и
я». Ученик такой комментарий не видел, хотя по названию должен был.

Стало три, и все названы от лица того, кто пишет:
1. «видно всей группе»;
2. «видно только этому ученику» — требует выбора ученика (адресата);
3. «заметка для себя» — не видит никто, кроме автора.
"""
from decimal import Decimal

import json

from django.test import TestCase
from django.urls import reverse

from problems.models import (
    Assignment, AssignmentItem, ProblemComment, StudentGroup,
)
from problems.models_platform import visibility_choices_for
from problems.tests.factories import make_problem, make_user


class VisibilityRulesTests(TestCase):
    """Кто что видит."""

    def setUp(self):
        self.tutor = make_user('t-vis', role='teacher')
        self.anya = make_user('anya', role='student')
        self.boris = make_user('boris', role='student')
        self.group = StudentGroup.objects.create(name='Группа',
                                                 teacher=self.tutor)
        self.group.students.add(self.anya, self.boris)
        self.assignment = Assignment.objects.create(
            name='Работа', author=self.tutor, group=self.group)
        self.assignment.students.add(self.anya, self.boris)
        self.item = AssignmentItem.objects.create(
            assignment=self.assignment, order=0,
            catalog_problem=make_problem('Задача.', difficulty=2),
            points=Decimal('2'))

    def _make(self, author, visibility, recipient=None, text='Текст'):
        return ProblemComment.objects.create(
            assignment=self.assignment, problem_item=self.item, author=author,
            text=text, visibility=visibility, recipient=recipient)

    def _seen_by(self, user):
        return set(ProblemComment.objects.visible_for(user)
                   .values_list('pk', flat=True))

    def test_group_comment_is_seen_by_everyone(self):
        comment = self._make(self.tutor, ProblemComment.Visibility.GROUP)
        for user in (self.tutor, self.anya, self.boris):
            self.assertIn(comment.pk, self._seen_by(user))

    def test_private_to_a_student_is_seen_by_that_student_only(self):
        """Главный чинимый случай: репетитор пишет ОДНОМУ ученику."""
        comment = self._make(self.tutor, ProblemComment.Visibility.PRIVATE,
                             recipient=self.anya)
        self.assertIn(comment.pk, self._seen_by(self.tutor))
        self.assertIn(comment.pk, self._seen_by(self.anya))
        self.assertNotIn(comment.pk, self._seen_by(self.boris))

    def test_self_note_is_seen_by_nobody_but_the_author(self):
        comment = self._make(self.tutor, ProblemComment.Visibility.SELF)
        self.assertIn(comment.pk, self._seen_by(self.tutor))
        self.assertNotIn(comment.pk, self._seen_by(self.anya))
        self.assertNotIn(comment.pk, self._seen_by(self.boris))

    def test_students_self_note_is_hidden_even_from_the_tutor(self):
        """⚠️ «Заметка для себя» обязана быть заметкой для СЕБЯ.

        Иначе это обещание, которого система не держит.
        """
        comment = self._make(self.anya, ProblemComment.Visibility.SELF)
        self.assertIn(comment.pk, self._seen_by(self.anya))
        self.assertNotIn(comment.pk, self._seen_by(self.tutor))
        self.assertNotIn(comment.pk, self._seen_by(self.boris))

    def test_student_question_is_seen_by_the_student_and_the_tutor(self):
        comment = self._make(self.anya, ProblemComment.Visibility.PRIVATE)
        self.assertIn(comment.pk, self._seen_by(self.anya))
        self.assertIn(comment.pk, self._seen_by(self.tutor))
        self.assertNotIn(comment.pk, self._seen_by(self.boris))


class VisibilityLabelsTests(TestCase):
    """Названия — от лица того, кто пишет; пометка — только у исключений."""

    def setUp(self):
        self.tutor = make_user('t-lab', role='teacher')
        self.student = make_user('s-lab', role='student')
        self.assignment = Assignment.objects.create(name='Работа',
                                                    author=self.tutor)
        self.item = AssignmentItem.objects.create(
            assignment=self.assignment, order=0,
            catalog_problem=make_problem('Задача.', difficulty=2),
            points=Decimal('2'))

    def _make(self, visibility, recipient=None, author=None):
        return ProblemComment.objects.create(
            assignment=self.assignment, problem_item=self.item,
            author=author or self.tutor, text='Т',
            visibility=visibility, recipient=recipient)

    def test_tutor_has_three_choices_named_from_the_writers_side(self):
        labels = [label for _, label in visibility_choices_for('tutor')]
        self.assertEqual(labels, ['видно всей группе',
                                  'видно только этому ученику',
                                  'заметка для себя'])
        for label in labels:
            self.assertNotIn('автор', label,
                             'название снова написано от лица читателя')

    def test_student_choices_are_their_own(self):
        labels = [label for _, label in visibility_choices_for('student')]
        self.assertIn('видно вам и преподавателю', labels)
        self.assertIn('заметка для себя', labels)
        self.assertNotIn('видно всей группе', labels,
                         'публичные вопросы учеников — канал списывания')

    def test_group_comment_carries_no_note(self):
        """Обычный комментарий не подписывается: выделять надо исключение."""
        self.assertEqual(
            self._make(ProblemComment.Visibility.GROUP).note_for(self.tutor),
            '')

    def test_private_note_depends_on_the_reader(self):
        comment = self._make(ProblemComment.Visibility.PRIVATE,
                             recipient=self.student)
        self.assertEqual(comment.note_for(self.student), 'лично вам')
        self.assertEqual(comment.note_for(self.tutor), 'лично ученику')

    def test_self_note_says_so(self):
        comment = self._make(ProblemComment.Visibility.SELF)
        self.assertEqual(comment.note_for(self.tutor), 'только я')

    def test_student_question_note_depends_on_the_reader(self):
        """Автору говорим, кому он написал; репетитору — что вопрос личный."""
        comment = self._make(ProblemComment.Visibility.PRIVATE,
                             author=self.student)
        self.assertEqual(comment.note_for(self.student), 'только преподавателю')
        self.assertEqual(comment.note_for(self.tutor), 'личный вопрос')


class CommentEndpointTests(TestCase):
    """Эндпоинт: адресат обязателен там, где без него получается «я и я»."""

    def setUp(self):
        self.tutor = make_user('t-api', role='teacher')
        self.student = make_user('s-api', role='student')
        self.outsider = make_user('outsider', role='student')
        self.group = StudentGroup.objects.create(name='Группа',
                                                 teacher=self.tutor)
        self.group.students.add(self.student)
        self.assignment = Assignment.objects.create(
            name='Работа', author=self.tutor, group=self.group)
        self.assignment.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.assignment, order=0,
            catalog_problem=make_problem('Задача.', difficulty=2),
            points=Decimal('2'))

    def _post(self, payload):
        payload.setdefault('item_id', self.item.pk)
        payload.setdefault('text', 'Сообщение')
        return self.client.post(reverse('teacher:api_comment_create'),
                                json.dumps(payload),
                                content_type='application/json')

    def test_tutor_private_without_a_student_is_rejected(self):
        """⚠️ Ровно эта дыра и была моделью «только я и я»."""
        self.client.force_login(self.tutor)
        response = self._post({'visibility': 'private'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('ученик', response.json()['error'].lower())
        self.assertEqual(ProblemComment.objects.count(), 0)

    def test_tutor_private_to_an_outsider_is_rejected(self):
        self.client.force_login(self.tutor)
        response = self._post({'visibility': 'private',
                               'recipient_id': self.outsider.pk})
        self.assertEqual(response.status_code, 400)

    def test_tutor_private_with_a_student_goes_through(self):
        self.client.force_login(self.tutor)
        response = self._post({'visibility': 'private',
                               'recipient_id': self.student.pk})
        self.assertEqual(response.status_code, 200)
        comment = ProblemComment.objects.get()
        self.assertEqual(comment.recipient_id, self.student.pk)
        self.assertEqual(response.json()['note'], 'лично ученику')

    def test_tutor_self_note_never_has_a_recipient(self):
        self.client.force_login(self.tutor)
        self._post({'visibility': 'self', 'recipient_id': self.student.pk})
        comment = ProblemComment.objects.get()
        self.assertEqual(comment.visibility, ProblemComment.Visibility.SELF)
        self.assertIsNone(comment.recipient_id)

    def test_student_cannot_write_to_the_whole_group(self):
        self.client.force_login(self.student)
        self._post({'visibility': 'group'})
        comment = ProblemComment.objects.get()
        self.assertEqual(comment.visibility, ProblemComment.Visibility.PRIVATE)

    def test_student_can_keep_a_note_for_themselves(self):
        self.client.force_login(self.student)
        self._post({'visibility': 'self'})
        comment = ProblemComment.objects.get()
        self.assertEqual(comment.visibility, ProblemComment.Visibility.SELF)


class OldCommentsKeepTheirAudienceTests(TestCase):
    """Миграция: те же люди видят то же самое.

    ⚠️ Приватный комментарий репетитора БЕЗ адресата не видел никто, кроме
    него самого, — это и есть «заметка для себя», просто у неё не было
    названия. Миграция даёт ей имя, круг читателей не меняя.
    """

    def test_migration_logic_matches_who_could_see_what(self):
        tutor = make_user('t-mig', role='teacher')
        student = make_user('s-mig', role='student')
        group = StudentGroup.objects.create(name='Г', teacher=tutor)
        group.students.add(student)
        assignment = Assignment.objects.create(name='Р', author=tutor,
                                               group=group)
        assignment.students.add(student)
        item = AssignmentItem.objects.create(
            assignment=assignment, order=0,
            catalog_problem=make_problem('З.', difficulty=2),
            points=Decimal('2'))

        note = ProblemComment.objects.create(
            assignment=assignment, problem_item=item, author=tutor,
            text='Пометка себе', visibility=ProblemComment.Visibility.SELF)
        to_student = ProblemComment.objects.create(
            assignment=assignment, problem_item=item, author=tutor,
            text='Ответ ученику', recipient=student,
            visibility=ProblemComment.Visibility.PRIVATE)
        question = ProblemComment.objects.create(
            assignment=assignment, problem_item=item, author=student,
            text='Вопрос', visibility=ProblemComment.Visibility.PRIVATE)

        seen_by_student = set(ProblemComment.objects.visible_for(student)
                              .values_list('pk', flat=True))
        self.assertEqual(seen_by_student, {to_student.pk, question.pk})

        seen_by_tutor = set(ProblemComment.objects.visible_for(tutor)
                            .values_list('pk', flat=True))
        self.assertEqual(seen_by_tutor,
                         {note.pk, to_student.pk, question.pk})
