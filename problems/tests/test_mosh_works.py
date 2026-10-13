"""Работы МОШ (`mosh_works`): только выдуманные данные, сеть не трогается.

Имена участников ниже — выдуманные; в index их быть не должно ни в каком
виде. Таблица — свой маленький HTML, zip и картинки собираются прямо в
тесте, поставщик ИИ — подставной.
"""
import io
import json
import os
import shutil
import tempfile
import urllib.error
import zipfile
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from problems.management.commands.mosh_works import read_jsonl, write_jsonl
from problems.mosh_works import fetch, listing, scans, scores
from problems.vp_works import hse

FAKE_SURNAME = 'Пупкинсон'

#: Выдуманные хвосты адресов: «формулы» нет — как у настоящих работ.
TAIL_A, TAIL_B = '0042', '7313'


def table_html(year=2024, with_zip=True):
    """Страница призёров в миниатюре: заголовок и три строки."""
    base = 'https://reg.olimpiada.ru/files/scans-public-by-oa/mosh-econ-%d/' % year
    first = ('<a href="%s%s%s.zip">70000001</a>' % (base, '70000001', TAIL_A)
             if with_zip else '70000001')
    return (
        '<html><body><table>'
        '<tr><td>Номер работы</td><td>Ф.И.О.</td><td>Класс участия</td><td>Класс</td>'
        '<td>Сумма</td><td>Результат</td></tr>'
        '<tr><td>%s</td><td>%s Вася Петрович</td><td>11</td><td>10</td><td>74,5</td>'
        '<td>победитель</td></tr>'
        '<tr><td><a href="%s70000002%s.zip">70000002</a></td><td>Выдумкина Анна</td>'
        '<td>9</td><td>9</td><td>63</td><td>призёр</td></tr>'
        '<tr><td>70000003</td><td>Тестов Тест</td><td>7</td><td>7</td><td>51</td>'
        '<td>призёр 2 степени</td></tr>'
        '</table></body></html>' % (first, FAKE_SURNAME, base, TAIL_B))


# ------------------------------------------------------------ сканы и zip

def page_image(red=False, yellow=False, work=False, cover=False, notable=False, grid=False,
               size=(600, 850)):
    """Выдуманная страница: «титул» с таблицей в полосе или лист с решением."""
    from PIL import Image, ImageDraw

    img = Image.new('RGB', size, 'white')
    d = ImageDraw.Draw(img)
    w, h = size
    if cover:
        # Обложка «Уважаемые участники олимпиады!»: фамилия, имя, отчество и рамка
        # школы там, где у титула пусто (выдуманные чернила вместо текста).
        d.rectangle((20, 60, 200, 140), fill='black')
        d.rectangle((w - 160, 60, w - 40, 180), fill='black')
        for k, y in enumerate((0.385, 0.415, 0.445)):
            d.rectangle((0.55 * w, y * h, 0.55 * w + 150 + 20 * k, y * h + 14), fill='black')
        d.rectangle((0.52 * w, 0.49 * h, 0.95 * w, 0.60 * h), outline='black', width=3)
        d.text((0.56 * w, 0.52 * h), 'SCHOOL NAME', fill='black')
        return img
    if work:
        for y in range(40, h - 40, 14):
            d.line((50, y, w - 50, y + (y % 5)), fill='black', width=2)
        d.rectangle((40, 30, w - 40, h - 30), outline='black', width=3)
        return img
    d.rectangle((20, 60, 200, 140), fill='black')          # логотип
    d.rectangle((w - 160, 60, w - 40, 180), fill='black')   # QR
    if notable:
        return img
    if grid:
        # Клетчатая бумага: линий намного больше, чем у таблицы баллов.
        for k in range(int(0.52 * h), int(0.92 * h), 11):
            d.line((20, k, w - 20, k), fill=(120, 120, 120), width=1)
        for k in range(20, w - 20, 11):
            d.line((k, int(0.52 * h), k, int(0.92 * h)), fill=(120, 120, 120), width=1)
        return img
    d.rectangle((60, 0.55 * h, w - 60, 0.85 * h), outline='black', width=3)
    for i in range(6):   # заголовок «Задача | 1 | 2 | 3 | 4 | Сумма»: по значку в клетке
        x = 60 + i * (w - 120) / 6 + 14
        d.rectangle((x, 0.55 * h + 10, x + 18, 0.55 * h + 24), fill='black')
    for i in range(1, 6):
        d.line((60 + i * (w - 120) / 6, 0.55 * h, 60 + i * (w - 120) / 6, 0.85 * h),
               fill='black', width=2)
    for j in range(1, 5):
        y = 0.55 * h + j * 0.3 * h / 5
        d.line((60, y, w - 60, y), fill='black', width=2)
    if red:
        d.text((90, 0.62 * h), '40 35 40', fill=(220, 20, 40))
        d.rectangle((120, 0.70 * h, 200, 0.73 * h), fill=(220, 20, 40))
    if yellow:
        d.rectangle((100, 0.60 * h, 300, 0.66 * h), fill=(255, 255, 0))
    return img


def jpeg(img):
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=90)
    return buf.getvalue()


def fake_pdf_bytes(pages=2, specs=None, **kw):
    import fitz

    doc = fitz.open()
    specs = specs or [kw if i == 0 else {'work': True} for i in range(pages)]
    for spec in specs:
        buf = io.BytesIO()
        page_image(**spec).save(buf, format='PNG')
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=buf.getvalue())
    data = doc.tobytes()
    doc.close()
    return data


def make_zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def zip_with_title(**kw):
    """Работа из JPG: титул и лист с решением."""
    return make_zip({'mosh-econ-01-0001.jpg': jpeg(page_image(**kw)),
                     'mosh-econ-01-0002.jpg': jpeg(page_image(work=True))})


def make_record(work_id='70000001', year=2024, total=74, url='default'):
    base = 'https://reg.olimpiada.ru/files/scans-public-by-oa/mosh-econ-%d/' % year
    return {'work_id': work_id, 'year': year, 'season': listing.season_of(year),
            'grade_participation': 11, 'grade': 11, 'total_listed': total,
            'result': 'winner', 'prize_degree': None,
            'zip_url': base + work_id + TAIL_A if url == 'default' else url,
            'listed_at': '2026-10-09T00:00:00Z'}


