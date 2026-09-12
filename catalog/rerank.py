# -*- coding: utf-8 -*-
"""catalog/rerank.py — переранжирование пула умного поиска моделью.

За флагом `SMART_SEARCH_RERANK` — и это ЕДИНСТВЕННЫЙ выключатель:
включён флаг, значит работает для всех, в том числе для гостя (13.09.2026,
прежнее «только сотрудникам» снято). Меняет ТОЛЬКО порядок задач в
уже существующей выдаче каталога — рендер, шаблоны, фильтры и пагинация не
задеты вовсе; вызывающая сторона (`catalog/views.py`) просто подставляет
другой список id на вход тому же коду, что рисовал карточки раньше.

Промпт (`INSTRUCTION`/`SCHEMA`), карточка кандидата (`card`) и правило
слияния пачек по баллу (`merge`) — БУКВАЛЬНО те же, что дали nDCG@10
0,77 → 0,95 на офлайн-замере 10.09.2026 (reports/llm_search_eval/,
направление принято в Notion «Решения» 11.09.2026). Их менять без
повторного замера на готовых метках нельзя — правило сессии, не прихоть.
`reports/llm_search_eval/reranking.py` и `poolbuild.py` импортируют эти
имена отсюда, а не дублируют их.

⚠️ ОДНА ДВЕРЬ НАРУЖУ (`problems/ai/core.run`) — ТЕПЕРЬ И ОТСЮДА
(13.09.2026, карточка Notion «Сортировщик поиска зовёт GLMProvider в
обход core.run», поставленная «до выхода на прод»). Раньше модуль звал
`providers.get_provider('glm')` напрямую, и довод был такой: `core.run`
— дверь для ПРОФИЛЕЙ генерации, у неё общий поставщик из `AI_PROVIDER`,
общая модель из `AI_MODEL` и суточный лимит ОБРАЩЕНИЙ на пользователя,
а переранжированию нужен свой поставщик, своя модель и никакого лимита
на пользователя (поиском пользуются и без входа). Довод был верен про
дверь и неверен про вывод: расход поисковой сортировки просто не
попадал в `AiUsageLog`, то есть не был виден нигде рядом с остальными
тратами сайта, и потолка у него не было вовсе.

Теперь у `core.run` есть переопределения (`provider_name`, `model`,
`system`, `parse`) и ВТОРОЙ вид лимита — суточный ДЕНЕЖНЫЙ потолок на
функцию. Поэтому здесь:

* поставщик по-прежнему `glm` и модель по-прежнему
  `SMART_SEARCH_RERANK_MODEL` — они заданы решением владельца
  11.09.2026 и за общей настройкой сайта не ездят;
* суточный лимит обращений на пользователя НЕ применяется
  (`check_limit=False`) — гостю списывать нечего;
* зато применяется потолок `AI_DAILY_COST_CAPS['search_rerank']`, и
  при его исчерпании выдача тихо уходит на базовый порядок;
* свой кэш (час по тексту запроса) и свой лог
  `reports/smart_search_log.jsonl` остаются: они про другое — про
  задержку и про качество сортировки, а не про деньги.
"""
import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FuturesTimeoutError
from concurrent.futures import as_completed
from datetime import datetime, timezone

from django.core.cache import cache

logger = logging.getLogger(__name__)


# ─── Карточка кандидата и промпт сортировщика (замер 10.09.2026) ─────────
#
# ⚠️ НЕ МЕНЯТЬ БЕЗ ПЕРЕМЕРА (правило сессии `feat/smart-search-rerank`,
# CLAUDE.md текущей сессии). `FINAL_INSTRUCTION`/`FINAL_SCHEMA` (с полем
# `why`) сюда намеренно не перенесены: замер 10.09 использовал систему S3
# (только `score`, без объяснений) — см. `reports/llm_search_eval/
# run_rerank.py:SYSTEMS['glm-flash']`, тот же путь `card`+`INSTRUCTION`+
# `SCHEMA`, что и здесь.

BATCH = 50
FIND_CHARS = 200

