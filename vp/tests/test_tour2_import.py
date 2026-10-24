"""Загрузчик для 2 тура: демоверсии ВШЭ 9/10/11 и испорченные копии.

Испорченные копии делаются в памяти и во временной папке теста, файлы в
`data/vp/` не трогаются. Каждая порча даёт СВОЮ понятную ошибку, а не общий отказ.
"""
import copy
import pathlib
import tempfile
from decimal import Decimal
from io import StringIO

import yaml
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from vp.loader import normalize
from vp.models import VPItem, VPVariant

DATA = pathlib.Path(__file__).resolve().parents[2] / 'data' / 'vp'
DEMOS = {'9': 'vp-2tur-2026-demo-9.yaml', '10': 'vp-2tur-2026-demo-10.yaml',
         '11': 'vp-2tur-2026-demo-11.yaml'}


def demo(band='10'):
    return yaml.safe_load((DATA / DEMOS[band]).read_text(encoding='utf-8'))


def item_of(data, number):
    return next(i for i in data['items'] if i['n'] == number)


class DemoFilesTests(SimpleTestCase):
    def test_demos_parse_without_errors_or_warnings(self):
        for band, count, numbers in (('9', 17, 12), ('10', 18, 14), ('11', 18, 14)):
            with self.subTest(band=band):
                parsed = normalize(demo(band))
                self.assertEqual(parsed.errors, [])
                self.assertEqual(parsed.warnings, [])
                self.assertEqual(len(parsed.items), count)
                self.assertEqual(sum(i['points'] for i in parsed.items), Decimal('100'))
                self.assertEqual(sum(1 for i in parsed.items if i['kind'] == 'number'), numbers)

    def test_rows_and_group_are_read(self):
        parsed = normalize(demo('10'))
        by_number = {i['number']: i for i in parsed.items}
        self.assertEqual(len(by_number[4]['rows']), 4)
        self.assertEqual((by_number[17]['group'], by_number[18]['group']), (1, 1))
        self.assertIsNone(by_number[16]['group'])


class BrokenCopiesTests(SimpleTestCase):
    """Испорченная копия → ровно названная ошибка."""

    def errors(self, data):
        return ' | '.join(normalize(data).errors)

    def test_sum_99(self):
        data = demo('10')
        item_of(data, 1)['points'] = 5   # 6 → 5: сумма 99 и блок не по структуре
        errors = self.errors(data)
        self.assertIn('сумма `points` по всем заданиям 99.00, а должна быть 100', errors)
        self.assertIn('№1: в блоке «multi» задание стоит 6 баллов, а в файле 5.00', errors)

    def test_extra_number_item(self):
        data = demo('10')
        extra = copy.deepcopy(item_of(data, 16))
        extra['n'] = 19
        data['items'].append(extra)
        errors = self.errors(data)
        self.assertIn('блок «number»: заданий 15, а у 10 класса должно быть 14', errors)
        self.assertIn('номера заданий не образуют ровно 1..18', errors)

    def test_gap_mark_without_key(self):
        data = demo('10')
        item_of(data, 3)['statement'] += ' Лишний пропуск [[9]].'
        self.assertIn('№3: метки пропусков в тексте [1, 2, 3, 4, 5, 6, 7, 8, 9] не совпадают '
                      'с ключами `correct` [1, 2, 3, 4, 5, 6, 7, 8]; без ключа: [9]',
                      self.errors(data))

    def test_answer_with_dot(self):
        data = demo('10')
        item_of(data, 6)['answer'] = '37.5'
        self.assertIn('№6: эталон «37.5» не в формате ответа ВШЭ', self.errors(data))

    def test_group_of_one(self):
        data = demo('10')
        del item_of(data, 18)['group']
        self.assertIn('группа 1: в ней одно задание (17)', self.errors(data))

    def test_group_not_consecutive(self):
        data = demo('10')
        item_of(data, 15)['group'] = 1
        del item_of(data, 18)['group']
        self.assertIn('группа 1: задания [15, 17] идут не подряд', self.errors(data))

    def test_matching_rows_count(self):
        data = demo('10')
        item_of(data, 4)['rows'] = item_of(data, 4)['rows'][:3]
        self.assertIn('№4: строк `rows` 3, а ключей `correct` 4', self.errors(data))

    def test_matching_without_rows(self):
        data = demo('10')
        del item_of(data, 4)['rows']
        self.assertIn('№4: у соотнесения пусто `rows`', self.errors(data))

    def test_option_out_of_pool(self):
        data = demo('10')
        item_of(data, 3)['correct']['1'] = 99
        self.assertIn('№3: `correct` «1» ссылается на 99', self.errors(data))

    def test_band_from_other_tour(self):
        data = demo('10')
        data['grade_band'] = '9-10'
        self.assertIn('`grade_band` = «9-10», допустимо: 9, 10, 11', self.errors(data))

    def test_wrong_kind_for_block(self):
        data = demo('10')
        item_of(data, 6)['kind'] = 'short_text'
        self.assertIn('№6: у блока «number» вид ответа `number`, а в файле `short_text`',
                      self.errors(data))

    def test_unknown_tour(self):
        data = demo('10')
        data['tour'] = 3
        self.assertIn('`tour` = 3, допустимо: 1, 2', self.errors(data))

    def test_accepted_is_not_format_checked(self):
        data = demo('10')
        item_of(data, 6)['accepted'] = ['3,125', '37.5']
        self.assertEqual(normalize(data).errors, [])


class Tour2CommandTests(TestCase):
    """Через `import_vp`: испорченная копия во временной папке, затем настоящая запись."""

    def run_import(self, data, *args):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'v.yaml'
            path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                            encoding='utf-8')
            out, err = StringIO(), StringIO()
            call_command('import_vp', str(path), *args, stdout=out, stderr=err)
            return out.getvalue()

    def test_broken_copy_refused_and_nothing_written(self):
        data = demo('10')
        item_of(data, 6)['answer'] = '37.5'
        with self.assertRaises(CommandError):
            self.run_import(data)
        self.assertFalse(VPVariant.objects.exists())

    def test_import_and_repeat_is_noop(self):
        out = self.run_import(demo('11'), '--publish')
        self.assertIn('Заданий в файле: 18', out)
        variant = VPVariant.objects.get(slug='vp-2tur-2026-demo-11')
        self.assertEqual((variant.tour, variant.grade_band, variant.max_score,
                          variant.duration_seconds, variant.is_published),
                         (2, '11', Decimal('100.00'), 4200, True))
        self.assertEqual(variant.items.filter(kind=VPItem.Kind.NUMBER).count(), 14)
        self.assertIn('Изменений нет', self.run_import(demo('11')))
