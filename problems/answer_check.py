"""
Автопроверка ответов: числа — точно, тесты — по множеству вариантов.

⚠️ Числа сравниваем через `fractions.Fraction`, а НЕ через float. Тот же
подход, что в «Классике» Econ Rush (`game/views.py::parse_exact_number`):
во float `0.1 + 0.2 != 0.3`, и честный ответ ученика оказался бы неверным.
Дробь `1/3` при этом НЕ равна `0,33` — это разные числа, и делать вид, что
они равны, значит принимать неверный ответ.

ПРАВИЛО МНОЖЕСТВЕННОГО ВЫБОРА — «ВСЁ ИЛИ НИЧЕГО»: засчитывается только
полное совпадение множества выбранных вариантов с множеством правильных.
Частично верный ответ = неверный, лишний вариант = неверный, пустой ответ =
неверный. Балл при этом — ПОЛНЫЙ балл задачи, а не единица (см.
`assignment_rows.item_max_score`).

Почему «всё или ничего», а не частичное начисление. Вопрос теста ОДИН
(«какие факторы сдвигают предложение»), и ответ на него — одно множество.
Отметить два верных фактора из трёх не значит «ответить на две трети
вопроса»: пропущенный фактор — это ошибка понимания ровно того же уровня,
что и лишний. Частичное начисление к тому же немедленно требует правила
для лишних вариантов («минус за каждый лишний» уходит в отрицательные
баллы, «не считать лишние» делает выгодным отметить ВСЕ варианты сразу).
Пункты задачи «а)/б)» — другое дело, там вопросов действительно несколько,
и они считаются раздельно (`part_grading`).
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


def normalize_label(text):
    """Метка варианта к общему виду: «Б)» и «б» — одно и то же.

    Отдельно от `normalize_text`: у метки чистится ещё и хвостовая скобка,
    а десятичная запятая ей не нужна. Та же нормализация 1-в-1 повторена в
    `game/management/commands/build_game_pool.py` — там она нужна без
    Django-контекста.
    """
    if not text:
        return ''
    return str(text).lower().strip().rstrip('.').rstrip(')').strip()


def _label_set(raw):
    """«а, в» → {'а', 'в'}. Порядок отметок значения не имеет."""
    return {normalize_label(chunk) for chunk in str(raw or '').split(',')
            if normalize_label(chunk)}


def catalog_test_correct_labels(problem):
    """Множество верных меток каталожного теста.

    Источников два, и они дублируют друг друга: разметка подпунктов
    (`ProblemPart.answer == 'верно'`) и общий `Problem.answer` («а, б, г»).
    Разметка подпунктов главнее — она подробнее и именно её видит ученик;
    `answer` работает запасным, потому что размечены далеко не все задачи.
    """
    labels = {normalize_label(part.label) for part in problem.parts.all()
              if normalize_label(part.answer) == 'верно'}
    return labels or _label_set(problem.answer)


def check_catalog_test(problem, submitted_answer, multiple=None):
    """Тест каталога: (проверяемо ли автоматически, верно ли).

    `multiple` — отмечает ли ученик НЕСКОЛЬКО вариантов. Значение берётся у
    того же `assignment_rows.item_answer_form`, который рисовал ученику
    форму: проверять надо ровно то, что человек видел на экране. Не
    передали — определяем по типу задачи.

    ⚠️ Множественный выбор сравнивается КАК МНОЖЕСТВО, а не строкой. Строкой
    сравнивалось раньше, и ответ зависел от порядка отметок: «в, а» против
    эталона «а, в» считался бы неверным, хотя ученик отметил ровно то же.
    """
    ptype = (problem.problem_type or '')
    if not ptype.startswith('тест'):
        return False, False
    given_raw = (submitted_answer or '').strip()
    if not given_raw:
        # Не ответил — это ноль, а не «нечем проверить».
        return True, False

    if multiple is None:
        multiple = ptype != 'тест: один ответ' and problem.parts.exists()

    if multiple:
        correct = catalog_test_correct_labels(problem)
        if not correct:
            return False, False
        return True, correct == _label_set(given_raw)

    if problem.parts.exists():
        # Один вариант из списка — сравниваем метки.
        correct = _label_set(problem.answer)
        if not correct:
            return False, False
        return True, correct == _label_set(given_raw)

    # Тест без вариантов (числовой ответ) — обычная проверка ответа.
    if not (problem.answer or '').strip():
        return False, False
    return True, check_open_answer(problem.answer, given_raw)


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
