"""
Management command: import_ap_mocks_course

Импортирует MCQ-части авторских мок-экзаменов AP Economics (Course Mocks 2026):
  materials/AP Economics материалы/Macro Mocks/Course Mocks 2026/
  materials/AP Economics материалы/Micro Mocks/Course Mocks 2026/

Берутся ТОЛЬКО MCQ (FRQ из этих файлов уже импортированы import_ap_frq).
Файлы группируются по экзамену (Practice Exam N / Mock Exam N).

Три формата вопросов (детектируются автоматически):
  CB-style     — «N. … (A)…(E)» + ключ «Question N: X»/таблица
                 (используются парсеры из import_ap_mocks_cb).
  ReviewEcon   — «N. … a. b. c. d. e.» (строчные с точкой) + ключ
                 «N. <буква>. <разбор>» (Jacob Reed, ReviewEcon.com).
  AnswerInline — «N. … (A)…(E) … Answer X … <разбор>» (AP Micro 2026 Practice).

Часть файлов — это перепечатки реальных экзаменов CollegeBoard (Mock Exam 2 =
2019/2016 Paper), их вопросы уже в базе → отсеиваются дедупликацией.

MCQ → Problem(statement, answer=буква, solution=разбор,
              problem_type='тест: один ответ') + ProblemPart A–E.
difficulty=4, status=published. Теги «AP Economics» + «MCQ».
Источник: «AP Economics — Course Mocks 2026». Дедупликация по content_hash.

Запуск:
    python manage.py import_ap_mocks_course
    python manage.py import_ap_mocks_course --dry-run
"""
import hashlib
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone

from problems.models import Job, Problem, ProblemPart, Source, SourceReference, Tag
from problems.management.commands.import_ap_mocks_cb import (
    clean, pdf_text, find_mcq_options, parse_mcq, parse_mcq_key,
)

AP_FOLDER = Path(settings.BASE_DIR) / 'materials' / 'AP Economics материалы'
FOLDERS = [('Macro Mocks', 'Macro'), ('Micro Mocks', 'Micro')]
SUBDIR = 'Course Mocks 2026'
SOURCE_NAME = 'AP Economics — Course Mocks 2026'
DIFFICULTY = 4

EXAM_RE = re.compile(r'(Mock Exam \d+|Practice Exam(?:\s+\d+)?)')


def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def exam_key(name: str):
    m = EXAM_RE.search(name)
    return m.group(1) if m else None


# ── ReviewEcon-формат ──────────────────────────────────────────────────────

def parse_reviewecon_mcq(text: str):
    out = []
    qs = list(re.finditer(r'(?m)^\s*(\d+)\.\s', text))
    for i, m in enumerate(qs):
        num = int(m.group(1))
        s = m.end()
        e = qs[i + 1].start() if i + 1 < len(qs) else len(text)
        block = text[s:e]
        opos = list(re.finditer(r'(?m)^\s*([a-e])\.\s', block))
        if len(opos) < 4:
            continue
        statement = block[:opos[0].start()].strip()
        if len(statement) < 8:
            continue
        opts = []
        for j, om in enumerate(opos):
            oe = opos[j + 1].start() if j + 1 < len(opos) else len(block)
            opts.append((om.group(1).upper(), block[om.end():oe].strip()))
        out.append((num, statement, opts))
    return out


def parse_reviewecon_key(text: str) -> dict:
    """{num: (буква, разбор)}."""
    ans = {}
    ms = list(re.finditer(r'(?m)^\s*(\d+)\.\s+([a-e])\.\s', text))
    for i, m in enumerate(ms):
        num = int(m.group(1))
        s = m.end()
        e = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        ans[num] = (m.group(2).upper(), text[s:e].strip())
    return ans


# ── AnswerInline-формат ────────────────────────────────────────────────────

def parse_answerinline(text: str):
    out = []
    qs = list(re.finditer(r'(?m)^\s*(\d+)\.', text))
    for i, m in enumerate(qs):
        num = int(m.group(1))
        s = m.start()
        e = qs[i + 1].start() if i + 1 < len(qs) else len(text)
        block = text[s:e]
        am = re.search(r'(?m)^\s*Answer\s+([A-E])\b', block)
        if not am:
            continue
        parsed = find_mcq_options(block[:am.start()])
        if not parsed:
            continue
        statement, opts = parsed
        statement = re.sub(r'^\s*\d+\.\s*', '', statement).strip()
        if len(statement) < 8:
            continue
        out.append((num, statement, opts, am.group(1), block[am.end():].strip()))
    return out


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