class FakeClient:
    """Сайт организатора в миниатюре: отдаёт заранее заданные байты по адресу."""

    def __init__(self, bodies=None, default=None, fail=False):
        self.requests = 0
        self.calls = []
        self.bodies = bodies or {}
        self.default = default
        self.fail = fail

    def get(self, url, expect='html'):
        self.requests += 1
        self.calls.append(url)
        if self.fail:
            raise hse.SiteError('сайт не ответил')
        body = self.bodies.get(url, self.default)
        if body is None:
            raise hse.SiteError('нет такого адреса: ' + url)
        return body


class TempDirMixin:
    def setUp(self):
        super().setUp()
        self.dir = tempfile.mkdtemp(prefix='mosh_works_test_')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)


def no_log(_message):
    return None


# ------------------------------------------------------------------ таблица

class ListingTests(SimpleTestCase):
    def parse(self, **kw):
        return listing.parse_table(table_html(**kw), 2024, '2026-10-09T00:00:00Z')

    def test_record_has_no_name(self):
        """Дефект 1: ФИО не попадает в строку index ни в каком поле."""
        rows = self.parse()
        self.assertEqual(len(rows), 3)
        for rec in rows:
            self.assertNotIn(FAKE_SURNAME, json.dumps(rec, ensure_ascii=False))
            self.assertEqual(tuple(rec), listing.INDEX_FIELDS)

    def test_name_column_is_not_even_accumulated(self):
        """Текст столбца ФИО не копится и во внутренних строках разборщика."""
        parser = listing._TableParser()
        parser.feed(table_html())
        self.assertNotIn(FAKE_SURNAME, json.dumps(parser.rows, ensure_ascii=False))

    def test_zip_url_is_taken_from_the_link_not_built(self):
        """Дефект 2: адрес — из ссылки в таблице; «хвост» не вычисляется."""
        rows = {r['work_id']: r for r in self.parse()}
        base = 'https://reg.olimpiada.ru/files/scans-public-by-oa/mosh-econ-2024/'
        self.assertEqual(rows['70000001']['zip_url'], base + '70000001' + TAIL_A + '.zip')
        self.assertEqual(rows['70000002']['zip_url'], base + '70000002' + TAIL_B + '.zip')
        # Нет ссылки — нет адреса: его не достраивают ни по какому шаблону.
        self.assertIsNone(rows['70000003']['zip_url'])
        self.assertIsNone(self.parse(with_zip=False)[0]['zip_url'])

    def test_foreign_or_odd_links_are_dropped(self):
        for href in ('https://evil.example/files/70000001%s.zip' % TAIL_A,
                     'https://reg.olimpiada.ru/files/other-folder/70000001%s.zip' % TAIL_A,
                     'https://reg.olimpiada.ru/files/scans-public-by-oa/mosh-econ-2023/'
                     '70000001%s.zip' % TAIL_A,
                     'https://reg.olimpiada.ru/files/scans-public-by-oa/mosh-econ-2024/'
                     '70000009%s.zip' % TAIL_A):
            self.assertIsNone(listing.pick_zip_url([href], 2024, '70000001'), href)

    def test_values(self):
        rec = {r['work_id']: r for r in self.parse()}
        self.assertEqual((rec['70000001']['result'], rec['70000001']['total_listed']),
                         ('winner', 74.5))
        self.assertEqual((rec['70000001']['grade_participation'], rec['70000001']['grade']),
                         (11, 10))
        self.assertEqual((rec['70000003']['result'], rec['70000003']['prize_degree']),
                         ('prizewinner', 2))
        self.assertEqual(rec['70000001']['season'], '2023/2024')

    def test_unknown_layout_is_an_error_not_a_guess(self):
        with self.assertRaises(ValueError):
            listing.parse_table('<table><tr><td>Номер работы</td><td>Что-то</td></tr></table>',
                                2024, 't')

    def test_check_index_reports_violations(self):
        rows = self.parse()
        rows.append(dict(rows[0]))
        rows[1]['total_listed'] = None
        check = listing.check_index(rows, expected_rows={2024: 3})
        self.assertEqual(check['duplicates'], 1)
        self.assertEqual((check['no_zip'], check['no_total']), (['70000003'], ['70000002']))
        self.assertTrue(check['problems'])


class IndexCommandTests(TempDirMixin, SimpleTestCase):
    def test_index_file_has_no_name(self):
        client = FakeClient(default=table_html().encode('utf-8'))
        out = io.StringIO()
        from problems.management.commands.mosh_works import Command

        cmd = Command(stdout=out)
        cmd.do_index(self.dir, {'years': '2024'}, client=client)
        raw = open(os.path.join(self.dir, 'index.jsonl'), encoding='utf-8').read()
        self.assertNotIn(FAKE_SURNAME, raw)
        self.assertEqual(len(read_jsonl(os.path.join(self.dir, 'index.jsonl'))), 3)
        self.assertIn('строк без ссылки на zip: 1', out.getvalue())


# ------------------------------------------------------------------ клиент

class _Resp(io.BytesIO):
    def __init__(self, body, ctype='application/zip'):
        super().__init__(body)
        self.status = 200
        self.headers = {'Content-Type': ctype}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class SiteClientTests(SimpleTestCase):
    URL = 'https://reg.olimpiada.ru/files/scans-public-by-oa/mosh-econ-2024/70000001%s.zip' % TAIL_A

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
        return fetch.Client(opener=opener, sleep=slept.append, clock=lambda: 0.0), slept

    def test_foreign_host_is_refused_before_any_request(self):
        client, _ = self.client_with()
        with self.assertRaises(ValueError):
            client.get('https://evil.example/a.zip', expect='zip')
        self.assertEqual(client.requests, 0)

    def test_403_stops_without_retry(self):
        client, slept = self.client_with(urllib.error.HTTPError('u', 403, 'F', {}, None))
        with self.assertRaises(hse.Blocked):
            client.get(self.URL, expect='zip')
        self.assertEqual(client.requests, 1)

    def test_404_is_not_retried(self):
        client, slept = self.client_with(urllib.error.HTTPError('u', 404, 'NF', {}, None))
        with self.assertRaises(hse.SiteError):
            client.get(self.URL, expect='zip')
        self.assertEqual((client.requests, slept), (1, []))

    def test_retry_pauses_and_broken_read(self):
        import http.client

        class Broken(_Resp):
            def read(self, *a):
                raise http.client.IncompleteRead(b'PK')
        ok = make_zip({'a.jpg': b'x'})
        client, slept = self.client_with(Broken(b''), urllib.error.URLError('reset'), _Resp(ok))
        self.assertEqual(client.get(self.URL, expect='zip'), ok)
        self.assertEqual([x for x in slept if x > 1], [5, 15])

    def test_not_a_zip_answer_is_retried(self):
        client, slept = self.client_with(*[_Resp(b'<html>oops</html>', 'text/plain')] * 4)
        with self.assertRaises(hse.SiteError):
            client.get(self.URL, expect='zip')
        self.assertEqual([x for x in slept if x > 1], [5, 15, 45])


