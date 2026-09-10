# -*- coding: utf-8 -*-
"""Судья 1 через Batch API OpenAI: вдвое дешевле, ответ в течение часов.

Решение владельца 10.09.2026: напрямую GPT-5.6 Sol стоит $23,00 при
потолке $19; через пакетную обработку — $11,50. Разметка пула ждать
может, в реальном времени её никто не читает.

⚠️ ОДНИМ ПАКЕТОМ НЕ ВЫХОДИТ. У организации потолок 900 000 токенов В
ОЧЕРЕДИ на модель; весь прогон — 5,1 млн, и пакет целиком отклоняется с
`token_limit_exceeded` ещё до первого вызова. Поэтому работа идёт
частями по `CHUNK` запросов, строго по одной в очереди: отправили,
дождались, забрали, следующая.

`max_output_tokens` снижен с 4 000 до 1 200 намеренно: в очереди
считается и зарезервированный выход, а замер показал 237 токенов ответа
на пачку. Лишний резерв уменьшал бы размер части втрое без всякой пользы.

Команды:
    --run       довести до конца: части по очереди, с продолжением
    --status    состояние текущей части
"""
import json
import math
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

HERE = os.path.dirname(os.path.abspath(__file__))
POOL = os.path.join(HERE, 'pool.jsonl')
CORPUS = os.path.join(HERE, 'corpus.jsonl')
STATE = os.path.join(HERE, 'batch_sol.json')
LABELS = os.path.join(HERE, 'labels_sol.jsonl')

PROVIDER, MODEL = 'openai', 'gpt-5.6-sol'
BATCH_DISCOUNT = 0.5
CHUNK = 60
MAX_OUTPUT = 1200
POLL_SECONDS = 30


def load():
    pool = [json.loads(line) for line in open(POOL, encoding='utf-8')]
    corpus = {}
    with open(CORPUS, encoding='utf-8') as handle:
        for line in handle:
            row = json.loads(line)
            corpus[row['id']] = row
    return pool, corpus


def ordered_tasks(pool):
    """Пачки в ФИКСИРОВАННОМ порядке: сперва размеченные владельцем.

    Порядок задан указанием владельца и важен не для красоты: если
    счётчик остановит разметку на середине, размеченными окажутся именно
    те запросы, по которым считается согласие судей со стоп-гейта 2.
    """
    manual = [r for r in pool if r['manual_id']]
    rest = [r for r in pool if not r['manual_id']]
    tasks = []
    for row in manual + rest:
        for number, chunk in enumerate(judging.batches(row['pool'])):
            tasks.append((row['query_id'], row['text'], chunk, number))
    return tasks


def client():
    import openai
    envbridge.apply_to_process()
    return openai.OpenAI(api_key=os.environ['OPENAI_API_KEY'])


def read_state():
    if os.path.exists(STATE):
        with open(STATE, encoding='utf-8') as handle:
            return json.load(handle)
    return {'done_chunks': [], 'spent_usd': 0.0, 'labels': 0, 'broken': [],
            'missing': 0, 'extra': 0}


def write_state(state):
    with open(STATE, 'w', encoding='utf-8') as handle:
        json.dump(state, handle, ensure_ascii=False, indent=1)


def build_requests(tasks, corpus, path):
    with open(path, 'w', encoding='utf-8') as handle:
        for qid, text, chunk, number in tasks:
            cards = [corpus[pid] for pid in chunk]
            handle.write(json.dumps({
                'custom_id': '%s#%d' % (qid, number),
                'method': 'POST',
                'url': '/v1/responses',
                'body': {
                    'model': MODEL,
                    'max_output_tokens': MAX_OUTPUT,
                    'instructions': judging.INSTRUCTION,
                    'input': judging.user_text(text, cards),
                    'reasoning': {'effort': 'none'},
                    'text': {'format': {'type': 'json_schema',
                                        'name': 'reply',
                                        'strict': True,
                                        'schema': judging.SCHEMA}},
                },
            }, ensure_ascii=False) + '\n')


