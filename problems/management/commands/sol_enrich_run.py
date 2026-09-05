# -*- coding: utf-8 -*-
"""sol_enrich_run — ЗАМЕР: те же 300 задач тем же промптом на gpt-5.6-sol.

Сессия 03.09.2026. Задача одна — ИЗМЕРИТЬ, а не улучшить. Ядра промпта,
схема полей, таксономия, словарь и набор проверок берутся как есть; всё,
что отличается от боевого прогона GLM-5.3-Flash, перечислено здесь и
только здесь:

1. модель `gpt-5.6-sol` вместо `glm-5.3-flash`, поставщик
   `OpenAIProvider` вместо `GLMProvider` (оба — слой `problems/ai/`);
2. уровень рассуждения `medium` — прямое указание владельца. У GLM было
   `low` (минимум доступного). Это НЕ равные условия, и вывод обязан
   называть эту разницу вслух;
3. строгая схема (`json_schema`, `strict: true`) — у OpenAI она есть, у
   Z.AI её нет вовсе. ⚠️ Наши собственные проверки при этом те же самые
   (`validate_call1_full` / `validate_call2_full` из `pilot_enrich_v2`):
   сравнение идёт по одинаковым правилам, а не «у одного схема, у другого
   нет». Доля не прошедших проверку считается для обеих моделей;
4. 10 одновременных запросов вместо 50 (лимиты OpenAI другие), со
   снижением до 5 на первом же 429 — см. `AdaptiveGate`;
5. свои файлы: `sol300_raw.jsonl`, `sol300_parsed.jsonl`,
   `sol300_metrics.json`. Файлы GLM не открываются на запись НИКОГДА.

Выборка НЕ строится заново: id читаются из готового манифеста боевого
прогона GLM (`--sample-manifest`, по умолчанию — манифест соседней папки,
ТОЛЬКО НА ЧТЕНИЕ). Своя выборка сделала бы сравнение бессмысленным.

⚠️ В базу НИЧЕГО не пишет — ни поля `Problem`, ни миграции. Свип-детектор
защищённых полей снимается до и после и печатается числом.

Запуск (реальные деньги, `--max-cost` обязателен):
    manage.py sol_enrich_run --limit 20  --max-cost 2.0   # проба цены
    manage.py sol_enrich_run             --max-cost 16.0  # все 300
"""
import json
import threading
import time
from decimal import Decimal
from pathlib import Path

from django.core.management.base import CommandError
from django.test import override_settings

from problems.ai import providers
from problems.enrich.shortlist import shortlist_for
from problems.enrich.text import problem_full_text
from problems.management.commands import glm_enrich_run as glm
from problems.management.commands import pilot_enrich_v2 as pilot

SOL_MODEL = 'gpt-5.6-sol'
#: (вход, кэшированный вход, выход) за миллион токенов — прайс OpenAI,
#: проверен владельцем по документации и передан заданием сессии.
SOL_PRICES = (4.00, 0.40, 20.00)

#: Старт — 10 одновременных запросов (указание задания). Первый же 429
#: снижает до 5 навсегда: рассуждающая модель на чужих лимитах — не то
#: место, где стоит нащупывать потолок повторными попытками.
WORKERS_DEFAULT = 10
WORKERS_AFTER_429 = 5

REPORT_DIR = Path('reports/enrich_pilot')
RAW_LOG_PATH = REPORT_DIR / 'sol300_raw.jsonl'
PARSED_LOG_PATH = REPORT_DIR / 'sol300_parsed.jsonl'
METRICS_PATH = REPORT_DIR / 'sol300_metrics.json'

#: Манифест выборки боевого прогона GLM. Соседняя рабочая копия, ТОЛЬКО
#: ЧТЕНИЕ: там идёт другая сессия, и писать туда нельзя ничего.
SAMPLE_MANIFEST_DEFAULT = (
    r'C:\Users\shipu\qls-models\reports\enrich_pilot\run300_sample_ids.json')

SOL_VARIANT = {
    'label': 'gpt-5.6-sol (уровень рассуждения medium — указание владельца)',
    'call1_model': SOL_MODEL, 'call1_effort': 'medium',
    'call2_model': SOL_MODEL, 'call2_effort': 'medium',
    'concepts': True,
}

PROGRESS_EVERY = 50


