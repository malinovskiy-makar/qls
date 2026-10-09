# -*- coding: utf-8 -*-
"""Сборка расшифрованных страниц в задания эталона v2.

Вход — `digitized\\` папки аудита: `events_files.jsonl` (комплект → файлы
условий, решений, критериев), страницы `pages\\<sha16>\\p<N>.json`
(расшифровка, `transcribe.py`) и `p<N>.png`. Выход:
`reference_problems_v2.jsonl` (задание = условие + рисунки + решение +
критерии + баллы), `events_v2.jsonl`, `figures\\<event_id>_<номер>_<k>.png`,
сверка с нарезкой v1 — `compare_v1_v2.csv`.

Склейка: `task_continuation` дописывается к заданию со своим номером, а
без номера — к последнему заданию файла (продолжение через страницу).
Решения и критерии ложатся на задания по (комплект, номер, вариант
задания), а без номера — по названию (rapidfuzz ≥ 0,85).

В базу не пишет ничего; эталон v2 — источник правды для импорта
следующей сессии (v1 — нарезка текста PDF — больше не используется).
"""
from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, OrderedDict, defaultdict
from datetime import date

from rapidfuzz import fuzz

from problems.olympiad_grades import parse_grades

TITLE_MATCH = 0.85
#: Рамка рисунка расширяется на 2 % размера страницы с каждой стороны.
FIGURE_PAD = 0.02
#: Вырезка с разбросом яркости меньше этого — пустая/залитая (флаг).
EMPTY_STDDEV = 4.0

_NUM = re.compile(r'\d+(?:[.,]\d+)?')
_LIST_ITEM = re.compile(r'^\s*(?:[-*]\s*)?(\(?[а-яa-z]\)|\d{1,2}[.)])\s+(.*)$')


def norm_number(value):
    """«Задача 3.» → «3», «2,1» → «2.1»; без цифр — как есть в нижнем
    регистре; «тест-4» остаётся «тест-4»."""
    text = str(value or '').strip()
    if text.startswith('тест-'):
        return text
    match = _NUM.search(text)
    if not match:
        return text.lower()
    return match.group().replace(',', '.')


