"""Отбор кандидатов экзамена: воронка, пул, квоты, пачки. Чистые функции.

На вход — записи `problems/ai_exam/bank.py::load_records` (словари), на
выход — строки candidates.jsonl. К базе модуль не обращается, поэтому тот
же seed на том же банке даёт тот же файл байт в байт.

Воронка — двенадцать фильтров строго по порядку; числа после каждого
только убывают. Если пул мал, фильтры ослабляются по одному (а → б → в) —
правило записано в `build_pool` и в docs/AI_EXAM.md.
"""
import hashlib
import json
import random
from collections import Counter, defaultdict

from problems import problem_types
from problems.ai_exam.numbers import propose_key
from problems.models import Problem
from problems.sections import section_of

FIGURE_MARKER = '[[FIGURE:'
#: `AnswerSecondOpinion.resolution`: «права модель, задача в брак».
MODEL_RIGHT = 'model_right'

#: Строгие пороги воронки и три ослабления по порядку.
STRICT = {
    'text_qualities': (str(Problem.TextQuality.CLEAN),),
    'min_solution': 200,
    'none_ok_topics': frozenset(),
}
RELAX_A = 'а: text_quality допускает «мелкие_дефекты»'
RELAX_B = 'б: решение от 80 знаков'
RELAX_C = 'в: в темах, где меньше 8 задач, допускается ключ none'

#: Правило решения после разведки.
POOL_MIN, TOPICS_MIN, TOPIC_SIZE = 600, 24, 8
#: Ниже этого после всех трёх ослаблений — СТОП, решает владелец.
STOP_POOL, STOP_TOPICS, STOP_TOPIC_SIZE = 350, 20, 5

STATEMENT_MIN, STATEMENT_MAX, PARTS_MAX = 100, 4000, 6
SOURCE_CAP = 3

EASY, MEDIUM, HARD, UNRATED = 'лёгкая', 'средняя', 'сложная', 'без оценки'
#: Порядок обхода уровней внутри темы.
LEVEL_ROUND = (MEDIUM, HARD, EASY, UNRATED)
LEVELS = (EASY, MEDIUM, HARD, UNRATED)
KIND_RANK = {'exact': 0, 'extracted': 1, 'none': 2}
_TEST_KINDS = (problem_types.SINGLE, problem_types.BOOLEAN, problem_types.MULTI)


# ── Запись задачи ───────────────────────────────────────────────────────

def level_of(difficulty):
    if difficulty in (1, 2):
        return EASY
    if difficulty == 3:
        return MEDIUM
    if difficulty in (4, 5):
        return HARD
    return UNRATED


def asks_of(record):
    """Вопросы задачи: вся задача, если подпунктов нет, иначе каждый
    подпункт (ответ — `ProblemPart.answer`). К каждому — предложенный ключ."""
    if not record['parts']:
        sources = [(None, '', record['answer'])]
    else:
        sources = [(p['id'], p['label'], p['answer']) for p in record['parts']]
    asks = []
    for part_id, label, raw in sources:
        key = propose_key(raw)
        asks.append({'part_id': part_id, 'label': label or '',
                     'bank_answer': raw or '', 'value': key['value'],
                     'unit': key['unit'], 'percent': key['percent'],
                     'kind': key['kind']})
    return asks


def key_kind(record):
    """Худший вид ключа среди вопросов задачи: exact < extracted < none."""
    return max((a['kind'] for a in record['asks']), key=KIND_RANK.get)


