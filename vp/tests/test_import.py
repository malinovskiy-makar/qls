"""Тесты импорта вариантов: `manage.py import_vp` на синтетическом варианте.

Файл `data/vp/_selftest.yaml` — 44 учебных задания по структуре 1 тура: целая
цепочка змейки, сумма ровно 100. Здесь проверяется то, что раньше видели
глазами: инварианты, идемпотентность, отказы, разрыв цепочки и балл 100,00.
"""
import copy
import pathlib
import tempfile
from decimal import Decimal
from io import StringIO

import yaml
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from vp.models import VPAttempt, VPItem, VPVariant
from vp.scoring import score_attempt
from vp.tests.helpers import answer_all

SELFTEST = pathlib.Path(__file__).resolve().parents[2] / 'data' / 'vp' / '_selftest.yaml'


def load_data():
    return yaml.safe_load(SELFTEST.read_text(encoding='utf-8'))


class ImportTestCase(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, data, name='v.yaml'):
        path = pathlib.Path(self.tmp.name) / name
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                        encoding='utf-8')
        return str(path)

    def run_import(self, data_or_path, *args, expect_error=False):
        path = data_or_path if isinstance(data_or_path, str) else self.write(data_or_path)
        out, err = StringIO(), StringIO()
        if expect_error:
            with self.assertRaises(CommandError) as ctx:
                call_command('import_vp', path, *args, stdout=out, stderr=err)
            return out.getvalue(), err.getvalue() + str(ctx.exception)
        call_command('import_vp', path, *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def edited(self, number, **changes):
        data = copy.deepcopy(load_data())
        for item in data['items']:
            if item['n'] == number:
                item.update(changes)
        return data

    def without(self, number):
        data = copy.deepcopy(load_data())
        data['items'] = [i for i in data['items'] if i['n'] != number]
        return data


class InvariantsTests(ImportTestCase):
    def test_dry_run_prints_invariants_and_writes_nothing(self):
        out, _ = self.run_import(str(SELFTEST), '--dry-run')
        self.assertIn('Заданий в файле: 44', out)
        self.assertIn('Сумма баллов: 100.00', out)
        for block, count, points in (('snake', 30, '60.00'), ('gapfill', 5, '10.00'),
                                     ('multi', 5, '15.00'), ('analytic', 2, '6.00'),
                                     ('single', 2, '9.00')):
            self.assertRegex(out, rf'{block}\s+{count}\s+{points}')
        self.assertIn('Разрывов цепочки змейки: 0', out)
        self.assertEqual(VPVariant.objects.count(), 0)
        self.assertEqual(VPItem.objects.count(), 0)

    def test_real_import_then_repeat_reports_no_changes(self):
        self.run_import(str(SELFTEST))
        variant = VPVariant.objects.get(slug='vp-selftest')
        self.assertEqual(variant.items.count(), 44)
        self.assertEqual(variant.max_score, Decimal('100.00'))
        self.assertFalse(variant.is_published)
        out, _ = self.run_import(str(SELFTEST))
        self.assertIn('Изменений нет', out)
        self.assertEqual(VPVariant.objects.count(), 1)
        self.assertEqual(VPItem.objects.count(), 44)

    def test_publish_flag_publishes(self):
        self.run_import(str(SELFTEST), '--publish')
        self.assertTrue(VPVariant.objects.get(slug='vp-selftest').is_published)

    def test_chain_letters_filled_from_first_word(self):
        self.run_import(str(SELFTEST))
        item = VPItem.objects.get(variant__slug='vp-selftest', number=12)
        self.assertEqual(item.chain_word(), item.answer.split()[0])
        self.assertEqual((item.chain_first, item.chain_second), ('м', 'н'))


class ChainTests(ImportTestCase):
    def test_break_is_reported_and_import_goes_on_by_default(self):
        out, _ = self.run_import(self.edited(10, answer='яяум'))
        self.assertIn('Разрывов цепочки змейки: 2', out)  # №9→№10 и №10→№11
        self.assertIn('ожидалась буква', out)
        self.assertEqual(VPItem.objects.count(), 44)  # предупреждение, не отказ

    def test_strict_chain_refuses_and_writes_nothing(self):
        out, err = self.run_import(self.edited(10, answer='яяум'),
                                   '--strict-chain', expect_error=True)
        self.assertIn('ожидалась буква', out)
        self.assertIn('цепочка змейки разорвана', err)
        self.assertEqual(VPVariant.objects.count(), 0)

    def test_exact_break_message_format(self):
        data = self.edited(22, answer='отрасль')
        data['items'][22]['answer'] = 'потолок цены'  # №23: «п», а от «отрасль» ждут «т»
        out, _ = self.run_import(data, '--dry-run')
        self.assertIn('№22 «отрасль» → №23 «потолок цены»: ожидалась буква «т»', out)

    def test_answer_without_second_letter_is_a_break(self):
        out, _ = self.run_import(self.edited(3, answer='я'), '--dry-run')
        self.assertIn('нет второй буквы', out)


class RefusalTests(ImportTestCase):
    def refuse(self, data, needle):
        _, err = self.run_import(data, expect_error=True)
        self.assertIn(needle, err)
        self.assertEqual(VPVariant.objects.count(), 0)
        self.assertEqual(VPItem.objects.count(), 0)

    def test_missing_item_breaks_1_to_44(self):
        self.refuse(self.without(17), 'не образуют ровно 1..44')

    def test_duplicate_number(self):
        data = self.edited(18, n=17)
        self.refuse(data, 'номера заданий повторяются: [17]')

    def test_sum_not_100(self):
        self.refuse(self.edited(1, points=3), 'сумма `points`')

    def test_short_text_without_answer_names_the_number(self):
        self.refuse(self.edited(5, answer=''), '№5: у короткого ответа пусто поле `answer`')

    def test_empty_options_names_the_number(self):
        self.refuse(self.edited(33, options=[]), '№33: пусто `options`')

    def test_empty_correct_names_the_number(self):
        self.refuse(self.edited(38, correct=[]), '№38: пусто `correct`')

    def test_correct_out_of_options_names_the_number(self):
        self.refuse(self.edited(36, correct=[1, 6]),
                    '№36: `correct` ссылается на номер 6, которого нет в options')

    def test_non_positive_points_names_the_number(self):
        self.refuse(self.edited(7, points=0), '№7: `points` должен быть больше нуля')

    def test_bad_slug(self):
        data = load_data()
        data['slug'] = 'плохой слаг!'
        self.refuse(data, 'не подходит под шаблон slug')

    def test_max_score_ignores_file_value(self):
        data = load_data()
        data['max_score'] = 999
        self.run_import(data)
        self.assertEqual(VPVariant.objects.get().max_score, Decimal('100.00'))


class IdempotencyTests(ImportTestCase):
    def test_one_edit_shows_exactly_one_difference(self):
        """Ручной сценарий из ТЗ: правка условия в админке → ровно одно отличие."""
        self.run_import(str(SELFTEST))
        item = VPItem.objects.get(variant__slug='vp-selftest', number=12)
        item.statement += ' (опечатка)'
        item.save()
        out, _ = self.run_import(str(SELFTEST), '--dry-run')
        self.assertEqual(out.count('изменены поля'), 1)
        self.assertIn('№12: изменены поля statement', out)
        self.assertIn('Без изменений заданий: 43', out)
        # Сухой прогон ничего не вернул в исходное состояние.
        item.refresh_from_db()
        self.assertTrue(item.statement.endswith('(опечатка)'))

    def test_removed_item_is_deleted_when_no_attempts(self):
        self.run_import(str(SELFTEST))
        # Файл теперь короче на одно задание — но tour=1 требует 44; берём tour=2.
        data = self.without(44)
        data['tour'] = 2
        data['items'][-1]['points'] = 9  # 4 + 5, чтобы сумма осталась 100
        out, _ = self.run_import(data)
        self.assertIn('Удалены задания: [44]', out)
        self.assertEqual(VPItem.objects.filter(variant__slug='vp-selftest').count(), 43)

    def test_removed_item_refused_when_attempts_exist(self):
        self.run_import(str(SELFTEST))
        VPAttempt.objects.create(variant=VPVariant.objects.get(), public_code='abc')
        data = self.without(44)
        data['tour'] = 2
        data['items'][-1]['points'] = 9
        _, err = self.run_import(data, expect_error=True)
        self.assertIn('есть попытки', err)
        self.assertEqual(VPItem.objects.count(), 44)


class ScoreOnImportedVariantTests(ImportTestCase):
    def test_all_right_attempt_gives_100(self):
        self.run_import(str(SELFTEST))
        variant = VPVariant.objects.get(slug='vp-selftest')
        self.assertEqual(score_attempt(answer_all(variant, right=True)), Decimal('100.00'))
