# -*- coding: utf-8 -*-
"""
Сессия H3, этап 3 — невытащенные ДЛИННЫЕ варианты в подпункты.

Продолжение fix_merged_variants (сессия G) для случаев, что G не ловит: G требует
расстояние первый→последний маркер ≤400 и каждый спан ≤120 (короткие MCQ). Здесь
спаны МОГУТ быть длинными (подпункты-подзадачи), разделённые \\n\\n.

Условия срабатывания (все обязательны):
  1. У задачи НЕТ ни одного ProblemPart.
  2. В statement есть кириллические маркеры В НАЧАЛЕ СТРОКИ (^\\s*[абвгде]\\)).
  3. Эти маркеры образуют РОВНО ОДИН чистый префикс-ран: «абв», «абвг», «абвгд»
     или «абвгде» — каждая буква один раз, по порядку, без повторов и лишних.
     (Защита от мульти-вопросов «1…а)б)в) 2…а)б)в)»: там «а» повторяется → skip.)
  4. Тело (текст до первого маркера) ≥ 15 символов (есть общее условие-стем).
  5. Каждый спан-вариант ≥ 3 символов после strip.

Каждый спан от маркера до следующего → отдельный ProblemPart (label «а)»…),
тело остаётся в Problem.statement как общее условие.

Латинские a)/b)/c) НЕ трогаем (в сессии F уже сконвертированы в кириллицу для
#14; в других источниках — отдельный разбор).

Запуск:
  ./venv/bin/python manage.py fix_long_variants                 # = dry-run, 15 примеров
  ./venv/bin/python manage.py fix_long_variants --apply
Флаги: --source-id N, --examples N, --limit N.
"""
import os
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart

CHANGED_IDS_FILE = 'reports/sessionH3/changed_ids_H3.txt'
EXPECTED = 'абвгде'
# маркер В НАЧАЛЕ СТРОКИ: начало строки, опц. пробелы, буква, ')'
LINE_MARKER = re.compile(r'(?m)^[ \t]*([абвгде])\)')


def find_long_variant(problem):
    """Возвращает dict {body, spans:[(label,content)]} или None."""
    stmt = problem.statement or ''
    if len(stmt) < 25:
        return None
    if problem.parts.exists():
        return None

    markers = [(m.group(1), m.start(), m.end()) for m in LINE_MARKER.finditer(stmt)]
    if len(markers) < 3 or len(markers) > 6:
        return None

    letters = [m[0] for m in markers]
    # Условие 3: ровно чистый префикс-ран абв(где), каждая по разу, по порядку
    if letters != list(EXPECTED[:len(letters)]):
        return None

    # тело — до первого маркера
    first_start = markers[0][1]
    body = stmt[:first_start].rstrip()
    if len(body) < 15:                       # условие 4: есть общий стем
        return None

    # спаны: от конца метки 'X)' до начала следующего маркера / конца
    spans = []
    for i, (letter, ms, me) in enumerate(markers):
        end = markers[i + 1][1] if i + 1 < len(markers) else len(stmt)
        content = stmt[me:end].strip()
        content = content.replace('﻿', '').replace('​', '').strip()
        if len(content) < 3:                 # условие 5
            return None
        spans.append((letter + ')', content))
    return {'body': body, 'spans': spans}


class Command(BaseCommand):
    help = 'H3 этап 3: длинные слитые варианты а)/б)/в) → ProblemPart'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--source-id', type=int, default=None)
        parser.add_argument('--examples', type=int, default=15)
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **o):
        os.makedirs('reports/sessionH3', exist_ok=True)
        qs = Problem.objects.prefetch_related('parts').only(
            'id', 'statement', 'problem_type')
        if o['source_id']:
            qs = qs.filter(source_references__source_id=o['source_id']).distinct()
        if o['limit']:
            qs = qs[:o['limit']]

        candidates = []
        for p in qs.iterator(chunk_size=1000):
            c = find_long_variant(p)
            if c:
                candidates.append((p, c))

        self.stdout.write(f'Кандидатов: {len(candidates)}')

        n = o['examples']
        for p, c in candidates[:n]:
            self.stdout.write(f'--- #{p.id} (тело {len(c["body"])} симв., '
                              f'{len(c["spans"])} вариантов) ---')
            self.stdout.write(f'  ТЕЛО: {c["body"][:160]!r}')
            for lbl, content in c['spans']:
                self.stdout.write(f'    {lbl} {content[:90]!r}')

        if not o['apply']:
            self.stdout.write(self.style.WARNING(
                f'\n[dry-run] {len(candidates)} задач будут разбиты. '
                f'Для применения: --apply'))
            return

        changed = []
        errors = 0
        for p, c in candidates:
            try:
                with transaction.atomic():
                    p.statement = c['body']
                    # тип теста — если все спаны короткие (≤40)
                    TEST = {'тест: один ответ', 'тест: все верные',
                            'тест: верно/неверно'}
                    if p.problem_type not in TEST and \
                       all(len(x[1]) <= 40 for x in c['spans']):
                        p.problem_type = 'тест: один ответ'
                    p.save(update_fields=['statement', 'problem_type'])
                    for order, (lbl, content) in enumerate(c['spans'], 1):
                        ProblemPart.objects.create(
                            problem=p, label=lbl, statement=content, order=order)
                changed.append(p.id)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Ошибка #{p.id}: {e}'))
                errors += 1

        if changed:
            with open(CHANGED_IDS_FILE, 'a', encoding='utf-8') as f:
                f.write('\n'.join(map(str, changed)) + '\n')
        self.stdout.write(self.style.SUCCESS(
            f'Изменено: {len(changed)} задач, ошибок: {errors}. '
            f'id → {CHANGED_IDS_FILE}'))
