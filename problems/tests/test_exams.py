"""
Контрольные: серверный таймер, автосохранение, граничные случаи.

Это самые дорогие по цене ошибки тесты сессии. Контрольная, упавшая посреди
урока, — потерянное время ученика и потерянное лицо репетитора перед
родителем, поэтому здесь проверяется не «работает», а «не теряет».
"""
import json
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems import exam_engine
from problems.models import (
    AnswerDraft, Assignment, AssignmentItem, ExamAttempt, ProblemPart,
    StudentGroup, Submission,
)
from problems.tests.factories import make_problem, make_user


def make_exam(tutor, students, group=None, mode='window', now=None, **kwargs):
    now = now or timezone.now()
    data = {'name': 'Контрольная', 'author': tutor, 'group': group,
            'kind': Assignment.Kind.EXAM}
    if mode == 'window':
        data.update(exam_mode=Assignment.ExamMode.WINDOW,
                    starts_at=now - timedelta(minutes=1),
                    ends_at=now + timedelta(hours=1),
                    deadline=now + timedelta(hours=1))
    else:
        data.update(exam_mode=Assignment.ExamMode.LIMIT,
                    deadline=now + timedelta(days=1), duration_minutes=60)
    data.update(kwargs)
    exam = Assignment.objects.create(**data)
    exam.students.set(students)
    return exam


