"""
Management command: import_ap_real2026

Импортирует MCQ и FRQ из реальных экзаменов AP Economics 2026.
Файлы:
  materials/AP Economics материалы/[ANSWERS] AP Macroeconomics Real 2026 Exam.pdf
  materials/AP Economics материалы/[ANSWERS] AP Microeconomics Real 2026 Exam.pdf

Структура каждого файла (Andrei Lengler, May 2026):
  MCQs — 60 вопросов, формат:
    «N. [вопрос]»
    «(A) вариант A» ... «(E) вариант E»
    «Answer: X. объяснение»
  FRQs — 3 вопроса (1 Long + 2 Short), формат:
    «N. (Long/Short FRQ) [вопрос]»
    «(a) [текст]»
    «Answer / Scoring Guideline: N points. [ответ]»
    «(b) ...»

MCQ создаёт:
  Problem: statement = вопрос (без вариантов), answer = буква, solution = объяснение
           problem_type = 'тест: один ответ'
  ProblemPart A-E: statement = вариант, answer = 'верно'/'неверно'
FRQ создаёт:
  Problem: statement = вопрос до первого (a), solution = все рубрики
  ProblemPart a-...: statement = вопрос подпункта, answer = рубрика оценивания

difficulty=4, status=published.
Теги: 'MCQ'/'FRQ' + 'AP Economics'.
Источник: 'AP Economics — Real Exams 2026'.
Дедупликация по content_hash.

Запуск:
    python manage.py import_ap_real2026
    python manage.py import_ap_real2026 --dry-run
"""
import hashlib
import re
from pathlib import Path

import fitz  # pymupdf

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction

from problems.models import Job, Problem, ProblemPart, Source, SourceReference, Tag


AP_FOLDER = Path(settings.BASE_DIR) / 'materials' / 'AP Economics материалы'
SOURCE_NAME = 'AP Economics — Real Exams 2026'
DIFFICULTY = 4

PDF_FILES = [
    '[ANSWERS] AP Macroeconomics Real 2026 Exam.pdf',
    '[ANSWERS] AP Microeconomics Real 2026 Exam.pdf',
]

# ── Regex ──────────────────────────────────────────────────────────────────

# Заголовок каждой страницы: «AP Macro/Microeconomics\nAndrei Lengler\n»
PAGE_HEADER_RE = re.compile(
    r'(?m)^AP (?:Macro|Micro)economics\nAndrei Lengler\n',
    re.UNICODE,
)
# Одиночный номер страницы
PAGE_NUM_RE = re.compile(r'(?m)^\d+\s*$')

# Границы разделов
MCQ_SECTION_RE = re.compile(r'(?m)^MCQs\s*$')
FRQ_SECTION_RE = re.compile(r'(?m)^FRQs\s*$')

# MCQ: вопрос в начале строки «N. »
MCQ_Q_RE = re.compile(r'(?m)^(\d+)\.\s+', re.UNICODE)
# MCQ: вариант ответа «(A) » ... «(E) »
MCQ_OPT_RE = re.compile(r'(?m)^\(([A-E])\)\s+', re.UNICODE)
# MCQ: строка с ответом «Answer: X. explanation»
MCQ_ANS_RE = re.compile(r'(?m)^Answer:\s+([A-E])\.\s+', re.UNICODE)

