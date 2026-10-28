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
