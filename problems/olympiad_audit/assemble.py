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

from problems.olympiad_audit import econ_rules
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


def load_page(root, page_dir, page, overlay=None):
    """Запись страницы v2; `overlay` (triage.PageOverlay) накладывает на неё
    заплатки разбора очереди «на глаза» (pages_v3). Файл v2 не меняется."""
    path = os.path.join(root, page_dir, f'p{page}.json')
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as handle:
        record = json.load(handle)
    return overlay.apply(page_dir, page, record) if overlay else record


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
        self.leads = []             # v5: инструкции раздела в начало условия
        self.subitems = 0           # v5: пункты «N)», дописанные к задаче
        self.absorbed = 0           # v5: из них размеченных моделью как задание

    @property
    def key(self):
        return (self.number, self.task_variant)


#: Служебные строки страницы, которые модель изредка размечает безномерным
#: заданием: «Комплект заданий № 1» (шапка каждой страницы теста), «Код
#: участника», «Бланк ответов». Блок служебный, если ВСЕ его строки такие.
_SERVICE_LINE = re.compile(
    r'^(комплект\s+заданий\s*№?\s*\d*|код\s+участника|бланк\s+ответов|'
    r'таблица\s+заполняется\s+жюри.*)$', re.IGNORECASE)
#: Вступление (части) комплекта: время, максимальный балл, правила.
_INTRO = re.compile(r'(общее\s+время|время\s+выполнени|максимальн\w*\s+(количество\s+)?балл|'
                    r'количество\s+баллов\s+за|критерии\s+оценивания\s*\(всего)',
                    re.IGNORECASE)
INTRO_SAME = 0.85


def _plain_lines(text):
    for line in str(text or '').splitlines():
        line = re.sub(r'[*#_`>|]+', ' ', line)
        line = ' '.join(re.sub(r'[.:;!\s]+$', '', line.strip()).split())
        if line:
            yield line


def is_service_text(text):
    lines = list(_plain_lines(text))
    return bool(lines) and all(_SERVICE_LINE.match(line) for line in lines)


def is_intro_text(text):
    return bool(_INTRO.search(str(text or '')[:400]))


def same_intro(text, seen):
    """Тот же текст вступления (повтор на следующей странице)."""
    a, b = ' '.join(_plain_lines(text)).lower(), ' '.join(_plain_lines(seen)).lower()
    return bool(a and b) and fuzz.ratio(a, b) / 100 >= INTRO_SAME


#: Повтор условия в файле решений: кусок входит в условие (partial_ratio).
ECHO_TAIL = 0.90
ECHO_PARAGRAPH = 0.95
_TASK_HEADING = re.compile(r'^\W*(\d+[.)]\s*)?(задача|задание|вопрос|ситуация)\s*№?\s*\d+(\.\d+)?\W*$',
                           re.IGNORECASE)


def _plain(text):
    return ' '.join(_plain_lines(text)).lower()


def is_statement_echo(text, statement):
    """Кусок — повтор текста условия (хвост условия на новой странице файла
    решений): от 20 знаков и входит в условие."""
    a, b = _plain(text), _plain(statement)
    return len(a) >= 20 and bool(b) and fuzz.partial_ratio(a, b) / 100 >= ECHO_TAIL


def strip_statement_echo(text, statement):
    """Срезать в начале решения абзацы, повторяющие условие, и заголовок
    «Задача N». Последний абзац не срезается никогда: решение не пустеет."""
    paras = [p for p in re.split(r'\n\s*\n', text or '') if p.strip()]
    plain_statement = _plain(statement)
    i = 0
    while i < len(paras) - 1:
        para = _plain(paras[i])
        if _TASK_HEADING.match(para) or (
                len(para) >= 20 and plain_statement
                and fuzz.partial_ratio(para, plain_statement) / 100 >= ECHO_PARAGRAPH):
            i += 1
            continue
        break
    return '\n\n'.join(paras[i:]) if i else text


#: Сопоставление по тексту условия: начало условия (до 200 знаков) входит в
#: блок файла решений (partial_ratio) не ниже TEXT_MATCH, и второй кандидат
#: заметно хуже (TEXT_MARGIN) — иначе неоднозначно, остаётся номер.
TEXT_MATCH = 0.90
TEXT_MARGIN = 0.05
#: Задание по номеру «не то», если его условие входит в блок слабее этого.
TEXT_OTHER = 0.60
TEXT_MIN = 40


#: Условие сравнивается целиком (до стольких знаков): у МОШ-финграма 2021/22
#: «Задания 19-20» начинаются тем же сюжетом, что задание 17, — по началу
#: условия они слились бы.
TEXT_SPAN = 600
#: Блок должен вмещать условие почти целиком: обрывок условия — не повтор.
TEXT_COVER = 0.8


def text_score(task, text):
    statement = _plain(join_pieces(task.statement))[:TEXT_SPAN]
    plain = _plain(text)
    if len(statement) < TEXT_MIN or len(plain) < max(TEXT_MIN, TEXT_COVER * len(statement)):
        return 0.0
    return fuzz.partial_ratio(statement, plain) / 100


def compatible_number(task_number, number):
    """Номер блока файла решений совместим с заданием: тот же, «тест-N»,
    «тест-k.N», «4.N». Блок без номера совместим с любым."""
    if not _real_number(number):
        return True
    return (task_number == number or task_number.endswith('-' + number)
            or task_number.endswith('.' + number))


def is_date_number(block):
    """Номер блока «ДД.ММ», а текст начинается с «ДД.ММ.ГГГГ» — это дата."""
    number = str(block.get('number') or '').strip()
    text = block.get('text') or ''
    if re.fullmatch(r'\d{1,2}\.\d{2}\.(?:19|20)\d\d', number):
        return bool(re.match(r'^\W*' + re.escape(number), text))      # «20.11.2013»
    if not re.fullmatch(r'\d{1,2}\.\d{2}', number):
        return False
    return bool(re.match(r'^\W*' + re.escape(number) + r'\.(?:19|20)\d\d', text))


