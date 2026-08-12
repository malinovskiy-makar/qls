"""
Фаза 9 сессии 9 — индивидуальные ученики.

Сквозная мысль владельца: в олимпиадной экономике многие репетиторы ведут
один на один, а вся платформа построена вокруг группы.

⚠️ ГЛАВНОЕ РЕШЕНИЕ, которое здесь и закрепляется: тип занятия — ПОЛЕ, а не
вычисление из числа учеников. Группа, из которой ушли двое, не должна сама
превратиться в индивидуальную и потерять теплокарту; к индивидуальному можно
подсадить второго, и история не теряется.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from problems.models import StudentGroup
from problems.tests.factories import make_problem, make_user


class KindIsAFieldTests(TestCase):
    def setUp(self):
        self.tutor = make_user('ik_tutor', role='teacher')

    def test_default_is_group(self):
        group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.assertEqual(group.kind, StudentGroup.Kind.GROUP)
        self.assertFalse(group.is_individual)

    def test_group_with_one_student_stays_a_group(self):
        """⚠️ Прямое решение владельца: не вычислять тип из числа учеников."""
        group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        group.students.add(make_user('ik_one', role='student'))
        self.assertFalse(group.is_individual)
        self.assertIsNone(group.single_student)

    def test_individual_with_two_students_keeps_its_type(self):
        """К индивидуальному подсадили второго — историю терять нельзя."""
        lesson = StudentGroup.objects.create(
            name='Пётр', teacher=self.tutor,
            kind=StudentGroup.Kind.INDIVIDUAL)
        lesson.students.add(make_user('ik_a', role='student'))
        lesson.students.add(make_user('ik_b', role='student'))
        self.assertTrue(lesson.is_individual)
        # Шапка просто перестаёт показывать имя — всё остальное работает.
        self.assertIsNone(lesson.single_student)

    def test_kind_label(self):
        group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        lesson = StudentGroup.objects.create(
            name='П', teacher=self.tutor, kind=StudentGroup.Kind.INDIVIDUAL)
        self.assertEqual(group.kind_label, 'группа')
        self.assertEqual(lesson.kind_label, 'индивидуально')


class CreateTests(TestCase):
    def setUp(self):
        self.tutor = make_user('ic_tutor', role='teacher')
        self.student = make_user('ic_student', role='student',
                                 first_name='Мария', last_name='Ким')
        self.client.force_login(self.tutor)

    def test_group_form_asks_for_a_name(self):
        html = self.client.get(reverse('teacher:group_create')).content.decode()
        self.assertIn('Название группы', html)
        self.assertNotIn('id_student', html)

    def test_individual_form_asks_for_a_student(self):
        html = self.client.get(
            reverse('teacher:group_create') + '?kind=individual'
        ).content.decode()
        self.assertIn('id_student', html)

    def test_individual_gets_the_student_name_by_default(self):
        self.client.post(reverse('teacher:group_create'),
                         {'kind': 'individual', 'student': self.student.pk,
                          'name': ''})
        lesson = StudentGroup.objects.get(teacher=self.tutor)
        self.assertEqual(lesson.kind, StudentGroup.Kind.INDIVIDUAL)
        self.assertEqual(lesson.name, 'Мария Ким')
        self.assertEqual(lesson.single_student, self.student)

    def test_own_name_wins_over_the_default(self):
        self.client.post(reverse('teacher:group_create'),
                         {'kind': 'individual', 'student': self.student.pk,
                          'name': 'Мария, подготовка к ВсОШ'})
        lesson = StudentGroup.objects.get(teacher=self.tutor)
        self.assertEqual(lesson.name, 'Мария, подготовка к ВсОШ')

    def test_individual_without_a_student_is_refused(self):
        self.client.post(reverse('teacher:group_create'),
                         {'kind': 'individual', 'name': 'Без ученика'})
        self.assertFalse(StudentGroup.objects.exists())

    def test_unknown_kind_falls_back_to_group(self):
        self.client.post(reverse('teacher:group_create'),
                         {'kind': 'банда', 'name': 'Гр'})
        self.assertEqual(StudentGroup.objects.get().kind,
                         StudentGroup.Kind.GROUP)


class LessonScreenTests(TestCase):
    """Экран занятия ветвится в ШАБЛОНАХ: логика одна, набор блоков разный."""

    def setUp(self):
        from problems.management.commands.apply_topic_mapping import CANONICAL
        from problems.models import (Assignment, AssignmentItem, Submission,
                                     Topic)

        for index, name in enumerate(CANONICAL):
            Topic.objects.get_or_create(name=name,
                                        defaults={'slug': 'ls-%d' % index})
        self.tutor = make_user('ls_tutor', role='teacher')
        self.student = make_user('ls_student', role='student',
                                 first_name='Тимур', last_name='Ахметов')
        self.other = make_user('ls_other', role='student')

        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([self.student, self.other])
        # У группы должна быть своя работа: без неё история пустая, и
        # проверять «два числа вместо даты» было бы не на чем.
        group_work = Assignment.objects.create(name='Групповая ДЗ',
                                               author=self.tutor,
                                               group=self.group)
        group_work.students.set([self.student, self.other])
        AssignmentItem.objects.create(
            assignment=group_work, order=0,
            catalog_problem=make_problem('Условие группы'),
            points=Decimal('10'))

        self.lesson = StudentGroup.objects.create(
            name='Тимур Ахметов', teacher=self.tutor,
            kind=StudentGroup.Kind.INDIVIDUAL)
        self.lesson.students.set([self.student])

        self.work = Assignment.objects.create(name='Занятие 1',
                                              author=self.tutor,
                                              group=self.lesson)
        self.work.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'), points=Decimal('10'))
        self.sub = Submission.objects.create(
            student=self.student, assignment=self.work,
            problem_item=self.item, status='submitted')
        self.client.force_login(self.tutor)

    def _html(self, group):
        url = reverse('teacher:group_detail', args=[group.pk])
        return self.client.get(url + '?tab=overview').content.decode()

    def test_group_screen_is_unchanged(self):
        html = self._html(self.group)
        self.assertIn('Ученики × темы', html)
        self.assertIn('id="students-table"', html)
        self.assertIn('по группе', html)

    def test_individual_has_no_heatmap_and_no_students_table(self):
        # ⚠️ Ищем РАЗМЕТКУ: имя `students-table` стоит ещё и в скрипте
        # кликабельной строки, и по нему тест находил бы совпадение всегда.
        html = self._html(self.lesson)
        self.assertNotIn('Ученики × темы', html)
        self.assertNotIn('id="students-table"', html)
        self.assertNotIn('по группе', html)

    def test_individual_shows_the_student_in_the_header(self):
        html = self._html(self.lesson)
        self.assertIn('Тимур Ахметов', html)
        self.assertIn('индивидуально', html)

    def test_individual_shows_topic_progress_instead(self):
        resp = self.client.get(
            reverse('teacher:group_detail', args=[self.lesson.pk])
            + '?tab=overview')
        self.assertIn('progress', resp.context)
        self.assertIn('solo', resp.context)
        self.assertEqual(resp.context['solo'], self.student)
        self.assertIn('Прогресс по темам', resp.content.decode())

    def test_individual_shows_four_metric_cards(self):
        resp = self.client.get(
            reverse('teacher:group_detail', args=[self.lesson.pk])
            + '?tab=overview')
        for key in ('solo_open', 'solo_test', 'solo_minutes',
                    'solo_difficulty'):
            self.assertIn(key, resp.context, key)

    def test_history_shows_submitted_column(self):
        html = self._html(self.lesson)
        self.assertIn('Сдано', html)
        self.assertNotIn('Невовремя / не сдано', html)

    def test_group_history_keeps_two_numbers(self):
        html = self._html(self.group)
        self.assertIn('Невовремя / не сдано', html)


class SubmissionsShortcutTests(TestCase):
    """Список из одного ученика вырождается — ведём сразу к работе."""

    def setUp(self):
        from problems.models import Assignment, AssignmentItem, Submission

        self.tutor = make_user('sh_tutor', role='teacher')
        self.student = make_user('sh_student', role='student')
        self.lesson = StudentGroup.objects.create(
            name='Ученик', teacher=self.tutor,
            kind=StudentGroup.Kind.INDIVIDUAL)
        self.lesson.students.set([self.student])
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.lesson)
        self.work.students.add(self.student)
        item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'), points=Decimal('10'))
        self.sub = Submission.objects.create(
            student=self.student, assignment=self.work, problem_item=item,
            status='submitted')
        self.client.force_login(self.tutor)

    def _url(self):
        return reverse('teacher:group_submissions',
                       args=[self.lesson.pk, self.work.pk])

    def test_redirects_straight_to_the_work(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/submissions/%d/' % self.sub.pk, resp['Location'])

    def test_explicit_list_still_works(self):
        """Прямой адрес не ломаем: сводка остаётся рабочей поверхностью."""
        resp = self.client.get(self._url() + '?list=1')
        self.assertEqual(resp.status_code, 200)

    def test_group_is_not_redirected(self):
        group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        group.students.add(self.student)
        from problems.models import Assignment

        work = Assignment.objects.create(name='ДЗ2', author=self.tutor,
                                         group=group)
        work.students.add(self.student)
        resp = self.client.get(reverse('teacher:group_submissions',
                                       args=[group.pk, work.pk]))
        self.assertEqual(resp.status_code, 200)


class CommentVisibilityWordingTests(TestCase):
    """«Видно всей группе» обещает группу, которой нет."""

    def test_wording_changes_but_the_rule_does_not(self):
        from problems.models_platform import (ProblemComment,
                                              visibility_choices_for)

        group = dict(visibility_choices_for('tutor'))
        solo = dict(visibility_choices_for('tutor', individual=True))
        self.assertEqual(group[ProblemComment.Visibility.GROUP],
                         'видно всей группе')
        self.assertEqual(solo[ProblemComment.Visibility.GROUP],
                         'видно ученику')
        # Набор значений тот же — правило доступа не тронуто.
        self.assertEqual(set(group), set(solo))
