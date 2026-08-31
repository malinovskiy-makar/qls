# -*- coding: utf-8 -*-
"""Batch API OpenAI (Б3): резка по байтам, манифест, возобновление, разбор.

Ни один тест здесь не обращается к настоящему OpenAI — `submit_pending` и
`refresh_statuses` принимают клиента параметром, и тесты подсовывают
подставной объект. Реальный вызов Batch API этот модуль ещё ни разу не
делал (см. предупреждение в докстринге `problems/ai/batch.py`).
"""
import json
import os
import tempfile

from django.test import SimpleTestCase

from problems.ai import batch


def _request(custom_id, filler=''):
    return batch.build_request(
        custom_id=custom_id, model='gpt-5.6-luna',
        system_blocks=['ЯДРО' + filler, 'ПРОФИЛЬ'],
        user_text='текст задачи', schema={'type': 'object'},
        max_tokens=500)


class BuildRequestTests(SimpleTestCase):

    def test_custom_id_и_эндпойнт_на_месте(self):
        request = _request('42:1')
        self.assertEqual(request['custom_id'], '42:1')
        self.assertEqual(request['method'], 'POST')
        self.assertEqual(request['url'], batch.ENDPOINT)

    def test_ядро_и_профиль_склеены_как_instructions(self):
        request = batch.build_request(
            'id', 'gpt-5.6-terra', ['ЯДРО', 'ПРОФИЛЬ'], 'текст',
            {'type': 'object'}, 500)
        self.assertEqual(request['body']['instructions'], 'ЯДРО\n\nПРОФИЛЬ')

    def test_effort_не_передан_если_не_задан(self):
        request = _request('id')
        self.assertNotIn('reasoning', request['body'])

    def test_effort_передан_если_задан(self):
        request = batch.build_request(
            'id', 'gpt-5.6-terra', ['ЯДРО'], 'текст', {'type': 'object'},
            500, reasoning_effort='low')
        self.assertEqual(request['body']['reasoning'], {'effort': 'low'})

    def test_схема_строгая(self):
        schema = {'type': 'object', 'properties': {}}
        request = batch.build_request(
            'id', 'gpt-5.6-luna', ['ЯДРО'], 'текст', schema, 500)
        text_format = request['body']['text']['format']
        self.assertTrue(text_format['strict'])
        self.assertEqual(text_format['schema'], schema)


class SplitIntoFilesTests(SimpleTestCase):

    def test_режет_по_числу_строк(self):
        requests = [_request(str(i)) for i in range(10)]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = batch.split_into_files(
                requests, tmp, max_bytes=10 ** 9, max_lines=3)
        self.assertEqual([len(e['custom_ids']) for e in manifest],
                         [3, 3, 3, 1])
        self.assertEqual(
            [i for e in manifest for i in e['custom_ids']],
            [str(i) for i in range(10)])

    def test_режет_по_байтам_а_не_по_строкам(self):
        """⚠️ Ядро повторяется в каждой строке — резать надо по байтам."""
        big_filler = 'x' * 1000
        requests = [_request(str(i), filler=big_filler) for i in range(5)]
        one_line_bytes = batch._line_bytes(requests[0])
        with tempfile.TemporaryDirectory() as tmp:
            manifest = batch.split_into_files(
                requests, tmp,
                max_bytes=int(one_line_bytes * 2.5), max_lines=10 ** 9)
        # Ёмкость файла — 2 строки максимум (2.5x), 5 строк -> минимум 3 файла.
        self.assertEqual(len(manifest), 3)
        for entry in manifest:
            self.assertLessEqual(len(entry['custom_ids']), 2)

    def test_каждый_файл_реально_укладывается_в_лимит(self):
        big_filler = 'x' * 1000
        requests = [_request(str(i), filler=big_filler) for i in range(9)]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = batch.split_into_files(
                requests, tmp, max_bytes=3000, max_lines=10 ** 9)
            for entry in manifest:
                actual = os.path.getsize(entry['path'])
                self.assertLessEqual(actual, 3000)
                self.assertEqual(actual, entry['byte_count'])

    def test_одна_строка_длиннее_лимита_кидает_ошибку(self):
        requests = [_request('0', filler='x' * 10000)]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                batch.split_into_files(requests, tmp, max_bytes=100,
                                       max_lines=10 ** 9)

    def test_файлы_реально_читаются_как_jsonl(self):
        requests = [_request(str(i)) for i in range(4)]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = batch.split_into_files(
                requests, tmp, max_bytes=10 ** 9, max_lines=2)
            for entry in manifest:
                with open(entry['path'], encoding='utf-8') as fh:
                    lines = [json.loads(line) for line in fh]
                self.assertEqual(len(lines), entry['line_count'])
                self.assertEqual([row['custom_id'] for row in lines],
                                 entry['custom_ids'])

    def test_пустой_поток_не_создаёт_файлов(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = batch.split_into_files([], tmp)
        self.assertEqual(manifest, [])


class ManifestRoundTripTests(SimpleTestCase):

    def test_запись_и_чтение(self):
        manifest = [{'path': 'a.jsonl', 'custom_ids': ['1', '2'],
                     'line_count': 2, 'byte_count': 40}]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'manifest.json')
            batch.save_manifest(manifest, path)
            loaded = batch.load_manifest(path)
        self.assertEqual(loaded, manifest)

    def test_чтение_несуществующего_файла_даёт_пустой_список(self):
        with tempfile.TemporaryDirectory() as tmp:
            loaded = batch.load_manifest(os.path.join(tmp, 'нет-такого.json'))
        self.assertEqual(loaded, [])


