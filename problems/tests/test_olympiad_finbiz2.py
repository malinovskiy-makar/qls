"""Финграмотность и основы бизнеса, сессия 2 (13.10.2026).

МОШ «по основам предпринимательства и финансовой грамотности» в реестре;
разбор `event_id` с дефисом в префиксе через реестр (`event_for`); разбор
очереди «на глаза» с заплатками `pages_v2` и сборкой v2 поверх v1; флаг
`auto_publish_ok`. Данные выдуманные; база не нужна.
"""
from django.test import SimpleTestCase

from problems.olympiad_audit import registry
from problems.olympiad_official import Reference


def _row(event_id, number=1):
    return {'event_id': event_id, 'number': number, 'norm_text': 'x'}


class RegistryEntrepreneurshipTests(SimpleTestCase):
    def test_1_new_slug_own_dir_prefix_and_predecessor_note(self):
        entry = registry.get('mosh-entrepreneurship')
        self.assertEqual(entry.audit_dir, 'audit_finbiz_20261013/mosh_entrepreneurship')
        self.assertEqual(entry.event_prefix, 'mosh-entrepreneurship-')
        self.assertEqual(entry.stages, ('qualifying', 'final'))
        self.assertEqual(entry.olympiad_name, 'Московская олимпиада школьников по основам '
                                              'предпринимательства и финансовой грамотности')
        self.assertEqual(entry.compare, 'markup_free')
        self.assertEqual(entry.family, ('mosh-entrepreneurship',))
        note = entry.official_source_defaults['note']
        self.assertIn('mos.olimpiada.ru/tasks/entr', note)
        self.assertIn('предшественник', note)
        names = registry.official_source_names()
        self.assertIn(entry.official_source_name, names)
        self.assertEqual(len(names), len(set(names)))
        # Старые записи не тронуты.
        self.assertEqual(registry.get('mosh-fingram').event_prefix, 'mosh-fingram-')
        self.assertEqual(registry.get('mosh').audit_dir, 'audit_mosh_20261009')


class ParseEventIdTests(SimpleTestCase):
    def test_2_hyphenated_prefixes_by_registry(self):
        cases = {
            'vp-fingram-2019-final-9-10-v1': ('vp-fingram', '2019', 'final', '9-10', 'v1'),
            'vp-ob-2024-final-11-v1': ('vp-ob', '2024', 'final', '11', 'v1'),
            'mosh-fingram-2017-qualifying-5-11-tour2':
                ('mosh-fingram', '2017', 'qualifying', '5-11', 'tour2'),
            'mosh-entrepreneurship-2012-final-8-11-v1':
                ('mosh-entrepreneurship', '2012', 'final', '8-11', 'v1'),
        }
        for event_id, expected in cases.items():
            self.assertEqual(registry.parse_event_id(event_id), expected, event_id)

    def test_3_old_event_ids_as_before(self):
        self.assertEqual(registry.parse_event_id('vp-2020-final-10-v1'),
                         ('vp', '2020', 'final', '10', 'v1'))
        self.assertEqual(registry.parse_event_id('vp-2021-final-10-reserve'),
                         ('vp', '2021', 'final', '10', 'reserve'))
        self.assertEqual(registry.parse_event_id('mosh-2015-final-8-9-day2'),
                         ('mosh', '2015', 'final', '8-9', 'day2'))
        self.assertIsNone(registry.parse_event_id('нечто'))

    def test_4_event_for_hyphenated_and_old(self):
        ref = Reference([_row('vp-fingram-2019-final-9-10-v1'),
                         _row('vp-fingram-2019-final-11-v1'),
                         _row('mosh-fingram-2018-final-10-11-v1'),
                         _row('mosh-fingram-2018-final-10-11-v2')])
        self.assertEqual(ref.event_for(2019, '9-10'), 'vp-fingram-2019-final-9-10-v1')
        self.assertEqual(ref.event_for(2019, 11), 'vp-fingram-2019-final-11-v1')
        self.assertEqual(ref.event_for(2018, '10-11'), 'mosh-fingram-2018-final-10-11-v1')
        self.assertIsNone(ref.event_for(2020, 11))
        old = Reference([_row('vp-2021-final-10-reserve'), _row('vp-2021-final-10-v1'),
                         _row('mosh-2015-final-8-9-day2')])
        self.assertEqual(old.event_for(2021, 10), 'vp-2021-final-10-v1')
        self.assertEqual(old.event_for(2015, '8-9'), 'mosh-2015-final-8-9-day2')
