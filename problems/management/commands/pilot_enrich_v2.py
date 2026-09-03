# -*- coding: utf-8 -*-
"""Пилот обогащения v2: таксономия 1.1 + OpenAIProvider (Б2).

⚠️ ЭТО НЕ pilot_enrich.py (Батч 1). Та команда — 47 тегов вместо 344,
свободный текст темы вместо закрытого списка, и она пишет `cleaned_statement`
(правит текст условия). Эта команда НИЧЕГО в условии не трогает и НИ ОДНОГО
нового поля `Problem` не заводит — только пишет отчёт в файл.

⚠️ ДВЕ ФАЗЫ, ЖЁСТКО РАЗДЕЛЁННЫЕ. Без `--apply` не уходит НИ ОДНОГО
обращения к API: печатается выборка, смета и полное содержимое обоих
промптов — это стоп-гейт, владелец смотрит промпты глазами и даёт «да»
до первой траты. `--apply` без `--max-cost` — ошибка, а не «прогон без
лимита»: `--max-cost` считается по ФАКТИЧЕСКОМУ usage каждого ответа, а
не по смете-прикидке, посчитанной один раз в начале — прогон
останавливается, как только реальный расход достиг потолка, а не когда
кто-то заметит перерасход постфактум.

⚠️ ОБХОД `problems/ai/core.run()` — ОСОЗНАННОЕ ИСКЛЮЧЕНИЕ ИЗ «ОДНОЙ ДВЕРИ
НАРУЖУ» (problems/ai/CLAUDE.md), А НЕ ЗАБЫТОЕ ПРАВИЛО. `core.run()`
рассчитан на продуктовый профиль: одна модель и один уровень рассуждения
из настроек, кэш на 15 минут в НАШЕМ Redis, суточный лимит на пользователя.
Пилоту нужно противоположное — разные модели и уровни рассуждения В ОДНОМ
прогоне (ветки `--variants`), реальные `cached_tokens` от поставщика без
маскировки нашим собственным кэшем ответов, и работа без Django `user`
(это management-команда, не веб-запрос). Вызывается `providers.
OpenAIProvider.complete()` напрямую; уровень рассуждения на вызов
переключается через `django.test.override_settings(AI_REASONING_EFFORT=…)`
— это не хак теста, а штатный способ временно подменить настройку и
вернуть её обратно, не трогая ни `providers.py`, ни `core.py`.

Стратификация выборки — по существующим 23 каноническим темам
(`apply_topic_mapping.py`), а не по 29 темам новой таксономии: те 29 в базе
пока нигде не проставлены (это и есть первая цель прогона). Английский
язык — эвристика по доле кириллицы (`problems.enrich.text.is_english_text`,
на базе нет отдельного поля языка). «Заведомо сломанные» —
`Problem.human_review == DEFECT` (`human_review_mark`).

Запуск:
    venv313\\Scripts\\python.exe manage.py pilot_enrich_v2
    venv313\\Scripts\\python.exe manage.py pilot_enrich_v2 --apply --max-cost 5.0
"""
import concurrent.futures
import hashlib
import json
import random
import re
import shutil
import sqlite3
import tempfile
import threading
import time
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.test import override_settings

from problems.ai import providers
from problems.enrich import prompts_v2, taxonomy, text as enrich_text, title_rules
from problems.enrich.text import (has_graph_in_statement,
                                  has_table_in_statement, images_for_call1,
                                  is_english_text, problem_full_text,
                                  with_figure_note, with_tikz_sources,
                                  TIKZ_MAX_TOKENS)
from problems.enrich.shortlist import shortlist_for
from problems.models import Problem

SEED_DEFAULT = 20260831
LIMIT_DEFAULT = 300

# ---------------------------------------------------------------------------
# Стратификация — 23 канонические темы из apply_topic_mapping.py, СВОДИМ по
# группам, потому что закрытых 5 групп задания шире одной темы каждая.
# ---------------------------------------------------------------------------

MICRO_TOPICS = [
    'Альтернативные издержки и КПВ', 'Спрос и предложение', 'Эластичность',
    'Теория потребителя и полезность',
    'Теория фирмы: производство и издержки', 'Совершенная конкуренция',
    'Монополия и ценовая дискриминация', 'Олигополия и теория игр',
    'Вмешательство государства',
]
MACRO_TOPICS = [
    'ВВП и национальные счета',
    'Совокупный спрос и совокупное предложение',
    'Инфляция и безработица', 'Фискальная политика', 'Монетарная политика',
    'Экономический рост и циклы',
]
FINANCE_TOPICS = ['Финансы и финансовые инструменты']
INTERNATIONAL_TOPICS = ['Международная торговля']
INEQUALITY_LABOR_TOPICS = ['Рынок труда', 'Неравенство доходов']

# (ключ страты, доля по умолчанию из 300, названия тем | None для особых страт)
# Фаза 6.1 (2026-09-01): добавлены визуальные страты (фигура/маркер, таблица)
# — раньше задачи с картинками и таблицами попадали в выборку случайно, и
# инвариант «не потеряли визуальное» было нечем проверить целенаправленно.
# Доли остальных страт УМЕНЬШЕНЫ пропорционально, чтобы сумма осталась 300.
STRATA = [
    ('микро', 80, MICRO_TOPICS),
    ('макро', 50, MACRO_TOPICS),
    ('финансы', 30, FINANCE_TOPICS),
    ('международка', 25, INTERNATIONAL_TOPICS),
    ('неравенство и труд', 25, INEQUALITY_LABOR_TOPICS),
    ('англоязычные', 20, None),  # эвристика is_english_text
    ('заведомо сломанные', 20, 'DEFECT'),  # human_review == DEFECT
    ('с фигурой/маркером', 25, 'FIGURE'),  # ProblemFigure или [[FIGURE:/tikz
    ('с таблицей', 25, 'TABLE'),  # tabular/array/table/markdown-таблица
]
STRATA_TOTAL = sum(target for _, target, _ in STRATA)  # 300 — база --limit


# ---------------------------------------------------------------------------
# Ветки сравнения. `effort=None` — параметр `reasoning` не передаётся вовсе
# (у Luna нет смысла платить за рассуждение — базовая ветка её не просит).
# ---------------------------------------------------------------------------

TERRA = 'gpt-5.6-terra'
LUNA = 'gpt-5.6-luna'

VARIANTS = {
    'base': {
        'label': 'terra-none + Luna (базовая рекомендуемая)',
        'call1_model': TERRA, 'call1_effort': 'none',
        'call2_model': LUNA, 'call2_effort': None,
        'concepts': True,
    },
    'terra-low': {
        'label': 'terra-low + Luna (стоит ли рассуждение своих денег)',
        'call1_model': TERRA, 'call1_effort': 'low',
        'call2_model': LUNA, 'call2_effort': None,
        'concepts': True,
    },
    'terra-gen': {
        'label': 'terra-none + Terra (нужна ли Terra на генеративной части)',
        'call1_model': TERRA, 'call1_effort': 'none',
        'call2_model': TERRA, 'call2_effort': 'none',
        'concepts': True,
    },
    'luna-luna': {
        'label': 'luna-luna (нижняя планка)',
        'call1_model': LUNA, 'call1_effort': None,
        'call2_model': LUNA, 'call2_effort': None,
        'concepts': True,
    },
    'no-concepts': {
        'label': 'no-concepts (нужны ли econ_concepts после 344 тегов)',
        'call1_model': TERRA, 'call1_effort': 'none',
        'call2_model': LUNA, 'call2_effort': None,
        'concepts': False,
    },
}
ALL_VARIANTS = tuple(VARIANTS)

# Оценка вых. токенов на дозвон СМЕТЫ — ДО реального прогона. ⚠️ Это ровно
# прикидка (см. `problems/ai/core.py::_cost`): сверяется с фактическим
# usage на пилоте, не более того.
ESTIMATED_OUTPUT_TOKENS_CALL1 = {True: 260, False: 200}
ESTIMATED_OUTPUT_TOKENS_CALL2 = {True: 480, False: 300}  # True = есть решение
REASONING_OUTPUT_TOKENS_ESTIMATE = 300  # добавка, если effort не 'none'/None
CHARS_PER_TOKEN_ESTIMATE = 2.3


# ---------------------------------------------------------------------------
# Выборка
# ---------------------------------------------------------------------------

def scale_strata(limit):
    """Страты по умолчанию суммируются в 300 — это и есть `--limit` по
    умолчанию. Для другого `--limit` доли масштабируются пропорционально,
    остаток (после округления) уходит в САМУЮ БОЛЬШУЮ страту, чтобы сумма
    точно совпала с `limit`.

    ⚠️ Это предположение, не часть исходного задания: там расписан только
    состав выборки на 300. Явно зафиксировано здесь и в отчёте, а не
    выбрано молча.

    ГАРАНТИЯ: при `limit >= len(STRATA)` ни одна страта не обнуляется —
    каждая получает минимум 1 (Фаза 6.1, 2026-09-01). До этой правки
    `round()` мог округлить малую страту в 0, а при отрицательном остатке
    вычитание из «самой большой» страты могло увести и её в 0 (например
    `limit=9` реально обнулял «микро» старым кодом). При `limit < len(STRATA)`
    гарантия буквально невыполнима (задач меньше, чем страт) — берём по 1
    для `limit` страт с наибольшей исходной долей, остальные — 0, и это
    явный частный случай, а не побочный эффект округления.
    """
    if limit == STRATA_TOTAL:
        return [(key, target, spec) for key, target, spec in STRATA]

    n = len(STRATA)
    if limit <= 0:
        return [(key, 0, spec) for key, _, spec in STRATA]
    if limit < n:
        order = sorted(range(n), key=lambda i: -STRATA[i][1])
        chosen = set(order[:limit])
        return [(STRATA[i][0], 1 if i in chosen else 0, STRATA[i][2])
               for i in range(n)]

    scaled = []
    for key, target, spec in STRATA:
        count = max(1, round(target * limit / STRATA_TOTAL))
        scaled.append([key, count, spec])
    diff = limit - sum(s[1] for s in scaled)
    while diff > 0:
        biggest = max(range(len(scaled)), key=lambda i: scaled[i][1])
        scaled[biggest][1] += diff
        diff = 0
    while diff < 0:
        shrinkable = [i for i in range(len(scaled)) if scaled[i][1] > 1]
        biggest = max(shrinkable, key=lambda i: scaled[i][1])
        scaled[biggest][1] -= 1
        diff += 1
    return [tuple(s) for s in scaled]


