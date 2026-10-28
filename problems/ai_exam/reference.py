"""Экзамен v1 из официального эталона ВП/МОШ (v6): отбор, ключи, сборка.

Чистые функции над строками `reference_problems_v6.jsonl`; к базе не
обращаются. Сами файлы эталона и собранный экзамен лежат ВНЕ репозитория
(ADR 0134, 0149): здесь только код, тесты — на выдуманных строках.

Два блока:

* A «Ответ числом» — ключ: список чисел по каждому пункту. Достаётся из
  поля `answer` (МОШ) или из строк «Ответ:» официального решения, и только
  если запись после чистки — одно число на сегмент (допустимы метка вида
  «L =», хвост единиц, проценты). Формула, неравенство, текст, «или»,
  диапазон — не ключ, задача в блок A не идёт.
* B «Олимпиадная задача» — полное официальное решение; оценивает судья
  (`judge.py`) по критериям или по решению и `max_score`.

Выбор из вариантов (список вариантов в условии, ответ — номер или текст
варианта, «выберите»/«отметьте»/«соотнесите») — это тест, хоть и без
номера «тест-N»: в v1 не берётся ни в A, ни в B, только считается.
"""
import hashlib
import json
import random
import re

from problems.ai_exam import numbers

SEED = 20261028
#: Сезоны, которые считаются свежими (обе записи года — ВП и МОШ).
FRESH_YEARS = ('2024/25', '2025/26', '2024/2025', '2025/2026')

#: Порядок причин исключения: считается ПЕРВАЯ сработавшая.
EXCLUDE_ORDER = ('тест', 'needs_eyes', 'numbers_ok=false', 'рисунок в условии',
                 'пустое условие', 'служебный блок', 'выбор из вариантов',
                 'нет ключа и нет решения')

#: Решение короче — не «полное официальное решение».
MIN_SOLUTION = 300
#: Отборочная задача идёт в B, только если она «длинная».
MIN_QUALIFYING_SOLUTION = 800
MIN_QUALIFYING_STATEMENT = 300
#: Короче — служебный блок (инструкция, заголовок), а не задача.
MIN_STATEMENT = 60

_SERVICE_RE = re.compile(r'^\s*(?:#+\s*)?(?:инструкция|общие указания|уважаемые участники|'
                         r'время выполнения|внимание[!:])', re.I)
#: Служебная строка посреди условия — признак склейки нескольких заданий.
_SERVICE_INSIDE_RE = re.compile(r'время выполнения задани|максимальное количество баллов', re.I)
_CHOICE_WORD_RE = re.compile(r'выбер(?:и|ите)|отметьте|соотнесите|укажите (?:все|номер)|'
                             r'какие из (?:перечисленных|приведённых|приведенных)', re.I)
_OPTION_LINE_RE = re.compile(r'^[ \t]*(?:[-•*]|\d{1,2}[.)]|[а-еa-e]\))[ \t]+(?P<text>\S.*)$', re.M)
_INDEX_LIST_RE = re.compile(r'^\[?\s*\d{1,2}(?:\s*,\s*\d{1,2})*\s*\]?$')
_ANSWER_LINE_RE = re.compile(r'^[ \t>]*(?:\*{1,2}|_)?\s*Ответы?\s*(?:\*{1,2})?\s*[:.]\s*(.*)$',
                             re.M | re.I)
#: Подвопрос в тексте условия: «А)», «б)», «2)» в начале строки (после «- »).
_SUBQUESTION_RE = re.compile(
    r'^[ \t]*(?:[-*][ \t]+)?(?:\*{1,2}|_)?(?:\(?(?:[а-гА-Гa-dA-D]|\d)\)|[а-гА-Гa-dA-D]\.[ \t])',
    re.M)
#: Вариант строкой таблицы: «| 1 | текст варианта |».
_OPTION_ROW_RE = re.compile(r'^[ \t]*\|[ \t]*(?:\d{1,2}|[а-еa-e])[ \t]*\|[ \t]*(?P<text>[^|\n]+)\|',
                            re.M)
_PART_LABEL_RE = re.compile(r'^\s*\(?(?P<label>[а-яa-z]|\d{1,2})\s*[).]\s*', re.I)
_VAR_LABEL_RE = re.compile(r'^\s*(?P<label>[A-Za-zА-Яа-я][\w{}\\^*\'’/ ]{0,14}?)\s*=\s*')
_AMBIGUOUS_RE = re.compile(r'\bили\b|\bлибо\b|\bот\s+\S+\s+до\b|\bне (?:более|менее)\b|'
                           r'\bпримерно\b|\bоколо\b|±|\.\.\.|…', re.I)
