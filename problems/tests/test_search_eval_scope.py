# -*- coding: utf-8 -*-
"""С14 — два среза поискового индекса.

Замер обязан считаться по двум разным множествам задач, и подписаны они
раздельно, потому что отвечают на разные вопросы:

  'prod' — что реально видит человек на сайте сегодня (5 078 задач). Это
           цифра, которую увидят бета-пользователи.
  'all'  — весь банк с вектором (31 694). Это цифра «как есть», по ней
           потом будет видно, помогли ли чистка корпуса и формула v2.

⚠️ ПО УМОЛЧАНИЮ — 'prod', И ЭТО ГЛАВНОЕ В ЭТОМ ФАЙЛЕ. Индекс сайта строится
той же функцией; ошибись здесь в умолчании — и в выдачу каталога поедут
скрытые и забракованные задачи. Поэтому первым же тестом проверяется, что
вызов без аргумента даёт ровно прежний, узкий набор.
"""
from django.test import TestCase

from catalog.semantic import index_queryset
from problems.models import Problem
from problems.tests.factories import make_problem


class IndexScopeTests(TestCase):

    def setUp(self):
        # Видна на сайте: опубликована, не забракована, просмотрена человеком.
        self.видимая = make_problem(title='видимая')
        Problem.objects.filter(pk=self.видимая.pk).update(
            status=Problem.Status.PUBLISHED, needs_quality_review=False,
            hidden_pending_review=False, embedding=b'\x00' * 4096)

        # Есть вектор, но человек её ещё не смотрел — на сайте её нет.
        self.непросмотренная = make_problem(title='непросмотренная')
        Problem.objects.filter(pk=self.непросмотренная.pk).update(
            status=Problem.Status.PUBLISHED, needs_quality_review=False,
            hidden_pending_review=True, embedding=b'\x00' * 4096)

        # Забракована детектором качества.
        self.бракованная = make_problem(title='бракованная')
        Problem.objects.filter(pk=self.бракованная.pk).update(
            status=Problem.Status.PUBLISHED, needs_quality_review=True,
            hidden_pending_review=False, embedding=b'\x00' * 4096)

        # Вектора нет вовсе — не попадает никуда.
        self.без_вектора = make_problem(title='без вектора')
        Problem.objects.filter(pk=self.без_вектора.pk).update(
            status=Problem.Status.PUBLISHED, needs_quality_review=False,
            hidden_pending_review=False, embedding=None)

    def _ids(self, scope=None):
        qs = index_queryset() if scope is None else index_queryset(scope)
        return set(qs.values_list('id', flat=True))

    def test_без_аргумента_срез_прода_как_было(self):
        self.assertEqual(self._ids(), {self.видимая.pk})

    def test_срез_прода_не_пускает_непросмотренное_и_бракованное(self):
        ids = self._ids('prod')
        self.assertNotIn(self.непросмотренная.pk, ids)
        self.assertNotIn(self.бракованная.pk, ids)

    def test_срез_всего_банка_берёт_всё_с_вектором(self):
        self.assertEqual(
            self._ids('all'),
            {self.видимая.pk, self.непросмотренная.pk, self.бракованная.pk},
        )

    def test_задача_без_вектора_не_попадает_ни_в_один_срез(self):
        self.assertNotIn(self.без_вектора.pk, self._ids('prod'))
        self.assertNotIn(self.без_вектора.pk, self._ids('all'))

    def test_неизвестный_срез_отвергается(self):
        # Опечатка в имени среза обязана падать громко: молча вернуть 'prod'
        # значило бы подписать отчёт «весь банк», посчитав его по 5 078.
        with self.assertRaises(ValueError):
            index_queryset('всё подряд')
