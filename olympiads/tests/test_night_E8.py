"""Ночь 30.10, Э8: результат тура, «Как решали другие» (от 20), «Оспорить оценку»."""
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from legal import consent
from olympiads import navigator as nav
from olympiads import training_engine as engine
from olympiads.models import (TrainingAttempt, TrainingCheck, TrainingItemResult)
from problems.models_legal import ConsentRecord
from problems.models_platform import ChatTurn

from . import night_fixtures as fx

User = get_user_model()


def done_attempt(variant, user=None, score=10, timer=True, session=''):
    return TrainingAttempt.objects.create(
        variant=variant, user=user, session_key=session, with_timer=timer,
        submitted_at=timezone.now(), score=score, max_score=48)


class OthersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.olymp = fx.olympiad('vs')
        cls.final = fx.stage(cls.olymp)
        cls.variant = fx.kit(cls.olymp, cls.final, '2025/26', tour='2')
        cls.me = User.objects.create_user('me', password='x')

    def make_others(self, n, start=1):
        for k in range(start, start + n):
            user = User.objects.create_user('u%d' % k, password='x')
            done_attempt(self.variant, user, score=k)

    def test_19_students_no_block_20_block_with_true_median(self):
        self.make_others(19)
        self.assertIsNone(nav.others_stats(self.variant, self.me, 15))
        self.make_others(1, start=20)
        stats = nav.others_stats(self.variant, self.me, 15)
        self.assertEqual(stats['count'], 20)
        self.assertEqual(stats['median'], 10.5)          # медиана 1…20
        self.assertEqual(stats['below_pct'], 70)          # 14 из 20 ниже 15

    def test_guests_free_mode_and_self_do_not_count(self):
        self.make_others(19)
        for k in range(5):
            done_attempt(self.variant, None, score=40, session='g%d' % k)
        done_attempt(self.variant, User.objects.create_user('free', password='x'),
                     score=40, timer=False)
        done_attempt(self.variant, self.me, score=48)
        self.assertIsNone(nav.others_stats(self.variant, self.me, 48))

    def test_latest_attempt_per_student(self):
        self.make_others(20)
        again = User.objects.get(username='u1')
        done_attempt(self.variant, again, score=48)
        stats = nav.others_stats(self.variant, self.me)
        self.assertEqual(stats['count'], 20)


@override_settings(OLYMPIADS_PUBLIC=True, AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake',
                   CATALOG_CHAT_VISION_MODEL='', OLYMPIAD_AI_CHECK=True)
class ResultAndDisputeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.olymp = fx.olympiad('vs')
        cls.final = fx.stage(cls.olymp)
        # Максимум задания = сумме критериев фикстуры (K1 2 + K2 2): точный режим.
        cls.variant = fx.kit(cls.olymp, cls.final, '2025/26', tour='2', tasks=2, score=4)
        cls.user = User.objects.create_user('secret_login', password='x',
                                            email='pupil-secret@example.com',
                                            first_name='Тайноимя')
        for kind in (ConsentRecord.Kind.PD, ConsentRecord.Kind.AI):
            consent.grant(cls.user, kind, ConsentRecord.Source.GATE)

    def setUp(self):
        cache.clear()
        self.client.force_login(self.user)
        self.client.post(self.url('training_start'), {'timer': '1'})
        self.attempt = TrainingAttempt.objects.get()
        self.items = engine.variant_items(self.variant)
        reply = json.dumps({'criteria': [
            {'code': 'K1', 'score': 2, 'verdict': 'ok', 'why': 'есть'},
            {'code': 'K2', 'score': 0, 'verdict': 'miss', 'why': 'нет экспорта'}],
            'summary': 'Частично.'}, ensure_ascii=False)
        data = {'solution_item_%d' % i.pk: 'решение %d' % n for n, i in enumerate(self.items)}
        with self.settings(AI_FAKE_REPLY=reply):
            self.client.post(self.url('training_finish'), data)
            for _ in self.items:
                self.client.post(self.url('training_check_next'),
                                 HTTP_X_REQUESTED_WITH='fetch')
        self.attempt.refresh_from_db()
        self.check = TrainingCheck.objects.filter(attempt=self.attempt).first()

    def url(self, name):
        return reverse('olympiads:' + name, args=['vs', self.variant.pk])

    def test_sum_of_tasks_equals_tour_total(self):
        rows = TrainingItemResult.objects.filter(attempt=self.attempt)
        self.assertEqual(sum(r.score for r in rows), self.attempt.score)
        html = self.client.get(self.url('training_result')).content.decode()
        self.assertIn('%s из %s' % (int(self.attempt.score), int(self.attempt.max_score)), html)
        self.assertIn('Проверено ИИ по критериям жюри'.lower(), html.lower())
        self.assertNotIn('Как решали другие', html)

    def test_dispute_does_not_change_score_and_logs_turn(self):
        seen = []

        def fake(system_blocks, user_text):
            seen.append((system_blocks, user_text))
            return json.dumps({'reply': 'По критерию K2 балл снят верно.'},
                              ensure_ascii=False)

        before = (self.check.score, self.attempt.score)
        with self.settings(AI_FAKE_REPLY=fake):
            r = self.client.post(self.url('training_dispute'),
                                 {'problem_id': self.check.problem_id, 'code': 'K2',
                                  'message': 'Почему ноль за K2?'},
                                 HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn('K2', r.json()['reply'])
        self.check.refresh_from_db()
        self.attempt.refresh_from_db()
        self.assertEqual((self.check.score, self.attempt.score), before)
        turn = ChatTurn.objects.get()
        self.assertEqual((turn.mode, turn.quote_source), ('dispute', 'criterion'))
        system, text = seen[-1]
        sent = '\n'.join(system) + '\n' + text
        for secret in ('secret_login', 'pupil-secret@example.com', 'Тайноимя'):
            self.assertNotIn(secret, sent)
        self.assertIn('ОЦЕНКА ПО КРИТЕРИЯМ ЖЮРИ', sent)
        self.assertIn('Почему ноль за K2?', text)

    def test_send_to_human_marks_pending_keeps_score(self):
        score = self.check.score
        self.client.post(self.url('training_dispute_human'),
                         {'problem_id': self.check.problem_id})
        self.check.refresh_from_db()
        result = TrainingItemResult.objects.get(attempt=self.attempt,
                                                problem_id=self.check.problem_id)
        self.assertTrue(self.check.human_review)
        self.assertTrue(result.is_pending)
        self.assertEqual(result.score, score)

    def test_someone_else_cannot_dispute(self):
        other = User.objects.create_user('other', password='x')
        self.client.force_login(other)
        r = self.client.post(self.url('training_dispute'),
                             {'problem_id': self.check.problem_id, 'message': 'хм'},
                             HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.status_code, 404)

    def test_dispute_panel_renders_without_js(self):
        html = self.client.get(self.url('training_result') + '?dispute=%d' %
                               self.check.problem_id).content.decode()
        self.assertIn('data-dispute', html)
        self.assertIn('Отправить на проверку человеку', html)

    def test_others_block_appears_from_20(self):
        for k in range(20):
            done_attempt(self.variant, User.objects.create_user('o%d' % k, password='x'),
                         score=k)
        html = self.client.get(self.url('training_result')).content.decode()
        self.assertIn('Как решали другие', html)
        self.assertIn('медиана других', html)

    def test_queue_progress_shown_while_waiting(self):
        TrainingCheck.objects.filter(attempt=self.attempt).update(status='queued')
        html = self.client.get(self.url('training_result')).content.decode()
        self.assertIn('data-queue', html)
        self.assertIn('Проверено', html)
        self.assertEqual(Decimal(1), Decimal(1))
