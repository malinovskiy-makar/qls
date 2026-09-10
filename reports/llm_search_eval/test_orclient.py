# -*- coding: utf-8 -*-
"""Клиент замера: бюджет, повторы, журнал отказов, разбор ответа.

Запуск (Django не нужен, сети нет):
    venv313\\Scripts\\python.exe -m unittest discover -s reports/llm_search_eval -p "test_*.py"

Что здесь стережётся:
  - счётчик бюджета срабатывает ДО вызова, а не после: правило сессии —
    «превышение это остановка, а не доделать чуть-чуть»;
  - КАЖДАЯ неудачная попытка попадает в журнал ДО паузы и повтора. Урок
    run2 (04.09): журнал только успехов сделал полтора часа отказов
    неразбираемыми, потому что записи появлялись лишь после удачи;
  - стоимость берётся из ответа посредника, а по прайсу — только когда
    посредник промолчал;
  - разбор JSON переживает массив вместо объекта и обрезанный хвост:
    оба случая run2 видел живьём.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orclient  # noqa: E402


class _Reply(object):
    def __init__(self, text='{"1": 2}', input_tokens=100, output_tokens=10,
                 cache_read_tokens=0, reasoning_tokens=0, cost_usd=None):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_tokens = cache_read_tokens
        self.reasoning_tokens = reasoning_tokens
        self.cost_usd = cost_usd


class _Boom(Exception):
    """Отказ поставщика с кодом, как у настоящего."""

    def __init__(self, status=500):
        super(_Boom, self).__init__('отказ %s' % status)
        self.kind = 'other'
        self.original = type('E', (), {'status_code': status})()


class _Provider(object):
    """Подставной поставщик: последовательность ответов или исключений."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


