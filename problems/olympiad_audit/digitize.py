# -*- coding: utf-8 -*-
"""Оцифровка официальных PDF олимпиады: инвентарь файлов и отрисовка страниц.

Помощники команды `olympiad_digitize` (подкоманды `inventory`, `render`).
В базу ничего не пишут и модель не зовут: читают папку `raw\\` аудита
(`weconomics-data\\olympiads\\<audit_dir>`) и пишут только в её
`digitized\\`.

Инвентарь — по строке на КАЖДЫЙ файл `raw\\` (html, json и телеграм тоже):
что это за файл (`kind`), к каким комплектам относится (`event_ids`), есть
ли текстовый слой, идёт ли он в оцифровку моделью (`digitize`) и если нет —
почему (`exclude_reason`). Сумма по категориям равна числу файлов: файл не
теряется молча.

Откуда берётся `kind` и `event_ids` — по убыванию силы:
  1) `reference_events.jsonl` аудита: у МОШ — `task_files`/`solution_files`
     по имени файла; у ВП файлов в эталоне нет, связь — через
     `raw\\fetch_log.jsonl` (файл → URL, URL ∈ `source_urls` комплекта,
     вид — поле `kind` журнала);
  2) ручная раскладка `MANUAL_FILES` (файлы сессии 4 и другие редакции
     критериев — разложены по шапкам глазами);
  3) `session1\\download_plan.csv` МОШ (колонка `kind_label`);
  4) имя файла (`tasks-`, `ans-`, `resheniya`, `kriterii`, …);
  5) шапка первой страницы.

⚠️ ПРОТОКОЛЫ И СПИСКИ ПОБЕДИТЕЛЕЙ В МОДЕЛЬ НЕ ОТПРАВЛЯЮТСЯ: это
персональные данные школьников (CLAUDE.md, P0). Ищутся по имени файла и по
заголовку первой страницы. Голое слово «результат» или «победитель» здесь
не годится: оно есть в половине условий («…результаты фирмы», «победитель
аукциона»), и такой фильтр выкинул бы задания.

⚠️ ДУБЛИ — ПО sha256, НЕ ПО ИМЕНИ. У МОШ файлы `raw\\news_files` и
`raw\\probe` во многом побайтно совпадают с `raw\\pdf`; у ВП два файла
SolveHub — копии «заданий». Дубль остаётся в инвентаре, но не рисуется и не
оцифровывается второй раз; его папка страниц — та же, что у первого файла
(`pages/<первые 16 знаков sha256>`: по хэшу, а не по имени — длинные имена
на Windows упираются в 260 знаков пути).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import struct
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

#: Документ «со слоем», если на страницах в сумме больше стольких знаков.
TEXT_LAYER_MIN_CHARS = 200
#: Страница «со слоем», если на ней хотя бы столько знаков (номер страницы
#: на скане — не слой).
PAGE_TEXT_MIN_CHARS = 20
RENDER_DPI = 200
#: Длинная сторона PNG не больше этого (ограничение входа модели).
MAX_SIDE_PX = 4000

KINDS = ('tasks', 'solutions', 'criteria', 'mixed', 'other')

DOC_PDF, DOC_DOCX, DOC_ZIP = 'pdf', 'docx', 'zip'

# ── Причины исключения из оцифровки ──────────────────────────────────────

REASON_NOT_DOC = 'не документ'
REASON_OTHER_OLYMPIAD_MOSH = 'другая олимпиада (fingram/entr)'
REASON_OTHER_OLYMPIAD = 'другая олимпиада'
REASON_PERSONAL = 'протокол/список (персональные данные)'
REASON_DOCX = 'docx — текст напрямую'
REASON_NOT_TASKS = 'не задания (расписание и прочее)'


def reason_duplicate(first):
    return f'дубль {first}'


def reason_text_duplicate(first):
    return f'дубль по тексту {first}'


# ── Настройки ────────────────────────────────────────────────────────────

def default_data_root(base_dir, environ=None):
    """Корень данных олимпиад: `OLYMPIAD_DATA_ROOT` или соседняя папка."""
    environ = os.environ if environ is None else environ
    value = environ.get('OLYMPIAD_DATA_ROOT')
    if value:
        return Path(value)
    return Path(base_dir).resolve().parent / 'weconomics-data' / 'olympiads'


def page_dir_for(sha256):
    return f'pages/{sha256[:16]}'


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with open(tmp, 'w', encoding='utf-8', newline='\n') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    os.replace(tmp, path)


# ── Ручная раскладка (проверено по шапкам PDF) ───────────────────────────

_SH = 'raw/pdf/api.solvehub.app__uploads__files__file-2024-10-07-'
_SH_NOTE = ('зеркало SolveHub, не сайт организатора; раскладка — по шапке '
            'PDF и подписи в raw/fetch_log.jsonl (сессия 4)')


def _vp_new(year, grade, variant, notes=()):
    return {'year': year, 'academic_year': f'{year - 1}/{year}',
            'stage': 'final', 'grade': grade, 'variant': variant,
            'official': False, 'source': 'solvehub-mirror',
            'source_urls': [f'https://solvehub.app/econ/olymp/vp/final/{year}'],
            'notes': [_SH_NOTE, *notes]}


_NO_GRADE = ('класс в шапке не указан (grade пустой, в event_id — '
             '«unknown», как у vp-2009-final-unknown-v1)')
_INTERNET = ('шапка: «Интернет-олимпиада по экономике»; на SolveHub лежит в '
             'final/<год>, этап по шапке не доказан — проверить')

#: Новые комплекты, которых нет в reference_events.jsonl (ВП: ранние годы
#: 2006/07–2010/11 только с зеркала SolveHub). event_id → описание.
NEW_EVENTS = {
    'vp': {
        **{f'vp-2007-final-11-v{v}': _vp_new(
            2007, '11', f'v{v}',
            ['«Обществознание „Экономическая сфера“», тест на 45 заданий'])
           for v in (5, 6, 7, 8)},
        **{f'vp-2008-final-11-t1v{v}': _vp_new(
            2008, '11', f't1v{v}',
            ['1 тур, вариант в шапке («Т 169 … Олимпиада 2008, задания '
             'А21–А40»); вариант и тур — в хвосте event_id'])
           for v in (5, 6, 7, 8)},
        'vp-2008-final-11-t2': _vp_new(2008, '11', 't2', ['2 тур']),
        'vp-2009-final-unknown-internet': _vp_new(
            2009, '', 'internet', [_INTERNET, _NO_GRADE,
                                   'файл «решений» SolveHub — побайтная '
                                   'копия заданий, решений нет']),
        **{f'vp-2009-final-unknown-var{v}': _vp_new(
            2009, '', f'var{v}',
            [f'скан, шапка «Экономика. Вариант {v} … Олимпиада 2009»',
             _NO_GRADE,
             'хвост var<N>, а не v<N>: vp-2009-final-unknown-v1 в эталоне — '
             'заглушка «материалов нет», с вариантом 1 её не смешиваем'])
           for v in range(1, 7)},
        'vp-2010-final-unknown-internet': _vp_new(
            2010, '', 'internet', [_INTERNET, _NO_GRADE]),
        'vp-2010-final-11-t2': _vp_new(
            2010, '11', 't2',
            ['задания: «Обществознание, профили „Экономика“, „Статистика“» '
             '(класс не указан); решения: «Обществознание (экономика), '
             '11 класс. 2 тур» — те же задачи']),
        'vp-2010-final-unknown-worldecon-v1': _vp_new(
            2010, '', 'worldecon-v1',
            ['«Обществознание, профиль „Мировая экономика“, вариант №1»',
             _NO_GRADE,
             'файл «решений» SolveHub — побайтная копия заданий']),
        **{f'vp-2011-final-{g}-v1': _vp_new(
            2011, g, 'v1',
            ['«Межрегиональная многопрофильная олимпиада НИУ-ВШЭ 2011»'])
           for g in ('9', '10', '11')},
    },
    'mosh': {},
}

#: Файл → вид и комплекты. Только для файлов, которых нет в эталоне.
MANUAL_FILES = {
    'vp': {
        _SH + '20-55-09-08132.pdf': ('tasks', ['vp-2007-final-11-v5']),
        _SH + '20-55-21-80688.pdf': ('tasks', ['vp-2007-final-11-v6']),
        _SH + '20-55-28-19750.pdf': ('tasks', ['vp-2007-final-11-v7']),
        _SH + '20-55-35-34605.pdf': ('tasks', ['vp-2007-final-11-v8']),
        _SH + '20-51-48-96069.pdf': ('tasks', ['vp-2008-final-11-t1v5']),
        _SH + '20-51-54-49623.pdf': ('tasks', ['vp-2008-final-11-t1v6']),
        _SH + '20-52-01-50694.pdf': ('tasks', ['vp-2008-final-11-t1v7']),
        _SH + '20-52-06-51431.pdf': ('tasks', ['vp-2008-final-11-t1v8']),
        _SH + '20-52-58-23868.pdf': ('tasks', ['vp-2008-final-11-t2']),
        _SH + '20-53-04-46210.pdf': ('solutions', ['vp-2008-final-11-t2']),
        _SH + '20-42-38-88685.pdf': ('tasks', ['vp-2009-final-unknown-internet']),
        _SH + '20-42-48-75124.pdf': ('tasks', ['vp-2009-final-unknown-internet']),
        _SH + '20-43-28-44726.pdf': ('tasks', ['vp-2009-final-unknown-var1']),
        _SH + '20-43-45-01698.pdf': ('tasks', ['vp-2009-final-unknown-var2']),
        _SH + '20-43-52-38854.pdf': ('tasks', ['vp-2009-final-unknown-var3']),
        _SH + '20-43-59-55248.pdf': ('tasks', ['vp-2009-final-unknown-var4']),
        _SH + '20-44-08-96118.pdf': ('tasks', ['vp-2009-final-unknown-var5']),
        _SH + '20-44-15-24285.pdf': ('tasks', ['vp-2009-final-unknown-var6']),
        _SH + '20-31-23-18666.pdf': ('tasks', ['vp-2010-final-unknown-internet']),
        _SH + '20-31-30-20007.pdf': ('solutions', ['vp-2010-final-unknown-internet']),
        _SH + '20-31-41-63844.pdf': ('solutions', ['vp-2010-final-unknown-internet']),
        _SH + '20-32-05-81598.pdf': ('tasks', ['vp-2010-final-11-t2']),
        _SH + '20-32-20-17501.pdf': ('solutions', ['vp-2010-final-11-t2']),
        _SH + '20-32-43-86205.pdf': ('tasks', ['vp-2010-final-unknown-worldecon-v1']),
        _SH + '20-32-50-49209.pdf': ('tasks', ['vp-2010-final-unknown-worldecon-v1']),
        _SH + '20-06-51-23352.pdf': ('tasks', ['vp-2011-final-11-v1']),
        _SH + '20-07-09-17642.pdf': ('solutions', ['vp-2011-final-11-v1']),
        _SH + '20-06-29-95263.pdf': ('tasks', ['vp-2011-final-10-v1']),
        _SH + '20-06-38-80208.pdf': ('solutions', ['vp-2011-final-10-v1']),
        _SH + '20-05-21-49950.pdf': ('tasks', ['vp-2011-final-9-v1']),
        _SH + '20-05-27-08165.pdf': ('solutions', ['vp-2011-final-9-v1']),
    },
    'mosh': {
        # Сессия 4: решения и критерии финала 2017/18 (условий внутри нет).
        **{f'raw/pdf/mosecon.olimpiada.ru__upload__files__MOSH-2018-{g}'
           '_resheniya_i_kriterii.pdf': ('solutions', [f'mosh-2018-final-{g}-v1'])
           for g in (8, 9, 10, 11)},
        ('raw/pdf/mos.olimpiada.ru__upload__files__Archive_tasks_2013-...__'
         '2013-14__econ__tasks-econ-11-otbor-13-4.pdf'):
            ('tasks', ['mosh-2014-qualifying-11-v1']),
        ('raw/pdf/mos.olimpiada.ru__upload__files__Archive_tasks_2013-...__'
         '2013-14__econ__tasks-econ-11-final-13-4.pdf'):
            ('tasks', ['mosh-2014-final-11-v1']),
        # Другие редакции критериев со страниц новостей (news/363, news/235):
        # с файлами mos.olimpiada.ru побайтно не совпали.
        ('raw/news_files/mosecon.olimpiada.ru__upload__files__2025-2026__8-11__'
         'Kriterii_8-y_klass_2026.pdf'): ('criteria', ['mosh-2026-final-8-v1']),
        ('raw/news_files/mosecon.olimpiada.ru__upload__files__2025-2026__8-11__'
         'Kriterii_10-y_klass_2026.pdf'): ('criteria', ['mosh-2026-final-10-v1']),
        ('raw/news_files/mosecon.olimpiada.ru__upload__files__Tasks__Utochnёnnyie__'
         'podrobnyie__kriterii_proverki_zadachi_10_2__i_11_2.pdf'):
            ('criteria', ['mosh-2021-final-10-v1', 'mosh-2021-final-11-v1']),
        # Проба сессии 1: другая редакция критериев 9 кл. финала 2025/26
        # (с sol-econ-9-final-25-26 сходство текста 0,89, побайтно нет).
        ('raw/probe/mosecon.olimpiada.ru__upload__files__2025-2026__8-11__'
         'Kriterii_9-y_klass_2026.pdf'): ('criteria', ['mosh-2026-final-9-v1']),
    },
}


# ── Классификация по имени и по тексту ───────────────────────────────────

_RE_MIXED = re.compile(
    r'tasks?_and_solutions|s_kriteriyami|задани\w*_и_решени', re.I)
_RE_SOLUTIONS = re.compile(
    r'(?:^|[^a-z])(?:ans|sol|otvet\w*|resh\w*|solutions?|klyuchi)(?:[^a-z]|$)'
    r'|решени|ответ|ключи', re.I)
_RE_CRITERIA = re.compile(r'krit|критери', re.I)
_RE_TASKS = re.compile(
    r'(?:^|[^a-z])(?:tasks?|zadaniya|zadanie|variant)(?:[^a-z]|$)|задани|вариант',
    re.I)
_RE_SCHEDULE = re.compile(r'schedule|raspisanie|расписани', re.I)


def kind_from_name(name):
    """Вид файла по имени (или по последнему сегменту URL); '' — не ясно."""
    name = name.lower()
    if _RE_MIXED.search(name):
        return 'mixed'
    has_tasks = bool(_RE_TASKS.search(name))
    if _RE_SOLUTIONS.search(name):
        return 'mixed' if has_tasks else 'solutions'
    if _RE_CRITERIA.search(name):
        return 'mixed' if has_tasks else 'criteria'
    if has_tasks:
        return 'tasks'
    if _RE_SCHEDULE.search(name):
        return 'other'
    return ''


_RE_HEAD_CRITERIA = re.compile(r'критерии\s+(?:оценивания|проверки|оценки)', re.I)
_RE_HEAD_SOLUTIONS = re.compile(
    r'\b(?:решения|ответы|ключи)\b|возможное решение|правильный ответ', re.I)
_RE_HEAD_TASKS = re.compile(
    r'время\s+(?:выполнения|написания)|вариант|задача\s*1|задание\s*1', re.I)


def kind_from_text(text):
    """Вид по шапке первой страницы — последнее средство."""
    head = (text or '')[:1500]
    if _RE_HEAD_CRITERIA.search(head):
        return 'criteria'
    if _RE_HEAD_SOLUTIONS.search(head):
        return 'solutions'
    if _RE_HEAD_TASKS.search(head):
        return 'tasks'
    return ''


#: Персональные данные: имя файла (транслит и кириллица).
_RE_PERSONAL_NAME = re.compile(
    r'protokol|pobedit|prizer|prizyor|spisok|spiski|rezultat|reyting|reiting'
    r'|registr|prikaz|протокол|победит|призёр|призер|списо?к|результат'
    r'|рейтинг|регистрац|приказ', re.I)
#: Персональные данные: заголовок первой страницы. Только устойчивые
#: обороты — голое «результат» есть в условиях задач.
_RE_PERSONAL_HEAD = re.compile(
    r'протокол\w*\s+(?:результат|проверк|жюри|апелляц|олимпиад)'
    r'|спис\w*\s+(?:победител|призёр|призер|участник)'
    r'|победител\w*\s+и\s+призёр|победител\w*\s+и\s+призер'
    r'|рейтинг\w*\s+участник|итогов\w+\s+результат'
    r'|результат\w*\s+(?:участник|олимпиад|этап)\w*\s*(?:\n|$)'
    r'|\bприказ\b'
    r'|\bФИО\b[^\n]{0,40}\n?[^\n]{0,40}(?:балл|место|школа|класс)',
    re.I)


def personal_data_hit(name, first_page_text):
    """Причина-находка, если файл похож на протокол/список; иначе ''."""
    match = _RE_PERSONAL_NAME.search(name)
    if match:
        return f'имя: {match.group(0)}'
    match = _RE_PERSONAL_HEAD.search((first_page_text or '')[:3000])
    if match:
        return f'первая страница: {" ".join(match.group(0).split())}'
    return ''


_RE_OTHER_MOSH = re.compile(r'(?:^|[_\-./])(?:fg|fingram|entr)(?:[_\-./]|$)', re.I)
_RE_OTHER_VP = re.compile(
    r'(?:^|[_\-./])(?:s2_business|s2_finance|business|finance|fingram|fg)'
    r'(?:[_\-./]|$)', re.I)


def other_olympiad_reason(slug, rel):
    """Файл другой олимпиады/предмета: причина или ''."""
    name = rel.rsplit('/', 1)[-1]
    if slug == 'mosh' and _RE_OTHER_MOSH.search(name):
        return REASON_OTHER_OLYMPIAD_MOSH
    if slug.startswith('vp') and _RE_OTHER_VP.search(name):
        return REASON_OTHER_OLYMPIAD
    return ''


def merge_kinds(kinds):
    """Несколько видов одного файла → один ('tasks' + решения → 'mixed')."""
    kinds = {k for k in kinds if k}
    if not kinds:
        return ''
    if len(kinds) == 1:
        return next(iter(kinds))
    if 'mixed' in kinds or 'tasks' in kinds:
        return 'mixed'
    if kinds == {'solutions', 'criteria'}:
        return 'solutions'
    return sorted(kinds)[0]


def doc_type(path):
    """pdf / docx / zip по сигнатуре (а не по расширению); '' — не документ."""
    try:
        with open(path, 'rb') as handle:
            head = handle.read(8)
    except OSError:
        return ''
    ext = Path(path).suffix.lower()
    if head.startswith(b'%PDF'):
        return DOC_PDF
    if head.startswith(b'PK'):
        if ext == '.docx':
            return DOC_DOCX
        if ext == '.zip':
            return DOC_ZIP
    return ''


def source_of(rel):
    name = rel.rsplit('/', 1)[-1]
    if name.startswith('api.solvehub.app__'):
        return 'solvehub-mirror'
    if rel.startswith('raw/probe/'):
        return 'probe'
    return 'official'


# ── Эталон и журналы аудита ──────────────────────────────────────────────

_KIND_FROM_LOG = {'tasks': 'tasks', 'solutions': 'solutions',
                  'tasks_and_solutions': 'mixed', 'criteria': 'criteria'}
def _log_kind(entry):
    """Вид по полю `kind` журнала загрузки ВП (`schedule_*` — прочее)."""
    kind = entry.get('kind') or ''
    if kind.startswith('schedule'):
        return 'other'
    return _KIND_FROM_LOG.get(kind, '')


_KIND_FROM_PLAN = {'задания': 'tasks', 'задания (варианты)': 'tasks',
                   'решения': 'solutions', 'критерии': 'criteria'}


def _fetch_log(audit_dir):
    """URL ↔ файл по `raw/fetch_log.jsonl` (оба формата журнала)."""
    path = Path(audit_dir) / 'raw' / 'fetch_log.jsonl'
    by_rel, by_url = {}, {}
    if not path.is_file():
        return by_rel, by_url
    for entry in read_jsonl(path):
        rel = entry.get('path') or (
            f'raw/pdf/{entry["file"]}' if entry.get('file') else '')
        url = entry.get('url') or ''
        if not rel:
            continue
        rel = rel.replace('\\', '/')
        by_rel.setdefault(rel, entry)
        if url:
            by_url.setdefault(url, rel)
            if entry.get('final_url'):
                by_url.setdefault(entry['final_url'], rel)
    return by_rel, by_url


def load_reference(audit_dir):
    """Файл (путь от папки аудита) → {'kinds': set, 'event_ids': set}.

    МОШ: `task_files`/`solution_files` эталона (имя файла в raw/pdf).
    ВП: файлов в эталоне нет — URL файла из журнала загрузки ищется в
    `source_urls` комплектов, вид — из поля `kind` журнала.
    """
    audit_dir = Path(audit_dir)
    path = audit_dir / 'reference_events.jsonl'
    out = defaultdict(lambda: {'kinds': set(), 'event_ids': set()})
    if not path.is_file():
        return {}, set()
    events = read_jsonl(path)
    event_ids = {e['event_id'] for e in events}
    by_rel, _ = _fetch_log(audit_dir)
    url_events = defaultdict(set)
    for event in events:
        for key, kind in (('task_files', 'tasks'), ('solution_files', 'solutions'),
                          ('criteria_files', 'criteria')):
            for item in event.get(key) or []:
                name = item['file'] if isinstance(item, dict) else item
                rel = f'raw/pdf/{name}'
                out[rel]['kinds'].add(kind)
                out[rel]['event_ids'].add(event['event_id'])
        for url in event.get('source_urls') or []:
            url_events[url].add(event['event_id'])
    for rel, entry in by_rel.items():
        kind = _log_kind(entry)
        events_for = url_events.get(entry.get('url') or '')
        if kind and events_for and rel not in out:
            out[rel]['kinds'].add(kind)
            out[rel]['event_ids'].update(events_for)
    return dict(out), event_ids


def load_download_plan(audit_dir):
    """URL и имя файла → вид по `session1/download_plan.csv` (МОШ)."""
    path = Path(audit_dir) / 'session1' / 'download_plan.csv'
    by_url, by_name = {}, {}
    if not path.is_file():
        return by_url, by_name
    with open(path, encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            kind = _KIND_FROM_PLAN.get((row.get('kind_label') or '').strip())
            if not kind:
                continue
            for url in [row.get('url') or '',
                        *(row.get('alt_urls') or '').split()]:
                if url:
                    by_url.setdefault(url, kind)
            if row.get('basename'):
                by_name.setdefault(row['basename'], kind)
    return by_url, by_name


def load_text_duplicates(audit_dir):
    """Файл новости → файл mos с тем же текстом (`news_vs_mos.csv`, МОШ)."""
    path = Path(audit_dir) / 'session1' / 'news_vs_mos.csv'
    out = {}
    if not path.is_file():
        return out
    _, by_url = _fetch_log(audit_dir)
    with open(path, encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            if row.get('verdict') != 'тот же текст':
                continue
            news = by_url.get(row.get('news_url') or '')
            mos = by_url.get(row.get('best_text_match') or '')
            if news and mos:
                out[news] = mos
    return out


# ── Чтение документов ────────────────────────────────────────────────────

def pdf_stats(path):
    """Страниц, знаков слоя, страниц со слоем, текст первой страницы."""
    import fitz
    with fitz.open(path) as doc:
        chars, with_text, first = 0, 0, ''
        for index, page in enumerate(doc):
            text = page.get_text()
            if index == 0:
                first = text
            n = len(text.strip())
            chars += n
            if n >= PAGE_TEXT_MIN_CHARS:
                with_text += 1
        return {'pages': doc.page_count, 'text_chars': chars,
                'pages_with_text': with_text,
                'text_layer': chars > TEXT_LAYER_MIN_CHARS}, first


def _md_cell(text):
    return ' '.join(text.split()).replace('|', '\\|')


def _local(element):
    return element.tag.rsplit('}', 1)[-1] if isinstance(element.tag, str) else ''


def _omml(element):
    """Формула Word (OMML) → LaTeX-подобный текст: индексы, степени, корни,
    дроби, скобки; прочее — подряд. python-docx формулы молча теряет
    (у МОШ 2017/18 так пропали бы функции спроса в 9 docx)."""
    name = _local(element)
    parts = {(_local(c)): c for c in element}

    def sub(key):
        return _omml(parts[key]) if key in parts else ''
    if name == 't':
        return element.text or ''
    if name == 'sSub':
        return f'{sub("e")}_{{{sub("sub")}}}'
    if name == 'sSup':
        return f'{sub("e")}^{{{sub("sup")}}}'
    if name == 'sSubSup':
        return f'{sub("e")}_{{{sub("sub")}}}^{{{sub("sup")}}}'
    if name == 'f':
        return f'\\frac{{{sub("num")}}}{{{sub("den")}}}'
    if name == 'rad':
        deg = sub('deg')
        return (f'\\sqrt[{deg}]{{{sub("e")}}}' if deg
                else f'\\sqrt{{{sub("e")}}}')
    if name == 'd':
        return '(' + ', '.join(_omml(c) for c in element if _local(c) == 'e') + ')'
    if name.endswith('Pr'):
        return ''
    return ''.join(_omml(c) for c in element)


def _run_text(element):
    """Текст абзаца или ячейки по порядку: обычные прогоны и формулы ($…$)."""
    name = _local(element)
    if name in ('oMath', 'oMathPara'):
        return f'${_omml(element)}$'
    if name == 't':
        return element.text or ''
    if name == 'tab':
        return '\t'
    if name in ('br', 'cr'):
        return '\n'
    if name in ('rPr', 'pPr', 'instrText', 'delText'):
        return ''
    return ''.join(_run_text(c) for c in element)


def _cell_text(cell_element):
    return '\n'.join(_run_text(p) for p in cell_element.iter()
                     if _local(p) == 'p' and _local(p.getparent()) == 'tc')


def docx_to_markdown(path):
    """Текст docx по порядку: абзацы и таблицы (таблицы — Markdown),
    формулы Word — $…$."""
    import docx
    from docx.table import Table

    document = docx.Document(path)
    lines = []
    for child in document.element.body.iterchildren():
        tag = _local(child)
        if tag == 'p':
            lines.append(_run_text(child))
        elif tag == 'tbl':
            table = Table(child, document)
            rows = [[_md_cell(_cell_text(cell._tc)) for cell in row.cells]
                    for row in table.rows]
            if not rows:
                continue
            width = max(len(r) for r in rows)
            rows = [r + [''] * (width - len(r)) for r in rows]
            lines.append('')
            lines.append('| ' + ' | '.join(rows[0]) + ' |')
            lines.append('|' + ' --- |' * width)
            lines.extend('| ' + ' | '.join(r) + ' |' for r in rows[1:])
            lines.append('')
    text = '\n'.join(lines).strip() + '\n'
    images = []
    for rel in document.part.rels.values():
        if 'image' in rel.reltype and not rel.is_external:
            part = rel.target_part
            ext = Path(str(part.partname)).suffix.lstrip('.') or 'bin'
            images.append((ext, part.blob))
    return text, images


def extract_docx(path, out_dir, sha16):
    """docx → `<sha16>.md` и картинки `<sha16>_img<k>.<ext>`."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    text, images = docx_to_markdown(path)
    (out_dir / f'{sha16}.md').write_text(text, encoding='utf-8')
    for k, (ext, blob) in enumerate(images, start=1):
        (out_dir / f'{sha16}_img{k}.{ext}').write_bytes(blob)
    return len(text.strip()), len(images)