_MD_RE = re.compile(r'\*{1,2}|__')


def row_key(row):
    """Ключ задачи эталона: event_id:number:variant (уникален в v6)."""
    return '%s:%s:%s' % (row.get('event_id', ''), row.get('number', ''),
                         row.get('task_variant', '') or '')


def is_test(row):
    return str(row.get('number', '')).startswith('тест')


def is_fresh(row):
    return str(row.get('academic_year', '')) in FRESH_YEARS


def olympiad(row):
    return str(row.get('event_id', '')).split('-')[0]


def is_choice(row):
    """Выбор из вариантов: тест без номера «тест-N»."""
    statement = row.get('statement_md') or ''
    answer = _MD_RE.sub('', str(row.get('answer') or '')).strip()
    if _CHOICE_WORD_RE.search(statement):
        return True
    options = [m.group('text').strip() for m in _OPTION_LINE_RE.finditer(statement)]
    rows = [m.group('text').strip() for m in _OPTION_ROW_RE.finditer(statement)]
    # Строки-варианты таблицы — словами, а не числами (таблица данных — не варианты).
    if len(rows) >= 3 and all(numbers.to_number(t) is None for t in rows):
        options += rows
    if len(options) < 3:
        return False
    if answer and _INDEX_LIST_RE.match(answer):
        return True
    norm = _norm_text(answer)
    if norm and any(_norm_text(o) == norm for o in options):
        return True
    # Ответ-число совпадает с вариантом-числом («- $1/10$»): это выбор.
    # Несколько чисел ответа («4; 10; 20») — все среди вариантов: «выберите все».
    values = [numbers.to_number(seg) for seg in re.split(r'[;,]\s+|;', answer) if seg.strip()]
    option_values = {numbers.to_number(o) for o in options} - {None}
    if values and None not in values and all(v in option_values for v in values):
        return True
    # Пункты — те же строки, что варианты в условии: это варианты, а не вопросы.
    parts = [_norm_text(p.get('text')) for p in row.get('parts') or []]
    return bool(parts) and all(p and p in _norm_text(statement) and len(p) < 120 for p in parts)


def _norm_text(text):
    return re.sub(r'[\s$\\.;:,]+', ' ', str(text or '')).strip().casefold()


def exclusion(row):
    """Причина исключения строки из v1 или '' (берётся как задача)."""
    if is_test(row):
        return 'тест'
    if row.get('needs_eyes'):
        return 'needs_eyes'
    if row.get('numbers_ok') is False:
        return 'numbers_ok=false'
    if row.get('figures'):
        return 'рисунок в условии'
    statement = (row.get('statement_md') or '').strip()
    if not statement:
        return 'пустое условие'
    if (len(statement) < MIN_STATEMENT or _SERVICE_RE.search(statement)
            or _SERVICE_INSIDE_RE.search(statement)):
        return 'служебный блок'
    if is_choice(row):
        return 'выбор из вариантов'
    return ''


# ── Ключ блока A ────────────────────────────────────────────────────────

def segment_value(text):
    """Сегмент ответа → {'label', 'value', 'unit', 'percent'} или None.

    Одно число, допустимы метка «L =» в начале и хвост единиц/процент.
    Формула, неравенство, «или», диапазон, коэффициент при букве — None.
    """
    s = _MD_RE.sub('', str(text or '')).strip().rstrip('.;,').strip()
    if not s or _AMBIGUOUS_RE.search(s):
        return None
    s = s.replace('$', '').strip()
    label = ''
    match = _VAR_LABEL_RE.match(s)
    if match:
        label = match.group('label').strip()
        s = s[match.end():]
        if '=' in s:
            return None
    proposal = numbers.propose_key(s)
    if proposal['kind'] != 'exact':
        return None
    return {'label': label, 'value': proposal['value'], 'unit': proposal['unit'],
            'percent': proposal['percent']}


def _segments(text):
    """Ответ → [(метка пункта или '', текст)] по «;» и строкам."""
    out = []
    for chunk in re.split(r'[;\n]+', str(text or '')):
        chunk = _MD_RE.sub('', chunk).strip()
        if not chunk:
            continue
        match = _PART_LABEL_RE.match(chunk)
        if match and match.end() < len(chunk):
            out.append((match.group('label').casefold(), chunk[match.end():]))
        else:
            out.append(('', chunk))
    return out


