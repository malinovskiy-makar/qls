# -*- coding: utf-8 -*-
"""glm_eval — быстрая проверка «годится ли GLM-5.3-Flash вместо GPT-5.6 Terra».

Разовый замер, не боевой конвейер. Переиспользует ЯДРО и СХЕМУ пилота v2
(`pilot_enrich_v2.py`) и ТУ ЖЕ выборку слепого сравнения
(`blind_models_export.build_sample`, тот же сид) — ничего в промпте не
меняет, иначе сравнение с веткой `base` (Terra+Luna) стало бы нечестным.

⚠️ У Z.AI НЕТ строгой structured-output схемы (`response_format` принимает
только `text`/`json_object`, не `json_schema`) — `GLMProvider.complete()`
шлёт схему ТЕКСТОМ, а `validate_schema()` здесь проверяет соответствие ей
уже на нашей стороне. Это и есть предмет замера «доля ответов, прошедших
схему», а не сокращение пути.

Три фазы:
    manage.py glm_eval --phase smoke --max-cost 0.10   # 5 задач, три числа
    manage.py glm_eval --phase full  --max-cost 0.50    # 25 задач (резюмируемо)
    manage.py glm_eval --phase report                  # печать + report.html
"""
import difflib
import html
import json
import statistics
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.test import override_settings

from problems.ai import providers
from problems.enrich import prompts_v2, taxonomy
from problems.enrich.text import problem_full_text
from problems.enrich.shortlist import shortlist_for
from problems.management.commands import blind_models_export as blind
from problems.management.commands import pilot_enrich_v2 as pilot
from problems.models import Problem

GLM_MODEL = 'glm-5.3-flash'
# Официальный прайс-лист Z.AI (без временной скидки 50%, см. отчёт) —
# $ за млн: вход, кэш, выход. Тот же порядок, что у AI_PRICES в settings.py.
GLM_PRICES = (0.15, 0.03, 0.50)
GLM_PRICES_PROMO = (0.075, 0.015, 0.25)

GLM_VARIANT = {
    'label': 'glm-flash-none + glm-flash-none (замена base на GLM, оба вызова)',
    'call1_model': GLM_MODEL, 'call1_effort': 'none',
    'call2_model': GLM_MODEL, 'call2_effort': 'none',
    'concepts': True,
}

LOG_PATH = 'reports/enrich_pilot/glm_raw_log.jsonl'
REPORT_HTML = 'reports/enrich_pilot/glm_vs_terra.html'

# Эталон владельца по 9 спорным задачам (Фаза 2 задания сессии).
DISPUTED_ANSWER_KEY = {
    162: '11 — Внешние эффекты и общественные блага',
    2028: '16 — Открытая экономика и валютный рынок',
    60699: '8 — Монополия и ценовая дискриминация',
    54217: '15 — Международная торговля',
    54405: '12 — Асимметрия информации и риск',
    60212: '11 — Внешние эффекты и общественные блага',
    49268: '8 — Монополия и ценовая дискриминация',
    3650: '24 — Проценты, вклады и кредиты',
    27421: '28 — Математический аппарат',
}

BASELINE_SCORES = [
    ('Terra, reasoning=none (ветка base)', 7),
    ('Terra с рассуждением (terra-low)', 4),
    ('Luna (luna-luna)', 2),
]


# ---------------------------------------------------------------------------
# Строгая проверка схемы вручную — jsonschema не установлен в venv313, а
# схема этого пилота плоская (object → примитивы/массивы примитивов), так
# что ручной обход не рискует разойтись с полноценным валидатором.
# ---------------------------------------------------------------------------

_TYPE_MAP = {'string': str, 'integer': int, 'array': list, 'object': dict,
            'boolean': bool, 'null': type(None)}


def _type_ok(value, types):
    for t in types:
        if t == 'integer' and isinstance(value, bool):
            continue  # bool — подкласс int, схема integer его не разрешает
        py = _TYPE_MAP.get(t)
        if py and isinstance(value, py):
            return True
    return False


def _check_value(label, value, spec):
    violations = []
    types = spec.get('type')
    types = [types] if isinstance(types, str) else list(types or [])
    if 'null' in types and value is None:
        return violations
    if types and not _type_ok(value, types):
        violations.append('%s: тип %s не входит в %s' % (label, type(value).__name__, types))
        return violations
    if 'enum' in spec and value not in spec['enum']:
        violations.append('%s: значение %r вне enum' % (label, value))
    if isinstance(value, list):
        min_items = spec.get('minItems')
        if min_items is not None and len(value) < min_items:
            violations.append('%s: короче minItems=%d (%d)' % (label, min_items, len(value)))
        items_spec = spec.get('items')
        if items_spec:
            for i, item in enumerate(value):
                violations.extend(_check_value('%s[%d]' % (label, i), item, items_spec))
    return violations


