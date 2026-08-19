"""
Management command: import_ap_frq

Импортирует задачи AP Economics FRQ из PDF-файлов.
Папка: materials/AP Economics материалы/Full-length mocks 2026/
Пропускает файлы с «MCQ» и «Solutions» в имени.

Структура задач:
  - Нумерованные вопросы 1., 2., 3. с подпунктами (a), (b), (c).
  - Файлы «FRQs Packet» / «FRQs Answers» содержат раздел «Answer Key».
  - Файлы «AP Makon Olympiad» — формат «Problem N.» с подпунктами a) (X rp).

Параметры:
  difficulty=4, status=published.
  Теги: «FRQ», «AP Economics».
  Источник: «AP Economics — Mock FRQ».
  Дедупликация по content_hash.

Запуск:
    python manage.py import_ap_frq
    python manage.py import_ap_frq --dry-run
"""
import hashlib
import re
from pathlib import Path

import fitz  # pymupdf

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction

from problems.models import Job, Problem, ProblemPart, Source, SourceReference, Tag


AP_FOLDER = (
    Path(settings.BASE_DIR)
    / 'materials'
    / 'AP Economics материалы'
    / 'Full-length mocks 2026'
)
SOURCE_NAME = 'AP Economics — Mock FRQ'
DIFFICULTY = 4

# ── Регулярные выражения ──────────────────────────────────────────────────

# Заголовок страницы вида «Andrei Lengler\n...\n...\n»
PAGE_HEADER_RE = re.compile(
    r'(?m)^Andrei Lengler\n[^\n]+\n[^\n]+\n'
)
# Одиночные числа — номера страниц
PAGE_NUM_RE = re.compile(r'(?m)^\d+\s*$')

# Граница «Questions» → только вопросы
QUESTIONS_START_RE = re.compile(r'(?m)^Questions\s*$')
# Граница «Answer Key...» → конец вопросов
ANSWER_KEY_RE = re.compile(
    r'(?m)^Answer\s+Key\s+and\s+Scoring\s+Guidelines',
    re.IGNORECASE,
)

# Границы вопросов: «1. », «2. » и т.д. в начале строки
FRQ_Q_SPLIT_RE = re.compile(r'(?m)^\d+\.\s')
# Заголовок вопроса: «1. (Long FRQ) text» или «1. text»
FRQ_Q_HEAD_RE = re.compile(
    r'^(\d+)\.\s+(?:\([^)]{0,20}\)\s+)?(.*)',
    re.DOTALL,
)

# Подпункты (a)...(e) — начало строки
SUBPART_FRQ_DETECT_RE = re.compile(r'(?m)^\(([a-e])\)\s')

# Olympiad-формат: «Problem N.»
OLY_DETECT_RE = re.compile(r'(?m)^Problem\s+\d+\.')
OLY_Q_SPLIT_RE = re.compile(r'(?m)^Problem\s+\d+\.')
OLY_Q_HEAD_RE = re.compile(
    r'^Problem\s+(\d+)\.\s+(.+?)(?:\n\(\d+\s*rp\))?\n',
    re.DOTALL,
)
# Подпункты «a) (X rp)» в начале строки
SUBPART_OLY_RE = re.compile(r'(?m)^([a-f])\)\s+\((\d+)\s*rp\)\s+(.*?)(?=^[a-f]\)\s+\(|\Z)', re.DOTALL)
POINTS_OLY_RE = re.compile(r'\((\d+)\s*rp\)')

# ── Вспомогательные функции ───────────────────────────────────────────────

_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
    'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
    'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def md5(text: str) -> str:
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()


def extract_pdf_text(pdf_path: Path) -> str:
    """Извлекает и склеивает текст всех страниц PDF."""
    doc = fitz.open(str(pdf_path))
    pages = [doc[i].get_text() for i in range(len(doc))]
    doc.close()
    return '\n'.join(pages)


def clean_page_markup(text: str) -> str:
    """Убирает заголовки страниц и номера страниц."""
    text = PAGE_HEADER_RE.sub('', text)
    text = PAGE_NUM_RE.sub('', text)
    return text


def extract_questions_section(text: str) -> str:
    """Возвращает текст только раздела с вопросами (до Answer Key)."""
    m_start = QUESTIONS_START_RE.search(text)
    if m_start:
        text = text[m_start.end():]

    m_end = ANSWER_KEY_RE.search(text)
    if m_end:
        text = text[:m_end.start()]

    return text.strip()


