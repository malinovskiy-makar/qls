"""
Management command: import_pdf_bakharev

Импортирует задачи из «Сборник тренировочных задач по олимпиадной экономике»
(Бахарев Рэм, PDF, 206 стр.). Использует PyMuPDF для извлечения текста.

Запуск:
    python manage.py import_pdf_bakharev
    python manage.py import_pdf_bakharev --file /path/to/file.pdf
    python manage.py import_pdf_bakharev --dry-run
"""
import hashlib
import re
from pathlib import Path

import fitz  # pymupdf

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from problems.models import Job, Problem, ProblemPart, Source, SourceReference, Topic


PDF_PATH = (
    Path(settings.BASE_DIR)
    / 'materials' / 'Archive 6' / 'Archive 5'
    / 'Задачник_по_экономике_Бахарев copy.pdf'
)

BATCH_SIZE = 50

# Название темы по номеру главы (из оглавления)
CHAPTER_TOPICS = {
    2: 'Альтернативный выбор, явные и неявные издержки',
    3: 'Теория потребителя и полезность',
    4: 'Теория фирмы: производство, издержки, выручка, прибыль',
    5: 'КПВ',
    6: 'Монополия',
    7: 'Совершенная конкуренция',
    8: 'Олигополия',
    9: 'Модель спроса и предложения, госвмешательство',
    10: 'Общественное благосостояние',
    11: 'Эластичность',
    12: 'Финансы',
    13: 'Неравенство в распределении доходов',
    14: 'Макроэкономика',
}

# Шапка на каждой странице PDF
HEADER_RE = re.compile(
    r'Сборник тренировочных задач по олимпиадной экономике\s*\n'
    r'Бахарев Рэм\s*\n',
    re.MULTILINE,
)

# «Задача N ***» на отдельной строке
TASK_RE = re.compile(r'^Задача\s+(\d+)\s+(\*+)\s*$', re.MULTILINE)

# N..M\n — маркер подраздела (общий)
SUBCHAP_MARKER_RE = re.compile(r'^(\d+)\.\.(\d+)\s*\n', re.MULTILINE)

# N..M\n[пробелы]Ответы — блок ответов главы
ANSWER_BLOCK_HDR_RE = re.compile(
    r'^(\d+)\.\.(\d+)\s*\n\s*Ответы\s*\n', re.MULTILINE
)

# K) — начало ответа на задачу K в блоке ответов
ANS_ITEM_RE = re.compile(r'(?:^|\n)(\d+)\)\s*', re.MULTILINE)

# (а) в тексте задачи — маркер подпункта
SUBPART_RE = re.compile(r'\(([а-яё])\)')

# Транслит для slug тем
_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
    'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
    'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya', ' ': '-', ':': '', ',': '',
}


def _make_slug(name: str) -> str:
    chars = [_TRANSLIT.get(c, c) for c in name.lower()]
    slug = ''.join(c for c in ''.join(chars) if c.isalnum() or c == '-')
    return slug[:110] or 'topic'


# ---------------------------------------------------------------------------
# Парсинг PDF
# ---------------------------------------------------------------------------

def extract_full_text(pdf_path: Path) -> str:
    """Извлекает текст PDF, убирает повторяющиеся шапки и номера страниц."""
    doc = fitz.open(str(pdf_path))
    pages = [doc[i].get_text() for i in range(len(doc))]
    doc.close()
    full = '\n'.join(pages)
    full = HEADER_RE.sub('\n', full)
    # Одиночный номер страницы на строке (1–3 цифры)
    full = re.sub(r'^\s*\d{1,3}\s*$', '', full, flags=re.MULTILINE)
    return full


def parse_subparts(body: str):
    """
    Разбивает тело задачи на основной текст и подпункты.
    Маркер подпункта: (а), (б), (в)...
    Возвращает (main_text, {'а': text, 'б': text, ...}).
    """
    matches = list(SUBPART_RE.finditer(body))
    if not matches:
        return body.strip(), {}
    main = body[:matches[0].start()].strip()
    parts = {}
    for i, m in enumerate(matches):
        label = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        parts[label] = body[start:end].strip()
    return main, parts


