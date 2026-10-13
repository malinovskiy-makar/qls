"""Финграмотность и основы бизнеса (сессия 13.10.2026): реестр и оцифровка.

Реестр знает три олимпиады со своей папкой аудита и своим префиксом
`event_id` (`vp-fingram`, `vp-ob`, `mosh-fingram`), а старые записи (`vp`,
`mosh`) не изменились. Данные выдуманные; база не нужна.
"""
from django.test import SimpleTestCase

from problems.olympiad_audit import digitize, registry


class RegistryTests(SimpleTestCase):
    def test_1_new_slugs_own_dirs_and_prefixes(self):
        expected = {
            'vp-fingram': ('audit_finbiz_20261013/vp_fingram', 'vp-fingram-',
                           'Олимпиада школьников «Высшая проба» по финансовой грамотности'),
            'vp-ob': ('audit_finbiz_20261013/vp_business', 'vp-ob-',
                      'Олимпиада школьников «Высшая проба» по основам бизнеса'),
            'mosh-fingram': ('audit_finbiz_20261013/mosh_fingram', 'mosh-fingram-',
                             'Московская олимпиада школьников по финансовой грамотности'),
        }
        for slug, (audit_dir, prefix, name) in expected.items():
            entry = registry.get(slug)
            self.assertEqual(entry.audit_dir, audit_dir, slug)
            self.assertEqual(entry.event_prefix, prefix, slug)
            self.assertEqual(entry.olympiad_name, name, slug)
        self.assertEqual(registry.get('vp-fingram').stages, ('final',))
        self.assertEqual(registry.get('vp-ob').stages, ('final',))
        self.assertEqual(registry.get('mosh-fingram').stages, ('qualifying', 'final'))
        # Свой официальный Source, не «по экономике».
        names = registry.official_source_names()
        self.assertEqual(len(names), len(set(names)))
        for slug in ('vp-fingram', 'vp-ob', 'mosh-fingram'):
            source = registry.get(slug).official_source_name
            self.assertNotIn('экономике', source)
            self.assertIn(source, names)
        self.assertIn('tasks-finance',
                      registry.get('vp-fingram').official_source_defaults['note'])
        self.assertIn('tasks-business', registry.get('vp-ob').official_source_defaults['note'])

    def test_2_old_entries_unchanged(self):
        vp, mosh = registry.get('vp'), registry.get('mosh')
        self.assertEqual((vp.audit_dir, vp.event_prefix, vp.official_source_name,
                          vp.session, vp.journal_dir, vp.compare, vp.family),
                         ('audit_vp_20261008', 'vp-', 'Высшая проба: официальный архив',
                          'vp3', 'session3', 'norm', ('vp', 'vp-fingram', 'vp-ob')))
        self.assertIn('tasks-eco', vp.official_source_defaults['note'])
        self.assertEqual((mosh.audit_dir, mosh.event_prefix, mosh.stages, mosh.session,
                          mosh.journal_dir, mosh.compare, mosh.family),
                         ('audit_mosh_20261009', 'mosh-', ('qualifying', 'final'), 'mosh2',
                          'session2', 'markup_free', ('mosh',)))
        self.assertEqual(mosh.olympiad_name, 'Московская олимпиада школьников по экономике')

    def test_3_event_year_stage_with_hyphenated_prefix(self):
        self.assertEqual(digitize.event_year_stage('vp-fingram-2019-final-9-10-v1'),
                         ('2019', 'final'))
        self.assertEqual(digitize.event_year_stage('mosh-fingram-2021-qualifying-5-7-v1'),
                         ('2021', 'qualifying'))
        self.assertEqual(digitize.event_year_stage('mosh-2014-final-11-v1'), ('2014', 'final'))

    def test_4_finance_file_not_other_olympiad_for_own_slug(self):
        rel = 'raw/pdf/olymp.hse.ru__mmo__s2_finance_11.pdf'
        self.assertEqual(digitize.other_olympiad_reason('vp', rel), digitize.REASON_OTHER_OLYMPIAD)
        self.assertEqual(digitize.other_olympiad_reason('vp-fingram', rel), '')
        self.assertEqual(digitize.other_olympiad_reason('vp-ob', 'raw/pdf/x__business_9.pdf'), '')
        fg = 'raw/pdf/mos.olimpiada.ru__2025-26__fg__tasks-fg-9-final-25-26.pdf'
        self.assertEqual(digitize.other_olympiad_reason('mosh', fg),
                         digitize.REASON_OTHER_OLYMPIAD_MOSH)
        self.assertEqual(digitize.other_olympiad_reason('mosh-fingram', fg), '')
