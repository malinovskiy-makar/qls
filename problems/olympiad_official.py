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

from rapidfuzz import fuzz

from problems.olympiad_audit.registry import REGISTRY
from problems.text_dedup import (
    fuzzy_ratio, normalize_for_compare, problem_identity_text,
)

#: Порог «то же задание» для правила близнецов и проверок на месте.
TWIN_THRESHOLD = 0.90

#: Источник для заданий ВП, импортированных из официального PDF организатора.
#: Для других олимпиад — `registry.get(slug).official_source_name`.
OFFICIAL_SOURCE_NAME = REGISTRY['vp'].official_source_name
OFFICIAL_SOURCE_DEFAULTS = REGISTRY['vp'].official_source_defaults

#: Названия олимпиад в строках OlympiadRef — как у уже записанных строк.
OLYMPIAD_NAMES = {slug: entry.olympiad_name for slug, entry in REGISTRY.items()}


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
    """Эталон: задания официальных комплектов по (event_id, номер).

    ⚠️ У отборочных МОШ внутри одного PDF бывают «Задание N. Вариант K» —
    одна пара (комплект, номер) на несколько заданий. Такие строки лежат по
    ключу (event_id, номер, вариант задания); по паре (event_id, номер)
    доступны только задания без варианта — как было у ВП.
    """

    def __init__(self, rows):
        self.tasks = {}
        self.by_event = {}
        for row in rows:
            number, variant = str(row['number']), str(row.get('task_variant') or '')
            self.tasks[(row['event_id'], number, variant)] = row
            if not variant:
                self.tasks[(row['event_id'], number)] = row
            self.by_event.setdefault(row['event_id'], []).append(row)

    def task(self, event_id, number, task_variant=''):
        return self.tasks.get((event_id, str(number), str(task_variant or '')))

    def events(self):
        """Комплекты эталона: event_id → (год, этап, класс) первой строки."""
        return {ev: rows[0] for ev, rows in self.by_event.items()}

    def best_in_event_by(self, text, event_id, score):
        """(номер, вариант задания, сходство) лучшего задания комплекта;
        `score(text, row)` — функция сходства."""
        best = (None, '', 0.0)
        for row in self.by_event.get(event_id) or []:
            value = score(text, row)
            if value > best[2]:
                best = (str(row['number']), str(row.get('task_variant') or ''), value)
        return best

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


# ── Ключ «без разметки» (МОШ: банк в LaTeX, PDF простым текстом) ─────────

_FIG = re.compile(r'\[\[figure:[^\]]*\]\]', re.IGNORECASE)
_TEXTCMD = re.compile(
    r'\\(?:text|mathrm|textbf|textit|mathbf|operatorname|mbox)\s*\{([^{}]*)\}')
_FRAC = re.compile(r'\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}')
_CMD = re.compile(r'\\[a-zA-Z]+')
#: «КофеиN ные» → «кофейные»: глиф «й» в части PDF МОШ извлекается так.
_PDF_Y = re.compile(r'и[nN] ?(?=[а-яё])')
_KEEP = re.compile(r'[^0-9a-zа-яё=+\-*/<>%]+')
_OPS = re.compile(r' ?([=+\-*/<>]) ?')


def markup_free_key(text, pdf=False):
    """Ключ сравнения без разметки: LaTeX, маркеры рисунков, пунктуация и
    регистр не различаются; числа и буквы остаются. Тот же ключ, что у
    сверки МОШ-1 (tools/s1_p3_match.py) и проверки Claude 09.10 — иначе
    пороги команды и проверки разъехались бы. Только для сравнения."""
    t = unicodedata.normalize('NFKC', text or '')
    if pdf:
        t = _PDF_Y.sub('й', t)
    t = (_FIG.sub(' ', t).replace('\\cdot', '*').replace('\\times', '*')
         .replace('\\le', '<=').replace('\\ge', '>='))
    for _ in range(2):
        t = _TEXTCMD.sub(r' \1 ', t)
        t = _FRAC.sub(r'(\1)/(\2)', t)
    t = _CMD.sub(' ', t).lower().replace('ё', 'е')
    t = re.sub('[‐‑‒–—―−]', '-', t)
    t = _KEEP.sub(' ', t)
    t = _OPS.sub(r'\1', t)
    return ' '.join(t.split())


