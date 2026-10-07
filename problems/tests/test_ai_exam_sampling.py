"""Экзамен для ИИ: воронка и отбор кандидатов на ВЫДУМАННОМ банке.

Ни одной настоящей задачи: банк собирается фабриками в тестовой базе
(воронка) или прямо словарями (квоты, пачки, порядок взятия).
"""
from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from problems.ai_exam import sampling
from problems.ai_exam.bank import load_records, load_topics
from problems.models import AnswerSecondOpinion, ProblemPart
from problems.tests.factories import make_problem, make_topic

LONG = 'Фирма выпускает товар, спрос задан функцией $Q = 100 - 2P$, издержки $TC = 10Q$. ' * 2
SOLUTION = 'Решение: приравниваем предельную выручку к предельным издержкам. ' * 5
FIGURE = '[[FIGURE:' + 'a' * 64 + ']]'


def dropped_at(records, params):
    """id → ключ фильтра, на котором задача выбыла (None — дошла до пула)."""
    alive = {r['id'] for r in records}
    out = {pk: None for pk in alive}
    current = list(records)
    for key, _label, step in sampling.steps(params):
        current = step(current)
        left = {r['id'] for r in current}
        for pk in alive - left:
            out[pk] = key
        alive = left
    return out


class FunnelTests(TestCase):
    """Каждый из двенадцати фильтров отсекает свою задачу, и только её."""

    def good(self, **kwargs):
        fields = dict(statement=LONG, answer='20', solution=SOLUTION,
                      task_nature='расчётная', answer_consistency='согласован',
                      text_quality='чистая', problem_type='задача с развёрнутым ответом',
                      difficulty=3, topic=self.topic)
        fields.update(kwargs)
        return make_problem(**fields)

    def setUp(self):
        self.topic = make_topic('Тема А', is_canonical=True, order=1)
        side = make_topic('Не канон', is_canonical=False, order=2)
        self.expect = {}
        self.keep = self.good()
        self.expect[self.keep.pk] = None

        cases = [
            ('nature', dict(task_nature='качественная')),
            ('consistency', dict(answer_consistency='ответ_не_совпадает_с_решением')),
            ('text', dict(text_quality='мелкие_дефекты')),
            ('solution', dict(solution='Коротко.')),
            ('solution', dict(solution_needs_review=True)),
            ('single', dict(multiple_problems=True)),
            ('not_test', dict(problem_type='единственный_выбор')),
            ('no_figure', dict(statement=LONG + FIGURE)),
            ('size', dict(statement='Найдите цену.')),
            ('key', dict(answer='вырастет')),
            ('topic', dict(topic=side)),
        ]
        self.relaxable = []
        for key, fields in cases:
            problem = self.good(**fields)
            self.expect[problem.pk] = key
            # Ослабления а, б, в открывают ровно эти три двери.
            if key in ('text', 'key') or fields.get('solution') == 'Коротко.':
                self.relaxable.append(problem.pk)

        # Картинка в условии подпункта — тоже картинка.
        with_part_figure = self.good()
        ProblemPart.objects.create(problem=with_part_figure, label='а',
                                   statement='Найдите по графику ' + FIGURE, answer='5')
        self.expect[with_part_figure.pk] = 'no_figure'

        # Подпунктов больше шести.
        many = self.good()
        for i in range(7):
            ProblemPart.objects.create(problem=many, label=str(i), statement='пункт',
                                       answer='1', order=i)
        self.expect[many.pk] = 'size'

        # Ответ одного из подпунктов — не число.
        part_words = self.good()
        ProblemPart.objects.create(problem=part_words, label='а', answer='5', order=0)
        ProblemPart.objects.create(problem=part_words, label='б', answer='вырастет', order=1)
        self.expect[part_words.pk] = 'key'

        # Группа копий с фаворитом: остаётся фаворит, даже с большим id.
        loser = self.good(dup_group='g1')
        best = self.good(dup_group='g1', dup_is_best=True)
        self.expect[loser.pk], self.expect[best.pk] = 'dup', None
        # Группа без фаворита: остаётся меньший id.
        first = self.good(dup_group='g2')
        second = self.good(dup_group='g2')
        self.expect[first.pk], self.expect[second.pk] = None, 'dup'

        # Второе мнение: открытое расхождение и «права модель» — вон;
        # старое расхождение, после которого модель согласилась, — не мешает.
        now = timezone.now()
        disputed = self.good()
        AnswerSecondOpinion.objects.create(problem=disputed, model='m', agrees=False)
        self.expect[disputed.pk] = 'opinion'
        model_right = self.good()
        AnswerSecondOpinion.objects.create(problem=model_right, model='m', agrees=False,
                                           resolved=True, resolution='model_right')
        self.expect[model_right.pk] = 'opinion'
        settled = self.good()
        AnswerSecondOpinion.objects.create(problem=settled, model='m', agrees=False,
                                           created_at=now - timedelta(days=2))
        AnswerSecondOpinion.objects.create(problem=settled, model='m', agrees=True,
                                           created_at=now)
        self.expect[settled.pk] = None
        bank_right = self.good()
        AnswerSecondOpinion.objects.create(problem=bank_right, model='m', agrees=False,
                                           resolved=True, resolution='bank_right')
        self.expect[bank_right.pk] = None

        # Скрытая из каталога задача в воронку не попадает вовсе.
        self.hidden = self.good(hidden_pending_review=True)

    def test_each_filter_cuts_its_problem(self):
        records = sampling.prepare(load_records())
        got = dropped_at(records, sampling.STRICT)
        self.assertNotIn(self.hidden.pk, got)
        self.assertEqual(got, self.expect)
        # Все двенадцать фильтров кого-то отсекли — беззубых нет.
        self.assertEqual(set(v for v in got.values() if v),
                         {key for key, _l, _s in sampling.steps(sampling.STRICT)})

    def test_funnel_never_grows(self):
        records = sampling.prepare(load_records())
        _pool, counts = sampling.funnel(records, sampling.STRICT)
        numbers = [len(records)] + [n for _k, _l, n in counts]
        self.assertEqual(numbers, sorted(numbers, reverse=True))

    def test_relaxations_open_the_gates(self):
        records = sampling.prepare(load_records())
        params = dict(sampling.STRICT, text_qualities=('чистая', 'мелкие_дефекты'),
                      min_solution=5, none_ok_topics=frozenset([self.topic.pk]))
        got = dropped_at(records, params)
        for pk in self.relaxable:
            with self.subTest(expected=self.expect[pk]):
                self.assertNotEqual(got[pk], self.expect[pk])


