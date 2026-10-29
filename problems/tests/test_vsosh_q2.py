"""ВсОШ v2 (сессия Q2): сведение двух мнений, правило приёма арбитра,
журнал денег. Без сети и без базы — маленькие выдуманные страницы."""
import json
import os
import tempfile
from types import SimpleNamespace

from django.test import SimpleTestCase

from problems.olympiad_audit import vsosh_verify as vv

LAYER = ('Задача 1. (10 баллов) Спрос на товар задан функцией Qd = 100 - 2P, '
         'предложение Qs = 3P - 20. Найдите равновесную цену и объём продаж. '
         'Ответ дайте с точностью до 0,5. Государство вводит налог 5 рублей за единицу товара.')


def rec(*blocks, status='ok'):
    return {'status': status, 'blocks': list(blocks)}


def task(number, text, points=None):
    return {'type': 'task', 'number': number, 'text': text, 'points': points}


def page(layer=LAYER):
    return SimpleNamespace(layer=layer, has_layer=len(layer) >= 80, footers=set(), page=1)


class NumbersTests(SimpleTestCase):
    def test_tex_comma_and_thousands_are_one_number(self):
        self.assertEqual(vv.numbers('$49{,}9$ и 1 000 000 руб.'), vv.numbers('49,9 и 1000000 руб.'))

    def test_option_label_not_glued_to_number(self):
        # «2) 500» — метка варианта и число, а не «2500» (ловушка P2).
        self.assertEqual(vv.numbers('1) 300\n2) 500'), vv.numbers('1) 300 2) 500'))
        self.assertNotIn('2500', vv.numbers('2) 500'))


class AgreeTests(SimpleTestCase):
    A = rec(task('1', 'Спрос $Q_d = 100 - 2P$, предложение $Q_s = 3P - 20$.', 10))

    def test_same_numbers_and_structure_agree(self):
        b = rec(task('1', 'Спрос Qd = 100 − 2P,  предложение Qs = 3P − 20.', 10))
        self.assertEqual(vv.agree(self.A, b), (True, []))

    def test_number_differs(self):
        b = rec(task('1', 'Спрос $Q_d = 100 - 2P$, предложение $Q_s = 3P - 26$.', 10))
        ok, why = vv.agree(self.A, b)
        self.assertFalse(ok)
        self.assertIn('числа', why)

    def test_lost_task_number_is_structure(self):
        b = rec(task('', 'Спрос $Q_d = 100 - 2P$, предложение $Q_s = 3P - 20$.', 10))
        self.assertIn('номера', vv.agree(self.A, b)[1])

    def test_options_and_table_rows_count(self):
        a = rec(task('2', 'Вопрос\n\n- а) да\n- б) нет\n\n| x | y |\n|---|---|\n| 1 | 2 |'))
        b = rec(task('2', 'Вопрос\n\n- а) да\n\n| x | y |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |'))
        why = vv.agree(a, b)[1]
        self.assertIn('варианты', why)
        self.assertIn('таблицы', why)

    def test_error_record_never_agrees(self):
        self.assertEqual(vv.agree(self.A, rec(status='error')), (False, ['нет_ответа']))


def reply(**kw):
    return json.dumps(dict({'decision': 'A', 'evidence': 'Спрос на товар задан функцией',
                            'confidence': 0.95}, **kw), ensure_ascii=False)


