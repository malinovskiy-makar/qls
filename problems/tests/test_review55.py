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
        import re

        source = inspect.getsource(hw_generator)
        # ⚠️ УТОЧНЁН (ревью 15.08, фаза 13). Проверка ищет ПАРАМЕТР ОТБОРА
        # `has_solution=`, а не любое упоминание слова: с этой сессии
        # карточка кандидата честно сообщает, ЕСТЬ ЛИ у задачи эталонное
        # решение (`'has_solution': bool(problem.solution)`) — это сведение
        # для глаз репетитора, а не фильтр. Смысл требования прежний:
        # фильтровать по решению, обещая ответ, нельзя.
        self.assertFalse(re.search(r'has_solution\s*=', source),
                         'параметр отбора по решению вернулся')


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


# ===========================================================================
# Фаза 5 — одна кнопка «Создание работы»
# ===========================================================================

class OneCreateButtonTests(TestCase):
    """Вход один, но ни один путь не потерян."""

    def setUp(self):
        from problems.models import StudentGroup
        from problems.tests.factories import make_user

        self.tutor = make_user('ocb_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.client.force_login(self.tutor)

    def _tab(self):
        from django.urls import reverse
        return self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments').content.decode()

    def test_one_button_instead_of_two(self):
        body = self._tab()
        self.assertIn('Создание работы', body)
        self.assertNotIn('Создать домашку', body)
        self.assertNotIn('Создать контрольную', body)

    def test_the_button_carries_the_group(self):
        """⚠️ ПЕРЕСЧИТАНО 17.08: вход в поток переехал на `work_start`.

        Проверка та же по смыслу — единственная кнопка входа несёт номер
        занятия, — но адрес теперь другой: сборка работы идёт по новому
        потоку, а вход чистит корзину этого занятия.
        """
        self.assertIn('/teacher/work/start/?group=%d' % self.group.pk,
                      self._tab())

    def test_the_kind_switch_keeps_the_group(self):
        """⚠️ Пока входов было два, группа приходила в адресе каждого.

        Со ОДНИМ входом потеря `group` на переключателе означала бы, что
        контрольная тихо собирается без окна и лимита времени.

        ⚠️ ПЕРЕСЧИТАНО 17.08: порядок параметров задаёт сборщик адреса
        (`views_work.flow_query`), и проверять его строкой значит ломаться
        от перестановки, которая ничего не меняет. Проверяем наличие обоих.
        """
        from django.urls import reverse

        body = self.client.get(
            reverse('teacher:assignment_generate')
            + '?group=%d' % self.group.pk).content.decode()
        switch = body.split('bh-kind"', 1)[1].split('</div>', 1)[0]
        self.assertIn('kind=exam', switch)
        self.assertIn('group=%d' % self.group.pk, switch)
        # Домашка — это отсутствие `kind=exam`, а не отдельное слово.
        self.assertEqual(switch.count('kind=exam'), 1)

    def test_exam_path_reaches_its_own_constructor(self):
        """Контрольная доходит до своего обработчика ВНУТРИ группы.

        Без номера группы такого адреса нет вовсе, и раньше путь молча
        уводил в обработчик домашки: настройки времени спросить было негде.

        ⚠️ ПЕРЕСЧИТАНО 17.08: адрес собирает шаг «Выдача» — там выбирают
        занятие, и там же стоят поля окна и лимита. На шаге подбора его
        больше нет и быть не должно.
        """
        from django.urls import reverse

        body = self.client.get(
            reverse('teacher:work_give')
            + '?kind=exam&group=%d' % self.group.pk).content.decode()
        self.assertIn('/teacher/groups/0/exams/new/', body)
        self.assertIn('name="starts_at"', body)


# ===========================================================================
# Фаза 6 — кольцо фокуса в каталоге нейтральное
# ===========================================================================

class CatalogFocusRingTests(TestCase):
    """Малиновое кольцо фокуса убрано со всех четырёх страниц каталога."""

    PAGES = (
        'catalog/templates/catalog/home.html',
        'catalog/templates/catalog/smart_search.html',
        'catalog/templates/catalog/problem_list.html',
        'catalog/templates/catalog/collection_new.html',
        'catalog/templates/catalog/collection_detail.html',
    )

    def test_no_accent_in_any_focus_rule(self):
        import io, re
        for path in self.PAGES:
            css = io.open(path, encoding='utf-8').read()
            for chunk in re.findall(r'([^{}]*:focus[^{}]*)\{([^}]*)\}', css):
                self.assertNotIn('--accent', chunk[1],
                                 '%s: %s' % (path, chunk[0].strip()))

    def test_selected_state_keeps_the_accent(self):
        """⚠️ Подсветка ВЫБРАННОГО — не фокус.

        Правило проекта прямо разрешает акцент на активном состоянии;
        вычищать его заодно значило бы лечить не ту болезнь.
        """
        import io
        css = io.open('catalog/templates/catalog/collection_new.html',
                      encoding='utf-8').read()
        self.assertIn('.tpl-card.selected', css)
        self.assertIn('var(--accent)', css)


# ===========================================================================
# Фаза 7 — четыре бага подбора по описанию
# ===========================================================================

class PickerFormActionTests(TestCase):
    """7.1 — поле `action` затеняло `form.action` и форма уходила в 404."""

    def setUp(self):
        from problems.tests.factories import make_user
        self.tutor = make_user('pfa_tutor', role='teacher')
        self.client.force_login(self.tutor)

    def test_no_field_named_action_in_the_picker(self):
        import io
        template = io.open('teacher/templates/teacher/generate.html',
                           encoding='utf-8').read()
        import re
        rules = re.sub(r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}', '',
                       template, flags=re.S)
        self.assertNotIn('name="action"', rules)
        self.assertIn('name="step_action"', rules)

    def test_every_form_has_an_explicit_address(self):
        """Без атрибута `action` у формы нет строкового адреса вовсе."""
        import io, re
        template = io.open('teacher/templates/teacher/generate.html',
                           encoding='utf-8').read()
        for tag in re.findall(r'<form[^>]*>', template):
            self.assertIn('action=', tag, tag)

    def test_the_server_reads_the_new_name(self):
        from django.urls import reverse

        response = self.client.post(reverse('teacher:assignment_generate'),
                                    {'step_action': 'research'})
        # Строк плана нет — но это ОБРАБОТАННЫЙ запрос, а не 404.
        self.assertEqual(response.status_code, 200)


