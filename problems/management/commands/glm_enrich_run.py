# -*- coding: utf-8 -*-
"""glm_enrich_run — боевая команда прогона обогащения на GLM-5.3-Flash.

Фазы 3–5 API_RUN_MASTER (`claude/API_RUN_MASTER_20260830.md`):
- Фаза 3: три файла в `reports/enrich_pilot/` — `run_raw.jsonl` (сырой
  ответ на каждый вызов, пишет `resumable_run_variant_concurrent`),
  `run_parsed.jsonl` (разобранные поля на задачу) и `run_metrics.json`
  (сводка на изучение перед слиянием).
- Фаза 4: возобновление (журнал уже резюмируем — Фаза 1/2Б), устойчивость
  к сети (повтор внутри `complete_fn`), `--max-cost` по фактическому
  usage.
- Фаза 5: первые 300 задач — КОНТРОЛЬНАЯ ТОЧКА, не отдельная выборка.
  Эта команда сама себя не запускает на весь корпус — `--limit` решает
  человек, и по умолчанию (без флага) он БЕЗ ограничения, что для этой
  сессии означает: запускать ТОЛЬКО с `--limit 300`.

⚠️ В базу НИЧЕГО не пишет. Ни `topic_candidate`, ни `title`, ни любое
другое поле `Problem` — только файлы. Установка в банк — отдельная сессия
после приёмки владельцем (§ Шаг 8 API_RUN_MASTER).

⚠️ Состав: все задачи, кроме пяти служебных фикстур рендерера
(`Source.name == 'Служебное: фикстуры рендерера (не публиковать)'`).
Дубли включены — решение владельца.

Запуск (реальные деньги, `--max-cost` обязателен):
    manage.py glm_enrich_run --limit 300 --max-cost 3.0 --workers 50
"""
import json
import statistics
import threading
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.test import override_settings

from problems.ai import providers
from problems.enrich import prompts_v2, taxonomy, text as enrich_text
from problems.enrich.shortlist import shortlist_for
from problems.enrich.text import problem_full_text
from problems.management.commands import pilot_enrich_v2 as pilot
from problems.models import Problem

GLM_MODEL = 'glm-5.3-flash'
GLM_PRICES_PROMO = (0.075, 0.015, 0.25)  # скидка 50% до 24:00 09.09.2026 (UTC+8)

# Выбрано разгонной пробой 02.09.2026 (glm_ramp_probe): 0% отказов 429 на
# всех уровнях, 50 — разрешённый максимум Z.AI для GLM-5.3-Flash (§3.6).
WORKERS_DEFAULT = 50

FIRST_PASS_FAIL_STOP_PCT = 3.0
FIRST_PASS_FAIL_MIN_SAMPLE = 20  # не судить о доле брака по первым 2-3 задачам
CHECKPOINT_EVERY = 2000

REPORT_DIR = Path('reports/enrich_pilot')
RAW_LOG_PATH = REPORT_DIR / 'run_raw.jsonl'
PARSED_LOG_PATH = REPORT_DIR / 'run_parsed.jsonl'
METRICS_PATH = REPORT_DIR / 'run_metrics.json'
REVIEW_HTML_PATH = REPORT_DIR / 'run300_review.html'

SERVICE_FIXTURE_SOURCE = 'Служебное: фикстуры рендерера (не публиковать)'

GLM_VARIANT = {
    'label': 'glm-5.3-flash (низкий уровень рассуждения — минимум доступного, см. GLMProvider)',
    'call1_model': GLM_MODEL, 'call1_effort': 'low',
    'call2_model': GLM_MODEL, 'call2_effort': 'low',
    'concepts': True,
}


def battle_queryset():
    """Все задачи, кроме пяти служебных фикстур рендерера (Фаза 4),
    упорядоченные по id — детерминированно, чтобы «первые 300» были
    воспроизводимым подмножеством прогона, а не случайным."""
    return (Problem.objects
           .exclude(source_references__source__name=SERVICE_FIXTURE_SOURCE)
           .distinct().order_by('id'))


