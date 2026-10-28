"""ВсОШ по экономике (ночь P3): разбор списков источников, метаданные,
дедупликация, пары «задания ↔ решения», сборка эталона v1.

Без сети и без базы: входы — маленькие выдуманные куски того же вида, что
ответ API ЦПМ, страницы ILE и манифест olimpiada.ru.
"""
import json
import os
import tempfile
import zipfile

from django.test import SimpleTestCase

from problems.olympiad_audit import vsosh_digitize, vsosh_manifest, vsosh_prepare
from problems.olympiad_audit import vsosh_sources as S

CPM_API = {'data': [{
    'id': '27', 'sid': '4', 'yname': '2024/2025',
    'tasks': ('<div class="tasks-solutions">\n'
              '<div><span class="name">Задания</span> '
              '<a href="/upload/files/Arhive_tasks/2024-25/reg/econ/tasks-econ-9-reg-24-25.pdf">'
              ' <span class="class">9 класс</span> </a> '
              '<a href="/upload/files/Arhive_tasks/2024-25/reg/econ/tasks-econ-10-11-reg-24-25.pdf">'
              ' <span class="class">10-11 классы</span> <span class="format">2 тур</span></a></div>\n'
              '<div><span class="name">Решения</span> '
              '<a href="/upload/files/Arhive_tasks/2024-25/reg/econ/ans-econ-9-reg-24-25.pdf">'
              ' <span class="class">9 класс</span> </a></div>\n</div>'),
}, {
    'id': '28', 'sid': '2', 'yname': '2025/2026',
    'tasks': ('<div><span class="name">Задания</span> '
              '<a href="/upload/files/Arhive_tasks/2025-26/school/econ/t-7-8.pdf">'
              '<span class="class">7-8 классы</span></a></div>'),
}]}

ILE_PAGES = [{
    'sec': 'region', 'y': '2009', 'title': 'Региональный этап ВОШ — 2009', 'files': [
        {'href': '/sites/default/files/olimp/region/2009/r2009_zad_11.pdf',
         'type': 'application/pdf', 'len': 1000, 'text': 'Задачи (11 класс)'},
        {'href': 'https://iloveeconomics.ru/sites/default/files/olimp/region/2009/r2009_test_otv.doc',
         'type': 'application/msword', 'len': 1000, 'text': 'Тест с ответами (10-11 класс)'},
        {'href': '/print-all-tasks/3621', 'type': '', 'len': None, 'text': 'Напечатать все задачи'},
        {'href': '/z/1930', 'type': '', 'len': None, 'text': 'Монополия'},
        {'href': '/sites/default/files/olymp_files/region-2009.zip', 'type': '', 'len': None,
         'text': 'Скачать все файлы в одном архиве'},
    ]}, {
    'sec': 'okrug', 'y': '2010-0', 'title': 'Муниципальный этап ВОШ (Москва) — 2010', 'files': [
        {'href': '/sites/default/files/olimp/okrug/2010/okrug_2010_9_zadachi.doc',
         'type': 'application/msword', 'len': 10, 'text': 'Задания 9 класс'}]}, {
    'sec': 'okrug', 'y': '2005', 'title': '…', 'files': [
        {'href': '/sites/default/files/olimp/okrug/2005/okrug_2005_oblast_9.doc',
         'type': 'application/msword', 'len': 10, 'text': 'Область 9 класс'}]},
]

OLIMPIADA_CSV = [
    {'season_start': '2018', 'stage': 'municipal', 'region_id': '2',
     'region': 'Республика Башкортостан', 'label': 'Задания', 'class_pages': '8/9',
     'url': 'https://tasks.olimpiada.ru/upload/files/tasks/86/2018/tasks-econ-8-9-mun-bash-18-9.PDF',
     'http_status': '200', 'bytes': '401654'},
    {'season_start': '2009', 'stage': 'final', 'region_id': '0', 'region': '',
     'label': 'Эссе', 'class_pages': '9/10/11',
     'url': 'https://vos.olimpiada.ru/upload/files/a&amp;b.pdf', 'http_status': '200', 'bytes': ''},
    {'season_start': '2018', 'stage': 'video', 'region_id': '2', 'region': '', 'label': 'x',
     'class_pages': '', 'url': 'https://x', 'http_status': '200', 'bytes': ''},
]