def build_sample(limit, seed):
    """Стратифицированная выборка id задач, детерминированная сидом.

    Возвращает `(sample_ids, report)`: `sample_ids` — список id в порядке
    страт (микро → … → сломанные), `report` — список строк «страта: нужно
    N, найдено M, взято K» для отчёта владельцу.
    """
    rng = random.Random(seed)
    used = set()
    sample_ids = []
    report = []

    for key, target, spec in scale_strata(limit):
        if spec == 'DEFECT':
            candidates = list(
                Problem.objects.filter(human_review=Problem.HumanReview.DEFECT)
                .exclude(id__in=used).order_by('id')
                .values_list('id', flat=True))
        elif spec is None:  # англоязычные — эвристика по тексту
            candidates = [
                pid for pid, text in
                Problem.objects.exclude(id__in=used).order_by('id')
                .values_list('id', 'statement').iterator(chunk_size=500)
                if is_english_text(text)
            ]
        elif spec == 'FIGURE':
            # ProblemFigure ИЛИ маркер `[[FIGURE:`/сырой tikzpicture — в
            # statement ИЛИ в тексте подпункта (см. Фаза 1, docs/TAXONOMY.md
            # §7 «график в условии»).
            figure_regex = r'\[\[FIGURE:|\\begin\{tikzpicture\}'
            candidates = list(
                Problem.objects.filter(
                    Q(figures__isnull=False)
                    | Q(statement__iregex=figure_regex)
                    | Q(parts__statement__iregex=figure_regex))
                .exclude(id__in=used).distinct().order_by('id')
                .values_list('id', flat=True))
        elif spec == 'TABLE':
            # tabular/array/table/HTML — SQL-стороной (быстро); markdown-
            # таблица (строка с ≥2 символами `|`) не выражается regex-ом с
            # подсчётом одинаковых символов в SQLite — добираем в Python
            # ТОЛЬКО по statement (как и страта «англоязычные» выше), без
            # обхода всех parts — компромисс ради скорости на 41 307 задач.
            table_regex = r'\\begin\{tabular\}|\\begin\{array\}|\\begin\{table\}|<table'
            sql_ids = set(
                Problem.objects.filter(
                    Q(statement__iregex=table_regex)
                    | Q(parts__statement__iregex=table_regex))
                .exclude(id__in=used).distinct()
                .values_list('id', flat=True))
            md_ids = {
                pid for pid, text in
                Problem.objects.exclude(id__in=used).order_by('id')
                .values_list('id', 'statement').iterator(chunk_size=500)
                if has_table_in_statement(text)
            }
            candidates = sorted(sql_ids | md_ids)
        else:
            candidates = list(
                Problem.objects.filter(topics__name__in=spec)
                .exclude(id__in=used).distinct().order_by('id')
                .values_list('id', flat=True))

        take = min(target, len(candidates))
        chosen = sorted(rng.sample(candidates, take)) if take else []
        used.update(chosen)
        sample_ids.extend(chosen)
        report.append('%s: нужно %d, доступно %d, взято %d' % (
            key, target, len(candidates), take))

    return sample_ids, report


# ---------------------------------------------------------------------------
# Проверка ограничений массивов — ⚠️ ТОЛЬКО ПРОМПТОМ И ЗДЕСЬ, НЕ СХЕМОЙ.
# structured output OpenAI не принимает maxItems (см. prompts_v2.py).
# ---------------------------------------------------------------------------

#: §12 правило 3 API_RUN_MASTER: «Ни одной цифры в given, find,
#: econ_concepts, plot, поисковых запросах и заголовке» — код, не промпт.
_DIGIT_RE = re.compile(r'\d')

#: Фаза B.2 (боевой прогон 02.09.2026): поле уже называется given/find —
#: приставка «Дано:»/«Найти:» это мусор, который иначе уходит в эмбеддинг.
#: Промпт больше не просит её (см. prompts_v2.CALL1_FIELDS), но старая
#: привычка модели срезается кодом на всякий случай — БЕЗ повтора, это не
#: нарушение схемы, а мелкая уборка после парсинга.
_GIVEN_PREFIX_RE = re.compile(r'^\s*дано\s*[:：]\s*', re.IGNORECASE)
_FIND_PREFIX_RE = re.compile(r'^\s*найти\s*[:：]\s*', re.IGNORECASE)

#: Фаза 1.3 (решение владельца 02.09.2026, четвёртая пересъёмка): правило
#: §12.3 «без цифр» для `given`/`find` остаётся ЖЁСТКИМ — это структурный
#: отпечаток задачи, ради него всё и затевалось. Меняется только СООБЩЕНИЕ
#: повтора: раньше модель получала общий запрет («given содержит цифру») и
#: не понимала, за что её ругают. Теперь сообщение цитирует нарушивший
#: кусок и показывает, чем его заменить.
_CLAUSE_BOUNDARY_RE = re.compile(r'[;,.!?\n]')

DIGIT_FIELD_VIOLATION = (
    'В поле %s встречается «%s». Числовые значения запрещены.\n'
    'Опиши структуру словами: «линейная функция спроса».\n'
    'Перепиши только given и find, остальные поля не меняй.'
)


