"""Набор «Решатель»: модель решает задачу, числа сверяются с ключом.

Системный блок — свой, через `core.run(..., system=)`: ядро `prompts.CORE`
сюда не входит, потому что оно запрещает считать («Арифметику делает
программа»), а решатель обязан считать. Имя работы в журнале —
`ai_exam_solve`, в `prompts.PROFILES` его нет намеренно.

Оценка вопроса (skip-вопросы не оцениваются): каждое число ключа совпадает
по `numbers.matches` с РАЗНЫМ числом ответа модели этого вопроса;
сопоставление жадное, подписи не учитываются, лишние числа модели не
штрафуются. Задача верна, если верны все её непропущенные вопросы. Сбой
формата — задача неверна и отдельный счётчик.
"""
import json
import re

from problems.ai_exam import numbers

PROFILE = 'ai_exam_solve'
MAX_TOKENS = 4000
#: Потолок одного вызова решателя: решение длиннее реплики чата.
TIMEOUT_SECONDS = 90

SYSTEM = """Ты решаешь задачу по олимпиадной экономике для школьников.

Реши задачу. Верни JSON: solution — краткое решение (до 1500 знаков), answers — по объекту на вопрос: ask (метка вопроса или пусто, если вопрос один), values — список {label, value}. value — одно число без единиц; проценты — числом процентов (25, а не 0,25).

Считай аккуратно, проверяй арифметику. Формулы в solution — в TeX. Язык — русский."""

SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['solution', 'answers'],
    'properties': {
        'solution': {'type': 'string'},
        'answers': {'type': 'array', 'items': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['ask', 'values'],
            'properties': {
                'ask': {'type': 'string'},
                'values': {'type': 'array', 'items': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['label', 'value'],
                    'properties': {'label': {'type': 'string'},
                                   'value': {'type': 'string'}},
                }},
            },
        }},
    },
}

_FENCE_RE = re.compile(r'^\s*```(?:json)?\s*|\s*```\s*$')


def label_of(raw):
    """Метка вопроса так же, как её печатает чат: «а)» → «а»."""
    return (raw or '').strip().rstrip(').').strip()


def _norm(label):
    return label_of(label).casefold()


def user_text(problem, parts, asks):
    """Условие, подпункты с метками и строка ВОПРОСЫ — только непропущенные."""
    lines = ['УСЛОВИЕ:', (problem.statement or '').strip()]
    for part in parts:
        if (part.statement or '').strip():
            lines.append('%s) %s' % (label_of(part.label) or '?', part.statement.strip()))
    lines.append('ВОПРОСЫ:')
    for ask in asks:
        if ask['skip']:
            continue
        name = label_of(ask['label']) or '(вся задача — ask пустой)'
        if len(ask['values']) > 1:
            name += ' — назови числа: %s' % '; '.join(v['label'] for v in ask['values'])
        lines.append('- ' + name)
    return '\n'.join(lines)


def parse(text):
    """Терпимый разбор: не разобралось — `_format_error`, деньги не теряются."""
    raw = text or ''
    try:
        data = json.loads(_FENCE_RE.sub('', raw))
    except ValueError:
        start, end = raw.find('{'), raw.rfind('}')
        try:
            data = json.loads(raw[start:end + 1]) if 0 <= start < end else None
        except ValueError:
            data = None
    if not isinstance(data, dict) or not isinstance(data.get('answers'), list):
        return {'_format_error': True, '_raw': raw}
    return data


def given_numbers(values):
    """Числа ответа модели: значение целиком, иначе все числа из записи."""
    out = []
    for item in values or []:
        raw = str(item.get('value') if isinstance(item, dict) else item).strip()
        if numbers.to_number(raw) is not None:
            out.append(raw)
        else:
            out += [core + ('%' if pct else '') for _v, core, pct in numbers._find(raw)]
    return out


def answers_by_ask(data, asks):
    """Ответ модели по вопросам: метка → список значений.

    Вопрос один — все значения ответа ему. Иначе по метке; если меток не
    узнать, а ответов столько же, сколько вопросов, — по порядку.
    """
    answers = [a for a in data.get('answers') or [] if isinstance(a, dict)]
    open_asks = [a for a in asks if not a['skip']]
    if len(asks) == 1:
        return {_norm(asks[0]['label']): [v for a in answers for v in a.get('values') or []]}
    by_label = {}
    for a in answers:
        by_label.setdefault(_norm(a.get('ask')), []).extend(a.get('values') or [])
    if not any(_norm(a['label']) in by_label for a in open_asks) and len(answers) == len(open_asks):
        return {_norm(ask['label']): a.get('values') or [] for ask, a in zip(open_asks, answers)}
    return by_label


def grade_ask(key_values, given):
    """Жадно: каждому числу ключа — своё, ещё не занятое число ответа."""
    used = set()
    for key in key_values:
        hit = next((i for i, g in enumerate(given) if i not in used
                    and numbers.matches(g, key['value'], key['percent'], key['tol'] or None)),
                   None)
        if hit is None:
            return False
        used.add(hit)
    return True


def grade(row, data):
    """{'correct', 'format_error', 'asks': [{label, ok, given}]} по строке экзамена."""
    if data.get('_format_error'):
        return {'correct': False, 'format_error': True, 'asks': []}
    by_ask = answers_by_ask(data, row['asks'])
    results = []
    for ask in row['asks']:
        if ask['skip']:
            continue
        given = given_numbers(by_ask.get(_norm(ask['label']), []))
        results.append({'label': ask['label'], 'ok': grade_ask(ask['values'], given),
                        'given': given})
    return {'correct': bool(results) and all(r['ok'] for r in results),
            'format_error': False, 'asks': results}
