"""Команда `find_olympiad_text_duplicates` — восемь проверок каскада.

Самый важный тест здесь — `test_3`: высокое текстовое сходство при
РАЗНЫХ числах не должно создавать ничего. Это защита от «шаблон тот же,
данные другие», и именно она отделяет копию задачи от другой задачи с
тем же сюжетом.

Тексты и векторы синтетические, но подобраны не на глаз: класс
`ДанныеСтендаTests` проверяет, что сходство действительно попадает в
нужный диапазон. Иначе тест проверял бы не то, что думает.
"""
import csv
import io
import os
import tempfile

import numpy as np
from django.core.management import call_command
from django.test import TestCase

from problems.embedding_config import EMBEDDING_DIM
from problems.models import OlympiadRef, Problem
from problems.text_dedup import fuzzy_ratio, normalize_for_compare

# Условие длиннее предохранителя минимальной длины (200 символов).
BASE = (
    'Фирма работает на рынке совершенной конкуренции. Обратная функция спроса '
    'задана как P = 100 - 2Q, а предельные издержки постоянны и равны 20 '
    'рублей за единицу выпуска. Найдите равновесный объём и равновесную цену, '
    'а также величину излишка потребителя в этой точке. ')
TAIL = 'э' * 60


def variant(changed):
    """Тот же текст с `changed` изменёнными буквами в хвосте.

    Меняются только буквы: числа условия обязаны остаться теми же, иначе
    тест про числовую проверку проверял бы не то.
    """
    return BASE + 'э' * (60 - changed) + 'ю' * changed


def other_numbers():
    """Тот же текст, но с другими исходными данными."""
    return BASE.replace('100', '900') + TAIL


def unit_vector(seed):
    """Нормированный вектор нужной размерности — как в банке (norm = 1)."""
    rng = np.random.default_rng(seed)
    vector = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    return (vector / np.linalg.norm(vector)).astype(np.float32).tobytes()


class БазаStendaMixin:
    """Общая обвязка: создание задач, якорей и запуск команды."""

    maxDiff = None

    def setUp(self):
        super().setUp()
        self.reports = tempfile.mkdtemp(prefix='olymp_dedup_')

    def problem(self, text, seed=1):
        return Problem.objects.create(statement=text, embedding=unit_vector(seed))

    def anchor(self, text, seed=1, *, slug='vseros', year=2021, stage='final',
               grade='9', name='Всероссийская олимпиада', site='solvehub',
               method='url_exact'):
        problem = self.problem(text, seed)
        OlympiadRef.objects.create(
            problem=problem, source_site=site, olympiad_slug=slug,
            olympiad_name=name, academic_year='2020/21', year=year, stage=stage,
            grade=grade, variant='Основной', number='4',
            event_id=f'{slug}-{year}-{stage}-{grade}-{problem.id}',
            record_id=f'rec-{problem.id}', match_method=method, match_score=1.0,
            official_url=f'https://example.test/{problem.id}')
        return problem

    def run_command(self, apply=True, **extra):
        args = ['--reports-dir', self.reports]
        if apply:
            args.append('--apply')
        for key, value in extra.items():
            args.extend([f'--{key.replace("_", "-")}', str(value)])
        call_command('find_olympiad_text_duplicates', *args,
                     stdout=io.StringIO(), stderr=io.StringIO())

    def read_csv(self, name):
        path = os.path.join(self.reports, name)
        if not os.path.exists(path):
            return []
        with open(path, encoding='utf-8', newline='') as handle:
            return list(csv.DictReader(handle))

    def propagated(self, problem):
        return OlympiadRef.objects.filter(
            problem=problem,
            match_method__in=('text_sha1', 'text_fuzzy_numeric'))


