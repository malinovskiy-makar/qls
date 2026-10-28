# -*- coding: utf-8 -*-
"""Стандарт эталонной задачи: проверки S1–S10 над карточкой задачи.

Карточка — словарь одного вида и для задачи банка, и для строки эталона
(собирают `bank.card_of` и `reference.card_of`):

    level          'bank' | 'ref'
    olympiad       слаг (vp, vp-fingram, vp-ob, mosh, mosh-fingram,
                   mosh-entrepreneurship, vseros)
    ref_key        «event_id|number|variant» или None
    problem_id     id задачи банка или None
    event_id, number
    title, statement, solution, answer, criteria   — тексты (markdown + TeX)
    parts          [{label, text, points, answer}] — пункты (у теста пусто)
    test           None | {kind, options: [{label, text, correct}], key, why}
                   kind: single | multi | boolean | short | broken
    max_score      число или None
    figures        [{name, exists, size, opens, rejected, flag, table_ok}]
    figure_markers_missing   хеши маркеров [[FIGURE:…]] без картинки
    figure_orphans           картинки задачи, на которые не ссылается текст
    tables_expected          число таблиц, найденных оцифровкой (эталон)
    layer          None | {text, scan}  — текстовый слой страниц условия
    numbers_ok     признак эталона (True/False/None)
    meta           {season, stage, grade, number, pdf_url, pdf_official}
    reference_suspect        критерии под сомнением (экзамен P4)
    solution_expected        у источника есть страницы решений
    section                  вступление раздела теста (эталон), в S3 не сверяется
    visible        видна ли в каталоге (банк) / None

Каждая проверка возвращает список провалов `{'check', 'code', 'details'}`;
пусто — прошла. Пропуск (нечем проверить) — провал не считается, пишется в
`skipped` (`check_card`). Формулы S4 — пакетом через `katex.check_texts`
(node), поэтому S4 собирается отдельно (`formula_texts` / `s4_from_results`).
"""
from __future__ import annotations

import re
from decimal import Decimal

from problems.olympiad_audit.claude_eyes import numbers
from problems.olympiad_audit.title_rule import (
    TEXT_START_KEEP_BELOW, is_stub, looks_like_text_start,
)

CHECKS = ('S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10')

CHECK_NAMES = {
    'S1': 'условие не пустое, без служебного текста',
    'S2': 'пункты с метками, сумма баллов = максимум',
    'S3': 'числа задачи есть в текстовом слое PDF',
    'S4': 'формулы без ошибок KaTeX',
    'S5': 'рисунки на месте, открываются, не в браке',
    'S6': 'таблицы правильные и текстом',
    'S7': 'у теста варианты и ключ',
    'S8': 'решение и критерии — своей задачи',
    'S9': 'метаданные и заголовок',
    'S10': 'нет дублей внутри события',
}


def fail(check, code, details=''):
    return {'check': check, 'code': code, 'details': details}


# ── S1. Условие и служебный текст ────────────────────────────────────────
#
# Шаблоны — построчно: служебная строка стоит отдельной строкой (шапка,
# колонтитул, номер страницы). Внутри предложения слово «Задания» или
# «олимпиада» — обычный текст условия, его не трогаем.

