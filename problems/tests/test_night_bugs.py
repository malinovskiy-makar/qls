"""
Одиннадцать багов приёмки (фаза 7 ночной сессии).

Каждый тест — про КОНКРЕТНЫЙ видимый дефект, найденный владельцем руками,
а не про «код работает». Номера совпадают с номерами в задании.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import (
    Assignment, AssignmentItem, CustomProblem, StudentGroup, Submission,
)
from problems.stats import needs_attention
from problems.timefmt import human_deadline
from problems.tests.factories import make_problem, make_user


class Bug71ProgressPageTests(TestCase):
    """7.1 — ошибка 500 на «Прогресс ученика»."""

    def setUp(self):
        self.tutor = make_user('b71_tutor', role='teacher')
        self.student = make_user('b71_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        self.client.force_login(self.tutor)

    def test_page_opens_when_submission_has_no_catalog_problem(self):
        """Работа по СВОЕЙ задаче репетитора: поля `problem` у неё нет.

        Именно на такой записи страница падала: код читал
        `submission.problem.problem_type`, а `problem` стал необязательным,
        когда появились свои задачи.
        """
        custom = CustomProblem.objects.create(
            owner=self.tutor, statement='Своя задача',
            kind=CustomProblem.Kind.OPEN, correct_answer='42')
        item = AssignmentItem.objects.create(assignment=self.work, order=0,
                                             custom_problem=custom)
        Submission.objects.create(student=self.student, assignment=self.work,
                                  problem=None, problem_item=item,
                                  status='reviewed')
        response = self.client.get(
            reverse('teacher:student_progress', args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)

    def test_custom_test_counts_as_a_test(self):
        """Тип берётся у ПОЗИЦИИ: она знает про оба вида задач."""
        from teacher.views import _submission_is_test

        custom = CustomProblem.objects.create(
            owner=self.tutor, statement='Свой тест',
            kind=CustomProblem.Kind.SINGLE)
        item = AssignmentItem.objects.create(assignment=self.work, order=1,
                                             custom_problem=custom)
        sub = Submission.objects.create(student=self.student,
                                        assignment=self.work,
                                        problem_item=item, status='reviewed')
        self.assertTrue(_submission_is_test(sub))


class Bug74SortTests(TestCase):
    """7.4 — задания сортируются по дедлайну, ближайшие первыми."""

    def setUp(self):
        self.tutor = make_user('b74_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.client.force_login(self.tutor)
        now = timezone.now()
        self.far = Assignment.objects.create(
            name='Далёкая', author=self.tutor, group=self.group,
            deadline=now + timedelta(days=10))
        self.near = Assignment.objects.create(
            name='Ближняя', author=self.tutor, group=self.group,
            deadline=now + timedelta(days=1))
        self.past = Assignment.objects.create(
            name='Прошедшая', author=self.tutor, group=self.group,
            deadline=now - timedelta(days=5))
        self.none = Assignment.objects.create(
            name='Без срока', author=self.tutor, group=self.group)

    def _names(self):
        response = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments')
        return [row['assignment'].name
                for row in response.context['assignment_rows']]

    def test_sorted_by_deadline(self):
        self.assertEqual(self._names(),
                         ['Прошедшая', 'Ближняя', 'Далёкая', 'Без срока'])

    def test_undated_goes_last(self):
        """У задания без срока нет места на шкале — оно не должно быть первым."""
        self.assertEqual(self._names()[-1], 'Без срока')


class Bug75CheckedBadgeTests(TestCase):
    """7.5 — «проверено» только когда было что проверять."""

    def setUp(self):
        self.tutor = make_user('b75_tutor', role='teacher')
        self.student = make_user('b75_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'))
        self.client.force_login(self.tutor)

    def _row(self):
        response = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments')
        return response.context['assignment_rows'][0]

    def test_nobody_submitted_is_not_checked(self):
        row = self._row()
        self.assertTrue(row['nobody_submitted'])
        self.assertFalse(row['all_checked'])

    def test_finished_work_without_submissions_says_so(self):
        """«Проверено» там, где никто не сдал, — ложь. Пишем правду.

        ⚠️ Проверка переписана под фазу 11: плоского списка с бейджами
        больше нет, задания сгруппированы по состоянию. Работа с прошедшим
        сроком, которую никто не сдал, попадает в «Завершены», и надпись на
        её строке — «никто не сдал», а не «средний балл».
        """
        self.work.deadline = timezone.now() - timedelta(days=2)
        self.work.save(update_fields=['deadline'])
        body = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments').content.decode()
        self.assertIn('никто не сдал', body)
        self.assertNotIn('средний балл', body)

    def test_checked_only_after_a_real_submission(self):
        Submission.objects.create(student=self.student, assignment=self.work,
                                  problem_item=self.item, status='reviewed')
        row = self._row()
        self.assertFalse(row['nobody_submitted'])
        self.assertTrue(row['all_checked'])


class Bug78TitlesTests(TestCase):
    """7.8 — в сводке решений нормальное название, а не «Задача #»."""

    def test_statement_start_instead_of_the_id(self):
        tutor = make_user('b78_tutor', role='teacher')
        student = make_user('b78_student', role='student')
        group = StudentGroup.objects.create(name='Гр', teacher=tutor)
        work = Assignment.objects.create(name='ДЗ', author=tutor, group=group)
        work.students.add(student)
        problem = make_problem(
            'Фирма выпускает 100 единиц, постоянные издержки 2000 рублей.')
        item = AssignmentItem.objects.create(assignment=work, order=0,
                                             catalog_problem=problem)
        Submission.objects.create(student=student, assignment=work,
                                  problem=problem, problem_item=item,
                                  status='submitted')
        self.client.force_login(tutor)
        # ⚠️ Названия задач живут в виде «по задачам». С фазы 12 сводка по
        # умолчанию открывается видом «по ученикам», где задач нет вовсе.
        body = self.client.get(
            reverse('teacher:group_submissions', args=[group.pk, work.pk])
            + '?view=problems').content.decode()
        self.assertIn('Фирма выпускает', body)
        self.assertNotIn('Задача #%d' % problem.pk, body)


