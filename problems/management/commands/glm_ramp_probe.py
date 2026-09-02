# -*- coding: utf-8 -*-
"""glm_ramp_probe — Фаза 1.1 API_RUN_MASTER: разгонная проба параллельности.

Z.AI лимитирует GLM-5.3-Flash по числу ОДНОВРЕМЕННЫХ запросов (§3.6), а не
по RPM/TPM — разрешённые 50 не обещание, что 50 реально выдержат под
нагрузкой. Эта команда прогоняет одну и ту же выборку из N задач ТРИ раза
подряд — при 50, затем при 25, затем при 10 одновременных запросах — и
печатает по каждому режиму: фактическую скорость (запросов/мин), долю 429,
среднюю и худшую задержку, число обрывов соединения.

⚠️ Каждый раунд бьёт по API заново (журнал НЕ используется — резюмируемый
`resumable_run_variant_concurrent` пропустил бы уже отвеченные задачи, и
второй/третий раунд не измерили бы throughput вовсе). Цена трёх раундов на
GLM тривиальна (ядро в кэше со второго вызова), но `--max-cost` всё равно
обязателен — без него разгонная проба не отличается от боевого прогона по
риску перерасхода.

⚠️ complete_fn ЗДЕСЬ НЕ ИСПОЛЬЗУЕТ автоматический повтор pilot_enrich_v2 —
тот прячет 429/обрывы за backoff, и снаружи их было бы не увидеть. Здесь
повтор свой, инструментированный: каждая попытка (успешная или нет) кладёт
секунду в статистику ДО того, как решить, повторять или нет.

Запуск (реальные деньги, `--max-cost` обязателен):
    manage.py glm_ramp_probe --limit 60 --max-cost 1.0
"""
import statistics
import threading
import time

from django.core.management.base import BaseCommand, CommandError
from django.test import override_settings

from problems.ai import providers
from problems.enrich.shortlist import shortlist_for
from problems.enrich.text import problem_full_text
from problems.management.commands import pilot_enrich_v2 as pilot
from problems.models import Problem

GLM_MODEL = 'glm-5.3-flash'
GLM_PRICES_PROMO = (0.075, 0.015, 0.25)  # скидка 50% до 24:00 09.09.2026 (UTC+8)

RAMP_LEVELS = (50, 25, 10)
MAX_ATTEMPTS = 6
BACKOFF_BASE_SECONDS = 2


def make_instrumented_glm_complete_fn(stats, stats_lock):
    """`complete_fn` для `run_variant_concurrent` — то же самое, что боевой
    вызов будет делать, но с явным счётом попыток вместо тихого backoff
    внутри `pilot_enrich_v2.make_openai_complete_fn`-подобной обёртки."""
    provider = providers.GLMProvider()

    def complete_fn(model, blocks, user_text, schema, effort, images=None):
        last_error = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            t0 = time.monotonic()
            try:
                with override_settings(AI_REASONING_EFFORT=effort or 'low'):
                    reply = provider.complete(
                        blocks, user_text, schema, model,
                        pilot._setting_max_tokens(), images=images)
                dt = time.monotonic() - t0
                with stats_lock:
                    stats['latencies'].append(dt)
                    stats['ok'] += 1
                return reply
            except providers.ProviderError as error:
                dt = time.monotonic() - t0
                last_error = error
                with stats_lock:
                    stats['latencies'].append(dt)
                    if error.kind == 'limit':
                        stats['rate_limited'] += 1
                    elif error.kind == 'other':
                        stats['connection_drops'] += 1
                    else:
                        stats['fatal'] += 1
                if error.kind not in ('limit', 'other') or attempt == MAX_ATTEMPTS:
                    raise
                time.sleep(min(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), 30))
        raise last_error

    return complete_fn


