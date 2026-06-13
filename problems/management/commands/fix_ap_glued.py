"""
Сессия C, этап 3b — разбор испорченных мат-спанов в англоязычных источниках.

Проблема: целые абзацы проглочены одним $...$-спаном:
  «...DomesticDemandDomesticSupplyOnesunnyday...» — слова склеены БЕЗ пробелов
  (пробелы потеряны при PDF-экстракции) — текст не восстановить;
  либо обычные словарные слова С пробелами — обёртку можно просто снять.

Два исхода для спана-кандидата:
  1. CamelCase-цепочка ≥3 «слов» и ≥25 символов → текст не восстановить:
     задача под флаг needs_quality_review, id → ap_glued_ids.txt.
     Пробелы НЕ угадываем (железное правило).
  2. ≥2 словарных английских слова с пробелами → $ были литеральными
     (валютными) и спарились ошибочно: ЭКРАНИРУЕМ оба ($X$ → \\$X\\$) —
     текст сохраняется посимвольно, доллары рендерятся как знаки валюты.

Запуск:
    ./venv/bin/python manage.py fix_ap_glued --dry-run
    ./venv/bin/python manage.py fix_ap_glued
"""

import os
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart
from problems.management.commands.fix_ile_formulas import append_ids_file
from problems.management.commands.fix_pdf_formulas import _EN_DICT

EN_SOURCES = [7, 8, 18, 20, 21, 22]
CHANGED_IDS_FILE_C = 'reports/quality_audit/changed_ids_C.txt'
GLUED_FILE = 'reports/quality_audit/ap_glued_ids.txt'

_SPAN_RE = re.compile(r'(?<!\\)\$([^$]+)(?<!\\)\$')
_CAMEL_RE = re.compile(r'(?:[A-Z][a-z]{2,}){3,}')


def classify_span(span: str):
    """'glued' (CamelCase, не восстановить) | 'prose' (снять обёртку) | None."""
    m = _CAMEL_RE.search(span)
    if m and len(m.group(0)) >= 25:
        return 'glued'
    tokens = re.findall(r'[A-Za-z]+', span)
    dict_words = [t for t in tokens
                  if not t.isupper() and t.lower() in _EN_DICT]
    if len(dict_words) >= 2 and ' ' in span.strip():
        return 'prose'
    return None


def process_field(text: str):
    """(новый_текст | None, glued_fragments). None = не менялось."""
    if not text or '$' not in text:
        return None, []
    glued = []
    changed = False

    def repl(m):
        nonlocal changed
        verdict = classify_span(m.group(1))
        if verdict == 'glued':
            glued.append(m.group(1)[:120])
            return m.group(0)            # текст не трогаем — задача под флаг
        if verdict == 'prose':
            changed = True
            return '\\$' + m.group(1) + '\\$'   # литеральные валютные $
        return m.group(0)

    new = _SPAN_RE.sub(repl, text)
    return (new if changed else None), glued


class Command(BaseCommand):
    help = 'Разбор склеенных $...$-спанов AP: снять обёртку или флаг шлюза'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--examples', type=int, default=15)

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('── DRY-RUN ──'))

        unwrap_examples = []        # (sid, pid, field, span)
        glued_rows = []             # (pid, sid, fragment)
        changed_ids = set()
        flagged_ids = set()

        with transaction.atomic():
            for sid in EN_SOURCES:
                problems = (Problem.objects
                            .filter(source_references__source_id=sid)
                            .distinct().prefetch_related('parts').order_by('id'))
                for problem in problems:
                    prob_glued = []
                    fields = {}
                    for field in ('statement', 'answer', 'solution'):
                        t = getattr(problem, field) or ''
                        new, glued = process_field(t)
                        prob_glued += glued
                        if new is not None:
                            fields[field] = new
                            for m in _SPAN_RE.finditer(t):
                                if classify_span(m.group(1)) == 'prose':
                                    unwrap_examples.append(
                                        (sid, problem.id, field, m.group(1)[:100]))
                    part_updates = []
                    for part in problem.parts.all():
                        pfields = {}
                        for field in ('statement', 'answer', 'solution'):
                            t = getattr(part, field) or ''
                            new, glued = process_field(t)
                            prob_glued += glued
                            if new is not None:
                                pfields[field] = new
                        if pfields:
                            part_updates.append((part.pk, pfields))

                    if fields or part_updates:
                        changed_ids.add(problem.id)
                        if not dry_run:
                            if fields:
                                Problem.objects.filter(pk=problem.pk).update(**fields)
                            for ppk, pf in part_updates:
                                ProblemPart.objects.filter(pk=ppk).update(**pf)
                    if prob_glued:
                        flagged_ids.add(problem.id)
                        glued_rows.append((problem.id, sid, prob_glued[0]))
                        if not dry_run:
                            Problem.objects.filter(pk=problem.pk).update(
                                needs_quality_review=True)

        self.stdout.write(f'Снята обёртка: {len(changed_ids)} задач; '
                          f'под флаг (CamelCase-склейки): {len(flagged_ids)} задач')
        self.stdout.write('\nПримеры снятия обёртки:')
        for sid, pid, field, span in unwrap_examples[:options['examples']]:
            self.stdout.write(f'  #{pid} (ист.{sid}) [{field}]: ${span}$ → без $')
        self.stdout.write('\nПримеры склеек (под флаг):')
        for pid, sid, frag in glued_rows[:options['examples']]:
            self.stdout.write(f'  #{pid} (ист.{sid}): {frag[:110]}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY-RUN: ничего не сохранено.'))
        else:
            append_ids_file(CHANGED_IDS_FILE_C, changed_ids)
            os.makedirs(os.path.dirname(GLUED_FILE), exist_ok=True)
            with open(GLUED_FILE, 'w', encoding='utf-8') as f:
                f.write('# id\tисточник\tфрагмент склейки\n')
                for pid, sid, frag in glued_rows:
                    f.write(f'{pid}\t#{sid}\t{frag}\n')
            self.stdout.write(self.style.SUCCESS(
                f'\nГотово. Флаги: {len(flagged_ids)} → {GLUED_FILE}'))