class AiQuotaTests(TestCase):
    """7.3 — неудачная попытка не тратит суточное обращение."""

    def setUp(self):
        from problems.tests.factories import make_user
        self.tutor = make_user('quota_tutor', role='teacher')

    def _log(self, ok):
        from problems.models import AiUsageLog
        AiUsageLog.objects.create(user=self.tutor, kind='homework_plan',
                                  model_name='claude-haiku-4-5', ok=ok)

    def test_failed_calls_do_not_count(self):
        from problems import ai

        for _ in range(5):
            self._log(ok=False)
        self.assertEqual(ai.used_today(self.tutor), 0)

    def test_successful_calls_count(self):
        from problems import ai

        self._log(ok=True)
        self._log(ok=False)
        self._log(ok=True)
        self.assertEqual(ai.used_today(self.tutor), 2)

    def test_failures_stay_in_the_journal(self):
        """Строки отказов не удаляем — по ним чинят поломку."""
        from problems.models import AiUsageLog

        self._log(ok=False)
        self.assertEqual(AiUsageLog.objects.filter(user=self.tutor).count(), 1)


class AiErrorTextTests(TestCase):
    """7.4 — три человеческих текста вместо кода ошибки."""

    def _text(self, kind):
        from problems.ai import AiUnavailable
        from teacher.views_generate import _human_error
        return _human_error(AiUnavailable('Сервис вернул ошибку (401)',
                                          kind=kind))['text']

    def test_no_key(self):
        self.assertIn('не настроен доступ', self._text('no_key'))

    def test_limit_names_the_number(self):
        from problems import ai
        self.assertIn(str(ai.daily_limit()), self._text('limit'))

    def test_other(self):
        self.assertIn('не ответил', self._text('other'))

    def test_the_error_code_never_reaches_the_screen(self):
        for kind in ('no_key', 'limit', 'other'):
            self.assertNotIn('401', self._text(kind))
            self.assertNotIn('(', self._text(kind).replace('(30 в сутки)', ''))


# ===========================================================================
# Фаза 8 — как считается статистика
# ===========================================================================

