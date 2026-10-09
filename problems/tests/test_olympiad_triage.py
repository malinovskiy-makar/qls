"""Разбор очереди «на глаза»: ярусы, судья, перечитывание, пакет для глаз.

Поставщик — заглушка (тот же путь через настоящий `core.run`, что у
боевого прогона). Страницы и PNG — выдуманные, во временной папке.
"""
import json
import os

from django.test import SimpleTestCase

from problems.olympiad_audit import assemble, judge, review_pack, transcribe, triage
from problems.tests.test_olympiad_digitize import (PARA, DigitizeBase, StubProvider, make_png,
                                                   page_reply)

FULL = [{'type': 'task', 'number': '1', 'text': '\n\n'.join(PARA)}]
SHORT = [{'type': 'task', 'number': '1', 'text': PARA[0]}]


def rec(**extra):
    """Запись страницы v2 «на глаза» со слоем."""
    base = {'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/abc', 'page': 1, 'pages': 3,
            'kind': 'tasks', 'has_layer': True, 'needs_eyes': True,
            'needs_eyes_reasons': ['расходится со слоем PDF'], 'status': 'needs_eyes',
            'layer_ratio': 0.95, 'numbers_ok': True, 'numbers_missing': [],
            'numbers_extra': []}
    return {**base, **extra}


def verdict_json(issues=(), numbers=(), ok=None):
    return json.dumps({'ok': (not issues) if ok is None else ok,
                       'issues': [{'kind': 'пропуск', 'where': 'низ', 'detail': d}
                                  for d in issues],
                       'numbers': [{'number': n, 'on_image': a, 'in_transcript': b}
                                   for n, a, b in numbers]}, ensure_ascii=False)


class TierTests(SimpleTestCase):
    def test_1_tiers_follow_real_risk(self):
        """A — расхождение со слоем, нехватка чисел, судья-скан, сбой формата;
        B — только лишние числа; C — плановая выборка скана; B не A."""
        cases = [
            (rec(layer_ratio=0.5), 'A'),
            (rec(layer_ratio=0.99, numbers_missing=['100']), 'A'),
            (rec(layer_ratio=None), 'A'),
            (rec(layer_ratio=0.99, numbers_extra=['7']), 'B'),
            (rec(layer_ratio=0.99, numbers_missing=['1'], numbers_extra=['7']), 'A'),
            (rec(has_layer=False, layer_ratio=None,
                 needs_eyes_reasons=['скан: выборка каждой 5-й страницы']), 'C'),
            (rec(has_layer=False, layer_ratio=None,
                 needs_eyes_reasons=['скан: выборка каждой 5-й страницы',
                                     'судья нашёл расхождения']), 'A'),
            (rec(needs_eyes_reasons=['сбой формата ответа'], layer_ratio=0.99), 'A'),
        ]
        for record, tier in cases:
            self.assertEqual(triage.classify(record)[0], tier, record)
        self.assertIsNone(triage.classify(rec(needs_eyes=False)))

    def test_2_control_sample_size_and_determinism(self):
        keys = [f'pages/x/p{n}' for n in range(1, 701)]
        sample = triage.control_sample(keys, 'B')
        self.assertEqual(len(sample), 35)               # 5 % от 700
        self.assertTrue(sample <= set(keys))
        self.assertEqual(sample, triage.control_sample(keys, 'B'))
        self.assertEqual(len(triage.control_sample(keys[:100], 'B')), 20)   # минимум 20
        self.assertEqual(len(triage.control_sample(keys[:7], 'C')), 7)      # ярус меньше

    def test_3_urgency_by_bank(self):
        bank = triage.bank_keys(
            [{'ref_event_matched': 'e1', 'ref_number_matched': '2'},
             {'best_any_event': 'e2', 'best_any_number': '1', 'best_any_fuzzy': '0.9'},
             {'best_any_event': 'e3', 'best_any_number': '1', 'best_any_fuzzy': '0.4'}],
            ['official:e4:3'])
        self.assertEqual(bank, {('e1', '2'), ('e2', '1'), ('e4', '3')})
        self.assertEqual(triage.urgency([('e1', '2', '', 'условие')], bank)[0],
                         triage.URGENT_UPDATE)
        self.assertEqual(triage.urgency([('e1', '2', '', 'условие'),
                                         ('e3', '1', '', 'условие')], bank)[0],
                         triage.URGENT_NEW)
        self.assertEqual(triage.urgency([], bank), (triage.NOT_URGENT, 2))

    def test_4_plan_selects_judge_pages_and_norm(self):
        records = [rec(page=n, layer_ratio=0.5) for n in range(1, 4)]              # A
        records += [rec(page=n, layer_ratio=0.99, numbers_extra=['7'])
                    for n in range(10, 40)]                                         # B ×30
        v2 = [{'event_id': 'e1', 'number': '1', 'task_variant': '',
               'source_pages': ['raw/pdf/t.pdf#p1'], 'solution_pages': [],
               'criteria_pages': []}]
        plan = triage.build_plan(records, v2, {'raw/pdf/t.pdf': 'pages/abc'}, set())
        by_page = {r['страница']: r for r in plan}
        self.assertEqual(by_page['pages/abc/p1']['срочность'], triage.URGENT_NEW)
        self.assertEqual(by_page['pages/abc/p2']['срочность'], triage.NOT_URGENT)
        judged = set(triage.pages_to_judge(plan))
        control = {r['страница'] for r in plan if r['контроль']}
        self.assertEqual(len(control), 20)
        self.assertTrue(all(by_page[k]['ярус'] == 'B' for k in control))
        self.assertEqual(judged, {'pages/abc/p1', 'pages/abc/p2', 'pages/abc/p3'} | control)
        self.assertEqual(triage.norm_pages(plan) & judged, set())
        self.assertEqual(len(triage.norm_pages(plan)), 10)


