# -*- coding: utf-8 -*-
"""
Сессия H4, этап 3b — ИНЛАЙН-подпункты (маркер в середине строки).

Расширение fix_long_variants (которая ловит только маркеры В НАЧАЛЕ строки) на
случай, когда маркеры подпунктов сидят ВНУТРИ сплошного текста:
  «…Предприниматели максимизируют прибыль. (a) Если ставка… (b) Определите… (c)…»

Поддерживаемые формы маркера (вне слова):
  - в скобках: «(a)», «(а)»  ← главный случай ILE;
  - голый «a)»/«а)», но ТОЛЬКО если ему предшествует конец предложения
    [.!?:] + пробел, либо начало строки (защита от «пункта)» и ссылок).

Условия срабатывания (все обязательны):
  1. У задачи НЕТ ни одного ProblemPart.
  2. Найден чистый префикс-ран из ≥3 маркеров: a,b,c(,d,e,f) или а,б,в(…),
     каждая буква РОВНО один раз, по порядку (латиница и кириллица — один алфавит
     по смыслу). Это отсекает ссылки «(a) и (b)» (их 2) и «сравните (a) с (c)»
     (нет b → ран не чистый).
  3. Тело (до первого маркера) ≥ 40 символов (есть содержательное условие).
  4. Каждый спан-вариант ≥ 15 символов (ссылки-маркеры короче).
  5. У КАЖДОГО маркера символ сразу после него (через пробелы) — буква/$ (т.е.
     начинается осмысленный текст, а не «,» / «и»).

Каждый спан → ProblemPart. Метки приводятся к раскладке тела (кириллица, если
тело преимущественно кириллическое; иначе латиница).

Запуск:
  ./venv/bin/python manage.py fix_inline_variants                 # dry-run, 15 примеров
  ./venv/bin/python manage.py fix_inline_variants --apply
Флаги: --source-id N, --examples N, --limit N.
"""
import os
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart

CHANGED_IDS_FILE = 'reports/sessionH4/changed_ids_H4.txt'

LAT = 'abcdef'
CYR = 'абвгде'
# буква → индекс (0..5), общий для латиницы и кириллицы
LETTER_IDX = {}
for i, (a, b) in enumerate(zip(LAT, CYR)):
    LETTER_IDX[a] = i
    LETTER_IDX[b] = i

# скобочный маркер: «(a)» вне слова
PAREN_RE = re.compile(r'(?<![\w(])\(([a-fа-е])\)')
# голый маркер «a)»: после [.!?:]+пробел или после \n
BARE_RE = re.compile(r'(?:(?<=[.!?:])\s|(?<=\n)\s?)([a-fа-е])\)')
# спан НЕБЕЗОПАСЕН, если содержит LaTeX-окружение/якорь/блок ответов
UNSAFE_SPAN_RE = re.compile(
    r'\\begin\{|\\end\{|\\hypertarget|\\hrulefill|<<[^>]*>>|hypertarget')
# невытащенный вложенный маркер ВНУТРИ спана (маркер в начале строки спана):
# одиночная буква (опц. в скобке) + «)» в начале строки → есть ещё подпункты,
# не захваченные (в т.ч. «(g)» за пределами алфавита a-f/а-е)
NESTED_MARKER_RE = re.compile(r'(?m)^[ \t]*\(?[a-zа-яёA-ZА-ЯЁ]\)')


def _cyr_ratio(s):
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return 0.0
    cyr = sum('а' <= c.lower() <= 'я' or c.lower() == 'ё' for c in letters)
    return cyr / len(letters)