class ДанныеСтендаTests(TestCase):
    """Проверка самого стенда: сходство обязано попасть в нужный диапазон.

    Без этого тесты ниже могли бы проходить по неверной причине.
    """

    def test_три_изменённые_буквы_дают_сходство_выше_097(self):
        ratio = fuzzy_ratio(normalize_for_compare(BASE + TAIL),
                            normalize_for_compare(variant(3)))
        self.assertGreaterEqual(ratio, 0.97)

    def test_пятнадцать_букв_дают_сходство_между_090_и_097(self):
        ratio = fuzzy_ratio(normalize_for_compare(BASE + TAIL),
                            normalize_for_compare(variant(15)))
        self.assertGreaterEqual(ratio, 0.90)
        self.assertLess(ratio, 0.97)

    def test_у_текста_с_другими_числами_сходство_всё_ещё_выше_097(self):
        """Иначе тест 3 отсеивался бы порогом, а не числовой проверкой."""
        ratio = fuzzy_ratio(normalize_for_compare(BASE + TAIL),
                            normalize_for_compare(other_numbers()))
        self.assertGreaterEqual(ratio, 0.97)

    def test_условие_длиннее_предохранителя_короткого_текста(self):
        self.assertGreater(len(normalize_for_compare(BASE + TAIL)), 200)


class Тест1ТочноеСовпадениеTests(БазаStendaMixin, TestCase):

    def test_точное_совпадение_создаёт_text_sha1_и_переносит_поля(self):
        anchor = self.anchor(BASE + TAIL, seed=1)
        copy = self.problem(BASE + TAIL, seed=1)

        self.run_command()

        rows = list(self.propagated(copy))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.match_method, 'text_sha1')
        self.assertEqual(row.match_score, 1.0)
        self.assertFalse(row.reviewed_by_human)

        # Поля олимпиады перенесены БУКВАЛЬНО — в этом весь смысл пропагации.
        source = anchor.olympiad_refs.get()
        for field in ('olympiad_slug', 'olympiad_name', 'academic_year', 'year',
                      'stage', 'grade', 'variant', 'number', 'official_url',
                      'source_site', 'record_id'):
            self.assertEqual(getattr(row, field), getattr(source, field),
                             f'поле {field} не перенесено буквально')
        self.assertEqual(row.raw_meta['propagated_from_problem_id'], anchor.id)
        self.assertTrue(row.raw_meta['numeric_match'])


class Тест2СходствоИЧислаTests(БазаStendaMixin, TestCase):

    def test_высокое_сходство_и_совпавшие_числа_создают_text_fuzzy_numeric(self):
        anchor = self.anchor(BASE + TAIL, seed=2)
        copy = self.problem(variant(3), seed=2)

        self.run_command()

        rows = list(self.propagated(copy))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.match_method, 'text_fuzzy_numeric')
        self.assertGreaterEqual(row.match_score, 0.97)

        source = anchor.olympiad_refs.get()
        for field in ('olympiad_slug', 'olympiad_name', 'year', 'stage',
                      'grade', 'variant', 'number', 'official_url'):
            self.assertEqual(getattr(row, field), getattr(source, field),
                             f'поле {field} не перенесено буквально')


class Тест3РазныеЧислаTests(БазаStendaMixin, TestCase):
    """САМЫЙ ВАЖНЫЙ ТЕСТ ФАЗЫ.

    «$P = 100 - 2Q$» и «$P = 900 - 2Q$» — разные задачи с разными ответами.
    Текст при этом совпадает на 99 %, и косинус их сводит. Единственное,
    что их разделяет, — мультимножество чисел.
    """

    def test_высокое_сходство_но_разные_числа_не_создаёт_ничего(self):
        self.anchor(BASE + TAIL, seed=3)
        подделка = self.problem(other_numbers(), seed=3)

        self.run_command()

        self.assertEqual(self.propagated(подделка).count(), 0,
                         'числовая проверка пропустила задачу с другими данными')
        self.assertEqual(
            OlympiadRef.objects.count(), 1,
            'в базе появилась лишняя строка — числовой гейт не сработал')
        # И в очередь тоже не попало: это не пограничный случай, а другая задача.
        queue = self.read_csv('text_dedup_review_queue.csv')
        self.assertEqual(
            [r for r in queue if str(r['candidate_id']) == str(подделка.id)], [])


class Тест4ПограничнаяПолосаTests(БазаStendaMixin, TestCase):

    def test_сходство_090_097_уходит_в_очередь_а_не_в_базу(self):
        anchor = self.anchor(BASE + TAIL, seed=4)
        похожая = self.problem(variant(15), seed=4)

        self.run_command()

        self.assertEqual(self.propagated(похожая).count(), 0)
        self.assertEqual(OlympiadRef.objects.count(), 1)

        queue = self.read_csv('text_dedup_review_queue.csv')
        rows = [r for r in queue if str(r['candidate_id']) == str(похожая.id)]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['reason'], 'band_0.90_0.97')
        self.assertEqual(rows[0]['conflict'], 'false')
        self.assertEqual(rows[0]['anchor_id'], str(anchor.id))


