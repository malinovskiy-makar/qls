# -*- coding: utf-8 -*-
"""Чистка корпуса (`content_cleanup`) — фаза 3 задания сессии 03.09.2026.

Команда удаляет записи НЕОБРАТИМО, поэтому проверяется в первую очередь не
то, что она удаляет, а то, чего она НЕ удаляет: запись со ссылкой, запись с
подпунктами, запись с ответом или решением, запись со связным текстом.
"""
import json
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from problems.management.commands import content_cleanup as cmd
from problems.models import (Collection, Problem, ProblemPart, Source,
                             SourceReference)


class JunkPatternTests(TestCase):
    """Шаблон мусора обязан покрывать текст ЦЕЛИКОМ, а не находиться внутри."""

    def test_пустой_текст_это_мусор(self):
        self.assertEqual(cmd.junk_kind(''), 'пустой текст')
        self.assertEqual(cmd.junk_kind('   \n  '), 'пустой текст')

    def test_только_номер_задачи_это_мусор(self):
        self.assertIsNotNone(cmd.junk_kind('Задача 5.'))
        self.assertIsNotNone(cmd.junk_kind('Задание №12'))

    def test_только_номер_страницы_это_мусор(self):
        self.assertIsNotNone(cmd.junk_kind('  17  '))
        self.assertIsNotNone(cmd.junk_kind('стр. 42'))

    def test_только_разметка_это_мусор(self):
        self.assertIsNotNone(cmd.junk_kind('\\\\ $$ {} []'))

    def test_номер_задачи_В_НАЧАЛЕ_условия_это_НЕ_мусор(self):
        """Главная защита от катастрофы: «Задача 5.» стоит в начале доброй
        половины импортированных условий."""
        self.assertIsNone(cmd.junk_kind(
            'Задача 5. Фирма-монополист максимизирует прибыль при линейном '
            'спросе. Найдите равновесный выпуск.'))

    def test_данетка_это_НЕ_мусор(self):
        """Утверждение без вопросительного знака — настоящая задача подтипа
        «верно-неверно», модель принимает её за служебный текст."""
        self.assertIsNone(cmd.junk_kind('Алюминий добывают в шахтах.'))
        self.assertIsNone(cmd.junk_kind(
            'В России действует режим фиксированного курса валюты.'))


class DefectKindTests(TestCase):

    def test_опечатка_не_прячет_задачу(self):
        kind, hide = cmd.defect_kind('Мелкие опечатки, смыслу не мешают.')
        self.assertEqual(kind, 'опечатки, не мешающие смыслу')
        self.assertFalse(hide)

    def test_битая_формула_прячет(self):
        _kind, hide = cmd.defect_kind('Формула не отрендерилась, виден LaTeX.')
        self.assertTrue(hide)

    def test_опечатка_рядом_с_битой_формулой_всё_равно_прячет(self):
        """Порядок шаблонов: опечатки проверяются последними, иначе заметка
        про формулу И опечатку ушла бы в «опечатки» и задача осталась бы
        видимой с битой формулой."""
        kind, hide = cmd.defect_kind(
            'Опечатка в слове «спрос», и формула не отрендерилась.')
        self.assertTrue(hide)
        self.assertNotEqual(kind, 'опечатки, не мешающие смыслу')

    def test_неразобранная_заметка_прячет_по_умолчанию(self):
        """Умолчание — в сторону осторожности: скрыть лишнее обратимо,
        оставить битое на экране — нет."""
        _kind, hide = cmd.defect_kind('Что-то совершенно неожиданное.')
        self.assertTrue(hide)


