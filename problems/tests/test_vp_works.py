"""Работы ВП (`vp_works`): только выдуманные данные, сеть не трогается.

Имена участников ниже — выдуманные; в index их быть не должно ни в каком
виде. PDF собираются прямо в тесте, поставщик ИИ — подставной.
"""
import io
import json
import os
import shutil
import tempfile
import urllib.error
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from problems.management.commands.vp_works import Command, read_jsonl, write_jsonl
from problems.vp_works import fetch, hse, listing, pdfwork, scores

FAKE_NAME = 'Пупкинсон Вася Петрович'
FAKE_SURNAME = 'Пупкинсон'

#: Маленький образец ответа шаблона SchoolWinners (как отдаёт сайт).
WINNERS_XML = (
    '<data eof="1">'
    '<row><ID type="int64">900001</ID><FullName>%s</FullName>'
    '<AddRoundMark>74</AddRoundMark><AddFinalMark>81</AddFinalMark>'
    '<BachRound-N>Олимпиада 11 класс</BachRound-N><RoundComp-N>Экономика</RoundComp-N>'
    '<RoundResult-N>rrFirstDegree</RoundResult-N></row>'
    '<row><ID type="int64">900002</ID><FullName>Выдумкина Анна Сергеевна</FullName>'
    '<AddRoundMark>70,5</AddRoundMark><AddFinalMark></AddFinalMark>'
    '<BachRound-N>Олимпиада 11 класс</BachRound-N><RoundComp-N>Экономика</RoundComp-N>'
    '<RoundResult-N>rrFirstDegree</RoundResult-N></row>'
    '</data>' % FAKE_NAME).encode('utf-8')


def fake_pdf_bytes(pages=2):
    """PDF-скан без текстового слоя: страницы-картинки, как у ВП."""
    import fitz
    from PIL import Image, ImageDraw

    doc = fitz.open()
    for i in range(pages):
        image = Image.new('RGB', (600, 850), 'white')
        draw = ImageDraw.Draw(image)
        draw.rectangle((40, 300, 560, 600), outline='black', width=3)
        draw.line((40, 400, 560, 400), fill='black', width=2)
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=buf.getvalue())
    data = doc.tobytes()
    doc.close()
    return data


class FakeClient:
    """Сайт ВП в миниатюре: один сезон, экономика, 11 класс."""

    def __init__(self, pdf=None, fail=False):
        self.requests = 0
        self.pdf_calls = []
        self.pdf = pdf if pdf is not None else fake_pdf_bytes()
        self.fail = fail

    def seasons(self):
        return [{'ID': '111', 'OlympLearnYear-D': '2019/2020 учебный год'}]

    def round_ids(self, season_id):
        return ['r1']

    def subjects(self, round_ids):
        return ['Экономика', 'Право']

    def grades(self, round_ids, subject_name):
        return [{'Master-N': 'Олимпиада 11 класс', 'Name': subject_name}]

    def winners(self, season_id, grade_label, subject_name, degree):
        return hse.parse_rows(WINNERS_XML) if degree == 1 else []

    def work_pdf(self, work_id):
        self.pdf_calls.append(work_id)
        if self.fail:
            raise hse.SiteError('сайт не ответил')
        return self.pdf


def make_record(work_id='900001', season='2019/2020', before=74, after=81):
    return {'work_id': work_id, 'subject': 'economics', 'season': season, 'grade': 11,
            'degree': 1, 'rank': 1, 'score_before': before, 'score_after': after,
            'score_after_listed': True, 'source_url': hse.work_source_url(work_id),
            'listed_at': '2026-10-09T00:00:00Z'}


class TempDirMixin:
    def setUp(self):
        super().setUp()
        self.dir = tempfile.mkdtemp(prefix='vp_works_test_')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)


# ------------------------------------------------------------------ списки