class ParseSourcesTests(SimpleTestCase):
    def test_cpm_rows_stage_season_grades_tour_from_api_fields(self):
        rows = S.cpm_rows(CPM_API)
        self.assertEqual(len(rows), 4)
        first = rows[0]
        self.assertEqual((first['stage'], first['season'], first['region_code']),
                         ('regional', '2024/25', 'ru'))
        self.assertEqual(first['url'], 'https://vos.olimpiada.ru/upload/files/Arhive_tasks/'
                                       '2024-25/reg/econ/tasks-econ-9-reg-24-25.pdf')
        self.assertEqual((first['kind'], first['grades']), ('tasks', '9'))
        self.assertEqual((rows[1]['grades'], rows[1]['tour']), ('10-11', '2'))
        self.assertEqual(rows[2]['kind'], 'solutions')
        school = rows[3]
        self.assertEqual((school['stage'], school['region_code'], school['region_name']),
                         ('school', '77', 'Москва'))

    def test_ile_rows_split_files_and_extras_with_section_metadata(self):
        files, extras = S.ile_rows(ILE_PAGES)
        self.assertEqual(len(files), 4)
        self.assertEqual({e['kind'] for e in extras},
                         {'ile_print', 'ile_task_page', 'archive_year'})
        z = files[0]
        self.assertEqual((z['stage'], z['season'], z['grades'], z['kind']),
                         ('regional', '2008/09', '11', 'tasks'))
        self.assertTrue(z['url'].startswith('https://iloveeconomics.ru/sites/'))
        test = files[1]
        self.assertEqual((test['kind'], test['tour'], test['grades'], test['with_solutions']),
                         ('test', 'test', '10-11', True))
        msk = files[2]
        self.assertEqual((msk['stage'], msk['season'], msk['region_code']),
                         ('municipal', '2009/10', '77'))
        # «окружной этап до 2009 года — окружной тур МГО»; 2010 — уже МЭ ВсОШ.
        self.assertNotIn('окружной_тур_МГО', msk['notes'])
        oblast = files[3]
        self.assertEqual(oblast['region_code'], '50')

    def test_olimpiada_rows_use_page_attributes_and_keep_case(self):
        rows = S.olimpiada_rows(OLIMPIADA_CSV)
        self.assertEqual(len(rows), 2)
        mun, final = rows
        self.assertEqual((mun['stage'], mun['season'], mun['region_code'], mun['grades']),
                         ('municipal', '2018/19', '2', '8-9'))
        self.assertTrue(mun['url'].endswith('.PDF'))
        self.assertEqual((final['region_code'], final['grades'], final['kind']),
                         ('ru', '9-11', 'essay'))
        self.assertEqual(final['url'], 'https://vos.olimpiada.ru/upload/files/a&b.pdf')

    def test_olimpiada_school_without_region_is_moscow(self):
        row = {'season_start': '2023', 'stage': 'school', 'region_id': '', 'region': '',
               'label': 'Задания', 'class_pages': '7', 'url': 'https://x/s.pdf',
               'http_status': '200', 'bytes': ''}
        school = S.olimpiada_rows([row])[0]
        self.assertEqual((school['region_code'], school['region_name']), ('77', 'Москва'))