def compatible_target(tasks, number, variant, last=None, profile=None):
    """Задание для номера N из файла решений, когда своего N нет: единственный
    совместимый кандидат (`тест-N`, `тест-k.N`, `4.N`); из нескольких — с тем
    же префиксом, что у последнего сопоставленного задания этого файла
    (МОШ-предпринимательство 2013/14, 10-11: критерии «6» за подпунктом кейса
    «4.5» — это «4.6», а не «тест-6»). Иначе None.

    В профиле ECON — всегда None: у МОШ 2010/11, 9 кл., задачи 6–10 есть только
    в файле решений, и номер «6» ушёл бы к вопросу «тест-6» (v5, 14.10.2026)."""
    if not _real_number(number) or profile == ECON:
        return None
    cands = [t for t in tasks.values() if t.number != number
             and compatible_number(t.number, number) and t.task_variant in (variant, '')]
    head = _leading_int(number)
    if last is not None and head is not None:
        prefix, tail = _tail(last.number)
        seq = [t for t in cands if prefix is not None and _tail(t.number)[0] == prefix
               and _tail(t.number)[1] == head and tail == head - 1]
        if len(seq) == 1:
            return seq[0]               # продолжение последовательности: 4.5 → «6» = 4.6
    tests = [t for t in cands if t.number.startswith('тест-')]
    return tests[0] if len(tests) == 1 else None


def match_by_text(tasks, text, number=''):
    """Задание с совместимым номером, чьё условие однозначно повторено в блоке,
    или None. Номер ограничивает выбор: МОШ-финграм 2024/25, отбор 5-6 —
    задание 4, склеенное моделью в условии 3, иначе «нашлось» бы внутри 3."""
    if len(_plain(text)) < TEXT_MIN:
        return None
    scored = sorted(((text_score(task, text), i, task) for i, task in enumerate(tasks.values())
                     if compatible_number(task.number, number)),
                    key=lambda x: (-x[0], x[1]))
    if not scored or scored[0][0] < TEXT_MATCH:
        return None
    if len(scored) > 1 and scored[1][0] > scored[0][0] - TEXT_MARGIN:
        return None
    return scored[0][2]


_ITEM_LINES = (re.compile(r'^\W*(\d{1,2})\.\s+\S'), re.compile(r'^\W*(\d{1,2})\)\s+\S'))


def _tail(number):
    """«тест-1.7» → («тест-1.», 7); «12» → («», 12); иначе (None, None)."""
    match = re.match(r'^(.*?)(\d+)$', number or '')
    return (match.group(1), int(match.group(2))) if match else (None, None)


def split_glued(tasks, report):
    """Склейка заданий (МОШ-предпринимательство 2009/10: вопросы теста 1–8
    одним блоком «1»): если следующий номер того же варианта и вида прыгает
    (1 → 9), а в условии построчно стоят пункты «2.», «3.» … «8.» — это
    слипшиеся задания, режутся по этим строкам. Без пропуска номеров
    нумерованный список — подпункты задания, не трогается."""
    order = list(tasks.values())
    out = OrderedDict()
    for i, task in enumerate(order):
        out[task.key] = task
        prefix, own = _tail(task.number)
        if own is None:
            continue
        # Следующий номер — по ВСЕМ заданиям комплекта того же вида и варианта,
        # а не по порядку создания: задание из файла решений заводится в конце
        # (ВП-финграм 2024/25, 11 кл.: задание 3 — после 5), и «пропуск 2 → 4»
        # отрезал бы у задания 2 его подпункт «3.».
        later = [_tail(t.number)[1] for t in order
                 if t.task_variant == task.task_variant and _tail(t.number)[0] == prefix
                 and (_tail(t.number)[1] or 0) > own]
        if not later or min(later) - own < 2:
            continue
        want = list(range(own + 1, min(later)))
        if any((f'{prefix}{n}', task.task_variant) in tasks for n in want):
            continue                      # такой номер уже есть — не резать поверх
        lines = join_pieces(task.statement).split('\n')
        # Сначала «2.», потом «2)»: у теста вопросы «2.», а варианты ответа «2)».
        for item in _ITEM_LINES:
            cuts, k = [], 0
            for j, line in enumerate(lines):
                match = item.match(line)
                if match and k < len(want) and int(match.group(1)) == want[k]:
                    cuts.append(j)
                    k += 1
            if k == len(want):
                break
        if k != len(want) or not cuts:
            continue
        task.statement = ['\n'.join(lines[:cuts[0]]).strip()]
        for n, (a, b) in zip(want, zip(cuts, cuts[1:] + [len(lines)])):
            new = Task(task.event_id, f'{prefix}{n}', task.task_variant)
            new.statement = ['\n'.join(lines[a:b]).strip()]
            new.pages, new.quality = list(task.pages), list(task.quality)
            out[new.key] = new
            report['склейка заданий разрезана по пропуску номеров'] += 1
    tasks.clear()
    tasks.update(out)


def _block_number(block):
    return norm_number(block.get('number')) if block.get('number') not in (None, '') else ''


#: Профиль сборки экономики ВП/МОШ (сессия v5, 14.10.2026). Правила, добавленные
#: после сборки v3 (09.10) для финграмотности и предпринимательства, на экономике
#: меняли ключи и текст: тем же кодом на тех же заплатках v3 — ключи 38
#: комплектов МОШ и 8 ВП (mosh-2010-final-11: 50 → 31 задание), а задачи 6–10
#: МОШ 2010/11, 9 кл. (условия только в файле решений) уходили к вопросам
#: «тест-6…10». В профиле ECON сборка идёт по правилам v3 (код 3bd9c593 на
#: заплатках pages_v3 даёт v3 ровно), поверх — только правила v5 (блоки отборочных
#: МОШ, служебные блоки, пункты задачи). Выключено: вариант из шапки файла,
#: несколько тестов подряд, сброс нумерации → подпункты, резка склейки, дата-номер,
#: служебная строка/повтор вступления, таблица критериев по строкам, бланк
#: ответов, сопоставление по тексту и по совместимому номеру, срез повтора
#: условия в решении, «номер вне заданий → продолжение».
ECON = 'econ'
ECON_SLUGS = ('vp', 'mosh')


def profile_for(slug):
    return ECON if slug in ECON_SLUGS else None


def collect(root, files, role, overlay=None, profile=None):
    """Блоки файлов комплекта по порядку страниц: [(файл, страница,
    запись страницы, блок)]. role — tasks/solutions/criteria."""
    out = []
    for entry in files:
        if not entry.get('page_dir'):
            continue      # docx: текст напрямую, страниц нет (см. docx_records)
        for page in range(1, int(entry.get('pages') or 0) + 1):
            record = load_page(root, entry['page_dir'], page, overlay)
            if record is None:
                out.append((entry, page, None, None))
                continue
            for block in record.get('blocks') or []:
                out.append((entry, page, record, block))
    if profile == ECON:
        return econ_rules.qualifying_blocks(out)
    return _header_variants(out)