class ListingTests(SimpleTestCase):
    def rows(self):
        return hse.parse_rows(WINNERS_XML)

    def record(self, row):
        return listing.winner_record(row, rank=1, subject='economics', season='2019/2020',
                                     grade=11, degree=1, source_url='u', listed_at='t')

    def test_record_has_no_name(self):
        """Дефект 1: ФИО не попадает в строку index ни в каком поле."""
        rec = self.record(self.rows()[0])
        self.assertNotIn(FAKE_SURNAME, json.dumps(rec, ensure_ascii=False))
        self.assertEqual(tuple(rec), listing.INDEX_FIELDS)

    def test_after_appeal_is_kept(self):
        """Дефект 2: «балл после апелляции» берётся из AddFinalMark."""
        rec = self.record(self.rows()[0])
        self.assertEqual((rec['score_before'], rec['score_after']), (74, 81))
        self.assertTrue(rec['score_after_listed'])

    def test_empty_final_mark_means_same_as_before(self):
        rec = self.record(self.rows()[1])
        self.assertEqual((rec['score_before'], rec['score_after']), (70.5, 70.5))
        self.assertFalse(rec['score_after_listed'])

    def test_labels(self):
        self.assertEqual(listing.season_label('2013/2014 учебный год'), '2013/2014')
        self.assertEqual(listing.grade_number('Олимпиада 08 класс'), 8)
        self.assertEqual(listing.parse_subjects('economics,law=Право'),
                         [('economics', 'Экономика'), ('law', 'Право')])
        with self.assertRaises(ValueError):
            listing.parse_subjects('неведомое')

    def test_check_index_reports_violations(self):
        a = make_record('1', before=80, after=75)
        b = make_record('1')
        check = listing.check_index([a, b], expected_total=3)
        self.assertEqual(check['duplicates'], 1)
        self.assertEqual(check['after_lower'], ['1'])
        self.assertEqual(len(check['problems']), 2)


class IndexCommandTests(TempDirMixin, SimpleTestCase):
    def test_index_file_has_no_name_and_matches_volume(self):
        """Дефект 1 целиком: ни в index.jsonl, ни в volume.jsonl нет ФИО."""
        cmd = Command(stdout=io.StringIO())
        cmd.do_index(self.dir, {'subjects': 'economics,fingram'}, client=FakeClient())
        for name in ('index.jsonl', 'volume.jsonl'):
            with open(os.path.join(self.dir, name), encoding='utf-8') as fh:
                self.assertNotIn(FAKE_SURNAME, fh.read())
        rows = read_jsonl(os.path.join(self.dir, 'index.jsonl'))
        self.assertEqual([r['work_id'] for r in rows], ['900001', '900002'])
        self.assertEqual(rows[0]['score_after'], 81)
        volume = read_jsonl(os.path.join(self.dir, 'volume.jsonl'))
        self.assertEqual(sum(v['works'] for v in volume), 2)
        self.assertIn('fingram: предмета в этом сезоне нет', cmd.stdout.getvalue())


# ------------------------------------------------------------------ сайт

class _Resp(io.BytesIO):
    def __init__(self, body, ctype='text/xml'):
        super().__init__(body)
        self.status = 200
        self.headers = {'Content-Type': ctype}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class SiteClientTests(SimpleTestCase):
    def client_with(self, *answers):
        answers = list(answers)
        opener = mock.Mock()

        def open_(request, timeout=None):
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        opener.open.side_effect = open_
        slept = []
        return hse.Client(opener=opener, sleep=slept.append, clock=lambda: 0.0), slept

    def test_403_stops_without_retry(self):
        err = urllib.error.HTTPError('u', 403, 'Forbidden', {}, None)
        client, slept = self.client_with(err)
        with self.assertRaises(hse.Blocked):
            client.seasons()
        self.assertEqual(client.requests, 1)

    def test_captcha_page_stops(self):
        client, _ = self.client_with(_Resp(b'<html>captcha</html>', 'text/html'))
        with self.assertRaises(hse.Blocked):
            client.seasons()

    def test_retry_with_pause_then_success(self):
        err = urllib.error.HTTPError('u', 502, 'Bad gateway', {}, None)
        client, slept = self.client_with(err, _Resp(WINNERS_XML))
        self.assertEqual(len(client.winners('1', 'Олимпиада 11 класс', 'Экономика', 1)), 2)
        self.assertIn(5, slept)

    def test_non_pdf_answer_is_not_a_pdf(self):
        client, _ = self.client_with(*[_Resp(b'<data/>')] * 4)
        with self.assertRaises(hse.SiteError):
            client.work_pdf('1')

    def test_mill_error_and_doctype(self):
        with self.assertRaises(hse.SiteError):
            hse.parse_rows(b'<error>bad</error>')
        with self.assertRaises(hse.SiteError):
            hse.parse_rows(b'<!DOCTYPE x [<!ENTITY a "b">]><data/>')

    def test_work_query_is_neutral(self):
        q = hse.q_work('36408207073')
        self.assertIn('<ID>36408207073</ID>', q)
        self.assertIn('filename="work_36408207073.pdf"', q)


# ------------------------------------------------------------------ скачивание

