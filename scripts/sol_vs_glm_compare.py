# -*- coding: utf-8 -*-
"""Сравнение gpt-5.6-sol и GLM-5.3-Flash по полям — сессия 03.09.2026.

Обе модели прогнаны по ОДНОЙ выборке (`run300_sample_ids.json`, 300 задач)
ОДНИМИ ядрами промпта (отпечаток 197742d2a3f7) и с одинаковыми шорт-листами
понятий — совпадение входа доказано отдельно (см. отчёт сессии).

Читает:
  - GLM:  qls-models/reports/enrich_pilot/run300_parsed.jsonl  (ТОЛЬКО ЧТЕНИЕ)
  - sol:  reports/enrich_pilot/sol300_parsed.jsonl
  - check_type SolveHub: qls/materials/corpus_sources/solvehub/problems/*.json

Пишет `reports/enrich_pilot/sol_vs_glm_fields.md` и печатает то же самое.

⚠️ ЦЕНА СЧИТАЕТСЯ ПО ТАРИФУ ЯВНО, а не через `pilot.real_call_cost`. У
OpenAI поле `cache_write_tokens` приходит равным свежему входу, и общая
формула (она рассчитана на Anthropic, где запись в кэш — отдельная
платная операция) взяла бы за свежий вход дважды: $4 плюс $4×1.25. У GLM
это поле всегда 0, надбавки нет — и сравнение цены «как есть» оказалось бы
не сравнением моделей, а сравнением артефактов учёта.
"""
import glob
import json
import os
import statistics
import sys
from collections import Counter
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from problems.enrich import taxonomy  # noqa: E402
from problems.models import SourceReference  # noqa: E402

GLM_PARSED = Path(
    r'C:\Users\shipu\qls-models\reports\enrich_pilot\run300_parsed.jsonl')
GLM_METRICS = Path(
    r'C:\Users\shipu\qls-models\reports\enrich_pilot\run300_metrics.json')
SOL_PARSED = Path('reports/enrich_pilot/sol300_parsed.jsonl')
SOL_METRICS = Path('reports/enrich_pilot/sol300_metrics.json')
SOLVEHUB_DIR = Path(r'C:\Users\shipu\qls\materials\corpus_sources\solvehub\problems')
OUT_MD = Path('reports/enrich_pilot/sol_vs_glm_fields.md')

SOLVEHUB_SOURCE = 'SolveHub — банк задач по экономике'

#: Тарифы за миллион токенов: (вход, кэшированный вход, выход).
#: GLM — промо-скидка 50 %, по которой прогон и был оплачен.
PRICES = {
    'glm': (0.075, 0.015, 0.25),
    'sol': (4.00, 0.40, 20.00),
}

#: Пропускная способность, замеренная контрольными строками прогонов:
#: (задач в минуту, одновременных запросов). GLM — `battle_run.log`
#: боевого прогона (последние строки: 99,5 / 108,8 / 116,0 задач/мин на
#: 50 потоках), sol — контрольные строки этой сессии (22,2-23,7 на 10).
#: ⚠️ Сравнивать «задач в минуту» напрямую нельзя: это свойство ЛИМИТА
#: поставщика, а не модели. Сравнимая величина — секунды на задачу на
#: ОДИН поток, она и считается ниже.
THROUGHPUT = {'glm': (116.0, 50), 'sol': (23.7, 10)}

#: problem_type ← check_type SolveHub (prompts_v2, шапка PROBLEM_TYPE).
CHECK_TYPE_MAP = {
    'single_choice': 'единственный_выбор',
    'multiple_choice': 'множественный_выбор',
    'true_false': 'верно_неверно',
    'matching_list': 'сопоставление',
    'single_freetext': 'открытый_ответ',
    'uncheckable': 'открытый_ответ',
    'multiple_questions': 'несколько_подвопросов',
}


def load(path):
    return {r['problem_id']: r
            for r in (json.loads(line) for line in
                      open(path, encoding='utf-8') if line.strip())}


def has_digit(text):
    return any(ch.isdigit() for ch in (text or ''))


def pct(part, whole):
    return (part / whole * 100) if whole else 0.0


def p95(values):
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def cost_by_tariff(usage, tariff):
    """Цена по трём ценам тарифа. `cache_write_tokens` НЕ тарифицируется —
    в прайсе владельца такой строки нет (см. шапку модуля)."""
    price_in, price_cache, price_out = tariff
    return (usage['input_tokens'] * price_in
            + usage['cache_read_tokens'] * price_cache
            + usage['output_tokens'] * price_out) / 1e6


