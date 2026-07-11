"""
Константы механики Econ Rush.

⚠️ Все значения — предмет тюнинга после живых прогонов; менять здесь,
фронтенд и API читают только отсюда.

Четыре режима (как контроли времени в шахматах): Пуля / Блиц / Рапид /
Классика. У каждого — свой тип вопросов, стартовое время и дельты за
верный/неверный/пропуск. Очки и комбо общие для всех режимов.
"""

# Режимы игры. duration — стартовый запас времени (секунд),
# time_* — дельты времени (секунд), question_type — тип GameQuestion.
MODES = {
    'bullet': {
        'title': 'Пуля',
        'question_type': 'boolean',   # данетка: Верно/Неверно
        'duration': 60,
        'time_correct': +2,
        'time_wrong': -5,
        'time_skip': -2,
    },
    'blitz': {
        'title': 'Блиц',
        'question_type': 'single',    # один из вариантов
        'duration': 120,
        'time_correct': +5,
        'time_wrong': -5,
        'time_skip': -3,
    },
    'rapid': {
        'title': 'Рапид',
        'question_type': 'multi',     # несколько из вариантов
        'duration': 300,
        'time_correct': +15,
        'time_wrong': -15,
        'time_skip': -5,
    },
    'classic': {
        'title': 'Классика',
        'question_type': 'numeric',   # числовой ответ вводом
        'duration': 600,
        'time_correct': +30,
        'time_wrong': -10,
        'time_skip': -5,
    },
}

# Режим по умолчанию (обратная совместимость: старые клиенты без ?mode=).
DEFAULT_MODE = 'blitz'

# Очки за верный ответ (до множителя) — одинаково во всех режимах.
BASE_POINTS = 100

# Комбо: длина серии верных ответов -> множитель очков.
# Серия 3..5 -> x2, 6..8 -> x3, 9+ -> x4.
# Неверный ответ рвёт серию; пропуск — НЕ рвёт.
COMBO_STEPS = [(9, 4), (6, 3), (3, 2)]


def combo_multiplier(streak):
    """Множитель очков для текущей серии верных ответов."""
    for threshold, mult in COMBO_STEPS:
        if streak >= threshold:
            return mult
    return 1