class DownloadTests(TempDirMixin, SimpleTestCase):
    def path_of(self, rec):
        return os.path.join(self.dir, pdfwork.pdf_relpath(rec))

    def test_existing_file_is_not_downloaded_again(self):
        """Дефект 3: целый файл на месте — сайт не трогаем."""
        rec = make_record()
        os.makedirs(os.path.dirname(self.path_of(rec)))
        with open(self.path_of(rec), 'wb') as fh:
            fh.write(fake_pdf_bytes())
        client = FakeClient()
        stats = fetch.download_all([rec], self.dir, client, log=lambda m: None)
        self.assertEqual(client.pdf_calls, [])
        self.assertEqual((stats['downloaded'], stats['skipped_existing']), (0, 1))
        self.assertEqual(rec['status'], 'ok')

    def test_second_run_downloads_nothing(self):
        recs = [make_record('1'), make_record('2')]
        client = FakeClient()
        fetch.download_all(recs, self.dir, client, log=lambda m: None)
        self.assertEqual(len(client.pdf_calls), 2)
        fetch.download_all(recs, self.dir, client, log=lambda m: None)
        self.assertEqual(len(client.pdf_calls), 2)
        self.assertEqual(recs[0]['pages'], 2)
        self.assertFalse(recs[0]['has_text_layer'])

    def test_junk_file_is_not_ok(self):
        """Дефект 4: файл без %PDF — не ok; он качается заново."""
        rec = make_record()
        os.makedirs(os.path.dirname(self.path_of(rec)))
        with open(self.path_of(rec), 'wb') as fh:
            fh.write(b'<html>not a pdf</html>')
        self.assertFalse(pdfwork.looks_like_pdf(self.path_of(rec)))
        client = FakeClient()
        fetch.download_all([rec], self.dir, client, log=lambda m: None)
        self.assertEqual(client.pdf_calls, ['900001'])
        self.assertEqual(rec['status'], 'ok')

    def test_broken_pdf_body_is_failed(self):
        rec = make_record()
        client = FakeClient(pdf=b'%PDF-1.4 oops, truncated')
        fetch.download_all([rec], self.dir, client, log=lambda m: None)
        self.assertEqual(rec['status'], 'failed')
        check = fetch.check_download([rec], self.dir)
        self.assertEqual((check['ok'], check['failed']), (0, 1))

    def test_fail_streak_pauses_then_stops(self):
        recs = [make_record(str(i)) for i in range(10)]
        slept = []
        with mock.patch.object(fetch, 'FAIL_STREAK', 2), \
                mock.patch.object(fetch, 'MAX_STREAK_PAUSES', 1):
            stats = fetch.download_all(recs, self.dir, FakeClient(fail=True),
                                       log=lambda m: None, sleep=slept.append)
        self.assertEqual(slept, [fetch.STREAK_PAUSE])
        self.assertEqual(stats['stopped'], 'fail_streak')
        self.assertEqual(stats['failed'], 4)


# ------------------------------------------------------------------ баллы

class VerdictTests(SimpleTestCase):
    def test_sum_must_match_listed_score(self):
        """Дефект 5: сумма по задачам сверяется с баллом до апелляции."""
        data = {'tasks': [{'n': 1, 'score': '20'}, {'n': 2, 'score': '21'}],
                'total': '74', 'readable': True}
        status, details = scores.verdict(data, 74)
        self.assertEqual((status, details['reason']), ('review', 'sum_mismatch'))
        status, _ = scores.verdict(data, 41)
        self.assertEqual(status, 'ok')
        status, _ = scores.verdict(data, 41.5)
        self.assertEqual(status, 'ok')

    def test_unreadable_and_format_go_to_review(self):
        self.assertEqual(scores.verdict({'tasks': [{'n': 1, 'score': None}],
                                         'readable': True}, 0)[1]['reason'],
                         'task_unreadable')
        self.assertEqual(scores.verdict({'readable': False}, 5)[1]['reason'], 'unreadable')
        self.assertEqual(scores.verdict(scores.tolerant_parse('мусор'), 5)[1]['reason'],
                         'format')

    def test_tolerant_parse(self):
        self.assertEqual(scores.tolerant_parse('```json\n{"tasks": [], "total": null}\n```')
                         ['tasks'], [])
        self.assertEqual(scores.tolerant_parse('вот: {"a": 1} всё')['a'], 1)
        self.assertEqual(scores.tolerant_parse('[{"n": 1, "score": "7,5"}]')['tasks'][0]['n'], 1)
        self.assertTrue(scores.tolerant_parse('')['_format_error'])
        self.assertEqual(scores.to_number('7,5'), 7.5)

    def test_blank_cell_is_zero_but_null_is_unreadable(self):
        data = {'tasks': [{'n': 1, 'score': '23'}, {'n': 2, 'score': ''}], 'readable': True}
        self.assertEqual(scores.verdict(data, 23)[0], 'ok')
        data['tasks'][1]['score'] = None
        self.assertEqual(scores.verdict(data, 23)[1]['reason'], 'task_unreadable')

    def test_layouts_are_fractions_and_unseen_seasons_have_none(self):
        for bands in scores.LAYOUTS.values():
            for x0, y0, x1, y1 in bands:
                self.assertTrue(0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1)
        self.assertIsNone(scores.layout_for('2014/2015'))
        self.assertEqual(scores.layout_for('2025/2026'), 'v3_2026')