class ArbiterRuleTests(SimpleTestCase):
    A = rec(task('1', 'Спрос $Q_d = 100 - 2P$', 10))
    B = rec(task('1', 'Спрос $Q_d = 100 - 3P$', 10))

    def test_confident_with_quote_accepts(self):
        verdict, chosen, why, _ = vv.judge_arbiter(reply(), page(), self.A, self.B)
        self.assertEqual((verdict, why), ('accept_A', []))
        self.assertIs(chosen, self.A)

    def test_choice_b(self):
        verdict, chosen, _w, _d = vv.judge_arbiter(reply(decision='B'), page(), self.A, self.B)
        self.assertEqual(verdict, 'accept_B')
        self.assertIs(chosen, self.B)

    def test_low_confidence_goes_to_retry_or_human(self):
        self.assertEqual(vv.judge_arbiter(reply(confidence=0.8), page(), self.A, self.B)[0], 'retry')
        self.assertEqual(vv.judge_arbiter(reply(confidence=0.7), page(), self.A, self.B)[0], 'human')
        self.assertEqual(vv.judge_arbiter(reply(confidence=0.9), page(), self.A, self.B)[0], 'accept_A')

    def test_quote_not_on_page_is_human(self):
        verdict, chosen, why, _ = vv.judge_arbiter(
            reply(evidence='Кривая Лаффера показывает зависимость'), page(), self.A, self.B)
        self.assertEqual((verdict, chosen), ('human', None))
        self.assertIn('нет_цитаты_со_страницы', why)

    def test_quote_with_foreign_number_is_human(self):
        verdict = vv.judge_arbiter(reply(evidence='налог 7 рублей за единицу товара'),
                                   page(), self.A, self.B)[0]
        self.assertEqual(verdict, 'human')

    def test_scan_quote_only_needs_text(self):
        verdict = vv.judge_arbiter(reply(evidence='что-то со скана'), page(layer=''),
                                   self.A, self.B)[0]
        self.assertEqual(verdict, 'accept_A')

    def test_fix_accepted_only_with_page_numbers(self):
        good = [task('1', 'Спрос $Q_d = 100 - 2P$, налог 5 рублей', 10)]
        verdict, chosen, _w, _d = vv.judge_arbiter(reply(decision='fix', blocks=good),
                                                   page(), self.A, self.B)
        self.assertEqual(verdict, 'accept_fix')
        self.assertEqual(chosen['blocks'][0]['text'], good[0]['text'])
        bad = [task('1', 'Спрос $Q_d = 100 - 7P$', 10)]
        verdict, _c, why, _d = vv.judge_arbiter(reply(decision='fix', blocks=bad),
                                                page(), self.A, self.B)
        self.assertEqual(verdict, 'human')
        self.assertIn('правка_с_числами_не_со_страницы', why)

    def test_human_and_garbage(self):
        self.assertEqual(vv.judge_arbiter(reply(decision='human'), page(), self.A, self.B)[0], 'human')
        self.assertEqual(vv.judge_arbiter('не JSON', page(), self.A, self.B)[0], 'human')


class LedgerTests(SimpleTestCase):
    def test_stops_at_ninety_percent(self):
        with tempfile.TemporaryDirectory() as d:
            led = vv.Ledger(os.path.join(d, 'l.jsonl'), caps={'openai': 10.0})
            led.add(model='gpt-6.1-terra', phase='x', usd=8.5)
            self.assertTrue(led.allow('openai', 0.4))
            self.assertFalse(led.allow('openai', 0.6))
            led.add(model='gpt-6.1-terra', phase='y', usd=0.4)
            self.assertAlmostEqual(led.spent('openai', 'x'), 8.5)
            self.assertAlmostEqual(led.spent('openai'), 8.9)