#: Короче этого ключа частичное сходство врёт (совпадёт с любым куском).
CONTAINMENT_MIN_LEN = 150


def containment(bank_key, task_key):
    """Насколько текст банка сидит внутри задания эталона (0..1): частичное
    сходство первых 600 знаков банка. Нужно там, где нарезка агрегатора
    склеила или разрезала задания. Короткий текст банка — 0 (не судим)."""
    if len(bank_key) < CONTAINMENT_MIN_LEN or not task_key:
        return 0.0
    return fuzz.partial_ratio(bank_key[:600], task_key) / 100.0


#: Номер задания эталона: `3`, у МОШ ещё `1.2` и `тест-4`.
_NUMBER = r'[\w.\-]+'
_EVENT = r'[a-z]+(?:-[\w]+)+'
_REVIEW_ROW = re.compile(
    rf'^\|\s*(\d+)\s*\|\s*({_EVENT})\s*\|\s*({_NUMBER})\s*\|(.*)\|\s*$')
_REVIEW_BULLET = re.compile(
    rf'^-\s*(\d+)\s+({_EVENT})\s+({_NUMBER})\s*→\s*(\S*)\s')


class ClaudeReview:
    """Разобранный файл проверки Claude (claude_review_*.md).

    * `high` — подтверждённые пары высокого яруса: (problem_id, event_id,
      номер, вариант задания). Вариант — из колонки «вариант», если она есть
      в шапке таблицы (у МОШ), иначе пусто (у ВП).
    * `high_eyeball` — пары высокого яруса из таблицы «на глаза» внутри
      того же раздела: НЕ подтверждены, не пишутся.
    * `renumber_eyeball` — {problem_id: [(event_id, текущий, предложенный)]}
      из раздела «Перенумеровка»: таблица (ВП) или список «- id event
      текущий→предложенный …» (МОШ, «сомнительные»).
    """

    def __init__(self):
        self.high = set()
        self.high_eyeball = set()
        self.renumber_eyeball = {}

    def is_renumber_eyeball(self, problem_id, event_id):
        return any(ev == event_id for ev, _cur, _new
                   in self.renumber_eyeball.get(problem_id, ()))


def parse_claude_review(path):
    """Файл проверки Claude → `ClaudeReview`.

    Разделы различаются по заголовку `## ` («Высокий ярус», «Перенумеровка»).
    Внутри высокого яруса строка, НАЧИНАЮЩАЯСЯ с «На глаза», открывает
    таблицу НЕподтверждённых пар — у ВП её не было, у МОШ она есть (16 пар).
    ⚠️ Именно «начинается»: слова «на глаза» стоят и в пояснительном абзаце
    перед таблицей подтверждённых — по вхождению все 657 пар МОШ ушли бы в
    «на глаза» (поймано сухим прогоном 09.10).
    """
    review = ClaudeReview()
    section, eyeball_table, variant_col = None, False, False
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            stripped = line.strip()
            if line.startswith('## '):
                lowered = line.lower()
                section = ('high' if 'высокий ярус' in lowered else
                           'renumber' if 'перенумер' in lowered else None)
                eyeball_table, variant_col = False, False
                continue
            if section == 'high' and stripped.lower().startswith('на глаза'):
                eyeball_table = True
                continue
            if stripped.startswith('|') and 'event_id' in stripped:
                # Шапка таблицы: есть ли колонка варианта задания.
                variant_col = 'вариант' in [c.strip().lower()
                                            for c in stripped.strip('|').split('|')]
                continue
            match = _REVIEW_ROW.match(stripped)
            if match and section == 'high':
                pid, event_id, number, rest = match.groups()
                variant = rest.split('|')[0].strip() if variant_col else ''
                key = (int(pid), event_id, number, variant)
                (review.high_eyeball if eyeball_table else review.high).add(key)
            elif match and section == 'renumber':
                pid, event_id, number, rest = match.groups()
                proposed = rest.split('|')[0].strip()
                review.renumber_eyeball.setdefault(int(pid), []).append(
                    (event_id, number, proposed))
            elif section == 'renumber':
                bullet = _REVIEW_BULLET.match(stripped)
                if bullet:
                    pid, event_id, number, proposed = bullet.groups()
                    review.renumber_eyeball.setdefault(int(pid), []).append(
                        (event_id, number, proposed))
    return review


