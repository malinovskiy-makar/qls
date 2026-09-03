"""Тренировочный режим: гость, таймер, перерешивание и совпадение проверки.

⚠️ ГЛАВНЫЙ ТЕСТ ФАЙЛА — `SameGradingTests`. Всё остальное можно починить
починкой экрана; расхождение проверки чинится только тем, что его заметят.
Ответ, верный в тренировке и неверный в контрольной, всплыл бы жалобой
школьника через месяцы.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from olympiads import training_engine as engine
from olympiads.models import (Olympiad, OlympiadVariant, TrainingAttempt,
                              TrainingDraft)
from problems.models import OlympiadRef, Problem

User = get_user_model()

EVENT = 'test-event-1'


def make_variant(duration_minutes=60, problem_count=2, event_id=EVENT):
    olympiad = Olympiad.objects.create(
        slug='vs', name_full='Тестовая', name_short='ТЕСТ',
        organizer='Никто', kind=Olympiad.Kind.VSOSH)
    return OlympiadVariant.objects.create(
        olympiad=olympiad, year=2026, grade=11,
        problem_count=problem_count, duration_minutes=duration_minutes,
        ref_event_id=event_id)


def make_problem(number, answer='42', problem_type='задача'):
    problem = Problem.objects.create(
        title='Задача %s' % number, statement='Условие %s' % number,
        answer=answer, solution='Разбор %s' % number,
        problem_type=problem_type)
    OlympiadRef.objects.create(
        problem=problem, event_id=EVENT, source_site='solvehub',
        olympiad_slug='vs', number=str(number), record_id='r%s' % number)
    return problem


class GuestTests(TestCase):
    """Решать может любой. Вход не требуется ни на одном экране."""

    def setUp(self):
        self.variant = make_variant()
        self.p1 = make_problem(1)
        self.p2 = make_problem(2)
        self.url = lambda name: reverse('olympiads:' + name,
                                        args=['vs', self.variant.pk])

    def test_guest_opens_intro(self):
        response = self.client.get(self.url('training_intro'))
        self.assertEqual(response.status_code, 200)

    def test_guest_answer_survives_page_reload(self):
        """Обрыв и обновление страницы НЕ теряют написанное.

        Ради этого черновики вообще существуют; у гостя единственный адрес
        попытки — ключ сессии, и без него ответ исчезал бы при F5.
        """
        self.client.post(self.url('training_start'), {'timer': '1'})
        attempt = TrainingAttempt.objects.get()
        item = engine.variant_items(self.variant)[0]
        response = self.client.post(
            self.url('training_autosave'),
            data={'item_id': item.pk, 'answer': 'мой ответ'},
            content_type='application/json')
        self.assertEqual(response.status_code, 200)

        again = self.client.get(self.url('training_take'))
        self.assertContains(again, 'мой ответ')
        self.assertTrue(attempt.is_guest)

    def test_guest_result_is_shown_but_not_tied_to_any_user(self):
        """Гость видит разбор, но в базе его попытка ни за кем не числится."""
        self.client.post(self.url('training_start'), {'timer': '0'})
        self.client.post(self.url('training_finish'), {})
        response = self.client.get(self.url('training_result'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            TrainingAttempt.objects.filter(user__isnull=False).count(), 0)

    def test_logged_in_attempt_is_tied_to_the_user(self):
        user = User.objects.create_user('petya', password='x')
        self.client.force_login(user)
        self.client.post(self.url('training_start'), {'timer': '1'})
        attempt = TrainingAttempt.objects.get()
        self.assertEqual(attempt.user_id, user.pk)
        self.assertFalse(attempt.is_guest)

    def test_retake_is_unlimited(self):
        """Перерешивать можно сколько угодно раз — так решил владелец."""
        self.client.post(self.url('training_start'), {'timer': '1'})
        self.client.post(self.url('training_finish'), {})
        self.client.post(self.url('training_start'), {'timer': '1'})
        self.assertEqual(TrainingAttempt.objects.count(), 2)


class TimerTests(TestCase):

    def setUp(self):
        self.variant = make_variant()
        make_problem(1)

    def test_expired_attempt_is_submitted_at_expiry_not_at_notice(self):
        """⚠️ Время сдачи — момент КОНЦА ВРЕМЕНИ, а не «когда заметили».

        Школьник закрыл вкладку и вернулся через сутки: работа обязана
        числиться сданной тогда, когда кончилось время, иначе в журнале
        стоит три часа ночи.
        """
        attempt = engine.start_attempt(self.variant, None, 'sess', True)
        expires = timezone.now() - timedelta(hours=5)
        TrainingAttempt.objects.filter(pk=attempt.pk).update(
            expires_at=expires)
        attempt.refresh_from_db()

        self.assertTrue(engine.finalize_if_expired(attempt))
        attempt.refresh_from_db()
        self.assertEqual(attempt.submitted_at, expires)
        self.assertTrue(attempt.is_auto_submitted)

    def test_attempt_without_timer_never_closes(self):
        attempt = engine.start_attempt(self.variant, None, 'sess', False)
        self.assertIsNone(attempt.expires_at)
        self.assertIsNone(engine.seconds_remaining(attempt))
        self.assertFalse(engine.finalize_if_expired(
            attempt, timezone.now() + timedelta(days=365)))
        attempt.refresh_from_db()
        self.assertIsNone(attempt.submitted_at)

    def test_timer_requires_known_duration(self):
        """Тур без известной длительности «на время» не запускается."""
        self.variant.duration_minutes = None
        self.variant.save(update_fields=['duration_minutes'])
        with self.assertRaises(engine.TrainingError):
            engine.start_attempt(self.variant, None, 'sess', True)


class DraftRaceTests(TestCase):
    """Гонка двух сохранений — страница, открытая в двух вкладках."""

    def setUp(self):
        self.variant = make_variant()
        self.problem = make_problem(1)

    def test_second_save_updates_instead_of_crashing(self):
        """Второе сохранение того же поля обязано ОБНОВИТЬ, а не упасть.

        ⚠️ Без лечения в `save_draft` второй INSERT ломается об уникальность
        и решающий получает 500 на сохранении своей работы. Повторяем
        запись через прямой `create`, а потом сохраняем ещё раз: если
        лечение убрать, `update_or_create` сломается ровно так же.
        """
        attempt = engine.start_attempt(self.variant, None, 'sess', False)
        TrainingDraft.objects.create(attempt=attempt, problem=self.problem,
                                     part=None, answer_draft='первый')
        engine.save_draft(attempt, self.problem, answer='второй')

        drafts = TrainingDraft.objects.filter(attempt=attempt,
                                              problem=self.problem)
        self.assertEqual(drafts.count(), 1)
        self.assertEqual(drafts.first().answer_draft, 'второй')

    def test_answer_and_solution_do_not_erase_each_other(self):
        """`None` = «не трогать поле», иначе решение стёрлось бы ответом."""
        attempt = engine.start_attempt(self.variant, None, 'sess', False)
        engine.save_draft(attempt, self.problem, solution='ход решения')
        engine.save_draft(attempt, self.problem, answer='7')
        draft = TrainingDraft.objects.get(attempt=attempt)
        self.assertEqual(draft.solution_draft, 'ход решения')
        self.assertEqual(draft.answer_draft, '7')


class SameGradingTests(TestCase):
    """ГЛАВНЫЙ ТЕСТ: тренировка и `grade_submission` дают ОДНО И ТО ЖЕ.

    Проверку копировать запрещено; этот тест сторожит, что её и не
    скопировали — на тех же данных результат обязан совпасть до балла.
    """

    def setUp(self):
        self.variant = make_variant()
        # Тест каталога: автопроверка работает без утверждения эталона.
        self.problem = make_problem(1, answer='б', problem_type='тест')

    def _grade_directly(self, answer):
        """Что скажет `grade_submission`, если позвать её напрямую."""
        from problems.models import Submission, TeacherFeedback
        from student.views import grade_submission

        item = engine.variant_items(self.variant)[0]
        assignment = engine.training_assignment(self.variant)
        submission = Submission.objects.create(
            student=engine.service_user(), assignment=assignment,
            problem_item=item, problem=self.problem, status='submitted',
            submitted_answer=answer)
        grade_submission(submission, item)
        feedback = TeacherFeedback.objects.filter(
            submission=submission).first()
        score = None if feedback is None or feedback.score is None \
            else float(feedback.score)
        submission.delete()
        return score

    def _grade_through_training(self, answer):
        attempt = engine.start_attempt(self.variant, None, 'sess', False)
        engine.save_draft(attempt, self.problem, answer=answer)
        engine.submit_attempt(attempt)
        attempt.refresh_from_db()
        return float(attempt.score) if attempt.score is not None else None

    def test_correct_answer_scores_the_same(self):
        self.assertEqual(self._grade_through_training('б'),
                         self._grade_directly('б'))

    def test_wrong_answer_scores_the_same(self):
        self.assertEqual(self._grade_through_training('в'),
                         self._grade_directly('в'))

    def test_correct_and_wrong_actually_differ(self):
        """Страховка от «оба None»: тест без неё зелен на сломанной проверке."""
        self.assertNotEqual(self._grade_directly('б'), self._grade_directly('в'))


class NoTraceInProblemsTests(TestCase):
    """От тренировавшегося в `problems` не остаётся ни одной записи.

    Иначе тренировка попала бы в опыт и в серию дней: и то и другое
    считается по `Submission.student` без сужения по работе.
    """

    def setUp(self):
        self.variant = make_variant()
        self.problem = make_problem(1, answer='б', problem_type='тест')

    def test_grading_leaves_no_submission(self):
        from problems.models import PartAnswer, Submission, TeacherFeedback

        user = User.objects.create_user('masha', password='x')
        attempt = engine.start_attempt(self.variant, user, '', False)
        engine.save_draft(attempt, self.problem, answer='б')
        engine.submit_attempt(attempt)

        self.assertEqual(Submission.objects.count(), 0)
        self.assertEqual(TeacherFeedback.objects.count(), 0)
        self.assertEqual(PartAnswer.objects.count(), 0)
        # А балл при этом посчитан — проверка действительно отработала.
        attempt.refresh_from_db()
        self.assertGreater(float(attempt.score), 0)

    def test_training_assignment_is_invisible_to_tutors(self):
        """Служебная работа не попадает ни в один список репетитора."""
        from problems.models import Assignment

        assignment = engine.training_assignment(self.variant)
        tutor = User.objects.create_user('teach', password='x', role='teacher')
        self.assertEqual(
            Assignment.objects.filter(author=tutor).count(), 0)
        self.assertEqual(assignment.students.count(), 0)
        self.assertIsNone(assignment.group)
        self.assertFalse(engine.service_user().is_active)


class UnlinkedVariantTests(TestCase):

    def test_variant_without_problems_is_not_trainable(self):
        variant = make_variant(event_id='')
        with self.assertRaises(engine.TrainingError):
            engine.variant_items(variant)
        response = self.client.get(
            reverse('olympiads:training_intro', args=['vs', variant.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Задания ещё не привязаны')


class CleanupTests(TestCase):

    def setUp(self):
        self.variant = make_variant()
        make_problem(1)

    def _aged(self, attempt, days):
        TrainingAttempt.objects.filter(pk=attempt.pk).update(
            started_at=timezone.now() - timedelta(days=days))

    def test_old_guest_attempts_are_removed_but_users_are_not(self):
        from django.core.management import call_command

        user = User.objects.create_user('kolya', password='x')
        guest = engine.start_attempt(self.variant, None, 'sess', False)
        mine = engine.start_attempt(self.variant, user, '', False)
        self._aged(guest, 30)
        self._aged(mine, 30)

        call_command('cleanup_training_attempts', verbosity=0)
        self.assertFalse(TrainingAttempt.objects.filter(pk=guest.pk).exists())
        self.assertTrue(TrainingAttempt.objects.filter(pk=mine.pk).exists())

    def test_dry_run_deletes_nothing(self):
        from django.core.management import call_command

        guest = engine.start_attempt(self.variant, None, 'sess', False)
        self._aged(guest, 30)
        call_command('cleanup_training_attempts', dry_run=True, verbosity=0)
        self.assertTrue(TrainingAttempt.objects.filter(pk=guest.pk).exists())

    def test_fresh_guest_attempt_is_kept(self):
        guest = engine.start_attempt(self.variant, None, 'sess', False)
        from django.core.management import call_command
        call_command('cleanup_training_attempts', verbosity=0)
        self.assertTrue(TrainingAttempt.objects.filter(pk=guest.pk).exists())
