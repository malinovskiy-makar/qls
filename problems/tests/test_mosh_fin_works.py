"""Работы МОШ по финансовой грамотности (`mosh_works --subject fin`): только выдуманные данные.

Предмет — параметр пакета `problems.mosh_works`: экономика (`econ`, по умолчанию) обязана
вести себя как раньше; финграм — свой слаг таблицы, своя папка zip, свой бланк титула.
"""
import io
import json
import os
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from problems.management.commands import mosh_works as cmd
from problems.management.commands.mosh_works import read_jsonl, write_jsonl
from problems.mosh_works import fetch, listing, scans
from problems.tests.test_mosh_works import (
    FAKE_SURNAME, FakeClient, TempDirMixin, jpeg, make_zip, no_log, page_image)

TAIL = '0042'


def fin_table(year=2023):
    base = 'https://reg.olimpiada.ru/files/scans-public-by-oa/mosh-fingram-%d/' % year
    econ = 'https://reg.olimpiada.ru/files/scans-public-by-oa/mosh-econ-%d/' % year
    return (
        '<table><tr><td>Номер работы</td><td>Ф.И.О.</td><td>Класс участия</td><td>Класс</td>'
        '<td>Сумма</td><td>Результат</td></tr>'
        '<tr><td><a href="%s80000001%s.zip">80000001</a></td><td>%s Финансист Иванович</td>'
        '<td>6</td><td>6</td><td>81</td><td>победитель</td></tr>'
        '<tr><td><a href="%s80000002%s.zip">80000002</a></td><td>Выдумкин Пётр</td>'
        '<td>9</td><td>9</td><td>60</td><td>призёр</td></tr>'
        '</table>' % (base, TAIL, FAKE_SURNAME, econ, TAIL))


def fin_record(work_id='80000001', year=2022):
    return {'work_id': work_id, 'year': year, 'season': listing.season_of(year),
            'grade_participation': 9, 'grade': 9, 'total_listed': 81, 'result': 'winner',
            'prize_degree': None,
            'zip_url': 'https://reg.olimpiada.ru/files/scans-public-by-oa/mosh-fingram-%d/%s%s.zip'
                       % (year, work_id, TAIL),
            'listed_at': '2026-10-13T00:00:00Z'}


class FinListingTests(SimpleTestCase):
    def test_fin_index_has_no_name(self):
        rows = listing.parse_table(fin_table(), 2023, 'x', 'fin')
        self.assertEqual(len(rows), 2)
        self.assertNotIn(FAKE_SURNAME, json.dumps(rows, ensure_ascii=False))
        self.assertEqual(set(rows[0]), set(listing.INDEX_FIELDS))

    def test_zip_only_from_the_link_of_its_own_subject(self):
        rows = listing.parse_table(fin_table(), 2023, 'x', 'fin')
        self.assertTrue(rows[0]['zip_url'].endswith('/mosh-fingram-2023/80000001%s.zip' % TAIL))
        # ссылка в папку ДРУГОГО предмета (экономики) — не «чинится», а отбрасывается
        self.assertIsNone(rows[1]['zip_url'])
        # и наоборот: экономика не берёт ссылку финграма
        self.assertIsNone(listing.pick_zip_url(
            ['https://reg.olimpiada.ru/files/scans-public-by-oa/mosh-fingram-2023/80000001%s.zip' % TAIL],
            2023, '80000001'))

    def test_subject_parameter_does_not_change_economics(self):
        self.assertEqual(listing.page_url(2024), listing.PAGE_URL % 2024)
        self.assertIs(listing.zip_url_re('econ'), listing.ZIP_URL_RE)
        self.assertEqual(listing.page_url(2024, 'fin'),
                         'https://reg.cpm.moscow/register/mosh-fingram-2024-prizewinners/'
                         'olympiad-protocol-static')
        self.assertEqual(cmd.DEFAULT_DIRS['econ'], cmd.DEFAULT_DIR)
        self.assertIs(cmd.RECON_ROWS_BY_SUBJECT['econ'], cmd.RECON_ROWS)


class FinIndexCommandTests(TempDirMixin, SimpleTestCase):
    def test_index_fin_reads_the_fin_page_and_stores_no_name(self):
        client = FakeClient(default=fin_table().encode('utf-8'))
        command = cmd.Command(stdout=io.StringIO())
        command.do_index(self.dir, {'years': '2023', 'subject': 'fin'}, client=client)
        self.assertEqual(client.calls, [listing.page_url(2023, 'fin')])
        with open(os.path.join(self.dir, 'index.jsonl'), encoding='utf-8') as fh:
            text = fh.read()
        self.assertNotIn(FAKE_SURNAME, text)
        self.assertNotIn('Выдумкин', text)

    def test_index_econ_by_default_reads_the_econ_page(self):
        client = FakeClient(default=('<table><tr><td>Номер работы</td><td>Ф.И.О.</td><td>Класс участия'
                                     '</td><td>Класс</td><td>Сумма</td><td>Результат</td></tr></table>'
                                     ).encode('utf-8'))
        cmd.Command(stdout=io.StringIO()).do_index(self.dir, {'years': '2024'}, client=client)
        self.assertEqual(client.calls, [listing.PAGE_URL % 2024])


