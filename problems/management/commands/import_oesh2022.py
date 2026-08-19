"""
Management command: import_oesh2022

Импортирует тематические подборки задач ОЭШ Олмат 2022.
Источник: вложенный ZIP внутри
  materials/Archive 6/Archive 5/Archive 3/Archive.zip

Вложенный ZIP содержит 32 PDF-подборки в трёх треках:
  1. Машины/Подборки/ — 12 тем (Олигополия, КПВ, Тервер, Эконометрика…)
  2. Роботы/Подборки/ — 11 тем (Вмешательство, Теория игр, Неравенство…)
  3. Человеки/Подборки/ — 12 тем (Спрос и предложение, КПВ, Издержки…)

Формат каждого PDF:
  Заголовок: «Олмат «Экономика»» / «Автор, Трек» / «Тема»  (повторяется на каждой стр.)
  Задачи: «N. текст задачи»
  Подпункты: «(a) текст» … «(e) текст» в начале строки (Latin lowercase).
  Возможна вводная секция (шпаргалка / «Как устроена подборка?»);
  если в тексте есть «Режим Lite», разбор начинается с него.

Параметры:
  status=draft.
  Тема: из заголовка PDF → Topic.
  SourceReference.note = «ОЭШ 2022, <трек>, <тема>, задача N».
  Источник: «ОЭШ Олмат 2022».
  Дедупликация по content_hash.

Запуск:
    python manage.py import_oesh2022
    python manage.py import_oesh2022 --dry-run
"""
import hashlib
import io
import re
import zipfile
from pathlib import Path
from typing import Optional

import fitz  # pymupdf

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Job, Problem, ProblemPart, Source, SourceReference, Topic


OUTER_ZIP = (
    Path(settings.BASE_DIR)
    / 'materials'
    / 'Archive 6'
    / 'Archive 5'
    / 'Archive 3'
    / 'Archive.zip'
)
SOURCE_NAME = 'ОЭШ Олмат 2022'

# ── Regex ──────────────────────────────────────────────────────────────────

# Заголовок страницы: «Олмат «Экономика»\n...\n...\n»
PAGE_HEADER_RE = re.compile(
    r'(?m)^Олмат «Экономика»\n[^\n]+\n[^\n]+\n',
    re.UNICODE,
)

# Маркеры режимов (Lite/Hard/Normal) — сигнал начала реального блока задач
REZHIM_RE = re.compile(r'(?m)^Режим\s+\S+\s*$', re.UNICODE)

# Задача: «N. text» в начале строки (N = 1..20, не более двух цифр)
PROBLEM_RE = re.compile(r'(?m)^(\d{1,2})\.\s+', re.UNICODE)

# Подпункт: «(a) text» — латинские строчные
SUBPART_RE = re.compile(r'(?m)^\(([a-h])\)\s+', re.UNICODE)

# Транслитерация для slug
_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
    'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
    'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya',
}


# ── Helpers ────────────────────────────────────────────────────────────────

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


def decode_zip_name(raw: str) -> str:
    """Декодирует русские имена файлов из ZIP (cp437 → cp866)."""
    try:
        return raw.encode('cp437').decode('cp866')
    except Exception:
        return raw


def open_inner_zip(outer_path: Path) -> zipfile.ZipFile:
    """Открывает вложенный ZIP из outer_path."""
    z_outer = zipfile.ZipFile(str(outer_path))
    for info in z_outer.infolist():
        if info.filename.endswith('.zip') and not info.filename.startswith('__'):
            data = z_outer.read(info.filename)
            z_outer.close()
            return zipfile.ZipFile(io.BytesIO(data))
    z_outer.close()
    raise FileNotFoundError('Вложенный ZIP не найден в ' + str(outer_path))


# ── PDF parsing ────────────────────────────────────────────────────────────

def extract_pdf_bytes(z: zipfile.ZipFile, raw_name: str) -> bytes:
    return z.read(raw_name)


def read_pdf_text(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype='pdf')
    pages = [doc[i].get_text() for i in range(len(doc))]
    doc.close()
    return '\n'.join(pages)


def extract_topic_from_header(raw_text: str) -> str:
    """
    Извлекает тему из заголовка первой страницы:
    строка 1: «Олмат «Экономика»»
    строка 2: «Автор, Трек»
    строка 3: «Тема»
    Возвращает очищенную тему.
    """
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    if len(lines) >= 3 and lines[0] == 'Олмат «Экономика»':
        return lines[2]
    # Fallback: пустая строка
    return ''


def clean_pdf_text(text: str) -> str:
    """Убирает повторяющиеся заголовки страниц."""
    return PAGE_HEADER_RE.sub('', text)


def find_problems_start(text: str) -> int:
    """
    Возвращает позицию начала первого реального блока задач.
    Если в тексте есть «Режим ...» — берём текст после ПОСЛЕДНЕГО такого маркера.
    Иначе — с самого начала.
    """
    rezhim_matches = list(REZHIM_RE.finditer(text))
    if rezhim_matches:
        # Начинаем после последнего «Режим» маркера
        return rezhim_matches[-1].end()
    return 0


