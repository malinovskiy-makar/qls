"""
Management command: import_pdf_shivarov

Импортирует тестовые вопросы из «Сборник тестов по экономике»
(Шиваров А.А. и др., Олмат.Экономика, 488 стр., 30 апр 2026).

Типы вопросов: Верно/Неверно, Один правильный ответ, Все верные ответы.
Вопросы со свободным ответом — пропускаются (нет вариантов а/б/в...).

Запуск:
    python manage.py import_pdf_shivarov
    python manage.py import_pdf_shivarov --dry-run
    python manage.py import_pdf_shivarov --file /путь/к/файлу.pdf
"""
import hashlib
import re
from pathlib import Path

import fitz  # pymupdf

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from problems.models import (
    Job, Problem, ProblemPart, Source, SourceReference, Topic,
)


PDF_PATH = (
    Path(settings.BASE_DIR) / 'materials' / 'Сборник тестов АА (30 апр 2026).pdf'
)

BATCH_SIZE = 50

# Стандартный заголовок на каждой странице (убирается перед парсингом)
PAGE_HEADER_RE = re.compile(
    r'Олмат\s*«Экономика»\s*\nСборник тестов\s+\d{4}\s*\n',
    re.MULTILINE,
)

# Разделы: (название темы, PyMuPDF-индекс первой страницы).
# PyMuPDF index = LaTeX page number из оглавления (проверено).
SECTIONS = [
    ('Математика',                                          4),
    ('Спрос и предложение',                                15),
    ('Полезность и выбор потребителя',                     37),
    ('Производство',                                       54),
    ('Кривые производственных и торговых возможностей и АИ', 64),
    ('Кривые торговых возможностей',                       90),
    ('Издержки производства',                              98),
    ('Монополия',                                         119),
    ('Совершенная конкуренция',                           144),
    ('Олигополия и теория игр',                           163),
    ('Вмешательство государства',                         173),
    ('Рыночные структуры',                                202),
    ('Рынок труда и профсоюзы',                           227),
    ('Международная торговля',                            241),
    ('Эластичность',                                      248),
    ('Неравенство доходов, индекс Джинни и кривая Лоренца', 278),
    ('Финансы–Микро',                                290),  # en-dash без пробелов
    ('Разное в микроэкономике',                           306),
    ('Модель кругооборота',                               321),
    ('ВВП и ВНП',                                         325),
    ('Индексы цен и дефлятор',                            343),
    ('Безработица и закон Оукена',                        359),
    ('Модель AD-AS',                                      373),
    ('Экономические циклы',                               385),
    ('Фискальная политика',                               394),
    ('Монетарная политика',                               408),
    ('Валюта и обменный курс',                            427),
    ('Финансы – Макро',                              440),  # en-dash с пробелами
    ('Разное про макроэкономику',                         445),
    ('Качественные вопросы и логические ошибки',          456),
    ('Вопросы на знание экономических фактов',            462),
    ('Редкие вопросы микроэкономики',                     467),
    ('Редкие вопросы макроэкономики',                     476),
]

# Заголовки блоков вопросов внутри раздела → тип блока
BLOCK_PATTERNS = [
    ('true_false', re.compile(r'Вопросы\s+типа\s+.Верно/Неверно.', re.IGNORECASE)),
    ('single',     re.compile(r'Вопросы\s+на\s+один\s+правильный\s+ответ', re.IGNORECASE)),
    ('multiple',   re.compile(r'Вопросы\s+на\s+все\s+верные\s+ответы', re.IGNORECASE)),
    ('open',       re.compile(r'Вопросы\s+с(?:о\s+свободным|\s+открытым)\s+ответ', re.IGNORECASE)),
]

# Маркер блока ответов в конце раздела
ANSWERS_MARKER_RE = re.compile(r'(?:^|\n)\s*Ответы\s*\n', re.MULTILINE)

# Маркеры типов ответов внутри ответного блока
ANS_TYPE_MARKERS = [
    ('true_false', re.compile(r'«Верно/Неверно»')),
    ('single',     re.compile(r'«Один\s+ответ»')),
    ('multiple',   re.compile(r'«Все\s+верные»')),
    ('open',       re.compile(r'«Свободный\s+ответ»')),
]

