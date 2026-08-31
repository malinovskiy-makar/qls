# -*- coding: utf-8 -*-
"""Фаза 2 (Б4-2, 31.08.2026): перезамер на 20 задачах после диеты префикса.

⚠️ ОГОВОРКА ЧЕСТНОСТИ. Промпт просил сравнить с ответами прогона Б4 —
«они сохранены». Не сохранены: журнал `pilot_b4_measurement.py::cmd_sync`
писал только счётчики токенов, не сам ответ модели (`reply.text`).
Чинить это задним числом для Б4 нельзя — 100 запросов уже оплачены и
переигрывать их ради одного забытого поля дорого и бессмысленно.

Вместо этого здесь — ДВА свежих прогона на ОДНИХ И ТЕХ ЖЕ 20 задачах
(первые 20 id из выборки Б4, seed 20260831):
  - `new` — нынешняя схема (id вместо названий в enum), тот вариант, что
    пойдёт в прод;
  - `old` — схема с полными названиями в enum, ЯДРО ТО ЖЕ САМОЕ (дерево с
    подписанными id тегов — оно безвредно для схемы на названиях, id там
    просто не используется), собрана из `git show 0c5ff29:...` — версии
    ДО диеты, чтобы формулировки поля были согласованы со своей схемой
    (в текущем `prompts_v2.py` эти формулировки уже говорят
    «идентификатор», это сломало бы old-вариант).

Сравнение "new vs old" честнее по конструкции, чем "new vs Б4 (вчера,
другой процесс, тот же код)": оба прогона видят один и тот же случайный
шум модели в одном и том же временном окне, различается только форма
enum схемы — ровно то, что проверяем.

Запуск:
    venv313\\Scripts\\python.exe scripts\\pilot_b4_phase2_diet_check.py
"""
import json
import os
import subprocess
import sys
import time
import types
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django  # noqa: E402
django.setup()  # noqa: E402

from django.conf import settings  # noqa: E402
from django.test import override_settings  # noqa: E402

from problems.ai import providers  # noqa: E402
from problems.enrich import prompts_v2 as new_prompts  # noqa: E402
from problems.enrich import taxonomy  # noqa: E402
from problems.enrich.text import problem_full_text  # noqa: E402
from problems.enrich.shortlist import shortlist_for  # noqa: E402
from problems.management.commands.pilot_enrich_v2 import real_call_cost  # noqa: E402
from problems.models import Problem  # noqa: E402

TERRA = 'gpt-5.6-terra'
N = 20
OLD_COMMIT = '0c5ff29'
OUT_DIR = Path('reports/pilot_b4')
OUT_PATH = OUT_DIR / 'phase2_diet_check.json'


def load_old_module():
    """Версия `prompts_v2.py` ДО диеты (полные названия в enum), взятая из
    коммита-чекпоинта — формулировки полей там согласованы со своей схемой.
    """
    src = subprocess.check_output(
        ['git', 'show', '%s:problems/enrich/prompts_v2.py' % OLD_COMMIT])
    module = types.ModuleType('prompts_v2_old_b4')
    exec(compile(src, 'prompts_v2_old_b4', 'exec'), module.__dict__)
    return module


def load_20_ids():
    with open(OUT_DIR / 'sample.json', encoding='utf-8') as fh:
        payload = json.load(fh)
    return payload['ids_in_order'][:N]


def run_variant(label, core, schema, user_text_fn, problems, shortlists):
    provider = providers.OpenAIProvider()
    max_tokens = getattr(settings, 'AI_MAX_TOKENS', 4000)
    rows = []
    spent = Decimal('0')
    with override_settings(AI_REASONING_EFFORT='none'):
        for i, problem in enumerate(problems, start=1):
            text = problem_full_text(problem.statement, problem.parts.all())
            user1 = user_text_fn(text, shortlists.get(problem.id))
            t0 = time.perf_counter()
            error = None
            reply = None
            try:
                reply = provider.complete([core], user1, schema, TERRA, max_tokens)
            except providers.ProviderError as exc:
                error = str(exc)
            elapsed = time.perf_counter() - t0

            row = {'problem_id': problem.id, 'elapsed_sec': elapsed}
            if reply is not None:
                cost = real_call_cost(TERRA, reply)
                spent += cost
                schema_ok = True
                data = None
                try:
                    data = json.loads(reply.text)
                except ValueError:
                    schema_ok = False
                row.update({
                    'data': data,
                    'input_tokens': reply.input_tokens,
                    'cached_tokens': reply.cache_read_tokens,
                    'cache_write_tokens': reply.cache_write_tokens,
                    'output_tokens': reply.output_tokens,
                    'schema_ok': schema_ok,
                    'cost_usd': str(cost),
                    'error': None,
                })
            else:
                row.update({'data': None, 'schema_ok': False, 'error': error})
            rows.append(row)
            print('  [%s] #%2d id=%-6d cached=%-6s out=%-4s ok=%s $%.4f' % (
                label, i, problem.id, row.get('cached_tokens'),
                row.get('output_tokens'), row['schema_ok'], spent))
    return rows, spent


def main():
    ids = load_20_ids()
    problems_by_id = {p.id: p for p in Problem.objects.filter(id__in=ids).prefetch_related('parts')}
    problems = [problems_by_id[i] for i in ids if i in problems_by_id]
    shortlists = {p.id: shortlist_for(problem_full_text(p.statement, p.parts.all())) for p in problems}
    print('20 задач (первые из выборки Б4, seed 20260831):', [p.id for p in problems])

    new_core = new_prompts.call1_core(with_concepts=True)
    new_schema = new_prompts.call1_schema(with_concepts=True)

    old_module = load_old_module()
    old_core = old_module.call1_core(with_concepts=True)
    old_schema = old_module.call1_schema(with_concepts=True)

    print()
    print('=== NEW (id в enum) ===')
    new_rows, new_spent = run_variant('new', new_core, new_schema,
                                      new_prompts.call1_user_text, problems, shortlists)
    print()
    print('=== OLD (названия в enum, свежий базовый прогон) ===')
    old_rows, old_spent = run_variant('old', old_core, old_schema,
                                      old_module.call1_user_text, problems, shortlists)

    with open(OUT_PATH, 'w', encoding='utf-8') as fh:
        json.dump({'new_rows': new_rows, 'old_rows': old_rows,
                  'new_spent': str(new_spent), 'old_spent': str(old_spent)},
                 fh, ensure_ascii=False, indent=2)

    print()
    print('=== ИТОГ ===')
    print('new: потрачено $%.4f' % new_spent)
    print('old: потрачено $%.4f' % old_spent)
    print('Сохранено:', OUT_PATH)


if __name__ == '__main__':
    main()