def validate_schema(data, schema):
    """Полная проверка JSON Schema объекта верхнего уровня — то, что у
    OpenAI/Anthropic делает сам поставщик (`strict`), а у GLM не делает
    никто, если не сделать это здесь."""
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
            violations.extend(_check_value(key, data[key], spec))
    return violations


def full_violations(row, with_concepts=True):
    """Схемные + промптовые (длины массивов, title_candidate) нарушения
    строкой — «прошла с первого раза» значит список пуст ЦЕЛИКОМ."""
    out = []
    data1 = row.get('call1')
    if data1 is None:
        return ['call1 не выполнен']
    out.extend(validate_schema(data1, prompts_v2.call1_schema(with_concepts)))
    _, extra1 = pilot.validate_call1(data1, with_concepts)
    out.extend('call1: ' + v for v in extra1)
    data2 = row.get('call2')
    if data2 is None:
        out.append('call2 не выполнен')
        return out
    out.extend(validate_schema(data2, prompts_v2.CALL2_SCHEMA))
    _, extra2 = pilot.validate_call2(data2)
    out.extend('call2: ' + v for v in extra2)
    return out


# ---------------------------------------------------------------------------
# Провайдер GLM — обёртка с ретраями сети, по образцу
# `pilot_enrich_v2.make_openai_complete_fn`.
# ---------------------------------------------------------------------------

def make_glm_complete_fn():
    provider = providers.GLMProvider()

    def _call_once(model, blocks, user_text, schema, effort, images):
        with override_settings(AI_REASONING_EFFORT=effort or 'none'):
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


def _with_glm_prices():
    from django.conf import settings
    prices = dict(getattr(settings, 'AI_PRICES', {}))
    prices[GLM_MODEL] = GLM_PRICES
    return override_settings(AI_PRICES=prices)


# ---------------------------------------------------------------------------
# Чтение уже собранной страницы слепого сравнения — ветка `base` для тех же
# 25 задач восстанавливается из HTML+ключа (rows.json на диске не оказалось),
# те же 8 полей, что видит владелец.
# ---------------------------------------------------------------------------

FIELD_RE = __import__('re').compile(r'<div class="field"><b>([^<]+):</b> (.*?)</div>', __import__('re').S)


def read_base_branch_fields(sample_ids):
    """`{problem_id: {имя_поля: строка}}` для ветки `base` — парсинг
    `blind_models.html` тем же способом, что `scripts/blind_models_stats.py`."""
    import re as _re
    key = json.load(open(blind.OUT_DIR + '/' + blind.KEY_NAME, encoding='utf-8'))
    columns_key = key['columns']
    page = open(blind.OUT_DIR + '/' + blind.HTML_NAME, encoding='utf-8').read()
    blocks = _re.split(r'<h2>Задача #(\d+)</h2>', page)[1:]
    out = {}
    for i in range(0, len(blocks), 2):
        pid = blocks[i]
        if int(pid) not in sample_ids:
            continue
        body = blocks[i + 1]
        cells = _re.findall(r'<td>(.*?)</td>', body, _re.S)
        letters = _re.findall(r'<th>Колонка ([A-D])</th>', body)
        for letter, cell in zip(letters, cells):
            branch = columns_key[pid][letter]
            if branch != 'base':
                continue
            fields = {name: html.unescape(value).strip()
                     for name, value in FIELD_RE.findall(cell)}
            out[int(pid)] = fields
    return out


def glm_fields_from_row(row):
    """То же самое 8-полей представление, но из «сырого» ответа GLM —
    `blind_models_export.column_cells` уже делает ровно это форматирование,
    имя ветки внутри не участвует."""
    return dict(blind.column_cells(row))


def tagset(value):
    import re as _re
    return set(_re.findall(r'\(([0-9.]+)\)', value or ''))


def sim(a, b):
    return difflib.SequenceMatcher(None, a or '', b or '').ratio()


