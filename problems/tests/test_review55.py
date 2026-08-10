"""
Тесты ревью владельца на 55 пунктов (сессия 7).

Один файл на всю сессию: правки идут по всему кабинету, и раскладывать их по
существующим файлам значило бы прятать связанные проверки друг от друга.
"""
from decimal import Decimal

from django.test import TestCase

from problems import hw_generator
from problems.models import Problem


def make_problem(statement='Условие', answer='', solution='', **kwargs):
    return Problem.objects.create(
        title=kwargs.pop('title', 'Задача'),
        statement=statement,
        answer=answer,
        solution=solution,
        status=Problem.Status.PUBLISHED,
        needs_quality_review=False,
        **kwargs)


# ===========================================================================
# Фаза 1 — флажок отбирает по ОТВЕТУ, а не по решению
# ===========================================================================

class AnswerFilterTests(TestCase):
    """Стоп-гейт фазы 1: поле `Problem.answer` есть, значит меняем и фильтр.

    Надпись «Искать только задачи с ответом» обязана соответствовать
    поведению. Проверяем именно поведение: задача с решением, но без ответа,
    при включённом флажке НЕ проходит.
    """

    def setUp(self):
        self.with_answer = make_problem('Спрос и предложение', answer='42')
        self.with_solution = make_problem('Спрос и предложение',
                                          solution='Разбор жюри')
        self.hits = [{'id': self.with_answer.pk, 'score': 1.0, 'how': '',
                      'dense_score': 1.0, 'term_hits': 1, 'term_total': 1},
                     {'id': self.with_solution.pk, 'score': 0.9, 'how': '',
                      'dense_score': 0.9, 'term_hits': 1, 'term_total': 1}]

    def _ids(self, has_answer):
        items = hw_generator._materialise(self.hits, has_answer, None)
        return {item['problem'].pk for item in items}

    def test_off_keeps_everything(self):
        self.assertEqual(self._ids(False),
                         {self.with_answer.pk, self.with_solution.pk})

    def test_on_keeps_only_problems_with_an_answer(self):
        self.assertEqual(self._ids(True), {self.with_answer.pk})

    def test_solution_alone_is_not_enough(self):
        """Задача с разбором, но без ответа, отсеивается.

        Ровно этим новый фильтр отличается от старого: раньше она проходила.
        """
        self.assertNotIn(self.with_solution.pk, self._ids(True))

    def test_the_old_parameter_name_is_gone(self):
        """`has_solution` в подборе не осталось нигде.

        Иначе половина конвейера фильтровала бы по решению, а надпись
        обещала бы ответ — тот самый разрыв, который и чинили.
        """
        import inspect
        source = inspect.getsource(hw_generator)
        self.assertNotIn('has_solution', source)


# ===========================================================================
# Фаза 2 — у числовых полей кабинета нет браузерных стрелок
# ===========================================================================

class NumberSpinnerTests(TestCase):
    """Одно правило в наборе деталей вместо правок по шаблонам."""

    def setUp(self):
        from django.conf import settings
        import io, os
        path = os.path.join(settings.BASE_DIR, 'templates', '_kit.html')
        self.kit = io.open(path, encoding='utf-8').read()

    def test_both_vendor_prefixes_are_present(self):
        """Нужны оба: webkit прячет кнопки, appearance выключает виджет."""
        self.assertIn('-webkit-appearance: none', self.kit)
        self.assertIn('appearance: textfield', self.kit)
        self.assertIn('-moz-appearance: textfield', self.kit)
        self.assertIn('::-webkit-inner-spin-button', self.kit)
        self.assertIn('::-webkit-outer-spin-button', self.kit)

    def test_rule_covers_every_cabinet_field_class(self):
        for selector in ('.k-input[type="number"]',
                         '.k-score input[type="number"]',
                         '.form-control[type="number"]'):
            self.assertIn(selector, self.kit, selector)

    def test_rule_is_not_hung_on_a_bare_selector(self):
        """Голый `input[type=number]` задел бы каталог и калькулятор.

        У них свои миры токенов; правило кабинета туда попасть не должно.
        """
        import re
        # Комментарии выбрасываем: в них селектор УПОМИНАЕТСЯ как раз затем,
        # чтобы объяснить, почему его нельзя писать. Ищем правила, не прозу.
        rules = re.sub(r'/\*.*?\*/', '', self.kit, flags=re.S)
        # Каждую ветку селектора проверяем целиком: `.k-score input[...]` —
        # это потомок класса набора и вполне законен, а вот ветка без единого
        # класса означала бы правило на весь сайт.
        for chunk in re.findall(r'([^{}]+)\{', rules):
            for branch in chunk.split(','):
                if 'input[type="number"]' not in branch:
                    continue
                self.assertIn('.', branch,
                              'ветка селектора без класса: %r' % branch.strip())


