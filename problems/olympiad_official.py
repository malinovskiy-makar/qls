# -*- coding: utf-8 -*-
"""Официальный эталон олимпиады: чтение файлов аудита и чистка текста PDF.

Чистые функции без записи в базу — их зовёт `apply_olympiad_audit`.
Эталон и формат файлов описаны в docs/OLYMPIAD_AUDIT.md.

⚠️ НОМЕР SOLVEHUB — ПОЗИЦИЯ В ИХ СПИСКЕ, А НЕ ОФИЦИАЛЬНЫЙ НОМЕР. В пилоте
ВП у 123 из 573 строк номер агрегатора не совпал с номером в PDF
организатора (перестановки 4→1, 3→1, 2→4). Номер берётся из эталона, а
старый сохраняется в `raw_meta['aggregator_number']`.

⚠️ КОСИНУС ПО ГОЛОМУ ТЕКСТУ PDF НЕ РАБОТАЕТ. Вектор банка строится по
формуле (условие + темы + решение, `problems/embedding_formula.py`), и
против голого текста PDF он нашёл 1 % верных пар. Здесь сравнивается
только текст: `fuzzy_ratio` по `normalize_for_compare` — та же
нормализация, что у `find_olympiad_text_duplicates`.
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata

from problems.text_dedup import (
    fuzzy_ratio, normalize_for_compare, problem_identity_text,
)

#: Порог «то же задание» для правила близнецов и проверок на месте.
TWIN_THRESHOLD = 0.90

#: Источник для заданий, импортированных из официального PDF организатора.
OFFICIAL_SOURCE_NAME = 'Высшая проба: официальный архив'
OFFICIAL_SOURCE_DEFAULTS = {
    'author': 'НИУ «Высшая школа экономики»',
    'kind': 'олимпиада',
    'note': ('Официальные задания и решения заключительного этапа олимпиады '
             '«Высшая проба» по экономике, опубликованные организатором: '
             'https://olymp.hse.ru/mmo/tasks-eco. У каждой задачи — ссылка '
             'на PDF в привязке к источнику.'),
}

#: Названия олимпиад в строках OlympiadRef — как у уже записанных строк.
OLYMPIAD_NAMES = {
    'vp': 'Олимпиада школьников «Высшая проба» по экономике',
    'vp-fingram': 'Олимпиада школьников «Высшая проба» по финансовой грамотности',
    'vp-ob': 'Олимпиада школьников «Высшая проба» по основам бизнеса',
}


# ── Файлы аудита ─────────────────────────────────────────────────────────

def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def bank_academic_year(value):
    """`2016/2017` → `2016/17`: в банке учебный год пишется коротко."""
    value = (value or '').strip()
    match = re.fullmatch(r'(\d{4})/(\d{2})(\d{2})', value)
    if match:
        return f'{match.group(1)}/{match.group(3)}'
    return value


def variant_of(event_id):
    """`vp-2021-final-10-reserve` → `reserve`, `vp-2013-final-11-v1` → `v1`."""
    return (event_id or '').rsplit('-', 1)[-1]


class Reference:
    """Эталон: задания официальных комплектов по (event_id, номер)."""

    def __init__(self, rows):
        self.tasks = {}
        self.by_event = {}
        for row in rows:
            key = (row['event_id'], str(row['number']))
            self.tasks[key] = row
            self.by_event.setdefault(row['event_id'], []).append(row)

    @classmethod
    def load(cls, path):
        return cls(read_jsonl(path))

    def event_url(self, event_id):
        rows = self.by_event.get(event_id) or []
        return rows[0].get('source_url', '') if rows else ''

    def event_for(self, year, grade):
        """Официальный комплект по году и классу (`v1` раньше `reserve`)."""
        found = [e for e in self.by_event
                 if e.split('-')[1] == str(year)
                 and '-'.join(e.split('-')[3:-1]) == str(grade)]
        found.sort(key=lambda e: (variant_of(e) != 'v1', e))
        return found[0] if found else None

    def best_in_event(self, bank_norm, event_id):
        """(номер, сходство) лучшего задания комплекта для текста банка."""
        best = (None, 0.0)
        for row in self.by_event.get(event_id) or []:
            score = fuzzy_ratio(bank_norm, row['norm_text'])
            if score > best[1]:
                best = (str(row['number']), score)
        return best


def bank_norm_text(problem):
    """Текст задачи банка для сравнения: условие + подпункты, нормализованно."""
    return normalize_for_compare(problem_identity_text(problem))


_REVIEW_ROW = re.compile(r'^\|\s*(\d+)\s*\|\s*(vp-[\w-]+)\s*\|\s*(\d+)\s*\|(.*)\|\s*$')


def parse_claude_review(path):
    """Файл проверки Claude → (подтверждённые высокие, перенумеровки «на глаза»).

    Высокие: множество (problem_id, event_id, номер) из таблицы раздела
    «Высокий ярус». На глаза: {problem_id: (event_id, текущий, предложенный)}
    из таблицы раздела «Перенумеровка». Разделы различаются по заголовку
    `## `, строки таблиц — по виду `| id | vp-… | № | … |`.
    """
    high, eyeball = set(), {}
    section = None
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            if line.startswith('## '):
                lowered = line.lower()
                section = ('high' if 'высокий ярус' in lowered else
                           'renumber' if 'перенумер' in lowered else None)
                continue
            match = _REVIEW_ROW.match(line.strip())
            if not match or section is None:
                continue
            pid, event_id, number, rest = match.groups()
            if section == 'high':
                high.add((int(pid), event_id, number))
            else:
                proposed = rest.split('|')[0].strip()
                eyeball[int(pid)] = (event_id, number, proposed)
    return high, eyeball


_OTHER_EVENT = re.compile(
    r'текст совпал с (?P<found>vp-[\w-]+) №(?P<found_no>\d+).*'
    r'координаты строки ведут в (?P<own>vp-[\w-]+) №(?P<own_no>\d+)')


def parse_other_event_reason(reason):
    """Причина строки `other_event` → (найденный комплект, №, свой комплект, №)."""
    match = _OTHER_EVENT.search(reason or '')
    if not match:
        return None
    return (match['found'], match['found_no'], match['own'], match['own_no'])


# ── Чистка текста из PDF для импорта ────────────────────────────────────

_MATH_ALNUM = re.compile('[\U0001D400-\U0001D7FF]')
_COLONTITLE = re.compile(
    r'олимпиада\s+школьников\s*[«"“]?\s*высшая\s+проба', re.IGNORECASE)
_SUBJECT_LINE = re.compile(r'^(экономика)?\s*(\d{1,2}\s*класс)?$', re.IGNORECASE)
_NEXT_PAGE = re.compile(r'^на следующей странице есть', re.IGNORECASE)
_PAGE_NUMBER = re.compile(r'^\d{1,2}$')
_HEADER = re.compile(
    r'^(?:Задание|Задача)\s*№?\s*(?P<no>\d+)\s*\.?\s*(?P<rest>.*)$')
_POINTS = re.compile(r'\(\s*(?P<pts>\d+)\s*балл\w*\s*\)')
_QUOTED = re.compile(r'«(?P<title>[^»]+)»')
_LIST_START = re.compile(r'^(\(?[а-яa-z]\)|\d+[.)]|[•\-–—])(\s|$)')
_ANSWER_START = re.compile(r'^(Возможные варианты ответ|Ответ\b|Решение\b)')
#: Строка такой длины — полная строка страницы PDF, а не заголовок.
_FULL_LINE = 50
_SHORT_RUN = re.compile(r'(?:^\S.{0,2}\n){4,}', re.MULTILINE)
_DOUBLED_MATH = re.compile('([\U0001D400-\U0001D7FF])\\1')


def formula_suspect(raw_text):
    """Признак рассыпанной при извлечении формулы: удвоенные курсивные
    буквы (𝑌𝑌) или четыре строки подряд по 0–3 знака. Только для отчёта."""
    raw = raw_text or ''
    return bool(_DOUBLED_MATH.search(raw) or _SHORT_RUN.search(raw))


def _plain_math_letters(text):
    """Курсивные математические буквы PDF (𝑃, 𝑄) → обычные (P, Q)."""
    return _MATH_ALNUM.sub(lambda m: unicodedata.normalize('NFKC', m.group()), text)


def _drop_colontitles(lines):
    """Колонтитулы страниц PDF: название олимпиады, «Экономика N класс»,
    «На следующей странице…» и номер страницы рядом с ними."""
    drop = set()
    for i, line in enumerate(lines):
        s = line.strip()
        if _COLONTITLE.search(s) or _NEXT_PAGE.match(s) or (
                s and _SUBJECT_LINE.match(s) and len(s) > 1):
            drop.add(i)
    # Номер страницы — только в окрестности колонтитула: одиночная цифра
    # в другом месте может быть обломком формулы, её не трогаем.
    for i, line in enumerate(lines):
        if _PAGE_NUMBER.match(line.strip()):
            near = [j for j in drop if abs(j - i) <= 4]
            if near:
                drop.add(i)
    return [line for i, line in enumerate(lines) if i not in drop]


def _unwrap(lines):
    """Склеить перенос строк по ширине страницы обратно в абзацы.

    Строка приклеивается к предыдущей, если начинается со строчной буквы
    или запятой, либо если предыдущая — полная строка страницы (от
    `_FULL_LINE` знаков) без точки в конце. Маркер списка или пустая строка
    оставляют перенос как есть (лишний перенос безвреден, лишняя склейка —
    нет). Перенос слова через дефис склеивается без дефиса.
    """
    out = []
    for raw in lines:
        s = ' '.join(raw.split())
        if not s:
            if out and out[-1] != '':
                out.append('')
            continue
        prev = out[-1] if out else ''
        wrapped = len(prev) >= _FULL_LINE and prev[-1] not in '.!?:;'
        joinable = prev and (
            prev in ('•', '-', '–', '—')
            or ((s[0].islower() or s[0] in ',;:)»' or wrapped)
                and not _LIST_START.match(s)))
        if joinable:
            if (prev.endswith('-') and len(prev) > 1 and prev[-2].isalpha()
                    and s[0].islower()):
                out[-1] = prev[:-1] + s
            else:
                out[-1] = prev + ' ' + s
        else:
            out.append(s)
    while out and out[-1] == '':
        out.pop()
    return out


def _escape_markdown(lines):
    """Текст из PDF — не разметка: `*` и `>` в начале строки экранируются."""
    escaped = []
    for line in lines:
        line = line.replace('*', r'\*').replace('_', r'\_')
        if line.startswith('>') or line.startswith('#'):
            line = '\\' + line
        escaped.append(line)
    return escaped


def parse_header(lines):
    """Шапка «Задание N. «Название» (N баллов)» → (название, баллы, остаток).

    Название ищется в кавычках «…» в первой строке или отдельной строкой
    после неё; иначе — текст между номером и «(N баллов)».
    """
    idx = next((i for i, s in enumerate(lines) if s.strip()), None)
    if idx is None:
        return '', None, lines
    match = _HEADER.match(lines[idx].strip())
    if not match:
        return '', None, lines
    rest = match['rest']
    points = None
    pts = _POINTS.search(rest)
    if pts:
        points = int(pts['pts'])
    title, tail = '', ''
    quoted = _QUOTED.search(rest)
    if quoted:
        title = quoted['title'].strip()
        tail = rest[max(quoted.end(), pts.end() if pts else 0):].strip()
    else:
        before = rest[:pts.start()] if pts else rest
        title = before.strip(' .')
        tail = rest[pts.end():].strip() if pts else ''
    remaining = lines[idx + 1:]
    if not title:
        nxt = next((i for i, s in enumerate(remaining) if s.strip()), None)
        if nxt is not None:
            alone = _QUOTED.fullmatch(remaining[nxt].strip())
            if alone:
                title = alone['title'].strip()
                remaining = remaining[nxt + 1:]
    if tail:
        remaining = [tail] + remaining
    return title, points, remaining


def split_combined(lines):
    """Условие и решение в ОДНОМ PDF: всё с «Возможные варианты ответов» /
    «Ответ» / «Решение» уходит в решение."""
    for i, line in enumerate(lines):
        if i and _ANSWER_START.match(line.strip()):
            return lines[:i], lines[i:]
    return lines, []


def clean_pdf_task(raw_text, solution_text, combined=False):
    """Текст задания из PDF → (название, баллы, условие, решение) в markdown.

    Только детерминированные правки формы: колонтитулы, шапка, переносы
    строк, курсивные буквы, экранирование. Слова не меняются.
    """
    lines = _plain_math_letters(raw_text or '').splitlines()
    lines = _drop_colontitles(lines)
    title, points, lines = parse_header(lines)
    extra_solution = []
    if combined:
        lines, extra_solution = split_combined(lines)
    statement = '\n'.join(_escape_markdown(_unwrap(lines)))
    sol_lines = extra_solution + [''] + _drop_colontitles(
        _plain_math_letters(solution_text or '').splitlines())
    solution = '\n'.join(_escape_markdown(_unwrap(sol_lines))).strip()
    return title, points, statement.strip(), solution