# ------------------------------------------------------------------ скачивание

class DownloadTests(TempDirMixin, SimpleTestCase):
    def run_download(self, recs, client, **kw):
        return fetch.download_all(recs, self.dir, client, log=no_log, sleep=lambda s: None, **kw)

    def test_downloads_unpacks_and_fills_the_record(self):
        rec = make_record()
        client = FakeClient(default=zip_with_title(red=True))
        stats = self.run_download([rec], client)
        self.assertEqual(stats['downloaded'], 1)
        self.assertEqual(rec['status'], 'ok')
        self.assertEqual((rec['files'], rec['pages']), (2, 2))
        self.assertEqual(len(rec['sha256']), 64)
        self.assertTrue(os.path.exists(os.path.join(self.dir, 'scans/2024/70000001/'
                                                    'mosh-econ-01-0001.jpg')))
        self.assertEqual(rec['first_page'], 'mosh-econ-01-0001.jpg')

    def test_existing_valid_zip_is_not_downloaded_again(self):
        """Дефект 3: докачка не качает заново целый zip."""
        rec = make_record()
        os.makedirs(os.path.join(self.dir, 'zip', '2024'))
        with open(os.path.join(self.dir, fetch.zip_relpath(rec)), 'wb') as fh:
            fh.write(zip_with_title())
        client = FakeClient(default=zip_with_title())
        stats = self.run_download([rec], client)
        self.assertEqual((client.requests, stats['skipped_existing'], rec['status']),
                         (0, 1, 'ok'))

    def test_second_run_downloads_nothing(self):
        recs = [make_record('70000001'), make_record('70000002')]
        client = FakeClient(default=zip_with_title())
        self.run_download(recs, client)
        first = client.requests
        self.run_download(recs, client)
        self.assertEqual((first, client.requests), (2, 2))

    def test_broken_zip_is_failed_not_ok(self):
        """Дефект 4: битый zip не считается ok."""
        rec = make_record()
        client = FakeClient(default=b'PK\x03\x04 this is not a zip at all')
        self.run_download([rec], client)
        self.assertEqual(rec['status'], 'failed')
        check = fetch.check_download([rec], self.dir)
        self.assertEqual((check['ok'], check['failed'], check['ok_bad_zip']), (0, 1, []))

    def test_junk_file_on_disk_is_downloaded_again(self):
        rec = make_record()
        os.makedirs(os.path.join(self.dir, 'zip', '2024'))
        with open(os.path.join(self.dir, fetch.zip_relpath(rec)), 'wb') as fh:
            fh.write(b'PK junk')
        client = FakeClient(default=zip_with_title())
        self.run_download([rec], client)
        self.assertEqual((client.requests, rec['status']), (1, 'ok'))

    def test_row_without_link_is_failed_without_any_request(self):
        rec = make_record(url=None)
        client = FakeClient(default=zip_with_title())
        self.run_download([rec], client)
        self.assertEqual((client.requests, rec['status']), (0, 'failed'))

    def test_ok_plus_failed_equals_rows(self):
        recs = [make_record('70000001'), make_record('70000002', url=None),
                make_record('70000003')]
        client = FakeClient(bodies={recs[0]['zip_url']: zip_with_title()})
        self.run_download(recs, client)
        check = fetch.check_download(recs, self.dir)
        self.assertEqual((check['ok'], check['failed'], check['pending']), (1, 2, 0))

    def test_limit_and_stop_after_fails(self):
        recs = [make_record(str(70000000 + i)) for i in range(1, 6)]
        client = FakeClient(default=zip_with_title())
        self.run_download(recs, client, limit=2)
        self.assertEqual(client.requests, 2)
        failing = [make_record(str(70000100 + i)) for i in range(5)]
        stats = self.run_download(failing, FakeClient(fail=True), stop_after_fails=2)
        self.assertEqual((stats['failed'], stats['stopped']), (2, 'site_down'))

    def test_block_is_not_swallowed_and_index_is_saved(self):
        saved = []

        class Blocking(FakeClient):
            def get(self, url, expect='html'):
                raise hse.Blocked('403')
        with self.assertRaises(hse.Blocked):
            self.run_download([make_record()], Blocking(), save=lambda rows: saved.append(1))
        self.assertTrue(saved)


class ExtractTests(TempDirMixin, SimpleTestCase):
    def test_path_outside_the_folder_is_skipped(self):
        """Дефект 5: член с ../ не выходит за папку распаковки."""
        data = make_zip({'../evil.jpg': b'x', 'sub/dir.jpg': b'x', '/abs.jpg': b'x',
                         'C:evil.jpg': b'x', 'script.exe': b'x', 'good-01.jpg': b'ok',
                         'имя.jpg': b'x'})
        zpath = os.path.join(self.dir, 'a.zip')
        with open(zpath, 'wb') as fh:
            fh.write(data)
        dest = os.path.join(self.dir, 'out', 'inner')
        result = fetch.extract_safe(zpath, dest, log=no_log)
        # Безопасное «странное» имя — под нейтральным; опасные пути — пропуск.
        self.assertEqual(sorted(os.listdir(dest)), ['f001.jpg', 'good-01.jpg'])
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'out', 'evil.jpg')))
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'evil.jpg')))
        self.assertEqual((result['files'], result['renamed'], len(result['skipped'])), (2, 1, 5))

    def test_skip_log_has_reasons_not_names(self):
        messages = []
        zpath = os.path.join(self.dir, 'a.zip')
        with open(zpath, 'wb') as fh:
            fh.write(make_zip({'Пупкинсон.jpg': b'x'}))
        fetch.extract_safe(zpath, os.path.join(self.dir, 'o'), log=messages.append)
        self.assertEqual(len(messages), 1)
        self.assertNotIn('Пупкинсон', messages[0])
        self.assertEqual(os.listdir(os.path.join(self.dir, 'o')), ['f001.jpg'])

    def test_interrupted_extraction_is_completed_on_resume(self):
        rec = make_record()
        client = FakeClient(default=zip_with_title())
        fetch.download_all([rec], self.dir, client, log=no_log)
        sdir = os.path.join(self.dir, fetch.scan_relpath(rec))
        os.remove(os.path.join(sdir, 'mosh-econ-01-0002.jpg'))
        rec.pop('analysis_version')
        fetch.download_all([rec], self.dir, client, log=no_log)
        self.assertEqual(len(os.listdir(sdir)), 2)
        self.assertEqual(client.requests, 1)


