"""
Блок проверки на карточке позиции (фаза 3 сессии фиксов).

Восемь правок по приёмке: одна кнопка вместо двух, лишняя надпись «готово»
убрана, статус написан один раз, объяснение сокращено, правка эталона
переживает переключение режима, эталон не показан трижды, кликабельна вся
строка заголовка, состояние отделено от действия чертой.

⚠️ Часть этих правок живёт в JS и проверяется браузером
(`node scripts/night_item_card.js`). Здесь — то, что видно в разметке и в
данных: питон-тест не увидит, стёрлось ли поле по клику, но увидит, что
кнопки в блоке две.
"""
import re
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from problems.models import (
    Assignment, AssignmentItem, ProblemPart, StudentGroup,
)
from problems.tests.factories import make_problem, make_user

TEMPLATE = 'teacher/templates/teacher/groups/assignment_detail.html'


class CheckBlockMarkupTests(TestCase):
    """Разметка блока: кнопка одна, лишних надписей нет."""

    def setUp(self):
        self.tutor = make_user('t-check', role='teacher')
        self.group = StudentGroup.objects.create(name='Группа',
                                                 teacher=self.tutor)
        problem = make_problem('Задача из каталога.', answer='42',
                               difficulty=2)
        self.assignment = Assignment.objects.create(
            name='Работа', author=self.tutor, group=self.group)
        self.item = AssignmentItem.objects.create(
            assignment=self.assignment, order=0, catalog_problem=problem,
            points=Decimal('2'))
        self.client.force_login(self.tutor)

    def _page(self):
        return self.client.get(reverse(
            'teacher:group_assignment',
            args=[self.group.pk, self.assignment.pk])).content.decode()

    def _markup(self):
        """Разметка БЕЗ скриптов.

        ⚠️ В скрипте страницы лежат ОБЕ надписи кнопки (он их и переключает).
        Искать надпись по всему исходнику значит всегда находить обе и не
        проверить ничего.
        """
        return re.sub(r'<script.*?</script>', '', self._page(), flags=re.S)

    def _buttons(self):
        html = self._markup()
        block = re.search(r'class="ans-actions">(.*?)</div>', html, re.S)
        if block is None:
            return []
        return [re.sub(r'\s+', ' ', text).strip() for text
                in re.findall(r'<button[^>]*>(.*?)</button>', block.group(1),
                              re.S)]

    def test_one_button_when_not_approved(self):
        """Кнопка одна, и надпись — «Включить автопроверку»."""
        self.assertEqual(self._buttons(), ['Включить автопроверку'])
        markup = self._markup()
        self.assertNotIn('ans-save', markup)
        self.assertNotIn('ans-clear', markup)

    def test_label_reads_manual_when_approved(self):
        self.item.answer_override = {'': '42'}
        self.item.save(update_fields=['answer_override'])
        self.assertEqual(self._buttons(), ['Проверять вручную'])

    def test_no_meaningless_done_caption(self):
        """Слова «готово» на экране нет ни в одном состоянии."""
        self.assertNotIn('готово', self._markup().lower())
        self.item.answer_override = {'': '42'}
        self.item.save(update_fields=['answer_override'])
        self.assertNotIn('готово', self._markup().lower())

    def test_status_lives_only_in_the_header(self):
        """У кнопки нет подписи-состояния: она уже есть в заголовке."""
        markup = self._markup()
        self.assertNotIn('снято — задачу проверяете вы', markup)
        # Заголовок при этом на месте — состояние написано ровно один раз.
        self.assertEqual(markup.count('Проверять придётся вам, вручную'), 1)

    def test_explanation_is_short(self):
        """Длинное объяснение читают один раз, а мешает оно каждый."""
        html = self._page()
        match = re.search(r'class="check-why">(.*?)</p>', html, re.S)
        self.assertIsNotNone(match, 'объяснение пропало совсем')
        text = re.sub(r'<[^>]+>', '', match.group(1))
        text = ' '.join(text.split())
        self.assertLess(len(text), 120, 'объяснение снова разрослось: %s' % text)


class CatalogHintShownOnlyWhenDiffersTests(TestCase):
    """Подпись «в каталоге» — только там, где каталог расходится с полем.

    ⚠️ В одной карточке одни и те же значения выводились ТРИЖДЫ: в свёрнутой
    строке заголовка, в поле ввода и подписью справа от поля.
    """

    def setUp(self):
        self.tutor = make_user('t-hint', role='teacher')
        self.problem = make_problem('Фирма выпускает 100 единиц.',
                                    answer='5000', difficulty=2)
        self.assignment = Assignment.objects.create(name='Работа',
                                                    author=self.tutor)
        self.item = AssignmentItem.objects.create(
            assignment=self.assignment, order=0,
            catalog_problem=self.problem, points=Decimal('2'))

    def _rows(self):
        from teacher.views_groups import _answer_rows

        return _answer_rows(self.item)

    def test_same_value_hides_the_hint(self):
        self.item.answer_override = {'': '5000'}
        self.assertFalse(self._rows()[0]['catalog_differs'])

    def test_different_value_shows_the_hint(self):
        self.item.answer_override = {'': '4900'}
        self.assertTrue(self._rows()[0]['catalog_differs'])

    def test_nothing_approved_yet_hides_the_hint(self):
        """До утверждения в поле стоит ровно каталожный ответ."""
        self.assertFalse(self._rows()[0]['catalog_differs'])

    def test_spaces_do_not_count_as_a_difference(self):
        self.item.answer_override = {'': '  5000 '}
        self.assertFalse(self._rows()[0]['catalog_differs'])


class CheckBlockTemplateHygieneTests(TestCase):
    """То, что живёт в скрипте шаблона и не видно через клиента."""

    def _source(self):
        with open(TEMPLATE, encoding='utf-8') as handle:
            return handle.read()

    def test_toggle_does_not_wipe_the_fields(self):
        """⚠️ ГЛАВНЫЙ БАГ ФАЗЫ: возврат к ручной проверке ОЧИЩАЛ поля.

        Репетитор правил эталон, передумывал, возвращал ручную проверку — и
        терял набранное. Проверяем по исходнику: очистки значений в
        обработчике кнопки быть не должно.
        """
        source = self._source()
        self.assertNotIn("input.value = '';", source,
                         'переключение режима снова стирает поля')

    def test_header_and_body_are_separated(self):
        self.assertIn('.check-fold[open] .check-head { border-bottom',
                      self._source())

    def test_whole_header_row_is_clickable(self):
        source = self._source()
        self.assertIn('.check-fold > summary { list-style: none; '
                      'cursor: pointer; }', source)
        self.assertIn('check-open', source, 'значок раскрытия пропал')
