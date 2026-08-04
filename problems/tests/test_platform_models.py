"""
Тесты моделей платформы для репетиторов (Фазы 1–7).

Проверяем ровно то, что легко сломать и трудно заметить:
профиль создаётся сам, база не пускает битые связи, решение открывается
тогда и только тогда, когда должно, контрольная закрывается вовремя,
а таймер считает сервер, а не устройство ученика.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from problems.models import Assignment, Problem, StudentGroup, Submission, User
from problems.models_platform import (
    AnswerDraft,
    AssignmentItem,
    CustomProblem,
    ExamAttempt,
    LearningEvent,
    ProblemComment,
    SolutionVisibility,
    UserProfile,
)


def make_user(username, role='student', **kwargs):
    user = User.objects.create_user(username=username,
                                    password='test12345', **kwargs)
    profile = user.profile
    profile.role = role
    profile.save()
    return user


# ---------------------------------------------------------------------------
# Фаза 1 — профиль
# ---------------------------------------------------------------------------

class UserProfileTests(TestCase):

    def test_profile_created_automatically(self):
        """Профиль появляется сам при создании пользователя."""
        user = User.objects.create_user(username='newbie', password='x12345')
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertEqual(user.profile.role, UserProfile.Role.STUDENT)

    def test_profile_role_from_existing_user_role(self):
        """Преподаватель получает роль репетитора, а не ученика."""
        user = User.objects.create_user(username='t1', password='x12345',
                                        role='teacher')
        self.assertEqual(user.profile.role, UserProfile.Role.TUTOR)

    def test_profile_role_syncs_back_to_user(self):
        """Роль профиля подтягивает старое поле User.role — иначе
        teacher_required перестал бы пускать репетитора."""
        user = User.objects.create_user(username='t2', password='x12345')
        self.assertEqual(user.role, 'student')
        profile = user.profile
        profile.role = UserProfile.Role.TUTOR
        profile.save()
        user.refresh_from_db()
        self.assertEqual(user.role, 'teacher')

    def test_parent_is_not_a_student(self):
        """Родителю не достаются права ученика."""
        user = make_user('parent1', role='parent')
        user.refresh_from_db()
        self.assertEqual(user.role, 'viewer')

    def test_grade_validated(self):
        user = make_user('s_grade')
        profile = user.profile
        profile.grade = 12
        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_no_password_field_on_profile(self):
        """Пароль в профиле не хранится ни под каким именем."""
        names = {f.name for f in UserProfile._meta.get_fields()}
        self.assertFalse({n for n in names if 'password' in n or 'pass' == n})


# ---------------------------------------------------------------------------
# Фаза 3 — позиция задачи в домашке, ограничения БД
# ---------------------------------------------------------------------------

class AssignmentItemConstraintTests(TestCase):

    def setUp(self):
        self.tutor = make_user('tutor_c', role='tutor')
        self.assignment = Assignment.objects.create(name='ДЗ',
                                                    author=self.tutor)
        self.problem = Problem.objects.create(statement='Условие каталога')
        self.custom = CustomProblem.objects.create(
            owner=self.tutor, statement='Своё условие')

    def test_catalog_problem_ok(self):
        item = AssignmentItem.objects.create(assignment=self.assignment,
                                             catalog_problem=self.problem)
        self.assertFalse(item.is_custom)
        self.assertEqual(item.problem, self.problem)

    def test_custom_problem_ok(self):
        item = AssignmentItem.objects.create(assignment=self.assignment,
                                             custom_problem=self.custom)
        self.assertTrue(item.is_custom)

    def test_both_filled_is_rejected_by_database(self):
        """Две задачи в одной позиции — порча данных, ловим до записи."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AssignmentItem.objects.create(
                    assignment=self.assignment,
                    catalog_problem=self.problem,
                    custom_problem=self.custom)

    def test_none_filled_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AssignmentItem.objects.create(assignment=self.assignment)


# ---------------------------------------------------------------------------
# Фаза 5 — правила показа решения
# ---------------------------------------------------------------------------