# Начало нового вопроса в блоке: цифра + точка + пробел в начале строки
QUESTION_START_RE = re.compile(r'(?:^|\n)(\d+)\.\s+', re.MULTILINE)

# Вариант ответа: а) или a) в начале строки (кириллица и латиница)
OPTION_RE = re.compile(r'^([аaбвгд])\)\s*', re.MULTILINE)

# Источник в начале вопроса: (МОШ 2009), (Региональный этап ВОШ 2018) и т.д.
INLINE_SOURCE_RE = re.compile(r'^\(([^)]{2,100})\)\s*')

# Транслит для slug тем
_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
    'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
    'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya', ' ': '-', ':': '', ',': '',
    '–': '-', '—': '-', '/': '-',
}


def _make_slug(name: str) -> str:
    chars = [_TRANSLIT.get(c, c) for c in name.lower()]
    slug = ''.join(c for c in ''.join(chars) if c.isalnum() or c == '-')
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug[:110] or 'topic'


# ---------------------------------------------------------------------------
# Извлечение и разбивка текста
# ---------------------------------------------------------------------------

def extract_pages(pdf_path: Path) -> list:
    """
    Извлекает текст каждой страницы PDF, убирает стандартный заголовок
    и номер страницы в конце.
    """
    doc = fitz.open(str(pdf_path))
    pages = []
    for i in range(len(doc)):
        text = doc[i].get_text()
        text = PAGE_HEADER_RE.sub('', text)
        # Убираем одиночный номер страницы в конце страницы (1–3 цифры)
        text = re.sub(r'\n\s*\d{1,3}\s*$', '', text.rstrip())
        pages.append(text)
    doc.close()
    return pages


def get_section_text(pages: list, start_idx: int, end_idx: int) -> str:
    """Склеивает страницы раздела в один текст."""
    return '\n'.join(pages[start_idx:end_idx])


# ---------------------------------------------------------------------------
# Парсинг блока ответов
# ---------------------------------------------------------------------------

def parse_answer_block(ans_text: str) -> dict:
    """
    Парсит блок «Ответы» в конце раздела.

    Формат:
        Ответы
        «Верно/Неверно»
        1. а
        2. б
        «Один ответ»
        1. б
        ...

    Возвращает {block_type: {num: answer_str}}.
    """
    result = {k: {} for k, _ in ANS_TYPE_MARKERS}
    current_type = None
    pending_num = None
    pending_lines = []

    def flush():
        if pending_num is not None and current_type:
            result[current_type][pending_num] = ' '.join(pending_lines).strip()

    for line in ans_text.split('\n'):
        s = line.strip()
        if not s:
            continue

        # Пропускаем строку-заголовок «Ответы»
        if s.lower() in ('ответы', 'ответы:'):
            continue

        # Проверяем маркер типа («Верно/Неверно», «Один ответ», …)
        matched = None
        for t, pat in ANS_TYPE_MARKERS:
            if pat.search(s):
                matched = t
                break
        if matched:
            flush()
            current_type = matched
            pending_num = None
            pending_lines = []
            continue

        if current_type is None:
            continue

        # Строка ответа: «1. а» или «1. ад» или «1. 42,5»
        m = re.match(r'^(\d+)\.\s*(.+)$', s)
        if m:
            flush()
            pending_num = int(m.group(1))
            pending_lines = [m.group(2).strip()]
        elif pending_num is not None:
            # Продолжение многострочного ответа (числовые задачи)
            pending_lines.append(s)

    flush()
    return result


# ---------------------------------------------------------------------------
# Парсинг вопросов из блока
# ---------------------------------------------------------------------------

def parse_options(raw: str):
    """
    Разделяет текст вопроса на условие и варианты ответов.
    Возвращает (stmt, {label: text}).
    """
    opts = list(OPTION_RE.finditer(raw))
    if not opts:
        return raw.strip(), {}

    stmt = raw[:opts[0].start()].strip()
    options = {}
    for j, om in enumerate(opts):
        label = om.group(1)
        if label == 'a':  # латинская a → кириллическая а
            label = 'а'
        opt_start = om.end()
        opt_end = opts[j + 1].start() if j + 1 < len(opts) else len(raw)
        options[label] = raw[opt_start:opt_end].strip()

    return stmt, options