class MetadataTests(SimpleTestCase):
    def test_parse_grades(self):
        cases = {'9-10 классы': '9-10', '11 класс': '11', 'Задания 11-го класса': '11',
                 'Тест 10-11 класс (с ответами)': '10-11', 'Задачи': '', '7–8 кл.': '7-8',
                 '2024 класс': ''}
        for text, want in cases.items():
            self.assertEqual(S.parse_grades(text), want, text)

    def test_classify_label(self):
        cases = {
            'Задачи с решениями': ('tasks+solutions', 'problems', True),
            'Задачи без решений': ('tasks', 'problems', False),
            'Решения': ('solutions', '', False),
            'Тест': ('test', 'test', False),
            'Эссе по макроэкономике с ответами': ('essay', 'essay', True),
            'Критерии': ('criteria', '', False),
            'Ответы': ('answers', '', False),
            'Задания второго тура': ('tasks', '2', False),
            'Методические рекомендации по проведению': ('methodical', '', False),
        }
        for text, want in cases.items():
            self.assertEqual(S.classify_label(text), want, text)

    def test_seasons(self):
        self.assertEqual(S.season_from_end('2010'), '2009/10')
        self.assertEqual(S.season_from_start(1999), '1999/00')
        self.assertEqual(S.season_from_cpm('2024/2025'), '2024/25')
        self.assertEqual(S.grades_from_pages('9/10/11'), '9-11')

    def test_names_inside_archives(self):
        self.assertEqual(vsosh_manifest.kind_from_name(
            'Экономика РЭ/критерии РЭ ВсОШ 2023-24 экономика/Решения 9 класс.pdf'), 'solutions')
        self.assertEqual(vsosh_manifest.kind_from_name('x/задания ЗЭ/10 класс 2 тур.pdf'), 'tasks')
        self.assertEqual(vsosh_manifest.kind_from_name('Решения и критерии 9 класс.pdf'),
                         'solutions')
        self.assertEqual(vsosh_manifest.tour_from_name('zadaniya_10_klass_2_tur.pdf'), '2')
        self.assertEqual(vsosh_manifest.tour_from_name('resheniya_11_klass_1_i_2_tur.pdf'), '')
        self.assertEqual(vsosh_manifest.grades_from_name('Задания 10 класс.pdf'), '10')

    def test_not_a_file_links(self):
        self.assertTrue(vsosh_manifest.not_a_file_reason({'url': 'https://youtu.be/x', 'source': 'cpm'}))
        self.assertTrue(vsosh_manifest.not_a_file_reason(
            {'url': 'https://vserosolimp.edsoo.ru/economy#!/tab/1', 'source': 'cpm'}))
        self.assertFalse(vsosh_manifest.not_a_file_reason(
            {'url': 'https://vos.olimpiada.ru/upload/files/a.pdf', 'source': 'cpm'}))


class ArchiveAndFormatTests(SimpleTestCase):
    def test_zip_cp866_names_and_macos_junk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'a.zip')
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('AAAAAAA 9.pdf', b'%PDF-1.4 test')   # имя без флага UTF-8
                z.writestr('__MACOSX/._junk', b'x')
            with open(path, 'rb') as fh:     # как пишет русский Windows: байты cp866
                raw = fh.read().replace(b'AAAAAAA', 'Задания'.encode('cp866'))
            with open(path, 'wb') as fh:
                fh.write(raw)
            out = vsosh_manifest.extract_archive(path, os.path.join(tmp, 'u'))
            self.assertEqual([rel for rel, _ in out], ['Задания 9.pdf'])
            self.assertEqual(vsosh_manifest.detect_format(out[0][1]), 'pdf')

    def test_detect_format_by_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = os.path.join(tmp, 'download')
            with open(doc, 'wb') as fh:
                fh.write(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'0' * 50)
            self.assertEqual(vsosh_manifest.detect_format(doc), 'doc')
            html_ = os.path.join(tmp, 'h')
            with open(html_, 'wb') as fh:
                fh.write(b'<!DOCTYPE html><html>')
            self.assertEqual(vsosh_manifest.detect_format(html_), 'html')
            stub = os.path.join(tmp, 'yd')
            with open(stub, 'wb') as fh:
                fh.write(b'{"href": "https://downloader.disk.yandex.ru/x", "method": "GET"}')
            self.assertEqual(vsosh_manifest.detect_format(stub), 'json')

    def test_api_stub_counts_as_not_downloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = os.path.join(tmp, 'work')
            os.makedirs(os.path.join(tmp, 'raw'))
            os.makedirs(work)
            with open(os.path.join(tmp, 'raw', 'a.pdf'), 'wb') as fh:
                fh.write(b'{"href": "x"}')
            job = {'url': 'https://cloud-api.yandex.net/x', 'dest': 'raw/a.pdf', 'source': 'region:x',
                   'stage': 'school', 'kind': 'tasks'}
            with open(os.path.join(work, 'jobs_t.jsonl'), 'w', encoding='utf-8') as fh:
                fh.write(json.dumps(job) + chr(10))
            with open(os.path.join(work, 'results_t.jsonl'), 'w', encoding='utf-8') as fh:
                fh.write(json.dumps(dict(job, status='ok', sha256='s', size=13)) + chr(10))
            rows = vsosh_manifest.build(tmp, work, ['t'], unpack=False)
            self.assertEqual(rows[0]['status'], 'not_downloaded')
            self.assertTrue(vsosh_manifest.invariants(rows)['balanced'])


