# -*- coding: utf-8 -*-
u"""Функциональная проверка `dump_for_deploy --bank-only`.

ЗАЧЕМ ЭТОТ ФАЙЛ ОТДЕЛЬНО ОТ test_deploy_dump.py. Тот файл — чисто
рефлективные проверки (SimpleTestCase, без базы): читают списки моделей и
поля классов, но ни разу не запускают команду. Здесь — наоборот: настоящие
строки в базе (User, Submission, Problem с owner) и настоящий прогон
команды, чтобы доказать эмпирически, а не только по именам полей, что
--bank-only не выносит работу ученика и учётные записи в файлы фикстур.

Решение владельца 2026-09-02: на прод — только банк задач (152-ФЗ).
"""
import json
import os
import shutil
import tempfile

from django.core.management import call_command
from django.test import TestCase

from problems.models import (
    Assignment, Hint, MistakeTag, Problem, ProblemFigure, Skill, Source,
    SourceReference, Submission, Tag, Topic, User,
)


def _read_all_fixture_rows(outdir):
    rows = []
    for name in sorted(os.listdir(outdir)):
        if not name.endswith('.json'):
            continue
        with open(os.path.join(outdir, name), encoding='utf-8') as fh:
            rows.extend(json.load(fh))
    return rows


class BankOnlyDumpTests(TestCase):

    def setUp(self):
        self.outdir = tempfile.mkdtemp(prefix='bank_only_dump_')
        self.addCleanup(shutil.rmtree, self.outdir, ignore_errors=True)

        self.teacher = User.objects.create_user(
            username='teacher1', password='x', role=User.Role.TEACHER)
        self.student = User.objects.create_user(
            username='student1', password='x', role=User.Role.STUDENT)

        self.topic = Topic.objects.create(name='Спрос и предложение',
                                          slug='demand-supply')
        self.tag = Tag.objects.create(name='базовый', slug='basic')
        self.source = Source.objects.create(name='Сборник АА', year=2020)
        self.skill = Skill.objects.create(name='Построить график спроса')
        self.mistake = MistakeTag.objects.create(name='Путает спрос и величину спроса')

        self.problem = Problem.objects.create(
            statement='Условие задачи', answer='42',
            status=Problem.Status.PUBLISHED, owner=self.teacher,
        )
        self.problem.topics.add(self.topic)
        self.problem.tags.add(self.tag)
        self.problem.skills.add(self.skill)
        self.problem.mistakes.add(self.mistake)
        SourceReference.objects.create(problem=self.problem, source=self.source)
        Hint.objects.create(problem=self.problem, order=1, text='Подумай о графике')
        ProblemFigure.objects.create(
            problem=self.problem, tikz_hash='a' * 64,
            tikz_source='\\begin{tikzpicture}\\end{tikzpicture}',
            svg='<svg></svg>')

        assignment = Assignment.objects.create(name='ДЗ №1')
        Submission.objects.create(student=self.student, assignment=assignment,
                                  problem=self.problem, solution_text='Мой ответ')

    def _run(self):
        call_command('dump_for_deploy', '--outdir', self.outdir,
                    '--chunk', '2000', '--bank-only')
        return _read_all_fixture_rows(self.outdir)

    def test_excludes_users_and_student_work(self):
        u"""User и Submission не попадают ни в один файл дампа."""
        rows = self._run()
        models_present = {row['model'] for row in rows}
        self.assertNotIn('problems.user', models_present)
        self.assertNotIn('problems.submission', models_present)
        self.assertNotIn('problems.assignment', models_present)

    def test_includes_bank_content(self):
        u"""Содержательные таблицы банка при этом на месте."""
        rows = self._run()
        models_present = {row['model'] for row in rows}
        for expected in ('problems.problem', 'problems.topic', 'problems.tag',
                         'problems.source', 'problems.sourcereference',
                         'problems.skill', 'problems.mistaketag', 'problems.hint',
                         'problems.problemfigure'):
            self.assertIn(expected, models_present)

    def test_problem_row_has_no_dangling_reference_to_excluded_models(self):
        u"""У Problem нет ни owner (-> User), ни files (-> FileAsset) —
        обе модели не входят в --bank-only, и висячая ссылка уронит
        заливку в чистую PostgreSQL внешним ключом."""
        rows = self._run()
        problem_rows = [r for r in rows if r['model'] == 'problems.problem']
        self.assertEqual(len(problem_rows), 1)
        fields = problem_rows[0]['fields']
        self.assertNotIn('owner', fields)
        self.assertNotIn('files', fields)
        self.assertNotIn('embedding', fields)
        self.assertNotIn('similar_problems', fields)
        # А содержательные M2M — на месте.
        self.assertEqual(fields['topics'], [self.topic.pk])
        self.assertEqual(fields['skills'], [self.skill.pk])
