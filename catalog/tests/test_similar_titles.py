# -*- coding: utf-8 -*-
"""Заголовки карточек «Похожие задачи» — без обрывков формул.

Владелец: в блоке «Похожие задачи» видны «голые доллары». Разбор по банку
(41 307 задач) показал ДВЕ разные причины, и лечить их надо по-разному:

* **449 заголовков** — обрезанное условие: импортёр положил в `title` первые
  ~80 символов текста, и рез пришёлся посреди формулы («…имеют вид $x =»).
  Незакрытый доллар KaTeX формулой не считает и не трогает — на карточке
  остаётся знак доллара с огрызком. Это чиним.
* **12 заголовков** — ВАЛЮТА без эскейпа: «Торговля рисом при мировой цене
  $3», «Цена продавцов при налоге $2». Это целые, осмысленные заголовки, и
  доллар в них — часть смысла. Резать их нельзя: пропадёт ровно то число,
  ради которого заголовок написан.

Плюс 2 504 задачи вовсе без заголовка — им берём начало условия, как в
списке каталога.
"""
from django.test import TestCase

from catalog.views import similar_title
from problems.models import Problem


class FakeProblem:
    """Задача без базы: проверяем чистую функцию, а не запросы."""

    def __init__(self, title='', statement=''):
        self.title = title
        self.statement = statement


class SimilarTitleTests(TestCase):

    def test_whole_formula_survives(self):
        """Целая формула остаётся целиком — её отрисует KaTeX."""
        p = FakeProblem(title='Спрос $Q_d = 120-P$, дальше')
        self.assertEqual(similar_title(p), 'Спрос $Q_d = 120-P$, дальше')

    def test_truncated_formula_is_cut_off(self):
        """Обрывок формулы срезается вместе с одиноким долларом."""
        p = FakeProblem(title='Спрос $Q_d = 12')
        result = similar_title(p)
        self.assertEqual(result, 'Спрос…')
        self.assertNotIn('$', result)

    def test_currency_is_kept(self):
        """⚠️ ГЛАВНАЯ ПРОВЕРКА: валюту не режем.

        Правило «нечётное число долларов → обрезать» испортило бы 12 живых
        заголовков банка, выкинув из них цену.
        """
        for title in ('Торговля рисом при мировой цене $3',
                      'Цена продавцов при налоге $2',
                      'Результат фирмы в краткосрочном периоде при цене $10'):
            self.assertEqual(similar_title(FakeProblem(title=title)), title)

    def test_empty_title_falls_back_to_statement(self):
        p = FakeProblem(
            title='',
            statement='Пусть спрос задан как $Q=10-P$, а предложение как '
                      '$Q=P$. Найдите равновесие, излишки и выручку продавца '
                      'при равновесной цене.')
        result = similar_title(p)
        self.assertTrue(result.startswith('Пусть спрос задан как'))
        self.assertNotIn('$', result)
        self.assertTrue(result.endswith('…'))
        self.assertLessEqual(len(result), 91)

    def test_short_statement_gets_no_ellipsis(self):
        p = FakeProblem(title='', statement='Найдите равновесие.')
        self.assertEqual(similar_title(p), 'Найдите равновесие.')

    def test_escaped_dollar_is_not_a_delimiter(self):
        """«\\$» — валюта в разметке источника, разделителем не считается."""
        title = r'Доход равен \$120 в неделю'
        self.assertEqual(similar_title(FakeProblem(title=title)), title)

    def test_plain_title_untouched(self):
        p = FakeProblem(title='Разложение функции издержек')
        self.assertEqual(similar_title(p), 'Разложение функции издержек')


class SimilarBlockRenderTests(TestCase):
    """Та же проверка, но на отрисованной странице задачи."""

    def setUp(self):
        self.main = Problem.objects.create(
            statement='Основная задача', status=Problem.Status.PUBLISHED,
            needs_quality_review=False, hidden_pending_review=False)
        self.whole = Problem.objects.create(
            title='Спрос $Q_d = 120-P$, дальше',
            statement='целая формула', status=Problem.Status.PUBLISHED,
            needs_quality_review=False, hidden_pending_review=False)
        self.cut = Problem.objects.create(
            title='Спрос $Q_d = 12',
            statement='обрывок', status=Problem.Status.PUBLISHED,
            needs_quality_review=False, hidden_pending_review=False)
        self.main.similar_problems.add(self.whole, self.cut)

    def test_page_keeps_whole_formula_and_drops_the_stub(self):
        html = self.client.get(
            '/catalog/problem/%d/' % self.main.pk).content.decode('utf-8')
        self.assertIn('Спрос $Q_d = 120-P$, дальше', html)
        self.assertIn('Спрос…', html)
        self.assertNotIn('Спрос $Q_d = 12<', html)