def find_inline_variants(problem):
    stmt = problem.statement or ''
    if len(stmt) < 60:
        return None
    if problem.parts.exists():
        return None

    # собираем кандидаты-маркеры из обоих паттернов, дедуп по позиции буквы
    marks = {}      # letter_start_pos -> (letter, marker_start, marker_end)
    for m in PAREN_RE.finditer(stmt):
        marks[m.start(1)] = (m.group(1).lower(), m.start(), m.end())
    for m in BARE_RE.finditer(stmt):
        if m.start(1) not in marks:
            marks[m.start(1)] = (m.group(1).lower(), m.start(1) - 0, m.end())
    if not marks:
        return None
    ordered = [marks[k] for k in sorted(marks)]

    # ищем максимальный чистый префикс-ран a,b,c… с начала первого маркера 'a'/'а'
    # (берём первую группу, начинающуюся с индекса 0)
    run = []
    expect = 0
    for letter, ms, me in ordered:
        idx = LETTER_IDX.get(letter)
        if idx is None:
            continue
        if idx == expect:
            run.append((letter, ms, me))
            expect += 1
        elif idx == 0 and expect > 0:
            # новый старт 'a' — мульти-вопрос, прерываем (защита)
            return None
        else:
            # пропуск/повтор — ран нечистый
            if expect >= 3:
                break
            return None
    if len(run) < 3:
        return None

    first_start = run[0][1]
    body = stmt[:first_start].rstrip()
    if len(body) < 40:
        return None

    spans = []
    for i, (letter, ms, me) in enumerate(run):
        end = run[i + 1][1] if i + 1 < len(run) else len(stmt)
        content = stmt[me:end].strip().replace('﻿', '').replace('​', '').strip()
        if len(content) < 15:
            return None
        # условие 5: спан НЕ начинается с продолжения-ссылки («,»/«;»/«)»).
        # Буквы, скобка «(», цифры, $, кавычки, «\\» (math) — допустимы.
        if content[0] in ',;)':
            return None
        # условие 6: спан не содержит LaTeX-окружения / блока ответов (утечка)
        if UNSAFE_SPAN_RE.search(content):
            return None
        # условие 7: внутри спана нет невытащенного вложенного маркера в начале
        # строки (иначе подпунктов больше, чем захвачено — неполное извлечение)
        if NESTED_MARKER_RE.search(content):
            return None
        spans.append((letter, content))

    use_cyr = _cyr_ratio(body) >= 0.5
    out = []
    for letter, content in spans:
        idx = LETTER_IDX[letter]
        lbl = (CYR if use_cyr else LAT)[idx] + ')'
        out.append((lbl, content))
    return {'body': body, 'spans': out}


class Command(BaseCommand):
    help = 'H4 этап 3b: инлайн-подпункты (a)(b)(c) в середине statement → ProblemPart'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--source-id', type=int, default=None)
        parser.add_argument('--examples', type=int, default=15)
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **o):
        os.makedirs('reports/sessionH4', exist_ok=True)
        qs = Problem.objects.prefetch_related('parts').only(
            'id', 'statement', 'problem_type')
        if o['source_id']:
            qs = qs.filter(source_references__source_id=o['source_id']).distinct()
        if o['limit']:
            qs = qs[:o['limit']]

        cands = []
        for p in qs.iterator(chunk_size=500):
            c = find_inline_variants(p)
            if c:
                cands.append((p, c))

        self.stdout.write(f'Кандидатов: {len(cands)}')
        for p, c in cands[:o['examples']]:
            self.stdout.write(f'--- #{p.id} (тело {len(c["body"])} симв., '
                              f'{len(c["spans"])} вариантов) ---')
            self.stdout.write(f'  ТЕЛО: ...{c["body"][-110:]!r}')
            for lbl, content in c['spans']:
                self.stdout.write(f'    {lbl} {content[:80]!r}')

        if not o['apply']:
            self.stdout.write(self.style.WARNING(
                f'\n[dry-run] {len(cands)} задач. Применить: --apply'))
            return

        changed, errors = [], 0
        TEST = {'тест: один ответ', 'тест: все верные', 'тест: верно/неверно'}
        for p, c in cands:
            try:
                with transaction.atomic():
                    p.statement = c['body']
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
            f'Изменено: {len(changed)}, ошибок: {errors}. id → {CHANGED_IDS_FILE}'))