class KeyGridTests(SimpleTestCase):
    """Фаза 3: ключ из сетки принимается только при согласии двух моделей
    и только если ответ — среди вариантов своего вопроса."""

    from problems.olympiad_audit import vsosh_keys as K

    ROWS = [{'number': 'тест-1', 'statement_md': 'Рост цен — это:\n\n1) инфляция\n2) дефляция\n3) стагфляция'},
            {'number': 'тест-2', 'statement_md': 'Выберите все верные:\n\n- а) спрос\n- б) предложение\n- в) налог'},
            {'number': 'тест-3', 'statement_md': '**Рост урожая уменьшает спрос на пшеницу.**'}]

    def test_norm_answer_forms(self):
        K = self.K
        self.assertEqual(K.norm_answer('**3)**'), ('3',))
        self.assertEqual(K.norm_answer('1, 3'), ('1', '3'))
        self.assertEqual(K.norm_answer('13'), ('1', '3'))
        self.assertEqual(K.norm_answer(['В', 'a']), ('а', 'в'))
        self.assertEqual(K.norm_answer('Неверно'), ('нет',))
        self.assertEqual(K.norm_answer(['1) верно']), ('1',))   # метка с текстом варианта

    def test_options_labels_plain_and_binary(self):
        K = self.K
        self.assertEqual([x[0] for x in K.options(self.ROWS[0]['statement_md'])], ['1', '2', '3'])
        self.assertEqual([x[0] for x in K.options(self.ROWS[1]['statement_md'])], ['а', 'б', 'в'])
        self.assertEqual([x[0] for x in K.options(self.ROWS[2]['statement_md'])], ['да', 'нет'])
        self.assertEqual([x[0] for x in K.options('Что?\n\n- хлеб\n- соль')], ['1', '2'])

    def test_decide_accepts_only_agreement_inside_options(self):
        K = self.K
        a = {'q1': (('3',), 0.95), 'q2': (('а', 'в'), 0.9), 'q3': (('нет',), 0.95)}
        b = {'q1': (('3',), 0.9), 'q2': (('а',), 0.9), 'q3': (('нет',), 0.95)}
        got = [(ans, why) for _r, ans, why in K.decide(self.ROWS, a, b)]
        # Третий вопрос — без напечатанных вариантов: согласие моделей есть,
        # но «да/нет» подставлены по умолчанию — человеку.
        self.assertEqual(got, [(('3',), ''), (None, 'модели_разошлись'),
                               (None, 'варианты_не_напечатаны')])
        rows = [{'number': 'тест-4', 'statement_md': 'Утверждение.\n\n- Да\n- Нет'}]
        self.assertEqual(K.decide(rows, {'q1': (('нет',), 0.9)}, {'q1': (('нет',), 0.9)})[0][1],
                         ('нет',))

    def test_answer_outside_options_rejected(self):
        K = self.K
        a = b = {'q1': (('5',), 0.99)}
        self.assertEqual(K.decide(self.ROWS[:1], a, b)[0][2], 'ответ_не_среди_вариантов')

    def test_low_confidence_and_missing(self):
        K = self.K
        self.assertEqual(K.decide(self.ROWS[:1], {'q1': (('1',), 0.5)}, {'q1': (('1',), 0.99)})[0][2],
                         'низкая_уверенность')
        self.assertEqual(K.decide(self.ROWS[:1], {}, {'q1': (('1',), 0.99)})[0][2], 'нет_ответа_модели')

    def test_parse_reply_and_answer_text(self):
        K = self.K
        got = K.parse_reply('```json\n{"answers": [{"id": "q1", "answer": ["3"], "confidence": 0.9},'
                            ' {"id": "q2", "answer": null, "confidence": 0.2}]}\n```')
        self.assertEqual(got, {'q1': (('3',), 0.9), 'q2': (None, 0.2)})
        self.assertEqual(K.answer_text(('1', '3'), K.options(self.ROWS[0]['statement_md'])), '1), 3)')
        self.assertEqual(K.answer_text(('нет',), K.options(self.ROWS[2]['statement_md'])), 'Нет')


class AgreeRefinedTests(SimpleTestCase):
    """Правило сведения после калибровки арбитра (29.10): разметка блоков,
    поле answer и метки списков расхождением не считаются."""

    def test_answer_field_and_metadata_ignored(self):
        a = rec(task('3', 'Найдите цену, если $Q = 100 - 2P$.', 20),
                {'type': 'solution', 'number': '3', 'text': 'Цена $P = 25$.', 'answer': '25'})
        b = rec({'type': 'task', 'number': '3',
                 'text': 'Задача 3 (20 баллов). Найдите цену, если $Q = 100 - 2P$.'},
                {'type': 'criteria', 'number': '3', 'text': 'Цена $P = 25$.'})
        self.assertEqual(vv.agree(a, b, 'tasks'), (True, []))

    def test_list_labels_not_numbers(self):
        a = rec(task('1', 'Вопрос\n\n1) 300\n2) 500'))
        b = rec(task('1', 'Вопрос\n\na) 300\nb) 500'))
        self.assertEqual(vv.agree(a, b), (True, []))

    def test_solution_page_ignores_task_numbers(self):
        a = rec(task('7', 'Решение: $Q = 40$'))
        b = rec({'type': 'criteria', 'number': '7', 'text': 'Решение: $Q = 40$'})
        self.assertFalse(vv.agree(a, b, 'tasks')[0])
        self.assertTrue(vv.agree(a, b, 'solutions')[0])

    def test_real_number_loss_still_disagrees(self):
        a = rec(task('1', 'Выручка 138 000 руб., прибыль 275 руб.'))
        b = rec(task('1', 'Выручка 138 000 руб.'))
        self.assertEqual(vv.agree(a, b)[1], ['числа'])

    def test_empty_page_vs_content_disagrees(self):
        self.assertFalse(vv.agree(rec(), rec(task('3', 'ЗАДАЧА 3')), 'tasks')[0])