class SolutionVisibilityTests(TestCase):

    def setUp(self):
        self.tutor = make_user('tutor_s', role='tutor')
        self.student = make_user('stud_s')
        self.other = make_user('stud_other')
        self.problem = Problem.objects.create(statement='Условие',
                                              solution='Решение каталога')
        self.now = timezone.now()

    def _item(self, mode, deadline=None, released=None):
        assignment = Assignment.objects.create(
            name='Работа', author=self.tutor, deadline=deadline)
        assignment.students.add(self.student, self.other)
        return AssignmentItem.objects.create(
            assignment=assignment, catalog_problem=self.problem,
            solution_visible_after=mode, solution_released_at=released)

    def test_tutor_always_sees(self):
        item = self._item(SolutionVisibility.NEVER)
        self.assertTrue(item.is_solution_visible_for(self.tutor))

    def test_never(self):
        item = self._item(SolutionVisibility.NEVER,
                          released=self.now - timedelta(days=1))
        self.assertFalse(item.is_solution_visible_for(self.student))

    def test_manual_closed_until_released(self):
        item = self._item(SolutionVisibility.MANUAL)
        self.assertFalse(item.is_solution_visible_for(self.student))
        item.solution_released_at = self.now - timedelta(minutes=1)
        item.save()
        self.assertTrue(item.is_solution_visible_for(self.student))

    def test_deadline_before_and_after(self):
        item = self._item(SolutionVisibility.DEADLINE,
                          deadline=self.now + timedelta(hours=2))
        self.assertFalse(item.is_solution_visible_for(self.student))
        item.assignment.deadline = self.now - timedelta(hours=2)
        item.assignment.save()
        item.refresh_from_db()
        self.assertTrue(item.is_solution_visible_for(self.student))

    def test_deadline_mode_without_deadline_stays_closed(self):
        """Случай, ради которого правило и написано: режим «после дедлайна»,
        а дедлайна нет. «После никогда» не наступает — значит закрыто,
        пока репетитор не откроет вручную."""
        item = self._item(SolutionVisibility.DEADLINE, deadline=None)
        self.assertFalse(item.is_solution_visible_for(self.student))
        item.solution_released_at = self.now - timedelta(minutes=1)
        item.save()
        self.assertTrue(item.is_solution_visible_for(self.student))

    def test_submit_mode_is_per_student(self):
        item = self._item(SolutionVisibility.SUBMIT)
        self.assertFalse(item.is_solution_visible_for(self.student))
        Submission.objects.create(
            student=self.student, assignment=item.assignment,
            problem=self.problem, problem_item=item,
            status='submitted', submitted_at=self.now)
        self.assertTrue(item.is_solution_visible_for(self.student))
        # Сосед по группе решение НЕ получает — он ещё не сдал.
        self.assertFalse(item.is_solution_visible_for(self.other))

    def test_override_beats_catalog(self):
        item = self._item(SolutionVisibility.MANUAL)
        self.assertEqual(item.solution_text, 'Решение каталога')
        item.solution_override = 'Моё решение'
        item.save()
        self.assertEqual(item.solution_text, 'Моё решение')
        self.assertEqual(item.solution_source, 'own')


# ---------------------------------------------------------------------------
# Фаза 6 — контрольные
# ---------------------------------------------------------------------------

class ExamOpenTests(TestCase):

    def setUp(self):
        self.tutor = make_user('tutor_e', role='tutor')
        self.student = make_user('stud_e')
        self.now = timezone.now()

    def _exam(self, mode, **kwargs):
        assignment = Assignment.objects.create(
            name='КР', author=self.tutor,
            kind=Assignment.Kind.EXAM, exam_mode=mode, **kwargs)
        assignment.students.add(self.student)
        return assignment

    def test_homework_always_open(self):
        hw = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                       deadline=self.now - timedelta(days=5))
        self.assertTrue(hw.is_open_for(self.student, self.now))

    def test_window_before_start(self):
        exam = self._exam(Assignment.ExamMode.WINDOW,
                          starts_at=self.now + timedelta(hours=1),
                          ends_at=self.now + timedelta(hours=2))
        is_open, reason = exam.open_state_for(self.student, self.now)
        self.assertFalse(is_open)
        self.assertIn('Начало', reason)

    def test_window_inside(self):
        exam = self._exam(Assignment.ExamMode.WINDOW,
                          starts_at=self.now - timedelta(minutes=5),
                          ends_at=self.now + timedelta(hours=1))
        self.assertTrue(exam.is_open_for(self.student, self.now))

    def test_window_after_end(self):
        exam = self._exam(Assignment.ExamMode.WINDOW,
                          starts_at=self.now - timedelta(hours=2),
                          ends_at=self.now - timedelta(hours=1))
        self.assertFalse(exam.is_open_for(self.student, self.now))

    def test_limit_before_due(self):
        exam = self._exam(Assignment.ExamMode.LIMIT,
                          due_at=self.now + timedelta(days=1),
                          duration_minutes=60)
        self.assertTrue(exam.is_open_for(self.student, self.now))

    def test_limit_after_due(self):
        exam = self._exam(Assignment.ExamMode.LIMIT,
                          due_at=self.now - timedelta(minutes=1),
                          duration_minutes=60)
        self.assertFalse(exam.is_open_for(self.student, self.now))

    def test_limit_closes_when_personal_time_ran_out(self):
        exam = self._exam(Assignment.ExamMode.LIMIT,
                          due_at=self.now + timedelta(days=1),
                          duration_minutes=60)
        attempt = ExamAttempt.start(exam, self.student, now=self.now)
        # Через 61 минуту личное время вышло, хотя срок сдачи ещё не настал.
        later = self.now + timedelta(minutes=61)
        self.assertFalse(exam.is_open_for(self.student, later))
        self.assertEqual(attempt.seconds_left(later), 0)


