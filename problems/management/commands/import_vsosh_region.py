# -*- coding: utf-8 -*-
"""
import_vsosh_region — импорт тестов регионального этапа ВсОШ из
parsed_<год>.json (результат parse_vsosh_region) в банк задач.

Двухфазная команда:
- БЕЗ --confirm (по умолчанию): только план — сколько Problem/ProblemPart
  будет создано, сколько отсеяно как дубликаты. В базу НЕ пишет.
- С --confirm: создаёт Source «ВсОШ — региональный этап» (kind «олимпиада»),
  задачи published с типами «тест: верно/неверно» / «тест: один ответ» /
  «тест: все верные» / «тест: числовой ответ», варианты — ProblemPart
  с метками а/б/в/г и отметкой «верно»/«неверно» (та же схема, что читают
  автопроверка ученика и build_game_pool), SourceReference со stage/year/
  grade/problem_number/url.

Дубликаты на этом этапе — ТОЧНОЕ совпадение нормализованного текста условия
(md5 после схлопывания пробелов и приведения к нижнему регистру) с любой
задачей базы. Дедуп по эмбеддингам — следующая сессия, здесь не делается.

Числовые ответы: Problem.answer хранит точную каноническую запись («0,19»,
«1/3») — это будущий correct_value игрового пула.

Запуск: ./venv/bin/python manage.py import_vsosh_region --year 2023
        (боевой режим: ... --confirm)
"""
import hashlib
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.models import Problem, ProblemPart, Source, SourceReference

SOURCE_NAME = 'ВсОШ — региональный этап'
SOURCE_KIND = 'олимпиада'

PROBLEM_TYPES = {
    'boolean': 'тест: верно/неверно',
    'single': 'тест: один ответ',
    'multi': 'тест: все верные',
    'numeric': 'тест: числовой ответ',
}

# Метки подпунктов-вариантов — как в остальном ru-банке.
LETTERS = ['а', 'б', 'в', 'г', 'д', 'е']

WS_RE = re.compile(r'\s+')


def norm_hash(text):
    """Хэш нормализованного условия: пробелы схлопнуты, регистр убран."""
    return hashlib.md5(WS_RE.sub(' ', text).strip().lower().encode()).hexdigest()


def raw_hash(text):
    """content_hash в поле Problem — md5 сырого условия (как в import_ieo)."""
    return hashlib.md5(text.encode()).hexdigest()


def plan_question(q):
    """Сколько подпунктов даст вопрос + строка ответа (буквы/значение)."""
    qtype = q['qtype']
    if qtype == 'boolean':
        return 2, ('а' if q['correct'] else 'б')
    if qtype == 'single':
        return len(q['options']), LETTERS[q['correct']]
    if qtype == 'multi':
        return len(q['options']), ''.join(LETTERS[i] for i in q['correct'])
    return 0, q['correct']  # numeric: точная каноническая запись


