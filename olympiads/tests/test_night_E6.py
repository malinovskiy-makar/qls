"""Ночь 30.10, Э6: фото решения с телефона по QR-коду."""
import shutil
import tempfile
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from olympiads import phone
from olympiads import training_engine as engine
from olympiads.models import PhoneUploadToken, TrainingAttempt, TrainingUpload

from . import night_fixtures as fx
from .test_night_E5 import image

MEDIA = tempfile.mkdtemp(prefix='night-e6-')


@override_settings(OLYMPIADS_PUBLIC=True, MEDIA_ROOT=MEDIA)
class PhoneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.olymp = fx.olympiad('vs')
        cls.final = fx.stage(cls.olymp)
        cls.variant = fx.kit(cls.olymp, cls.final, '2025/26', tour='2')

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.client.post(reverse('olympiads:training_start',
                                 args=['vs', self.variant.pk]), {'timer': '1'})
        self.attempt = TrainingAttempt.objects.get()
        self.items = engine.variant_items(self.variant)
        self.first, self.second = self.items[0], self.items[1]

    def token(self, item=None):
        return phone.issue(self.attempt, (item or self.first).catalog_problem)

    def url(self, token):
        return reverse('olympiads:phone_upload', args=[token.token])

    def test_token_lives_30_minutes_and_is_reused(self):
        token = self.token()
        self.assertAlmostEqual((token.expires_at - token.created_at).total_seconds(),
                               30 * 60, delta=2)
        self.assertEqual(self.token().pk, token.pk)
        self.assertGreaterEqual(len(token.token), 32)

    def test_phone_page_opens_without_login_and_uploads(self):
        from django.test import Client
        phone_client = Client()
        token = self.token()
        self.assertEqual(phone_client.get(self.url(token)).status_code, 200)
        r = phone_client.post(self.url(token), {'file': image()})
        self.assertEqual(r.status_code, 302)
        sheet = TrainingUpload.objects.get()
        self.assertEqual((sheet.source, sheet.problem_id),
                         ('phone', self.first.catalog_problem_id))
        token.refresh_from_db()
        self.assertIsNotNone(token.used_at)

    def test_wrong_file_from_phone_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad = SimpleUploadedFile('x.png', b'nope', content_type='image/png')
        r = self.client.post(self.url(self.token()), {'file': bad})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(TrainingUpload.objects.count(), 0)

    def test_expired_token_is_410(self):
        token = self.token()
        PhoneUploadToken.objects.filter(pk=token.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(self.url(token)).status_code, 410)
        self.assertEqual(self.client.post(self.url(token),
                                          {'file': image()}).status_code, 410)

    def test_token_after_submit_is_410(self):
        token = self.token()
        engine.submit_attempt(self.attempt)
        self.assertEqual(self.client.get(self.url(token)).status_code, 410)

    def test_unknown_token_is_404(self):
        r = self.client.get(reverse('olympiads:phone_upload', args=['no-such']))
        self.assertEqual(r.status_code, 404)

    def test_token_does_not_open_another_task(self):
        token = self.token(self.first)
        other = phone.issue(self.attempt, self.second.catalog_problem)
        self.client.post(self.url(other), {'file': image()})
        sheet = TrainingUpload.objects.get(problem=self.second.catalog_problem)
        r = self.client.get(reverse('olympiads:phone_sheet',
                                    args=[token.token, sheet.pk]))
        self.assertEqual(r.status_code, 404)
        # А по «своему» токену лист виден.
        r = self.client.get(reverse('olympiads:phone_sheet',
                                    args=[other.token, sheet.pk]))
        self.assertEqual(r.status_code, 200)

    def test_desk_poll_sees_phone_sheets_and_closes_after_submit(self):
        poll = reverse('olympiads:training_sheets', args=['vs', self.variant.pk])
        self.client.post(self.url(self.token()), {'file': image()})
        data = self.client.get(poll, {'item': self.first.pk}).json()
        self.assertFalse(data['closed'])
        self.assertEqual([s['source'] for s in data['sheets']], ['phone'])
        self.assertTrue(data['connected'])
        engine.submit_attempt(self.attempt)
        data = self.client.get(poll, {'item': self.first.pk}).json()
        self.assertTrue(data['closed'])

    def test_take_page_shows_qr_and_no_qr_without_library(self):
        take = reverse('olympiads:training_take', args=['vs', self.variant.pk])
        html = self.client.get(take).content.decode()
        self.assertIn('С телефона', html)
        self.assertIn('<svg', html.split('data-qr>', 1)[1][:200])
        with mock.patch.object(phone, 'qr_svg', return_value=''):
            html = self.client.get(take).content.decode()
        self.assertNotIn('data-phone ', html)
        self.assertIn('Выбрать файлы', html)