class StatsFormulaTests(TestCase):
    """Формулы владельца: вес неполного балла, состав, «Всего», два числа."""

    def setUp(self):
        from problems.management.commands.apply_topic_mapping import CANONICAL
        from problems.models import (Assignment, AssignmentItem, StudentGroup,
                                     Submission, TeacherFeedback, Topic)
        from problems.tests.factories import make_user
        from problems.tests.factories import make_problem as factory_problem

        self.tutor = make_user('sf_tutor', role='teacher')
        self.other = make_user('sf_other', role='teacher')
        self.student = make_user('sf_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        # Темы каталога должны существовать: строки строятся по ним.
        # ⚠️ slug уникален и не заполняется сам — без него все 21 тема
        # получили бы пустой slug и вторая упала бы на ограничении.
        for index, name in enumerate(CANONICAL):
            Topic.objects.get_or_create(name=name,
                                        defaults={'slug': 'topic-%d' % index})
        self.topic = Topic.objects.get(name='Эластичность')

        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        problem = factory_problem('Условие про эластичность')
        problem.topics.add(self.topic)
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0, catalog_problem=problem,
            points=Decimal('10'))
        self.sub = Submission.objects.create(
            student=self.student, assignment=self.work,
            problem_item=self.item, status='reviewed')
        TeacherFeedback.objects.create(submission=self.sub,
                                       score=Decimal('8'),
                                       reviewed_by=self.tutor)

    def test_partial_score_counts_as_a_weight(self):
        """8 из 10 — это вклад 0,8, а не «верно» и не «неверно»."""
        from problems import stats

        rows = stats.topic_progress(self.student)['rows']
        row = [r for r in rows if r['name'] == 'Эластичность'][0]
        self.assertEqual(row['solved'], 1)
        self.assertEqual(row['percent'], 80)

    def test_every_canonical_topic_is_present(self):
        """Тема без попыток — пустая строка, а не пропуск (8.1).

        ⚠️ Число берётся ИЗ САМОГО СПИСКА, а не зашито цифрой. Раньше здесь
        стояла 21, и расширение атласа до 23 (сессия 9, фаза 2) покрасило
        тест, который на самом деле проверяет другое: что показаны ВСЕ темы
        канона, а не сколько их сегодня.
        """
        from problems.management.commands.apply_topic_mapping import CANONICAL
        from problems import stats

        result = stats.topic_progress(self.student)
        self.assertEqual(len(result['rows']), len(CANONICAL))
        empty = [r for r in result['rows'] if r['empty']]
        self.assertEqual(len(empty), len(CANONICAL) - 1)

    def test_total_row_counts_over_all_tasks(self):
        """«Всего» — по всем задачам, а не среднее из процентов тем (8.7)."""
        from problems import stats

        total = stats.topic_progress(self.student)['total']
        self.assertEqual(total['name'], 'Всего')
        self.assertEqual(total['solved'], 1)
        self.assertEqual(total['percent'], 80)

    def test_two_numbers_of_accuracy(self):
        """По всему сайту и по работам ЭТОГО репетитора (8.8)."""
        from problems import stats

        pair = stats.accuracy_pair(self.student, tutor=self.tutor)
        self.assertEqual(pair['all'], 80)
        self.assertEqual(pair['mine'], 80)
        # Чужой репетитор своих работ не имеет — второе число пусто.
        other = stats.accuracy_pair(self.student, tutor=self.other)
        self.assertEqual(other['all'], 80)
        self.assertIsNone(other['mine'])

    def test_game_is_in_neither_number(self):
        """⚠️ Поправка владельца: игра не входит НИ В ОДНО из двух чисел.

        В игре другой формат ответа и другая цена ошибки; смешивание портит
        обе шкалы.
        """
        from problems import stats
        from problems.models import LearningEvent

        for _ in range(20):
            LearningEvent.objects.create(user=self.student, source='game',
                                         event_type='failed',
                                         topic=self.topic)
        pair = stats.accuracy_pair(self.student, tutor=self.tutor)
        self.assertEqual(pair['all'], 80)     # не поехало от двадцати ошибок
        self.assertEqual(pair['mine'], 80)

    def test_game_is_in_the_heatmap(self):
        """…но в теплокарту владения темами игра ВХОДИТ (8.6).

        Привязка есть: 7 219 вопросов пула из 8 782 несут каноническую тему,
        и game/views.py резолвит её в LearningEvent.topic.
        """
        from problems import stats
        from problems.models import LearningEvent

        LearningEvent.objects.create(user=self.student, source='game',
                                     event_type='solved', topic=self.topic)
        matrix = stats.group_topic_matrix(self.group)
        cells = {c['topic_id']: c for c in matrix['columns']}
        self.assertGreater(cells[self.topic.pk]['attempted'], 0)

    def test_heatmap_shows_every_canonical_topic(self):
        from problems.management.commands.apply_topic_mapping import CANONICAL
        from problems import stats

        matrix = stats.group_topic_matrix(self.group)
        self.assertEqual(len(matrix['columns']), len(CANONICAL))

    def test_group_average_is_weighted_by_solved_count(self):
        """8.3 — средневзвешенное по числу решённых, не среднее из процентов.

        Второй ученик решает одну задачу на 0 из 10. Среднее из процентов
        дало бы 40 %; правильный ответ — 40 % только если у них поровну
        задач, а здесь их поровну и есть, поэтому добавляем третьего с
        двумя верными: среднее из процентов дало бы 60 %, взвешенное — 65 %.
        """
        from problems import stats
        from problems.models import (Assignment, AssignmentItem, Submission,
                                     TeacherFeedback)
        from problems.tests.factories import make_problem as factory_problem
        from problems.tests.factories import make_user

        weak = make_user('sf_weak', role='student')
        self.group.students.add(weak)
        self.work.students.add(weak)
        sub = Submission.objects.create(student=weak, assignment=self.work,
                                        problem_item=self.item,
                                        status='reviewed')
        TeacherFeedback.objects.create(submission=sub, score=Decimal('0'),
                                       reviewed_by=self.tutor)
        # Двое: 0,8 и 0,0 по одной задаче каждый → 40 %.
        self.assertEqual(stats.group_accuracy(self.group, tutor=self.tutor),
                         40)

        strong = make_user('sf_strong', role='student')
        self.group.students.add(strong)
        self.work.students.add(strong)
        for _ in range(2):
            item = AssignmentItem.objects.create(
                assignment=self.work, order=AssignmentItem.objects.count(),
                catalog_problem=factory_problem('Ещё условие'),
                points=Decimal('10'))
            s = Submission.objects.create(student=strong, assignment=self.work,
                                          problem_item=item, status='reviewed')
            TeacherFeedback.objects.create(submission=s, score=Decimal('10'),
                                           reviewed_by=self.tutor)
        # Взвешенно: (0,8 + 0 + 1 + 1) / 4 = 70 %.
        # Среднее из процентов дало бы (80 + 0 + 100) / 3 = 60 %.
        self.assertEqual(stats.group_accuracy(self.group, tutor=self.tutor),
                         70)

    def test_levels_follow_the_owner_thresholds(self):
        from problems import stats

        self.assertEqual(stats.level_of(70), 'good')
        self.assertEqual(stats.level_of(69), 'mid')
        self.assertEqual(stats.level_of(40), 'mid')
        self.assertEqual(stats.level_of(39), 'bad')
        self.assertEqual(stats.level_of(None), 'none')


