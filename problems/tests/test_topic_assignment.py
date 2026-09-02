u"""
Тесты двух команд простановки тем: из источника и через модель.

Главные инварианты, ради которых они написаны:
- обе пишут ТОЛЬКО `topics` и не трогают тексты задачи (запрет P0);
- наружу уходит только заголовок и условие — ни ответа, ни решения;
- сухой прогон не обращается к API вовсе;
- таблица соответствий целиком лежит в каноническом списке тем.
"""
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from io import StringIO

from problems.models import Problem, Topic
from problems.management.commands.apply_topic_mapping import CANONICAL
from problems.management.commands import assign_topics_by_model as by_model
from problems.management.commands.assign_topics_from_source import (
    SOLVEHUB_TO_CANONICAL, SOLVEHUB_SECTIONS)


class SourceMappingTests(SimpleTestCase):
    u"""Таблица соответствий SolveHub → банк."""

    def test_every_target_is_canonical(self):
        u"""Неканоническая тема справа = мусор в фильтре каталога."""
        bad = sorted(set(SOLVEHUB_TO_CANONICAL.values()) - set(CANONICAL))
        self.assertEqual(bad, [], u'вне канона: %s' % bad)

    def test_sections_are_not_mapped(self):
        u"""Раздел дерева темой не становится: «тема: микроэкономика» —
        это не тема, это половина курса."""
        overlap = sorted(set(SOLVEHUB_SECTIONS) & set(SOLVEHUB_TO_CANONICAL))
        self.assertEqual(overlap, [], u'раздел попал в темы: %s' % overlap)


class ModelRequestTests(TestCase):
    u"""Что уходит наружу и что не уходит."""

    def setUp(self):
        self.problem = Problem.objects.create(
            title=u'Заголовок задачи',
            statement=u'Монополист максимизирует прибыль. Найдите объём.',
            answer=u'СЕКРЕТНЫЙ_ОТВЕТ_42',
            solution=u'СЕКРЕТНОЕ_РЕШЕНИЕ: приравниваем MR к MC.',
            problem_type=u'тест: один ответ',
            status=Problem.Status.PUBLISHED)

    def test_request_carries_only_title_and_statement(self):
        text = by_model.user_text(self.problem)
        self.assertIn(u'Заголовок задачи', text)
        self.assertIn(u'Найдите объём', text)
        self.assertNotIn(u'СЕКРЕТНЫЙ_ОТВЕТ_42', text)
        self.assertNotIn(u'СЕКРЕТНОЕ_РЕШЕНИЕ', text)

    def test_request_carries_the_closed_topic_list(self):
        u"""Список тем закрытый: без него модель сочинит свою тему."""
        text = by_model.user_text(self.problem)
        for name in CANONICAL:
            self.assertIn(name, text)

    def test_dry_run_never_touches_the_network(self):
        u"""Смета обязана считаться без единого обращения к API.

        Ломаем сам клиент: если команда полезет наружу, тест покраснеет."""
        import problems.management.commands.assign_topics_by_model as mod

        class Boom(object):
            def __getattr__(self, name):
                raise AssertionError(u'сухой прогон полез в сеть: %s' % name)

        real_import = __builtins__['__import__'] \
            if isinstance(__builtins__, dict) else __builtins__.__import__

        def guard(name, *args, **kwargs):
            if name == 'anthropic':
                raise AssertionError(u'сухой прогон импортировал anthropic')
            return real_import(name, *args, **kwargs)

        # Задача обязана реально попасть в смету: на пустом пуле проверка
        # прошла бы, ничего не посчитав.
        from game.models import GameQuestion
        GameQuestion.objects.create(
            problem=self.problem, question_type='single',
            question=u'Вопрос', options=['а', 'б'], correct_index=0,
            topics=[], lang='ru')

        import builtins
        builtins.__import__ = guard
        try:
            out = StringIO()
            call_command('assign_topics_by_model', '--dry-run', stdout=out)
        finally:
            builtins.__import__ = real_import
        text = out.getvalue()
        self.assertIn(u'Ничего не отправлено', text)
        self.assertIn(mod.MODEL, text)
        self.assertIn(u'задач без темы в пуле: 1', text)

    def test_submit_without_a_ceiling_is_refused(self):
        u"""Потолок расхода задаёт человек, а не команда."""
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError) as ctx:
            call_command('assign_topics_by_model', '--submit',
                         stdout=StringIO())
        self.assertIn('--max-cost', str(ctx.exception))


class ApplyWritesOnlyTopicsTests(TestCase):
    u"""Запись трогает только M2M тем."""

    def test_texts_are_untouched(self):
        topic = Topic.objects.create(name=CANONICAL[7])
        problem = Problem.objects.create(
            title=u'Т', statement=u'Условие', answer=u'а',
            solution=u'решение', problem_type=u'тест: один ответ',
            status=Problem.Status.PUBLISHED)
        before = (problem.statement, problem.answer, problem.solution)

        import json
        import os
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), 'res.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'results': {str(problem.id): {
                'topic_primary': CANONICAL[7],
                'topics_secondary': [],
                'confidence': 0.9}}}, fh, ensure_ascii=False)

        call_command('assign_topics_by_model', '--apply', path,
                     stdout=StringIO())
        problem.refresh_from_db()
        self.assertEqual((problem.statement, problem.answer,
                          problem.solution), before)
        self.assertEqual([t.name for t in problem.topics.all()], [topic.name])

    def test_low_confidence_is_not_written(self):
        Topic.objects.create(name=CANONICAL[7])
        problem = Problem.objects.create(
            title=u'Т', statement=u'Условие', answer=u'а',
            problem_type=u'тест: один ответ',
            status=Problem.Status.PUBLISHED)
        import json
        import os
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), 'res.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'results': {str(problem.id): {
                'topic_primary': CANONICAL[7],
                'topics_secondary': [],
                'confidence': 0.2}}}, fh, ensure_ascii=False)
        call_command('assign_topics_by_model', '--apply', path,
                     stdout=StringIO())
        self.assertEqual(problem.topics.count(), 0)

    def test_topic_outside_the_canon_is_dropped(self):
        problem = Problem.objects.create(
            title=u'Т', statement=u'Условие', answer=u'а',
            problem_type=u'тест: один ответ',
            status=Problem.Status.PUBLISHED)
        import json
        import os
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), 'res.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'results': {str(problem.id): {
                'topic_primary': u'Придуманная моделью тема',
                'topics_secondary': [],
                'confidence': 0.99}}}, fh, ensure_ascii=False)
        call_command('assign_topics_by_model', '--apply', path,
                     stdout=StringIO())
        self.assertEqual(problem.topics.count(), 0)
