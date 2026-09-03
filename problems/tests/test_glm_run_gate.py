# -*- coding: utf-8 -*-
"""glm_run_gate — гейт перед боевым прогоном (Фаза 3 задания сессии
02.09.2026, четвёртая пересъёмка).

Главное, что здесь проверяется: гейт ЗАКРЫВАЕТСЯ на каждом из восьми
условий «результат негоден» по отдельности. Гейт, который всегда зелёный,
хуже отсутствия гейта — он создаёт видимость проверки перед тратой $70.
"""
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems.enrich import taxonomy
from problems.management.commands import glm_run_gate as gate
from problems.models import AutoTopicAssignment, Problem, Topic

CANON_TOPIC = 'Спрос и предложение'  # -> тема v2 «3» в CANON_TO_V2

#: Тридцать разных понятий без единой цифры — заготовка для выборки, где
#: «верхние три термина» покрывают заведомо меньше половины задач.
_CONCEPTS = ['термин ' + letter for letter in 'абвгдеёжзийклмнопрстуфхцчшщэюя']


def _row(problem_id, **overrides):
    """Строка `run_parsed.jsonl`, по всем инвариантам благополучная."""
    row = {
        'problem_id': problem_id,
        'defect': False,
        'call1_ok': True, 'call1_retried': False, 'call1_violations': [],
        'call2_ok': True, 'call2_retried': False, 'call2_violations': [],
        'soft_violations': [], 'dropped_queries': [],
        'topic_primary': '3',
        'topics_secondary': ['4'],
        'tags': ['3.1', '3.2'],
        'given': 'линейные функции спроса и предложения, известны эластичности',
        'find': 'равновесную цену и объём',
        'econ_concepts': ['спрос', 'предложение', 'равновесие'],
        'concepts_offlist': [],
        'task_nature': 'расчётная',
        'features_1': [],
        'topic_confidence': 'высокая',
        'graphical_solution': False,
        'graphical_solution_source': 'none',
        'search_queries': ['рыночное равновесие', 'эластичность спроса',
                           'излишек потребителя', 'потоварный налог',
                           'кривая предложения'],
        'plot': None, 'hints': None,
        'text_quality': 'чистая', 'text_quality_note': '',
        'problem_type': 'тест: короткий ответ',
        'difficulty': 3, 'difficulty_note': '',
        'answer_consistency': 'согласован',
        'title_candidate': 'Рынок кофе',
        'images_sent': 1,
        'tikz': {'replaced': 0, 'truncated': 0},
    }
    row.update(overrides)
    return row


def _metrics(rows, **overrides):
    metrics = {
        'total_processed': len(rows),
        'defects': sum(1 for r in rows if r['defect']),
        'defect_pct': sum(1 for r in rows if r['defect']) / len(rows) * 100,
        'retried_rows': sum(1 for r in rows
                            if r['call1_retried'] or r['call2_retried']),
        'sweep_detector': {'checked': len(rows), 'changed': 0, 'changed_ids': []},
        'problems_image_sent': sum(1 for r in rows if r['images_sent']),
    }
    metrics.update(overrides)
    return metrics