# ===========================================================================
# Фаза 9 — субъективная сложность работы
# ===========================================================================

class WorkDifficultyTests(TestCase):
    """Ученик сам оценивает работу по шкале 1–10. Вопрос необязательный."""

    def setUp(self):
        from problems.models import Assignment, StudentGroup
        from problems.tests.factories import make_user

        self.tutor = make_user('wd_tutor', role='teacher')
        self.student = make_user('wd_student', role='student')
        self.other = make_user('wd_other', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student, self.other)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student, self.other)
        self.client.force_login(self.student)

    def _url(self):
        from django.urls import reverse
        return reverse('student:rate_difficulty', args=[self.work.pk])

    def test_vote_is_saved(self):
        from problems.models_platform import WorkDifficulty

        response = self.client.post(self._url(), {'value': '7'})
        self.assertEqual(response.status_code, 200)
        vote = WorkDifficulty.objects.get(assignment=self.work,
                                          student=self.student)
        self.assertEqual(vote.value, 7)

    def test_second_vote_updates_instead_of_duplicating(self):
        from problems.models_platform import WorkDifficulty

        self.client.post(self._url(), {'value': '3'})
        self.client.post(self._url(), {'value': '9'})
        votes = WorkDifficulty.objects.filter(assignment=self.work,
                                              student=self.student)
        self.assertEqual(votes.count(), 1)
        self.assertEqual(votes.first().value, 9)

    def test_out_of_range_is_refused_politely(self):
        from problems.models_platform import WorkDifficulty

        for bad in ('0', '11', '-3', 'много', ''):
            response = self.client.post(self._url(), {'value': bad})
            self.assertEqual(response.status_code, 400, bad)
        self.assertFalse(WorkDifficulty.objects.exists())

    def test_average_over_a_work(self):
        from problems.models_platform import (WorkDifficulty,
                                              difficulty_for_work)

        WorkDifficulty.objects.create(assignment=self.work,
                                      student=self.student, value=4)
        WorkDifficulty.objects.create(assignment=self.work,
                                      student=self.other, value=5)
        self.assertEqual(difficulty_for_work(self.work), 4.5)

    def test_average_over_a_student(self):
        from problems.models import Assignment
        from problems.models_platform import (WorkDifficulty,
                                              difficulty_for_student)

        second = Assignment.objects.create(name='ДЗ2', author=self.tutor,
                                           group=self.group)
        WorkDifficulty.objects.create(assignment=self.work,
                                      student=self.student, value=4)
        WorkDifficulty.objects.create(assignment=second,
                                      student=self.student, value=7)
        self.assertEqual(difficulty_for_student(self.student), 5.5)

    def test_empty_state_is_none_not_zero(self):
        """⚠️ Ноль по шкале 1–10 означал бы оценку, а её нет.

        Поэтому «нет оценок» пишется словами, а функция отдаёт None.
        """
        from problems.models_platform import (difficulty_for_student,
                                              difficulty_for_work)

        self.assertIsNone(difficulty_for_work(self.work))
        self.assertIsNone(difficulty_for_student(self.student))

    def test_the_question_is_a_div_not_a_nested_form(self):
        """Вложенную форму браузер выбрасывает — на этом уже обжигались."""
        import io, re
        template = io.open('student/templates/student/work_review.html',
                           encoding='utf-8').read()
        # Режем по РАЗМЕТКЕ, а не по первому вхождению имени класса: выше по
        # файлу лежит его же CSS, и срез от него ничего не проверял бы.
        start = template.index('<div class="wr-diff"')
        block = template[start:template.index('<div class="wr-order">')]
        self.assertNotIn('<form', block)
        self.assertIn('type="button"', block)

    def test_tutor_is_not_asked(self):
        """Репетитор работу не решал — спрашивать его не о чем."""
        from django.urls import reverse

        self.client.force_login(self.tutor)
        body = self.client.get(
            reverse('teacher:student_work_review',
                    args=[self.group.pk, self.work.pk,
                          self.student.pk])).content.decode()
        self.assertNotIn('Насколько сложной была работа', body)


