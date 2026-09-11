# -*- coding: utf-8 -*-
"""Фаза 2: разметка пула двумя судьями из разных семейств.

Карточка кандидата, пачка, инструкция и разбор ответа — здесь. Сам прогон
и учёт денег — в `run_judges.py`; так карточку можно проверить тестами
без единого вызова модели.

Критерий один и тот же для обоих судей и совпадает со шкалой владельца:
2 годится, 1 спорно, 0 не годится.
"""
import json

BATCH = 25

#: ⚠️ Схема пригодна для СТРОГОГО режима OpenAI: объект с произвольными
#: ключами там не выразить, поэтому ответ — массив пар внутри «rows».
#: Одинаковая форма у всех судей: разные формы означали бы разный разбор.
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
    'Ты оцениваешь, подходит ли задача под поисковый запрос преподавателя '
    'олимпиадной экономики.\n'
    'Годится — репетитор, написавший этот запрос, взял бы задачу в листок '
    'без оговорок.\n'
    'Для КАЖДОГО кандидата верни score: 2 — годится, 1 — спорно, '
    '0 — не годится.\n'
    'Верни ровно по одной строке на каждого кандидата, id переписывай '
    'без изменений. Ничего не пропускай и ничего не добавляй.'
)

STATEMENT_CHARS = 600
FIELD_CHARS = 300


def card(row):
    """Карточка кандидата для судьи.

    Условие обрезано 600 знаками намеренно: судье нужно узнать задачу, а
    не решить её, а полный текст на 141 кандидата умножил бы вход впятеро.
    """
    parts = [
        'id: %s' % row['id'],
        'тема: %s' % ', '.join(row.get('topics') or []),
        'теги: %s' % ', '.join(row.get('tags') or []),
        'понятия: %s' % ', '.join(row.get('concepts') or []),
        'тип: %s' % (row.get('problem_type') or ''),
        'сложность: %s' % (row.get('difficulty') if row.get('difficulty')
                           is not None else ''),
        'заголовок: %s' % (row.get('title') or ''),
        'дано: %s' % (row.get('given') or '')[:FIELD_CHARS],
        'найти: %s' % (row.get('find') or '')[:FIELD_CHARS],
        'условие: %s' % (row.get('statement') or '')[:STATEMENT_CHARS],
    ]
    return '\n'.join(parts)


def batches(ids, size=BATCH):
    """Пул одного запроса → пачки по `size` кандидатов."""
    return [ids[i:i + size] for i in range(0, len(ids), size)]


def user_text(query, rows):
    """Текст запроса пользователя: формулировка плюс карточки пачки."""
    cards = '\n\n'.join(card(row) for row in rows)
    return 'ЗАПРОС ПРЕПОДАВАТЕЛЯ: %s\n\nКАНДИДАТЫ:\n\n%s' % (query, cards)


def parse_verdicts(data, expected_ids):
    """Ответ модели → {id: метка}. Пропуски и мусор названы, а не скрыты.

    Возвращает `(метки, пропущенные, лишние)`. Пропущенный кандидат НЕ
    получает метку по умолчанию: «модель про него не сказала» и «модель
    сказала ноль» — разные утверждения, и заполнять первое вторым значит
    портить разметку молча.
    """
    labels, extra = {}, []
    expected = set(expected_ids)
    for key, value in data.items():
        try:
            pid = int(key)
            score = int(value)
        except (TypeError, ValueError):
            extra.append(key)
            continue
        if pid not in expected:
            extra.append(key)
            continue
        labels[pid] = max(0, min(2, score))
    missing = [pid for pid in expected_ids if pid not in labels]
    return labels, missing, extra


#: Три правила слияния меток двух судей (решение владельца 10.09.2026).
#: Основным становится то, у которого согласие с ручной разметкой
#: владельца по шкале «годится / не годится» окажется выше; два других
#: идут в отчёт строками чувствительности. Если выводы от правила не
#: зависят, это надо показать числами, а не утверждать.
MERGE_RULES = ('согласие', 'мягкое', 'строгое')


def _merged_label(a, b, rule):
    if rule == 'согласие':
        # Годится, только когда согласны оба; спор превращается в «спорно».
        if a == 2 and b == 2:
            return 2
        return 0 if (a == 0 and b == 0) else 1
    if rule == 'мягкое':
        # Хватает одного «годится»; «не годится» — только при согласии.
        if a == 2 or b == 2:
            return 2
        return 0 if (a == 0 and b == 0) else 1
    if rule == 'строгое':
        # Один «не годится» роняет пару; годится — только при двух двойках.
        if a == 0 or b == 0:
            return 0
        return 2 if (a == 2 and b == 2) else 1
    raise ValueError('Неизвестное правило слияния: %r. Допустимы: %s'
                     % (rule, ', '.join(MERGE_RULES)))


def merge(first, second, rule='согласие'):
    """Две разметки → итоговая по выбранному правилу.

    Флаг разногласия от правила НЕ зависит: он про то, разошлись ли судьи,
    а не про то, как мы этот спор разрешили. Пара, размеченная одним
    судьёй, получает его метку с пометкой `partial` — решение владельца на
    случай остановки счётчиком.
    """
    out = {}
    for pid in set(first) | set(second):
        a, b = first.get(pid), second.get(pid)
        if a is None or b is None:
            out[pid] = {'label': a if b is None else b,
                        'disagreement': False, 'partial': True}
            continue
        out[pid] = {'label': _merged_label(a, b, rule),
                    'disagreement': a != b, 'partial': False}
    return out


def agreement(machine, manual):
    """Согласие машинной разметки с ручной: точное и «годится / не годится».

    «Спорно» из второй доли выброшено с обеих сторон: сравнивать «спорно»
    судьи со «спорно» человека можно, но решение владельца принимается по
    границе годности, и именно она должна быть на виду.
    """
    common = [pid for pid in manual if pid in machine]
    if not common:
        return {'общих пар': 0}
    exact = sum(1 for pid in common if machine[pid] == manual[pid])
    binary = [(pid, machine[pid], manual[pid]) for pid in common
              if machine[pid] != 1 and manual[pid] != 1]
    binary_hit = sum(1 for _, m, h in binary if (m >= 2) == (h >= 2))
    return {
        'общих пар': len(common),
        'точное совпадение': round(exact / len(common), 3),
        'пар без «спорно»': len(binary),
        'годится / не годится': (round(binary_hit / len(binary), 3)
                                 if binary else None),
    }


def dump(rows, path):
    with open(path, 'w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
