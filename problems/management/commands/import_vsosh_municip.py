# -*- coding: utf-8 -*-
"""
import_vsosh_municip — импорт муниципального этапа ВсОШ (Москва) из
parsed.json (результат parse_vsosh_municip) в банк задач. Двухфазная
команда по образцу import_vsosh_region:

- БЕЗ --confirm (по умолчанию): только план — сколько Problem/ProblemPart
  будет создано, сколько отсеяно как дубли (с id и источником совпадения),
  сколько уйдёт в draft. В базу НЕ пишет, Source НЕ создаёт.
- С --confirm: создаёт Source «ВсОШ — муниципальный этап (Москва)»,
  задачи, варианты-ProblemPart (буквы а/б/в/г/д, «верно»/«неверно» — схема
  автопроверки и build_game_pool), SourceReference со stage='муниципальный'/
  year/grade/problem_number; список созданных id →
  materials/vsosh_municip/<год>/imported_ids.txt.

Статусы: published — только тесты (single/numeric) с надёжно распознанным
ответом и без пометок, ставящих под сомнение текст условия; draft — всё
остальное (открытые задачи, вопросы с линеаризованной/пересобранной
математикой, с потерянным рисунком).

Дубликаты: точное совпадение нормализованного условия ПЛЮС вариантов против
ВСЕЙ базы (тот же механизм, что на регионе: генерические стемы не съедают
новые вопросы). URL исходников не заполняется — сеть к первоисточнику с этой
машины закрыта, а выдумывать ссылки нельзя; имя файла хранится в note.

Запуск: ./venv/bin/python manage.py import_vsosh_municip --year 2023
        (боевой режим: ... --confirm — ТОЛЬКО после одобрения превью)
"""
import hashlib
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.models import Problem, ProblemPart, Source, SourceReference

SOURCE_NAME = 'ВсОШ — муниципальный этап (Москва)'
SOURCE_KIND = 'олимпиада'
STAGE = 'муниципальный'

PROBLEM_TYPES = {
    'single': 'тест: один ответ',
    'numeric': 'тест: числовой ответ',
    'open': '',   # открытые задачи в банке идут без типа
}

LETTERS = ['а', 'б', 'в', 'г', 'д', 'е']
WS_RE = re.compile(r'\s+')

# Пометки парсера, ставящие под сомнение сам ТЕКСТ условия/вариантов —
# такие вопросы уходят в draft до ручной вычитки (решение о публикации
# принимает преподаватель в Сессии B).
DOUBTFUL_NOTE_RE = re.compile(
    r'линеаризован|по координатам|скобка|рисунок|STIX')


def norm_hash(text):
    return hashlib.md5(WS_RE.sub(' ', text).strip().lower().encode(), usedforsecurity=False).hexdigest()


def norm_option(text):
    t = WS_RE.sub(' ', text).strip().lower().replace('ё', 'е')
    return t.rstrip(';.').strip()


def is_duplicate_of_existing(q, cand_ids, parts_of):
    """Как на регионе: совпадение условия + совпадение набора вариантов;
    вопрос без вариантов — по условию; кандидат-пустышка не дубликат."""
    if not q.get('options'):
        return True
    want = sorted(norm_option(o) for o in q['options'])
    for pid in cand_ids:
        have = sorted(norm_option(s) for s in parts_of(pid))
        if have and have == want:
            return True
    return False


def raw_hash(text):
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()


def is_draft(q):
    """draft — всё сомнительное; published — только тесты с надёжным ответом."""
    if q['qtype'] == 'open':
        return True
    notes = q.get('notes') or ''
    return bool(DOUBTFUL_NOTE_RE.search(notes))


def plan_question(q):
    """(число подпунктов, строка ответа)."""
    qtype = q['qtype']
    if qtype == 'single':
        return len(q['options']), LETTERS[q['correct']]
    if qtype == 'numeric':
        return 0, q['correct']
    return 0, q.get('answer_text') or ''   # open