class DedupTests(SimpleTestCase):
    def test_duplicates_by_sha_keep_highest_source_and_loose_file(self):
        rows = [
            {'url': 'ile1', 'source': 'ile', 'status': 'ok', 'sha256': 'A'},
            {'url': 'cpm1', 'source': 'cpm', 'status': 'ok', 'sha256': 'A'},
            {'url': 'arch#x', 'source': 'cpm', 'status': 'ok', 'sha256': 'A', 'from_archive': 'arch'},
            {'url': 'reg1', 'source': 'region:zsfond.ru', 'status': 'ok', 'sha256': 'B'},
            {'url': 'olim1', 'source': 'olimpiada', 'status': 'ok', 'sha256': 'B'},
            {'url': 'bad', 'source': 'cpm', 'status': 'not_downloaded'},
        ]
        vsosh_manifest.mark_duplicates(rows)
        self.assertEqual(rows[1]['dup_of'], '')
        self.assertEqual(rows[0]['dup_of'], 'cpm1')
        self.assertEqual(rows[2]['dup_of'], 'cpm1')
        self.assertEqual(rows[4]['dup_of'], '')
        self.assertEqual(rows[3]['dup_of'], 'olim1')
        self.assertNotIn('dup_of', rows[5])

    def test_loose_file_beats_archive_member_of_same_source(self):
        rows = [{'url': 'arch#x', 'source': 'cpm', 'status': 'ok', 'sha256': 'A',
                 'from_archive': 'arch'},
                {'url': 'cpm1', 'source': 'cpm', 'status': 'ok', 'sha256': 'A'}]
        vsosh_manifest.mark_duplicates(rows)
        self.assertEqual((rows[1]['dup_of'], rows[0]['dup_of']), ('', 'cpm1'))

    def test_invariant_links_balance(self):
        rows = [{'url': 'a', 'status': 'ok', 'sha256': 'A'},
                {'url': 'b', 'status': 'not_downloaded'},
                {'url': 'c', 'status': 'archive', 'sha256': 'C'},
                {'url': 'c#1', 'status': 'ok', 'sha256': 'D', 'from_archive': 'c'},
                {'url': 'v', 'status': 'not_a_file'}]
        inv = vsosh_manifest.invariants(rows)
        self.assertEqual((inv['links'], inv['downloaded'], inv['not_downloaded']), (4, 2, 2))
        self.assertTrue(inv['balanced'])
        self.assertEqual(inv['unique_sha256_files'], 2)


def _t(sha, kind, grades='', tour='', stage='regional', season='2024/25', reg='ru'):
    return {'sha256': sha, 'kind': kind, 'grades': grades, 'tour': tour, 'stage': stage,
            'season': season, 'region_code': reg, 'region_name': '', 'url': 'u' + sha,
            'path': sha, 'subject': 'econ', 'source': 'cpm'}


