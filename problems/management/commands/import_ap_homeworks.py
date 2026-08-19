"""
Management command: import_ap_homeworks

Импортирует задачи AP Economics из домашних заданий (Homeworks).
Папки:
  materials/AP Economics материалы/Macro Homeworks/
  materials/AP Economics материалы/Micro Homeworks/

В каждой папке — пары файлов на каждый Unit:
  «AP Macro - Unit 1 HW (...).pdf»          — задания (вопросы)
  «ANSWERS AP Macro - Unit 1 HW.pdf»        — ключ ответов

Файлы парятся по номеру Unit (regex «Unit X[.Y]»).

Структура HW-файла:
  MCQs  — вопросы «N.» с вариантами «(a)…(e)»
  FRQs  — открытые вопросы «N.» с подпунктами «(a)…(e)» (или без)

Где брать правильный ответ MCQ (три формата ключа):
  1) terse  — строки «N. C» (буква ответа) — ранние Macro юниты.
  2) boxed  — вопросы повторены, правильный вариант обведён рамкой
              (4 отрезка-линии вокруг буквы). Определяем рамку через
              page.get_drawings() и сопоставляем с вариантом по координате Y.
              Буква ответа = порядковый номер варианта (1-й=A, 2-й=B, …),
              т.к. печатные метки в ключе иногда сбиты (двойная «C» и т.п.).
  Покрытие ответов ~97% вопросов; где рамка не найдена — answer пустой.

FRQ-ответы берутся из FRQ-раздела ключа, сопоставляются с вопросами HW
ПОЗИЦИОННО (i-й вопрос ↔ i-й блок ответа) — устойчиво к сбросу нумерации
при наличии разделов «Long FRQs» / «Short FRQs».

Создаёт:
  MCQ → Problem(statement, answer=буква, problem_type='тест: один ответ')
        + ProblemPart a–e (answer='верно'/'неверно')
  FRQ → Problem(statement, solution=полный разбор)
        + ProblemPart по подпунктам (answer=разбор подпункта)

difficulty=4, status=published.
Теги: «AP Economics» + «Homework» (+ «MCQ»/«FRQ»).
Источник: «AP Economics — Homeworks».
Дедупликация по content_hash (md5 условия).

Запуск:
    python manage.py import_ap_homeworks
    python manage.py import_ap_homeworks --dry-run
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
FOLDERS = [('Macro Homeworks', 'Macro'), ('Micro Homeworks', 'Micro')]
SOURCE_NAME = 'AP Economics — Homeworks'
DIFFICULTY = 4

# ── Регулярные выражения ──────────────────────────────────────────────────
UNIT_RE = re.compile(r'Unit\s+(\d+(?:\.\d+)?)')
MCQ_HDR = re.compile(r'(?mi)^\s*MCQs?\s*$')
FRQ_HDR = re.compile(r'(?mi)^\s*(?:Short |Long )?FRQs?\s*$')
# Terse ключ: «N. C»
TERSE_RE = re.compile(r'(?m)^\s*(\d+)\.\s+([A-E])\s*\.?\s*$')
# Маркер вопроса «N. »
QNUM_RE = re.compile(r'(?m)^\s*(\d+)\.\s')
QNUM_LINE_RE = re.compile(r'^\s*(\d+)\.\s')
# Вариант MCQ/подпункт FRQ в HW: «(a) …» (строчные, в скобках)
HW_OPT_RE = re.compile(r'(?m)^\s*\(([a-e])\)\s')
# Вариант в boxed-ключе: «(a)», «a)» — допускаем обе регистра, обе формы скобок
KEY_OPT_RE = re.compile(r'^\s*\(?\s*([A-Za-e])\)\s')
# Заголовок страницы
PG_HDR1_RE = re.compile(r'^\s*AP (?:Macro|Micro)economics[^\n]*\n')
PG_HDR2_RE = re.compile(r'^\s*Andrei Lengler[^\n]*\n')
PG_NUM_TAIL_RE = re.compile(r'\n\s*\d+\s*$')


# ── Вспомогательные функции ────────────────────────────────────────────────

def md5(text: str) -> str:
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()


def clean_pages(doc) -> str:
    """Извлекает текст постранично, убирая шапку и хвостовой номер страницы."""
    out = []
    for i in range(len(doc)):
        p = doc[i].get_text()
        p = PG_HDR1_RE.sub('', p)
        p = PG_HDR2_RE.sub('', p)
        p = PG_NUM_TAIL_RE.sub('', p.rstrip())
        out.append(p)
    return '\n'.join(out)


def dehyphenate(text: str) -> str:
    """«ma-\\nterial» → «material»."""
    return re.sub(r'(\w)-\n(\w)', r'\1\2', text)


def split_sections(full: str):
    """Возвращает (mcq_text, frq_text) по заголовкам MCQs / FRQs."""
    m = MCQ_HDR.search(full)
    f = FRQ_HDR.search(full, m.end() if m else 0)
    mcq = full[(m.end() if m else 0): (f.start() if f else len(full))]
    frq = full[f.end():] if f else ''
    return mcq, frq


def split_by_qnum(text: str):
    """Разбивает текст по «N. » → список (num, block)."""
    res = []
    pos = list(QNUM_RE.finditer(text))
    for i, m in enumerate(pos):
        s = m.end()
        e = pos[i + 1].start() if i + 1 < len(pos) else len(text)
        res.append((int(m.group(1)), text[s:e]))
    return res


def split_subparts(block: str):
    """Возвращает (statement, [(label, text), …]) по подпунктам «(a)…»."""
    pos = list(HW_OPT_RE.finditer(block))
    if not pos:
        return block.strip(), []
    statement = block[:pos[0].start()].strip()
    parts = []
    for i, m in enumerate(pos):
        s = m.end()
        e = pos[i + 1].start() if i + 1 < len(pos) else len(block)
        parts.append((m.group(1), block[s:e].strip()))
    return statement, parts


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


# ── Извлечение правильных букв MCQ из ключа ────────────────────────────────

def _merge_boxes(rects):
    """Сливает короткие отрезки-линии в прямоугольники (рамки) по координате Y."""
    rects = sorted(rects, key=lambda r: r[1])
    boxes = []
    for r in rects:
        if boxes and r[1] <= boxes[-1][3] + 6:
            b = boxes[-1]
            boxes[-1] = [min(b[0], r[0]), min(b[1], r[1]),
                         max(b[2], r[2]), max(b[3], r[3])]
        else:
            boxes.append(list(r))
    return [b for b in boxes if b[3] - b[1] > 6]


def _find_frq_bound(doc):
    """Координаты (page, y) первого заголовка FRQ (граница MCQ-раздела)."""
    for pi in range(len(doc)):
        for b in doc[pi].get_text('dict')['blocks']:
            for l in b.get('lines', []):
                t = ''.join(s['text'] for s in l['spans']).strip()
                if FRQ_HDR.match(t):
                    return pi, l['bbox'][1]
    return len(doc), float('inf')


def extract_mcq_answers(path: Path) -> dict:
    """Возвращает {номер_вопроса: буква} из файла-ключа."""
    doc = fitz.open(str(path))
    try:
        full = '\n'.join(doc[i].get_text() for i in range(len(doc)))
        mcq_text, _ = split_sections(full)
        terse = {int(a): b for a, b in TERSE_RE.findall(mcq_text)}
        if len(terse) >= 5:
            return terse

        # boxed: контекст вопроса/варианта сохраняется МЕЖДУ страницами
        frq_pi, frq_y = _find_frq_bound(doc)
        answers = {}
        cur_q = None
        opt_idx = 0
        opt_lines = []  # (page, bbox, q, idx)
        for pi in range(min(frq_pi + 1, len(doc))):
            ylim = frq_y if pi == frq_pi else float('inf')
            d = doc[pi].get_text('dict')
            lines = []
            for b in d['blocks']:
                for l in b.get('lines', []):
                    if l['bbox'][1] >= ylim:
                        continue
                    lines.append((l['bbox'], ''.join(s['text'] for s in l['spans'])))
            lines.sort(key=lambda x: (round(x[0][1]), x[0][0]))
            for bbox, txt in lines:
                t = txt.strip()
                mq = QNUM_LINE_RE.match(t)
                if mq and not t.startswith('('):
                    cur_q = int(mq.group(1))
                    opt_idx = 0
                    continue
                if KEY_OPT_RE.match(t) and cur_q is not None:
                    opt_lines.append((pi, bbox, cur_q, opt_idx))
                    opt_idx += 1
            rects = [[r['rect'][0], r['rect'][1], r['rect'][2], r['rect'][3]]
                     for r in doc[pi].get_drawings()
                     if (r['rect'][2] - r['rect'][0]) < 60]
            for bx in _merge_boxes(rects):
                if pi == frq_pi and bx[1] >= frq_y:
                    continue
                for (lp, bbox, q, idx) in opt_lines:
                    if lp != pi:
                        continue
                    yc = (bbox[1] + bbox[3]) / 2
                    if bx[1] - 3 <= yc <= bx[3] + 3:
                        answers[q] = chr(65 + idx)
                        break
        return answers
    finally:
        doc.close()


def extract_frq_answers(path: Path):
    """Возвращает список блоков-ответов FRQ в порядке следования.

    Каждый элемент: dict(full=весь текст блока, parts={label: text}).
    """
    doc = fitz.open(str(path))
    try:
        full = dehyphenate(clean_pages(doc))
    finally:
        doc.close()
    _, frq_text = split_sections(full)
    if not frq_text.strip():
        return []
    blocks = []
    for _num, block in split_by_qnum(frq_text):
        _stmt, parts = split_subparts(block)
        part_map = {label: text for label, text in parts}
        # solution: если есть верхнеуровневый «Answer:», берём после него
        sol = block.strip()
        m = re.search(r'(?mi)^\s*Answer\s*[:.]', block)
        if m and not parts:
            sol = block[m.end():].strip()
        blocks.append({'full': sol, 'parts': part_map})
    return blocks


# ── Команда ────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Импортирует AP Economics Homeworks (MCQ + FRQ) из PDF'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Только считать, ничего не писать в базу')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if not AP_FOLDER.exists():
            self.stderr.write(self.style.ERROR(f'Папка не найдена: {AP_FOLDER}'))
            return

        # Пары HW/ANSWERS по Unit
        units = []  # (subject, unit, hw_path, ans_path)
        for folder, subj in FOLDERS:
            fdir = AP_FOLDER / folder
            if not fdir.exists():
                self.stderr.write(f'Нет папки: {fdir}')
                continue
            pairs = {}
            for p in sorted(fdir.glob('*.pdf')):
                m = UNIT_RE.search(p.name)
                if not m:
                    continue
                u = m.group(1)
                is_ans = p.name.strip().upper().startswith('ANSWERS')
                pairs.setdefault(u, {})['ans' if is_ans else 'hw'] = p
            for u in sorted(pairs, key=lambda s: [int(x) for x in s.split('.')]):
                pr = pairs[u]
                if 'hw' in pr:
                    units.append((subj, u, pr['hw'], pr.get('ans')))

        self.stdout.write(f'Найдено юнитов (HW): {len(units)}')
        if dry_run:
            self.stdout.write(self.style.WARNING('Режим --dry-run: база не изменяется.'))

        existing_hashes = set(
            Problem.objects.exclude(content_hash='').values_list('content_hash', flat=True)
        )
        tag_cache = {}

        source = job = None
        tag_ap = tag_hw = tag_mcq = tag_frq = None
        if not dry_run:
            source, _ = Source.objects.get_or_create(
                name=SOURCE_NAME,
                defaults={'kind': 'домашние задания',
                          'note': 'AP Macro/Micro Homeworks, Andrei Lengler, 2025–2026'},
            )
            job = Job.objects.create(
                kind='import', status='running',
                params={'source': SOURCE_NAME, 'units': len(units)},
            )
            tag_ap = ensure_tag('AP Economics', tag_cache)
            tag_hw = ensure_tag('Homework', tag_cache)
            tag_mcq = ensure_tag('MCQ', tag_cache)
            tag_frq = ensure_tag('FRQ', tag_cache)

        created = skipped = errors = 0
        n_mcq = n_frq = n_with_ans = 0

        for subj, u, hw_path, ans_path in units:
            self.stdout.write(f'\n→ {subj} Unit {u}  ({hw_path.name})')

            # Парсим HW
            try:
                doc = fitz.open(str(hw_path))
                full = dehyphenate(clean_pages(doc))
                doc.close()
            except Exception as exc:
                self.stderr.write(f'  Ошибка чтения HW: {exc}')
                errors += 1
                continue

            mcq_text, frq_text = split_sections(full)
            mcq_blocks = split_by_qnum(mcq_text)
            frq_blocks = split_by_qnum(frq_text) if frq_text.strip() else []

            # Ответы из ключа
            mcq_answers = {}
            frq_answer_blocks = []
            if ans_path:
                try:
                    mcq_answers = extract_mcq_answers(ans_path)
                    frq_answer_blocks = extract_frq_answers(ans_path)
                except Exception as exc:
                    self.stderr.write(f'  Ошибка чтения ключа: {exc}')
            self.stdout.write(
                f'  MCQ: {len(mcq_blocks)} (ответов {len(mcq_answers)}), '
                f'FRQ: {len(frq_blocks)} (ключей {len(frq_answer_blocks)})'
            )

            # ── MCQ ──────────────────────────────────────────────────────
            for q_num, block in mcq_blocks:
                try:
                    statement, opts = split_subparts(block)
                    if not statement or not opts:
                        continue
                    stmt_hash = md5(statement)
                    if stmt_hash in existing_hashes:
                        skipped += 1
                        continue
                    correct = mcq_answers.get(q_num, '')
                    if correct:
                        n_with_ans += 1
                    n_mcq += 1

                    if dry_run:
                        created += 1
                        existing_hashes.add(stmt_hash)
                        continue

                    with transaction.atomic():
                        problem = Problem.objects.create(
                            title='',
                            statement=statement,
                            answer=correct,
                            problem_type='тест: один ответ',
                            difficulty=DIFFICULTY,
                            status=Problem.Status.PUBLISHED,
                            content_hash=stmt_hash,
                        )
                        problem.tags.add(tag_ap, tag_hw, tag_mcq)
                        SourceReference.objects.create(
                            problem=problem, source=source,
                            note=f'AP {subj}, Unit {u}, MCQ #{q_num}',
                        )
                        for order, (label, text) in enumerate(opts):
                            if correct:
                                ans = 'верно' if label.upper() == correct else 'неверно'
                            else:
                                ans = ''
                            ProblemPart.objects.create(
                                problem=problem, label=label, statement=text,
                                answer=ans, order=order,
                            )
                    created += 1
                    existing_hashes.add(stmt_hash)
                except Exception as exc:
                    self.stderr.write(f'  Ошибка MCQ #{q_num}: {exc}')
                    errors += 1

            # ── FRQ ──────────────────────────────────────────────────────
            for i, (q_num, block) in enumerate(frq_blocks):
                try:
                    statement, parts = split_subparts(block)
                    if not statement and not parts:
                        continue
                    hash_base = statement or (parts[0][1] if parts else '')
                    if not hash_base:
                        continue
                    stmt_hash = md5(hash_base)
                    if stmt_hash in existing_hashes:
                        skipped += 1
                        continue
                    n_frq += 1

                    # позиционное сопоставление с ключом
                    ans_block = frq_answer_blocks[i] if i < len(frq_answer_blocks) else None
                    solution = ans_block['full'] if ans_block else ''
                    ans_parts = ans_block['parts'] if ans_block else {}

                    if dry_run:
                        created += 1
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
                        problem.tags.add(tag_ap, tag_hw, tag_frq)
                        SourceReference.objects.create(
                            problem=problem, source=source,
                            note=f'AP {subj}, Unit {u}, FRQ #{q_num}',
                        )
                        for order, (label, text) in enumerate(parts):
                            ProblemPart.objects.create(
                                problem=problem, label=label, statement=text,
                                answer=ans_parts.get(label, ''), order=order,
                            )
                    created += 1
                    existing_hashes.add(stmt_hash)
                except Exception as exc:
                    self.stderr.write(f'  Ошибка FRQ #{q_num}: {exc}')
                    errors += 1

        if not dry_run and job:
            job.status = 'done' if errors == 0 else 'failed'
            job.progress = 100
            job.finished_at = timezone.now()
            job.result = {'created': created, 'skipped': skipped, 'errors': errors,
                          'mcq': n_mcq, 'frq': n_frq, 'mcq_with_answer': n_with_ans}
            job.save(update_fields=['status', 'progress', 'finished_at', 'result'])

        self.stdout.write(self.style.SUCCESS(
            f'\nИтог AP Homeworks: создано {created}, пропущено {skipped}, '
            f'ошибок {errors}\n'
            f'  MCQ: {n_mcq} (с ответом {n_with_ans}), FRQ: {n_frq}'
        ))