class _Case(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.slept = []
        self.client = orclient.Client(
            providers={},
            costs_path=os.path.join(self.dir, 'costs.json'),
            failures_path=os.path.join(self.dir, 'failures.jsonl'),
            budgets={'zai': 1.0, 'openai': 1.0, 'deepseek': 1.0,
                     'anthropic': 1.0},
            sleep=self.slept.append)

    def failures(self):
        path = self.client.failures_path
        if not os.path.exists(path):
            return []
        with open(path, encoding='utf-8') as f:
            return [json.loads(line) for line in f if line.strip()]

    def call(self, fake, **kwargs):
        name = kwargs.setdefault('provider', 'zai')
        self.client.providers[name] = fake
        kwargs.setdefault('stage', 'test')
        kwargs.setdefault('query_id', 'q01')
        kwargs.setdefault('model', 'glm-5.3-flash')
        kwargs.setdefault('system_blocks', ['s'])
        kwargs.setdefault('user_text', 'u')
        kwargs.setdefault('schema', {})
        kwargs.setdefault('max_tokens', 100)
        return self.client.call(**kwargs)


class BudgetTests(_Case):
    def test_превышение_бюджета_останавливает_до_вызова(self):
        self.client.spent['zai'] = 0.99
        provider = _Provider(_Reply(cost_usd=0.5))
        with self.assertRaises(orclient.BudgetExceeded):
            self.call(provider, estimated_usd=0.5)
        self.assertEqual(provider.calls, 0)

    def test_потрачено_растёт_по_стоимости_из_ответа(self):
        self.call(_Provider(_Reply(cost_usd=0.0123)))
        self.assertAlmostEqual(self.client.spent['zai'], 0.0123)

    def test_расход_разложен_по_этапам_и_моделям(self):
        self.call(_Provider(_Reply(cost_usd=0.01)), stage='2. судья')
        self.call(_Provider(_Reply(cost_usd=0.02)), stage='3. реранкер',
                  model='glm-5.3')
        with open(self.client.costs_path, encoding='utf-8') as handle:
            costs = json.load(handle)
        self.assertAlmostEqual(
            costs['by_stage']['2. судья']['glm-5.3-flash']['usd'], 0.01)
        self.assertAlmostEqual(
            costs['by_stage']['3. реранкер']['glm-5.3']['usd'], 0.02)
        self.assertAlmostEqual(costs['by_provider']['zai']['usd'], 0.03)
        self.assertAlmostEqual(costs['total_usd'], 0.03)

    def test_без_цены_от_провайдера_считаем_по_прайсу(self):
        # glm-5.3-flash, прямой прайс Z.ai: $0,15 вход, $0,50 выход.
        self.call(_Provider(_Reply(input_tokens=1_000_000,
                                   output_tokens=1_000_000, cost_usd=None)))
        self.assertAlmostEqual(self.client.spent['zai'], 0.65)

    def test_счётчик_переживает_перезапуск(self):
        self.call(_Provider(_Reply(cost_usd=0.04)))
        second = orclient.Client(providers={},
                                 costs_path=self.client.costs_path,
                                 failures_path=self.client.failures_path,
                                 budgets={'zai': 1.0})
        self.assertAlmostEqual(second.spent['zai'], 0.04)

    def test_потолок_одного_провайдера_не_запирает_другого(self):
        # Баланс у каждого провайдера свой: исчерпав Z.ai, судью на
        # OpenAI останавливать не за что.
        self.client.spent['zai'] = 1.0
        with self.assertRaises(orclient.BudgetExceeded):
            self.call(_Provider(_Reply(cost_usd=0.01)), estimated_usd=0.01)
        reply = self.call(_Provider(_Reply(cost_usd=0.01)), provider='openai',
                          model='gpt-5.6-sol', estimated_usd=0.01)
        self.assertIsNotNone(reply)

    def test_у_deepseek_пиковый_тариф_вдвое_дороже(self):
        # Пик 01:00-04:00 и 06:00-10:00 UTC по будням, цена вдвое.
        off = orclient.price_of_tokens('deepseek', 'deepseek-v4-pro',
                                       1_000_000, 0, 0, peak=False)
        peak = orclient.price_of_tokens('deepseek', 'deepseek-v4-pro',
                                        1_000_000, 0, 0, peak=True)
        self.assertAlmostEqual(off, 0.66)
        self.assertAlmostEqual(peak, 1.32)

    def test_пик_определяется_по_часу_utc_и_дню_недели(self):
        import datetime
        # Среда 02:30 UTC — пик; среда 12:00 UTC — не пик; суббота 02:30 — не пик.
        self.assertTrue(orclient.is_peak(datetime.datetime(
            2026, 9, 9, 2, 30, tzinfo=datetime.timezone.utc)))
        self.assertFalse(orclient.is_peak(datetime.datetime(
            2026, 9, 9, 12, 0, tzinfo=datetime.timezone.utc)))
        self.assertFalse(orclient.is_peak(datetime.datetime(
            2026, 9, 12, 2, 30, tzinfo=datetime.timezone.utc)))


class RetryTests(_Case):
    def test_отказ_потом_успех_возвращает_ответ(self):
        reply = self.call(_Provider(_Boom(500), _Reply(text='{"ok": 1}')))
        self.assertEqual(reply.text, '{"ok": 1}')

    def test_три_отказа_подряд_пробрасывают_ошибку(self):
        provider = _Provider(_Boom(500), _Boom(500), _Boom(500))
        with self.assertRaises(Exception):
            self.call(provider)
        self.assertEqual(provider.calls, 3)

    def test_пауза_растёт_экспоненциально(self):
        with self.assertRaises(Exception):
            self.call(_Provider(_Boom(500), _Boom(500), _Boom(500)))
        # После третьей попытки паузы нет — повторять уже нечего.
        self.assertEqual(self.slept, [2, 4])


class FailureLogTests(_Case):
    def test_каждая_неудачная_попытка_записана(self):
        with self.assertRaises(Exception):
            self.call(_Provider(_Boom(500), _Boom(429), _Boom(503)))
        rows = self.failures()
        self.assertEqual([r['attempt'] for r in rows], [1, 2, 3])
        self.assertEqual([r['http_status'] for r in rows], [500, 429, 503])

    def test_последняя_попытка_помечена_что_повтора_не_будет(self):
        with self.assertRaises(Exception):
            self.call(_Provider(_Boom(500), _Boom(500), _Boom(500)))
        rows = self.failures()
        self.assertEqual([r['will_retry'] for r in rows], [True, True, False])

    def test_в_записи_есть_все_поля_журнала(self):
        with self.assertRaises(Exception):
            self.call(_Provider(_Boom(500), _Boom(500), _Boom(500)))
        row = self.failures()[0]
        for field in ('ts', 'stage', 'query_id', 'model', 'attempt',
                      'http_status', 'error', 'will_retry'):
            self.assertIn(field, row)

    def test_запись_ложится_на_диск_до_паузы(self):
        # Урок run2: если писать после повтора, обрыв процесса стирает
        # причину отказа. Проверяем это единственным честным способом —
        # читаем журнал в момент паузы.
        seen = []
        self.client.sleep = lambda s: seen.append(len(self.failures()))
        with self.assertRaises(Exception):
            self.call(_Provider(_Boom(500), _Boom(500), _Boom(500)))
        self.assertEqual(seen, [1, 2])

    def test_ключ_не_попадает_в_журнал(self):
        with self.assertRaises(Exception):
            self.call(_Provider(_Boom(401)))
        self.assertNotIn('sk-', json.dumps(self.failures(), ensure_ascii=False))


class JsonParseTests(unittest.TestCase):
    def test_обычный_объект(self):
        self.assertEqual(orclient.parse_json_object('{"12": 2}'), {'12': 2})

    def test_массив_вместо_объекта_склеивается_в_объект(self):
        # run2 видел это живьём: модель отвечает [{"id":12,"score":2}, ...]
        # вместо {"12": 2}. Терять всю пачку из-за формы обёртки нельзя.
        got = orclient.parse_json_object(
            '[{"id": 12, "score": 2}, {"id": 13, "score": 0}]')
        self.assertEqual(got, {'12': 2, '13': 0})

    def test_обрезанный_json_отдаёт_разобранную_часть(self):
        got = orclient.parse_json_object('{"12": 2, "13": 1, "14":')
        self.assertEqual(got, {'12': 2, '13': 1})

    def test_обёртка_rows_разворачивается(self):
        # Строгий режим OpenAI не умеет объект с произвольными ключами:
        # {"12": 2} им не выразить. Поэтому судей просят отвечать
        # {"rows": [{"id": 12, "score": 2}, ...]}, и обёртку надо снять.
        got = orclient.parse_json_object(
            '{"rows": [{"id": 12, "score": 2}, {"id": 13, "score": 0}]}')
        self.assertEqual(got, {'12': 2, '13': 0})

    def test_обычный_объект_не_путается_с_обёрткой(self):
        # У объекта с ключом «rows» и НЕ списком внутри разворачивать нечего.
        self.assertEqual(orclient.parse_json_object('{"rows": 5}'),
                         {'rows': 5})

    def test_обрамление_markdown_снимается(self):
        self.assertEqual(
            orclient.parse_json_object('```json\n{"12": 2}\n```'), {'12': 2})

    def test_совсем_не_json_даёт_ошибку_а_не_пустой_объект(self):
        # Пустой объект молча означал бы «модель всё сочла негодным».
        with self.assertRaises(ValueError):
            orclient.parse_json_object('извините, не могу помочь')


class EnvFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, '.env')

    def test_ключ_из_файла_попадает_в_окружение(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('# комментарий\nOPENROUTER_API_KEY=abc123\n')
        env = {}
        orclient.load_env_file(self.path, env)
        self.assertEqual(env['OPENROUTER_API_KEY'], 'abc123')

    def test_уже_заданная_переменная_не_перетирается(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('OPENROUTER_API_KEY=from-file\n')
        env = {'OPENROUTER_API_KEY': 'from-shell'}
        orclient.load_env_file(self.path, env)
        self.assertEqual(env['OPENROUTER_API_KEY'], 'from-shell')

    def test_кавычки_снимаются(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('A="v1"\nB=\'v2\'\n')
        env = {}
        orclient.load_env_file(self.path, env)
        self.assertEqual((env['A'], env['B']), ('v1', 'v2'))

    def test_нет_файла_не_ошибка(self):
        env = {}
        orclient.load_env_file(os.path.join(self.dir, 'нет.env'), env)
        self.assertEqual(env, {})


if __name__ == '__main__':
    unittest.main()