def clean_statement_first_line(text: str) -> str:
    """
    Убирает первую строку если она — декоративный инициал или лирика.
    Артефакты PDF: заглавная буква в начале (drop cap) или строка с '-'
    (обрыв лирики), встречаются в файлах «Разнобой».
    """
    lines = text.split('\n')
    if not lines:
        return text
    first = lines[0].strip()
    if (
        len(first) <= 1           # декоративная заглавная буква
        or first.startswith('-')  # продолжение лирики
        or first.endswith('-')    # обрыв лирики
    ):
        return '\n'.join(lines[1:]).strip()
    return text


def split_subparts(body: str) -> tuple:
    """
    Разбивает тело задачи на (statement, [(label, content), ...]).
    Подпункты: «(a)» … «(h)» в начале строки (Latin lowercase).
    """
    body = clean_statement_first_line(body)
    matches = list(SUBPART_RE.finditer(body))
    if not matches:
        return body.strip(), []

    statement = body[:matches[0].start()].strip()
    parts = []
    for i, m in enumerate(matches):
        label = m.group(1)
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[content_start:content_end].strip()
        parts.append((label, content))

    return statement, parts


def parse_problems(text: str) -> list:
    """
    Разбивает текст (после удаления заголовков) на список
    (num, statement, [(label, content), ...]).
    Фильтрует задачи с пустым или очень коротким statement.
    """
    start = find_problems_start(text)
    content = text[start:]

    matches = list(PROBLEM_RE.finditer(content))
    if not matches:
        return []

    results = []
    for i, m in enumerate(matches):
        num = int(m.group(1))
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[body_start:body_end]
        statement, parts = split_subparts(body)

        # Фильтр: пустые или слишком короткие (< 20 симв.) условия — пропускаем
        if len(statement.strip()) < 20 and not parts:
            continue

        results.append((num, statement.strip(), parts))

    return results


# ── Command ────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Импортирует тематические подборки ОЭШ Олмат 2022 из вложенного ZIP'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только считать, ничего не писать в базу',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if not OUTER_ZIP.exists():
            self.stderr.write(self.style.ERROR(f'Архив не найден: {OUTER_ZIP}'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('Режим --dry-run: база не изменяется.'))

        # Открываем вложенный ZIP
        try:
            z_inner = open_inner_zip(OUTER_ZIP)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'Ошибка открытия ZIP: {exc}'))
            return

        # Собираем список Подборок: (raw_name, decoded_name, track, filename)
        podborki = []
        for info in z_inner.infolist():
            decoded = decode_zip_name(info.filename)
            if '__MACOSX' in decoded or not decoded.endswith('.pdf'):
                continue
            parts = decoded.split('/')
            # Структура: root/track/Подборки/filename.pdf
            if len(parts) >= 4 and parts[2] == 'Подборки':
                track = parts[1]  # «1. Машины» / «2. Роботы» / «3. Человеки»
                podborki.append((info.filename, decoded, track, parts[-1]))

        self.stdout.write(f'Найдено Подборок: {len(podborki)}')

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
                    'note': 'Подборки и решалки ОЭШ Олмат, ноябрь 2022. '
                            'Три трека: 1. Машины, 2. Роботы, 3. Человеки.',
                },
            )
            job = Job.objects.create(
                kind='import',
                status='running',
                params={'source': SOURCE_NAME, 'files': len(podborki)},
                started_by=None,
            )

        total_created = total_skipped = total_errors = 0

        for raw_name, decoded_name, track, fname in sorted(podborki):
            self.stdout.write(f'\n→ {track}/{fname}')

            try:
                pdf_bytes = extract_pdf_bytes(z_inner, raw_name)
                raw_text = read_pdf_text(pdf_bytes)
            except Exception as exc:
                self.stderr.write(f'  Ошибка чтения PDF: {exc}')
                total_errors += 1
                continue

            topic_name = extract_topic_from_header(raw_text)
            if not topic_name:
                self.stderr.write(f'  Не удалось извлечь тему, пропуск.')
                total_errors += 1
                continue

            self.stdout.write(f'  Тема: {topic_name!r}')

            text = clean_pdf_text(raw_text)

            try:
                problems = parse_problems(text)
            except Exception as exc:
                self.stderr.write(f'  Ошибка парсинга: {exc}')
                total_errors += 1
                continue

            self.stdout.write(f'  Задач найдено: {len(problems)}')

            topic_obj = get_or_create_topic(topic_name, topic_cache, dry_run)

            for num, statement, parts_data in problems:
                try:
                    if not statement and not parts_data:
                        continue

                    hash_base = statement or (parts_data[0][1] if parts_data else '')
                    stmt_hash = md5(hash_base)

                    if stmt_hash in existing_hashes:
                        total_skipped += 1
                        continue

                    if dry_run:
                        self.stdout.write(
                            f'  [dry] Задача {num}: {statement[:55]!r}'
                            f' — {len(parts_data)} подпунктов'
                        )
                        total_created += 1
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
                            note=f'ОЭШ 2022, {track}, {topic_name}, задача {num}',
                        )

                        for order, (label, content) in enumerate(parts_data):
                            ProblemPart.objects.create(
                                problem=problem,
                                label=label,
                                statement=content,
                                answer='',
                                order=order,
                            )

                    total_created += 1
                    existing_hashes.add(stmt_hash)

                except Exception as exc:
                    self.stderr.write(
                        f'  Ошибка при задаче {num} [{topic_name}]: {exc}'
                    )
                    total_errors += 1

        z_inner.close()

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
                f'\nИтог ОЭШ Олмат 2022: создано {total_created}, '
                f'пропущено {total_skipped}, ошибок {total_errors}'
            )
        )
