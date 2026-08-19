"""
Management command: import_course822_demo

Импортирует задачи из двух демо-файлов курса 822 «Введение в экономику» (Олмат):

  1. Демо КР (7 задач) — папка «Демо КР/Примеры заданий (17638)/»
     Условия: _ДемоКР.pdf; решения: _ДемоКР - с решением.pdf.

  2. Демо Экзамен (11 задач) — папка «Экзамен. Демо-версия/Демо-версия (27575)/»

Источник тот же, что import_course822: «Курс 822 — Введение в экономику (Олмат)».
Темы: «Демо КР» и «Демо Экзамен».
Дедупликация по content_hash (MD5 условия).

Запуск:
    python manage.py import_course822_demo
    python manage.py import_course822_demo --dry-run
"""
import hashlib
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import fitz  # pymupdf

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Job, Problem, ProblemPart, Source, SourceReference, Topic


SOURCE_NAME = 'Курс 822 — Введение в экономику (Олмат)'
COURSE_FOLDER = Path(settings.BASE_DIR) / 'materials' / 'course_822_materials (1)'
KR_FOLDER = COURSE_FOLDER / 'Демо КР' / 'Примеры заданий (17638)'
EXAM_FOLDER = COURSE_FOLDER / 'Экзамен. Демо-версия' / 'Демо-версия (27575)'

# ── Регулярные выражения ──────────────────────────────────────────────────

PAGE_NUM_RE = re.compile(r'(?m)^\d+\s*$')

# КР: маркер задания «ЗАДАНИЕ N» (между ЗАДАНИЕ и N возможен перенос строки)
KR_TASK_SPLIT_RE = re.compile(r'ЗАДАНИЕ\s+(\d+)', re.UNICODE)

# КР: заголовок с баллами в начале тела задания «(16 баллов)»
POINTS_HEADER_RE = re.compile(r'^\s*\([^)]*\)\s*', re.UNICODE)

# КР: подпункты «А. (2 балла)» или «А (2 балла)» в начале строки
# Требуем «(» после letter+dot+space, чтобы не захватывать MCQ-варианты
KR_SUBPART_RE = re.compile(r'(?m)^([А-Е])\.?\s+\(', re.UNICODE)

# Баллы из текста подпункта: «(1,5 балла)» / «(2 балла)» / «(4б)»
SUBPART_POINTS_RE = re.compile(
    r'\(([0-9]+(?:[.,][0-9]+)?)\s*(?:балл\w*|б[^)]*)\)',
    re.UNICODE,
)

# Экзамен: маркер задачи «1. (12 баллов)» в начале строки
# Не захватывает «1.1. (2б)» — после N. следует пробел, а не цифра
EXAM_TASK_SPLIT_RE = re.compile(r'(?m)^(\d+)\.\s+\(\d+[^)]*\)', re.UNICODE)

# Экзамен: подпункты «1.1. (2б)» / «7.3. (8б)» в начале строки
EXAM_SUBPART_RE = re.compile(
    r'(?m)^\d+\.(\d+)\.\s*\((\d+(?:[.,]\d+)?)\s*(?:балл\w*|б[^)]*)\)',
    re.UNICODE,
)

# Решения КР: маркеры «Задача N» и «Решение»
KR_SOLUTION_TASK_RE = re.compile(r'Задача\s+(\d+)\s*\n', re.UNICODE)
KR_SOLUTION_BODY_RE = re.compile(r'Решение\s*\n', re.UNICODE)
KR_CRITERIA_RE = re.compile(r'\nКритерии\s*\n', re.UNICODE)

# Транслитерация для slug тем
_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
    'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
    'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya',
}


# ── Вспомогательные функции ───────────────────────────────────────────────

def md5(text: str) -> str:
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()


def make_topic_slug(name: str) -> str:
    s = name.lower()
    chars = [_TRANSLIT.get(c, c) for c in s]
    slug = re.sub(r'[^a-z0-9]+', '-', ''.join(chars)).strip('-')
    return slug[:110] or 'topic'