def digit_fragment(text, max_len=60):
    """Кусок текста вокруг ПЕРВОЙ цифры — то, что цитируется модели в
    сообщении повтора. Границы куска — знаки конца предложения/запятая/
    перевод строки: «Дана линейная функция спроса P = 100 − 2Q, найдите
    равновесие» даёт «Дана линейная функция спроса P = 100 − 2Q», а не всю
    строку и не голую цифру, по которой не понять, что переписывать.

    Кусок длиннее `max_len` обрезается ОКНОМ ВОКРУГ цифры, а не с начала:
    цифра обязана остаться видна, иначе цитата бессмысленна."""
    match = _DIGIT_RE.search(text or '')
    if not match:
        return ''
    pos = match.start()
    left = 0
    for boundary in _CLAUSE_BOUNDARY_RE.finditer(text, 0, pos):
        left = boundary.end()
    right_match = _CLAUSE_BOUNDARY_RE.search(text, pos)
    right = right_match.start() if right_match else len(text)
    fragment = text[left:right].strip()
    if len(fragment) > max_len:
        start = max(left, pos - max_len // 2)
        fragment = text[start:start + max_len].strip()
    return fragment


def strip_given_find_prefixes(data):
    """Срезает «Дано:»/«Найти:» из `data['given']`/`data['find']` на
    месте. `data` может быть `None`/не-словарём (после неудачного разбора
    JSON) — тогда просто ничего не делает."""
    if not isinstance(data, dict):
        return data
    if data.get('given'):
        data['given'] = _GIVEN_PREFIX_RE.sub('', data['given'])
    if data.get('find'):
        data['find'] = _FIND_PREFIX_RE.sub('', data['find'])
    return data


def validate_call1(data, with_concepts=True, shortlist_terms=None):
    """ЖЁСТКИЕ нарушения — те, что портят банк, если пропустить (Фаза 1
    задания сессии 02.09.2026, вторая пересъёмка): триггерят повтор внутри
    `call_with_retry`. Мягкие — см. `soft_violations_call1` ниже, отдельно
    от этой функции и НЕ влияют на `ok`.

    `shortlist_terms`, если задан (боевой путь GLM — список для КОНКРЕТНОЙ
    задачи), проверяет «понятие вне шорт-листа» — иначе (тесты с
    плейсхолдерами вида `econ_concepts: ['a','b','c']`) эта проверка
    пропускается, как и раньше делал вызывающий код с enum таксономии."""
    if not isinstance(data, dict):
        return (False, ['ответ вызова 1 — не JSON-объект (%s)' % type(data).__name__])
    violations = []
    # Границы расширены 03.09.2026 решением владельца перед перегоном
    # корпуса: многотемье в олимпиадной экономике — норма, а не исключение,
    # поэтому дополнительных тем стало 0–4 вместо 0–2, а теги теперь
    # выписываются по КАЖДОЙ названной теме, а не только по главной, — 1–8
    # вместо 1–5. Верхняя граница остаётся ЖЁСТКОЙ (повтор): список тем и
    # тегов закрытый, и выход за границу означает, что модель перестала
    # следовать таксономии, а не что она нашла лишний оттенок смысла.
    if len(data.get('topics_secondary') or []) > 4:
        violations.append('topics_secondary длиннее 4 (%d)'
                          % len(data.get('topics_secondary') or []))
    tags = data.get('tags') or []
    if not 1 <= len(tags) <= 8:
        violations.append('tags вне диапазона 1..8 (%d)' % len(tags))
    if with_concepts:
        concepts = data.get('econ_concepts') or []
        # Верхняя граница остаётся жёсткой — только нижняя (Фаза 1, 02.09)
        # ушла в мягкие: починка шорт-листа сделала его честнее и уже, и на
        # части задач физически не набрать три понятия — не наша ошибка.
        if len(concepts) > 6:
            violations.append('econ_concepts длиннее 6 (%d)' % len(concepts))
        if len(data.get('concepts_offlist') or []) > 2:
            violations.append('concepts_offlist длиннее 2')
        # ⚠️ Пустой список — как отсутствие: `shortlist_for()` в бою
        # никогда не отдаёт пустой список (добор ядром до MIN_SHORTLIST),
        # `[]` встречается только в тестах как «не о том тесте» плейсхолдер
        # — не должен читаться как «ничего не разрешено».
        shortlist_set = set(shortlist_terms) if shortlist_terms else None
        for i, concept in enumerate(concepts):
            # ⚠️ Не-строка сюда доходит (модель без строгой схемы может
            # вернуть число) и раньше роняла проверку целиком —
            # `_DIGIT_RE.search(42)` это TypeError, а не нарушение. Тип
            # ловит `check_against_schema` жёстко и по своей части, здесь
            # же проверяются только текстовые правила.
            if not isinstance(concept, str):
                continue
            if _DIGIT_RE.search(concept):
                violations.append('econ_concepts[%d] содержит цифру' % i)
            # §12 правило 5 / §4.6 API_RUN_MASTER: «P», «π» и подобные
            # однобуквенные обозначения неоднозначны без контекста.
            if len(concept) <= 1:
                violations.append(
                    'econ_concepts[%d] однобуквенное обозначение' % i)
            if shortlist_set is not None and concept not in shortlist_set:
                violations.append('econ_concepts[%d] вне шорт-листа задачи' % i)
    if len(data.get('features_1') or []) > 6:
        violations.append('features_1 длиннее 6')
    for field in ('given', 'find'):
        value = data.get(field) or ''
        if _DIGIT_RE.search(value):
            violations.append(
                DIGIT_FIELD_VIOLATION % (field, digit_fragment(value)))
    return (not violations, violations)


def soft_violations_call1(data, with_concepts=True):
    """МЯГКИЕ нарушения вызова 1 (Фаза 1, 02.09.2026, вторая пересъёмка) —
    не портят банк, повтор не делают. Пишутся в журнал (`soft_violations`
    в `run_parsed.jsonl` — см. `glm_enrich_run.parsed_row`), не влияют на
    `ok`/автостоп."""
    if not isinstance(data, dict):
        return []
    violations = []
    if with_concepts:
        concepts = data.get('econ_concepts') or []
        if not (len(concepts) == 0 and data.get('task_nature') == 'не_задача'):
            if len(concepts) < 3:
                violations.append('econ_concepts меньше 3 (%d)' % len(concepts))
    if not (data.get('topics_secondary') or []):
        violations.append('topics_secondary пусто')
    return violations


# ---------------------------------------------------------------------------
# Инварианты «не потеряли визуальное» (Фаза 6.2) — пилот НЕ пишет в
# statement/answer/solution/ProblemPart.statement (P0), так что расхождение
# здесь сигналит о нарушении этого правила, а не об ожидаемом результате.
# ---------------------------------------------------------------------------

_FIGURE_MARKER_RE = re.compile(r'\[\[FIGURE:')
_TABLE_ENV_RE = re.compile(
    r'\\begin\{tabular\}|\\begin\{array\}|\\begin\{table\}')


def visual_snapshot(sample_ids):
    """Снимок «сколько визуального» и хеш текстовых полей — берётся ДО и
    ПОСЛЕ прогона по одним и тем же id, сравнивается `diff_visual_snapshots`.
    """
    problems = list(Problem.objects.filter(id__in=sample_ids)
                    .prefetch_related('parts', 'figures'))
    markers = 0
    table_envs = 0
    figure_rows = 0
    text_hash = {}
    for p in problems:
        parts = list(p.parts.all())
        markers += len(_FIGURE_MARKER_RE.findall(p.statement or ''))
        table_envs += len(_TABLE_ENV_RE.findall(p.statement or ''))
        for part in parts:
            markers += len(_FIGURE_MARKER_RE.findall(part.statement or ''))
            table_envs += len(_TABLE_ENV_RE.findall(part.statement or ''))
        figure_rows += len(list(p.figures.all()))
        text_hash[p.id] = (
            p.statement, p.answer, p.solution,
            tuple(part.statement for part in parts))
    return {'figure_markers': markers, 'table_envs': table_envs,
            'problem_figure_rows': figure_rows, 'text_hash': text_hash}


def diff_visual_snapshots(before, after):
    """Строки отчёта — числа до/после и список id, где текст ИЗМЕНИЛСЯ
    (свип-детектор). Ожидание по всем строкам — 0 расхождений."""
    lines = []
    for key, label in (('figure_markers', 'маркеров [[FIGURE:'),
                       ('table_envs', 'table-окружений (tabular/array/table)'),
                       ('problem_figure_rows', 'строк ProblemFigure')):
        b, a = before[key], after[key]
        lines.append('%s до/после: %d / %d — %s' % (
            label, b, a, 'совпало' if b == a else 'РАСХОЖДЕНИЕ'))
    changed = sorted(
        pid for pid, snap in before['text_hash'].items()
        if snap != after['text_hash'].get(pid))
    lines.append(
        'свип-детектор statement/answer/solution/ProblemPart.statement: '
        'расхождений %d%s' % (
            len(changed), (' — id: %s' % changed) if changed else ''))
    return lines


def is_visual_problem(problem):
    """Задача из визуальных страт — ProblemFigure, маркер/tikz или таблица."""
    has_pf = problem.figures.exists()
    text = problem_full_text(problem.statement, problem.parts.all())
    return (has_graph_in_statement(text, has_problem_figure=has_pf)
           or has_table_in_statement(text))


def visual_flag_lists(rows):
    """Два списка для глаз владельца (Фаза 6.2):
    - задачи с ProblemFigure, помеченные «содержание в утраченном
      визуальном элементе» — ожидание: список пуст;
    - задачи из визуальных страт, помеченные «это не задача» вызовом 1.
    """
    ids = [row['problem_id'] for row in rows]
    problems_by_id = {
        p.id: p for p in
        Problem.objects.filter(id__in=ids).prefetch_related('parts', 'figures')
    }
    lost_visual = []
    not_task_visual = []
    for row in rows:
        problem = problems_by_id.get(row['problem_id'])
        if problem is None:
            continue
        call1 = row.get('call1') or {}
        call2 = row.get('call2') or {}
        if (problem.figures.exists()
                and 'содержание в утраченном визуальном элементе' in
                (call2.get('text_quality_note') or '')):
            lost_visual.append(problem.id)
        if is_visual_problem(problem) and call1.get('task_nature') == 'не_задача':
            not_task_visual.append(problem.id)
    return lost_visual, not_task_visual


def graphical_solution_breakdown(rows, problems_by_id):
    """0-бис.3: разбивка особенности «Графическое решение» после
    объединения по ИЛИ (`enrich_text.merge_graphical_solution`) —
    `{'model': N, 'code': N, 'both': N, 'none': N, 'total_graphical': N}`.
    `total_graphical` — итог для инварианта (model+code+both), печатается
    рядом с разбивкой, а не вместо неё (задание требует именно три числа)."""
    counts = {'model': 0, 'code': 0, 'both': 0, 'none': 0}
    for row in rows:
        problem = problems_by_id.get(row['problem_id'])
        if problem is None:
            continue
        features_1 = (row.get('call1') or {}).get('features_1')
        _, source = enrich_text.merge_graphical_solution(features_1, problem)
        counts[source] += 1
    counts['total_graphical'] = counts['model'] + counts['code'] + counts['both']
    return counts


def task_nature_divergence(rows):
    """Инвариант Фазы 5: доля задач, где вызов 1 (`task_nature`) и вызов 2
    (`problem_type`) расходятся в оценке «это задача / это не задача».
    Ожидание на пилоте — единицы процентов; больше — сигнал, что одна из
    формулировок промпта плывёт. Возвращает `(расхождений, пар, доля_%)`.
    """
    divergent = 0
    total = 0
    for row in rows:
        call2_data = row.get('call2')
        if call2_data is None:
            continue
        call1_data = row.get('call1') or {}
        total += 1
        not_task_1 = call1_data.get('task_nature') == 'не_задача'
        not_task_2 = call2_data.get('problem_type') == 'не_задача'
        if not_task_1 != not_task_2:
            divergent += 1
    pct = (divergent / total * 100) if total else 0.0
    return divergent, total, pct


_TITLE_CANDIDATE_DIGIT_RE = re.compile(r'\d')
_TITLE_CANDIDATE_LATEX_RE = re.compile(r'[$\\]')


def validate_call2(data):
    """ЖЁСТКИЕ нарушения вызова 2 — см. докстринг `validate_call1`. Нижняя
    граница `search_queries` и длина/число слов `title_candidate` ушли в
    `soft_violations_call2` (Фаза 1, 02.09.2026, вторая пересъёмка):
    заголовки не пишутся в базу автоматически (свой стоп-гейт §5.8), а
    пять точных запросов лучше восьми с натяжкой."""
    if not isinstance(data, dict):
        return (False, ['ответ вызова 2 — не JSON-объект (%s)' % type(data).__name__])
    violations = []
    queries = data.get('search_queries') or []
    # Верхняя граница остаётся жёсткой — нижняя (было 5..8 целиком) ушла в
    # мягкие, см. `soft_violations_call2`.
    if len(queries) > 8:
        violations.append('search_queries длиннее 8 (%d)' % len(queries))
    for i, query in enumerate(queries):
        # Не-строка — нарушение ТИПА (его ловит `check_against_schema`), а
        # не «запрос с цифрой»; раньше `_DIGIT_RE.search(42)` роняло всю
        # проверку исключением.
        if isinstance(query, str) and _DIGIT_RE.search(query):
            violations.append('search_queries[%d] содержит цифру' % i)
    hints = data.get('hints')
    if hints is not None and not 3 <= len(hints) <= 5:
        violations.append('hints вне диапазона 3..5 (%d)' % len(hints))
    plot = data.get('plot')
    if plot and _DIGIT_RE.search(plot):
        violations.append('plot содержит цифру')

    # `title_candidate` (§5.8, Фаза 4.1/6.4) — границы не выражаются
    # схемой (maxLength не пробовали на этой schema, чтобы не рисковать
    # `strict` перед смок-тестом), проверяем в Python. Длина/число слов —
    # мягкие (см. `soft_violations_call2`); пустота/регистр/точка/цифра/
    # LaTeX остаются жёсткими.
    title = data.get('title_candidate') or ''
    if not title:
        violations.append('title_candidate пуст')
    else:
        if not title[:1].isupper():
            violations.append('title_candidate не с заглавной буквы')
        if title.endswith('.'):
            violations.append('title_candidate заканчивается точкой')
        if _TITLE_CANDIDATE_DIGIT_RE.search(title):
            violations.append('title_candidate содержит цифру')
        if _TITLE_CANDIDATE_LATEX_RE.search(title):
            violations.append('title_candidate содержит $ или \\')

    return (not violations, violations)


def drop_digit_search_queries(data):
    """Фаза 1.2 (решение владельца 02.09.2026, четвёртая пересъёмка):
    запрос с цифрой ВЫБРАСЫВАЕТСЯ из массива, а не роняет весь вызов.

    Причина структурная. Проверка «нет цифр» применялась ко ВСЕМУ массиву
    целиком, поэтому один плохой запрос из восьми убивал вызов, где семь
    были в порядке — восьмикратный усилитель отказов на ровном месте, и
    самая большая доля нарушений чек-поинта (71 случай из 142 задач).
    Само правило §12.3 не ослаблено: цифра в поисковом запросе по-прежнему
    недопустима, меняется только реакция — выбросить один запрос, а не
    платить за повторный вызов.

    Правит `data['search_queries']` НА МЕСТЕ, возвращает список
    выброшенных запросов ТЕКСТОМ (идёт в журнал полем `dropped_queries`).
    Не-строки не трогаются — их поймает проверка типа по схеме, это
    жёсткое нарушение, а не «запрос с цифрой».

    Осталось меньше 5 — это `soft_violations_call2` («search_queries
    меньше 5»), то есть мягкое нарушение без повтора; отдельной проверки
    здесь не нужно.
    """
    if not isinstance(data, dict):
        return []
    queries = data.get('search_queries')
    if not isinstance(queries, list):
        return []
    kept = []
    dropped = []
    for query in queries:
        if isinstance(query, str) and _DIGIT_RE.search(query):
            dropped.append(query)
        else:
            kept.append(query)
    if dropped:
        data['search_queries'] = kept
    return dropped


def make_query_sanitizer():
    """`(sanitize_fn, state)` для `call_with_retry`: `sanitize_fn(data)`
    выбрасывает запросы с цифрой ещё ДО проверки, `state['dropped']` —
    что выброшено из ПОСЛЕДНЕЙ попытки (повтор перезаписывает, а не
    копит: в журнал идёт то, что выброшено из финального ответа)."""
    state = {'dropped': []}

    def sanitize(data):
        state['dropped'] = drop_digit_search_queries(data)

    return sanitize, state


def soft_violations_call2(data):
    """МЯГКИЕ нарушения вызова 2 (Фаза 1, 02.09.2026, вторая пересъёмка) —
    см. докстринг `soft_violations_call1`."""
    if not isinstance(data, dict):
        return []
    violations = []
    queries = data.get('search_queries') or []
    if len(queries) < 5:
        violations.append('search_queries меньше 5 (%d)' % len(queries))
    title = data.get('title_candidate') or ''
    if title:
        if len(title) > 40:
            violations.append('title_candidate длиннее 40 символов (%d)' % len(title))
        word_count = len(title.split())
        if not 1 <= word_count <= 4:
            violations.append('title_candidate не 1..4 слова (%d)' % word_count)
    return violations


# ---------------------------------------------------------------------------
# §12 правило 4 API_RUN_MASTER: «Понятия только из шорт-листа, теги только
# из 344, темы только из 29. Всё вне списка — в отчёт, не в базу.» У
# OpenAI/Anthropic это держит `strict: true` на стороне поставщика; у GLM
# (Z.AI) `response_format` не принимает `json_schema`/`strict` вовсе (см.
# докстринг `providers.GLMProvider`) — enum/тип/обязательность проверяет
# ТОЛЬКО этот код. `validate_call1`/`validate_call2` выше НЕ включают эту
# проверку специально: они гоняются в 130+ тестах с плейсхолдерами вида
# `topic_primary: 'X'`, `tags: ['a']`, которые не обязаны быть настоящими
# id из `data/taxonomy.json` — совмещать со схемой их вызывающий код должен
# сам (см. `_process_one_problem` для боевого пути).
# ---------------------------------------------------------------------------

_JSON_TYPE_MAP = {'string': str, 'integer': int, 'array': list, 'object': dict,
                  'boolean': bool, 'null': type(None)}


def _json_type_ok(value, types):
    for t in types:
        if t == 'integer' and isinstance(value, bool):
            continue  # bool — подкласс int, схема integer его не разрешает
        py = _JSON_TYPE_MAP.get(t)
        if py and isinstance(value, py):
            return True
    return False


def _check_schema_value(label, value, spec):
    violations = []
    types = spec.get('type')
    types = [types] if isinstance(types, str) else list(types or [])
    if 'null' in types and value is None:
        return violations
    if types and not _json_type_ok(value, types):
        violations.append('%s: тип %s не входит в %s' % (label, type(value).__name__, types))
        return violations
    if 'enum' in spec and value not in spec['enum']:
        violations.append('%s: значение %r вне enum' % (label, value))
    # `difficulty` (1..5) — единственное числовое поле схемы с границами;
    # JSON Schema `minimum`/`maximum` не проверялись здесь вовсе (Фаза 1,
    # 02.09.2026, вторая пересъёмка) — раньше их держал только тип
    # integer/null, диапазон не проверялся никем.
    if (isinstance(value, (int, float)) and not isinstance(value, bool)):
        minimum = spec.get('minimum')
        maximum = spec.get('maximum')
        if minimum is not None and value < minimum:
            violations.append('%s: значение %r меньше минимума %r'
                              % (label, value, minimum))
        if maximum is not None and value > maximum:
            violations.append('%s: значение %r больше максимума %r'
                              % (label, value, maximum))
    if isinstance(value, list):
        items_spec = spec.get('items')
        if items_spec:
            for i, item in enumerate(value):
                violations.extend(_check_schema_value('%s[%d]' % (label, i), item, items_spec))
    return violations


def check_against_schema(data, schema):
    """Полная проверка JSON Schema верхнего уровня — required/
    additionalProperties/type/enum, рекурсивно по элементам массивов. Тем
    же способом, каким это уже делает `glm_eval.py::validate_schema` —
    отдельная копия здесь, а не импорт из `glm_eval`, потому что тот файл
    — разовый замер сравнения моделей, а этот — постоянный боевой путь;
    менять их синхронно означало бы держать связь там, где её не должно
    быть."""
    if not isinstance(data, dict):
        return ['ответ — не JSON-объект (%s)' % type(data).__name__]
    violations = []
    props = schema.get('properties', {})
    for key in schema.get('required', []):
        if key not in data:
            violations.append('нет обязательного поля %s' % key)
    if schema.get('additionalProperties') is False:
        extra = sorted(set(data) - set(props))
        if extra:
            violations.append('лишние поля вне схемы: %s' % extra)
    for key, spec in props.items():
        if key in data:
            violations.extend(_check_schema_value(key, data[key], spec))
    return violations


def validate_call1_full(data, with_concepts=True, shortlist_terms=None):
    """`validate_call1` + `check_against_schema` вместе — боевой путь
    (GLM), где enum/тип поставщик не проверяет вовсе. Только ЖЁСТКИЕ
    нарушения — мягкие считаются отдельно, см. `soft_violations_call1`."""
    schema_violations = check_against_schema(
        data, prompts_v2.call1_schema(with_concepts=with_concepts))
    ok, violations = validate_call1(data, with_concepts=with_concepts,
                                    shortlist_terms=shortlist_terms)
    all_violations = schema_violations + violations
    return (not all_violations, all_violations)


def validate_call2_full(data):
    """`validate_call2` + `check_against_schema` вместе — боевой путь."""
    schema_violations = check_against_schema(data, prompts_v2.CALL2_SCHEMA)
    ok, violations = validate_call2(data)
    all_violations = schema_violations + violations
    return (not all_violations, all_violations)


# ---------------------------------------------------------------------------
# Фаза 2 (боевой прогон на GLM, 02.09.2026): у Z.AI нет строгой схемы
# (`response_format` принимает только `text`/`json_object`, не
# `json_schema` со `strict`) — весь контроль формата держит наш код, а не
# поставщик. §12 правило 4: «Механика при нарушении: один повтор с коротким
# сообщением, что именно не так. Не помогло — задача в очередь брака, а не
# в результат.»
# ---------------------------------------------------------------------------

def _safe_json_loads(text):
    """`None` вместо исключения — для журналирования неудачных попыток,
    где сам факт «не распарсилось» и есть содержательный результат."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


RETRY_PROMPT_TEMPLATE = (
    '\n\n=== ПРЕДЫДУЩИЙ ОТВЕТ НЕ ПРОШЁЛ ПРОВЕРКУ ===\n'
    'Вот что было не так:\n- %s\n'
    'Ответь ЗАНОВО, тем же JSON-объектом целиком, исправив ровно это. '
    'Остальное в ответе не трогай, если оно не упомянуто выше.'
)


def call_with_retry(complete_fn, model, blocks, user_text, schema, effort,
                    images, validate_fn, sanitize_fn=None):
    """Один вызов; если `validate_fn(data)` вернула нарушения (включая
    «это вообще не JSON») — ровно ОДИН повторный вызов с явным списком
    нарушений в промпте. Не помогло — возвращается `ok=False` с
    нарушениями второй попытки, дальше решает вызывающий код (очередь
    брака, не результат).

    `sanitize_fn(data)`, если задан, правит разобранный ответ НА МЕСТЕ
    ПЕРЕД проверкой — там, где нарушение чинится выбрасыванием части
    ответа, а не повторным вызовом (Фаза 1.2: запрос с цифрой, см.
    `drop_digit_search_queries`). Зовётся на КАЖДОЙ попытке: иначе повтор
    проверялся бы по другим правилам, чем первая попытка.

    Возвращает `(reply, data, ok, violations, retried, attempts)` —
    `reply`/`data` от ПОСЛЕДНЕЙ попытки, `attempts` — список ВСЕХ `Reply`
    (1 или 2) для учёта расхода: неудачная первая попытка тоже стоила
    денег, и `real_call_cost` должен просуммировать обе, а не только
    финальную — иначе `--max-cost` молча недосчитывает потраченное.
    """
    def parse_and_check(reply):
        try:
            data = json.loads(reply.text)
        except (ValueError, TypeError):
            return None, False, ['ответ не является JSON']
        if sanitize_fn is not None:
            sanitize_fn(data)
        ok, violations = validate_fn(data)
        return data, ok, violations

    reply = complete_fn(model, blocks, user_text, schema, effort, images=images)
    data, ok, violations = parse_and_check(reply)
    if ok:
        return reply, data, True, [], False, [reply]

    retry_text = user_text + RETRY_PROMPT_TEMPLATE % '\n- '.join(violations)
    reply2 = complete_fn(model, blocks, retry_text, schema, effort, images=images)
    data2, ok2, violations2 = parse_and_check(reply2)
    return reply2, data2, ok2, violations2, True, [reply, reply2]


# ---------------------------------------------------------------------------
# Смета — ОЦЕНКА до прогона. Формула повторяет `problems/ai/core.py::_cost`
# (кэш-запись ×1.25 один раз на ядро/модель, кэш-чтение на все повторные).
# ---------------------------------------------------------------------------

def _model_prices(model):
    prices = getattr(settings, 'AI_PRICES', {})
    row = prices.get(model)
    if not row or len(row) != 3:
        raise CommandError(
            'В AI_PRICES нет тройной цены (вход, кэш, выход) для модели '
            '%r — без неё смета посчитается неверно.' % model)
    return tuple(Decimal(str(x)) for x in row)


def estimate_call_cost(model, effort, core_chars, variable_chars_list,
                       output_tokens_each):
    """Смета одного из двух вызовов на всю выборку одной ветки."""
    price_in, price_cache, price_out = _model_prices(model)
    core_tokens = Decimal(core_chars) / Decimal(str(CHARS_PER_TOKEN_ESTIMATE))
    n = len(variable_chars_list)
    if n == 0:
        return Decimal('0')

    variable_tokens = sum(
        Decimal(c) / Decimal(str(CHARS_PER_TOKEN_ESTIMATE))
        for c in variable_chars_list)
    output_tokens = Decimal(output_tokens_each) * n
    if effort not in (None, 'none'):
        output_tokens += Decimal(REASONING_OUTPUT_TOKENS_ESTIMATE) * n

    cache_write = core_tokens * price_in * Decimal('1.25')
    cache_read = core_tokens * Decimal(n - 1) * price_cache if n > 1 else Decimal('0')
    variable_cost = variable_tokens * price_in
    output_cost = output_tokens * price_out

    return (cache_write + cache_read + variable_cost + output_cost) / Decimal(10 ** 6)


def estimate_variant_cost(sample_problems, variant, shortlists,
                          with_tikz=True):
    """Смета одной ветки на всю выборку. Возвращает `(total, breakdown)`."""
    with_concepts = variant['concepts']
    core1 = prompts_v2.call1_core(with_concepts=with_concepts)
    core2 = prompts_v2.call2_core()

    call1_texts = []
    call2_texts = []
    call2_has_solution = []
    for problem in sample_problems:
        text = problem_full_text(problem.statement, problem.parts.all())
        text = with_figure_note(text, problem.figures.count())
        # §3.5: чертёж уходит ТОЛЬКО в вызов 1, поэтому и в смете он
        # считается только там — `text` для вызова 2 остаётся прежним.
        text1 = text
        if with_tikz:
            text1, _ = with_tikz_sources(text, problem.figures.all())
        shortlist_terms = shortlists.get(problem.id) if with_concepts else None
        call1_texts.append(prompts_v2.call1_user_text(text1, shortlist_terms))
        has_solution = bool(problem.solution)
        call2_texts.append(prompts_v2.call2_user_text(
            text, '', '', problem.solution, problem.answer))
        call2_has_solution.append(has_solution)

    cost1 = estimate_call_cost(
        variant['call1_model'], variant['call1_effort'], len(core1),
        [len(t) for t in call1_texts],
        ESTIMATED_OUTPUT_TOKENS_CALL1[with_concepts])

    # Выход вызова 2 разный, есть решение или нет — считаем по факту решения.
    out2 = [ESTIMATED_OUTPUT_TOKENS_CALL2[has] for has in call2_has_solution]
    cost2 = estimate_call_cost(
        variant['call2_model'], variant['call2_effort'], len(core2),
        [len(t) for t in call2_texts], 0)
    # у вызова 2 выходные токены неравномерны — добавляем отдельно.
    price2_out = _model_prices(variant['call2_model'])[2]
    cost2 += (Decimal(sum(out2)) * price2_out) / Decimal(10 ** 6)
    if variant['call2_effort'] not in (None, 'none'):
        cost2 += (Decimal(REASONING_OUTPUT_TOKENS_ESTIMATE * len(sample_problems))
                 * price2_out) / Decimal(10 ** 6)

    total = cost1 + cost2
    return total, {'call1': cost1, 'call2': cost2}


# ---------------------------------------------------------------------------
# Прогон --apply. `complete_fn(model, blocks, user_text, schema, effort) ->
# providers.Reply` — параметр, а не жёстко зашитый провайдер: тесты
# подсовывают подставную функцию, боевой код — обёртку над
# `OpenAIProvider.complete`.
# ---------------------------------------------------------------------------

def real_call_cost(model, reply):
    """То же самое, что `problems.ai.core._cost`, но без импорта core —
    core.py рассчитан на профиль продукта (см. докстринг модуля)."""
    price_in, price_cache, price_out = _model_prices(model)
    total = (
        Decimal(reply.input_tokens) * price_in
        + Decimal(reply.output_tokens) * price_out
        + Decimal(reply.cache_write_tokens) * price_in * Decimal('1.25')
        + Decimal(reply.cache_read_tokens) * price_cache
    )
    return total / Decimal(10 ** 6)


NETWORK_RETRIES = 5
NETWORK_RETRY_BASE_SECONDS = 2  # 2, 4, 8, 16 — растёт на каждой попытке
RETRYABLE_PROVIDER_ERROR_KINDS = ('other', 'limit')


def make_openai_complete_fn():
    """Обёртка над `OpenAIProvider.complete` для боевого `--apply`.

    ⚠️ ОБХОД `core.run()` — см. докстринг модуля целиком.

    ⚠️ ПОВТОР НА ОБРЫВЕ СЕТИ (Фаза 5, боевой пилот 01.09.2026) — у
    владельца постоянно включён VPN, и `luna-luna` упала на 86-й задаче из
    3000 запланированных именно на таймауте. `kind='no_key'` (ключ не
    настроен) НЕ повторяется — ждать тут нечего, отказ постоянный.
    """
    provider = providers.OpenAIProvider()

    def _call_once(model, blocks, user_text, schema, effort, images):
        if effort is None:
            return provider.complete(blocks, user_text, schema, model,
                                     _setting_max_tokens(), images=images)
        with override_settings(AI_REASONING_EFFORT=effort):
            return provider.complete(blocks, user_text, schema, model,
                                     _setting_max_tokens(), images=images)

    def complete_fn(model, blocks, user_text, schema, effort, images=None):
        last_error = None
        for attempt in range(NETWORK_RETRIES):
            if attempt:
                time.sleep(NETWORK_RETRY_BASE_SECONDS * (2 ** (attempt - 1)))
            try:
                return _call_once(model, blocks, user_text, schema, effort, images)
            except providers.ProviderError as error:
                if error.kind not in RETRYABLE_PROVIDER_ERROR_KINDS:
                    raise
                last_error = error
        raise last_error

    return complete_fn


def _setting_max_tokens():
    return getattr(settings, 'AI_MAX_TOKENS', 4000)


def run_variant(sample_problems, variant, complete_fn, shortlists,
                max_cost=None, on_progress=None, on_row=None,
                with_tikz=True):
    """Реальный прогон одной ветки. Останавливается, как только
    накопленный ФАКТИЧЕСКИЙ расход достигает `max_cost` — не по смете.

    `on_row(row)` — опционально, зовётся сразу после того, как строка
    добавлена в `rows` (Фаза 2Б.1/2Б.2, 2026-09-01): туда вешается запись
    сырого ответа в журнал, не трогая саму функцию прогона.
    """
    with_concepts = variant['concepts']
    core1_blocks = [prompts_v2.call1_core(with_concepts=with_concepts)]
    core2_blocks = [prompts_v2.call2_core()]
    schema1 = prompts_v2.call1_schema(with_concepts=with_concepts)
    schema2 = prompts_v2.CALL2_SCHEMA

    spent = Decimal('0')
    rows = []
    stopped_early = False

    for problem in sample_problems:
        if max_cost is not None and spent >= Decimal(str(max_cost)):
            stopped_early = True
            break

        text = problem_full_text(problem.statement, problem.parts.all())
        text = with_figure_note(text, problem.figures.count())
        # §3.5 API_RUN_MASTER: маркер чертежа заменяется его исходником —
        # ТОЛЬКО в вызове 1. Порядок с `with_figure_note` не случайный:
        # она смотрит, есть ли в тексте маркер, и подстановка съедает его.
        # `text` ниже (вызов 2) остаётся БЕЗ чертежа — там его смысл уже
        # несут `given`/`find`.
        text1 = text
        tikz_stats = {'replaced': 0, 'truncated': 0}
        if with_tikz:
            text1, tikz_stats = with_tikz_sources(text, problem.figures.all())
        shortlist_terms = shortlists.get(problem.id) if with_concepts else None
        # Фаза 1 (2026-09-04, реверс §3.4 API_RUN_MASTER): решение — только
        # как подсказка об аппарате, только если оно есть, с потолком.
        solution_block, solution_stats = enrich_text.solution_hint_for_call1(
            problem.solution)
        user1 = prompts_v2.call1_user_text(
            text1, shortlist_terms, solution_block=solution_block)
        # Фаза 0.4: растровые картинки условия — В КАРТИНКУ вызова 1, а не
        # текстом (GLM-5.3-Flash подтверждённо их читает). Только вызов 1 —
        # во втором смысл картинки уже несут given/find первого.
        images1 = images_for_call1(problem.figures.all())
        reply1 = complete_fn(variant['call1_model'], core1_blocks, user1,
                             schema1, variant['call1_effort'], images=images1)
        spent += real_call_cost(variant['call1_model'], reply1)
        data1 = json.loads(reply1.text)
        ok1, violations1 = validate_call1(data1, with_concepts)

        row = {'problem_id': problem.id, 'call1': data1,
              'call1_violations': violations1, 'call1_usage': reply1,
              'tikz': tikz_stats, 'images_sent': len(images1),
              'solution_sent': solution_stats['sent'],
              'solution_tokens': solution_stats['tokens'],
              'solution_truncated': solution_stats['truncated']}

        if max_cost is not None and spent >= Decimal(str(max_cost)):
            rows.append(row)
            if on_row:
                on_row(row)
            stopped_early = True
            break

        try:
            topic_primary_name = taxonomy.theme_name_from_id(
                data1.get('topic_primary', ''))
        except KeyError:
            topic_primary_name = ''
        user2 = prompts_v2.call2_user_text(
            text, data1.get('given', ''), data1.get('find', ''),
            problem.solution, problem.answer,
            topic_primary_name=topic_primary_name,
            task_nature=data1.get('task_nature', ''))
        reply2 = complete_fn(variant['call2_model'], core2_blocks, user2,
                             schema2, variant['call2_effort'])
        spent += real_call_cost(variant['call2_model'], reply2)
        data2 = json.loads(reply2.text)
        ok2, violations2 = validate_call2(data2)

        row['call2'] = data2
        row['call2_violations'] = violations2
        row['call2_usage'] = reply2
        rows.append(row)
        if on_row:
            on_row(row)

        if on_progress:
            on_progress(problem.id, spent)

    return rows, spent, stopped_early


# ---------------------------------------------------------------------------
# Фаза 1 (02.09.2026, подготовка боевого прогона на GLM-5.3-Flash): пул
# воркеров. Z.AI ограничивает не RPM/TPM, а числом одновременных запросов
# «в полёте» (§3.6 API_RUN_MASTER) — 50 для GLM-5.3-Flash, разгонная проба
# выбирает рабочее число по факту. `run_variant` (последовательный) остаётся
# как есть — он проще для тестов и достаточен для пилотов до 300 задач без
# спешки; `run_variant_concurrent` — для разгонной пробы и боевого прогона.
# ---------------------------------------------------------------------------

def _process_one_problem(problem, variant, complete_fn, shortlists,
                         with_tikz, core1_blocks, core2_blocks, schema1,
                         schema2, call1_only=False):
    """Тело одной задачи (оба вызова) для `run_variant_concurrent` — БОЕВОЙ
    путь (GLM), с одним повтором на нарушение схемы (§12 правило 4, Фаза 2).

    `run_variant` (последовательный) — отдельный, более простой путь для
    пилотов/сравнения веток на OpenAI со `strict` схемой, где повтор почти
    не нужен; здесь дублирования логики нет специально: `run_variant`
    проще для его собственных тестов, а не забытая копия этой функции.

    Возвращает готовую `row`, включая `call1_ok`/`call2_ok` (прошла ли
    схему хоть с повтором — задача-брак получает `False`) и `call1_retried`
    /`call2_retried`. Расход и решение об остановке по `max_cost` — дело
    вызывающего кода.

    `call1_only=True` — вызов 2 НЕ ДЕЛАЕТСЯ ВОВСЕ (перегон корпуса
    03.09.2026): менялись только поля вызова 1 (темы, доп. темы, теги,
    понятия, «дано», «найти», характер задачи, особенности), а заголовок,
    сложность, тип задачи, подсказки и сюжет вызова 2 не трогали — платить
    за них второй раз незачем, это около трети сметы. В `row` тогда нет
    ключа `call2` вовсе, и журнал его не пишет (`resumable_run_variant*`
    проверяет `if 'call2' in row`); поля вызова 2 подставляет читающий код
    из СТАРОГО журнала — см. `glm_enrich_run._rows_from_log`.
    """
    with_concepts = variant['concepts']
    text = problem_full_text(problem.statement, problem.parts.all())
    text = with_figure_note(text, problem.figures.count())
    text1 = text
    tikz_stats = {'replaced': 0, 'truncated': 0}
    if with_tikz:
        text1, tikz_stats = with_tikz_sources(text, problem.figures.all())
    shortlist_terms = shortlists.get(problem.id) if with_concepts else None
    # Фаза 1 (2026-09-04, реверс §3.4 API_RUN_MASTER): решение — только как
    # подсказка об аппарате, только если оно есть, с потолком 800 токенов.
    solution_block, solution_stats = enrich_text.solution_hint_for_call1(
        problem.solution)
    user1 = prompts_v2.call1_user_text(
        text1, shortlist_terms, solution_block=solution_block)
    images1 = images_for_call1(problem.figures.all())
    reply1, data1, ok1, violations1, retried1, attempts1 = call_with_retry(
        complete_fn, variant['call1_model'], core1_blocks, user1, schema1,
        variant['call1_effort'], images1,
        lambda d: validate_call1_full(d, with_concepts, shortlist_terms=shortlist_terms))
    strip_given_find_prefixes(data1)
    row = {'problem_id': problem.id, 'call1': data1,
          'call1_violations': violations1, 'call1_usage': reply1,
          'call1_ok': ok1, 'call1_retried': retried1,
          'call1_attempts': attempts1,
          'call1_soft_violations': soft_violations_call1(data1, with_concepts),
          'tikz': tikz_stats, 'images_sent': len(images1),
          'solution_sent': solution_stats['sent'],
          'solution_tokens': solution_stats['tokens'],
          'solution_truncated': solution_stats['truncated']}

    if call1_only:
        return row

    data1 = data1 or {}
    try:
        topic_primary_name = taxonomy.theme_name_from_id(
            data1.get('topic_primary', ''))
    except KeyError:
        topic_primary_name = ''
    user2 = prompts_v2.call2_user_text(
        text, data1.get('given', ''), data1.get('find', ''),
        problem.solution, problem.answer,
        topic_primary_name=topic_primary_name,
        task_nature=data1.get('task_nature', ''))
    # Фаза 1.2: запрос с цифрой выбрасывается ДО проверки — вызов из-за
    # него не повторяется (см. `drop_digit_search_queries`).
    sanitize2, dropped2 = make_query_sanitizer()
    reply2, data2, ok2, violations2, retried2, attempts2 = call_with_retry(
        complete_fn, variant['call2_model'], core2_blocks, user2, schema2,
        variant['call2_effort'], None, validate_call2_full,
        sanitize_fn=sanitize2)
    row['call2'] = data2
    row['call2_violations'] = violations2
    row['call2_usage'] = reply2
    row['call2_ok'] = ok2
    row['call2_retried'] = retried2
    row['call2_attempts'] = attempts2
    row['call2_soft_violations'] = soft_violations_call2(data2)
    row['dropped_queries'] = dropped2['dropped']
    return row


def run_variant_concurrent(sample_problems, variant, complete_fn, shortlists,
                           workers, max_cost=None, on_progress=None,
                           on_row=None, with_tikz=True, stop_event=None,
                           call1_only=False):
    """Как `run_variant`, но до `workers` задач обрабатываются ОДНОВРЕМЕННО
    (`ThreadPoolExecutor`) — Z.AI лимитирует одновременность, а не RPM,
    поэтому throughput держит именно параллелизм (§3.6).

    `max_cost` проверяется под локом ПЕРЕД тем, как задача берёт вызов 1 —
    значит перебор потолка возможен максимум на те задачи, что УЖЕ летят
    (до `workers` штук), не больше. Это тот же компромисс, что у любого
    распределённого лимитера — точный стоп ровно на потолке потребовал бы
    отменять уже отправленные HTTP-запросы, а платить за них всё равно
    придётся.

    `complete_fn` обязан быть потокобезопасным — `OpenAIProvider`/
    `GLMProvider.complete()` создают свой HTTP-клиент на каждый вызов,
    общего изменяемого состояния между вызовами нет.

    Задача, упавшая исключением ПОСЛЕ исчерпания сетевых повторов внутри
    `complete_fn` (не 429/обрыв — те уже отработаны там), НЕ роняет весь
    пул — 300 оплаченных задач не должны теряться из-за одной. Ошибка
    попадает в четвёртый элемент возврата `errors` — `[(problem_id,
    exception), ...]` — вызывающий код решает, звать ли повтор.

    `stop_event` (`threading.Event`, опционально) — Фаза 2, автостоп при
    доле брака выше 3%: вызывающий код (обычно `on_row`) может дёрнуть
    `.set()`, и НОВЫЕ задачи перестанут стартовать (уже летящие —
    доработают). Тот же кооперативный компромисс, что и у `max_cost`.

    Возвращает `(rows, spent, stopped_early, errors)`.
    """
    with_concepts = variant['concepts']
    core1_blocks = [prompts_v2.call1_core(with_concepts=with_concepts)]
    core2_blocks = [prompts_v2.call2_core()]
    schema1 = prompts_v2.call1_schema(with_concepts=with_concepts)
    schema2 = prompts_v2.CALL2_SCHEMA

    lock = threading.Lock()
    state = {'spent': Decimal('0'), 'stopped': False}
    rows = []
    errors = []

    def worker(problem):
        with lock:
            if state['stopped']:
                return
            if max_cost is not None and state['spent'] >= Decimal(str(max_cost)):
                state['stopped'] = True
                return
            if stop_event is not None and stop_event.is_set():
                state['stopped'] = True
                return

        try:
            row = _process_one_problem(
                problem, variant, complete_fn, shortlists, with_tikz,
                core1_blocks, core2_blocks, schema1, schema2,
                call1_only=call1_only)
        except Exception as error:  # сеть/парсинг — не роняем весь пул
            with lock:
                errors.append((problem.id, error))
            return

        # Суммируем ВСЕ попытки (call_with_retry могла сделать по 2 на
        # каждый вызов) — иначе неудачная первая попытка тратит деньги,
        # но не учитывается в `spent`, и --max-cost недосчитывает расход.
        cost = (
            sum(real_call_cost(variant['call1_model'], r) for r in row['call1_attempts'])
            + sum(real_call_cost(variant['call2_model'], r)
                  for r in row.get('call2_attempts') or [])
        )
        with lock:
            state['spent'] += cost
            if max_cost is not None and state['spent'] >= Decimal(str(max_cost)):
                state['stopped'] = True
            rows.append(row)
            if on_row:
                on_row(row)
            spent_now = state['spent']
        if on_progress:
            on_progress(problem.id, spent_now)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker, problem) for problem in sample_problems]
        concurrent.futures.wait(futures)

    return rows, state['spent'], state['stopped'], errors


# ---------------------------------------------------------------------------
# Фаза 2Б.1 (2026-09-01): сырой ответ модели ЦЕЛИКОМ — JSONL, одна строка на
# вызов. Разбор в Python может содержать баг или не сохранить поле, которое
# понадобится позже; сырой JSON рядом с манифестом (run_id, версия промпта,
# модель, usage) позволяет восстановить что угодно БЕЗ повторной оплаты
# прогона. НЕ путать с отчётом `--out`: тот — для глаз владельца, этот —
# архив на случай, если разбор придётся переделать.
# ---------------------------------------------------------------------------

def prompt_fingerprint(with_concepts=True):
    """Короткий отпечаток ТЕКСТА обоих ядер — «версия промпта» без ручного
    номера, который легко забыть увеличить. Меняется сам, как только
    меняется хоть один символ `call1_core()`/`call2_core()`."""
    blob = prompts_v2.call1_core(with_concepts=with_concepts) + '\x00' + \
        prompts_v2.call2_core()
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()[:12]


def append_raw_log(path, run_id, prompt_version, model, problem_id,
                   call_name, effort, reply, data):
    """Дописывает ОДНУ строку JSONL — один вызов (`call_name` = 'call1' или
    'call2') одной задачи. `data` — уже `json.loads(reply.text)`, но это
    ТОТ ЖЕ САМЫЙ ответ без потерь: разбор строки в словарь ничего не роняет,
    в отличие от прежнего бага, где в отчёт уходил `repr()` объекта `Reply`
    (`default=str` в `json.dumps`) вместо чисел usage.
    """
    entry = {
        'run_id': run_id,
        'prompt_version': prompt_version,
        'model': model,
        'effort': effort,
        'problem_id': problem_id,
        'call': call_name,
        'raw_response': data,
        'usage': {
            'input_tokens': reply.input_tokens,
            'output_tokens': reply.output_tokens,
            'cache_write_tokens': reply.cache_write_tokens,
            'cache_read_tokens': reply.cache_read_tokens,
            'reasoning_tokens': reply.reasoning_tokens,
        },
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(entry, ensure_ascii=False))
        fh.write('\n')
    return entry


def iter_raw_log(path):
    """Строки журнала ПО ОДНОЙ, генератором. Нет файла — пусто (первый
    прогон, резюмировать ещё нечего).

    ⚠️ Для боевого прогона это не украшательство: 41 тысяча задач даёт
    журнал под 150 МБ текста, и `read_raw_log` (список всех разобранных
    ответов сразу) на машине с полутора свободными гигабайтами его просто
    не удержит. Всё, что читает журнал целиком, обязано идти отсюда."""
    path = Path(path)
    if not path.exists():
        return
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_raw_log(path):
    """Все строки журнала обратно в СПИСОК словарей — удобно на пилотах и
    в тестах, где журнал маленький. На боевом прогоне — `iter_raw_log`."""
    return list(iter_raw_log(path))


def done_problem_ids_from_log(path, prompt_version, variant,
                              call1_only=False):
    """`_done_problem_ids`, но потоком по файлу — без списка всех записей
    в памяти (см. предупреждение в `iter_raw_log`)."""
    return _done_problem_ids(iter_raw_log(path), prompt_version, variant,
                             call1_only=call1_only)


# ---------------------------------------------------------------------------
# Фаза 2Б.2 (2026-09-01): резюмирование без повторной оплаты. «Уже
# обработана» — задача, у которой в журнале ЕСТЬ и call1, и call2 с той же
# версией промпта и той же моделью ветки. Задача, упавшая ровно между
# call1 и call2 (частичная строка), «обработанной» не считается и будет
# пересчитана целиком заново — это осознанное упрощение, не баг: различать
# «допилить только call2» от «начать с нуля» посреди строки `run_variant`
# не умеет, а такое падение — редкий пограничный случай, не типичный сбой.
# ---------------------------------------------------------------------------

def _done_problem_ids(log_entries, prompt_version, variant, call1_only=False):
    """⚠️ МОДЕЛЬ + EFFORT, НЕ ТОЛЬКО МОДЕЛЬ (баг Фазы 5, боевой пилот
    01.09.2026). `base` и `terra-low` зовут ОДНИ И ТЕ ЖЕ модели — их
    различает только `call1_effort` ('none' vs 'low'). Проверка по одной
    модели приняла результаты `base` за готовые для `terra-low` и тихо
    пропустила всю ветку: 0 обращений к API вместо 600 на боевом прогоне.
    """
    have_call1 = set()
    have_call2 = set()
    for entry in log_entries:
        if entry.get('prompt_version') != prompt_version:
            continue
        if (entry['call'] == 'call1'
                and entry['model'] == variant['call1_model']
                and entry.get('effort') == variant['call1_effort']):
            have_call1.add(entry['problem_id'])
        elif (entry['call'] == 'call2'
                and entry['model'] == variant['call2_model']
                and entry.get('effort') == variant['call2_effort']):
            have_call2.add(entry['problem_id'])
    # `call1_only` — вызова 2 в этом прогоне нет вовсе, и требовать его
    # наличия значило бы никогда ничего не считать готовым: резюмирование
    # платило бы за уже сделанный вызов 1 при каждом перезапуске.
    if call1_only:
        return have_call1
    return have_call1 & have_call2


def resumable_run_variant(sample_problems, variant, complete_fn, shortlists,
                          log_path, run_id, prompt_version,
                          max_cost=None, on_progress=None):
    """Обёртка над `run_variant`: сначала читает журнал, выкидывает из
    выборки уже полностью обработанные задачи (см. докстринг выше), затем
    прогоняет ОСТАВШИЕСЯ и дописывает каждую строку в журнал сразу — не
    в конце, чтобы падение на середине не потеряло уже оплаченное.

    Возвращает `(rows, spent, stopped_early, skipped)`.
    """
    existing = read_raw_log(log_path)
    done = _done_problem_ids(existing, prompt_version, variant)
    todo = [p for p in sample_problems if p.id not in done]
    skipped = len(sample_problems) - len(todo)

    def on_row(row):
        append_raw_log(log_path, run_id, prompt_version,
                       variant['call1_model'], row['problem_id'], 'call1',
                       variant['call1_effort'], row['call1_usage'],
                       row['call1'])
        if 'call2' in row:
            append_raw_log(log_path, run_id, prompt_version,
                           variant['call2_model'], row['problem_id'],
                           'call2', variant['call2_effort'],
                           row['call2_usage'], row['call2'])

    rows, spent, stopped_early = run_variant(
        todo, variant, complete_fn, shortlists, max_cost=max_cost,
        on_progress=on_progress, on_row=on_row)
    return rows, spent, stopped_early, skipped


def resumable_run_variant_concurrent(sample_problems, variant, complete_fn,
                                     shortlists, log_path, run_id,
                                     prompt_version, workers, max_cost=None,
                                     on_progress=None, stop_event=None,
                                     extra_on_row=None, done_ids=None,
                                     call1_only=False):
    """`resumable_run_variant` + `run_variant_concurrent` — журнал (Фаза 3)
    и резюмируемость (Фаза 4) вместе с пулом воркеров (Фаза 1). Боевая
    команда прогона использует именно эту функцию — `on_row` здесь
    ОБЯЗАН быть под локом: без него параллельные `append_raw_log` из
    разных потоков могут перемешать строки JSONL.

    `extra_on_row(row)`, если задан, зовётся ПОСЛЕ записи в журнал (тот же
    лок) — боевая команда вешает сюда автостоп при доле брака выше 3%
    (Фаза 2): журнал уже видел эту задачу, отменять нечего.

    `done_ids`, если задан, ЗАМЕНЯЕТ чтение журнала: боевой прогон идёт
    кусками по 2000 задач, и перечитывать журнал на каждый кусок значило
    бы разобрать его двадцать раз подряд (см. `iter_raw_log`).

    Возвращает `(rows, spent, stopped_early, skipped, errors)`.
    """
    if done_ids is None:
        done_ids = _done_problem_ids(iter_raw_log(log_path), prompt_version,
                                     variant, call1_only=call1_only)
    todo = [p for p in sample_problems if p.id not in done_ids]
    skipped = len(sample_problems) - len(todo)

    log_lock = threading.Lock()

    def on_row(row):
        with log_lock:
            # `call1_attempts`/`call2_attempts` — 1 или 2 записи (Фаза 2:
            # неудачная первая попытка тоже стоила денег и тоже уходит в
            # журнал, иначе «run_raw.jsonl — страховка от повторной
            # оплаты» держит слово только для успешных с первого раза
            # задач). Последняя попытка — под именем 'call1'/'call2',
            # как и раньше (совместимость с `_done_problem_ids`/отчётом);
            # более ранние — под 'call1_retryN', отчётом не читаются, но
            # доступны для разбора.
            #
            # ⚠️ В журнал идёт РАЗБОР `reply.text`, а не `row['call1']`/
            # `row['call2']` — то есть ответ модели ДО нашей постобработки
            # (Фаза 1.2, 02.09.2026, четвёртая пересъёмка). Раньше
            # финальная попытка писалась уже обработанной, и с появлением
            # `drop_digit_search_queries` журнал перестал бы быть «сырым»:
            # восстановление метрик из него не увидело бы НИ ОДНОГО
            # выброшенного запроса, потому что выбросили их до записи.
            # Постобработку повторяет читающий код (`_rows_from_log`), и
            # тогда восстановление — чистая функция журнала.
            attempts1 = row.get('call1_attempts') or [row['call1_usage']]
            for i, reply in enumerate(attempts1):
                is_last = i == len(attempts1) - 1
                append_raw_log(
                    log_path, run_id, prompt_version, variant['call1_model'],
                    row['problem_id'], 'call1' if is_last else 'call1_retry%d' % (i + 1),
                    variant['call1_effort'], reply, _safe_json_loads(reply.text))
            if 'call2' in row:
                attempts2 = row.get('call2_attempts') or [row['call2_usage']]
                for i, reply in enumerate(attempts2):
                    is_last = i == len(attempts2) - 1
                    append_raw_log(
                        log_path, run_id, prompt_version, variant['call2_model'],
                        row['problem_id'], 'call2' if is_last else 'call2_retry%d' % (i + 1),
                        variant['call2_effort'], reply, _safe_json_loads(reply.text))
            if extra_on_row:
                extra_on_row(row)

    rows, spent, stopped_early, errors = run_variant_concurrent(
        todo, variant, complete_fn, shortlists, workers, max_cost=max_cost,
        on_progress=on_progress, on_row=on_row, stop_event=stop_event,
        call1_only=call1_only)
    return rows, spent, stopped_early, skipped, errors


# ---------------------------------------------------------------------------
# Фаза 2Б.3 (2026-09-01): путь записи `title_candidate`/`title_source` —
# ЕДИНСТВЕННЫЕ поля таксономии v2, у которых уже есть место в `Problem`
# (миграция 0049). Остальные поля вызова 1/2 (topic_primary, tags,
# econ_concepts, ...) своих колонок в базе пока не имеют — заводить их не
# входит в эту сессию (решение о хранении/схеме — отдельный разговор).
# Репетиция ПИШЕТ ТОЛЬКО В КОПИЮ db.sqlite3 — канон не трогает НИКОГДА.
# ---------------------------------------------------------------------------

def title_candidate_updates(rows, problems_by_id):
    """`(problem_id, title_candidate, title_source)` для задач, чья
    категория (§ `title_rules.classify_current_title`) требует записи —
    категория `CATEGORY_KEEP` ('D') сюда не попадает, значит их
    `title_candidate` останется как есть (обычно пустым)."""
    updates = []
    for row in rows:
        problem = problems_by_id.get(row['problem_id'])
        if problem is None:
            continue
        category, source = title_rules.classify_and_pick_source(
            problem.title, problem.statement)
        if category == title_rules.CATEGORY_KEEP:
            continue
        candidate = (row.get('call2') or {}).get('title_candidate', '')
        updates.append((row['problem_id'], candidate, source))
    return updates


def rehearse_db_write(db_path, updates):
    """Копирует `db_path` во временный файл, применяет `updates`
    (`title_candidate`/`title_source`) SQL-запросом К КОПИИ и возвращает
    `(путь_к_копии, список_инвариантов)`. Канон (`db_path`) не открывается
    на запись НИ РАЗУ — только `shutil.copy2` на чтение исходника.
    """
    table = Problem._meta.db_table
    canon_before = Path(db_path).stat().st_mtime_ns

    tmp_dir = tempfile.mkdtemp(prefix='pilot_enrich_rehearsal_')
    tmp_path = str(Path(tmp_dir) / 'rehearsal.sqlite3')
    shutil.copy2(db_path, tmp_path)

    conn = sqlite3.connect(tmp_path)
    try:
        cur = conn.cursor()
        applied = 0
        for problem_id, candidate, source in updates:
            cur.execute(
                'UPDATE %s SET title_candidate=?, title_source=? '
                'WHERE id=?' % table, (candidate, source, problem_id))
            if cur.rowcount:
                applied += 1
        conn.commit()
        cur.execute(
            "SELECT COUNT(*) FROM %s WHERE title_candidate != ''" % table)
        nonempty = cur.fetchone()[0]
    finally:
        conn.close()

    canon_after = Path(db_path).stat().st_mtime_ns
    invariants = [
        'строк со сменой title_candidate/title_source: %d из %d запрошенных'
        % (applied, len(updates)),
        'title_candidate непусто в копии: %d' % nonempty,
        'канон (%s) не тронут: mtime %s' % (
            db_path, 'совпадает' if canon_before == canon_after
            else 'ИЗМЕНИЛСЯ — ОСТАНОВИСЬ'),
        'копия: %s' % tmp_path,
    ]
    return tmp_path, invariants


# ---------------------------------------------------------------------------
# Команда
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Пилот прогона обогащения v2 (таксономия 1.1, OpenAIProvider).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=LIMIT_DEFAULT)
        parser.add_argument('--apply', action='store_true',
                            help='Без него API не вызывается вовсе.')
        parser.add_argument('--max-cost', type=float, default=None,
                            help='Обязателен вместе с --apply.')
        parser.add_argument('--variants', type=str, default='all',
                            help='Через запятую: %s или "all".' % ', '.join(ALL_VARIANTS))
        parser.add_argument('--out', type=str, default='pilot_v2_results.txt')
        parser.add_argument('--seed', type=int, default=SEED_DEFAULT)
        parser.add_argument('--mode', choices=['sync', 'batch'], default='sync')
        parser.add_argument(
            '--no-tikz', dest='with_tikz', action='store_false',
            help='Не подставлять исходник чертежа вместо маркера (§3.5). '
                 'Нужен ровно для замера «с чертежом против без»; в боевом '
                 'прогоне подстановка включена.')

    def handle(self, *args, **options):
        if options['apply'] and options['max_cost'] is None:
            raise CommandError('--apply требует --max-cost — прогона без '
                               'потолка расхода не бывает.')

        variants = self._resolve_variants(options['variants'])

        sample_ids, strata_report = build_sample(options['limit'], options['seed'])
        self.stdout.write('=== ВЫБОРКА (seed=%d) ===' % options['seed'])
        for line in strata_report:
            self.stdout.write('  ' + line)
        self.stdout.write('Итого задач: %d' % len(sample_ids))

        problems = list(
            Problem.objects.filter(id__in=sample_ids)
            .prefetch_related('parts').order_by('id'))
        problems_by_id = {p.id: p for p in problems}
        problems = [problems_by_id[pid] for pid in sample_ids if pid in problems_by_id]

        shortlists = {p.id: shortlist_for(
            problem_full_text(p.statement, p.parts.all())) for p in problems}

        self.stdout.write('')
        self.stdout.write('=== СМЕТА (оценка, не счёт — сверяется на '
                          'самом пилоте) ===')
        grand_total = Decimal('0')
        for key in variants:
            variant = VARIANTS[key]
            total, breakdown = estimate_variant_cost(
                problems, variant, shortlists, with_tikz=options['with_tikz'])
            grand_total += total
            self.stdout.write('  %-14s %-55s ~$%.4f (вызов1 ~$%.4f + вызов2 ~$%.4f)' % (
                key, variant['label'], total, breakdown['call1'], breakdown['call2']))
        self.stdout.write('ИТОГО по всем выбранным веткам: ~$%.4f' % grand_total)

        self.stdout.write('')
        self.stdout.write('=== СОДЕРЖИМОЕ ПРОМПТОВ (ядро вызова 1 с понятиями) ===')
        self.stdout.write(prompts_v2.call1_core(with_concepts=True))
        self.stdout.write('')
        self.stdout.write('=== СОДЕРЖИМОЕ ПРОМПТОВ (ядро вызова 2) ===')
        self.stdout.write(prompts_v2.call2_core())

        if problems:
            example = problems[0]
            example_text = problem_full_text(example.statement, example.parts.all())
            self.stdout.write('')
            self.stdout.write('=== ПРИМЕР ПОЛЬЗОВАТЕЛЬСКОЙ ЧАСТИ (задача #%d) ===' % example.id)
            self.stdout.write('--- вызов 1 ---')
            self.stdout.write(prompts_v2.call1_user_text(
                example_text, shortlists.get(example.id)))

        if not options['apply']:
            self.stdout.write('')
            self.stdout.write('ФАЗА ПОКАЗА: API не вызывался, денег не '
                              'потрачено. Если промпты и смета ок — '
                              'запусти с --apply --max-cost <сумма>.')
            return

        # --apply: реальный прогон. Не исполняется в этой сессии по правилу
        # CLAUDE.md — «Обращаться к API без явного «да» владельца» запрещено,
        # и стоп-гейт печати промптов выше как раз для этого «да».
        if options['mode'] == 'batch':
            raise CommandError(
                '--mode batch ещё не подключён к этой команде — Б3 '
                '(problems/ai/batch.py) построен отдельно, интеграция '
                'сюда — после замера Б4.')

        visual_before = visual_snapshot(sample_ids)

        complete_fn = make_openai_complete_fn()
        out_path = Path(options['out'])
        report_lines = []
        all_rows = []
        for key in variants:
            variant = VARIANTS[key]
            self.stdout.write('')
            self.stdout.write('=== ПРОГОН ВЕТКИ %s ===' % key)
            per_variant_cap = options['max_cost'] / len(variants)
            rows, spent, stopped_early = run_variant(
                problems, variant, complete_fn, shortlists,
                max_cost=per_variant_cap, with_tikz=options['with_tikz'],
                on_progress=lambda pid, s: self.stdout.write(
                    '  #%d готово, потрачено $%.4f' % (pid, s)))
            all_rows.extend(rows)
            report_lines.append('=== %s: обработано %d, потрачено $%.4f%s ===' % (
                key, len(rows), spent,
                ' (остановлено по --max-cost)' if stopped_early else ''))
            tikz_done = sum(r.get('tikz', {}).get('replaced', 0) for r in rows)
            tikz_cut = sum(r.get('tikz', {}).get('truncated', 0) for r in rows)
            report_lines.append(
                '=== %s: чертежей подставлено в вызов 1 — %d (обрезано по '
                'потолку %d токенов — %d) ===' % (
                    key, tikz_done, TIKZ_MAX_TOKENS, tikz_cut))
            divergent, pairs, pct = task_nature_divergence(rows)
            report_lines.append(
                '=== %s: расхождение вызов1/вызов2 по «это задача» — '
                '%d/%d (%.1f%%) ===' % (key, divergent, pairs, pct))
            gs = graphical_solution_breakdown(rows, problems_by_id)
            report_lines.append(
                '=== %s: «Графическое решение» после объединения по ИЛИ — '
                'итого %d (модель %d, код %d, совпало %d) ===' % (
                    key, gs['total_graphical'], gs['model'], gs['code'], gs['both']))
            for row in rows:
                report_lines.append(json.dumps(row, ensure_ascii=False, default=str))

        visual_after = visual_snapshot(sample_ids)
        diff_lines = diff_visual_snapshots(visual_before, visual_after)
        lost_visual, not_task_visual = visual_flag_lists(all_rows)
        diff_lines.append(
            'задач с ProblemFigure, помеченных «содержание в утраченном '
            'визуальном элементе»: %d%s' % (
                len(lost_visual),
                (' — id: %s' % lost_visual) if lost_visual else ''))
        diff_lines.append(
            'задач из визуальных страт, помеченных «это не задача»: %d%s' % (
                len(not_task_visual),
                (' — id: %s' % not_task_visual) if not_task_visual else ''))

        report_lines.append('')
        report_lines.append('=== ИНВАРИАНТЫ «НЕ ПОТЕРЯЛИ ВИЗУАЛЬНОЕ» (Фаза 6.2) ===')
        report_lines.extend(diff_lines)
        self.stdout.write('')
        self.stdout.write('=== ИНВАРИАНТЫ «НЕ ПОТЕРЯЛИ ВИЗУАЛЬНОЕ» ===')
        for line in diff_lines:
            self.stdout.write('  ' + line)

        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(report_lines))
        self.stdout.write('')
        self.stdout.write('Отчёт: %s' % out_path)

    def _resolve_variants(self, raw):
        if raw == 'all':
            return list(ALL_VARIANTS)
        keys = [k.strip() for k in raw.split(',') if k.strip()]
        unknown = [k for k in keys if k not in VARIANTS]
        if unknown:
            raise CommandError('Неизвестные ветки: %s. Доступны: %s' % (
                ', '.join(unknown), ', '.join(ALL_VARIANTS)))
        return keys