def _read_jsonl(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_page(root, page_dir, page):
    path = os.path.join(root, page_dir, f'p{page}.json')
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


class Task:
    """Задание в сборке."""

    def __init__(self, event_id, number, task_variant=''):
        self.event_id, self.number, self.task_variant = event_id, number, task_variant
        self.title, self.points = '', None
        self.statement, self.solution, self.criteria = [], [], []
        self.answer = ''
        self.figures = []           # (page_dir, page, bbox, caption)
        self.solution_figures = []  # рисунки из решения — так же
        self.own_figures = False    # были ли рисунки из файла условий
        self.pages = []             # (file, page) — откуда условие
        self.solution_pages, self.criteria_pages = [], []
        self.criteria_points = None
        self.quality = []           # записи страниц, давших текст
        self.from_solution_only = False

    @property
    def key(self):
        return (self.number, self.task_variant)


def _block_number(block):
    return norm_number(block.get('number')) if block.get('number') not in (None, '') else ''


def collect(root, files, role):
    """Блоки файлов комплекта по порядку страниц: [(файл, страница,
    запись страницы, блок)]. role — tasks/solutions/criteria."""
    out = []
    for entry in files:
        if not entry.get('page_dir'):
            continue      # docx: текст напрямую, страниц нет (см. docx_records)
        for page in range(1, int(entry.get('pages') or 0) + 1):
            record = load_page(root, entry['page_dir'], page)
            if record is None:
                out.append((entry, page, None, None))
                continue
            for block in record.get('blocks') or []:
                out.append((entry, page, record, block))
    return out


def build_event(root, event, figures_dir, crop=True, shared=()):
    """Комплект → (задания по порядку, отчёт комплекта)."""
    event_id = event['event_id']
    tasks = OrderedDict()
    report = Counter()
    missing_pages = []
    event['preamble'] = []

    def task_for(number, variant='', create=True):
        key = (number, variant)
        if key not in tasks and create:
            tasks[key] = Task(event_id, number, variant)
        return tasks.get(key)

    # 1. Условия (и всё, что лежит в файлах условий / смешанных).
    current = None
    current_file = None
    for entry, page, record, block in collect(root, event.get('task_files') or [], 'tasks'):
        if entry['file'] != current_file:
            # Продолжение и вступление не переходят через границу файла:
            # у МОШ задачи и тест — два файла одного комплекта.
            current, current_file = None, entry['file']
            file_keys, last_int, restarted = [], 0, False
        if record is None:
            missing_pages.append(f'{entry["page_dir"]}/p{page}')
            continue
        block = _test_number(block, entry['file'])
        kind = block['type']
        number = _block_number(block)
        if kind == 'task' and not _real_number(number):
            # Блок «задание» без номера (или «0», «intro», буква подпункта):
            # до первого задания — вступление комплекта («Время выполнения —
            # 90 минут…»), после — кусок текущего задания («(б) …»), который
            # модель пометила заданием. Пилот ВП: 23 лишних «задания» v2.
            if current is None:
                event['preamble'].append(block.get('text') or block.get('title') or '')
                report['вступление комплекта'] += 1
            else:
                current.statement.append(block.get('text') or '')
                current.pages.append((entry['file'], page))
                current.quality.append(record)
                report['безномерной кусок → к заданию'] += 1
            continue
        if kind == 'task':
            head = _leading_int(number)
            if (head is not None and head < last_int and not restarted
                    and len(file_keys) >= TEST_MIN_ITEMS
                    and not number.startswith('тест-')):
                # Нумерация в файле пошла заново: до этого был тест, теперь
                # задачи (МОШ 2011: вопросы 1–15, затем задачи 6–10). Уже
                # собранная часть файла — тест, номера «тест-N» (как в v1);
                # иначе вопрос 10 и задача 10 слились бы в одно задание.
                restarted = True
                for key in file_keys:
                    task = tasks.pop(key)
                    task.number = f'тест-{task.number}'
                    tasks[(task.number, task.task_variant)] = task
                report['нумерация пошла заново: часть файла — тест'] += 1
            if head is not None:
                last_int = head
            current = task_for(number, block.get('task_variant') or '')
            if not restarted and current.key not in file_keys:
                file_keys.append(current.key)
            current.title = current.title or (block.get('title') or '').strip()
            if block.get('points') not in (None, ''):
                current.points = block.get('points')
            current.statement.append(block.get('text') or '')
            current.pages.append((entry['file'], page))
            current.quality.append(record)
        elif kind == 'task_continuation':
            target = tasks.get((number, block.get('task_variant') or '')) if number else current
            if target is None:
                target = current
            if target is None:
                report['продолжение без задания'] += 1
                continue
            target.statement.append(block.get('text') or '')
            target.pages.append((entry['file'], page))
            target.quality.append(record)
            report['склеено продолжений'] += 1
        elif kind == 'figure':
            target = (tasks.get((number, '')) if number else None) or current
            if target is None:
                report['рисунок без задания'] += 1
                continue
            target.figures.append((entry['page_dir'], page, block.get('bbox'),
                                   block.get('caption') or ''))
            target.own_figures = True
        elif kind in ('solution', 'criteria'):
            if (kind == 'solution' and _real_number(number) and _find_task(
                    tasks, number, block.get('title') or '',
                    block.get('task_variant') or '') is None):
                # Задание целиком (условие + решение) модель положила одним
                # блоком «решение» (ВП 2012, 10 кл., №4): заводим задание с
                # пустым условием — оно уйдёт «на глаза», а не потеряется.
                current = task_for(number, block.get('task_variant') or '')
                current.title = (block.get('title') or '').strip()
                current.quality.append(record)
                report['задание только блоком решения'] += 1
            _attach_answer(tasks, current, block, kind, entry, page, report)

    # 2. Решения и 3. критерии из своих файлов.
    grades = parse_grades(event.get('grade') or '')
    no_task_files = not (event.get('task_files') or []) and not tasks
    # Смешанный файл стоит и в task_files, и в solution_files: его решения
    # уже легли при проходе условий — второй раз их не берём.
    seen_dirs = {entry.get('page_dir') for entry in event.get('task_files') or []} - {None}
    for role, files in (('solution', [f for f in event.get('solution_files') or []
                                      if f['page_dir'] not in seen_dirs]),
                        ('criteria', [f for f in event.get('criteria_files') or []
                                      if f['page_dir'] not in seen_dirs])):
        last = None
        in_statement = False      # сразу после повторённого условия
        for entry, page, record, block in collect(root, files, role):
            if record is None:
                missing_pages.append(f'{entry["page_dir"]}/p{page}')
                continue
            if entry['page_dir'] in shared:
                block = _own_grade_number(block, grades)
            if block is None:
                report['номер другого класса общего файла — мимо'] += 1
                continue
            kind = block['type']
            if (kind in ('solution', 'criteria') and no_task_files
                    and _real_number(_block_number(block))
                    and _find_task(tasks, _block_number(block), '', '') is None):
                # Условий у комплекта нет вовсе (финал МОШ 2017/18, 8, 9, 11
                # кл.): решение с номером заводит задание с пустым условием.
                created = task_for(_block_number(block), block.get('task_variant') or '')
                created.title = (block.get('title') or '').strip()
                created.quality.append(record)
                report['задание только из решений (условий нет)'] += 1
            if kind in ('footer', 'noise', 'header'):
                continue
            if kind == 'figure':
                # Рисунок сразу за условием, повторённым в файле решений
                # (у ВП условия часто только там), — рисунок условия, если
                # своих у задания нет; внутри решения — рисунок решения.
                target = last or (list(tasks.values())[-1] if tasks else None)
                if target is None:
                    report['рисунок без задания'] += 1
                    continue
                figure = (entry['page_dir'], page, block.get('bbox'), block.get('caption') or '')
                if in_statement and not target.own_figures:
                    target.figures.append(figure)
                else:
                    target.solution_figures.append(figure)
                continue
            in_statement = kind == 'task'
            if kind == 'task':
                # Условие, повторённое в файле решений: запоминаем как
                # последнее задание; если условия нет нигде — берём его.
                number = _block_number(block)
                target = _find_task(tasks, number, block.get('title') or '',
                                    block.get('task_variant') or '')
                if target is None and not _real_number(number):
                    # Подпункт, повторённый в файле решений («г», «(а)»): к
                    # последнему заданию, нового не заводим.
                    last = last or (list(tasks.values())[-1] if tasks else None)
                    report['безномерной кусок решения → к заданию'] += 1
                    continue
                if target is None:
                    target = task_for(number, block.get('task_variant') or '')
                    target.from_solution_only = True
                    target.title = (block.get('title') or '').strip()
                    report['условие только из файла решений'] += 1
                if not target.statement and target.from_solution_only:
                    target.statement.append(block.get('text') or '')
                    target.pages.append((entry['file'], page))
                    target.quality.append(record)
                if block.get('answer'):
                    # Тест с отмеченным ответом (сканы отборочных МОШ): файл
                    # ответов повторяет вопрос, ответ — в поле answer.
                    target.answer = (target.answer + '\n' + block['answer']).strip()
                    target.solution_pages.append((entry['file'], page))
                    report['ответ теста из файла ответов'] += 1
                last = target
                continue
            if kind == 'task_continuation' and last is not None and \
                    last.from_solution_only and not (last.solution or last.criteria):
                last.statement.append(block.get('text') or '')
                continue
            last = _attach_answer(tasks, last, block, role if kind == 'task_continuation'
                                  else kind, entry, page, report) or last

    # Рисунки: вырезка.
    for task in tasks.values():
        # Номер-заглушка и прочие знаки, которых Windows не терпит в имени
        # файла, → «_».
        safe = re.sub(r'[^\w.-]', '_', f'{task.number}{task.task_variant and "v" + task.task_variant}')
        for attr, out, suffix in (('figures', 'figure_files', ''),
                                  ('solution_figures', 'solution_figure_files', 's')):
            files = []
            for k, (page_dir, page, bbox, caption) in enumerate(getattr(task, attr), 1):
                path = os.path.join(figures_dir, f'{event_id}_{safe}_{suffix}{k}.png')
                flag = crop_figure(os.path.join(root, page_dir, f'p{page}.png'), bbox, path) \
                    if crop else 'не вырезано'
                files.append({'path': os.path.relpath(path, root).replace('\\', '/'),
                              'caption': caption, 'flag': flag, 'page': page})
                report[f'рисунок: {flag or "вырезан"}'] += 1
            setattr(task, out, files)
        # Рамка рисунка условия не удалась (пустая вырезка / нет рамки), а в
        # файле решений тот же рисунок (подпись ≥ 0,85) вырезан чисто — берём
        # его (ВП 2020, «ТратьБанк»: рамки в файле условий мимо, в решениях
        # точные).
        for i, fig in enumerate(task.figure_files):
            if not fig['flag']:
                continue
            for alt in task.solution_figure_files:
                if not alt['flag'] and fig['caption'] and fuzz.ratio(
                        fig['caption'].lower(), alt['caption'].lower()) / 100 >= TITLE_MATCH:
                    task.figure_files[i] = dict(alt, replaced=fig['flag'])
                    report['рисунок условия взят из решений'] += 1
                    break
    report['страниц без расшифровки'] = len(missing_pages)
    return list(tasks.values()), report, missing_pages


_GRADE_NUMBER = re.compile(r'(\d{1,2})\.(\d+)')


def _own_grade_number(block, grades):
    """Общий файл решений на несколько классов нумерует «класс.задача»
    («5.1» — 5 класс, задача 1; МОШ 2019/20, 5–7 кл.). Номер своего класса
    → номер задачи; чужого класса → None (решение другого комплекта).
    Номер вида N.M без класса впереди (у МОШ «1.2» — задание 1, пункт 2)
    не трогается: первое число должно быть классом 5–11 и совпасть с
    классом комплекта или с другим классом из того же диапазона."""
    number = _block_number(block)
    match = _GRADE_NUMBER.fullmatch(number or '')
    if not match or not grades:
        return block
    grade = int(match.group(1))
    if grade in grades and len(grades) == 1:
        return dict(block, number=match.group(2))
    if 5 <= grade <= 11 and grade not in grades and min(grades) >= 5:
        return None
    return block


_TEST_FILE = re.compile(r'(^|[-_/])test[-_]', re.IGNORECASE)


def _test_number(block, filename):
    """Файл теста МОШ («tasks-econ-10-test-final-…») нумерует вопросы с 1,
    как и файл задач того же комплекта: номер вопроса → «тест-N» (как в
    v1), иначе вопрос 1 сольётся с задачей 1 (МОШ 2013, финал 10 кл.)."""
    number = _block_number(block)
    if not _TEST_FILE.search(filename.rsplit('__', 1)[-1]) or not _real_number(number):
        return block
    return dict(block, number=f'тест-{number}')


#: Перезапуск нумерации считается границей «тест → задачи», только если до
#: него в файле не меньше стольких вопросов: у ВП файл повторяет задачи 1–5
#: перед решениями (тоже «перезапуск»), а тест МОШ — это 15–40 вопросов.
TEST_MIN_ITEMS = 8


def _leading_int(number):
    match = re.match(r'\d+', number or '')
    return int(match.group()) if match else None


def _real_number(number):
    """Номер задания — с цифрой и не «0» (вступление/подпункт — нет)."""
    return bool(number) and any(ch.isdigit() for ch in number) and number != '0'


def _find_task(tasks, number, title, variant=''):
    if number and (number, variant) in tasks:
        return tasks[(number, variant)]
    if number and (number, '') in tasks:
        return tasks[(number, '')]
    if number and '.' in number:
        # «1.1» без своего задания — подпункт задания 1 (у ВП); у МОШ, где
        # «1.1» — самостоятельное задание, оно найдётся точным ключом выше.
        parent = number.split('.')[0]
        found = tasks.get((parent, variant)) or tasks.get((parent, ''))
        if found is not None:
            return found
    title = (title or '').strip().lower()
    if not title:
        return None
    best, score = None, 0.0
    for task in tasks.values():
        if task.title:
            value = fuzz.ratio(title, task.title.strip().lower()) / 100.0
            if value > score:
                best, score = task, value
    return best if score >= TITLE_MATCH else None


def _attach_answer(tasks, last, block, kind, entry, page, report):
    """Решение/критерии → задание по номеру, иначе по названию, иначе —
    продолжение предыдущего решения (блок без номера сразу за ним)."""
    number = _block_number(block)
    target = _find_task(tasks, number, block.get('title') or '', block.get('task_variant') or '')
    how = 'по номеру' if target is not None and number else 'по названию'
    if target is None and not _real_number(number) and last is not None:
        target, how = last, 'продолжение'
    if target is None:
        report[f'{kind}: не сопоставлено'] += 1
        report.setdefault('_unmatched', [])
        report['_unmatched'].append(f'{entry["file"]}#p{page} №{number or "—"} '
                                    f'«{(block.get("title") or "")[:40]}»')
        return None
    text = block.get('text') or ''
    if kind == 'criteria':
        target.criteria.append(text)
        target.criteria_pages.append((entry['file'], page))
        if block.get('points') not in (None, ''):
            target.criteria_points = block.get('points')
    else:
        target.solution.append(text)
        target.solution_pages.append((entry['file'], page))
        if block.get('answer'):
            target.answer = (target.answer + '\n' + block['answer']).strip()
    report[f'{kind}: сопоставлено {how}'] += 1
    return target


def crop_figure(png_path, bbox, out_path):
    """Вырезать рамку (доли 0..1000) с запасом 2 %, обрезать по краям.
    Возвращает '' (вырезано) или флаг: 'нет рамки', 'нет картинки',
    'пустая вырезка'."""
    from PIL import Image, ImageStat
    if not bbox or len(bbox) != 4:
        return 'нет рамки'
    if not os.path.isfile(png_path):
        return 'нет картинки'
    try:
        x0, y0, x1, y1 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return 'нет рамки'
    if x1 <= x0 or y1 <= y0:
        return 'нет рамки'
    with Image.open(png_path) as image:
        width, height = image.size
        pad_x, pad_y = FIGURE_PAD * width, FIGURE_PAD * height
        box = (max(0, int(x0 / 1000 * width - pad_x)), max(0, int(y0 / 1000 * height - pad_y)),
               min(width, int(x1 / 1000 * width + pad_x)),
               min(height, int(y1 / 1000 * height + pad_y)))
        if box[2] - box[0] < 10 or box[3] - box[1] < 10:
            return 'нет рамки'
        piece = image.crop(box)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        piece.save(out_path)
        stddev = ImageStat.Stat(piece.convert('L')).stddev[0]
    return 'пустая вырезка' if stddev < EMPTY_STDDEV else ''


def split_parts(statement):
    """Подпункты условия: строки «а) …», «1) …» → [{label, text}]."""
    parts = []
    for line in statement.splitlines():
        match = _LIST_ITEM.match(line)
        if match:
            parts.append({'label': match.group(1).strip('()').rstrip('.)'),
                          'text': match.group(2).strip()})
        elif parts and line.strip() and line.startswith((' ', '\t')):
            parts[-1]['text'] += ' ' + line.strip()
    return parts


def count_tables(markdown):
    """Число Markdown-таблиц: строка-разделитель `|---|`."""
    return len(re.findall(r'(?m)^\s*\|?\s*:?-{3,}', markdown or ''))


def task_record(task, event, model):
    statement = join_pieces(task.statement)
    solution = '\n\n'.join(t.strip() for t in task.solution if t.strip())
    criteria = '\n\n'.join(t.strip() for t in task.criteria if t.strip())
    pages = task.quality
    ratios = [p.get('layer_ratio') for p in pages if p.get('layer_ratio') is not None]
    numbers = [p.get('numbers_ok') for p in pages if p.get('numbers_ok') is not None]
    max_score = task.points if task.points not in (None, '') else task.criteria_points
    return {
        'event_id': task.event_id, 'number': task.number,
        'task_variant': task.task_variant, 'title': task.title,
        'year': event.get('year'), 'academic_year': event.get('academic_year'),
        'stage': event.get('stage'), 'grade': event.get('grade'),
        'statement_md': statement, 'parts': split_parts(statement),
        'tables': count_tables(statement), 'figures': task.figure_files,
        'solution_figures': task.solution_figure_files,
        'solution_md': solution, 'answer': task.answer, 'criteria_md': criteria,
        'max_score': max_score,
        'source_file': sorted({f for f, _p in task.pages}),
        'source_pages': [f'{f}#p{p}' for f, p in task.pages],
        'solution_pages': [f'{f}#p{p}' for f, p in task.solution_pages],
        'criteria_pages': [f'{f}#p{p}' for f, p in task.criteria_pages],
        'layer_ratio': min(ratios) if ratios else None,
        'numbers_ok': all(numbers) if numbers else None,
        'needs_eyes': any(p.get('needs_eyes') for p in pages) or not statement,
        'retries': sum(int(p.get('retries') or 0) for p in pages),
        'statement_from_solution_file': task.from_solution_only,
        'official': event.get('official', True), 'source': event.get('source', 'official'),
        'digitized_by': {'model': model, 'date': date.today().isoformat()},
    }


def join_pieces(pieces):
    """Куски условия по порядку страниц. Кусок со строчной буквы —
    продолжение предложения, разорванного границей страницы («…и ценой, |
    назначенной…»): клеится пробелом, остальные — абзацем."""
    out = ''
    for piece in (p.strip() for p in pieces):
        if not piece:
            continue
        if out and piece[0].islower():
            out += ' ' + piece
        else:
            out += ('\n\n' if out else '') + piece
    return out


def docx_records(event, v1_rows):
    """Задания комплекта, чьи условия лежат только в docx: текст v1."""
    out = []
    for row in v1_rows:
        out.append({
            'event_id': event['event_id'], 'number': str(row['number']),
            'task_variant': row.get('task_variant') or '', 'title': row.get('title') or '',
            'year': event.get('year'), 'academic_year': event.get('academic_year'),
            'stage': event.get('stage'), 'grade': event.get('grade'),
            'statement_md': row.get('raw_text') or '', 'parts': [], 'tables': 0,
            'figures': [], 'solution_figures': [], 'solution_md': '', 'answer': '',
            'criteria_md': '', 'max_score': row.get('max_score'),
            'source_file': [f['file'] for f in event['task_files']], 'source_pages': [],
            'solution_pages': [], 'criteria_pages': [], 'layer_ratio': None,
            'numbers_ok': None, 'needs_eyes': False, 'retries': 0,
            'statement_from_solution_file': False, 'source_text': 'docx',
            'official': event.get('official', True), 'source': event.get('source', 'official'),
            'digitized_by': {'model': 'docx-text (v1)', 'date': date.today().isoformat()},
        })
    return out


def completeness(records):
    if not records or not any(r['statement_md'] for r in records):
        return 'index_only'
    if all(r['statement_md'] and (r['solution_md'] or r['criteria_md'] or r['answer'])
           for r in records):
        return 'full'
    return 'partial'


def assemble(digitized, reference_events, v1_rows, model, only_events=None, crop=True):
    """Собрать всё. Возвращает сводку; файлы пишет в `digitized`."""
    events_files = {e['event_id']: e for e in _read_jsonl(
        os.path.join(digitized, 'events_files.jsonl'))}
    meta = {e['event_id']: e for e in reference_events}
    figures_dir = os.path.join(digitized, 'figures')
    v1_counts = Counter(r['event_id'] for r in v1_rows)
    # Файлы решений, общие для нескольких комплектов (один PDF на 5–7 кл.).
    usage = Counter(f.get('page_dir') for e in events_files.values()
                    for key in ('solution_files', 'criteria_files') for f in e.get(key) or [])
    shared = {page_dir for page_dir, n in usage.items() if page_dir and n > 1}
    v1_by_event = defaultdict(list)
    for row in v1_rows:
        v1_by_event[row['event_id']].append(row)
    out_rows, out_events, compare = [], [], []
    summary = Counter()
    unmatched = []
    for event_id in sorted(set(events_files) | set(meta)):
        if only_events and event_id not in only_events:
            continue
        # Файлы комплекта — только из описи digitized (в reference_events у
        # файлов нет папок страниц); комплект без файлов — пустой.
        files = events_files.get(event_id, {})
        event = {**meta.get(event_id, {}), **files}
        for key in ('task_files', 'solution_files', 'criteria_files'):
            event[key] = files.get(key) or []
        event['event_id'] = event_id
        tasks, report, missing = build_event(digitized, event, figures_dir, crop=crop,
                                             shared=shared)
        records = [task_record(t, event, model) for t in tasks]
        if not records and any(f.get('docx_md') for f in event['task_files']):
            # Условия только в docx (дистанционный тур МОШ 2017/18): текст
            # извлечён напрямую, модель не вызывалась — задания берутся из
            # v1 этого комплекта (там тоже текст docx, а не PDF).
            records = docx_records(event, v1_by_event.get(event_id, []))
            summary['заданий из docx (v1)'] += len(records)
        out_rows.extend(records)
        unmatched.extend(report.pop('_unmatched', []))
        summary.update({k: v for k, v in report.items() if isinstance(v, int)})
        status = completeness(records)
        out_events.append({
            'event_id': event_id, 'year': event.get('year'), 'stage': event.get('stage'),
            'grade': event.get('grade'), 'variant': event.get('variant'),
            'official': event.get('official', True), 'source': event.get('source', 'official'),
            'completeness': status, 'problem_count': len(records),
            'problem_count_v1': v1_counts.get(event_id, 0),
            'with_solution': sum(bool(r['solution_md']) for r in records),
            'with_criteria': sum(bool(r['criteria_md']) for r in records),
            'needs_eyes': sum(r['needs_eyes'] for r in records),
            'pages_missing': len(missing), 'new': bool(event.get('new')),
            'preamble_md': '\n\n'.join(p for p in event.get('preamble') or [] if p),
        })
        summary[f'комплектов {status}'] += 1
        if len(records) != v1_counts.get(event_id, 0):
            compare.append({'event_id': event_id, 'v1': v1_counts.get(event_id, 0),
                            'v2': len(records),
                            'v2_numbers': ' '.join(r['number'] for r in records)})
    with open(os.path.join(digitized, 'reference_problems_v2.jsonl'), 'w',
              encoding='utf-8') as handle:
        for row in out_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    with open(os.path.join(digitized, 'events_v2.jsonl'), 'w', encoding='utf-8') as handle:
        for row in out_events:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    with open(os.path.join(digitized, 'compare_v1_v2.csv'), 'w', encoding='utf-8-sig',
              newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['event_id', 'v1', 'v2', 'v2_numbers'])
        writer.writeheader()
        writer.writerows(compare)
    with open(os.path.join(digitized, 'unmatched_solutions.txt'), 'w',
              encoding='utf-8') as handle:
        handle.write('\n'.join(unmatched) + '\n')
    summary['заданий v2'] = len(out_rows)
    summary['заданий v1'] = sum(v1_counts.values())
    summary['комплектов'] = len(out_events)
    summary['комплектов с другим числом заданий'] = len(compare)
    summary['решений не сопоставлено'] = len(unmatched)
    return summary


def problem_count_by(records, key):
    counts = defaultdict(int)
    for record in records:
        counts[record.get(key)] += 1
    return dict(counts)