class GlmRunGateTests(TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # ⚠️ Благополучная выборка обязана быть РАЗНООБРАЗНОЙ: 300 задач в
        # одной теме — это условие блокировки №6, и на такой заготовке
        # нельзя проверить ни одно из остальных семи. Темы раздаются по
        # кругу, человеческая тема ставится ПОД неё, чтобы совпадение с
        # человеком было честным 100%, а не случайным.
        pairs = sorted((canon, sorted(ids)[0])
                       for canon, ids in gate.CANON_TO_V2.items())
        # slug задаётся явно: он unique, а автослаг с кириллицы даёт
        # пустую строку — вторая тема упала бы на UNIQUE.
        self.topics = {canon: Topic.objects.create(name=canon, slug='t%d' % i)
                      for i, (canon, _) in enumerate(pairs)}
        self.problems = [Problem.objects.create(statement='Задача %d.' % i)
                        for i in range(gate.CHECKPOINT_SIZE)]
        all_tags = list(taxonomy.tag_ids())
        self.rows = []
        for i, problem in enumerate(self.problems):
            canon, theme_id = pairs[i % len(pairs)]
            problem.topics.add(self.topics[canon])
            self.rows.append(_row(
                problem.id,
                topic_primary=theme_id,
                # вторая тема у каждой третьей — попадает в вилку 25-40%
                topics_secondary=['4'] if i % 3 == 0 else [],
                tags=[all_tags[i % 200], all_tags[(i + 1) % 200]],
                # ⚠️ БЕЗ ЦИФР в названиях понятий: §12.3 запрещает цифру
                # в econ_concepts, и «понятие 7» сломало бы соседний
                # инвариант, а не проверяемый.
                econ_concepts=[_CONCEPTS[i % len(_CONCEPTS)],
                               _CONCEPTS[(i + 7) % len(_CONCEPTS)],
                               _CONCEPTS[(i + 13) % len(_CONCEPTS)]],
                # вилка 2-8%: заполнено у каждой двадцатой
                concepts_offlist=['вне списка'] if i % 20 == 0 else [],
            ))

    def _run(self, rows=None, metrics=None, expect_block=False):
        rows = self.rows if rows is None else rows
        metrics = _metrics(rows) if metrics is None else metrics
        parsed_path = self.tmp / 'parsed.jsonl'
        metrics_path = self.tmp / 'metrics.json'
        out_path = self.tmp / 'gate.json'
        with open(parsed_path, 'w', encoding='utf-8') as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + '\n')
        with open(metrics_path, 'w', encoding='utf-8') as fh:
            json.dump(metrics, fh, ensure_ascii=False)
        kwargs = dict(parsed=str(parsed_path), metrics=str(metrics_path),
                     out=str(out_path))
        if expect_block:
            with self.assertRaises(CommandError):
                call_command('glm_run_gate', **kwargs)
        else:
            call_command('glm_run_gate', **kwargs)
        return json.loads(out_path.read_text(encoding='utf-8'))

    def _tripped(self, result):
        return [b['number'] for b in result['blockers'] if b['tripped']]

    # --- гейт открыт -----------------------------------------------------

    def test_благополучный_прогон_гейт_пропускает(self):
        result = self._run()
        self.assertEqual(result['verdict'], 'РАЗРЕШЁН')
        self.assertEqual(self._tripped(result), [])

    def test_семнадцать_инвариантов_печатаются_всегда(self):
        # 17-й добавлен 03.09.2026 — 95-й процентиль длины `given`. Он
        # справочный (вилки нет): потолок длины снят решением владельца, и
        # осмысленной верхней границы у хвоста без потолка не существует.
        result = self._run()
        self.assertEqual(len(result['invariants']), 17)
        self.assertEqual(result['invariants_total'], 17)
        for inv in result['invariants']:
            self.assertTrue(inv['threshold'])
            self.assertTrue(inv['fact'])

    # --- восемь условий блокировки, каждое по отдельности ----------------

    def test_блокирует_обработано_меньше_300(self):
        rows = self.rows[:299]
        result = self._run(rows, _metrics(rows), expect_block=True)
        self.assertIn(1, self._tripped(result))

    def test_блокирует_брак_пять_процентов(self):
        rows = list(self.rows)
        for row in rows[:15]:  # ровно 5% — порог «>= 5%»
            row['defect'] = True
            row['call1_ok'] = False
        result = self._run(rows, _metrics(rows), expect_block=True)
        self.assertIn(2, self._tripped(result))

    def test_брак_чуть_ниже_пяти_процентов_не_блокирует(self):
        rows = [dict(r) for r in self.rows]
        for row in rows[:14]:  # 4,7%
            row['defect'] = True
            row['call1_ok'] = False
        result = self._run(rows, _metrics(rows))
        self.assertNotIn(2, self._tripped(result))

    def test_блокирует_свип_детектор(self):
        metrics = _metrics(self.rows)
        metrics['sweep_detector'] = {'checked': 300, 'changed': 1,
                                     'changed_ids': [self.problems[0].id]}
        result = self._run(self.rows, metrics, expect_block=True)
        self.assertIn(3, self._tripped(result))

    def test_блокирует_расхождение_с_темой_человека(self):
        # «28» (Математический аппарат) не совпадает почти ни с одной
        # канонической темой, кроме «Математика и оптимизация».
        rows = [dict(r, topic_primary='28') for r in self.rows]
        result = self._run(rows, _metrics(rows), expect_block=True)
        self.assertIn(4, self._tripped(result))

    def test_блокирует_мало_уникальных_тегов(self):
        rows = [dict(r, tags=['3.1']) for r in self.rows]
        result = self._run(rows, _metrics(rows), expect_block=True)
        self.assertIn(5, self._tripped(result))

    def test_блокирует_одна_тема_больше_четверти(self):
        """Треть выборки в одной теме — больше четверти."""
        rows = [dict(r) for r in self.rows]
        for row in rows[:100]:
            row['topic_primary'] = '3'
        result = self._run(rows, _metrics(rows), expect_block=True)
        self.assertIn(6, self._tripped(result))

    def test_блокирует_много_не_задач(self):
        rows = [dict(r) for r in self.rows]
        for row in rows[:40]:  # 13,3%
            row['text_quality'] = 'не_задача'
        result = self._run(rows, _metrics(rows), expect_block=True)
        self.assertIn(7, self._tripped(result))

    def test_блокирует_мало_задач_с_картинкой(self):
        metrics = _metrics(self.rows)
        metrics['problems_image_sent'] = 39
        result = self._run(self.rows, metrics, expect_block=True)
        self.assertIn(8, self._tripped(result))

    def test_ровно_сорок_картинок_не_блокирует(self):
        metrics = _metrics(self.rows)
        metrics['problems_image_sent'] = 40
        result = self._run(self.rows, metrics)
        self.assertNotIn(8, self._tripped(result))

    # --- отдельные детали замера ----------------------------------------

    def test_автоназначенная_тема_не_считается_проставленной_человеком(self):
        """`auto_assign_topics` пишет в тот же M2M, что и человек. Считать
        его человеком значило бы сверять модель с другой моделью."""
        for problem in self.problems:
            for topic in problem.topics.all():
                AutoTopicAssignment.objects.create(
                    problem=problem, topic=topic, neighbor_votes=7)
        _, compared, _ = gate.human_topic_match(self.rows)
        self.assertEqual(compared, 0)

    def test_вилки_не_блокируют_запуск(self):
        """`concepts_offlist` вне вилки 2-8% — расхождение инварианта, но
        НЕ условие блокировки: это настройка, чинится на следующем круге
        из уже сохранённых журналов, без второго обращения к API."""
        rows = [dict(r, concepts_offlist=['сравнительное преимущество'])
                for r in self.rows]  # заполнено у 100% вместо 2-8%
        result = self._run(rows, _metrics(rows))
        self.assertEqual(result['verdict'], 'РАЗРЕШЁН')
        offlist = [i for i in result['invariants']
                   if 'concepts_offlist' in i['name']][0]
        self.assertFalse(offlist['passed'])

    def test_цифры_в_защищённых_полях_видны_инварианту(self):
        rows = [dict(r) for r in self.rows]
        rows[0]['given'] = 'цена 100 рублей'
        result = self._run(rows, _metrics(rows))
        digits = [i for i in result['invariants'] if 'Цифры' in i['name']][0]
        self.assertFalse(digits['passed'])
        self.assertEqual(digits['fact'], '1')

    def test_схожесть_запросов_ловит_восемь_перефразировок(self):
        same = ['рыночное равновесие спроса'] * 5
        rows = [dict(r, search_queries=list(same)) for r in self.rows]
        result = self._run(rows, _metrics(rows))
        sim = [i for i in result['invariants'] if 'схожесть' in i['name']][0]
        self.assertFalse(sim['passed'])