# ===========================================================================
# Фаза 3 — пресеты балла: ноль, РОВНО половина, максимум
# ===========================================================================

class ScorePresetTests(TestCase):
    """Средняя кнопка — ровно половина, а не округление вверх."""

    def _values(self, top):
        from teacher.views import _score_presets
        return [p['value'] for p in _score_presets(top)]

    def _labels(self, top):
        from teacher.views import _score_presets
        return [p['label'] for p in _score_presets(top)]

    def test_the_six_maximums_from_the_review(self):
        self.assertEqual(self._labels(1), ['0', '0,5', '1'])
        self.assertEqual(self._labels(2), ['0', '1', '2'])
        self.assertEqual(self._labels(3), ['0', '1,5', '3'])
        self.assertEqual(self._labels(5), ['0', '2,5', '5'])
        self.assertEqual(self._labels(7), ['0', '3,5', '7'])
        self.assertEqual(self._labels(10), ['0', '5', '10'])

    def test_half_is_never_rounded_up(self):
        """Раньше максимум 3 давал 0 / 2 / 3 — «два из трёх» это не половина."""
        self.assertNotIn('2', self._values(3))

    def test_value_uses_a_dot_and_the_label_a_comma(self):
        """Запятая в ЗНАЧЕНИИ обнулила бы балл.

        Значение кладут в `<input type="number">` и разбирают `float()`:
        «1,5» дало бы пустое поле в браузере и ноль на сервере.
        """
        presets = self._values(3)
        self.assertIn('1.5', presets)
        for value in presets:
            self.assertNotIn(',', value)
            float(value)                      # разбирается сервером

    def test_no_trailing_zero(self):
        for label in self._labels(10) + self._labels(4):
            self.assertFalse(label.endswith(',0'), label)
            self.assertFalse(label.endswith('.0'), label)

    def test_duplicates_collapse(self):
        """Максимум 0 — одна кнопка, а не три нуля."""
        self.assertEqual(self._values(0), ['0'])


class ScoreRoundTripTests(TestCase):
    """Дробный балл проходит весь путь: форма → сервер → база → экран."""

    def setUp(self):
        from problems.models import (Assignment, AssignmentItem, StudentGroup,
                                     Submission)
        from problems.tests.factories import make_user
        from problems.tests.factories import make_problem as factory_problem

        self.tutor = make_user('sp_tutor', role='teacher')
        self.student = make_user('sp_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=factory_problem('Условие'), points=Decimal('3'))
        self.sub = Submission.objects.create(
            student=self.student, assignment=self.work, problem_item=self.item,
            status='submitted', submitted_answer='что-то')
        self.client.force_login(self.tutor)

    def _url(self):
        from django.urls import reverse
        return reverse('teacher:group_review_submission',
                       args=[self.group.pk, self.sub.pk])

    def test_the_form_offers_the_exact_half(self):
        body = self.client.get(self._url()).content.decode()
        self.assertIn('data-score="1.5"', body)
        self.assertIn('>1,5<', body)

    def test_half_is_stored_and_not_truncated(self):
        """Целая часть вместо 1,5 означала бы, что кнопка врёт.

        Сервер обрезает балл по максимуму (`_max_score_for`) — надо
        убедиться, что обрезка не роняет дробную часть по дороге.
        """
        self.client.post(self._url(), {'score': '1.5', 'comment': ''})
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.feedback.score, Decimal('1.50'))

    def test_score_above_the_maximum_is_still_clipped(self):
        self.client.post(self._url(), {'score': '99', 'comment': ''})
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.feedback.score, Decimal('3.00'))


# ===========================================================================
# Фаза 4 — крупный балл: итог в сводке, пробелы, цвет в итогах проверки
# ===========================================================================