def parse_answers(answer_text: str) -> dict:
    """
    Парсит блок ответов главы.
    Возвращает {task_num: {None: text} | {subpart_letter: text}}.
    """
    result = {}
    items = list(ANS_ITEM_RE.finditer(answer_text))
    for i, m in enumerate(items):
        num = int(m.group(1))
        start = m.end()
        end = items[i + 1].start() if i + 1 < len(items) else len(answer_text)
        body = answer_text[start:end].strip()

        # Подпункты «а) ...», «б) ...» — буква не предшествует другой букве
        sp_matches = list(re.finditer(r'(?<![а-яё])([а-яё])\)\s*', body))
        if sp_matches:
            subparts = {}
            before = body[:sp_matches[0].start()].strip()
            if before:
                subparts[None] = before
            for j, sm in enumerate(sp_matches):
                sp_label = sm.group(1)
                sp_start = sm.end()
                sp_end = (sp_matches[j + 1].start()
                          if j + 1 < len(sp_matches) else len(body))
                subparts[sp_label] = body[sp_start:sp_end].strip()
            result[num] = subparts
        else:
            result[num] = {None: body}
    return result


def parse_document(text: str) -> list:
    """
    Основной парсер: разбирает весь текст PDF на задачи с ответами.

    Возвращает list[dict]:
        chapter_num, task_num, stars, main, parts, answer, answer_parts
    """
    # Позиции answer-блоков (чтобы не путать с subchap-маркерами)
    answer_start_positions: set = set()
    events = []

    for m in ANSWER_BLOCK_HDR_RE.finditer(text):
        answer_start_positions.add(m.start())
        events.append((m.start(), 'answer', {
            'chapter_num': int(m.group(1)),
            'body_start': m.end(),
        }))

    for m in SUBCHAP_MARKER_RE.finditer(text):
        if m.start() in answer_start_positions:
            continue  # уже обработан как answer block
        events.append((m.start(), 'subchap', {
            'chapter_num': int(m.group(1)),
        }))

    for m in TASK_RE.finditer(text):
        events.append((m.start(), 'task', {
            'task_num': int(m.group(1)),
            'stars': m.group(2),
            'body_start': m.end(),
        }))

    # Детектируем заголовки глав как отдельные строки.
    # Нужно для глав без подразделов (11 «Эластичность», 13 «Неравенство...»):
    # их задачи иначе попадают в предыдущую главу.
    # В TOC имена глав идут с префиксом «N.Название» — не совпадут.
    for chap_num, chap_name in CHAPTER_TOPICS.items():
        # Первые слова достаточно уникальны; разрешаем необязательный \s
        # на случай тонких различий в пробелах при экстракции.
        pattern = re.compile(
            r'^' + re.escape(chap_name) + r'\s*$', re.MULTILINE
        )
        for m in pattern.finditer(text):
            events.append((m.start(), 'chapter_header', {
                'chapter_num': chap_num,
            }))

    events.sort(key=lambda e: e[0])

    # Обходим события в порядке документа
    # Задачи главы 2 идут до первого N..M маркера → current_chapter = 2
    current_chapter = 2
    raw_tasks = []      # список dict с полями chapter, task_num, stars, body
    answer_blocks = {}  # chapter_num → parse_answers(...)

    for i, (pos, etype, data) in enumerate(events):
        next_pos = events[i + 1][0] if i + 1 < len(events) else len(text)

        if etype in ('subchap', 'chapter_header'):
            current_chapter = data['chapter_num']

        elif etype == 'task':
            body = text[data['body_start']:next_pos].strip()
            raw_tasks.append({
                'chapter': current_chapter,
                'task_num': data['task_num'],
                'stars': data['stars'],
                'body': body,
            })

        elif etype == 'answer':
            chapter_num = data['chapter_num']
            ans_text = text[data['body_start']:next_pos]
            answer_blocks[chapter_num] = parse_answers(ans_text)

    # Собираем финальные записи с ответами
    records = []
    for task in raw_tasks:
        chap = task['chapter']
        tnum = task['task_num']
        stars = task['stars']
        body = task['body']

        main, parts = parse_subparts(body)
        if not main and not parts:
            continue

        chapter_answers = answer_blocks.get(chap, {})
        task_ans_data = chapter_answers.get(tnum, {})

        answer = task_ans_data.get(None, '')
        answer_parts = {k: v for k, v in task_ans_data.items() if k is not None}

        records.append({
            'chapter_num': chap,
            'task_num': tnum,
            'stars': stars,
            'main': main,
            'parts': parts,
            'answer': answer,
            'answer_parts': answer_parts,
        })

    return records


