# -*- coding: utf-8 -*-
"""
Сессия H4, этап 3e — ГОЛАЯ математика вне $...$ (класс 11). Консервативно.

Работает построчно (вне существующих мат-спанов).

БЕЗОПАСНЫЙ подкласс (оборачиваем строку целиком в $...$):
  - строка содержит «=» (или ≤≥<>);
  - переменные ТОЛЬКО латинские (ни одной кириллической буквы — кириллица в
    формуле = OCR-артефакт, одной обёрткой не лечится → в список);
  - все символы из мат-набора (буквы, цифры, + - * / ^ _ ( ) . , = < > ≤ ≥ ≠
    пробелы и немного типографики);
  - сбалансированные скобки;
  - нет английского слова ≥4 латинских букв ПОДРЯД (защита от прозы; короткие
    аббревиатуры MC/TC/AVC/GDP/MRP — ≤3–4 заглавных — разрешены);
  - длина < 80 символов.

СОМНИТЕЛЬНЫЙ (есть =/мат-токены, но кириллица/проза/несбаланс) → только в
список `reports/sessionH4/03e_naked_math_candidates.md`, НЕ трогаем.

Guard: чётность $ не ухудшается; поле не пустеет. Идемпотентна.

Запуск:
  ./venv/bin/python manage.py fix_naked_math --dry-run --examples 25
  ./venv/bin/python manage.py fix_naked_math --all
Флаги: --source-id N.
"""
import os
import re

from django.core.management.base import BaseCommand

from problems.models import Problem
from problems.management.commands.fix_text_punctuation import _mask, _unmask

REPORT = 'reports/sessionH4'
CHANGED_IDS_FILE = os.path.join(REPORT, 'changed_ids_H4.txt')
CAND_FILE = os.path.join(REPORT, '03e_naked_math_candidates.md')

CYR_RE = re.compile(r'[А-Яа-яЁё]')
# латинское «слово» ≥4 букв подряд (англ. проза)
ENG_WORD_RE = re.compile(r'[A-Za-z]{4,}')
HAS_EQ_RE = re.compile(r'[=≤≥]|<|>')
# разрешённый мат-набор символов (для безопасного подкласса)
MATH_CHARS_RE = re.compile(r'^[A-Za-z0-9\s+\-*/^_(){}.,=<>≤≥≠·×÷√%\'’|]+$')
# строка должна выглядеть как уравнение: есть LHS-переменная и '='
EQ_SHAPE_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_^{}()]*\s*[=]')


def balanced(s):
    d = 0
    for c in s:
        if c == '(':
            d += 1
        elif c == ')':
            d -= 1
            if d < 0:
                return False
    return d == 0


def classify_line(line):
    """('safe', wrapped) | ('doubtful', None) | (None, None)."""
    stripped = line.strip()
    if not stripped or '$' in stripped or '\\' in stripped:
        return None, None
    if not HAS_EQ_RE.search(stripped):
        return None, None
    # должен содержать хотя бы один мат-оператор/степень помимо '='
    if not re.search(r'[+\-*/^]|\d', stripped):
        return None, None
    # уже похоже на математику?
    has_cyr = bool(CYR_RE.search(stripped))
    eng_words = ENG_WORD_RE.findall(stripped)
    # ALL-CAPS аббревиатуры (MC, GDP, MRP) допустимы как «слова»
    long_eng = [w for w in eng_words if not w.isupper()]
    if (not has_cyr and not long_eng and len(stripped) < 80
            and MATH_CHARS_RE.match(stripped) and balanced(stripped)
            and EQ_SHAPE_RE.match(stripped)):
        return 'safe', '$' + stripped + '$'
    # сомнительный: есть = и токены, но не прошёл безопасные условия
    return 'doubtful', None