def parse_questions(block_text: str) -> list:
    """
    Парсит все вопросы из одного блока.
    Возвращает list[dict]: {num, source_ref, statement, options}.
    """
    matches = list(QUESTION_START_RE.finditer(block_text))
    questions = []

    for i, m in enumerate(matches):
        num = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block_text)
        raw = block_text[start:end].strip()

        # Источник в начале: (МОШ 2009), (Региональный этап ВОШ 2018), …
        src_m = INLINE_SOURCE_RE.match(raw)
        source_ref = ''
        if src_m:
            source_ref = src_m.group(1).strip()
            raw = raw[src_m.end():]

        stmt, options = parse_options(raw)

        questions.append({
            'num': num,
            'source_ref': source_ref,
            'statement': stmt,
            'options': options,
        })

    return questions


# ---------------------------------------------------------------------------
# Парсинг раздела
# ---------------------------------------------------------------------------

def parse_section(text: str) -> dict:
    """
    Парсит один раздел: находит блоки вопросов и блок ответов.

    Возвращает:
        {
          blocks: [{'block_type': ..., 'questions': [...]}],
          answers: {'true_false': {N: 'а'}, 'single': {N: 'б'}, ...}
        }
    """
    # Отделяем блок ответов от блока вопросов
    ans_m = ANSWERS_MARKER_RE.search(text)
    if ans_m:
        question_text = text[:ans_m.start()]
        answer_text = text[ans_m.start():]
    else:
        question_text = text
        answer_text = ''

    answers = parse_answer_block(answer_text) if answer_text else {}

    # Находим позиции заголовков блоков вопросов
    block_events = []
    for btype, pat in BLOCK_PATTERNS:
        for m in pat.finditer(question_text):
            block_events.append((m.start(), btype, m.end()))
    block_events.sort(key=lambda x: x[0])

    # Парсим каждый блок (пропускаем «открытый»/«свободный» ответ)
    blocks = []
    for i, (bstart, btype, btext_start) in enumerate(block_events):
        if btype == 'open':
            continue
        bend = block_events[i + 1][0] if i + 1 < len(block_events) else len(question_text)
        block_content = question_text[btext_start:bend]
        qs = parse_questions(block_content)
        if qs:
            blocks.append({'block_type': btype, 'questions': qs})

    return {'blocks': blocks, 'answers': answers}


