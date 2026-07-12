# -*- coding: utf-8 -*-
"""
check_vsosh_gates — шлюзы качества для parsed_<год>.json перед импортом
(ночной конвейер ВсОШ-регион). Все проверки статические, без браузера:

1. unparsed ≤ 3 вопросов И ≤ 10% от общего числа года;
2. уникальных вопросов в разумном диапазоне 12–60;
3. у каждого вопроса валидный правильный ответ своего типа
   (boolean: true/false; single: индекс в пределах вариантов; multi: ≥1
   уникальных индексов в пределах; numeric: parse_exact_number разбирает);
4. single/boolean — ровно один правильный ответ (single это индекс по
   построению, boolean — bool; проверяется тип);
5. парность $ (нечётное число — ошибка), баланс {} внутри математики,
   парность \\left/\\right, отсутствие U+FFFD и управляющих символов.

Выход: отчёт в stdout; код возврата 0 = все шлюзы пройдены, 1 = HELD.
Запуск: ./venv/bin/python manage.py check_vsosh_gates --year 2025
"""
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from game.views import parse_exact_number

DOLLAR_RE = re.compile(r'(?<!\\)\$')
MATH_SEG_RE = re.compile(r'\$([^$]*)\$')
CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

RANGE_MIN, RANGE_MAX = 12, 60
UNPARSED_MAX_ABS, UNPARSED_MAX_SHARE = 3, 0.10


def text_problems(text, where):
    """Список проблем разметки в одном тексте."""
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
    """Все проблемы одного вопроса (пустой список = вопрос чист)."""
    problems = []
    qtype = q['qtype']
    correct = q.get('correct')

    if qtype == 'boolean':
        if not isinstance(correct, bool):
            problems.append(f'boolean: correct не true/false: {correct!r}')
    elif qtype == 'single':
        if not isinstance(correct, int) or isinstance(correct, bool):
            problems.append(f'single: correct не индекс: {correct!r}')
        elif not (0 <= correct < len(q['options'])):
            problems.append(f'single: индекс {correct} вне вариантов')
    elif qtype == 'multi':
        ok = (isinstance(correct, list) and correct
              and all(isinstance(i, int) and not isinstance(i, bool)
                      and 0 <= i < len(q['options']) for i in correct)
              and len(set(correct)) == len(correct))
        if not ok:
            problems.append(f'multi: correct не список валидных индексов: '
                            f'{correct!r}')
    elif qtype == 'numeric':
        if not isinstance(correct, str) or parse_exact_number(correct) is None:
            problems.append(f'numeric: correct не разбирается '
                            f'parse_exact_number: {correct!r}')
    else:
        problems.append(f'неизвестный тип {qtype!r}')

    problems += text_problems(q.get('statement', ''), 'условие')
    for i, opt in enumerate(q.get('options') or []):
        problems += text_problems(opt, f'вариант {i + 1}')
        if not opt.strip():
            problems.append(f'вариант {i + 1} пуст')
    problems += text_problems(q.get('solution', ''), 'решение')
    if not q.get('grades'):
        problems.append('нет классов (grades)')
    return problems


class Command(BaseCommand):
    help = 'Шлюзы качества parsed_<год>.json перед импортом ВсОШ-региона'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, required=True)

    def handle(self, *args, **options):
        year = options['year']
        src = Path(f'materials/vsosh_region/{year}/parsed_{year}.json')
        if not src.exists():
            raise CommandError(f'Нет файла {src}')
        data = json.loads(src.read_text(encoding='utf-8'))
        questions = data['questions']
        unparsed = data.get('unparsed', [])
        failures = []

        total = len(questions) + len(unparsed)
        if len(unparsed) > UNPARSED_MAX_ABS:
            failures.append(f'unparsed {len(unparsed)} > {UNPARSED_MAX_ABS}')
        if total and len(unparsed) / total > UNPARSED_MAX_SHARE:
            failures.append(f'unparsed {len(unparsed)}/{total} > 10%')
        if not (RANGE_MIN <= len(questions) <= RANGE_MAX):
            failures.append(f'уникальных вопросов {len(questions)} вне '
                            f'{RANGE_MIN}–{RANGE_MAX}')

        bad_questions = 0
        for q in questions:
            probs = question_problems(q)
            if probs:
                bad_questions += 1
                failures.append(f'вопрос {q["number"]} (классы {q["grades"]}):')
                failures.extend(f'  - {p}' for p in probs)

        self.stdout.write(f'Год {year}: вопросов {len(questions)}, '
                          f'unparsed {len(unparsed)}, '
                          f'проблемных вопросов {bad_questions}')
        if failures:
            self.stdout.write(self.style.ERROR('ШЛЮЗЫ НЕ ПРОЙДЕНЫ:'))
            for f in failures:
                self.stdout.write(self.style.ERROR(f'  {f}'))
            raise CommandError(f'Год {year}: HELD')
        self.stdout.write(self.style.SUCCESS(
            f'Год {year}: все шлюзы пройдены ✅'))
