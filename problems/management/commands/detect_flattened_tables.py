# -*- coding: utf-8 -*-
"""
Сессия H3, этап 6 — расплющенные/данные-таблицы: ТОЛЬКО детектор (прятать шлюзом).

Решение преподавателя: таблицы пока НЕ восстанавливаем. Команда собирает ЕДИНЫЙ
консолидированный список id таблиц и пишет его в
  reports/quality_audit/06_flattened_tables_ids.txt   (читает quality_gate)
  reports/sessionH3/06_flattened_tables_ids.txt        (отчёт H3, копия)

Список = свежий скан ∪ три исторических файла:
  flattened_table_ids.txt (detect_junk), tabular_data_tables_ids.txt
  (fix_tabular_variants), data_tables_gate_ids.txt (сессия H). Так quality_gate
  читает ОДИН файл-суперсет вместо трёх (consolidation, без потери id).

Свежий скан: поле содержит `\\begin{tabular}` (KaTeX не рендерит — где угодно)
ИЛИ «&» вне математики (строки таблицы).

Запуск: ./venv/bin/python manage.py detect_flattened_tables
Регенерировать список перед шлюзом, затем: quality_gate --apply.
"""
import os
import re

from django.core.management.base import BaseCommand

from problems.models import Problem, ProblemPart

QA = 'reports/quality_audit'
H3 = 'reports/sessionH3'
OUT = '06_flattened_tables_ids.txt'
LEGACY = ('flattened_table_ids.txt', 'tabular_data_tables_ids.txt',
          'data_tables_gate_ids.txt')

MATH = re.compile(
    r'\$\$.*?\$\$|\$[^$\n]*\$|\\\[.*?\\\]|\\\(.*?\\\)'
    r'|\\begin\{(?:align|equation|aligned|array|matrix|cases|gather|pmatrix'
    r'|bmatrix|vmatrix)\*?\}.*?\\end\{(?:align|equation|aligned|array|matrix'
    r'|cases|gather|pmatrix|bmatrix|vmatrix)\*?\}',
    re.DOTALL)
TABULAR = re.compile(r'\\begin\{tabular\}')
AMP = re.compile(r'(?<!\\)&')


def is_table_field(text):
    if not text:
        return False
    if TABULAR.search(text):              # KaTeX не рендерит tabular
        return True
    return bool(AMP.search(MATH.sub(' ', text)))   # & вне математики


def load_ids(path):
    if not os.path.exists(path):
        return set()
    out = set()
    for ln in open(path, encoding='utf-8'):
        ln = ln.strip()
        if ln and not ln.startswith('#'):
            try:
                out.add(int(ln.split('\t')[0]))
            except ValueError:
                pass
    return out


class Command(BaseCommand):
    help = 'H3 этап 6: консолидированный список расплющенных таблиц для шлюза'

    def handle(self, *args, **o):
        os.makedirs(H3, exist_ok=True)
        # свежий скан
        fresh = set()
        for p in Problem.objects.all().only('id', 'statement', 'answer',
                                            'solution'):
            for fld in ('statement', 'answer', 'solution'):
                if is_table_field(getattr(p, fld)):
                    fresh.add(p.id)
                    break
        for pt in ProblemPart.objects.all().only('id', 'problem_id',
                                                 'statement', 'answer'):
            for fld in ('statement', 'answer'):
                if is_table_field(getattr(pt, fld)):
                    fresh.add(pt.problem_id)
                    break

        legacy = set()
        for f in LEGACY:
            legacy |= load_ids(os.path.join(QA, f))

        union = fresh | legacy
        new_only = fresh - legacy

        header = (f'# Консолидированный список расплющенных/данных-таблиц (H3 этап 6).\n'
                  f'# Объединение: свежий скан ({len(fresh)}) ∪ 3 файла '
                  f'({len(legacy)}) = {len(union)}. Новых из свежего скана: '
                  f'{len(new_only)}.\n'
                  f'# Решение преподавателя: таблицы НЕ восстанавливаем — '
                  f'только скрыть шлюзом.\n')
        body = '\n'.join(map(str, sorted(union))) + '\n'
        for d in (QA, H3):
            with open(os.path.join(d, OUT), 'w', encoding='utf-8') as fh:
                fh.write(header + body)

        vis = Problem.objects.filter(
            id__in=union, status='published',
            needs_quality_review=False).count()
        self.stdout.write(self.style.SUCCESS(
            f'Свежий скан: {len(fresh)} | 3 файла: {len(legacy)} | '
            f'объединение: {len(union)} (новых: {len(new_only)}).'))
        self.stdout.write(f'Сейчас видимых среди них: {vis}.')
        self.stdout.write(f'Записано: {QA}/{OUT} и {H3}/{OUT}.')