class LayerTiebreakTests(SimpleTestCase):
    def test_layer_picks_version_with_page_numbers(self):
        a = rec(task('1', 'Спрос $Q_d = 100 - 2P$, налог 5 рублей.'))
        b = rec(task('1', 'Спрос $Q_d = 100 - 2P$, налог 6 рублей.'))
        why = vv.agree(a, b)[1]
        self.assertEqual(vv.layer_tiebreak(a, b, page(), why), 'A')
        self.assertEqual(vv.layer_tiebreak(b, a, page(), why), 'B')

    def test_layer_cannot_decide_structure_or_scan(self):
        a = rec(task('1', 'Спрос $Q_d = 100 - 2P$'))
        b = rec(task('1', 'Спрос $Q_d = 100 - 3P$'))
        self.assertIsNone(vv.layer_tiebreak(a, b, page(), ['числа', 'варианты']))
        self.assertIsNone(vv.layer_tiebreak(a, b, page(layer=''), ['числа']))

    def test_both_off_page_goes_to_arbiter(self):
        a = rec(task('1', 'налог 7 рублей'))
        b = rec(task('1', 'налог 8 рублей'))
        self.assertIsNone(vv.layer_tiebreak(a, b, page(), ['числа']))


class RecheckRuleTests(SimpleTestCase):
    """Фаза 4: правило приёма решения Opus (как P2)."""

    from problems.olympiad_audit import vsosh_recheck as RC
    ROW = {'statement_md': 'Спрос на товар задан функцией Qd = 100 - 2P. Найдите равновесную цену.',
           'answer': ''}

    def reply(self, **kw):
        return json.dumps(dict({'decision': 'keep', 'evidence': 'Спрос на товар задан функцией',
                                'confidence': 0.95}, **kw), ensure_ascii=False)

    def test_keep_and_fix_accepted(self):
        self.assertEqual(self.RC.judge(self.reply(), self.ROW, [LAYER])[0], 'keep')
        v, fixes, _w, _d = self.RC.judge(self.reply(decision='fix', fixes={'answer': '0,5'}),
                                          self.ROW, [LAYER])
        self.assertEqual((v, fixes), ('fix', {'answer': '0,5'}))

    def test_fix_with_foreign_number_or_truncation_rejected(self):
        v, _f, why, _d = self.RC.judge(self.reply(decision='fix', fixes={'answer': '42'}),
                                        self.ROW, [LAYER])
        self.assertEqual(v, 'human')
        self.assertIn('числа_не_со_страницы:answer', why)
        v, _f, why, _d = self.RC.judge(self.reply(decision='fix', fixes={'statement_md': 'Спрос.'}),
                                        self.ROW, [LAYER])
        self.assertIn('урезание_условия', why)

    def test_unknown_field_dropped_and_retry_band(self):
        v, _f, why, _d = self.RC.judge(self.reply(decision='fix', fixes={'event_id': 'x'}),
                                        self.ROW, [LAYER])
        self.assertIn('правка_пустая', why)
        self.assertEqual(self.RC.judge(self.reply(confidence=0.8), self.ROW, [LAYER])[0], 'retry')
        self.assertEqual(self.RC.judge(self.reply(evidence='чужая цитата про Лаффера'),
                                       self.ROW, [LAYER])[0], 'human')

    def test_needs_recheck_scope(self):
        rc = self.RC
        self.assertTrue(rc.needs_recheck({'stage': 'final', 'check_flags': ['нет_решения']}))
        self.assertFalse(rc.needs_recheck({'stage': 'final', 'check_flags': ['тест_без_ключа']}))
        self.assertFalse(rc.needs_recheck({'stage': 'municipal', 'check_flags': ['нет_решения']}))
        self.assertTrue(rc.needs_recheck({'stage': 'regional', 'check_flags': [],
                                          'math_star_unescaped': 1}))


