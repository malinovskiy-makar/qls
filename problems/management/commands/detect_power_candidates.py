# -*- coding: utf-8 -*-
"""
Сессия H3, этап 5b — кандидаты на ПОТЕРЯННУЮ СТЕПЕНЬ. ТОЛЬКО СПИСОК, без правок
(решение преподавателя — ненадёжная эвристика, ручной просмотр).

«Буква+цифра» в математике почти всегда ИНДЕКС (Q_2, P_2 — второй период/фирма),
и лишь изредка — потерянная степень (Q2 = Q², X3Y = X³Y). Детектор находит
кандидатов и классифицирует догадкой:
  • степень — полиномиальный/издержечный контекст (4Q2+, TC= …Q2 …, перед буквой
    коэффициент, рядом ключевые слова TC/AC/U/издержк/полезност);
  • индекс  — нумерованная переменная (P2 = 30; рядом есть P1; пара X2/X1);
  • неясно  — иначе.

Выход: reports/sessionH3/05_power_candidates.md. НИЧЕГО не меняет.
Запуск: ./venv/bin/python manage.py detect_power_candidates
"""
import os
import re

from django.core.management.base import BaseCommand

from problems.models import Problem, ProblemPart, SourceReference

REPORT = 'reports/sessionH3/05_power_candidates.md'
MATHSPAN = re.compile(r'\$[^$\n]{1,250}?\$')
# буква + 2/3 без _/^/буквы/цифры ПЕРЕД (после допускаем букву — X3Y=X³Y)
POWER = re.compile(r'(?<![_^A-Za-zА-Яа-я0-9\\])([A-Za-zА-Яа-я])([23])(?![0-9])')
# степень в определении издержек через _: «TC = … Q_2» (Q² записано индексом)
COST_POW = re.compile(
    r'(?:TC|AC|VC|FC|MC|ATC|AVC)\s*=\s*[^=$]{0,10}?([A-Za-zА-Яа-я])_([23])'
    r'(?![0-9A-Za-zА-Яа-я])')
# буква-цифра-буква (X3Y) — цифра между буквами часто потерянная степень
LETTER_DIGIT_LETTER = re.compile(r'[A-Za-zА-Яа-я][23][A-Za-zА-Яа-я]')
# издержки/полезность/полином
COST_KW = re.compile(r'TC|AC|VC|FC|MC|ATC|AVC|TR|MR|издержк|полезност|costs?|utility|выпуск')
COEF_BEFORE = re.compile(r'[0-9)]\s*$')        # перед буквой коэффициент → степень
POLY_AFTER = re.compile(r'^\s*[+\-]')          # после — оператор → полиномиальный член


def classify(span, m):
    letter, digit = m.group(1), m.group(2)
    before = span[:m.start()]
    after = span[m.end():]
    frag = m.group(0)
    # буква-цифра-буква (X3Y) — почти наверняка степень
    if after[:1].isalpha():
        return 'степень?'
    # индекс: рядом «=число» или есть «letter1»/«letterN» того же типа
    if re.match(r'\s*=\s*-?\d', after):
        return 'индекс'
    if re.search(re.escape(letter) + r'1\b', span) or \
       re.search(re.escape(letter) + r'_1\b', span):
        return 'индекс'
    # степень: коэффициент перед буквой ИЛИ полиномиальный оператор после,
    # и есть издержечный/полиномиальный контекст
    poly = bool(COEF_BEFORE.search(before)) or bool(POLY_AFTER.match(after))
    if poly and COST_KW.search(span):
        return 'степень'
    if poly:
        return 'степень?'
    return 'неясно'


class Command(BaseCommand):
    help = 'H3 этап 5b: список кандидатов на потерянную степень (без правок)'

    def handle(self, *args, **o):
        os.makedirs('reports/sessionH3', exist_ok=True)
        pid_src = dict(
            SourceReference.objects.values_list('problem_id', 'source_id'))
        from problems.models import Source
        src_name = {s.id: s.name[:30] for s in Source.objects.all()}

        rows = []   # (guess, sid, pid, fld, fragment, context)

        def scan(pid, fld, text):
            if not text:
                return
            for sm in MATHSPAN.finditer(text):
                span = sm.group(0)
                for m in POWER.finditer(span):
                    guess = classify(span, m)
                    frag = m.group(0)
                    i = sm.start() + m.start()
                    ctx = text[max(0, i - 50):i + 50].replace('\n', ' ')
                    rows.append((guess, pid_src.get(pid) or 0, pid, fld,
                                 frag, ctx))
                # степень, записанная индексом в определении издержек: TC = Q_2
                for m in COST_POW.finditer(span):
                    i = sm.start() + m.start()
                    ctx = text[max(0, i - 50):i + 50].replace('\n', ' ')
                    rows.append(('степень? (TC=Q_2)', pid_src.get(pid) or 0,
                                 pid, fld, m.group(1) + '_' + m.group(2), ctx))

        for p in Problem.objects.all().only('id', 'statement', 'answer',
                                            'solution'):
            for fld in ('statement', 'answer', 'solution'):
                scan(p.id, fld, getattr(p, fld))
        for pt in ProblemPart.objects.all().only('id', 'problem_id',
                                                 'statement', 'answer'):
            for fld in ('statement', 'answer'):
                scan(pt.problem_id, 'part.' + fld, getattr(pt, fld))

        from collections import Counter
        gc = Counter(r[0] for r in rows)
        # сортировка: сначала «степень», потом «степень?», «неясно», «индекс»
        order = {'степень': 0, 'степень? (TC=Q_2)': 1, 'степень?': 2,
                 'неясно': 3, 'индекс': 4}
        rows.sort(key=lambda r: (order.get(r[0], 9), r[1], r[2]))

        lines = ['# Этап 5b (H3) — Кандидаты на потерянную степень (СПИСОК, без правок)',
                 '',
                 'Решение преподавателя: НЕ править автоматически. Эвристика ненадёжна.',
                 'Просмотреть вручную; где «буква2» означает квадрат — поправить точечно.',
                 '',
                 f'Всего кандидатов: **{len(rows)}** — {dict(gc)}.',
                 '',
                 'Известные примеры из аудита: #47671 (TC=Q² записано Q_2), '
                 '#5442 (U_2 = X3Y → X³Y).',
                 '',
                 '| догадка | ист | id | поле | фрагмент | контекст ±50 |',
                 '|---------|-----|----|------|----------|--------------|']
        for guess, sid, pid, fld, frag, ctx in rows:
            ctx_e = ctx.replace('|', '\\|')
            lines.append(f'| {guess} | #{sid} | {pid} | {fld} | `{frag}` '
                         f'| {ctx_e} |')
        with open(REPORT, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

        self.stdout.write(f'Кандидатов: {len(rows)} {dict(gc)}')
        self.stdout.write(f'Список (БЕЗ правок): {REPORT}')