def make_glm_complete_fn():
    """Как `pilot.make_openai_complete_fn`, но для GLM — сетевые повторы
    (429/обрыв) те же, что и у боевого OpenAI-пути (Фаза 5, боевой пилот
    01.09.2026: обрыв на VPN — штатное событие, не падение)."""
    provider = providers.GLMProvider()

    def _call_once(model, blocks, user_text, schema, effort, images):
        with override_settings(AI_REASONING_EFFORT=effort or 'low'):
            return provider.complete(blocks, user_text, schema, model,
                                     pilot._setting_max_tokens(), images=images)

    def complete_fn(model, blocks, user_text, schema, effort, images=None):
        last_error = None
        for attempt in range(pilot.NETWORK_RETRIES):
            if attempt:
                time.sleep(pilot.NETWORK_RETRY_BASE_SECONDS * (2 ** (attempt - 1)))
            try:
                return _call_once(model, blocks, user_text, schema, effort, images)
            except providers.ProviderError as error:
                if error.kind not in pilot.RETRYABLE_PROVIDER_ERROR_KINDS:
                    raise
                last_error = error
        raise last_error

    return complete_fn


# ---------------------------------------------------------------------------
# Фаза 2: автостоп при доле брака (retry) выше 3% — считается по СКОЛЬЗЯЩЕМУ
# счётчику задач, обработанных С НАЧАЛА ЭТОГО ЗАПУСКА (не считая пропущенных
# резюмированием — те уже прошли проверку в прошлый раз).
# ---------------------------------------------------------------------------

class FirstPassFailureTracker(object):
    def __init__(self, min_sample=FIRST_PASS_FAIL_MIN_SAMPLE,
                stop_pct=FIRST_PASS_FAIL_STOP_PCT):
        self.lock = threading.Lock()
        self.total = 0
        self.retried = 0
        self.min_sample = min_sample
        self.stop_pct = stop_pct
        self.breached = False

    def record(self, row):
        with self.lock:
            self.total += 1
            if row.get('call1_retried') or row.get('call2_retried'):
                self.retried += 1
            if self.total >= self.min_sample:
                pct = self.retried / self.total * 100
                if pct > self.stop_pct:
                    self.breached = True

    def pct(self):
        with self.lock:
            return (self.retried / self.total * 100) if self.total else 0.0


# ---------------------------------------------------------------------------
# Фаза 3.2: run_parsed.jsonl — по строке на задачу.
# ---------------------------------------------------------------------------

def parsed_row(row, problem):
    """Одна строка `run_parsed.jsonl` — все разобранные поля обоих
    вызовов в готовом для слияния виде, что прошло проверку, брак ли."""
    call1 = row.get('call1') or {}
    call2 = row.get('call2') or {}
    is_defect = not (row.get('call1_ok') and row.get('call2_ok'))
    merged_graphical, graphical_source = enrich_text.merge_graphical_solution(
        call1.get('features_1'), problem)
    return {
        'problem_id': row['problem_id'],
        'defect': is_defect,
        'call1_ok': row.get('call1_ok'),
        'call1_retried': row.get('call1_retried'),
        'call1_violations': row.get('call1_violations'),
        'call2_ok': row.get('call2_ok'),
        'call2_retried': row.get('call2_retried'),
        'call2_violations': row.get('call2_violations'),
        'topic_primary': call1.get('topic_primary'),
        'topics_secondary': call1.get('topics_secondary'),
        'tags': call1.get('tags'),
        'given': call1.get('given'),
        'find': call1.get('find'),
        'econ_concepts': call1.get('econ_concepts'),
        'concepts_offlist': call1.get('concepts_offlist'),
        'task_nature': call1.get('task_nature'),
        'features_1': call1.get('features_1'),
        'topic_confidence': call1.get('topic_confidence'),
        'graphical_solution': merged_graphical,
        'graphical_solution_source': graphical_source,
        'search_queries': call2.get('search_queries'),
        'plot': call2.get('plot'),
        'hints': call2.get('hints'),
        'text_quality': call2.get('text_quality'),
        'text_quality_note': call2.get('text_quality_note'),
        'problem_type': call2.get('problem_type'),
        'difficulty': call2.get('difficulty'),
        'difficulty_note': call2.get('difficulty_note'),
        'answer_consistency': call2.get('answer_consistency'),
        'title_candidate': call2.get('title_candidate'),
        'images_sent': row.get('images_sent', 0),
        'tikz': row.get('tikz'),
    }


def write_parsed_log(path, rows, problems_by_id):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        for row in rows:
            problem = problems_by_id.get(row['problem_id'])
            if problem is None:
                continue
            fh.write(json.dumps(parsed_row(row, problem), ensure_ascii=False))
            fh.write('\n')


# ---------------------------------------------------------------------------
# Фаза 3.3: run_metrics.json — сводка.
# ---------------------------------------------------------------------------

