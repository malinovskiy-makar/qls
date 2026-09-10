# -*- coding: utf-8 -*-
"""Нога S_concept: разбор запроса по карте понятий моделью GLM-5.3-Flash.

Вход модели: запрос плюс список 29 канонических тем и 344 тегов. Список
один и тот же на все запросы и стоит ПЕРВЫМ — так у него есть шанс попасть
в кэш префикса провайдера; в смету эта экономия не заложена.

Выход: {topics ≤3, tags ≤6, concepts_free ≤8, difficulty?, problem_type?}.
`concepts_free` сопоставляются с закрытым словарём `EconConcept` точным
совпадением после нормализации регистра и «ё». Несопоставленное уходит в
`concepts_offlist.jsonl` и в отчёт, но НЕ в пул: понятия только из словаря.

Кандидаты запроса — два источника, по топ-50 каждый:
  счёт пересечения — совпавшие понятия × 2 + совпавшие теги;
  BM25 по строке из канонических имён найденных понятий.

Запуск:
    venv313\\Scripts\\python.exe reports/llm_search_eval/run_concept.py [--limit N]
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

import concepts as concept_dict  # noqa: E402
import envbridge  # noqa: E402
import orclient  # noqa: E402
from catalog import lexical_bm25 as lex  # noqa: E402
from problems.ai.providers import get_provider  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
QUERIES = os.path.join(HERE, 'queries.json')
CORPUS = os.path.join(HERE, 'corpus.jsonl')
INDEX_DIR = os.path.join(HERE, 'bm25_index')
OUT = os.path.join(HERE, 'concept_runs.json')
OFFLIST = os.path.join(HERE, 'concepts_offlist.jsonl')
PARSED = os.path.join(HERE, 'query_parsed.jsonl')

PROVIDER, MODEL = 'zai', 'glm-5.3-flash'
TOP_K = 50

SCHEMA = {
    'type': 'object',
    'properties': {
        'topics': {'type': 'array', 'items': {'type': 'string'}},
        'tags': {'type': 'array', 'items': {'type': 'string'}},
        'concepts_free': {'type': 'array', 'items': {'type': 'string'}},
        'difficulty': {'type': ['integer', 'null']},
        'problem_type': {'type': ['string', 'null']},
    },
    'required': ['topics', 'tags', 'concepts_free'],
    'additionalProperties': False,
}

INSTRUCTION = (
    'Ты разбираешь поисковый запрос преподавателя олимпиадной экономики.\n'
    'Верни JSON: topics — не более 3 тем ТОЧНО из списка тем; tags — не '
    'более 6 тегов ТОЧНО из списка тегов; concepts_free — не более 8 '
    'экономических понятий, которые обязана содержать подходящая задача '
    '(свободные формулировки, по одному понятию в строке); difficulty — '
    'число 1–5 или null; problem_type — короткая строка или null.\n'
    'Не придумывай тем и тегов вне списков. Если ничего не подходит, '
    'верни пустой список.'
)


def load_map():
    from problems.models import Tag, Topic
    topics = sorted(Topic.objects.filter(is_canonical=True)
                    .values_list('name', flat=True))
    tags = sorted(Tag.objects.filter(kind='canonical')
                  .values_list('name', flat=True))
    return topics, tags


def load_dictionary():
    from problems.models import EconConcept
    return concept_dict.build_dictionary(
        EconConcept.objects.values_list('canonical', flat=True))


def main():
    limit = None
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])

    envbridge.apply_to_process()
    with open(QUERIES, encoding='utf-8') as f:
        queries = json.load(f)
    if limit:
        queries = queries[:limit]
    with open(CORPUS, encoding='utf-8') as f:
        corpus = [json.loads(line) for line in f]

    topics, tags = load_map()
    dictionary = load_dictionary()
    index = lex.load_index(INDEX_DIR)

    by_concept, by_tag = {}, {}
    for row in corpus:
        for name in row['concepts']:
            by_concept.setdefault(name, set()).add(row['id'])
        for name in row['tags']:
            by_tag.setdefault(name, set()).add(row['id'])

    prefix = ('СПИСОК ТЕМ (%d):\n%s\n\nСПИСОК ТЕГОВ (%d):\n%s'
              % (len(topics), '\n'.join(topics), len(tags), '\n'.join(tags)))

    client = orclient.Client(
        providers={PROVIDER: get_provider('glm')},
        costs_path=os.path.join(HERE, 'costs.json'),
        failures_path=os.path.join(HERE, 'failures.jsonl'),
        budgets=orclient.BUDGETS)

    runs, parsed_rows, offlist_rows = {}, [], []
    started = time.perf_counter()
    for query in queries:
        qid = query['query_id']
        reply = client.call(
            stage='1. разбор запроса (S_concept)', query_id=qid,
            provider=PROVIDER, model=MODEL,
            system_blocks=[prefix, INSTRUCTION],
            user_text='ЗАПРОС: %s' % query['text'],
            schema=SCHEMA, max_tokens=800, timeout=120, estimated_usd=0.01)
        data = orclient.parse_json_object(reply.text)

        found, offlist = concept_dict.match(data.get('concepts_free') or [],
                                            dictionary)
        picked_tags = [t for t in (data.get('tags') or []) if t in by_tag]
        rejected_tags = [t for t in (data.get('tags') or []) if t not in by_tag]

        score = {}
        for name in found:
            for pid in by_concept.get(name, ()):
                score[pid] = score.get(pid, 0) + concept_dict.CONCEPT_WEIGHT
        for name in picked_tags:
            for pid in by_tag.get(name, ()):
                score[pid] = score.get(pid, 0) + concept_dict.TAG_WEIGHT
        by_overlap = sorted(score, key=lambda pid: (-score[pid], pid))[:TOP_K]

        by_bm25 = []
        if found:
            by_bm25 = [pid for pid, _ in
                       lex.search(index, ' '.join(found), TOP_K)]

        merged, seen = [], set()
        for pid in by_overlap + by_bm25:
            if pid not in seen:
                seen.add(pid)
                merged.append(pid)
        runs[qid] = merged

        parsed_rows.append({
            'query_id': qid, 'text': query['text'],
            'topics': data.get('topics') or [], 'tags_kept': picked_tags,
            'tags_rejected': rejected_tags,
            'concepts_matched': found, 'concepts_offlist': offlist,
            'difficulty': data.get('difficulty'),
            'problem_type': data.get('problem_type'),
            'by_overlap': len(by_overlap), 'by_bm25': len(by_bm25),
            'merged': len(merged),
        })
        for name in offlist:
            offlist_rows.append({'query_id': qid, 'concept': name})

    elapsed = time.perf_counter() - started
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(runs, f, ensure_ascii=False)
    with open(PARSED, 'w', encoding='utf-8') as f:
        for row in parsed_rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    with open(OFFLIST, 'w', encoding='utf-8') as f:
        for row in offlist_rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

    matched = sum(len(r['concepts_matched']) for r in parsed_rows)
    off = sum(len(r['concepts_offlist']) for r in parsed_rows)
    print('Запросов разобрано: %d за %.1f с' % (len(parsed_rows), elapsed))
    print('Понятий предложено: %d, из словаря %d (%.0f%%), вне словаря %d'
          % (matched + off, matched,
             100.0 * matched / max(matched + off, 1), off))
    print('Тегов отвергнуто как несловарные: %d'
          % sum(len(r['tags_rejected']) for r in parsed_rows))
    print('Кандидатов на запрос: среднее %.1f'
          % (sum(r['merged'] for r in parsed_rows) / max(len(parsed_rows), 1)))
    print('Потрачено у Z.ai: $%.4f из $%.2f'
          % (client.spent['zai'], orclient.BUDGETS['zai']))


if __name__ == '__main__':
    main()
