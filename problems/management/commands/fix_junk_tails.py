# -*- coding: utf-8 -*-
"""
Сессия H4, этап 3f — мусорные хвосты (класс 13).

Режет всё ОТ паттерна ДО конца поля (Problem/ProblemPart .statement).

Высокоточные паттерны (AP-источники 7,8,18,20,21,22):
  - "IF YOU FINISH BEFORE …"          (CollegeBoard, улика #49229)
  - "Copyright YYYY: … ReviewEcon"    (Jacob Reed, улики #49401, #49552)
  - "Please do not post this on the internet"
  - "GO ON TO THE NEXT PAGE"
  - "DO NOT OPEN THIS …"

Все источники:
  - висячий `\hline` в конце поля (LaTeX-остаток, улика #5057).

Guard: после обрезки поле НЕ пустое (иначе пропуск). content_hash не трогаем.
Идемпотентна.

Библиографические хвосты Акимовой («…ТЕИС…-С. 358», «Безработица 207») —
слишком вариативны для авто-обрезки → список `reports/sessionH4/bibliographic_tail_ids.txt`
(маршрут — ручной разбор/шлюз), не режем.

Запуск:
  ./venv/bin/python manage.py fix_junk_tails --dry-run --examples 15
  ./venv/bin/python manage.py fix_junk_tails --all
"""
import os
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart

CHANGED_IDS_FILE = 'reports/sessionH4/changed_ids_H4.txt'
AP_SOURCES = {7, 8, 18, 20, 21, 22}

# Хвосты для AP (режем от match до конца поля)
AP_TAIL_RE = [
    re.compile(r'\n[ \t]*IF YOU FINISH BEFORE', re.IGNORECASE),
    re.compile(r'\n[ \t\n]*Copyright\s+\d{4}\s*:', re.IGNORECASE),
    re.compile(r'\n[ \t]*Please do not post this on the internet', re.IGNORECASE),
    re.compile(r'\n[ \t]*GO ON TO THE NEXT PAGE', re.IGNORECASE),
    re.compile(r'\n[ \t]*DO NOT OPEN THIS', re.IGNORECASE),
]
# Висячий \hline в самом конце поля (все источники)
TRAILING_HLINE_RE = re.compile(r'(?:\n[ \t]*|\s)*\\hline\s*$')


def clean_ap_tail(text):
    if not text:
        return None
    positions = [m.start() for r in AP_TAIL_RE for m in [r.search(text)] if m]
    if not positions:
        return None
    cut = min(positions)
    cleaned = text[:cut].rstrip()
    if cleaned == text.rstrip() or not cleaned.strip():
        return None
    return cleaned


def clean_hline(text):
    if not text or '\\hline' not in text:
        return None
    cleaned = TRAILING_HLINE_RE.sub('', text).rstrip()
    if cleaned == text.rstrip() or not cleaned.strip():
        return None
    return cleaned


class Command(BaseCommand):
    help = 'H4 этап 3f: вырезать мусорные хвосты (Copyright/IF YOU FINISH/\\hline)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=False)
        parser.add_argument('--all', action='store_true', default=False)
        parser.add_argument('--examples', type=int, default=15)

    def handle(self, *args, **o):
        os.makedirs('reports/sessionH4', exist_ok=True)
        dry = o['dry_run'] or not o['all']
        ex = o['examples']

        changed_ids = set()
        n_fields = 0

        # ── AP-хвосты: ProblemPart.statement и Problem.statement ──
        ap_parts = ProblemPart.objects.filter(
            problem__source_references__source_id__in=AP_SOURCES).distinct()
        for pp in ap_parts.iterator(chunk_size=500):
            new = clean_ap_tail(pp.statement)
            if new is None:
                continue
            n_fields += 1
            if ex > 0:
                ex -= 1
                self.stdout.write(f'--- part#{pp.id} (prob {pp.problem_id}) AP-хвост\n'
                                  f'  ДО : ...{pp.statement[-120:]!r}\n'
                                  f'  ПОС: ...{new[-60:]!r}')
            if not dry:
                pp.statement = new
                pp.save(update_fields=['statement'])
            changed_ids.add(pp.problem_id)

        ap_probs = Problem.objects.filter(
            source_references__source_id__in=AP_SOURCES).distinct()
        for p in ap_probs.iterator(chunk_size=500):
            new = clean_ap_tail(p.statement)
            if new is None:
                continue
            n_fields += 1
            if ex > 0:
                ex -= 1
                self.stdout.write(f'--- #{p.id} AP-хвост (statement)\n'
                                  f'  ДО : ...{p.statement[-120:]!r}\n'
                                  f'  ПОС: ...{new[-60:]!r}')
            if not dry:
                p.statement = new
                p.save(update_fields=['statement'])
            changed_ids.add(p.id)

        # ── висячий \hline: все источники ──
        # list() вместо iterator(): защита от пропуска строк курсором SQLite
        # при сохранении во время обхода (поле меняется → строка уходит из выборки).
        hl_probs = list(Problem.objects.filter(statement__contains='\\hline'))
        for p in hl_probs:
            new = clean_hline(p.statement)
            if new is None:
                continue
            n_fields += 1
            if ex > 0:
                ex -= 1
                self.stdout.write(f'--- #{p.id} \\hline-хвост\n'
                                  f'  ДО : ...{p.statement[-80:]!r}\n'
                                  f'  ПОС: ...{new[-50:]!r}')
            if not dry:
                p.statement = new
                p.save(update_fields=['statement'])
            changed_ids.add(p.id)

        hl_parts = list(ProblemPart.objects.filter(statement__contains='\\hline'))
        for pp in hl_parts:
            new = clean_hline(pp.statement)
            if new is None:
                continue
            n_fields += 1
            if not dry:
                pp.statement = new
                pp.save(update_fields=['statement'])
            changed_ids.add(pp.problem_id)

        mode = 'DRY-RUN' if dry else 'БОЕВОЙ'
        self.stdout.write(self.style.SUCCESS(
            f'{mode}: задач затронуто {len(changed_ids)}, полей {n_fields}.'))
        if not dry and changed_ids:
            with open(CHANGED_IDS_FILE, 'a', encoding='utf-8') as f:
                f.write('\n'.join(map(str, sorted(changed_ids))) + '\n')
            self.stdout.write(f'id → {CHANGED_IDS_FILE}')