def make_short_title(stmt: str, max_len: int = 200) -> str:
    """Первые max_len символов первой непустой строки."""
    for line in stmt.splitlines():
        line = line.strip()
        if line:
            return line[:max_len]
    return stmt[:max_len].strip()


def ensure_tag(name: str, cache: dict) -> Tag:
    if name in cache:
        return cache[name]
    try:
        tag = Tag.objects.get(name=name)
    except Tag.DoesNotExist:
        slug_base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:110] or 'tag'
        slug = slug_base
        counter = 1
        while True:
            try:
                with transaction.atomic():
                    tag = Tag.objects.create(name=name, slug=slug)
                break
            except IntegrityError:
                slug = f'{slug_base}-{counter}'
                counter += 1
    cache[name] = tag
    return tag


# ── Парсинг стандартного FRQ ──────────────────────────────────────────────

def split_frq_subparts(text: str) -> tuple:
    """
    Разбивает текст вопроса на statement + список (label, content).
    Подпункты: (a), (b), ..., (e) в начале строки.
    """
    # Собираем позиции всех (a)/(b)/... в начале строки
    positions = []
    for m in re.finditer(r'(?m)^\(([a-e])\)\s', text):
        positions.append((m.start(), m.group(1), m.end()))

    if not positions:
        return text.strip(), []

    statement = text[:positions[0][0]].strip()
    parts = []
    for i, (start, label, content_start) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        content = text[content_start:end].strip()
        parts.append((label, content))

    return statement, parts


def parse_frq_questions(text: str) -> list:
    """
    Возвращает список (q_num, statement, [(label, content), ...]).
    """
    text = clean_page_markup(text)
    text = extract_questions_section(text)

    # Ищем позиции начал вопросов: строки вида «1. », «2. » и т.д.
    positions = []
    for m in re.finditer(r'(?m)^(\d+)\.\s', text):
        positions.append((m.start(), m.group(1), m.end()))

    if not positions:
        return []

    questions = []
    for i, (start, q_num, content_start) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        # Убираем маркер типа «(Long FRQ)» или «(Short FRQ)» из начала
        body = text[content_start:end]
        body = re.sub(r'^\([^)]{0,20}FRQ\)\s+', '', body.lstrip())
        statement, parts = split_frq_subparts(body)
        if statement.strip():
            questions.append((q_num, statement.strip(), parts))

    return questions


# ── Парсинг Olympiad-формата ──────────────────────────────────────────────

def parse_oly_subparts(body: str) -> tuple:
    """
    Разбивает текст задачи олимпиады на statement + список (label, content, points).
    Подпункты: «a) (X rp) ...» в начале строки.
    """
    # Ищем «a) (X rp)» в начале строки
    positions = []
    for m in re.finditer(r'(?m)^([a-f])\)\s+\((\d+)\s*rp\)\s', body):
        positions.append((m.start(), m.group(1), int(m.group(2)), m.end()))

    if not positions:
        return body.strip(), []

    statement = body[:positions[0][0]].strip()
    parts = []
    for i, (start, label, pts, content_start) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(body)
        content = body[content_start:end].strip()
        parts.append((label, content, pts))

    return statement, parts


def parse_oly_questions(text: str) -> list:
    """
    Возвращает список (q_num, title, statement, [(label, content, points), ...]).
    """
    text = clean_page_markup(text)

    # Ищем «Problem N.» в начале строки
    positions = []
    for m in re.finditer(r'(?m)^Problem\s+(\d+)\.\s+([^\n]+)', text):
        positions.append((m.start(), m.group(1), m.group(2).strip(), m.end()))

    if not positions:
        return []

    questions = []
    for i, (start, q_num, title, content_start) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        body = text[content_start:end]
        # Убираем строку вида «(X rp)» сразу после заголовка
        body = re.sub(r'^\s*\(\d+\s*rp\)\s*\n', '', body)
        statement, parts = parse_oly_subparts(body)
        if statement.strip() or parts:
            questions.append((q_num, title, statement.strip(), parts))

    return questions


