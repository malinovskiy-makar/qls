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
- Фаза 5: 300 задач — КОНТРОЛЬНАЯ ТОЧКА. НЕ «первые 300 по id» (решение
  02.09.2026: id 1-300 оказались целиком легаси без единой картинки —
  images_sent_total=0, tikz_replaced_total=0 на прошлой попытке) — Фаза C
  заменила это на стратифицированную случайную выборку с гарантиями на
  визуальный пласт, см. `stratified_checkpoint_sample()`. Список id
  сохраняется в `SAMPLE_MANIFEST_PATH` ДО первого обращения к API и
  переиспользуется при повторном запуске. Эта команда сама себя не
  запускает на весь корпус — `--limit` решает человек, и для этой сессии
  это ТОЛЬКО 300.

⚠️ В базу НИЧЕГО не пишет. Ни `topic_candidate`, ни `title`, ни любое
другое поле `Problem` — только файлы. Установка в банк — отдельная сессия
после приёмки владельцем (§ Шаг 8 API_RUN_MASTER).

⚠️ Состав: все задачи, кроме пяти служебных фикстур рендерера
(`Source.name == 'Служебное: фикстуры рендерера (не публиковать)'`).
Дубли включены — решение владельца.

Запуск (реальные деньги, `--max-cost` обязателен):
    manage.py glm_enrich_run --limit 300 --max-cost 3.0 --workers 50
"""
import hashlib
import json
import random
import re
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
from problems.enrich.text import (RASTER_CALL1_SOURCE_FIELDS,
                                  images_for_call1, looks_like_tikz,
                                  problem_full_text, with_figure_note,
                                  with_tikz_sources)
from problems.management.commands import pilot_enrich_v2 as pilot
from problems.models import (Problem, ProblemFigure, ProblemPart,
                             SourceReference)

GLM_MODEL = 'glm-5.3-flash'
GLM_PRICES_PROMO = (0.075, 0.015, 0.25)  # скидка 50% до 24:00 09.09.2026 (UTC+8)

# Выбрано разгонной пробой 02.09.2026 (glm_ramp_probe): 0% отказов 429 на
# всех уровнях, 50 — разрешённый максимум Z.AI для GLM-5.3-Flash (§3.6).
WORKERS_DEFAULT = 50

# ⚠️ РЕШЕНИЕ ВЛАДЕЛЬЦА 02.09.2026 (четвёртая пересъёмка): автостоп считает
# ФИНАЛЬНЫЙ БРАК — долю задач, которые ПОСЛЕ повтора всё равно ушли в брак.
# Прежний показатель («доля задач, потребовавших повтора») качество не
# измеряет: он одинаково срабатывает и когда модель выдаёт мусор, и когда
# модель на трудной задаче ошибается один раз, а со второго попадает — нас
# интересует только первое. Доля повторов — это про ДЕНЬГИ, а деньги
# огорожены `--max-cost`: считаем и печатаем, но прогон по ней не
# останавливаем.
FINAL_DEFECT_STOP_PCT = 5.0
# ⚠️ 200, А НЕ 20. Порог 5% сам по себе не меняется (это прямой запрет
# задания), но решение о ПРЕВЫШЕНИИ порога нельзя принимать по двадцати
# задачам: при пороге 5% две неудачи подряд из двадцати читаются как 10%
# и останавливают прогон на шуме. Замер по уже оплаченному журналу
# (142 задачи чек-поинта, пересчёт по правилам этой сессии) даёт брак
# 2,1% — при такой доле скользящая проверка с min_sample=20 ложно
# срабатывала бы примерно на каждом десятом прогоне. На 200 задачах
# честный брак 8% виден почти наверняка (в среднем 16 против порога 10),
# а ложное срабатывание при 2,1% — меньше процента; цена такой задержки
# на боевом прогоне — около $0,30 из $70.
FINAL_DEFECT_MIN_SAMPLE = 200
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
    упорядоченные по id — детерминированный полный корпус боевого прогона.
    Проверка `--ids` идёт по нему; сама выборка контрольной точки — Фаза C,
    см. `stratified_checkpoint_sample()` ниже (id 1-300 по возрастанию
    оказались целиком легаси без единой картинки — решение владельца
    02.09.2026 заменило «первые N» на стратифицированную выборку)."""
    return (Problem.objects
           .exclude(source_references__source__name=SERVICE_FIXTURE_SOURCE)
           .distinct().order_by('id'))


# ---------------------------------------------------------------------------
# Фаза C (боевой прогон 02.09.2026): контрольная точка — стратифицированная
# случайная выборка по всему корпусу, не «первые N по id». Гарантии на
# визуальный пласт нужны буквально: на прошлой контрольной точке (id 1-300)
# путь картинок и TikZ не проверился НИ РАЗУ — images_sent_total=0,
# tikz_replaced_total=0.
# ---------------------------------------------------------------------------

CHECKPOINT_SEED = 20260902
MIN_TIKZ = 10          # в банке всего 7 настоящих — берём все, что есть
MIN_RASTER_IMAGES = 40
MIN_SOLUTION_IMAGES = 15
SAMPLE_MANIFEST_PATH = REPORT_DIR / 'run300_sample_ids.json'

#: Размер контрольной точки. `--limit` БОЛЬШЕ этого числа означает боевой
#: прогон по всему корпусу — своя выборка, свой манифест (см.
#: `Command._battle_sample`), чек-поинт не затирается.
CHECKPOINT_LIMIT = 300
BATTLE_MANIFEST_PATH = REPORT_DIR / 'run_full_sample_ids.json'

#: Сколько задач держится в памяти одновременно. Весь корпус сразу не
#: помещается: 41 302 задачи это 338 МБ байтов изображений плюс 38 МБ
#: текста плюс объекты Django, а свободной памяти на машине владельца
#: было полтора гигабайта.
CHUNK_SIZE_DEFAULT = 2000

#: Сколько id за раз уходит в `filter(id__in=[...])`. Больше — риск
#: «too many SQL variables» у SQLite.
_SQL_IN_CHUNK = 900


