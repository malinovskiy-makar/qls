"""Ночь 30.10, Э9: сквозной путь ученика через тестовый клиент (браузерный —
`claude/night_olymp_20261030/tools/e2e.mjs`). Ни одного ответа 500 на пути."""
import json
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from legal import consent
from olympiads import navigator as nav
from olympiads import training_engine as engine
from olympiads.models import TrainingAttempt, TrainingCheck
from problems.models_legal import ConsentRecord

from . import night_fixtures as fx
from .test_night_E5 import image

User = get_user_model()
MEDIA = tempfile.mkdtemp(prefix='night-e9-')
REPLY = json.dumps({'criteria': [
    {'code': 'K1', 'score': 2, 'verdict': 'ok', 'why': 'есть'},
    {'code': 'K2', 'score': 1, 'verdict': 'part', 'why': 'частично'}],
    'summary': 'Подставной ответ.', 'reply': 'По критерию K2 снято верно.', 'text': ''},
    ensure_ascii=False)


@override_settings(OLYMPIADS_PUBLIC=True, MEDIA_ROOT=MEDIA, AI_PROVIDER='fake',
                   CATALOG_CHAT_PROVIDER='fake', CATALOG_CHAT_VISION_MODEL='',
                   OLYMPIAD_AI_CHECK=True, AI_FAKE_REPLY=REPLY)
class StudentPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.olymp = fx.olympiad('vs')
        cls.final = fx.stage(cls.olymp)
        cls.tour1 = fx.kit(cls.olymp, cls.final, '2025/26', tour='1', tasks=2, score=4)
        cls.tour2 = fx.kit(cls.olymp, cls.final, '2025/26', tour='2', tasks=2, score=4)
        cls.user = User.objects.create_user('pupil', password='x')
        for kind in (ConsentRecord.Kind.PD, ConsentRecord.Kind.AI):
            consent.grant(cls.user, kind, ConsentRecord.Source.GATE)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def ok(self, response, code=200):
        self.assertEqual(response.status_code, code, getattr(response, 'url', ''))
        return response

    def url(self, name, variant):
        return reverse('olympiads:' + name, args=['vs', variant.pk])

    def test_whole_path_free_then_timed(self):
        cache.clear()
        self.client.force_login(self.user)
        self.ok(self.client.get(reverse('olympiads:list')))
        page = nav.olympiad_page(self.olymp)
        cell = [c for c in page['grids'][0]['cells'] if c['grades'] == [11]][0]
        detail = self.ok(self.client.get(reverse('olympiads:detail', args=['vs']),
                                         {'open': cell['key']})).content.decode()
        intro = self.url('training_intro', self.tour2)
        self.assertIn(intro + '?mode=free', detail)
        self.ok(self.client.get(intro, {'mode': 'free'}))

        # Без времени: задание текстом → проверка → оспорить → завершить.
        self.client.post(self.url('training_start', self.tour2), {'timer': '0'})
        items = engine.variant_items(self.tour2)
        take = self.url('training_take', self.tour2)
        self.ok(self.client.get(take))
        first = items[0]
        self.ok(self.client.post(self.url('training_item_submit', self.tour2),
                                 {'item_id': first.pk,
                                  'solution_item_%d' % first.pk: 'моё решение'}), 302)
        checked = self.ok(self.client.get(take + '?task=1')).content.decode()
        self.assertIn('3 из 4', checked)
        self.ok(self.client.get(take, {'task': 1, 'dispute': first.catalog_problem_id}))
        r = self.ok(self.client.post(self.url('training_dispute', self.tour2),
                                     {'problem_id': first.catalog_problem_id,
                                      'message': 'Почему?'},
                                     HTTP_X_REQUESTED_WITH='fetch'))
        self.assertIn('K2', r.json()['reply'])
        self.ok(self.client.post(self.url('training_finish', self.tour2), {}), 302)
        self.ok(self.client.get(self.url('training_result', self.tour2)))

        # На время: лист с компьютера → сдать тур → очередь → результат.
        self.client.post(self.url('training_start', self.tour2), {'timer': '1'})
        attempt = TrainingAttempt.objects.filter(with_timer=True).latest('started_at')
        self.ok(self.client.get(take))
        self.ok(self.client.post(self.url('training_upload', self.tour2),
                                 {'item_id': first.pk, 'file': image()},
                                 HTTP_X_REQUESTED_WITH='fetch'))
        self.ok(self.client.post(self.url('training_finish', self.tour2), {}), 302)
        self.assertEqual(TrainingCheck.objects.filter(attempt=attempt).count(), 1)
        self.ok(self.client.post(self.url('training_check_next', self.tour2),
                                 HTTP_X_REQUESTED_WITH='fetch'))
        result = self.ok(self.client.get(self.url('training_result', self.tour2))).content.decode()
        self.assertIn('проверено ИИ по критериям жюри', result)
        self.assertNotIn('data-queue', result)
        attempt.refresh_from_db()
        self.assertEqual(float(attempt.score), 3.0)