class PairsTests(SimpleTestCase):
    def test_exact_grade_and_range_and_tour(self):
        targets = [_t('t9', 'tasks', '9'), _t('t10', 'tasks', '10'), _t('t11', 'tasks', '11'),
                   _t('s9', 'solutions', '9'), _t('s911', 'criteria', '9-11'),
                   _t('f1', 'tasks', '9', '1', 'final'), _t('f2', 'tasks', '9', '2', 'final'),
                   _t('fs', 'solutions', '9', '', 'final'),
                   _t('x', 'solutions', '9', '', 'municipal', '2024/25', '50')]
        events, orphans = vsosh_prepare.build_events(targets)
        e9 = events['vseros-regional-2024-25-ru-9-all']
        self.assertEqual([f['sha256'] for f in e9['solution_files']], ['s9'])
        self.assertEqual([f['sha256'] for f in e9['criteria_files']], ['s911'])
        e10 = events['vseros-regional-2024-25-ru-10-all']
        self.assertEqual(e10['solution_files'], [])
        self.assertEqual([f['sha256'] for f in e10['criteria_files']], ['s911'])
        for tour in ('1', '2'):
            ev = events[f'vseros-final-2024-25-ru-9-{tour}']
            self.assertEqual([f['sha256'] for f in ev['solution_files']], ['fs'])
            self.assertIn('solutions_shared_across_tours', ev['flags'])
        self.assertEqual([o['sha256'] for o in orphans], ['x'])

    def test_exact_grade_range_wins_over_single_grades_inside(self):
        events, _ = vsosh_prepare.build_events(
            [_t('a', 'tasks', '9-11'), _t('b', 'tasks', '9'), _t('s', 'solutions', '9-11')])
        self.assertEqual([f['sha256'] for f in events['vseros-regional-2024-25-ru-9-11-all']
                          ['solution_files']], ['s'])
        self.assertEqual(events['vseros-regional-2024-25-ru-9-all']['solution_files'], [])

    def test_solution_of_one_tour_goes_to_that_tour_only(self):
        events, _ = vsosh_prepare.build_events(
            [_t('t1', 'tasks', '9', '1', 'final'), _t('t2', 'tasks', '9', '2', 'final'),
             _t('s2', 'solutions', '9', '2', 'final')])
        self.assertEqual([f['sha256'] for f in events['vseros-final-2024-25-ru-9-2']
                          ['solution_files']], ['s2'])
        self.assertEqual(events['vseros-final-2024-25-ru-9-1']['solution_files'], [])

    def test_unknown_grade_solution_pairs_only_single_group(self):
        events, orphans = vsosh_prepare.build_events(
            [_t('a', 'tasks', '9'), _t('b', 'tasks', '10'), _t('s', 'solutions', '')])
        self.assertEqual([o['sha256'] for o in orphans], ['s'])
        events, orphans = vsosh_prepare.build_events(
            [_t('a', 'tasks', '9-11'), _t('s', 'solutions', '')])
        self.assertEqual(orphans, [])

    def test_group_of(self):
        self.assertEqual(vsosh_prepare.group_of({'stage': 'final'}), 1)
        self.assertEqual(vsosh_prepare.group_of({'stage': 'municipal', 'region_code': '77'}), 3)
        self.assertEqual(vsosh_prepare.group_of({'stage': 'municipal', 'region_code': '66'}), 4)
        self.assertEqual(vsosh_prepare.group_of({'stage': 'school', 'region_code': '66'}), 5)
        self.assertEqual(vsosh_prepare.group_of({'stage': 'final',
                                                 'subject': 'entrepreneurship'}), 6)

    def test_targets_skip_duplicates_methodical_and_unknown_stage(self):
        man = [dict(_t('a', 'tasks'), status='ok', format='pdf'),
               dict(_t('b', 'methodical'), status='ok', format='pdf'),
               dict(_t('c', 'tasks'), status='ok', format='pdf', dup_of='u1'),
               dict(_t('d', 'tasks', stage='school+municipal'), status='ok', format='pdf'),
               dict(_t('e', 'tasks'), status='ok', format='zip')]
        targets, excluded = vsosh_prepare.digitize_targets(man)
        self.assertEqual([t['sha256'] for t in targets], ['a'])
        self.assertEqual(len(excluded), 3)


