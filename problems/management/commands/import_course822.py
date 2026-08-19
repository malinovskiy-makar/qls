"""
Management command: import_course822

Импортирует домашние задания из курса 822 «Введение в экономику» (Олмат).
Папка: materials/course_822_materials (1)/
Подпапки вида «Неделя N_ <тема>/Домашнее задание (XXXXX)/Неделя N_*_ДЗ.pdf».

Структура каждого PDF:
  - Страница 1 — обложка (пропускается).
  - Страницы 2+ — задания вида «ЗАДАНИЕ N\nX балла\n...».
  - Подпункты: кириллические А., Б., В., Г., Д. в начале строки.
  - Баллы подпункта: «(X балла)» или «(X балл)» в тексте подпункта.

Параметры:
  status=draft (учебный материал).
  Тема: из названия папки-недели → Topic.
  Источник: «Курс 822 — Введение в экономику (Олмат)».
  Дедупликация по content_hash.

Запуск:
    python manage.py import_course822
    python manage.py import_course822 --dry-run
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


COURSE_FOLDER = (
    Path(settings.BASE_DIR) / 'materials' / 'course_822_materials (1)'
)
SOURCE_NAME = 'Курс 822 — Введение в экономику (Олмат)'

# ── Регулярные выражения ──────────────────────────────────────────────────

# Номер страницы (одиночная цифра/число на отдельной строке)
PAGE_NUM_RE = re.compile(r'(?m)^\d+\s*$')

# Маркер задания: «ЗАДАНИЕ N» (с возможным пробелом перед \n)
TASK_SPLIT_RE = re.compile(r'(?m)^ЗАДАНИЕ\s+(\d+)\s*$', re.UNICODE)

# Баллы за задание: строка «X балл...» или «X,Y балл...» — целиком до конца строки
TASK_POINTS_RE = re.compile(
    r'^([0-9]+(?:[.,][0-9]+)?)\s+балл\w*[^\n]*\n',
    re.MULTILINE | re.UNICODE,
)

# Подпункты: А. / Б. / В. / Г. / Д. / Е. в начале строки
# Возможны варианты: «А.\n», «А. \t», «А.  текст», «А.\tтекст»
SUBPART_RE = re.compile(
    r'(?m)^([А-Е])\.\s*',
    re.UNICODE,
)

# Баллы внутри подпункта: «(0,8 балла)», «(1 балл)», «(1,5 балла)»
SUBPART_POINTS_RE = re.compile(
    r'\(([0-9]+(?:[.,][0-9]+)?)\s+балл\w*\)',
    re.UNICODE,
)

# Транслит для slug тем
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
    """Извлекает текст со всех страниц PDF."""
    doc = fitz.open(str(pdf_path))
    pages = [doc[i].get_text() for i in range(len(doc))]
    doc.close()
    return '\n'.join(pages)


def clean_text(text: str) -> str:
    """Убирает номера страниц."""
    return PAGE_NUM_RE.sub('', text)


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


def parse_decimal(s: str) -> Optional[Decimal]:
    """Преобразует строку вида «1,5» или «1.5» в Decimal."""
    try:
        return Decimal(s.replace(',', '.'))
    except InvalidOperation:
        return None


def parse_subparts(text: str) -> tuple:
    """
    Разбивает текст задания на statement + список (label, content, points).

    Логика:
    - Ищем кириллические маркеры А./Б./В. в начале строки.
    - Считаем подпункт «настоящим» если его текст > 20 символов.
    - Для каждого подпункта ищем баллы «(X балл...)».
    """
    matches = list(SUBPART_RE.finditer(text))

    if not matches:
        return text.strip(), []

    # Собираем сегменты
    segments = []
    for i, m in enumerate(matches):
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip()
        segments.append((m.start(), m.group(1), content))

    # Фильтруем фиктивные записи (подсказки-примеры ответов: «А. 1.» и т.п.)
    real_parts = [
        (start, label, content)
        for start, label, content in segments
        if len(content) >= 20
    ]

    if not real_parts:
        return text.strip(), []

    statement_end = real_parts[0][0]
    statement = text[:statement_end].strip()

    result = []
    for _, label, content in real_parts:
        pts_match = SUBPART_POINTS_RE.search(content)
        points = parse_decimal(pts_match.group(1)) if pts_match else None
        result.append((label, content, points))

    return statement, result


def parse_tasks(text: str) -> list:
    """
    Разбивает текст PDF на список заданий.
    Возвращает [(task_num, statement, [(label, content, points), ...]), ...].
    """
    text = clean_text(text)

    splits = list(TASK_SPLIT_RE.finditer(text))
    if not splits:
        return []

    tasks = []
    for i, m in enumerate(splits):
        task_num = m.group(1)
        body_start = m.end()
        body_end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
        body = text[body_start:body_end].strip()

        # Убираем первую строку «X балл(а/ов)» если есть
        pts_m = TASK_POINTS_RE.match(body)
        if pts_m:
            body = body[pts_m.end():].strip()

        statement, parts = parse_subparts(body)
        tasks.append((task_num, statement, parts))

    return tasks


def topic_name_from_folder(folder_name: str) -> str:
    """
    «Неделя 1_ Введение в экономическую теорию»
    → «Введение в экономическую теорию».
    """
    m = re.match(r'^Неделя\s+\d+_\s*(.*)', folder_name, re.UNICODE)
    if m:
        return m.group(1).strip()
    return folder_name.strip()


# ── Команда ──────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Импортирует домашние задания курса 822 из PDF-файлов'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только считать, ничего не писать в базу',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if not COURSE_FOLDER.exists():
            self.stderr.write(self.style.ERROR(f'Папка не найдена: {COURSE_FOLDER}'))
            return

        # Собираем пары (week_folder, pdf_path)
        # Только из подпапок «Домашнее задание» (не Материалы/Семинар и т.д.)
        week_pdfs = []
        for week_dir in sorted(COURSE_FOLDER.iterdir()):
            if not week_dir.is_dir() or not week_dir.name.startswith('Неделя'):
                continue
            for dz_dir in week_dir.iterdir():
                if not dz_dir.is_dir():
                    continue
                # Фильтруем: только папки «Домашнее задание»
                if 'Домашнее' not in dz_dir.name and 'ДЗ' not in dz_dir.name:
                    continue
                for pdf in sorted(dz_dir.glob('*.pdf')):
                    week_pdfs.append((week_dir.name, pdf))

        self.stdout.write(f'Найдено недель с ДЗ: {len(week_pdfs)}')

        if not week_pdfs:
            self.stdout.write('Нет файлов для обработки.')
            return

        existing_hashes: set = set(
            Problem.objects.exclude(content_hash='').values_list('content_hash', flat=True)
        )
        topic_cache: dict = {}

        if dry_run:
            self.stdout.write(self.style.WARNING('Режим --dry-run: база не изменяется.'))

        source = job = None
        if not dry_run:
            source, _ = Source.objects.get_or_create(
                name=SOURCE_NAME,
                defaults={'kind': 'учебный курс', 'note': 'Курс 822 Олмат, домашние задания'},
            )
            job = Job.objects.create(
                kind='import',
                status='running',
                params={'source': SOURCE_NAME, 'weeks': len(week_pdfs)},
                started_by=None,
            )

        created = skipped = errors = 0

        for week_folder_name, pdf_path in week_pdfs:
            topic_name = topic_name_from_folder(week_folder_name)
            self.stdout.write(f'\n→ {week_folder_name}')
            self.stdout.write(f'  PDF: {pdf_path.name}')
            self.stdout.write(f'  Тема: {topic_name!r}')

            topic_obj = get_or_create_topic(topic_name, topic_cache, dry_run)

            try:
                raw_text = extract_pdf_text(pdf_path)
            except Exception as exc:
                self.stderr.write(f'  Ошибка чтения PDF: {exc}')
                errors += 1
                continue

            try:
                tasks = parse_tasks(raw_text)
            except Exception as exc:
                self.stderr.write(f'  Ошибка парсинга: {exc}')
                errors += 1
                continue

            self.stdout.write(f'  Заданий найдено: {len(tasks)}')

            for task_num, statement, parts_data in tasks:
                try:
                    if not statement.strip() and not parts_data:
                        continue

                    # Для дедупликации: если statement пуст, берём текст первого подпункта
                    hash_base = statement or (parts_data[0][1] if parts_data else '')
                    stmt_hash = md5(hash_base)

                    if stmt_hash in existing_hashes:
                        skipped += 1
                        continue

                    if dry_run:
                        self.stdout.write(
                            f'  [dry] Задание {task_num}: {statement[:60]!r}'
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
                            note=f'{week_folder_name}, задание {task_num}',
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
                    self.stderr.write(
                        f'  Ошибка при задании {task_num}: {exc}'
                    )
                    errors += 1

        if not dry_run and job:
            job.status = 'done' if errors == 0 else 'failed'
            job.result = {
                'created': created,
                'skipped': skipped,
                'errors': errors,
            }
            job.save(update_fields=['status', 'result'])

        self.stdout.write(
            self.style.SUCCESS(
                f'\nИтог курс 822: создано {created}, пропущено {skipped}, ошибок {errors}'
            )
        )