class _FakeUploadedFile(object):
    def __init__(self, file_id):
        self.id = file_id


class _FakeBatch(object):
    def __init__(self, batch_id, status='validating', output_file_id=None,
                error_file_id=None):
        self.id = batch_id
        self.status = status
        self.output_file_id = output_file_id
        self.error_file_id = error_file_id


class _FakeFiles(object):
    def __init__(self):
        self.created = []
        self.content_calls = []

    def create(self, file, purpose):
        name = getattr(file, 'name', '?')
        self.created.append(name)
        return _FakeUploadedFile('file-%d' % len(self.created))

    def content(self, file_id):
        self.content_calls.append(file_id)

        class _Resp(object):
            def read(self_inner):
                return ('{"custom_id": "1", "response": {"status_code": 200, '
                       '"body": {"output_text": "{}"}}}\n').encode('utf-8')
        return _Resp()


class _FakeBatches(object):
    def __init__(self, statuses_by_call=None):
        self.created = []
        self._by_id = {}
        self._statuses_by_call = statuses_by_call or {}
        self._call_counts = {}

    def create(self, input_file_id, endpoint, completion_window):
        batch_id = 'batch-%d' % (len(self.created) + 1)
        self.created.append((input_file_id, endpoint, completion_window))
        fake = _FakeBatch(batch_id)
        self._by_id[batch_id] = fake
        return fake

    def retrieve(self, batch_id):
        sequence = self._statuses_by_call.get(batch_id)
        if sequence:
            n = self._call_counts.get(batch_id, 0)
            status = sequence[min(n, len(sequence) - 1)]
            self._call_counts[batch_id] = n + 1
            self._by_id[batch_id].status = status
        return self._by_id[batch_id]


class _FakeClient(object):
    def __init__(self, statuses_by_call=None):
        self.files = _FakeFiles()
        self.batches = _FakeBatches(statuses_by_call)