class ApplyV2Tests(SimpleTestCase):
    from problems.olympiad_audit import vsosh_v2 as V

    def row(self, **kw):
        return dict({'event_id': 'e', 'number': 'тест-1', 'task_variant': '', 'stage': 'municipal',
                     'statement_md': 'Вопрос\n\n1) да\n2) нет', 'answer': ''}, **kw)

    def test_keys_applied_only_to_same_question(self):
        with tempfile.TemporaryDirectory() as d:
            acc = os.path.join(d, 'a.jsonl')
            with open(acc, 'w', encoding='utf-8') as fh:
                fh.write(json.dumps({'row': 'e|тест-1|', 'answer': '2)', 'models': ['a', 'b']}) + '\n')
                fh.write(json.dumps({'row': 'e|тест-2|', 'answer': '1)', 'models': ['a', 'b']}) + '\n')
            v1 = [self.row(), self.row(number='тест-2')]
            v2 = [self.row(), self.row(number='тест-2',
                                       statement_md='Совсем другой вопрос после пересборки')]
            st = self.V.apply_keys(v2, acc, v1)
            self.assertEqual(v2[0]['answer'], '2)')
            self.assertEqual(v2[1]['answer'], '')
            self.assertEqual(dict(st), {'ключ': 1, 'строка_сдвинулась': 1})

    def test_recheck_fix_and_keep(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'd.jsonl')
            with open(p, 'w', encoding='utf-8') as fh:
                fh.write(json.dumps({'row': 'e|1|', 'verdict': 'fix', 'fixes': {'answer': '25'}}) + '\n')
                fh.write(json.dumps({'row': 'e|2|', 'verdict': 'keep'}) + '\n')
            rows = [self.row(number='1'), self.row(number='2')]
            self.V.apply_recheck(rows, p)
            self.assertEqual((rows[0]['answer'], rows[0]['q2_fixed_fields']), ('25', ['answer']))
            self.assertEqual(rows[1]['q2_recheck'], 'keep')

    def test_key_grid_invariant(self):
        rows = [self.row(answer='2)', answer_from_key_grid=['a', 'b']),
                self.row(number='тест-2', answer='5)', answer_from_key_grid=['a', 'b'])]
        self.assertEqual(self.V.test_keys_in_options(rows), ['e|тест-2|'])

    def test_queue_item_format(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, 'render_index.jsonl'), 'w', encoding='utf-8') as fh:
                fh.write(json.dumps({'pdf': 'x.pdf', 'page_dir': 'pages/ab'}) + '\n')
            r = self.row(check_flags=['тест_без_ключа', 'ключа_нет_в_источнике'],
                         source_pages=['x.pdf#p2'])
            out = self.V.build_queue([r], d, [{'row': 'e|тест-1|', 'why': 'модели_разошлись',
                                               'replies': {'m1': [['1'], 0.9], 'm2': [['2'], 0.9]}}],
                                     [], os.path.join(d, 'q', 'q.jsonl'))
            self.assertEqual(len(out), 1)
            x = out[0]
            self.assertEqual(x['item_id'], 'q2_vsosh_v2:vseros:e|тест-1|:тест_без_ключа')
            self.assertEqual(set(x), {'item_id', 'source', 'olympiad', 'ref_key', 'problem_id', 'check',
                                      'details', 'page_images', 'current', 'proposed', 'confidence'})
            self.assertTrue(x['page_images'][0].endswith(os.path.join('pages', 'ab', 'p2.png')))
            self.assertEqual(x['proposed'], {'answer_by_model': {'m1': ['1'], 'm2': ['2']}})


