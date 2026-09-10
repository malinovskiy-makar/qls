# -*- coding: utf-8 -*-
"""Фаза 3: переранжирование пула моделью (системы S3 и S4).

Реранкер получает весь пул запроса пачками по 50 и выставляет каждому
кандидату балл 0–100. Условие в карточку НЕ входит: реранкер не решает,
годится ли задача вообще, он раскладывает уже отобранное, и лишние 600
знаков на кандидата умножились бы на 12 903 пары.
"""
BATCH = 50
FIND_CHARS = 200

#: Схема пригодна для строгого режима OpenAI (см. `judging.SCHEMA`).
SCHEMA = {
    'type': 'object',
    'properties': {
        'rows': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'id': {'type': 'integer'},
                    'score': {'type': 'integer'},
                },
                'required': ['id', 'score'],
                'additionalProperties': False,
            },
        },
    },
    'required': ['rows'],
    'additionalProperties': False,
}

INSTRUCTION = (
    'Ты раскладываешь найденные задачи по тому, насколько они подходят '
    'под поисковый запрос преподавателя олимпиадной экономики.\n'
    'Каждому кандидату поставь score от 0 до 100: 100 — репетитор возьмёт '
    'задачу в листок первой, 0 — задача не про то.\n'
    'Верни ровно по одной строке на каждого кандидата, id переписывай без '
    'изменений.'
)

#: Инструкция финального прохода S4: к порядку добавляется строка «почему».
FINAL_INSTRUCTION = (
    'Ты выбираешь для преподавателя олимпиадной экономики лучшие задачи '
    'под его запрос.\n'
    'Расставь кандидатов по убыванию пригодности: score от 0 до 100. '
    'Для десяти лучших добавь why — одну короткую строку, чем задача '
    'подходит именно под этот запрос. Остальным why не нужен.\n'
    'Верни ровно по одной строке на каждого кандидата.'
)

FINAL_SCHEMA = {
    'type': 'object',
    'properties': {
        'rows': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'id': {'type': 'integer'},
                    'score': {'type': 'integer'},
                    'why': {'type': ['string', 'null']},
                },
                'required': ['id', 'score', 'why'],
                'additionalProperties': False,
            },
        },
    },
    'required': ['rows'],
    'additionalProperties': False,
}


def card(row, concept_hits=None):
    """Короткая карточка кандидата.

    `concept_hits` — сколько понятий запроса нашлось у этой задачи. Строка
    появляется только для системы S4 и только у кандидатов из ноги
    S_concept: без неё эта нога неотличима от прочих, и проверить, даёт
    ли пометка выигрыш, было бы нечем.
    """
    parts = [
        'id: %s' % row['id'],
        'тема: %s' % ', '.join(row.get('topics') or []),
        'теги: %s' % ', '.join(row.get('tags') or []),
        'понятия: %s' % ', '.join(row.get('concepts') or []),
        'найти: %s' % (row.get('find') or '')[:FIND_CHARS],
        'тип: %s' % (row.get('problem_type') or ''),
        'сложность: %s' % (row.get('difficulty') if row.get('difficulty')
                           is not None else ''),
        'заголовок: %s' % (row.get('title') or ''),
    ]
    if concept_hits:
        parts.append('совпало понятий из запроса: %d' % concept_hits)
    return '\n'.join(parts)


def user_text(query, rows, hits=None):
    hits = hits or {}
    cards = '\n\n'.join(card(row, hits.get(row['id'])) for row in rows)
    return 'ЗАПРОС ПРЕПОДАВАТЕЛЯ: %s\n\nКАНДИДАТЫ:\n\n%s' % (query, cards)


def clamp(score):
    return max(0, min(100, int(score)))


def merge(chunks, all_ids=None):
    """Баллы из нескольких пачек → один порядок по убыванию.

    Кандидат, которому модель балла не дала, уходит в хвост, а не
    получает ноль молча: «не оценён» и «оценён нулём» — разные вещи, и
    первое должно быть видно в отчёте.
    """
    scores = {}
    for chunk in chunks:
        for pid, score in chunk.items():
            scores[int(pid)] = clamp(score)
    ranked = sorted(scores, key=lambda pid: (-scores[pid], pid))
    if all_ids:
        ranked += [pid for pid in all_ids if pid not in scores]
    return ranked


def parse_scores(data, expected_ids):
    """Ответ модели → ({id: балл}, не оценённые, лишние)."""
    scores, extra = {}, []
    expected = set(expected_ids)
    for key, value in data.items():
        try:
            pid, score = int(key), int(value)
        except (TypeError, ValueError):
            extra.append(key)
            continue
        if pid not in expected:
            extra.append(key)
            continue
        scores[pid] = clamp(score)
    missing = [pid for pid in expected_ids if pid not in scores]
    return scores, missing, extra
