"""
Переписка по задаче: акценты и различение ролей (фаза 6 сессии фиксов).

Что было не так: разделитель «Переписка по задаче» — самый бледный элемент
карточки, хотя отделяет два РАЗНЫХ занятия (настройку проверки и разговор с
учеником); сообщения шли плоским потоком без воздуха; своё сообщение от
ученического не отличалось никак; метка видимости стояла серым курсивом.

Приём различения выбран ОДИН — подложка. Смещение, цвет имени и рамка
вместе превратили бы карточку задачи в мессенджер, которым она не является.
"""
import re
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from problems.models import (
    Assignment, AssignmentItem, ProblemComment, StudentGroup,
)
from problems.tests.factories import make_problem, make_user

KIT = 'templates/_kit.html'
TEACHER_STYLE = 'teacher/templates/teacher/groups/_style.html'
STUDENT_STYLE = 'student/templates/student/_work_style.html'


def read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


class AuthorSideTests(TestCase):
    """Признак «написал преподаватель» — по роли В ЭТОЙ РАБОТЕ."""

    def setUp(self):
        self.tutor = make_user('t-talk', role='teacher')
        self.student = make_user('s-talk', role='student')
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

    def _make(self, author):
        return ProblemComment.objects.create(
            assignment=self.assignment, problem_item=self.item, author=author,
            text='Текст', visibility=ProblemComment.Visibility.GROUP)

    def test_tutor_message_is_marked_as_tutors(self):
        self.assertTrue(self._make(self.tutor).by_tutor)

    def test_student_message_is_not(self):
        self.assertFalse(self._make(self.student).by_tutor)

    def test_group_teacher_counts_as_tutor_too(self):
        """Работу мог завести один преподаватель, а вести — другой."""
        other = make_user('t-other', role='teacher')
        self.group.teacher = other
        self.group.save(update_fields=['teacher'])
        self.assertTrue(self._make(other).by_tutor)

    def test_screen_marks_only_student_messages(self):
        self._make(self.tutor)
        self._make(self.student)
        self.client.force_login(self.tutor)
        html = self.client.get(reverse(
            'teacher:group_assignment',
            args=[self.group.pk, self.assignment.pk])).content.decode()
        markup = re.sub(r'<(script|style).*?</\1>', '', html, flags=re.S)
        self.assertEqual(markup.count('comment--student'), 1,
                         'подложка стоит не у одного сообщения')


class TalkStyleTests(TestCase):
    """Оформление: разделитель весомее, воздух есть, форма отделена."""

    def test_loud_separator_exists_in_the_kit(self):
        """Разделитель разделов, а не строк — вариант из НАБОРА деталей.

        Свой стиль в шаблоне разошёлся бы с соседними экранами.
        """
        kit = read(KIT)
        self.assertIn('.k-sep--loud', kit)
        self.assertIn('.k-sep--loud .k-sep__cap { font-size: 13px; '
                      'font-weight: 700;', kit)

    def test_hidden_select_wrapper_really_hides(self):
        """⚠️ `display` из набора СИЛЬНЕЕ браузерного `[hidden]`.

        Той же ловушкой в прошлой сессии рисовалась спрятанная кнопка; здесь
        так же рисовался список учеников у варианта «видно всей группе».
        Поймано глазами на скриншоте, питон-тесты этого не видят.
        """
        self.assertIn('.k-select-wrap[hidden]', read(KIT))

    def test_messages_have_air_between_them(self):
        style = read(TEACHER_STYLE)
        self.assertIn('.comment-list { display: flex; flex-direction: column; '
                      'gap: 10px; }', style)

    def test_form_is_separated_from_the_feed(self):
        """Форма сливалась с последним сообщением."""
        for path in (TEACHER_STYLE, STUDENT_STYLE):
            self.assertIn('border-top', read(path))
        self.assertIn('.comment-form { margin-top: 14px; padding-top: 12px;',
                      read(TEACHER_STYLE))

    def test_visibility_note_reads_as_important(self):
        """Метка видимости — единственный признак того, кто это увидит.

        Серый курсив для такого не годится.
        """
        style = read(TEACHER_STYLE)
        match = re.search(r'\.comment-private \{(.*?)\}', style, re.S)
        self.assertIsNotNone(match)
        rule = match.group(1)
        self.assertNotIn('italic', rule)
        self.assertIn('var(--amber)', rule)

    def test_both_screens_use_the_same_device(self):
        """Подложка — и у репетитора, и у ученика; приём ОДИН."""
        self.assertIn('.comment--student { background: var(--surface-2); }',
                      read(TEACHER_STYLE))
        self.assertIn('.pf-comment--student { background: var(--surface-2); }',
                      read(STUDENT_STYLE))

    def test_no_avatars_and_no_bubbles(self):
        """Это переписка внутри карточки задачи, а не мессенджер."""
        for path in (TEACHER_STYLE, STUDENT_STYLE):
            style = read(path)
            self.assertNotIn('avatar', style)
            self.assertNotIn('border-radius: 18px', style)
