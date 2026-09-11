# -*- coding: utf-8 -*-
"""Судья 2: DeepSeek V4 Pro без рассуждения. База только читается.

Решения владельца 10.09.2026, каждое здесь исполняется буквально:
  * рассуждение выключено (`AI_REASONING_EFFORT=none`): с ним выход
    5 902 токена на пачку и смета $10,45, без него 359 и $4,27;
  * потолок DeepSeek $5,00 — это ВЕСЬ баланс, пополнения не будет;
  * вызовы только ВНЕ ПИКА (пик 01:00–04:00 и 06:00–10:00 UTC по
    будням, тариф вдвое). В пик прогон не начинается и прерывается;
  * порядок пачек фиксированный, первыми — 10 запросов с ручной
    разметкой владельца: если счётчик остановит разметку, размеченными
    окажутся именно те запросы, на которых считается стоп-гейт 2;
  * остановка по потолку — не авария: пары без второго судьи получат
    метку судьи 1 с флагом `single_judge`, доля таких пар пойдёт в отчёт.

Прогон продолжаемый: уже размеченные пачки читаются из файла и
не повторяются.

Запуск:
    venv313\\Scripts\\python.exe reports/llm_search_eval/run_judge2.py [--workers 8]
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
import judging  # noqa: E402
import orclient  # noqa: E402
import run_batch_judge  # noqa: E402
from problems.ai.providers import get_provider  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = os.path.join(HERE, 'labels_deepseek.jsonl')
DONE = os.path.join(HERE, 'labels_deepseek.done')

PROVIDER, MODEL = 'deepseek', 'deepseek-v4-pro'
STAGE = '2. судья deepseek'


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def load_done():
    if not os.path.exists(DONE):
        return set()
    with open(DONE, encoding='utf-8') as handle:
        return {line.strip() for line in handle if line.strip()}


def main():
    workers = int(arg('--workers', 8))
    envbridge.apply_to_process()

    if orclient.is_peak():
        print('ПИК DeepSeek (01:00–04:00 и 06:00–10:00 UTC по будням) — '
              'тариф вдвое. Прогон не начинаю.')
        return 2

    pool, corpus = run_batch_judge.load()
    tasks = run_batch_judge.ordered_tasks(pool)
    done = load_done()
    todo = [t for t in tasks if '%s#%d' % (t[0], t[3]) not in done]
    print('Пачек всего %d, уже размечено %d, осталось %d'
          % (len(tasks), len(done), len(todo)))

    client = orclient.Client(
        providers={PROVIDER: get_provider('deepseek')},
        costs_path=os.path.join(HERE, 'costs.json'),
        failures_path=os.path.join(HERE, 'failures.jsonl'),
        budgets=orclient.BUDGETS)
    print('Потрачено у DeepSeek $%.4f, остаток $%.4f'
          % (client.spent[PROVIDER], client.remaining(PROVIDER)))

    lock = threading.Lock()
    stop = threading.Event()
    stats = {'batches': 0, 'labels': 0, 'missing': 0, 'extra': 0,
             'broken': 0, 'failed': 0}

    labels_file = open(LABELS, 'a', encoding='utf-8')
    done_file = open(DONE, 'a', encoding='utf-8')

    def handle(task):
        qid, text, chunk, number = task
        if stop.is_set():
            return
        # Пик может начаться посреди прогона — проверяем перед каждой пачкой.
        if orclient.is_peak():
            stop.set()
            return
        cards = [corpus[pid] for pid in chunk]
        try:
            with lock:
                if client.remaining(PROVIDER) < 0.05:
                    stop.set()
                    return
            reply = client.call(
                stage=STAGE, query_id=qid, provider=PROVIDER, model=MODEL,
                system_blocks=[judging.INSTRUCTION],
                user_text=judging.user_text(text, cards),
                schema=judging.SCHEMA, max_tokens=4000, timeout=300,
                estimated_usd=0.02)
        except orclient.BudgetExceeded:
            stop.set()
            return
        except Exception:                               # noqa: BLE001
            with lock:
                stats['failed'] += 1
            return
        try:
            data = orclient.parse_json_object(reply.text)
        except ValueError:
            with lock:
                stats['broken'] += 1
            return
        labels, missing, extra = judging.parse_verdicts(data, chunk)
        with lock:
            for pid, label in labels.items():
                labels_file.write(json.dumps(
                    {'query_id': qid, 'problem_id': pid, 'label': label},
                    ensure_ascii=False) + '\n')
            done_file.write('%s#%d\n' % (qid, number))
            labels_file.flush()
            done_file.flush()
            stats['batches'] += 1
            stats['labels'] += len(labels)
            stats['missing'] += len(missing)
            stats['extra'] += len(extra)
            if stats['batches'] % 50 == 0:
                print('   %d пачек, $%.3f, остаток $%.3f'
                      % (stats['batches'], client.spent[PROVIDER],
                         client.remaining(PROVIDER)))

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool_exec:
        list(pool_exec.map(handle, todo))
    labels_file.close()
    done_file.close()

    elapsed = time.perf_counter() - started
    print('\nПачек размечено %d за %.0f с, меток %d'
          % (stats['batches'], elapsed, stats['labels']))
    print('Пропущено моделью %d, лишних %d, неразобранных %d, отказов %d'
          % (stats['missing'], stats['extra'], stats['broken'],
             stats['failed']))
    print('Потрачено у DeepSeek $%.4f из $%.2f (тариф ВНЕ ПИКА)'
          % (client.spent[PROVIDER], orclient.BUDGETS[PROVIDER]))
    if stop.is_set():
        print('⚠️ Прогон остановлен: потолок или начало пика. Оставшиеся '
              'пары получат метку судьи 1 с флагом single_judge.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
