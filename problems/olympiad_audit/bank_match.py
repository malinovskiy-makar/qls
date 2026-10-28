# -*- coding: utf-8 -*-
"""«Это задание уже есть в банке?» — кандидаты и подтверждение текстом.

Кандидаты — гибридный поиск сайта по ВСЕМУ банку (решение 09.10.2026):
плотная нога BGE-M3 по запросу «название + условие[:500]» против векторов
`Problem.embedding` (тот же `catalog.semantic._build_index(scope='all')`) и
BM25 (`catalog.lexical_bm25`, сборка строк как у умного поиска), слияние
RRF k = 60, top-20. Порога по косинусу НЕТ: ранжирование у гибрида верное,
а абсолютный косинус к голому тексту низкий (медиана у верных пар 0,73).

Подтверждение — текстом по ключу без разметки (`markup_free_key`): сходство
rapidfuzz ≥ 0,90 или вхождение ≥ 0,90 (задание целиком внутри задачи банка —
агрегатор хранит комплект одной задачей — или наоборот). Плюс числовой
отпечаток (решение 02.09): у пары без различающих чисел текст один — не
доказательство, такая пара идёт на ручной разбор, а не в базу.

Кандидаты считаются один раз и пишутся файлом (`--build-candidates`):
модель весит 2 ГБ, а сухих прогонов плана несколько.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter

from problems.olympiad_official import markup_free_key
from problems.text_dedup import extract_numeric_tokens

RRF_K = 60
TOP_K = 20
POOL_K = 100
CONTAIN_MIN = 150          # короче — частичное сходство врёт
CONTAIN_HEAD = 600         # частичное сходство длинных строк квадратично


def task_text(row):
    """Условие + пункты эталона (как `problem_identity_text` у банка).

    В эталоне v2 пункты обычно УЖЕ стоят в тексте условия — дописываются
    только те, которых там нет, иначе ключ задваивал бы хвост и вхождение в
    задачу-комплект падало бы до 0,74 при дословном совпадении."""
    statement = row.get('statement_md') or ''
    extra = [p.get('text') or '' for p in row.get('parts') or []
             if (p.get('text') or '').strip() and (p.get('text') or '').strip() not in statement]
    return ' '.join([statement] + extra).strip()


def task_key(row):
    return markup_free_key(task_text(row))


def query_text(row):
    title = (row.get('title') or '').strip()
    body = ' '.join((row.get('statement_md') or '').split())[:500]
    return f'{title}. {body}' if title else body


def row_key(row):
    variant = row.get('task_variant') or ''
    return f'{row["event_id"]}:{row["number"]}' + (f':{variant}' if variant else '')


def scores(task, bank):
    """(сходство, вхождение) двух ключей без разметки, 0..1."""
    from rapidfuzz import fuzz
    if not task or not bank:
        return 0.0, 0.0
    ratio = fuzz.ratio(task, bank) / 100.0
    a, b = task[:CONTAIN_HEAD], bank[:CONTAIN_HEAD]
    contain = max(fuzz.partial_ratio(a, bank) if len(a) >= CONTAIN_MIN and len(bank) >= len(a) else 0,
                  fuzz.partial_ratio(b, task) if len(b) >= CONTAIN_MIN and len(task) >= len(b) else 0)
    return ratio, contain / 100.0


#: «300 000» в эталоне (разряды пробелом) и «300000» в банке — одно число;
#: без склейки отпечаток видел бы «300» и «000» и не совпадал. В банке
#: разряды бывают и LaTeX-пробелом: `70\,000`, `70~000`, `70\ 000`, в том
#: числе с пробелами вокруг (`$60 \ 000$`), и переносом строки между
#: группами («200» в конце строки, «000» в начале следующей; гейт 1 И3).
#: Склеиваются только настоящие группы разрядов: 1–3 цифры, затем группы
#: ровно по 3 — иначе перенос строки склеил бы «5» и «100» соседних строк.
#: `2{,}5` — десятичная запятая TeX, её понимает `extract_numeric_tokens`.
_SP = '[ \t   ]'
_SEP = _SP + r'*(?:\\[,;: ]|\\thinspace|\{\s*\}|~)' + _SP + '*|' + _SP + '+'
_SEP_RE = re.compile(_SEP)
_GROUPED = re.compile(r'(?<![\d.,])(\d{1,3}(?:(?:' + _SEP + r')\d{3})+)(?!\d)')
#: Перенос строки — только между группами ровно по 3 цифры («200» / «000»).
_LINE_GROUPS = re.compile(r'(?<![\d.,])(\d{3})' + _SP + r'*\n' + _SP + r'*(?=\d{3}(?!\d))')


def _join_groups(text):
    text = _LINE_GROUPS.sub(r'\1', text or '')
    return _GROUPED.sub(lambda m: _SEP_RE.sub('', m.group(1)), text)


def _numbers(text):
    return extract_numeric_tokens(_join_groups(text))


def numbers_signal(text):
    """'none' — чисел нет; 'weak' — 1–4 различных и все однозначные; 'ok'."""
    nums = _numbers(text)
    if not nums:
        return 'none'
    distinct = set(nums)
    if len(distinct) <= 4 and all(len(n.lstrip('-')) == 1 for n in distinct):
        return 'weak'
    return 'ok'


def numbers_compatible(task_text_, bank_text):
    """Числа одного текста целиком входят в числа другого (мультимножество).

    Однозначные числа не сравниваются: это метки пунктов «1) 2) 3)» и
    номера, которые у копии агрегатора стоят по-своему; различающих
    данных в них нет (решение 02.09 считает их «слабым сигналом»)."""
    def significant(text):
        return Counter({n: k for n, k in _numbers(text).items() if len(n.lstrip('-')) > 1})
    a, b = significant(task_text_), significant(bank_text)
    return not (a - b) or not (b - a)


# ── Кандидаты (тяжёлая часть: модель и индексы) ───────────────────────

def _rrf(*lists):
    fused = {}
    for lst in lists:
        for rank, pid in enumerate(lst):
            fused[pid] = fused.get(pid, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(fused, key=lambda p: (-fused[p], p))


def build_candidates(rows, out_path, log=print):
    """Гибрид top-20 для каждой строки → JSON {ключ строки: [id задач]}."""
    import numpy as np
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
    from sentence_transformers import SentenceTransformer

    from catalog import lexical_bm25 as bm25
    from catalog import semantic
    from problems.embedding_config import EMBEDDING_MAX_SEQ_LENGTH, EMBEDDING_MODEL_NAME
    from problems.models import Problem, ProblemPart

    index = semantic._build_index(scope='all')
    matrix, dense_ids = index['matrix'], np.array(index['ids'])
    log(f'плотный индекс: {matrix.shape[0]} задач с вектором')
    parts_by = {}
    for pid, st in (ProblemPart.objects.order_by('problem_id', 'order')
                    .values_list('problem_id', 'statement').iterator(chunk_size=5000)):
        if st:
            parts_by.setdefault(pid, []).append(st)
    ids, texts = [], []
    qs = (Problem.objects.prefetch_related('topics', 'tags', 'econ_concepts')
          .only('id', 'title', 'title_candidate', 'statement', 'find', 'given'))
    for p in qs.iterator(chunk_size=500):
        ids.append(p.id)
        texts.append(bm25.index_text({
            'title': p.title_candidate or p.title or '', 'statement': p.statement or '',
            'find': p.find or '', 'given': p.given or '', 'parts': parts_by.get(p.id, []),
            'topics': [t.name for t in p.topics.all() if t.is_canonical],
            'tags': [t.name for t in p.tags.all() if t.kind == 'canonical'],
            'concepts': [c.canonical for c in p.econ_concepts.all()]}))
    lexical = bm25.build_index(ids, texts)
    log(f'BM25: {len(ids)} задач')
    model = SentenceTransformer(EMBEDDING_MODEL_NAME, device='cpu')
    model.max_seq_length = EMBEDDING_MAX_SEQ_LENGTH
    queries = [query_text(r) for r in rows]
    vecs = model.encode(queries, batch_size=8, normalize_embeddings=True,
                        show_progress_bar=False).astype('float32')
    out = {}
    for row, vec in zip(rows, vecs):
        sims = matrix @ vec
        top = np.argpartition(-sims, POOL_K)[:POOL_K]
        dense = [int(dense_ids[i]) for i in top[np.argsort(-sims[top])]]
        lex = [pid for pid, _w in bm25.search(lexical, task_text(row), top_k=POOL_K)]
        out[row_key(row)] = _rrf(dense, lex)[:TOP_K]
    meta = {'built_at': __import__('datetime').datetime.now().isoformat(timespec='seconds'),
            'problems': Problem.objects.count(), 'with_vector': int(matrix.shape[0]),
            'rows': len(rows), 'top_k': TOP_K, 'rrf_k': RRF_K}
    with open(out_path, 'w', encoding='utf-8') as handle:
        json.dump({'meta': meta, 'candidates': out}, handle, ensure_ascii=False, indent=0)
    return meta


def load_candidates(path):
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    return data['meta'], data['candidates']


def best_match(row, candidate_ids, bank_keys):
    """Лучший кандидат: (id, сходство, вхождение) по max(сходство, вхождение)."""
    key = task_key(row)
    best = (None, 0.0, 0.0)
    for pid in candidate_ids:
        bank = bank_keys.get(pid)
        if bank is None:
            continue
        ratio, contain = scores(key, bank)
        if max(ratio, contain) > max(best[1], best[2]):
            best = (pid, ratio, contain)
    return best


def summarize(values):
    return dict(Counter(values))