class AdaptiveGate(object):
    """Ограничитель одновременности, который умеет ОДИН раз ужаться.

    `run_variant_concurrent` создаёт пул фиксированного размера, и менять
    его на лету нельзя. Поэтому пул поднимается на `start` воркеров, а
    реально одновременных запросов не больше, чем разрешает этот гейт:
    после первого 429 он навсегда забирает у себя часть пропусков
    (`start - floor`) и дальше держит `floor`.

    Само ожидание после 429 (2, 4, 8, 16 секунд) уже делает
    `pilot.make_openai_complete_fn` — здесь только ширина потока.
    """

    def __init__(self, start, floor):
        self.start = start
        self.floor = floor
        self._sem = threading.Semaphore(start)
        self._lock = threading.Lock()
        self.narrowed = False
        self.rate_limit_hits = 0

    def note_rate_limit(self):
        with self._lock:
            self.rate_limit_hits += 1
            if self.narrowed:
                return False
            self.narrowed = True
        # Пропуски забираются НЕ под локом: acquire блокирующий, и держать
        # на нём общий лок значило бы остановить всех остальных.
        for _ in range(max(0, self.start - self.floor)):
            self._sem.acquire()
        return True

    def width(self):
        return self.floor if self.narrowed else self.start

    def __enter__(self):
        self._sem.acquire()
        return self

    def __exit__(self, *exc):
        self._sem.release()
        return False


def make_sol_complete_fn(gate):
    """`pilot.make_openai_complete_fn` плюс гейт одновременности.

    Повторы на 429/обрыве сети — те же, что у боевого пути (внутри
    `pilot.make_openai_complete_fn`): менять их значило бы мерить не
    модель, а свою обвязку.
    """
    inner = pilot.make_openai_complete_fn()

    def complete_fn(model, blocks, user_text, schema, effort, images=None):
        with gate:
            try:
                return inner(model, blocks, user_text, schema, effort,
                             images=images)
            except providers.ProviderError as error:
                if error.kind == 'limit':
                    gate.note_rate_limit()
                raise

    return complete_fn


def usage_totals_from_rows(rows, model):
    """То же, что `glm_enrich_run.usage_totals_from_rows`, но цена берётся
    по переданной модели, а не по зашитой в модуль GLM."""
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
                cost += pilot.real_call_cost(model, reply)
    totals['cost_usd'] = str(cost)
    return totals


