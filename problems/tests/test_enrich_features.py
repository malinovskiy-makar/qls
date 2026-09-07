# -*- coding: utf-8 -*-
"""Особенности задачи: канон, витрина каталога и порог показа.

Витрина `Problem.features` — производное от связи `ProblemFeature`, а не
второе место хранения. Здесь проверяется именно это: что витрина строится
одной функцией, что расхождение видно, и что команда пересчёта его чинит.
"""
from django.core.management import call_command
from django.test import TestCase

from problems.enrich import features as feat
from problems.enrich.layout import ensure_features, merge_feature_sources
from problems.models import Feature, Problem, ProblemFeature


class CanonTests(TestCase):
    """Список особенностей закрыт решением владельца — ровно двенадцать."""

    def test_особенностей_двенадцать_шесть_и_шесть(self):
        self.assertEqual(len(feat.CATALOG_FEATURES), 12)
        self.assertEqual(len(feat.MODEL_KEYS), 6)
        self.assertEqual(len(feat.CODE_KEYS), 6)

    def test_список_модели_совпадает_с_промптом(self):
        """Канон и промпт — одно и то же множество, иначе прогон вернёт
        особенность, которой в справочнике нет."""
        from problems.enrich.prompts_v2 import FEATURES_1
        self.assertEqual(set(feat.MODEL_KEYS), set(FEATURES_1))

    def test_убранные_владельцем_особенности_не_вернулись(self):
        keys = set(feat.ALL_KEYS)
        self.assertNotIn('реальные_данные', keys)
        self.assertNotIn('нестандартный_поворот', keys)

    def test_справочник_в_базе_повторяет_канон(self):
        ensure_features()
        self.assertEqual(
            list(Feature.objects.order_by('order').values_list('key', flat=True)),
            list(feat.ALL_KEYS))

    def test_наполнение_справочника_идемпотентно(self):
        ensure_features()
        ensure_features()
        self.assertEqual(Feature.objects.count(), 12)


class CatalogViewTests(TestCase):
    """Три ключа фильтра — объединение особенностей по правилу владельца."""

    def test_график_зажигается_любой_из_трёх_особенностей(self):
        for key in ('графическое_решение', 'нужен_график_в_ответе', 'график_в_условии'):
            self.assertEqual(feat.catalog_view([key]), ['graph'], key)

    def test_таблица_и_доказательство(self):
        self.assertEqual(feat.catalog_view(['табличка_в_условии']), ['table'])
        self.assertEqual(feat.catalog_view(['на_доказательство']), ['proof'])

    def test_особенность_вне_витрины_ничего_не_зажигает(self):
        self.assertEqual(feat.catalog_view(['параметры', 'бизнесовое']), [])

    def test_пустой_вход_даёт_пустую_витрину(self):
        self.assertEqual(feat.catalog_view([]), [])
        self.assertEqual(feat.catalog_view(None), [])


class CoverageGateTests(TestCase):
    """Особенность без данных в фильтр не выводится."""

    def test_олимпиадная_скрыта_при_низком_покрытии(self):
        visible = feat.catalog_visible_keys({'с_реальной_олимпиады': 0.07})
        self.assertNotIn('с_реальной_олимпиады', visible)

    def test_олимпиадная_появляется_при_достижении_порога(self):
        visible = feat.catalog_visible_keys(
            {'с_реальной_олимпиады': feat.MIN_CATALOG_COVERAGE})
        self.assertIn('с_реальной_олимпиады', visible)

    def test_остальные_особенности_порогом_не_ограничены(self):
        visible = feat.catalog_visible_keys({})
        self.assertIn('параметры', visible)
        self.assertIn('многопунктовая', visible)


class FeatureSourceTests(TestCase):
    """Кто поставил особенность — модель, код или оба."""

    def test_совпадение_модели_и_кода_даёт_both(self):
        merged = merge_feature_sources({'графическое_решение'},
                                       {'графическое_решение'})
        self.assertEqual(merged['графическое_решение'], feat.BY_BOTH)

    def test_только_модель_и_только_код(self):
        merged = merge_feature_sources({'параметры'}, {'многопунктовая'})
        self.assertEqual(merged['параметры'], feat.BY_MODEL)
        self.assertEqual(merged['многопунктовая'], feat.BY_CODE)

    def test_чужой_ключ_не_проходит(self):
        merged = merge_feature_sources({'выдуманная'}, {'тоже_выдуманная'})
        self.assertEqual(merged, {})


class ViewMatchesLinksTests(TestCase):
    """⚠️ ГЛАВНЫЙ ТЕСТ ДВУХСЛОЙНОГО ХРАНЕНИЯ: витрина обязана совпадать со
    связью. Если он покраснел — где-то появился второй способ писать
    `Problem.features`, и данные разъедутся молча."""

    def setUp(self):
        self.features = ensure_features()
        self.problem = Problem.objects.create(
            title='Тест', statement='Условие', answer='42')
        ProblemFeature.objects.create(
            problem=self.problem, feature=self.features['на_доказательство'],
            source=feat.BY_MODEL)
        call_command('rebuild_feature_view', '--apply', verbosity=0)
        self.problem.refresh_from_db()

    def test_витрина_собрана_из_связи(self):
        self.assertEqual(self.problem.features, ['proof'])

    def test_повторный_пересчёт_ничего_не_меняет(self):
        call_command('rebuild_feature_view', '--apply', verbosity=0)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.features, ['proof'])

    def test_расхождение_витрины_и_связи_чинится_пересчётом(self):
        Problem.objects.filter(pk=self.problem.pk).update(features=['graph', 'table'])
        call_command('rebuild_feature_view', '--apply', verbosity=0)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.features, ['proof'])

    def test_снятая_связь_убирает_ключ_из_витрины(self):
        ProblemFeature.objects.filter(problem=self.problem).delete()
        call_command('rebuild_feature_view', '--apply', verbosity=0)
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.features, [])