class Bug79WordCutTests(TestCase):
    """7.9 — обрезка условия по СЛОВАМ: число нельзя рвать пополам."""

    def test_numbers_are_not_split(self):
        from teacher.picker import word_cut

        text = ('Фирма выпускает продукцию, её постоянные издержки равны '
                '2000 рублей, а переменные — 3000 рублей в месяц всего')
        cut = word_cut(text, 100)
        self.assertTrue(cut.endswith('…'))
        # Обрезка ровно по границе слова: обрубка числа быть не должно.
        self.assertNotIn('300…', cut)
        self.assertNotIn('200…', cut)

    def test_short_text_is_untouched(self):
        from teacher.picker import word_cut

        self.assertEqual(word_cut('Коротко', 100), 'Коротко')


class Bug710HumanDeadlineTests(TestCase):
    """7.10 — срок по-человечески, точная дата в подсказке."""

    def setUp(self):
        self.now = timezone.now().replace(hour=12, minute=0, second=0,
                                          microsecond=0)

    def test_tomorrow(self):
        self.assertTrue(
            human_deadline(self.now + timedelta(days=1), self.now)
            .startswith('завтра до '))

    def test_in_three_days(self):
        self.assertEqual(
            human_deadline(self.now + timedelta(days=3), self.now),
            'через 3 дня')

    def test_two_days_ago(self):
        self.assertEqual(
            human_deadline(self.now - timedelta(days=2), self.now),
            'прошёл 2 дня назад')

    def test_today(self):
        self.assertTrue(
            human_deadline(self.now + timedelta(hours=3), self.now)
            .startswith('сегодня до '))

    def test_no_deadline_is_an_empty_string(self):
        """Пусто — решает вызывающий, писать ли «без срока»."""
        self.assertEqual(human_deadline(None), '')

    def test_calendar_days_not_twenty_four_hours(self):
        """Сегодня 23:00 и завтра 01:00 — это «сегодня» и «завтра».

        ⚠️ Моменты строим в МЕСТНОМ поясе, а не в UTC. Проект живёт в
        UTC+3: «23:00 UTC» — это уже 02:00 следующего дня по Москве, и
        тест, собранный в UTC, проверял бы не то, что видит человек.
        """
        from problems.timefmt import local

        here = local(self.now)
        late = here.replace(hour=23, minute=0)
        soon = (here + timedelta(days=1)).replace(hour=1, minute=0)
        self.assertTrue(human_deadline(late, self.now).startswith('сегодня'))
        self.assertTrue(human_deadline(soon, self.now).startswith('завтра'))


