# -*- coding: utf-8 -*-
"""
Сессия H3, этап 5a — двойные скобки (класс C).

ВАЖНО по итогам разведки: наивный паттерн «буква))» почти всегда ловит
ЛЕГИТИМНЫЕ вложенные/мат-скобки (`(см. пункт (а))`, `(ln(x))'`, `(8 класс))`),
а НЕ маркеры. Меток `label=='а))'` в базе нет. Поэтому правим только два
высокоточных, безопасных случая:

  RULE A — тег источника с лишней скобкой: поле НАЧИНАЕТСЯ с
    `(тег-без-вложенных-скобок))` → `(тег)`. Это класс C преподавателя
    (#38862 «(Региональный этап ВСОШ 2024))»). `[^()]+` исключает вложенные
    скобки (`(…(8 класс))` НЕ трогаем). Guard: убирать «)» только если баланс
    скобок поля улучшается (поле имело лишнюю «)»).
  RULE B — маркер-вариант СТРОГО в начале строки: `^\s*([абвгде])\)\)` →
    `\1)` (а не в прозе после «(см. пункт »). Плюс `label == 'а))'` → 'а)'.

Запуск:
  ./venv/bin/python manage.py fix_double_paren            # = dry-run, 15 примеров
  ./venv/bin/python manage.py fix_double_paren --apply
"""
import os
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart

CHANGED_IDS_FILE = 'reports/sessionH3/changed_ids_H3.txt'

RULE_A = re.compile(r'^\(([^()]+)\)\)')
RULE_B = re.compile(r'(?m)^([ \t]*)([абвгдеabcde])\)\)(?=[ \t]|$)')
LABEL_DP = re.compile(r'^([абвгдеabcde])\)\)$')


def paren_balance(s):
    return s.count('(') - s.count(')')


def apply_rule_a(text):
    """Возвращает (new_text, changed?) — убирает лишнюю ) у тега в начале поля."""
    m = RULE_A.match(text)
    if not m:
        return text, False
    new = '(' + m.group(1) + ')' + text[m.end():]
    # guard: баланс скобок должен стать НЕ хуже (поле имело лишнюю «)»)
    if abs(paren_balance(new)) > abs(paren_balance(text)):
        return text, False
    return new, True


def apply_rule_b(text):
    """Маркер-вариант в начале строки буква)) → буква)."""
    new, n = RULE_B.subn(r'\1\2)', text)
    return new, (n > 0)


class Command(BaseCommand):
    help = 'H3 этап 5a: двойные скобки (тег источника + маркер в начале строки)'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--examples', type=int, default=15)

    def handle(self, *args, **o):
        os.makedirs('reports/sessionH3', exist_ok=True)
        apply = o['apply']
        changed_ids = set()
        examples = []
        n_a = n_b = n_label = 0

        with transaction.atomic():
            # Problem: title/statement (RULE A), statement/answer/solution (RULE B)
            for p in Problem.objects.all().only(
                    'id', 'title', 'statement', 'answer', 'solution'):
                fields_changed = []
                # RULE A — только title и statement (тег в начале)
                for fld in ('title', 'statement'):
                    v = getattr(p, fld) or ''
                    nv, ch = apply_rule_a(v)
                    if ch:
                        setattr(p, fld, nv)
                        fields_changed.append(fld)
                        n_a += 1
                        if len(examples) < o['examples']:
                            examples.append(('A', p.id, fld, v[:70], nv[:70]))
                # RULE B — statement/answer/solution
                for fld in ('statement', 'answer', 'solution'):
                    v = getattr(p, fld) or ''
                    nv, ch = apply_rule_b(v)
                    if ch:
                        setattr(p, fld, nv)
                        if fld not in fields_changed:
                            fields_changed.append(fld)
                        n_b += 1
                        if len(examples) < o['examples']:
                            examples.append(('B', p.id, fld, v[:70], nv[:70]))
                if fields_changed:
                    changed_ids.add(p.id)
                    if apply:
                        p.save(update_fields=fields_changed)

            # ProblemPart: statement (RULE B) + label (== 'а))')
            for pt in ProblemPart.objects.all().only(
                    'id', 'problem_id', 'label', 'statement', 'answer'):
                fc = []
                for fld in ('statement', 'answer'):
                    v = getattr(pt, fld) or ''
                    nv, ch = apply_rule_b(v)
                    if ch:
                        setattr(pt, fld, nv)
                        fc.append(fld)
                        n_b += 1
                lm = LABEL_DP.match((pt.label or '').strip())
                if lm:
                    pt.label = lm.group(1) + ')'
                    fc.append('label')
                    n_label += 1
                if fc:
                    changed_ids.add(pt.problem_id)
                    if apply:
                        pt.save(update_fields=fc)

            if not apply:
                transaction.set_rollback(True)

        self.stdout.write(f'RULE A (тег источника))→тег)): {n_a} полей')
        self.stdout.write(f'RULE B (маркер в начале строки): {n_b} полей')
        self.stdout.write(f'label «а))»→«а)»: {n_label}')
        self.stdout.write(f'Задач затронуто: {len(changed_ids)}')
        self.stdout.write('\n=== ПРИМЕРЫ ===')
        for rule, pid, fld, before, after in examples:
            self.stdout.write(f'[{rule}] #{pid}.{fld}')
            self.stdout.write(f'  до: {before!r}')
            self.stdout.write(f'  по: {after!r}')

        if not apply:
            self.stdout.write(self.style.WARNING(
                '\n[dry-run] ничего не изменено. Для применения: --apply'))
            return
        if changed_ids:
            with open(CHANGED_IDS_FILE, 'a', encoding='utf-8') as f:
                f.write('\n'.join(map(str, sorted(changed_ids))) + '\n')
        self.stdout.write(self.style.SUCCESS(
            f'\nПрименено. Задач изменено: {len(changed_ids)} → {CHANGED_IDS_FILE}'))