# FRQ: вопрос «N. (Long/Short FRQ) text» или просто «N. text»
FRQ_Q_SPLIT_RE = re.compile(r'(?m)^(\d+)\.\s+', re.UNICODE)
FRQ_TYPE_RE = re.compile(r'^\((?:Long|Short)\s+FRQ\)\s+', re.IGNORECASE)
# FRQ: подпункт «(a) text» в начале строки (строчные латинские)
FRQ_SUB_RE = re.compile(r'(?m)^\(([a-h])\)\s+', re.UNICODE)
# FRQ: граница рубрики оценивания
FRQ_RUBRIC_RE = re.compile(
    r'Answer\s*/\s*Scoring\s+Guideline[s]?:\s*\d+\s+points?\.?\s*',
    re.IGNORECASE | re.UNICODE,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def clean_text(text: str) -> str:
    text = PAGE_HEADER_RE.sub('', text)
    text = PAGE_NUM_RE.sub('', text)
    return text


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


# ── MCQ parsing ────────────────────────────────────────────────────────────

def split_mcq_question(block: str) -> dict:
    """
    Разбирает блок MCQ на: statement, options, answer, solution.
    block — текст от «N. » до следующего «N. »
    """
    # Найдём первый вариант (A)
    opt_matches = list(MCQ_OPT_RE.finditer(block))
    ans_match = MCQ_ANS_RE.search(block)

    if not opt_matches:
        return None
    if not ans_match:
        return None

    # Вопрос — текст до первого варианта
    statement = block[:opt_matches[0].start()].strip()

    # Варианты
    options = {}
    for i, m in enumerate(opt_matches):
        label = m.group(1)
        content_start = m.end()
        if i + 1 < len(opt_matches):
            content_end = opt_matches[i + 1].start()
        else:
            content_end = ans_match.start()
        options[label] = block[content_start:content_end].strip()

    # Правильный ответ и объяснение
    correct = ans_match.group(1)
    solution = block[ans_match.end():].strip()

    return {
        'statement': statement,
        'options': options,
        'answer': correct,
        'solution': solution,
    }


def parse_mcq_section(text: str) -> list:
    """
    Возвращает список dict (statement, options, answer, solution) для каждого MCQ.
    """
    matches = list(MCQ_Q_RE.finditer(text))
    results = []
    for i, m in enumerate(matches):
        num = int(m.group(1))
        block_start = m.end()
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[block_start:block_end]
        parsed = split_mcq_question(block)
        if parsed and parsed['statement']:
            results.append((num, parsed))
    return results


# ── FRQ parsing ────────────────────────────────────────────────────────────

def split_frq_subparts(body: str) -> tuple:
    """
    Разбивает тело FRQ-вопроса на (statement, [(label, question_text, answer_text), ...]).
    """
    sub_matches = list(FRQ_SUB_RE.finditer(body))
    if not sub_matches:
        return body.strip(), []

    statement = body[:sub_matches[0].start()].strip()
    parts = []

    for i, m in enumerate(sub_matches):
        label = m.group(1)
        content_start = m.end()
        content_end = sub_matches[i + 1].start() if i + 1 < len(sub_matches) else len(body)
        content = body[content_start:content_end]

        # Внутри подпункта найдём рубрику
        rubric_m = FRQ_RUBRIC_RE.search(content)
        if rubric_m:
            q_text = content[:rubric_m.start()].strip()
            a_text = content[rubric_m.end():].strip()
        else:
            q_text = content.strip()
            a_text = ''

        parts.append((label, q_text, a_text))

    return statement, parts


def parse_frq_section(text: str) -> list:
    """
    Возвращает список (q_num, statement, parts) для FRQ-вопросов.
    """
    matches = list(FRQ_Q_SPLIT_RE.finditer(text))
    results = []
    for i, m in enumerate(matches):
        num = int(m.group(1))
        block_start = m.end()
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[block_start:block_end]
        # Убираем «(Long FRQ)» / «(Short FRQ)» в начале
        body = FRQ_TYPE_RE.sub('', body.lstrip())
        statement, parts = split_frq_subparts(body)
        if statement.strip() or parts:
            results.append((num, statement.strip(), parts))
    return results


# ── Main command ───────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Импортирует MCQ и FRQ из реальных экзаменов AP Economics 2026'

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
        tag_cache: dict = {}

        source = job = None
        if not dry_run:
            source, _ = Source.objects.get_or_create(
                name=SOURCE_NAME,
                defaults={
                    'kind': 'экзамен',
                    'note': 'Реальные экзамены AP Macro и Micro, май 2026, Andrei Lengler',
                },
            )
            job = Job.objects.create(
                kind='import',
                status='running',
                params={'source': SOURCE_NAME},
                started_by=None,
            )
            tag_mcq = ensure_tag('MCQ', tag_cache)
            tag_frq = ensure_tag('FRQ', tag_cache)
            tag_ap = ensure_tag('AP Economics', tag_cache)
        else:
            tag_mcq = tag_frq = tag_ap = None

        total_created = total_skipped = total_errors = 0

        for pdf_name in PDF_FILES:
            pdf_path = AP_FOLDER / pdf_name
            if not pdf_path.exists():
                self.stderr.write(self.style.ERROR(f'Файл не найден: {pdf_path}'))
                total_errors += 1
                continue

            self.stdout.write(f'\n→ {pdf_name}')

            # Извлекаем текст
            try:
                doc = fitz.open(str(pdf_path))
                pages = [doc[i].get_text() for i in range(len(doc))]
                doc.close()
                full_text = '\n'.join(pages)
            except Exception as exc:
                self.stderr.write(f'  Ошибка чтения: {exc}')
                total_errors += 1
                continue

            text = clean_text(full_text)

            # Разбиваем на разделы MCQ / FRQ
            m_mcq = MCQ_SECTION_RE.search(text)
            m_frq = FRQ_SECTION_RE.search(text)

            if not m_mcq:
                self.stderr.write('  Не найден раздел MCQs')
                total_errors += 1
                continue

            mcq_text = text[m_mcq.end(): m_frq.start() if m_frq else len(text)]
            frq_text = text[m_frq.end():] if m_frq else ''

            # Субъект (Macro / Micro)
            subject = 'Macro' if 'Macroeconomics' in pdf_name else 'Micro'

            # ── MCQ ──────────────────────────────────────────────────────
            mcq_questions = parse_mcq_section(mcq_text)
            self.stdout.write(f'  MCQ вопросов: {len(mcq_questions)}')

            for q_num, parsed in mcq_questions:
                try:
                    stmt = parsed['statement']
                    opts = parsed['options']
                    correct = parsed['answer']
                    sol = parsed['solution']

                    if not stmt:
                        continue

                    stmt_hash = md5(stmt)
                    if stmt_hash in existing_hashes:
                        total_skipped += 1
                        continue

                    if dry_run:
                        self.stdout.write(
                            f'  [MCQ dry] Q{q_num} [{subject}]: {stmt[:55]!r}'
                            f' → {correct}'
                        )
                        total_created += 1
                        existing_hashes.add(stmt_hash)
                        continue

                    with transaction.atomic():
                        problem = Problem.objects.create(
                            title='',
                            statement=stmt,
                            answer=correct,
                            solution=sol,
                            problem_type='тест: один ответ',
                            difficulty=DIFFICULTY,
                            status=Problem.Status.PUBLISHED,
                            content_hash=stmt_hash,
                        )
                        problem.tags.add(tag_mcq, tag_ap)

                        SourceReference.objects.create(
                            problem=problem,
                            source=source,
                            note=f'AP {subject}, MCQ #{q_num}',
                        )

                        for order, letter in enumerate(['A', 'B', 'C', 'D', 'E']):
                            if letter not in opts:
                                continue
                            ProblemPart.objects.create(
                                problem=problem,
                                label=letter,
                                statement=opts[letter],
                                answer='верно' if letter == correct else 'неверно',
                                order=order,
                            )

                    total_created += 1
                    existing_hashes.add(stmt_hash)

                except Exception as exc:
                    self.stderr.write(f'  Ошибка MCQ Q{q_num}: {exc}')
                    total_errors += 1

            # ── FRQ ──────────────────────────────────────────────────────
            if not frq_text:
                self.stdout.write('  FRQ раздел не найден, пропуск.')
                continue

            frq_questions = parse_frq_section(frq_text)
            self.stdout.write(f'  FRQ вопросов: {len(frq_questions)}')

            for q_num, statement, parts in frq_questions:
                try:
                    if not statement and not parts:
                        continue

                    hash_base = statement or (parts[0][1] if parts else '')
                    stmt_hash = md5(hash_base)
                    if stmt_hash in existing_hashes:
                        total_skipped += 1
                        continue

                    # Решение = все рубрики оценивания через \n
                    solution = '\n'.join(
                        a for _, _, a in parts if a
                    )

                    if dry_run:
                        self.stdout.write(
                            f'  [FRQ dry] Q{q_num} [{subject}]: {statement[:55]!r}'
                            f' — {len(parts)} подпунктов'
                        )
                        total_created += 1
                        existing_hashes.add(stmt_hash)
                        continue

                    with transaction.atomic():
                        problem = Problem.objects.create(
                            title='',
                            statement=statement,
                            solution=solution,
                            difficulty=DIFFICULTY,
                            status=Problem.Status.PUBLISHED,
                            content_hash=stmt_hash,
                        )
                        problem.tags.add(tag_frq, tag_ap)

                        SourceReference.objects.create(
                            problem=problem,
                            source=source,
                            note=f'AP {subject}, FRQ #{q_num}',
                        )

                        for order, (label, q_text, a_text) in enumerate(parts):
                            ProblemPart.objects.create(
                                problem=problem,
                                label=label,
                                statement=q_text,
                                answer=a_text,
                                order=order,
                            )

                    total_created += 1
                    existing_hashes.add(stmt_hash)

                except Exception as exc:
                    self.stderr.write(f'  Ошибка FRQ Q{q_num}: {exc}')
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
                f'\nИтог AP Real 2026: создано {total_created}, '
                f'пропущено {total_skipped}, ошибок {total_errors}'
            )
        )