class BigScoreTests(TestCase):
    """Итог и автопроверка — два числа в одном начертании, «N из M»."""

    def setUp(self):
        from problems.models import (Assignment, AssignmentItem, StudentGroup,
                                     Submission, TeacherFeedback)
        from problems.tests.factories import make_user
        from problems.tests.factories import make_problem as factory_problem

        self.tutor = make_user('bs_tutor', role='teacher')
        self.student = make_user('bs_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        self.items = [
            AssignmentItem.objects.create(
                assignment=self.work, order=i,
                catalog_problem=factory_problem('Условие %d' % i),
                points=Decimal('4'))
            for i in range(3)]
        self.subs = []
        for index, item in enumerate(self.items):
            sub = Submission.objects.create(
                student=self.student, assignment=self.work, problem_item=item,
                status='reviewed', submitted_answer='ответ')
            TeacherFeedback.objects.create(submission=sub,
                                           score=Decimal('2'),
                                           reviewed_by=self.tutor)
            self.subs.append(sub)
        self.client.force_login(self.tutor)

    def _cards(self):
        from teacher.views_groups import student_cards
        return {c['student'].username: c
                for c in student_cards(self.work, self.group)}

    def test_summary_card_carries_the_work_total(self):
        card = self._cards()['bs_student']
        self.assertEqual(card['scored'], '6')
        self.assertEqual(card['scored_max'], '12')
        self.assertTrue(card['has_scored'])

    def test_total_matches_the_completion_screen(self):
        """Два экрана об одной работе обязаны показывать один итог.

        Раньше итога в сводке не было вовсе; появившись, он не имеет права
        разойтись с экраном итогов проверки — там сумма считается по той же
        сборке `work_review.work_summary`.
        """
        from django.urls import reverse

        card = self._cards()['bs_student']
        response = self.client.get(
            reverse('teacher:work_done',
                    args=[self.group.pk, self.work.pk, self.student.pk]))
        self.assertEqual(str(response.context['total']), card['scored'])
        self.assertEqual(str(response.context['maximum']), card['scored_max'])

    def test_both_numbers_use_the_same_kit_class(self):
        """Одно начертание на оба числа — прямое требование владельца."""
        from django.urls import reverse

        # Одну оценку делаем МАШИННОЙ (`reviewed_by=None`), иначе блока
        # автопроверки на карточке не будет и сравнивать будет нечего.
        machine = self.subs[0].feedback
        machine.reviewed_by = None
        machine.save(update_fields=['reviewed_by'])

        body = self.client.get(
            reverse('teacher:group_submissions',
                    args=[self.group.pk, self.work.pk])).content.decode()
        self.assertEqual(body.count('k-score k-score--pair'), 2)
        self.assertIn('Итоговый балл', body)
        self.assertIn('Результат автопроверки', body)
        # Своего шрифта у сводки больше нет — только класс набора.
        self.assertNotIn('stu-score-value', body)

    def test_the_denominator_is_a_separate_element(self):
        """«из» отдельным узлом, а не пробелом внутри <small>.

        Пробел на крупном кегле с отрицательным letter-spacing съедался, и
        на экране читалось «4из18». За разделитель отвечают отступы.
        """
        from django.urls import reverse

        body = self.client.get(
            reverse('teacher:group_submissions',
                    args=[self.group.pk, self.work.pk])).content.decode()
        self.assertIn('k-score__of', body)
        self.assertIn('k-score__max', body)


class CompletionScreenColourTests(TestCase):
    """Итоги проверки красятся ТЕМИ ЖЕ состояниями, что разбор ученика."""

    def test_states_come_from_the_shared_assembly(self):
        import io
        template = io.open(
            'teacher/templates/teacher/groups/work_done.html',
            encoding='utf-8').read()
        # Полоса и бейдж — классы набора, своих цветов на экране нет.
        self.assertIn('k-mark k-mark--{{ row.state }}', template)
        self.assertIn('k-flag k-flag--{{ row.state }}', template)
        # Балл и максимум, а не одинокое число.
        self.assertIn('row.max_points', template)

    def test_blank_is_not_painted_as_wrong(self):
        """«Не отвечал» — не ошибка: балл тот же, но цвета опасности нет."""
        import io, re
        kit = io.open('templates/_kit.html', encoding='utf-8').read()
        blank = re.search(r'\.k-mark\.k-mark--blank\s*\{([^}]*)\}', kit)
        self.assertIsNotNone(blank)
        self.assertNotIn('--error', blank.group(1))