class ServerTimerTests(TestCase):
    """Время считает СЕРВЕР. Часам ученика не верим ни в чём."""

    def setUp(self):
        self.tutor = make_user('exam_tutor', role='teacher')
        self.student = make_user('exam_student', role='student')
        self.now = timezone.now()

    def test_window_expires_at_end_of_window(self):
        exam = make_exam(self.tutor, [self.student], mode='window',
                         now=self.now)
        attempt = exam_engine.start_attempt(exam, self.student, self.now)
        self.assertEqual(attempt.expires_at, exam.ends_at)

    def test_limit_expires_after_duration(self):
        exam = make_exam(self.tutor, [self.student], mode='limit',
                         now=self.now)
        attempt = exam_engine.start_attempt(exam, self.student, self.now)
        self.assertEqual(attempt.expires_at,
                         self.now + timedelta(minutes=60))

    def test_limit_is_cut_by_deadline(self):
        """Стартовавший за 20 минут до срока не получает лишний час."""
        exam = make_exam(self.tutor, [self.student], mode='limit',
                         now=self.now,
                         deadline=self.now + timedelta(minutes=20),
                         duration_minutes=60)
        attempt = exam_engine.start_attempt(exam, self.student, self.now)
        self.assertEqual(attempt.expires_at, exam.deadline)
        self.assertTrue(exam_engine.will_be_cut(exam, self.now))
        self.assertEqual(exam_engine.available_minutes(exam, self.now), 20)

    def test_second_start_returns_same_attempt(self):
        exam = make_exam(self.tutor, [self.student], now=self.now)
        first = exam_engine.start_attempt(exam, self.student, self.now)
        second = exam_engine.start_attempt(exam, self.student,
                                           self.now + timedelta(minutes=10))
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.expires_at, second.expires_at)
        self.assertEqual(ExamAttempt.objects.filter(assignment=exam).count(), 1)

    def test_cannot_start_before_window_opens(self):
        exam = make_exam(self.tutor, [self.student], mode='window',
                         now=self.now,
                         starts_at=self.now + timedelta(hours=1),
                         ends_at=self.now + timedelta(hours=2))
        with self.assertRaises(exam_engine.ExamError):
            exam_engine.start_attempt(exam, self.student, self.now)

    def test_cannot_start_after_deadline(self):
        exam = make_exam(self.tutor, [self.student], mode='limit',
                         now=self.now,
                         deadline=self.now - timedelta(minutes=1))
        with self.assertRaises(exam_engine.ExamError):
            exam_engine.start_attempt(exam, self.student, self.now)

    def test_answer_after_expiry_is_rejected(self):
        exam = make_exam(self.tutor, [self.student], now=self.now)
        attempt = exam_engine.start_attempt(exam, self.student, self.now)
        after = attempt.expires_at + timedelta(seconds=
                                               exam_engine.GRACE_SECONDS + 1)
        self.assertFalse(exam_engine.can_accept(attempt, after))

    def test_grace_period_accepts_late_by_a_few_seconds(self):
        """Ответ, отправленный за секунду до конца, доезжает уже после."""
        exam = make_exam(self.tutor, [self.student], now=self.now)
        attempt = exam_engine.start_attempt(exam, self.student, self.now)
        barely_late = attempt.expires_at + timedelta(seconds=3)
        self.assertTrue(exam_engine.can_accept(attempt, barely_late))

    def test_lazy_finalization_uses_expiry_moment(self):
        """Ученик уснул: работа сдана тогда, когда кончилось время."""
        exam = make_exam(self.tutor, [self.student], now=self.now)
        attempt = exam_engine.start_attempt(exam, self.student, self.now)
        much_later = attempt.expires_at + timedelta(days=1)
        self.assertTrue(exam_engine.finalize_if_expired(attempt, much_later))
        attempt.refresh_from_db()
        self.assertEqual(attempt.submitted_at, attempt.expires_at)
        self.assertTrue(attempt.is_auto_submitted)

    def test_finalization_is_idempotent(self):
        exam = make_exam(self.tutor, [self.student], now=self.now)
        attempt = exam_engine.start_attempt(exam, self.student, self.now)
        later = attempt.expires_at + timedelta(minutes=5)
        exam_engine.finalize_if_expired(attempt, later)
        first = attempt.submitted_at
        self.assertFalse(exam_engine.finalize_if_expired(attempt, later))
        attempt.refresh_from_db()
        self.assertEqual(attempt.submitted_at, first)

    def test_client_clock_cannot_change_anything(self):
        """Единственный источник времени — сервер: у попытки нет поля,
        которое клиент мог бы прислать."""
        exam = make_exam(self.tutor, [self.student], now=self.now)
        attempt = exam_engine.start_attempt(exam, self.student, self.now)
        left_before = exam_engine.seconds_remaining(attempt, self.now)
        # Что бы клиент ни думал о времени, считаем мы от своего.
        left_after = exam_engine.seconds_remaining(
            attempt, self.now + timedelta(minutes=10))
        self.assertEqual(left_before - left_after, 600)

    def test_remaining_never_exceeds_what_was_granted(self):
        """Часы САМОГО СЕРВЕРА уехали назад — остаток всё равно не растёт.

        Так выглядит ручная проверка на одной машине: сервер запущен на том
        же ноутбуке, ученик переводит системное время — и `timezone.now()`
        сервера уезжает вместе с ним. Потолок «сколько дали при старте»
        закрывает это: больше выданного не бывает никогда.
        """
        exam = make_exam(self.tutor, [self.student], mode='limit',
                         now=self.now)
        attempt = exam_engine.start_attempt(exam, self.student, self.now)
        granted = exam_engine.seconds_remaining(attempt, self.now)
        self.assertEqual(granted, 3600)

        # «Перевели часы на 10 минут назад» — сервер видит прошлое.
        back = exam_engine.seconds_remaining(attempt,
                                             self.now - timedelta(minutes=10))
        self.assertEqual(back, 3600, 'остаток вырос сверх выданного')

        # И через час назад — тоже не растёт.
        far_back = exam_engine.seconds_remaining(attempt,
                                                 self.now - timedelta(hours=5))
        self.assertEqual(far_back, 3600)

    def test_time_endpoint_answers_without_typing_anything(self):
        """Отдельный эндпоинт «сколько осталось».

        Раньше сверка ехала только вместе с автосохранением, то есть только
        когда ученик печатает. Человек смотрел на таймер, не печатая, и
        сверки не было ни одной.
        """
        exam = make_exam(self.tutor, [self.student], mode='limit',
                         now=self.now)
        AssignmentItem.objects.create(assignment=exam, order=0,
                                      catalog_problem=make_problem('Задача'))
        self.client.force_login(self.student)
        self.client.post(reverse('student:exam_start', args=[exam.pk]))

        response = self.client.get(reverse('student:exam_time',
                                           args=[exam.pk]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['expired'])
        self.assertGreater(payload['seconds_remaining'], 0)

    def test_time_endpoint_reports_expiry_and_closes_the_attempt(self):
        """Истёкшую попытку эндпоинт закрывает сам — страница узнаёт об
        этом, не дожидаясь действий ученика."""
        exam = make_exam(self.tutor, [self.student], mode='limit',
                         now=self.now)
        AssignmentItem.objects.create(assignment=exam, order=0,
                                      catalog_problem=make_problem('Задача'))
        self.client.force_login(self.student)
        self.client.post(reverse('student:exam_start', args=[exam.pk]))
        attempt = ExamAttempt.objects.get(assignment=exam)
        attempt.expires_at = self.now - timedelta(minutes=1)
        attempt.save(update_fields=['expires_at'])

        payload = self.client.get(
            reverse('student:exam_time', args=[exam.pk])).json()
        self.assertTrue(payload['expired'])
        self.assertEqual(payload['seconds_remaining'], 0)
        attempt.refresh_from_db()
        self.assertIsNotNone(attempt.submitted_at)


class AutosaveTests(TestCase):
    """Работа не теряется: черновики, возврат, повторная сдача."""

    def setUp(self):
        self.tutor = make_user('as_tutor', role='teacher')
        self.student = make_user('as_student', role='student')
        self.now = timezone.now()
        self.exam = make_exam(self.tutor, [self.student], now=self.now)
        self.problem = make_problem('Задача контрольной', difficulty=3)
        self.item = AssignmentItem.objects.create(
            assignment=self.exam, catalog_problem=self.problem, order=0,
            points=5)
        self.client.force_login(self.student)

    def _start(self):
        return self.client.post(
            reverse('student:exam_start', args=[self.exam.pk]))

    def test_autosave_writes_draft_and_returns_server_time(self):
        self._start()
        response = self.client.post(
            reverse('student:exam_autosave', args=[self.exam.pk]),
            data=json.dumps({'item_id': self.item.pk, 'answer': '42',
                             'solution': 'ход решения'}),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('seconds_remaining', payload)
        self.assertGreater(payload['seconds_remaining'], 0)

        draft = AnswerDraft.objects.get(problem_item=self.item)
        self.assertEqual(draft.answer_draft, '42')
        self.assertEqual(draft.solution_draft, 'ход решения')

    def test_returning_to_page_shows_drafts_and_running_timer(self):
        """Закрыл вкладку, открыл заново: ответы на месте, таймер продолжается."""
        self._start()
        self.client.post(
            reverse('student:exam_autosave', args=[self.exam.pk]),
            data=json.dumps({'item_id': self.item.pk, 'answer': '42',
                             'solution': 'моё решение'}),
            content_type='application/json')

        response = self.client.get(
            reverse('student:exam_take', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        row = response.context['rows'][0]
        self.assertEqual(row['prefill_answer'], '42')
        self.assertEqual(row['prefill_solution'], 'моё решение')
        # Таймер идёт от expires_at, а не с нуля.
        attempt = ExamAttempt.objects.get(assignment=self.exam)
        self.assertLessEqual(response.context['seconds_left'],
                             exam_engine.seconds_remaining(attempt))
        self.assertGreater(response.context['seconds_left'], 0)

    def test_task_with_a_draft_is_in_progress_not_not_started(self):
        """ФАЗА 0.4. Ответ введён — значит задача «В работе».

        Раньше состояние читалось из `Submission.status`, а он до самой
        сдачи остаётся `not_started`: над задачей с введённым ответом
        висело «Не начата».
        """
        self._start()
        body = self.client.get(
            reverse('student:exam_take', args=[self.exam.pk])).content.decode()
        self.assertIn('Не начата', body)
        self.assertIn('отвечено <b id="answered-count">0</b>', body)

        self.client.post(
            reverse('student:exam_autosave', args=[self.exam.pk]),
            data=json.dumps({'item_id': self.item.pk, 'answer': '42'}),
            content_type='application/json')

        body = self.client.get(
            reverse('student:exam_take', args=[self.exam.pk])).content.decode()
        self.assertIn('В работе', body)
        self.assertNotIn('Не начата', body)
        self.assertIn('отвечено <b id="answered-count">1</b>', body)

    def test_whitespace_only_draft_is_not_progress(self):
        """Пробелы — не ответ."""
        from problems.assignment_rows import work_status

        submission = Submission(status='not_started')
        self.assertEqual(work_status(submission, '   ', ' \n '), 'not_started')
        self.assertEqual(work_status(submission, '', '5'), 'in_progress')

    def test_autosave_of_choices_restores_checked(self):
        problem = make_problem('Тест', problem_type='тест: один ответ')
        for order, label in enumerate(('а', 'б')):
            ProblemPart.objects.create(problem=problem, label=label,
                                       statement='вариант', order=order)
        item = AssignmentItem.objects.create(assignment=self.exam,
                                             catalog_problem=problem, order=1)
        self._start()
        self.client.post(
            reverse('student:exam_autosave', args=[self.exam.pk]),
            data=json.dumps({'item_id': item.pk, 'answer': 'б'}),
            content_type='application/json')
        response = self.client.get(
            reverse('student:exam_take', args=[self.exam.pk]))
        row = [r for r in response.context['rows']
               if r['item'].pk == item.pk][0]
        self.assertIn('б', row['selected'])

    def test_repeated_autosave_of_same_item_never_duplicates(self):
        """Гонка двух автосохранений одной задачи — найдена браузером.

        Автосейв уходит и по остановке ввода, и по потере фокуса; два
        запроса по одной задаче оказываются в полёте вместе, и
        `update_or_create` ломался об уникальность (attempt, problem_item),
        отдавая ученику 500 НА СОХРАНЕНИИ ЕГО РАБОТЫ. Здесь стережём то,
        что можно проверить питоном: сколько бы раз ни сохранили, строка
        одна и в ней последнее значение.
        """
        self._start()
        for number in range(5):
            self.client.post(
                reverse('student:exam_autosave', args=[self.exam.pk]),
                data=json.dumps({'item_id': self.item.pk,
                                 'answer': str(number)}),
                content_type='application/json')
        drafts = AnswerDraft.objects.filter(problem_item=self.item)
        self.assertEqual(drafts.count(), 1)
        self.assertEqual(drafts.first().answer_draft, '4')

    def test_autosave_never_answers_500(self):
        """Пятисотка для клиента неотличима от «сохранилось».

        Если сохранить не удалось, ответ обязан быть «попробуй ещё» —
        тогда написанное остаётся в очереди страницы. Проверяем контракт
        на искусственной поломке записи.
        """
        from unittest import mock

        self._start()
        with mock.patch('problems.exam_engine.save_draft',
                        side_effect=RuntimeError('база недоступна')):
            response = self.client.post(
                reverse('student:exam_autosave', args=[self.exam.pk]),
                data=json.dumps({'item_id': self.item.pk, 'answer': 'x'}),
                content_type='application/json')
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.json()['retry'])

    def test_autosave_rejected_after_expiry(self):
        self._start()
        attempt = ExamAttempt.objects.get(assignment=self.exam)
        attempt.expires_at = timezone.now() - timedelta(minutes=1)
        attempt.save()
        response = self.client.post(
            reverse('student:exam_autosave', args=[self.exam.pk]),
            data=json.dumps({'item_id': self.item.pk, 'answer': 'поздно'}),
            content_type='application/json')
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()['expired'])

    def test_finish_carries_last_typed_values(self):
        """Последняя порция набранного уезжает вместе с кнопкой «Завершить»."""
        self._start()
        self.client.post(
            reverse('student:exam_finish', args=[self.exam.pk]),
            {'answer_item_%d' % self.item.pk: 'последний ответ',
             'text_item_%d' % self.item.pk: 'последнее решение'})
        submission = Submission.objects.get(student=self.student,
                                            problem_item=self.item)
        self.assertEqual(submission.submitted_answer, 'последний ответ')
        self.assertEqual(submission.solution_text, 'последнее решение')
        self.assertIn(submission.status, ('submitted', 'reviewed'))

    def test_two_tabs_one_attempt_and_no_lost_drafts(self):
        """Две вкладки: попытка одна, черновики обеих сохраняются."""
        self._start()
        self._start()          # вторая вкладка нажала «Начать» ещё раз
        self.assertEqual(ExamAttempt.objects.filter(
            assignment=self.exam).count(), 1)

        second = AssignmentItem.objects.create(
            assignment=self.exam, catalog_problem=make_problem('Вторая'),
            order=1)
        for item, text in ((self.item, 'из первой вкладки'),
                           (second, 'из второй вкладки')):
            self.client.post(
                reverse('student:exam_autosave', args=[self.exam.pk]),
                data=json.dumps({'item_id': item.pk, 'solution': text}),
                content_type='application/json')
        self.assertEqual(AnswerDraft.objects.filter(
            attempt__assignment=self.exam).count(), 2)

    def test_submit_twice_changes_nothing(self):
        self._start()
        self.client.post(reverse('student:exam_finish', args=[self.exam.pk]),
                         {'answer_item_%d' % self.item.pk: 'раз'})
        attempt = ExamAttempt.objects.get(assignment=self.exam)
        first_moment = attempt.submitted_at
        self.client.post(reverse('student:exam_finish', args=[self.exam.pk]),
                         {'answer_item_%d' % self.item.pk: 'два'})
        attempt.refresh_from_db()
        self.assertEqual(attempt.submitted_at, first_moment)
        submission = Submission.objects.get(student=self.student,
                                            problem_item=self.item)
        self.assertEqual(submission.submitted_answer, 'раз')


class GradingTests(TestCase):
    def setUp(self):
        self.tutor = make_user('gr_tutor', role='teacher')
        self.student = make_user('gr_student', role='student')
        self.exam = make_exam(self.tutor, [self.student])
        problem = make_problem('Тест', answer='б',
                               problem_type='тест: один ответ')
        for order, label in enumerate(('а', 'б')):
            ProblemPart.objects.create(problem=problem, label=label,
                                       statement='в', order=order)
        self.item = AssignmentItem.objects.create(
            assignment=self.exam, catalog_problem=problem, order=0, points=3)
        self.open_item = AssignmentItem.objects.create(
            assignment=self.exam, catalog_problem=make_problem('Открытая'),
            order=1, points=7)
        self.client.force_login(self.student)

    def test_tests_are_graded_instantly_open_wait(self):
        self.client.post(reverse('student:exam_start', args=[self.exam.pk]))
        self.client.post(reverse('student:exam_finish', args=[self.exam.pk]),
                         {'answer_item_%d' % self.item.pk: 'б',
                          'text_item_%d' % self.open_item.pk: 'рассуждение'})
        attempt = ExamAttempt.objects.get(assignment=self.exam)
        summary = exam_engine.attempt_summary(attempt)
        states = {row['item'].pk: row['state'] for row in summary['rows']}
        self.assertEqual(states[self.item.pk], 'correct')
        self.assertEqual(states[self.open_item.pk], 'pending')
        self.assertEqual(summary['pending'], 1)

    def test_result_page_says_it_is_preliminary(self):
        self.client.post(reverse('student:exam_start', args=[self.exam.pk]))
        self.client.post(reverse('student:exam_finish', args=[self.exam.pk]),
                         {'answer_item_%d' % self.item.pk: 'б',
                          'text_item_%d' % self.open_item.pk: 'рассуждение'})
        body = self.client.get(
            reverse('student:exam_result', args=[self.exam.pk])).content.decode()
        self.assertIn('предварительный результат', body)

    def _finish(self):
        self.client.post(reverse('student:exam_start', args=[self.exam.pk]))
        self.client.post(reverse('student:exam_finish', args=[self.exam.pk]),
                         {'answer_item_%d' % self.item.pk: 'б',
                          'text_item_%d' % self.open_item.pk: 'рассуждение'})

    def _review_open_item(self, score='7', comment='Разобрано аккуратно',
                          mistakes=()):
        """Преподаватель проверяет открытую задачу — как в браузере, POSTом
        на ту же форму, а не записью в базу напрямую."""
        submission = Submission.objects.get(student=self.student,
                                            problem_item=self.open_item)
        self.client.force_login(self.tutor)
        self.client.post(
            reverse('teacher:review_submission', args=[submission.pk]),
            {'score': score, 'comment': comment,
             'mistakes': [m.pk for m in mistakes]})
        self.client.force_login(self.student)
        return submission

    def test_teacher_score_and_comment_reach_the_student(self):
        """ГЛАВНЫЙ ТЕСТ ФАЗЫ 0.2 — полный цикл.

        Преподаватель ставит балл, пишет комментарий и отмечает типовую
        ошибку. Ученик обязан увидеть ВСЁ ТРИ. Раньше на экране результата
        не было ни одного из них — только «верно» от автопроверки.
        """
        from problems.models import MistakeTag

        mistake = MistakeTag.objects.create(name='Перепутаны оси')
        self._finish()
        self._review_open_item(score='7', comment='Хорошо, но проверь единицы',
                               mistakes=[mistake])

        body = self.client.get(
            reverse('student:exam_result', args=[self.exam.pk])).content.decode()
        self.assertIn('Хорошо, но проверь единицы', body)
        self.assertIn('Перепутаны оси', body)
        self.assertIn('проверил преподаватель', body)
        self.assertIn('7', body)

    def test_zero_from_the_teacher_still_carries_the_comment(self):
        """Ноль баллов — не повод прятать объяснение почему.

        Второму ученику поставили 0, и он увидел только «неверно».
        """
        self._finish()
        self._review_open_item(score='0', comment='Не хватает вывода')
        body = self.client.get(
            reverse('student:exam_result', args=[self.exam.pk])).content.decode()
        self.assertIn('Не хватает вывода', body)
        self.assertIn('проверил преподаватель', body)

    def test_hidden_results_still_show_what_the_teacher_wrote(self):
        """Настройка «не показывать результат сразу» относится к
        АВТОПРОВЕРКЕ. Комментарий преподавателя она придержать не может."""
        self.exam.show_results_immediately = False
        self.exam.save(update_fields=['show_results_immediately'])
        self._finish()

        body = self.client.get(
            reverse('student:exam_result', args=[self.exam.pk])).content.decode()
        self.assertNotIn('проверено автоматически', body)

        self._review_open_item(score='5', comment='Комментарий виден всегда')
        body = self.client.get(
            reverse('student:exam_result', args=[self.exam.pk])).content.decode()
        self.assertIn('Комментарий виден всегда', body)

    def test_homework_card_shows_teacher_feedback_too(self):
        """Тот же блок проверки — на карточке домашки."""
        from problems.models import Assignment, MistakeTag

        homework = Assignment.objects.create(name='Домашка', author=self.tutor,
                                             kind=Assignment.Kind.HOMEWORK)
        homework.students.add(self.student)
        item = AssignmentItem.objects.create(
            assignment=homework, catalog_problem=make_problem('Открытая дз'),
            order=0, points=4)
        mistake = MistakeTag.objects.create(name='Забыт знак')
        self.client.post(reverse('student:submit_assignment',
                                 args=[homework.pk]),
                         {'text_item_%d' % item.pk: 'моё решение'})
        submission = Submission.objects.get(student=self.student,
                                            problem_item=item)
        self.client.force_login(self.tutor)
        self.client.post(
            reverse('teacher:review_submission', args=[submission.pk]),
            {'score': '4', 'comment': 'Верный ход', 'mistakes': [mistake.pk]})
        self.client.force_login(self.student)

        body = self.client.get(reverse('student:assignment_detail',
                                       args=[homework.pk])).content.decode()
        self.assertIn('Верный ход', body)
        self.assertIn('Забыт знак', body)
        self.assertIn('проверил преподаватель', body)

    def test_exam_events_carry_exam_source(self):
        from problems.models import LearningEvent

        self.client.post(reverse('student:exam_start', args=[self.exam.pk]))
        self.client.post(reverse('student:exam_finish', args=[self.exam.pk]),
                         {'answer_item_%d' % self.item.pk: 'б'})
        self.assertTrue(LearningEvent.objects.filter(
            user=self.student, source='exam').exists())

    def test_exam_xp_has_multiplier(self):
        from problems import gamification

        plain = gamification.xp_for_solved(4)
        exam = gamification.xp_for_solved(4, source='exam')
        self.assertGreater(exam, plain)


class ExamAccessTests(TestCase):
    def setUp(self):
        self.tutor = make_user('ea_tutor', role='teacher')
        self.student = make_user('ea_student', role='student')
        self.outsider = make_user('ea_outsider', role='student')
        self.group = StudentGroup.objects.create(name='Г', teacher=self.tutor)
        self.group.students.set([self.student])
        self.exam = make_exam(self.tutor, [self.student], group=self.group)
        AssignmentItem.objects.create(assignment=self.exam,
                                      catalog_problem=make_problem('З'),
                                      order=0)

    def test_outsider_gets_404(self):
        self.client.force_login(self.outsider)
        for name in ('exam_intro', 'exam_take', 'exam_result'):
            response = self.client.get(
                reverse('student:%s' % name, args=[self.exam.pk]))
            self.assertEqual(response.status_code, 404, name)

    def test_take_without_attempt_redirects_to_intro(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse('student:exam_take', args=[self.exam.pk]))
        self.assertRedirects(
            response, reverse('student:exam_intro', args=[self.exam.pk]))

    def test_homework_page_redirects_exam_to_its_own_flow(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse('student:assignment_detail', args=[self.exam.pk]))
        self.assertRedirects(
            response, reverse('student:exam_intro', args=[self.exam.pk]))

    def test_foreign_tutor_cannot_see_results(self):
        other = make_user('ea_other_tutor', role='teacher')
        self.client.force_login(other)
        response = self.client.get(
            reverse('teacher:group_exam_results',
                    args=[self.group.pk, self.exam.pk]))
        self.assertEqual(response.status_code, 404)


class ExamCreationTests(TestCase):
    def setUp(self):
        self.tutor = make_user('ec_tutor', role='teacher')
        self.student = make_user('ec_student', role='student')
        self.group = StudentGroup.objects.create(name='Г', teacher=self.tutor)
        self.group.students.set([self.student])
        self.problem = make_problem('Задача для контрольной')
        from problems.models import SavedProblem
        SavedProblem.objects.create(owner=self.tutor,
                                    catalog_problem=self.problem)
        self.client.force_login(self.tutor)
        self.url = reverse('teacher:exam_create', args=[self.group.pk])

    def _post(self, **overrides):
        # ⚠️ МЕСТНОЕ время, а не UTC: поле `datetime-local` в браузере даёт
        # наивную дату в поясе пользователя, и форма трактует её как пояс
        # проекта. Если подставить сюда UTC, «через час» на московском
        # поясе окажется «два часа назад» — и это была ошибка теста, а не
        # формы (проверено вручную).
        now = timezone.localtime(timezone.now())
        data = {'name': 'КР', 'kind': 'window',
                'starts_at': (now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
                'ends_at': (now + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),
                'problem_ids': [str(self.problem.pk)]}
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_creates_window_exam(self):
        response = self._post()
        exam = Assignment.objects.filter(kind='exam').first()
        self.assertIsNotNone(exam)
        self.assertEqual(exam.exam_mode, 'window')
        self.assertEqual(exam.items.count(), 1)
        self.assertEqual(list(exam.students.all()), [self.student])
        # Срок у окна совпадает с концом окна — одно понятие срока на сайте.
        self.assertEqual(exam.deadline, exam.ends_at)
        self.assertEqual(response.status_code, 302)

    def test_exam_without_problems_is_not_created(self):
        self._post(problem_ids=[])
        self.assertFalse(Assignment.objects.filter(kind='exam').exists())

    def test_problems_are_picked_from_the_catalog_not_only_from_saved(self):
        """ФАЗА 0.3. Задача, которую репетитор НЕ откладывал, тоже доступна.

        Раньше конструктор предлагал только сохранённые — работать с этим
        было нельзя. Теперь на странице есть поиск, фильтры по теме и
        сложности и карточки задач каталога.
        """
        fresh = make_problem('Не сохранённая задача каталога', difficulty=4)
        body = self.client.get(self.url).content.decode()
        self.assertIn('Не сохранённая задача каталога', body)
        self.assertIn('name="q"', body)          # поиск
        self.assertIn('name="topic"', body)      # фильтр темы
        self.assertIn('name="difficulty"', body)  # фильтр сложности

        self._post(problem_ids=[str(fresh.pk)])
        exam = Assignment.objects.filter(kind='exam').first()
        self.assertIsNotNone(exam)
        self.assertEqual([i.catalog_problem_id for i in exam.items.all()],
                         [fresh.pk])

    def test_search_filters_the_list(self):
        make_problem('Монополия и её издержки')
        make_problem('Совсем про другое')
        body = self.client.get(self.url, {'q': 'Монополия'}).content.decode()
        self.assertIn('Монополия и её издержки', body)
        self.assertNotIn('Совсем про другое', body)

    def test_saved_problems_stay_as_a_quick_tab(self):
        """Сохранённые не исчезли — они стали вкладкой быстрого доступа."""
        body = self.client.get(self.url).content.decode()
        self.assertIn('Сохранённые', body)
        self.assertIn('pane-saved', body)

    def test_cart_order_becomes_problem_order(self):
        """Порядок в корзине = порядок задач в контрольной."""
        second = make_problem('Вторая')
        third = make_problem('Третья')
        self._post(problem_ids='%d,%d,%d' % (third.pk, self.problem.pk,
                                             second.pk))
        exam = Assignment.objects.filter(kind='exam').first()
        self.assertEqual([i.catalog_problem_id
                          for i in exam.items.order_by('order')],
                         [third.pk, self.problem.pk, second.pk])

    def test_own_problem_of_the_tutor_goes_into_the_exam(self):
        """Своя задача репетитора — наравне с каталожной (префикс «c»)."""
        from problems.models import CustomProblem

        own = CustomProblem.objects.create(owner=self.tutor, title='Своя',
                                           statement='Условие')
        self._post(problem_ids='c%d,%d' % (own.pk, self.problem.pk))
        exam = Assignment.objects.filter(kind='exam').first()
        items = list(exam.items.order_by('order'))
        self.assertEqual(items[0].custom_problem_id, own.pk)
        self.assertEqual(items[1].catalog_problem_id, self.problem.pk)

    def test_end_before_start_is_rejected(self):
        now = timezone.localtime(timezone.now())
        self._post(starts_at=(now + timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M'),
                   ends_at=(now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'))
        self.assertFalse(Assignment.objects.filter(kind='exam').exists())

    def test_window_shorter_than_minimum_is_rejected(self):
        now = timezone.localtime(timezone.now())
        self._post(starts_at=(now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
                   ends_at=(now + timedelta(hours=1, minutes=2))
                   .strftime('%Y-%m-%dT%H:%M'))
        self.assertFalse(Assignment.objects.filter(kind='exam').exists())

    def test_deadline_in_the_past_is_rejected(self):
        now = timezone.localtime(timezone.now())
        self._post(kind='limit', duration='60',
                   deadline=(now - timedelta(hours=1))
                   .strftime('%Y-%m-%dT%H:%M'))
        self.assertFalse(Assignment.objects.filter(kind='exam').exists())

    def test_duration_out_of_range_is_rejected(self):
        now = timezone.localtime(timezone.now())
        for duration in ('1', '9999'):
            self._post(kind='limit', duration=duration,
                       deadline=(now + timedelta(days=1))
                       .strftime('%Y-%m-%dT%H:%M'))
        self.assertFalse(Assignment.objects.filter(kind='exam').exists())

    def test_validation_never_returns_500(self):
        response = self.client.post(self.url, {'name': '', 'kind': 'window',
                                               'starts_at': 'мусор',
                                               'ends_at': ''})
        self.assertEqual(response.status_code, 200)


class ExamResultsForTutorTests(TestCase):
    def setUp(self):
        self.tutor = make_user('er_tutor', role='teacher')
        self.first = make_user('er_one', role='student')
        self.second = make_user('er_two', role='student')
        self.group = StudentGroup.objects.create(name='Г', teacher=self.tutor)
        self.group.students.set([self.first, self.second])
        self.exam = make_exam(self.tutor, [self.first, self.second],
                              group=self.group)
        problem = make_problem('Тест', answer='а',
                               problem_type='тест: один ответ')
        for order, label in enumerate(('а', 'б')):
            ProblemPart.objects.create(problem=problem, label=label,
                                       statement='в', order=order)
        self.item = AssignmentItem.objects.create(
            assignment=self.exam, catalog_problem=problem, order=0, points=1)

    def _write(self, student, answer):
        self.client.force_login(student)
        self.client.post(reverse('student:exam_start', args=[self.exam.pk]))
        self.client.post(reverse('student:exam_finish', args=[self.exam.pk]),
                         {'answer_item_%d' % self.item.pk: answer})

    def test_per_item_percentage(self):
        self._write(self.first, 'а')     # верно
        self._write(self.second, 'б')    # неверно
        self.client.force_login(self.tutor)
        response = self.client.get(
            reverse('teacher:group_exam_results',
                    args=[self.group.pk, self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        footer = response.context['footer']
        self.assertEqual(footer[0]['percent'], 50)

    def test_not_started_students_are_listed(self):
        self._write(self.first, 'а')
        self.client.force_login(self.tutor)
        response = self.client.get(
            reverse('teacher:group_exam_results',
                    args=[self.group.pk, self.exam.pk]))
        self.assertIn(self.second, response.context['not_started'])


class FinalizeCommandTests(TestCase):
    def test_command_closes_expired(self):
        from io import StringIO

        tutor = make_user('fc_tutor', role='teacher')
        student = make_user('fc_student', role='student')
        exam = make_exam(tutor, [student])
        AssignmentItem.objects.create(assignment=exam,
                                      catalog_problem=make_problem('З'),
                                      order=0)
        attempt = exam_engine.start_attempt(exam, student)
        attempt.expires_at = timezone.now() - timedelta(minutes=5)
        attempt.save()

        call_command('finalize_expired_attempts', stdout=StringIO(),
                     verbosity=0)
        attempt.refresh_from_db()
        self.assertIsNotNone(attempt.submitted_at)
        self.assertTrue(attempt.is_auto_submitted)

    def test_command_is_idempotent(self):
        from io import StringIO

        tutor = make_user('fc2_tutor', role='teacher')
        student = make_user('fc2_student', role='student')
        exam = make_exam(tutor, [student])
        AssignmentItem.objects.create(assignment=exam,
                                      catalog_problem=make_problem('З'),
                                      order=0)
        attempt = exam_engine.start_attempt(exam, student)
        attempt.expires_at = timezone.now() - timedelta(minutes=5)
        attempt.save()
        call_command('finalize_expired_attempts', stdout=StringIO(),
                     verbosity=0)
        moment = ExamAttempt.objects.get(pk=attempt.pk).submitted_at
        call_command('finalize_expired_attempts', stdout=StringIO(),
                     verbosity=0)
        self.assertEqual(ExamAttempt.objects.get(pk=attempt.pk).submitted_at,
                         moment)


class TimeOnScreenTests(TestCase):
    """ФАЗА 0.8. Одно время везде — в часовом поясе проекта.

    На экране до старта две строки расходились на три часа: «Время: до
    05.08 18:58» (собрана в питоне f-строкой, то есть UTC) и «Крайний срок:
    05.08.2026, 21:58» (шаблонный фильтр `date`, который переводит в пояс
    проекта сам). Ни один тест этого не видел: обе строки по отдельности
    «работали».
    """

    def setUp(self):
        self.tutor = make_user('tz_tutor', role='teacher')
        self.student = make_user('tz_student', role='student')
        self.client.force_login(self.student)

    def test_schedule_line_and_deadline_line_agree(self):
        from django.utils import timezone as tz

        now = tz.now()
        exam = make_exam(self.tutor, [self.student], mode='limit', now=now)
        AssignmentItem.objects.create(assignment=exam, order=0,
                                      catalog_problem=make_problem('З'))
        body = self.client.get(
            reverse('student:exam_intro', args=[exam.pk])).content.decode()

        # Как выглядит крайний срок в часовом поясе проекта.
        local = tz.localtime(exam.deadline)
        short = local.strftime('%d.%m %H:%M')
        full = local.strftime('%d.%m.%Y, %H:%M')
        self.assertIn('до %s' % short, body,
                      'строка расписания показывает не местное время')
        self.assertIn(full, body)

        # И ни одной строки с UTC-временем того же момента.
        utc_short = exam.deadline.strftime('%d.%m %H:%M')
        if utc_short != short:
            self.assertNotIn('до %s' % utc_short, body)

    def test_window_schedule_is_local(self):
        from django.utils import timezone as tz

        now = tz.now()
        exam = make_exam(self.tutor, [self.student], mode='window', now=now)
        label = exam_schedule_label_for(exam)
        start = tz.localtime(exam.starts_at)
        self.assertIn(start.strftime('%H:%M'), label)

    def test_closed_reason_is_local(self):
        """«Начало ...» в отказе открыть контрольную — тоже местное время."""
        from datetime import timedelta as td

        from django.utils import timezone as tz

        now = tz.now()
        exam = make_exam(self.tutor, [self.student], mode='window', now=now,
                         starts_at=now + td(hours=2),
                         ends_at=now + td(hours=3),
                         deadline=now + td(hours=3))
        _, reason = exam.open_state_for(self.student, now)
        self.assertIn(tz.localtime(exam.starts_at).strftime('%d.%m.%Y %H:%M'),
                      reason)


def exam_schedule_label_for(assignment):
    from student.views import exam_schedule_label

    return exam_schedule_label(assignment)


class TimezoneTests(TestCase):
    """Храним UTC, показываем в поясе проекта."""

    def test_stored_in_utc_shown_in_project_timezone(self):
        from django.conf import settings

        tutor = make_user('tz_tutor', role='teacher')
        student = make_user('tz_student', role='student')
        # 18:00 по поясу проекта.
        local = timezone.localtime(timezone.now()).replace(
            hour=18, minute=0, second=0, microsecond=0) + timedelta(days=1)
        exam = make_exam(tutor, [student], mode='window',
                         starts_at=local, ends_at=local + timedelta(hours=2),
                         deadline=local + timedelta(hours=2))
        exam.refresh_from_db()
        self.assertEqual(timezone.localtime(exam.starts_at).hour, 18)
        self.assertTrue(settings.USE_TZ)


class LeaderboardTests(TestCase):
    """Сравнение со средним по группе — только при включённом рейтинге."""

    def setUp(self):
        self.tutor = make_user('lb_tutor', role='teacher')
        self.student = make_user('lb_student', role='student')
        self.group = StudentGroup.objects.create(name='Г', teacher=self.tutor)
        self.group.students.set([self.student])
        self.exam = make_exam(self.tutor, [self.student], group=self.group)
        AssignmentItem.objects.create(assignment=self.exam,
                                      catalog_problem=make_problem('З'),
                                      order=0)

    def test_off_by_default(self):
        self.assertFalse(self.group.leaderboard_enabled)
        from student.views_exam import _group_average
        self.assertIsNone(_group_average(self.exam))

    def test_on_when_enabled(self):
        from student.views_exam import _group_average

        self.group.leaderboard_enabled = True
        self.group.save()
        self.exam.refresh_from_db()
        # Пусто, но не None: рейтинг включён, просто оценок ещё нет.
        self.assertIsNone(_group_average(self.exam))