# ---------------------------------------------------------------------------
# Django management command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Импортирует задачи из PDF Бахарева (Сборник тренировочных задач)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', type=str, default=str(PDF_PATH),
            help='Путь к PDF файлу',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Показать статистику без записи в базу',
        )

    def handle(self, *args, **options):
        pdf_path = Path(options['file'])
        dry_run = options['dry_run']

        if not pdf_path.exists():
            self.stderr.write(self.style.ERROR(f'Файл не найден: {pdf_path}'))
            return

        # ── Извлечение текста ─────────────────────────────────────────────
        self.stdout.write(f'Читаю PDF: {pdf_path.name}')
        full_text = extract_full_text(pdf_path)
        self.stdout.write(f'Текст извлечён, символов: {len(full_text)}')

        # ── Парсинг ───────────────────────────────────────────────────────
        self.stdout.write('Парсю задачи...')
        records = parse_document(full_text)
        total = len(records)

        # Диагностика
        chapters_found = {}
        for rec in records:
            chapters_found[rec['chapter_num']] = (
                chapters_found.get(rec['chapter_num'], 0) + 1
            )
        self.stdout.write(f'Найдено задач: {total}')
        for chap_num in sorted(chapters_found):
            topic = CHAPTER_TOPICS.get(chap_num, '?')
            self.stdout.write(
                f'  Глава {chap_num}: {chapters_found[chap_num]} задач ({topic})'
            )

        if dry_run:
            self.stdout.write('(dry-run: в базу ничего не пишем)')
            # Показываем первые 3 задачи для проверки
            for rec in records[:3]:
                self.stdout.write(
                    f'\n--- Гл.{rec["chapter_num"]} Зад.{rec["task_num"]} '
                    f'{rec["stars"]} ---\n'
                    f'Условие: {rec["main"][:120]}\n'
                    f'Подпункты: {list(rec["parts"].keys())}\n'
                    f'Ответ: {rec["answer"][:80]}\n'
                    f'Ответы подпунктов: {list(rec["answer_parts"].keys())}'
                )
            return

        # ── Источник ─────────────────────────────────────────────────────
        source, created_src = Source.objects.get_or_create(
            name='Бахарев — Сборник тренировочных задач',
            defaults={
                'kind': 'сборник задач',
                'note': (
                    'Бахарев Рэм, «Сборник тренировочных задач '
                    'по олимпиадной экономике».'
                ),
            },
        )
        self.stdout.write(
            f'Источник «{source.name}» '
            f'{"создан" if created_src else "найден"}: #{source.pk}'
        )

        # ── Job ───────────────────────────────────────────────────────────
        job = Job.objects.create(
            kind=Job.Kind.IMPORT,
            status=Job.Status.RUNNING,
            params={'file': str(pdf_path), 'total': total},
        )
        self.stdout.write(f'Job #{job.pk} создан')

        # ── Кэши ─────────────────────────────────────────────────────────
        existing_hashes: set = set(
            Problem.objects.exclude(content_hash='')
            .values_list('content_hash', flat=True)
        )
        topic_cache: dict = {t.name: t for t in Topic.objects.all()}

        # ── Основной цикл: батчами по {BATCH_SIZE} ────────────────────────
        created = skipped = errors = 0

        for batch_start in range(0, total, BATCH_SIZE):
            batch = records[batch_start:batch_start + BATCH_SIZE]

            with transaction.atomic():
                for rec in batch:
                    stmt = rec['main']
                    if not stmt and rec['parts']:
                        first_label = next(iter(rec['parts']))
                        stmt = f'({first_label}) ' + rec['parts'][first_label]
                    if not stmt:
                        continue

                    stmt_hash = hashlib.md5(stmt.encode(), usedforsecurity=False).hexdigest()
                    if stmt_hash in existing_hashes:
                        skipped += 1
                        continue

                    try:
                        with transaction.atomic():
                            topic_name = CHAPTER_TOPICS.get(rec['chapter_num'], '')
                            topic_obj = None
                            if topic_name:
                                if topic_name not in topic_cache:
                                    base_slug = _make_slug(topic_name)
                                    slug = base_slug
                                    counter = 1
                                    while Topic.objects.filter(slug=slug).exists():
                                        slug = f'{base_slug}-{counter}'
                                        counter += 1
                                    topic_cache[topic_name] = Topic.objects.create(
                                        name=topic_name, slug=slug
                                    )
                                topic_obj = topic_cache[topic_name]

                            # Заголовок — первые ~80 символов до переноса
                            title = stmt.split('\n')[0].strip()[:80]
                            if not title:
                                title = f'Задача {rec["task_num"]}'

                            difficulty = len(rec['stars'])  # * → 1, **** → 4

                            p = Problem.objects.create(
                                title=title,
                                statement=stmt,
                                answer=rec['answer'],
                                difficulty=difficulty,
                                difficulty_native=rec['stars'],
                                status=Problem.Status.DRAFT,
                                content_hash=stmt_hash,
                                problem_type='',
                            )

                            if topic_obj:
                                p.topics.add(topic_obj)

                            SourceReference.objects.create(
                                problem=p,
                                source=source,
                                note=(
                                    f'Глава {rec["chapter_num"]}, '
                                    f'задача {rec["task_num"]}'
                                ),
                            )

                            for idx, (label, part_text) in enumerate(
                                rec['parts'].items()
                            ):
                                ans = rec['answer_parts'].get(label, '')
                                ProblemPart.objects.create(
                                    problem=p,
                                    label=label,
                                    statement=part_text,
                                    answer=ans,
                                    order=idx,
                                )

                        existing_hashes.add(stmt_hash)
                        created += 1

                    except Exception as exc:
                        errors += 1
                        self.stderr.write(
                            f'  Ошибка: гл.{rec["chapter_num"]} '
                            f'зад.{rec["task_num"]}: {exc}'
                        )

            done = min(batch_start + BATCH_SIZE, total)
            progress = int(done / total * 100) if total else 100

            job.progress = progress
            job.result = {'created': created, 'skipped': skipped, 'errors': errors}
            job.save(update_fields=['progress', 'result'])

            self.stdout.write(
                f'  [{done:4d}/{total}]  '
                f'создано: {created},  пропущено: {skipped},  ошибок: {errors}'
            )

        # ── Завершаем Job ─────────────────────────────────────────────────
        job.status = Job.Status.DONE
        job.progress = 100
        job.finished_at = timezone.now()
        job.result = {'created': created, 'skipped': skipped, 'errors': errors}
        job.save(update_fields=['status', 'progress', 'finished_at', 'result'])

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово!\n'
            f'  Создано задач:     {created}\n'
            f'  Пропущено (дубли): {skipped}\n'
            f'  Ошибок:            {errors}\n'
            f'  Job #{job.pk}: {job.status}'
        ))
