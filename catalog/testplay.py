"""Тест в каталоге как игра: варианты, верное множество, попытки (этап 7).

Варианты — подпункты задачи (`ProblemPart`), верные метки —
`answer_check.catalog_test_correct_labels`, правило «всё или ничего» —
`answer_check.check_option_answer`. Какой строке `problem_type` какой вид
теста соответствует, знает `problems.problem_types` — одна точка правды на
весь проект; здесь эти строки НЕ повторяются. Виджет отмечает варианты, и
поэтому играются три вида из четырёх: `multi` — множественный выбор,
`single` и `boolean` — одиночный (у «верно/неверно» плитки «Верно» и
«Неверно» тоже хранятся подпунктами). Вид `numeric` вариантов не имеет
вовсе, поля для ввода короткого ответа в каталоге нет — такой тест
показывается обычной задачей. Тест без вариантов или с верными метками вне
вариантов игры тоже не получает.

Попытки не ограничены; счётчик живёт в сессии (и у гостя тоже), число
верных сообщается с третьей попытки, то есть после двух неудач
(ADR 0082). Верный ответ вошедшего фиксируется `CatalogAttempt`.
"""
from problems import answer_check, problem_types

SESSION_KEY = 'catalog_test_%d'
COUNT_FROM_ATTEMPT = 3   # с какой попытки сообщается число верных


def is_test(problem):
    """Признак теста берётся из `problems.problem_types` — одной точки правды
    на весь проект (оба словаря названий типа сразу, старый и v2)."""
    return problem_types.is_test(problem.problem_type)


def game_of(problem, parts=None):
    """Модель игры или None, если играть не во что.

    Возвращает {'multi', 'options': [{'label', 'text', 'pk'}], 'correct': set,
    'rule'}. Метки нормализованы (`normalize_label`): «Б)» и «б» — одно.
    """
    if not is_test(problem):
        return None
    parts = list(problem.parts.all()) if parts is None else list(parts)
    options = [{'label': answer_check.normalize_label(part.label),
                'text': part.statement, 'pk': part.pk}
               for part in parts if answer_check.normalize_label(part.label)]
    if not options:
        return None
    labels = {opt['label'] for opt in options}
    if len(labels) != len(options):
        return None                       # метки дублируются: не сопоставить
    correct = answer_check.catalog_test_correct_labels(problem)
    if not correct or not correct <= labels:
        return None                       # верные метки вне вариантов: брак данных
    multi = problem_types.test_kind(problem.problem_type) == problem_types.MULTI
    if not multi and len(correct) != 1:
        return None                       # одиночный выбор с несколькими верными
    return {
        'multi': multi,
        'options': options,
        'correct': correct,
        'rule': 'верных может быть несколько: отметьте все' if multi else 'выберите один',
    }


def check(game, given_labels):
    """Всё или ничего по МНОЖЕСТВУ вариантов (`check_option_answer`)."""
    by_label = {opt['label']: opt['pk'] for opt in game['options']}
    given = [by_label[label] for label in given_labels if label in by_label]
    correct = [by_label[label] for label in game['correct']]
    return answer_check.check_option_answer(correct, given)


def attempts_made(session, problem_id):
    return int(session.get(SESSION_KEY % problem_id) or 0)


def record_attempt(session, problem_id):
    """Ещё одна попытка → её порядковый номер (с единицы)."""
    n = attempts_made(session, problem_id) + 1
    session[SESSION_KEY % problem_id] = n
    return n


def reset_attempts(session, problem_id):
    if (SESSION_KEY % problem_id) in session:
        del session[SESSION_KEY % problem_id]


def solved_summary(attempt):
    return 'тест: решено с %d-й попытки' % attempt