class ClassifyNotAProblemTests(TestCase):
    """Четыре категории задания и — главное — что НЕ попадает в удаление."""

    def setUp(self):
        self.source = Source.objects.create(name='Тестовый источник')

    def _classify(self, problem, refs=None, parents=None):
        return cmd.classify_not_a_problem(
            [problem], {problem.id: refs or {}},
            {problem.id: parents or []})[problem.id]

    def test_пустая_запись_без_ссылок_удаляется(self):
        p = Problem.objects.create(statement='')
        category, _why, action = self._classify(p)
        self.assertEqual(category, 'технический мусор')
        self.assertEqual(action, 'удалить')

    def test_мусор_со_ссылкой_из_домашки_НЕ_удаляется(self):
        p = Problem.objects.create(statement='')
        category, _why, action = self._classify(p, refs={'assignments': 1})
        self.assertEqual(action, 'needs_fix')
        self.assertEqual(category, 'фрагмент с родителем')

    def test_мусор_с_подпунктами_НЕ_удаляется(self):
        p = Problem.objects.create(statement='')
        _c, _w, action = self._classify(p, refs={'parts': 2})
        self.assertEqual(action, 'needs_fix')

    def test_мусор_с_обрывающимся_соседом_НЕ_удаляется(self):
        p = Problem.objects.create(statement='')
        _c, _w, action = self._classify(
            p, parents=['сосед #1 того же источника обрывается на полуслове'])
        self.assertEqual(action, 'needs_fix')

    def test_мусор_с_ответом_НЕ_удаляется(self):
        """В `answer` лежит работа человека — она дороже чистоты списка."""
        p = Problem.objects.create(statement='', answer='верно')
        _c, _w, action = self._classify(p)
        self.assertEqual(action, 'needs_fix')

    def test_паспорт_источника_НЕ_мешает_удалению(self):
        """`source_references` есть у КАЖДОЙ импортированной записи. Считать
        его ссылкой значит не удалить никогда ничего."""
        p = Problem.objects.create(statement='')
        _c, _w, action = self._classify(p, refs={'source_references': 1})
        self.assertEqual(action, 'удалить')

    def test_связный_текст_без_ссылок_идёт_в_needs_fix_а_не_в_удаление(self):
        p = Problem.objects.create(
            statement='Алюминий добывают в шахтах.')
        category, _w, action = self._classify(p)
        self.assertEqual(action, 'needs_fix')
        self.assertEqual(category, 'фрагмент без родителя')


class LooksTruncatedTests(TestCase):

    def test_обрыв_на_полуслове(self):
        self.assertTrue(cmd.looks_truncated('Фирма выпускает товар и произ'))

    def test_законченное_предложение_не_обрыв(self):
        self.assertFalse(cmd.looks_truncated('Найдите равновесную цену.'))
        self.assertFalse(cmd.looks_truncated('Сколько стоит товар?'))

    def test_пустой_текст_не_обрыв(self):
        self.assertFalse(cmd.looks_truncated(''))