def build_metrics(rows, problems_by_id, usage_totals):
    parsed = [parsed_row(row, problems_by_id[row['problem_id']])
             for row in rows if row['problem_id'] in problems_by_id]
    n = len(parsed)
    defects = [p for p in parsed if p['defect']]
    ok = [p for p in parsed if not p['defect']]

    def dist(field):
        return dict(Counter(p[field] for p in ok if p.get(field)))

    given_lens = [len(p['given']) for p in ok if p.get('given')]
    find_lens = [len(p['find']) for p in ok if p.get('find')]
    tags_counts = [len(p['tags'] or []) for p in ok]
    graphical = Counter(p['graphical_solution_source'] for p in parsed)

    return {
        'total_processed': n,
        'defects': len(defects),
        'defect_pct': (len(defects) / n * 100) if n else 0.0,
        'retried_call1': sum(1 for p in parsed if p['call1_retried']),
        'retried_call2': sum(1 for p in parsed if p['call2_retried']),
        'topic_primary_distribution': dist('topic_primary'),
        'problem_type_distribution': dist('problem_type'),
        'difficulty_distribution': dist('difficulty'),
        'text_quality_distribution': dist('text_quality'),
        'task_nature_distribution': dist('task_nature'),
        'given_len_median': statistics.median(given_lens) if given_lens else 0,
        'find_len_median': statistics.median(find_lens) if find_lens else 0,
        'tags_per_task_mean': statistics.mean(tags_counts) if tags_counts else 0,
        'images_sent_total': sum(p['images_sent'] for p in parsed),
        'tikz_replaced_total': sum((p['tikz'] or {}).get('replaced', 0) for p in parsed),
        'tikz_truncated_total': sum((p['tikz'] or {}).get('truncated', 0) for p in parsed),
        'graphical_solution': {
            'model': graphical.get('model', 0), 'code': graphical.get('code', 0),
            'both': graphical.get('both', 0), 'none': graphical.get('none', 0),
            'total': graphical.get('model', 0) + graphical.get('code', 0) + graphical.get('both', 0),
        },
        'usage_totals': usage_totals,
    }


def usage_totals_from_rows(rows):
    """Суммарный расход по input/cache/output — по ВСЕМ попыткам (Фаза 2:
    неудачные первые попытки тоже стоили денег)."""
    totals = {'input_tokens': 0, 'cache_read_tokens': 0,
             'cache_write_tokens': 0, 'output_tokens': 0,
             'reasoning_tokens': 0, 'cost_usd': '0'}
    cost = Decimal('0')
    for row in rows:
        for attempts in (row.get('call1_attempts') or [row.get('call1_usage')],
                         row.get('call2_attempts') or [row.get('call2_usage')]):
            for reply in attempts:
                if reply is None:
                    continue
                totals['input_tokens'] += reply.input_tokens
                totals['cache_read_tokens'] += reply.cache_read_tokens
                totals['cache_write_tokens'] += reply.cache_write_tokens
                totals['output_tokens'] += reply.output_tokens
                totals['reasoning_tokens'] += getattr(reply, 'reasoning_tokens', 0)
                cost += pilot.real_call_cost(GLM_MODEL, reply)
    totals['cost_usd'] = str(cost)
    return totals


