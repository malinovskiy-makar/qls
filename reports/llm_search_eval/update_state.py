# -*- coding: utf-8 -*-
"""Дописать в STATE.json итоги фаз 0 и 1. Базу не трогает."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
state = json.load(open(os.path.join(HERE, 'STATE.json'), encoding='utf-8'))
queries = json.load(open(os.path.join(HERE, 'queries.json'), encoding='utf-8'))
timing = json.load(open(os.path.join(HERE, 'timing.json'), encoding='utf-8'))
pool = [json.loads(line) for line in
        open(os.path.join(HERE, 'pool.jsonl'), encoding='utf-8')]

state['phase'] = 'фазы 0 и 1 (без S_concept) сделаны; ждём ключ OpenRouter'
state['owner_answers_20260909'] = {
    'эталон': '61 различная формулировка; 10 с ручной разметкой внутри как контроль. Все «119» и «129» в задании читать как «61».',
    'формула': 'S0 — то, что в банке: v2_focus_repeat, версия 95.',
    'смета': 'утверждена, $21,15 при бюджете $35; судья GPT-5.6 Sol остаётся.',
    'ключ': 'владелец добавит OPENROUTER_API_KEY в .env сам; до этого — всё, что не требует API.',
}
state['formula_pinned'] = {'spec': 'v2_focus_repeat', 'version': 95,
                           'model': 'BAAI/bge-m3', 'build': 'bge-m3/st-fp32',
                           'min_score_setting': 0.40}
state['queries'] = {
    'total': len(queries),
    'короткий': sum(1 for q in queries if q['type'] == 'короткий'),
    'описательный': sum(1 for q in queries if q['type'] == 'описательный'),
    'с ручной разметкой': sum(1 for q in queries if q['manual_id']),
    'файл': 'reports/llm_search_eval/queries.json',
    'правится руками': 'reports/llm_search_eval/query_types.csv',
    'ВНИМАНИЕ': ('Коротких по эвристике всего 2 из 61 — деление по типу '
                 'запроса в таком виде метрику не разделит. Живые '
                 'формулировки владельца почти все описательные.'),
}
state['phase_0'] = {
    'провайдер': 'problems/ai/providers.py: OpenRouterProvider, 15 тестов',
    'клиент замера': 'reports/llm_search_eval/orclient.py: бюджет, 3 попытки, журнал отказов, разбор JSON — 22 теста',
    'повторы': 'в клиенте, а не в провайдере: ни один из четырёх соседей по файлу не ретраит сам',
    'счётчик': 'reports/llm_search_eval/costs.json (создаётся первым вызовом)',
    'потрачено_usd': 0.0,
}
sizes = [len(r['pool']) for r in pool]
state['phase_1'] = {
    'ноги': ['S0 dense (v2_focus_repeat)', 'S1 bm25 (pymorphy3 + bm25s)',
             'S2 rrf k=60'],
    'S_concept': 'не собрана: нужен ключ OpenRouter',
    'корпус': timing['dense_index_rows'],
    'пул': {'min': min(sizes), 'max': max(sizes),
            'mean': round(sum(sizes) / len(sizes), 1)},
    'якорь_в_пуле': sum(1 for r in pool if r['anchor_in_pool']),
    'якорь_в_сыром_объединении': 30,
    'якорь_убран_как_дубль': 4,
    'якорь_вне_топ30_обеих_ног': 31,
    'убрано_дублей_всего': sum(len(r['dropped_dups']) for r in pool),
    'перекрытие_ног_среднее': 8.0,
    'время': {
        'сборка_bm25_с': timing.get('bm25_build_s'),
        'поиск_bm25_мс_на_запрос': timing.get('bm25_search_per_query_ms'),
        'кодирование_61_запроса_с': timing.get('encode_queries_s'),
        'сборка_плотного_индекса_с': timing.get('dense_index_s'),
    },
    'инварианты': 'все проверены check_pool: размер 30…200, только видимые, без повторов, ни одной пары из дедуп-группы',
}
json.dump(state, open(os.path.join(HERE, 'STATE.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('STATE.json обновлён')