def key_from_text(text, part_labels):
    """Запись ответа → список вопросов [{label, skip, values}] или None.

    Пункты есть — каждому свой сегмент (по метке, иначе по порядку при
    равном числе); не сошлось — None. Пунктов нет — один вопрос, сегменты —
    его числа. Хоть один сегмент не число — None: ключ должен быть
    однозначным целиком.
    """
    segments = _segments(text)
    if not segments:
        return None
    values = []
    for label, seg in segments:
        value = segment_value(seg)
        if value is None:
            return None
        values.append((label, value))
    labels = [str(p).casefold() for p in part_labels]
    if not labels:
        if any(label for label, _v in values):
            return None
        return [_ask('', [v for _l, v in values])]
    if all(label for label, _v in values):
        if sorted(set(label for label, _v in values)) != sorted(set(labels)):
            return None
        return [_ask(p, [v for label, v in values if label == p]) for p in labels]
    if len(values) == len(labels) and not any(label for label, _v in values):
        return [_ask(p, [v]) for p, (_l, v) in zip(labels, values)]
    return None


def _ask(label, values):
    return {'label': label, 'skip': False,
            'values': [dict(v, tol='') for v in values]}


def answer_lines(solution):
    """Тексты строк «Ответ:» решения; пустая после двоеточия — следующая строка."""
    text = solution or ''
    out = []
    lines = text.split('\n')
    for number, line in enumerate(lines):
        match = _ANSWER_LINE_RE.match(line)
        if not match:
            continue
        rest = _MD_RE.sub('', match.group(1)).strip()
        if not rest:
            following = [line_ for line_ in lines[number + 1:number + 3] if line_.strip()]
            rest = following[0].strip() if following else ''
        if rest:
            out.append(rest)
    return out


def key_for(row):
    """(вопросы, источник ключа) блока A или (None, '')."""
    labels = [p.get('label') for p in row.get('parts') or [] if (p.get('label') or '').strip()]
    labels = [str(label).strip().rstrip(').').strip() for label in labels]
    # Вопросы «А) … Б) …» прямо в условии, а пунктов нет: одно число — ответ
    # лишь на один из них, ключ задачи целиком не однозначен.
    if not labels and len(_SUBQUESTION_RE.findall(row.get('statement_md') or '')) >= 2:
        return None, ''
    answer = str(row.get('answer') or '').strip()
    if answer:
        asks = key_from_text(answer, labels)
        if asks:
            return asks, 'answer'
    found = answer_lines(row.get('solution_md'))
    if len(found) == 1:
        asks = key_from_text(found[0], labels)
        if asks:
            return asks, 'solution'
    elif found and labels and len(found) == len(labels):
        asks = []
        for label, line in zip(labels, found):
            one = key_from_text(line, [])
            if not one:
                return None, ''
            asks.append(dict(one[0], label=label.casefold()))
        return asks, 'solution'
    return None, ''


def leak_keys(row):
    """Числа итогового ответа задачи B для набора «Утечка» (мягко: все числа
    поля `answer` и строк «Ответ:»). Различимость решает `leak.distinguishable`."""
    texts = [str(row.get('answer') or '')] + answer_lines(row.get('solution_md'))
    keys, seen = [], set()
    for text in texts:
        for _value, core, pct in numbers._find(text):
            canon = core.replace(',', '.')
            if (canon, pct) in seen:
                continue
            seen.add((canon, pct))
            keys.append({'label': '', 'value': canon, 'unit': '', 'percent': pct, 'tol': ''})
    return [{'label': '', 'skip': False, 'values': keys}] if keys else []


# ── Пригодность для блоков ──────────────────────────────────────────────

def b_eligible(row):
    solution = (row.get('solution_md') or '').strip()
    if len(solution) < MIN_SOLUTION:
        return False
    # Финал без критериев и без max_score всё равно годится: судья ставит по
    # шкале DEFAULT_MAX (judge.py) и опирается на официальное решение.
    if row.get('stage') == 'final':
        return True
    return (len(solution) >= MIN_QUALIFYING_SOLUTION
            and len((row.get('statement_md') or '').strip()) >= MIN_QUALIFYING_STATEMENT)