SCHEMA = {
    'type': 'object',
    'properties': {
        'rows': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'id': {'type': 'integer'},
                    'score': {'type': 'integer'},
                },
                'required': ['id', 'score'],
                'additionalProperties': False,
            },
        },
    },
    'required': ['rows'],
    'additionalProperties': False,
}

INSTRUCTION = (
    'Ты раскладываешь найденные задачи по тому, насколько они подходят '
    'под поисковый запрос преподавателя олимпиадной экономики.\n'
    'Каждому кандидату поставь score от 0 до 100: 100 — репетитор возьмёт '
    'задачу в листок первой, 0 — задача не про то.\n'
    'Верни ровно по одной строке на каждого кандидата, id переписывай без '
    'изменений.'
)


def card(row, concept_hits=None):
    """Короткая карточка кандидата — без условия (см. докстринг модуля)."""
    parts = [
        'id: %s' % row['id'],
        'тема: %s' % ', '.join(row.get('topics') or []),
        'теги: %s' % ', '.join(row.get('tags') or []),
        'понятия: %s' % ', '.join(row.get('concepts') or []),
        'найти: %s' % (row.get('find') or '')[:FIND_CHARS],
        'тип: %s' % (row.get('problem_type') or ''),
        'сложность: %s' % (row.get('difficulty') if row.get('difficulty')
                           is not None else ''),
        'заголовок: %s' % (row.get('title') or ''),
    ]
    if concept_hits:
        parts.append('совпало понятий из запроса: %d' % concept_hits)
    return '\n'.join(parts)


def user_text(query, rows, hits=None):
    hits = hits or {}
    cards = '\n\n'.join(card(row, hits.get(row['id'])) for row in rows)
    return 'ЗАПРОС ПРЕПОДАВАТЕЛЯ: %s\n\nКАНДИДАТЫ:\n\n%s' % (query, cards)


def clamp(score):
    return max(0, min(100, int(score)))


def merge(chunks, all_ids=None):
    """Баллы из нескольких пачек → один порядок по убыванию.

    Кандидат, которому модель балла не дала, уходит в хвост, а не
    получает ноль молча.
    """
    scores = {}
    for chunk in chunks:
        for pid, score in chunk.items():
            scores[int(pid)] = clamp(score)
    ranked = sorted(scores, key=lambda pid: (-scores[pid], pid))
    if all_ids:
        ranked += [pid for pid in all_ids if pid not in scores]
    return ranked


def parse_scores(data, expected_ids):
    """Ответ модели → ({id: балл}, не оценённые, лишние)."""
    scores, extra = {}, []
    expected = set(expected_ids)
    for key, value in data.items():
        try:
            pid, score = int(key), int(value)
        except (TypeError, ValueError):
            extra.append(key)
            continue
        if pid not in expected:
            extra.append(key)
            continue
        scores[pid] = clamp(score)
    missing = [pid for pid in expected_ids if pid not in scores]
    return scores, missing, extra


# ─── Разбор ответа модели (терпит массив, обрезку, ``` ``` обрамление) ────

_FENCE_RE = None
_ID_KEYS = ('id', 'problem_id', 'задача')
_VALUE_KEYS = ('score', 'verdict', 'label', 'value', 'rating', 'балл', 'оценка')


def _strip_fence(text):
    import re
    global _FENCE_RE
    if _FENCE_RE is None:
        _FENCE_RE = re.compile(r'^\s*```(?:json)?\s*|\s*```\s*$')
    return _FENCE_RE.sub('', text.strip())


def _as_object(data):
    """Массив записей → объект {id: значение}. Модель регулярно отвечает
    списком вида [{"id": 12, "score": 2}, ...] вместо объекта — терять из-за
    формы обёртки целую пачку из 50 кандидатов нельзя."""
    if isinstance(data, dict):
        rows = data.get('rows')
        if isinstance(rows, list):
            return _as_object(rows)
        return data
    if not isinstance(data, list):
        raise ValueError('Ответ не объект и не массив: %r' % type(data))
    out = {}
    for item in data:
        if not isinstance(item, dict):
            raise ValueError('Элемент массива не объект: %r' % (item,))
        key = next((item[k] for k in _ID_KEYS if k in item), None)
        value = next((item[k] for k in _VALUE_KEYS if k in item), None)
        if key is None or value is None:
            raise ValueError('В элементе нет пары «id — значение»: %r' % (item,))
        out[str(key)] = value
    return out


