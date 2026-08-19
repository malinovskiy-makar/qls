"""
Management command: import_fridman

Импортирует задачи по микроэкономике из:
  «Задачи для самостоятельной работы с ответами/подсказками/решениями»
  А. Фридман, НИУ ВШЭ, 2020. (~50 стр., 23 задачи, 7 разделов)

Файл: «Задачи и решения 2020_250414_142626.pdf» внутри
  materials/Archive 6/Archive 5/Archive 3/Archive 4.zip

7 разделов (темы):
  Выбор потребителя | Неопределенность |
  Теория фирмы и совершенная конкуренция |
  Монополия/Монопсония и ценовая дискриминация |
  Стратегические взаимодействия |
  Экстерналии и общественные блага |
  Асимметричная информация

В каждом разделе три части:
  «задачи» — условия (импортируются)
  «ответы и подсказки» — краткие ответы (пропускаются)
  «решения» — полные решения (импортируются, пишутся в Problem.solution)

Формат задачи: «N. Текст...»; подпункты: «(а) ...», «(б) ...» в начале строки.
Дедупликация по content_hash. Источник: «Фридман — Задачи по микроэкономике (ВШЭ 2020)».

Запуск:
    python manage.py import_fridman
    python manage.py import_fridman --dry-run
"""
import hashlib
import io
import re
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Optional

import fitz  # pymupdf

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Job, Problem, ProblemPart, Source, SourceReference, Topic


SOURCE_NAME = 'Фридман — Задачи по микроэкономике (ВШЭ 2020)'
ZIP_PATH = (
    Path(settings.BASE_DIR)
    / 'materials'
    / 'Archive 6'
    / 'Archive 5'
    / 'Archive 3'
    / 'Archive 4.zip'
)

# ── Regex patterns ─────────────────────────────────────────────────────────

# Заголовок секции «Topic: задачи/ответы/решения» в начале строки.
# Negative lookahead исключает строки из оглавления вида «...задачи ... 3 »
SECTION_TITLE_RE = re.compile(
    r'(?m)^(.+): (задачи|ответы(?:\s+и\s+|\/)подсказки|решения)'
    r'(?![ \t]*\.[ \t]*\d)[ \t]*$',
    re.UNICODE,
)

# Блок заголовка страницы на листах-продолжениях (без заголовка секции):
#   <blank lines> <N> НИУ ВШЭ - 2020 <TopicName> <blank lines> <Задачи|Решения|...> <blank lines>
PAGE_HEADER_RE = re.compile(
    r'\n[ \t]*\n(?:[ \t]*\n)*[ \t]*\d+[ \t]*\nНИУ ВШЭ - 2020[ \t]*\n'
    r'[^\n]+\n(?:[ \t]*\n)*'
    r'(?:Задачи|Решения|Ответы[^\n]*|Solutions)[ \t]*\n(?:[ \t]*\n)*',
    re.UNICODE,
)

# Номер задачи: «1. Текст...» или «3*1.» (задача со звёздочкой + сноска) в начале строки
PROBLEM_RE = re.compile(r'(?m)^(\d+)\*?\d*\.\s+', re.UNICODE)

# Подпункт задачи: «(а) Текст» в начале строки (кириллица)
SUBPART_RE = re.compile(r'(?m)^\(([а-е])\)\s+', re.UNICODE)

# Транслитерация для slug тем
_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
    'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
    'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya',
}


# ── Helper functions ───────────────────────────────────────────────────────

def md5(text: str) -> str:
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()


def make_topic_slug(name: str) -> str:
    s = name.lower()
    chars = [_TRANSLIT.get(c, c) for c in s]
    slug = re.sub(r'[^a-z0-9]+', '-', ''.join(chars)).strip('-')
    return slug[:110] or 'topic'


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


def extract_fridman_pdf() -> bytes:
    """Извлекает PDF Фридмана из Archive 4.zip (определяет по размеру: меньший файл)."""
    z = zipfile.ZipFile(str(ZIP_PATH))
    candidates = [
        i for i in z.infolist()
        if not i.filename.startswith('__') and i.filename.lower().endswith('.pdf')
    ]
    # Меньший файл — задачи Фридмана, больший — Сборник тестов АА
    fridman_info = min(candidates, key=lambda i: i.file_size)
    data = z.read(fridman_info.filename)
    z.close()
    return data


def extract_full_text(pdf_bytes: bytes) -> str:
    """Извлекает полный текст PDF из байтов."""
    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype='pdf')
    pages = [doc[i].get_text() for i in range(len(doc))]
    doc.close()
    return '\n'.join(pages)


def parse_sections(full_text: str) -> list:
    """
    Разбивает текст на секции по заголовкам «Topic: задачи/решения/ответы».
    Возвращает [(topic, sec_type, content), ...] в порядке следования в документе.
    """
    # Удаляем заголовки страниц-продолжений (без заголовка секции)
    text = PAGE_HEADER_RE.sub('\n', full_text)

    matches = list(SECTION_TITLE_RE.finditer(text))
    sections = []
    for i, m in enumerate(matches):
        topic = m.group(1).strip()
        raw_type = m.group(2).strip()
        # Нормализуем тип секции
        if 'ответы' in raw_type or 'подсказки' in raw_type:
            sec_type = 'ответы'
        elif 'задачи' in raw_type:
            sec_type = 'задачи'
        else:
            sec_type = 'решения'

        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip()
        sections.append((topic, sec_type, content))

    return sections


