"""Ночь 30.10, Э7: ИИ-проверка решения тура по критериям жюри (подставной поставщик)."""
import json
import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from legal import consent
from olympiads import ai_check
from olympiads import training_engine as engine
from olympiads.models import TrainingAttempt, TrainingCheck, TrainingItemResult
from problems.models_legal import ConsentRecord

from . import night_fixtures as fx

User = get_user_model()
MEDIA = tempfile.mkdtemp(prefix='night-e7-')

# Критерии задачи 59997 дословно по устройству: 9 с баллами, 6 правил.
CRITERIA_59997 = """Схема проверки

а) Всего за пункт 4 балла, из них:

- K1 Записаны условия равновесия → 1 балл
- K2 Найдена равновесная мировая цена $p^{\\star} = 1$ → 2 балла
- K3 Рассчитаны объемы производства и потребления → 1 балл

б) Всего за пункт 4 балла, из них:

- K4 Рассчитан объем экспорта Альфы при цене 0,9 → 1 балл
- K5 Найдено оптимальное внутреннее производство Беты → 2 балла
- K6 Определение величины потребления и сделан верный вывод о выигрыше → 1 балл
- K7 Если участник вычислял потребление минуя производство, он получает и К5, и К6
- K8 Если участник исходил из равенства $X_B/200 = p$, то он не получает баллов по К5 и К6
- K9 Если вывод был неверным, то К6 не засчитывается

в) Всего за пункт 4 балла, из них:

- K10 Рассчитан объем экспорта Альфы при цене 2/3 → 1 балл
- K11 Найдено оптимальное внутреннее производство Беты → 2 балла
- K12 Определение величины потребления и сделан верный вывод о проигрыше → 1 балл
- K13 Если участник вычислял потребление минуя производство, он получает и К11, и К12
- K14 Если участник исходил из равенства $X_B/200 = p$, то он не получает баллов по К11 и К12
- K15 Если вывод был неверным, то К12 не засчитывается"""

SCORES = {'K1': 1, 'K2': 2, 'K3': 1, 'K4': 1, 'K5': 2, 'K6': 0,
          'K10': 1, 'K11': 0, 'K12': 0}


def reply(scores=SCORES, extra=None):
    rows = [{'code': c, 'score': s, 'verdict': 'ok' if s else 'miss',
             'why': 'пояснение %s' % c} for c, s in scores.items()]
    rows += extra or []
    return json.dumps({'criteria': rows, 'summary': 'Итог по решению.'},
                      ensure_ascii=False)


class Capture:
    """AI_FAKE_REPLY-функция: отдаёт ответ и запоминает запрос наружу."""

    def __init__(self, text):
        self.text, self.calls = text, []

    def __call__(self, system_blocks, user_text):
        self.calls.append(user_text)
        return self.text


class ParseTests(TestCase):
    def test_59997_criteria_9_scored_6_rules_sum_12(self):
        scored, rules = ai_check.parse_criteria(CRITERIA_59997)
        self.assertEqual([c['code'] for c in scored],
                         ['K1', 'K2', 'K3', 'K4', 'K5', 'K6', 'K10', 'K11', 'K12'])
        self.assertEqual([r['code'] for r in rules],
                         ['K7', 'K8', 'K9', 'K13', 'K14', 'K15'])
        self.assertEqual(sum(c['max'] for c in scored), 12)
        self.assertEqual([c['part'] for c in scored][:4], ['а', 'а', 'а', 'б'])


@override_settings(OLYMPIADS_PUBLIC=True, MEDIA_ROOT=MEDIA, AI_PROVIDER='fake',
                   OLYMPIAD_AI_CHECK=True, AI_FAKE_REPLY=reply())
class CheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.olymp = fx.olympiad('vs')
        cls.final = fx.stage(cls.olymp)
        cls.variant = fx.kit(cls.olymp, cls.final, '2025/26', tour='2', tasks=2)
        for item in cls.variant.items.all():
            item.problem.solution = 'Разбор.\n\n## Критерии оценивания\n' + CRITERIA_59997
            item.problem.save(update_fields=['solution'])
        cls.user = User.objects.create_user(
            'secret_login', password='x', email='pupil-secret@example.com',
            first_name='Тайноимя', last_name='Тайнофамилия')
        for kind in (ConsentRecord.Kind.PD, ConsentRecord.Kind.AI):
            consent.grant(cls.user, kind, ConsentRecord.Source.GATE)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.client.force_login(self.user)

    def url(self, name):
        return reverse('olympiads:' + name, args=['vs', self.variant.pk])

    def free_submit(self, text='а) X_A/1000 = p … б) … в) …'):
        self.client.post(self.url('training_start'), {'timer': '0'})
        attempt = TrainingAttempt.objects.latest('started_at')
        item = engine.variant_items(self.variant)[0]
        self.client.post(self.url('training_item_submit'),
                         {'item_id': item.pk, 'solution_item_%d' % item.pk: text})
        return attempt, item

    def test_good_reply_scores_by_criteria_and_total(self):
        attempt, item = self.free_submit()
        check = TrainingCheck.objects.get(attempt=attempt)
        self.assertEqual(check.status, 'done')
        self.assertEqual(check.score, Decimal('8'))
        self.assertEqual(sum(c['score'] for c in check.criteria), 8)
        result = TrainingItemResult.objects.get(attempt=attempt, problem=item.catalog_problem)
        self.assertEqual((result.score, result.is_pending), (Decimal('8'), False))
        html = self.client.get(self.url('training_take') + '?task=1').content.decode()
        self.assertIn('8 из 12', html)
        self.assertIn('Проверено ИИ по критериям жюри', html)

    def test_off_schema_replies_are_errors_not_crashes(self):
        bad = [
            reply(extra=[{'code': 'K99', 'score': 1, 'verdict': 'ok', 'why': ''}]),
            reply(dict(SCORES, K2=3)),                       # больше максимума
            reply(dict(SCORES, K2=1.3)),                     # не кратно 0,5
            reply({k: v for k, v in SCORES.items() if k != 'K12'}),  # пропуск
            json.dumps({'nonsense': True}),
        ]
        for text in bad:
            TrainingAttempt.objects.all().delete()
            cache.clear()
            with self.settings(AI_FAKE_REPLY=text):
                attempt, item = self.free_submit()
                check = TrainingCheck.objects.get(attempt=attempt)
                self.assertEqual(check.status, 'error', text)
                self.assertIsNone(check.score)
                page = self.client.get(self.url('training_take') + '?task=1')
                self.assertEqual(page.status_code, 200)

    def test_sum_above_task_maximum_is_error(self):
        how = {'approximate': False, 'maximum': 3.0,
               'criteria': [{'code': 'K1', 'text': '', 'max': 2.0, 'part': ''},
                            {'code': 'K2', 'text': '', 'max': 2.0, 'part': ''}],
               'rules': []}
        data = {'criteria': [{'code': 'K1', 'score': 2, 'verdict': 'ok', 'why': ''},
                             {'code': 'K2', 'score': 2, 'verdict': 'ok', 'why': ''}],
                'summary': ''}
        self.assertIsNone(ai_check.validate(data, how))

    def test_unparsed_criteria_give_approximate_single_score(self):
        for item in self.variant.items.all():
            item.problem.solution = ('Разбор.\n\n## Критерии оценивания\n'
                                     'Полное решение — 12 баллов, ход верный — 6.')
            item.problem.save(update_fields=['solution'])
        try:
            with self.settings(AI_FAKE_REPLY=json.dumps({'score': 6, 'summary': 'Ход верный.'})):
                attempt, _ = self.free_submit()
            check = TrainingCheck.objects.get(attempt=attempt)
            self.assertTrue(check.approximate)
            self.assertEqual(check.score, Decimal('6'))
            html = self.client.get(self.url('training_take') + '?task=1').content.decode()
            self.assertIn('Оценка ориентировочная', html)
        finally:
            for item in self.variant.items.all():
                item.problem.solution = 'Разбор.\n\n## Критерии оценивания\n' + CRITERIA_59997
                item.problem.save(update_fields=['solution'])

    def test_no_criteria_no_call_and_reference_shown(self):
        capture = Capture(reply())
        for item in self.variant.items.all():
            item.problem.solution = 'ЭТАЛОН-БЕЗ-КРИТЕРИЕВ'
            item.problem.save(update_fields=['solution'])
        with self.settings(AI_FAKE_REPLY=capture):
            attempt, _ = self.free_submit()
        self.assertEqual(capture.calls, [])
        self.assertFalse(TrainingCheck.objects.exists())
        html = self.client.get(self.url('training_take') + '?task=1').content.decode()
        self.assertIn('ЭТАЛОН-БЕЗ-КРИТЕРИЕВ', html)

    def test_flag_off_and_guest_make_zero_calls(self):
        capture = Capture(reply())
        with self.settings(AI_FAKE_REPLY=capture, OLYMPIAD_AI_CHECK=False):
            self.free_submit()
        self.client.logout()
        with self.settings(AI_FAKE_REPLY=capture):
            self.free_submit()
        self.assertEqual(capture.calls, [])
        self.assertFalse(TrainingCheck.objects.exists())

    def test_outgoing_prompt_has_no_profile_fields(self):
        capture = Capture(reply())
        self.user.profile_grade = '11'
        with self.settings(AI_FAKE_REPLY=capture):
            self.free_submit('моё решение задачи')
        self.assertEqual(len(capture.calls), 1)
        sent = capture.calls[0]
        for secret in ('secret_login', 'pupil-secret@example.com', 'Тайноимя',
                       'Тайнофамилия'):
            self.assertNotIn(secret, sent)
        self.assertIn('моё решение задачи', sent)
        self.assertIn('K12', sent)
        self.assertNotIn('Разбор.', sent)  # эталон наружу не уходит

    def test_timed_tour_queues_and_checks_one_per_request(self):
        self.client.post(self.url('training_start'), {'timer': '1'})
        attempt = TrainingAttempt.objects.latest('started_at')
        items = engine.variant_items(self.variant)
        data = {'solution_item_%d' % i.pk: 'решение %d' % n for n, i in enumerate(items)}
        self.client.post(self.url('training_finish'), data)
        self.assertEqual(TrainingCheck.objects.filter(attempt=attempt, status='queued').count(), 2)
        first = self.client.post(self.url('training_check_next'),
                                 HTTP_X_REQUESTED_WITH='fetch').json()
        self.assertEqual((first['done'], first['total'], first['finished']), (1, 2, False))
        second = self.client.post(self.url('training_check_next'),
                                  HTTP_X_REQUESTED_WITH='fetch').json()
        self.assertEqual((second['done'], second['finished']), (2, True))
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, Decimal('16'))
        self.assertEqual(attempt.pending_count, 0)