def rec(pk, topics=(1,), difficulty=3, answer='20', source_id=None, dup_group=''):
    """Запись банка без базы — для чистых функций отбора."""
    record = {
        'id': pk, 'title': '', 'statement': LONG, 'answer': answer, 'solution': SOLUTION,
        'problem_type': '', 'difficulty': difficulty, 'task_nature': 'расчётная',
        'answer_consistency': 'согласован', 'text_quality': 'чистая',
        'solution_needs_review': False, 'multiple_problems': False,
        'dup_group': dup_group, 'dup_is_best': False, 'parts': [],
        'topics': list(topics), 'source': 'S%s' % source_id if source_id else '',
        'source_id': source_id, 'opinion': None,
    }
    return sampling.prepare([record])[0]


TOPICS = {t: {'id': t, 'name': 'Тема %d' % t, 'order': t} for t in range(1, 5)}


class QuotaTests(SimpleTestCase):
    def test_even_split_and_remainder_to_biggest_pool(self):
        alloc = sampling.quotas({1: 10, 2: 20, 3: 15}, 10, TOPICS)
        self.assertEqual(alloc, {1: 3, 2: 4, 3: 3})

    def test_shortage_moves_to_biggest_leftover_one_per_round(self):
        # Квота 4; у темы 1 только 2 — две задачи уходят темам 2 и 3 по одной.
        alloc = sampling.quotas({1: 2, 2: 10, 3: 9}, 12, TOPICS)
        self.assertEqual(alloc, {1: 2, 2: 5, 3: 5})

    def test_pool_smaller_than_count_takes_everything(self):
        alloc = sampling.quotas({1: 2, 2: 3}, 10, TOPICS)
        self.assertEqual(alloc, {1: 2, 2: 3})

    def test_empty_topics_get_nothing(self):
        alloc = sampling.quotas({1: 0, 2: 6}, 4, TOPICS)
        self.assertEqual(alloc, {2: 4})