def _variant_of_header(block):
    """Номер варианта из шапки: «2», «2 Вариант», «Вариант 1». «Комплект
    заданий № 2 (основы потребительских знаний)» — часть комплекта, а
    «Решебник, 16 марта 2014 г.» — дата (МОШ-предпринимательство): не варианты."""
    text = str(block.get('variant') or '')
    if not (re.fullmatch(r'\s*\d+\s*', text) or 'вариант' in text.lower()):
        return ''
    match = re.search(r'\d+', text)
    return match.group() if match else ''


_MARKED = re.compile(r'\(отмечено\)')
#: Ответ теста в таблице «номер | ответ»: буквы вариантов или да/нет/верно/неверно.
_CHOICE = re.compile(r'^(?:[А-ЕA-Eа-еa-e](?:\s*[,;/]\s*[А-ЕA-Eа-еa-e])*|да|нет|верно|неверно)$',
                     re.IGNORECASE)
_PLUS = re.compile(r'^[+xх×✓]$', re.IGNORECASE)


def _tables(text):
    """Markdown-таблицы текста: [[строка ячеек, …], …] без строк-разделителей."""
    tables, rows = [], []
    for line in (text or '').splitlines():
        if line.strip().startswith('|'):
            if not re.fullmatch(r'\s*\|?[\s:|-]+\|?\s*', line):
                rows.append(_cells(line))
            continue
        if rows:
            tables.append(rows)
            rows = []
    if rows:
        tables.append(rows)
    return tables


_KEY_LINE = re.compile(r'^\W*(\d{1,2})\s*[.)]\s+(.{1,25})$')
_KEY_PAIR = re.compile(r'(\d{1,2})\s*[—–-]\s*([^;]{1,25})')


def parse_answer_list(text, answer=''):
    """Ключ ответов без таблицы (МОШ-финграм 2019/20): строки «1. Нет, не
    является / 2. В / 3. А, Б» (≥ 3 подряд с 1, ответ до 25 знаков) или поле
    answer «1 — А, Б, В; 2 — Г; …». {номер: ответ} или {}."""
    out = {}
    for line in _plain_lines(text):
        match = _KEY_LINE.match(line)
        if match:
            out[match.group(1)] = match.group(2).strip(' *')
    if len(out) < 3 or [int(n) for n in out] != list(range(1, len(out) + 1)):
        out = {}
    if not out and answer:
        pairs = _KEY_PAIR.findall(answer)
        if len(pairs) >= 3 and [int(n) for n, _a in pairs] == list(range(1, len(pairs) + 1)):
            out = {n: a.strip(' .') for n, a in pairs}
    return out


def parse_answer_grid(text):
    """Бланк ответов теста → {номер вопроса: ответ} (МОШ-предпринимательство).

    Раскладки: а) шапка — номера вопросов, ниже строки вариантов, выбранный
    помечен «(отмечено)»; б) «№ | А | В | С …» (группы с «№»), в строке вопроса
    выбранная буква отмечена «+». Вопрос с нулём или несколькими отметками —
    без ответа. Таблица без отметок — не бланк ({})."""
    out = {}
    for rows in _tables(text):
        head = rows[0]
        if len(rows) >= 3 and all(c.isdigit() for c in head if c) and any(head):
            for j, number in enumerate(head):
                if not number:
                    continue
                marked = [row[j] for row in rows[1:] if j < len(row) and _MARKED.search(row[j])]
                if len(marked) == 1:
                    out[number] = _MARKED.sub('', marked[0]).strip(' *')
            continue
        pairs = [row for row in rows if len([c for c in row if c]) == 2]
        if (len(rows) >= 3 and len(pairs) == len(rows)
                and all(row[0].isdigit() and _CHOICE.match(row[1].strip(' *')) for row in rows)
                and [int(row[0]) for row in rows] == list(range(int(rows[0][0]),
                                                                int(rows[0][0]) + len(rows)))):
            # в) «1 | В / 2 | Б, В / 3 | А» — номер подряд и ответ (МОШ-финграм 2019/20).
            for row in rows:
                out[row[0]] = row[1].strip(' *')
            continue
        groups = [j for j, c in enumerate(head) if c in ('№', 'N')]
        for row in rows[1:] if groups else ():
            for k, start in enumerate(groups):
                end = groups[k + 1] if k + 1 < len(groups) else len(head)
                if start >= len(row) or not row[start].isdigit():
                    continue
                hits = [head[j] for j in range(start + 1, min(end, len(row)))
                        if _PLUS.match(row[j].strip())]
                if len(hits) == 1:
                    out[row[start]] = hits[0]
    return out


_VARIANT_MARK = re.compile(r'(?:^|\s)(\d)\s*вариант\b|\bвариант\s*№?\s*(\d)\b', re.IGNORECASE)


def _variant_marker(block):
    """Метка варианта текстом безномерного блока («**Правильные ответы** /
    **2 вариант**», МОШ-финграм 2019/20): короткий блок без номера — как шапка."""
    if block.get('type') not in ('task', 'solution', 'criteria') or \
            _real_number(_block_number(block)):
        return ''
    # Метка — отдельной короткой строкой в первых трёх строках блока
    # («КЛЮЧИ С ПРАВИЛЬНЫМИ ОТВЕТАМИ / Вариант 1 / …»).
    for line in list(_plain_lines(block.get('text') or ''))[:3]:
        match = _VARIANT_MARK.search(line) if len(line) <= 60 else None
        if match:
            return match.group(1) or match.group(2)
    return ''