class Command(BaseCommand):
    help = ('Импорт тестов регионального этапа ВсОШ из parsed_<год>.json. '
            'Без --confirm — только план.')

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, default=2023)
        parser.add_argument('--file', help='путь к parsed-JSON (по умолчанию '
                            'materials/vsosh_region/<год>/parsed_<год>.json)')
        parser.add_argument('--confirm', action='store_true',
                            help='боевой режим: записать в базу')

    def handle(self, *args, **options):
        year = options['year']
        src_path = Path(options['file'] or
                        f'materials/vsosh_region/{year}/parsed_{year}.json')
        if not src_path.exists():
            raise CommandError(f'Нет файла {src_path} — сначала parse_vsosh_region')
        data = json.loads(src_path.read_text(encoding='utf-8'))
        questions = data['questions']
        pdf_urls = data.get('pdf_urls', {})
        stage = data.get('stage', 'региональный')

        self.stdout.write(f'Файл: {src_path} — вопросов {len(questions)}, '
                          f'unparsed {len(data.get("unparsed", []))}')

        # --- Дубликаты: нормализованное условие против ВСЕЙ базы -----------
        self.stdout.write('Считаю хэши условий существующих задач…')
        existing = set()
        qs = Problem.objects.values_list('statement', flat=True).iterator()
        for stmt in qs:
            existing.add(norm_hash(stmt))
        self.stdout.write(f'  в базе задач: {len(existing)} уникальных условий')

        new_items, dupes = [], []
        seen_batch = set()
        for q in questions:
            h = norm_hash(q['statement'])
            if h in existing or h in seen_batch:
                dupes.append(q)
            else:
                seen_batch.add(h)
                new_items.append(q)

        n_parts = 0
        by_type = {}
        for q in new_items:
            parts, _ = plan_question(q)
            n_parts += parts
            by_type[q['qtype']] = by_type.get(q['qtype'], 0) + 1

        # --- План ----------------------------------------------------------
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'ПЛАН ИМПОРТА (год {year}, этап «{stage}»)'))
        src_exists = Source.objects.filter(name=SOURCE_NAME).exists()
        self.stdout.write(f'Source «{SOURCE_NAME}» ({SOURCE_KIND}): '
                          + ('уже есть' if src_exists else 'будет создан'))
        self.stdout.write(f'Будет создано Problem: {len(new_items)}')
        for t, label in PROBLEM_TYPES.items():
            if by_type.get(t):
                self.stdout.write(f'  «{label}»: {by_type[t]}')
        self.stdout.write(f'Будет создано ProblemPart (вариантов): {n_parts}')
        self.stdout.write(f'Будет создано SourceReference: {len(new_items)}')
        self.stdout.write(f'Отсеяно как дубликаты по условию: {len(dupes)}')
        for q in dupes:
            self.stdout.write(f'  дубликат: {q["number"]} (классы '
                              f'{q["grades"]}) — {q["statement"][:60]!r}')
        flagged = [q for q in new_items if q.get('notes')]
        if flagged:
            self.stdout.write(self.style.WARNING(
                f'С пометками о линеаризованной математике: {len(flagged)} — '
                + ', '.join(q['number'] for q in flagged)))

        if not options['confirm']:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'Предпросмотр: в базу НИЧЕГО не записано. '
                'Боевой запуск — с флагом --confirm.'))
            return

        # --- Боевой режим ---------------------------------------------------
        with transaction.atomic():
            source, created = Source.objects.get_or_create(
                name=SOURCE_NAME, defaults={'kind': SOURCE_KIND})
            n_created = 0
            for q in new_items:
                n_created += self._create_problem(q, source, year, stage,
                                                  pdf_urls)
        self.stdout.write(self.style.SUCCESS(
            f'Импортировано задач: {n_created} '
            f'(Source {"создан" if created else "существовал"}).'))
        self.stdout.write(
            '⚠ Прод: перед заливкой новых записей выровнять sequence '
            '(sqlsequencereset) — см. CLAUDE.md.')

    def _create_problem(self, q, source, year, stage, pdf_urls):
        qtype = q['qtype']
        _, answer = plan_question(q)
        grades_str = ', '.join(str(g) for g in q['grades'])
        title = (f'ВсОШ, регион {year - 1}/{year}. '
                 f'Тест {q["number"]} ({grades_str} класс)')[:300]

        problem = Problem.objects.create(
            title=title,
            statement=q['statement'],
            answer=answer,
            solution=q['solution'],
            problem_type=PROBLEM_TYPES[qtype],
            status=Problem.Status.PUBLISHED,
            content_hash=raw_hash(q['statement']),
        )

        if qtype == 'boolean':
            option_texts = ['Верно', 'Неверно']
            correct_idx = {0} if q['correct'] else {1}
        elif qtype in ('single', 'multi'):
            option_texts = q['options']
            correct_idx = ({q['correct']} if qtype == 'single'
                           else set(q['correct']))
        else:
            option_texts, correct_idx = [], set()

        for i, text in enumerate(option_texts):
            ProblemPart.objects.create(
                problem=problem,
                label=LETTERS[i],
                statement=text,
                answer='верно' if i in correct_idx else 'неверно',
                order=i,
            )

        # Ссылка на источник: URL PDF младшего класса; остальные — в note.
        note_bits = []
        if q.get('points'):
            note_bits.append(f'{q["points"]} б. за верный ответ')
        if q.get('unit'):
            note_bits.append(f'единица ответа: {q["unit"]}')
        if len(q['grades']) > 1:
            note_bits.append(f'общий вопрос классов {", ".join(map(str, q["grades"]))}')
        if q.get('notes'):
            note_bits.append(q['notes'])
        SourceReference.objects.create(
            problem=problem,
            source=source,
            stage=stage,
            year=year,
            grade=', '.join(str(g) for g in q['grades']),
            problem_number=q['number'],
            url=pdf_urls.get(str(min(q['grades'])), ''),
            note='; '.join(note_bits)[:300],
        )
        return 1