# ------------------------------------------------------------------ сканы

class ScansTests(TempDirMixin, SimpleTestCase):
    def folder(self, files):
        for name, data in files.items():
            with open(os.path.join(self.dir, name), 'wb') as fh:
                fh.write(data)
        return self.dir

    def test_two_variants_the_checked_one_is_chosen(self):
        """2024: в zip чистый и проверенный комплект — берём тот, где красные чернила."""
        d = self.folder({
            '1-a.jpg': jpeg(page_image()), '2-a.jpg': jpeg(page_image(work=True)),
            '3-a.jpg': jpeg(page_image(work=True)),
            '4-b.jpg': jpeg(page_image(red=True)), '5-b.jpg': jpeg(page_image(work=True)),
            '6-b.jpg': jpeg(page_image(work=True))})
        info = scans.analyze(d)
        self.assertEqual((info['first_page'], info['variants']), ('4-b.jpg', 2))
        self.assertGreater(info['band_red_pct'], 0.05)

    def test_jpg_has_priority_over_pdf_and_pdf_stickers_are_reported(self):
        d = self.folder({'t-01.jpg': jpeg(page_image(red=True)),
                         't-02.jpg': jpeg(page_image(work=True)),
                         'w.pdf': fake_pdf_bytes(yellow=True)})
        info = scans.analyze(d)
        self.assertEqual((info['source_kind'], info['first_page']), ('jpg', 't-01.jpg'))
        self.assertFalse(info['has_stickers'])
        self.assertGreater(info['pdf_stickers_pct'], scans.STICKER_PCT)
        self.assertEqual(scans.count_pages(d), 2)

    def test_stickers_in_the_table_are_found(self):
        d = self.folder({'w.pdf': fake_pdf_bytes(yellow=True)})
        info = scans.analyze(d)
        self.assertEqual(info['source_kind'], 'pdf')
        self.assertTrue(info['has_stickers'])
        self.assertGreaterEqual(info['band_stickers_pct'], scans.HIDDEN_BAND_PCT)

    def test_clean_page_has_no_stickers(self):
        d = self.folder({'w.pdf': fake_pdf_bytes(red=True)})
        info = scans.analyze(d)
        self.assertFalse(info['has_stickers'])
        self.assertEqual(info['band_stickers_pct'], 0.0)

    def test_pdf_with_a_cover_first_uses_the_next_page(self):
        """Обложка с ФИО (2021) никогда не становится «первой страницей»."""
        d = self.folder({'w.pdf': fake_pdf_bytes(specs=[{'cover': True}, {'red': True},
                                                        {'work': True}])})
        info = scans.analyze(d)
        self.assertEqual((info['first_page'], info['first_page_index'], info['cover_skipped']),
                         ('w.pdf', 1, 1))
        self.assertGreater(info['band_red_pct'], 0.05)

    def test_only_covers_means_no_safe_page(self):
        """Обложка без настоящего титула следом: для 2021 ловит зона ФИО."""
        d = self.folder({'w.pdf': fake_pdf_bytes(specs=[{'cover': True}, {'cover': True},
                                                        {'cover': True}, {'work': True}])})
        info = scans.analyze(d, 2021)
        self.assertIsNone(info['first_page'])
        self.assertEqual(info['cover_skipped'], 3)

    def test_jpg_cover_is_never_chosen(self):
        d = self.folder({'1.jpg': jpeg(page_image(cover=True)),
                         '2.jpg': jpeg(page_image(red=True)),
                         '3.jpg': jpeg(page_image(work=True))})
        info = scans.analyze(d)
        self.assertEqual((info['first_page'], info['cover_skipped']), ('2.jpg', 1))
        d2 = os.path.join(self.dir, 'only_cover')
        os.makedirs(d2)
        with open(os.path.join(d2, 'a.jpg'), 'wb') as fh:
            fh.write(jpeg(page_image(cover=True)))
        self.assertIsNone(scans.analyze(d2, 2021)['first_page'])

    def test_crop_refuses_a_cover_even_if_it_was_chosen_by_hand(self):
        """Дефект 10: вырез обложки с ФИО не создаётся."""
        d = self.folder({'c.jpg': jpeg(page_image(cover=True)),
                         'p.pdf': fake_pdf_bytes(specs=[{'cover': True}])})
        with self.assertRaises(scans.UnsafePage):
            scans.first_page_image(d, 'c.jpg', year=2021)
        with self.assertRaises(scans.UnsafePage):
            scans.first_page_image(d, 'p.pdf', page=0, year=2021)

    def test_cover_in_front_of_a_title_is_caught_by_the_shared_header(self):
        """Правило 1 работает для любого года: шапка обложки = шапка следующей страницы."""
        d = self.folder({'w.pdf': fake_pdf_bytes(specs=[{'cover': True}, {'red': True},
                                                        {'work': True}])})
        info = scans.analyze(d, 2023)
        self.assertEqual((info['first_page_index'], info['cover_skipped']), (1, 1))
        d2 = os.path.join(self.dir, 'jpg')
        os.makedirs(d2)
        for name, spec in (('1.jpg', {'cover': True}), ('2.jpg', {'red': True}),
                           ('3.jpg', {'work': True})):
            with open(os.path.join(d2, name), 'wb') as fh:
                fh.write(jpeg(page_image(**spec)))
        with self.assertRaises(scans.UnsafePage):
            scans.first_page_image(d2, '1.jpg', year=2023)

    def test_cover_zone_is_clean_on_a_real_title_and_dirty_on_a_cover(self):
        self.assertLess(scans.cover_ink_pct(page_image(red=True)), scans.COVER_INK_PCT)
        self.assertGreater(scans.cover_ink_pct(page_image(cover=True)), scans.COVER_INK_PCT)

    def test_shield_passes_a_table_and_holds_everything_else(self):
        """Щит: рамка и шапка таблицы — да; обложка, пустая страница, клетчатая бумага — нет."""
        ok, why, m = scans.table_shield(scans.crop_band(page_image(red=True)))
        self.assertEqual((ok, why), (True, ''), m)
        for spec in ({'cover': True}, {'notable': True}, {'grid': True}, {'work': True}):
            ok, why, m = scans.table_shield(scans.crop_band(page_image(**spec)))
            self.assertFalse(ok, (spec, m))

    def test_band_cuts_off_header_with_participant_number(self):
        from PIL import Image

        img = Image.new('RGB', (1000, 1000), 'white')
        self.assertEqual(scans.crop_band(img).size, (960, 410))
        self.assertGreaterEqual(scans.BAND[1], 0.5)   # номер участника выше полосы


