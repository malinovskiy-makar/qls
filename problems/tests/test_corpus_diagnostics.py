# -*- coding: utf-8 -*-
"""Диагностика корпуса (С13): что считать устареванием вектора.

Главная мысль модуля, ради которой он вообще существует: **правка текста
задачи и устаревание её вектора — не одно и то же**. В отпечаток
(`problem_to_text`) входят title, statement, подпункты, темы, навыки,
ai_blurb и канонические теги — и НЕ входят solution и answer. Значит,
фикс-пак, поправивший только решение, вектор не трогает.

Считать «правку текста» устареванием — завысить работу пересчёта.
Не считать правку statement — занизить и оставить поиск сломанным именно
на починенных задачах. Оба направления ошибки сторожатся здесь.
"""
from django.test import TestCase

from problems import corpus_diagnostics as diag
from problems.models import Problem, ProblemPart


class ShadowFingerprintTests(TestCase):
    """Отпечаток «каким он был до правки» — через настоящую формулу."""

    def setUp(self):
        self.problem = Problem.objects.create(
            title='Монополия', statement='Спрос P = 100 - Q.',
            answer='Q = 25', solution='Приравниваем MR = MC.',
        )
        ProblemPart.objects.create(
            problem=self.problem, label='а)', statement='Найдите выпуск.', order=1)

    def test_правка_solution_не_старит_вектор(self):
        """Решение в отпечаток не входит — пересчитывать нечего.

        Если бы этот тест был красным, пересчёт получил бы лишние задачи:
        фикс-паки правят решения массово.
        """
        self.assertFalse(diag.fingerprint_changed(
            self.problem, {'solution': 'Совершенно другое решение'}))

    def test_правка_answer_не_старит_вектор(self):
        self.assertFalse(diag.fingerprint_changed(self.problem, {'answer': 'Q = 999'}))

    def test_правка_statement_старит_вектор(self):
        self.assertTrue(diag.fingerprint_changed(
            self.problem, {'statement': 'Совсем другое условие'}))

    def test_правка_title_старит_вектор(self):
        """Заголовок стоит в отпечатке первым блоком."""
        self.assertTrue(diag.fingerprint_changed(self.problem, {'title': 'Другой заголовок'}))

    def test_правка_подпункта_старит_вектор(self):
        part = self.problem.parts.first()
        self.assertTrue(diag.fingerprint_changed(
            self.problem, {'parts': {part.pk: 'Найдите цену.'}}))

    def test_правка_за_границей_обрезки_вектор_не_трогает(self):
        """Формула берёт statement[:500]. Правка на 900-м символе в отпечаток
        не попадает, и объявлять такой вектор устаревшим — выдумывать работу.
        """
        long_statement = 'А' * 600 + 'хвост'
        Problem.objects.filter(pk=self.problem.pk).update(statement=long_statement)
        self.problem.refresh_from_db()
        self.assertFalse(diag.fingerprint_changed(
            self.problem, {'statement': 'А' * 600 + 'другой хвост'}))

    def test_пустой_набор_правок_ничего_не_старит(self):
        self.assertFalse(diag.fingerprint_changed(self.problem, {}))


class TokenizerTests(TestCase):
    """Токенизатор словарного покрытия: банк написан на LaTeX, не на прозе."""

    def test_имена_макросов_latex_не_считаются_словами(self):
        """Иначе топ частых слов возглавляют frac, sqrt, begin и hline.

        Замер до починки: в топ-50 «экономических слов вне словаря» попали
        шесть имён макросов. Список, где четверть позиций — разметка,
        отвечает не на тот вопрос, который задавали.
        """
        from problems.management.commands.corpus_diagnostics import _tokens

        self.assertEqual(_tokens(r'\frac{Q}{P} растёт'), ['q', 'p', 'растёт'.replace('ё', 'е')])

    def test_содержимое_фигурных_скобок_остаётся(self):
        """Внутри \text{} лежит настоящий русский текст — его терять нельзя."""
        from problems.management.commands.corpus_diagnostics import _tokens

        self.assertIn('спрос', _tokens(r'\text{спрос} = 5'))
