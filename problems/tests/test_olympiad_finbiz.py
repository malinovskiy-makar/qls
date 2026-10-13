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


# ── Пилот 13.10: таблица критериев одним блоком и усиленная инструкция ───

CRITERIA_PAGE = (
    '11 класс\n\n**КРИТЕРИИ ОЦЕНИВАНИЯ (всего 100 баллов)**\n\n'
    '**Е.Ясакова. 2022 – РБК: Рост за счет двух сделок**\n\n'
    '| № | Формулировка задания | Критерии оценки и примеры | Макс. сумма баллов '
    '| Баллы и примечания |\n'
    '| --- | --- | --- | --- | --- |\n'
    '| 1 | Поясните, что означает снижение мультипликаторов? | Примеры верных '
    'ответов:<br>1. Недооценка стоимости стартапа. | 25 | Макс. 15 баллов – пояснение |\n'
    '|  |  | 2. EV/EBITDA – отношение стоимости бизнеса к прибыли. |  |  |\n'
    '| 2 | Назовите два риска сделки. | Риск 1 и риск 2 | 20 | по 10 баллов |')


class CriteriaTableTests(SimpleTestCase):
    def test_7_criteria_table_rows_become_criteria_blocks(self):
        from problems.olympiad_audit import assemble
        block = {'type': 'task', 'number': '', 'text': CRITERIA_PAGE}
        parts = assemble.explode_table_rows(block, 'criteria')
        self.assertEqual([p['type'] for p in parts], ['task', 'criteria', 'criteria'])
        self.assertIn('Ясакова', parts[0]['text'])              # источник кейса цел
        self.assertEqual((parts[1]['number'], parts[1]['points']), ('1', 25))
        self.assertIn('**Критерии оценки и примеры:**', parts[1]['text'])
        self.assertIn('EV/EBITDA', parts[1]['text'])             # строка-продолжение
        self.assertIn('Макс. 15 баллов', parts[1]['text'])
        self.assertEqual((parts[2]['number'], parts[2]['points']), ('2', 20))
        # Продолжение таблицы на следующей странице без шапки — по шапке-подсказке.
        tail = {'type': 'task_continuation', 'number': '',
                'text': '| 3 | Оцените сделку. | Верная оценка | 15 | — |'}
        self.assertEqual(assemble.explode_table_rows(tail, 'criteria'), [tail])
        cont = assemble.explode_table_rows(tail, 'criteria', parts[-1]['_header'])
        self.assertEqual((cont[0]['type'], cont[0]['number'], cont[0]['points']),
                         ('criteria', '3', 15))
        # Таблица данных с целыми в первом столбце — не критерии.
        data = {'type': 'task_continuation', 'number': '',
                'text': '| Q | P |\n| --- | --- |\n| 1 | 100 |\n| 2 | 90 |'}
        self.assertEqual(assemble.explode_table_rows(data, 'solution'), [data])
        # Нумерованная таблица данных («№ | Q | P») — тоже не критерии.
        numbered = {'type': 'task_continuation', 'number': '',
                    'text': '| № | Q | P |\n| --- | --- | --- |\n| 1 | 10 | 100 |\n| 2 | 20 | 90 |'}
        self.assertEqual(assemble.explode_table_rows(numbered, 'solution'), [numbered])

    def test_8_criteria_table_attaches_to_task_in_assembly(self):
        from problems.olympiad_audit import assemble
        root = Path(tempfile.mkdtemp(prefix='finbiz_asm_'))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)

        def page(page_dir, blocks):
            transcribe.Transcriber._write(str(root / page_dir / 'p1.json'),
                                          {'status': 'ok', 'blocks': blocks})
        page('pages/t', [{'type': 'task', 'number': '1', 'points': 25,
                          'text': 'Поясните, что означает снижение мультипликаторов?'},
                         {'type': 'task', 'number': '2', 'text': 'Назовите два риска сделки.'}])
        page('pages/k', [{'type': 'task', 'number': '', 'text': CRITERIA_PAGE}])
        event = {'event_id': 'vp-ob-2023-final-11-v1', 'grade': '11',
                 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t', 'pages': 1}],
                 'criteria_files': [{'file': 'raw/pdf/k.pdf', 'page_dir': 'pages/k',
                                     'pages': 1}]}
        tasks, report, _missing = assemble.build_event(str(root), event, str(root / 'fig'),
                                                       crop=False)
        by = {t.number: t for t in tasks}
        self.assertEqual(set(by), {'1', '2'})
        self.assertIn('EV/EBITDA', '\n'.join(by['1'].criteria))
        self.assertEqual(by['2'].criteria_points, 20)
        self.assertEqual(report['таблица критериев → по строкам'], 1)

    def test_9_strict_prompt_only_with_flag(self):
        base = transcribe.Transcriber(root='.', provider=None, budget=None, cost_log=None)
        strict = transcribe.Transcriber(root='.', provider=None, budget=None, cost_log=None,
                                        strict=True)
        self.assertEqual(base.system_prompt, transcribe.SYSTEM_PROMPT)
        self.assertTrue(strict.system_prompt.endswith(transcribe.STRICT_SUFFIX))
        for rule in ('Вступление комплекта', 'Логотипы', '`criteria`'):
            self.assertIn(rule, transcribe.STRICT_SUFFIX)


