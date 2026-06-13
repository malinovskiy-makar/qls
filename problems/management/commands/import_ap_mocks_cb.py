"""
Management command: import_ap_mocks_cb

Импортирует реальные экзамены CollegeBoard AP Economics из папок:
  materials/AP Economics материалы/Macro Mocks/Independent Mocks 2026/
  materials/AP Economics материалы/Micro Mocks/Independent Mocks 2026/

Берутся ТОЛЬКО реальные экзамены CollegeBoard (не авторские моки —
те лежат в «Course Mocks 2026», см. import_ap_mocks_course).

Файлы одного экзамена могут быть разбиты на части (MCQ / FRQ / ключи) или
лежать одним PDF «Answer Key Inside». Поэтому файлы группируются по
идентификатору экзамена (год из имени, иначе метка «Practice Exam 2» и т.п.),
тексты всех частей склеиваются, и из общего текста извлекаются:
  - MCQ-вопросы: «N. … (A)…(E)» (заглавные варианты в скобках)
  - ключ MCQ:  «Question N: X»  ИЛИ табличный «N \\n X» в разделе Answer Key
  - FRQ-вопросы: «N. … (a)…(b)…» (строчные подпункты) + разбор из Scoring Guide

Сканы без текстового слоя (Micro 2005, Macro 2025, …) пропускаются.

MCQ → Problem(statement, answer=буква, problem_type='тест: один ответ')
      + ProblemPart A–E (answer='верно'/'неверно')
FRQ → Problem(statement, solution=scoring guidelines) + ProblemPart по подпунктам

difficulty=4, status=published.
Теги: «AP Economics» + «MCQ»/«FRQ».
Год → SourceReference.note.
Источник: «AP Economics — CollegeBoard Exams».
Дедупликация по content_hash.

Запуск:
    python manage.py import_ap_mocks_cb
    python manage.py import_ap_mocks_cb --dry-run
"""
import hashlib
import re
from pathlib import Path

import fitz  # pymupdf

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone

from problems.models import Job, Problem, ProblemPart, Source, SourceReference, Tag


AP_FOLDER = Path(settings.BASE_DIR) / 'materials' / 'AP Economics материалы'
FOLDERS = [('Macro Mocks', 'Macro'), ('Micro Mocks', 'Micro')]
SUBDIR = 'Independent Mocks 2026'
SOURCE_NAME = 'AP Economics — CollegeBoard Exams'
DIFFICULTY = 4

# ── Очистка служебного текста ──────────────────────────────────────────────
JUNK_RE = re.compile(
    r'(?mi)^.*(?:Downloaded by|lOMoARcPSD|Studocu|Scan to open|'
    r'not sponsored or endorsed|College Board|AP Central|collegeboard\.org|'
    r'GO ON TO THE NEXT PAGE|Unauthorized copying|This exam may not be posted|'
    r'Exams may not be posted|Teachers are permitted|This practice exam is provided).*$'
)
PAGE_MARK_RE = re.compile(r'(?m)^\s*-\s*\d+\s*-\s*$')
BLANK_PAGE_RE = re.compile(r'(?mi)^\s*(?:BLANK PAGE|STOP|END OF (?:SECTION|EXAM)).*$')

# Граница, где обрывать «хвост» варианта (E) / блока вопроса
BOUNDARY_RE = re.compile(
    r'(END OF SECTION|GO ON TO|STOP\b|Section II|Multiple-Choice Answer Key|'
    r'Free-Response|Scoring Guidelines)'
)

# ── MCQ ────────────────────────────────────────────────────────────────────
QNUM_RE = re.compile(r'(?m)^\s*(\d+)\.\s')
KEY_Q_RE = re.compile(r'Question\s+(\d+):\s*([A-E])\b')
KEY_TBL_RE = re.compile(r'(\d+)\s*\n\s*([A-E])(?=\s)')
ANSKEY_START_RE = re.compile(r'(Multiple-Choice Answer Key|Answer Key for AP)')
ANSKEY_END_RE = re.compile(r'(Free-Response|Scoring Guidelines)')

# FRQ-подпункты — строчные «(a)»
SUBLOW_RE = re.compile(r'(?m)^\s*\(([a-h])\)\s')


def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def pdf_text(path: Path) -> str:
    doc = fitz.open(str(path))
    try:
        return '\n'.join(doc[i].get_text() for i in range(len(doc)))
    finally:
        doc.close()


