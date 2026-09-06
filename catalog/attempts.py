"""Проверка каталожной попытки моделью: сборка запроса, схема ответа, разбор.

Этап 5 редизайна каталога (промпт владельца 04.09.2026). Ученик пишет
решение на странице задачи, эндпоинт `catalog.views.api_attempt` создаёт
`CatalogAttempt` и зовёт `check_attempt`. Проверка синхронная, с потолком
времени (ADR 0071); модель отвечает по схеме `CHECK_SCHEMA`.

⚠️ ЧТО УХОДИТ НАРУЖУ — ТОЛЬКО ЭТО: условие, подпункты, эталонное решение и
ответ (если есть), рубрика (если есть), текст ученика и текст, распознанный
с фото. Ни одного поля профиля (P0, `problems/ai/CLAUDE.md`). Пользователь
передаётся в `core.run` лишь ради лимита и журнала расхода.

⚠️ ВАЛИДАЦИЯ НА СВОЕЙ СТОРОНЕ ОБЯЗАТЕЛЬНА. Структурированный вывод не
гарантирует ни диапазонов, ни смысла: балл вне 0..10, шаг-ошибка, которого
нет в списке, «уверенность high» без эталона — всё это ловится здесь, и
ответ вне схемы делает попытку `error`, а не роняет страницу.
"""
from __future__ import annotations

from problems.ai import core

PROFILE = 'catalog_check'
MAX_SCORE = 10
MAX_STEPS = 8
VERDICTS = ('ok', 'partial', 'wrong', 'needs_human')
STEP_VERDICTS = ('ok', 'bad', 'part', 'na')
CONFIDENCES = ('high', 'medium', 'low')
SUMMARY_MAX = 300

# Балл — перечень 0..10, а не min/max: structured outputs границ не форсируют.
# ⚠️ У массива `steps` НЕТ `maxItems`: structured output Anthropic отвечает
# 400 ещё до генерации на любой `maxItems` и на `minItems` кроме 0/1 (так
# 28.08 упал пилот набора B — `build_eval_set_b.py`; сторожит
# `problems/tests/test_eval_set_b.py`). «Не больше восьми» держат профиль
# промпта и `validate()` (`steps[:MAX_STEPS]`). Найдено при синхронизации
# веток 06.09.2026.
CHECK_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['score', 'verdict', 'steps', 'first_error_step',
                 'confidence', 'needs_human', 'summary'],
    'properties': {
        'score': {'type': 'integer', 'enum': list(range(MAX_SCORE + 1))},
        'verdict': {'type': 'string', 'enum': list(VERDICTS)},
        'steps': {
            'type': 'array',
            'items': {
                'type': 'object', 'additionalProperties': False,
                'required': ['n', 'title', 'verdict', 'comment'],
                'properties': {
                    'n': {'type': 'integer'},
                    'title': {'type': 'string'},
                    'verdict': {'type': 'string', 'enum': list(STEP_VERDICTS)},
                    'comment': {'type': 'string'},
                },
            },
        },
        'first_error_step': {'type': ['integer', 'null']},
        'confidence': {'type': 'string', 'enum': list(CONFIDENCES)},
        'needs_human': {'type': 'boolean'},
        'summary': {'type': 'string'},
    },
}

NO_REFERENCE = ('ЭТАЛОННОГО РЕШЕНИЯ НЕТ: проверяй по условию и ответу; '
                'уверенность не выше medium.')
OFF_SCHEMA = ('Модель вернула ответ не по схеме. Попробуйте отправить '
              'решение ещё раз.')


def _label(part):
    return (part.label or '').strip().rstrip(').') or '?'