# ---------------------------------------------------------------------------
# Команда
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Разовая проверка GLM-5.3-Flash против ветки base (Terra+Luna).'

    def add_arguments(self, parser):
        parser.add_argument('--phase', choices=['smoke', 'full', 'report'],
                            required=True)
        parser.add_argument('--max-cost', type=float, default=None)
        parser.add_argument('--seed', type=int, default=blind.SEED)

    def handle(self, *args, **options):
        phase = options['phase']
        if phase in ('smoke', 'full') and options['max_cost'] is None:
            raise CommandError('--max-cost обязателен для --phase %s.' % phase)

        sample_ids, sample_report = blind.build_sample(options['seed'])
        problems_by_id = {p.id: p for p in
                          Problem.objects.filter(id__in=sample_ids)
                          .prefetch_related('parts', 'figures')}
        problems = [problems_by_id[i] for i in sample_ids if i in problems_by_id]
        shortlists = {p.id: shortlist_for(problem_full_text(p.statement, p.parts.all()))
                     for p in problems}

        if phase == 'smoke':
            self._phase_smoke(problems[:5], shortlists, options['max_cost'])
        elif phase == 'full':
            self._phase_full(problems, shortlists, options['max_cost'])
        else:
            self._phase_report(sample_ids, problems_by_id)

    # -----------------------------------------------------------------
    def _phase_smoke(self, problems, shortlists, max_cost):
        self.stdout.write('=== ФАЗА 0: смок-тест на %d задачах (%s) ==='
                          % (len(problems), ', '.join(str(p.id) for p in problems)))
        complete_fn = make_glm_complete_fn()
        with _with_glm_prices():
            rows, spent, stopped = pilot.run_variant(
                problems, GLM_VARIANT, complete_fn, shortlists,
                max_cost=max_cost,
                on_progress=lambda pid, s: self.stdout.write(
                    '  #%d готово, потрачено $%.4f' % (pid, s)))

            ok_count = 0
            for row in rows:
                violations = full_violations(row, GLM_VARIANT['concepts'])
                ok = not violations
                ok_count += ok
                c1u = row.get('call1_usage')
                c2u = row.get('call2_usage')
                self.stdout.write('')
                self.stdout.write('#%d: схема %s' % (
                    row['problem_id'], 'OK' if ok else 'НАРУШЕНА: %s' % violations))
                if c1u:
                    self.stdout.write(
                        '  call1: in=%d cache=%d out=%d cost=$%.5f'
                        % (c1u.input_tokens, c1u.cache_read_tokens,
                           c1u.output_tokens, pilot.real_call_cost(GLM_MODEL, c1u)))
                if c2u:
                    self.stdout.write(
                        '  call2: in=%d cache=%d out=%d cost=$%.5f'
                        % (c2u.input_tokens, c2u.cache_read_tokens,
                           c2u.output_tokens, pilot.real_call_cost(GLM_MODEL, c2u)))

        n = len(rows)
        self.stdout.write('')
        self.stdout.write('=== ИТОГО ФАЗА 0 ===')
        self.stdout.write('доля прошедших схему с первого раза: %d/%d (%.0f%%)'
                          % (ok_count, n, 100 * ok_count / n if n else 0))
        self.stdout.write('потрачено по факту: $%.5f (остановлено по потолку: %s)'
                          % (spent, stopped))
        if n < len(problems):
            self.stdout.write('⚠️ упёрлись в --max-cost раньше, чем прошли все %d — '
                              'подними потолок.' % len(problems))

    # -----------------------------------------------------------------
    def _phase_full(self, problems, shortlists, max_cost):
        self.stdout.write('=== ФАЗА 1: полный прогон, %d задач ===' % len(problems))
        complete_fn = make_glm_complete_fn()
        run_id = 'glm-eval-%d' % int(time.time())
        prompt_version = pilot.prompt_fingerprint(GLM_VARIANT['concepts'])
        with _with_glm_prices():
            rows, spent, stopped, skipped = pilot.resumable_run_variant(
                problems, GLM_VARIANT, complete_fn, shortlists,
                LOG_PATH, run_id, prompt_version, max_cost=max_cost,
                on_progress=lambda pid, s: self.stdout.write(
                    '  #%d готово, потрачено $%.4f' % (pid, s)))
        self.stdout.write('обработано сейчас: %d, пропущено (уже в журнале): %d, '
                          'потрачено сейчас: $%.4f%s'
                          % (len(rows), skipped, spent,
                             ' (остановлено по потолку)' if stopped else ''))
        self.stdout.write('журнал: %s' % LOG_PATH)
        total_done = len(rows) + skipped
        if total_done < len(problems):
            self.stdout.write('⚠️ готово %d из %d — прогони ещё раз с большим '
                              '--max-cost, резюмируется само.' % (total_done, len(problems)))

    # -----------------------------------------------------------------
    def _phase_report(self, sample_ids, problems_by_id):
        entries = pilot.read_raw_log(LOG_PATH)
        by_pid = {}
        for entry in entries:
            row = by_pid.setdefault(entry['problem_id'], {'problem_id': entry['problem_id']})
            data = entry['raw_response']
            usage = entry['usage']

            class _U(object):
                pass
            u = _U()
            u.input_tokens = usage['input_tokens']
            u.output_tokens = usage['output_tokens']
            u.cache_write_tokens = usage.get('cache_write_tokens', 0)
            u.cache_read_tokens = usage['cache_read_tokens']
            u.reasoning_tokens = usage.get('reasoning_tokens', 0)
            row[entry['call']] = data
            row['%s_usage' % entry['call']] = u

        missing = [pid for pid in sample_ids if pid not in by_pid or 'call2' not in by_pid[pid]]
        n_done = len(sample_ids) - len(missing)
        self.stdout.write('=== ЖУРНАЛ GLM: %d/%d задач с обоими вызовами ==='
                          % (n_done, len(sample_ids)))
        if missing:
            self.stdout.write('  не хватает: %s' % missing)

        rows = [by_pid[pid] for pid in sample_ids if pid in by_pid and 'call2' in by_pid[pid]]

        # --- цена -----------------------------------------------------
        with _with_glm_prices():
            total_cost = sum(
                (pilot.real_call_cost(GLM_MODEL, r['call1_usage'])
                 + pilot.real_call_cost(GLM_MODEL, r['call2_usage']))
                for r in rows)
        per_problem = total_cost / len(rows) if rows else Decimal('0')
        self.stdout.write('')
        self.stdout.write('=== ЦЕНА (официальный прайс-лист, БЕЗ временной скидки 50%%) ===')
        self.stdout.write('%d задач (2 вызова): $%.5f, на 1 задачу: $%.6f'
                          % (len(rows), total_cost, per_problem))
        for n in (41307, 35846):
            self.stdout.write('  экстраполяция на %d задач: $%.2f' % (n, per_problem * n))

        # --- доля прошедших схему -------------------------------------
        ok_count = sum(1 for r in rows if not full_violations(r, True))
        self.stdout.write('')
        self.stdout.write('доля прошедших схему с первого раза (все %d): %d/%d (%.0f%%)'
                          % (len(rows), ok_count, len(rows),
                             100 * ok_count / len(rows) if rows else 0))

        # --- счёт по 9 спорным ------------------------------------------
        self.stdout.write('')
        self.stdout.write('=== ФАЗА 2: счёт по 9 спорным задачам ===')
        correct = 0
        detail = []
        for pid, canonical in DISPUTED_ANSWER_KEY.items():
            row = by_pid.get(pid)
            if not row or 'call1' not in row:
                detail.append('#%d: НЕТ ОТВЕТА GLM' % pid)
                continue
            got_id = row['call1'].get('topic_primary')
            got_label = blind.theme_label(got_id)
            is_correct = got_label.strip() == canonical.strip()
            correct += is_correct
            detail.append('#%d: GLM=%r эталон=%r %s'
                          % (pid, got_label, canonical, 'OK' if is_correct else 'МИМО'))
        for line in detail:
            self.stdout.write('  ' + line)
        self.stdout.write('')
        self.stdout.write('| Ветка | Верных тем из 9 |')
        self.stdout.write('|---|---:|')
        for label, score in BASELINE_SCORES:
            self.stdout.write('| %s | %d |' % (label, score))
        self.stdout.write('| GLM-5.3-Flash | %d |' % correct)

        # --- Фаза 3: GLM против base на всех 25 --------------------------
        base_fields = read_base_branch_fields(sample_ids)
        self._phase3_stats(rows, base_fields)
        self._build_report_html(sample_ids, by_pid, base_fields, problems_by_id)

    # -----------------------------------------------------------------
    def _phase3_stats(self, rows, base_fields):
        self.stdout.write('')
        self.stdout.write('=== ФАЗА 3: GLM против base на всех задачах ===')
        n = 0
        same_topic = 0
        tags_full = tags_part = tags_zero = 0
        given_sims, find_sims = [], []
        n_tags_glm = []
        conf_counter = Counter()
        for row in rows:
            pid = row['problem_id']
            base = base_fields.get(pid)
            if not base:
                continue
            glm = dict(blind.column_cells(row))
            n += 1
            if glm.get('Тема') == base.get('Тема'):
                same_topic += 1
            ta, tb = tagset(glm.get('Теги')), tagset(base.get('Теги'))
            if ta == tb:
                tags_full += 1
            elif ta & tb:
                tags_part += 1
            else:
                tags_zero += 1
            n_tags_glm.append(len(row['call1'].get('tags') or []))
            conf_counter[row['call1'].get('topic_confidence') or '—'] += 1
            given_sims.append(sim(glm.get('Дано'), base.get('Дано')))
            find_sims.append(sim(glm.get('Найти'), base.get('Найти')))

        self.stdout.write('n = %d (задач, где есть и GLM, и base)' % n)
        if n:
            self.stdout.write('topic_primary совпал: %d (%.0f%%)' % (same_topic, 100 * same_topic / n))
            self.stdout.write('теги — полное совпадение: %d (%.0f%%), частичное: %d (%.0f%%), '
                              'нулевое пересечение: %d (%.0f%%)'
                              % (tags_full, 100 * tags_full / n, tags_part, 100 * tags_part / n,
                                 tags_zero, 100 * tags_zero / n))
            self.stdout.write('среднее число тегов у GLM: %.2f (у прежних веток было 2.2–2.3)'
                              % statistics.mean(n_tags_glm))
            self.stdout.write('распределение topic_confidence (GLM): %s' % dict(conf_counter))
            self.stdout.write('«дано» близость: медиана %.3f' % statistics.median(given_sims))
            self.stdout.write('«найти» близость: медиана %.3f' % statistics.median(find_sims))

    # -----------------------------------------------------------------
    def _build_report_html(self, sample_ids, by_pid, base_fields, problems_by_id):
        FIELD_ORDER = ['Тема', 'Уверенность', 'Теги', 'Дано', 'Найти',
                      'Понятия', 'Заголовок', 'Сложность']
        parts = ["""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>GLM-5.3-Flash против Terra (base) — 9 спорных задач</title>
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;font-size:14px;margin:24px;color:#222}
table{border-collapse:collapse;width:100%;margin-bottom:14px}
td,th{border:1px solid #ccc;padding:8px;vertical-align:top;text-align:left}
th{background:#f0f0f0}
.stmt{white-space:pre-wrap;font-size:13px;color:#333;background:#fafafa}
.field{margin-bottom:6px}
.field b{color:#555}
.canon{background:#eaf6ea;font-weight:bold;padding:8px;border:1px solid #9c9}
h2{margin-top:36px;font-size:16px}
</style></head><body>
<h1>GLM-5.3-Flash против Terra (base) — 9 спорных задач слепого сравнения</h1>
<p style="color:#777;font-size:12px">Колонки подписаны честно — скрывать уже нечего.
Под каждой парой — эталонная тема владельца.</p>
"""]
        for pid, canonical in DISPUTED_ANSWER_KEY.items():
            problem = problems_by_id.get(pid)
            base = base_fields.get(pid, {})
            row = by_pid.get(pid)
            glm = dict(blind.column_cells(row)) if row and 'call2' in row else {}
            parts.append('<h2>Задача #%d</h2>' % pid)
            parts.append('<table><tr><th style="width:24%">Условие</th>'
                         '<th>Terra (base)</th><th>GLM-5.3-Flash</th></tr><tr>')
            if problem:
                text = problem_full_text(problem.statement, problem.parts.all())
                parts.append('<td class="stmt">%s</td>' % html.escape(text[:1200]))
            else:
                parts.append('<td>—</td>')
            for cells in (base, glm):
                body = ''.join(
                    '<div class="field"><b>%s:</b> %s</div>'
                    % (name, html.escape(str(cells.get(name) or '—')))
                    for name in FIELD_ORDER)
                parts.append('<td>%s</td>' % body)
            parts.append('</tr></table>')
            parts.append('<p class="canon">Эталон владельца: %s</p>' % html.escape(canonical))
        parts.append('</body></html>')

        Path(REPORT_HTML).parent.mkdir(parents=True, exist_ok=True)
        with open(REPORT_HTML, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(parts))
        self.stdout.write('')
        self.stdout.write('Страница: %s' % REPORT_HTML)
