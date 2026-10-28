# -*- coding: utf-8 -*-
"""Строка эталона олимпиады (v2 и дальше) → поля новой задачи банка.

Чистые функции, без базы: их зовёт команда `import_olympiad_reference`, а
тесты проверяют их по отдельности. Эталон — `reference_problems_vN.jsonl`
или очередь импорта на его основе (`import_queue_vN.jsonl`): у строки
markdown-условие, пункты, рисунки, решение, ответ, критерии.

Правила (стоп-гейт 1 сессии И2, 14.10.2026):

* **Пункты** кладутся в `ProblemPart`, только если в условии они стоят
  сплошным хвостовым списком («- а) …», «1. …») — тогда этот хвост вырезается
  из условия, иначе пункты показались бы дважды (страница рисует условие и
  под ним список пунктов). Пункты, вплетённые в рассказ (вопросы интервью,
  кейс с вопросами посередине), остаются в условии как есть, `ProblemPart`
  не создаётся — как у импорта ВП-экономики 63322–63327.
* **Баллы пункта** «(k баллов)» — в `ProblemPart.points`; текст пункта
  не меняется.
* **Ответ** «а) …; б) …» раскладывается по пунктам, только если метки в
  ответе ровно те же и в том же порядке, что у пунктов; иначе весь ответ —
  в `Problem.answer`.
* **Критерии** — разделом «Критерии оценивания» в конце решения (обычай
  ILE, SolveHub, импорта ВП-экономики), а не `Rubric`.
* **Рисунки** — маркер `[[FIGURE:<sha256>]]` там, где о рисунке говорится.
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
from decimal import Decimal

#: Порог «уверенного» совпадения текста с задачей банка и нижняя граница
#: «сомнительного» (решение 09.10: подтверждение текстом ≥ 0,90).
LINK_THRESHOLD = 0.90
DOUBT_THRESHOLD = 0.80

STAGE_LABELS = {'final': 'Заключительный этап', 'qualifying': 'Отборочный этап'}

TYPE_MULTI = 'несколько_подвопросов'
TYPE_OPEN = 'задача с развёрнутым ответом'

CRITERIA_HEADING = '**Критерии оценивания**'

_POINTS = re.compile(r'\(\s*\**\s*(\d+(?:[.,]\d+)?)\s*\**\s*балл[а-я]*\s*\**\s*\)', re.IGNORECASE)
# Что может стоять между пунктами хвостового списка: маркер списка, метка,
# скобка/точка после метки, пробелы. Больше ничего — иначе это рассказ.
_GAP_TOKEN = r'[\s\-*•·]*(?:\(?\**{label}\**[).:]?\**)?[\s\-*•·]*'


def part_points(text):
    """Баллы пункта из «(2 балла)» / «(**4 балла**)»; ровно одно упоминание,
    иначе None (два числа баллов в пункте — не угадываем)."""
    found = _POINTS.findall(text or '')
    if len(found) != 1:
        return None
    return Decimal(found[0].replace(',', '.'))


def split_parts_from_statement(statement, parts):
    """(условие без хвоста пунктов, True) или (условие как есть, False, причина).

    Хвост — это пункты подряд в конце условия: между текстами пунктов
    только маркеры списка и метки, после последнего — пусто."""
    if len(parts) < 1:
        return statement, False, 'нет пунктов'
    pos, spans = 0, []
    for part in parts:
        text = (part.get('text') or '').strip()
        if not text:
            return statement, False, 'пустой текст пункта'
        at = statement.find(text, pos)
        if at < 0:
            return statement, False, 'текст пункта не найден в условии по порядку'
        spans.append((at, at + len(text)))
        pos = at + len(text)
    if statement[spans[-1][1]:].strip():
        return statement, False, 'после пунктов идёт текст (пункты вплетены в рассказ)'
    for i in range(1, len(spans)):
        gap = statement[spans[i - 1][1]:spans[i][0]]
        token = _GAP_TOKEN.format(label=re.escape(parts[i]['label']))
        if not re.fullmatch(token, gap):
            return statement, False, 'между пунктами есть текст'
    line_start = statement.rfind('\n', 0, spans[0][0]) + 1
    lead = statement[line_start:spans[0][0]]
    if not re.fullmatch(_GAP_TOKEN.format(label=re.escape(parts[0]['label'])), lead):
        return statement, False, 'перед первым пунктом в строке есть текст'
    head = statement[:line_start].rstrip()
    if not head:
        return statement, False, 'кроме пунктов в условии ничего нет'
    return head, True, ''


def split_answer(answer, labels):
    """{метка: ответ} при однозначной разметке «а) …; б) …», иначе None."""
    if not answer or len(labels) < 2:
        return None
    marks = []
    for m in re.finditer(r'(?:^|(?<=[\s;.,]))\(?([а-яёa-z0-9]{1,2})\)', answer, re.IGNORECASE):
        marks.append((m.group(1).lower(), m.start(), m.end()))
    if [m[0] for m in marks] != [str(lb).lower() for lb in labels]:
        return None
    if answer[:marks[0][1]].strip():
        return None
    out = {}
    for i, (label, _start, end) in enumerate(marks):
        stop = marks[i + 1][1] if i + 1 < len(marks) else len(answer)
        text = answer[end:stop].strip().rstrip(';').strip()
        if not text:
            return None
        out[labels[i]] = text
    return out


# ── Разметка под рендерер сайта ────────────────────────────────────────
#
# Рендерер (`problems/rendering.py`) — узкое подмножество markdown: абзацы,
# списки, таблицы, жирный/курсив, `html: False`. Чего он не знает, то он
# покажет БУКВАЛЬНО: `<br>` в ячейке выйдет текстом «<br>», «# Заголовок» —
# решёткой. Поэтому новые тексты приводятся к подмножеству детерминированно
# (решение владельца на стоп-гейте 1, 14.10). `~~` и ссылки не трогаем.

_BR = re.compile(r'<br\s*/?>', re.IGNORECASE)
_U = re.compile(r'<u>(.*?)</u>', re.IGNORECASE | re.DOTALL)
_HEADING = re.compile(r'^#{1,6}\s+(.+?)\s*#*\s*$')
_HR = re.compile(r'^\s*(?:-{3,}|\*{3,}|_{3,})\s*$')


def adapt_markup(text):
    """Текст → (текст в подмножестве рендерера, счётчик правок по видам)."""
    counts = {}

    def bump(kind, n=1):
        if n:
            counts[kind] = counts.get(kind, 0) + n

    out = []
    for line in (text or '').split('\n'):
        if line.lstrip().startswith('|'):
            new, n = _BR.subn(' ', line)
            bump('br в таблице', n)
            line = re.sub(r'  +', ' ', new) if n else new
        else:
            new, n = _BR.subn('\n', line)
            bump('br', n)
            line = new
        line, n = _U.subn(lambda m: f'*{m.group(1).strip()}*', line)
        bump('u', n)
        heading = _HEADING.match(line)
        if heading:
            line = f'**{heading.group(1).strip("*").strip()}**'
            bump('#', 1)
        elif _HR.match(line):
            line = ''
            bump('---', 1)
        out.append(line)
    return '\n'.join(out), counts


def quote_url(url):
    """Адрес с пробелами и кириллицей → процентная запись (как у импорта ВП)."""
    from urllib.parse import quote, urlsplit, urlunsplit
    if not url:
        return ''
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe='/%'),
                       quote(parts.query, safe='=&%'), parts.fragment))


def solution_with_criteria(solution_md, criteria_md):
    """Решение + раздел «Критерии оценивания» в конце (заголовок не дублируется)."""
    solution_md = (solution_md or '').strip()
    criteria_md = (criteria_md or '').strip()
    if not criteria_md:
        return solution_md
    first = criteria_md.split('\n', 1)[0]
    block = criteria_md if 'ритерии' in first.lower() else f'{CRITERIA_HEADING}\n\n{criteria_md}'
    return f'{solution_md}\n\n{block}' if solution_md else block


# ── Рисунки ────────────────────────────────────────────────────────────

_FIG_WORDS = re.compile(r'рис\.|рисун|график|диаграмм|схем|инфографи|изображ', re.IGNORECASE)
# Абзац-подпись на месте рисунка: «*Диаграмма*», «*Рисунок 1*», «**График**».
_FIG_LABEL = re.compile(r'^\s*[*_]{1,2}[^*_\n]{1,40}[*_]{1,2}\s*$')


def _norm(text):
    return re.sub(r'[\W_]+', ' ', (text or '').lower()).strip()


def figure_hash(source_file, event_id, number, path):
    """Тело маркера: стабильно для того же рисунка того же задания."""
    ref = f'official-pdf:{os.path.basename(source_file)}#{event_id}:{number}:{os.path.basename(path)}'
    return hashlib.sha256(ref.encode('utf-8')).hexdigest(), ref


_TEXT_BLOCKS = ('task', 'task_continuation', 'solution', 'criteria')


def _page_blocks(digitized_dir, page_dir, page):
    """Блоки страницы: заплатка pages_v2 (если в ней есть блоки), иначе pages."""
    name = os.path.basename(page_dir or '')
    for base in ('pages_v2', 'pages'):
        path = os.path.join(digitized_dir, base, name, f'p{page}.json')
        if os.path.isfile(path):
            import json
            with open(path, encoding='utf-8') as handle:
                data = json.load(handle)
            if data.get('blocks'):
                return data['blocks']
    return []


def figure_anchor(digitized_dir, fig):
    """Текст, рядом с которым рисунок стоит на странице PDF.

    Порядок блоков страницы сохраняет расшифровка: рисунок идёт сразу за
    текстовым блоком. Возвращает ('after', хвост текста перед рисунком) или
    ('before', начало текста после него) или None."""
    blocks = _page_blocks(digitized_dir, fig.get('page_dir'), fig.get('page'))
    bbox = fig.get('bbox_model')
    idx = next((i for i, b in enumerate(blocks)
                if b.get('type') == 'figure' and b.get('bbox') == bbox), None)
    if idx is None:
        return None
    for b in reversed(blocks[:idx]):
        if b.get('type') in _TEXT_BLOCKS and (b.get('text') or '').strip():
            return 'after', b['text'].strip()
    for b in blocks[idx + 1:]:
        if b.get('type') in _TEXT_BLOCKS and (b.get('text') or '').strip():
            return 'before', b['text'].strip()
    return None


def _anchor_paragraph(paragraphs, anchor, floor):
    """Индекс абзаца, куда встаёт маркер по якорю (после него), или None."""
    side, text = anchor
    lines = [ln for ln in text.split('\n') if _norm(ln)]
    if not lines:
        return None
    key = _norm(lines[-1])[-80:] if side == 'after' else _norm(lines[0])[:80]
    if len(key) < 12:
        return None
    for i in range(floor, len(paragraphs)):
        if key in _norm(paragraphs[i]):
            return i if side == 'after' else i - 1
    return None


def place_figures(text, figures):
    """Вставить маркеры рисунков в текст. `figures` — [(marker, caption, anchor)].

    Каждый рисунок — после абзаца:
      0) за которым он стоит на странице PDF (якорь `figure_anchor`), или
      1) содержащего начало его подписи (первые 4 слова), или
      2) очередного абзаца-подписи на месте рисунка («*Диаграмма*»), или
      3) очередного абзаца, где говорится о рисунке/графике/диаграмме;
      4) иначе — в конец текста.
    Порядок рисунков сохраняется: маркер не встаёт раньше предыдущего.
    Возвращает (текст, [способ для каждого рисунка])."""
    paragraphs = (text or '').split('\n\n')
    inserts = {}             # индекс абзаца -> [маркеры]
    how, floor = [], 0
    used_label, used_word = set(), set()
    for marker, caption, anchor in figures:
        words = _norm(caption).split()[:4]
        at, way = None, ''
        if anchor:
            found = _anchor_paragraph(paragraphs, anchor, floor)
            if found is not None and found >= floor - 1:
                at, way = max(found, -1), 'по странице PDF'
        if at is None and len(words) >= 2:
            key = ' '.join(words)
            for i in range(floor, len(paragraphs)):
                if key in _norm(paragraphs[i]):
                    at, way = i, 'подпись'
                    break
        if at is None:
            for i in range(floor, len(paragraphs)):
                if i not in used_label and _FIG_LABEL.match(paragraphs[i]) \
                        and _FIG_WORDS.search(paragraphs[i]):
                    at, way = i, 'метка на месте рисунка'
                    used_label.add(i)
                    break
        if at is None:
            for i in range(floor, len(paragraphs)):
                if i not in used_word and _FIG_WORDS.search(paragraphs[i]):
                    at, way = i, 'абзац о рисунке'
                    used_word.add(i)
                    break
        if at is None:
            at, way = len(paragraphs) - 1, 'в конец'
        inserts.setdefault(at, []).append(marker)
        how.append(way)
        floor = max(at, 0)
    out = list(inserts.get(-1, []))      # рисунок перед первым абзацем
    for i, para in enumerate(paragraphs):
        out.append(para)
        out.extend(inserts.get(i, []))
    return '\n\n'.join(out), how


# ── Источник ───────────────────────────────────────────────────────────

def load_url_map(subdir, official_hosts=()):
    """basename файла PDF → (адрес на сайте, official).

    Источники по старшинству: `download_plan.csv` подпапки (финграм, бизнес),
    `raw/fetch_log.jsonl` (ВП-экономика: файл → адрес скачивания). Файл,
    которого нет ни там, ни там, но имя которого кодирует адрес
    (`mos.olimpiada.ru__upload__files__…pdf`, `api.solvehub.app__uploads__…pdf`),
    раскрывается по имени: `__` → `/` (у МОШ так сходятся 3 015 из 3 015
    файлов с `session1/download_plan.csv`). `official` — хост из реестра."""
    import json
    out = {}
    path = os.path.join(subdir, 'download_plan.csv')
    if os.path.isfile(path):
        with open(path, encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle):
                if row.get('file') and row.get('url'):
                    out[os.path.basename(row['file'])] = (row['url'], row.get('official') == 'true')
    log = os.path.join(subdir, 'raw', 'fetch_log.jsonl')
    if os.path.isfile(log):
        with open(log, encoding='utf-8') as handle:
            for line in handle:
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec.get('file') and rec.get('url') and rec.get('curl_rc', 0) == 0:
                    out.setdefault(os.path.basename(rec['file']),
                                   (rec['url'], _host_official(rec['url'], official_hosts)))
    return UrlMap(out, official_hosts)


def _host_official(url, official_hosts):
    from urllib.parse import urlsplit
    host = urlsplit(url).netloc.lower()
    return any(host == h or host.endswith('.' + h) for h in official_hosts)


class UrlMap(dict):
    """dict с запасным путём: адрес из имени файла `хост__путь`."""

    def __init__(self, data=None, official_hosts=()):
        super().__init__(data or {})
        self.official_hosts = tuple(official_hosts)

    def get(self, key, default=None):
        if key in self:
            return self[key]
        if key and '__' in key and '.' in key.split('__', 1)[0]:
            url = 'https://' + key.replace('__', '/')
            return url, _host_official(url, self.official_hosts)
        return default


def default_title(olympiad_short, row):
    return (f'{olympiad_short} {row.get("academic_year") or row.get("year")}, '
            f'{row.get("grade")} кл., задание {row.get("number")}')


def problem_type_for(parts):
    return TYPE_MULTI if len(parts or []) >= 2 else TYPE_OPEN


#: Тестовые вопросы (2.3 ночи 28.10): вид — по самому вопросу.
TYPE_SINGLE = 'единственный_выбор'
TYPE_MULTI_CHOICE = 'множественный_выбор'
TYPE_BOOLEAN = 'верно_неверно'
TYPE_SHORT = 'тест: короткий ответ'
CORRECT_MARK = 'верно'


def is_test_row(row):
    """Вопрос теста: номер `тест-N` / `тест-N.M` (эталон v2 и дальше)."""
    return str(row.get('number') or '').startswith('тест')


def test_fields(statement, answer):
    """Вопрос теста → (условие, problem_type, подпункты, заметка).

    По обычаю банка (`test_options_from_statement`, решение 15.09.2026):
    варианты — в `ProblemPart` (метка, текст, «верно» у верных), блок
    вариантов вырезается из условия; у «верно/неверно» — подпункты «а»
    Верно, «б» Неверно, строка вариантов в хвосте снимается. Ключ остаётся
    в `Problem.answer`. Нет вариантов — «тест: короткий ответ»."""
    from problems.test_options_parse import (
        BOOLEAN_PARTS, boolean_correct_label, correct_labels, cut_boolean_tail,
        formula_worse, parse_with_reason,
    )
    parsed, why = parse_with_reason(statement)
    if parsed is None:
        return statement, TYPE_SHORT, [], f'тест без вариантов ({why}) — короткий ответ'
    texts = [_norm(t) for _label, t in parsed.options]
    if texts in (['верно', 'неверно'], ['да', 'нет']):
        label = boolean_correct_label(answer, statement)
        stem = cut_boolean_tail(statement)
        stem = stem if isinstance(stem, str) and stem.strip() else parsed.stem
        parts = [{'label': key, 'statement_md': text,
                  'answer': CORRECT_MARK if key == label else '', 'points': None}
                 for key, text in BOOLEAN_PARTS]
        return (stem, TYPE_BOOLEAN, parts,
                'тест верно/неверно' + ('' if label else ': ключа нет'))
    if formula_worse(statement, parsed.stem) or any(formula_worse('', t) for _l, t in parsed.options):
        return statement, TYPE_SHORT, [], 'варианты с формулами не вырезаю (баланс $) — условие как есть'
    correct = correct_labels(answer, parsed) if (answer or '').strip() else set()
    kind = TYPE_MULTI_CHOICE if len(correct) > 1 else TYPE_SINGLE
    parts = [{'label': label, 'statement_md': text,
              'answer': CORRECT_MARK if label in correct else '', 'points': None}
             for label, text in parsed.options]
    return (parsed.stem, kind, parts,
            f'тест: {len(parts)} вариантов, верных {len(correct)}' + ('' if correct else ' (ключа нет)'))


def auto_publish_of(row):
    """(ok, причины) для строки без готового `auto_publish_ok` (эталон v6).

    Строгая автопроверка по полям самого эталона: `needs_eyes` (судья и
    мерило страниц), `numbers_ok`, непустое условие, ответ/решение при
    файле решений, ключ у теста, рисунки без флага. Строка очереди с
    готовым флагом — как есть (решение 13–14.10)."""
    if 'auto_publish_ok' in row:
        return bool(row.get('auto_publish_ok')), list(row.get('auto_publish_fail') or [])
    why = []
    if row.get('needs_eyes'):
        why.append('needs_eyes: страница на глаза')
    if row.get('numbers_ok') is False:
        why.append('числа слоя не сошлись')
    if not (row.get('statement_md') or '').strip():
        why.append('пустое условие')
    if row.get('solution_pages') and not any(
            (row.get(k) or '').strip() for k in ('answer', 'solution_md', 'criteria_md')):
        why.append('нет ответа/решения при файле решений')
    if is_test_row(row) and not (row.get('answer') or '').strip():
        why.append('тест без ключа')
    for fig in (row.get('figures') or []) + (row.get('solution_figures') or []):
        if fig.get('flag'):
            why.append(f'рисунок с флагом «{fig["flag"]}»')
            break
    return not why, why


def build_fields(row, *, digitized_dir, url_map, olympiad_short):
    """Строка эталона → план новой задачи (dict без обращения к базе).

    Возвращает поля задачи, пункты, рисунки (с путём к файлу на диске) и
    заметки о том, какое правило сработало."""
    notes = []
    parts_in = row.get('parts') or []
    statement = row.get('statement_md') or ''
    parts_out = []
    problem_type = None
    if is_test_row(row):
        statement, problem_type, parts_out, note = test_fields(statement, row.get('answer') or '')
        notes.append(note)
        parts_in = []
    if parts_in:
        cut, ok, why = split_parts_from_statement(statement, parts_in)
        if ok:
            statement = cut
            answers = split_answer(row.get('answer') or '', [p['label'] for p in parts_in]) or {}
            for p in parts_in:
                parts_out.append({'label': p['label'], 'statement_md': p['text'].strip(),
                                  'answer': answers.get(p['label'], ''),
                                  'points': part_points(p['text'])})
            notes.append(f'пункты в ProblemPart: {len(parts_out)}'
                         + ('; ответ разложен по пунктам' if answers else ''))
        else:
            notes.append(f'пункты оставлены в условии: {why}')
    answer = row.get('answer') or ''
    if parts_out and any(p['answer'] for p in parts_out) and not problem_type:
        answer = ''
    solution = solution_with_criteria(row.get('solution_md'), row.get('criteria_md'))

    markup = {}

    def adapt(text):
        new, counts = adapt_markup(text)
        for kind, n in counts.items():
            markup[kind] = markup.get(kind, 0) + n
        return new

    statement, answer, solution = adapt(statement), adapt(answer), adapt(solution)
    for p in parts_out:
        p['statement_md'], p['answer'] = adapt(p['statement_md']), adapt(p['answer'])

    src = (row.get('source_file') or [''])[0]
    url, url_official = url_map.get(os.path.basename(src), ('', False))
    url = quote_url(url)
    figures = []
    for field, key in (('statement', 'figures'), ('solution', 'solution_figures')):
        items = []
        for fig in row.get(key) or []:
            path = os.path.join(digitized_dir, fig['path'])
            used = 'figures_clean_v2'
            if fig.get('flag') and fig.get('path_model'):
                path = os.path.join(digitized_dir, fig['path_model'])
                used = 'figures_v2 (у чистой вырезки флаг)'
            digest, ref = figure_hash(src, row['event_id'], row['number'], fig['path'])
            items.append({'field': field, 'path': path, 'hash': digest, 'ref': ref,
                          'caption': fig.get('caption') or '', 'flag': fig.get('flag') or '',
                          'from': used, 'anchor': figure_anchor(digitized_dir, fig)})
        if items:
            text = statement if field == 'statement' else solution
            if not text.strip() and field == 'solution':
                notes.append('рисунок решения без текста решения — решение из одного рисунка')
            text, how = place_figures(text, [(f'[[FIGURE:{i["hash"]}]]', i['caption'], i['anchor'])
                                             for i in items])
            for item, way in zip(items, how):
                item['placed'] = way
                item.pop('anchor')
            if field == 'statement':
                statement = text
            else:
                solution = text
            figures.extend(items)

    stage = row.get('stage') or 'final'
    from problems.olympiad_audit.title_rule import is_stub
    title = (row.get('title') or '').strip()
    if is_stub(title):
        # Заглушка эталона («Задача 1», «Тест № 1.») — своя заглушка; настоящий
        # заголовок поставит обогащение (`import_reference_titles`).
        title = default_title(olympiad_short, row)
    return {
        'title': title[:300],
        'statement': statement.strip(),
        'answer': answer.strip(),
        'solution': solution.strip(),
        'problem_type': problem_type or problem_type_for(row.get('parts')),
        'parts': parts_out,
        'figures': figures,
        'source_url': url,
        'source_url_official': url_official,
        'stage': stage,
        'stage_label': STAGE_LABELS.get(stage, stage),
        'markup': markup,
        'notes': notes,
    }