def _header_variants(items):
    """Файл из нескольких вариантов подряд (МОШ, финграмотность, отборочный
    2017/18–2021/22: «вариант 1» на стр. 1–6, «вариант 2» на стр. 7–12, у
    каждого нумерация с 1): вариант переносится на блоки без своего
    `task_variant`, начало новой части помечается `_variant_switch` (сборка
    сбрасывает счётчик «нумерация пошла заново»). Части узнаются так:
      а) в шапках файла два и больше вариантов; шапка без номера и блоки до
         первой шапки — вариант 1, если номер 1 не занят другой шапкой;
      б) шапка с номером варианта одна, а нумерация заданий/ответов
         сбрасывается к 1 после ≥ 8 пунктов — следующий вариант (ответы
         «1 Вариант», затем снова 1, 2, … без шапки).
    Файл без номеров вариантов в шапках не меняется."""
    by_file = defaultdict(list)
    for i, (entry, _page, _record, block) in enumerate(items):
        if block is not None:
            by_file[entry['file']].append(i)
    items = list(items)
    for _name, idxs in by_file.items():
        headers = [(i, _variant_of_header(items[i][3]) or _variant_marker(items[i][3]))
                   for i in idxs if items[i][3].get('type') == 'header'
                   or _variant_marker(items[i][3])]
        digits = []
        for _i, v in headers:
            if v and v not in digits:
                digits.append(v)
        if not digits:
            continue
        before_first = any(items[i][3].get('type') in ('task', 'solution', 'criteria')
                           for i in idxs if i < headers[0][0])
        multi = (len(digits) >= 2 or any(not v for _i, v in headers)
                 or (digits[0] != '1' and before_first))
        # Блоки до первой шапки — вариант 1, если номер 1 не занят шапкой.
        current = '1' if multi and '1' not in digits else None
        if not multi:
            # б) одна шапка с номером: меняем файл, только если нумерация
            # действительно сбрасывается к 1 (вторая часть без шапки).
            last_int, seen, restarts = 0, 0, 0
            for i in idxs:
                block = items[i][3]
                if block.get('type') in ('task', 'solution', 'criteria'):
                    head = _leading_int(_block_number(block))
                    if head == 1 and seen >= TEST_MIN_ITEMS and last_int > 1:
                        restarts, seen = restarts + 1, 0
                    if head is not None:
                        last_int, seen = head, seen + 1
            if not restarts:
                continue
        last_int, seen = 0, 0
        for i in idxs:
            entry, page, record, block = items[i]
            kind = block.get('type')
            marker = _variant_marker(block)
            if kind == 'header' or marker:
                v = (_variant_of_header(block) or marker
                     or ('1' if multi and '1' not in digits else ''))
                if v:
                    block = dict(block, _variant_switch=current not in (None, v))
                    if marker and not block.get('task_variant'):
                        block['task_variant'] = v      # ключ ответов внутри блока-метки
                    current, last_int, seen = v, 0, 0
            elif kind in ('task', 'task_continuation', 'solution', 'criteria', 'figure'):
                head = _leading_int(_block_number(block)) if kind in ('task', 'solution',
                                                                      'criteria') else None
                if (not multi and head == 1 and seen >= TEST_MIN_ITEMS and last_int > 1
                        and current and current.isdigit()):
                    current = str(int(current) + 1)
                    block = dict(block, _variant_switch=True)
                    last_int, seen = 0, 0
                if head is not None:
                    last_int, seen = head, seen + 1
                if current and not block.get('task_variant'):
                    block = dict(block, task_variant=current)
            items[i] = (entry, page, record, block)
    return items
def _item_count(task):
    return max(econ_rules.items_in(join_pieces(task.statement)), task.subitems)