def build_prompt(problem, parts, student_text, ocr_text=''):
    """Пользовательская часть запроса — ВСЁ переменное, только текст задачи."""
    lines = ['УСЛОВИЕ:', (problem.statement or '').strip()]
    for part in parts:
        if (part.statement or '').strip():
            lines.append('%s) %s' % (_label(part), part.statement.strip()))

    reference = []
    solution = '' if problem.solution_needs_review else (problem.solution or '').strip()
    if solution:
        reference += ['ЭТАЛОННОЕ РЕШЕНИЕ:', solution]
    if (problem.answer or '').strip():
        reference.append('ОТВЕТ: ' + problem.answer.strip())
    for part in parts:
        part_solution = '' if problem.solution_needs_review else (part.solution or '').strip()
        if (part.answer or '').strip() or part_solution:
            reference.append('ПУНКТ %s) ОТВЕТ: %s%s' % (
                _label(part), (part.answer or '').strip(),
                ('; РЕШЕНИЕ: ' + part_solution) if part_solution else ''))
    lines += reference if reference else [NO_REFERENCE]

    criteria = []
    for rubric in problem.rubrics.all():
        for criterion in rubric.criteria.all():
            criteria.append('- %s (%s б.)%s' % (
                criterion.name, criterion.max_points,
                (': ' + criterion.description) if criterion.description else ''))
    if criteria:
        lines += ['РУБРИКА:'] + criteria

    lines += ['РЕШЕНИЕ УЧЕНИКА:', (student_text or '').strip()]
    if (ocr_text or '').strip():
        lines += ['ТЕКСТ, РАСПОЗНАННЫЙ С ФОТО:', ocr_text.strip()]
    return '\n'.join(lines)


def has_reference(problem, parts):
    """Есть ли у задачи эталон (решение или ответ) — от этого зависит потолок уверенности."""
    if (problem.answer or '').strip():
        return True
    if not problem.solution_needs_review and (problem.solution or '').strip():
        return True
    return any((part.answer or '').strip() for part in parts)


def validate(data, with_reference=True):
    """Ответ модели → нормализованный словарь; вне схемы → None."""
    if not isinstance(data, dict):
        return None
    try:
        score = data['score']
        verdict = data['verdict']
        steps = data['steps']
        first = data.get('first_error_step')
        confidence = data['confidence']
        needs_human = bool(data['needs_human'])
        summary = str(data['summary'] or '').strip()
    except (KeyError, TypeError):
        return None
    if (isinstance(score, bool) or not isinstance(score, int)
            or not 0 <= score <= MAX_SCORE):
        return None
    if verdict not in VERDICTS or confidence not in CONFIDENCES:
        return None
    if not isinstance(steps, list):
        return None
    clean_steps = []
    for step in steps[:MAX_STEPS]:
        if not isinstance(step, dict) or step.get('verdict') not in STEP_VERDICTS:
            return None
        n = step.get('n')
        if isinstance(n, bool) or not isinstance(n, int):
            return None
        clean_steps.append({'n': n, 'title': str(step.get('title') or '').strip()[:200],
                            'verdict': step['verdict'],
                            'comment': str(step.get('comment') or '').strip()[:600]})
    if first is not None:
        if isinstance(first, bool) or not isinstance(first, int):
            return None
        if clean_steps and first not in {s['n'] for s in clean_steps}:
            first = None
    if not with_reference and confidence == 'high':
        confidence = 'medium'
    if needs_human or verdict == 'needs_human':
        verdict, needs_human = 'needs_human', True
    return {'score': score, 'verdict': verdict, 'steps': clean_steps,
            'first_error_step': first, 'confidence': confidence,
            'needs_human': needs_human, 'summary': summary[:SUMMARY_MAX]}


def fill_attempt(attempt, data):
    """Записать разобранный ответ в попытку (без сохранения)."""
    if data['needs_human']:
        attempt.status = 'needs_human'
        attempt.verdict = 'needs_human'
        attempt.score = None
    else:
        attempt.status = 'checked'
        attempt.verdict = data['verdict']
        attempt.score = data['score']
    attempt.max_score = MAX_SCORE
    attempt.steps = data['steps']
    attempt.first_error_step = data['first_error_step']
    attempt.confidence = data['confidence']
    attempt.summary = data['summary']
    return attempt


def check_attempt(attempt, user, timeout=None):
    """Проверить попытку моделью и сохранить результат.

    Поднимает `core.AiUnavailable` — вызывающий превращает его в человеческое
    сообщение (ключа нет, лимит, таймаут). Ответ вне схемы попытку не
    роняет: `status='error'` и текст, что делать.
    """
    problem = attempt.problem
    parts = list(problem.parts.all())
    prompt = build_prompt(problem, parts, attempt.text, attempt.ocr_text)
    result = core.run(PROFILE, prompt, CHECK_SCHEMA, user, timeout=timeout)
    data = validate(result.data, with_reference=has_reference(problem, parts))
    if data is None:
        attempt.status = 'error'
        attempt.summary = OFF_SCHEMA
    else:
        fill_attempt(attempt, data)
    attempt.save()
    return attempt
