"""Чат по одной задаче: сборка запроса, схема ответа, режим домашки.

Этап 5 редизайна каталога (ADR 0080): один вызов `core.run('catalog_chat')`
на реплику, история — последние шесть реплик — приходит от клиента и на
сервере не хранится.

⚠️ НАРУЖУ УХОДИТ ТОЛЬКО ТЕКСТ ЗАДАЧИ И РАЗГОВОРА: условие, подпункты,
последняя попытка ученика и результат её проверки, реплики. Ни имени, ни
почты, ни класса — ничего из профиля (P0).
"""
from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from problems.ai import core

PROFILE = 'catalog_chat'
HISTORY_LIMIT = 6
MESSAGE_MAX = 2000
REPLY_MAX = 900
HOMEWORK_MODE = ('РЕЖИМ: ТОЛЬКО НАВОДЯЩИЕ ВОПРОСЫ. Задача входит в домашку '
                 'ученика: не объясняй решение, задавай вопросы и говори, где искать.')

CHAT_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['reply'],
    'properties': {'reply': {'type': 'string'}},
}

VERDICT_WORDS = {'ok': 'верно', 'partial': 'частично верно', 'wrong': 'неверно',
                 'needs_human': 'модель не поставила балл'}


def in_active_homework(user, problem):
    """Задача лежит в незакрытой домашке этого ученика.

    Домашка адресуется списком учеников (`students`) или группой; закрытой
    считается работа с прошедшим дедлайном. Тогда помощник отвечает только
    наводящими вопросами — иначе чат превращается в решебник для домашки.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    from problems.models_platform import AssignmentItem

    now = timezone.now()
    open_work = Q(assignment__deadline__isnull=True) | Q(assignment__deadline__gte=now)
    mine = Q(assignment__students=user) | Q(assignment__group__students=user)
    return AssignmentItem.objects.filter(catalog_problem=problem).filter(open_work).filter(mine).exists()


def clean_history(history):
    """Последние шесть реплик в виде [{role: me|ai, text}], мусор отброшен."""
    out = []
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        role = 'ai' if item.get('role') == 'ai' else 'me'
        text = str(item.get('text') or '').strip()[:MESSAGE_MAX]
        if text:
            out.append({'role': role, 'text': text})
    return out[-HISTORY_LIMIT:]


def build_prompt(problem, parts, message, history, last_attempt=None, homework=False):
    lines = ['УСЛОВИЕ:', (problem.statement or '').strip()]
    for part in parts:
        if (part.statement or '').strip():
            lines.append('%s) %s' % ((part.label or '').strip().rstrip(').') or '?',
                                     part.statement.strip()))
    if last_attempt is not None and (last_attempt.text or '').strip():
        lines += ['ПОСЛЕДНЯЯ ПОПЫТКА УЧЕНИКА:', last_attempt.text.strip()]
        if last_attempt.status != 'error':
            verdict = VERDICT_WORDS.get(last_attempt.verdict, '')
            result = 'РЕЗУЛЬТАТ ПРОВЕРКИ: %s' % verdict
            if last_attempt.score is not None:
                result += ', %d из %d' % (last_attempt.score, last_attempt.max_score)
            if last_attempt.first_error_step:
                title = next((s.get('title', '') for s in last_attempt.steps
                              if s.get('n') == last_attempt.first_error_step), '')
                result += '; первая ошибка в шаге %d%s' % (
                    last_attempt.first_error_step, (': ' + title) if title else '')
            if last_attempt.summary:
                result += '. ' + last_attempt.summary
            lines.append(result)
    if homework:
        lines.append(HOMEWORK_MODE)
    if history:
        lines.append('РАЗГОВОР (последние реплики):')
        for item in history:
            lines.append(('Ученик: ' if item['role'] == 'me' else 'Помощник: ') + item['text'])
    lines += ['ВОПРОС УЧЕНИКА:', message.strip()]
    return '\n'.join(lines)


def answer(problem, message, history, user, last_attempt=None):
    """Одна реплика помощника. Поднимает `core.AiUnavailable`."""
    parts = list(problem.parts.all())
    prompt = build_prompt(problem, parts, message, clean_history(history),
                          last_attempt=last_attempt,
                          homework=in_active_homework(user, problem))
    result = core.run(PROFILE, prompt, CHAT_SCHEMA, user)
    reply = str((result.data or {}).get('reply') or '').strip()
    if not reply:
        raise core.AiUnavailable('Помощник не ответил. Попробуйте спросить иначе.')
    return reply[:REPLY_MAX]
