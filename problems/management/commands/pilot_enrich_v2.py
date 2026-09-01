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
import json
import random
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.test import override_settings

from problems.ai import providers
from problems.enrich import prompts_v2, taxonomy
from problems.enrich.text import (has_graph_in_statement,
                                  has_table_in_statement, is_english_text,
                                  problem_full_text)
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

def validate_call1(data, with_concepts=True):
    violations = []
    if len(data.get('topics_secondary') or []) > 2:
        violations.append('topics_secondary длиннее 2')
    tags = data.get('tags') or []
    if not 1 <= len(tags) <= 5:
        violations.append('tags вне диапазона 1..5 (%d)' % len(tags))
    if with_concepts:
        concepts = data.get('econ_concepts') or []
        # Пустой список — законное исключение при `не_задача` (Фаза 4.5):
        # промпт разрешает 0 понятий именно в этом случае, счётчик не имеет
        # права ругаться на него как на промах мимо диапазона 3..6.
        if not (len(concepts) == 0 and data.get('task_nature') == 'не_задача'):
            if not 3 <= len(concepts) <= 6:
                violations.append(
                    'econ_concepts вне диапазона 3..6 (%d)' % len(concepts))
        if len(data.get('concepts_offlist') or []) > 2:
            violations.append('concepts_offlist длиннее 2')
    if len(data.get('features_1') or []) > 8:
        violations.append('features_1 длиннее 8')
    return (not violations, violations)


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
    violations = []
    queries = data.get('search_queries') or []
    if len(queries) != 8:
        violations.append('search_queries не равно 8 (%d)' % len(queries))
    hints = data.get('hints')
    if hints is not None and not 3 <= len(hints) <= 5:
        violations.append('hints вне диапазона 3..5 (%d)' % len(hints))

    # `title_candidate` (§5.8, Фаза 4.1/6.4) — границы не выражаются
    # схемой (maxLength не пробовали на этой schema, чтобы не рисковать
    # `strict` перед смок-тестом), проверяем в Python.
    title = data.get('title_candidate') or ''
    if not title:
        violations.append('title_candidate пуст')
    else:
        if len(title) > 40:
            violations.append('title_candidate длиннее 40 символов (%d)' % len(title))
        word_count = len(title.split())
        if not 1 <= word_count <= 4:
            violations.append('title_candidate не 1..4 слова (%d)' % word_count)
        if not title[:1].isupper():
            violations.append('title_candidate не с заглавной буквы')
        if title.endswith('.'):
            violations.append('title_candidate заканчивается точкой')
        if _TITLE_CANDIDATE_DIGIT_RE.search(title):
            violations.append('title_candidate содержит цифру')
        if _TITLE_CANDIDATE_LATEX_RE.search(title):
            violations.append('title_candidate содержит $ или \\')

    return (not violations, violations)


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


def estimate_variant_cost(sample_problems, variant, shortlists):
    """Смета одной ветки на всю выборку. Возвращает `(total, breakdown)`."""
    with_concepts = variant['concepts']
    core1 = prompts_v2.call1_core(with_concepts=with_concepts)
    core2 = prompts_v2.call2_core()

    call1_texts = []
    call2_texts = []
    call2_has_solution = []
    for problem in sample_problems:
        text = problem_full_text(problem.statement, problem.parts.all())
        shortlist_terms = shortlists.get(problem.id) if with_concepts else None
        call1_texts.append(prompts_v2.call1_user_text(text, shortlist_terms))
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


def make_openai_complete_fn():
    """Обёртка над `OpenAIProvider.complete` для боевого `--apply`.

    ⚠️ ОБХОД `core.run()` — см. докстринг модуля целиком.
    """
    provider = providers.OpenAIProvider()

    def complete_fn(model, blocks, user_text, schema, effort):
        if effort is None:
            reply = provider.complete(blocks, user_text, schema, model,
                                      _setting_max_tokens())
        else:
            with override_settings(AI_REASONING_EFFORT=effort):
                reply = provider.complete(blocks, user_text, schema, model,
                                          _setting_max_tokens())
        return reply

    return complete_fn


def _setting_max_tokens():
    return getattr(settings, 'AI_MAX_TOKENS', 4000)


def run_variant(sample_problems, variant, complete_fn, shortlists,
                max_cost=None, on_progress=None):
    """Реальный прогон одной ветки. Останавливается, как только
    накопленный ФАКТИЧЕСКИЙ расход достигает `max_cost` — не по смете.
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
        shortlist_terms = shortlists.get(problem.id) if with_concepts else None
        user1 = prompts_v2.call1_user_text(text, shortlist_terms)
        reply1 = complete_fn(variant['call1_model'], core1_blocks, user1,
                             schema1, variant['call1_effort'])
        spent += real_call_cost(variant['call1_model'], reply1)
        data1 = json.loads(reply1.text)
        ok1, violations1 = validate_call1(data1, with_concepts)

        row = {'problem_id': problem.id, 'call1': data1,
              'call1_violations': violations1, 'call1_usage': reply1}

        if max_cost is not None and spent >= Decimal(str(max_cost)):
            rows.append(row)
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

        if on_progress:
            on_progress(problem.id, spent)

    return rows, spent, stopped_early


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
            total, breakdown = estimate_variant_cost(problems, variant, shortlists)
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
                max_cost=per_variant_cap,
                on_progress=lambda pid, s: self.stdout.write(
                    '  #%d готово, потрачено $%.4f' % (pid, s)))
            all_rows.extend(rows)
            report_lines.append('=== %s: обработано %d, потрачено $%.4f%s ===' % (
                key, len(rows), spent,
                ' (остановлено по --max-cost)' if stopped_early else ''))
            divergent, pairs, pct = task_nature_divergence(rows)
            report_lines.append(
                '=== %s: расхождение вызов1/вызов2 по «это задача» — '
                '%d/%d (%.1f%%) ===' % (key, divergent, pairs, pct))
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
