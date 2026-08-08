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

    def test_badge_says_nobody_submitted(self):
        response = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments')
        body = response.content.decode()
        self.assertIn('никто не сдал', body)
        self.assertNotIn('>проверено<', body)

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
        body = self.client.get(
            reverse('teacher:group_submissions',
                    args=[group.pk, work.pk])).content.decode()
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