def _repair_truncated(text):
    """Обрезанный JSON → самый длинный разбираемый префикс."""
    if not text or text[0] not in '{[':
        raise ValueError('Не похоже на JSON: %r' % text[:60])
    closing = '}' if text[0] == '{' else ']'
    depth, in_string, escaped, cuts = 0, False, False, []
    for i, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if ch == '\\':
            escaped = True
        elif ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch in '{[':
                depth += 1
            elif ch in '}]':
                depth -= 1
            elif ch == ',' and depth == 1:
                cuts.append(i)
    for cut in reversed(cuts):
        try:
            return json.loads(text[:cut] + closing)
        except ValueError:
            continue
    raise ValueError('JSON не восстановить: %r' % text[:60])


def parse_json_object(text):
    """Ответ модели → словарь. Терпит массив, обрезку и ``` ``` обрамление.

    Неудача — исключение, а не пустой словарь: пустой читался бы как
    «модель всё сочла негодным», а это другое утверждение.
    """
    if not text or not text.strip():
        raise ValueError('Пустой ответ модели')
    body = _strip_fence(text)
    try:
        return _as_object(json.loads(body))
    except ValueError:
        return _as_object(_repair_truncated(body))


# ─── Дедуп пула по группам копий ──────────────────────────────────────────

def collapse_dedup(ids, groups):
    """Оставить по одному представителю дедуп-группы (`Problem.dup_group`).

    `groups`: {id: (группа, фаворит ли)}. Представитель — фаворит
    (`dup_is_best=True`), а если фаворит в пул не попал, то первый по
    порядку исходного списка, то есть лучший по рангу.
    """
    best = {}
    for pid in ids:
        group = groups.get(pid, (None, False))[0]
        if group is None:
            continue
        is_best = groups.get(pid, (None, False))[1]
        current = best.get(group)
        if current is None or (is_best and not groups[current][1]):
            best[group] = pid

    kept, dropped = [], []
    for pid in ids:
        group = groups.get(pid, (None, False))[0]
        if group is None or best[group] == pid:
            kept.append(pid)
        else:
            dropped.append({'id': pid, 'group': group, 'kept': best[group]})
    return kept, dropped


# ─── Флаг и доступ ─────────────────────────────────────────────────────────

def is_enabled():
    from django.conf import settings
    return getattr(settings, 'SMART_SEARCH_RERANK', False)


def is_available(user):
    """Работает ли сортировщик для этого посетителя.

    ⚠️ ОГРАНИЧЕНИЯ «ТОЛЬКО СОТРУДНИКАМ» БОЛЬШЕ НЕТ (13.09.2026). Оно
    стояло, пока функция не была обкатана: `is_staff` служил кнопкой
    «показать одному себе» в отсутствие второй кнопки. Теперь вторая
    кнопка есть — `SMART_SEARCH_RERANK`, общий выключатель, и он же
    остаётся единственным. Два выключателя подряд означали бы, что
    включённый флаг всё равно ничего не меняет для тех, ради кого
    функцию и делали: каталогом пользуются ученики, а поиском — и гости,
    не входя вовсе.

    `user` в подписи оставлен: вызывающая сторона его передаёт, а
    различать посетителей эта функция ещё может понадобиться (например,
    если появится платный тариф). Сегодня она их не различает.
    """
    return is_enabled()


# ─── Корпус для карточек и bm25-индекс: синглтон в памяти процесса ────────
#
# Тот же приём, что у `catalog/semantic.py` (версия в общем кэше, локальная
# копия перестраивается при расхождении) — см. докстринг `semantic.get_index`.

_corpus_cache = None            # (bm25.Index, {id: row})
_corpus_cache_version = None
_CORPUS_VERSION_KEY = 'smart_search_rerank:corpus_version'
_NO_CACHE = object()


