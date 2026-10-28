"""Судья «Решателя» v1 (блок B): Claude оценивает решение модели по эталону.

На входе: условие, официальное решение, критерии (или `max_score`) и
решение проверяемой модели. Ответ строго JSON (`SCHEMA`). Судья — Claude
(решение владельца 14.10.2026): другое семейство, чем проверяемые модели.

Кэш. Постоянная часть по задаче (инструкция + условие + официальное
решение + критерии) — ПЕРВЫЙ системный блок: `AnthropicProvider` ставит
`cache_control` только на него, и одну задачу судят для нескольких моделей
по одному префиксу. Решение модели — в тексте запроса.

Температура 0 — на своём экземпляре поставщика (`provider.temperature`),
её ставит прогонщик (`v1run.judge_run`, флаг `--temperature`).

Оценка: доля баллов `total / max`; «решено», если ≥ `SOLVED_SHARE`.
"""
import json
import re

from problems.ai import core

PROFILE = 'ai_exam_judge'
MAX_TOKENS = 4000
TIMEOUT_SECONDS = 180
SOLVED_SHARE = 0.8
#: Шкала, если у задачи нет ни критериев с баллами, ни max_score.
DEFAULT_MAX = 10

INSTRUCTIONS = """Ты — член жюри олимпиады по экономике для школьников. Оцени решение участника строго по официальному решению и критериям ниже.

Правила:
- Ставь баллы по пунктам задачи. Если пунктов нет — один пункт с пустой меткой на всю задачу. Сумма points_max по пунктам равна максимуму задачи.
- Верный ответ без обоснования — не полный балл. Иной путь решения, верный и обоснованный, — полный балл.
- Арифметическую ошибку, сломавшую ответ, снижай по критериям; если критериев нет — как снизило бы жюри.
- verdict: correct — полный балл за пункт, partial — часть, wrong — ноль.
- reasons — коротко, за что сняты баллы (или почему полный балл).
- quote — ДОСЛОВНАЯ цитата из решения участника (до 200 знаков), на которую опирается вердикт; нечего цитировать — пустая строка.
- confidence — high / medium / low: насколько ты уверен в оценке.
- reference_suspect — true, только если ты уверен, что ошибается САМ эталон (официальное решение или ответ); тогда в reference_reason — доказательство: расчёт или ссылка на условие. Иначе false и пустая строка.
Ответ — строго JSON по схеме."""

SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['parts', 'total', 'max', 'confidence', 'reference_suspect',
                 'reference_reason'],
    'properties': {
        'parts': {'type': 'array', 'items': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['label', 'points_awarded', 'points_max', 'verdict', 'reasons',
                         'quote'],
            'properties': {
                'label': {'type': 'string'},
                'points_awarded': {'type': 'number'},
                'points_max': {'type': 'number'},
                'verdict': {'type': 'string', 'enum': ['correct', 'partial', 'wrong']},
                'reasons': {'type': 'string'},
                'quote': {'type': 'string'},
            },
        }},
        'total': {'type': 'number'},
        'max': {'type': 'number'},
        'confidence': {'type': 'string', 'enum': ['high', 'medium', 'low']},
        'reference_suspect': {'type': 'boolean'},
        'reference_reason': {'type': 'string'},
    },
}

_FENCE_RE = re.compile(r'^\s*```(?:json)?\s*|\s*```\s*$')


def task_max(row):
    """Максимум задачи: max_score эталона, иначе DEFAULT_MAX."""
    try:
        value = float(row.get('max_score'))
        return value if value > 0 else DEFAULT_MAX
    except (TypeError, ValueError):
        return DEFAULT_MAX


def system_block(row):
    """Постоянная часть по задаче — один блок (кэшируется у Anthropic)."""
    parts = ''.join('\n%s) %s' % (p['label'], p['text']) for p in row.get('parts') or []
                    if (p.get('text') or '').strip() and p['text'].strip() not in row['statement'])
    criteria = (row.get('criteria') or '').strip()
    return '\n\n'.join([
        INSTRUCTIONS,
        'УСЛОВИЕ ЗАДАЧИ:\n' + row['statement'].strip() + parts,
        'ОФИЦИАЛЬНОЕ РЕШЕНИЕ:\n' + (row.get('solution') or '').strip(),
        ('КРИТЕРИИ ЖЮРИ:\n' + criteria) if criteria else
        'КРИТЕРИЕВ НЕТ: оценивай по официальному решению.',
        'МАКСИМУМ ЗА ЗАДАЧУ: %g баллов.' % task_max(row),
    ])


def user_text(solution_text):
    return 'РЕШЕНИЕ УЧАСТНИКА:\n' + (solution_text or '').strip()


def parse(text):
    """Терпимый разбор; не JSON или нет `parts` — `_format_error`."""
    raw = text or ''
    try:
        data = json.loads(_FENCE_RE.sub('', raw))
    except ValueError:
        start, end = raw.find('{'), raw.rfind('}')
        try:
            data = json.loads(raw[start:end + 1]) if 0 <= start < end else None
        except ValueError:
            data = None
    if not isinstance(data, dict) or not isinstance(data.get('parts'), list):
        return {'_format_error': True, '_raw': raw}
    return data


def score(data, row):
    """Вердикт судьи → {'total', 'max', 'share', 'solved'}.

    `max` — максимум задачи из эталона (судья мог ошибиться в своей сумме);
    `total` — сумма баллов по пунктам, обрезанная в [0, max]. Сумма пунктов
    расходится с `total` судьи — берётся сумма пунктов: она проверяема.
    """
    top = task_max(row)
    try:
        total = sum(float(p.get('points_awarded') or 0) for p in data.get('parts') or [])
    except (TypeError, ValueError):
        total = 0.0
    total = max(0.0, min(total, top))
    share = total / top if top else 0.0
    return {'total': round(total, 3), 'max': top, 'share': round(share, 4),
            'solved': share >= SOLVED_SHARE}


def judge(row, solution_text, provider, model, timeout=None):
    """Один вызов судьи → AiResult (данные — разобранный JSON или `_format_error`).

    Бросает `core.AiUnavailable` на отказе (расход — в `.usage`).
    """
    return core.run(PROFILE, user_text(solution_text), SCHEMA, None, max_tokens=MAX_TOKENS,
                    cache_seconds=0, check_limit=False, timeout=timeout or TIMEOUT_SECONDS,
                    provider=provider, model=model, system=[system_block(row)], parse=parse,
                    log=False, check_budget=False)