# ── Команда ──────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Импортирует задачи AP Economics FRQ из PDF-файлов'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только считать, ничего не писать в базу',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if not AP_FOLDER.exists():
            self.stderr.write(self.style.ERROR(f'Папка не найдена: {AP_FOLDER}'))
            return

        # Все PDF, кроме MCQ и Solutions
        pdf_files = sorted([
            p for p in AP_FOLDER.glob('*.pdf')
            if 'MCQ' not in p.name and 'Solutions' not in p.name
        ])

        self.stdout.write(f'Найдено файлов: {len(pdf_files)}')
        for p in pdf_files:
            self.stdout.write(f'  {p.name}')

        if not pdf_files:
            self.stdout.write('Нет файлов для обработки.')
            return

        # Данные базы
        existing_hashes: set = set(
            Problem.objects.exclude(content_hash='').values_list('content_hash', flat=True)
        )
        tag_cache: dict = {}

        if dry_run:
            self.stdout.write(self.style.WARNING('Режим --dry-run: база не изменяется.'))

        # Источник и задание
        source = job = None
        if not dry_run:
            source, _ = Source.objects.get_or_create(
                name=SOURCE_NAME,
                defaults={'kind': 'мок-экзамен', 'note': 'AP Makon 2026 — задания FRQ'},
            )
            job = Job.objects.create(
                kind='import',
                status='running',
                params={'source': SOURCE_NAME, 'files': len(pdf_files)},
                started_by=None,
            )

        tag_frq = tag_ap = None
        if not dry_run:
            tag_frq = ensure_tag('FRQ', tag_cache)
            tag_ap = ensure_tag('AP Economics', tag_cache)

        created = skipped = errors = 0

        for pdf_path in pdf_files:
            self.stdout.write(f'\n→ {pdf_path.name}')
            try:
                raw_text = extract_pdf_text(pdf_path)
            except Exception as exc:
                self.stderr.write(f'  Ошибка чтения PDF: {exc}')
                errors += 1
                continue

            # Определяем формат файла
            is_olympiad = bool(OLY_DETECT_RE.search(raw_text))

            try:
                if is_olympiad:
                    questions = parse_oly_questions(raw_text)
                    self.stdout.write(f'  Формат: Olympiad, вопросов: {len(questions)}')
                else:
                    questions = parse_frq_questions(raw_text)
                    self.stdout.write(f'  Формат: FRQ, вопросов: {len(questions)}')
            except Exception as exc:
                self.stderr.write(f'  Ошибка парсинга: {exc}')
                errors += 1
                continue

            for q_data in questions:
                try:
                    if is_olympiad:
                        q_num, title, statement, parts_data = q_data
                    else:
                        q_num, statement, parts_data = q_data
                        title = make_short_title(statement)

                    if not statement and not parts_data:
                        continue

                    stmt_hash = md5(statement)

                    if stmt_hash in existing_hashes:
                        skipped += 1
                        continue

                    if dry_run:
                        self.stdout.write(
                            f'  [dry] Q{q_num}: {title[:60]!r} — {len(parts_data)} подпунктов'
                        )
                        created += 1
                        existing_hashes.add(stmt_hash)
                        continue

                    with transaction.atomic():
                        problem = Problem.objects.create(
                            title=title[:200] if is_olympiad else '',
                            statement=statement,
                            difficulty=DIFFICULTY,
                            status=Problem.Status.PUBLISHED,
                            content_hash=stmt_hash,
                        )
                        problem.tags.add(tag_frq, tag_ap)

                        SourceReference.objects.create(
                            problem=problem,
                            source=source,
                            note=pdf_path.name,
                        )

                        for order, part in enumerate(parts_data):
                            if is_olympiad:
                                label, content, pts = part
                                ProblemPart.objects.create(
                                    problem=problem,
                                    label=label,
                                    statement=content,
                                    answer='',
                                    points=pts,
                                    order=order,
                                )
                            else:
                                label, content = part
                                ProblemPart.objects.create(
                                    problem=problem,
                                    label=label,
                                    statement=content,
                                    answer='',
                                    order=order,
                                )

                    created += 1
                    existing_hashes.add(stmt_hash)

                except Exception as exc:
                    self.stderr.write(f'  Ошибка при создании Q{q_num}: {exc}')
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
                f'\nИтог AP FRQ: создано {created}, пропущено {skipped}, ошибок {errors}'
            )
        )