# ---------------------------------------------------------------------------
# Django management command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Импортирует тестовые вопросы из Сборника тестов АА (Шиваров и др.)'

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

        # ── Извлечение текста ────────────────────────────────────────────────
        self.stdout.write(f'Читаю PDF: {pdf_path.name}')
        pages = extract_pages(pdf_path)
        self.stdout.write(f'Страниц: {len(pages)}')

        # ── Разбивка на разделы по индексам страниц из оглавления ───────────
        self.stdout.write('Парсю разделы...')
        all_records = []  # список всех вопросов для импорта

        for sec_idx, (topic_name, start_page) in enumerate(SECTIONS):
            end_page = (
                SECTIONS[sec_idx + 1][1]
                if sec_idx + 1 < len(SECTIONS)
                else len(pages)
            )
            section_text = get_section_text(pages, start_page, end_page)
            parsed = parse_section(section_text)

            sec_count = sum(len(b['questions']) for b in parsed['blocks'])

            for block in parsed['blocks']:
                btype = block['block_type']
                answers = parsed['answers'].get(btype, {})
                for q in block['questions']:
                    all_records.append({
                        'topic_name': topic_name,
                        'block_type': btype,
                        'num': q['num'],
                        'source_ref': q['source_ref'],
                        'statement': q['statement'],
                        'options': q['options'],
                        'answer': answers.get(q['num'], ''),
                    })

            self.stdout.write(
                f'  [{topic_name[:45]}]: {sec_count} вопросов'
            )

        total = len(all_records)
        self.stdout.write(f'\nВсего вопросов найдено: {total}')

        if dry_run:
            self.stdout.write('(dry-run: база не изменяется)')
            self.stdout.write('\nПримеры (первые 3 записи):')
            for rec in all_records[:3]:
                self.stdout.write(
                    f'  [{rec["block_type"]}] №{rec["num"]} '
                    f'({rec["source_ref"][:40]})\n'
                    f'  {rec["statement"][:100]}\n'
                    f'  Варианты: {list(rec["options"].keys())}\n'
                    f'  Ответ: {rec["answer"]}'
                )
            return

        # ── Источник ─────────────────────────────────────────────────────────
        source, src_created = Source.objects.get_or_create(
            name='Сборник тестов АА',
            defaults={
                'author': 'Шиваров А.А., Хроменко А.Д., Шиварова А.А.',
                'year': 2026,
                'kind': 'сборник тестов',
                'note': (
                    'Олмат.Экономика, «Сборник тестов по экономике», '
                    'составлен на основе олимпиад прошлых лет, апр 2026.'
                ),
            },
        )
        self.stdout.write(
            f'Источник «{source.name}» '
            f'{"создан" if src_created else "найден"}: #{source.pk}'
        )

        # ── Job ───────────────────────────────────────────────────────────────
        job = Job.objects.create(
            kind=Job.Kind.IMPORT,
            status=Job.Status.RUNNING,
            params={'file': str(pdf_path), 'total': total},
        )
        self.stdout.write(f'Job #{job.pk} создан')

        # ── Кэши ─────────────────────────────────────────────────────────────
        existing_hashes: set = set(
            Problem.objects.exclude(content_hash='')
            .values_list('content_hash', flat=True)
        )
        topic_cache: dict = {t.name: t for t in Topic.objects.all()}

        created = skipped = errors = 0

        # ── Основной цикл: батчами по {BATCH_SIZE} ────────────────────────────
        for batch_start in range(0, total, BATCH_SIZE):
            batch = all_records[batch_start:batch_start + BATCH_SIZE]

            with transaction.atomic():
                for rec in batch:
                    stmt = rec['statement']
                    if not stmt:
                        skipped += 1
                        continue

                    stmt_hash = hashlib.md5(stmt.encode()).hexdigest()
                    if stmt_hash in existing_hashes:
                        skipped += 1
                        continue

                    try:
                        with transaction.atomic():
                            # Тема
                            tname = rec['topic_name']
                            if tname not in topic_cache:
                                base_slug = _make_slug(tname)
                                slug = base_slug
                                counter = 1
                                while Topic.objects.filter(slug=slug).exists():
                                    slug = f'{base_slug}-{counter}'
                                    counter += 1
                                topic_cache[tname] = Topic.objects.create(
                                    name=tname, slug=slug,
                                )
                            topic_obj = topic_cache[tname]

                            # Заголовок — первые 80 символов условия
                            title = stmt.split('\n')[0].strip()[:80]
                            if not title:
                                title = f'Вопрос {rec["num"]}'

                            # Тип вопроса
                            ptype_map = {
                                'true_false': 'тест: верно/неверно',
                                'single':     'тест: один ответ',
                                'multiple':   'тест: все верные',
                            }
                            prob_type = ptype_map.get(rec['block_type'], 'тест')

                            p = Problem.objects.create(
                                title=title,
                                statement=stmt,
                                answer=rec['answer'],
                                status=Problem.Status.PUBLISHED,
                                problem_type=prob_type,
                                content_hash=stmt_hash,
                            )
                            p.topics.add(topic_obj)

                            # Привязка к источнику
                            SourceReference.objects.create(
                                problem=p,
                                source=source,
                                note=rec['source_ref'],
                            )

                            # ProblemPart — один на каждый вариант ответа (а, б, в, г, д)
                            for idx, (label, opt_text) in enumerate(
                                rec['options'].items()
                            ):
                                ProblemPart.objects.create(
                                    problem=p,
                                    label=label,
                                    statement=opt_text,
                                    answer='',  # правильный ответ — в Problem.answer
                                    order=idx,
                                )

                        existing_hashes.add(stmt_hash)
                        created += 1

                    except Exception as exc:
                        errors += 1
                        self.stderr.write(
                            f'  Ошибка: тема={rec["topic_name"][:30]} '
                            f'тип={rec["block_type"]} №{rec["num"]}: {exc}'
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

        # ── Завершаем Job ─────────────────────────────────────────────────────
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