def solvehub_check_types(ids):
    """`{problem_id: check_type}` для задач выборки, пришедших из SolveHub."""
    hash_by_pid = dict(
        SourceReference.objects
        .filter(problem_id__in=list(ids), source__name=SOLVEHUB_SOURCE)
        .exclude(problem_number='')
        .values_list('problem_id', 'problem_number'))
    if not hash_by_pid:
        return {}
    wanted = set(hash_by_pid.values())
    by_hash = {}
    for path in glob.glob(str(SOLVEHUB_DIR / '*.json')):
        try:
            raw = json.load(open(path, encoding='utf-8'))
        except Exception:
            continue
        external = str(raw.get('hash') or '')
        if external in wanted:
            by_hash[external] = raw.get('check_type')
    return {pid: by_hash[h] for pid, h in hash_by_pid.items() if h in by_hash}


def field_stats(rows):
    """Все числа одной модели по разобранным строкам."""
    n = len(rows)
    ok = [r for r in rows if not r.get('defect')]
    st = {'n': n, 'n_ok': len(ok)}

    st['topic_dist'] = Counter(r['topic_primary'] for r in rows if r.get('topic_primary'))
    sec = [r.get('topics_secondary') or [] for r in rows]
    st['sec_nonempty_pct'] = pct(sum(1 for s in sec if s), n)
    st['sec_mean'] = statistics.mean([len(s) for s in sec]) if sec else 0

    tags = [r.get('tags') or [] for r in rows]
    st['tags_mean'] = statistics.mean([len(t) for t in tags]) if tags else 0
    st['tags_one_pct'] = pct(sum(1 for t in tags if len(t) == 1), n)
    st['tags_unique'] = len({t for lst in tags for t in lst})

    concepts = [r.get('econ_concepts') or [] for r in rows]
    st['concepts_mean'] = statistics.mean([len(c) for c in concepts]) if concepts else 0
    st['offlist_pct'] = pct(sum(1 for r in rows if r.get('concepts_offlist')), n)

    for field in ('given', 'find'):
        vals = [r.get(field) or '' for r in rows]
        lens = [len(v) for v in vals if v]
        st['%s_median' % field] = statistics.median(lens) if lens else 0
        st['%s_p95' % field] = p95(lens)
        st['%s_digit_pct' % field] = pct(sum(1 for v in vals if has_digit(v)), n)

    st['type_dist'] = Counter(r['problem_type'] for r in rows if r.get('problem_type'))
    st['difficulty_dist'] = Counter(
        r['difficulty'] for r in rows if r.get('difficulty') is not None)

    titles = [(r.get('title_candidate') or '').strip() for r in rows]
    st['title_long_pct'] = pct(sum(1 for t in titles if len(t) > 40), n)
    top = Counter(t for t in titles if t).most_common(1)
    st['title_top'] = top[0] if top else ('—', 0)

    queries = [r.get('search_queries') or [] for r in rows]
    st['queries_mean'] = statistics.mean([len(q) for q in queries]) if queries else 0
    st['queries_digit_pct'] = pct(sum(1 for r in rows if r.get('dropped_queries')), n)

    st['defect_pct'] = pct(sum(1 for r in rows if r.get('defect')), n)
    st['retried_pct'] = pct(
        sum(1 for r in rows if r.get('call1_retried') or r.get('call2_retried')), n)
    return st


def agreement(a_rows, b_rows, field, ids):
    """Доля задач, где обе модели дали одно и то же значение поля."""
    same = sum(1 for i in ids if a_rows[i].get(field) == b_rows[i].get(field))
    return pct(same, len(ids))