SERVICE_PATTERNS = (
    ('olympiad_header', re.compile(
        r'^\W*(?:межрегиональная\s+)?(?:олимпиада\s+школьников\s+[«"]?высшая\s+проба|'
        r'московская\s+олимпиада\s+школьников|всероссийская\s+олимпиада\s+школьников|'
        r'(?:[а-яё]+\s+)?этап\s+всероссийской\s+олимпиады)[^\n]{0,120}$',
        re.IGNORECASE | re.MULTILINE)),
    ('continued', re.compile(
        r'(?:продолжение\s+(?:см\.?\s+)?на\s+(?:следующей\s+странице|обороте|следующем\s+листе)|'
        r'см\.?\s+на\s+обороте|переверните\s+лист|\(\s*продолжение\s*\)\s*$)',
        re.IGNORECASE | re.MULTILINE)),
    ('page_number', re.compile(
        # «3/4» отдельной строкой — это вариант теста (дробь), не колонтитул
        r'^\W*(?:страница|стр\.)\s*\d+\s*(?:из\s*\d+)?\W*$|^\s*[-–—]\s*\d{1,2}\s*[-–—]\s*$',
        re.IGNORECASE | re.MULTILINE)),
    ('tasks_heading', re.compile(
        r'^\W*(?:задания|задачи|условия\s+задач)\W*$', re.IGNORECASE | re.MULTILINE)),
    ('authors', re.compile(
        r'^\W*(?:составител[ьи]|автор[ыа]?\s+задач[иа]?|разработчик[и]?|задачи\s+подготовил[аи]?)'
        r'\s*[:\-–—]', re.IGNORECASE | re.MULTILINE)),
    ('answers_heading', re.compile(
        r'^\W*(?:ответы\s+и\s+решения|решения\s+и\s+(?:ответы|критерии)|'
        r'критерии\s+(?:оценивания|оценки|проверки)|ключи\s+к\s+заданиям|'
        r'возможные\s+решения)\W*$', re.IGNORECASE | re.MULTILINE)),
    ('timing_header', re.compile(
        r'^\W*(?:время\s+(?:выполнения|написания|работы)[^\n]{0,40}\d+\s*(?:мин|час)|'
        r'максимальн(?:ый|ое)\s+(?:балл|количество\s+баллов)\s+за\s+(?:работу|олимпиаду|тур))',
        re.IGNORECASE | re.MULTILINE)),
)


def service_hits(text):
    """[(код, найденная строка)] служебного текста в условии."""
    out = []
    for code, pattern in SERVICE_PATTERNS:
        for m in pattern.finditer(text or ''):
            out.append((code, m.group(0).strip()[:80]))
    return out


def s1(card):
    statement = (card.get('statement') or '').strip()
    body = re.sub(r'\[\[FIGURE:[0-9a-f]+\]\]', '', statement).strip()
    if not body and not card.get('parts') and not (card.get('test') or {}).get('options'):
        return [fail('S1', 'empty_statement', 'условие пустое')]
    out = []
    for text in [statement] + [p.get('text') or '' for p in card.get('parts') or []]:
        for code, line in service_hits(text):
            out.append(fail('S1', code, line))
    return out


# ── S2. Пункты и баллы ───────────────────────────────────────────────────

_POINTS = re.compile(r'\(\s*\**\s*(\d+(?:[.,]\d+)?)\s*\**\s*балл[а-я]*\s*\**\s*\)', re.IGNORECASE)


def text_points(text):
    found = _POINTS.findall(text or '')
    return Decimal(found[0].replace(',', '.')) if len(found) == 1 else None


def s2(card):
    parts = card.get('parts') or []
    if not parts:
        return []
    out = []
    labels = [str(p.get('label') or '').strip() for p in parts]
    if any(not lb for lb in labels):
        out.append(fail('S2', 'part_without_label',
                        'пунктов без метки: %d из %d' % (labels.count(''), len(labels))))
    seen, dup = set(), []
    for lb in labels:
        if lb and lb.lower() in seen:
            dup.append(lb)
        seen.add(lb.lower())
    if dup:
        out.append(fail('S2', 'duplicate_labels', 'повтор меток: %s' % ', '.join(dup[:8])))
    empty = [lb for lb, p in zip(labels, parts) if not (p.get('text') or '').strip()]
    if empty:
        out.append(fail('S2', 'empty_part', 'пустые пункты: %s' % ', '.join(empty[:8])))
    max_score = card.get('max_score')
    points = [p.get('points') for p in parts]
    if max_score not in (None, '') and points and all(pt is not None for pt in points):
        total = sum(Decimal(str(pt)) for pt in points)
        if total != Decimal(str(max_score)):
            out.append(fail('S2', 'points_sum', 'сумма баллов пунктов %s ≠ максимум %s'
                            % (_num(total), _num(max_score))))
    return out