def clean(text: str) -> str:
    text = JUNK_RE.sub('', text)
    text = PAGE_MARK_RE.sub('', text)
    text = BLANK_PAGE_RE.sub('', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def exam_key(name: str):
    m = re.search(r'\b(20\d{2})\b', name)
    if m:
        return m.group(1)
    if 'Practice Exam 2' in name:
        return 'Practice Exam 2'
    if 'Practice Test' in name:
        return 'Practice Test'
    return None


def find_mcq_options(block: str):
    """Возвращает (statement, [(letter, text), …]) если есть варианты A→E по порядку."""
    a_pos = block.find('(A)')
    if a_pos < 0:
        return None
    statement = block[:a_pos].strip()
    if len(statement) < 8:
        return None
    # последовательно ищем A,B,C,D,E
    marks = []
    pos = a_pos
    for L in 'ABCDE':
        m = re.compile(r'\(' + L + r'\)\s').search(block, pos)
        if not m:
            break
        marks.append((L, m.end()))
        pos = m.end()
    if len(marks) < 4:   # допускаем 4 (иногда E «съедается»), но обычно 5
        return None
    opts = []
    for i, (L, start) in enumerate(marks):
        end = marks[i + 1][1] - 3 if i + 1 < len(marks) else len(block)
        # у первого после marks[i+1] нужно отрезать «(B)\s» — берём до начала следующего маркера
        if i + 1 < len(marks):
            nxt = block.rfind('(' + marks[i + 1][0] + ')', start, marks[i + 1][1])
            end = nxt if nxt > start else marks[i + 1][1] - 4
        opts.append((L, block[start:end].strip()))
    return statement, opts


def parse_mcq(text: str):
    """Список (num, statement, [(letter, text), …])."""
    out = []
    qs = list(QNUM_RE.finditer(text))
    for i, m in enumerate(qs):
        num = int(m.group(1))
        s = m.end()
        e = qs[i + 1].start() if i + 1 < len(qs) else len(text)
        block = text[s:e]
        bm = BOUNDARY_RE.search(block)
        if bm:
            block = block[:bm.start()]
        if len(block) > 2000:
            block = block[:2000]
        parsed = find_mcq_options(block)
        if parsed:
            out.append((num, parsed[0], parsed[1]))
    return out


def parse_mcq_key(text: str) -> dict:
    ans = {}
    for m in KEY_Q_RE.finditer(text):
        ans[int(m.group(1))] = m.group(2)
    if len(ans) >= 10:
        return ans
    # табличная форма: якорь — НАСТОЯЩИЙ заголовок ключа (не строка оглавления).
    anchor = None
    m = re.search(r'Answer Key for AP', text)
    if m:
        anchor = m.start()
    else:
        occ = [mm.start() for mm in re.finditer(r'Multiple-Choice Answer Key', text)]
        if occ:
            anchor = occ[-1]   # последнее вхождение — реальный ключ, не оглавление
    if anchor is not None:
        region = text[anchor:anchor + 5000]
        em = ANSKEY_END_RE.search(region, 60)
        if em:
            region = region[:em.start()]
        for m in KEY_TBL_RE.finditer(region):
            n = int(m.group(1))
            if 1 <= n <= 80:
                ans[n] = m.group(2)
    return ans


def parse_frq(text: str):
    """Список (num, statement, [(label, text), …]) — блоки со строчными (a)(b)."""
    out = []
    qs = list(QNUM_RE.finditer(text))
    seen = set()
    for i, m in enumerate(qs):
        num = int(m.group(1))
        s = m.end()
        e = qs[i + 1].start() if i + 1 < len(qs) else len(text)
        block = text[s:e]
        subs = list(SUBLOW_RE.finditer(block))
        # FRQ: есть строчные (a) и (b), нет пятёрки заглавных вариантов
        if len(subs) < 2:
            continue
        if block.find('(A)') >= 0 and block.find('(B)') >= 0 and block.find('(A)') < subs[0].start():
            continue
        if len(block) > 4000:
            block = block[:4000]
            subs = list(SUBLOW_RE.finditer(block))
        statement = block[:subs[0].start()].strip()
        if len(statement) < 15:
            continue
        if num in seen:
            continue
        seen.add(num)
        parts = []
        for j, sm in enumerate(subs):
            se = subs[j + 1].start() if j + 1 < len(subs) else len(block)
            parts.append((sm.group(1), block[sm.end():se].strip()))
        out.append((num, statement, parts))
    return out


def parse_frq_scoring(text: str) -> dict:
    """{num: текст разбора} из раздела Scoring Guidelines.

    Заголовок разбора FRQ — «Question N» ОТДЕЛЬНОЙ строкой (а не «Question N: X»,
    что является ключом MCQ). Поэтому якорь — `^Question N$`.
    """
    res = {}
    pos = [(int(m.group(1)), m.start())
           for m in re.finditer(r'(?m)^\s*Question\s+(\d+)\s*$', text)]
    for i, (num, s) in enumerate(pos):
        e = pos[i + 1][1] if i + 1 < len(pos) else len(text)
        body = text[s:e].strip()
        if num not in res or len(body) > len(res[num]):
            res[num] = body
    return res


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


class Command(BaseCommand):
    help = 'Импортирует реальные экзамены CollegeBoard AP Economics'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # ── собрать группы экзаменов ──────────────────────────────────────
        groups = []  # (subject, key, [paths])
        for folder, subj in FOLDERS:
            fdir = AP_FOLDER / folder / SUBDIR
            if not fdir.exists():
                self.stderr.write(f'Нет папки: {fdir}')
                continue
            by_key = {}
            for p in sorted(fdir.glob('*.pdf')):
                if 'Scoring Worksheet' in p.name:
                    continue
                k = exam_key(p.name)
                if not k:
                    continue
                by_key.setdefault(k, []).append(p)
            for k in sorted(by_key):
                groups.append((subj, k, by_key[k]))

        self.stdout.write(f'Групп-экзаменов: {len(groups)}')
        if dry_run:
            self.stdout.write(self.style.WARNING('Режим --dry-run.'))

        existing_hashes = set(
            Problem.objects.exclude(content_hash='').values_list('content_hash', flat=True)
        )
        tag_cache = {}
        source = job = None
        tag_ap = tag_mcq = tag_frq = None
        if not dry_run:
            source, _ = Source.objects.get_or_create(
                name=SOURCE_NAME,
                defaults={'kind': 'экзамен',
                          'note': 'Реальные экзамены CollegeBoard AP Macro/Micro'},
            )
            job = Job.objects.create(kind='import', status='running',
                                     params={'source': SOURCE_NAME, 'groups': len(groups)})
            tag_ap = ensure_tag('AP Economics', tag_cache)
            tag_mcq = ensure_tag('MCQ', tag_cache)
            tag_frq = ensure_tag('FRQ', tag_cache)

        created = skipped = errors = 0
        n_mcq = n_frq = n_with_ans = 0

        for subj, key, paths in groups:
            combined = clean('\n'.join(pdf_text(p) for p in paths))
            mcqs = parse_mcq(combined)
            mkey = parse_mcq_key(combined)
            frqs = parse_frq(combined)
            scoring = parse_frq_scoring(combined)
            note = f'{key}' if re.match(r'^20\d{2}$', key) else key
            self.stdout.write(
                f'\n→ {subj} {key}: MCQ {len(mcqs)} (ключей {len(mkey)}), '
                f'FRQ {len(frqs)} (разборов {len(scoring)})  [{len(paths)} файл(ов)]'
            )

            # ── MCQ ──────────────────────────────────────────────────────
            for num, statement, opts in mcqs:
                try:
                    stmt_hash = md5(statement)
                    if stmt_hash in existing_hashes:
                        skipped += 1
                        continue
                    correct = mkey.get(num, '')
                    if correct:
                        n_with_ans += 1
                    n_mcq += 1
                    if dry_run:
                        created += 1
                        existing_hashes.add(stmt_hash)
                        continue
                    with transaction.atomic():
                        problem = Problem.objects.create(
                            title='', statement=statement, answer=correct,
                            problem_type='тест: один ответ', difficulty=DIFFICULTY,
                            status=Problem.Status.PUBLISHED, content_hash=stmt_hash,
                        )
                        problem.tags.add(tag_ap, tag_mcq)
                        SourceReference.objects.create(
                            problem=problem, source=source,
                            note=f'AP {subj} {note}, MCQ #{num}')
                        for order, (L, txt) in enumerate(opts):
                            a = ('верно' if L == correct else 'неверно') if correct else ''
                            ProblemPart.objects.create(
                                problem=problem, label=L, statement=txt,
                                answer=a, order=order)
                    created += 1
                    existing_hashes.add(stmt_hash)
                except Exception as exc:
                    self.stderr.write(f'  Ошибка MCQ #{num}: {exc}')
                    errors += 1

            # ── FRQ ──────────────────────────────────────────────────────
            for num, statement, parts in frqs:
                try:
                    stmt_hash = md5(statement)
                    if stmt_hash in existing_hashes:
                        skipped += 1
                        continue
                    n_frq += 1
                    solution = scoring.get(num, '')
                    if dry_run:
                        created += 1
                        existing_hashes.add(stmt_hash)
                        continue
                    with transaction.atomic():
                        problem = Problem.objects.create(
                            title='', statement=statement, solution=solution,
                            difficulty=DIFFICULTY, status=Problem.Status.PUBLISHED,
                            content_hash=stmt_hash)
                        problem.tags.add(tag_ap, tag_frq)
                        SourceReference.objects.create(
                            problem=problem, source=source,
                            note=f'AP {subj} {note}, FRQ #{num}')
                        for order, (L, txt) in enumerate(parts):
                            ProblemPart.objects.create(
                                problem=problem, label=L, statement=txt,
                                answer='', order=order)
                    created += 1
                    existing_hashes.add(stmt_hash)
                except Exception as exc:
                    self.stderr.write(f'  Ошибка FRQ #{num}: {exc}')
                    errors += 1

        if not dry_run and job:
            job.status = 'done' if errors == 0 else 'failed'
            job.progress = 100
            job.finished_at = timezone.now()
            job.result = {'created': created, 'skipped': skipped, 'errors': errors,
                          'mcq': n_mcq, 'frq': n_frq, 'mcq_with_answer': n_with_ans}
            job.save(update_fields=['status', 'progress', 'finished_at', 'result'])

        self.stdout.write(self.style.SUCCESS(
            f'\nИтог CollegeBoard: создано {created}, пропущено {skipped}, '
            f'ошибок {errors}\n  MCQ {n_mcq} (с ответом {n_with_ans}), FRQ {n_frq}'))