class Bug711StaleReviewTests(TestCase):
    """7.11 — четвёртое условие плашки: работа ждёт ВАШЕЙ проверки."""

    def setUp(self):
        self.tutor = make_user('b711_tutor', role='teacher')
        self.student = make_user('b711_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'))

    def _submit(self, days_ago):
        return Submission.objects.create(
            student=self.student, assignment=self.work,
            problem_item=self.item, status='submitted',
            submitted_at=timezone.now() - timedelta(days=days_ago))

    def _reasons(self):
        rows = needs_attention(self.group)
        for row in rows:
            if row['student'].pk == self.student.pk:
                return row['reasons']
        return []

    def test_fresh_submission_is_not_flagged(self):
        self._submit(1)
        self.assertFalse([r for r in self._reasons() if 'вашей проверки' in r])

    def test_stale_submission_is_flagged(self):
        self._submit(4)
        stale = [r for r in self._reasons() if 'вашей проверки' in r]
        self.assertEqual(len(stale), 1)
        self.assertIn('4 дня', stale[0])

    def test_wording_is_about_the_tutor(self):
        """Формулировка про репетитора, а не «ученик виноват»."""
        self._submit(5)
        stale = [r for r in self._reasons() if 'вашей проверки' in r][0]
        self.assertIn('вашей проверки', stale)
        self.assertNotIn('не сдал', stale)

    def test_reviewed_work_does_not_count(self):
        sub = self._submit(9)
        sub.status = 'reviewed'
        sub.save()
        self.assertFalse([r for r in self._reasons() if 'вашей проверки' in r])


class DemoSeedTests(TestCase):
    """Фаза 8 — витрина. Мусор в демо читается как поломка кода."""

    def _seed(self):
        from django.core.management import call_command
        from io import StringIO

        call_command('seed_platform_demo', stdout=StringIO())

    def test_seed_is_idempotent_for_the_graph(self):
        """8.3 — второй прогон не добавляет второй плашки графика.

        Раньше график цеплялся на «первую» и «последнюю» позицию, а состав
        домашки за сессии менялся: каждый прогон делал «последней» новую
        позицию, со старых плашку никто не снимал. Так одна плашка
        оказалась на четырёх задачах.
        """
        from problems.models import SavedGraph

        self._seed()
        first = {g.pk: AssignmentItem.objects.filter(graph=g).count()
                 for g in SavedGraph.objects.all()}
        self._seed()
        second = {g.pk: AssignmentItem.objects.filter(graph=g).count()
                  for g in SavedGraph.objects.all()}
        self.assertEqual(first, second)
        for count in second.values():
            self.assertLessEqual(count, 1, 'график не должен дублироваться')

    def test_students_have_different_surnames(self):
        """8.4 — три Иванова подряд выглядят как ошибка выборки."""
        from django.contrib.auth import get_user_model

        self._seed()
        User = get_user_model()
        surnames = [u.last_name for u in User.objects.filter(
            username__in=['student1@test.local', 'student2@test.local',
                          'student3@test.local'])]
        self.assertEqual(len(surnames), 3)
        self.assertEqual(len(set(surnames)), 3, surnames)

    def test_custom_problem_answer_matches_its_own_solution(self):
        """8.2 — стояло «-0,54», а решение под ним даёт −0,57."""
        self._seed()
        problem = CustomProblem.objects.get(
            title='Эластичность спроса на проездные')
        self.assertEqual(problem.correct_answer, '-0,57')
        self.assertIn('0{,}57', problem.solution)

    def test_solution_matches_its_problem(self):
        """8.1 — под задачей про эластичность стоял разбор равновесия."""
        self._seed()
        item = (AssignmentItem.objects
                .filter(solution_override__gt='')
                .select_related('catalog_problem').first())
        if item is None:
            self.skipTest('в демо нет позиции со своим решением')
        title = (item.problem_title or '').lower()
        text = item.solution_override
        if 'эластич' in title:
            self.assertIn('эластичност', text.lower())
            # Разбора равновесия под задачей об эластичности быть не должно.
            self.assertNotIn('Приравниваем спрос и предложение', text)

    def test_second_run_does_not_multiply_users(self):
        from django.contrib.auth import get_user_model

        self._seed()
        User = get_user_model()
        before = User.objects.count()
        self._seed()
        self.assertEqual(User.objects.count(), before)