def _num(x):
    d = Decimal(str(x))
    return str(d.quantize(Decimal(1)) if d == d.to_integral() else d.normalize())


# ── S3. Числа против текстового слоя PDF ─────────────────────────────────
#
# Разбор чисел — `claude_eyes.numbers` (P2, с исправленной склейкой меток:
# пункт и его текст через табуляцию). Однозначные числа не сверяются: метки,
# степени и номера есть на любой странице, проверка шумела бы без пользы.

SCAN_LAYER_BELOW = 200


def _layer_join(text):
    # перенос слова на стыке строк слоя склеивается («мил-\nлион» → «миллион»)
    return re.sub(r'-\n(?=\w)', '', text or '')


def card_number_text(card):
    chunks = [card.get('statement') or '']
    chunks += ['%s\t%s' % (p.get('label') or '', p.get('text') or '') for p in card.get('parts') or []]
    chunks += ['%s\t%s' % (o.get('label') or '', o.get('text') or '')
               for o in (card.get('test') or {}).get('options') or []]
    text = '\n'.join(chunks)
    # вступление раздела теста («Тест включает 30 вопросов…») стоит на первой
    # странице раздела, а не на странице вопроса — его числа не сверяем
    section = (card.get('section') or '').strip()
    if section:
        text = text.replace(section, ' ')
    return re.sub(r'\[\[FIGURE:[0-9a-f]+\]\]', '', text)


def alien_numbers(card):
    layer = card.get('layer') or {}
    corpus = numbers(_layer_join(layer.get('text') or ''))
    mine = {n for n in numbers(card_number_text(card)) if len(n.lstrip('0') or '0') >= 2}
    return sorted(mine - corpus, key=lambda s: (len(s), s))


def s3(card):
    layer = card.get('layer')
    if not layer:
        return []
    if layer.get('scan'):
        return []
    alien = alien_numbers(card)
    if alien:
        return [fail('S3', 'number_not_in_pdf', 'нет в слое PDF: %s' % ', '.join(alien[:10]))]
    return []


def s3_skip_reason(card):
    layer = card.get('layer')
    if not layer:
        return 'нет слоя PDF (задача не связана с эталоном)'
    if layer.get('scan'):
        return 'скан: слой < %d знаков' % SCAN_LAYER_BELOW
    return ''


# ── S4. Формулы ──────────────────────────────────────────────────────────

def formula_texts(card):
    """[(поле, текст)] всего, что сайт пропустит через KaTeX."""
    out = [('statement', card.get('statement') or ''), ('solution', card.get('solution') or ''),
           ('answer', card.get('answer') or ''), ('criteria', card.get('criteria') or '')]
    for i, p in enumerate(card.get('parts') or []):
        out.append(('part%d' % i, p.get('text') or ''))
        out.append(('part%d.answer' % i, p.get('answer') or ''))
    for i, o in enumerate((card.get('test') or {}).get('options') or []):
        out.append(('option%d' % i, o.get('text') or ''))
    return [(f, t) for f, t in out if t.strip()]


def s4_from_results(results):
    """Провалы S4 из ответа `katex.check_texts` по текстам одной карточки."""
    out = []
    for field, res in results:
        for err in res.get('errors') or []:
            out.append(fail('S4', 'katex_error', '%s: %s ⟵ %s' % (field, err['problem'][:120],
                                                                    err['tex'][:80])))
        for seg in res.get('currency') or []:
            out.append(fail('S4', 'currency_dollar', '%s: «%s»' % (field, seg[:80])))
        for seg in res.get('text_in_math') or []:
            out.append(fail('S4', 'text_in_math', '%s: «%s»' % (field, seg[:80])))
        if res.get('unpaired'):
            out.append(fail('S4', 'unpaired_dollar', '%s: непарный $ (%d)' % (field, res['unpaired'])))
    return out