def statement_hash(record):
    """sha256 условия, подпунктов и ответов: ловит правку банка после
    проверки — ключ, утверждённый человеком, тогда устарел."""
    payload = {
        'statement': record['statement'] or '',
        'answer': record['answer'] or '',
        'parts': [[p['label'] or '', p['statement'] or '', p['answer'] or '']
                  for p in record['parts']],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _text_len(record):
    return len((record['statement'] or '').strip()) + sum(
        len((p['statement'] or '').strip()) for p in record['parts'])


def _has_figure(record):
    texts = [record['statement'] or ''] + [p['statement'] or '' for p in record['parts']]
    return any(FIGURE_MARKER in t for t in texts)


def _open_dispute(opinion):
    if opinion is None:
        return False
    if opinion['resolution'] == MODEL_RIGHT:
        return True
    return not opinion['agrees'] and not opinion['resolved']


def _one_per_dup_group(records):
    """С `dup_is_best`, иначе с меньшим id — среди дошедших до этого шага."""
    keep = {}
    for record in records:
        group = record['dup_group']
        if not group:
            continue
        best = keep.get(group)
        if (best is None
                or (record['dup_is_best'] and not best['dup_is_best'])
                or (record['dup_is_best'] == best['dup_is_best']
                    and record['id'] < best['id'])):
            keep[group] = record
    return [r for r in records
            if not r['dup_group'] or keep[r['dup_group']] is r]


# ── Воронка ─────────────────────────────────────────────────────────────

def steps(params):
    """[(ключ, подпись, функция список → список)] — двенадцать фильтров."""
    qualities = params['text_qualities']
    min_solution = params['min_solution']
    none_ok = params['none_ok_topics']

    def each(test):
        return lambda records: [r for r in records if test(r)]

    def key_ok(r):
        if r['key_kind'] != 'none':
            return True
        return bool(none_ok.intersection(r['topics']))

    return [
        ('nature', 'task_nature = расчётная',
         each(lambda r: r['task_nature'] == Problem.TaskNature.CALC)),
        ('consistency', 'answer_consistency = согласован',
         each(lambda r: r['answer_consistency'] == Problem.AnswerConsistency.AGREES)),
        ('text', 'text_quality ∈ {%s}' % ', '.join(qualities),
         each(lambda r: r['text_quality'] in qualities)),
        ('solution', 'решение от %d знаков, solution_needs_review = False' % min_solution,
         each(lambda r: len((r['solution'] or '').strip()) >= min_solution
              and not r['solution_needs_review'])),
        ('single', 'multiple_problems = False',
         each(lambda r: not r['multiple_problems'])),
        ('not_test', 'не тест с вариантами (single / boolean / multi)',
         each(lambda r: problem_types.test_kind(r['problem_type']) not in _TEST_KINDS)),
        ('no_figure', 'без картинки: нет [[FIGURE: в условии и подпунктах',
         each(lambda r: not _has_figure(r))),
        ('size', 'условие с подпунктами %d–%d знаков, подпунктов ≤ %d'
         % (STATEMENT_MIN, STATEMENT_MAX, PARTS_MAX),
         each(lambda r: STATEMENT_MIN <= _text_len(r) <= STATEMENT_MAX
              and len(r['parts']) <= PARTS_MAX)),
        ('key', 'ключ предлагается на каждый вопрос (exact или extracted)'
         + (' — в %d малых темах допускается none' % len(none_ok) if none_ok else ''),
         each(key_ok)),
        ('dup', 'одна задача на группу копий', _one_per_dup_group),
        ('topic', 'есть каноническая тема', each(lambda r: bool(r['topics']))),
        ('opinion', 'нет неразобранного расхождения второго мнения',
         each(lambda r: not _open_dispute(r['opinion']))),
    ]


def prepare(records):
    """Дописать в записи вопросы и вид ключа (один раз, до воронки)."""
    for record in records:
        record['asks'] = asks_of(record)
        record['key_kind'] = key_kind(record)
    return records


def funnel(records, params):
    """(пул, [(ключ, подпись, осталось)]) — числа после каждого фильтра."""
    counts = []
    current = list(records)
    for key, label, step in steps(params):
        current = step(current)
        counts.append((key, label, len(current)))
    return current, counts


# ── Своя тема ───────────────────────────────────────────────────────────

def own_topics(pool, topics):
    """id задачи → своя тема: из её канонических та, у которой пул меньше
    (при равенстве — меньший Topic.order, затем id)."""
    sizes = Counter(t for r in pool for t in r['topics'])
    return {r['id']: min(r['topics'],
                         key=lambda t: (sizes[t], topics[t]['order'], t))
            for r in pool}


def topic_counts(pool, topics):
    return Counter(own_topics(pool, topics).values())


def _enough(pool, topics, size_min, topics_min, pool_min):
    counts = topic_counts(pool, topics)
    big = sum(1 for n in counts.values() if n >= size_min)
    return len(pool) >= pool_min and big >= topics_min


def build_pool(records, topics):
    """Пул по правилу решения.

    Строгая воронка; не хватает (пул < 600 или тем с 8+ задачами < 24) —
    ослабления по одному: а, б, в. После всех трёх пул < 350 или тем с 5+
    задачами < 20 → stop=True: решает владелец.

    Возвращает {'pool', 'funnel', 'relaxed', 'params', 'stop', 'attempts'};
    в `attempts` — воронка каждой попытки, для RECON.md.
    """
    params = dict(STRICT)
    relaxed = []
    plan = [
        (RELAX_A, lambda p, _pool: p.update(text_qualities=(
            str(Problem.TextQuality.CLEAN), str(Problem.TextQuality.MINOR)))),
        (RELAX_B, lambda p, _pool: p.update(min_solution=80)),
        (RELAX_C, lambda p, pool: p.update(none_ok_topics=frozenset(
            t for t in topics
            if topic_counts(pool, topics).get(t, 0) < TOPIC_SIZE))),
    ]
    attempts = []

    def attempt():
        pool, counts = funnel(records, params)
        sizes = topic_counts(pool, topics)
        attempts.append({
            'relaxed': list(relaxed), 'funnel': counts, 'pool': len(pool),
            'topics_8': sum(1 for n in sizes.values() if n >= TOPIC_SIZE),
            'topics_5': sum(1 for n in sizes.values() if n >= STOP_TOPIC_SIZE),
        })
        return pool, counts

    pool, counts = attempt()
    for label, apply in plan:
        if _enough(pool, topics, TOPIC_SIZE, TOPICS_MIN, POOL_MIN):
            break
        apply(params, pool)
        relaxed.append(label)
        pool, counts = attempt()
    stop = (not _enough(pool, topics, TOPIC_SIZE, TOPICS_MIN, POOL_MIN)
            and not _enough(pool, topics, STOP_TOPIC_SIZE, STOP_TOPICS, STOP_POOL))
    return {'pool': pool, 'funnel': counts, 'relaxed': relaxed,
            'params': params, 'stop': stop, 'attempts': attempts}


# ── Отбор ───────────────────────────────────────────────────────────────

def _order_key(topics):
    return lambda t: (topics[t]['order'], t)


def quotas(sizes, count, topics):
    """Тема → сколько задач брать.

    Квота = count // число тем с непустым пулом; остаток — по одной темам с
    самым большим пулом. Нехватку темы забирают темы с наибольшим остатком
    пула, по одной задаче за круг.
    """
    live = sorted((t for t, n in sizes.items() if n > 0), key=_order_key(topics))
    if not live:
        return {}
    base, rest = divmod(count, len(live))
    target = {t: base for t in live}
    for t in sorted(live, key=lambda t: (-sizes[t], topics[t]['order'], t))[:rest]:
        target[t] += 1
    alloc = {t: min(target[t], sizes[t]) for t in live}
    shortage = sum(target.values()) - sum(alloc.values())
    while shortage > 0:
        open_ = sorted((t for t in live if sizes[t] > alloc[t]),
                       key=lambda t: (-(sizes[t] - alloc[t]), topics[t]['order'], t))
        if not open_:
            break
        for t in open_:
            if shortage == 0:
                break
            alloc[t] += 1
            shortage -= 1
    return alloc


def _source_key(record):
    # Задача без источника ни с кем источник не делит.
    return record['source_id'] if record['source_id'] is not None else ('-', record['id'])


def pick_topic(records, quota, rank):
    """Задачи темы в порядке взятия: по кругу уровней средняя → сложная →
    лёгкая → без оценки; в уровне exact раньше extracted, дальше порядок
    seed. Не больше трёх задач одного источника, пока есть другие."""
    queues = {level: [] for level in LEVEL_ROUND}
    for record in records:
        queues[level_of(record['difficulty'])].append(record)
    for queue in queues.values():
        queue.sort(key=lambda r: (KIND_RANK[r['key_kind']], rank[r['id']]))

    used = Counter()
    picked = []

    def free(record):
        return used[_source_key(record)] < SOURCE_CAP

    while len(picked) < quota and any(queues.values()):
        for level in LEVEL_ROUND:
            if len(picked) >= quota:
                break
            queue = queues[level]
            if not queue:
                continue
            item = next((r for r in queue if free(r)), None)
            if item is None:
                if any(free(r) for q in queues.values() for r in q):
                    continue
                item = queue[0]
            queue.remove(item)
            used[_source_key(item)] += 1
            picked.append(item)
    return picked


def select(pool, topics, count, chunks, seed):
    """Строки candidates.jsonl в порядке (пачка, номер в пачке)."""
    rng = random.Random(seed)
    ids = sorted(r['id'] for r in pool)
    rng.shuffle(ids)
    rank = {pk: i for i, pk in enumerate(ids)}

    own = own_topics(pool, topics)
    by_topic = defaultdict(list)
    for record in pool:
        by_topic[own[record['id']]].append(record)
    sizes = {t: len(rs) for t, rs in by_topic.items()}
    alloc = quotas(sizes, count, topics)

    order = sorted(alloc, key=_order_key(topics))
    picks = {t: pick_topic(by_topic[t], alloc[t], rank) for t in order}

    # Пачки: задачи темы раздаются по кругу общим счётчиком — размеры
    # пачек различаются не больше чем на одну задачу.
    per_chunk = {c: defaultdict(list) for c in range(1, chunks + 1)}
    counter = 0
    for t in order:
        for record in picks[t]:
            per_chunk[counter % chunks + 1][t].append(record)
            counter += 1

    rows = []
    for chunk in range(1, chunks + 1):
        lists = per_chunk[chunk]
        n = 0
        depth = max((len(v) for v in lists.values()), default=0)
        for i in range(depth):
            for t in order:
                if i < len(lists[t]):
                    n += 1
                    rows.append(candidate_row(lists[t][i], topics[t], chunk, n, seed))
    return rows


def candidate_row(record, topic, chunk, n, seed):
    return {
        'id': record['id'],
        'topic': topic['name'],
        'section': section_of(topic['name']),
        'difficulty': record['difficulty'],
        'level': level_of(record['difficulty']),
        'problem_type': record['problem_type'] or '',
        'source': record['source'],
        'statement_hash': statement_hash(record),
        'asks': record['asks'],
        'chunk': chunk,
        'n': n,
        'seed': seed,
    }


def dump_jsonl(rows):
    """Байты candidates.jsonl: порядок ключей и перевод строки закреплены."""
    return ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n'
                   for row in rows).encode('utf-8')