# ------------------------------------------------------------------ баллы

def reply(tasks, total=''):
    return {'tasks': [{'n': i, 'label': str(i), 'score': s}
                      for i, s in enumerate(tasks, 1)], 'total': total, 'readable': True}


class VerdictTests(SimpleTestCase):
    def test_sum_must_match_the_total_cell(self):
        """Дефект 6: сумма задач сверяется с клеткой «Сумма» того же листа."""
        status, d = scores.verdict(reply(['40', '35', '40', '6'], '121'), 130)
        self.assertEqual((status, d['verified_by'], d['appeal_delta']), ('ok', 'total_cell', 9))
        status, d = scores.verdict(reply(['40', '35', '40', '6'], '120'), 130)
        self.assertEqual((status, d['reason']), ('review', 'sum_mismatch'))

    def test_empty_total_cell_and_sum_equals_listed_is_ok_by_listed(self):
        status, d = scores.verdict(reply(['8', '0', '20', '46'], ''), 74)
        self.assertEqual((status, d['verified_by'], d['appeal_delta']), ('ok', 'listed', 0))

    def test_empty_total_cell_and_other_sum_is_not_verified(self):
        """Сверить не с чем: разницу пишем, но «ok» не ставим."""
        status, d = scores.verdict(reply(['35', '15', '31', '32'], None), 125)
        self.assertEqual((status, d['reason'], d['appeal_delta']), ('review', 'no_total_cell', 12))

    def test_negative_appeal_delta_goes_to_review(self):
        """Дефект 9: балл в таблице меньше балла на скане — не ok."""
        status, d = scores.verdict(reply(['40', '35'], '75'), 70)
        self.assertEqual((status, d['reason'], d['appeal_delta']),
                         ('review', 'appeal_negative', -5))
        # Половинка в допуске — не отрицательная разница.
        status, _ = scores.verdict(reply(['40', '35'], '75'), 74.5)
        self.assertEqual(status, 'ok')

    def test_missing_task_is_partial_with_found_list(self):
        """2022: в таблице нет задачи 4 — partial, найденные перечислены."""
        status, d = scores.verdict(reply(['42', '29', '19', '']), 102)
        self.assertEqual((status, d['missing'], d['tasks_sum']), ('partial', [4], 90))
        self.assertEqual([t['score'] for t in d['tasks']], [42, 29, 19, None])

    def test_dash_is_zero_but_null_is_unreadable_and_blank_is_missing(self):
        status, d = scores.verdict(reply(['8', '—', '20', '46'], '74'), 80)
        self.assertEqual(status, 'ok')
        status, d = scores.verdict(reply(['8', None, '20', '46']), 74)
        self.assertEqual((status, d['reason']), ('review', 'task_unreadable'))
        status, d = scores.verdict(reply(['', '', '']), 74)
        self.assertEqual((status, d['reason']), ('review', 'empty_table'))

    def test_merged_1_5_is_kept_as_is(self):
        data = {'tasks': [{'n': 1, 'label': '1-5', 'score': '16'},
                          {'n': 2, 'label': '6', 'score': '1'},
                          {'n': 3, 'label': '7', 'score': '5'},
                          {'n': 4, 'label': '8', 'score': '25'}], 'total': '47', 'readable': True}
        status, d = scores.verdict(data, 65)
        self.assertEqual((status, d['merged_1_5'], d['appeal_delta']), ('ok', True, 18))
        self.assertEqual(d['tasks'][0]['label'], '1-5')

    def test_format_and_unreadable_go_to_review(self):
        self.assertEqual(scores.verdict({'_format_error': True}, 5)[1]['reason'], 'format')
        self.assertEqual(scores.verdict({'tasks': [], 'readable': True}, 5)[1]['reason'], 'no_tasks')
        self.assertEqual(scores.verdict({'tasks': [{'n': 1, 'score': '1'}], 'readable': False},
                                        5)[1]['reason'], 'unreadable')

    def test_tolerant_parse(self):
        fenced = '```json\n{"tasks": [], "total": "1", "readable": true}\n```'
        self.assertEqual(scores.tolerant_parse(fenced)['total'], '1')
        self.assertTrue(scores.tolerant_parse('чепуха')['_format_error'])


def rows_reply(*rows, total='', form='tasks4'):
    return {'form': form, 'rows': [{'label': 'Баллы', 'cells': list(r)} for r in rows],
            'total': total, 'readable': True}


class Verdict2021Tests(SimpleTestCase):
    def test_last_non_empty_row_wins_and_sum_must_equal_listed(self):
        status, d = scores.verdict_rows(
            rows_reply(['7', '9', '25', '25'], ['7', '9.5', '25', '25']), 66.5)
        self.assertEqual((status, d['verified_by'], d['appeal_delta']), ('ok', 'listed', 0))
        self.assertEqual([t['score'] for t in d['tasks']], [7, 9.5, 25, 25])
        self.assertEqual(d['tasks'][1]['rows'], [9, 9.5])

    def test_closed_cell_falls_back_to_the_other_row(self):
        status, d = scores.verdict_rows(rows_reply(['7', None, '25'], ['', '9', None]), 41)
        self.assertEqual((status, [t['score'] for t in d['tasks']]), ('ok', [7, 9, 25]))

    def test_part_closed_is_partial_with_found_values_and_nulls(self):
        status, d = scores.verdict_rows(
            rows_reply(['7', None, '25', None], ['', None, '', None]), 80)
        self.assertEqual((status, d['reason'], d['closed']), ('partial', 'tasks_closed', [2, 4]))
        self.assertEqual([t['score'] for t in d['tasks']], [7, None, 25, None])
        self.assertEqual((d['tasks_sum'], d['sum_matches_listed']), (32, False))

    def test_all_closed_is_hidden_by_stickers(self):
        status, d = scores.verdict_rows(rows_reply([None] * 4, [None] * 4), 80)
        self.assertEqual((status, d['reason']), ('hidden_by_stickers', 'all_closed'))

    def test_nothing_written_is_review_not_hidden(self):
        status, d = scores.verdict_rows(rows_reply(['', '', '', '']), 80)
        self.assertEqual((status, d['reason']), ('review', 'empty_table'))

    def test_blank_cells_are_missing_not_zero(self):
        """Бланк «Задание №1…№5»: одна строка «Балл», пустое — не вписано."""
        status, d = scores.verdict_rows(rows_reply(['5', '', '22', '', ''], form='tasks5'), 27)
        self.assertEqual((status, d['blank'], d['sum_matches_listed']),
                         ('partial', [2, 4, 5], True))
        self.assertEqual(len(d['tasks']), 5)

    def test_all_found_but_sum_differs_is_review(self):
        status, d = scores.verdict_rows(rows_reply(['5', '6', '7', '8']), 30)
        self.assertEqual((status, d['reason'], d['appeal_delta']), ('review', 'sum_mismatch', 4))

    def test_total_cell_that_disagrees_is_review(self):
        status, d = scores.verdict_rows(rows_reply(['5', '6', '7', '8'], total='30'), 26)
        self.assertEqual((status, d['reason']), ('review', 'sum_mismatch'))

    def test_extra_sum_column_is_not_a_task(self):
        """Модель положила «Сумма» пятой ячейкой в бланк из четырёх задач — срезается."""
        status, d = scores.verdict_rows(rows_reply(['7', '9', '25', '25', ''], ['', '', '', '', '']), 66)
        self.assertEqual((status, len(d['tasks'])), ('ok', 4))
        status, d = scores.verdict_rows(rows_reply([None] * 5), 66)
        self.assertEqual((status, len(d['tasks'])), ('hidden_by_stickers', 4))

    def test_format_and_no_rows(self):
        self.assertEqual(scores.verdict_rows({'_format_error': True}, 5)[1]['reason'], 'format')
        self.assertEqual(
            scores.verdict_rows({'rows': [], 'readable': True}, 5)[1]['reason'], 'no_tasks')