def _proportional_by_source(pool_ids, remaining_slots, rng):
    """Распределяет `remaining_slots` id из `pool_ids` пропорционально по
    источнику (`SourceReference.source.name`; задача без источника или с
    несколькими — берётся по ПЕРВОЙ найденной ссылке, простое приближение,
    не точный учёт). Округление — методом наибольшего остатка, чтобы сумма
    точно совпала с `remaining_slots`, а не «примерно»."""
    if remaining_slots <= 0 or not pool_ids:
        return [], {}

    pool_set = set(pool_ids)
    by_source = {}
    seen = set()
    # ⚠️ НЕ `filter(problem_id__in=pool_set)` — на полном корпусе pool_set
    # доходит до ~41 тысячи id, а SQLite падает с «too many SQL variables»
    # на IN-списке такого размера. Таблица SourceReference сама по себе не
    # огромна — читаем её целиком одним запросом и фильтруем в Python.
    for problem_id, source_name in (
            SourceReference.objects.order_by('id')
            .values_list('problem_id', 'source__name')):
        if problem_id not in pool_set or problem_id in seen:
            continue
        seen.add(problem_id)
        by_source.setdefault(source_name or 'без источника', []).append(problem_id)
    orphans = pool_set - seen
    if orphans:
        by_source.setdefault('без источника', []).extend(sorted(orphans))

    total = sum(len(v) for v in by_source.values())
    if total == 0:
        return [], {}

    raw_shares = {name: remaining_slots * len(ids) / total
                 for name, ids in by_source.items()}
    base = {name: min(int(share), len(by_source[name]))
           for name, share in raw_shares.items()}
    assigned = sum(base.values())
    remainder = remaining_slots - assigned
    # наибольший остаток первым — пока есть что распределять и есть кому.
    order = sorted(by_source, key=lambda n: -(raw_shares[n] - base[n]))
    i = 0
    while remainder > 0 and any(base[n] < len(by_source[n]) for n in by_source):
        name = order[i % len(order)]
        if base[name] < len(by_source[name]):
            base[name] += 1
            remainder -= 1
        i += 1

    chosen = []
    counts = {}
    for name, ids in by_source.items():
        take = base.get(name, 0)
        if take:
            picked = sorted(rng.sample(ids, take))
            chosen.extend(picked)
            counts[name] = take
    return chosen, counts


def stratified_checkpoint_sample(limit=300, seed=CHECKPOINT_SEED):
    """Контрольная точка Фазы 5 — id ЗАРАНЕЕ, до единого обращения к API
    (список сохраняется в `SAMPLE_MANIFEST_PATH` вызывающим кодом,
    чтобы повторный запуск с тем же журналом резюмировался на тех же id).

    Гарантии, в порядке резервирования (каждая следующая не трогает уже
    занятые id из предыдущей):
    1. ВСЕ настоящие TikZ (`looks_like_tikz`) — их 7 в банке, меньше
       `MIN_TIKZ`, поэтому «минимум 10» на деле значит «все, что есть».
    2. `MIN_RASTER_IMAGES` растровых картинок УСЛОВИЯ
       (`source_field in ('import', 'statement')`).
    3. `MIN_SOLUTION_IMAGES` картинок у РЕШЕНИЯ (`source_field='solution'`)
       — иначе кодовая половина «Графического решения» снова не
       проверится ни разу.
    4. Остаток — пропорционально по источнику.

    Возвращает `(ids, report_lines)` — `report_lines` печатается владельцу
    целиком: сколько по каждому источнику, сколько с картинкой, сколько с
    TikZ, сколько с картинкой у решения.
    """
    rng = random.Random(seed)
    allowed_ids = set(battle_queryset().values_list('id', flat=True))
    report = []

    # ⚠️ НЕ `filter(problem_id__in=allowed_ids)` — то же самое ограничение
    # SQLite, что и в `_proportional_by_source()`. `ProblemFigure` — таблица
    # в тысячи строк, не в десятки тысяч — читаем целиком, фильтруем в Python.
    figures = [
        (pid, field, tikz_source, img) for pid, field, tikz_source, img in
        ProblemFigure.objects.values_list(
            'problem_id', 'source_field', 'tikz_source', 'image_data')
        if pid in allowed_ids
    ]
    tikz_ids = sorted({pid for pid, _field, tikz_source, _img in figures
                       if looks_like_tikz(tikz_source)})
    raster_condition_ids = sorted({
        pid for pid, field, tikz_source, img in figures
        if field in ('import', 'statement') and img and not looks_like_tikz(tikz_source)
    })
    raster_solution_ids = sorted({
        pid for pid, field, tikz_source, img in figures
        if field == 'solution' and img and not looks_like_tikz(tikz_source)
    })

    chosen = []
    chosen_set = set()

    def reserve(pool, want, label):
        available = [i for i in pool if i not in chosen_set]
        take_n = min(want, len(available))
        picked = sorted(rng.sample(available, take_n)) if take_n else []
        chosen.extend(picked)
        chosen_set.update(picked)
        report.append('%s: нужно >= %d, доступно %d, взято %d'
                      % (label, want, len(available), take_n))
        return picked

    reserve(tikz_ids, len(tikz_ids), 'настоящий TikZ')
    reserve(raster_condition_ids, MIN_RASTER_IMAGES, 'растровая картинка условия')
    reserve(raster_solution_ids, MIN_SOLUTION_IMAGES, 'картинка у решения')

    remaining_slots = max(0, limit - len(chosen))
    pool = sorted(allowed_ids - chosen_set)
    extra, source_counts = _proportional_by_source(pool, remaining_slots, rng)
    chosen.extend(extra)
    chosen_set.update(extra)

    report.append('добор пропорционально по источнику (%d слотов):' % remaining_slots)
    for name, n in sorted(source_counts.items(), key=lambda kv: -kv[1]):
        report.append('  %s: %d' % (name, n))
    report.append('итого в выборке: %d (лимит %d)' % (len(chosen), limit))

    # Фаза 2 задания сессии 02.09.2026 (третья пересъёмка): ДВЕ попытки
    # подряд остановились автостопом на 69/300 без единой картинки/TikZ в
    # обработанных — `sorted(chosen)` в конце ставил визуальный пласт (id
    # ≈ 57000-63000, решение владельца про Фазу C) в хвост 300-списка, а
    # `ThreadPoolExecutor` в `run_variant_concurrent` разбирает очередь
    # СТРОГО в порядке `sample_problems` (`pool.submit` в цикле по списку)
    # — воркеры физически не успевали дойти до конца до срабатывания
    # порога. Перемешиваем ТЕМ ЖЕ `rng` (тот же `seed` — порядок
    # детерминирован и переживает резюмирование по манифесту), чтобы любой
    # начальный кусок выборки был представительным по визуальному пласту.
    rng.shuffle(chosen)

    return chosen, report


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
# Автостоп — по ФИНАЛЬНОМУ БРАКУ (решение владельца 02.09.2026, см. выше).
# Считается по СКОЛЬЗЯЩЕМУ счётчику задач, обработанных С НАЧАЛА ЭТОГО
# ЗАПУСКА (не считая пропущенных резюмированием — те уже прошли проверку в
# прошлый раз). Доля повторов и доля мягких нарушений считаются тем же
# счётчиком, но остановкой НЕ являются — только печатаются.
# ---------------------------------------------------------------------------