def collect_mcqs(files):
    """Возвращает (format, list[(num, statement, opts, correct, solution)])."""
    combined = clean('\n'.join(pdf_text(p) for p in files))

    # ── ReviewEcon ──
    if 'ReviewEcon' in combined or 'reviewecon' in combined.lower():
        mcq_files = [p for p in files if '(MCQ)' in p.name
                     and 'Answer' not in p.name and 'Scoring' not in p.name]
        key_files = [p for p in files if 'Answer Key' in p.name]
        mcq_text = clean('\n'.join(pdf_text(p) for p in mcq_files)) if mcq_files else combined
        key_text = clean('\n'.join(pdf_text(p) for p in key_files)) if key_files else combined
        questions = parse_reviewecon_mcq(mcq_text)
        keys = parse_reviewecon_key(key_text)
        recs = []
        for num, stmt, opts in questions:
            letter, expl = keys.get(num, ('', ''))
            recs.append((num, stmt, opts, letter, expl))
        return 'ReviewEcon', recs

    # ── AnswerInline ──
    if re.search(r'(?m)^\s*Answer\s+[A-E]\b', combined):
        recs = parse_answerinline(combined)
        return 'AnswerInline', recs

    # ── CB-style ──
    mcqs = parse_mcq(combined)
    mkey = parse_mcq_key(combined)
    recs = [(num, stmt, opts, mkey.get(num, ''), '') for num, stmt, opts in mcqs]
    return 'CB', recs


class Command(BaseCommand):
    help = 'Импортирует MCQ авторских мок-экзаменов AP Economics (Course Mocks 2026)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        groups = []
        for folder, subj in FOLDERS:
            fdir = AP_FOLDER / folder / SUBDIR
            if not fdir.exists():
                self.stderr.write(f'Нет папки: {fdir}')
                continue
            by_key = {}
            for p in sorted(fdir.glob('*.pdf')):
                if 'Scoring Worksheet' in p.name or 'FRQ' in p.name:
                    continue
                k = exam_key(p.name)
                if not k:
                    continue
                by_key.setdefault(k, []).append(p)
            for k in sorted(by_key):
                # год, если есть в любом имени файла группы
                year = ''
                for p in by_key[k]:
                    ym = re.search(r'\b(20\d{2})\b', p.name)
                    if ym:
                        year = ym.group(1)
                        break
                groups.append((subj, k, year, by_key[k]))

        self.stdout.write(f'Групп-экзаменов: {len(groups)}')
        if dry_run:
            self.stdout.write(self.style.WARNING('Режим --dry-run.'))

        existing_hashes = set(
            Problem.objects.exclude(content_hash='').values_list('content_hash', flat=True)
        )
        tag_cache = {}
        source = job = None
        tag_ap = tag_mcq = None
        if not dry_run:
            source, _ = Source.objects.get_or_create(
                name=SOURCE_NAME,
                defaults={'kind': 'мок-экзамен',
                          'note': 'Авторские мок-экзамены AP Macro/Micro 2026'},
            )
            job = Job.objects.create(kind='import', status='running',
                                     params={'source': SOURCE_NAME, 'groups': len(groups)})
            tag_ap = ensure_tag('AP Economics', tag_cache)
            tag_mcq = ensure_tag('MCQ', tag_cache)

        created = skipped = errors = 0
        n_with_ans = 0

        for subj, key, year, files in groups:
            try:
                fmt, recs = collect_mcqs(files)
            except Exception as exc:
                self.stderr.write(f'  Ошибка чтения {subj} {key}: {exc}')
                errors += 1
                continue
            note = f'{subj}, {key}' + (f' ({year})' if year else '')
            self.stdout.write(
                f'\n→ {subj} {key} [{fmt}]: MCQ {len(recs)}, '
                f'с ответом {sum(1 for r in recs if r[3])}  [{len(files)} файл(ов)]')

            for num, statement, opts, correct, solution in recs:
                try:
                    if not statement or len(opts) < 4:
                        continue
                    stmt_hash = md5(statement)
                    if stmt_hash in existing_hashes:
                        skipped += 1
                        continue
                    if correct:
                        n_with_ans += 1
                    if dry_run:
                        created += 1
                        existing_hashes.add(stmt_hash)
                        continue
                    with transaction.atomic():
                        problem = Problem.objects.create(
                            title='', statement=statement, answer=correct,
                            solution=solution, problem_type='тест: один ответ',
                            difficulty=DIFFICULTY, status=Problem.Status.PUBLISHED,
                            content_hash=stmt_hash)
                        problem.tags.add(tag_ap, tag_mcq)
                        SourceReference.objects.create(
                            problem=problem, source=source,
                            note=f'AP {note}, MCQ #{num}')
                        for order, (L, txt) in enumerate(opts):
                            a = ('верно' if L == correct else 'неверно') if correct else ''
                            ProblemPart.objects.create(
                                problem=problem, label=L.lower(), statement=txt,
                                answer=a, order=order)
                    created += 1
                    existing_hashes.add(stmt_hash)
                except Exception as exc:
                    self.stderr.write(f'  Ошибка MCQ #{num}: {exc}')
                    errors += 1

        if not dry_run and job:
            job.status = 'done' if errors == 0 else 'failed'
            job.progress = 100
            job.finished_at = timezone.now()
            job.result = {'created': created, 'skipped': skipped, 'errors': errors,
                          'mcq_with_answer': n_with_ans}
            job.save(update_fields=['status', 'progress', 'finished_at', 'result'])

        self.stdout.write(self.style.SUCCESS(
            f'\nИтог Course Mocks: создано {created} (с ответом {n_with_ans}), '
            f'пропущено {skipped}, ошибок {errors}'))