class AssembleWrapperTests(SimpleTestCase):
    def test_official_title(self):
        for service in ('Задача 3', 'Задание № 2.', 'СПРАВКА', 'Тест (10 вопросов)', '', 'Вопрос 12'):
            self.assertEqual(vsosh_digitize.official_title(service), '', service)
        self.assertEqual(vsosh_digitize.official_title('Монополия на острове'),
                         'Монополия на острове')

    def test_reference_events_shape(self):
        meta = {'e': {'event_id': 'e', 'year': 2025, 'academic_year': '2024/25',
                      'stage': 'regional', 'grade': '9', 'tour': '', 'source_urls': ['u']}}
        ev = vsosh_digitize.reference_events(meta)[0]
        self.assertEqual((ev['olympiad_slug'], ev['variant'], ev['official']),
                         ('vseros', 'all', True))

    def test_event_id_format(self):
        self.assertEqual(vsosh_prepare.event_id_for('municipal', '2023/24', '66', '7-8', ''),
                         'vseros-municipal-2023-24-66-7-8-all')

    def test_claude_overlay_replaces_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'abc'))
            with open(os.path.join(tmp, 'abc', 'p2.json'), 'w', encoding='utf-8') as fh:
                json.dump({'status': 'ok', 'blocks': [{'type': 'task', 'text': 'C'}],
                           'model': 'claude-sonnet-5-5'}, fh)
            ov = vsosh_digitize.ClaudeOverlay(tmp)
            rec = ov.apply('pages/abc', 2, {'blocks': [{'type': 'task', 'text': 'F'}],
                                            'needs_eyes': True})
            self.assertEqual(rec['blocks'][0]['text'], 'C')
            self.assertFalse(rec['needs_eyes'])
            same = ov.apply('pages/abc', 3, {'blocks': [1]})
            self.assertEqual(same['blocks'], [1])

    def test_batch_cost(self):
        usage = {'input_tokens': 1000, 'output_tokens': 1000, 'cache_read_input_tokens': 2000}
        # (1000 + 0,1·2000)·2 + 1000·10 = 12 400 → ×0,5 / 1e6
        self.assertAlmostEqual(vsosh_digitize.batch_cost(usage, 'claude-sonnet-5-5'), 0.0062)

    def test_page_usd_from_ledger_after_50_pages(self):
        few = [{'kind': 'result', 'model': 'claude-sonnet-5-5', 'cost_usd': 1.0, 'ok': 10}]
        self.assertEqual(vsosh_digitize.page_usd(few)['claude-sonnet-5-5'],
                         vsosh_digitize.CLAUDE_PAGE_USD['claude-sonnet-5-5'])
        many = [{'kind': 'result', 'model': 'claude-sonnet-5-5', 'cost_usd': 0.5, 'ok': 98,
                 'failed': 2}, {'kind': 'submitted', 'model': 'claude-sonnet-5-5', 'cost_usd': 9}]
        self.assertAlmostEqual(vsosh_digitize.page_usd(many)['claude-sonnet-5-5'], 0.0055)

    def test_late_haiku_does_not_overwrite_sonnet(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'p1.json')
            haiku = {'status': 'ok', 'model': 'claude-haiku-5-5', 'blocks': [1]}
            sonnet = {'status': 'ok', 'model': 'claude-sonnet-5-5', 'blocks': [1]}
            self.assertFalse(vsosh_digitize.keeps_existing(path, haiku))
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(sonnet, fh)
            self.assertTrue(vsosh_digitize.keeps_existing(path, haiku))
            self.assertFalse(vsosh_digitize.keeps_existing(path, dict(sonnet)))
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(dict(sonnet, status='error'), fh)
            self.assertFalse(vsosh_digitize.keeps_existing(path, haiku))

    def test_pending_usd_skips_collected_batches(self):
        ledger = [{'kind': 'submitted', 'batch_id': 'a', 'estimate_usd': 2.5},
                  {'kind': 'result', 'batch_id': 'a', 'cost_usd': 2.8},
                  {'kind': 'collected', 'batch_id': 'a'},
                  {'kind': 'submitted', 'batch_id': 'b', 'estimate_usd': 3.0}]
        self.assertEqual(vsosh_digitize.pending_usd(ledger), 3.0)

    def test_batch_request_downscales_and_turns_thinking_off(self):
        import base64
        import io

        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            png = os.path.join(tmp, 'p1.png')
            Image.new('L', (1654, 2339), 255).save(png)
            job = type('J', (), {'png': png, 'layer': '', 'footers': (), 'key': 'pages/abc/p1',
                                 'user_text': lambda self: 'стр'})()
            model = 'claude-sonnet-5-5'
            req = vsosh_digitize.batch_request(
                job, model, thinking=vsosh_digitize.THINKING_OFF[model])
            data = req['params']['messages'][0]['content'][0]['source']['data']
            # Маленький PNG уходит как есть (API ужмёт сам).
            self.assertEqual(Image.open(io.BytesIO(base64.b64decode(data))).size, (1654, 2339))
            noisy = os.path.join(tmp, 'p2.png')
            Image.effect_noise((1654, 2339), 64).save(noisy)
            media, big = vsosh_digitize.page_image_b64(noisy)
            self.assertEqual(media, 'image/jpeg')
            self.assertEqual(max(Image.open(io.BytesIO(base64.b64decode(big))).size),
                             vsosh_digitize.CLAUDE_MAX_SIDE)
            self.assertEqual(req['params']['thinking'], {'type': 'between_tools'})
            self.assertEqual(req['custom_id'], 'pages__abc__p1')
            self.assertNotIn('thinking', vsosh_digitize.batch_request(job, model)['params'])


