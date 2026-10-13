"""Финграмотность и основы бизнеса (сессия 13.10.2026): реестр и оцифровка.

Реестр знает три олимпиады со своей папкой аудита и своим префиксом
`event_id` (`vp-fingram`, `vp-ob`, `mosh-fingram`), а старые записи (`vp`,
`mosh`) не изменились. Путь новой олимпиады (инвентарь → страницы → сборка
v1): `event_id` со своим префиксом, протоколы и списки не идут в модель,
комплект зеркала получает official=false; без --yes ни одного вызова,
--max-usd обрывает прогон. Данные выдуманные; база не нужна.
"""
import json
import os
import shutil
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from problems.olympiad_audit import digitize, registry, transcribe
from problems.tests.test_olympiad_digitize import PARA, StubProvider, page_reply
from problems.tests.test_olympiad_digitize_inventory import LONG, make_pdf


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


# ── Путь новой олимпиады: инвентарь → страницы → сборка v1 ───────────────

#: слаг → (комплект официальный, комплект-зеркало)
EVENTS = {
    'vp-fingram': ('vp-fingram-2019-final-9-10-v1', 'vp-fingram-2018-final-11-v1'),
    'vp-ob': ('vp-ob-2026-final-9-v1', 'vp-ob-2019-final-9-10-v1'),
    'mosh-fingram': ('mosh-fingram-2017-qualifying-5-7-tour2',
                     'mosh-fingram-2021-final-6-7-v1'),
}


class FinbizPipelineTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='finbiz_'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def make_audit(self, slug):
        audit = self.root / registry.get(slug).audit_dir
        pdf = audit / 'raw' / 'pdf'
        make_pdf(pdf / 'official__t.pdf', [LONG], pages=2)
        make_pdf(pdf / 'mirror__t.pdf', [LONG])
        # Протоколы и списки — по имени и по шапке первой страницы.
        make_pdf(pdf / 'protokol_rezultatov.pdf', ['Иванов Иван 10 баллов'])
        make_pdf(pdf / 'itogi_2019.pdf', ['Список победителей и призёров\n'
                                          'Петров Пётр Петрович — 95'])
        official, mirror = EVENTS[slug]
        events = [
            {'event_id': official, 'year': 2019, 'academic_year': '2018/2019',
             'stage': digitize.event_year_stage(official)[1], 'grade': '9-10',
             'variant': 'v1', 'official': True, 'source': 'official',
             'task_files': ['official__t.pdf']},
            # Протокол ошибочно приписан комплекту — в модель он всё равно не идёт.
            {'event_id': mirror, 'year': 2018, 'academic_year': '2017/2018', 'stage': 'final',
             'grade': '11', 'variant': 'v1', 'official': False,
             'source': 'mirror:solvehub.app', 'task_files': ['mirror__t.pdf'],
             'solution_files': ['protokol_rezultatov.pdf']},
        ]
        with open(audit / 'reference_events.jsonl', 'w', encoding='utf-8') as fh:
            for e in events:
                fh.write(json.dumps(e, ensure_ascii=False) + '\n')
        return audit

    def cmd(self, *args, **kw):
        out = StringIO()
        call_command('olympiad_digitize', *args, data_root=str(self.root), stdout=out, **kw)
        return out.getvalue()

    def test_5_event_ids_protocols_and_mirror_official_false(self):
        for slug, (official, mirror) in EVENTS.items():
            with self.subTest(slug=slug):
                audit = self.make_audit(slug)
                digitized = audit / 'digitized'
                self.cmd('inventory', olympiad=slug)
                rows = {r['file'].rsplit('/', 1)[-1]: r for r in digitize.read_jsonl(
                    digitized / 'inventory.jsonl')}
                for name in ('protokol_rezultatov.pdf', 'itogi_2019.pdf'):
                    self.assertFalse(rows[name]['digitize'], name)
                    self.assertEqual(rows[name]['exclude_reason'], digitize.REASON_PERSONAL)
                self.assertTrue(rows['official__t.pdf']['digitize'])
                self.assertEqual(rows['official__t.pdf']['event_ids'], [official])
                events = {e['event_id']: e for e in digitize.read_jsonl(
                    digitized / 'events_files.jsonl')}
                self.assertEqual(set(events), {official, mirror})
                self.assertEqual(events[mirror]['solution_files'], [])
                self.cmd('render', olympiad=slug)
                jobs = transcribe.build_jobs(digitize.read_jsonl(digitized / 'inventory.jsonl'),
                                             str(digitized), registry.get(slug).olympiad_name)
                self.assertEqual({j.file.rsplit('/', 1)[-1] for j in jobs},
                                 {'official__t.pdf', 'mirror__t.pdf'})
                self.assertEqual(len(jobs), 3)
                self.assertIn(registry.get(slug).olympiad_name, jobs[0].user_text())
                # Расшифровка — готовыми записями страниц, затем сборка v1.
                for job in jobs:
                    transcribe.Transcriber._write(job.out_path(str(digitized)), {
                        'status': 'ok', 'layer_ratio': 1.0, 'numbers_ok': True,
                        'blocks': ([{'type': 'task', 'number': '1', 'text': PARA[0]}]
                                   if job.page == 1 else [])})
                self.cmd('assemble', olympiad=slug, suffix='v1', no_crop=True)
                out = digitize.read_jsonl(digitized / 'reference_problems_v1.jsonl')
                by_event = {r['event_id']: r for r in out}
                self.assertEqual(set(by_event), {official, mirror})
                prefix = registry.get(slug).event_prefix
                self.assertTrue(all(r['event_id'].startswith(prefix) for r in out))
                self.assertTrue(by_event[official]['official'])
                self.assertEqual(by_event[official]['source'], 'official')
                self.assertFalse(by_event[mirror]['official'])
                self.assertEqual(by_event[mirror]['source'], 'mirror:solvehub.app')
                self.assertTrue((digitized / 'events_v1.jsonl').is_file())
                self.assertFalse((digitized / 'reference_problems_v2.jsonl').exists())

    def test_6_plan_without_yes_and_max_usd_cuts(self):
        slug = 'vp-ob'
        audit = self.make_audit(slug)
        self.cmd('inventory', olympiad=slug)
        self.cmd('render', olympiad=slug)
        provider = StubProvider([page_reply([{'type': 'task', 'number': '1',
                                              'text': '\n\n'.join(PARA)}])])
        with mock.patch.object(transcribe, 'make_provider', return_value=provider):
            out = self.cmd('transcribe', olympiad=slug, max_usd=10)
            self.assertIn('ПЛАН', out)
            self.assertEqual(provider.calls, 0)
            with self.assertRaises(CommandError):
                self.cmd('transcribe', olympiad=slug, yes=True)
            self.assertEqual(provider.calls, 0)
            # Смета страницы до замера — $0,005 × 1,3; потолок пропускает одну-две
            # страницы из трёх, затем прогон обрывается.
            out = self.cmd('transcribe', olympiad=slug, max_usd=0.008, workers=1, yes=True)
        self.assertIn('ОСТАНОВЛЕНО', out)
        self.assertGreaterEqual(provider.calls, 1)
        done = list((audit / 'digitized' / 'pages').rglob('p*.json'))
        self.assertLess(len(done), 3)
        self.assertTrue(os.path.isfile(audit / 'digitized' / 'transcribe_cost.jsonl'))