class CommandTests(TestCase):
    """Команда целиком: dry-run ничего не трогает, выгрузка идёт ДО удаления."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.nap = self.tmp / 'nap.jsonl'
        self.broken = self.tmp / 'broken.jsonl'
        self.dump = self.tmp / 'deleted.jsonl'
        self.decisions = self.tmp / 'decisions.json'

        self.junk = Problem.objects.create(statement='',
                                           status=Problem.Status.PUBLISHED)
        self.kept = Problem.objects.create(
            statement='Алюминий добывают в шахтах.',
            status=Problem.Status.PUBLISHED)
        self.used = Problem.objects.create(statement='',
                                           status=Problem.Status.PUBLISHED)
        collection = Collection.objects.create(name='Подборка')
        collection.problems.add(self.used)
        self.broken_one = Problem.objects.create(
            statement='Условие с битой формулой.',
            status=Problem.Status.PUBLISHED)
        self.typo_one = Problem.objects.create(
            statement='Условие с опечаткой.',
            status=Problem.Status.PUBLISHED)

        with open(self.nap, 'w', encoding='utf-8') as fh:
            for problem in (self.junk, self.kept, self.used):
                fh.write(json.dumps({'problem_id': problem.id}) + '\n')
        with open(self.broken, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps({
                'problem_id': self.broken_one.id,
                'text_quality_note': 'Формула не отрендерилась.'},
                ensure_ascii=False) + '\n')
            fh.write(json.dumps({
                'problem_id': self.typo_one.id,
                'text_quality_note': 'Мелкие опечатки, смыслу не мешают.'},
                ensure_ascii=False) + '\n')

    def _patch(self):
        return mock.patch.multiple(
            cmd,
            NOT_A_PROBLEM_QUEUE=self.nap,
            BROKEN_TEXT_QUEUE=self.broken,
            DELETED_DUMP=self.dump,
            DECISIONS_PATH=self.decisions,
        )

    def test_без_apply_база_не_меняется(self):
        with self._patch():
            call_command('content_cleanup')
        self.assertEqual(Problem.objects.count(), 5)
        self.assertFalse(Problem.objects.exclude(
            content_status=Problem.ContentStatus.OK).exists())

    def test_без_allow_delete_мусор_помечается_а_не_удаляется(self):
        with self._patch():
            call_command('content_cleanup', apply=True)
        self.assertEqual(Problem.objects.count(), 5)
        self.junk.refresh_from_db()
        self.assertEqual(self.junk.content_status,
                         Problem.ContentStatus.JUNK)

    def test_с_allow_delete_мусор_удаляется_а_остальное_нет(self):
        with self._patch():
            call_command('content_cleanup', apply=True, allow_delete=True)
        self.assertFalse(Problem.objects.filter(id=self.junk.id).exists())
        self.assertTrue(Problem.objects.filter(id=self.kept.id).exists())
        self.assertTrue(Problem.objects.filter(id=self.used.id).exists())

    def test_выгрузка_записана_до_удаления_и_полна(self):
        with self._patch():
            call_command('content_cleanup', apply=True, allow_delete=True)
        lines = [json.loads(line) for line
                 in self.dump.read_text(encoding='utf-8').splitlines()
                 if line.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]['id'], self.junk.id)
        # все конкретные поля модели, а не выборочные
        for field in Problem._meta.concrete_fields:
            self.assertIn(field.attname, lines[0])

    def test_неполная_выгрузка_отменяет_удаление(self):
        """Если файл на диске оказался короче списка — не удаляем НИЧЕГО."""
        real_open = open

        def short_open(path, *args, **kwargs):
            handle = real_open(path, *args, **kwargs)
            if str(path) == str(self.dump) and 'w' in (args[0] if args
                                                       else ''):
                handle.write('')
                handle.close()

                class _Sink:
                    def write(self, *a, **k):
                        return None

                    def __enter__(self):
                        return self

                    def __exit__(self, *a):
                        return False
                return _Sink()
            return handle

        with self._patch(), mock.patch(
                'problems.management.commands.content_cleanup.open',
                side_effect=short_open, create=True):
            with self.assertRaises(Exception):
                call_command('content_cleanup', apply=True, allow_delete=True)
        self.assertTrue(Problem.objects.filter(id=self.junk.id).exists())

    def test_опечатка_остаётся_видимой_а_битая_формула_прячется(self):
        with self._patch():
            call_command('content_cleanup', apply=True)
        self.typo_one.refresh_from_db()
        self.broken_one.refresh_from_db()
        self.assertEqual(self.typo_one.content_status,
                         Problem.ContentStatus.OK)
        self.assertEqual(self.broken_one.content_status,
                         Problem.ContentStatus.NEEDS_FIX)

    def test_revert_возвращает_всё_в_ok(self):
        with self._patch():
            call_command('content_cleanup', apply=True)
            call_command('content_cleanup', revert=True)
        self.assertFalse(Problem.objects.exclude(
            content_status=Problem.ContentStatus.OK).exists())

    def test_тексты_задач_не_меняются(self):
        """Свип-детектор P0: команда не имеет права трогать statement,
        answer, solution и подпункты."""
        part = ProblemPart.objects.create(
            problem=self.kept, label='а', statement='Подпункт а.')
        before = {p.id: (p.statement, p.answer, p.solution)
                  for p in Problem.objects.all()}
        with self._patch():
            call_command('content_cleanup', apply=True)
        for problem in Problem.objects.all():
            self.assertEqual(
                (problem.statement, problem.answer, problem.solution),
                before[problem.id])
        part.refresh_from_db()
        self.assertEqual(part.statement, 'Подпункт а.')


class ParentSignalsTests(TestCase):

    def test_обрывающийся_сосед_того_же_источника_находится(self):
        source = Source.objects.create(name='Листок')
        orphan = Problem.objects.create(statement='и тогда прибыль равна.')
        neighbour = Problem.objects.create(
            statement='Фирма выпускает товар, издержки её равны и произ')
        SourceReference.objects.create(problem=orphan, source=source,
                                       problem_number='5')
        SourceReference.objects.create(problem=neighbour, source=source,
                                       problem_number='4')
        signals = cmd.parent_signals([orphan.id])
        self.assertTrue(signals[orphan.id])

    def test_сосед_с_далёким_номером_не_считается(self):
        source = Source.objects.create(name='Листок')
        orphan = Problem.objects.create(statement='и тогда прибыль равна.')
        far = Problem.objects.create(statement='Фирма выпускает и произ')
        SourceReference.objects.create(problem=orphan, source=source,
                                       problem_number='5')
        SourceReference.objects.create(problem=far, source=source,
                                       problem_number='99')
        signals = cmd.parent_signals([orphan.id])
        self.assertFalse(signals.get(orphan.id))