def classify(rows):
    """→ (кандидаты A, кандидаты B, счётчики исключений, годных тестов).

    Задача с числовым ключом идёт в A, даже если годится и в B: числовых
    ключей меньше, а оценка программой дешевле и надёжнее судьи.
    """
    excluded = {reason: 0 for reason in EXCLUDE_ORDER}
    pool_a, pool_b = [], []
    tests_ok = 0
    for row in rows:
        reason = exclusion(row)
        if reason == 'тест':
            if (str(row.get('answer') or '').strip() and not row.get('figures')
                    and not row.get('needs_eyes') and row.get('numbers_ok') is not False):
                tests_ok += 1
        if reason:
            excluded[reason] += 1
            continue
        asks, source = key_for(row)
        if asks:
            pool_a.append((row, asks, source))
        elif b_eligible(row):
            pool_b.append(row)
        else:
            excluded['нет ключа и нет решения'] += 1
    return pool_a, pool_b, excluded, tests_ok


# ── Отбор ───────────────────────────────────────────────────────────────

def _spread(rows, rng, keyfunc):
    """Перемешать и разложить по кругу групп: в начале — разнообразие."""
    groups = {}
    shuffled = list(rows)
    rng.shuffle(shuffled)
    for item in shuffled:
        groups.setdefault(keyfunc(item), []).append(item)
    order = sorted(groups)
    rng.shuffle(order)
    out = []
    while any(groups.values()):
        for name in order:
            if groups[name]:
                out.append(groups[name].pop(0))
    return out