# ── Инвентарь ────────────────────────────────────────────────────────────

def _walk_raw(audit_dir):
    """Файлы raw/ в порядке «сначала raw/pdf, потом корень, потом прочее»:
    первым экземпляром дубля становится файл из raw/pdf."""
    raw = Path(audit_dir) / 'raw'
    files = [p for p in raw.rglob('*') if p.is_file()]

    def order(p):
        rel = p.relative_to(raw).as_posix()
        top = rel.split('/', 1)[0] if '/' in rel else ''
        rank = 0 if top == 'pdf' else (1 if top == '' else 2)
        return rank, rel
    return sorted(files, key=order)


def _expand_zip(path, rel, digitized, sha):
    """Распаковать zip в digitized/zip/<sha16>/ → [(путь, file-ключ)]."""
    target = Path(digitized) / 'zip' / sha[:16]
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    out = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            inner = Path(info.filename)
            if inner.is_absolute() or '..' in inner.parts:
                continue
            dest = target / inner
            dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, open(dest, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            out.append((dest, f'zip:{rel}!{info.filename}'))
    return out


def build_inventory(slug, audit_dir, log=None):
    """Строки инвентаря по всем файлам raw/ (см. шапку модуля)."""
    audit_dir = Path(audit_dir)
    digitized = audit_dir / 'digitized'
    reference, _ = load_reference(audit_dir)
    log_by_rel, _ = _fetch_log(audit_dir)
    plan_by_url, plan_by_name = load_download_plan(audit_dir)
    text_dups = load_text_duplicates(audit_dir)
    manual = MANUAL_FILES.get(slug, {})

    queue = [(p, p.relative_to(audit_dir).as_posix()) for p in _walk_raw(audit_dir)]
    rows, first_by_sha = [], {}
    while queue:
        path, rel = queue.pop(0)
        sha = sha256_file(path)
        ext = path.suffix.lower().lstrip('.')
        dtype = doc_type(path)
        row = {'file': rel, 'sha256': sha, 'size': path.stat().st_size,
               'ext': ext, 'kind': 'other', 'kind_source': '',
               'event_ids': [], 'digitize': False, 'exclude_reason': '',
               'duplicate_of': '', 'page_dir': '', 'source': source_of(rel)}
        if rel.startswith('raw/news_files/'):
            row['edition'] = 'news'
        rows.append(row)

        if dtype == DOC_ZIP:
            row['exclude_reason'] = 'архив — вложенные файлы отдельными строками'
            row['kind_source'] = 'zip'
            queue[0:0] = _expand_zip(path, rel, digitized, sha)
            continue
        if not dtype:
            row['exclude_reason'] = REASON_NOT_DOC
            row['kind_source'] = 'none'
            continue

        first_text = ''
        if dtype == DOC_PDF:
            row['page_dir'] = page_dir_for(sha)
            try:
                stats, first_text = pdf_stats(path)
                row.update(stats)
            except Exception as exc:  # битый PDF — строка остаётся
                row['exclude_reason'] = f'{REASON_NOT_DOC} (PDF не читается: {exc})'
                continue
        else:  # docx
            sha16 = sha[:16]
            chars, images = extract_docx(path, digitized / 'docx', sha16)
            row['docx_text_chars'] = chars
            row['docx_images'] = images
            row['docx_md'] = f'digitized/docx/{sha16}.md'
            first_text = (digitized / 'docx' / f'{sha16}.md').read_text(
                encoding='utf-8')[:3000]
        if rel.startswith('zip:'):
            row['extracted_to'] = path.relative_to(audit_dir).as_posix()

        _classify(row, rel, first_text, reference, manual, log_by_rel,
                  plan_by_url, plan_by_name)

        first = first_by_sha.get(sha)
        name = rel.rsplit('/', 1)[-1]
        other = other_olympiad_reason(slug, rel)
        personal = personal_data_hit(name, first_text)
        if other:
            row['exclude_reason'] = other
        elif personal:
            row['exclude_reason'] = REASON_PERSONAL
            row['personal_data_hit'] = personal
        elif first is not None:
            _merge_duplicate(row, first)
            row['duplicate_of'] = first['file']
            row['exclude_reason'] = reason_duplicate(first['file'])
            row['kind'] = first['kind']
            row['kind_source'] = f'duplicate:{first["kind_source"]}'
            row['event_ids'] = list(first['event_ids'])
        elif rel in text_dups:
            twin = next((r for r in rows if r['file'] == text_dups[rel]), None)
            row['text_duplicate_of'] = text_dups[rel]
            row['exclude_reason'] = reason_text_duplicate(text_dups[rel])
            if twin and twin['event_ids']:
                row['kind'] = twin['kind']
                row['event_ids'] = list(twin['event_ids'])
                row['kind_source'] = f'text_duplicate:{twin["kind_source"]}'
        elif row['kind'] == 'other':
            row['exclude_reason'] = REASON_NOT_TASKS
        elif dtype == DOC_DOCX:
            row['exclude_reason'] = REASON_DOCX
        else:
            row['digitize'] = True
        if first is None:
            first_by_sha[sha] = row
        if log:
            log(row)
    return rows


def _merge_duplicate(row, first):
    """Дубль по sha256: что делать с его собственной раскладкой.

    Вид тот же — один файл на несколько комплектов (у МОШ 2019/20 решения
    5, 6 и 7 кл. — один PDF): комплекты дубля дописываются первому файлу.
    Вид другой по эталону — организатор выложил не тот файл (у МОШ 2016/17
    «задания финала 10–11» — побайтная копия ответов отборочного): верна
    раскладка по содержимому, т. е. первого файла, а расхождение
    записывается в `duplicate_conflict` для отчёта.
    """
    own_kind, own_events = row['kind'], list(row['event_ids'])
    if not own_events:
        return
    if own_kind == first['kind']:
        first['event_ids'] = sorted(set(first['event_ids']) | set(own_events))
    elif row['kind_source'] in ('reference_events', 'manual'):
        row['duplicate_conflict'] = (
            f'по эталону {own_kind} {", ".join(own_events)}; по содержимому — '
            f'копия {first["file"]} ({first["kind"]})')
        row['own_event_ids'] = own_events


def _classify(row, rel, first_text, reference, manual, log_by_rel,
              plan_by_url, plan_by_name):
    ref = reference.get(rel)
    if ref:
        row['kind'] = merge_kinds(ref['kinds']) or 'other'
        row['event_ids'] = sorted(ref['event_ids'])
        row['kind_source'] = 'reference_events'
        return
    if rel in manual:
        kind, event_ids = manual[rel]
        row['kind'], row['event_ids'] = kind, list(event_ids)
        row['kind_source'] = 'manual'
        return
    entry = log_by_rel.get(rel) or {}
    url = entry.get('url') or ''
    url_name = url.rstrip('/').rsplit('/', 1)[-1] if url else ''
    kind = plan_by_url.get(url) or plan_by_name.get(url_name)
    if kind:
        row['kind'], row['kind_source'] = kind, 'download_plan'
        return
    log_kind = _log_kind(entry)
    if log_kind:
        row['kind'], row['kind_source'] = log_kind, 'fetch_log'
        return
    name_kind = (kind_from_name(url_name)
                 or kind_from_name(rel.rsplit('/', 1)[-1]))
    if name_kind:
        row['kind'], row['kind_source'] = name_kind, 'name'
        return
    text_kind = kind_from_text(first_text)
    if text_kind:
        row['kind'], row['kind_source'] = text_kind, 'first_page'
        return
    row['kind'], row['kind_source'] = 'other', 'none'


# ── Комплекты → файлы ────────────────────────────────────────────────────

_LIST_FOR_KIND = {'tasks': ('task_files',), 'solutions': ('solution_files',),
                  'criteria': ('criteria_files',),
                  'mixed': ('task_files', 'solution_files')}


def build_events_files(slug, audit_dir, rows):
    """По комплекту — файлы к оцифровке (digitize=true или docx)."""
    _, known = load_reference(audit_dir)
    new_defs = NEW_EVENTS.get(slug, {})
    events = {}
    for row in rows:
        usable = row['digitize'] or row['exclude_reason'] == REASON_DOCX
        if not usable:
            continue
        for event_id in row['event_ids']:
            event = events.setdefault(event_id, {
                'event_id': event_id, 'new': event_id not in known,
                'task_files': [], 'solution_files': [], 'criteria_files': []})
            if event['new'] and event_id in new_defs:
                for key, value in new_defs[event_id].items():
                    event.setdefault(key, value)
            item = {'file': row['file'], 'sha256': row['sha256'],
                    'kind': row['kind'], 'source': row['source']}
            for key in ('page_dir', 'pages', 'text_layer', 'edition', 'docx_md'):
                if row.get(key) not in (None, ''):
                    item[key] = row[key]
            for key in _LIST_FOR_KIND.get(row['kind'], ()):
                event[key].append(item)
    return [events[k] for k in sorted(events, key=_event_sort_key)]


def _event_sort_key(event_id):
    parts = event_id.split('-')
    year = next((int(p) for p in parts if p.isdigit() and len(p) == 4), 0)
    return year, event_id


def event_year_stage(event_id):
    """('2014', 'final') из `mosh-2014-final-11-v1`; ('', '') — не разобрать."""
    match = re.match(r'^[a-z]+-(\d{4})-([a-z]+)-', event_id)
    return (match.group(1), match.group(2)) if match else ('', '')


# ── Сводка ───────────────────────────────────────────────────────────────

def summarize(rows):
    """Счётчики для контроля: сумма по категориям = число файлов."""
    by_kind = Counter(r['kind'] for r in rows)
    by_reason = Counter('оцифровка' if r['digitize'] else
                        (r['exclude_reason'].split(' raw/')[0]
                         if r['exclude_reason'].startswith('дубль') else
                         r['exclude_reason'])
                        for r in rows)
    kind_x_digitize = Counter((r['kind'], r['digitize']) for r in rows)
    todo = [r for r in rows if r['digitize']]
    pages = sum(r.get('pages', 0) for r in todo)
    with_layer = sum(r.get('pages_with_text', 0) for r in todo)
    by_year_stage = Counter()
    for r in todo:
        year, stage = event_year_stage(r['event_ids'][0]) if r['event_ids'] else ('', '')
        by_year_stage[(year or '?', stage or '?')] += r.get('pages', 0)
    return {
        'files': len(rows),
        'by_kind': dict(by_kind),
        'by_reason': dict(by_reason),
        'kind_x_digitize': {f'{k}/{"да" if d else "нет"}': n
                            for (k, d), n in sorted(kind_x_digitize.items())},
        'pdf_to_digitize': len(todo),
        'pages_to_digitize': pages,
        'pages_with_layer': with_layer,
        'pages_scan': pages - with_layer,
        'pdf_scans': sum(1 for r in todo if not r.get('text_layer')),
        'pages_by_year_stage': {f'{y} {s}': n
                                for (y, s), n in sorted(by_year_stage.items())},
        'personal_data': [r['file'] for r in rows
                          if r['exclude_reason'] == REASON_PERSONAL],
    }


# ── Отрисовка ────────────────────────────────────────────────────────────

def png_size(path):
    """(ширина, высота) из заголовка PNG, без декодирования."""
    with open(path, 'rb') as handle:
        head = handle.read(24)
    return struct.unpack('>II', head[16:24])


def render_pdf(pdf_path, out_dir, dpi=RENDER_DPI, max_side=MAX_SIDE_PX):
    """PDF → `p<N>.png` + `p<N>.txt`; готовые страницы не перерисовываются.

    Возвращает (строки манифеста без file/page_dir, сколько нарисовано).
    """
    import fitz
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, drawn = [], 0
    with fitz.open(pdf_path) as doc:
        for index, page in enumerate(doc, start=1):
            png = out_dir / f'p{index}.png'
            txt = out_dir / f'p{index}.txt'
            zoom = dpi / 72
            longest = max(page.rect.width, page.rect.height) * zoom
            scaled = longest > max_side + 0.5
            if scaled:
                zoom *= max_side / longest
            if not (png.is_file() and txt.is_file()):
                text = page.get_text()
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                pix.save(png)
                txt.write_text(text, encoding='utf-8')
                drawn += 1
            else:
                text = txt.read_text(encoding='utf-8')
            width, height = png_size(png)
            n = len(text.strip())
            row = {'page': index, 'png': f'p{index}.png', 'width': width,
                   'height': height, 'text_chars': n,
                   'has_layer': n >= PAGE_TEXT_MIN_CHARS}
            if scaled:
                row['scaled_to_max_side'] = max_side
                row['dpi_effective'] = round(zoom * 72, 1)
            rows.append(row)
    return rows, drawn


def render_targets(rows):
    """Строки инвентаря, которые рисуются: digitize=true, не дубль, PDF."""
    return [r for r in rows if r['digitize'] and not r['duplicate_of']
            and r.get('page_dir') and r.get('pages')]


def source_path(audit_dir, row):
    return Path(audit_dir) / (row.get('extracted_to') or row['file'])