class RunQualityTracker(object):
    """Три доли на одном счётчике:

    - `defect_pct()` — задачи, у которых ПОСЛЕ повтора остались жёсткие
      нарушения. Единственное, по чему прогон останавливается.
    - `retry_pct()` — задачи, потребовавшие повтора (жёсткие нарушения на
      первой попытке). Это про деньги, а не про качество.
    - `soft_pct()` — задачи хотя бы с одним мягким нарушением. Повтора за
      них не было вовсе.
    """

    def __init__(self, min_sample=FINAL_DEFECT_MIN_SAMPLE,
                stop_pct=FINAL_DEFECT_STOP_PCT):
        self.lock = threading.Lock()
        self.total = 0
        self.defects = 0
        self.retried = 0
        self.soft = 0
        self.min_sample = min_sample
        self.stop_pct = stop_pct
        self.breached = False

    def record(self, row):
        with self.lock:
            self.total += 1
            if not (row.get('call1_ok') and row.get('call2_ok')):
                self.defects += 1
            if row.get('call1_retried') or row.get('call2_retried'):
                self.retried += 1
            if (row.get('call1_soft_violations')
                    or row.get('call2_soft_violations')):
                self.soft += 1
            if self.total >= self.min_sample:
                if self.defects / self.total * 100 > self.stop_pct:
                    self.breached = True

    def pcts(self):
        """Все три доли ОДНИМ снимком под локом — иначе числа в одной
        печатной строке относились бы к разным моментам прогона.
        Возвращает `(брак%, повторы%, мягкие%)`."""
        with self.lock:
            if not self.total:
                return 0.0, 0.0, 0.0
            return (self.defects / self.total * 100,
                    self.retried / self.total * 100,
                    self.soft / self.total * 100)

    def defect_pct(self):
        return self.pcts()[0]


# ---------------------------------------------------------------------------
# Фаза 3.2: run_parsed.jsonl — по строке на задачу.
# ---------------------------------------------------------------------------

def parsed_row(row, problem):
    """Одна строка `run_parsed.jsonl` — все разобранные поля обоих
    вызовов в готовом для слияния виде, что прошло проверку, брак ли.

    `defect`/`call*_ok`/`call*_retried` считаются ТОЛЬКО по жёстким
    нарушениям (Фаза 1 задания сессии 02.09.2026, вторая пересъёмка) —
    `soft_violations` ниже не портят банк и повтор не вызывают, но
    печатаются для отчёта владельцу (`run_metrics.json`, раздел
    `soft_violations`)."""
    call1 = row.get('call1') or {}
    call2 = row.get('call2') or {}
    is_defect = not (row.get('call1_ok') and row.get('call2_ok'))
    merged_graphical, graphical_source = enrich_text.merge_graphical_solution(
        call1.get('features_1'), problem)
    soft = list(row.get('call1_soft_violations') or []) + \
        list(row.get('call2_soft_violations') or [])
    figures = list(problem.figures.all())
    tikz_figures = [f for f in figures if looks_like_tikz(f.tikz_source or '')]
    has_raster = any(
        f.source_field in RASTER_CALL1_SOURCE_FIELDS and f.image_data
        and not looks_like_tikz(f.tikz_source or '') for f in figures)
    has_tikz = bool(tikz_figures)
    has_tikz_statement = any(
        f.source_field in RASTER_CALL1_SOURCE_FIELDS for f in tikz_figures)
    return {
        'problem_id': row['problem_id'],
        'defect': is_defect,
        'call1_ok': row.get('call1_ok'),
        'call1_retried': row.get('call1_retried'),
        'call1_violations': row.get('call1_violations'),
        'call2_ok': row.get('call2_ok'),
        'call2_retried': row.get('call2_retried'),
        'call2_violations': row.get('call2_violations'),
        'soft_violations': soft,
        # Фаза 1.2: запросы с цифрой, выброшенные из массива вместо повтора
        # всего вызова — ТЕКСТОМ каждого, чтобы владелец видел, что именно
        # модель писала и почему это выброшено.
        'dropped_queries': row.get('dropped_queries') or [],
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
        # ⚠️ Три признака визуального пласта пишутся В СТРОКУ, а не
        # считаются потом по базе: на боевом прогоне метрики собираются
        # кусками по 2000 задач, и держать 41 тысячу объектов `Problem` с
        # картинками в памяти нельзя (338 МБ одних только байтов
        # изображений при полутора свободных гигабайтах свободной памяти).
        # Строка журнала обязана быть самодостаточной.
        'has_raster': has_raster,
        'has_tikz': has_tikz,
        'has_tikz_in_statement': has_tikz_statement,
    }