def _build_corpus():
    from . import filters, lexical_bm25 as bm25
    from problems.models import Problem, ProblemPart

    ids = list(filters.base_queryset('catalog').values_list('id', flat=True))
    id_set = set(ids)

    parts_by_id = {}
    for pid, statement in (ProblemPart.objects
                            .filter(problem_id__in=id_set)
                            .order_by('problem_id', 'order')
                            .values_list('problem_id', 'statement')
                            .iterator(chunk_size=5000)):
        if statement:
            parts_by_id.setdefault(pid, []).append(statement)

    rows = {}
    qs = (Problem.objects.filter(id__in=id_set)
          .prefetch_related('topics', 'tags', 'econ_concepts')
          .only('id', 'title', 'title_candidate', 'statement', 'find', 'given',
                'problem_type', 'difficulty', 'dup_group', 'dup_is_best'))
    for p in qs.iterator(chunk_size=500):
        rows[p.id] = {
            'id': p.id,
            'title': p.title_candidate or p.title or '',
            'statement': p.statement or '',
            'parts': parts_by_id.get(p.id, []),
            'find': p.find or '',
            'given': p.given or '',
            'problem_type': p.problem_type or '',
            'difficulty': p.difficulty,
            'topics': [t.name for t in p.topics.all() if t.is_canonical],
            'tags': [t.name for t in p.tags.all() if t.kind == 'canonical'],
            'concepts': [c.canonical for c in p.econ_concepts.all()],
            'dup_group': p.dup_group or None,
            'dup_is_best': bool(p.dup_is_best),
        }

    index = bm25.build_index(list(rows.keys()),
                             [bm25.index_text(rows[pid]) for pid in rows])
    return index, rows


def _shared_corpus_version():
    version = cache.get(_CORPUS_VERSION_KEY)
    if version is not None:
        return version
    cache.add(_CORPUS_VERSION_KEY, uuid.uuid4().hex, None)
    version = cache.get(_CORPUS_VERSION_KEY)
    return version if version is not None else _NO_CACHE


def get_corpus():
    """(bm25.Index, {id: row}) — строится лениво при первом обращении."""
    global _corpus_cache, _corpus_cache_version
    version = _shared_corpus_version()
    if version is _NO_CACHE:
        if _corpus_cache is None:
            _corpus_cache = _build_corpus()
        return _corpus_cache
    if _corpus_cache is None or _corpus_cache_version != version:
        _corpus_cache = _build_corpus()
        _corpus_cache_version = version
    return _corpus_cache


def invalidate_corpus():
    """Сбросить кэш корпуса/bm25-индекса (например, после переимпорта)."""
    global _corpus_cache, _corpus_cache_version
    _corpus_cache = None
    _corpus_cache_version = None
    cache.set(_CORPUS_VERSION_KEY, uuid.uuid4().hex, None)


# ─── Сборка пула: dense топ-N + bm25 топ-N, объединение, дедуп ────────────

def _dense_leg(query, depth):
    from . import semantic
    if not semantic.is_enabled():
        return []
    try:
        hits = semantic.search(query_text=query, content_kind='all', limit=depth)
    except Exception:                                       # noqa: BLE001
        logger.warning('умный поиск: плотная нога пула недоступна',
                       exc_info=True)
        return []
    return [hit['problem'].pk for hit in hits]


def _bm25_leg(query, depth, index):
    from . import lexical_bm25 as bm25
    hits = bm25.search(index, query, top_k=depth)
    return [pid for pid, _score in hits]