class VerdictTests(SimpleTestCase):
    def parse(self, text, expected=()):
        return judge.parse_verdict(transcribe.tolerant_parse(text), expected)

    def test_5_strict_json(self):
        good = self.parse(verdict_json())
        self.assertEqual((good['ok'], good['issues']), (True, []))
        bad = ['не JSON', '{"issues": []}', '{"ok": "да", "issues": []}', '{"ok": true}',
               '{"ok": false, "issues": [{"kind": "пропуск"}]}',
               '{"ok": false, "issues": ["строка"]}']
        for text in bad:
            with self.assertRaises(judge.BadVerdict, msg=text):
                self.parse(text)
        # Чисел для проверки просили — список обязателен и с bool-полями.
        with self.assertRaises(judge.BadVerdict):
            self.parse('{"ok": true, "issues": []}', expected=['100'])
        with self.assertRaises(judge.BadVerdict):
            self.parse('{"ok": true, "issues": [], "numbers": [{"number": "100"}]}', ['100'])
        # ok=false без объяснения — всё равно замечание (в сомнении не проходит).
        unclear = self.parse('{"ok": false, "issues": []}')
        self.assertEqual(len(unclear['issues']), 1)

    def test_6_status_rule(self):
        """0 замечаний и нет реального пропуска числа → ok_judge; иначе needs_fix."""
        ok = self.parse(verdict_json(numbers=[('100', False, False)]), ['100'])
        self.assertEqual(judge.decide_status(ok), 'ok_judge')     # числа нет на картинке
        found = self.parse(verdict_json(numbers=[('100', True, True)]), ['100'])
        self.assertEqual(judge.decide_status(found), 'ok_judge')  # в расшифровке есть
        lost = self.parse(verdict_json(numbers=[('100', True, False)]), ['100'])
        self.assertEqual(lost['real_missing'], ['100'])
        self.assertEqual(judge.decide_status(lost), 'needs_fix')
        silent = self.parse(verdict_json(numbers=[]), ['100'])    # судья промолчал
        self.assertEqual(judge.decide_status(silent), 'needs_fix')
        remark = self.parse(verdict_json(['строка пропущена']))
        self.assertEqual(judge.decide_status(remark), 'needs_fix')

    def test_7_transcript_for_judge_is_readable(self):
        text = judge.judge_transcript(transcribe.clean_blocks(
            [{'type': 'task', 'number': '2', 'points': 6, 'text': 'Условие'},
             {'type': 'footer', 'text': 'Колонтитул'}]))
        self.assertIn('№ 2', text)
        self.assertIn('6 баллов', text)
        self.assertNotIn('Колонтитул', text)

    def test_7a_answer_field_is_shown_to_judge_as_part_of_block(self):
        """Поле answer судье — с пометкой «часть блока» (не голая строка «Ответ:»,
        которую он принимал за лишнее), человеку в пакете — как есть."""
        blocks = [{'type': 'task', 'number': '1', 'text': 'Выберите (отмечено) вариант 2',
                   'answer': 'ОТВЕТ-ДУБЛЬ'}]
        for_judge = judge.judge_user_text('pages/a/p1', blocks, [])
        self.assertIn('ОТВЕТ-ДУБЛЬ', for_judge)
        self.assertIn('часть блока', for_judge)
        self.assertNotIn('Ответ: ОТВЕТ-ДУБЛЬ', for_judge)
        self.assertIn('Ответ: ОТВЕТ-ДУБЛЬ', judge.judge_transcript(blocks))
        self.assertIn('Поле answer', judge.JUDGE_PROMPT)
        patches = {
            'p1': {'phase': 'judge', 'judge': {'issues': [{'detail': 'Строка «Ответ: 2» лишняя'}]}},
            'p2': {'phase': 'judge', 'judge': {'issues': [{'detail': 'нет таблицы'}]}},
            'p3': {'phase': 'judge', 'judge_prev': {}, 'judge': {
                'issues': [{'detail': 'Ответ'}]}},
            'p4': {'phase': 'reread', 'judge': {'issues': [{'detail': 'Ответ'}]}}}
        self.assertEqual(judge.answer_artifact_pages(patches), ['p1'])