def process_field(text):
    """Возвращает (new_text, n_safe, doubtful_lines)."""
    if not text:
        return text, 0, []
    masked, spans = _mask(text)
    lines = masked.split('\n')
    out = []
    n_safe = 0
    doubtful = []
    for ln in lines:
        kind, wrapped = classify_line(ln)
        if kind == 'safe':
            # сохранить отступ
            lead = ln[:len(ln) - len(ln.lstrip())]
            out.append(lead + wrapped)
            n_safe += 1
        else:
            if kind == 'doubtful':
                doubtful.append(ln.strip()[:90])
            out.append(ln)
    if n_safe == 0:
        return text, 0, doubtful
    result = _unmask('\n'.join(out), spans)
    # guard чётности $
    if result.count('$') % 2 != text.count('$') % 2:
        return text, 0, doubtful
    return result, n_safe, doubtful


class Command(BaseCommand):
    help = 'H4 этап 3e: обернуть безопасную голую математику в $...$ (консервативно)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=False)
        parser.add_argument('--all', action='store_true', default=False)
        parser.add_argument('--source-id', type=int, default=None)
        parser.add_argument('--examples', type=int, default=25)

    def handle(self, *args, **o):
        os.makedirs(REPORT, exist_ok=True)
        dry = o['dry_run'] or not o['all']
        ex = o['examples']

        qs = Problem.objects.prefetch_related('parts').only(
            'id', 'statement', 'solution', 'answer')
        if o['source_id']:
            qs = qs.filter(source_references__source_id=o['source_id']).distinct()

        changed_ids = set()
        n_safe_total = 0
        doubtful_ids = set()
        safe_examples = []
        doubtful_examples = []

        for p in qs.iterator(chunk_size=500):
            touched = False
            for field in ('statement', 'solution', 'answer'):
                old = getattr(p, field) or ''
                new, n_safe, doubtful = process_field(old)
                if doubtful:
                    doubtful_ids.add(p.id)
                    if len(doubtful_examples) < 25:
                        doubtful_examples.append((p.id, field, doubtful[0]))
                if n_safe:
                    n_safe_total += n_safe
                    touched = True
                    if len(safe_examples) < ex:
                        safe_examples.append((p.id, field, old, new))
                    if not dry:
                        setattr(p, field, new)
            if touched:
                changed_ids.add(p.id)
                if not dry:
                    p.save(update_fields=['statement', 'solution', 'answer'])
            for pt in p.parts.all():
                ptouch = False
                for field in ('statement', 'answer'):
                    old = getattr(pt, field) or ''
                    new, n_safe, doubtful = process_field(old)
                    if doubtful:
                        doubtful_ids.add(p.id)
                    if n_safe:
                        n_safe_total += n_safe
                        ptouch = True
                        if not dry:
                            setattr(pt, field, new)
                if ptouch:
                    changed_ids.add(p.id)
                    if not dry:
                        pt.save(update_fields=['statement', 'answer'])

        self.stdout.write('=== БЕЗОПАСНЫЕ примеры (обёртка в $...$) ===')
        for pid, field, old, new in safe_examples[:ex]:
            # покажем первую изменённую строку
            for a, b in zip(old.split('\n'), new.split('\n')):
                if a != b:
                    self.stdout.write(f'  #{pid}[{field}]: {a.strip()!r} → {b.strip()!r}')
                    break
        self.stdout.write('\n=== СОМНИТЕЛЬНЫЕ примеры (только список) ===')
        for pid, field, frag in doubtful_examples[:25]:
            self.stdout.write(f'  #{pid}[{field}]: {frag!r}')

        # пишем список сомнительных
        with open(CAND_FILE, 'w', encoding='utf-8') as f:
            f.write(f'# Сомнительная голая математика (НЕ тронута), '
                    f'{len(doubtful_ids)} задач\n\n')
            for pid in sorted(doubtful_ids):
                f.write(f'{pid}\n')

        mode = 'DRY-RUN' if dry else 'БОЕВОЙ'
        self.stdout.write(self.style.SUCCESS(
            f'\n{mode}: безопасных обёрток {n_safe_total} в {len(changed_ids)} задачах; '
            f'сомнительных задач {len(doubtful_ids)} → {CAND_FILE}'))
        if not dry and changed_ids:
            with open(CHANGED_IDS_FILE, 'a', encoding='utf-8') as f:
                f.write('\n'.join(map(str, sorted(changed_ids))) + '\n')