# ── S5. Рисунки ──────────────────────────────────────────────────────────

def s5(card):
    out = []
    for h in card.get('figure_markers_missing') or []:
        out.append(fail('S5', 'marker_without_figure', 'маркер [[FIGURE:%s…]] без картинки' % h[:12]))
    for fig in card.get('figures') or []:
        name = fig.get('name') or '?'
        if not fig.get('exists'):
            out.append(fail('S5', 'figure_missing', '%s: файла нет' % name))
        elif not fig.get('size'):
            out.append(fail('S5', 'figure_empty', '%s: пустой файл' % name))
        elif not fig.get('opens'):
            out.append(fail('S5', 'figure_broken', '%s: PIL не открывает' % name))
        if fig.get('rejected'):
            out.append(fail('S5', 'figure_rejected', '%s: в списке брака (%s)' % (name, fig['rejected'])))
        if fig.get('flag'):
            out.append(fail('S5', 'figure_flag', '%s: флаг вырезки «%s»' % (name, fig['flag'])))
    for name in card.get('figure_orphans') or []:
        out.append(fail('S5', 'figure_orphan', '%s: картинка задачи, на которую текст не ссылается' % name))
    return out


# ── S6. Таблицы ──────────────────────────────────────────────────────────

_TABLE_LINE = re.compile(r'^\s*\|.*\|\s*$')
_SEPARATOR = re.compile(r'^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$')
_TABLE_WORD = re.compile(r'\bтаблиц[аеуыойами]*\b|\bтабл\.', re.IGNORECASE)


def _cells(line):
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|') and not s.endswith('\\|'):
        s = s[:-1]
    return len(re.split(r'(?<!\\)\|', s))


def table_blocks(text):
    """[[строки таблицы]] — подряд идущие строки вида «| … |»."""
    blocks, cur = [], []
    for line in (text or '').split('\n'):
        if _TABLE_LINE.match(line):
            cur.append(line)
        else:
            if cur:
                blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    return blocks


def table_problems(text):
    out = []
    for block in table_blocks(text):
        if len(block) < 2 or not _SEPARATOR.match(block[1]):
            out.append(('no_separator', block[0].strip()[:60]))
            continue
        widths = {_cells(line) for line in block if not _SEPARATOR.match(line)}
        widths.add(_cells(block[1]))
        if len(widths) > 1:
            out.append(('ragged_table', '%s: столбцов %s' % (block[0].strip()[:50],
                                                            '/'.join(map(str, sorted(widths))))))
    return out


def all_texts(card):
    texts = [card.get('statement') or '', card.get('solution') or '', card.get('answer') or '',
             card.get('criteria') or '']
    texts += [p.get('text') or '' for p in card.get('parts') or []]
    texts += [o.get('text') or '' for o in (card.get('test') or {}).get('options') or []]
    return texts


def s6(card):
    out = []
    for text in all_texts(card):
        for code, details in table_problems(text):
            out.append(fail('S6', code, details))
    task_text = '\n'.join([card.get('statement') or ''] + [p.get('text') or '' for p in card.get('parts') or []])
    has_table = bool(table_blocks(task_text))
    mentions = bool(_TABLE_WORD.search(re.sub(r'\[\[FIGURE:[0-9a-f]+\]\]', '', task_text)))
    task_figs = [f for f in card.get('figures') or [] if f.get('field', 'statement') == 'statement']
    intentional = any(f.get('table_ok') for f in task_figs)
    expected = card.get('tables_expected') or 0
    any_table = any(table_blocks(text) for text in all_texts(card))
    if not has_table and not intentional:
        if expected and not any_table:
            out.append(fail('S6', 'table_lost', 'оцифровка нашла таблиц: %d, в тексте нет ни одной' % expected))
        elif mentions and task_figs:
            out.append(fail('S6', 'table_as_image', 'условие говорит о таблице, таблицы текстом нет, есть картинка'))
        elif mentions:
            out.append(fail('S6', 'table_mentioned_missing', 'условие говорит о таблице, таблицы нет'))
    return out