class HintProvider(StubProvider):
    """Заглушка, запоминающая тексты запросов."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_texts = []

    def complete(self, system_blocks, user_text, schema, model, max_tokens,
                 timeout=None, images=None):
        self.user_texts.append(user_text)
        return super().complete(system_blocks, user_text, schema, model, max_tokens,
                                timeout, images)


class RunnerBase(DigitizeBase):
    def setUp(self):
        super().setUp()
        self.costs = transcribe.CostLog(os.path.join(self.root, 'triage_cost.jsonl'))

    def runner(self, cls, provider):
        return cls(root=self.root, provider=provider, budget=transcribe.Budget(1.0, 0.001),
                   cost_log=self.costs, workers=1, sleep=lambda _s: None,
                   plan={'pages/abc/p1': {'ярус': 'A', 'контроль': ''}})

    def write_v2(self, **extra):
        path = os.path.join(self.root, 'pages/abc/p1.json')
        transcribe.Transcriber._write(path, rec(blocks=SHORT, numbers_missing=['100'],
                                                layer_ratio=0.5, numbers_ok=False, **extra))
        with open(path, 'rb') as handle:
            self.v2_bytes = handle.read()
        return path

    def assert_v2_untouched(self, path):
        with open(path, 'rb') as handle:
            self.assertEqual(handle.read(), self.v2_bytes)

    def patch(self):
        return triage.read_json(triage.v3_path(self.root, 'pages/abc', 1))


class JudgeRunTests(RunnerBase):
    def test_8_invalid_json_one_retry_then_ok(self):
        v2 = self.write_v2()
        provider = StubProvider(['не json', verdict_json(numbers=[('100', False, False)])])
        status = self.runner(judge.JudgeRunner, provider).transcribe_page(self.job())
        self.assertEqual((status, provider.calls), ('ok_judge', 2))
        self.assertEqual(self.patch()['status'], 'ok_judge')
        self.assert_v2_untouched(v2)

    def test_9_two_invalid_answers_stay_for_eyes(self):
        self.write_v2()
        provider = StubProvider(['не json'])
        status = self.runner(judge.JudgeRunner, provider).transcribe_page(self.job())
        self.assertEqual((status, provider.calls), ('judge_error', 2))   # один повтор, не больше
        self.assertEqual(self.patch()['status'], 'judge_error')
        self.assertEqual(judge.judge_todo(['pages/abc/p1'], self.root), ['pages/abc/p1'])

    def test_10_remark_or_real_missing_number_is_needs_fix(self):
        for reply in (verdict_json(['пропущена строка']),
                      verdict_json(numbers=[('100', True, False)])):
            self.write_v2()
            status = self.runner(judge.JudgeRunner, StubProvider([reply])).transcribe_page(
                self.job())
            self.assertEqual(status, 'needs_fix', reply)
            self.assertEqual(self.patch()['status'], 'needs_fix')

    def test_11_reread_selection(self):
        """На перечитывание идут только needs_fix; остальные — нет."""
        for page, status in enumerate(('ok_judge', 'needs_fix', 'judge_error', 'fixed',
                                       'human', 'needs_fix'), 1):
            triage.write_json_atomic(triage.v3_path(self.root, 'pages/abc', page),
                                     {'status': status})
        keys = [f'pages/abc/p{n}' for n in range(1, 7)]
        self.assertEqual(judge.select_for_reread(keys, self.root),
                         ['pages/abc/p2', 'pages/abc/p6'])


class RereadTests(RunnerBase):
    def judged(self, reply):
        v2 = self.write_v2()
        self.runner(judge.JudgeRunner, StubProvider([reply])).transcribe_page(self.job())
        return v2

    def test_12_reread_fixed_writes_only_v3(self):
        v2 = self.judged(verdict_json(['пропущены абзацы 2 и 3'],
                                      numbers=[('100', True, False)]))
        provider = HintProvider([page_reply(FULL), verdict_json(numbers=[])])
        status = self.runner(judge.RereadRunner, provider).transcribe_page(self.job())
        self.assertEqual((status, provider.calls), ('fixed', 2))    # перечитывание + судья
        patch = self.patch()
        self.assertEqual(patch['chosen'], 'v3')
        self.assertEqual(patch['blocks'][0]['text'], FULL[0]['text'])
        self.assertTrue(patch['numbers_ok'])
        self.assert_v2_untouched(v2)                                 # старый файл цел
        # Подсказка: замечания судьи и недостающие числа слоя.
        self.assertIn('пропущены абзацы 2 и 3', provider.user_texts[0])
        self.assertIn('100', provider.user_texts[0])
        self.assertIn('если нет — не добавляй', provider.user_texts[0])
        # Одна попытка: fixed больше не выбирается на перечитывание.
        self.assertEqual(judge.select_for_reread(['pages/abc/p1'], self.root), [])

    def test_13_reread_still_flagged_is_human_with_one_attempt(self):
        v2 = self.judged(verdict_json(['а', 'б']))
        provider = HintProvider([page_reply(FULL), verdict_json(['а'])])
        status = self.runner(judge.RereadRunner, provider).transcribe_page(self.job())
        self.assertEqual(status, 'human')
        # Замечаний стало меньше (2 замечания и непроверенное число → 1): берём новое.
        self.assertEqual(self.patch()['chosen'], 'v3')
        self.assert_v2_untouched(v2)
        self.assertEqual(judge.select_for_reread(['pages/abc/p1'], self.root), [])

    def test_14_reread_not_better_keeps_old_text(self):
        self.judged(verdict_json(['а']))        # 1 замечание + число 100 без ответа = 2
        provider = HintProvider([page_reply(FULL), verdict_json(['а', 'б'])])    # 2: не лучше
        self.runner(judge.RereadRunner, provider).transcribe_page(self.job())
        patch = self.patch()
        self.assertEqual((patch['status'], patch['chosen']), ('human', 'v2'))
        self.assertNotIn('blocks', patch)
        self.assertIn('blocks', patch['reread'])                     # перечитанное — для глаз


class OverlayTests(RunnerBase):
    def apply(self, patch, norm=()):
        if patch:
            triage.write_json_atomic(triage.v3_path(self.root, 'pages/abc', 1), patch)
        return triage.PageOverlay(self.root, norm=norm).apply('pages/abc', 1, rec(blocks=SHORT))

    def test_15_overlay_by_status(self):
        self.assertTrue(self.apply(None)['needs_eyes'])
        self.assertTrue(self.apply({'status': 'needs_fix'})['needs_eyes'])
        self.assertTrue(self.apply({'status': 'judge_error'})['needs_eyes'])
        ok = self.apply({'status': 'ok_judge'})
        self.assertEqual((ok['needs_eyes'], ok['blocks']), (False, SHORT))
        fixed = self.apply({'status': 'fixed', 'blocks': FULL, 'layer_ratio': 0.99})
        self.assertEqual((fixed['needs_eyes'], fixed['blocks'], fixed['layer_ratio']),
                         (False, FULL, 0.99))
        human = self.apply({'status': 'human', 'chosen': 'v3', 'blocks': FULL})
        self.assertEqual((human['needs_eyes'], human['blocks']), (True, FULL))
        kept = self.apply({'status': 'human', 'chosen': 'v2'})
        self.assertEqual((kept['needs_eyes'], kept['blocks']), (True, SHORT))

    def test_16_norm_pages_only_without_patch(self):
        out = triage.PageOverlay(self.root, norm={'pages/abc/p1'}).apply('pages/abc', 1, rec())
        self.assertFalse(out['needs_eyes'])
        self.assertEqual(out['status'], 'ok_norm')

    def test_17_assemble_reads_overlay_not_v2(self):
        """Сборка с заплаткой берёт исправленный текст; без неё — старый."""
        self.write_v2()
        triage.write_json_atomic(triage.v3_path(self.root, 'pages/abc', 1),
                                 {'status': 'fixed', 'blocks': FULL, 'layer_ratio': 0.99})
        self.assertEqual(assemble.load_page(self.root, 'pages/abc', 1)['blocks'], SHORT)
        overlay = triage.PageOverlay(self.root)
        self.assertEqual(assemble.load_page(self.root, 'pages/abc', 1, overlay)['blocks'], FULL)


class CompareTests(SimpleTestCase):
    def test_18_invariants(self):
        def row(event, number, text, **extra):
            return {'event_id': event, 'number': number, 'task_variant': '',
                    'statement_md': text, 'solution_md': '', 'criteria_md': '', **extra}
        old = [row('e1', '1', 'a'), row('e1', '2', ''), row('e2', '1', 'b')]
        new = [row('e1', '1', 'a+'), row('e1', '2', '')]
        report = triage.compare_versions(old, new, {'e1': 2, 'e2': 1})
        self.assertEqual(report['комплектов, где v3 меньше v2'], {'e2': (1, 0)})
        self.assertEqual(report['пустых statement_md v3'], 1)
        self.assertEqual(report['заданий с изменённым текстом'], [('e1', '1', '')])
        self.assertEqual(report['комплектов, совпадающих с v1 по числу заданий'], '1 из 2')


class ReviewPackTests(DigitizeBase):
    def items(self, count, urgent=0):
        plan, patches, records = [], {}, {}
        for n in range(1, count + 1):
            key = f'pages/abc/p{n}'
            # Срочные — с самыми поздними ключами: порядок по ключу их не вынесет вперёд.
            label = triage.URGENT_NEW if n > count - urgent else triage.NOT_URGENT
            plan.append({'страница': key, 'файл': 'raw/pdf/t.pdf', 'комплекты': 'e1',
                         'ярус': 'A', 'причина': '', 'срочность': label,
                         'задания': f'e1#{n}', 'контроль': ''})
            patches[key] = {'status': 'human', 'tier': 'A', 'judge_before': {
                'issues': [{'kind': 'пропуск', 'detail': f'пропущена <b>строка</b> {n}'}],
                'real_missing': []}}
            records[key] = rec(page=n, blocks=SHORT)
            make = os.path.join(self.root, 'pages/abc', f'p{n}.png')
            make_png(make)
        patches['pages/abc/p900'] = {'status': 'fixed'}          # разобрана — не в пакете
        patches['pages/abc/p901'] = {'status': 'ok_judge'}
        return review_pack.build_items(plan, patches, records)

    def test_19_only_remainder_urgent_first(self):
        items = self.items(6, urgent=2)
        self.assertEqual(len(items), 6)
        self.assertTrue(all(i['status'] == 'human' for i in items))
        self.assertEqual([i['urgency'] for i in items][:2], [triage.URGENT_NEW] * 2)
        self.assertEqual({i['urgency'] for i in items[2:]}, {triage.NOT_URGENT})

    def test_20_one_pack_or_two(self):
        self.assertEqual(list(review_pack.split_items(self.items(10))), [''])
        two = review_pack.split_items(self.items(151, urgent=40))
        self.assertEqual({k: len(v) for k, v in two.items()}, {'urgent': 40, 'other': 111})

    def test_21_pack_files_and_escaping(self):
        items = self.items(3, urgent=1)
        result = review_pack.build_pack(self.root, items)
        index = os.path.join(self.root, 'human_review', 'index.html')
        with open(index, encoding='utf-8') as handle:
            page = handle.read()
        self.assertEqual(result['packs'], {'общий': 3})
        self.assertIn('pages/abc/p1', page)
        self.assertIn('пропущена &lt;b&gt;строка&lt;/b&gt; 1', page)    # экранировано
        self.assertNotIn('<b>строка</b>', page)
        self.assertTrue(os.path.isfile(os.path.join(self.root, 'human_review', 'img', 'abc_p1.png')))
        with open(os.path.join(self.root, 'human_review.csv'), encoding='utf-8-sig') as handle:
            self.assertEqual(len(handle.read().strip().splitlines()), 4)   # шапка + 3

    def test_22_two_packs_have_entry_index(self):
        result = review_pack.build_pack(self.root, self.items(151, urgent=40))
        self.assertEqual(result['packs'], {'urgent': 40, 'other': 111})
        for pack in ('urgent', 'other'):
            self.assertTrue(os.path.isfile(os.path.join(self.root, 'human_review', pack,
                                                         'index.html')))
        with open(result['index'], encoding='utf-8') as handle:
            self.assertIn('urgent/index.html', handle.read())


class ControlPackTests(DigitizeBase):
    def test_23_candidates_are_judge_passed_tier_a(self):
        plan = [{'страница': f'pages/a/p{n}', 'ярус': tier}
                for n, tier in enumerate('AAABA', 1)]
        patches = {
            'pages/a/p1': {'status': 'ok_judge', 'phase': 'judge'},
            'pages/a/p2': {'status': 'needs_fix', 'phase': 'judge'},
            'pages/a/p3': {'status': 'fixed', 'phase': 'reread'},
            'pages/a/p4': {'status': 'ok_judge', 'phase': 'judge'},      # ярус B
            'pages/a/p5': {'status': 'ok_judge', 'phase': 'judge'}}
        self.assertEqual(review_pack.control_candidates(plan, patches),
                         ['pages/a/p1', 'pages/a/p5'])

    def test_24_pick_is_reproducible_and_sized(self):
        pool = [('vp', f'pages/a/p{n}') for n in range(100)] + \
               [('mosh', f'pages/b/p{n}') for n in range(100)]
        picked = review_pack.pick_control(pool)
        self.assertEqual(len(picked), 30)
        self.assertEqual(picked, review_pack.pick_control(list(reversed(pool))))
        self.assertNotEqual(picked, review_pack.pick_control(pool, seed=1))
        self.assertEqual(len(review_pack.pick_control(pool[:5])), 5)

    def test_25_control_pack_hides_judge_marks(self):
        digitized = os.path.join(self.root, 'dig')
        make_png(os.path.join(digitized, 'pages/abc/p1.png'))
        entry = {'olympiad': 'vp', 'digitized': digitized, 'key': 'pages/abc/p1',
                 'blocks': SHORT, 'tasks': 'e1#3', 'events': 'e1'}
        out = os.path.join(self.root, 'control')
        review_pack.build_control_pack([entry], out)
        with open(os.path.join(out, 'index.html'), encoding='utf-8') as handle:
            page = handle.read()
        for hidden in ('ok_judge', 'срочн', 'ярус', 'прошл'):
            self.assertNotIn(hidden, page)
        self.assertIn('pages/abc/p1', page)
        self.assertTrue(os.path.isfile(os.path.join(out, 'img', 'vp_abc_p1.png')))
        with open(os.path.join(out, 'control_marks.csv'), encoding='utf-8-sig') as handle:
            self.assertIn('ошибок найдено', handle.read())


class AnswerRejudgeTests(RunnerBase):
    def human_page(self):
        v2 = self.write_v2()
        self.runner(judge.JudgeRunner, StubProvider([verdict_json(['нет ответа'])])
                    ).transcribe_page(self.job())
        provider = HintProvider([page_reply(FULL), verdict_json(['пропущен ответ 0,1'])])
        self.runner(judge.RereadRunner, provider).transcribe_page(self.job())
        self.assertEqual(self.patch()['status'], 'human')
        return v2

    def test_26_selection_only_human_with_answer_remark(self):
        self.human_page()
        patches = judge.v3_statuses(self.root)
        self.assertEqual(judge.answer_rejudge_pages(patches), ['pages/abc/p1'])
        self.assertEqual(judge.answer_rejudge_pages({'k': {**patches['pages/abc/p1'],
                                                           'rejudge': {}}}), [])

    def test_27_both_versions_judged_clean_reread_is_fixed(self):
        v2 = self.human_page()
        provider = StubProvider([verdict_json(['а', 'б']), verdict_json()])
        status = self.runner(judge.AnswerRejudgeRunner, provider).transcribe_page(self.job())
        patch = self.patch()
        self.assertEqual((status, provider.calls, patch['chosen']), ('fixed', 2, 'v3'))
        self.assertIn('blocks', patch)
        self.assertEqual(patch['rejudge']['status'], 'human')
        self.assert_v2_untouched(v2)

    def test_28_old_text_clean_is_ok_judge_without_blocks(self):
        self.human_page()
        provider = StubProvider([verdict_json(numbers=[('100', False, False)]),
                                 verdict_json(['хуже'])])
        status = self.runner(judge.AnswerRejudgeRunner, provider).transcribe_page(self.job())
        patch = self.patch()
        self.assertEqual((status, patch['chosen']), ('ok_judge', 'v2'))
        self.assertNotIn('blocks', patch)
        overlay = triage.PageOverlay(self.root).apply('pages/abc', 1, rec(blocks=SHORT))
        self.assertEqual((overlay['needs_eyes'], overlay['blocks']), (False, SHORT))

    def test_29_judge_failure_keeps_page_human(self):
        self.human_page()
        before = self.patch()
        status = self.runner(judge.AnswerRejudgeRunner, StubProvider(['не json'])
                             ).transcribe_page(self.job())
        self.assertEqual(status, 'judge_error')
        self.assertEqual(self.patch(), before)


    def test_31_tie_keeps_old_text(self):
        """Замечаний поровну — остаётся прежний текст (v2), перечитанный не берётся."""
        self.human_page()
        provider = StubProvider([verdict_json(['а'], numbers=[('100', False, False)]),
                                 verdict_json(['б'])])
        status = self.runner(judge.AnswerRejudgeRunner, provider).transcribe_page(self.job())
        patch = self.patch()
        self.assertEqual((status, patch['chosen']), ('human', 'v2'))
        self.assertNotIn('blocks', patch)


class SkeletonGuardTests(RunnerBase):
    def test_30_human_text_with_changed_structure_is_not_applied(self):
        """Реклассификация блока task→solution на human-странице не должна
        тихо убрать задание из сборки; на fixed (подтверждена судьёй) — можно."""
        base = rec(blocks=[{'type': 'task', 'number': '6.1', 'text': 'условие'}])
        moved = [{'type': 'solution', 'number': '6.1', 'text': 'решение'}]
        triage.write_json_atomic(triage.v3_path(self.root, 'pages/abc', 1),
                                 {'status': 'human', 'chosen': 'v3', 'blocks': moved})
        overlay = triage.PageOverlay(self.root)
        out = overlay.apply('pages/abc', 1, base)
        self.assertEqual((out['blocks'][0]['type'], out['needs_eyes']), ('task', True))
        triage.write_json_atomic(triage.v3_path(self.root, 'pages/abc', 1),
                                 {'status': 'fixed', 'blocks': moved})
        self.assertEqual(overlay.apply('pages/abc', 1, base)['blocks'][0]['type'], 'solution')
