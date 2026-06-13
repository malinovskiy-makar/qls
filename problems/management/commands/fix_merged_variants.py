"""
fix_merged_variants — разбивает слитые варианты а)/б)/в)/г)/д)/е) из statement
в отдельные ProblemPart-записи.

Условия срабатывания (все обязательны):
  1. Найдены ≥3 последовательных кириллических маркера а)→б)→в) (г/д/е — опционально).
  2. Расстояние от первого до последнего маркера ≤ 400 символов.
  3. Каждый спан (текст одного варианта) ≤ 120 символов после strip.
  4. Контент каждого спана (без метки "а) ") ≥ 10 символов (фильтр "а), б) и в)").
  5. У задачи нет ни одного ProblemPart.
  6. Ни один спан не содержит \n\n (структурированный текст = не трогаем).

Особый случай "Верно/Неверно": ≥2 маркеров, контент каждого из короткого словаря.

Использование:
    ./venv/bin/python manage.py fix_merged_variants --all --dry-run --examples
    ./venv/bin/python manage.py fix_merged_variants --all
    ./venv/bin/python manage.py fix_merged_variants --source-id 14
"""

import re
import random
from django.core.management.base import BaseCommand
from django.db import transaction
from problems.models import Problem, ProblemPart, Source

# Маркеры: строго кириллические
LETTERS_ORDER = 'абвгде'
# Допустимые предшествующие символы — пробел/перенос/пунктуация/начало строки
MARKER_PATTERN = re.compile(
    r'(?m)(?:(?<=\n)|(?<=[ \t,;.!?«(])|(?<= ))([абвгде])\)'
    r'|(?:^)([абвгде])\)',
    re.MULTILINE
)

# Короткий словарь «Верно/Неверно»
VERNONEVERNO = {
    'верно', 'неверно', 'зависит от условий', 'зависит от обстоятельств',
    'нельзя определить', 'да', 'нет',
    'это верно', 'это неверно', 'нет, неверно', 'да, верно',
}

# problem_type для тестовых задач
TEST_TYPES = {'тест: один ответ', 'тест: все верные', 'тест: верно/неверно', 'test_one', 'test_all', 'test_truefalse'}

# IDs файла с изменёнными задачами
CHANGED_IDS_FILE = 'reports/quality_audit/changed_ids_G.txt'


def _get_letter(m):
    """Возвращает пойманную букву маркера из матча."""
    return m.group(1) or m.group(2)


def _get_letter_end(m):
    """Позиция сразу после 'X)' в строке."""
    if m.group(1):
        return m.start() + 1 + 2  # (1 char lookbehind char) + 'X)'
    else:
        return m.start() + 2  # 'X)' at ^


def find_markers(stmt):
    """Возвращает список (letter, content_start_in_stmt, match_end) для каждого маркера."""
    result = []
    for m in MARKER_PATTERN.finditer(stmt):
        letter = _get_letter(m)
        content_start = _get_letter_end(m)  # позиция ПОСЛЕ 'X)'
        result.append((letter, content_start, m.start()))
    return result


def find_candidate(problem):
    """
    Проверяет задачу на наличие слитых вариантов.
    Возвращает dict с данными для разбивки или None.
    """
    stmt = problem.statement or ''
    if not stmt:
        return None

    # Условие 5: нет подпунктов
    if problem.parts.exists():
        return None

    markers = find_markers(stmt)
    if not markers:
        return None

    letters_all = [x[0] for x in markers]

    # --- Особый случай «Верно/Неверно» (≥2 маркеров а+б) ---
    if len(markers) >= 2 and letters_all[0] == 'а':
        bi = next((i for i, l in enumerate(letters_all) if l == 'б'), None)
        if bi is not None:
            vn_seq = markers[:bi + 1]
            # Вычислим спаны
            vn_spans = _extract_spans(stmt, vn_seq)
            if vn_spans is not None:
                contents = [c.lower().strip('.!? ') for _, c in vn_spans]
                if all(c in VERNONEVERNO for c in contents):
                    return {
                        'body': stmt[:vn_seq[0][2]].rstrip(),
                        'spans': vn_spans,
                        'vernoneverno': True,
                    }

    # --- Основной случай: ≥3 маркеров а→б→в в порядке ---
    # Найти первое 'а'
    start_idx = None
    for i, (letter, cs, ms) in enumerate(markers):
        if letter != 'а':
            continue
        bi = next((j for j in range(i + 1, len(markers)) if markers[j][0] == 'б'), None)
        if bi is None:
            continue
        ci = next((j for j in range(bi + 1, len(markers)) if markers[j][0] == 'в'), None)
        if ci is None:
            continue
        start_idx = i
        break

    if start_idx is None:
        return None

    seq = markers[start_idx:]

    # Условие 2: расстояние от первого до последнего маркера ≤ 400
    first_marker_start = seq[0][2]
    last_marker_start = seq[-1][2]
    if last_marker_start - first_marker_start > 400:
        return None

    # Вычислим спаны
    spans = _extract_spans(stmt, seq)
    if spans is None:
        return None

    body = stmt[:first_marker_start].rstrip()

    return {
        'body': body,
        'spans': spans,
        'vernoneverno': False,
    }