# ── S7. Тесты ────────────────────────────────────────────────────────────

def s7(card):
    test = card.get('test')
    if not test:
        return []
    kind = test.get('kind')
    if kind == 'short':
        if not (test.get('key') or '').strip():
            return [fail('S7', 'no_key', 'тест с коротким ответом без ответа')]
        return []
    if kind == 'broken':
        return [fail('S7', 'not_playable', test.get('why') or 'тест не собирается в игру')]
    out = []
    options = test.get('options') or []
    if len(options) < 2:
        out.append(fail('S7', 'few_options', 'вариантов: %d %s' % (len(options), test.get('why') or '')))
    labels = [str(o.get('label') or '').lower() for o in options]
    if len(set(labels)) != len(labels):
        out.append(fail('S7', 'duplicate_option_labels', 'метки вариантов повторяются'))
    correct = [o for o in options if o.get('correct')]
    key = (test.get('key') or '').strip()
    if not key and not correct:
        out.append(fail('S7', 'no_key', 'ключа нет'))
    elif not correct:
        out.append(fail('S7', 'key_not_in_options', 'ключ «%s» не совпал ни с одним вариантом' % key[:40]))
    elif kind == 'single' and len(correct) > 1:
        out.append(fail('S7', 'single_many_correct', 'один выбор, верных %d' % len(correct)))
    return out


# ── S8. Решение и критерии — своей задачи ────────────────────────────────

_SOLUTION_IN_STATEMENT = re.compile(
    r'^\W*(?:решение|ответ|критерии\s+оценивания|возможное\s+решение|разбалловка)\s*[:.]?\s*$|'
    # «Ответ: ______» — поле бланка для ответа, а не ответ
    r'^\W*(?:решение|ответ)\s*:(?![\s_.…*]*$)', re.IGNORECASE | re.MULTILINE)
_TASK_NO = re.compile(r'^\W*(?:задача|задание)\s*№?\s*(\d+)\b', re.IGNORECASE)
_PART_MARK = re.compile(r'(?:^|\n)\s*\**\(?([а-е])\)\s', re.IGNORECASE)


def s8(card):
    out = []
    statement = card.get('statement') or ''
    m = _SOLUTION_IN_STATEMENT.search(statement)
    if m and not (card.get('test') and m.group(0).strip().lower().startswith('ответ')):
        out.append(fail('S8', 'solution_in_statement', '«%s» в условии' % m.group(0).strip()[:40]))
    number = str(card.get('number') or '')
    for field in ('solution', 'criteria'):
        text = card.get(field) or ''
        mm = _TASK_NO.match(text)
        if mm and number.isdigit() and mm.group(1) != number:
            out.append(fail('S8', 'solution_other_number',
                            '%s начинается с «задача %s», номер задачи %s' % (field, mm.group(1), number)))
    labels = {str(p.get('label') or '').lower() for p in card.get('parts') or []}
    if labels and all(len(lb) == 1 and 'а' <= lb <= 'е' for lb in labels):
        sol_marks = {x.lower() for x in _PART_MARK.findall(card.get('solution') or '')}
        extra = sorted(sol_marks - labels)
        if extra and max(extra) > max(labels):
            out.append(fail('S8', 'solution_extra_parts',
                            'в решении пункты %s, у задачи до «%s»' % (', '.join(extra), max(labels))))
    if card.get('solution_expected') and not any(
            (card.get(k) or '').strip() for k in ('solution', 'answer', 'criteria'))             and not any((p.get('answer') or '').strip() for p in card.get('parts') or [])             and not any(o.get('correct') for o in (card.get('test') or {}).get('options') or []):
        out.append(fail('S8', 'no_solution', 'у источника есть файл решений, у задачи нет ни ответа, ни решения'))
    if card.get('reference_suspect'):
        out.append(fail('S8', 'criteria_other_task', 'критерии не от этой задачи (экзамен P4)'))
    return out