def build_pool(query):
    """Пул кандидатов: dense топ-N (БЕЗ порога близости) + bm25 топ-N,
    объединение по порядку появления, один представитель на дедуп-группу.

    Возвращает `(id пула, размеры ног, {id: row корпуса})`. Пустой пул —
    легитимный результат (запрос ничего не нашёл ни одной ногой), не
    исключение.
    """
    from django.conf import settings

    legs = settings.SMART_SEARCH_RERANK_LEGS
    depth = settings.SMART_SEARCH_RERANK_LEG_DEPTH
    cap = settings.SMART_SEARCH_RERANK_POOL_CAP

    index, rows = get_corpus()

    ordered, seen, leg_sizes = [], set(), {}
    if 'dense' in legs:
        ids = _dense_leg(query, depth)
        leg_sizes['dense'] = len(ids)
        for pid in ids:
            if pid not in seen:
                seen.add(pid)
                ordered.append(pid)
    if 'bm25' in legs:
        ids = _bm25_leg(query, depth, index)
        leg_sizes['bm25'] = len(ids)
        for pid in ids:
            if pid not in seen:
                seen.add(pid)
                ordered.append(pid)

    if not ordered:
        return [], leg_sizes, rows

    groups = {pid: (rows[pid]['dup_group'], rows[pid]['dup_is_best'])
              for pid in ordered if pid in rows}
    deduped, _dropped = collapse_dedup(ordered, groups)
    return deduped[:cap], leg_sizes, rows


# ─── Вызов модели: пачки параллельно, слияние по баллу ────────────────────

# ⚠️ СВОЕЙ ТАБЛИЦЫ ЦЕН ЗДЕСЬ БОЛЬШЕ НЕТ (13.09.2026). Цена GLM переехала в
# `settings.AI_PRICES` — туда, где её считает `core._cost` для всех
# остальных функций сайта. Две таблицы цен разошлись бы так же тихо, как
# разошлись два словаря `problem_type`.


#: Имя работы в журнале расхода (`AiUsageLog.kind`) и ключ денежного
#: потолка (`AI_DAILY_COST_CAPS`). В `prompts.PROFILES` его НЕТ и быть не
#: должно: это не профиль генерации, системный блок у него свой
#: (`INSTRUCTION`), и менять его без повторного офлайн-замера запрещено.
USAGE_KIND = 'search_rerank'

PROVIDER_NAME = 'glm'


def _get_provider():
    """Единственное место, где модуль знает имя поставщика — подмена в
    тестах идёт через monkeypatch этой функции, без реального ключа.

    Поставщик разбирается ЗДЕСЬ и готовым объектом уходит в `core.run`:
    так шов подмены остаётся один, и тест, подменивший его, проверяет тот
    же путь, которым идёт боевой код.
    """
    from problems.ai.providers import get_provider
    return get_provider(PROVIDER_NAME)