class ExamAttemptTests(TestCase):

    def setUp(self):
        self.tutor = make_user('tutor_a', role='tutor')
        self.student = make_user('stud_a')
        self.now = timezone.now()

    def test_expires_at_is_computed_by_server(self):
        """Ключевое: момент истечения считает СЕРВЕР от своего времени.
        Клиент не передаёт его и не может на него повлиять."""
        exam = Assignment.objects.create(
            name='КР', author=self.tutor, kind=Assignment.Kind.EXAM,
            exam_mode=Assignment.ExamMode.LIMIT, duration_minutes=45,
            due_at=self.now + timedelta(days=1))
        before = timezone.now()
        attempt = ExamAttempt.start(exam, self.student)
        after = timezone.now()
        self.assertIsNotNone(attempt.expires_at)
        self.assertGreaterEqual(attempt.expires_at,
                                before + timedelta(minutes=45))
        self.assertLessEqual(attempt.expires_at,
                             after + timedelta(minutes=45))

    def test_limit_never_outlives_due_date(self):
        """Старт за минуту до срока не даёт лишнего часа."""
        exam = Assignment.objects.create(
            name='КР', author=self.tutor, kind=Assignment.Kind.EXAM,
            exam_mode=Assignment.ExamMode.LIMIT, duration_minutes=60,
            due_at=timezone.now() + timedelta(minutes=1))
        attempt = ExamAttempt.start(exam, self.student)
        self.assertEqual(attempt.expires_at, exam.due_at)

    def test_window_expires_at_end_of_window(self):
        exam = Assignment.objects.create(
            name='КР', author=self.tutor, kind=Assignment.Kind.EXAM,
            exam_mode=Assignment.ExamMode.WINDOW,
            starts_at=self.now, ends_at=self.now + timedelta(hours=1))
        attempt = ExamAttempt.start(exam, self.student)
        self.assertEqual(attempt.expires_at, exam.ends_at)

    def test_second_start_returns_same_attempt(self):
        exam = Assignment.objects.create(
            name='КР', author=self.tutor, kind=Assignment.Kind.EXAM,
            exam_mode=Assignment.ExamMode.LIMIT, duration_minutes=30)
        first = ExamAttempt.start(exam, self.student)
        second = ExamAttempt.start(exam, self.student)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ExamAttempt.objects.count(), 1)

    def test_draft_survives_and_is_unique_per_item(self):
        exam = Assignment.objects.create(
            name='КР', author=self.tutor, kind=Assignment.Kind.EXAM,
            exam_mode=Assignment.ExamMode.LIMIT, duration_minutes=30)
        problem = Problem.objects.create(statement='Условие')
        item = AssignmentItem.objects.create(assignment=exam,
                                             catalog_problem=problem)
        attempt = ExamAttempt.start(exam, self.student)
        AnswerDraft.objects.create(attempt=attempt, problem_item=item,
                                   answer_draft='42')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AnswerDraft.objects.create(attempt=attempt, problem_item=item,
                                           answer_draft='43')
        self.assertEqual(
            AnswerDraft.objects.get(attempt=attempt,
                                    problem_item=item).answer_draft, '42')


# ---------------------------------------------------------------------------
# Фаза 2 — доступ к комментариям
# ---------------------------------------------------------------------------

