"""
Автопроверка ответов: числа — точно, тесты — по множеству вариантов.

⚠️ Числа сравниваем через `fractions.Fraction`, а НЕ через float. Тот же
подход, что в «Классике» Econ Rush (`game/views.py::parse_exact_number`):
во float `0.1 + 0.2 != 0.3`, и честный ответ ученика оказался бы неверным.
Дробь `1/3` при этом НЕ равна `0,33` — это разные числа, и делать вид, что
они равны, значит принимать неверный ответ.

ПРАВИЛО МНОЖЕСТВЕННОГО ВЫБОРА — «ВСЁ ИЛИ НИЧЕГО»: засчитывается только
полное совпадение множества выбранных вариантов с множеством правильных.
Частично верный ответ = неверный. Половинчатые баллы обсуждаемы, но их
надо было бы объяснять ученику и учитывать в среднем балле; пока их нет,
и правило записано здесь, а не размазано по вьюхам.
"""
from fractions import Fraction

# Что считаем «десятичной запятой» и как чистим ввод.
_TRASH = ' \t '


def parse_number(text):
    """Строка → Fraction или None, если это не число.

    Понимает: целые, десятичные с точкой и запятой, простые дроби a/b,
    знак минус. Мусор — не число (None), а не ноль: «не ответил» и
    «ответил ноль» — разные вещи.
    """
    if text is None:
        return None
    value = str(text).strip().strip(_TRASH).replace('−', '-')
    for ch in _TRASH:
        value = value.replace(ch, '')
    if not value:
        return None
    value = value.replace(',', '.')
    try:
        if '/' in value:
            numerator, _, denominator = value.partition('/')
            return Fraction(int(numerator), int(denominator))
        return Fraction(value)
    except (ValueError, ZeroDivisionError, ArithmeticError):
        return None


def normalize_text(text):
    """Нормализация для строкового сравнения: пробелы, запятая, регистр."""
    if text is None:
        return ''
    value = ' '.join(str(text).split())
    return value.replace(',', '.').strip().rstrip('.').lower()


def check_open_answer(correct, given, tolerance=0):
    """Верен ли ответ на открытую задачу.

    Сначала пробуем как числа (с допуском). Если хотя бы одно из двух
    числом не является — сравниваем нормализованные строки: у части задач
    ответ словесный («вырастет»), и отказывать им в проверке незачем.
    """
    correct_number = parse_number(correct)
    given_number = parse_number(given)
    if correct_number is not None and given_number is not None:
        try:
            allowed = Fraction(str(tolerance or 0))
        except (ValueError, ArithmeticError):
            allowed = Fraction(0)
        return abs(correct_number - given_number) <= allowed
    return bool(normalize_text(correct)) and \
        normalize_text(correct) == normalize_text(given)


def check_option_answer(correct_ids, given_ids):
    """Тест: сравнение по МНОЖЕСТВУ выбранных вариантов, всё или ничего."""
    correct_set = {int(x) for x in correct_ids}
    given_set = {int(x) for x in given_ids if str(x).strip()}
    return bool(correct_set) and correct_set == given_set


def check_custom_problem(problem, submitted_answer):
    """Проверяет ответ на свою задачу репетитора.

    Возвращает (проверяемо ли автоматически, верно ли).
    Открытая задача без эталонного ответа автоматически не проверяется —
    её смотрит репетитор.
    """
    if problem.is_test:
        correct = problem.correct_option_ids()
        given = [x for x in str(submitted_answer or '').split(',')]
        return True, check_option_answer(correct, given)

    if not (problem.correct_answer or '').strip():
        return False, False
    return True, check_open_answer(problem.correct_answer, submitted_answer,
                                   problem.answer_tolerance)
