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
        bare = re.search(r'(?<![\w.\-\]])input\[type=[\'"]?number', rules)
        self.assertIsNone(bare, 'правило повешено на голый селектор')
