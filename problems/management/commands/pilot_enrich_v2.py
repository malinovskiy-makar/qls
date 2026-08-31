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
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import override_settings

from problems.ai import providers
from problems.enrich import prompts_v2
from problems.enrich.text import is_english_text, problem_full_text
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
STRATA = [
    ('микро', 100, MICRO_TOPICS),
    ('макро', 60, MACRO_TOPICS),
    ('финансы', 40, FINANCE_TOPICS),
    ('международка', 30, INTERNATIONAL_TOPICS),
    ('неравенство и труд', 30, INEQUALITY_LABOR_TOPICS),
    ('англоязычные', 20, None),  # эвристика is_english_text
    ('заведомо сломанные', 20, 'DEFECT'),  # human_review == DEFECT
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
    """
    if limit == STRATA_TOTAL:
        return [(key, target, spec) for key, target, spec in STRATA]
    scaled = []
    for key, target, spec in STRATA:
        scaled.append([key, round(target * limit / STRATA_TOTAL), spec])
    diff = limit - sum(s[1] for s in scaled)
    if diff:
        biggest = max(range(len(scaled)), key=lambda i: scaled[i][1])
        scaled[biggest][1] += diff
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
        if not 3 <= len(concepts) <= 6:
            violations.append(
                'econ_concepts вне диапазона 3..6 (%d)' % len(concepts))
        if len(data.get('concepts_offlist') or []) > 2:
            violations.append('concepts_offlist длиннее 2')
    if len(data.get('features_1') or []) > 8:
        violations.append('features_1 длиннее 8')
    return (not violations, violations)


def validate_call2(data):
    violations = []
    queries = data.get('search_queries') or []
    if len(queries) != 8:
        violations.append('search_queries не равно 8 (%d)' % len(queries))
    hints = data.get('hints')
    if hints is not None and not 3 <= len(hints) <= 5:
        violations.append('hints вне диапазона 3..5 (%d)' % len(hints))
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

        user2 = prompts_v2.call2_user_text(
            text, data1.get('given', ''), data1.get('find', ''),
            problem.solution, problem.answer)
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

        complete_fn = make_openai_complete_fn()
        out_path = Path(options['out'])
        report_lines = []
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
            report_lines.append('=== %s: обработано %d, потрачено $%.4f%s ===' % (
                key, len(rows), spent,
                ' (остановлено по --max-cost)' if stopped_early else ''))
            for row in rows:
                report_lines.append(json.dumps(row, ensure_ascii=False, default=str))

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