# ---------------------------------------------------------------------------
# Команда
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Боевой прогон обогащения на GLM-5.3-Flash (Фазы 3-5 API_RUN_MASTER).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=None,
                            help='Число задач с начала battle_queryset(). '
                                 'ФАЗА 5 ЭТОЙ СЕССИИ: обязательно 300.')
        parser.add_argument('--max-cost', type=float, required=True)
        parser.add_argument('--workers', type=int, default=WORKERS_DEFAULT)
        parser.add_argument('--run-id', type=str, default=None)
        parser.add_argument(
            '--ids', type=str, default=None,
            help='Через запятую — конкретные id вместо первых --limit из '
                 'battle_queryset(). Например, донабор с картинками для '
                 'run300_review.html, который НЕ входит в официальный '
                 'чек-поинт «первые 300» (решение владельца 02.09.2026: '
                 'два честных прогона, не подмена выборки).')
        parser.add_argument(
            '--parsed-out', type=str, default=None,
            help='Переопределить путь run_parsed.jsonl (по умолчанию — '
                 'официальный файл Фазы 3.2). Использовать для донабора, '
                 'чтобы не затереть чек-поинт «первые 300».')
        parser.add_argument(
            '--metrics-out', type=str, default=None,
            help='Переопределить путь run_metrics.json — как --parsed-out.')

    def handle(self, *args, **options):
        run_id = options['run_id'] or ('glm-enrich-%d' % int(time.time()))
        limit = options['limit']
        parsed_out = Path(options['parsed_out']) if options['parsed_out'] else PARSED_LOG_PATH
        metrics_out = Path(options['metrics_out']) if options['metrics_out'] else METRICS_PATH

        if options['ids']:
            requested = [int(x) for x in options['ids'].split(',') if x.strip()]
            allowed = set(battle_queryset().values_list('id', flat=True))
            problem_ids = [i for i in requested if i in allowed]
            missing = set(requested) - allowed
            if missing:
                self.stdout.write('⚠️ вне battle_queryset() (фикстуры или не '
                                  'существуют), пропущены: %s' % sorted(missing))
        else:
            qs = battle_queryset()
            problem_ids = list(qs.values_list('id', flat=True))
            if limit is not None:
                problem_ids = problem_ids[:limit]
        problems = list(
            Problem.objects.filter(id__in=problem_ids)
            .prefetch_related('parts', 'figures'))
        problems_by_id = {p.id: p for p in problems}
        problems = [problems_by_id[pid] for pid in problem_ids if pid in problems_by_id]
        if not problems:
            raise CommandError('Выборка пуста.')

        self.stdout.write('=== БОЕВОЙ ПРОГОН GLM-5.3-Flash: %d задач, run_id=%s ==='
                          % (len(problems), run_id))
        self.stdout.write('workers=%d, max-cost=$%.4f' % (
            options['workers'], options['max_cost']))

        shortlists = {p.id: shortlist_for(problem_full_text(p.statement, p.parts.all()))
                     for p in problems}
        prompt_version = pilot.prompt_fingerprint(GLM_VARIANT['concepts'])
        complete_fn = make_glm_complete_fn()

        tracker = FirstPassFailureTracker()
        stop_event = threading.Event()
        processed_count = {'n': 0}
        count_lock = threading.Lock()
        start_time = time.monotonic()

        def on_progress(problem_id, spent):
            with count_lock:
                processed_count['n'] += 1
                n = processed_count['n']
            if n % CHECKPOINT_EVERY == 0:
                elapsed = time.monotonic() - start_time
                rate = n / elapsed * 60 if elapsed else 0.0
                remaining = len(problems) - n
                eta_min = remaining / rate if rate else float('inf')
                self.stdout.write(
                    '  [%d/%d] брак %.1f%%, потрачено $%.4f, %.1f задач/мин, '
                    'прогноз оставшегося: %.0f мин'
                    % (n, len(problems), tracker.pct(), spent, rate, eta_min))

        def extra_on_row(row):
            tracker.record(row)
            if tracker.breached:
                stop_event.set()

        # ⚠️ AI_PRICES для GLM оборачивает и сам прогон, и подсчёт метрик
        # НИЖЕ (usage_totals_from_rows -> real_call_cost тоже читает эту
        # настройку) — баг боевого пилота 02.09: контекст закрывался ДО
        # метрик, `_model_prices('glm-5.3-flash')` падал с CommandError
        # уже после того, как деньги были потрачены и журнал записан.
        with override_settings(AI_PRICES={GLM_MODEL: GLM_PRICES_PROMO}):
            try:
                rows, spent, stopped, skipped, errors = pilot.resumable_run_variant_concurrent(
                    problems, GLM_VARIANT, complete_fn, shortlists,
                    str(RAW_LOG_PATH), run_id, prompt_version,
                    options['workers'], max_cost=options['max_cost'],
                    on_progress=on_progress, stop_event=stop_event,
                    extra_on_row=extra_on_row)
            except KeyboardInterrupt:
                self.stdout.write('')
                self.stdout.write('⚠️ ОСТАНОВЛЕНО ПО Ctrl+C. Журнал %s уже содержит '
                                  'всё оплаченное — повторный запуск с тем же '
                                  '--run-id продолжит с места остановки, платить '
                                  'заново не придётся.' % RAW_LOG_PATH)
                return

            self.stdout.write('')
            self.stdout.write('обработано сейчас: %d, пропущено (уже в журнале): %d'
                              % (len(rows), skipped))
            self.stdout.write('потрачено: $%.4f%s' % (
                spent, ' (остановлено потолком)' if stopped else ''))
            if errors:
                self.stdout.write('⚠️ %d задач упали без восстановления (после сетевых '
                                  'повторов) — не попали ни в результат, ни в брак, '
                                  'нужен отдельный разбор: %s'
                                  % (len(errors), [pid for pid, _ in errors][:20]))
            if tracker.breached:
                self.stdout.write('')
                self.stdout.write('🔴 СТОП: доля задач, потребовавших повтор, — %.1f%% '
                                  '(порог 3%%). Прогон остановлен сам, дальше решает '
                                  'владелец.' % tracker.pct())

            # --- Фаза 3.2/3.3 -------------------------------------------
            all_entries = pilot.read_raw_log(str(RAW_LOG_PATH))
            all_rows = self._rows_from_log(all_entries, problem_ids, GLM_VARIANT, prompt_version)
            write_parsed_log(parsed_out, all_rows, problems_by_id)
            usage_totals = usage_totals_from_rows(all_rows)
            metrics = build_metrics(all_rows, problems_by_id, usage_totals)

        metrics_out.parent.mkdir(parents=True, exist_ok=True)
        with open(metrics_out, 'w', encoding='utf-8') as fh:
            json.dump(metrics, fh, ensure_ascii=False, indent=2, default=str)

        self.stdout.write('')
        self.stdout.write('=== СВОДКА (%s) ===' % metrics_out)
        self.stdout.write('всего в журнале для этой выборки: %d, брак: %d (%.1f%%)'
                          % (metrics['total_processed'], metrics['defects'],
                             metrics['defect_pct']))
        self.stdout.write('«Графическое решение»: модель %d, код %d, совпало %d, итого %d'
                          % (metrics['graphical_solution']['model'],
                             metrics['graphical_solution']['code'],
                             metrics['graphical_solution']['both'],
                             metrics['graphical_solution']['total']))
        self.stdout.write('расход по журналу (все попытки): $%s'
                          % usage_totals['cost_usd'])
        self.stdout.write('журналы: %s, %s' % (RAW_LOG_PATH, parsed_out))

    def _rows_from_log(self, entries, problem_ids, variant, prompt_version):
        """Восстанавливает `rows`-подобные словари из `run_raw.jsonl` для
        ВСЕЙ запрошенной выборки (не только обработанных в этом запуске —
        нужно для метрик после резюмирования, где часть задач могла быть
        пропущена как уже готовая).

        Собирает ВСЕ попытки каждого вызова (`call1` и, если была,
        `call1_retry1`) в `call1_attempts` — иначе `usage_totals_from_rows`
        недосчитает деньги, потраченные на неудачную первую попытку.
        `ok`/`retried` считаются `validate_call1_full`/`validate_call2_full`
        по ФИНАЛЬНОЙ попытке — тем же способом, каким это решалось вживую.
        """
        by_pid = {}
        for entry in entries:
            if entry.get('prompt_version') != prompt_version:
                continue
            call = entry['call']
            base_call = call.split('_retry')[0]
            if base_call not in ('call1', 'call2'):
                continue
            row = by_pid.setdefault(
                entry['problem_id'],
                {'problem_id': entry['problem_id'], 'call1_attempts': [],
                'call2_attempts': []})
            usage = entry['usage']

            class _U(object):
                pass
            u = _U()
            u.input_tokens = usage['input_tokens']
            u.output_tokens = usage['output_tokens']
            u.cache_write_tokens = usage.get('cache_write_tokens', 0)
            u.cache_read_tokens = usage['cache_read_tokens']
            u.reasoning_tokens = usage.get('reasoning_tokens', 0)
            row['%s_attempts' % base_call].append(u)
            if call == base_call:  # финальная попытка (без суффикса _retryN)
                row[base_call] = entry['raw_response']
                row['%s_usage' % base_call] = u

        rows = []
        wanted = set(problem_ids)
        for pid, row in by_pid.items():
            if pid not in wanted or 'call1' not in row:
                continue
            row['call1_ok'], _ = pilot.validate_call1_full(
                row.get('call1'), variant['concepts'])
            row['call1_retried'] = len(row['call1_attempts']) > 1
            row['call2_ok'], _ = pilot.validate_call2_full(row.get('call2'))
            row['call2_retried'] = len(row['call2_attempts']) > 1
            row.setdefault('images_sent', 0)
            row.setdefault('tikz', {'replaced': 0, 'truncated': 0})
            rows.append(row)
        return rows