_OTHER_EVENT = re.compile(
    rf'текст совпал с (?P<found>{_EVENT}) №(?P<found_no>{_NUMBER}).*'
    rf'координаты строки ведут в (?P<own>{_EVENT}) №(?P<own_no>{_NUMBER})')


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


def _drop_figure_text(lines, drop_lines):
    """Убрать строки, лежащие внутри вырезанного рисунка (подписи осей,
    подписи к рисунку): их текст есть на картинке.

    Строка — подпись, если совпадает с подписью без учёта пробелов или
    целиком состоит из её слов. Короткая (до 5 знаков: «1», «45,»)
    убирается, только если соседняя непустая строка — тоже подпись:
    одиночная цифра в тексте может быть номером пункта.
    """
    if not drop_lines:
        return lines
    keys = {re.sub(r'\s+', '', s) for s in drop_lines}
    tokens = {t for s in drop_lines for t in s.split()}

    def is_figure(line):
        key = re.sub(r'\s+', '', line)
        return bool(key) and (key in keys or all(t in tokens for t in line.split()))

    marks = [is_figure(line) for line in lines]
    filled = [i for i, line in enumerate(lines) if line.strip()]
    keep = []
    for pos, i in enumerate(filled):
        if not marks[i]:
            continue
        if len(re.sub(r'\s+', '', lines[i])) >= 6:
            continue
        neighbours = [filled[j] for j in (pos - 1, pos + 1) if 0 <= j < len(filled)]
        if not any(marks[j] for j in neighbours):
            keep.append(i)
    for i in keep:
        marks[i] = False
    return [line for line, mark in zip(lines, marks) if not mark]


def split_combined(lines):
    """Условие и решение в ОДНОМ PDF: всё с «Возможные варианты ответов» /
    «Ответ» / «Решение» уходит в решение."""
    for i, line in enumerate(lines):
        if i and _ANSWER_START.match(line.strip()):
            return lines[:i], lines[i:]
    return lines, []


def clean_pdf_task(raw_text, solution_text, combined=False, drop_lines=()):
    """Текст задания из PDF → (название, баллы, условие, решение) в markdown.

    Только детерминированные правки формы: колонтитулы, шапка, подписи
    вырезанного рисунка (`drop_lines`), переносы строк, курсивные буквы,
    экранирование. Слова не меняются.
    """
    lines = _plain_math_letters(raw_text or '').splitlines()
    lines = _drop_colontitles(lines)
    lines = _drop_figure_text(lines, [_plain_math_letters(s) for s in drop_lines])
    title, points, lines = parse_header(lines)
    extra_solution = []
    if combined:
        lines, extra_solution = split_combined(lines)
    statement = '\n'.join(_escape_markdown(_unwrap(lines)))
    sol_lines = extra_solution + [''] + _drop_colontitles(
        _plain_math_letters(solution_text or '').splitlines())
    solution = '\n'.join(_escape_markdown(_unwrap(sol_lines))).strip()
    return title, points, statement.strip(), solution