def collect(content, chunks, state):
    rows, tokens = [], {'input': 0, 'output': 0, 'cache_read': 0}
    for line in content.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        qid, chunk = chunks[item['custom_id']]
        body = (item.get('response') or {}).get('body') or {}
        usage = body.get('usage') or {}
        tokens['input'] += usage.get('input_tokens', 0)
        tokens['output'] += usage.get('output_tokens', 0)
        tokens['cache_read'] += (usage.get('input_tokens_details') or {}).get(
            'cached_tokens', 0)
        text = ''
        for block in body.get('output') or []:
            for piece in block.get('content') or []:
                text += piece.get('text') or ''
        try:
            data = orclient.parse_json_object(text)
        except ValueError as error:
            state['broken'].append({'custom_id': item['custom_id'],
                                    'error': str(error)[:200]})
            continue
        labels, missing, extra = judging.parse_verdicts(data, chunk)
        state['missing'] += len(missing)
        state['extra'] += len(extra)
        for pid, label in labels.items():
            rows.append({'query_id': qid, 'problem_id': pid, 'label': label})
    return rows, tokens


def run():
    pool, corpus = load()
    tasks = ordered_tasks(pool)
    chunks_by_id = {'%s#%d' % (qid, number): (qid, chunk)
                    for qid, _t, chunk, number in tasks}
    parts = [tasks[i:i + CHUNK] for i in range(0, len(tasks), CHUNK)]
    state = read_state()
    api = client()

    counter = orclient.Client(
        providers={}, costs_path=os.path.join(HERE, 'costs.json'),
        failures_path=os.path.join(HERE, 'failures.jsonl'),
        budgets=orclient.BUDGETS)
    print('Частей %d по %d пачек; уже сделано %d; остаток потолка $%.2f'
          % (len(parts), CHUNK, len(state['done_chunks']),
             counter.remaining(PROVIDER)))

    for index, part in enumerate(parts):
        if index in state['done_chunks']:
            continue
        forecast = orclient.price_of_tokens(
            PROVIDER, MODEL, len(part) * 9099, len(part) * 237) * BATCH_DISCOUNT
        if forecast > counter.remaining(PROVIDER):
            print('ОСТАНОВКА: часть %d не помещается в остаток потолка.' % index)
            break

        path = os.path.join(HERE, 'batch_part_%02d.jsonl' % index)
        build_requests(part, corpus, path)
        with open(path, 'rb') as handle:
            uploaded = api.files.create(file=handle, purpose='batch')
        batch = api.batches.create(input_file_id=uploaded.id,
                                   endpoint='/v1/responses',
                                   completion_window='24h')
        print('часть %d/%d: пакет %s' % (index + 1, len(parts), batch.id))

        while batch.status in ('validating', 'in_progress', 'finalizing'):
            time.sleep(POLL_SECONDS)
            batch = api.batches.retrieve(batch.id)
        if batch.status != 'completed':
            print('   ОТКАЗ: %s %s' % (batch.status, batch.errors))
            break

        content = api.files.content(batch.output_file_id).text
        rows, tokens = collect(content, chunks_by_id, state)
        with open(LABELS, 'a', encoding='utf-8') as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + '\n')

        fresh = max(tokens['input'] - tokens['cache_read'], 0)
        cost = orclient.price_of_tokens(
            PROVIDER, MODEL, fresh, tokens['output'],
            tokens['cache_read']) * BATCH_DISCOUNT

        class _Reply(object):
            input_tokens = fresh
            output_tokens = tokens['output']
            cache_read_tokens = tokens['cache_read']
            reasoning_tokens = 0
            cost_usd = cost

        counter._record('2. судья sol (batch)', PROVIDER, MODEL, _Reply(), cost)
        state['done_chunks'].append(index)
        state['spent_usd'] = round(state['spent_usd'] + cost, 4)
        state['labels'] += len(rows)
        write_state(state)
        os.remove(path)
        print('   готово: меток %d, $%.2f, всего потрачено $%.2f, остаток $%.2f'
              % (len(rows), cost, counter.spent[PROVIDER],
                 counter.remaining(PROVIDER)))

    print('\nЧастей сделано %d из %d, меток %d, пропущено %d, лишних %d, '
          'неразобранных %d' % (len(state['done_chunks']), len(parts),
                                state['labels'], state['missing'],
                                state['extra'], len(state['broken'])))
    print('Потрачено у OpenAI $%.2f из $%.2f'
          % (counter.spent[PROVIDER], orclient.BUDGETS[PROVIDER]))
    return 0 if len(state['done_chunks']) == len(parts) else 2


def status():
    state = read_state()
    pool, _ = load()
    parts = math.ceil(len(ordered_tasks(pool)) / CHUNK)
    print('Частей сделано %d из %d, меток %d, потрачено $%.2f'
          % (len(state['done_chunks']), parts, state['labels'],
             state['spent_usd']))
    return 0


if __name__ == '__main__':
    if '--run' in sys.argv:
        sys.exit(run())
    if '--status' in sys.argv:
        sys.exit(status())
    print(__doc__)
    sys.exit(1)