class CurrencyDollarTests(SimpleTestCase):
    BS = chr(92)

    def test_money_escaped_math_kept(self):
        text = ('если билет стоит не более $700, а туристы – если не более $300. '
                'При $P = 10$ спрос $Q = 400$, цена $100$ и $$W = 2q$$.')
        fixed, n = vsosh_digitize.fix_currency_dollars(text)
        self.assertEqual(n, 2)
        self.assertIn('не более ' + self.BS + '$700, а туристы', fixed)
        self.assertIn('не более ' + self.BS + '$300. При $P = 10$', fixed)
        self.assertIn('$100$', fixed)
        self.assertIn('$$W = 2q$$', fixed)

    def test_text_command_inside_math_is_not_money(self):
        text = '$5' + self.BS + 'text{ рублей}$ и всё'
        self.assertEqual(vsosh_digitize.fix_currency_dollars(text), (text, 0))

    def test_idempotent(self):
        once, _ = vsosh_digitize.fix_currency_dollars('стоит $700, а потом $300.')
        twice, n = vsosh_digitize.fix_currency_dollars(once)
        self.assertEqual((twice, n), (once, 0))


ILE_PRINT = ('<html><body><h2>10 класс</h2>'
             '<div class="task"><h3>1. Товар Х</h3><div class="condition"><div class="tex2jax">'
             'Спрос на товар Х задан уравнением $Q=400-4P$, предложение $Q=4P-80$. Найдите цену.'
             '</div></div><div class="solution_and_answer">Решение: 60</div></div>'
             '<h2>11 класс</h2><div class="task"><h3>2. Безработица</h3><div class="condition">'
             'Уровень безработицы составил 8 %.</div></div></body></html>')


class IlePrintTests(SimpleTestCase):
    def test_parse_print_page(self):
        from problems.olympiad_audit import vsosh_ile
        tasks = vsosh_ile.parse_print_page(ILE_PRINT)
        self.assertEqual([(t['grades'], t['number'], t['title']) for t in tasks],
                         [('10', '1', 'Товар Х'), ('11', '2', 'Безработица')])
        self.assertIn('$Q=400-4P$', tasks[0]['text'])
        self.assertNotIn('Решение', tasks[0]['text'])

    def test_compare_sets_title_and_flags(self):
        from problems.olympiad_audit import vsosh_ile
        ile = [dict(t, stage='regional', season='2013/14', url='u')
               for t in vsosh_ile.parse_print_page(ILE_PRINT)]
        rows = [{'event_id': 'e', 'number': '1', 'stage': 'regional', 'academic_year': '2013/14',
                 'statement_md': 'Спрос на товар Х задан уравнением $Q=400-4P$, предложение '
                                 '$Q=4P-80$. Найдите цену.'},
                {'event_id': 'e', 'number': '9', 'stage': 'regional', 'academic_year': '2013/14',
                 'statement_md': 'Совсем другая задача про монополию и ценовую дискриминацию '
                                 'третьей степени на двух рынках.'}]
        report = vsosh_ile.compare(rows, ile)
        self.assertEqual(rows[0].get('ile_title'), 'Товар Х')
        self.assertEqual(report[0]['verdict'], 'совпало')
        self.assertNotEqual(report[1]['verdict'], 'совпало')

    def test_compare_only_same_region(self):
        from problems.olympiad_audit import vsosh_ile
        ile = [dict(t, stage='municipal', season='2013/14', url='u', region_code='77')
               for t in vsosh_ile.parse_print_page(ILE_PRINT)]
        text = 'Спрос на товар Х задан уравнением $Q=400-4P$, предложение $Q=4P-80$. Найдите цену.'
        rows = [{'event_id': 'm66', 'number': '1', 'stage': 'municipal', 'academic_year': '2013/14',
                 'region_code': '66', 'statement_md': text},
                {'event_id': 'm77', 'number': '1', 'stage': 'municipal', 'academic_year': '2013/14',
                 'region_code': '77', 'statement_md': text}]
        report = vsosh_ile.compare(rows, ile)
        self.assertEqual([x['event_id'] for x in report], ['m77'])


