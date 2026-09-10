# -*- coding: utf-8 -*-
"""Фаза 3: прогон реранкеров S3 и финального прохода S4.

Продолжаемый: сделанные запросы читаются из файла и не повторяются.
Потолок провайдера проверяется перед каждым вызовом; остановка по
потолку не авария, а штатный конец — что успели, то и меряем.

Запуск:
    venv313\\Scripts\\python.exe reports/llm_search_eval/run_rerank.py \\
        --system glm-flash [--workers 8]
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

import envbridge  # noqa: E402
import orclient  # noqa: E402
import reranking  # noqa: E402
import run_batch_judge  # noqa: E402
from problems.ai.providers import get_provider  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

#: система → (провайдер, поставщик в реестре, модель)
SYSTEMS = {
    'glm-flash': ('zai', 'glm', 'glm-5.3-flash'),
    'glm': ('zai', 'glm', 'glm-5.3'),
    'haiku': ('anthropic', 'anthropic', 'claude-haiku-4-5'),
    'sonnet': ('anthropic', 'anthropic', 'claude-sonnet-5'),
}


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    system = arg('--system', 'glm-flash')
    workers = int(arg('--workers', 8))
    provider, registry, model = SYSTEMS[system]
    out_path = os.path.join(HERE, 'rerank_%s.jsonl' % system)
    done_path = out_path + '.done'

    envbridge.apply_to_process()
    pool, corpus = run_batch_judge.load()

    # Порядок тот же, что у судей: сперва запросы с ручной разметкой.
    manual = [r for r in pool if r['manual_id']]
    ordered = manual + [r for r in pool if not r['manual_id']]

    done = set()
    if os.path.exists(done_path):
        with open(done_path, encoding='utf-8') as handle:
            done = {line.strip() for line in handle if line.strip()}
    todo = [r for r in ordered if r['query_id'] not in done]
    print('Система %s (%s / %s): запросов %d, сделано %d, осталось %d'
          % (system, provider, model, len(pool), len(done), len(todo)))

    client = orclient.Client(
        providers={provider: get_provider(registry)},
        costs_path=os.path.join(HERE, 'costs.json'),
        failures_path=os.path.join(HERE, 'failures.jsonl'),
        budgets=orclient.BUDGETS)
    print('Потрачено у %s $%.4f, остаток $%.4f'
          % (provider, client.spent[provider], client.remaining(provider)))

    lock = threading.Lock()
    stop = threading.Event()
    stats = {'queries': 0, 'missing': 0, 'extra': 0, 'failed': 0, 'broken': 0}
    out_file = open(out_path, 'a', encoding='utf-8')
    done_file = open(done_path, 'a', encoding='utf-8')

    def handle(row):
        if stop.is_set():
            return
        qid, text, ids = row['query_id'], row['text'], row['pool']
        chunks, missing_all, extra_all = [], [], []
        for chunk in [ids[i:i + reranking.BATCH]
                      for i in range(0, len(ids), reranking.BATCH)]:
            cards = [corpus[pid] for pid in chunk]
            try:
                with lock:
                    if client.remaining(provider) < 0.05:
                        stop.set()
                        return
                reply = client.call(
                    stage='3. реранкер %s' % system, query_id=qid,
                    provider=provider, model=model,
                    system_blocks=[reranking.INSTRUCTION],
                    user_text=reranking.user_text(text, cards),
                    schema=reranking.SCHEMA, max_tokens=3000, timeout=300,
                    estimated_usd=0.05)
            except orclient.BudgetExceeded:
                stop.set()
                return
            except Exception:                           # noqa: BLE001
                with lock:
                    stats['failed'] += 1
                return
            try:
                data = orclient.parse_json_object(reply.text)
            except ValueError:
                with lock:
                    stats['broken'] += 1
                continue
            scores, missing, extra = reranking.parse_scores(data, chunk)
            chunks.append(scores)
            missing_all += missing
            extra_all += extra

        ranked = reranking.merge(chunks, all_ids=ids)
        with lock:
            out_file.write(json.dumps(
                {'query_id': qid, 'ranked': ranked,
                 'not_scored': missing_all, 'extra': extra_all},
                ensure_ascii=False) + '\n')
            done_file.write(qid + '\n')
            out_file.flush()
            done_file.flush()
            stats['queries'] += 1
            stats['missing'] += len(missing_all)
            stats['extra'] += len(extra_all)
            if stats['queries'] % 20 == 0:
                print('   %d запросов, $%.3f, остаток $%.3f'
                      % (stats['queries'], client.spent[provider],
                         client.remaining(provider)))

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(handle, todo))
    out_file.close()
    done_file.close()

    print('\nЗапросов разложено %d за %.0f с' % (stats['queries'],
                                                 time.perf_counter() - started))
    print('Не оценено моделью %d, лишних %d, неразобранных %d, отказов %d'
          % (stats['missing'], stats['extra'], stats['broken'],
             stats['failed']))
    print('Потрачено у %s $%.4f из $%.2f'
          % (provider, client.spent[provider], orclient.BUDGETS[provider]))
    if stop.is_set():
        print('⚠️ Остановлено потолком провайдера.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
