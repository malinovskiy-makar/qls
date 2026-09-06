"""Фаза 6.2: фото и файл к попытке — проверка загрузки, лимит, распознавание."""
import io
import json
import tempfile

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from catalog import attachments
from catalog.tests.test_attempts import _reply
from problems.models import CatalogAttempt, FileAsset
from problems.tests.factories import make_problem, make_user

MEDIA = tempfile.mkdtemp(prefix='qls_media_')


def _png(name='тетрадь.png'):
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), (255, 255, 255)).save(buf, 'PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


@override_settings(AI_PROVIDER='fake', MEDIA_ROOT=MEDIA)
class AttemptFileTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user('фотограф')
        self.other = make_user('чужой')
        self.problem = make_problem('Найдите равновесие.', solution='Эталон длиннее тридцати знаков.',
                                    answer='40')
        self.upload_url = reverse('catalog:api_attempt_file')
        self.attempt_url = reverse('catalog:api_attempt')
        self.client.force_login(self.user)

    def _upload(self, file, pending=''):
        return self.client.post(self.upload_url, {'file': file, 'pending': pending})

    def test_wrong_type_is_400_with_a_human_text(self):
        resp = self._upload(SimpleUploadedFile('решение.docx', b'PK\x03\x04', content_type='application/msword'))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.content)['message'], attachments.WRONG_TYPE)
        # Расширение картинки, а внутри мусор — тоже отказ.
        resp = self._upload(SimpleUploadedFile('фото.png', b'not an image', content_type='image/png'))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(FileAsset.objects.count(), 0)

    def test_too_big_is_400(self):
        big = SimpleUploadedFile('большое.pdf', b'%PDF' + b'0' * (attachments.MAX_BYTES + 1),
                                 content_type='application/pdf')
        resp = self._upload(big)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.content)['message'], attachments.TOO_BIG)

    def test_fourth_file_is_400(self):
        ids = []
        for _ in range(3):
            resp = self._upload(_png(), pending=','.join(str(i) for i in ids))
            self.assertEqual(resp.status_code, 200, resp.content)
            ids.append(json.loads(resp.content)['id'])
        resp = self._upload(_png(), pending=','.join(str(i) for i in ids))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.content)['message'], attachments.TOO_MANY)

    def test_attempt_with_a_photo_is_recognised_and_checked(self):
        asset_id = json.loads(self._upload(_png()).content)['id']
        seen = []

        def fake(system_blocks, user_text):
            seen.append(user_text)
            if 'переписать математический текст' in system_blocks[1]:
                return json.dumps({'text': 'Qs = 2(P - t1 - t2); t1 = t2 = 40'}, ensure_ascii=False)
            return _reply()

        with override_settings(AI_FAKE_REPLY=fake):
            resp = self.client.post(self.attempt_url, json.dumps({
                'problem_id': self.problem.pk, 'text': '', 'file_ids': [asset_id]}),
                content_type='application/json')
        self.assertEqual(resp.status_code, 200, resp.content)
        data = json.loads(resp.content)
        self.assertEqual(data['status'], 'checked')
        self.assertIn('как мы его прочитали', data['html'])
        self.assertIn('Qs = 2(P - t1 - t2); t1 = t2 = 40', data['html'])
        attempt = CatalogAttempt.objects.get(pk=data['attempt_id'])
        self.assertEqual(attempt.ocr_text, 'Qs = 2(P - t1 - t2); t1 = t2 = 40')
        self.assertEqual(list(attempt.files.values_list('pk', flat=True)), [asset_id])
        # Первый вызов — распознавание (хеш файла в тексте), второй — проверка с распознанным.
        self.assertEqual(len(seen), 2)
        self.assertIn('sha256', seen[0])
        self.assertIn('ТЕКСТ, РАСПОЗНАННЫЙ С ФОТО:', seen[1])
        self.assertIn('t1 = t2 = 40', seen[1])

    def test_someone_elses_file_is_rejected_and_text_or_file_required(self):
        foreign = FileAsset.objects.create(file=_png(), kind=FileAsset.Kind.STUDENT_WORK,
                                           uploaded_by=self.other)
        resp = self.client.post(self.attempt_url, json.dumps({
            'problem_id': self.problem.pk, 'text': 'x', 'file_ids': [foreign.pk]}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post(self.attempt_url, json.dumps({
            'problem_id': self.problem.pk, 'text': '', 'file_ids': []}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_page_offers_the_button_only_with_model_and_login(self):
        page = reverse('catalog:problem_detail', args=[self.problem.pk])
        html = self.client.get(page).content.decode()
        self.assertIn('id="att-add"', html)
        self.assertIn('"fileUrl": "/catalog/api/attempt-file/"', html)
        self.client.logout()
        html = self.client.get(page).content.decode()
        self.assertNotIn('id="att-add"', html)

    def test_anonymous_upload_is_403(self):
        self.client.logout()
        self.assertEqual(self._upload(_png()).status_code, 403)