class CheckRulesTests(SimpleTestCase):
    def test_repeated_paragraphs_dropped_once(self):
        text = 'Тест №2. Выберите ответ\n\nТест №2. Выберите ответ\n\nВопрос?\n\n- да\n- нет'
        out, n = vsosh_digitize.drop_repeated_paragraphs(text)
        self.assertEqual((out, n), ('Тест №2. Выберите ответ\n\nВопрос?\n\n- да\n- нет', 1))
        self.assertEqual(vsosh_digitize.drop_repeated_paragraphs('А\n\nБ'), ('А\n\nБ', 0))

    def test_page_models_from_claude_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'pages_claude', 'abc'))
            with open(os.path.join(tmp, 'pages_claude', 'abc', 'p1.json'), 'w',
                      encoding='utf-8') as fh:
                json.dump({'status': 'ok', 'model': 'claude-sonnet-5-5'}, fh)
            dirs = {'f.pdf': 'pages/abc'}
            self.assertEqual(vsosh_digitize.page_models(tmp, dirs, ['f.pdf#p1']),
                             'claude-sonnet-5-5')
            self.assertEqual(vsosh_digitize.page_models(tmp, dirs, ['f.pdf#p2']),
                             vsosh_digitize.FLASH_MODEL)

    def test_test_flags_options_and_key_source(self):
        from problems.olympiad_audit import vsosh_quality as Q
        r = {'number': 'тест-1', 'statement_md': 'Вопрос?\n\n- хлеб\n- вода\n- a. гречка'}
        self.assertEqual(Q.task_flags(dict(r), False), ['ключа_нет_в_источнике'])
        self.assertEqual(Q.task_flags(dict(r), True), ['тест_без_ключа'])
        bare = {'number': 'тест-2', 'statement_md': 'Выберите единственно правильный ответ.',
                'answer': 'а'}
        self.assertEqual(Q.task_flags(bare, True), ['тест_без_вариантов'])

    def test_numbers_from_other_files_of_event_count(self):
        from problems.olympiad_audit import vsosh_quality as Q
        page = 'Вопрос про спрос и предложение на рынке товара. ' * 3
        st = 'Вопросы с 6 по 15 оцениваются в 2 балла. Цена 40.'
        self.assertEqual(Q.numbers_not_on_page(st, [page]), ['15', '40'])
        self.assertEqual(Q.numbers_not_on_page(st, [page], ['с 6 по 15']), ['40'])
        self.assertIsNone(Q.numbers_not_on_page(st, [''], ['с 6 по 15 и 40']))

    def test_answer_like(self):
        for good in ('Да', 'неверно', '1)', 'а, в', '2; 4', '**Б**', '3 и 5'):
            self.assertTrue(vsosh_digitize.answer_like(good), good)
        for bad in ('Всего 40 баллов.', 'Задача 4. При равновесии', '', 'а) 20%'):
            self.assertFalse(vsosh_digitize.answer_like(bad), bad)

    def test_fill_test_keys_by_number_and_unhook_from_problem(self):
        rows = [{'number': 'тест-1'}, {'number': 'тест-2'}, {'number': 'тест-10'},
                {'number': '1', 'criteria_md': 'Да\n\nКритерии задачи 1'}]
        keys = [('1', 'Да'), ('2', 'Нет'), ('10', '1)')]
        self.assertEqual(vsosh_digitize.fill_test_keys(rows, keys), 3)
        self.assertEqual([r.get('answer') for r in rows[:3]], ['Да', 'Нет', '1)'])
        self.assertEqual(rows[3]['criteria_md'], 'Критерии задачи 1')

    def test_fill_test_keys_restarted_numbering_by_order_only_if_counts_match(self):
        rows = [{'number': 'тест-1'}, {'number': 'тест-2'}, {'number': 'тест-3'}]
        self.assertEqual(vsosh_digitize.fill_test_keys(
            rows, [('1', 'Да'), ('1', 'а'), ('2', 'б')]), 3)
        self.assertEqual([r['answer'] for r in rows], ['Да', 'а', 'б'])
        rows = [{'number': 'тест-1'}, {'number': 'тест-2'}]
        self.assertEqual(vsosh_digitize.fill_test_keys(
            rows, [('1', 'Да'), ('1', 'а'), ('2', 'б')]), 0)

    def test_key_table_pairs_vertical_horizontal_and_not_data(self):
        vert = 'Ответы\n\n| Номер вопроса | Правильный ответ |\n|---|---|\n| 11 | а |\n| 17 | а,в,д |'
        self.assertEqual(vsosh_digitize.key_table_pairs(vert), [('11', 'а'), ('17', 'а,в,д')])
        hor = ('| Номер вопроса | 1 | 2 | 3 |\n|---|---|---|---|\n'
               '| Ответ | Да | **Нет** | Да |')
        self.assertEqual(vsosh_digitize.key_table_pairs(hor),
                         [('1', 'Да'), ('2', 'Нет'), ('3', 'Да')])
        data = '| Год | ВВП |\n|---|---|\n| 2017 | 91,8 |\n| 2018 | 103,9 |'
        self.assertEqual(vsosh_digitize.key_table_pairs(data), [])