GOOD = json.dumps(reply(['40', '34'], '74'))


@mock.patch.dict(os.environ, {'MOSH_WORKS_WORKERS': '1'})
class ScoresCommandTests(TempDirMixin, TestCase):
    def prepare(self, n=3, **page):
        recs = [make_record(str(70000100 + i), total=81) for i in range(n)]
        client = FakeClient(default=zip_with_title(**page))
        fetch.download_all(recs, self.dir, client, log=no_log, sleep=lambda s: None)
        write_jsonl(os.path.join(self.dir, 'index.jsonl'), recs)
        return recs

    def scores(self, *args):
        call_command('mosh_works', 'scores', '--dir', self.dir, *args, stdout=io.StringIO())
        return {r['work_id']: r for r in read_jsonl(os.path.join(self.dir, 'scores.jsonl'))}

    def test_without_yes_provider_is_never_called(self):
        """Дефект 7: без --yes настоящий поставщик не вызывается вовсе."""
        self.prepare()
        with mock.patch('problems.ai.providers.GLMProvider.complete',
                        side_effect=AssertionError('вызов модели без --yes')) as complete, \
                mock.patch('problems.ai.providers.GLMProvider.is_available', return_value=True):
            call_command('mosh_works', 'scores', '--dir', self.dir, stdout=io.StringIO())
        complete.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'scores.jsonl')))
        self.assertEqual(len(os.listdir(os.path.join(self.dir, 'crops', '2024'))), 3)

    @override_settings(MOSH_WORKS_PROVIDER='fake', AI_FAKE_REPLY=GOOD)
    def test_yes_reads_and_checks_the_sum(self):
        self.prepare(n=2, red=True)
        rows = self.scores('--yes')
        for row in rows.values():
            self.assertEqual((row['scores_status'], row['verified_by'], row['appeal_delta']),
                             ('ok', 'total_cell', 7))
            self.assertEqual((row['source'], row['runs']), ('model', 1))
            self.assertEqual([t['score'] for t in row['tasks']], [40, 34])
        self.assertEqual(len(os.listdir(os.path.join(self.dir, 'crops', '2024'))), 2)
        # index.jsonl баллов не содержит: его пишет только download.
        self.assertTrue(all('scores_status' not in r
                            for r in read_jsonl(os.path.join(self.dir, 'index.jsonl'))))

    @override_settings(MOSH_WORKS_PROVIDER='fake', AI_FAKE_REPLY=GOOD)
    def test_stickers_hide_the_scores_without_model_and_money(self):
        self.prepare(n=2, yellow=True)
        with mock.patch('problems.ai.core.run',
                        side_effect=AssertionError('закрашенное ушло в модель')):
            rows = self.scores('--yes')
        self.assertEqual({r['scores_status'] for r in rows.values()}, {'hidden_by_stickers'})
        with open(os.path.join(self.dir, 'review.csv'), encoding='utf-8-sig') as fh:
            self.assertEqual(len(fh.readlines()), 1)   # только заголовок
        self.assertEqual(sum(r['cost'] for r in rows.values()), 0)

    @override_settings(MOSH_WORKS_PROVIDER='fake', AI_FAKE_REPLY=GOOD)
    def test_2021_goes_to_the_model_only_when_asked(self):
        recs = [make_record('70000500', year=2021)]
        fetch.download_all(recs, self.dir, FakeClient(default=zip_with_title(red=True)),
                           log=no_log)
        write_jsonl(os.path.join(self.dir, 'index.jsonl'), recs)
        self.assertEqual(self.scores('--yes'), {})
        self.assertEqual(list(self.scores('--yes', '--years', '2021')), ['70000500'])

    @override_settings(MOSH_WORKS_PROVIDER='fake', AI_FAKE_REPLY=GOOD,
                       AI_PRICES={'glm-5.3-flash': (1000.0, 1000.0)})
    def test_max_usd_stops_new_calls(self):
        """Дефект 8: потолок --max-usd обрывает прогон — новых вызовов нет."""
        self.prepare(n=5, red=True)
        out = io.StringIO()
        call_command('mosh_works', 'scores', '--dir', self.dir, '--yes', '--max-usd', '0.01',
                     stdout=out)
        self.assertEqual(len(read_jsonl(os.path.join(self.dir, 'scores.jsonl'))), 1)
        self.assertIn('ОСТАНОВЛЕНО', out.getvalue())
        # Потолок общий на все прогоны: второй запуск не делает ни одного вызова.
        call_command('mosh_works', 'scores', '--dir', self.dir, '--yes', '--max-usd', '0.01',
                     stdout=io.StringIO())
        self.assertEqual(len(read_jsonl(os.path.join(self.dir, 'scores.jsonl'))), 1)

    @override_settings(MOSH_WORKS_PROVIDER='fake')
    def test_retry_review_rotates_and_accepts_a_good_read(self):
        self.prepare(n=2, red=True)

        def answer(system, user_text):
            if '(вырез повёрнут' in user_text:
                return json.loads(GOOD)
            return {'tasks': [{'n': 1, 'score': None}], 'readable': True}
        with override_settings(AI_FAKE_REPLY=answer):
            first = self.scores('--yes')
            self.assertEqual({r['reason'] for r in first.values()}, {'task_unreadable'})
            second = self.scores('--yes', '--retry-review')
        self.assertEqual({r['scores_status'] for r in second.values()}, {'ok'})
        # Один прогон, затем тот же вырез с подсказкой и повёрнутый: три вызова.
        self.assertTrue(all(r['retried'] and r['runs'] == 3 for r in second.values()))
        rot = [f for f in os.listdir(os.path.join(self.dir, 'crops', '2024'))
               if f.endswith('_rot180.png')]
        self.assertEqual(len(rot), 2)

    def prepare_years(self, per_year=4, years=(2022, 2023, 2024, 2025), **page):
        recs = []
        for y in years:
            for i in range(per_year):
                recs.append(make_record(str(70000000 + y * 10 + i), year=y, total=81))
        client = FakeClient(default=zip_with_title(**page))
        fetch.download_all(recs, self.dir, client, log=no_log, sleep=lambda s: None)
        write_jsonl(os.path.join(self.dir, 'index.jsonl'), recs)
        return recs

    @override_settings(MOSH_WORKS_PROVIDER='fake', AI_FAKE_REPLY=GOOD)
    def test_crop_without_a_table_frame_is_held_and_never_sent(self):
        """Дефект 11: вырез без рамки таблицы не уходит в модель (held_shield)."""
        recs = [make_record('70000800', year=2023), make_record('70000801', year=2023)]
        bodies = {recs[0]['zip_url']: zip_with_title(notable=True),
                  recs[1]['zip_url']: zip_with_title(red=True)}
        fetch.download_all(recs, self.dir, FakeClient(bodies=bodies), log=no_log)
        write_jsonl(os.path.join(self.dir, 'index.jsonl'), recs)
        sent = []
        real_run = __import__('problems.ai.core', fromlist=['run']).run

        def spy(*args, **kwargs):
            sent.append(kwargs.get('images'))
            return real_run(*args, **kwargs)
        with mock.patch('problems.ai.core.run', side_effect=spy):
            rows = self.scores('--yes')
        self.assertEqual(rows['70000800']['scores_status'], 'held_shield')
        self.assertEqual(rows['70000800']['reason'], 'shield_no_frame')
        self.assertEqual(rows['70000801']['scores_status'], 'ok')
        self.assertEqual(len(sent), 1)          # в модель ушёл один вырез, не два
        self.assertTrue(os.path.exists(os.path.join(self.dir, 'held', '2023', '70000800.png')))
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'crops', '2023', '70000800.png')))
        with open(os.path.join(self.dir, 'review.csv'), encoding='utf-8-sig') as fh:
            self.assertIn('70000800', fh.read())
        # Владелец посмотрел вырез и разрешил: с --release он идёт в модель.
        rows = self.scores('--yes', '--release', '70000800')
        self.assertEqual(rows['70000800']['scores_status'], 'ok')

    @override_settings(MOSH_WORKS_PROVIDER='fake', AI_FAKE_REPLY=json.dumps(
        {'form': 'tasks4', 'rows': [{'label': 'Баллы', 'cells': ['40', '34']}],
         'total': '', 'readable': True}))
    def test_2021_cover_never_goes_to_the_model(self):
        """Дефект 10: обложка 2021 с ФИО не идёт в модель — уходит вырез следующей страницы."""
        from PIL import Image

        rec = make_record('70000900', year=2021, total=74)
        pdf = fake_pdf_bytes(specs=[{'cover': True}, {'red': True}, {'work': True}])
        fetch.download_all([rec], self.dir, FakeClient(default=make_zip({'w.pdf': pdf})),
                           log=no_log)
        self.assertEqual(rec['first_page_index'], 1)
        write_jsonl(os.path.join(self.dir, 'index.jsonl'), [rec])
        sent = []
        real_run = __import__('problems.ai.core', fromlist=['run']).run

        def spy(*args, **kwargs):
            sent.append(kwargs['images'][0][1])
            return real_run(*args, **kwargs)
        with mock.patch('problems.ai.core.run', side_effect=spy):
            rows = self.scores('--yes', '--years', '2021')
        self.assertEqual(len(sent), 1)
        picture = Image.open(io.BytesIO(sent[0])).convert('RGB')
        self.assertGreater(scans.red_pct(picture), 0.05)       # красные цифры титула
        self.assertLess(scans.cover_ink_pct(picture), 100)
        self.assertEqual(rows['70000900']['scores_status'], 'ok')

    @override_settings(MOSH_WORKS_PROVIDER='fake')
    def test_double_read_makes_ok_only_when_both_reads_agree_and_appeal_is_plausible(self):
        """Дефект 12: double_read не ставит ok без совпадения чтений."""
        recs = [make_record(str(70001000 + i), year=2024, total=85) for i in range(2)]
        fetch.download_all(recs, self.dir, FakeClient(default=zip_with_title(red=True)),
                           log=no_log)
        write_jsonl(os.path.join(self.dir, 'index.jsonl'), recs)
        first = reply(['20', '20', '20', '20'], '')       # сумма 80, «Сумма» пуста, в таблице 85

        def answer(system, user_text):
            if scores.SECOND_HINT not in user_text:
                return first
            # Второе чтение — у каждой работы свой ответ: у первой то же, у второй иное.
            return first if '70001000' in user_text else reply(['20', '20', '20', '21'], '')
        calls = []
        real_run = __import__('problems.ai.core', fromlist=['run']).run

        def spy(*args, **kwargs):
            from PIL import Image
            calls.append((kwargs.get('model'), user_of(args),
                          Image.open(io.BytesIO(kwargs['images'][0][1])).size))
            return real_run(*args, **kwargs)

        def user_of(args):
            return args[1]
        with override_settings(AI_FAKE_REPLY=answer), \
                mock.patch('problems.ai.core.run', side_effect=spy):
            rows = self.scores('--yes')
        # Второе чтение — другая модель, НЕ повёрнутый вырез, увеличенный вдвое.
        firsts = [c for c in calls if scores.SECOND_HINT not in c[1]]
        seconds = [c for c in calls if scores.SECOND_HINT in c[1]]
        self.assertEqual({c[0] for c in firsts}, {scores.MODEL})
        self.assertEqual({c[0] for c in seconds}, {scores.MODEL_SECOND})
        self.assertTrue(all('повёрнут' not in c[1] for c in seconds))
        self.assertEqual(seconds[0][2], (firsts[0][2][0] * 2, firsts[0][2][1] * 2))
        good, bad = rows['70001000'], rows['70001001']
        self.assertEqual((good['scores_status'], good['verified_by'], good['appeal_delta']),
                         ('ok', 'double_read', 5))
        self.assertEqual(good['runs'], 2)
        self.assertEqual((bad['scores_status'], bad['reason']), ('review', 'double_read_disagree'))

    def test_double_read_rejects_implausible_appeals_and_merged_form(self):
        first = {'tasks': [{'n': 1, 'score': 20}, {'n': 2, 'score': 20}], 'tasks_sum': 40}
        same = {'tasks': [{'n': 1, 'score': 20}, {'n': 2, 'score': 20}]}
        self.assertEqual(scores.double_read(first, same, 44)[0], 'ok')
        self.assertEqual(scores.double_read(first, same, 40)[0], 'ok')      # delta = 0 допустима
        for listed, reason in ((39, 'double_read_delta_negative'),
                               (50, 'double_read_delta_large')):
            status, d = scores.double_read(first, same, listed)
            self.assertEqual((status, d['reason']), ('review', reason))

    @override_settings(MOSH_WORKS_PROVIDER='fake')
    def test_merged_1_5_without_a_match_is_review_without_second_read(self):
        rec = make_record('70001100', year=2025, total=65)
        fetch.download_all([rec], self.dir, FakeClient(default=zip_with_title(red=True)),
                           log=no_log)
        write_jsonl(os.path.join(self.dir, 'index.jsonl'), [rec])
        merged = {'tasks': [{'n': 1, 'label': '1-5', 'score': '16'},
                            {'n': 2, 'label': '6', 'score': '1'},
                            {'n': 3, 'label': '7', 'score': '5'},
                            {'n': 4, 'label': '8', 'score': '25'}], 'total': '', 'readable': True}
        with override_settings(AI_FAKE_REPLY=json.dumps(merged)):
            rows = self.scores('--yes')
        self.assertEqual((rows['70001100']['scores_status'], rows['70001100']['reason'],
                          rows['70001100']['runs']), ('review', 'merged_unverified', 1))

    @override_settings(MOSH_WORKS_PROVIDER='fake', AI_FAKE_REPLY=GOOD)
    def test_upside_down_scan_is_flipped_and_then_passes_the_shield(self):
        rec = make_record('70001200', year=2023, total=81)
        upside = make_zip({'mosh-econ-01-0001.jpg': jpeg(page_image(red=True).rotate(180)),
                           'mosh-econ-01-0002.jpg': jpeg(page_image(work=True))})
        fetch.download_all([rec], self.dir, FakeClient(default=upside), log=no_log)
        write_jsonl(os.path.join(self.dir, 'index.jsonl'), [rec])
        rows = self.scores('--yes')
        self.assertEqual(rows['70001200']['scores_status'], 'ok')
        self.assertTrue(os.path.exists(os.path.join(self.dir, 'crops', '2023', '70001200.png')))
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'held', '2023', '70001200.png')))

    @override_settings(MOSH_WORKS_PROVIDER='fake', AI_FAKE_REPLY=GOOD)
    def test_database_error_from_core_run_is_one_failed_work_not_a_crash(self):
        from django.db import OperationalError

        self.prepare(n=2, red=True)
        with mock.patch('problems.ai.core.run', side_effect=OperationalError('no such table')):
            rows = self.scores('--yes')
        self.assertEqual({r['reason'] for r in rows.values()}, {'ai_error'})
        self.assertEqual(len(rows), 2)

    @override_settings(MOSH_WORKS_PROVIDER='fake', AI_FAKE_REPLY=GOOD)
    def test_limit_is_stratified_by_year(self):
        self.prepare_years(per_year=4, red=True)
        rows = self.scores('--yes', '--limit', '8')
        by_year = {}
        for r in rows.values():
            by_year[r['year']] = by_year.get(r['year'], 0) + 1
        self.assertEqual(by_year, {2022: 2, 2023: 2, 2024: 2, 2025: 2})

    @override_settings(MOSH_WORKS_PROVIDER='fake')
    def test_2021_reads_rows_and_marks_partial_and_hidden(self):
        recs = [make_record(str(70000600 + i), year=2021, total=66) for i in range(3)]
        fetch.download_all(recs, self.dir, FakeClient(default=zip_with_title(red=True)),
                           log=no_log)
        write_jsonl(os.path.join(self.dir, 'index.jsonl'), recs)
        replies = iter([rows_reply(['7', '9', '25', '25'], ['7', '9', '25', '25']),
                        rows_reply(['7', None, '25', None]),
                        rows_reply([None] * 4, [None] * 4)])
        seen = []

        def answer(system, user_text):
            seen.append(system)
            return next(replies)
        with override_settings(AI_FAKE_REPLY=answer):
            rows = self.scores('--yes', '--years', '2021')
        self.assertEqual(sorted(r['scores_status'] for r in rows.values()),
                         ['hidden_by_stickers', 'ok', 'partial'])
        self.assertTrue(all('tasks4' in str(s) for s in seen))
        partial = [r for r in rows.values() if r['scores_status'] == 'partial'][0]
        self.assertEqual([t['score'] for t in partial['tasks']], [7, None, 25, None])
        self.assertEqual(partial['closed'], [2, 4])

    @override_settings(MOSH_WORKS_PROVIDER='fake', AI_FAKE_REPLY=GOOD)
    def test_2021_closed_almost_everywhere_never_goes_to_the_model(self):
        recs = [make_record('70000700', year=2021, total=66)]
        fetch.download_all(recs, self.dir, FakeClient(default=zip_with_title(red=True)),
                           log=no_log)
        recs[0]['band_stickers_pct'] = scores.HIDDEN_ALL_BAND_PCT + 1
        write_jsonl(os.path.join(self.dir, 'index.jsonl'), recs)
        with mock.patch('problems.ai.core.run', side_effect=AssertionError('в модель')):
            rows = self.scores('--yes', '--years', '2021')
        self.assertEqual(rows['70000700']['scores_status'], 'hidden_by_stickers')

    def test_data_dir_inside_repo_is_refused(self):
        from django.core.management.base import CommandError

        repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with self.assertRaises(CommandError):
            call_command('mosh_works', 'report', '--dir', os.path.join(repo, 'tmp_mosh'),
                         stdout=io.StringIO())
