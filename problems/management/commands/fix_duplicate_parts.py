# -*- coding: utf-8 -*-
"""
Сессия H4, этап 3c — ДУБЛЬ подпунктов: текст подпунктов есть И в Problem.statement
(инлайн-маркеры (a)/(б)…), И отдельно в ProblemPart. На странице задачи это
показывается дважды. Убираем инлайн-копию из statement, оставляя ProblemPart.

Условия срабатывания (все обязательны):
  1. У задачи ≥2 ProblemPart с метками-буквами (a/б/в… или a/b/c…), чистый
     префикс-ран без пропусков.
  2. В statement находится маркер ПЕРВОГО подпункта `(a)`/`a)`/`(а)`/`а)` на
     позиции > 40 символов (есть содержательный стем-условие до него).
  3. От этого маркера до конца statement ВСЕ подпункты идут по порядку, и текст
     после каждого маркера по нормализованному префиксу (первые 20 символов)
     совпадает с соответствующим ProblemPart.statement.
  4. После обрезки (statement = до первого маркера) остаётся ≥40 символов.

Режем statement по позиции маркера первого подпункта. content_hash НЕ трогаем
(ProblemPart остаются — данные не теряются, только убирается визуальный дубль).

Запуск:
  ./venv/bin/python manage.py fix_duplicate_parts            # dry-run, 15 примеров
  ./venv/bin/python manage.py fix_duplicate_parts --apply
Флаги: --source-id N, --examples N, --limit N.
"""
import os
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem

CHANGED_IDS_FILE = 'reports/sessionH4/changed_ids_H4.txt'

# Эквивалентные буквы метки (кириллица ↔ латиница, тот же порядковый смысл)
LETTER_ALT = {
    'а': ['а', 'a'], 'a': ['а', 'a'],
    'б': ['б', 'b'], 'b': ['б', 'b'],
    'в': ['в', 'c'], 'c': ['в', 'c'],
    'г': ['г', 'd'], 'd': ['г', 'd'],
    'д': ['д', 'e'], 'e': ['д', 'e'],
    'е': ['е', 'f'], 'f': ['е', 'f'],
}
SEQ_CYR = 'абвгде'
SEQ_LAT = 'abcdef'


def _norm(s):
    return re.sub(r'\s+', ' ', (s or '')).strip().lower()


def bare_letter(label):
    """Метка → одиночная буква (без скобок/точек)."""
    t = (label or '').strip().strip('().').strip().lower()
    return t[:1] if t else ''


def find_duplicate_run(problem, parts):
    """Возвращает позицию обрезки statement или None."""
    stmt = problem.statement or ''
    if len(stmt) < 80:
        return None
    if len(parts) < 2:
        return None

    letters = [bare_letter(p.label) for p in parts]
    if any(not l for l in letters):
        return None
    # чистый префикс-ран по одной из двух раскладок
    if letters != list(SEQ_CYR[:len(letters)]) and \
       letters != list(SEQ_LAT[:len(letters)]):
        return None

    pos = 0           # ищем маркеры строго по возрастанию позиции
    first_pos = None
    for idx, (letter, part) in enumerate(zip(letters, parts)):
        alts = LETTER_ALT.get(letter, [letter])
        # маркер: не часть слова, опц. «(», буква, «)»
        marker_re = re.compile(
            r'(?<![\w])\(?(?:' + '|'.join(map(re.escape, alts)) + r')\)')
        m = marker_re.search(stmt, pos)
        if not m:
            return None
        if first_pos is None:
            first_pos = m.start()
            if first_pos < 40:        # нет содержательного стема
                return None
        # текст после маркера до следующего маркера/конца
        nxt = len(stmt)
        if idx + 1 < len(letters):
            nl = LETTER_ALT.get(letters[idx + 1], [letters[idx + 1]])
            nm = re.compile(
                r'(?<![\w])\(?(?:' + '|'.join(map(re.escape, nl)) + r')\)'
            ).search(stmt, m.end())
            if nm:
                nxt = nm.start()
        inline = _norm(stmt[m.end():nxt])
        part_norm = _norm(part.statement)
        if len(part_norm) < 20:
            return None
        # строгое совпадение по префиксу (20 символов)
        if inline[:20] != part_norm[:20]:
            return None
        pos = m.end()

    body = stmt[:first_pos].rstrip()
    if len(body) < 40:
        return None
    return first_pos


class Command(BaseCommand):
    help = 'H4 этап 3c: убрать инлайн-дубль подпунктов из statement'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--source-id', type=int, default=None)
        parser.add_argument('--examples', type=int, default=15)
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **o):
        os.makedirs('reports/sessionH4', exist_ok=True)
        qs = Problem.objects.prefetch_related('parts').only('id', 'statement')
        if o['source_id']:
            qs = qs.filter(source_references__source_id=o['source_id']).distinct()
        if o['limit']:
            qs = qs[:o['limit']]

        cands = []
        for p in qs.iterator(chunk_size=500):
            parts = list(p.parts.all().order_by('order', 'id'))
            cut = find_duplicate_run(p, parts)
            if cut is not None:
                cands.append((p, cut))

        self.stdout.write(f'Кандидатов: {len(cands)}')
        for p, cut in cands[:o['examples']]:
            old = p.statement
            self.stdout.write(f'--- #{p.id} (режем на {cut}, было {len(old)} симв.) ---')
            self.stdout.write(f'  ОСТАНЕТСЯ: ...{old[max(0,cut-80):cut]!r}')
            self.stdout.write(f'  УБИРАЕМ:   {old[cut:cut+100]!r} ...')

        if not o['apply']:
            self.stdout.write(self.style.WARNING(
                f'\n[dry-run] {len(cands)} задач. Применить: --apply'))
            return

        changed, errors = [], 0
        for p, cut in cands:
            try:
                with transaction.atomic():
                    p.statement = p.statement[:cut].rstrip()
                    p.save(update_fields=['statement'])
                changed.append(p.id)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Ошибка #{p.id}: {e}'))
                errors += 1
        if changed:
            with open(CHANGED_IDS_FILE, 'a', encoding='utf-8') as f:
                f.write('\n'.join(map(str, changed)) + '\n')
        self.stdout.write(self.style.SUCCESS(
            f'Изменено: {len(changed)}, ошибок: {errors}. id → {CHANGED_IDS_FILE}'))
