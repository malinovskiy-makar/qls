"""Чистые функции цифр беты ИИ (`problems/ai_beta/metrics.py`). Данные выдуманные."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from django.test import SimpleTestCase

from problems.ai_beta import metrics as m

T0 = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)  # понедельник, 12:00 МСК


def turn(i, user, minutes=0, mode='free', error='', reply='ответ', files=(), cost='0.003',
         problem=1, thread='t1', latency=5000):
    return {'id': i, 'user_id': user, 'problem_id': problem, 'thread': thread, 'mode': mode,
            'created_at': T0 + timedelta(minutes=minutes), 'latency_ms': latency,
            'cost_usd': Decimal(cost), 'input_tokens': 1000, 'output_tokens': 400,
            'vision_in': 0, 'vision_out': 0, 'vision_text': '', 'reply': reply,
            'error': error, 'files': list(files)}


class PercentileTests(SimpleTestCase):
    def test_nearest_rank(self):
        values = list(range(1, 11))
        self.assertEqual(m.percentile(values, 50), 5)
        self.assertEqual(m.percentile(values, 75), 8)
        self.assertEqual(m.percentile(values, 90), 9)
        self.assertEqual(m.percentile(values, 100), 10)

    def test_empty_is_none(self):
        self.assertIsNone(m.percentile([], 50))
        self.assertIsNone(m.dist([])['median'])

    def test_order_does_not_matter(self):
        self.assertEqual(m.percentile([10, 1, 5, 3, 7, 2, 9, 4, 8, 6], 50), 5)


class ConcurrencyTests(SimpleTestCase):
    def test_three_overlap(self):
        self.assertEqual(m.max_concurrency([(0, 10), (5, 15), (9, 12), (20, 25)]), 3)

    def test_touch_is_not_overlap(self):
        self.assertEqual(m.max_concurrency([(0, 10), (10, 20)]), 1)

    def test_episodes(self):
        intervals = [(0, 10), (5, 15), (9, 12), (20, 25), (21, 22), (21.5, 23)]
        self.assertEqual(m.concurrency_episodes(intervals, 3), [9, 21.5])
        self.assertEqual(len(m.concurrency_episodes(intervals, 4)), 0)

    def test_zero_length_ignored(self):
        self.assertEqual(m.max_concurrency([(5, 5), (0, 10)]), 1)


class ErrorKindTests(SimpleTestCase):
    def test_kinds(self):
        cases = {
            'limit: На сегодня лимит обращений исчерпан (30 в сутки).': 'personal_limit',
            'limit: На сегодня исчерпан суточный бюджет этой функции ($1.0).': 'cost_cap',
            'other: Разбор запроса вернул неожиданный ответ. Попробуйте описать домашку '
            'иначе или соберите её вручную.': 'format',
            'other: Помощник не ответил. Попробуйте спросить иначе.': 'empty',
            'other: Ответ занял больше 25 секунд и прерван. Попробуйте отправить ещё раз.':
                'timeout',
            'other: Не удалось связаться с сервисом разбора запроса. Проверьте сеть или '
            'соберите домашку вручную.': 'network',
            'other: Сервис разбора вернул ошибку (500).': 'other',
        }
        for text, kind in cases.items():
            with self.subTest(text=text):
                self.assertEqual(m.error_kind(text), kind)

    def test_empty_string_is_no_error(self):
        self.assertIsNone(m.error_kind(''))
        self.assertIsNone(m.error_kind(None))

    def test_connection_at_timeout_is_timeout(self):
        text = 'other: Не удалось связаться с сервисом разбора запроса.'
        self.assertEqual(m.error_kind(text, latency_ms=24800, timeout_ms=25000), 'timeout')
        self.assertEqual(m.error_kind(text, latency_ms=3000, timeout_ms=25000), 'network')


class BrokenFormulaTests(SimpleTestCase):
    def test_broken(self):
        self.assertTrue(m.is_broken_formula('$' + '\x0c' + 'rac{1}{2}$'))
        self.assertTrue(m.is_broken_formula('2 ' + '\t' + 'imes 3'))
        self.assertTrue(m.is_broken_formula('\x08' + 'eta'))
        self.assertTrue(m.is_broken_formula('\\left( x ' + '\r' + 'ight)'))

    def test_not_broken(self):
        self.assertFalse(m.is_broken_formula('текст\nс переносом'))
        self.assertFalse(m.is_broken_formula('$\\frac{1}{2}$'))
        self.assertFalse(m.is_broken_formula('столбец\tтаблицы'))
        self.assertFalse(m.is_broken_formula(''))

    def test_near_cap(self):
        self.assertTrue(m.near_cap('x' * 7920, 8000))
        self.assertFalse(m.near_cap('x' * 7919, 8000))


class StaffSliceTests(SimpleTestCase):
    users = [{'id': 1, 'is_staff': True, 'is_superuser': False},
             {'id': 2, 'is_staff': False, 'is_superuser': True},
             {'id': 3, 'is_staff': False, 'is_superuser': False},
             {'id': 4, 'is_staff': False, 'is_superuser': False}]

    def test_team_file(self):
        self.assertEqual(m.read_team_ids(['3', '', '# Андрей', '  7  # друг']), {3, 7})

    def test_no_staff_removes_flags_and_team_file(self):
        staff = m.staff_ids(self.users, m.read_team_ids(['3']))
        self.assertEqual(staff, {1, 2, 3})
        data = {'users': [dict(u, role='student') for u in self.users],
                'events': [], 'ai': [], 'search': [], 'solves': [], 'opened': set(),
                'topics': {},
                'turns': [turn(i, u, minutes=i) for i, u in enumerate([1, 2, 3, 4, 4])]}
        cut = m.sliced(data, staff)
        self.assertEqual({t['user_id'] for t in cut['turns']}, {4})
        self.assertEqual([u['id'] for u in cut['users']], [4])

    def test_guest_survives_slice(self):
        self.assertEqual(m.without([{'user_id': None}, {'user_id': 1}], {1}),
                         [{'user_id': None}])


class BlockTests(SimpleTestCase):
    def data(self, turns, events=()):
        return {'users': [{'id': u, 'role': 'student'} for u in (1, 2, 3)],
                'events': list(events), 'turns': turns, 'ai': [], 'search': [],
                'solves': [], 'opened': set(), 'topics': {1: ['Спрос']}}

    def test_modes_sum_to_one(self):
        turns = [turn(1, 1, mode='free'), turn(2, 1, mode='method'),
                 turn(3, 2, mode='theory'), turn(4, 2, mode='check')]
        c = m.block_c(self.data(turns))
        self.assertAlmostEqual(sum(v['turn_share'] for v in c['modes'].values()), 1.0)

    def test_losses(self):
        turns = [turn(1, 1, error='limit: На сегодня лимит обращений исчерпан (30 в сутки).',
                      reply=''),
                 turn(2, 1, reply='2 \t' + 'imes 3'), turn(3, 2), turn(4, 2, reply='y' * 8000)]
        d = m.block_d(self.data(turns), 8000, 10000)
        self.assertEqual(d['kinds']['personal_limit']['n'], 1)
        self.assertEqual(d['broken'], 1)
        self.assertEqual(d['near_cap'], 1)

    def test_cost_total_exact(self):
        turns = [turn(1, 1, cost='0.001234'), turn(2, 2, cost='0.002000')]
        e = m.block_e(self.data(turns), {'glm-5.3': (1.4, 4.4), 'glm-5.3-flash': (0.15, 0.5)})
        self.assertEqual(e['cost']['total'], '0.003234')

    def test_thread_sizes(self):
        turns = [turn(1, 1, thread='a'), turn(2, 1, thread='a'), turn(3, 2, thread='b')]
        b = m.block_b(self.data(turns))
        self.assertEqual(b['threads'], 2)
        self.assertEqual(b['single_share'], 0.5)

    def test_week_is_moscow_monday(self):
        # Воскресенье 22:30 UTC — это уже понедельник по Москве.
        sunday_late = datetime(2026, 9, 20, 22, 30, tzinfo=timezone.utc)
        self.assertEqual(m.week_start(sunday_late).isoformat(), '2026-09-21')