class SubmitPendingTests(SimpleTestCase):

    def test_отправляет_только_записи_без_batch_id(self):
        client = _FakeClient()
        manifest = [
            {'path': _write_tmp_jsonl(self, 'a'), 'batch_id': 'already-sent'},
            {'path': _write_tmp_jsonl(self, 'b')},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = os.path.join(tmp, 'manifest.json')
            batch.submit_pending(client, manifest, manifest_path)

        self.assertEqual(manifest[0]['batch_id'], 'already-sent')
        self.assertIsNotNone(manifest[1].get('batch_id'))
        self.assertEqual(len(client.files.created), 1)
        self.assertEqual(len(client.batches.created), 1)

    def test_манифест_сохраняется_после_каждой_отправки(self):
        client = _FakeClient()
        manifest = [{'path': _write_tmp_jsonl(self, 'a')},
                    {'path': _write_tmp_jsonl(self, 'b')}]
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = os.path.join(tmp, 'manifest.json')
            batch.submit_pending(client, manifest, manifest_path)
            on_disk = batch.load_manifest(manifest_path)
        self.assertEqual(len(on_disk), 2)
        self.assertTrue(all(e.get('batch_id') for e in on_disk))


class RefreshStatusesTests(SimpleTestCase):

    def test_статус_обновляется_и_пишется_на_диск(self):
        client = _FakeClient(statuses_by_call={'batch-1': ['in_progress',
                                                           'completed']})
        client.batches._by_id['batch-1'] = _FakeBatch(
            'batch-1', status='in_progress', output_file_id='out-1')
        manifest = [{'path': 'a.jsonl', 'batch_id': 'batch-1',
                    'status': 'validating'}]
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = os.path.join(tmp, 'manifest.json')
            batch.save_manifest(manifest, manifest_path)
            batch.refresh_statuses(client, manifest, manifest_path)
            on_disk = batch.load_manifest(manifest_path)
        self.assertEqual(manifest[0]['status'], 'in_progress')
        self.assertEqual(on_disk[0]['status'], 'in_progress')

    def test_записи_без_batch_id_пропускаются(self):
        client = _FakeClient()
        manifest = [{'path': 'a.jsonl'}]
        batch.refresh_statuses(client, manifest, 'unused.json')
        self.assertNotIn('status', manifest[0])


class AllTerminalTests(SimpleTestCase):

    def test_все_терминальные(self):
        manifest = [{'status': 'completed'}, {'status': 'failed'}]
        self.assertTrue(batch.all_terminal(manifest))

    def test_хотя_бы_один_в_процессе(self):
        manifest = [{'status': 'completed'}, {'status': 'in_progress'}]
        self.assertFalse(batch.all_terminal(manifest))


class DownloadResultsTests(SimpleTestCase):

    def test_скачивает_только_завершённые_и_ещё_не_скачанные(self):
        client = _FakeClient()
        manifest = [
            {'path': 'a.jsonl', 'status': 'completed',
             'output_file_id': 'out-1'},
            {'path': 'b.jsonl', 'status': 'in_progress'},
            {'path': 'c.jsonl', 'status': 'completed',
             'result_path': 'already/there.jsonl'},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            downloaded = batch.download_results(client, manifest, tmp)
        self.assertEqual(len(client.files.content_calls), 1)
        self.assertIn('already/there.jsonl', downloaded)
        self.assertEqual(len(downloaded), 2)


class ParseResultsTests(SimpleTestCase):

    def test_разбирает_успешную_строку(self):
        line = json.dumps({
            'custom_id': '10:1',
            'response': {'status_code': 200,
                        'body': {'output_text': '{"topic_primary": "X"}'}},
            'error': None,
        }, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'r.jsonl')
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(line + '\n')
            results = batch.parse_results(path)
        self.assertEqual(results['10:1']['data'], {'topic_primary': 'X'})
        self.assertIsNone(results['10:1']['error'])

    def test_отказ_по_отдельной_строке_не_роняет_остальные(self):
        good = json.dumps({
            'custom_id': '1:1',
            'response': {'status_code': 200,
                        'body': {'output_text': '{"a": 1}'}},
        }, ensure_ascii=False)
        bad_json = '{не json'
        errored = json.dumps({
            'custom_id': '2:1', 'error': {'message': 'rate limited'},
        }, ensure_ascii=False)
        http_error = json.dumps({
            'custom_id': '3:1',
            'response': {'status_code': 500, 'body': {}},
        }, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'r.jsonl')
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join([good, bad_json, errored, http_error]) + '\n')
            results = batch.parse_results(path)

        self.assertEqual(results['1:1']['data'], {'a': 1})
        self.assertEqual(results['2:1']['data'], None)
        self.assertIn('rate limited', results['2:1']['error'])
        self.assertEqual(results['3:1']['data'], None)
        self.assertIn('500', results['3:1']['error'])
        parse_error_keys = [k for k in results if k.startswith('_parse_error_line_')]
        self.assertEqual(len(parse_error_keys), 1)

    def test_ответ_не_json_даёт_ошибку_а_не_падение(self):
        line = json.dumps({
            'custom_id': '1:1',
            'response': {'status_code': 200,
                        'body': {'output_text': 'не json вовсе'}},
        }, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'r.jsonl')
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(line + '\n')
            results = batch.parse_results(path)
        self.assertIsNone(results['1:1']['data'])
        self.assertIsNotNone(results['1:1']['error'])


def _write_tmp_jsonl(testcase, name):
    tmp_dir = tempfile.mkdtemp()
    testcase.addCleanup(lambda: None)  # директория живёт до конца процесса теста
    path = os.path.join(tmp_dir, name + '.jsonl')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(json.dumps({'custom_id': name}) + '\n')
    return path
