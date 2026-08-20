# -*- coding: utf-8 -*-
"""Фаза 5: проверка, что бракованное и непросмотренное не выходит наружу.

Проверяем ИСПОЛНЕНИЕМ, а не чтением кода: каждая поверхность выдачи спрашивается
по-настоящему, и в её ответе ищутся задачи, которых там быть не должно.

⚠️ Два правила, без которых прибор врёт (оба уже поймали себя на этой сессии):
1. Пустой ответ НИЧЕГО НЕ ДОКАЗЫВАЕТ. Поверхность, отдавшая ноль задач, помечается
   «не измерено», а не «чисто»: чистой она выглядит и когда сломана.
2. Проверяется КОНКРЕТНЫЙ код ответа, а не «не 200». Первая версия засчитала 400
   от ALLOWED_HOSTS за «задача закрыта» — закрыт был весь сайт.
"""
import os, sys, django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.conf import settings
if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

import logging
logging.disable(logging.ERROR)
from django.test import Client
from django.test.utils import setup_test_environment
# ⚠️ Без этого response.context остаётся None, и любая проверка контекста
# «проходит» на пустоте: сигнал отрисовки шаблона иначе не подключён.
setup_test_environment()
from problems.models import Problem

APPROVED = Problem.HumanReview.APPROVED
bad_ids = set(Problem.objects.exclude(human_review=APPROVED).values_list('id', flat=True))
ok_ids  = set(Problem.objects.filter(human_review=APPROVED).values_list('id', flat=True))
print(f"одобрено человеком: {len(ok_ids)}   всё остальное: {len(bad_ids)}\n")

results = []
def check(name, got_ids, note=''):
    got = list(got_ids)
    leaked = sorted(set(got) & bad_ids)
    if not got:
        results.append((name, 0, None, 'НЕ ИЗМЕРЕНО: поверхность отдала ноль задач'))
        print(f"  {name:<44} отдало {0:>6}  ??? НЕ ИЗМЕРЕНО — пустой ответ не доказательство")
        return
    results.append((name, len(got), len(leaked), note))
    print(f"  {name:<44} отдало {len(got):>6}  "
          f"{'ЧИСТО' if not leaked else f'!!! УТЕЧКА {len(leaked)}: {leaked[:5]}'}")

page_fail = []
c = Client()

print("=== 1. КАТАЛОГ (живой запрос) ===")
r = c.get('/catalog/')
print(f"  /catalog/ код ответа: {r.status_code}")
ctx = r.context or {}
cards = ctx.get('cards') or []
CATALOG_TOTAL = ctx.get('total')
check('каталог, первая страница', [getattr(x, 'id', None) or x['problem'].id for x in cards])
print(f"  счётчик каталога: {CATALOG_TOTAL}")
if CATALOG_TOTAL != len(ok_ids):
    page_fail.append(('каталог', CATALOG_TOTAL, f'счётчик не равен числу одобренных {len(ok_ids)}'))

print("\n=== 2. СТРАНИЦА ЗАДАЧИ ПО ПРЯМОМУ АДРЕСУ ===")
sample_bad = sorted(Problem.objects.filter(human_review='defect').values_list('id', flat=True))[:3]
sample_unseen = sorted(Problem.objects.filter(human_review='', status='published',
                                              needs_quality_review=False)
                       .values_list('id', flat=True))[:2]
sample_ok = sorted(ok_ids)[:2]
for pid, kind, want in ([(p, 'брак', (404, 403)) for p in sample_bad]
                        + [(p, 'не смотрели', (404, 403)) for p in sample_unseen]
                        + [(p, 'одобрена', (200,)) for p in sample_ok]):
    code = c.get(f'/catalog/problem/{pid}/').status_code
    good = code in want
    if not good:
        page_fail.append((pid, code, f'{kind}: ожидался {want}'))
    print(f"  задача {pid:<6} ({kind:<12}): код {code}  "
          f"{'как надо' if good else f'!!! ожидался {want}'}")

print("\n=== 3. СЛУЧАЙНАЯ ЗАДАЧА (30 бросков) ===")
rnd = []
for _ in range(30):
    rr = c.get('/catalog/random/', follow=True)
    if rr.redirect_chain:
        tail = rr.redirect_chain[-1][0].rstrip('/').rsplit('/', 1)[-1]
        if tail.isdigit():
            rnd.append(int(tail))
check('случайная задача', rnd)

print("\n=== 4. СЛОВЕСНЫЙ ПОИСК (гибрид) ===")
from catalog import hybrid
res = hybrid.lexical_search('спрос и предложение равновесие', limit=200)
check('lexical_search', list(res[0] if isinstance(res, tuple) else res))

print("\n=== 5. СМЫСЛОВОЙ ПОИСК: индекс эмбеддингов ===")
from catalog import semantic
semantic.invalidate_index()
idx = semantic._build_index()
check('индекс smart-search', list(idx['ids']))

print("\n=== 6. ЭКСПОРТ ПОДБОРКИ В LaTeX ===")
# В боевую базу не пишем: берём ТОТ ЖЕ фильтр, что стоит в generate_latex
# (catalog/latex_export.py), и даём ему заведомо смешанный набор.
mixed = list(sample_bad) + list(sample_unseen) + list(sample_ok)
got = list(Problem.objects.filter(id__in=mixed, needs_quality_review=False,
                                  hidden_pending_review=False)
           .values_list('id', flat=True))
check('фильтр generate_latex', got, f'на вход подано {len(mixed)}')
if len(got) != len(sample_ok):
    page_fail.append(('экспорт', len(got), f'ожидалось ровно {len(sample_ok)} одобренных'))

print("\n=== 7. ПОДБОР ДОМАШКИ ===")
from problems import hw_generator
rows = [{'query': 'спрос и предложение', 'count': 40, 'topic': None,
         'difficulty': None, 'kind': None}]
# find_problems возвращает КОРТЕЖ (найденное, недобор) — не список.
picked = hw_generator.find_problems(rows)
found = picked[0] if isinstance(picked, tuple) else picked
ids = []
for item in (found or []):
    if isinstance(item, dict):
        p = item.get('problem', item)
        ids.append(getattr(p, 'id', p if isinstance(p, int) else None))
    else:
        ids.append(getattr(item, 'id', item))
ids = [i for i in ids if isinstance(i, int)]
check('hw_generator.find_problems', ids)

print("\n" + "=" * 82)
leaks    = [r for r in results if r[2]]
unmeas   = [r for r in results if r[2] is None]
print(f"поверхностей опрошено: {len(results)}   с утечкой: {len(leaks)}   не измерено: {len(unmeas)}")
for r in unmeas:
    print(f"  ??? {r[0]}: {r[3]}")
for pid, code, why in page_fail:
    print(f"  !!! {pid}: {code} — {why}")
ok = not leaks and not unmeas and not page_fail
print("ВЕРДИКТ:", "наружу выходит только одобренное человеком" if ok else "!!! ЕСТЬ ЗАМЕЧАНИЯ !!!")
sys.exit(0 if ok else 1)