# ===========================================================================
# Фаза 10 — карточка ученика
# ===========================================================================

class StudentCardTests(TestCase):
    """Один экран об ученике вместо двух; шкалы не малиновые; заметки."""

    def setUp(self):
        from problems.management.commands.apply_topic_mapping import CANONICAL
        from problems.models import (Assignment, AssignmentItem, StudentGroup,
                                     Submission, TeacherFeedback, Topic)
        from problems.tests.factories import make_user
        from problems.tests.factories import make_problem as factory_problem

        self.tutor = make_user('sc_tutor', role='teacher')
        self.student = make_user('sc_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        for index, name in enumerate(CANONICAL):
            Topic.objects.get_or_create(name=name,
                                        defaults={'slug': 'sc-%d' % index})
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=factory_problem('Условие'), points=Decimal('10'))
        sub = Submission.objects.create(student=self.student,
                                        assignment=self.work,
                                        problem_item=item, status='reviewed')
        TeacherFeedback.objects.create(submission=sub, score=Decimal('8'),
                                       reviewed_by=self.tutor)
        self.client.force_login(self.tutor)

    def _url(self):
        from django.urls import reverse
        return reverse('teacher:student_progress', args=[self.student.pk])

    def test_the_second_screen_redirects_here(self):
        """⚠️ Стоп-гейт 10.1: экран об ученике ровно ОДИН."""
        from django.urls import reverse

        response = self.client.get(
            reverse('teacher:student_stats', args=[self.student.pk]))
        self.assertRedirects(response, self._url())

    def test_three_cards_replaced_the_old_four(self):
        body = self.client.get(self._url()).content.decode()
        self.assertIn('Процент верно решённых задач', body)
        self.assertIn('Процент верно решённых тестов', body)
        self.assertIn('Средняя сложность работ', body)
        for gone in ('Открытых проверено', 'Тестов пройдено',
                     'Верных ответов'):
            self.assertNotIn(gone, body, gone)

    def test_progress_shows_tasks_and_tests(self):
        """⚠️ Было ДВЕ карточки, стал ОДИН блок в две колонки (сессия 9,
        фаза 7.3). Требование то же: на экране есть и задачи, и тесты —
        просто теперь в одной строке темы, а не в двух списках по 23 строки.
        """
        body = self.client.get(self._url()).content.decode()
        self.assertIn('Прогресс по темам', body)
        self.assertIn('>Задачи<', body)
        self.assertIn('>Тесты<', body)

    def test_bars_are_not_magenta(self):
        """⚠️ Малиновый в шкалах ЗАПРЕЩЁН — это и просили убрать.

        Проверяем правила заливки шкалы: цвет берётся из сигнальных токенов
        (зелёный / янтарь / красный), акцентного среди них нет.
        """
        import io, re
        # ⚠️ Правила `.tp-*` переехали в общий `platform/_stats_style.html`
        # (сессия 9, фаза 9): тот же блок прогресса стоит и на обзоре
        # индивидуального занятия.
        template = io.open(
            'problems/templates/platform/_stats_style.html',
            encoding='utf-8').read()
        for rule in re.findall(r'\.tp-fill--\w+\s*\{([^}]*)\}', template):
            self.assertNotIn('--accent', rule)
        self.assertIn('.tp-fill--good', template)
        self.assertIn('.tp-fill--mid', template)
        self.assertIn('.tp-fill--bad', template)

    def test_topic_column_has_a_fixed_width(self):
        """«Все шкалы начинаются от одной вертикали» — это и есть колонка.

        ⚠️ Ширины изменились в сессии 9 (фаза 7.3): строка стала двухколоночной
        (тема · задачи · разделитель · тесты), поэтому имя темы 200px, а
        значение 58px внутри половины. Требование то же — колонка имени
        ФИКСИРОВАННАЯ, иначе шкалы стартуют каждая со своего места.
        """
        import io
        template = io.open(
            'problems/templates/platform/_stats_style.html',
            encoding='utf-8').read()
        self.assertIn('grid-template-columns: 200px 1fr 1px 1fr', template)
        self.assertIn('.tp-half .tp-value { width: 58px', template)

    def test_hover_swap_is_pure_css(self):
        """⚠️ Наведение теперь на ПОЛОВИНЕ, а не на всей строке (фаза 7.3).

        Половин две, и подмена процента на дробь сразу в обеих означала бы,
        что посмотреть дробь только по тестам нельзя.
        """
        import io
        template = io.open(
            'problems/templates/platform/_stats_style.html',
            encoding='utf-8').read()
        self.assertIn('.tp-half:hover .tp-value .frac', template)
        self.assertNotIn('.tp-row:hover .tp-value .frac', template)

    def test_work_history_has_seven_columns(self):
        body = self.client.get(self._url()).content.decode()
        for column in ('Работа', 'Тип', '% верных задач', '% верных тестов',
                       'Оценка', 'Дата сдачи', 'Дедлайн'):
            self.assertIn(column, body, column)

    def test_mark_is_a_percent_not_raw_points(self):
        """У разных работ разный максимум — сырые баллы несопоставимы."""
        rows = self.client.get(self._url()).context['works']
        self.assertEqual(rows[0]['mark'], 80)

    def test_note_saves_and_is_private(self):
        from problems.models_platform import TutorNote
        from problems.tests.factories import make_user

        self.client.post(self._url(), {'note': 'быстро считает, но спешит'})
        note = TutorNote.objects.get(tutor=self.tutor, student=self.student)
        self.assertEqual(note.text, 'быстро считает, но спешит')

        # Чужой репетитор своей заметки здесь не заводил — и видит пустое.
        other = make_user('sc_other', role='teacher')
        self.group.students.add(self.student)
        from problems.models import StudentGroup
        StudentGroup.objects.create(name='Гр2',
                                    teacher=other).students.add(self.student)
        self.client.force_login(other)
        self.assertNotIn('быстро считает',
                         self.client.get(self._url()).content.decode())

    def test_note_uses_the_kit_field(self):
        """Владелец просил поле из набора, а не голую textarea."""
        body = self.client.get(self._url()).content.decode()
        self.assertIn('class="k-area" name="note"', body)
        self.assertIn('Видно только вам', body)

    def test_personal_facts_are_shown_when_filled(self):
        profile = self.student.profile
        profile.grade = 10
        profile.city = 'Казань'
        profile.goal = 'победитель региона'
        profile.save()
        body = self.client.get(self._url()).content.decode()
        self.assertIn('Казань', body)
        self.assertIn('победитель региона', body)

    def test_empty_facts_are_not_written_as_unset(self):
        """«Не указано» — строка ни о чём; пустое поле просто не рисуется.

        Смотрим САМ БЛОК фактов, а не всю страницу: выше по ней идёт
        таблица стилей, и в её комментарии это выражение упоминается как
        раз затем, чтобы объяснить, почему его нет в разметке.
        """
        body = self.client.get(self._url()).content.decode()
        start = body.find('<div class="student-facts">')
        if start == -1:
            return                       # ни одно поле не заполнено — блока нет
        block = body[start:body.index('</div>', start)]
        self.assertNotIn('не указано', block.lower())
        self.assertNotIn('—', block)