class GridKeyTests(SimpleTestCase):
    """Ключ-сетка кодом: столбец — вопрос, отметка — в строке варианта."""

    def test_yes_no_grid_over_two_rows(self):
        from problems.olympiad_audit import vsosh_digitize as D
        text = ('Ответы на тест\n\n| 1 | 2 | 3 | 4 | 5 |\n|---|---|---|---|---|\n'
                '|  | ДА | ДА |  |  |\n| НЕТ |  |  | НЕТ | НЕТ |')
        self.assertEqual(D.key_table_pairs(text),
                         [('1', 'НЕТ'), ('2', 'ДА'), ('3', 'ДА'), ('4', 'НЕТ'), ('5', 'НЕТ')])

    def test_positional_marks_and_multi(self):
        from problems.olympiad_audit import vsosh_digitize as D
        text = ('| вариант | 1 | 2 | 3 |\n|---|---|---|---|\n'
                '| а) | X |  | X |\n| б) |  | X | X |')
        self.assertEqual(D.key_table_pairs(text), [('1', 'а)'), ('2', 'б)'), ('3', 'а), б)')])

    def test_data_table_is_not_a_grid(self):
        from problems.olympiad_audit import vsosh_digitize as D
        text = '| Q | 1 | 2 | 3 |\n|---|---|---|---|\n| P | 100 | 90 | 80 |\n| TC | 20 | 35 | 45 |'
        self.assertEqual(D.key_table_pairs(text), [])

    def test_single_answer_row_keeps_old_rule(self):
        from problems.olympiad_audit import vsosh_digitize as D
        text = '| 1 | 2 | 3 |\n|---|---|---|\n| Б | А | В |'
        self.assertEqual(D.key_table_pairs(text), [('1', 'Б'), ('2', 'А'), ('3', 'В')])

    def test_vet_table_keys_and_text_match(self):
        from problems.olympiad_audit import vsosh_keys as K
        from problems.olympiad_audit import vsosh_v2 as V
        self.assertTrue(K.key_matches_options('ДА', 'Утверждение.\n\n1) верно\n2) неверно'))
        self.assertTrue(K.key_matches_options('2)', 'Вопрос\n\n1) a\n2) b'))
        self.assertFalse(K.key_matches_options('5)', 'Вопрос\n\n1) a\n2) b'))
        rows = [{'event_id': 'e', 'number': 'тест-1', 'task_variant': '', 'answer': '5)',
                 'answer_from_key_table': True, 'statement_md': 'Вопрос\n\n1) a\n2) b'},
                {'event_id': 'e', 'number': 'тест-2', 'task_variant': '', 'answer': '2)',
                 'answer_from_key_table': True, 'statement_md': 'Вопрос\n\n1) a\n2) b'}]
        v1 = [dict(rows[0], answer=''), {'event_id': 'e', 'number': 'тест-2', 'task_variant': '',
                                         'answer': '9)'}]
        self.assertEqual(V.vet_table_keys(rows, v1), (0, 1))
        self.assertEqual((rows[0]['answer'], rows[0]['key_table_rejected']), ('', '5)'))
        self.assertEqual(rows[1]['answer'], '2)')   # был в v1 — не трогаем

    def test_open_answer_test(self):
        from problems.olympiad_audit import vsosh_v2 as V
        self.assertTrue(V.open_answer({'statement_md': 'Часть 4. Задания с открытым ответом. Найдите Q.'}))
        self.assertTrue(V.open_answer({'statement_md': 'Найдите цену.', 'answer': '150'}))
        self.assertFalse(V.open_answer({'statement_md': 'Выберите верное.', 'answer': '3)'}))
        self.assertFalse(V.open_answer({'statement_md': 'Выберите верное.'}))


class Ile2008Tests(SimpleTestCase):
    HTML = ('<html><body><h2>1-й тур: задачи</h2>'
            '<div class="task"><h3>1. Простая задача</h3><div class="condition"><div class="tex2jax">'
            '<p>Спрос $Q = 100 - P$.</p><ul><li>а) цена</li><li>б) объём</li></ul></div></div>'
            '<div class="solution_and_answer"><div class="title">Решение</div>'
            '<p>Ответ: $P = 50$.</p></div></div>'
            '<h2>Тест</h2><div class="task"><h3>1. Вопрос</h3><div class="condition">'
            '<div class="tex2jax">Что выбрать?<br/>1)50 кг<br/>2)60 кг</div></div></div></body></html>')

    def test_rows_and_source_note(self):
        from problems.olympiad_audit import vsosh_v2 as V
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'p.html')
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(self.HTML)
            rows = V.ile_2008_rows(path, os.path.join(d, 'v2', 'figures_v2', 'ile'), fetch=False)
        self.assertEqual([(r['event_id'], r['number']) for r in rows],
                         [('vseros-final-2008-09-ru-all-tur1', '1'),
                          ('vseros-final-2008-09-ru-all-test', 'тест-1')])
        self.assertEqual(rows[0]['statement_md'], 'Спрос $Q = 100 - P$.\n\n- а) цена\n- б) объём')
        self.assertEqual(rows[0]['solution_md'], 'Ответ: $P = 50$.')
        self.assertEqual(rows[1]['statement_md'], 'Что выбрать?\n1)50 кг\n2)60 кг')
        self.assertEqual(rows[0]['source_note'], 'ILE (печатная страница), официальный файл не найден')
        self.assertFalse(rows[0]['official'])
