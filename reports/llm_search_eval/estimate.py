# -*- coding: utf-8 -*-
"""Смета сессии по замеренным длинам карточек. Ни одного вызова API."""
import json

# Цены OpenRouter, $ за миллион токенов (GET /api/v1/models, 09.09.2026).
PRICES = {
    'z-ai/glm-5.3-flash':        (0.075, 0.25),
    'z-ai/glm-5.3':              (1.40, 4.40),
    'anthropic/claude-haiku-4.5': (1.00, 5.00),
    'anthropic/claude-sonnet-5': (2.00, 10.00),
    'openai/gpt-5.6-sol':        (2.00, 10.00),
    'openai/gpt-5.6-terra':      (2.00, 12.00),
    'deepseek/deepseek-v4-pro':  (0.87, 1.74),
}

# Замерено на 200 случайных видимых задачах, tiktoken o200k_base.
JUDGE_CARD = 349.4
RERANK_CARD = 162.8
MAP_PREFIX = 4213

QUERIES = 61          # различных формулировок (C58 ⊂ C65)
POOL = 110            # ожидаемый размер пула на запрос; пересчитаю по факту в фазе 1
JUDGE_BATCH = 25
RERANK_BATCH = 50

# Запас на рассуждение у моделей, которые думают перед ответом (доля от выхода).
REASONING_MULT = {'openai/gpt-5.6-sol': 4.0, 'openai/gpt-5.6-terra': 4.0,
                  'deepseek/deepseek-v4-pro': 2.0, 'anthropic/claude-sonnet-5': 2.0}

rows = []


def cost(model, tin, tout):
    pin, pout = PRICES[model]
    mult = REASONING_MULT.get(model, 1.0)
    return tin / 1e6 * pin + tout * mult / 1e6 * pout


def add(stage, model, calls, tin_per_call, tout_per_call):
    tin, tout = calls * tin_per_call, calls * tout_per_call
    rows.append({'этап': stage, 'модель': model, 'вызовов': calls,
                 'вход_ткн': round(tin), 'выход_ткн': round(tout),
                 'стоимость_$': round(cost(model, tin, tout), 2)})


import math

# Фаза 1: разбор запроса по карте понятий.
add('1. разбор запроса (S_concept)', 'z-ai/glm-5.3-flash', QUERIES,
    MAP_PREFIX + 350, 220)

# Фаза 2: два судьи на все пары «запрос — кандидат».
pairs = QUERIES * POOL
judge_calls = QUERIES * math.ceil(POOL / JUDGE_BATCH)
for m in ('openai/gpt-5.6-sol', 'deepseek/deepseek-v4-pro'):
    add('2. судья пула', m, judge_calls, JUDGE_BATCH * JUDGE_CARD + 450, JUDGE_BATCH * 12)

# Фаза 3: три реранкера на весь пул.
rr_calls = QUERIES * math.ceil(POOL / RERANK_BATCH)
for m in ('z-ai/glm-5.3-flash', 'z-ai/glm-5.3', 'anthropic/claude-haiku-4.5'):
    add('3. реранкер S3', m, rr_calls, RERANK_BATCH * RERANK_CARD + 450, RERANK_BATCH * 10)

# Фаза 3: финальный проход S4 по топ-30.
add('3. финал S4 + «почему»', 'anthropic/claude-sonnet-5', QUERIES,
    30 * RERANK_CARD + 550, 750)

total = sum(r['стоимость_$'] for r in rows)
retries = round(total * 0.15, 2)

print(f'Запросов: {QUERIES}   пул на запрос (ожидание): {POOL}   пар: {pairs}')
print()
hdr = f"{'этап':<28}{'модель':<28}{'выз.':>6}{'вход':>10}{'выход':>8}{'$':>8}"
print(hdr); print('-' * len(hdr))
for r in rows:
    print(f"{r['этап']:<28}{r['модель']:<28}{r['вызовов']:>6}"
          f"{r['вход_ткн']:>10}{r['выход_ткн']:>8}{r['стоимость_$']:>8.2f}")
print('-' * len(hdr))
print(f"{'ИТОГО по этапам':<62}{total:>8.2f}")
print(f"{'+ 15% на повторы и отказы':<62}{retries:>8.2f}")
print(f"{'ИТОГО с запасом':<62}{total + retries:>8.2f}")
print(f"{'Бюджет сессии':<62}{35.00:>8.2f}")

json.dump({'rows': rows, 'total': round(total, 2), 'with_retries': round(total + retries, 2),
           'queries': QUERIES, 'pool_assumed': POOL, 'budget': 35.0},
          open('reports/llm_search_eval/estimate.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
