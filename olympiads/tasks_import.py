"""Заливка заданий пакета олимпиад в банк задач (Problem) — вся логика.

Команда — `manage.py import_olympiads_tasks`; здесь всё, что она делает,
чтобы проверять тестами без запуска команды. Решения владельца 30.10:
задания едут в банк СКРЫТЫМИ, «под вопросом» — признак позиции комплекта,
критерии — разделом в конце решения.

⚠️ СУЩЕСТВУЮЩИЕ ЗАДАЧИ БАНКА НЕ ТРОГАЕМ НИКАК. Задание, совпавшее с задачей
банка (`olympiads/bank_match.py`), только связывается с ней позицией
комплекта. Ни условие, ни ответ, ни решение, ни видимость не меняются; после
записи это сверяется отпечатком всех прежних задач (`existing_digest`).

⚠️ НОВАЯ ЗАДАЧА — `status='draft'` И `hidden_pending_review=True`, ВМЕСТЕ.
Одного второго мало: подбор репетитора (`base_queryset('tutor')`) его не
смотрит, а `pending_review_gate --revert` выпустил бы весь массив разом.

⚠️ ПОВТОРНЫЙ ПРОГОН ЗАДАЧИ НЕ ПЕРЕПИСЫВАЕТ. Ключ — `ref_key` позиции. Есть
позиция — задание пропускается; если запись пакета изменилась, обновляются
только поля самой позиции. Так ручная правка задачи не затирается никогда.
"""
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from decimal import Decimal

from olympiads import bank_match as bm
from olympiads import kits_import as ki

CRITERIA_HEADING = '## Критерии оценивания'

# Заголовок раздела критериев — ОТДЕЛЬНОЙ строкой (с жирным, решёткой,
# двоеточием), а не начало фразы «Схема проверки этой задачи описана…».
_CRITERIA_HEADING_LINE = re.compile(
    r'(?im)^[ \t]*[*#_>]*[ \t]*(?:схема проверки|критерии оценивания)'
    r'[ \t]*[*_]*[ \t]*[:.]?[ \t]*[*_]*[ \t]*$')
_LEADING_SAME_HEADING = re.compile(
    r'\A\s*[*#_>]*[ \t]*критерии оценивания[ \t]*[*_]*[ \t]*[:.]?[ \t]*[*_]*'
    r'[ \t]*(?:\n|\Z)', re.IGNORECASE)
_WS = re.compile(r'\s+')

# Вид теста пакета → `problem_type`. Словарь — ТОТ ЖЕ, что во всей локальной
# базе (старый: «тест: один ответ» и т. д.), см. `problems/problem_types.py`.
# ⚠️ `broken` — НЕ ТЕСТ (решение владельца 30.10, вопрос 2): структуру теста
# оцифровка не разобрала, играть его машиной всерьёз нельзя. Пустой тип —
# обычная задача; ключ, если есть, лежит в `answer`.
PROBLEM_TYPES = {
    'single': 'тест: один ответ',
    'multi': 'тест: все верные',
    'boolean': 'тест: верно/неверно',
    'short': 'тест: числовой ответ',
    'broken': '',
}

# Где в решении задачи начинается раздел критериев: наш заголовок
# «## Критерии оценивания» и обычай прежних источников банка (ILE, Overleaf,
# SolveHub — решение владельца 14.10) — строка, начинающаяся словами
# «Критерии…» или «Схема проверки / оценивания».
_SOLUTION_CRITERIA_START = re.compile(
    r'(?im)^[ \t]*[*#_>]*[ \t]*(?:критерии (?:оценивания|проверки|оценки)'
    r'|схема (?:проверки|оценивания)|критерии[ \t*_]*[:.]?[ \t*_]*$)')

REASON_NO_FIGURE_FILE = 'рисунок без файла'
REASON_FEWER_OPTIONS = 'вариантов меньше, чем пунктов'


def ws(text):
    return _WS.sub(' ', text or '').strip()


# ── критерии ─────────────────────────────────────────────────────────────