class Command(BaseCommand):
    help = ('Импорт муниципального этапа ВсОШ из parsed.json. '
            'Без --confirm — только план (в базу не пишет).')

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, required=True)
        parser.add_argument('--file', help='путь к parsed.json (по умолчанию '
                            'materials/vsosh_municip/<год>/parsed.json)')
        parser.add_argument('--confirm', action='store_true',
                            help='боевой режим: записать в базу')

    def handle(self, *args, **options):
        year = options['year']
        src_path = Path(options['file'] or
                        f'materials/vsosh_municip/{year}/parsed.json')
        if not src_path.exists():
            raise CommandError(f'Нет файла {src_path} — сначала '
                               'parse_vsosh_municip')
        data = json.loads(src_path.read_text(encoding='utf-8'))
        questions = data['questions']
        files = data.get('files', {})

        self.stdout.write(f'Файл: {src_path} — вопросов {len(questions)}, '
                          f'unparsed {len(data.get("unparsed", []))}')

        # --- Дубликаты: нормализованное условие против ВСЕЙ базы -----------
        self.stdout.write('Считаю хэши условий существующих задач…')
        existing = {}
        qs = Problem.objects.values_list('id', 'statement').iterator()
        for pid, stmt in qs:
            existing.setdefault(norm_hash(stmt), []).append(pid)
        self.stdout.write(f'  в базе задач: {len(existing)} уникальных условий')

        def parts_of(pid):
            return list(ProblemPart.objects.filter(problem_id=pid)
                        .values_list('statement', flat=True))

        new_items, dupes = [], []
        seen_batch = set()
        for q in questions:
            h = norm_hash(q['statement'])
            batch_key = norm_hash(
                q['statement'] + '\x1f'
                + '\x1f'.join(norm_option(o) for o in q.get('options') or []))
            if batch_key in seen_batch:
                dupes.append((q, ['внутри партии']))
                continue
            if h in existing and is_duplicate_of_existing(q, existing[h],
                                                          parts_of):
                dupes.append((q, existing[h]))
                continue
            seen_batch.add(batch_key)
            new_items.append(q)

        n_parts = 0
        by_type = {}
        n_draft = 0
        for q in new_items:
            parts, _ = plan_question(q)
            n_parts += parts
            by_type[q['qtype']] = by_type.get(q['qtype'], 0) + 1
            if is_draft(q):
                n_draft += 1

        # --- План ------------------------------------------------------------
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'ПЛАН ИМПОРТА (год {year}, этап «{STAGE}»)'))
        src_exists = Source.objects.filter(name=SOURCE_NAME).exists()
        self.stdout.write(f'Source «{SOURCE_NAME}» ({SOURCE_KIND}): '
                          + ('уже есть' if src_exists
                             else 'будет создан (только при --confirm)'))
        self.stdout.write(f'Будет создано Problem: {len(new_items)} '
                          f'(published {len(new_items) - n_draft}, '
                          f'draft {n_draft})')
        for t, label in (('single', 'тест: один ответ'),
                         ('numeric', 'тест: числовой ответ'),
                         ('open', 'задача (решение жюри)')):
            if by_type.get(t):
                self.stdout.write(f'  {label}: {by_type[t]}')
        self.stdout.write(f'Будет создано ProblemPart (вариантов): {n_parts}')
        self.stdout.write(f'Будет создано SourceReference: {len(new_items)}')
        self.stdout.write(f'Отсеяно как дубли: {len(dupes)}')
        src_names = dict(Source.objects.values_list('id', 'name'))
        srcref = {}
        if dupes:
            pids = [pid for _, ids in dupes for pid in ids
                    if isinstance(pid, int)]
            for r in SourceReference.objects.filter(
                    problem_id__in=pids).values('problem_id', 'source_id'):
                srcref.setdefault(r['problem_id'], r['source_id'])
        for q, ids in dupes:
            if ids == ['внутри партии']:
                match = 'повтор внутри года (другой класс)'
            else:
                bits = []
                for pid in ids[:3]:
                    sname = src_names.get(srcref.get(pid), 'без источника')
                    bits.append(f'#{pid} ({sname})')
                match = 'совпал с ' + ', '.join(bits)
            self.stdout.write(f'  дубль: {q["grade_group"]} №{q["number"]} '
                              f'({q["qtype"]}) — {match} — '
                              f'{q["statement"][:60]!r}')
        flagged = [q for q in new_items if q.get('notes')]
        if flagged:
            self.stdout.write(self.style.WARNING(
                f'С пометками парсера: {len(flagged)}'))

        if not options['confirm']:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'Предпросмотр: в базу НИЧЕГО не записано. '
                'Боевой запуск — с флагом --confirm.'))
            return

        # --- Боевой режим -----------------------------------------------------
        created_ids = []
        with transaction.atomic():
            source, created = Source.objects.get_or_create(
                name=SOURCE_NAME, defaults={'kind': SOURCE_KIND})
            for q in new_items:
                created_ids.append(
                    self._create_problem(q, source, year, files))
        ids_path = src_path.parent / 'imported_ids.txt'
        ids_path.write_text('\n'.join(map(str, created_ids)) + '\n',
                            encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(
            f'Импортировано задач: {len(created_ids)} '
            f'(Source {"создан" if created else "существовал"}). '
            f'Id → {ids_path}'))
        self.stdout.write(
            '⚠ Прод: перед заливкой новых записей выровнять sequence '
            '(sqlsequencereset) — см. CLAUDE.md.')

    def _create_problem(self, q, source, year, files):
        qtype = q['qtype']
        _, answer = plan_question(q)
        grades_str = ', '.join(str(g) for g in q['grades'])
        kind = 'Тест' if qtype in ('single', 'numeric') else 'Задача'
        title = (f'ВсОШ, муниципальный (Москва) {year - 1}/{year}. '
                 f'{kind} №{q["number"]} ({grades_str} класс)')[:300]

        status = (Problem.Status.DRAFT if is_draft(q)
                  else Problem.Status.PUBLISHED)
        problem = Problem.objects.create(
            title=title,
            statement=q['statement'],
            answer=answer,
            solution=q.get('solution') or '',
            problem_type=PROBLEM_TYPES[qtype],
            status=status,
            content_hash=raw_hash(q['statement']),
        )

        if qtype == 'single':
            for i, text in enumerate(q['options']):
                ProblemPart.objects.create(
                    problem=problem,
                    label=LETTERS[i],
                    statement=text,
                    answer='верно' if i == q['correct'] else 'неверно',
                    order=i,
                )

        note_bits = [f'файл: {q.get("src_file", "")}'
                     + (f', стр. {q["src_page"]}' if q.get('src_page') else '')]
        if q.get('points'):
            note_bits.append(f'{q["points"]} б. за верный ответ')
        numbers = q.get('numbers') or {}
        if len(numbers) > 1:
            note_bits.append('номера по группам: ' + ', '.join(
                f'{g} кл. — {n}' for g, n in sorted(numbers.items())))
        if q.get('unit'):
            note_bits.append(f'единица ответа: {q["unit"]}')
        if q.get('notes'):
            note_bits.append(q['notes'])
        SourceReference.objects.create(
            problem=problem,
            source=source,
            stage=STAGE,
            year=year,
            grade=', '.join(str(g) for g in q['grades']),
            problem_number=q['number'],
            url='',
            note='; '.join(note_bits)[:300],
        )
        return problem.id