def run_one_level(problems, variant, shortlists, workers, max_cost):
    """Один режим разгонной пробы. Возвращает словарь метрик — печатается
    как есть, без интерпретации (интерпретация — «выбери максимум, где доля
    429 < 1%» — дело человека/отчёта, не этой функции)."""
    stats = {'latencies': [], 'ok': 0, 'rate_limited': 0,
             'connection_drops': 0, 'fatal': 0}
    stats_lock = threading.Lock()
    complete_fn = make_instrumented_glm_complete_fn(stats, stats_lock)

    with override_settings(AI_PRICES={GLM_MODEL: GLM_PRICES_PROMO}):
        t0 = time.monotonic()
        rows, spent, stopped, errors = pilot.run_variant_concurrent(
            problems, variant, complete_fn, shortlists, workers,
            max_cost=max_cost)
        wall_seconds = time.monotonic() - t0

    total_attempts = stats['ok'] + stats['rate_limited'] + stats['connection_drops'] + stats['fatal']
    requests_per_min = (total_attempts / wall_seconds * 60) if wall_seconds else 0.0
    lat = stats['latencies']
    return {
        'workers': workers,
        'tasks_done': len(rows),
        'tasks_total': len(problems),
        'wall_seconds': wall_seconds,
        'requests_per_min': requests_per_min,
        'attempts_total': total_attempts,
        'rate_limited': stats['rate_limited'],
        'rate_limited_pct': (stats['rate_limited'] / total_attempts * 100) if total_attempts else 0.0,
        'connection_drops': stats['connection_drops'],
        'fatal': stats['fatal'],
        'latency_avg': statistics.mean(lat) if lat else 0.0,
        'latency_worst': max(lat) if lat else 0.0,
        'spent': spent,
        'errors': len(errors),
        'stopped_by_cap': stopped,
    }


class Command(BaseCommand):
    help = 'Фаза 1.1 API_RUN_MASTER: разгонная проба 50/25/10 одновременных запросов GLM.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=60)
        parser.add_argument('--max-cost', type=float, required=True,
                            help='Потолок на КАЖДЫЙ из трёх режимов, не суммарно.')
        parser.add_argument('--seed', type=int, default=20260902)

    def handle(self, *args, **options):
        limit = options['limit']
        sample_ids, strata_report = pilot.build_sample(limit, options['seed'])
        problems = list(
            Problem.objects.filter(id__in=sample_ids).prefetch_related('parts', 'figures'))
        problems_by_id = {p.id: p for p in problems}
        problems = [problems_by_id[pid] for pid in sample_ids if pid in problems_by_id]
        if not problems:
            raise CommandError('Выборка пуста — нечего гонять.')

        shortlists = {p.id: shortlist_for(problem_full_text(p.statement, p.parts.all()))
                     for p in problems}
        variant = {'call1_model': GLM_MODEL, 'call1_effort': 'low',
                  'call2_model': GLM_MODEL, 'call2_effort': 'low',
                  'concepts': True}

        self.stdout.write('=== РАЗГОННАЯ ПРОБА: %d задач, режимы %s ===' % (
            len(problems), RAMP_LEVELS))

        results = []
        for level in RAMP_LEVELS:
            self.stdout.write('')
            self.stdout.write('--- %d одновременных запросов ---' % level)
            metrics = run_one_level(problems, variant, shortlists, level,
                                    options['max_cost'])
            results.append(metrics)
            self.stdout.write(
                '  готово %d/%d задач за %.1fс — %.1f запросов/мин'
                % (metrics['tasks_done'], metrics['tasks_total'],
                   metrics['wall_seconds'], metrics['requests_per_min']))
            self.stdout.write(
                '  429: %d/%d (%.2f%%), обрывов: %d, фатальных: %d'
                % (metrics['rate_limited'], metrics['attempts_total'],
                   metrics['rate_limited_pct'], metrics['connection_drops'],
                   metrics['fatal']))
            self.stdout.write(
                '  задержка: средняя %.2fс, худшая %.2fс'
                % (metrics['latency_avg'], metrics['latency_worst']))
            self.stdout.write('  потрачено: $%.5f%s' % (
                metrics['spent'],
                ' (остановлено потолком)' if metrics['stopped_by_cap'] else ''))
            if metrics['errors']:
                self.stdout.write('  ⚠️ %d задач упали без восстановления' % metrics['errors'])

        self.stdout.write('')
        self.stdout.write('=== ИТОГ: доля 429 по режимам (порог для выбора — < 1%) ===')
        for m in results:
            verdict = 'OK' if m['rate_limited_pct'] < 1.0 else 'ВЫШЕ ПОРОГА'
            self.stdout.write('  %3d потоков: %.2f%% 429 — %s' % (
                m['workers'], m['rate_limited_pct'], verdict))