def _extract_spans(stmt, seq):
    """
    Из последовательности маркеров seq = [(letter, content_start, marker_start), ...]
    вычисляет список (label, content_text).
    Возвращает None если не прошли фильтры 3/4/6.
    """
    end_positions = [m[2] for m in seq[1:]] + [len(stmt)]
    spans = []

    for i, (letter, content_start, marker_start) in enumerate(seq):
        end = end_positions[i]
        raw = stmt[content_start:end]
        content = raw.strip()

        # Убираем BOM и невидимые символы
        content = content.replace('﻿', '').replace('​', '').strip()

        # Убираем trailing метку следующего варианта (например если был захвачен " б)")
        content = re.sub(r'\s+[абвгде]\)\s*$', '', content).strip()

        # Убираем открывающую «кавычку» в начале контента — артефакт «а) (где «...»
        content = content.lstrip('«»')

        label = letter + ')'

        # Условие 6: нет \n\n внутри спана
        if '\n\n' in raw:
            return None

        # Условие 3: длина спана ≤ 120
        if len(content) > 120:
            return None

        # Условие 4: контент ≥ 10 символов
        if len(content) < 10:
            return None

        spans.append((label, content))

    return spans


def apply_split(problem, candidate, dry_run=False):
    """Применяет разбивку: обновляет statement, создаёт ProblemPart."""
    body = candidate['body']
    spans = candidate['spans']
    vernoneverno = candidate.get('vernoneverno', False)

    if dry_run:
        return True

    with transaction.atomic():
        problem.statement = body
        # Тип задачи: если все спаны короткие (≤40) — тест
        if problem.problem_type not in TEST_TYPES:
            if vernoneverno:
                problem.problem_type = 'тест: верно/неверно'
            elif all(len(c) <= 40 for _, c in spans):
                problem.problem_type = 'тест: один ответ'
        problem.save(update_fields=['statement', 'problem_type'])

        for order, (label, content) in enumerate(spans, start=1):
            ProblemPart.objects.create(
                problem=problem,
                label=label,
                statement=content,
                order=order,
            )

    return True


class Command(BaseCommand):
    help = 'Разбивает слитые варианты а)/б)/в) из statement в ProblemPart'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--all', action='store_true', dest='all_sources')
        parser.add_argument('--source-id', type=int)
        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--examples', type=int, default=0,
                            help='Показать N случайных примеров (только dry-run)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']
        show_examples = options['examples']

        qs = Problem.objects.prefetch_related('parts').only(
            'id', 'statement', 'problem_type'
        )

        if options['source_id']:
            src = Source.objects.get(pk=options['source_id'])
            self.stdout.write(f'Источник: {src.name}')
            qs = qs.filter(source_references__source=src).distinct()
        elif options['all_sources']:
            pass
        else:
            self.stdout.write(self.style.ERROR('Укажи --all или --source-id N'))
            return

        if limit:
            qs = qs[:limit]

        candidates = []
        for p in qs.iterator(chunk_size=1000):
            c = find_candidate(p)
            if c:
                candidates.append((p, c))

        self.stdout.write(f'Кандидатов: {len(candidates)}')

        if show_examples and candidates:
            sample = random.sample(candidates, min(show_examples, len(candidates)))
            self.stdout.write(f'\n=== {len(sample)} ПРИМЕРОВ ===\n')
            for p, c in sample:
                self.stdout.write(f'--- id={p.id} type={p.problem_type} ---')
                self.stdout.write(f'БЫЛО statement: {repr((p.statement or "")[:300])}')
                self.stdout.write(f'СТАНЕТ body: {repr(c["body"][:200])}')
                for label, content in c['spans']:
                    self.stdout.write(f'  ProblemPart {label}: {repr(content[:100])}')
                self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY-RUN: {len(candidates)} задач будут обработаны'))
            return

        changed = []
        errors = 0
        for p, c in candidates:
            try:
                apply_split(p, c, dry_run=False)
                changed.append(p.id)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Ошибка id={p.id}: {e}'))
                errors += 1

        # Сохраняем id
        if changed:
            with open(CHANGED_IDS_FILE, 'a') as f:
                for pid in changed:
                    f.write(f'{pid}\n')

        self.stdout.write(self.style.SUCCESS(
            f'Изменено: {len(changed)} задач, ошибок: {errors}'
        ))