# ── S9. Метаданные и заголовок ───────────────────────────────────────────

_OLYMPIAD_IN_TITLE = re.compile(r'олимпиад|высшая проба|\bВП\b|\bМОШ\b|\bВсОШ\b', re.IGNORECASE)


def s9(card):
    out = []
    meta = card.get('meta') or {}
    missing = [name for key, name in (('season', 'сезон'), ('stage', 'этап'),
                                      ('grade', 'класс'), ('number', 'номер'))
               if not str(meta.get(key) or '').strip()]
    if not card.get('olympiad'):
        missing.insert(0, 'олимпиада')
    if missing:
        out.append(fail('S9', 'meta_missing', 'нет: %s' % ', '.join(missing)))
    if not meta.get('pdf_url'):
        out.append(fail('S9', 'no_pdf_link', 'нет ссылки на PDF источника'))
    elif meta.get('pdf_official') is False:
        out.append(fail('S9', 'pdf_not_official', 'PDF не с официального сайта: %s' % meta['pdf_url'][:80]))
    if card.get('level') == 'bank':
        title = (card.get('title') or '').strip()
        if is_stub(title):
            out.append(fail('S9', 'title_stub', 'заголовок-заглушка: «%s»' % title[:60]))
        elif _OLYMPIAD_IN_TITLE.search(title):
            out.append(fail('S9', 'title_has_olympiad', 'олимпиада в заголовке: «%s»' % title[:60]))
        elif len(title) >= TEXT_START_KEEP_BELOW and looks_like_text_start(title, card.get('statement')):
            out.append(fail('S9', 'title_text_start', 'заголовок — начало условия (%d знаков)' % len(title)))
    return out


# ── S10. Дубли внутри события ────────────────────────────────────────────

def dup_text(card):
    chunks = [card.get('statement') or ''] + [p.get('text') or '' for p in card.get('parts') or []]
    chunks += [o.get('text') or '' for o in (card.get('test') or {}).get('options') or []]
    text = re.sub(r'\[\[FIGURE:[0-9a-f]+\]\]', ' ', ' '.join(chunks)).lower().replace('ё', 'е')
    return ' '.join(re.findall(r'\w+', text))


def s10_groups(cards):
    """{id карточки: [провал]} — одинаковый нормализованный текст в одном событии.

    Банк считает только видимые задачи (решение: дубль виден ученику);
    у эталона — все строки одного `event_id`."""
    groups = {}
    for i, card in enumerate(cards):
        if card.get('level') == 'bank' and not card.get('visible'):
            continue
        text = dup_text(card)
        if len(text) < 20:
            continue
        groups.setdefault((card.get('level'), card.get('event_id'), text), []).append(i)
    out = {}
    for (_level, event, _text), idx in groups.items():
        if len(idx) < 2:
            continue
        for i in idx:
            others = [cards[j].get('problem_id') or cards[j].get('ref_key') for j in idx if j != i]
            out.setdefault(i, []).append(fail('S10', 'duplicate_in_event', '%s: тот же текст у %s'
                                              % (event, ', '.join(map(str, others[:5])))))
    return out


# ── Сборка ───────────────────────────────────────────────────────────────

LOCAL_CHECKS = (s1, s2, s3, s5, s6, s7, s8, s9)


def check_card(card, s4_fails=(), s10_fails=()):
    """{fails: [...], skipped: {проверка: причина}} одной карточки."""
    fails = []
    for check in LOCAL_CHECKS:
        fails.extend(check(card))
    fails.extend(s4_fails)
    fails.extend(s10_fails)
    skipped = {}
    why = s3_skip_reason(card)
    if why:
        skipped['S3'] = why
    if not card.get('test'):
        skipped['S7'] = 'не тест'
    order = {c: i for i, c in enumerate(CHECKS)}
    fails.sort(key=lambda f: order.get(f['check'], 99))
    return {'fails': fails, 'skipped': skipped}