def _score_pool(query, pool_ids, rows, timeout):
    """Пачки по `BATCH` кандидатов, ПАРАЛЛЕЛЬНО (потоки), слияние по баллу.

    Бросает исключение при любой поломке (нет ключа, таймаут, нечитаемый
    ответ) — фолбэк решает вызывающая сторона (`_run`), здесь причина не
    глушится.

    Возвращает `(ranked, usage, scores)` — третий элемент, сырой словарь
    `{id: балл}` по всем ОЦЕНЁННЫМ кандидатам (без хвоста неоценённых из
    `ranked`), нужен только `manage.py rerank_trace` для отладочной печати;
    `_run` его игнорирует.
    """
    from django.conf import settings

    from problems.ai import core

    provider = _get_provider()
    if not provider.is_available():
        raise RuntimeError(provider.unavailable_reason() or
                           'поставщик GLM недоступен')

    # Суточный денежный потолок спрашивается ОДИН РАЗ и здесь, в потоке
    # запроса: пачки уходят в рабочие потоки, и обращаться к базе оттуда
    # нельзя (см. `log=False` ниже). Исчерпан — исключение, и `_run` выше
    # тихо уводит выдачу на базовый порядок.
    if core.budget_exceeded(USAGE_KIND):
        raise RuntimeError(
            'на сегодня исчерпан суточный бюджет сортировщика поиска ($%s)'
            % core.daily_cost_cap(USAGE_KIND))

    batch_size = settings.SMART_SEARCH_RERANK_BATCH_SIZE
    model = settings.SMART_SEARCH_RERANK_MODEL
    batches = [pool_ids[i:i + batch_size]
               for i in range(0, len(pool_ids), batch_size)]

    def call_one(ids_chunk):
        cards = [rows[pid] for pid in ids_chunk if pid in rows]
        started = time.perf_counter()
        # ⚠️ ЧЕРЕЗ ОБЩУЮ ДВЕРЬ (см. докстринг модуля).
        # `cache_seconds=0` намеренно: одинаковый запрос уже ловит СВОЙ
        # кэш на час выше по стеку, а кэш `core` ключом по пачке
        # кандидатов сработал бы только при побайтовом совпадении пачки и
        # лишь дублировал бы первый.
        # `log=False` — тоже намеренно: пачки идут в ПОТОКАХ, а
        # соединение с базой в Django потоко-локальное и закрыть его в
        # рабочем потоке некому. Расход складывается и пишется ОДНОЙ
        # строкой ниже, в потоке запроса, — по строке на поисковый
        # запрос человека, а не на пачку из пятидесяти карточек.
        result = core.run(
            USAGE_KIND, user_text(query, cards), SCHEMA, user=None,
            max_tokens=3000, timeout=timeout, check_limit=False,
            cache_seconds=0, provider=provider, model=model,
            system=[INSTRUCTION], parse=parse_json_object, log=False,
            check_budget=False)
        elapsed = time.perf_counter() - started
        scores, _missing, _extra = parse_scores(result.data, ids_chunk)
        return scores, result.usage, elapsed

    chunks = []
    usages = []
    input_tokens = output_tokens = 0
    cost_usd = 0.0
    model_seconds = 0.0
    pool_started = time.perf_counter()
    executor = ThreadPoolExecutor(max_workers=max(len(batches), 1))
    try:
        futures = [executor.submit(call_one, chunk) for chunk in batches]
        try:
            for future in as_completed(futures, timeout=timeout):
                scores, usage, elapsed = future.result()
                chunks.append(scores)
                usages.append(usage)
                input_tokens += usage['input_tokens']
                output_tokens += usage['output_tokens']
                cost_usd += usage['cost_usd']
                model_seconds = max(model_seconds, elapsed)
        except _FuturesTimeoutError:
            raise TimeoutError(
                'не все пачки (%d) ответили за %.1f с' % (len(batches), timeout))
    finally:
        # wait=False: висящий поток не должен держать HTTP-запрос
        # пользователя дольше заявленного таймаута; поток доработает и
        # тихо отдаст результат в никуда.
        executor.shutdown(wait=False, cancel_futures=True)

    if len(chunks) != len(batches):
        raise TimeoutError('обработаны не все пачки (%d из %d)'
                           % (len(chunks), len(batches)))

    # ОДНА строка расхода на поисковый запрос — здесь, в потоке запроса.
    core.record_usage(USAGE_KIND, provider.name, model, usages,
                      time.perf_counter() - pool_started)

    ranked = merge(chunks, all_ids=pool_ids)
    scores = {}
    for chunk in chunks:
        for pid, score in chunk.items():
            scores[int(pid)] = clamp(score)
    usage = {'input_tokens': input_tokens, 'output_tokens': output_tokens,
             'batches': len(batches), 'model_seconds': round(model_seconds, 3),
             'cost_usd': cost_usd}
    return ranked, usage, scores


# ─── Кэш результата (час по нормализованному тексту запроса) ──────────────

_CACHE_TTL_SECONDS = 3600
_cache_lock = threading.Lock()
_cache = {}


def _normalize_query(query):
    return ' '.join((query or '').strip().lower().split())


class RerankResult:
    """Итог одного переранжирования — для лога и для `apply()`."""

    __slots__ = ('ids', 'status', 'reason', 'leg_sizes', 'batches',
                 'model_seconds', 'total_seconds', 'cost_usd', 'cache_hit')

    def __init__(self, ids, status, reason='', leg_sizes=None, batches=0,
                model_seconds=0.0, total_seconds=0.0, cost_usd=0.0,
                cache_hit=False):
        self.ids = ids
        self.status = status                # 'rerank' | 'fallback'
        self.reason = reason
        self.leg_sizes = leg_sizes or {}
        self.batches = batches
        self.model_seconds = model_seconds
        self.total_seconds = total_seconds
        self.cost_usd = cost_usd
        self.cache_hit = cache_hit