def _points(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_subitem(current, block, head, declared):
    """v5: блок «задание № N» — пункт N) текущей задачи: у задачи есть название,
    у блока нет, N продолжает её пункты, и либо баллы блока меньше баллов
    задачи, либо N больше заявленного во вступлении числа задач."""
    if head is None or not current.title or (block.get('title') or '').strip():
        return False
    if head != _item_count(current) + 1:
        return False
    mine, theirs = _points(block.get('points')), _points(current.points)
    if mine is not None and theirs is not None and mine < theirs:
        return True
    return declared is not None and head > declared


def build_event(root, event, figures_dir, crop=True, shared=(), overlay=None, profile=None,
                keep_keys=None):
    """Комплект → (задания по порядку, отчёт комплекта)."""
    event_id = event['event_id']
    tasks = OrderedDict()
    report = Counter()
    missing_pages = []
    event['preamble'] = []
    econ = profile == ECON
    leads_by_number = {}          # v5: номер задания → инструкции раздела
    section = {'file': None, 'lead': '', 'left': None}   # v5: инструкция раздела без номеров
    open_lead = []                # v5: подводка «ответьте на вопросы (3)-(5)» + цитата

    def task_for(number, variant='', create=True):
        key = (number, variant)
        if key not in tasks and create:
            tasks[key] = Task(event_id, number, variant)
            if econ and section['lead'] and section['file'] == current_file:
                tasks[key].leads.append(section['lead'])
                if section['left'] is not None:      # «(10 вопросов)» — ровно столько заданий
                    section['left'] -= 1
                    if section['left'] <= 0:
                        section['lead'] = ''
        return tasks.get(key)

    def add_lead(numbers, text, file=None):
        # file — инструкция действует только на задания своего файла (тест и
        # задачи у МОШ — разные файлы с номерами 1…N у обоих).
        for n in numbers:
            got = leads_by_number.setdefault(n, [])
            if text and not any(same_intro(text, seen) for seen, _f in got):
                got.append((text, file))

    def declared_count():
        for text in event['preamble']:
            m = re.search(r'количеств\w*\s+задач\W{0,3}[–—-]\s*(\d+)|\((\d+)\s+задач', text, re.I)
            if m:
                return int(m.group(1) or m.group(2))
        return None

    # 1. Условия (и всё, что лежит в файлах условий / смешанных).
    current = None
    current_file = None
    for entry, page, record, block in collect(root, event.get('task_files') or [], 'tasks', overlay,
                                                  profile):
        if entry['file'] != current_file:
            # Продолжение и вступление не переходят через границу файла:
            # у МОШ задачи и тест — два файла одного комплекта.
            current, current_file = None, entry['file']
            file_keys, last_int, restarted = [], 0, False
            test_section, test_last, sub_prefix, top = 1, 0, '', 0
        if record is None:
            missing_pages.append(f'{entry["page_dir"]}/p{page}')
            continue
        if block.get('_variant_switch'):
            # Новый вариант в том же файле — новая нумерация, не «тест → задачи».
            current, file_keys, last_int = None, [], 0
            report['вариант из шапки файла'] += 1
        if profile != ECON and is_date_number(block):
            # «20.11.2013 Бизнес моей мечты» — дата записи блога в кейсе, номер
            # «20.11» — не номер задания (МОШ-предпринимательство 2013/14).
            block = dict(block, number='')
            report['дата в начале блока — не номер'] += 1
        raw_number = _block_number(block)
        block = _test_number(block, entry['file'])
        kind = block['type']
        number = _block_number(block)
        numbered = kind in ('task', 'task_continuation', 'solution', 'criteria', 'figure') \
            and _real_number(number)
        if profile == ECON:
            pass        # нумерация — по правилам сборки v3 (см. ECON)
        elif numbered and number.startswith('тест-'):
            # Несколько тестов подряд в файле теста («Тест № 1» 1–15, «Тест № 2»
            # 1–15…, МОШ-предпринимательство 2009/10–2011/12): нумерация снова с
            # 1 — следующий тест, вопросы `тест-<тест>.<вопрос>`, а не слияние.
            head = _leading_int(raw_number)
            if kind == 'task' and head == 1 and test_last > 1:
                test_section += 1
                if test_section == 2:
                    for key in file_keys:
                        task = tasks.pop(key)
                        task.number = task.number.replace('тест-', 'тест-1.', 1)
                        tasks[(task.number, task.task_variant)] = task
                    report['файл теста: несколько тестов подряд'] += 1
            if kind == 'task' and head is not None:
                test_last = head
            if test_section >= 2:
                number = f'тест-{test_section}.{raw_number}'
                block = dict(block, number=number)
        elif numbered and restarted:
            # После «тест → задачи» нумерация ещё раз пошла с 1 (финал 2013/14,
            # 10-11: тест 1–15, задания 2 и 3, затем вопросы кейса 1–11):
            # вопросы — подпункты СЛЕДУЮЩЕГО задания (4.1, 4.2 …).
            head = _leading_int(number)
            if kind == 'task' and head == 1 and last_int > 1:
                top = (top or last_int) + 1
                sub_prefix, last_int = f'{top}.', 0
                report['нумерация снова с 1: подпункты следующего задания'] += 1
            if sub_prefix:
                if kind == 'task' and head is not None:
                    last_int = head
                number = sub_prefix + number
                block = dict(block, number=number)
        if econ and block.get('_rules_head') and not any(
                same_intro(block['_rules_head'], seen) for seen in event['preamble']):
            event['preamble'].append(block['_rules_head'])     # v5: правила этапа
        if econ and block.get('_lead'):
            # v5: инструкция блока отборочного МОШ (служебный блок или начало вопроса).
            add_lead(block.get('_lead_numbers') or [], block['_lead'], entry['file'])
        if econ and block.get('_service'):
            text = block.get('text') or ''
            if econ_rules.is_rules_text(text, block.get('title') or '') and not any(
                    same_intro(text, seen) for seen in event['preamble']):
                event['preamble'].append(text)
            report['v5: служебный блок — не задание'] += 1
            continue
        if (econ and kind == 'task' and _real_number(number)
                and econ_rules.format_lines(block.get('text') or '', block.get('title') or '')
                and econ_rules.is_service_text(block.get('text') or '', block.get('title') or '')):
            # v5: служебный блок с номером («Раздел III (5 вопросов, 20 баллов). Из
            # нескольких вариантов нужно выбрать ВСЕ верные ответы», mosh-2009-
            # qualifying-9) — инструкция раздела, не задание.
            block = dict(block, number='')
            number = ''
            report['v5: служебный блок с номером — не задание'] += 1
        if econ and kind == 'task' and not _real_number(number):
            text, title = block.get('text') or '', block.get('title') or ''
            if econ_rules.is_rules_text(text, title):
                if not any(same_intro(text, seen) for seen in event['preamble']):
                    event['preamble'].append(text)
                report['v5: правила этапа → вступление'] += 1
                continue
            lines = econ_rules.format_lines(text, title)
            nums = econ_rules.targets(f'{title}\n{text}')
            if lines and econ_rules.is_service_text(text, title):
                # Построчно: строка с номерами («Задачи 1—5 требуют записи
                # решения») — этим заданиям, остальные — раздел дальше по файлу.
                rest_lines = []
                for line in lines:
                    line_nums = econ_rules.targets(line)
                    if line_nums:
                        add_lead(line_nums, line, entry['file'])
                    else:
                        rest_lines.append(line)
                if rest_lines:
                    section.update(file=entry['file'], lead='\n\n'.join(rest_lines),
                                   left=econ_rules.section_count(f'{title}\n{text}'))
                rest = [para for para in re.split(r'\n\s*\n', f'{title}\n\n{text}')
                        if para.strip() and para.strip() not in lines
                        and not econ_rules.marker_of({'title': para.strip()})]
                if rest and current is None:
                    event['preamble'].append('\n\n'.join(rest))
                report['v5: инструкция раздела → в условие заданий'] += 1
                continue
            if nums and re.search(r'ответьте на вопрос|к заданиям|к вопросам', text, re.I):
                # Подводка к нескольким вопросам («Прочитайте текст ниже и ответьте на
                # вопросы (3) - (5)», vp-2026-final-10) — к ним, не к предыдущему.
                open_lead[:] = [nums, [text], entry['file']]
                report['v5: подводка к вопросам'] += 1
                continue
            if open_lead:
                open_lead[1].append(text)
                continue
        if econ and open_lead and kind == 'task' and _real_number(number):
            add_lead(open_lead[0], '\n\n'.join(open_lead[1]), open_lead[2])
            open_lead.clear()
        if kind == 'task' and not _real_number(number):
            # Блок «задание» без номера (или «0», «intro», буква подпункта):
            # до первого задания — вступление комплекта («Время выполнения —
            # 90 минут…»), после — кусок текущего задания («(б) …»), который
            # модель пометила заданием. Пилот ВП: 23 лишних «задания» v2.
            text = block.get('text') or block.get('title') or ''
            if profile == ECON:
                if current is None:
                    event['preamble'].append(text)
                    report['вступление комплекта'] += 1
                else:
                    current.statement.append(block.get('text') or '')
                    current.pages.append((entry['file'], page))
                    current.quality.append(record)
                    report['безномерной кусок → к заданию'] += 1
                continue
            if is_service_text(text):
                report['служебная строка — мимо'] += 1
                continue
            if any(same_intro(text, seen) for seen in event['preamble']):
                # Вступление части комплекта повторено на каждой странице
                # (МОШ-предпринимательство 2012/13: «Общее время… баллов…»).
                report['повтор вступления — мимо'] += 1
                continue
            if current is None or is_intro_text(text):
                event['preamble'].append(text)
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
                section['lead'] = ''      # v5: инструкция теста не переходит на задачи
                for key in file_keys:
                    task = tasks.pop(key)
                    task.number = f'тест-{task.number}'
                    tasks[(task.number, task.task_variant)] = task
                report['нумерация пошла заново: часть файла — тест'] += 1
            if econ and current is not None and _is_subitem(current, block, head,
                                                            declared_count()):
                # v5: пункт «N)» текущей задачи, размеченный заданием № N.
                current.statement.append(econ_rules.item_label(head, block.get('points'),
                                                               block.get('text') or ''))
                current.subitems = current.absorbed = head
                current.pages.append((entry['file'], page))
                current.quality.append(record)
                report['v5: пункт задачи — не задание'] += 1
                continue
            if head is not None and not sub_prefix:
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
            text = block.get('text') or ''
            item = _leading_int(number)
            if (econ and target is current and item is not None and item > 1
                    and item == _item_count(current) + 1):
                text = econ_rules.item_label(item, block.get('points'), text)
                current.subitems = item
            target.statement.append(text)
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
            _attach_answer(tasks, current, block, kind, entry, page, report, profile=profile)

    section['lead'] = ''          # v5: инструкция раздела — только внутри файла условий
    if profile != ECON:
        split_glued(tasks, report)
    for task in tasks.values():
        head = _leading_int(task.number.replace('тест-', ''))
        files = {f for f, _p in task.pages}
        for text, file in leads_by_number.get(head, []):
            if (file is None or file in files) and not any(
                    same_intro(text, seen) for seen in task.leads):
                task.leads.append(text)

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
        follow = None             # (задание, номер) вопроса, найденного по тексту
        in_statement = False      # сразу после повторённого условия
        stream, table_header = [], {}
        for entry, page, record, block in collect(root, files, role, overlay, profile):
            # Таблица критериев одним безномерным блоком (ВП, основы бизнеса:
            # «№ | Формулировка | Критерии | Макс. | Баллы») — по строкам.
            if (profile != ECON and block is not None
                    and block['type'] in ('task', 'task_continuation', 'criteria', 'solution')
                    and not _real_number(_block_number(block))):
                parts = explode_table_rows(block, role, table_header.get(entry['file']))
                if len(parts) > 1 or parts[0] is not block:
                    report['таблица критериев → по строкам'] += 1
                    table_header[entry['file']] = parts[-1]['_header']
                stream.extend((entry, page, record, part) for part in parts)
            else:
                stream.append((entry, page, record, block))
        # v5: файл решений «задача (повтор с названием) → её решение и критерии»:
        # под повтором задачи T блоки без названия с другим номером — пункты T
        # («Пункт №3 (7 баллов)», vp-2026-final-11), а не решения задачи № 3.
        headers = {_block_number(b) for _e, _p, _r, b in stream
                   if b is not None and b.get('type') == 'task' and (b.get('title') or '').strip()
                   and _real_number(_block_number(b))
                   and _find_task(tasks, _block_number(b), '', b.get('task_variant') or '')}
        # Только у комплекта, где в файле условий нашлись пункты, размеченные
        # заданиями (_is_subitem), — иначе правило задело бы десятки комплектов.
        region_mode = (profile == ECON and len(headers) >= 2
                       and any(t.absorbed for t in tasks.values()))
        region = None
        for entry, page, record, block in stream:
            if record is None:
                missing_pages.append(f'{entry["page_dir"]}/p{page}')
                continue
            if block.get('_service'):
                continue          # v5: служебный блок файла ответов — не решение
            if (profile == ECON and block.get('_qfile')
                    and block.get('type') in ('task', 'solution', 'criteria')):
                # v5: файл ответов отборочного МОШ с блоками — номер по тексту
                # повторённого вопроса того же варианта (модель путает номера:
                # «вопрос 1, вар. 3» записан как «2/3», mosh-2025-qualifying-7).
                variant = block.get('task_variant') or ''
                same = OrderedDict((k, t) for k, t in tasks.items() if t.task_variant == variant)
                found = match_by_text(same, block.get('text') or '', '')
                if found is not None:
                    if found.number != _block_number(block):
                        report['v5: номер файла ответов — по тексту вопроса'] += 1
                    block = dict(block, number=found.number)
                elif block.get('type') == 'task':
                    report['v5: вопрос файла ответов без пары — мимо'] += 1
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
            if profile != ECON and kind in ('task', 'solution', 'criteria', 'task_continuation'):
                grid = parse_answer_grid(block.get('text') or '')
                own = _block_number(block)
                if _real_number(own) and own not in grid:
                    grid = {}          # таблица с номером блока — только если с него и начинается
                if not grid and not _real_number(own):
                    grid = parse_answer_list(block.get('text') or '', block.get('answer') or '')
                variant = block.get('task_variant') or ''
                hits = [(tasks.get((f'тест-1.{n}', variant)) or tasks.get((f'тест-{n}', variant))
                         or tasks.get((f'тест-{n}', '')) or tasks.get((n, variant)), a)
                        for n, a in grid.items()] if len(grid) >= 3 else []
                if any(t is not None for t, _a in hits):
                    # Бланк ответов теста (сетка «вопрос → отмеченный вариант»)
                    # или таблица «номер | ответ».
                    for target, answer in hits:
                        if target is not None and not target.answer:
                            target.answer = answer
                            target.solution_pages.append((entry['file'], page))
                            report['бланк ответов → ответы теста'] += 1
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
            if region_mode and kind == 'task':
                number = _block_number(block)
                if (block.get('title') or '').strip() and number in headers:
                    region = _find_task(tasks, number, '', block.get('task_variant') or '')
                elif (region is not None and _real_number(number) and number != region.number
                      and not (block.get('title') or '').strip()):
                    last = region                 # повтор пункта задачи — мимо
                    report['v5: пункт задачи в файле решений'] += 1
                    continue
            if kind == 'task':
                # Условие, повторённое в файле решений: запоминаем как
                # последнее задание; если условия нет нигде — берём его.
                number = _block_number(block)
                target = _find_task(tasks, number, block.get('title') or '',
                                    block.get('task_variant') or '')
                # Текст повторённого вопроса надёжнее номера: в файле ответов
                # МОШ-предпринимательства вопрос теста «1» — это «тест-1», а
                # не задача 1 комплекта (номера в файле ответов идут с 1).
                by_text = (match_by_text(tasks, block.get('text') or '', number)
                           if profile != ECON else None)
                follow = None
                if by_text is not None and by_text is not target and (
                        target is None or text_score(target, block.get('text') or '')
                        < TEXT_OTHER):
                    target = by_text
                    follow = (target, number)
                    report['условие в файле решений — по тексту'] += 1
                if target is None and not _real_number(number):
                    # Подпункт, повторённый в файле решений («г», «(а)»): к
                    # последнему заданию, нового не заводим.
                    last = last or (list(tasks.values())[-1] if tasks else None)
                    report['безномерной кусок решения → к заданию'] += 1
                    continue
                if target is None:
                    target = compatible_target(tasks, number, block.get('task_variant') or '',
                                               last, profile)
                    if target is not None:
                        follow = (target, number)
                        report['номер файла решений → совместимое задание'] += 1
                key = (event_id, number, block.get('task_variant') or '')
                if (target is None and profile == ECON and keep_keys is not None
                        and key not in keep_keys):
                    # v5: нового ключа (которого не было в v4) файл ответов не заводит:
                    # повтор вопроса — к заданию с тем же текстом; блок перечитанной
                    # страницы без пары — мимо (ключи v4 сохраняются как были).
                    found = match_by_text(tasks, block.get('text') or '', '')
                    if found is not None:
                        target, follow = found, (found, number)
                        report['v5: повтор вопроса в ответах — по тексту'] += 1
                    elif block.get('_v5'):
                        report['v5: перечитанный блок ответов без пары — мимо'] += 1
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
                elif target.statement and not target.from_solution_only and profile != ECON:
                    # «Решебник» МОШ-предпринимательства: условие повторено, а
                    # ответ («СТ. 18») — абзацем в том же блоке: хвост — решение.
                    text = block.get('text') or ''
                    statement = join_pieces(target.statement)
                    rest = strip_statement_echo(text, statement)
                    if rest != text and rest.strip() and not is_statement_echo(rest, statement):
                        target.solution.append(rest)
                        target.solution_pages.append((entry['file'], page))
                        report['решение внутри повтора условия'] += 1
                if block.get('answer'):
                    # Тест с отмеченным ответом (сканы отборочных МОШ): файл
                    # ответов повторяет вопрос, ответ — в поле answer.
                    target.answer = (target.answer + '\n' + block['answer']).strip()
                    target.solution_pages.append((entry['file'], page))
                    report['ответ теста из файла ответов'] += 1
                last = target
                continue
            if kind == 'task_continuation' and profile != ECON:
                # Хвост условия, повторённого в файле решений (МОШ: условие →
                # решение, условие переходит на новую страницу), — не решение.
                number = _block_number(block)
                echo_of = (_find_task(tasks, number, '', block.get('task_variant') or '')
                           if _real_number(number) else None) or last
                if (echo_of is not None and echo_of.statement and not echo_of.from_solution_only
                        and is_statement_echo(block.get('text') or '',
                                              join_pieces(echo_of.statement))):
                    report['повтор условия в файле решений — мимо'] += 1
                    last = echo_of
                    continue
            if kind == 'task_continuation' and last is not None and \
                    last.from_solution_only and not (last.solution or last.criteria):
                last.statement.append(block.get('text') or '')
                continue
            force = None
            if (follow is not None and follow[0] is last and kind in ('solution', 'criteria')
                    and _block_number(block) == follow[1]):
                # Решение с тем же номером сразу за вопросом, сопоставленным по
                # тексту, — решение ЭТОГО вопроса, а не задания с таким номером.
                force = last
            else:
                follow = None
            if (force is None and region is not None and not (block.get('title') or '').strip()
                    and _real_number(_block_number(block))
                    and _block_number(block) != region.number):
                force = region
                report['v5: пункт задачи в файле решений'] += 1
            last = _attach_answer(tasks, last, block, role if kind == 'task_continuation'
                                  else kind, entry, page, report, force=force,
                                  profile=profile) or last

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
                              'caption': caption, 'flag': flag, 'page': page,
                              'page_dir': page_dir, 'bbox_model': bbox})
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