def _exact_half(text):
    """Первая половина, если текст — это X + X (пробелы не в счёт), иначе None."""
    flat = ws(text)
    n = len(flat)
    for cut in range(max(1, n // 2 - 2), n // 2 + 3):
        left, right = flat[:cut].strip(), flat[cut:].strip()
        if left and left == right:
            # Ищем в исходном тексте место, где нормализованный префикс
            # равен половине: так сохраняются переносы строк и абзацы.
            for pos in range(len(text)):
                if text[pos].isspace() and ws(text[:pos]) == left:
                    return text[:pos].rstrip()
            return left
    return None


def _heading_chunks(text):
    """(префикс до первого заголовка, [куски от заголовка до заголовка])."""
    starts = [m.start() for m in _CRITERIA_HEADING_LINE.finditer(text)]
    if not starts:
        return text, []
    bounds = starts + [len(text)]
    return text[:starts[0]], [text[bounds[i]:bounds[i + 1]]
                              for i in range(len(starts))]


def _near_repeat(a, b):
    na, nb = bm.norm(a), bm.norm(b)
    if len(na) < bm.MIN_LEN or len(nb) < bm.MIN_LEN:
        return False
    return bm.ratio(na, nb) >= bm.ACCEPT


def clean_criteria(text):
    """(чистый текст, правило): правило — None, 'exact' или 'headings'.

    1. Точное: после нормализации пробелов текст — две одинаковые половины;
       остаётся одна.
    2. Неточное: заголовок «Схема проверки» / «Критерии оценивания» стоит
       отдельной строкой больше одного раза. Кусок от заголовка до
       следующего, который почти повторяет (та же мера, что в
       сопоставлении с банком, ≥ 0,90) уже оставленный кусок, выпадает.
       Это общая форма правила «второй кусок — почти-повтор первого»: у
       четырёх критериев склейка вида A B A B и A B A, их ловит только она.
       Текст ДО первого заголовка остаётся всегда — там бывают свои баллы
       («K7. Нахождение p₃ — 1 балл»).
    """
    if not (text or '').strip():
        return text, None
    half = _exact_half(text)
    if half is not None:
        return half, 'exact'
    prefix, chunks = _heading_chunks(text)
    if len(chunks) < 2:
        return text, None
    kept = []
    for chunk in chunks:
        if any(_near_repeat(prev, chunk) for prev in kept):
            continue
        kept.append(chunk)
    if len(kept) == len(chunks):
        return text, None
    return (prefix + ''.join(kept)).rstrip(), 'headings'


def heading_repeats(text):
    return len(_CRITERIA_HEADING_LINE.findall(text or '')) > 1


def drop_leading_same_heading(text):
    """Первая строка «Критерии оценивания» — дубль нашего заголовка раздела.

    Решение владельца 30.10 (вопрос 3): убирается ТОЛЬКО строка с этими
    самыми словами; «Схема проверки» и прочие заголовки остаются.
    """
    return _LEADING_SAME_HEADING.sub('', text, count=1).lstrip('\n')


# ── задание пакета → поля задачи ─────────────────────────────────────────

def _points(raw):
    if raw is None or str(raw).strip() == '':
        return None
    return Decimal(str(raw).strip().replace(',', '.'))


def _paragraphs(text):
    return [p.strip() for p in re.split(r'\n\s*\n', text or '') if p.strip()]


def missing_section(task):
    """Абзацы вступления раздела теста, которых в условии ещё нет.

    ⚠️ Решение владельца 30.10: текст вступления выбрасывать нельзя — там
    бывает условие для всех вопросов раздела. Чего нет в условии, то
    дописывается в его конец; что есть — не трогается.
    """
    statement = ws(task['statement_md'])
    return [p for p in _paragraphs(task.get('section_md'))
            if ws(p) not in statement]


def figure_marker(tikz_hash):
    return '[[FIGURE:{}]]'.format(tikz_hash)


class FigureFiles:
    """Файлы рисунков пакета: хеш содержимого и байты, с кэшем по пути."""

    def __init__(self, root):
        self.root = root
        self._sha = {}

    def path(self, rel):
        return os.path.join(self.root, *rel.split('/'))

    def content_sha(self, rel):
        if rel not in self._sha:
            with open(self.path(rel), 'rb') as fh:
                self._sha[rel] = hashlib.sha256(fh.read()).hexdigest()
        return self._sha[rel]

    def read(self, rel):
        with open(self.path(rel), 'rb') as fh:
            return fh.read()


def uses_options(task):
    """Тест, варианты которого становятся пунктами задачи (с отметкой «верно»)."""
    test = task.get('test') or {}
    return bool(test) and test.get('kind') != 'broken' and bool(test.get('options'))


def build_problem(task, files):
    """Поля новой задачи из задания пакета: dict, без записи в базу.

    Раскладка — отчёт фазы 0 и ответы владельца 30.10:
    - `statement` — условие; затем метки рисунков условия; затем абзацы
      вступления раздела, которых в условии нет;
    - `solution` — решение, метки рисунков решения, затем раздел
      «## Критерии оценивания» с почищенными критериями;
    - `answer` — ответ, а если пуст — ключ теста;
    - тест — варианты пунктами (`answer='верно'` у верных), пункты пакета —
      только если вариантов нет;
    - `tables`, `bank` и вид теста `broken` в задачу не попадают.

    ⚠️ Рисунок без места в тексте: метка ставится в КОНЕЦ поля. Пакет не
    знает, где рисунок стоял, — так же делает `corpus_legacy_figures`.
    """
    test = task.get('test') or {}
    reasons = []
    figures, statement_marks, solution_marks, statement_shas = [], [], [], []
    for fig in task.get('figures') or []:
        if not fig.get('path'):
            if REASON_NO_FIGURE_FILE not in reasons:
                reasons.append(REASON_NO_FIGURE_FILE)
            continue
        tikz_hash = hashlib.sha256(fig['path'].encode('utf-8')).hexdigest()
        field = 'solution' if fig.get('field') == 'solution' else 'statement'
        figures.append({'field': field, 'path': fig['path'],
                        'tikz_hash': tikz_hash})
        if field == 'statement':
            statement_marks.append(figure_marker(tikz_hash))
            statement_shas.append(files.content_sha(fig['path']))
        else:
            solution_marks.append(figure_marker(tikz_hash))

    section = missing_section(task)
    pieces = [task['statement_md'].strip()] + statement_marks + section
    statement = '\n\n'.join(p for p in pieces if p)

    criteria, rule = clean_criteria(task.get('criteria_md') or '')
    criteria = (criteria or '').strip()
    without_heading = drop_leading_same_heading(criteria).strip()
    solution = '\n\n'.join(p for p in [(task.get('solution_md') or '').strip()]
                           + solution_marks if p)
    if without_heading:
        solution = '\n\n'.join(p for p in [solution, CRITERIA_HEADING,
                                           without_heading] if p)

    if uses_options(task):
        parts = [{'label': (o.get('label') or '')[:10],
                  'statement': o.get('text') or '',
                  'answer': 'верно' if o.get('correct') else '',
                  'points': None}
                 for o in test['options']]
        if len(test['options']) < len(task.get('parts') or []):
            reasons.append(REASON_FEWER_OPTIONS)
    else:
        parts = [{'label': (p.get('label') or '')[:10],
                  'statement': p.get('text') or '', 'answer': '',
                  'points': _points(p.get('points'))}
                 for p in task.get('parts') or []]

    answer = (task.get('answer') or '').strip() or (test.get('key') or '').strip()
    return {
        'title': (task.get('title') or '')[:300],
        'statement': statement,
        'answer': answer,
        'solution': solution,
        'problem_type': PROBLEM_TYPES.get(test.get('kind'), '') if test else '',
        'parts': parts,
        'figures': figures,
        'identity': _identity(task, statement_shas, section, parts),
        'section_added': len(section),
        'criteria_rule': rule,
        'heading_dropped': without_heading != criteria,
        'has_criteria': bool(without_heading),
        'extra_reasons': reasons,
    }


def _identity(task, statement_shas, section, parts):
    """Ключ «та же задача» для склейки НОВЫХ задач, или None — склеивать нельзя.

    ⚠️ ПРАВИЛО, КОТОРОЕ СКЛЕИВАЕТ МЕНЬШЕ ВСЕГО (решение владельца 30.10).
    Склеить две разные задачи — потерять задачу молча и навсегда; две копии
    одной — дубль, его поймает дедупликация. Поэтому одна задача — только
    когда совпадают условие, пункты (с метками и отметками «верно»),
    дописанное вступление и БАЙТЫ рисунков условия, а текст сравнивается
    `normalize_for_compare` (регистр, пробелы, вид тире — и всё). Грубая
    нормализация сопоставления с банком (только буквы и цифры) для склейки
    не годится: для неё «P = 100 − 2Q» и «P = 100 + 2Q» — один текст.
    `bank.problem_id` пакета в ключ не входит вовсе.

    Пустое и очень короткое условие (< 40 букв и цифр вместе с пунктами) —
    отдельная задача всегда: «одинаковость» там ничего не доказывает.
    """
    from problems.text_dedup import normalize_for_compare as nfc
    plain = bm.norm(task['statement_md']) + bm.norm(''.join(bm.part_texts(task)))
    if len(plain) < bm.MIN_LEN:
        return None
    return json.dumps([
        nfc(task['statement_md']),
        [nfc(s) for s in section],
        [[nfc(p['label']), nfc(p['statement']), p['answer']] for p in parts],
        sorted(statement_shas),
    ], ensure_ascii=False)


def solution_flags(solution):
    """(есть ли решение, есть ли критерии) — по тексту решения ЗАДАЧИ."""
    text = solution or ''
    m = _SOLUTION_CRITERIA_START.search(text)
    if m is None:
        return bool(text.strip()), False
    return bool(text[:m.start()].strip()), bool(text[m.end():].strip())


def item_fields(task, payload, linked):
    """Поля позиции комплекта из задания (без комплекта, задачи и порядка).

    ⚠️ «ЕСТЬ РЕШЕНИЕ» И «ЕСТЬ КРИТЕРИИ» — ПО ЗАДАЧЕ, А НЕ ПО ПАКЕТУ (решение
    владельца 30.10). `solution` — решение той задачи, на которую смотрит
    позиция: у совпавшей с банком — её прежнее решение (мы его не трогаем, и
    критериев пакета в нём нет), у новой — то, что в неё запишется. Иначе
    экран пообещал бы «решение проверяет ИИ» там, где в задаче критериев нет.
    То же — «есть эталон ответа» (решение владельца 30.10, после замера:
    257 совпавших позиций с ответом в пакете смотрят на задачу без ответа):
    непустой `answer` задачи или хоть один вариант с отметкой «верно».

    `linked` — {'solution', 'has_answer'} задачи, на которую смотрит позиция.
    """
    extra_reasons = payload['extra_reasons']
    quality = task.get('quality') or {}
    reasons = list(quality.get('reasons') or [])
    reasons += [r for r in extra_reasons if r not in reasons]
    flagged = quality.get('status') == 'flagged' or bool(extra_reasons)
    has_solution, has_criteria = solution_flags(linked['solution'])
    pages = {key: task.get(key) or [] for key in (
        'source_file', 'source_pages', 'solution_pages', 'criteria_pages')}
    # Подпись, страница и пометка рисунка — сюда, в задаче им места нет
    # (решение владельца 30.10, вопрос 1). Рисунки без файла — тоже здесь.
    pages['figures'] = [{key: fig.get(key) for key in (
        'field', 'path', 'caption', 'page', 'flag', 'rejected')}
        for fig in task.get('figures') or []]
    max_score = task.get('max_score')
    return {
        'number': (task.get('number') or '')[:20],
        'task_variant': (task.get('task_variant') or '')[:20],
        'max_score': None if max_score is None else Decimal(str(max_score)),
        'quality': 'flagged' if flagged else 'clean',
        'quality_reasons': reasons,
        'has_solution': has_solution,
        'has_answer': linked['has_answer'],
        'has_criteria': has_criteria,
        'pages': pages,
        'content_hash': record_hash(task),
    }


def record_hash(task):
    raw = json.dumps(task, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


# ── план ─────────────────────────────────────────────────────────────────

def read_tasks(root, only=''):
    """[(kit_id, порядок в комплекте, задание)] по комплектам пакета."""
    out = []
    for _, data in ki.read_package(root, only):
        for order, task in enumerate(data.get('tasks') or []):
            out.append((data['kit_id'], order, task))
    keys = Counter(task['ref_key'] for _, _, task in out)
    dup = [key for key, n in keys.items() if n > 1]
    if dup:
        raise ki.KitImportError('Повторяются ref_key: {}'.format(', '.join(dup[:10])))
    return out


def read_package_bank(root):
    """Задачи банка пакета по их номеру — только запасное сито сопоставления."""
    path = os.path.join(root, 'bank', 'problems.jsonl')
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as fh:
        return {rec['id']: rec for rec in map(json.loads, fh)}


def _representative_key(entry):
    task = entry['task']
    flags = ki.task_flags(task)
    return ((task.get('quality') or {}).get('status') != 'clean',
            not flags['has_criteria'], not flags['has_solution'],
            not flags['has_answer'], entry['index'])


def make_plan(root, only='', index=None):
    """Что сделает запись — без единой записи в базу.

    `index` — готовый `BankIndex` (тесты подставляют свой); по умолчанию
    строится из базы.
    """
    from olympiads.models import OlympiadVariant, OlympiadVariantItem

    rows = read_tasks(root, only)
    variants = dict(OlympiadVariant.objects.exclude(kit_key=None)
                    .values_list('kit_key', 'id'))
    missing = sorted({kit for kit, _, _ in rows if kit not in variants})
    if missing:
        raise ki.KitImportError(
            'Комплектов нет в базе (сначала import_olympiads_kits): {}'
            .format(', '.join(missing[:10])))
    existing = {item.ref_key: item for item in OlympiadVariantItem.objects.all()}

    files = FigureFiles(root)
    package_bank = read_package_bank(root)
    entries, pending = [], []
    for index_in_package, (kit, order, task) in enumerate(rows):
        entry = {'kit': kit, 'variant_id': variants[kit], 'order': order,
                 'task': task, 'index': index_in_package,
                 'payload': build_problem(task, files),
                 'item': existing.get(task['ref_key'])}
        entries.append(entry)
        if entry['item'] is None:
            pending.append(entry)

    if pending and index is None:
        index = bm.BankIndex.from_db()
    matched = {}
    for entry in pending:
        verdict = index.match(entry['task'], package_bank)
        entry['match'] = verdict
        if verdict['problem_id']:
            matched[entry['task']['ref_key']] = verdict['problem_id']

    # Новые задачи: склейка по ключу «та же задача». Если в группе уже есть
    # позиция (прошлый прогон, другой слаг через --only) — её задача и
    # берётся, новая не заводится.
    groups = defaultdict(list)
    for entry in entries:
        ref = entry['task']['ref_key']
        if ref in matched:
            continue
        identity = entry['payload']['identity']
        key = ('id', identity) if identity is not None else ('alone', ref)
        groups[key].append(entry)
    new_groups, reused = [], {}
    for members in groups.values():
        with_item = [e for e in members if e['item'] is not None]
        if with_item:
            for e in members:
                if e['item'] is None:
                    reused[e['task']['ref_key']] = with_item[0]['item'].problem_id
            continue
        members.sort(key=_representative_key)
        new_groups.append(members)

    # Решение и эталон задачи, на которую будет смотреть позиция, — для
    # признаков позиции (решение владельца 30.10: по задаче, а не по пакету).
    for members in new_groups:
        payload = members[0]['payload']
        for e in members:
            e['linked'] = {'solution': payload['solution'],
                           'has_answer': bool(payload['answer']) or any(
                               p['answer'] == 'верно' for p in payload['parts'])}
    linked = {}
    for entry in entries:
        ref = entry['task']['ref_key']
        if entry['item'] is not None:
            linked[ref] = entry['item'].problem_id
        elif ref in matched:
            linked[ref] = matched[ref]
        elif ref in reused:
            linked[ref] = reused[ref]
    known = _linked_problems(set(linked.values()))
    for entry in entries:
        ref = entry['task']['ref_key']
        if ref in linked:
            entry['linked'] = known[linked[ref]]

    updates = []
    for entry in entries:
        item = entry['item']
        if item is not None and item.content_hash != record_hash(entry['task']):
            updates.append(entry)
    return {'entries': entries, 'matched': matched, 'reused': reused,
            'new_groups': new_groups, 'updates': updates}


def _linked_problems(ids):
    """{id: {'solution', 'has_answer'}} задач банка — порциями по 900."""
    from problems.models import Problem, ProblemPart
    ids, out = sorted(ids), {}
    for start in range(0, len(ids), 900):   # «too many SQL variables» SQLite
        chunk = ids[start:start + 900]
        marked = set(ProblemPart.objects.filter(problem_id__in=chunk,
                                                answer='верно')
                     .values_list('problem_id', flat=True))
        for pid, solution, answer in (Problem.objects.filter(id__in=chunk)
                                      .values_list('id', 'solution', 'answer')):
            out[pid] = {'solution': solution or '',
                        'has_answer': bool((answer or '').strip()) or pid in marked}
    return out


def summarize(plan):
    entries, groups = plan['entries'], plan['new_groups']
    pending = [e for e in entries if e['item'] is None]
    created_items = [item_fields(e['task'], e['payload'], e['linked'])
                     for e in pending]
    reasons = Counter(e['match']['reason'] for e in pending if 'match' in e)
    reps = [g[0]['payload'] for g in groups]
    return {
        'заданий в пакете': len(entries),
        'уже есть позиция (пропуск)': len(entries) - len(pending),
        'сопоставилось с задачами банка (заданий)': len(plan['matched']),
        'сопоставилось с задачами банка (разных задач)': len(set(plan['matched'].values())),
        'привязано к задаче прошлого прогона': len(plan['reused']),
        'новых задач будет создано': len(groups),
        'заданий в новых задачах': sum(len(g) for g in groups),
        'позиций будет создано': len(pending),
        'позиций «под вопросом»': sum(i['quality'] == 'flagged' for i in created_items),
        'из них только из-за «рисунок без файла»': sum(
            REASON_NO_FIGURE_FILE in e['payload']['extra_reasons']
            and (e['task'].get('quality') or {}).get('status') != 'flagged'
            for e in pending),
        'из них только из-за «вариантов меньше, чем пунктов»': sum(
            REASON_FEWER_OPTIONS in e['payload']['extra_reasons']
            and (e['task'].get('quality') or {}).get('status') != 'flagged'
            for e in pending),
        'новых задач с критериями в решении': sum(CRITERIA_HEADING in p['solution'] for p in reps),
        'новых задач с критериями без решения': sum(
            p['solution'].startswith(CRITERIA_HEADING) for p in reps),
        'новых задач с дописанным вступлением': sum(p['section_added'] > 0 for p in reps),
        'новых задач-тестов': sum(bool(p['problem_type']) for p in reps),
        'пунктов у новых задач': sum(len(p['parts']) for p in reps),
        'рисунков у новых задач': sum(len(p['figures']) for p in reps),
        'критерии почищены точным правилом (у новых задач)': sum(p['criteria_rule'] == 'exact' for p in reps),
        'критерии почищены неточным правилом (у новых задач)': sum(p['criteria_rule'] == 'headings' for p in reps),
        'позиций с изменившейся записью пакета': len(plan['updates']),
        'позиций «есть решение» (по задаче)': sum(i['has_solution'] for i in created_items),
        'позиций «есть критерии» (по задаче)': sum(i['has_criteria'] for i in created_items),
        'позиций «есть эталон ответа» (по задаче)': sum(i['has_answer'] for i in created_items),
        'вердикты сопоставления': dict(reasons),
    }


# ── запись ───────────────────────────────────────────────────────────────

def existing_digest(max_id):
    """Отпечаток всех задач банка с id ≤ max_id: поля, пункты, рисунки."""
    from problems.models import Problem, ProblemFigure, ProblemPart
    digest = hashlib.sha256()
    fields = ('id', 'title', 'statement', 'answer', 'solution', 'status',
              'problem_type', 'hidden_pending_review', 'human_review',
              'needs_quality_review', 'content_status', 'content_format',
              'updated_at')
    for row in (Problem.objects.filter(id__lte=max_id).order_by('id')
                .values_list(*fields).iterator(chunk_size=2000)):
        digest.update(repr(row).encode('utf-8'))
    for row in (ProblemPart.objects.filter(problem_id__lte=max_id)
                .order_by('id').values_list('id', 'problem_id', 'label',
                                            'statement', 'answer')
                .iterator(chunk_size=5000)):
        digest.update(repr(row).encode('utf-8'))
    digest.update(repr(ProblemFigure.objects.filter(problem_id__lte=max_id)
                       .count()).encode('utf-8'))
    return digest.hexdigest()


def catalog_counts():
    """Сколько задач видит НАСТОЯЩИЙ запрос каталога и подбора репетитора."""
    from catalog.filters import base_queryset
    return {'catalog': base_queryset('catalog').count(),
            'tutor': base_queryset('tutor').count()}


def apply_plan(plan, root, report):
    """Запись плана. Вызывать внутри `transaction.atomic()`."""
    from problems.corpus_converter.images import sniff_content_type
    from problems.corpus_converter.ingest import content_hash_for
    from problems.models import Problem, ProblemFigure, ProblemPart
    from olympiads.models import OlympiadVariantItem

    files = FigureFiles(root)
    problem_of = dict(plan['matched'])
    problem_of.update(plan['reused'])
    created_ids = []
    for members in plan['new_groups']:
        payload = members[0]['payload']
        problem = Problem.objects.create(
            title=payload['title'], statement=payload['statement'],
            answer=payload['answer'], solution=payload['solution'],
            problem_type=payload['problem_type'],
            status=Problem.Status.DRAFT,
            hidden_pending_review=True,
            human_review=Problem.HumanReview.NONE,
            content_format=Problem.ContentFormat.MARKDOWN,
            content_hash=content_hash_for(payload['statement']),
        )
        created_ids.append(problem.pk)
        ProblemPart.objects.bulk_create([
            ProblemPart(problem=problem, label=p['label'],
                        statement=p['statement'], answer=p['answer'],
                        points=p['points'], order=n)
            for n, p in enumerate(payload['parts'])])
        for fig in payload['figures']:
            data = files.read(fig['path'])
            content_type = sniff_content_type(data)
            if content_type is None:
                raise ki.KitImportError(
                    'Рисунок {} — не картинка по содержимому.'.format(fig['path']))
            ProblemFigure.objects.create(
                problem=problem, source_field=fig['field'],
                tikz_hash=fig['tikz_hash'], tikz_source=fig['path'],
                svg='', image_data=data, content_type=content_type)
            report.add('рисунков создано')
            report.add('байт рисунков', len(data))
        report.add('пунктов создано', len(payload['parts']))
        for entry in members:
            problem_of[entry['task']['ref_key']] = problem.pk
    report.add('задач создано', len(created_ids))
    report.lists['created_problem_ids'] = created_ids

    items = []
    for entry in plan['entries']:
        if entry['item'] is not None:
            continue
        fields = item_fields(entry['task'], entry['payload'], entry['linked'])
        items.append(OlympiadVariantItem(
            variant_id=entry['variant_id'], ref_key=entry['task']['ref_key'],
            problem_id=problem_of[entry['task']['ref_key']],
            order=entry['order'], **fields))
    OlympiadVariantItem.objects.bulk_create(items, batch_size=500)
    report.add('позиций создано', len(items))

    for entry in plan['updates']:
        fields = item_fields(entry['task'], entry['payload'], entry['linked'])
        item = entry['item']
        for name, value in fields.items():
            setattr(item, name, value)
        item.order = entry['order']
        item.save()
        report.add('позиций обновлено')
    return created_ids