def extract_pdf_text(pdf_path: Path) -> str:
    doc = fitz.open(str(pdf_path))
    pages = [doc[i].get_text() for i in range(len(doc))]
    doc.close()
    return '\n'.join(pages)


def clean_page_nums(text: str) -> str:
    return PAGE_NUM_RE.sub('', text)


def parse_decimal(s: str) -> Optional[Decimal]:
    try:
        return Decimal(s.replace(',', '.'))
    except InvalidOperation:
        return None


def get_or_create_topic(name: str, cache: dict, dry_run: bool) -> Optional[Topic]:
    if name in cache:
        return cache[name]
    try:
        topic = Topic.objects.get(name=name)
        cache[name] = topic
        return topic
    except Topic.DoesNotExist:
        pass
    if dry_run:
        return None
    base_slug = make_topic_slug(name)
    slug = base_slug
    counter = 1
    while Topic.objects.filter(slug=slug).exists():
        slug = f'{base_slug}-{counter}'
        counter += 1
    topic = Topic.objects.create(name=name, slug=slug)
    cache[name] = topic
    return topic


def parse_kr_solutions(sol_text: str) -> dict:
    """
    Парсит решебник КР. Возвращает {номер_задачи: текст_решения}.
    Структура файла: «Задача N\\nРешение\\n<текст>\\nКритерии\\n<критерии>».
    """
    solutions = {}
    task_matches = list(KR_SOLUTION_TASK_RE.finditer(sol_text))
    for i, tm in enumerate(task_matches):
        task_num = int(tm.group(1))
        chunk_start = tm.end()
        chunk_end = task_matches[i + 1].start() if i + 1 < len(task_matches) else len(sol_text)
        chunk = sol_text[chunk_start:chunk_end]

        sol_body = KR_SOLUTION_BODY_RE.match(chunk)
        if not sol_body:
            continue
        body_start = sol_body.end()

        crit_m = KR_CRITERIA_RE.search(chunk, body_start)
        body_end = crit_m.start() if crit_m else len(chunk)

        solution = chunk[body_start:body_end].strip()
        if solution:
            solutions[task_num] = solution

    return solutions


def parse_kr_tasks(text: str) -> list:
    """
    Разбивает текст КР на [(task_num, body), ...].
    Обложка (до ЗАДАНИЕ 1) пропускается.
    """
    text = clean_page_nums(text)
    splits = list(KR_TASK_SPLIT_RE.finditer(text))
    tasks = []
    for i, m in enumerate(splits):
        task_num = int(m.group(1))
        body_start = m.end()
        body_end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
        body = text[body_start:body_end]
        # Убираем заголовок «(16 баллов)» в начале тела
        body = POINTS_HEADER_RE.sub('', body, count=1).strip()
        tasks.append((task_num, body))
    return tasks


def parse_kr_subparts(text: str) -> tuple:
    """
    Разбивает тело задания КР на (statement, [(label, content, points), ...]).
    Маркеры подпунктов: «А. (X балл)» или «А (X балл)» в начале строки.
    """
    matches = list(KR_SUBPART_RE.finditer(text))
    if not matches:
        return text.strip(), []

    segments = []
    for i, m in enumerate(matches):
        label = m.group(1)
        # Включаем «(» в начало содержимого (m.end() - 1)
        content_start = m.end() - 1
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip()
        pts_match = SUBPART_POINTS_RE.search(content)
        points = parse_decimal(pts_match.group(1)) if pts_match else None
        segments.append((label, content, points))

    statement = text[:matches[0].start()].strip()
    return statement, segments


def parse_exam_tasks(text: str) -> list:
    """
    Разбивает текст экзамена на [(task_num, body), ...].
    Маркер: «N. (X баллов)» в начале строки.
    """
    text = clean_page_nums(text)
    splits = list(EXAM_TASK_SPLIT_RE.finditer(text))
    tasks = []
    for i, m in enumerate(splits):
        task_num = int(m.group(1))
        body_start = m.end()
        body_end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
        body = text[body_start:body_end].strip()
        tasks.append((task_num, body))
    return tasks


