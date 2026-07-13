# -*- coding: utf-8 -*-
"""
check_vsosh_municip_gates — шлюзы качества parsed.json муниципального этапа
перед импортом (по образцу check_vsosh_gates региона). Проверки статические:

1. unparsed ≤ 10% от общего числа вопросов года И ≤ 3 на исходный файл;
2. вопросов на класс-группу 8–25, уникальных на год 30–80
   (факт муниципа: тест 5 + краткий ответ 6–10 + развёрнутые 0–4 на группу,
   групп 3–4 — см. reports/vsosh_municip/00_recon.md);
3. валидный ответ своего типа: single — индекс в пределах 4–5 вариантов;
   numeric — parse_exact_number разбирает; open — есть условие и хотя бы
   одно из (решение, текст ответа);
4. разметка: парность $, баланс {} в математике, \\left/\\right,
   отсутствие U+FFFD и управляющих символов.

Выход: отчёт в stdout; код возврата 0 = шлюзы пройдены, CommandError = HELD.
Запуск: ./venv/bin/python manage.py check_vsosh_municip_gates [--year N]
"""
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from game.views import parse_exact_number

DOLLAR_RE = re.compile(r'(?<!\\)\$')
MATH_SEG_RE = re.compile(r'(?<!\\)\$((?:\\.|[^$\\])*)\$')
CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

GROUP_MIN, GROUP_MAX = 8, 25
YEAR_MIN, YEAR_MAX = 30, 80
UNPARSED_MAX_PER_FILE, UNPARSED_MAX_SHARE = 3, 0.10
YEARS = (2017, 2018, 2019, 2020, 2021, 2022, 2023)


def text_problems(text, where):
    problems = []
    if not text:
        return problems
    if '�' in text:
        problems.append(f'{where}: символ U+FFFD (нерасшифрованный глиф)')
    if CTRL_RE.search(text):
        problems.append(f'{where}: управляющие символы')
    n_dollar = len(DOLLAR_RE.findall(text))
    if n_dollar % 2:
        problems.append(f'{where}: непарный $ (всего {n_dollar})')
    else:
        for seg in MATH_SEG_RE.findall(text):
            bare = seg.replace('\\{', '').replace('\\}', '')
            if bare.count('{') != bare.count('}'):
                problems.append(f'{where}: дисбаланс {{}} в ${seg[:40]}…$')
    if text.count('\\left') != text.count('\\right'):
        problems.append(f'{where}: \\left≠\\right')
    return problems


def question_problems(q):
    problems = []
    qtype = q['qtype']
    correct = q.get('correct')

    if qtype == 'single':
        if not (isinstance(correct, int) and not isinstance(correct, bool)):
            problems.append(f'single: correct не индекс: {correct!r}')
        elif not (0 <= correct < len(q['options'])):
            problems.append(f'single: индекс {correct} вне вариантов')
        if not 4 <= len(q.get('options') or []) <= 5:
            problems.append(f'single: вариантов {len(q.get("options") or [])}')
    elif qtype == 'numeric':
        if not isinstance(correct, str) or parse_exact_number(correct) is None:
            problems.append(f'numeric: correct не разбирается '
                            f'parse_exact_number: {correct!r}')
    elif qtype == 'open':
        if not (q.get('solution') or q.get('answer_text')):
            problems.append('open: нет ни решения, ни ответа')
    else:
        problems.append(f'неизвестный тип {qtype!r}')

    problems += text_problems(q.get('statement', ''), 'условие')
    for i, opt in enumerate(q.get('options') or []):
        problems += text_problems(opt, f'вариант {i + 1}')
        if not opt.strip():
            problems.append(f'вариант {i + 1} пуст')
    problems += text_problems(q.get('solution', ''), 'решение')
    problems += text_problems(q.get('answer_text', ''), 'текст ответа')
    if not q.get('grades'):
        problems.append('нет классов (grades)')
    return problems


class Command(BaseCommand):
    help = 'Шлюзы качества parsed.json муниципального этапа ВсОШ'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int,
                            help='один год (по умолчанию все)')

    def handle(self, *args, **options):
        years = [options['year']] if options['year'] else list(YEARS)
        held = []
        for year in years:
            ok = self.check_year(year)
            if not ok:
                held.append(year)
        if held:
            raise CommandError(f'HELD: {", ".join(map(str, held))}')
        self.stdout.write(self.style.SUCCESS('Все годы прошли шлюзы ✅'))

    def check_year(self, year):
        src = Path(f'materials/vsosh_municip/{year}/parsed.json')
        if not src.exists():
            self.stdout.write(self.style.ERROR(
                f'{year}: нет {src} — сначала parse_vsosh_municip'))
            return False
        data = json.loads(src.read_text(encoding='utf-8'))
        questions = data['questions']
        unparsed = data.get('unparsed', [])
        failures = []

        total = len(questions) + len(unparsed)
        if total and len(unparsed) / total > UNPARSED_MAX_SHARE:
            failures.append(f'unparsed {len(unparsed)}/{total} > 10%')
        per_file = {}
        for u in unparsed:
            per_file[u.get('src_file', '?')] = \
                per_file.get(u.get('src_file', '?'), 0) + 1
        for fname, n in sorted(per_file.items()):
            if n > UNPARSED_MAX_PER_FILE:
                failures.append(f'unparsed {n} > {UNPARSED_MAX_PER_FILE} '
                                f'в файле {fname}')

        if not YEAR_MIN <= len(questions) <= YEAR_MAX:
            failures.append(f'уникальных вопросов {len(questions)} вне '
                            f'{YEAR_MIN}–{YEAR_MAX}')
        by_group = {}
        for q in questions:
            for g in q['numbers']:
                by_group[g] = by_group.get(g, 0) + 1
        for g, n in sorted(by_group.items()):
            if not GROUP_MIN <= n <= GROUP_MAX:
                failures.append(f'группа {g}: вопросов {n} вне '
                                f'{GROUP_MIN}–{GROUP_MAX}')

        bad = 0
        for q in questions:
            probs = question_problems(q)
            if probs:
                bad += 1
                failures.append(f'вопрос {q["grade_group"]} №{q["number"]}:')
                failures.extend(f'  - {p}' for p in probs)

        self.stdout.write(f'Год {year}: вопросов {len(questions)}, '
                          f'unparsed {len(unparsed)}, проблемных {bad}')
        if failures:
            self.stdout.write(self.style.ERROR(f'  ШЛЮЗЫ {year} НЕ ПРОЙДЕНЫ:'))
            for f in failures:
                self.stdout.write(self.style.ERROR(f'    {f}'))
            return False
        self.stdout.write(self.style.SUCCESS(f'  {year}: шлюзы пройдены ✅'))
        return True