class FinScansTests(TempDirMixin, SimpleTestCase):
    def test_cover_file_is_never_a_page_and_never_a_title(self):
        for name, img in (('fg-01-0001.jpg', page_image(red=True)), ('fg-01-0003.jpg', page_image(work=True)),
                          ('mosh-fin-titul-000441.jpg', page_image(cover=True))):
            with open(os.path.join(self.dir, name), 'wb') as fh:
                fh.write(jpeg(img))
        names = [n for n, _ in scans.fin_pages(self.dir)]
        self.assertNotIn('mosh-fin-titul-000441.jpg', names)
        info = scans.fin_analyze(self.dir, 2023)
        self.assertEqual(info['first_page'], 'fg-01-0001.jpg')
        self.assertEqual(info['cover_skipped'], 1)
        with self.assertRaises(scans.UnsafePage):
            scans.fin_title_image(self.dir, 'mosh-fin-titul-000441.jpg')

    def test_numeric_order_of_sheets(self):
        for name in ('10-sc1-a.jpg', '2-sc1-a.jpg', '1-sc1-a.jpg'):
            with open(os.path.join(self.dir, name), 'wb') as fh:
                fh.write(jpeg(page_image(work=True)))
        self.assertEqual([n for n, _ in scans.fin_pages(self.dir)], ['1-sc1-a.jpg', '2-sc1-a.jpg', '10-sc1-a.jpg'])

    def test_years_without_score_table_have_no_title(self):
        with open(os.path.join(self.dir, '1-a.jpg'), 'wb') as fh:
            fh.write(jpeg(page_image(work=True)))
        info = scans.fin_analyze(self.dir, 2024)
        self.assertIsNone(info['first_page'])
        self.assertEqual(info['form'], 'answer_sheets')


GOOD_FIN = json.dumps({'variant': '2', 'tasks': [{'n': i, 'label': '№%d' % i, 'score': s}
                                                 for i, s in enumerate(['20', '18', '15', '16', '12'], 1)],
                       'total': '81', 'readable': True})


class FinScoresCommandTests(TempDirMixin, TestCase):
    def prepare(self, years=(2022,), **page):
        recs = []
        for y in years:
            rec = fin_record(str(80000100 + y), year=y)
            recs.append(rec)
        client = FakeClient(default=make_zip({'fg-01-0001.jpg': jpeg(page_image(**page)),
                                              'fg-01-0002.jpg': jpeg(page_image(work=True))}))
        fetch.download_all(recs, self.dir, client, log=no_log, sleep=lambda s: None)
        write_jsonl(os.path.join(self.dir, 'index.jsonl'), recs)
        return recs

    def scores(self, *args):
        call_command('mosh_works', 'scores', '--subject', 'fin', '--dir', self.dir, *args,
                     stdout=io.StringIO())
        p = os.path.join(self.dir, 'scores.jsonl')
        return {r['work_id']: r for r in read_jsonl(p)} if os.path.exists(p) else {}

    def test_without_yes_zero_calls(self):
        self.prepare(red=True)
        with mock.patch('problems.ai.core.run', side_effect=AssertionError('вызов без --yes')) as run:
            self.scores()
        run.assert_not_called()

    @override_settings(MOSH_WORKS_PROVIDER='fake', AI_FAKE_REPLY=GOOD_FIN)
    def test_only_score_years_go_to_the_model_and_variant_is_kept(self):
        self.prepare(years=(2022, 2024), red=True)
        rows = self.scores('--yes', '--years', '2022,2024', '--release', '80002122')
        self.assertEqual(list(rows), ['80002122'])          # 2024 — таблицы нет, в модель не идёт
        self.assertEqual(rows['80002122']['variant'], '2')
        self.assertEqual(rows['80002122']['scores_status'], 'ok')

    @override_settings(MOSH_WORKS_PROVIDER='fake', AI_FAKE_REPLY=GOOD_FIN,
                       AI_PRICES={'glm-5.3-flash': (1000.0, 1000.0)})
    def test_max_usd_stops(self):
        recs = [fin_record(str(80000200 + i), year=2022) for i in range(4)]
        client = FakeClient(default=make_zip({'fg-01-0001.jpg': jpeg(page_image(red=True))}))
        fetch.download_all(recs, self.dir, client, log=no_log, sleep=lambda s: None)
        write_jsonl(os.path.join(self.dir, 'index.jsonl'), recs)
        # один поток: после первого ответа потолок достигнут — новых вызовов нет
        with mock.patch.dict(os.environ, {'MOSH_WORKS_WORKERS': '1'}):
            rows = self.scores('--yes', '--max-usd', '0.000001',
                               '--release', ','.join(r['work_id'] for r in recs))
        self.assertEqual(len(rows), 1)