class PickTests(SimpleTestCase):
    def test_level_round_and_exact_first(self):
        records = [rec(1, difficulty=1), rec(2, difficulty=4), rec(3, difficulty=3),
                   rec(4, difficulty=3, answer='Q = 7'), rec(5, difficulty=None)]
        rank = {r['id']: 0 for r in records}
        picked = [r['id'] for r in sampling.pick_topic(records, 5, rank)]
        # средняя (exact раньше extracted) → сложная → лёгкая → без оценки → средняя
        self.assertEqual(picked, [3, 2, 1, 5, 4])

    def test_source_cap_while_others_exist(self):
        records = [rec(i, source_id=7) for i in range(1, 6)] + [rec(9, source_id=8)]
        rank = {r['id']: r['id'] for r in records}
        picked = [r['id'] for r in sampling.pick_topic(records, 4, rank)]
        self.assertEqual(picked, [1, 2, 3, 9])

    def test_source_cap_gives_way_when_nothing_else(self):
        records = [rec(i, source_id=7) for i in range(1, 6)]
        rank = {r['id']: r['id'] for r in records}
        self.assertEqual(len(sampling.pick_topic(records, 5, rank)), 5)


class SelectTests(SimpleTestCase):
    def pool(self):
        return [rec(i, topics=(i % 4 + 1,), difficulty=i % 5 + 1, source_id=i % 6)
                for i in range(1, 61)]

    def test_same_seed_same_bytes(self):
        a = sampling.dump_jsonl(sampling.select(self.pool(), TOPICS, 30, 4, 20261007))
        b = sampling.dump_jsonl(sampling.select(self.pool(), TOPICS, 30, 4, 20261007))
        c = sampling.dump_jsonl(sampling.select(self.pool(), TOPICS, 30, 4, 7))
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_chunks_balanced_and_numbered(self):
        rows = sampling.select(self.pool(), TOPICS, 30, 4, 1)
        sizes = [sum(1 for r in rows if r['chunk'] == c) for c in range(1, 5)]
        self.assertEqual(sorted(sizes), [7, 7, 8, 8])
        for chunk in range(1, 5):
            numbers = [r['n'] for r in rows if r['chunk'] == chunk]
            self.assertEqual(numbers, list(range(1, len(numbers) + 1)))
        self.assertEqual(len({r['id'] for r in rows}), 30)

    def test_chunk_order_goes_round_topics(self):
        rows = [r for r in sampling.select(self.pool(), TOPICS, 32, 4, 1) if r['chunk'] == 1]
        self.assertEqual([r['topic'] for r in rows[:4]],
                         ['Тема 1', 'Тема 2', 'Тема 3', 'Тема 4'])

    def test_own_topic_is_the_smaller_pool(self):
        pool = [rec(1, topics=(1, 2))] + [rec(i, topics=(1,)) for i in range(2, 6)]
        self.assertEqual(sampling.own_topics(pool, TOPICS)[1], 2)

    def test_one_per_dup_group_in_pool(self):
        pool = [rec(1, dup_group='g'), rec(2, dup_group='g'), rec(3)]
        kept = sampling._one_per_dup_group(pool)
        self.assertEqual([r['id'] for r in kept], [1, 3])

    def test_row_carries_hash_and_asks(self):
        row = sampling.select([rec(1)], TOPICS, 1, 1, 1)[0]
        self.assertEqual(len(row['statement_hash']), 64)
        self.assertEqual(row['asks'][0]['value'], '20')
        self.assertEqual(row['asks'][0]['kind'], 'exact')
        self.assertEqual(row['level'], sampling.MEDIUM)