def pick(items, n, fresh_share, rng, rowfunc, prefer=None, prefer_share=0.0):
    """n штук: доля свежих ≥ fresh_share (если хватает), с разнообразием по
    (олимпиада, этап, класс). prefer — признак, у которого доля ≥ prefer_share."""
    def group(item):
        row = rowfunc(item)
        return (olympiad(row), row.get('stage'), str(row.get('grade')))

    fresh = _spread([i for i in items if is_fresh(rowfunc(i))], rng, group)
    old = _spread([i for i in items if not is_fresh(rowfunc(i))], rng, group)
    need_fresh = min(len(fresh), -(-int(n * fresh_share * 100) // 100))
    chosen = _take(fresh, need_fresh, prefer, prefer_share) \
        + _take(old, n - need_fresh, prefer, prefer_share)
    if len(chosen) < n:
        rest = [i for i in fresh + old if i not in chosen]
        chosen += rest[:n - len(chosen)]
    return chosen


def _take(items, n, prefer, share):
    if prefer is None or n <= 0:
        return items[:n]
    want = -(-int(n * share * 100) // 100)
    yes = [i for i in items if prefer(i)][:want]
    no = [i for i in items if i not in yes]
    return (yes + no)[:n] if len(yes) >= want else (yes + [i for i in no])[:n]


def exam_row(row, block, asks=None, key_source=''):
    """Строка экзамена v1: всё, что нужно прогонщику и судье, без базы."""
    return {
        'key': row_key(row), 'block': block, 'fresh': is_fresh(row),
        'olympiad': olympiad(row), 'event_id': row.get('event_id'),
        'number': str(row.get('number')), 'variant': str(row.get('task_variant') or ''),
        'year': row.get('academic_year'), 'stage': row.get('stage'),
        'grade': str(row.get('grade')),
        'statement': row.get('statement_md') or '',
        'parts': [{'label': str(p.get('label') or ''), 'text': p.get('text') or ''}
                  for p in row.get('parts') or []],
        'tables': row.get('tables') or [],
        'solution': row.get('solution_md') or '',
        'criteria': row.get('criteria_md') or '',
        'max_score': row.get('max_score'),
        'answer': str(row.get('answer') or ''),
        'asks': asks if asks is not None else [],
        'key_source': key_source,
        'leak_asks': leak_keys(row) if block == 'B' else [],
    }


def build(rows, seed=SEED, n_a=60, n_b=90, safe_a=12, safe_b=18, fresh_share=0.45,
          criteria_share=0.62):
    """→ (рабочие строки, сейф, отчёт). Детерминированно при том же seed и входе."""
    rng = random.Random(seed)
    pool_a, pool_b, excluded, tests_ok = classify(rows)
    pool_a.sort(key=lambda item: row_key(item[0]))
    pool_b.sort(key=row_key)
    chosen_a = pick(pool_a, n_a, fresh_share, rng, lambda item: item[0])
    chosen_b = pick(pool_b, n_b, fresh_share, rng, lambda row: row,
                    prefer=lambda row: bool((row.get('criteria_md') or '').strip()),
                    prefer_share=criteria_share)
    rows_a = [exam_row(row, 'A', asks, source) for row, asks, source in chosen_a]
    rows_b = [exam_row(row, 'B') for row in chosen_b]
    safe = _safe_split(rows_a, safe_a, rng) + _safe_split(rows_b, safe_b, rng)
    safe_keys = {r['key'] for r in safe}
    work = [r for r in rows_a + rows_b if r['key'] not in safe_keys]
    work.sort(key=lambda r: (r['block'], r['key']))
    safe.sort(key=lambda r: (r['block'], r['key']))
    report = {'pool_a': len(pool_a), 'pool_b': len(pool_b), 'excluded': excluded,
              'tests_usable_later': tests_ok, 'rows_in': len(rows),
              'pool_a_fresh': sum(1 for item in pool_a if is_fresh(item[0])),
              'pool_b_fresh': sum(1 for row in pool_b if is_fresh(row)),
              'pool_b_criteria': sum(1 for row in pool_b if (row.get('criteria_md') or '').strip())}
    report['leak'] = leak_set(work, safe, pool_b, seed=seed + 1)
    return work, safe, report


def has_leak_key(row):
    """У строки экзамена есть число ответа, различимое на фоне условия."""
    from problems.ai_exam import leak

    task = Task(row)
    return bool(leak.distinguishable({'asks': row['leak_asks']},
                                     leak.context_numbers(task, task.parts.all())))


def leak_set(work, safe, pool_b, n=40, seed=SEED + 1):
    """Набор «Утечки»: задачи B с различимым ключом — сначала рабочие, затем
    из пула B вне экзамена и сейфа (сейф не трогается). Свой генератор —
    состав экзамена от набора «Утечки» не зависит."""
    rng = random.Random(seed)
    chosen = [r for r in work if r['block'] == 'B' and has_leak_key(r)]
    taken = {r['key'] for r in work + safe}
    extra = [exam_row(row, 'B') for row in pool_b if row_key(row) not in taken]
    extra = [r for r in extra if has_leak_key(r)]
    rng.shuffle(extra)
    chosen += extra[:max(0, n - len(chosen))]
    return {'rows': chosen[:n], 'from_work': sum(1 for r in chosen[:n] if r['key'] in taken)}


def _safe_split(rows, n, rng):
    """Сейф из блока: свежие и старые в той же доле, что в блоке."""
    fresh = [r for r in rows if r['fresh']]
    old = [r for r in rows if not r['fresh']]
    n_fresh = round(n * len(fresh) / len(rows)) if rows else 0
    return rng.sample(fresh, min(n_fresh, len(fresh))) + rng.sample(old, min(n - n_fresh, len(old)))


def dumps(rows):
    """JSONL с устойчивым порядком ключей — ради одинакового sha256."""
    return ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows)


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ── Задача как объект для промпта (без базы) ────────────────────────────

class Part(object):
    """Пункт задачи эталона так, как его ждут `solve.user_text` и чат."""

    def __init__(self, label, statement, answer='', solution=''):
        self.label = label
        self.statement = statement
        self.answer = answer
        self.solution = solution
        self.id = None


class _Empty(object):
    def all(self):
        return []


class Task(object):
    """Задача эталона «как задача банка»: условие, пункты, эталон для чата.

    Таблицы эталона уже внутри `statement_md` (поле `tables` — их число).
    Текст пункта, который уже стоит в условии (так у ВП), второй раз не
    повторяется: у пункта остаётся только метка. Рубрики нет — критерии идут
    в `solution` чата отдельным абзацем (чат видит эталон во всех режимах).
    """

    solution_needs_review = False

    def __init__(self, row):
        self.statement = row['statement']
        self.answer = row.get('answer') or ''
        self.solution = row.get('solution') or ''
        if row.get('criteria'):
            self.solution += '\n\nКРИТЕРИИ:\n' + row['criteria']
        self.id = row['key']
        self._parts = [Part(p['label'], '' if (p['text'] or '').strip() in self.statement
                            else p['text'])
                       for p in row.get('parts') or []]
        self.rubrics = _Empty()

    @property
    def parts(self):
        task = self

        class _Parts(object):
            def all(self):
                return list(task._parts)
        return _Parts()