_ROW_NUMBER = re.compile(r'^\**\s*(\d{1,2}(?:\.\d{1,2})?)\.?\s*\**$')


def _cells(line):
    body = line.strip()
    if body.startswith('|'):
        body = body[1:]
    if body.endswith('|'):
        body = body[:-1]
    return [c.strip() for c in body.split('|')]


def explode_table_rows(block, role, header_hint=None):
    """Таблица критериев/ответов («№ | Формулировка задания | Критерии оценки
    и примеры | Макс. сумма баллов | Баллы и примечания» — ВП, основы бизнеса)
    в блоке БЕЗ номера → по блоку `role` (criteria/solution) на строку с
    номером задания в первой ячейке; ячейки — абзацами «**Заголовок:** текст»,
    балл — из столбца «Макс…». Текст до таблицы остаётся исходным блоком.
    Строка без номера (продолжение объединённой ячейки) дописывается к
    предыдущей. Продолжение таблицы на следующей странице без шапки —
    с шапкой `header_hint` (то же «№», те же столбцы). Нет строк с номером
    или шапка не критериев — блок как был ([block])."""
    lines = (block.get('text') or '').splitlines()
    header, rows, before, in_table, head_first = [], [], [], False, ''
    for i, line in enumerate(lines):
        if not line.strip().startswith('|'):
            if not in_table:
                before.append(line)
            elif rows and line.strip():
                rows[-1][1][-1] += '\n' + line.strip()
            continue
        in_table = True
        cells = _cells(line)
        if all(re.fullmatch(r':?-{3,}:?', c) for c in cells if c):
            continue
        number = _ROW_NUMBER.match(cells[0]) if cells else None
        if number:
            rows.append((number.group(1), cells[1:]))
        elif rows and cells:
            prev = rows[-1][1]
            for k, cell in enumerate(cells[1:]):
                if cell and k < len(prev):
                    prev[k] = (prev[k] + '\n' + cell).strip()
        elif not rows:
            header = cells[1:]
            head_first = cells[0] if cells else ''
    if not header and header_hint:
        head_first, header = header_hint[0], list(header_hint[1])
    # Только таблица КРИТЕРИЕВ: шапка «№ | … Критерии/Формулировка/Ответ …».
    # Таблица данных с целыми в первом столбце (Q, P, год) — не трогаем.
    if not rows or not header or not re.match(r'\**\s*(№|N\b|No\.?|Номер)',
                                                    head_first or '', re.I) or not any(
            re.search(r'критери|формулиров|ответ|решени', h, re.I) for h in header):
        return [block]
    out = []
    head = '\n'.join(before).strip()
    if head:
        out.append(dict(block, text=head))
    for number, cells in rows:
        parts, points = [], None
        for k, cell in enumerate(cells):
            cell = cell.replace('<br>', '\n').strip()
            name = header[k] if k < len(header) else ''
            if not cell:
                continue
            if name.lower().startswith('макс') and re.fullmatch(r'\d{1,3}', cell):
                points = int(cell)
                continue
            parts.append(f'**{name}:** {cell}' if name else cell)
        out.append({'type': role, 'number': number, 'text': '\n\n'.join(parts),
                    'points': points, '_from_table': True,
                    '_header': (head_first, header)})
    return out


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
    """Номер задания — с цифрой и не «0» (вступление/подпункт — нет). Номер
    с ведущим нулём («06.11», «08.12») — дата записи в тексте кейса (ВП,
    основы бизнеса 2019/20), а не номер задания."""
    return (bool(number) and any(ch.isdigit() for ch in number) and number != '0'
            and not re.match(r'0\d', number))


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