class GroupOverviewTests(TestCase):
    """Фаза 10 — вкладка «Ученики» удалена, статистика стала обзором."""

    def setUp(self):
        self.tutor = make_user('go_tutor', role='teacher')
        self.student = make_user('go_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.client.force_login(self.tutor)

    def _url(self, query=''):
        return reverse('teacher:group_detail', args=[self.group.pk]) + query

    def test_overview_is_the_default_tab(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['tab'], 'overview')

    def test_three_tabs_and_no_students_tab(self):
        body = self.client.get(self._url()).content.decode()
        self.assertIn('?tab=overview', body)
        self.assertIn('?tab=assignments', body)
        self.assertIn('?tab=materials', body)
        self.assertNotIn('?tab=students', body)

    def test_tabs_visible_on_the_overview(self):
        """Раньше на статистике ряд вкладок пропадал совсем."""
        body = self.client.get(self._url('?tab=overview')).content.decode()
        self.assertIn('class="tabs"', body)

    def test_old_students_tab_redirects(self):
        """Адрес мог попасть в закладки — 404 там недопустима."""
        response = self.client.get(self._url('?tab=students'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('tab=overview', response['Location'])

    def test_old_stats_url_redirects(self):
        response = self.client.get(
            reverse('teacher:group_stats', args=[self.group.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('tab=overview', response['Location'])

    def test_old_stats_url_keeps_the_period(self):
        response = self.client.get(
            reverse('teacher:group_stats', args=[self.group.pk])
            + '?period=week')
        self.assertIn('period=week', response['Location'])

    def test_one_students_table_with_full_columns(self):
        """Таблица одна и полная: «решено» и «доля верных» были только тут."""
        body = self.client.get(self._url()).content.decode()
        self.assertIn('Решено', body)
        self.assertIn('Доля верных', body)
        self.assertIn('Сдано работ', body)
        self.assertIn('Последняя активность', body)
        # Прежней колонки «Последний вход на сайт» из вкладки «Ученики» нет.
        self.assertNotIn('Последний вход на сайт', body)

    def test_open_button_leads_to_student_progress(self):
        body = self.client.get(self._url()).content.decode()
        self.assertIn(
            reverse('teacher:student_progress', args=[self.student.pk]), body)

    def test_heatmap_headers_are_not_shouting(self):
        """Заголовки тем остались вертикальными, но без капслока."""
        from django.template.loader import render_to_string

        css = render_to_string('platform/_stats_style.html')
        self.assertIn('writing-mode: vertical-rl', css)
        matrix = css[css.index('.matrix-head'):css.index('.matrix-head') + 260]
        self.assertIn('text-transform: none', matrix)


class AssignmentGroupingTests(TestCase):
    """Фаза 11 — задания группируются по состоянию, а не лежат списком."""

    def setUp(self):
        self.tutor = make_user('ag_tutor', role='teacher')
        self.student = make_user('ag_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.client.force_login(self.tutor)
        self.now = timezone.now()

    def _work(self, name, days, pending=0, submitted=0):
        work = Assignment.objects.create(
            name=name, author=self.tutor, group=self.group,
            deadline=self.now + timedelta(days=days))
        work.students.add(self.student)
        item = AssignmentItem.objects.create(
            assignment=work, order=0,
            catalog_problem=make_problem('Условие ' + name))
        for _ in range(pending):
            Submission.objects.create(student=self.student, assignment=work,
                                      problem_item=item, status='submitted')
        for _ in range(submitted):
            Submission.objects.create(student=self.student, assignment=work,
                                      problem_item=item, status='reviewed')
        return work

    def _groups(self):
        response = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments')
        return {key: [r['assignment'].name for r in rows]
                for key, _, rows in response.context['assignment_groups']}

    def test_unchecked_work_goes_to_needs_you(self):
        self._work('С непроверенным', days=5, pending=1)
        self.assertEqual(self._groups()['needs_you'], ['С непроверенным'])

    def test_future_deadline_without_work_is_running(self):
        self._work('Идёт', days=5)
        self.assertEqual(self._groups()['running'], ['Идёт'])

    def test_past_deadline_all_checked_is_done(self):
        self._work('Закрыта', days=-5, submitted=1)
        self.assertEqual(self._groups()['done'], ['Закрыта'])

    def test_past_deadline_nobody_submitted_is_done(self):
        self._work('Никто не сдал', days=-5)
        self.assertEqual(self._groups()['done'], ['Никто не сдал'])

    def test_needs_you_beats_a_passed_deadline(self):
        """Срок прошёл, но непроверенное лежит — это всё ещё ваша работа."""
        self._work('Просрочена и не проверена', days=-5, pending=1)
        self.assertEqual(self._groups()['needs_you'],
                         ['Просрочена и не проверена'])

    def test_empty_group_is_not_shown(self):
        self._work('Только эта', days=5)
        self.assertNotIn('needs_you', self._groups())
        self.assertNotIn('done', self._groups())

    def test_groups_go_in_order_of_urgency(self):
        self._work('Требует', days=3, pending=1)
        self._work('Идёт', days=4)
        self._work('Закрыта', days=-2, submitted=1)
        response = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments')
        keys = [key for key, _, _ in response.context['assignment_groups']]
        self.assertEqual(keys, ['needs_you', 'running', 'done'])

    def test_exam_kind_is_quiet_text_not_an_accent_badge(self):
        work = self._work('Контрольная', days=4)
        work.kind = Assignment.Kind.EXAM
        work.save(update_fields=['kind'])
        body = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments').content.decode()
        self.assertIn('class="ass-kind"', body)
        # Розового бейджа нет ни в разметке, ни в стилях страницы.
        self.assertNotIn('badge-exam', body)
        self.assertNotIn('badge badge-exam', body)

    def test_finished_card_shows_the_average(self):
        from problems.models import TeacherFeedback

        work = self._work('Закрыта', days=-3)
        item = work.items.first()
        sub = Submission.objects.create(student=self.student, assignment=work,
                                        problem_item=item, status='reviewed')
        TeacherFeedback.objects.create(submission=sub, score=Decimal('4'))
        body = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments').content.decode()
        self.assertIn('средний балл', body)


class SubmissionsByStudentTests(TestCase):
    """Фаза 12 — сводка решений карточками по ученикам."""

    def setUp(self):
        self.tutor = make_user('sbs_tutor', role='teacher')
        self.a = make_user('sbs_a', role='student')
        self.b = make_user('sbs_b', role='student')
        self.c = make_user('sbs_c', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        for s in (self.a, self.b, self.c):
            self.group.students.add(s)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.set([self.a, self.b, self.c])
        self.items = [
            AssignmentItem.objects.create(
                assignment=self.work, order=i,
                catalog_problem=make_problem('Условие %d' % i),
                points=Decimal('3'))
            for i in range(2)]
        self.client.force_login(self.tutor)

    def _url(self, query='?view=students'):
        return reverse('teacher:group_submissions',
                       args=[self.group.pk, self.work.pk]) + query

    def _cards(self):
        return {c['student'].username: c
                for c in self.client.get(self._url()).context['cards']}

    def _submit(self, student, item, status='submitted', score=None,
                by_machine=True):
        from problems.models import TeacherFeedback

        sub = Submission.objects.create(
            student=student, assignment=self.work, problem_item=item,
            status=status, submitted_at=timezone.now())
        if score is not None:
            TeacherFeedback.objects.create(
                submission=sub, score=Decimal(str(score)),
                reviewed_by=None if by_machine else self.tutor)
        return sub

    def test_one_card_per_student(self):
        cards = self._cards()
        self.assertEqual(len(cards), 3)

    def test_not_started_card(self):
        card = self._cards()['sbs_c']
        self.assertEqual(card['state'], 'not_started')
        self.assertEqual(card['button']['label'], 'Написать')
        self.assertEqual(card['button']['kind'], 'quiet')

    def test_pending_card_offers_checking(self):
        self._submit(self.a, self.items[0])
        card = self._cards()['sbs_a']
        self.assertEqual(card['state'], 'partial')
        self.assertEqual(card['button']['kind'], 'main')
        self.assertIn('Проверить 1 задачу', card['button']['label'])

    def test_button_leads_to_the_first_unchecked(self):
        self._submit(self.a, self.items[0], status='reviewed', score=3)
        pending = self._submit(self.a, self.items[1])
        card = self._cards()['sbs_a']
        self.assertIn(str(pending.pk), card['button']['url'])

    def test_all_checked_card(self):
        for item in self.items:
            self._submit(self.a, item, status='reviewed', score=3)
        card = self._cards()['sbs_a']
        self.assertEqual(card['state'], 'checked')
        self.assertEqual(card['button']['label'], 'Смотреть работу')

    def test_machine_score_counts_only_machine_marks(self):
        """«Машина уже насчитала» — только машинные проверки.

        Оценку человека сюда мешать нельзя: подпись перестала бы быть
        правдой ровно в тот момент, когда репетитор поставит первый балл.
        """
        self._submit(self.a, self.items[0], status='reviewed', score=3)
        self._submit(self.a, self.items[1], status='reviewed', score=2,
                     by_machine=False)
        card = self._cards()['sbs_a']
        self.assertEqual(card['machine_got'], '3')
        self.assertEqual(card['machine_could'], '3')

    def test_order_is_the_work_queue(self):
        """Сначала требующие проверки, потом проверенные, в конце пустые."""
        self._submit(self.a, self.items[0])                       # ждёт
        self._submit(self.b, self.items[0], status='reviewed', score=3)
        cards = self.client.get(self._url()).context['cards']
        self.assertEqual([c['student'].username for c in cards],
                         ['sbs_a', 'sbs_b', 'sbs_c'])

    def test_view_choice_is_not_remembered(self):
        """Выбор вида БОЛЬШЕ НЕ ЗАПОМИНАЕТСЯ (сессия 7, фаза 1).

        Раньше запоминался. С удалением переключателя это стало ловушкой:
        один заход по прямой ссылке `?view=problems` — и репетитор навсегда
        оставался на таблице, с которой некуда вернуться.
        """
        self.client.get(self._url('?view=problems'))
        response = self.client.get(self._url(''))
        self.assertIn('cards', response.context)

    def test_switch_is_gone_but_the_table_still_opens(self):
        """Переключателя в интерфейсе нет, а вид «по задачам» жив.

        Владелец просил убрать выбор, а не функцию: таблица «ученик × задача»
        остаётся рабочей поверхностью и открывается прямой ссылкой.
        """
        by_student = self.client.get(self._url('?view=students')).content.decode()
        self.assertNotIn('?view=problems', by_student)
        self.assertNotIn('sub-switch', by_student)
        self.assertEqual(
            self.client.get(self._url('?view=problems')).status_code, 200)


class ReviewFlowTests(TestCase):
    """Фаза 13 — проверка стала потоком по работе одного ученика."""

    def setUp(self):
        self.tutor = make_user('rf_tutor', role='teacher')
        self.student = make_user('rf_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        self.items = [
            AssignmentItem.objects.create(
                assignment=self.work, order=i,
                catalog_problem=make_problem('Условие %d' % i),
                points=Decimal('4'))
            for i in range(3)]
        self.subs = [
            Submission.objects.create(student=self.student,
                                      assignment=self.work, problem_item=item,
                                      status='submitted',
                                      submitted_answer='ответ')
            for item in self.items]
        self.client.force_login(self.tutor)

    def _review(self, sub):
        return reverse('teacher:group_review_submission',
                       args=[self.group.pk, sub.pk])

    def test_screen_knows_its_place_in_the_work(self):
        response = self.client.get(self._review(self.subs[1]))
        self.assertEqual(response.context['number'], 2)
        self.assertEqual(response.context['total'], 3)
        self.assertEqual(response.context['prev_sub'].pk, self.subs[0].pk)
        self.assertEqual(response.context['next_sub'].pk, self.subs[2].pk)

    def test_first_has_no_previous_and_last_has_no_next(self):
        first = self.client.get(self._review(self.subs[0])).context
        last = self.client.get(self._review(self.subs[2])).context
        self.assertIsNone(first['prev_sub'])
        self.assertIsNone(last['next_sub'])

    def test_save_and_next_goes_to_the_next_unchecked(self):
        response = self.client.post(self._review(self.subs[0]),
                                    {'score': '4', 'comment': '', 'go': 'next'})
        self.assertEqual(response.status_code, 302)
        self.assertIn(str(self.subs[1].pk), response['Location'])

    def test_save_and_next_skips_the_already_checked(self):
        """Проверенное пропускаем: «дальше» ведёт к работе, а не по кругу."""
        self.subs[1].status = 'reviewed'
        self.subs[1].save(update_fields=['status'])
        response = self.client.post(self._review(self.subs[0]),
                                    {'score': '4', 'comment': '', 'go': 'next'})
        self.assertIn(str(self.subs[2].pk), response['Location'])

    def test_last_one_leads_to_the_completion_screen(self):
        for sub in self.subs[:2]:
            sub.status = 'reviewed'
            sub.save(update_fields=['status'])
        response = self.client.post(self._review(self.subs[2]),
                                    {'score': '4', 'comment': '', 'go': 'next'})
        self.assertIn('/done/', response['Location'])

    def test_completion_screen_shows_the_total(self):
        from problems.models import TeacherFeedback

        for sub in self.subs:
            sub.status = 'reviewed'
            sub.save(update_fields=['status'])
            TeacherFeedback.objects.create(submission=sub, score=Decimal('3'),
                                           reviewed_by=self.tutor)
        response = self.client.get(
            reverse('teacher:work_done',
                    args=[self.group.pk, self.work.pk, self.student.pk]))
        self.assertEqual(response.status_code, 200)
        # Сравниваем ЗНАЧЕНИЕ, а не тип: с сессии 7 итог собирает
        # `work_review.work_summary` (одна сборка на все экраны) и отдаёт
        # Decimal вместо строки. На экране это то же самое число.
        self.assertEqual(str(response.context['total']), '9')
        self.assertEqual(str(response.context['maximum']), '12')

    def test_work_comment_lives_on_the_completion_screen(self):
        from problems.models import WorkFeedback

        url = reverse('teacher:work_done',
                      args=[self.group.pk, self.work.pk, self.student.pk])
        self.client.post(url, {'work_comment': 'Повтори эластичность.'})
        feedback = WorkFeedback.objects.get(assignment=self.work,
                                            student=self.student)
        self.assertEqual(feedback.comment, 'Повтори эластичность.')

    def test_review_screen_no_longer_asks_for_the_work_comment(self):
        """Поле переехало: писать про работу целиком можно, прочитав её."""
        body = self.client.get(self._review(self.subs[0])).content.decode()
        self.assertNotIn('work_comment', body)
        self.assertNotIn('Комментарий ко всей работе', body)

    def test_mistake_tags_are_gone(self):
        """13.5 — список ошибок не связан с темой задачи, убран совсем."""
        body = self.client.get(self._review(self.subs[0])).content.decode()
        self.assertNotIn('Отметить ошибки', body)
        self.assertNotIn('name="mistakes"', body)

    def test_score_presets_are_zero_half_max(self):
        presets = self.client.get(
            self._review(self.subs[0])).context['score_presets']
        self.assertEqual([p['value'] for p in presets], ['0', '2', '4'])

    def test_presets_do_not_repeat_when_max_is_tiny(self):
        """Максимум 1 — три РАЗНЫЕ кнопки, дубля быть не должно.

        Проверка про дубли, а не про округление: с сессии 7 половина не
        округляется вовсе, и при максимуме 1 середина — это 0,5.
        """
        self.items[0].points = Decimal('1')
        self.items[0].save(update_fields=['points'])
        presets = self.client.get(
            self._review(self.subs[0])).context['score_presets']
        values = [p['value'] for p in presets]
        self.assertEqual(values, ['0', '0.5', '1'])
        self.assertEqual(len(values), len(set(values)))

    def test_answer_falls_back_to_the_submission(self):
        """Ответ есть в работе — экран обязан его показать.

        ⚠️ Найдено глазами: у задачи без пунктов запись `PartAnswer` может
        отсутствовать (старые и демо-данные), и экран писал «ответа нет»
        ученику, который ответил.
        """
        from problems import part_grading

        rows = part_grading.part_rows(self.items[0], self.subs[0])
        self.assertEqual(rows[0]['given'], 'ответ')


class QuotaByKindTests(TestCase):
    """Фаза 17–18: ровно столько тестов и столько открытых задач."""

    def test_allocation_never_loses_or_adds_places(self):
        from problems.hw_generator import allocate

        self.assertEqual(sum(allocate(7, [2, 3])), 7)
        self.assertEqual(sum(allocate(4, [1, 1, 1])), 4)
        self.assertEqual(allocate(0, [1, 2]), [0, 0])

    def test_split_gives_exact_totals(self):
        from problems.hw_generator import split_by_kind

        rows = [{'label': 'A', 'query': 'a', 'topic': '', 'difficulty': 3,
                 'count': 2},
                {'label': 'B', 'query': 'b', 'topic': '', 'difficulty': 4,
                 'count': 3}]
        plan = split_by_kind(rows, 4, 3)
        opens = sum(r['count'] for r in plan if r['kind'] == 'open')
        tests = sum(r['count'] for r in plan if r['kind'] == 'test')
        self.assertEqual((opens, tests), (4, 3))

    def test_zero_tests_means_no_test_rows(self):
        from problems.hw_generator import split_by_kind

        rows = [{'label': 'A', 'query': 'a', 'topic': '', 'difficulty': 3,
                 'count': 5}]
        plan = split_by_kind(rows, 5, 0)
        self.assertTrue(all(r['kind'] == 'open' for r in plan))

    def test_last_resort_respects_the_kind(self):
        """⚠️ Последний рубеж ИСКЛЮЧАЛ тесты — и молча подменял их задачами.

        Найдено проверкой в браузере: репетитор просил три теста, получал
        три открытые задачи под видом выполненной просьбы.
        """
        from problems.hw_generator import _any_problems, is_test_problem
        from problems.models import Problem

        make_problem('Открытая задача про спрос', difficulty=3)
        make_problem('Верно ли утверждение?', difficulty=3,
                     problem_type='тест: один ответ')
        rows = [{'label': 'x', 'query': 'спрос', 'topic': '', 'difficulty': 3,
                 'count': 2}]

        want_tests = _any_problems(rows, 20, kind='test')
        ids = [hit['id'] for hit in want_tests]
        for problem in Problem.objects.filter(pk__in=ids):
            self.assertTrue(is_test_problem(problem))

        want_open = _any_problems(rows, 20, kind='open')
        ids = [hit['id'] for hit in want_open]
        for problem in Problem.objects.filter(pk__in=ids):
            self.assertFalse(is_test_problem(problem))


class ManualOrderDetectionTests(TestCase):
    """Фаза 18.5 — порядок, заданный словами, отменяет перестановку."""

    def test_order_words_are_detected(self):
        from problems.hw_generator import describes_order

        self.assertTrue(describes_order(
            'Первая задача — вывод функции КПВ, вторая и третья на сложение'))
        self.assertTrue(describes_order('одна посложнее в конце'))
        self.assertTrue(describes_order('сначала тесты, затем задачи'))

    def test_plain_counts_are_not_an_order(self):
        """«Две задачи на КПВ» — это количество, а не порядок."""
        from problems.hw_generator import describes_order

        self.assertFalse(describes_order(
            'Домашка на КПВ и эластичность, четыре задачи и три теста'))
        self.assertFalse(describes_order('монополия и олигополия'))
        self.assertFalse(describes_order(''))

    def test_flag_reaches_the_assignment(self):
        tutor = make_user('mo_tutor', role='teacher')
        group = StudentGroup.objects.create(name='Гр', teacher=tutor)
        problem = make_problem('Условие')
        self.client.force_login(tutor)
        self.client.post(reverse('teacher:assignment_create'), {
            'name': 'С порядком', 'problem_ids': str(problem.pk),
            'groups': [str(group.pk)], 'manual_order': '1'})
        work = Assignment.objects.get(name='С порядком')
        self.assertTrue(work.manual_order)

    def test_without_the_flag_grouping_still_applies(self):
        tutor = make_user('mo_tutor2', role='teacher')
        group = StudentGroup.objects.create(name='Гр2', teacher=tutor)
        problem = make_problem('Условие')
        self.client.force_login(tutor)
        self.client.post(reverse('teacher:assignment_create'), {
            'name': 'Без порядка', 'problem_ids': str(problem.pk),
            'groups': [str(group.pk)]})
        work = Assignment.objects.get(name='Без порядка')
        self.assertFalse(work.manual_order)