def write_parsed_rows(path, parsed, append=False):
    """Дописывает готовые строки `parsed_row` в JSONL. `append=False` —
    файл создаётся заново (первый кусок боевого прогона)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a' if append else 'w', encoding='utf-8') as fh:
        for row in parsed:
            fh.write(json.dumps(row, ensure_ascii=False))
            fh.write('\n')


def parsed_rows_for(rows, problems_by_id):
    return [parsed_row(row, problems_by_id[row['problem_id']])
            for row in rows if row['problem_id'] in problems_by_id]


# ---------------------------------------------------------------------------
# Фаза 3.3: run_metrics.json — сводка.
# ---------------------------------------------------------------------------

def build_metrics(parsed, usage_totals, sweep=None):
    """Сводка по УЖЕ РАЗОБРАННЫМ строкам (`parsed_row`). База здесь не
    нужна вовсе — всё, что раньше пересчитывалось по `Problem`, лежит в
    самой строке (`has_raster`, `has_tikz`, ...), и метрики боевого
    прогона собираются кусками, не держа корпус в памяти.

    ⚠️ TikZ считается ДВУМЯ числами. §3.4 API_RUN_MASTER: решение не
    подаётся в вызов 1 — значит чертёж, привязанный к РЕШЕНИЮ, туда
    уходить не имеет права, и его отсутствие это работающее правило, а не
    потеря. Сравнивать с «подставлено» можно только «TikZ у условия»:
    замер чек-поинта 02.09.2026 дал 4 задачи с TikZ, из них 2 у условия —
    и ровно 2 подстановки. Задачи с TikZ у решения ловятся кодовой
    половиной «Графического решения» (`merge_graphical_solution`)."""
    n = len(parsed)
    defects = [p for p in parsed if p['defect']]
    ok = [p for p in parsed if not p['defect']]

    def dist(field):
        return dict(Counter(p[field] for p in ok if p.get(field)))

    given_lens = [len(p['given']) for p in ok if p.get('given')]
    find_lens = [len(p['find']) for p in ok if p.get('find')]
    tags_counts = [len(p['tags'] or []) for p in ok]
    graphical = Counter(p['graphical_solution_source'] for p in parsed)
    # Фаза B.3: нижняя граница снижена 8 → 5 — сколько всё же осталось
    # ровно с восемью (не сама по себе плохо, просто числовой факт для
    # чтения владельцем на контрольной точке).
    queries_counts = Counter(len(p['search_queries'] or []) for p in ok)

    # Фаза 1 задания сессии 02.09.2026 (вторая пересъёмка): мягкие
    # нарушения не портят банк и не считаются в defect/retried выше, но
    # печатаются отдельным разделом — «принять как есть, записать в
    # журнал» дословно требует владелец. Причина нормализуется без
    # хвостового «(N)», чтобы «econ_concepts меньше 3 (1)» и «(2)»
    # схлопывались в одну строку счётчика.
    soft_reason_re = re.compile(r'\s*\(\d+\)$')
    soft_by_reason = Counter()
    rows_with_soft = 0
    for p in parsed:
        reasons = {soft_reason_re.sub('', v) for v in (p.get('soft_violations') or [])}
        if reasons:
            rows_with_soft += 1
        soft_by_reason.update(reasons)

    # Фаза 1.2: сколько поисковых запросов выброшено (вместо повтора всего
    # вызова) и у скольких задач после выброса осталось меньше пяти.
    dropped_total = sum(len(p.get('dropped_queries') or []) for p in parsed)
    rows_with_dropped = sum(1 for p in parsed if p.get('dropped_queries'))
    rows_under_five = sum(
        1 for p in parsed
        if p.get('search_queries') is not None and len(p['search_queries']) < 5)

    # Фаза 1.1: доля повторов — метрика ДЕНЕГ, не качества. Печатается и
    # пишется в журнал, но остановкой прогона не является (решение
    # владельца 02.09.2026): для остановки есть `defect_pct` выше.
    retried_rows = sum(1 for p in parsed
                       if p['call1_retried'] or p['call2_retried'])
    tikz_total = sum(1 for p in parsed if p.get('has_tikz'))
    tikz_in_statement = sum(1 for p in parsed if p.get('has_tikz_in_statement'))

    return {
        'total_processed': n,
        'defects': len(defects),
        'defect_pct': (len(defects) / n * 100) if n else 0.0,
        'retried_rows': retried_rows,
        'retried_pct': (retried_rows / n * 100) if n else 0.0,
        'retried_call1': sum(1 for p in parsed if p['call1_retried']),
        'retried_call2': sum(1 for p in parsed if p['call2_retried']),
        'dropped_queries_total': dropped_total,
        'rows_with_dropped_queries': rows_with_dropped,
        'rows_with_dropped_queries_pct': (
            rows_with_dropped / n * 100) if n else 0.0,
        'rows_under_5_queries': rows_under_five,
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
        # ⚠️ Числа ЗАДАЧ, а не картинок. Инвариант владельца звучит как
        # «задач с растром / отправлено с изображением — числа равны»:
        # `images_sent_total` (70 картинок) на него не отвечает, потому что
        # у одной задачи картинок бывает несколько. Знаменатель берётся из
        # БАЗЫ (есть растровая картинка условия), числитель — из журнала
        # (картинка реально ушла в вызов 1); расхождение означает, что
        # `images_for_call1` что-то отбросил (битые байты, конверсия).
        'problems_with_raster': sum(1 for p in parsed if p.get('has_raster')),
        'problems_image_sent': sum(1 for p in parsed if p['images_sent']),
        'problems_with_tikz': tikz_total,
        'problems_with_tikz_in_statement': tikz_in_statement,
        'problems_tikz_replaced': sum(
            1 for p in parsed if (p['tikz'] or {}).get('replaced')),
        'graphical_solution': {
            'model': graphical.get('model', 0), 'code': graphical.get('code', 0),
            'both': graphical.get('both', 0), 'none': graphical.get('none', 0),
            'total': graphical.get('model', 0) + graphical.get('code', 0) + graphical.get('both', 0),
        },
        'search_queries_count_distribution': dict(queries_counts),
        'search_queries_exactly_8_pct': (
            queries_counts.get(8, 0) / len(ok) * 100 if ok else 0.0),
        'soft_violations': {
            'rows_with_soft': rows_with_soft,
            'rows_with_soft_pct': (rows_with_soft / n * 100) if n else 0.0,
            'by_reason': dict(soft_by_reason),
            'by_reason_pct': {reason: (count / n * 100 if n else 0.0)
                             for reason, count in soft_by_reason.items()},
        },
        'usage_totals': usage_totals,
        # §12 правило 2 / §11 «Свип-детектор»: расхождения в защищённых
        # полях (statement/answer/solution/ProblemPart.statement) между
        # снимком ДО прогона и снимком ПОСЛЕ. Прогон в базу не пишет
        # вовсе, поэтому ожидание — ровно 0; ненулевое число означает,
        # что нарушено P0, а не «немного разошлось».
        'sweep_detector': sweep if sweep is not None else {
            'checked': 0, 'changed': 0, 'changed_ids': []},
    }


def protected_fields_digest(problem_ids):
    """Отпечаток ЗАЩИЩЁННЫХ полей (`statement`, `answer`, `solution`,
    `ProblemPart.statement`) — `{id задачи: md5}`. Снимается ДО прогона и
    ПОСЛЕ, разница и есть свип-детектор §12 правило 2.

    ⚠️ Именно ХЕШ, а не сами тексты: на боевом прогоне это 41 тысяча задач,
    и держать два полных снимка текстов в памяти незачем. Чтение идёт
    `values_list` + `iterator()` — построчно, без загрузки объектов
    `Problem` целиком.
    """
    # ⚠️ Запрос идёт ПОРЦИЯМИ по 900 id: `filter(id__in=[...])` с
    # десятками тысяч значений роняет SQLite («too many SQL variables») —
    # та же ловушка, что уже описана в `_proportional_by_source`.
    ids = list(problem_ids)
    digests = {}
    for start in range(0, len(ids), _SQL_IN_CHUNK):
        batch = ids[start:start + _SQL_IN_CHUNK]
        for pid, statement, answer, solution in (
                Problem.objects.filter(id__in=batch)
                .values_list('id', 'statement', 'answer', 'solution')
                .iterator()):
            h = hashlib.md5()
            for value in (statement, answer, solution):
                h.update((value or '').encode('utf-8'))
                h.update(b'\x00')
            digests[pid] = h
        for pid, part_id, part_statement in (
                ProblemPart.objects.filter(problem_id__in=batch)
                .order_by('problem_id', 'id')
                .values_list('problem_id', 'id', 'statement')
                .iterator()):
            h = digests.get(pid)
            if h is not None:
                h.update(('%d:%s' % (part_id, part_statement or '')).encode('utf-8'))
                h.update(b'\x00')
    return {pid: h.hexdigest() for pid, h in digests.items()}


def sweep_report(before, after):
    """`{'checked': N, 'changed': N, 'changed_ids': [...]}` по двум
    отпечаткам `protected_fields_digest`. Ожидание — `changed == 0`."""
    changed = sorted(pid for pid, digest in before.items()
                     if after.get(pid) != digest)
    return {'checked': len(before), 'changed': len(changed),
            'changed_ids': changed[:50]}


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
                            help='Размер стратифицированной выборки Фазы C '
                                 '(stratified_checkpoint_sample) — НЕ '
                                 '«первые N по id». ФАЗА 5 ЭТОЙ СЕССИИ: '
                                 'обязательно 300.')
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
        parser.add_argument(
            '--chunk', type=int, default=CHUNK_SIZE_DEFAULT,
            help='Сколько задач держать в памяти одновременно. Корпус '
                 'целиком не помещается: 41 тысяча задач это 338 МБ одних '
                 'только байтов изображений плюс тексты и подпункты.')

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
        elif limit is not None and limit > CHECKPOINT_LIMIT:
            # ⚠️ БОЕВОЙ ПРОГОН. `--limit` больше размера контрольной точки
            # означает «весь корпус», и манифест чек-поинта здесь брать
            # НЕЛЬЗЯ: он содержит ровно те 300 задач, и `--limit 50000`
            # молча прогнал бы их же по второму разу вместо корпуса.
            # Своя выборка — свой манифест, чек-поинт не затирается.
            problem_ids = self._battle_sample(limit)
        elif SAMPLE_MANIFEST_PATH.exists():
            # Фаза C: список id сохраняется в файл ДО первого обращения к
            # API — повторный запуск (резюмирование после обрыва, добавка
            # к --max-cost) обязан взять ТУ ЖЕ выборку, а не пересчитать
            # заново со смещённым состоянием случайности.
            with open(SAMPLE_MANIFEST_PATH, encoding='utf-8') as fh:
                manifest = json.load(fh)
            problem_ids = manifest['ids']
            self.stdout.write('=== ВЫБОРКА: манифест уже существует, беру его '
                              '(%s, seed=%s) ===' % (SAMPLE_MANIFEST_PATH, manifest.get('seed')))
        else:
            problem_ids, sample_report = stratified_checkpoint_sample(
                limit=limit or 300, seed=CHECKPOINT_SEED)
            self.stdout.write('=== ВЫБОРКА (стратифицированная, seed=%d) ==='
                              % CHECKPOINT_SEED)
            for line in sample_report:
                self.stdout.write('  ' + line)
            SAMPLE_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(SAMPLE_MANIFEST_PATH, 'w', encoding='utf-8') as fh:
                json.dump({'seed': CHECKPOINT_SEED, 'limit': limit or 300,
                          'ids': problem_ids, 'report': sample_report},
                         fh, ensure_ascii=False, indent=2)
            self.stdout.write('манифест сохранён: %s' % SAMPLE_MANIFEST_PATH)

        if not problem_ids:
            raise CommandError('Выборка пуста.')
        total_ids = len(problem_ids)
        chunk_size = options['chunk']

        self.stdout.write('=== БОЕВОЙ ПРОГОН GLM-5.3-Flash: %d задач, run_id=%s ==='
                          % (total_ids, run_id))
        self.stdout.write('workers=%d, max-cost=$%.4f, кусок=%d задач' % (
            options['workers'], options['max_cost'], chunk_size))

        prompt_version = pilot.prompt_fingerprint(GLM_VARIANT['concepts'])
        complete_fn = make_glm_complete_fn()

        tracker = RunQualityTracker()
        stop_event = threading.Event()
        processed_count = {'n': 0}
        count_lock = threading.Lock()
        start_time = time.monotonic()

        # Свип-детектор (§12 правило 2): отпечаток защищённых полей ДО
        # прогона. Прогон в базу не пишет вовсе — ожидание ровно 0
        # расхождений, и это надо ПОКАЗАТЬ числом, а не утверждать.
        sweep_before = protected_fields_digest(problem_ids)

        def on_progress(problem_id, spent):
            with count_lock:
                processed_count['n'] += 1
                n = processed_count['n']
            if n % CHECKPOINT_EVERY == 0:
                elapsed = time.monotonic() - start_time
                rate = n / elapsed * 60 if elapsed else 0.0
                remaining = todo_total - n
                eta_min = remaining / rate if rate else float('inf')
                defect_pct, retry_pct, soft_pct = tracker.pcts()
                self.stdout.write(
                    '  [%d/%d] брак %.1f%% (порог %.0f%%), повторы %.1f%%, '
                    'мягкие %.1f%%, потрачено $%.4f, %.1f задач/мин, '
                    'прогноз оставшегося: %.0f мин'
                    % (n, todo_total, defect_pct, tracker.stop_pct,
                       retry_pct, soft_pct, spent, rate, eta_min))
                self.stdout.flush()

        def extra_on_row(row):
            tracker.record(row)
            if tracker.breached:
                stop_event.set()

        # ⚠️ Журнал читается ОДИН раз, потоком (`iter_raw_log`), а не на
        # каждый кусок: на 41 тысяче задач в нём 80+ тысяч строк, и
        # двадцать перечитываний стоили бы дороже самого прогона.
        done_ids = pilot.done_problem_ids_from_log(
            str(RAW_LOG_PATH), prompt_version, GLM_VARIANT)
        todo_ids = [pid for pid in problem_ids if pid not in done_ids]
        todo_total = len(todo_ids)
        skipped = total_ids - todo_total
        self.stdout.write('уже в журнале (платить заново не нужно): %d, '
                          'к обработке: %d' % (skipped, todo_total))

        spent = Decimal('0')
        stopped = False
        errors = []
        processed_now = 0

        # ⚠️ AI_PRICES для GLM оборачивает и сам прогон, и подсчёт метрик
        # НИЖЕ (usage_totals_from_rows -> real_call_cost тоже читает эту
        # настройку) — баг боевого пилота 02.09: контекст закрывался ДО
        # метрик, `_model_prices('glm-5.3-flash')` падал с CommandError
        # уже после того, как деньги были потрачены и журнал записан.
        with override_settings(AI_PRICES={GLM_MODEL: GLM_PRICES_PROMO}):
            try:
                for start in range(0, todo_total, chunk_size):
                    chunk_ids = todo_ids[start:start + chunk_size]
                    problems, _by_id = self._load_problems(chunk_ids)
                    shortlists = {
                        p.id: shortlist_for(
                            problem_full_text(p.statement, p.parts.all()))
                        for p in problems}
                    remaining_budget = float(
                        Decimal(str(options['max_cost'])) - spent)
                    if remaining_budget <= 0:
                        stopped = True
                        break
                    rows, chunk_spent, chunk_stopped, _s, chunk_errors = (
                        pilot.resumable_run_variant_concurrent(
                            problems, GLM_VARIANT, complete_fn, shortlists,
                            str(RAW_LOG_PATH), run_id, prompt_version,
                            options['workers'], max_cost=remaining_budget,
                            on_progress=on_progress, stop_event=stop_event,
                            extra_on_row=extra_on_row, done_ids=set()))
                    spent += chunk_spent
                    processed_now += len(rows)
                    errors.extend(chunk_errors)
                    # Куски держатся в памяти по одному: 41 тысяча задач с
                    # картинками сразу не помещается (338 МБ одних байтов
                    # изображений).
                    del problems, _by_id, shortlists, rows
                    if chunk_stopped or stop_event.is_set():
                        stopped = chunk_stopped
                        break
            except KeyboardInterrupt:
                self.stdout.write('')
                self.stdout.write('⚠️ ОСТАНОВЛЕНО ПО Ctrl+C. Журнал %s уже содержит '
                                  'всё оплаченное — повторный запуск с тем же '
                                  '--run-id продолжит с места остановки, платить '
                                  'заново не придётся.' % RAW_LOG_PATH)
                return

            self.stdout.write('')
            self.stdout.write('обработано сейчас: %d, пропущено (уже в журнале): %d'
                              % (processed_now, skipped))
            self.stdout.write('потрачено: $%.4f%s' % (
                spent, ' (остановлено потолком)' if stopped else ''))
            if errors:
                self.stdout.write('⚠️ %d задач упали без восстановления (после сетевых '
                                  'повторов) — не попали ни в результат, ни в брак, '
                                  'нужен отдельный разбор: %s'
                                  % (len(errors), [pid for pid, _ in errors][:20]))
            defect_pct, retry_pct, soft_pct = tracker.pcts()
            self.stdout.write(
                'в этом запуске: брак %.1f%%, повторы %.1f%%, мягкие %.1f%% '
                '(остановка — только по браку, порог %.1f%%)'
                % (defect_pct, retry_pct, soft_pct, tracker.stop_pct))
            if tracker.breached:
                self.stdout.write('')
                # ⚠️ Порог печатается ИЗ ТРЕКЕРА, а не зашитой константой:
                # трекер можно построить с другим порогом, и сообщение
                # обязано называть тот, по которому он реально сработал.
                self.stdout.write(
                    '🔴 СТОП: финальный брак (после повтора) — %.1f%% '
                    '(порог %.1f%%). Прогон остановлен сам, дальше решает '
                    'владелец.' % (defect_pct, tracker.stop_pct))

            # --- Фаза 3.2/3.3 -------------------------------------------
            sweep = sweep_report(sweep_before,
                                 protected_fields_digest(problem_ids))
            parsed_all, usage_totals = self._collect_parsed(
                problem_ids, chunk_size, prompt_version, parsed_out)
            metrics = build_metrics(parsed_all, usage_totals, sweep=sweep)

        metrics_out.parent.mkdir(parents=True, exist_ok=True)
        with open(metrics_out, 'w', encoding='utf-8') as fh:
            json.dump(metrics, fh, ensure_ascii=False, indent=2, default=str)

        self.stdout.write('')
        self.stdout.write('=== СВОДКА (%s) ===' % metrics_out)
        self.stdout.write('всего в журнале для этой выборки: %d, брак: %d (%.1f%%)'
                          % (metrics['total_processed'], metrics['defects'],
                             metrics['defect_pct']))
        self.stdout.write('повторов (метрика ДЕНЕГ, не остановка): %d задач (%.1f%%)'
                          % (metrics['retried_rows'], metrics['retried_pct']))
        self.stdout.write('поисковых запросов выброшено (цифра в запросе): %d '
                          'у %d задач (%.1f%%); осталось меньше 5 запросов: %d'
                          % (metrics['dropped_queries_total'],
                             metrics['rows_with_dropped_queries'],
                             metrics['rows_with_dropped_queries_pct'],
                             metrics['rows_under_5_queries']))
        self.stdout.write('свип-детектор (защищённые поля): проверено %d, '
                          'расхождений %d%s'
                          % (metrics['sweep_detector']['checked'],
                             metrics['sweep_detector']['changed'],
                             (' — id: %s' % metrics['sweep_detector']['changed_ids'])
                             if metrics['sweep_detector']['changed'] else ''))
        self.stdout.write('задач с растром / отправлено с изображением: %d / %d '
                          '(картинок всего %d)'
                          % (metrics['problems_with_raster'],
                             metrics['problems_image_sent'],
                             metrics['images_sent_total']))
        self.stdout.write('задач с настоящим TikZ: %d, из них чертёж У УСЛОВИЯ: '
                          '%d, получили чертёж в вызове 1: %d (у решения '
                          'чертёж не подаётся — §3.4)'
                          % (metrics['problems_with_tikz'],
                             metrics['problems_with_tikz_in_statement'],
                             metrics['problems_tikz_replaced']))
        self.stdout.write('мягкие нарушения (не брак, повтор не делался): %d задач (%.1f%%), '
                          'по причинам: %s'
                          % (metrics['soft_violations']['rows_with_soft'],
                             metrics['soft_violations']['rows_with_soft_pct'],
                             metrics['soft_violations']['by_reason']))
        self.stdout.write('«Графическое решение»: модель %d, код %d, совпало %d, итого %d'
                          % (metrics['graphical_solution']['model'],
                             metrics['graphical_solution']['code'],
                             metrics['graphical_solution']['both'],
                             metrics['graphical_solution']['total']))
        self.stdout.write('search_queries: распределение по числу запросов %s, '
                          'ровно 8 у %.1f%% задач'
                          % (metrics['search_queries_count_distribution'],
                             metrics['search_queries_exactly_8_pct']))
        self.stdout.write('расход по журналу (все попытки): $%s'
                          % usage_totals['cost_usd'])
        self.stdout.write('журналы: %s, %s' % (RAW_LOG_PATH, parsed_out))

    # --- работа кусками -------------------------------------------------

    def _battle_sample(self, limit):
        """Весь корпус `battle_queryset()`, перемешанный тем же зерном, что
        и контрольная точка, и урезанный до `limit`.

        Перемешивание — не украшательство. Урок Фазы C: id идут пластами
        (визуальный пласт лежит в диапазоне 57000-63000), и при обходе по
        возрастанию любой начальный кусок прогона непредставителен —
        автостоп судил бы о качестве корпуса по одному источнику. Порядок
        детерминирован зерном и сохраняется в свой манифест, поэтому
        возобновление берёт ту же выборку в том же порядке."""
        if BATTLE_MANIFEST_PATH.exists():
            with open(BATTLE_MANIFEST_PATH, encoding='utf-8') as fh:
                manifest = json.load(fh)
            self.stdout.write('=== БОЕВАЯ ВЫБОРКА: манифест уже существует, '
                              'беру его (%s, seed=%s, задач %d) ==='
                              % (BATTLE_MANIFEST_PATH, manifest.get('seed'),
                                 len(manifest['ids'])))
            return manifest['ids']
        ids = list(battle_queryset().values_list('id', flat=True))
        random.Random(CHECKPOINT_SEED).shuffle(ids)
        if limit < len(ids):
            ids = ids[:limit]
        BATTLE_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BATTLE_MANIFEST_PATH, 'w', encoding='utf-8') as fh:
            json.dump({'seed': CHECKPOINT_SEED, 'limit': limit, 'ids': ids},
                     fh, ensure_ascii=False)
        self.stdout.write('=== БОЕВАЯ ВЫБОРКА: весь корпус кроме служебных '
                          'фикстур, %d задач, перемешан зерном %d ==='
                          % (len(ids), CHECKPOINT_SEED))
        self.stdout.write('манифест сохранён: %s' % BATTLE_MANIFEST_PATH)
        return ids

    def _load_problems(self, chunk_ids):
        """Задачи одного куска, В ТОМ ЖЕ ПОРЯДКЕ, что и `chunk_ids`."""
        by_id = {p.id: p for p in
                Problem.objects.filter(id__in=list(chunk_ids))
                .prefetch_related('parts', 'figures')}
        return [by_id[pid] for pid in chunk_ids if pid in by_id], by_id

    def _collect_parsed(self, problem_ids, chunk_size, prompt_version,
                        parsed_out):
        """Строки `run_parsed.jsonl` и суммарный расход — КУСКАМИ.

        Журнал перечитывается потоком на каждый кусок (`iter_raw_log`), но
        в памяти остаются только маленькие разобранные строки: держать
        одновременно 80 тысяч сырых ответов И корпус с картинками нельзя."""
        parsed_all = []
        usage_totals = {'input_tokens': 0, 'cache_read_tokens': 0,
                        'cache_write_tokens': 0, 'output_tokens': 0,
                        'reasoning_tokens': 0, 'cost_usd': '0'}
        cost = Decimal('0')
        written = False
        for start in range(0, len(problem_ids), chunk_size):
            chunk_ids = problem_ids[start:start + chunk_size]
            wanted = set(chunk_ids)
            entries = [e for e in pilot.iter_raw_log(str(RAW_LOG_PATH))
                       if e.get('problem_id') in wanted]
            # Задачи, которых в журнале НЕТ (прогон остановился раньше),
            # незачем ни грузить, ни считать им шорт-лист: строки в
            # `run_parsed.jsonl` у них всё равно не будет.
            in_log = {e['problem_id'] for e in entries}
            chunk_ids = [pid for pid in chunk_ids if pid in in_log]
            if not chunk_ids:
                del entries
                continue
            problems, by_id = self._load_problems(chunk_ids)
            shortlists = {
                p.id: shortlist_for(problem_full_text(p.statement, p.parts.all()))
                for p in problems}
            rows = self._rows_from_log(entries, chunk_ids, GLM_VARIANT,
                                       prompt_version, shortlists, by_id)
            chunk_usage = usage_totals_from_rows(rows)
            for key in ('input_tokens', 'cache_read_tokens', 'cache_write_tokens',
                        'output_tokens', 'reasoning_tokens'):
                usage_totals[key] += chunk_usage[key]
            cost += Decimal(chunk_usage['cost_usd'])
            parsed_chunk = parsed_rows_for(rows, by_id)
            # ⚠️ `append` считается по УЖЕ ЗАПИСАННОМУ, а не по номеру
            # куска: первый кусок может целиком отсутствовать в журнале
            # (прогон остановился раньше), и тогда `append=start > 0`
            # дописывал бы в старый файл, не обнулив его.
            write_parsed_rows(parsed_out, parsed_chunk, append=written)
            written = True
            parsed_all.extend(parsed_chunk)
            del entries, problems, by_id, shortlists, rows, parsed_chunk
        if not written:  # в журнале нет ни одной задачи выборки
            write_parsed_rows(parsed_out, [])
        usage_totals['cost_usd'] = str(cost)
        return parsed_all, usage_totals

    def _rows_from_log(self, entries, problem_ids, variant, prompt_version,
                       shortlists, problems_by_id):
        """Восстанавливает `rows`-подобные словари из `run_raw.jsonl` для
        ВСЕЙ запрошенной выборки (не только обработанных в этом запуске —
        нужно для метрик после резюмирования, где часть задач могла быть
        пропущена как уже готовая).

        Собирает ВСЕ попытки каждого вызова (`call1` и, если была,
        `call1_retry1`) в `call1_attempts` — иначе `usage_totals_from_rows`
        недосчитает деньги, потраченные на неудачную первую попытку.
        `ok`/`retried` считаются `validate_call1_full`/`validate_call2_full`
        по ФИНАЛЬНОЙ попытке — тем же способом, каким это решалось вживую.

        ⚠️ `images_sent`/`tikz` — журнал (`run_raw.jsonl`) их НЕ хранит
        (только `raw_response`/`usage`), а `_process_one_problem` считал их
        живьём. Баг живого чек-поинта 02.09.2026 (третья пересъёмка):
        `row.setdefault('images_sent', 0)` тут раньше означало «журнал
        молчит — считаем, что картинок не было», и `run_metrics.json` врал
        нулём даже когда картинки реально ушли в вызов 1 (проверено на 142
        обработанных: 19 задач/29 картинок по факту при заявленных 0).
        Обе величины — ЧИСТАЯ функция текста/`ProblemFigure` задачи, без
        обращения к API, поэтому пересчитываются здесь заново, без
        повторной оплаты."""
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
            # `shortlist_terms` — тот же список, что видела модель в
            # промпте (детерминированная функция текста задачи, Фаза 1,
            # 02.09.2026), нужен для «понятие вне шорт-листа»: без него
            # эта жёсткая проверка молча не переигралась бы при
            # восстановлении метрик из журнала.
            shortlist_terms = shortlists.get(pid) if variant['concepts'] else None
            # Постобработка ТА ЖЕ, что живьём (`_process_one_problem`), и в
            # том же порядке: журнал хранит сырой ответ модели, а не
            # результат разбора, поэтому «выбросить запрос с цифрой» и
            # «срезать приставку Дано:/Найти:» обязан повторить читающий
            # код — иначе метрики, восстановленные из журнала, разошлись
            # бы с тем, что решалось вживую.
            pilot.strip_given_find_prefixes(row.get('call1'))
            row['dropped_queries'] = pilot.drop_digit_search_queries(
                row.get('call2'))
            row['call1_ok'], _ = pilot.validate_call1_full(
                row.get('call1'), variant['concepts'], shortlist_terms=shortlist_terms)
            row['call1_retried'] = len(row['call1_attempts']) > 1
            row['call2_ok'], _ = pilot.validate_call2_full(row.get('call2'))
            row['call2_retried'] = len(row['call2_attempts']) > 1
            row['call1_soft_violations'] = pilot.soft_violations_call1(
                row.get('call1'), variant['concepts'])
            row['call2_soft_violations'] = pilot.soft_violations_call2(row.get('call2'))
            problem = problems_by_id.get(pid)
            if problem is not None:
                text = with_figure_note(
                    problem_full_text(problem.statement, problem.parts.all()),
                    problem.figures.count())
                _, tikz_stats = with_tikz_sources(text, problem.figures.all())
                row['images_sent'] = len(images_for_call1(problem.figures.all()))
                row['tikz'] = tikz_stats
            else:
                row.setdefault('images_sent', 0)
                row.setdefault('tikz', {'replaced': 0, 'truncated': 0})
            rows.append(row)
        return rows