def _attach_answer(tasks, last, block, kind, entry, page, report, force=None, profile=None):
    """Решение/критерии → задание по номеру, иначе по названию, иначе —
    продолжение предыдущего решения (блок без номера сразу за ним).

    `force` — задание задано вызывающим (решение за вопросом, найденным по
    тексту). Номер N без своего задания при единственном `тест-N` — к нему
    (файл ответов нумерует вопросы теста с 1). Блок, повторяющий условие
    другого задания (по тексту, однозначно), — к тому заданию."""
    number = _block_number(block)
    variant = block.get('task_variant') or ''
    target = force if force is not None else _find_task(tasks, number,
                                                        block.get('title') or '', variant)
    how = 'за вопросом' if force is not None else \
        'по номеру' if target is not None and number else 'по названию'
    if target is None and _real_number(number) and not number.startswith('тест-'):
        test_target = compatible_target(tasks, number, variant, last, profile)
        if test_target is not None:
            target, how = test_target, 'номер → тест-N'
    if force is None and profile != ECON:
        by_text = match_by_text(tasks, block.get('text') or '', number)
        if by_text is not None and by_text is not target and (
                target is None or text_score(target, block.get('text') or '') < TEXT_OTHER):
            target, how = by_text, 'по тексту условия'
    if target is None and not _real_number(number) and last is not None:
        target, how = last, 'продолжение'
    head = _leading_int(number)
    if target is None and last is not None and head is not None and tasks and profile != ECON and             head > max((_leading_int(t.number) or 0) for t in tasks.values()):
        # Номер больше любого задания комплекта СРАЗУ за блоком того же вида
        # (решение за решением, критерии за критериями, тот же файл, та же или
        # предыдущая страница) — пункт списка внутри него («5)…14)» при
        # четырёх заданиях; ВП, финграмотность). Иначе — в несопоставленные.
        pages = last.criteria_pages if kind == 'criteria' else last.solution_pages
        if pages and pages[-1][0] == entry['file'] and page - pages[-1][1] in (0, 1):
            target, how = last, 'номер вне заданий → продолжение'
    if target is None:
        report[f'{kind}: не сопоставлено'] += 1
        report.setdefault('_unmatched', [])
        report['_unmatched'].append(f'{entry["file"]}#p{page} №{number or "—"} '
                                    f'«{(block.get("title") or "")[:40]}»')
        return None
    text = block.get('text') or ''
    if kind == 'solution' and target.statement and not target.from_solution_only             and profile != ECON:
        trimmed = strip_statement_echo(text, join_pieces(target.statement))
        if trimmed != text:
            report['повтор условия в начале решения — срезан'] += 1
            text = trimmed
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
    # v5: инструкция раздела — в начало условия, если её там ещё нет (у ВП 2007
    # каждый вопрос уже начинается с «Выберите среди предложенных ответов…»).
    missing = [lead for lead in task.leads if not is_statement_echo(lead, statement)]
    if missing:
        statement = '\n\n'.join(missing + ([statement] if statement else []))
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
        **({'section_md': '\n\n'.join(task.leads)} if task.leads else {}),
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