def _run(query):
    """Пул → модель → результат. Любая поломка — `status='fallback'`,
    исключение из этой функции наружу не уходит."""
    from django.conf import settings

    started = time.perf_counter()
    timeout = settings.SMART_SEARCH_RERANK_TIMEOUT
    leg_sizes = {}
    try:
        pool_ids, leg_sizes, rows = build_pool(query)
        if not pool_ids:
            return RerankResult(
                [], 'fallback', reason='пустой пул', leg_sizes=leg_sizes,
                total_seconds=time.perf_counter() - started)
        ranked, usage, _scores = _score_pool(query, pool_ids, rows, timeout)
        return RerankResult(
            ranked, 'rerank', leg_sizes=leg_sizes, batches=usage['batches'],
            model_seconds=usage['model_seconds'],
            total_seconds=time.perf_counter() - started,
            cost_usd=usage['cost_usd'])
    except Exception as exc:                                # noqa: BLE001
        logger.warning('умный поиск: переранжирование упало (%s) — '
                       'базовый порядок', exc, exc_info=True)
        return RerankResult(
            [], 'fallback', reason='%s: %s' % (type(exc).__name__, exc),
            leg_sizes=leg_sizes, total_seconds=time.perf_counter() - started)


def rerank(query):
    """Пул → модель → порядок пула, с кэшем на час по тексту запроса.

    Никогда не бросает исключение наружу. На фолбэке `.ids` пуст —
    решение, что делать дальше, принимает `apply()`.
    """
    key = _normalize_query(query)
    now = time.time()
    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None and cached['expires'] > now:
        source = cached['result']
        result = RerankResult(
            source.ids, source.status, reason=source.reason,
            leg_sizes=source.leg_sizes, batches=source.batches,
            model_seconds=source.model_seconds, total_seconds=0.0,
            cost_usd=0.0, cache_hit=True)
        _log(query, result)
        return result

    result = _run(query)
    with _cache_lock:
        _cache[key] = {'result': result, 'expires': now + _CACHE_TTL_SECONDS}
    _log(query, result)
    return result


def clear_cache():
    """Сбросить кэш результатов — для тестов."""
    with _cache_lock:
        _cache.clear()


def apply(user, query):
    """Точка входа для `catalog/views.py`.

    Возвращает `(порядок пула или None, статус для заголовка
    X-Smart-Search)`. `None` значит «ничего не менять» — вызывающая
    сторона идёт прежним путём один в один, поэтому фолбэк побайтово
    совпадает со старым поведением, а не просто похож на него.
    """
    if not is_available(user):
        return None, 'off'
    result = rerank(query)
    if result.status != 'rerank':
        return None, result.status
    return result.ids, result.status


# ─── Лог: консоль + reports/smart_search_log.jsonl ────────────────────────

_log_write_lock = threading.Lock()


def _log_path():
    from django.conf import settings
    return os.path.join(str(settings.BASE_DIR), 'reports',
                        'smart_search_log.jsonl')


def _log(query, result):
    outcome = 'rerank' if result.status == 'rerank' else (
        'fallback: %s' % (result.reason or 'причина не записана'))
    logger.info(
        'умный поиск: запрос=%r пул=%s пачек=%d модель=%.3fс всего=%.3fс '
        'стоимость=$%.4f итог=%s%s',
        query, result.leg_sizes, result.batches, result.model_seconds,
        result.total_seconds, result.cost_usd, outcome,
        ' (кэш)' if result.cache_hit else '')
    row = {
        'ts': datetime.now(timezone.utc).isoformat(),
        'query': query,
        'pool_by_leg': result.leg_sizes,
        'batches': result.batches,
        'model_seconds': result.model_seconds,
        'total_seconds': round(result.total_seconds, 3),
        'cost_usd': round(result.cost_usd, 6),
        'outcome': outcome,
        'cache_hit': result.cache_hit,
    }
    path = _log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _log_write_lock:
            with open(path, 'a', encoding='utf-8') as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    except OSError:
        logger.warning('умный поиск: не удалось записать %s', path,
                       exc_info=True)