def parse_problems(content: str) -> list:
    """
    Разбивает текст секции «задачи» на [(num, statement, parts), ...].
    parts = [(label, text), ...]
    """
    matches = list(PROBLEM_RE.finditer(content))
    if not matches:
        return []

    result = []
    for i, m in enumerate(matches):
        num = int(m.group(1))
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[body_start:body_end].strip()
        statement, parts = split_subparts(body)
        result.append((num, statement, parts))

    return result


def parse_solutions(content: str) -> dict:
    """
    Разбивает текст секции «решения» на {num: solution_text}.
    """
    matches = list(PROBLEM_RE.finditer(content))
    solutions = {}
    for i, m in enumerate(matches):
        num = int(m.group(1))
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        solutions[num] = content[body_start:body_end].strip()
    return solutions


def split_subparts(text: str) -> tuple:
    """
    Разбивает тело задачи на (main_statement, [(label, content), ...]).
    Подпункты: «(а)», «(б)», ..., «(е)» в начале строки.
    """
    matches = list(SUBPART_RE.finditer(text))
    if not matches:
        return text.strip(), []

    statement = text[:matches[0].start()].strip()
    parts = []
    for i, m in enumerate(matches):
        label = m.group(1)
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip()
        parts.append((label, content))

    return statement, parts


# ── Command ────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Импортирует задачи Фридмана по микроэкономике (НИУ ВШЭ 2020)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только считать, ничего не писать в базу',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if not ZIP_PATH.exists():
            self.stderr.write(self.style.ERROR(f'Архив не найден: {ZIP_PATH}'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('Режим --dry-run: база не изменяется.'))

        # ── Загрузка и парсинг PDF ─────────────────────────────────────
        self.stdout.write('Извлекаю PDF из архива...')
        try:
            pdf_bytes = extract_fridman_pdf()
            self.stdout.write(f'PDF: {len(pdf_bytes):,} байт')
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'Ошибка извлечения PDF: {exc}'))
            return

        self.stdout.write('Читаю текст...')
        try:
            full_text = extract_full_text(pdf_bytes)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'Ошибка чтения PDF: {exc}'))
            return

        sections = parse_sections(full_text)
        self.stdout.write(f'Секций найдено: {len(sections)}')

        zadachi_list = [(t, c) for t, st, c in sections if st == 'задачи']
        resheniya_list = [(t, c) for t, st, c in sections if st == 'решения']

        self.stdout.write(
            f'  задачи: {len(zadachi_list)}, решения: {len(resheniya_list)}'
        )
        if len(zadachi_list) != len(resheniya_list):
            self.stderr.write(
                self.style.WARNING(
                    f'ВНИМАНИЕ: количество секций задачи ({len(zadachi_list)}) '
                    f'≠ решения ({len(resheniya_list)}), '
                    f'матчинг по позиции, остаток без решений.'
                )
            )

        # ── База данных ────────────────────────────────────────────────
        existing_hashes: set = set(
            Problem.objects.exclude(content_hash='').values_list('content_hash', flat=True)
        )
        topic_cache: dict = {}

        source = job = None
        if not dry_run:
            source, _ = Source.objects.get_or_create(
                name=SOURCE_NAME,
                defaults={
                    'kind': 'учебное пособие',
                    'note': 'Микроэкономика. Задачи для самостоятельной работы. '
                            'А. Фридман, НИУ ВШЭ, 2020.',
                },
            )
            job = Job.objects.create(
                kind='import',
                status='running',
                params={'source': SOURCE_NAME},
                started_by=None,
            )

        total_created = total_skipped = total_errors = 0

        # ── Импорт по разделам ─────────────────────────────────────────
        for idx, (topic_name, zadachi_content) in enumerate(zadachi_list):
            solutions = {}
            if idx < len(resheniya_list):
                _, resheniya_content = resheniya_list[idx]
                try:
                    solutions = parse_solutions(resheniya_content)
                except Exception as exc:
                    self.stderr.write(f'Ошибка парсинга решений [{topic_name}]: {exc}')

            problems = parse_problems(zadachi_content)
            self.stdout.write(
                f'\n[{idx + 1}] {topic_name}: '
                f'{len(problems)} задач, {len(solutions)} решений'
            )

            topic_obj = get_or_create_topic(topic_name, topic_cache, dry_run)

            for num, statement, parts in problems:
                try:
                    if not statement.strip() and not parts:
                        continue

                    hash_base = statement or (parts[0][1] if parts else '')
                    stmt_hash = md5(hash_base)

                    if stmt_hash in existing_hashes:
                        total_skipped += 1
                        continue

                    solution = solutions.get(num, '')

                    if dry_run:
                        self.stdout.write(
                            f'  [dry] Задача {num}: {statement[:55]!r}'
                            f' — {len(parts)} подпунктов'
                            + (f', решение {len(solution)} симв.' if solution else '')
                        )
                        total_created += 1
                        existing_hashes.add(stmt_hash)
                        continue

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
                            note=f'{topic_name}, задача {num}',
                        )

                        for order, (label, content) in enumerate(parts):
                            ProblemPart.objects.create(
                                problem=problem,
                                label=label,
                                statement=content,
                                answer='',
                                points=None,
                                order=order,
                            )

                    total_created += 1
                    existing_hashes.add(stmt_hash)

                except Exception as exc:
                    self.stderr.write(
                        f'  Ошибка при задаче {num} [{topic_name}]: {exc}'
                    )
                    total_errors += 1

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
                f'\nИтого Фридман ВШЭ: создано {total_created}, '
                f'пропущено {total_skipped}, ошибок {total_errors}'
            )
        )