class Тест5НесколькоКандидатовTests(БазаStendaMixin, TestCase):

    def test_три_кандидата_одного_якоря_все_получают_привязку(self):
        """Ни одна копия не теряется — сколько бы их ни было."""
        self.anchor(BASE + TAIL, seed=5)
        копии = [
            self.problem(BASE + TAIL, seed=5),   # точное совпадение
            self.problem(variant(2), seed=5),    # сходство выше 0,97
            self.problem(variant(4), seed=5),    # тоже выше 0,97
        ]

        self.run_command()

        for копия in копии:
            self.assertEqual(self.propagated(копия).count(), 1,
                             f'задача #{копия.id} потеряна')
        self.assertEqual(OlympiadRef.objects.count(), 1 + 3)


class Тест6КонфликтЯкорейTests(БазаStendaMixin, TestCase):

    def test_кандидат_двух_якорей_с_разной_олимпиадой_ничего_не_пишет(self):
        первый = self.anchor(BASE + TAIL, seed=6, slug='vseros', year=2021)
        второй = self.anchor(BASE + TAIL, seed=6, slug='mosh', year=2019,
                             name='Московская олимпиада')
        кандидат = self.problem(BASE + TAIL, seed=6)

        self.run_command()

        self.assertEqual(self.propagated(кандидат).count(), 0)
        self.assertEqual(OlympiadRef.objects.count(), 2, 'база изменилась')

        queue = self.read_csv('text_dedup_review_queue.csv')
        rows = [r for r in queue if str(r['candidate_id']) == str(кандидат.id)]
        self.assertEqual(len(rows), 2, 'в очередь должны попасть ОБА варианта')
        self.assertTrue(all(r['conflict'] == 'true' for r in rows))
        self.assertTrue(all(r['reason'] == 'anchor_conflict' for r in rows))
        self.assertEqual({r['anchor_id'] for r in rows},
                         {str(первый.id), str(второй.id)})
        # Перечислены все конфликтующие варианты, а не только свой.
        self.assertIn('vseros', rows[0]['variants'])
        self.assertIn('mosh', rows[0]['variants'])


class Тест7ЯкоряСогласныTests(БазаStendaMixin, TestCase):

    def test_совпадающая_олимпиада_в_файл_конфликтов_не_попадает(self):
        self.anchor(BASE + TAIL, seed=7, slug='vseros', year=2021, stage='final')
        self.anchor(variant(3), seed=7, slug='vseros', year=2021, stage='final',
                    site='ile')

        self.run_command()

        self.assertEqual(self.read_csv('anchor_metadata_conflicts.csv'), [])


class Тест8ЯкоряСпорятTests(БазаStendaMixin, TestCase):

    def test_разная_олимпиада_попадает_в_файл_и_база_не_меняется(self):
        левый = self.anchor(BASE + TAIL, seed=8, slug='vseros', year=2021)
        правый = self.anchor(variant(3), seed=8, slug='mosh', year=2019,
                             name='Московская олимпиада', site='ile')
        было = {r.id: (r.olympiad_slug, r.year, r.stage, r.grade)
                for r in OlympiadRef.objects.all()}

        self.run_command()

        rows = self.read_csv('anchor_metadata_conflicts.csv')
        self.assertEqual(len(rows), 1)
        пара = {rows[0]['problem_a'], rows[0]['problem_b']}
        self.assertEqual(пара, {str(левый.id), str(правый.id)})
        self.assertIn('vseros', rows[0]['a_says'] + rows[0]['b_says'])
        self.assertIn('mosh', rows[0]['a_says'] + rows[0]['b_says'])

        # Шаг C только докладывает: ни одна строка не создана и не изменена.
        стало = {r.id: (r.olympiad_slug, r.year, r.stage, r.grade)
                 for r in OlympiadRef.objects.all()}
        self.assertEqual(стало, было)
