# -*- coding: utf-8 -*-
"""Фаза 2: разметка пула двумя судьями. База только читается.

Судьи из разных семейств и НЕ совпадают с реранкерами фазы 3:
  судья 1 — OpenAI (модель задаётся ключом --judge1),
  судья 2 — DeepSeek V4 Pro.

Режимы:
    --pilot N   прогнать N пачек на каждого судью и напечатать
                фактические токены: смета считается по ним, а не на глаз;
    (без ключа) полный прогон по всему пулу.

Запуск:
    venv313\\Scripts\\python.exe reports/llm_search_eval/run_judges.py --pilot 2
"""
import json
import os
import sys
import time

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

import envbridge  # noqa: E402
import judging  # noqa: E402
import orclient  # noqa: E402
from problems.ai.providers import get_provider  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
POOL = os.path.join(HERE, 'pool.jsonl')
CORPUS = os.path.join(HERE, 'corpus.jsonl')

JUDGES = {
    'sol': ('openai', 'gpt-5.6-sol', 'labels_sol.jsonl'),
    'terra': ('openai', 'gpt-5.6-terra', 'labels_terra.jsonl'),
    'deepseek': ('deepseek', 'deepseek-v4-pro', 'labels_deepseek.jsonl'),
}


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def load():
    pool = [json.loads(line) for line in open(POOL, encoding='utf-8')]
    corpus = {}
    with open(CORPUS, encoding='utf-8') as handle:
        for line in handle:
            row = json.loads(line)
            corpus[row['id']] = row
    return pool, corpus


def main():
    pilot = int(arg('--pilot', 0) or 0)
    judge_names = (arg('--judges', 'sol,deepseek') or '').split(',')

    envbridge.apply_to_process()
    pool, corpus = load()

    client = orclient.Client(
        providers={'openai': get_provider('openai'),
                   'deepseek': get_provider('deepseek')},
        costs_path=os.path.join(HERE, 'costs.json'),
        failures_path=os.path.join(HERE, 'failures.jsonl'),
        budgets=orclient.BUDGETS)

    # Пачки: (query_id, текст запроса, список id кандидатов).
    tasks = []
    for row in pool:
        for chunk in judging.batches(row['pool']):
            tasks.append((row['query_id'], row['text'], chunk))
    print('Пачек всего: %d (пар %d, запросов %d)'
          % (len(tasks), sum(len(t[2]) for t in tasks), len(pool)))
    if pilot:
        tasks = tasks[:pilot]
        print('Пилот: беру %d пачек на судью' % len(tasks))

    if orclient.is_peak() and 'deepseek' in judge_names:
        print('⚠️ Сейчас ПИК DeepSeek — тариф вдвое. Прогон судьи 2 лучше '
              'отложить; пилот пойдёт, полный прогон остановлен.')
        if not pilot:
            return 1

    for name in judge_names:
        provider, model, out_name = JUDGES[name]
        rows, stats = [], {'input': 0, 'output': 0, 'reasoning': 0,
                           'cache_read': 0, 'usd': 0.0, 'missing': 0,
                           'extra': 0, 'batches': 0}
        started = time.perf_counter()
        for qid, text, chunk in tasks:
            cards = [corpus[pid] for pid in chunk]
            reply = client.call(
                stage='2. судья %s' % name, query_id=qid,
                provider=provider, model=model,
                system_blocks=[judging.INSTRUCTION],
                user_text=judging.user_text(text, cards),
                schema=judging.SCHEMA, max_tokens=4000, timeout=300,
                estimated_usd=0.20)
            data = orclient.parse_json_object(reply.text)
            labels, missing, extra = judging.parse_verdicts(data, chunk)
            for pid, label in labels.items():
                rows.append({'query_id': qid, 'problem_id': pid,
                             'label': label})
            stats['input'] += reply.input_tokens
            stats['output'] += reply.output_tokens
            stats['reasoning'] += reply.reasoning_tokens
            stats['cache_read'] += reply.cache_read_tokens
            stats['missing'] += len(missing)
            stats['extra'] += len(extra)
            stats['batches'] += 1
        stats['usd'] = client.costs['by_stage'].get(
            '2. судья %s' % name, {}).get(model, {}).get('usd', 0.0)
        elapsed = time.perf_counter() - started

        suffix = '.pilot' if pilot else ''
        judging.dump(rows, os.path.join(HERE, out_name + suffix))
        per = stats['batches'] or 1
        print('\n%s (%s):' % (name, model))
        print('   пачек %d, меток %d, пропущено %d, лишних %d'
              % (stats['batches'], len(rows), stats['missing'], stats['extra']))
        print('   на пачку: вход %d, выход %d (из них рассуждение %d), кэш %d'
              % (stats['input'] / per, stats['output'] / per,
                 stats['reasoning'] / per, stats['cache_read'] / per))
        print('   потрачено $%.4f за %.0f с (%.1f с на пачку)'
              % (stats['usd'], elapsed, elapsed / per))
        if pilot:
            full = len(pool) and sum(
                len(judging.batches(r['pool'])) for r in pool)
            print('   ПРОГНОЗ на все %d пачек: $%.2f'
                  % (full, stats['usd'] / per * full))

    print('\nПотрачено по провайдерам:')
    for name, ceiling in orclient.BUDGETS.items():
        print('   %-10s $%.4f из $%.2f' % (name, client.spent.get(name, 0.0),
                                           ceiling))
    return 0


if __name__ == '__main__':
    sys.exit(main())