TEST_LAYOUT = {'test': ((0.05, 0.35, 0.95, 0.40), (0.05, 0.55, 0.95, 0.65))}
GOOD_REPLY = json.dumps({'tasks': [{'n': 1, 'score': '40'}, {'n': 2, 'score': '34'}],
                         'total': '74', 'readable': True})


@mock.patch.object(scores, 'LAYOUTS', TEST_LAYOUT)
@mock.patch.object(scores, 'layout_for', lambda season: 'test')
@mock.patch.dict(os.environ, {'VP_WORKS_WORKERS': '1'})
class ScoresCommandTests(TempDirMixin, TestCase):
    def prepare(self, n=3):
        recs = [make_record(str(900100 + i)) for i in range(n)]
        fetch.download_all(recs, self.dir, FakeClient(), log=lambda m: None)
        write_jsonl(os.path.join(self.dir, 'index.jsonl'), recs)

    def test_crop_is_two_bands(self):
        from PIL import Image

        out = scores.crop_scores(Image.new('RGB', (1000, 1000), 'white'), 'test')
        self.assertEqual(out.size, (900, 50 + 100 + 6))

    def test_without_yes_provider_is_never_called(self):
        """Дефект 6: без --yes настоящий поставщик не вызывается вовсе."""
        self.prepare()
        with mock.patch('problems.ai.providers.GLMProvider.complete',
                        side_effect=AssertionError('вызов модели без --yes')) as complete, \
                mock.patch('problems.ai.providers.GLMProvider.is_available',
                           return_value=True):
            call_command('vp_works', 'scores', '--dir', self.dir, stdout=io.StringIO())
        complete.assert_not_called()
        rows = read_jsonl(os.path.join(self.dir, 'index.jsonl'))
        self.assertTrue(all('scores_status' not in r for r in rows))
        self.assertEqual(len(os.listdir(os.path.join(self.dir, 'crops', '2019_2020'))), 3)

    @override_settings(VP_WORKS_PROVIDER='fake', AI_FAKE_REPLY=GOOD_REPLY)
    def test_yes_reads_and_checks_sum(self):
        self.prepare(n=2)
        call_command('vp_works', 'scores', '--dir', self.dir, '--yes', stdout=io.StringIO())
        rows = read_jsonl(os.path.join(self.dir, 'index.jsonl'))
        self.assertEqual([r['scores_status'] for r in rows], ['ok', 'ok'])
        self.assertEqual(rows[0]['scores_tasks'], [40.0, 34.0])

    @override_settings(VP_WORKS_PROVIDER='fake', AI_FAKE_REPLY=GOOD_REPLY,
                       AI_PRICES={'glm-5.3-flash': (1000.0, 1000.0)})
    def test_max_usd_stops_new_calls(self):
        """Дефект 7: потолок --max-usd обрывает прогон — новых вызовов нет."""
        self.prepare(n=5)
        out = io.StringIO()
        call_command('vp_works', 'scores', '--dir', self.dir, '--yes', '--max-usd', '0.01',
                     stdout=out)
        rows = read_jsonl(os.path.join(self.dir, 'index.jsonl'))
        called = [r for r in rows if r.get('scores_status')]
        self.assertEqual(len(called), 1)
        self.assertIn('ОСТАНОВЛЕНО', out.getvalue())

    def test_data_dir_inside_repo_is_refused(self):
        from django.core.management.base import CommandError

        repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with self.assertRaises(CommandError):
            call_command('vp_works', 'report', '--dir', os.path.join(repo, 'tmp_vp'),
                         stdout=io.StringIO())