def assemble(digitized, reference_events, v1_rows, model, only_events=None, crop=True,
             overlay=None, out_dir=None, suffix='v2', figures_subdir='figures', profile=None,
             keep_keys=None):
    """Собрать всё. Возвращает сводку; файлы пишет в `out_dir` (по умолчанию
    `digitized`) с именами `reference_problems_<suffix>.jsonl` и т. д.
    Страницы читаются из `digitized`, поверх них — заплатки `overlay`."""
    out_dir = out_dir or digitized
    os.makedirs(out_dir, exist_ok=True)
    events_files = {e['event_id']: e for e in _read_jsonl(
        os.path.join(digitized, 'events_files.jsonl'))}
    meta = {e['event_id']: e for e in reference_events}
    # Сборка с заплатками (--overlay) пишет вырезки в свою папку (figures_v2):
    # общая figures\ у v1 и v2 затирала вырезки v1 (сессия 2, 14.10).
    figures_dir = os.path.join(out_dir, figures_subdir)
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
                                             shared=shared, overlay=overlay, profile=profile,
                                             keep_keys=keep_keys)
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
    with open(os.path.join(out_dir, f'reference_problems_{suffix}.jsonl'), 'w',
              encoding='utf-8') as handle:
        for row in out_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    with open(os.path.join(out_dir, f'events_{suffix}.jsonl'), 'w', encoding='utf-8') as handle:
        for row in out_events:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    with open(os.path.join(out_dir, f'compare_v1_{suffix}.csv'), 'w', encoding='utf-8-sig',
              newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['event_id', 'v1', 'v2', 'v2_numbers'])
        writer.writeheader()
        writer.writerows(compare)
    with open(os.path.join(out_dir, 'unmatched_solutions.txt'), 'w',
              encoding='utf-8') as handle:
        handle.write('\n'.join(unmatched) + '\n')
    summary[f'заданий {suffix}'] = len(out_rows)
    # Ключ сверки с нарезкой v1 — не «заданий v1»: при --suffix v1 он затёр бы
    # число собранных заданий.
    summary['заданий в нарезке v1'] = sum(v1_counts.values())
    summary['комплектов'] = len(out_events)
    summary['комплектов с другим числом заданий'] = len(compare)
    summary['решений не сопоставлено'] = len(unmatched)
    return summary


def problem_count_by(records, key):
    counts = defaultdict(int)
    for record in records:
        counts[record.get(key)] += 1
    return dict(counts)
