# -*- coding: utf-8 -*-
"""SolveHub: ответ и варианты ответа из машинных полей источника.

У SolveHub правильный ответ лежит не текстом, а структурой
`correct_answer` — JSON вида `{"type": <check_type>, "value": ...}`, форма
`value` своя у каждого из семи типов проверки. Рядом `check_options` —
варианты ответа (у типов выбора) или подписи полей (у составных).

Замер по всем 6121 записям корпуса:

| `check_type` | задач | что в `value` |
|---|---:|---|
| `uncheckable` | 2294 | `null` — ответа в источнике нет вовсе |
| `single_choice` | 1765 | индекс варианта |
| `single_freetext` | 804 | список принимаемых написаний |
| `true_false` | 538 | булево |
| `multiple_choice` | 476 | булев список по числу вариантов |
| `multiple_questions` | 243 | список значений по числу подписей |
| `matching_list` | 1 | список значений по числу подписей |

⚠️ **Индекс `single_choice` — с НУЛЯ, и это измерено, а не предположено.**
Два независимых свидетельства: (1) среди задач, где в `answer_md` дословно
встречается ровно один из вариантов, 0-база сходится у 71 задачи, 1-база —
у 5; (2) значение `0` встречается 363 раза, чего при 1-базе быть не может.
Ошибка на единицу здесь означала бы неправильный ответ у 1765 задач, поэтому
проверка сделана до, а не после импорта.
"""
from __future__ import annotations

import json

#: `level1`..`level5` -> единая шкала банка 1..5, `none` -> нет сложности.
#: Замер по корпусу: level1 861, level2 2533, level3 1182, level4 772,
#: level5 29, none 744. Шкала источника уже пятибалльная — маппинг прямой,
#: без переклейки границ.
DIFFICULTY_MAP = {
    'level1': (1, 'level1'),
    'level2': (2, 'level2'),
    'level3': (3, 'level3'),
    'level4': (4, 'level4'),
    'level5': (5, 'level5'),
    'none': (None, ''),
}

#: Варианты ответа дописываются в условие ТОЛЬКО у типов выбора: там они
#: часть вопроса, без них задача не имеет смысла (2241 задача). У
#: `multiple_questions`/`matching_list` подписи — это названия полей ответа,
#: и они не теряются: попадают в текст ответа парами «подпись: значение».
OPTIONS_IN_STATEMENT = ('single_choice', 'multiple_choice')
OPTIONS_HEADER = 'Варианты ответа:'


def _loads(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return default


def parse_options(check_options):
    """`check_options` -> список строк (в источнике это JSON-строка)."""
    value = _loads(check_options, [])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def options_block(check_type, options):
    """Варианты ответа как markdown-список для дописывания в условие.

    Пустая строка, если дописывать нечего — тогда условие не трогается."""
    if check_type not in OPTIONS_IN_STATEMENT or not options:
        return ''
    lines = [OPTIONS_HEADER, '']
    lines += [f'{i}. {text}' for i, text in enumerate(options, start=1)]
    return '\n'.join(lines)


def format_answer(correct_answer, options, warnings=None):
    """`correct_answer` (JSON-строка источника) -> текст ответа для банка.

    Ничего не выдумывает: у `uncheckable` (2294 задачи) ответа в источнике
    нет, и поле остаётся пустым. Непонятная форма — пустой ответ плюс
    предупреждение, а не догадка."""
    def warn(text):
        if warnings is not None:
            warnings.append(text)

    data = _loads(correct_answer, None)
    if not isinstance(data, dict):
        if correct_answer:
            warn(f'correct_answer не разобран как JSON: {str(correct_answer)[:80]}')
        return ''
    kind = data.get('type')
    value = data.get('value')

    if kind == 'uncheckable' or value is None:
        return ''

    if kind == 'true_false':
        return 'Верно' if value else 'Неверно'

    if kind == 'single_choice':
        if not isinstance(value, int) or not (0 <= value < len(options)):
            warn(f'single_choice: индекс {value!r} вне списка из {len(options)} вариантов')
            return ''
        # Нумерация в тексте — с единицы, как её видит человек в
        # options_block(); индекс источника — с нуля (см. docstring модуля).
        return f'{value + 1}. {options[value]}'

    if kind == 'multiple_choice':
        if not isinstance(value, list) or len(value) != len(options):
            warn(f'multiple_choice: {len(value) if isinstance(value, list) else "?"} '
                 f'флагов против {len(options)} вариантов')
            return ''
        chosen = [f'{i}. {text}' for i, (text, flag)
                  in enumerate(zip(options, value), start=1) if flag]
        if not chosen:
            warn('multiple_choice: ни один вариант не отмечен верным')
        return '\n'.join(chosen)

    if kind == 'single_freetext':
        if isinstance(value, list):
            # Все принимаемые написания сохраняются: это разные формы
            # одного ответа («70,71» / «70.71%»), выбрасывать их —
            # терять то, что источник считает верным.
            seen = []
            for item in value:
                text = str(item).strip()
                if text and text not in seen:
                    seen.append(text)
            return ' / '.join(seen)
        return str(value).strip()

    if kind in ('multiple_questions', 'matching_list'):
        if not isinstance(value, list):
            warn(f'{kind}: value не список')
            return ''
        lines = []
        for i, item in enumerate(value):
            label = options[i].strip() if i < len(options) else ''
            text = str(item).strip()
            lines.append(f'{label} {text}'.strip() if label else text)
        if len(value) != len(options):
            warn(f'{kind}: {len(value)} значений против {len(options)} подписей')
        return '\n'.join(line for line in lines if line)

    warn(f'неизвестный check_type: {kind!r}')
    return ''