def parse_exam_subparts(text: str) -> tuple:
    """
    Разбивает тело задачи экзамена на (statement, [(label, content, points), ...]).
    Маркеры подпунктов: «N.M. (Xб)» / «N.M. (X баллов)» в начале строки.
    """
    matches = list(EXAM_SUBPART_RE.finditer(text))
    if not matches:
        return text.strip(), []

    segments = []
    for i, m in enumerate(matches):
        label = m.group(1)       # M из N.M.
        points_str = m.group(2)  # число баллов из скобок
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip()
        points = parse_decimal(points_str)
        segments.append((label, content, points))

    statement = text[:matches[0].start()].strip()
    return statement, segments


# ── Команда ──────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Импортирует демо-КР и демо-экзамен курса 822 «Введение в экономику»'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только считать, ничего не писать в базу',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('Режим --dry-run: база не изменяется.'))

        existing_hashes: set = set(
            Problem.objects.exclude(content_hash='').values_list('content_hash', flat=True)
        )
        topic_cache: dict = {}

        source = job = None
        if not dry_run:
            source, _ = Source.objects.get_or_create(
                name=SOURCE_NAME,
                defaults={'kind': 'учебный курс', 'note': 'Курс 822 Олмат'},
            )
            job = Job.objects.create(
                kind='import',
                status='running',
                params={'source': SOURCE_NAME, 'files': ['Демо КР', 'Демо Экзамен']},
                started_by=None,
            )

        total_created = total_skipped = total_errors = 0

        # ── 1. Демо КР ────────────────────────────────────────────────────
        self.stdout.write('\n══ Демо КР ══')
        c, s, e = self._import_kr(
            KR_FOLDER, 'Демо КР',
            source, dry_run, existing_hashes, topic_cache,
        )
        total_created += c
        total_skipped += s
        total_errors += e

        # ── 2. Демо Экзамен ───────────────────────────────────────────────
        self.stdout.write('\n══ Демо Экзамен ══')
        c, s, e = self._import_exam(
            EXAM_FOLDER, 'Демо Экзамен',
            source, dry_run, existing_hashes, topic_cache,
        )
        total_created += c
        total_skipped += s
        total_errors += e

        if not dry_run and job:
            job.status = 'done' if total_errors == 0 else 'failed'
            job.result = {
                'created': total_created,
                'skipped': total_skipped,
                'errors': total_errors,
            }
            job.save(update_fields=['status', 'result'])

        self.stdout.write(
            self.style.SUCCESS(
                f'\nИтого: создано {total_created}, '
                f'пропущено {total_skipped}, ошибок {total_errors}'
            )
        )

    def _import_kr(self, folder, topic_name, source, dry_run,
                   existing_hashes, topic_cache):
        created = skipped = errors = 0

        pdfs = sorted(folder.glob('*.pdf'))
        main_pdf = next((p for p in pdfs if 'с решением' not in p.name), None)
        sol_pdf = next((p for p in pdfs if 'с решением' in p.name), None)

        if not main_pdf:
            self.stderr.write(self.style.ERROR(f'Основной PDF не найден в {folder}'))
            return 0, 0, 1

        self.stdout.write(f'  Условия: {main_pdf.name}')
        if sol_pdf:
            self.stdout.write(f'  Решения: {sol_pdf.name}')

        solutions = {}
        if sol_pdf:
            try:
                solutions = parse_kr_solutions(extract_pdf_text(sol_pdf))
                self.stdout.write(f'  Решений найдено: {len(solutions)}')
            except Exception as exc:
                self.stderr.write(f'  Ошибка чтения решений: {exc}')

        try:
            main_text = extract_pdf_text(main_pdf)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'  Ошибка чтения PDF: {exc}'))
            return 0, 0, 1

        tasks = parse_kr_tasks(main_text)
        self.stdout.write(f'  Заданий найдено: {len(tasks)}')

        topic_obj = get_or_create_topic(topic_name, topic_cache, dry_run)

        for task_num, body in tasks:
            try:
                statement, parts_data = parse_kr_subparts(body)
                if not statement.strip() and not parts_data:
                    continue

                hash_base = statement or (parts_data[0][1] if parts_data else '')
                stmt_hash = md5(hash_base)

                if stmt_hash in existing_hashes:
                    skipped += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f'  [dry] Задание {task_num}: {statement[:60]!r}'
                        f' — {len(parts_data)} подпунктов'
                        + (f', решение {len(solutions.get(task_num,""))} симв.' if task_num in solutions else '')
                    )
                    created += 1
                    existing_hashes.add(stmt_hash)
                    continue

                solution = solutions.get(task_num, '')
                with transaction.atomic():
                    problem = Problem.objects.create(
                        title='',
                        statement=statement,
                        solution=solution,
                        status=Problem.Status.DRAFT,
                        content_hash=stmt_hash,
                    )
                    if topic_obj:
                        problem.topics.add(topic_obj)
                    SourceReference.objects.create(
                        problem=problem,
                        source=source,
                        note=f'Демо КР, задание {task_num}',
                    )
                    for order, (label, content, points) in enumerate(parts_data):
                        ProblemPart.objects.create(
                            problem=problem,
                            label=label,
                            statement=content,
                            answer='',
                            points=points,
                            order=order,
                        )

                created += 1
                existing_hashes.add(stmt_hash)

            except Exception as exc:
                self.stderr.write(f'  Ошибка при задании {task_num}: {exc}')
                errors += 1

        self.stdout.write(
            f'  Итог Демо КР: создано {created}, пропущено {skipped}, ошибок {errors}'
        )
        return created, skipped, errors

    def _import_exam(self, folder, topic_name, source, dry_run,
                     existing_hashes, topic_cache):
        created = skipped = errors = 0

        pdfs = sorted(folder.glob('*.pdf'))
        if not pdfs:
            self.stderr.write(self.style.ERROR(f'PDF не найден в {folder}'))
            return 0, 0, 1

        exam_pdf = pdfs[0]
        self.stdout.write(f'  Файл: {exam_pdf.name}')

        try:
            exam_text = extract_pdf_text(exam_pdf)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'  Ошибка чтения PDF: {exc}'))
            return 0, 0, 1

        tasks = parse_exam_tasks(exam_text)
        self.stdout.write(f'  Заданий найдено: {len(tasks)}')

        topic_obj = get_or_create_topic(topic_name, topic_cache, dry_run)

        for task_num, body in tasks:
            try:
                statement, parts_data = parse_exam_subparts(body)
                if not statement.strip() and not parts_data:
                    continue

                hash_base = statement or (parts_data[0][1] if parts_data else '')
                stmt_hash = md5(hash_base)

                if stmt_hash in existing_hashes:
                    skipped += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f'  [dry] Задача {task_num}: {statement[:60]!r}'
                        f' — {len(parts_data)} подпунктов'
                    )
                    created += 1
                    existing_hashes.add(stmt_hash)
                    continue

                with transaction.atomic():
                    problem = Problem.objects.create(
                        title='',
                        statement=statement,
                        status=Problem.Status.DRAFT,
                        content_hash=stmt_hash,
                    )
                    if topic_obj:
                        problem.topics.add(topic_obj)
                    SourceReference.objects.create(
                        problem=problem,
                        source=source,
                        note=f'Демо Экзамен, задача {task_num}',
                    )
                    for order, (label, content, points) in enumerate(parts_data):
                        ProblemPart.objects.create(
                            problem=problem,
                            label=label,
                            statement=content,
                            answer='',
                            points=points,
                            order=order,
                        )

                created += 1
                existing_hashes.add(stmt_hash)

            except Exception as exc:
                self.stderr.write(f'  Ошибка при задаче {task_num}: {exc}')
                errors += 1

        self.stdout.write(
            f'  Итог Демо Экзамен: создано {created}, пропущено {skipped}, ошибок {errors}'
        )
        return created, skipped, errors
