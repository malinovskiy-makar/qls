# -*- coding: utf-8 -*-
"""Фаза 5: список «идеальных» задач МатЭка, которые держат ту же подозрительную
форму, что и бракованные («решение притворяется подпунктами»).

Вердикт «идеально» с них НЕ снимается: шесть вопросов у задачи бывают законно, а
форма — признак НЕОБХОДИМЫЙ, но не достаточный (докстринг matek_zero_step).
Список нужен, чтобы вернуться к этим задачам при сверке с авторскими .tex.
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from problems.models import Problem
from problems.management.commands.matek_zero_step import shape_ok, parts_of

OUT = 'reports/anich_merge_20260820/matek_form_approved_ids.txt'
SOURCE_ID = 13

qs = (Problem.objects
      .filter(source_references__source_id=SOURCE_ID)
      .distinct()
      .prefetch_related('parts'))

buckets = {'approved': [], 'defect': [], '': []}
for p in qs:
    if shape_ok(parts_of(p)):
        buckets[p.human_review].append(p.id)

for k, label in (('approved', 'вердикт «идеально»'), ('defect', 'вердикт «брак»'), ('', 'вердикта нет')):
    print(f"  форма «подряд, чётное число меток», {label:<22} {len(buckets[k])}")
print(f"  всего задач МатЭка: {qs.count()}")

ids = sorted(buckets['approved'])
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write("# Задачи МатЭка (источник 13) с вердиктом «идеально», которые держат\n")
    f.write("# ту же форму, что и бракованные: метки подряд с «а», чётное число, >= 4.\n")
    f.write("# Форма — признак НЕОБХОДИМЫЙ, но НЕ достаточный: шесть вопросов у задачи\n")
    f.write("# бывают законно. Вердикт «идеально» с них НЕ снят и снимать его нельзя\n")
    f.write("# без сверки с авторским .tex. Список — чтобы вернуться к ним на сверке.\n")
    f.write(f"# Снято {len(ids)} задач, 2026-08-20.\n")
    for i in ids:
        f.write(f"{i}\n")
print(f"\n  список записан: {OUT} ({len(ids)} id)")