class Command(glm.Command):
    """Наследование от боевой команды GLM — намеренное: `_load_problems`
    и `_rows_from_log` обязаны быть ТЕМИ ЖЕ, иначе разойдутся не модели, а
    способы разбора журнала. Переопределяется только то, что отличается."""

    help = 'Замер: те же 300 задач тем же промптом на gpt-5.6-sol.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=None,
                            help='Взять первые N id манифеста (проба цены). '
                                 'Порядок манифеста уже перемешан зерном — '
                                 'любой начальный кусок представителен.')
        parser.add_argument('--max-cost', type=float, required=True)
        parser.add_argument('--workers', type=int, default=WORKERS_DEFAULT)
        parser.add_argument('--run-id', type=str, default=None)
        parser.add_argument('--sample-manifest', type=str,
                            default=SAMPLE_MANIFEST_DEFAULT,
                            help='Манифест выборки боевого прогона GLM. '
                                 'ТОЛЬКО ЧТЕНИЕ.')
        parser.add_argument('--parsed-out', type=str, default=None)
        parser.add_argument('--metrics-out', type=str, default=None)
        parser.add_argument('--raw-out', type=str, default=None)

    # --- прогон ---------------------------------------------------------

    def handle(self, *args, **options):
        run_id = options['run_id'] or ('sol-enrich-%d' % int(time.time()))
        raw_path = Path(options['raw_out'] or RAW_LOG_PATH)
        parsed_out = Path(options['parsed_out'] or PARSED_LOG_PATH)
        metrics_out = Path(options['metrics_out'] or METRICS_PATH)

        manifest_path = Path(options['sample_manifest'])
        if not manifest_path.exists():
            raise CommandError('Манифест выборки не найден: %s' % manifest_path)
        with open(manifest_path, encoding='utf-8') as fh:
            manifest = json.load(fh)
        problem_ids = list(manifest['ids'])
        if options['limit'] is not None:
            problem_ids = problem_ids[:options['limit']]
        if not problem_ids:
            raise CommandError('Выборка пуста.')

        known = set(glm.battle_queryset()
                    .filter(id__in=problem_ids).values_list('id', flat=True))
        missing = [pid for pid in problem_ids if pid not in known]
        if missing:
            raise CommandError(
                'В этой базе нет %d id выборки (%s...) — сравнивать нечего, '
                'нужна та же копия базы.' % (len(missing), missing[:10]))

        total_ids = len(problem_ids)
        self.stdout.write('=== ЗАМЕР gpt-5.6-sol: %d задач, run_id=%s ==='
                          % (total_ids, run_id))
        self.stdout.write('выборка: %s (seed=%s, всего в манифесте %d)'
                          % (manifest_path, manifest.get('seed'),
                             len(manifest['ids'])))
        self.stdout.write('уровень рассуждения: %s (у GLM было %s), '
                          'строгая схема: да, max-cost=$%.2f'
                          % (SOL_VARIANT['call1_effort'], 'low',
                             options['max_cost']))

        prompt_version = pilot.prompt_fingerprint(SOL_VARIANT['concepts'])
        self.stdout.write('версия промпта (отпечаток обоих ядер): %s'
                          % prompt_version)

        gate = AdaptiveGate(options['workers'], WORKERS_AFTER_429)
        complete_fn = make_sol_complete_fn(gate)

        # ⚠️ АВТОСТОПА ПО БРАКУ ЗДЕСЬ НЕТ, в отличие от боевого прогона
        # GLM. Причина: это замер, и сравнение требует ВСЕ 300 задач — с
        # прогона, оборванного на 210-й, таблицу по полям не построить.
        # Деньги огорожены `--max-cost`; доля брака считается тем же
        # трекером и печатается каждые 50 задач, чтобы срыв был виден
        # сразу, а решение остановиться принял человек.

        processed_count = {'n': 0}
        count_lock = threading.Lock()
        start_time = time.monotonic()
        tracker = glm.RunQualityTracker()

        # Прогон в базу не пишет вовсе — ожидание ровно 0 расхождений, и
        # это показывается числом, а не утверждается.
        sweep_before = glm.protected_fields_digest(problem_ids)

        def on_progress(problem_id, spent_now):
            with count_lock:
                processed_count['n'] += 1
                n = processed_count['n']
            if n % PROGRESS_EVERY:
                return
            elapsed = time.monotonic() - start_time
            rate = n / elapsed * 60 if elapsed else 0.0
            remaining = todo_total - n
            eta_min = remaining / rate if rate else float('inf')
            defect_pct, retry_pct, soft_pct = tracker.pcts()
            per_task = Decimal(str(spent_now)) / n if n else Decimal('0')
            self.stdout.write(
                '  [%d/%d] брак %.1f%%, повторы %.1f%%, мягкие %.1f%%, '
                'потрачено $%.4f ($%.4f/задача, прогноз на %d: $%.2f), '
                '%.1f задач/мин, осталось ~%.0f мин, потоков %d'
                % (n, todo_total, defect_pct, retry_pct, soft_pct,
                   spent_now, per_task, total_ids, per_task * total_ids,
                   rate, eta_min, gate.width()))
            self.stdout.flush()

        done_ids = pilot.done_problem_ids_from_log(
            str(raw_path), prompt_version, SOL_VARIANT)
        todo_ids = [pid for pid in problem_ids if pid not in done_ids]
        todo_total = len(todo_ids)
        skipped = total_ids - todo_total
        self.stdout.write('уже в журнале (платить заново не нужно): %d, '
                          'к обработке: %d' % (skipped, todo_total))

        spent = Decimal('0')
        stopped = False
        errors = []
        processed_now = 0

        # ⚠️ AI_PRICES оборачивает и прогон, и подсчёт метрик ниже
        # (`real_call_cost` читает ту же настройку) — ловушка уже описана
        # в `glm_enrich_run`: контекст, закрытый до метрик, роняет команду
        # после того, как деньги потрачены.
        with override_settings(AI_PRICES={SOL_MODEL: SOL_PRICES}):
            try:
                if todo_total:
                    problems, _by_id = self._load_problems(todo_ids)
                    shortlists = {
                        p.id: shortlist_for(
                            problem_full_text(p.statement, p.parts.all()))
                        for p in problems}
                    rows, spent, stopped, _s, errors = (
                        pilot.resumable_run_variant_concurrent(
                            problems, SOL_VARIANT, complete_fn, shortlists,
                            str(raw_path), run_id, prompt_version,
                            options['workers'], max_cost=options['max_cost'],
                            on_progress=on_progress,
                            extra_on_row=tracker.record, done_ids=set()))
                    processed_now = len(rows)
                    del problems, _by_id, shortlists, rows
            except KeyboardInterrupt:
                self.stdout.write('')
                self.stdout.write('⚠️ ОСТАНОВЛЕНО ПО Ctrl+C. Журнал %s уже '
                                  'содержит всё оплаченное — повторный запуск '
                                  'продолжит с места остановки.' % raw_path)
                return

            self.stdout.write('')
            self.stdout.write('обработано сейчас: %d, пропущено (уже в '
                              'журнале): %d' % (processed_now, skipped))
            self.stdout.write('потрачено: $%.4f%s' % (
                spent, ' (остановлено потолком)' if stopped else ''))
            self.stdout.write('одновременных запросов фактически: %d%s '
                              '(429 поймано: %d)'
                              % (gate.width(),
                                 ' — снижено с %d после 429' % gate.start
                                 if gate.narrowed else ' (снижения не было)',
                                 gate.rate_limit_hits))
            if errors:
                self.stdout.write('⚠️ %d задач упали без восстановления: %s'
                                  % (len(errors), [pid for pid, _ in errors][:20]))
            defect_pct, retry_pct, soft_pct = tracker.pcts()
            self.stdout.write('в этом запуске: брак %.1f%%, повторы %.1f%%, '
                              'мягкие %.1f%%' % (defect_pct, retry_pct, soft_pct))

            sweep = glm.sweep_report(sweep_before,
                                     glm.protected_fields_digest(problem_ids))
            parsed_all, usage_totals = self._collect_parsed_sol(
                problem_ids, prompt_version, raw_path, parsed_out)
            metrics = glm.build_metrics(parsed_all, usage_totals, sweep=sweep)
            metrics['model'] = SOL_MODEL
            metrics['effort'] = SOL_VARIANT['call1_effort']
            metrics['prompt_version'] = prompt_version
            metrics['workers_final'] = gate.width()
            metrics['rate_limit_hits'] = gate.rate_limit_hits

        metrics_out.parent.mkdir(parents=True, exist_ok=True)
        with open(metrics_out, 'w', encoding='utf-8') as fh:
            json.dump(metrics, fh, ensure_ascii=False, indent=2, default=str)

        self._print_summary(metrics, usage_totals, metrics_out, raw_path,
                            parsed_out, total_ids)

    def _print_summary(self, metrics, usage_totals, metrics_out, raw_path,
                       parsed_out, total_ids):
        u = usage_totals
        n = metrics['total_processed'] or 1
        self.stdout.write('')
        self.stdout.write('=== СВОДКА (%s) ===' % metrics_out)
        self.stdout.write('всего в журнале для этой выборки: %d, брак: %d (%.1f%%)'
                          % (metrics['total_processed'], metrics['defects'],
                             metrics['defect_pct']))
        self.stdout.write('повторов: %d задач (%.1f%%)'
                          % (metrics['retried_rows'], metrics['retried_pct']))
        self.stdout.write('свип-детектор (защищённые поля): проверено %d, '
                          'расхождений %d'
                          % (metrics['sweep_detector']['checked'],
                             metrics['sweep_detector']['changed']))
        self.stdout.write('задач с растром / отправлено с изображением: %d / %d '
                          '(картинок всего %d)'
                          % (metrics['problems_with_raster'],
                             metrics['problems_image_sent'],
                             metrics['images_sent_total']))
        self.stdout.write('')
        self.stdout.write('--- токены на задачу (обе фазы вызова вместе) ---')
        self.stdout.write('вход свежий: %.0f, из кэша: %.0f (доля кэша %.1f%%)'
                          % (u['input_tokens'] / n, u['cache_read_tokens'] / n,
                             u['cache_read_tokens'] * 100.0
                             / max(1, u['input_tokens'] + u['cache_read_tokens'])))
        self.stdout.write('выход всего: %.0f, из них рассуждение: %.0f'
                          % (u['output_tokens'] / n, u['reasoning_tokens'] / n))
        cost = Decimal(u['cost_usd'])
        self.stdout.write('цена по факту usage: $%s на %d задач '
                          '($%.5f на задачу)'
                          % (cost, metrics['total_processed'],
                             cost / n))
        self.stdout.write('ПЕРЕСЧЁТ на %d задач: $%.2f'
                          % (total_ids, cost / n * total_ids))
        self.stdout.write('журналы: %s, %s' % (raw_path, parsed_out))

    def _collect_parsed_sol(self, problem_ids, prompt_version, raw_path,
                            parsed_out):
        """`_collect_parsed` боевой команды, но по журналу sol и одним
        куском: 300 задач в память помещаются, дробление на куски здесь
        было бы усложнением без причины."""
        wanted = set(problem_ids)
        entries = [e for e in pilot.iter_raw_log(str(raw_path))
                   if e.get('problem_id') in wanted]
        in_log = {e['problem_id'] for e in entries}
        chunk_ids = [pid for pid in problem_ids if pid in in_log]
        if not chunk_ids:
            glm.write_parsed_rows(parsed_out, [])
            return [], usage_totals_from_rows([], SOL_MODEL)

        problems, by_id = self._load_problems(chunk_ids)
        shortlists = {
            p.id: shortlist_for(problem_full_text(p.statement, p.parts.all()))
            for p in problems}
        rows = self._rows_from_log(entries, chunk_ids, SOL_VARIANT,
                                   prompt_version, shortlists, by_id)
        usage_totals = usage_totals_from_rows(rows, SOL_MODEL)
        parsed = glm.parsed_rows_for(rows, by_id)
        glm.write_parsed_rows(parsed_out, parsed)
        return parsed, usage_totals
