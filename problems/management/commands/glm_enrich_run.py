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

# ⚠️ Фаза 5 (2026-09-04): два сторожа поверх финального брака — прямые
# детекторы риска Фазы 1 (решение в вызове 1 может утечь в find, а блок
# решения может не доехать до модели). Тот же порог 5% и та же
# минимальная выборка 200 — не поднимать, чтобы «прошло» (прямой запрет
# задания). Проверяются НЕПРЕРЫВНО по накопленному счёту (как и
# финальный брак выше), а не по последним N задачам буквально — «скользящее
# окно» здесь означает «пересчитывается на каждой строке», а не «забывает
# старые данные»; так же устроен уже существующий сторож брака.
FIND_LEAK_STOP_PCT = 5.0
EMPTY_HINTS_STOP_PCT = 5.0
CHECKPOINT_EVERY = 2000

_WORD_RE = re.compile(r'[a-zA-Zа-яА-ЯёЁ0-9]+')
_HAS_DIGIT_RE = re.compile(r'\d')


def _fourgrams(text):
    words = _WORD_RE.findall((text or '').lower())
    if len(words) < 4:
        return set()
    return {tuple(words[i:i + 4]) for i in range(len(words) - 3)}


def find_leaks_solution(find_text, answer_text):
    """Фаза 5 (сторож «утечка решения в find»): True, если `find`
    содержит цифру ИЛИ пересекается с `answer` четырёхграммой (общее
    4-словное окно) — прямой детектор того, ради чего затевалась Фаза 1.2:
    величина, выведенная в решении, не имеет права попасть в `find`.

    Цифра в `find` уже ловится жёстко как нарушение схемы (§12.3,
    `pilot_enrich_v2.validate_call1`) и должна была вызвать повтор раньше
    — эта проверка ловит и её тоже, на случай если строка попала в отчёт
    в обход (рескью Фазы 4.2, ручной разбор старого журнала). Четырёхграмма
    с `answer` — единственная РЕАЛЬНО новая проверка: текстовый пересказ
    ответа без единой цифры цифровым запретом не ловится вовсе."""
    if _HAS_DIGIT_RE.search(find_text or ''):
        return True
    if not answer_text:
        return False
    return bool(_fourgrams(find_text) & _fourgrams(answer_text))

REPORT_DIR = Path('reports/enrich_pilot')
RAW_LOG_PATH = REPORT_DIR / 'run_raw.jsonl'
PARSED_LOG_PATH = REPORT_DIR / 'run_parsed.jsonl'
METRICS_PATH = REPORT_DIR / 'run_metrics.json'
# Задачи, у которых в старом журнале нет вызова 2 (режим --call1-only):
# поимённый список, а не число — их поля заголовка/сложности/типа/подсказок
# останутся пустыми и требуют отдельного прогона.
NO_CALL2_PATH = REPORT_DIR / 'run_call1_only_no_call2.json'
REVIEW_HTML_PATH = REPORT_DIR / 'run300_review.html'

SERVICE_FIXTURE_SOURCE = 'Служебное: фикстуры рендерера (не публиковать)'

#: Фаза 2 (2026-09-04): 'high', а не 'medium' — реальный API Z.AI для
#: GLM-5.3-Flash принимает только `reasoning_effort` ∈ {low, high, max}
#: (подтверждено документацией Z.AI и ошибкой самого API — см. докстринг
#: `GLMProvider.complete`), «средний» уровень физически не существует.
#: 'low' первого прогона был минимумом доступного, не выбором по вкусу;
#: 'high' — решение владельца при разборе этого ограничения (следующий
#: шаг вверх, а не 'max' — дороже без замера пользы).
GLM_VARIANT = {
    'label': 'glm-5.3-flash (высокий уровень рассуждения — medium недоступен API, см. GLMProvider)',
    'call1_model': GLM_MODEL, 'call1_effort': 'high',
    'call2_model': GLM_MODEL, 'call2_effort': 'high',
    'concepts': True,
}