# ===========================================================================
# Фаза 14 — экран проверки работы
# ===========================================================================

class ReviewSkeletonTests(TestCase):
    """Скелет задачи ОДИН И ТОТ ЖЕ, что бы ученик ни написал."""

    def setUp(self):
        from problems.models import (Assignment, AssignmentItem, StudentGroup,
                                     Submission)
        from problems.tests.factories import make_user
        from problems.tests.factories import make_problem as factory_problem

        self.tutor = make_user('rs_tutor', role='teacher')
        self.student = make_user('rs_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=factory_problem('Условие'), points=Decimal('6'))
        self.sub = Submission.objects.create(
            student=self.student, assignment=self.work,
            problem_item=self.item, status='submitted')
        self.client.force_login(self.tutor)

    def _body(self):
        from django.urls import reverse
        return self.client.get(
            reverse('teacher:group_review_submission',
                    args=[self.group.pk, self.sub.pk])).content.decode()

    def test_skeleton_is_the_same_with_and_without_a_solution(self):
        """⚠️ Раньше блок решения появлялся по условию, и экран ПЛАВАЛ."""
        empty = self._body()
        self.assertIn('Решение ученика', empty)
        self.assertIn('решение не написано', empty)

        self.sub.solution_text = 'Считаем по формуле'
        self.sub.save(update_fields=['solution_text'])
        filled = self._body()
        self.assertIn('Решение ученика', filled)
        self.assertNotIn('решение не написано', filled)

    def test_the_caption_no_longer_changes_shape(self):
        """«но решение написал:» меняла ЗАГОЛОВОК блока — то есть скелет."""
        self.sub.solution_text = 'Рассуждение без ответа'
        self.sub.save(update_fields=['solution_text'])
        self.assertNotIn('но решение написал', self._body())

    def test_answer_block_is_always_there(self):
        self.assertIn('ответил ученик', self._body())
        self.assertIn('ответа нет', self._body())

    def test_grading_block_is_separated(self):
        body = self._body()
        self.assertIn('rv-grade', body)
        self.assertIn('Оценивание', body)

    def test_state_uses_the_shared_kit_classes(self):
        """Цвета — те же, что в разборе работы; своих на экране нет."""
        body = self._body()
        self.assertIn('k-mark k-mark--pending', body)
        self.assertIn('k-flag k-flag--pending', body)

    def test_states_match_the_review_screen(self):
        from decimal import Decimal as D

        from problems.models import TeacherFeedback
        from teacher.views import _answer_state

        feedback = TeacherFeedback.objects.create(submission=self.sub,
                                                  score=D('6'))
        self.assertEqual(_answer_state(feedback, 6, False), 'correct')
        feedback.score = D('3')
        self.assertEqual(_answer_state(feedback, 6, False), 'partial')
        feedback.score = D('0')
        self.assertEqual(_answer_state(feedback, 6, False), 'wrong')
        # ⚠️ Ноль за ПУСТОТУ — не «неверно»: балл тот же, но ошибиться
        # ученик не успел.
        self.assertEqual(_answer_state(feedback, 6, True), 'blank')
        self.assertEqual(_answer_state(None, 6, False), 'pending')

    def test_image_solution_is_shown_whole(self):
        """Решение картинкой показываем целиком, а не ссылкой (14.2)."""
        import io
        template = io.open('teacher/templates/teacher/review.html',
                           encoding='utf-8').read()
        self.assertIn('rv-solution-img', template)
        self.assertIn('max-width: 100%', template)


# ===========================================================================
# Фаза 12.0 — вид первого шага подбора (поправка 5 владельца)
# ===========================================================================

class PickerFirstStepTests(TestCase):
    """Переделан ВИД. Полей не убрано и не добавлено ни одного."""

    # Список полей ДО правки — выписан из шаблона перед переделкой.
    FIELDS = ('text', 'count_open', 'count_test',
              'min_difficulty', 'max_difficulty', 'has_answer',
              'step_action', 'kind', 'group')

    def setUp(self):
        from problems.models import StudentGroup
        from problems.tests.factories import make_user

        self.tutor = make_user('pf_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.client.force_login(self.tutor)

    def _body(self):
        """⚠️ С ПОДСТАВНЫМ ПОСТАВЩИКОМ. Без него слой модели выключен, экран
        честно показывает «Функция выключена», и проверять на нём нечего."""
        from django.test import override_settings
        from django.urls import reverse

        with override_settings(AI_PROVIDER='fake'):
            return self.client.get(
                reverse('teacher:assignment_generate')
                + '?group=%d' % self.group.pk).content.decode()

    def test_every_field_survived(self):
        body = self._body()
        for name in self.FIELDS:
            self.assertIn('name="%s"' % name, body, name)

    def test_no_extra_fields_appeared(self):
        import re
        names = set(re.findall(r'<(?:input|textarea|select)[^>]*name="([^"]+)"',
                               self._body()))
        names.discard('csrfmiddlewaretoken')
        self.assertEqual(names, set(self.FIELDS))

    def test_fields_are_grouped_into_cards(self):
        body = self._body()
        self.assertIn('Опишите словами', body)
        self.assertIn('Сколько и какой сложности', body)

    def test_examples_are_behind_a_quiet_disclosure(self):
        """Подсказка занимала столько же места, сколько само поле ввода."""
        body = self._body()
        self.assertIn('gen-examples', body)
        self.assertIn('<summary>Так тоже можно</summary>', body)

    def test_usage_counter_sits_next_to_the_button(self):
        import re
        body = self._body()
        actions = re.search(r'<div class="gen-actions">(.*?)</div>', body,
                            re.S).group(1)
        self.assertIn('сегодня использовано', actions)

    def test_active_step_is_not_magenta(self):
        """⚠️ Шаги формы — не навигация сайта, акцент им не полагается.

        ПЕРЕСЧИТАН (ревью 17.08, п. 4.1): свой ряд шагов у подбора удалён,
        на экране осталась ОДНА лента — общая для потока. Требование то же
        и проверяется на ней.
        """
        import io, re
        kit = io.open('templates/_kit.html', encoding='utf-8').read()
        rule = re.search(r'\.wk-rail__s\.is-on[^{]*\{([^}]*)\}', kit)
        self.assertIsNotNone(rule, 'правила активного шага ленты нет')
        self.assertNotIn('background: var(--accent)', rule.group(1))

    def test_number_fields_share_one_width(self):
        import io
        template = io.open('teacher/templates/teacher/generate.html',
                           encoding='utf-8').read()
        # ⚠️ ПЕРЕСЧИТАНО (визуальная сессия 17.08, п. 1.1). Числа на этом
        # экране правятся без рамки (`.k-num`), и класс поля сменился;
        # смысл проверки прежний — ширина у всех трёх одна и задана здесь.
        self.assertIn('.gen-params .k-num { width: 68px; min-width: 68px; }',
                      template)
