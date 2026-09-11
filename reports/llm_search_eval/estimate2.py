# -*- coding: utf-8 -*-
"""Смета стоп-гейта 1 по ЗАМЕРЕННЫМ числам, а не по оценкам.

Длины входа и выхода взяты из живых пилотных вызовов 10.09.2026, а не
из прикидок по символам. Где пилота не было (реранкеры), длина карточки
считается токенизатором по НАСТОЯЩИМ кандидатам пула, а выход берётся из
замера соседнего этапа на той же модели.

Кэш префикса в смету НЕ заложен: указание владельца. У Z.ai он на
S_concept сработал (вход 67 свежих токенов из 4 280), и это делает
смету по Z.ai заведомо завышенной — в безопасную сторону.
"""
import json
import math
import os
import sys

import tiktoken

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import judging  # noqa: E402
import orclient  # noqa: E402

JUDGE_BATCH = 25
RERANK_BATCH = 50
FINAL_TOP = 30

#: Замерено пилотом 10.09.2026 на пачках по 25 карточек.
MEASURED = {
    ('openai', 'gpt-5.6-sol'): {'in': 9099, 'out': 237},
    ('openai', 'gpt-5.6-terra'): {'in': 9099, 'out': 237},
    ('deepseek', 'deepseek-v4-pro'): {'in': 10510, 'out': 359},
    ('deepseek', 'deepseek-flash'): {'in': 10510, 'out': 359},
}

#: Выход реранкера: по одной короткой строке на кандидата плюс обёртка.
#: Опора — S_concept на glm-5.3-flash: 186 токенов выхода на вызов при
#: 8 позициях, то есть около 12 токенов на позицию, плюс рассуждение 14.
RERANK_OUT_PER_ITEM = 12
RERANK_REASONING = 60


def rerank_card_tokens(pool, corpus, enc):
    """Средняя длина карточки реранкера по НАСТОЯЩИМ кандидатам пула."""
    seen, lengths = set(), []
    for row in pool:
        for pid in row['pool']:
            if pid in seen:
                continue
            seen.add(pid)
            problem = corpus[pid]
            card = '\n'.join([
                'id: %s' % pid,
                'тема: %s' % ', '.join(problem.get('topics') or []),
                'теги: %s' % ', '.join(problem.get('tags') or []),
                'понятия: %s' % ', '.join(problem.get('concepts') or []),
                'найти: %s' % (problem.get('find') or '')[:200],
                'тип: %s' % (problem.get('problem_type') or ''),
                'сложность: %s' % (problem.get('difficulty') or ''),
                'заголовок: %s' % (problem.get('title') or ''),
            ])
            lengths.append(len(enc.encode(card)))
    return sum(lengths) / len(lengths), len(lengths)


