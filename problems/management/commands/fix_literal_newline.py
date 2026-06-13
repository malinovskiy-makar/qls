# -*- coding: utf-8 -*-
"""
Сессия H4, этап 3d — литеральные «\\n» (бэкслеш+n) как артефакт импорта МатЭк.

В части задач МатЭк кастом-макрос разделителя подпунктов `\\n` остался в тексте
ЛИТЕРАЛЬНО (два символа: обратный слэш и n). На странице это видно как «\n».

Правило: литеральный «\\n», за которым НЕ следует латинская буква (защита от
\\neq, \\nu, \\node, \\newline, \\not…), вне мат-спанов → реальный перенос строки.

Guard: поле не пустеет; чётность $ не меняется (мат-спаны маскируются).
Идемпотентна.

Запуск:
  ./venv/bin/python manage.py fix_literal_newline --dry-run --examples 15
  ./venv/bin/python manage.py fix_literal_newline --all
"""
import os
import re

from django.core.management.base import BaseCommand

from problems.models import Problem
from problems.management.commands.fix_text_punctuation import _mask, _unmask

CHANGED_IDS_FILE = 'reports/sessionH4/changed_ids_H4.txt'

# литеральный \n, не перед латинской буквой
LIT_N_RE = re.compile(r'\\n(?![a-zA-Z])')
MULTI_NL_RE = re.compile(r'\n{3,}')


def fix_field(text):
    if not text or '\\n' not in text:
        return text, False
    masked, spans = _mask(text)
    if not LIT_N_RE.search(masked):
        return text, False
    fixed = LIT_N_RE.sub('\n', masked)
    fixed = MULTI_NL_RE.sub('\n\n', fixed)
    result = _unmask(fixed, spans).strip()
    if not result:
        return text, False
    return result, True


class Command(BaseCommand):
    help = 'H4 этап 3d: литеральные \\n (МатЭк-артефакт) → перенос строки'

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

        for p in Problem.objects.prefetch_related('parts').iterator(chunk_size=500):
            touched = False
            for field in ('statement', 'solution', 'answer'):
                old = getattr(p, field) or ''
                new, ch = fix_field(old)
                if ch:
                    n_fields += 1
                    if ex > 0:
                        ex -= 1
                        self.stdout.write(f'--- #{p.id} [{field}]\n'
                                          f'  ДО : {old[:120]!r}\n'
                                          f'  ПОС: {new[:120]!r}')
                    if not dry:
                        setattr(p, field, new)
                        touched = True
            if touched:
                p.save(update_fields=['statement', 'solution', 'answer'])
            for pt in p.parts.all():
                ptouch = False
                for field in ('statement', 'answer'):
                    old = getattr(pt, field) or ''
                    new, ch = fix_field(old)
                    if ch:
                        n_fields += 1
                        ptouch = True
                        if not dry:
                            setattr(pt, field, new)
                if ptouch:
                    changed_ids.add(p.id)
                    if not dry:
                        pt.save(update_fields=['statement', 'answer'])
            if touched:
                changed_ids.add(p.id)

        mode = 'DRY-RUN' if dry else 'БОЕВОЙ'
        self.stdout.write(self.style.SUCCESS(
            f'{mode}: задач {len(changed_ids)}, полей {n_fields}.'))
        if not dry and changed_ids:
            with open(CHANGED_IDS_FILE, 'a', encoding='utf-8') as f:
                f.write('\n'.join(map(str, sorted(changed_ids))) + '\n')
