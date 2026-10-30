"""Ночь 30.10, Э5: вход в тур, «на время» / «без времени», листы фото, утечки."""
import io
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from olympiads import training_engine as engine
from olympiads import uploads
from olympiads.models import TrainingAttempt, TrainingItemResult, TrainingUpload

from . import night_fixtures as fx

User = get_user_model()
MEDIA = tempfile.mkdtemp(prefix='night-e5-')
SECRET = 'ЭТАЛОН-РАЗБОР-СЕКРЕТ: оптимум при p равном единице'
CRIT = 'K1 Найден оптимум → 2 балла'


def image(fmt='JPEG', name='a.jpg', exif=False):
    from PIL import Image
    buf = io.BytesIO()
    img = Image.new('RGB', (40, 30), 'white')
    if exif:
        data = Image.Exif()
        data[0x010F] = 'ТелефонМарки'   # Make
        data[0x8825] = {2: (55, 45, 0)}  # GPS
        img.save(buf, fmt, exif=data)
    else:
        img.save(buf, fmt)
    return SimpleUploadedFile(name, buf.getvalue(),
                              content_type='image/' + fmt.lower())


@override_settings(OLYMPIADS_PUBLIC=True, MEDIA_ROOT=MEDIA,
                   OLYMPIAD_AI_CHECK=False)
class TourTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.olymp = fx.olympiad('vs')
        cls.final = fx.stage(cls.olymp)
        cls.variant = fx.kit(cls.olymp, cls.final, '2025/26', tour='2')
        for item in cls.variant.items.all():
            item.problem.solution = SECRET + '\n\n## Критерии оценивания\n' + CRIT
            item.problem.save(update_fields=['solution'])
        cls.user = User.objects.create_user('pupil', password='x')

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def url(self, name, *extra):
        return reverse('olympiads:' + name, args=['vs', self.variant.pk, *extra])

    def start(self, timer='1', **extra):
        self.client.post(self.url('training_start'), dict(timer=timer, **extra))
        return TrainingAttempt.objects.latest('started_at')

    def items(self):
        return engine.variant_items(self.variant)

    # ── время и источник задач ──
    def test_timed_tour_gets_stage_time_210(self):
        attempt = self.start()
        # `started_at` ставит база при записи — на доли секунды позже `now`.
        self.assertAlmostEqual((attempt.expires_at - attempt.started_at)
                               .total_seconds(), 210 * 60, delta=1)

    def test_client_cannot_set_time(self):
        attempt = self.start(minutes='999', expires_at='2099-01-01')
        # `started_at` ставит база при записи — на доли секунды позже `now`.
        self.assertAlmostEqual((attempt.expires_at - attempt.started_at)
                               .total_seconds(), 210 * 60, delta=1)

    def test_tour_problems_come_from_package_items(self):
        self.assertEqual([i.catalog_problem_id for i in self.items()],
                         list(self.variant.items.order_by('order')
                              .values_list('problem_id', flat=True)))
        self.assertEqual([float(i.points) for i in self.items()], [12.0] * 4)

    # ── утечки ──
    def test_no_solution_or_criteria_before_submit(self):
        for timer in ('1', '0'):
            TrainingAttempt.objects.all().delete()
            self.start(timer)
            html = self.client.get(self.url('training_take')).content.decode()
            self.assertNotIn('ЭТАЛОН-РАЗБОР-СЕКРЕТ', html, timer)
            self.assertNotIn('Найден оптимум', html, timer)
            intro = self.client.get(self.url('training_intro')).content.decode()
            self.assertNotIn('ЭТАЛОН-РАЗБОР-СЕКРЕТ', intro)
            self.assertNotIn('Найден оптимум', intro)

    # ── листы ──
    def test_jpeg_and_png_pass_eleventh_and_wrong_rejected(self):
        attempt = self.start()
        item = self.items()[0]
        for n in range(5):
            r = self.client.post(self.url('training_upload'),
                                 {'item_id': item.pk, 'file': image()},
                                 HTTP_X_REQUESTED_WITH='fetch')
            self.assertEqual(r.status_code, 200, r.content)
            r = self.client.post(self.url('training_upload'),
                                 {'item_id': item.pk,
                                  'file': image('PNG', 'b.png')},
                                 HTTP_X_REQUESTED_WITH='fetch')
            self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(TrainingUpload.objects.filter(attempt=attempt).count(), 10)
        r = self.client.post(self.url('training_upload'),
                             {'item_id': item.pk, 'file': image()},
                             HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['error'], uploads.TOO_MANY_SHEETS)
        bad = SimpleUploadedFile('x.jpg', b'not an image', content_type='image/jpeg')
        r = self.client.post(self.url('training_upload'),
                             {'item_id': self.items()[1].pk, 'file': bad},
                             HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['error'], uploads.WRONG_TYPE)

    def test_exif_is_stripped(self):
        from PIL import Image
        self.start()
        self.client.post(self.url('training_upload'),
                         {'item_id': self.items()[0].pk, 'file': image(exif=True)})
        sheet = TrainingUpload.objects.get()
        with sheet.file.open('rb') as fh:
            data = fh.read()
        self.assertNotIn(b'\xd0\xa2\xd0\xb5\xd0\xbb', data)  # «Тел…» марки нет
        self.assertEqual(dict(Image.open(io.BytesIO(data)).getexif()), {})

    def test_sheet_is_served_only_to_its_owner(self):
        self.start()
        self.client.post(self.url('training_upload'),
                         {'item_id': self.items()[0].pk, 'file': image()})
        sheet = TrainingUpload.objects.get()
        self.assertEqual(self.client.get(self.url('training_sheet', sheet.pk)).status_code, 200)
        from django.test import Client
        stranger = Client()
        self.assertEqual(stranger.get(self.url('training_sheet', sheet.pk)).status_code, 404)

    # ── без времени ──
    def test_free_submit_locks_that_task_only(self):
        attempt = self.start('0')
        first, second = self.items()[:2]
        r = self.client.post(self.url('training_item_submit'),
                             {'item_id': first.pk,
                              'solution_item_%d' % first.pk: 'моё решение'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(TrainingItemResult.objects.filter(
            attempt=attempt, problem=first.catalog_problem).exists())
        locked = self.client.post(self.url('training_autosave'),
                                  data={'item_id': first.pk, 'solution': 'правка'},
                                  content_type='application/json')
        self.assertEqual(locked.status_code, 409)
        open_ = self.client.post(self.url('training_autosave'),
                                 data={'item_id': second.pk, 'solution': 'черновик'},
                                 content_type='application/json')
        self.assertEqual(open_.status_code, 200)
        up = self.client.post(self.url('training_upload'),
                              {'item_id': first.pk, 'file': image()},
                              HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(up.status_code, 409)
        html = self.client.get(self.url('training_take') + '?task=1').content.decode()
        self.assertIn('ЭТАЛОН-РАЗБОР-СЕКРЕТ', html)       # разбор сданного
        self.assertEqual(html.count('ЭТАЛОН-РАЗБОР-СЕКРЕТ'), 1)  # только у него

    def test_solution_only_is_pending_not_zero(self):
        attempt = self.start('0')
        item = self.items()[0]
        self.client.post(self.url('training_item_submit'),
                         {'item_id': item.pk,
                          'solution_item_%d' % item.pk: 'развёрнутое решение'})
        result = TrainingItemResult.objects.get(attempt=attempt)
        self.assertTrue(result.is_pending)
        self.assertIsNone(result.score)

    def test_last_free_task_submits_the_tour(self):
        attempt = self.start('0')
        for item in self.items():
            r = self.client.post(self.url('training_item_submit'), {'item_id': item.pk})
        self.assertEqual(r['Location'], self.url('training_result'))
        attempt.refresh_from_db()
        self.assertIsNotNone(attempt.submitted_at)

    # ── вход ──
    def test_ai_promise_only_with_flag_and_criteria(self):
        intro = self.client.get(self.url('training_intro')).content.decode()
        self.assertNotIn('проверяет ИИ', intro)
        with self.settings(OLYMPIAD_AI_CHECK=True):
            intro = self.client.get(self.url('training_intro')).content.decode()
            self.assertIn('Решения проверяет ИИ по критериям жюри', intro)
            self.variant.items.update(has_criteria=False)
            intro = self.client.get(self.url('training_intro')).content.decode()
            self.assertNotIn('ИИ', intro.split('class="om om-intro"', 1)[1])

    def test_intro_shows_both_modes_and_time(self):
        html = self.client.get(self.url('training_intro')).content.decode()
        self.assertIn('3 ч 30 мин', html)
        self.assertIn('Без таймера', html)

    # ── уборка ──
    def test_cleanup_removes_guest_sheet_files(self):
        attempt = self.start()
        self.client.post(self.url('training_upload'),
                         {'item_id': self.items()[0].pk, 'file': image()})
        sheet = TrainingUpload.objects.get()
        path = sheet.file.path
        TrainingAttempt.objects.filter(pk=attempt.pk).update(
            started_at=timezone.now() - timedelta(days=8))
        import os
        self.assertTrue(os.path.exists(path))
        call_command('cleanup_training_attempts', stdout=io.StringIO())
        self.assertFalse(os.path.exists(path))
        self.assertEqual(TrainingUpload.objects.count(), 0)