def battle_queryset():
    """Все ГОДНЫЕ задачи, кроме пяти служебных фикстур рендерера (Фаза 4),
    упорядоченные по id — детерминированный полный корпус боевого прогона.
    Проверка `--ids` идёт по нему; сама выборка контрольной точки — Фаза C,
    см. `stratified_checkpoint_sample()` ниже (id 1-300 по возрастанию
    оказались целиком легаси без единой картинки — решение владельца
    02.09.2026 заменило «первые N» на стратифицированную выборку).

    ⚠️ Фаза 4.1 (2026-09-04): `content_status != 'ok'` исключается —
    прошлая сессия скрыла 3 836 задач с битым текстом (`needs_fix`/`junk`)
    и НАЗВАЛА, что этот фильтр здесь отсутствовал, но не чинила. Обогащение
    битого текста даёт битые поля; такие задачи обогащаются отдельным
    маленьким проходом после починки текста, не этим прогоном."""
    return (Problem.objects
           .exclude(source_references__source__name=SERVICE_FIXTURE_SOURCE)
           .filter(content_status=Problem.ContentStatus.OK)
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
    """Три доли на одном счётчике, плюс два сторожа Фазы 5:

    - `defect_pct()` — задачи, у которых ПОСЛЕ повтора остались жёсткие
      нарушения. Останавливает прогон.
    - `retry_pct()` — задачи, потребовавшие повтора (жёсткие нарушения на
      первой попытке). Это про деньги, а не про качество.
    - `soft_pct()` — задачи хотя бы с одним мягким нарушением. Повтора за
      них не было вовсе.
    - утечка решения в `find` (`find_leaks_solution`) — тоже останавливает.
    - пустые подсказки у задач с решением — тоже останавливает; знаменатель
      здесь — задачи С РЕШЕНИЕМ, а не все обработанные (см. `record`).
    """

    def __init__(self, min_sample=FINAL_DEFECT_MIN_SAMPLE,
                stop_pct=FINAL_DEFECT_STOP_PCT, call1_only=False,
                find_leak_stop_pct=FIND_LEAK_STOP_PCT,
                empty_hints_stop_pct=EMPTY_HINTS_STOP_PCT):
        self.lock = threading.Lock()
        self.total = 0
        self.defects = 0
        self.retried = 0
        self.soft = 0
        self.find_leaks = 0
        self.solution_tasks = 0
        self.empty_hints_with_solution = 0
        self.min_sample = min_sample
        self.stop_pct = stop_pct
        self.find_leak_stop_pct = find_leak_stop_pct
        self.empty_hints_stop_pct = empty_hints_stop_pct
        self.breached = False
        self.breach_reason = None
        # ⚠️ В режиме `--call1-only` вызова 2 не было вовсе, и `call2_ok`
        # у строки ОТСУТСТВУЕТ. Без этого флага `not (call1_ok and
        # call2_ok)` считал бы браком КАЖДУЮ задачу (None — ложь),
        # автостоп сработал бы на 200-й и убил перегон корпуса на ровном
        # месте. Судим по тому, что реально делали.
        self.call1_only = call1_only

    def record(self, row):
        with self.lock:
            self.total += 1
            ok = row.get('call1_ok') if self.call1_only else (
                row.get('call1_ok') and row.get('call2_ok'))
            if not ok:
                self.defects += 1
            retried = row.get('call1_retried') if self.call1_only else (
                row.get('call1_retried') or row.get('call2_retried'))
            if retried:
                self.retried += 1
            soft = row.get('call1_soft_violations') if self.call1_only else (
                row.get('call1_soft_violations')
                or row.get('call2_soft_violations'))
            if soft:
                self.soft += 1

            call1 = row.get('call1') or {}
            if find_leaks_solution(call1.get('find'), row.get('answer')):
                self.find_leaks += 1

            # Пустые подсказки — сторож ИМЕЕТ СМЫСЛ только у задач с
            # решением (без решения `hints` легитимно `null`), и в режиме
            # `--call1-only` вызов 2 не делался вовсе — считать нечего.
            if row.get('solution_sent') and not self.call1_only:
                self.solution_tasks += 1
                call2 = row.get('call2') or {}
                if not call2.get('hints'):
                    self.empty_hints_with_solution += 1

            if self.total >= self.min_sample:
                if self.defects / self.total * 100 > self.stop_pct:
                    self.breached = True
                    self.breach_reason = self.breach_reason or (
                        'финальный брак %.1f%% (порог %.1f%%)'
                        % (self.defects / self.total * 100, self.stop_pct))
                if self.find_leaks / self.total * 100 > self.find_leak_stop_pct:
                    self.breached = True
                    self.breach_reason = self.breach_reason or (
                        'утечка решения в find %.1f%% (порог %.1f%%)'
                        % (self.find_leaks / self.total * 100,
                           self.find_leak_stop_pct))
            if self.solution_tasks >= self.min_sample:
                if (self.empty_hints_with_solution / self.solution_tasks * 100
                        > self.empty_hints_stop_pct):
                    self.breached = True
                    self.breach_reason = self.breach_reason or (
                        'пустые подсказки у задач с решением %.1f%% '
                        '(порог %.1f%%)'
                        % (self.empty_hints_with_solution
                           / self.solution_tasks * 100,
                           self.empty_hints_stop_pct))

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

#: Фаза 4.2 (2026-09-04): группы полей, которые подстраховка целиком
#: заменяет старыми значениями — по ОДНОМУ вызову за раз, не построчно
#: (вызов 1 и вызов 2 проверяются и подстраховываются независимо).
CALL1_MERGE_FIELDS = (
    'topic_primary', 'topics_secondary', 'tags', 'given', 'find',
    'econ_concepts', 'concepts_offlist', 'task_nature', 'features_1',
    'topic_confidence',
)
CALL2_MERGE_FIELDS = (
    'search_queries', 'plot', 'hints', 'text_quality', 'text_quality_note',
    'problem_type', 'difficulty', 'difficulty_note', 'answer_consistency',
    'title_candidate',
)


# ---------------------------------------------------------------------------
# Форма полезной нагрузки ответа модели (2026-09-04, разбор падения
# `run2-corpus-20260904`).
#
# Схемы у Z.AI нет вовсе, формат держит только наш код, и модель изредка
# отвечает не объектом: из 37 035 задач боевого прогона шесть финальных
# ответов вызова 2 пришли МАССИВОМ из нескольких кусков (огрызок объекта,
# потом голые списки, потом полный объект). `parsed_row` звал у него
# `.get(...)`, ловил `AttributeError` и ронял сборку результата ЦЕЛИКОМ —
# 37 тысяч оплаченных ответов не собрались из-за шести строк.
#
# Правило простое и без угадывания: словарь — работаем; массив ровно из
# одного словаря — разворачиваем (модель обернула объект) и помечаем
# МЯГКИМ нарушением; что угодно ещё — ответ этого вызова невалиден,
# ЖЁСТКОЕ нарушение и обычная ветка брака/подстраховки. Складывать куски
# многоэлементного массива в один объект мы не пробуем: последний элемент
# часто выглядит полным, но «часто» — это и есть угадывание.
# ---------------------------------------------------------------------------

PAYLOAD_WRAPPED_IN_LIST = 'payload_wrapped_in_list'
PAYLOAD_NOT_OBJECT = 'payload_not_object'
PARSE_CRASH = 'parse_crash'


def normalize_payload(payload):
    """`(словарь_или_None, мягкие_нарушения, жёсткие_нарушения)`.

    `None` (JSON вообще не разобрался, `_safe_json_loads`) — тоже «не
    объект»: валидаторы и раньше считали такой вызов неудачным, метка
    лишь называет причину вслух. Поведение от неё не меняется, меняется
    читаемость отчёта. Функция идемпотентна на словарях, поэтому её
    безопасно звать дважды (журнал + `parsed_row`)."""
    if isinstance(payload, dict):
        return payload, [], []
    if (isinstance(payload, list) and len(payload) == 1
            and isinstance(payload[0], dict)):
        return payload[0], [PAYLOAD_WRAPPED_IN_LIST], []
    return None, [], [PAYLOAD_NOT_OBJECT]


def _normalized_call(row, name):
    """Полезная нагрузка вызова `name` строки `row` плюс пометки формы.

    Пометки могли быть проставлены раньше — `_rows_from_log` нормализует
    ответ ДО валидаторов, иначе развёрнутый из массива объект всё равно
    считался бы браком. Здесь они только подхватываются, а нормализация
    повторяется для строк живого прогона, где её ещё не было."""
    payload, soft, hard = normalize_payload(row.get(name))
    for stored, collected in ((row.get('%s_payload_soft' % name), soft),
                              (row.get('%s_payload_hard' % name), hard)):
        for mark in stored or []:
            if mark not in collected:
                collected.append(mark)
    return payload, soft, hard


def _missing_required_fields(result):
    """Поля, которые НЕ ИМЕЮТ ПРАВА быть пустыми ни при каких легитимных
    обстоятельствах этой конкретной задачи (Фаза 4.2, 2026-09-04) —
    легитимные исключения учтены явно, а не как общий список «может быть
    пустым»:
      - `given`/`find`/`difficulty` легитимно пусты у `не_задача`
        (`task_nature` ИЛИ `problem_type` — тексту вызова 1 могло не
        повезти определить характер, а вызову 2 повезло, и наоборот);
      - `plot`/`hints` легитимно `null`, если решения не было вовсе
        (`solution_sent` — чистый факт из этой же строки, БД не нужна),
        ИЛИ если задача сама по себе `не_задача` (см. выше);
      - `topics_secondary`/`features_1`/`concepts_offlist` НЕ входят
        сюда вовсе — 0 элементов для них легитимно всегда, это не брак.

    Пустой список — «всё на месте». Непустой — ровно то, ради чего
    существует инвариант «доля задач с пустым полем — ноль»."""
    missing = []
    for field in ('topic_primary', 'task_nature', 'problem_type',
                  'text_quality', 'answer_consistency', 'title_candidate'):
        if not result.get(field):
            missing.append(field)
    if not result.get('tags'):
        missing.append('tags')
    if not result.get('search_queries'):
        missing.append('search_queries')
    is_not_a_problem = (result.get('task_nature') == 'не_задача'
                        or result.get('problem_type') == 'не_задача')
    if not is_not_a_problem:
        if not result.get('given'):
            missing.append('given')
        if not result.get('find'):
            missing.append('find')
        if result.get('difficulty') is None:
            missing.append('difficulty')
    if result.get('solution_sent') and not is_not_a_problem:
        if not result.get('plot'):
            missing.append('plot')
        if not result.get('hints'):
            missing.append('hints')
    return missing


def parsed_row(row, problem, fallback_index=None):
    """Одна строка `run_parsed.jsonl` — все разобранные поля обоих
    вызовов в готовом для слияния виде, что прошло проверку, брак ли.

    `defect`/`call*_ok`/`call*_retried` считаются ТОЛЬКО по жёстким
    нарушениям (Фаза 1 задания сессии 02.09.2026, вторая пересъёмка) —
    `soft_violations` ниже не портят банк и повтор не вызывают, но
    печатаются для отчёта владельцу (`run_metrics.json`, раздел
    `soft_violations`)."""
    call1, call1_soft, call1_hard = _normalized_call(row, 'call1')
    call2, call2_soft, call2_hard = _normalized_call(row, 'call2')
    call1 = call1 or {}
    call2 = call2 or {}
    # Ответ не той формы — это брак вызова, даже если валидаторы почему-то
    # сказали «ok»: работать с ним всё равно нечем, и строка обязана уйти
    # по той же ветке подстраховки, что и сломанный JSON.
    call1_ok = bool(row.get('call1_ok')) and not call1_hard
    call2_ok = bool(row.get('call2_ok')) and not call2_hard
    is_defect = not (call1_ok and call2_ok)
    soft = list(row.get('call1_soft_violations') or []) + \
        list(row.get('call2_soft_violations') or []) + \
        call1_soft + call2_soft
    figures = list(problem.figures.all())
    tikz_figures = [f for f in figures if looks_like_tikz(f.tikz_source or '')]
    has_raster = any(
        f.source_field in RASTER_CALL1_SOURCE_FIELDS and f.image_data
        and not looks_like_tikz(f.tikz_source or '') for f in figures)
    has_tikz = bool(tikz_figures)
    has_tikz_statement = any(
        f.source_field in RASTER_CALL1_SOURCE_FIELDS for f in tikz_figures)
    result = {
        'problem_id': row['problem_id'],
        'defect': is_defect,
        'call1_ok': call1_ok,
        'call1_retried': row.get('call1_retried'),
        'call1_violations': list(row.get('call1_violations') or []) + call1_hard,
        'call2_ok': call2_ok,
        'call2_retried': row.get('call2_retried'),
        'call2_violations': list(row.get('call2_violations') or []) + call2_hard,
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
        'solution_sent': row.get('solution_sent', False),
        'solution_tokens': row.get('solution_tokens', 0),
        'solution_truncated': row.get('solution_truncated', False),
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

    # Фаза 4.2 (2026-09-04): «второй прогон не может сделать хуже» — вызов,
    # не прошедший проверку ДАЖЕ ПОСЛЕ ПОВТОРА, берёт свои поля из журнала
    # ПЕРВОГО прогона целиком (не построчно — вызов 1 и вызов 2 независимо).
    # Не трогает `ok`-вызовы: удачный ответ этого прогона всегда новее и
    # актуальнее старого журнала.
    fallback_index = fallback_index or {}
    old = fallback_index.get(row['problem_id'])
    fallback_from_run1 = []
    if not call1_ok and old is not None:
        for field in CALL1_MERGE_FIELDS:
            result[field] = old.get(field)
        fallback_from_run1.append('call1')
    if not call2_ok and old is not None:
        for field in CALL2_MERGE_FIELDS:
            result[field] = old.get(field)
        fallback_from_run1.append('call2')
    result['fallback_from_run1'] = fallback_from_run1
    # Откуда в строке данные — одним словом, чтобы «сколько задач реально
    # обогащены вторым прогоном» считалось без разбора списков. Второй
    # прогон шёл на effort high, с чтением решения и подсказками 3-5;
    # строка, закрытая подстраховкой, ничего этого не содержит.
    result['source'] = (
        'run2' if not fallback_from_run1
        else 'run1_fallback' if len(fallback_from_run1) == 2 else 'mixed')

    # `graphical_solution` считается ПОСЛЕ подстраховки — если вызов 1
    # рескьюнут, `features_1` теперь из старого журнала, и код-признак
    # обязан слиться именно с ним, а не с забракованным свежим ответом.
    merged_graphical, graphical_source = enrich_text.merge_graphical_solution(
        result.get('features_1'), problem)
    result['graphical_solution'] = merged_graphical
    result['graphical_solution_source'] = graphical_source

    result['missing_required_fields'] = _missing_required_fields(result)
    return result


def write_parsed_rows(path, parsed, append=False):
    """Дописывает готовые строки `parsed_row` в JSONL. `append=False` —
    файл создаётся заново (первый кусок боевого прогона)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a' if append else 'w', encoding='utf-8') as fh:
        for row in parsed:
            fh.write(json.dumps(row, ensure_ascii=False))
            fh.write('\n')


def crash_row(problem_id, exc):
    """Строка-заглушка вместо задачи, на которой разбор упал непредвиденно.

    Смысл в том, чтобы сборка НЕ теряла задачу молча и не падала целиком:
    строка есть, она помечена браком, причина названа текстом исключения.
    Поля заполнены безопасными пустыми значениями — `build_metrics` ходит
    по ним без `.get`, и отсутствие ключа уронило бы уже метрики."""
    return {
        'problem_id': problem_id,
        'defect': True,
        'call1_ok': False, 'call1_retried': False,
        'call1_violations': ['%s: %s' % (PARSE_CRASH, exc)],
        'call2_ok': False, 'call2_retried': False,
        'call2_violations': ['%s: %s' % (PARSE_CRASH, exc)],
        'parse_crash': '%s: %s' % (type(exc).__name__, exc),
        'soft_violations': [], 'dropped_queries': [],
        'topic_primary': None, 'topics_secondary': None, 'tags': None,
        'given': None, 'find': None, 'econ_concepts': None,
        'concepts_offlist': None, 'task_nature': None, 'features_1': None,
        'topic_confidence': None, 'search_queries': None, 'plot': None,
        'hints': None, 'text_quality': None, 'text_quality_note': None,
        'problem_type': None, 'difficulty': None, 'difficulty_note': None,
        'answer_consistency': None, 'title_candidate': None,
        'images_sent': 0, 'tikz': None, 'solution_sent': False,
        'solution_tokens': 0, 'solution_truncated': False,
        'has_raster': False, 'has_tikz': False, 'has_tikz_in_statement': False,
        # Не 'run2': данных этого прогона в строке тоже нет.
        'source': PARSE_CRASH,
        'fallback_from_run1': [], 'graphical_solution': None,
        'graphical_solution_source': 'none', 'missing_required_fields': [],
    }


def parsed_rows_for(rows, problems_by_id, fallback_index=None):
    """⚠️ НЕ ВЫБРАСЫВАЕТ ИСКЛЮЧЕНИЙ НИ ПРИ КАКОЙ ФОРМЕ ВХОДА.

    04.09.2026 боевой прогон `run2-corpus-20260904` отработал все 37 035
    задач, заплатил $31,46 — и сборка результата легла на первой же задаче
    с ответом-массивом (`AttributeError: 'list' object has no attribute
    'get'`). Одна кривая строка не имеет права стоить всего прогона:
    непредвиденная ошибка на задаче записывается браком `parse_crash`, и
    сборка идёт дальше."""
    out = []
    for row in rows:
        pid = row.get('problem_id')
        if pid not in problems_by_id:
            continue
        try:
            out.append(parsed_row(row, problems_by_id[pid],
                                  fallback_index=fallback_index))
        except Exception as exc:  # noqa: BLE001 — намеренно широко, см. докстринг
            out.append(crash_row(pid, exc))
    return out


def load_fallback_index(path):
    """`{problem_id: старая_строка_run_parsed.jsonl}` — Фаза 4.2
    (2026-09-04): источник подстраховки. Пусто, если файла нет (обычный
    самый первый прогон — рескьюить неоткуда, это ожидаемо, не ошибка)."""
    path = Path(path)
    if not path.exists():
        return {}
    index = {}
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            index[entry['problem_id']] = entry
    return index


# ---------------------------------------------------------------------------
# Фаза 3.3: run_metrics.json — сводка.
# ---------------------------------------------------------------------------

def _payload_anomalies(parsed):
    """Сколько строк и какие именно пострадали от формы ответа модели."""
    def ids(pred):
        return sorted(p['problem_id'] for p in parsed if pred(p))

    def in_hard(p, mark):
        return any(mark in v for v in
                   (list(p.get('call1_violations') or [])
                    + list(p.get('call2_violations') or [])))

    wrapped = ids(lambda p: PAYLOAD_WRAPPED_IN_LIST
                  in (p.get('soft_violations') or []))
    not_object = ids(lambda p: in_hard(p, PAYLOAD_NOT_OBJECT))
    crashed = ids(lambda p: p.get('parse_crash'))
    return {
        PAYLOAD_WRAPPED_IN_LIST: len(wrapped),
        '%s_ids' % PAYLOAD_WRAPPED_IN_LIST: wrapped[:50],
        PAYLOAD_NOT_OBJECT: len(not_object),
        '%s_ids' % PAYLOAD_NOT_OBJECT: not_object[:50],
        PARSE_CRASH: len(crashed),
        '%s_ids' % PARSE_CRASH: crashed[:50],
    }


def build_metrics(parsed, usage_totals, sweep=None):
    """Сводка по УЖЕ РАЗОБРАННЫМ строкам (`parsed_row`). База здесь не
    нужна вовсе — всё, что раньше пересчитывалось по `Problem`, лежит в
    самой строке (`has_raster`, `has_tikz`, ...), и метрики боевого
    прогона собираются кусками, не держа корпус в памяти.

    ⚠️ TikZ считается ДВУМЯ числами. Текст решения с Фазы 1 (2026-09-04,
    реверс §3.4 API_RUN_MASTER) подаётся в вызов 1, но чертёж, привязанный
    к РЕШЕНИЮ (`ProblemFigure.source_field='solution'`), туда по-прежнему
    не уходит — `with_tikz_sources` подставляет исходник только там, где в
    ТЕКСТЕ есть маркер `[[FIGURE:...]]`, а он живёт у условия, не у
    решения. Его отсутствие — работающее правило, а не потеря. Сравнивать
    с «подставлено» можно только «TikZ у условия»:
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
        # Фаза 1 (2026-09-04, реверс §3.4 API_RUN_MASTER): сколько задач
        # реально получили решение в вызове 1, и сколько из них обрезано
        # по потолку 800 токенов — печатается в контрольной строке отчёта.
        'solution_sent_total': sum(1 for p in parsed if p.get('solution_sent')),
        'solution_truncated_total': sum(
            1 for p in parsed if p.get('solution_truncated')),
        'solution_tokens_mean': (
            statistics.mean([p['solution_tokens'] for p in parsed
                            if p.get('solution_sent')])
            if any(p.get('solution_sent') for p in parsed) else 0),
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
        # Фаза 4.2 (2026-09-04): подстраховка старым журналом — «второй
        # прогон не может сделать хуже». `by_field` считает КОНКРЕТНЫЕ поля
        # (не только «call1»/«call2»), чтобы видеть, что именно унаследовано.
        'fallback_from_run1': {
            'rows_call1': sum(1 for p in parsed
                             if 'call1' in (p.get('fallback_from_run1') or [])),
            'rows_call2': sum(1 for p in parsed
                             if 'call2' in (p.get('fallback_from_run1') or [])),
            # Одним словом на строку: 'run2' — обе половины свежие,
            # 'run1_fallback' — обе из старого журнала, 'mixed' — одна из
            # двух. Без этого «сколько задач реально обогащены вторым
            # прогоном» пришлось бы каждый раз считать разбором списков.
            'by_source': dict(Counter(p.get('source') for p in parsed)),
        },
        # Форма ответа модели (2026-09-04): не объект, объект в массиве из
        # одного элемента, непредвиденное падение разбора. Поимённо, как и
        # `rows_with_missing_fields_ids` ниже: это не «шум в процентах», а
        # список задач, с которыми надо что-то делать.
        'payload_anomalies': _payload_anomalies(parsed),
        # Инвариант владельца: доля задач с хоть одним пустым обязательным
        # полем — ноль. Список id — поимённо, не только число: пробитый
        # инвариант обязан быть виден и разбираем, а не потонуть в проценте.
        'rows_with_missing_fields': sum(
            1 for p in parsed if p.get('missing_required_fields')),
        'rows_with_missing_fields_ids': sorted(
            p['problem_id'] for p in parsed if p.get('missing_required_fields')
        )[:50],
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
        parser.add_argument(
            '--max-cost', type=float, default=None,
            help='Потолок расхода, обязателен для настоящего прогона. Не '
                 'требуется с --rebuild-from-raw: там не тратится ничего.')
        parser.add_argument(
            '--rebuild-from-raw', action='store_true',
            help='ОФЛАЙН-ПЕРЕСБОРКА: ни одного обращения к API. Берёт '
                 'готовые ответы из --raw-out и прогоняет их через ту же '
                 'логику разбора и подсчёта метрик, минуя провайдера '
                 '(провайдер не создаётся вовсе). Заведено 04.09.2026 '
                 'после падения `run2-corpus-20260904`: прогон отработал '
                 'все запросы и заплатил $31,46, а сборка результата легла '
                 'на одной кривой форме ответа — пересобрать оплаченное '
                 'было нечем, кроме как повторив прогон за деньги.')
        parser.add_argument('--workers', type=int, default=WORKERS_DEFAULT)
        parser.add_argument('--run-id', type=str, default=None)
        parser.add_argument(
            '--call1-only', action='store_true',
            help='Переделывать ТОЛЬКО вызов 1 (темы, доп. темы, теги, '
                 'понятия, «дано», «найти», характер задачи, особенности). '
                 'Вызов 2 не выполняется вовсе, его поля (заголовок, '
                 'сложность, тип задачи, подсказки, сюжет) переносятся в '
                 'результат из старого журнала без изменений. Экономит '
                 'около трети сметы перегона.')
        parser.add_argument(
            '--ids', type=str, default=None,
            help='Через запятую — конкретные id вместо первых --limit из '
                 'battle_queryset(). Например, донабор с картинками для '
                 'run300_review.html, который НЕ входит в официальный '
                 'чек-поинт «первые 300» (решение владельца 02.09.2026: '
                 'два честных прогона, не подмена выборки).')
        parser.add_argument(
            '--raw-out', type=str, default=None,
            help='Переопределить путь run_raw.jsonl (по умолчанию — '
                 'официальный файл ПЕРВОГО прогона, НЕПРИКОСНОВЕННЫЙ). '
                 'Второй/повторный прогон обязан задавать свой путь '
                 '(например run2_raw.jsonl) — иначе новый прогон допишет '
                 'сырые ответы в чужой, уже оплаченный журнал.')
        parser.add_argument(
            '--parsed-out', type=str, default=None,
            help='Переопределить путь run_parsed.jsonl (по умолчанию — '
                 'официальный файл Фазы 3.2). Использовать для донабора, '
                 'чтобы не затереть чек-поинт «первые 300».')
        parser.add_argument(
            '--metrics-out', type=str, default=None,
            help='Переопределить путь run_metrics.json — как --parsed-out.')
        parser.add_argument(
            '--fallback-parsed', type=str, default=None,
            help='Путь к СТАРОМУ run_parsed.jsonl (Фаза 4.2) — задача, не '
                 'прошедшая проверку даже после повтора, берёт свои поля '
                 'оттуда, а не остаётся пустой. По умолчанию — официальный '
                 'файл первого прогона (PARSED_LOG_PATH); нет файла — '
                 'подстраховки нет, это ожидаемо для самого первого '
                 'прогона корпуса.')
        parser.add_argument(
            '--battle-manifest', type=str, default=None,
            help='Переопределить путь БОЕВОГО манифеста выборки '
                 '(BATTLE_MANIFEST_PATH) — `--limit` больше '
                 'CHECKPOINT_LIMIT. ⚠️ Найдено владельцем перед вторым '
                 'прогоном: `_battle_sample` читает существующий манифест '
                 'КАК ЕСТЬ, не сверяя его с текущим `battle_queryset()` — '
                 'манифест первого прогона содержит задачи, которые новый '
                 'фильтр content_status уже исключает. Второй/повторный '
                 'прогон ОБЯЗАН задавать свой путь, иначе унаследует '
                 'устаревший список молча.')
        parser.add_argument(
            '--chunk', type=int, default=CHUNK_SIZE_DEFAULT,
            help='Сколько задач держать в памяти одновременно. Корпус '
                 'целиком не помещается: 41 тысяча задач это 338 МБ одних '
                 'только байтов изображений плюс тексты и подпункты.')

    def handle(self, *args, **options):
        rebuild = options['rebuild_from_raw']
        if not rebuild and options['max_cost'] is None:
            raise CommandError(
                '--max-cost обязателен: без потолка расхода боевой прогон '
                'не запускается. (Не нужен только с --rebuild-from-raw.)')
        run_id = options['run_id'] or ('glm-enrich-%d' % int(time.time()))
        limit = options['limit']
        raw_path = Path(options['raw_out']) if options['raw_out'] else RAW_LOG_PATH
        parsed_out = Path(options['parsed_out']) if options['parsed_out'] else PARSED_LOG_PATH
        metrics_out = Path(options['metrics_out']) if options['metrics_out'] else METRICS_PATH
        fallback_parsed_path = (Path(options['fallback_parsed'])
                               if options['fallback_parsed'] else PARSED_LOG_PATH)
        battle_manifest_path = (Path(options['battle_manifest'])
                               if options['battle_manifest'] else BATTLE_MANIFEST_PATH)

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
            problem_ids = self._battle_sample(limit, battle_manifest_path)
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

        if rebuild:
            self.stdout.write(
                '=== ОФЛАЙН-ПЕРЕСБОРКА: %d задач, run_id=%s ===' % (total_ids, run_id))
            self.stdout.write(
                'обращений к API — НИ ОДНОГО, провайдер не создаётся. '
                'Источник ответов: %s, кусок=%d задач' % (raw_path, chunk_size))
        else:
            self.stdout.write('=== БОЕВОЙ ПРОГОН GLM-5.3-Flash: %d задач, run_id=%s ==='
                              % (total_ids, run_id))
            self.stdout.write('workers=%d, max-cost=$%.4f, кусок=%d задач' % (
                options['workers'], options['max_cost'], chunk_size))

        prompt_version = pilot.prompt_fingerprint(GLM_VARIANT['concepts'])
        # ⚠️ Провайдер создаётся ТОЛЬКО для настоящего прогона: в режиме
        # пересборки его нет вовсе, и случайное обращение к API упадёт на
        # `None`, а не уйдёт в сеть за деньги.
        complete_fn = None if rebuild else make_glm_complete_fn()
        call1_only = options['call1_only']
        if call1_only:
            self.stdout.write(
                'режим --call1-only: ровно ОДИН вызов на задачу; поля вызова '
                '2 переносятся из старого журнала без изменений')

        tracker = RunQualityTracker(call1_only=call1_only)
        stop_event = threading.Event()
        processed_count = {'n': 0}
        count_lock = threading.Lock()
        start_time = time.monotonic()

        # Свип-детектор (§12 правило 2): отпечаток защищённых полей ДО
        # прогона. Прогон в базу не пишет вовсе — ожидание ровно 0
        # расхождений, и это надо ПОКАЗАТЬ числом, а не утверждать.
        # В режиме пересборки снимать нечего: прогон не идёт, база не
        # трогается, и два снимка по 37 тысячам задач стоили бы минут
        # чтения ради заведомого нуля.
        sweep_before = None if rebuild else protected_fields_digest(problem_ids)

        # ⚠️ Расход завершённых кусков. `on_progress` получает от
        # `run_variant_concurrent` расход ТЕКУЩЕГО КУСКА (его `state['spent']`
        # начинается с нуля на каждый вызов), и печатать его как «потрачено»
        # значит врать: на боевом прогоне 02.09.2026 контрольная строка
        # показала $1,0814 на 2000 задачах и $1,0411 на 4000 — расход как
        # будто уменьшился. Правильное число — сумма завершённых кусков плюс
        # расход текущего.
        spent_done = {'v': Decimal('0')}

        def on_progress(problem_id, chunk_spent):
            with count_lock:
                processed_count['n'] += 1
                n = processed_count['n']
            if n % CHECKPOINT_EVERY == 0:
                elapsed = time.monotonic() - start_time
                rate = n / elapsed * 60 if elapsed else 0.0
                remaining = todo_total - n
                eta_min = remaining / rate if rate else float('inf')
                defect_pct, retry_pct, soft_pct = tracker.pcts()
                total_spent = spent_done['v'] + Decimal(str(chunk_spent))
                self.stdout.write(
                    '  [%d/%d] брак %.1f%% (порог %.0f%%), повторы %.1f%%, '
                    'мягкие %.1f%%, потрачено $%.4f, %.1f задач/мин, '
                    'прогноз оставшегося: %.0f мин'
                    % (n, todo_total, defect_pct, tracker.stop_pct,
                       retry_pct, soft_pct, total_spent, rate, eta_min))
                self.stdout.flush()

        def extra_on_row(row):
            tracker.record(row)
            if tracker.breached:
                stop_event.set()

        # ⚠️ Журнал читается ОДИН раз, потоком (`iter_raw_log`), а не на
        # каждый кусок: на 41 тысяче задач в нём 80+ тысяч строк, и
        # двадцать перечитываний стоили бы дороже самого прогона.
        if rebuild:
            # Пересборка не обрабатывает НИ ОДНОЙ задачи заново: цикл
            # запросов ниже просто не выполняется (`todo_total = 0`), а
            # результат собирается из журнала в разделе «Фаза 3.2/3.3».
            todo_ids, todo_total, skipped = [], 0, total_ids
        else:
            done_ids = pilot.done_problem_ids_from_log(
                str(raw_path), prompt_version, GLM_VARIANT,
                call1_only=call1_only)
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
                            str(raw_path), run_id, prompt_version,
                            options['workers'], max_cost=remaining_budget,
                            on_progress=on_progress, stop_event=stop_event,
                            extra_on_row=extra_on_row, done_ids=set(),
                            call1_only=call1_only))
                    spent += chunk_spent
                    spent_done['v'] = spent
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
                                  '--run-id (и тем же --raw-out) продолжит с места '
                                  'остановки, платить заново не придётся.' % raw_path)
                return

            self.stdout.write('')
            if rebuild:
                self.stdout.write(
                    'обращений к API: 0, потрачено: $0.0000 — пересборка '
                    'из уже оплаченного журнала')
            else:
                self.stdout.write('обработано сейчас: %d, пропущено (уже в журнале): %d'
                                  % (processed_now, skipped))
                self.stdout.write('потрачено: $%.4f%s' % (
                    spent, ' (остановлено потолком)' if stopped else ''))
            if errors:
                self.stdout.write('⚠️ %d задач упали без восстановления (после сетевых '
                                  'повторов) — не попали ни в результат, ни в брак, '
                                  'нужен отдельный разбор: %s'
                                  % (len(errors), [pid for pid, _ in errors][:20]))
            if not rebuild:
                defect_pct, retry_pct, soft_pct = tracker.pcts()
                self.stdout.write(
                    'в этом запуске: брак %.1f%%, повторы %.1f%%, мягкие %.1f%% '
                    '(остановка — брак/утечка в find/пустые подсказки, порог '
                    'каждого %.1f%%)'
                    % (defect_pct, retry_pct, soft_pct, tracker.stop_pct))
            if tracker.breached:
                self.stdout.write('')
                # ⚠️ Причина печатается ИЗ ТРЕКЕРА (`breach_reason`), а не
                # зашита текстом «финальный брак»: сработать мог любой из
                # трёх сторожей Фазы 5, и сообщение обязано называть
                # ИМЕННО того, кто остановил прогон.
                self.stdout.write(
                    '🔴 СТОП: %s. Прогон остановлен сам, дальше решает '
                    'владелец.' % tracker.breach_reason)

            # --- Фаза 3.2/3.3 -------------------------------------------
            sweep = (None if sweep_before is None
                     else sweep_report(sweep_before,
                                       protected_fields_digest(problem_ids)))
            # Фаза 4.2: читается ОДИН раз, не на каждый кусок (те же
            # соображения, что у `done_ids` — 41 тысяча строк не перечитать
            # двадцать раз подряд бесплатно).
            fallback_index = load_fallback_index(fallback_parsed_path)
            if fallback_index:
                self.stdout.write(
                    'подстраховка старым журналом: %s (%d задач доступно '
                    'для рескью)' % (fallback_parsed_path, len(fallback_index)))
            parsed_all, usage_totals = self._collect_parsed(
                problem_ids, chunk_size, prompt_version, parsed_out,
                raw_path, call1_only=call1_only, fallback_index=fallback_index)
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
                          '%d, получили чертёж в вызове 1: %d (картинка '
                          'решения по-прежнему не подаётся, только текст)'
                          % (metrics['problems_with_tikz'],
                             metrics['problems_with_tikz_in_statement'],
                             metrics['problems_tikz_replaced']))
        self.stdout.write('решение в вызове 1 (Фаза 1, реверс §3.4): у %d задач, '
                          'обрезано по потолку 800 токенов у %d, средний размер '
                          'блока %.0f токенов'
                          % (metrics['solution_sent_total'],
                             metrics['solution_truncated_total'],
                             metrics['solution_tokens_mean']))
        self.stdout.write('подстраховка старым журналом (Фаза 4.2): вызов 1 '
                          'рескьюнут у %d задач, вызов 2 — у %d'
                          % (metrics['fallback_from_run1']['rows_call1'],
                             metrics['fallback_from_run1']['rows_call2']))
        self.stdout.write('доля задач с пустым обязательным полем (инвариант, '
                          'ожидание 0): %d%s'
                          % (metrics['rows_with_missing_fields'],
                             (' — id: %s' % metrics['rows_with_missing_fields_ids'])
                             if metrics['rows_with_missing_fields'] else ''))
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
        self.stdout.write('журналы: %s, %s' % (raw_path, parsed_out))

    # --- работа кусками -------------------------------------------------

    def _battle_sample(self, limit, battle_manifest_path=BATTLE_MANIFEST_PATH):
        """Весь корпус `battle_queryset()`, перемешанный тем же зерном, что
        и контрольная точка, и урезанный до `limit`.

        Перемешивание — не украшательство. Урок Фазы C: id идут пластами
        (визуальный пласт лежит в диапазоне 57000-63000), и при обходе по
        возрастанию любой начальный кусок прогона непредставителен —
        автостоп судил бы о качестве корпуса по одному источнику. Порядок
        детерминирован зерном и сохраняется в свой манифест, поэтому
        возобновление берёт ту же выборку в том же порядке.

        ⚠️ Манифест читается КАК ЕСТЬ, если существует — НЕ сверяется с
        текущим `battle_queryset()` заново (найдено владельцем перед вторым
        прогоном: манифест первого прогона содержит задачи, которые
        добавленный позже фильтр `content_status` уже исключает). Второй
        прогон обязан передать СВОЙ `battle_manifest_path` (флаг
        `--battle-manifest`), а не переиспользовать чужой файл молча."""
        if battle_manifest_path.exists():
            with open(battle_manifest_path, encoding='utf-8') as fh:
                manifest = json.load(fh)
            self.stdout.write('=== БОЕВАЯ ВЫБОРКА: манифест уже существует, '
                              'беру его (%s, seed=%s, задач %d) ==='
                              % (battle_manifest_path, manifest.get('seed'),
                                 len(manifest['ids'])))
            return manifest['ids']
        ids = list(battle_queryset().values_list('id', flat=True))
        random.Random(CHECKPOINT_SEED).shuffle(ids)
        if limit < len(ids):
            ids = ids[:limit]
        battle_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(battle_manifest_path, 'w', encoding='utf-8') as fh:
            json.dump({'seed': CHECKPOINT_SEED, 'limit': limit, 'ids': ids},
                     fh, ensure_ascii=False)
        self.stdout.write('=== БОЕВАЯ ВЫБОРКА: весь корпус кроме служебных '
                          'фикстур, %d задач, перемешан зерном %d ==='
                          % (len(ids), CHECKPOINT_SEED))
        self.stdout.write('манифест сохранён: %s' % battle_manifest_path)
        return ids

    def _load_problems(self, chunk_ids):
        """Задачи одного куска, В ТОМ ЖЕ ПОРЯДКЕ, что и `chunk_ids`."""
        by_id = {p.id: p for p in
                Problem.objects.filter(id__in=list(chunk_ids))
                .prefetch_related('parts', 'figures')}
        return [by_id[pid] for pid in chunk_ids if pid in by_id], by_id

    def _collect_parsed(self, problem_ids, chunk_size, prompt_version,
                        parsed_out, raw_path, call1_only=False,
                        fallback_index=None):
        """Строки `run_parsed.jsonl` и суммарный расход — КУСКАМИ.

        Журнал перечитывается потоком на каждый кусок (`iter_raw_log`), но
        в памяти остаются только маленькие разобранные строки: держать
        одновременно 80 тысяч сырых ответов И корпус с картинками нельзя.

        `fallback_index` (Фаза 4.2) — `{problem_id: строка_старого_run_
        parsed.jsonl}`, читается ОДИН раз вызывающим кодом (`handle()`),
        не на каждый кусок — те же соображения памяти/времени, что и у
        `done_ids`."""
        parsed_all = []
        usage_totals = {'input_tokens': 0, 'cache_read_tokens': 0,
                        'cache_write_tokens': 0, 'output_tokens': 0,
                        'reasoning_tokens': 0, 'cost_usd': '0'}
        cost = Decimal('0')
        written = False
        no_call2 = []
        for start in range(0, len(problem_ids), chunk_size):
            chunk_ids = problem_ids[start:start + chunk_size]
            wanted = set(chunk_ids)
            entries = [e for e in pilot.iter_raw_log(str(raw_path))
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
                                       prompt_version, shortlists, by_id,
                                       call1_only=call1_only)
            if call1_only:
                no_call2.extend(r['problem_id'] for r in rows
                                if not r.get('call2_carried'))
            chunk_usage = usage_totals_from_rows(rows)
            for key in ('input_tokens', 'cache_read_tokens', 'cache_write_tokens',
                        'output_tokens', 'reasoning_tokens'):
                usage_totals[key] += chunk_usage[key]
            cost += Decimal(chunk_usage['cost_usd'])
            parsed_chunk = parsed_rows_for(rows, by_id,
                                          fallback_index=fallback_index)
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
        if no_call2:
            # Поимённо, а не числом: у этих задач заголовок, сложность, тип
            # и подсказки останутся пустыми, и это надо чинить отдельным
            # прогоном вызова 2, а не обнаружить через месяц в каталоге.
            NO_CALL2_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(NO_CALL2_PATH, 'w', encoding='utf-8') as fh:
                json.dump({'count': len(no_call2), 'ids': sorted(no_call2)},
                          fh, ensure_ascii=False, indent=2)
            self.stdout.write(
                '⚠️ у %d задач в старом журнале НЕТ вызова 2 — поля '
                'заголовка/сложности/типа/подсказок останутся пустыми. '
                'Список: %s' % (len(no_call2), NO_CALL2_PATH))
        # Форма ответа модели — сводка сразу, а не только в JSON метрик:
        # падение сборки 04.09.2026 началось именно отсюда, и следующий
        # раз это должно быть видно в консоли, а не найдено потом.
        anomalies = _payload_anomalies(parsed_all)
        if any(anomalies[k] for k in (PAYLOAD_WRAPPED_IN_LIST,
                                      PAYLOAD_NOT_OBJECT, PARSE_CRASH)):
            self.stdout.write(
                '⚠️ форма ответа модели: объект в массиве (развёрнут) — %d, '
                'не объект (брак) — %d, разбор упал — %d'
                % (anomalies[PAYLOAD_WRAPPED_IN_LIST],
                   anomalies[PAYLOAD_NOT_OBJECT], anomalies[PARSE_CRASH]))
            if anomalies[PARSE_CRASH]:
                self.stdout.write(
                    '   упавшие при разборе id: %s'
                    % anomalies['%s_ids' % PARSE_CRASH])
        return parsed_all, usage_totals

    def _rows_from_log(self, entries, problem_ids, variant, prompt_version,
                       shortlists, problems_by_id, call1_only=False):
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
        повторной оплаты.

        ⚠️ `call1_only=True` — ПЕРЕНОС ПОЛЕЙ ВЫЗОВА 2 ИЗ СТАРОГО ЖУРНАЛА.
        Перегон корпуса переделывает только вызов 1, поэтому записи вызова 2
        с НОВОЙ версией промпта в журнале не появятся никогда. Брать их
        нужно из записей СТАРОЙ версии — иначе `run_parsed.jsonl` вышел бы
        с пустыми заголовком, сложностью, типом задачи и подсказками, то
        есть перегон стёр бы уже оплаченную работу.

        Правило: вызов 1 берётся ТОЛЬКО со своей (новой) версией промпта,
        вызов 2 — с ЛЮБОЙ. Журнал дописывается в конец, поэтому при
        нескольких старых версиях побеждает последняя, то есть самая
        свежая.

        Деньги при этом НЕ смешиваются: попытки вызова 2 из чужого прогона
        уходят в `call2_carried_attempts` и в расход этого запуска не
        попадают — иначе цена перегона включала бы то, за что мы уже
        заплатили в прошлый раз. `call2_retried` при этом сохраняется:
        повтор был, просто оплачен раньше."""
        by_pid = {}
        for entry in entries:
            call = entry['call']
            base_call = call.split('_retry')[0]
            if base_call not in ('call1', 'call2'):
                continue
            same_version = entry.get('prompt_version') == prompt_version
            if not same_version and not (call1_only and base_call == 'call2'):
                continue
            row = by_pid.setdefault(
                entry['problem_id'],
                {'problem_id': entry['problem_id'], 'call1_attempts': [],
                'call2_attempts': [], 'call2_carried_attempts': []})
            usage = entry['usage']

            class _U(object):
                pass
            u = _U()
            u.input_tokens = usage['input_tokens']
            u.output_tokens = usage['output_tokens']
            u.cache_write_tokens = usage.get('cache_write_tokens', 0)
            u.cache_read_tokens = usage['cache_read_tokens']
            u.reasoning_tokens = usage.get('reasoning_tokens', 0)
            carried = call1_only and base_call == 'call2'
            if carried:
                # Новая версия промпта могла бы дописать сюда свои записи
                # только по ошибке — но если такое случилось, они всё равно
                # НЕ оплачены этим запуском (вызов 2 не делался вовсе), так
                # что место у них одно.
                row['call2_carried_attempts'].append(u)
                row['call2_carried_from'] = entry.get('prompt_version')
            else:
                row['%s_attempts' % base_call].append(u)
            if call == base_call:  # финальная попытка (без суффикса _retryN)
                # ⚠️ Форма ответа приводится ЗДЕСЬ, до валидаторов: объект,
                # обёрнутый моделью в массив из одного элемента, иначе не
                # прошёл бы проверку схемы и ушёл бы в брак, хотя внутри
                # он целый. Пометки формы едут в строке и попадают в
                # нарушения через `parsed_row`.
                payload, soft, hard = normalize_payload(entry['raw_response'])
                row[base_call] = payload
                row['%s_payload_soft' % base_call] = soft
                row['%s_payload_hard' % base_call] = hard
                if not carried:
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
            # ⚠️ Тексты нарушений СОХРАНЯЮТСЯ, а не выбрасываются в `_`
            # (04.09.2026): живой путь кладёт их в `call*_violations`, а
            # восстановление из журнала клало пустой список — и в
            # `run_parsed.jsonl` у бракованных задач причина брака была
            # пустой. Разбирать «почему 94 задачи ушли в брак» было не по
            # чему, хотя сам ответ модели лежит на диске.
            row['call1_ok'], row['call1_violations'] = pilot.validate_call1_full(
                row.get('call1'), variant['concepts'], shortlist_terms=shortlist_terms)
            row['call1_retried'] = len(row['call1_attempts']) > 1
            row['call2_ok'], row['call2_violations'] = pilot.validate_call2_full(
                row.get('call2'))
            # Повтор вызова 2 в режиме переноса был в ПРОШЛОМ прогоне и
            # оплачен там же — факт сохраняем, деньги не пересчитываем.
            row['call2_retried'] = len(
                row['call2_carried_attempts'] if call1_only
                else row['call2_attempts']) > 1
            if call1_only:
                # Задачи, у которых старого вызова 2 нет вовсе: их поля
                # заголовка/сложности/типа останутся пустыми, и владелец
                # обязан видеть поимённый список, а не узнать об этом из
                # пустой колонки через месяц.
                row['call2_carried'] = 'call2' in row
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
                _, solution_stats = enrich_text.solution_hint_for_call1(
                    problem.solution)
                row['solution_sent'] = solution_stats['sent']
                row['solution_tokens'] = solution_stats['tokens']
                row['solution_truncated'] = solution_stats['truncated']
            else:
                row.setdefault('images_sent', 0)
                row.setdefault('tikz', {'replaced': 0, 'truncated': 0})
                row.setdefault('solution_sent', False)
                row.setdefault('solution_tokens', 0)
                row.setdefault('solution_truncated', False)
            rows.append(row)
        return rows