class CommentVisibilityTests(TestCase):

    def setUp(self):
        self.tutor = make_user('tutor_k', role='tutor')
        self.a = make_user('stud_a_k')
        self.b = make_user('stud_b_k')
        self.group = StudentGroup.objects.create(name='Группа',
                                                 teacher=self.tutor)
        self.group.students.add(self.a, self.b)
        self.assignment = Assignment.objects.create(
            name='ДЗ', author=self.tutor, group=self.group)
        self.assignment.students.add(self.a, self.b)
        problem = Problem.objects.create(statement='Условие')
        self.item = AssignmentItem.objects.create(
            assignment=self.assignment, catalog_problem=problem)

        self.public = ProblemComment.objects.create(
            assignment=self.assignment, problem_item=self.item,
            author=self.tutor, text='Всем: смотрите на единицы',
            visibility=ProblemComment.Visibility.GROUP)
        self.private_a = ProblemComment.objects.create(
            assignment=self.assignment, problem_item=self.item,
            author=self.a, text='Я не понял пункт б',
            visibility=ProblemComment.Visibility.PRIVATE)
        self.reply_to_a = ProblemComment.objects.create(
            assignment=self.assignment, problem_item=self.item,
            author=self.tutor, recipient=self.a, text='Смотри формулу спроса',
            visibility=ProblemComment.Visibility.PRIVATE)

    def test_student_b_does_not_see_private_of_student_a(self):
        """Главная проверка: ученик Б не видит приватного вопроса ученика А."""
        visible = set(ProblemComment.objects.visible_for(self.b)
                      .values_list('pk', flat=True))
        self.assertIn(self.public.pk, visible)
        self.assertNotIn(self.private_a.pk, visible)
        self.assertNotIn(self.reply_to_a.pk, visible)

    def test_student_a_sees_own_and_reply(self):
        visible = set(ProblemComment.objects.visible_for(self.a)
                      .values_list('pk', flat=True))
        self.assertEqual(visible, {self.public.pk, self.private_a.pk,
                                   self.reply_to_a.pk})

    def test_tutor_sees_everything(self):
        visible = set(ProblemComment.objects.visible_for(self.tutor)
                      .values_list('pk', flat=True))
        self.assertEqual(len(visible), 3)

    def test_soft_deleted_hidden_from_everyone(self):
        self.public.is_deleted = True
        self.public.save()
        self.assertNotIn(
            self.public.pk,
            set(ProblemComment.objects.visible_for(self.tutor)
                .values_list('pk', flat=True)))


# ---------------------------------------------------------------------------
# Фаза 7 — логирование не имеет права ломать основной сценарий
# ---------------------------------------------------------------------------

class EventLoggingTests(TestCase):

    def setUp(self):
        self.student = make_user('stud_log')
        self.problem = Problem.objects.create(statement='Условие',
                                              difficulty=3)

    def test_event_written(self):
        from problems.event_log import log_problem_event
        event = log_problem_event('catalog', 'opened', self.student,
                                  self.problem)
        self.assertIsNotNone(event)
        self.assertEqual(event.difficulty, 3)
        self.assertEqual(LearningEvent.objects.count(), 1)

    def test_broken_logging_does_not_break_the_flow(self):
        """Падение записи события не должно ронять сценарий пользователя."""
        from problems import event_log
        event = event_log.log_event('catalog', 'opened',
                                    user=self.student,
                                    nonexistent_field='бум')
        self.assertIsNone(event)
        self.assertEqual(LearningEvent.objects.count(), 0)

    def test_anonymous_event_keeps_session_key(self):
        from problems.event_log import log_event
        event = log_event('game', 'solved', user=None,
                          session_key='abc123')
        self.assertIsNone(event.user)
        self.assertEqual(event.session_key, 'abc123')

    def test_link_anonymous_events_command(self):
        from django.core.management import call_command
        from io import StringIO
        LearningEvent.objects.create(source='game', event_type='solved',
                                     user=self.student, session_key='k1')
        LearningEvent.objects.create(source='game', event_type='failed',
                                     user=None, session_key='k1')
        call_command('link_anonymous_events', stdout=StringIO())
        self.assertEqual(
            LearningEvent.objects.filter(user=self.student).count(), 2)


# ---------------------------------------------------------------------------
# Фаза 4 — сохранённое
# ---------------------------------------------------------------------------

class SavedProblemTests(TestCase):

    def test_cannot_save_the_same_problem_twice(self):
        from problems.models_platform import SavedProblem
        user = make_user('saver')
        problem = Problem.objects.create(statement='Условие')
        SavedProblem.objects.create(owner=user, catalog_problem=problem)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SavedProblem.objects.create(owner=user,
                                            catalog_problem=problem)

    def test_saved_problem_needs_exactly_one_link(self):
        from problems.models_platform import SavedProblem
        user = make_user('saver2')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SavedProblem.objects.create(owner=user)


class CustomProblemTests(TestCase):

    def test_tolerance_default_is_exact(self):
        user = make_user('author_cp', role='tutor')
        problem = CustomProblem.objects.create(owner=user, statement='Условие')
        self.assertEqual(problem.answer_tolerance, Decimal('0'))
        self.assertFalse(problem.is_test)

    def test_test_kinds_are_marked_as_tests(self):
        user = make_user('author_cp2', role='tutor')
        for kind in ('tf', 'single', 'multiple'):
            problem = CustomProblem.objects.create(
                owner=user, statement='Условие', kind=kind)
            self.assertTrue(problem.is_test, kind)