def main():
    enc = tiktoken.get_encoding('o200k_base')
    pool = [json.loads(line) for line in
            open(os.path.join(HERE, 'pool.jsonl'), encoding='utf-8')]
    corpus = {}
    with open(os.path.join(HERE, 'corpus.jsonl'), encoding='utf-8') as handle:
        for line in handle:
            row = json.loads(line)
            corpus[row['id']] = row

    pairs = sum(len(r['pool']) for r in pool)
    judge_batches = sum(len(judging.batches(r['pool'], JUDGE_BATCH))
                        for r in pool)
    rerank_batches = sum(math.ceil(len(r['pool']) / RERANK_BATCH) for r in pool)
    card_tokens, distinct = rerank_card_tokens(pool, corpus, enc)

    print('Запросов %d, пар «запрос — кандидат» %d, различных задач в пулах %d'
          % (len(pool), pairs, distinct))
    print('Пачек: судейских по %d — %d; реранкерных по %d — %d'
          % (JUDGE_BATCH, judge_batches, RERANK_BATCH, rerank_batches))
    print('Карточка реранкера: %.0f токенов (замер по кандидатам пула)\n'
          % card_tokens)

    rows = []

    def add(role, provider, model, calls, tin, tout, note=''):
        cost = orclient.price_of_tokens(provider, model, calls * tin,
                                        calls * tout, peak=False)
        rows.append({'роль': role, 'провайдер': provider, 'модель': model,
                     'вызовов': calls, 'вход': round(calls * tin),
                     'выход': round(calls * tout), 'usd': cost, 'note': note})

    # Фаза 1 — уже потрачено.
    add('разбор запросов (сделано)', 'zai', 'glm-5.3-flash', 91, 67, 186)

    # Фаза 2 — судьи.
    for provider, model in (('openai', 'gpt-5.6-sol'),
                            ('openai', 'gpt-5.6-terra'),
                            ('deepseek', 'deepseek-v4-pro'),
                            ('deepseek', 'deepseek-flash')):
        m = MEASURED[(provider, model)]
        add('судья', provider, model, judge_batches, m['in'], m['out'],
            'замер пилота')

    # Фаза 3 — реранкеры.
    rerank_in = RERANK_BATCH * card_tokens + 400
    rerank_out = RERANK_BATCH * RERANK_OUT_PER_ITEM + RERANK_REASONING
    for provider, model in (('zai', 'glm-5.3-flash'), ('zai', 'glm-5.3'),
                            ('anthropic', 'claude-haiku-4-5')):
        add('сортировщик', provider, model, rerank_batches, rerank_in,
            rerank_out)

    # Тот же судья 1 через Batch API OpenAI: скидка 50 % на вход и выход,
    # ответ приходит в течение часов. Разметка пула это допускает —
    # ждать её никто не будет в реальном времени.
    m = MEASURED[('openai', 'gpt-5.6-sol')]
    batch_cost = orclient.price_of_tokens(
        'openai', 'gpt-5.6-sol', judge_batches * m['in'],
        judge_batches * m['out'], peak=False) / 2
    rows.append({'роль': 'судья через Batch API', 'провайдер': 'openai',
                 'модель': 'gpt-5.6-sol (batch)', 'вызовов': judge_batches,
                 'вход': judge_batches * m['in'],
                 'выход': judge_batches * m['out'], 'usd': batch_cost,
                 'note': 'скидка 50 %'})

    # Фаза 3 — финальный проход.
    add('финал + «почему»', 'anthropic', 'claude-sonnet-5', len(pool),
        FINAL_TOP * card_tokens + 550, 750)

    head = (f"{'роль':<26}{'провайдер':<11}{'модель':<20}{'выз.':>6}"
            f"{'вход':>10}{'выход':>8}{'$':>8}{'+15%':>8}")
    print(head)
    print('-' * len(head))
    for r in rows:
        print(f"{r['роль']:<26}{r['провайдер']:<11}{r['модель']:<20}"
              f"{r['вызовов']:>6}{r['вход']:>10}{r['выход']:>8}"
              f"{r['usd']:>8.2f}{r['usd'] * 1.15:>8.2f}")

    plans = {
        'А. ровно как в задании': {
            'openai': ['gpt-5.6-sol'], 'deepseek': ['deepseek-v4-pro'],
            'zai': ['glm-5.3-flash', 'glm-5.3'],
            'anthropic': ['claude-haiku-4-5', 'claude-sonnet-5']},
        'Б. Sol через Batch API, судья 2 — deepseek-flash': {
            'openai': ['gpt-5.6-sol (batch)'], 'deepseek': ['deepseek-flash'],
            'zai': ['glm-5.3-flash', 'glm-5.3'],
            'anthropic': ['claude-haiku-4-5', 'claude-sonnet-5']},
        'В. Terra вместо Sol, судья 2 — deepseek-flash': {
            'openai': ['gpt-5.6-terra'], 'deepseek': ['deepseek-flash'],
            'zai': ['glm-5.3-flash', 'glm-5.3'],
            'anthropic': ['claude-haiku-4-5', 'claude-sonnet-5']},
    }
    for title, plan in plans.items():
        print('\n%s:' % title)
        for provider, models in plan.items():
            total = sum(r['usd'] for r in rows
                        if r['провайдер'] == provider and r['модель'] in models)
            ceiling = orclient.BUDGETS[provider]
            mark = 'влезает' if total * 1.15 <= ceiling else 'НЕ ВЛЕЗАЕТ'
            print('   %-10s $%6.2f  с запасом 15%% $%6.2f  потолок $%5.2f  %s'
                  % (provider, total, total * 1.15, ceiling, mark))

    json.dump(rows, open(os.path.join(HERE, 'estimate2.json'), 'w',
                         encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