class AssembleNumberTests(SimpleTestCase):
    def test_10_dates_are_not_task_numbers_and_header_variants(self):
        from problems.olympiad_audit import assemble
        self.assertFalse(assemble._real_number('06.11'))
        self.assertFalse(assemble._real_number('08.12'))
        self.assertTrue(assemble._real_number('1.1'))
        self.assertTrue(assemble._real_number('10'))
        block = {'type': 'criteria', 'number': '',
                 'text': '| № задания | Формулировка задания | Критерии оценки и примеры | '
                         'Максимальная сумма баллов |\n| --- | --- | --- | --- |\n'
                         '| 1 | Объясните термины. | За каждый — 3 балла | 15 |'}
        parts = assemble.explode_table_rows(block, 'criteria')
        self.assertEqual((parts[-1]['number'], parts[-1]['points']), ('1', 15))

    def test_11_list_item_number_beyond_tasks_continues_last(self):
        from problems.olympiad_audit import assemble
        root = Path(tempfile.mkdtemp(prefix='finbiz_asm2_'))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)

        def page(page_dir, blocks):
            transcribe.Transcriber._write(str(root / page_dir / 'p1.json'),
                                          {'status': 'ok', 'blocks': blocks})
        page('pages/t', [{'type': 'task', 'number': str(n), 'text': f'Условие {n}.'}
                         for n in (1, 2)])
        page('pages/s', [{'type': 'solution', 'number': '2', 'text': 'Решение 2.'},
                         {'type': 'solution', 'number': '5', 'text': 'Пункт 5 решения 2.'},
                         {'type': 'criteria', 'number': '1', 'text': 'Критерии 1.'}])
        event = {'event_id': 'vp-fingram-2022-final-9-10-v1', 'grade': '9-10',
                 'task_files': [{'file': 't.pdf', 'page_dir': 'pages/t', 'pages': 1}],
                 'solution_files': [{'file': 's.pdf', 'page_dir': 'pages/s', 'pages': 1}]}
        tasks, report, _ = assemble.build_event(str(root), event, str(root / 'f'), crop=False)
        by = {t.number: t for t in tasks}
        self.assertEqual(set(by), {'1', '2'})
        self.assertIn('Пункт 5 решения 2.', by['2'].solution)
        self.assertEqual(by['1'].criteria, ['Критерии 1.'])
        self.assertEqual(report['solution: не сопоставлено'], 0)

    def test_12_two_variants_in_one_file_by_header(self):
        """Файл «вариант 1» (1–9) + «вариант 2» (1–9) и ответы так же: задания
        не становятся «тест-N», ответы ложатся на свой вариант; файл с одним
        вариантом в шапке не меняется."""
        from problems.olympiad_audit import assemble
        root = Path(tempfile.mkdtemp(prefix='finbiz_var_'))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)

        def page(page_dir, n, blocks):
            transcribe.Transcriber._write(str(root / page_dir / f'p{n}.json'),
                                          {'status': 'ok', 'blocks': blocks})
        for v, n in (('1', 1), ('2', 2)):
            page('pages/t', n, [{'type': 'header', 'variant': f'Вариант {v}'}] + [
                {'type': 'task', 'number': str(k), 'text': f'Вопрос {k} варианта {v}'}
                for k in range(1, 10)])
            page('pages/a', n, [{'type': 'header', 'variant': v}] + [
                {'type': 'solution', 'number': str(k), 'text': f'Ответ {k}.{v}'}
                for k in range(1, 10)])
        event = {'event_id': 'mosh-fingram-2019-qualifying-8-9-v1', 'grade': '8-9',
                 'task_files': [{'file': 't.pdf', 'page_dir': 'pages/t', 'pages': 2}],
                 'solution_files': [{'file': 'a.pdf', 'page_dir': 'pages/a', 'pages': 2}]}
        tasks, report, _ = assemble.build_event(str(root), event, str(root / 'f'), crop=False)
        keys = {(t.number, t.task_variant): t for t in tasks}
        self.assertEqual(len(tasks), 18)
        self.assertFalse(any(t.number.startswith('тест-') for t in tasks))
        self.assertEqual(keys[('3', '2')].solution, ['Ответ 3.2'])
        self.assertEqual(keys[('3', '1')].solution, ['Ответ 3.1'])
        self.assertEqual(report['вариант из шапки файла'], 1)
        # Один вариант в шапках — ключи без варианта, как раньше.
        single = assemble._header_variants([
            ({'file': 'x'}, 1, {}, {'type': 'header', 'variant': '1'}),
            ({'file': 'x'}, 1, {}, {'type': 'task', 'number': '1'})])
        self.assertNotIn('task_variant', single[1][3])
        # «1 Вариант» в шапке один раз, затем нумерация снова с 1 — вариант 2.
        items = [({'file': 'a'}, 1, {}, {'type': 'header', 'variant': '1 Вариант'})] + [
            ({'file': 'a'}, 1, {}, {'type': 'solution', 'number': str(k % 9 + 1)})
            for k in range(18)]
        out = assemble._header_variants(items)
        self.assertEqual([b[3]['task_variant'] for b in out[1:]], ['1'] * 9 + ['2'] * 9)
        self.assertTrue(out[10][3]['_variant_switch'])