def main():
    glm = load(GLM_PARSED)
    sol = load(SOL_PARSED)
    ids = sorted(set(glm) & set(sol))
    out = []

    def say(line=''):
        out.append(line)
        print(line)

    say('# gpt-5.6-sol против GLM-5.3-Flash: поле за полем')
    say()
    say('Выборка: %d задач в обеих моделях (GLM %d, sol %d, пересечение %d).'
        % (len(ids), len(glm), len(sol), len(ids)))
    say('Ядра промпта одинаковые (отпечаток `197742d2a3f7`), шорт-листы '
        'понятий одинаковые, картинки уходили тем же путём.')
    say()
    say('⚠️ Условия НЕ полностью равные, и это надо держать в голове при '
        'чтении любой строки ниже:')
    say('уровень рассуждения у sol — `medium` (указание владельца), у GLM — '
        '`low`; у sol включена строгая схема (`json_schema`, `strict`), '
        'у Z.AI её нет вовсе. Наши собственные проверки при этом одни и те же.')
    say()

    g = field_stats([glm[i] for i in ids])
    s = field_stats([sol[i] for i in ids])

    say('## Тема (`topic_primary`)')
    say()
    say('| | GLM | sol |')
    say('|---|---|---|')
    say('| разных тем использовано | %d из 29 | %d из 29 |'
        % (len(g['topic_dist']), len(s['topic_dist'])))
    say('| самая частая тема | %s (%d) | %s (%d) |'
        % (g['topic_dist'].most_common(1)[0] + s['topic_dist'].most_common(1)[0]))
    say()
    say('**Модели согласны по теме в %.1f %% задач** (%d из %d).'
        % (agreement(glm, sol, 'topic_primary', ids),
           round(agreement(glm, sol, 'topic_primary', ids) * len(ids) / 100), len(ids)))
    say()
    say('Распределение по темам (задач):')
    say()
    say('| id | тема | GLM | sol |')
    say('|---|---|---|---|')
    for tid in sorted(set(g['topic_dist']) | set(s['topic_dist']),
                      key=lambda x: -(g['topic_dist'].get(x, 0) + s['topic_dist'].get(x, 0))):
        try:
            name = taxonomy.theme_name_from_id(tid)
        except KeyError:
            name = '(неизвестный id)'
        say('| %s | %s | %d | %d |' % (tid, name, g['topic_dist'].get(tid, 0),
                                       s['topic_dist'].get(tid, 0)))
    say()

    say('## Остальные поля')
    say()
    say('| поле | что считаем | GLM | sol |')
    say('|---|---|---|---|')
    rows = [
        ('`topics_secondary`', 'доля непустых', '%.1f %%' % g['sec_nonempty_pct'],
         '%.1f %%' % s['sec_nonempty_pct']),
        ('`topics_secondary`', 'среднее число тем', '%.2f' % g['sec_mean'],
         '%.2f' % s['sec_mean']),
        ('`tags`', 'среднее число тегов', '%.2f' % g['tags_mean'], '%.2f' % s['tags_mean']),
        ('`tags`', 'доля ровно с 1 тегом', '%.1f %%' % g['tags_one_pct'],
         '%.1f %%' % s['tags_one_pct']),
        ('`tags`', 'уникальных тегов на выборку', '%d' % g['tags_unique'],
         '%d' % s['tags_unique']),
        ('`econ_concepts`', 'среднее число', '%.2f' % g['concepts_mean'],
         '%.2f' % s['concepts_mean']),
        ('`econ_concepts`', 'доля с непустым `concepts_offlist`',
         '%.1f %%' % g['offlist_pct'], '%.1f %%' % s['offlist_pct']),
        ('`given`', 'медиана длины', '%.0f' % g['given_median'], '%.0f' % s['given_median']),
        ('`given`', '95-й процентиль длины', '%d' % g['given_p95'], '%d' % s['given_p95']),
        ('`given`', 'доля с цифрами (нарушение §12.3)',
         '%.1f %%' % g['given_digit_pct'], '%.1f %%' % s['given_digit_pct']),
        ('`find`', 'медиана длины', '%.0f' % g['find_median'], '%.0f' % s['find_median']),
        ('`find`', '95-й процентиль длины', '%d' % g['find_p95'], '%d' % s['find_p95']),
        ('`find`', 'доля с цифрами (нарушение §12.3)',
         '%.1f %%' % g['find_digit_pct'], '%.1f %%' % s['find_digit_pct']),
        ('`title_candidate`', 'доля длиннее 40 символов',
         '%.1f %%' % g['title_long_pct'], '%.1f %%' % s['title_long_pct']),
        ('`title_candidate`', 'самый частый заголовок',
         '«%s» ×%d' % g['title_top'], '«%s» ×%d' % s['title_top']),
        ('`search_queries`', 'среднее число запросов', '%.2f' % g['queries_mean'],
         '%.2f' % s['queries_mean']),
        ('`search_queries`', 'доля задач, где модель написала запрос с цифрой',
         '%.1f %%' % g['queries_digit_pct'], '%.1f %%' % s['queries_digit_pct']),
    ]
    for row in rows:
        say('| %s | %s | %s | %s |' % row)
    say()

    say('## `problem_type`')
    say()
    say('| значение | GLM | sol |')
    say('|---|---|---|')
    for key in sorted(set(g['type_dist']) | set(s['type_dist'])):
        say('| %s | %d | %d |' % (key, g['type_dist'].get(key, 0),
                                  s['type_dist'].get(key, 0)))
    say()
    say('Модели согласны по `problem_type` в %.1f %% задач.'
        % agreement(glm, sol, 'problem_type', ids))
    say()

    checks = solvehub_check_types(ids)
    say('### Сверка с `check_type` SolveHub')
    say()
    if not checks:
        say('Задач SolveHub в выборке не нашлось — сверять не с чем.')
    else:
        say('Задач SolveHub в выборке: **%d**. Совпадение считается по '
            'каждому подтипу отдельно — усреднённая цифра прячет то, ради '
            'чего сверка и делается.' % len(checks))
        say()
        say('| `check_type` | ожидаемый `problem_type` | задач | GLM совпало | sol совпало |')
        say('|---|---|---|---|---|')
        by_type = {}
        for pid, ct in checks.items():
            by_type.setdefault(ct, []).append(pid)
        for ct in sorted(by_type, key=lambda k: -len(by_type[k])):
            pids = by_type[ct]
            want = CHECK_TYPE_MAP.get(ct, '—')
            gh = sum(1 for p in pids if glm[p].get('problem_type') == want)
            sh = sum(1 for p in pids if sol[p].get('problem_type') == want)
            say('| %s | %s | %d | %d (%.0f %%) | %d (%.0f %%) |'
                % (ct, want, len(pids), gh, pct(gh, len(pids)), sh, pct(sh, len(pids))))
        total = len(checks)
        gh = sum(1 for p, ct in checks.items()
                 if glm[p].get('problem_type') == CHECK_TYPE_MAP.get(ct))
        sh = sum(1 for p, ct in checks.items()
                 if sol[p].get('problem_type') == CHECK_TYPE_MAP.get(ct))
        say('| **всего** | | **%d** | **%d (%.0f %%)** | **%d (%.0f %%)** |'
            % (total, gh, pct(gh, total), sh, pct(sh, total)))
    say()

    say('## `difficulty`')
    say()
    say('| балл | GLM | sol |')
    say('|---|---|---|')
    for level in (1, 2, 3, 4, 5):
        say('| %d | %d | %d |' % (level, g['difficulty_dist'].get(level, 0),
                                  s['difficulty_dist'].get(level, 0)))
    say('| не указана | %d | %d |'
        % (len(ids) - sum(g['difficulty_dist'].values()),
           len(ids) - sum(s['difficulty_dist'].values())))
    say()
    say('Модели ставят один и тот же балл в %.1f %% задач.'
        % agreement(glm, sol, 'difficulty', ids))
    say()

    say('## Техника')
    say()
    gm = json.load(open(GLM_METRICS, encoding='utf-8'))
    sm = json.load(open(SOL_METRICS, encoding='utf-8'))
    gu, su = gm['usage_totals'], sm['usage_totals']
    g_cost = cost_by_tariff(gu, PRICES['glm'])
    s_cost = cost_by_tariff(su, PRICES['sol'])
    say('| | GLM | sol |')
    say('|---|---|---|')
    say('| модель | glm-5.3-flash | gpt-5.6-sol |')
    say('| уровень рассуждения | low | medium |')
    say('| строгая схема на стороне API | нет | да |')
    say('| **не прошло наши проверки с первого раза** | **%.1f %%** | **%.1f %%** |'
        % (g['retried_pct'], s['retried_pct']))
    say('| **не прошло окончательно (брак после повтора)** | **%.1f %%** | **%.1f %%** |'
        % (g['defect_pct'], s['defect_pct']))
    say('| вход свежий, токенов на задачу | %.0f | %.0f |'
        % (gu['input_tokens'] / g['n'], su['input_tokens'] / s['n']))
    say('| вход из кэша, токенов на задачу | %.0f | %.0f |'
        % (gu['cache_read_tokens'] / g['n'], su['cache_read_tokens'] / s['n']))
    say('| выход, токенов на задачу | %.0f | %.0f |'
        % (gu['output_tokens'] / g['n'], su['output_tokens'] / s['n']))
    say('| из них рассуждение | %.0f | %.0f |'
        % (gu.get('reasoning_tokens', 0) / g['n'], su.get('reasoning_tokens', 0) / s['n']))
    say('| цена на задачу | $%.5f | $%.5f |' % (g_cost / g['n'], s_cost / s['n']))
    say('| цена за 300 задач | $%.2f | $%.2f |'
        % (g_cost / g['n'] * 300, s_cost / s['n'] * 300))
    grate, gw = THROUGHPUT['glm']
    srate, sw = THROUGHPUT['sol']
    say('| одновременных запросов | %d | %d |' % (gw, sw))
    say('| задач в минуту (это про лимит поставщика, не про модель) '
        '| %.1f | %.1f |' % (grate, srate))
    say('| **секунд на задачу на один поток** | **%.1f** | **%.1f** |'
        % (60 * gw / grate, 60 * sw / srate))
    say()
    say('Цена GLM — по промо-тарифу, которым прогон и был оплачен '
        '(вход $0,075 / кэш $0,015 / выход $0,25 за миллион, скидка 50 % '
        'до 09.09.2026). Без скидки цифру надо удвоить.')
    say()

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text('\n'.join(out) + '\n', encoding='utf-8')
    print()
    print('записано: %s' % OUT_MD)


if __name__ == '__main__':
    main()
