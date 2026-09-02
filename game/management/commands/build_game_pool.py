"""
build_game_pool — сборка игрового пула Econ Rush из тестовых задач.

Идея: GameQuestion — это КЭШ. Команда проходит по published-тестам без флага
качества и КОНСЕРВАТИВНО отбирает пригодные для игры: короткое условие,
внятные варианты, однозначно известный правильный ответ, без
картинок/таблиц/битого LaTeX. Не уверены → не берём: качество пула важнее
размера. Контент-таблицы (Problem/ProblemPart) не изменяются.

Три извлекателя по подвиду теста (Фаза 2 сессии game-modes):
- «тест: один ответ»    → single (Блиц): варианты из подпунктов, один правильный.
- «тест: верно/неверно» → boolean (Пуля): разведка 2026-07-11 показала, что
  это НЕ пачки утверждений, а одиночные данетки — утверждение лежит в
  Problem.statement, подпункты — служебные варианты «Верно»/«Неверно».
  Конвертация 1:1: question = утверждение, options = ['Верно', 'Неверно'].
  Если варианты не строго «Верно»/«Неверно» — фолбэк в single (не гадаем).
- «тест: все верные»    → multi (Рапид): варианты как в single, правильные —
  буквы из Problem.answer (строка вида «аб»); любая несопоставленная буква
  или ноль правильных = брак.
- «тест: числовой ответ» → numeric (Классика): вопрос из statement, вариантов
  нет, correct_value = Problem.answer. Ответ обязан парситься тем же
  parse_exact_number, что проверяет ввод игрока (game/views.py) — иначе брак:
  вопрос, на который движок не сможет честно сверить ответ, в пул не попадает.
  Лимит длины условия мягче, чем у остальных типов (MAX_QUESTION_LEN_NUMERIC=700
  вместо 300) — Классика даёт 600 с на вопрос, полноценные расчётные задачи
  региона длиннее куцых тестовых вопросов из других источников.

Метаданные олимпиады (stage/year/grade) денормализуются во ВСЕ типы вопросов
из первой SourceReference задачи, где они заполнены, — под фильтр
«только регион» в игре.

Правильный ответ определяется так же, как в автопроверке ученика
(student/views.py::auto_check_submission): буква из Problem.answer против
меток ProblemPart.label (с той же нормализацией) и/или метка «верно» в
ProblemPart.answer. Если оба сигнала есть и расходятся — задача бракуется.

Запуск: ./venv/bin/python manage.py build_game_pool
        (полная пересборка: пул очищается и наполняется заново)
"""
import json
import os
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import AnswerSecondOpinion, Problem
from problems.management.commands.apply_topic_mapping import CANONICAL
from game.sources import group_of
from game.models import GameQuestion
from game.views import parse_exact_number

# Подвид теста → тип игрового вопроса.
GAME_TYPES = {
    'тест: один ответ': 'single',
    'тест: верно/неверно': 'boolean',
    'тест: все верные': 'multi',
    'тест: числовой ответ': 'numeric',
}

# Лимит поля GameQuestion.correct_value (CharField max_length=50).
MAX_NUMERIC_ANSWER_LEN = 50

# Единица ответа в SourceReference.note («…; единица ответа: %; …») —
# записывает import_vsosh_region, пул денормализует в GameQuestion.unit.
UNIT_NOTE_RE = re.compile(r'единица ответа:\s*([^;]+)')

# ⚠️ ПОРОГ ДЛИНЫ В ПУЛЕ ОДИН И МЯГКИЙ ДЛЯ ВСЕХ ТИПОВ. Раньше их было два:
# 300 для boolean/single/multi и 700 для numeric — и вопрос на 450 знаков не
# попадал в БАЗУ вовсе, хотя Рапиду с его полуминутой на ответ он подходит.
# Кто из режимов какую длину выдержит, решает отбор при выдаче
# (config.MODE_MAX_CHARS, game/views.py::_candidate_rows): там это правится
# одной константой, а здесь — пересборкой пула.
MAX_QUESTION_LEN = 700   # символов после чистки переносов
MAX_QUESTION_LEN_NUMERIC = 700
MIN_QUESTION_LEN = 15
MAX_OPTION_LEN = 160
MIN_OPTIONS = 2
MAX_OPTIONS = 6   # олимпиадные тесты бывают а–е (6 вариантов)

# Признаки контента, который в игре не отрисуется честно:
# картинки, ссылки, остатки PDF-вёрстки, псевдотаблицы. \begin{...}/\end{...}
# сюда не входят — окружения разбираются отдельно (see has_bad_environment):
# кусочные функции/матрицы допускаем и рендерим как display-формулу,
# остальные окружения (таблицы, списки и т.п.) по-прежнему брак.
BAD_CONTENT_RE = re.compile(
    r'\\includegraphics|\\hline|\\url\{|\\iffalse'
    r'|\\item\b|\\footnote'
    r'|Scoring Guide|Page \d+ of'
    r'|\|\s*\|'          # двойная вертикальная черта — псевдотаблица
)
# Корректный блок реконструированной таблицы. Его \hline и рамки {|l|c|}
# легитимны — перед общими фильтрами такие блоки вырезаем, чтобы они не
# путались с псевдотаблицами/битой вёрсткой из других источников.
GOOD_ARRAY_RE = re.compile(r'\$\$\\begin\{array\}.*?\\end\{array\}\$\$', re.S)

# Математические окружения, которые KaTeX рендерит честно (кусочные функции,
# матрицы, выровненные системы) — их не бракуем, а оставляем display-формулой.
# Любое другое \begin{...} (tabular, itemize, figure, …) — по-прежнему брак.
TALL_MATH_ENVS = {
    'cases', 'aligned', 'array', 'matrix', 'pmatrix', 'bmatrix',
    'vmatrix', 'Vmatrix', 'smallmatrix', 'gathered',
}
ENV_NAME_RE = re.compile(r'\\begin\{([a-zA-Z*]+)\}')


def has_bad_environment(text):
    """True, если в тексте есть LaTeX-окружение, которое мы не умеем
    честно отрисовать (не входит в TALL_MATH_ENVS)."""
    return any(name not in TALL_MATH_ENVS for name in ENV_NAME_RE.findall(text))


# Формула «высокая» — содержит окружение или явный перенос \\ внутри себя.
# Такую не сжимаем в строчный режим, оставляем display (см. normalize_formulas).
TALL_FORMULA_RE = re.compile(r'\\begin\{|\\\\')

DISPLAY_DOLLAR_RE = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
DISPLAY_BRACKET_RE = re.compile(r'\\\[(.*?)\\\]', re.DOTALL)
DFRAC_RE = re.compile(r'\\dfrac\b')


def normalize_formulas(text):
    """Простые display-формулы ($$...$$, \\[...\\]) без высоких конструкций
    переводим в строчный режим — иначе на компактной карточке текст рвётся
    (формула встаёт отдельным блоком посреди предложения). Формулы с
    \\begin{...} или \\-переносом внутри — высокие, их не трогаем: остаются
    display, отрисовку берёт на себя CSS карточки (game.html)."""
    def shrink(m):
        body = m.group(1)
        if TALL_FORMULA_RE.search(body):
            return m.group(0)
        return '$' + DFRAC_RE.sub(r'\\frac', body) + '$'

    text = DISPLAY_DOLLAR_RE.sub(shrink, text)
    text = DISPLAY_BRACKET_RE.sub(shrink, text)
    # \dfrac форсирует «display style» дроби даже внутри строчной формулы —
    # тоже сжимаем, даже если формула не была в display-обёртке.
    text = DFRAC_RE.sub(r'\\frac', text)
    return text


# Огрызок метки подпункта в начале вопроса: осиротевшая «)», «б)», «1.», тире,
# двоеточие — остаётся после того, как исходная метка подпункта была срезана
# импортом не до конца. Срезаем итеративно, пока не останется осмысленный текст.
LEADING_JUNK_RE = re.compile(
    r'^\s*(?:'
    r'[а-яА-Яa-zA-Z]\s*[.\)]'      # одиночная буква-метка: «б)», «a.»
    r'|\d+\s*[.\)](?!\d)'          # цифра-метка: «1.», «1)» (не «1.5»)
    r'|[)\.\-–—:]+'      # огрызок пунктуации: «)», «.», тире, «:»
    r')\s*'
)
# Висячая открывающая скобка в конце — обрезанная ссылка на сноску/рисунок.
TRAILING_JUNK_RE = re.compile(r'\s*\(+\s*$')


def strip_label_debris(text):
    """Срезает огрызки меток подпунктов в начале и висячие открывающие
    скобки в конце текста вопроса (итеративно, см. регэкспы выше)."""
    while True:
        new = LEADING_JUNK_RE.sub('', text, count=1)
        if new == text:
            break
        text = new
    while True:
        new = TRAILING_JUNK_RE.sub('', text)
        if new == text:
            break
        text = new
    return text


# Аудит-детектор: что осталось подозрительным после чистки (для отчёта).
SUSPICIOUS_START_RE = re.compile(r'^[)\.\-–—:,;]')
SUSPICIOUS_END_RE = re.compile(r'[(\-–—]\s*$')

# Вопрос ссылается на РИСУНОК/график — его в игре не показать, брак.
NEEDS_FIGURE_RE = re.compile(
    r'рисунк|диаграмм|на графике|графике ниже|схеме ниже'
    r'|figure|graph below|graph above|shown below'
    r'|на основе графика|по графику',
    re.IGNORECASE,
)
# Ссылка на ТАБЛИЦУ. Если таблица реконструирована (\begin{array} в тексте) —
# ссылка удовлетворена, вопрос берём; иначе (таблица потеряна) — брак.
NEEDS_TABLE_RE = re.compile(
    r'в таблице|в таблице ниже|таблиц[ае]|in the table|table below',
    re.IGNORECASE,
)
HAS_TABLE_RE = re.compile(r'\\begin\{array\}')

WS_RE = re.compile(r'\s+')


def dedup_norm(s):
    """Нормализация текста для ключа схлопывания повторов в пуле: регистр,
    ё→е, пробелы схлопнуты. Не трогает контентные таблицы — только сборку
    пула (см. Command.handle)."""
    return WS_RE.sub(' ', (s or '').strip().lower().replace('ё', 'е'))


def pool_dedup_key(qtype, question, options, correct_value):
    """Ключ повтора: нормализованный текст + нормализованные варианты В
    ИСХОДНОМ ПОРЯДКЕ (не сортируем — переставленные варианты это другой
    вопрос для игрока). Тип вопроса — тоже часть ключа (не смешиваем
    boolean/single с случайно совпавшими вариантами «Верно»/«Неверно»).
    numeric: вариантов нет, поэтому в ключ обязательно входит correct_value —
    иначе одинаковый текст с разными числовыми ответами (варианты одной и
    той же задачи по годам) схлопнулся бы в один вопрос с одним ответом."""
    key = (qtype, dedup_norm(question), tuple(dedup_norm(o) for o in options))
    if qtype == 'numeric':
        key = key + (dedup_norm(correct_value),)
    return key


def pool_dedup_wins(candidate, incumbent):
    """True, если candidate должен вытеснить incumbent при совпадении ключа:
    более свежий year побеждает; при равенстве (в т.ч. оба без year) —
    меньший problem_id."""
    cy = candidate.year or -1
    iy = incumbent.year or -1
    if cy != iy:
        return cy > iy
    return candidate.problem_id < incumbent.problem_id


# Латинские двойники кириллических букв-меток. В ответах Сборника АА
# встречается латинская «a» при кириллических метках «а, б, в, г»: на глаз
# буквы неразличимы, а по коду это разные символы, и сопоставление рушилось.
# Замер 2026-09-02: так терялись 6 задач АА («aг», «aбг», «a» дважды и др.),
# причём каждая с виду выглядела правильной. Чиним извлекатель, а не
# пропускаем задачу.
# Только НЕОТЛИЧИМЫЕ на глаз пары. Похожие, но различимые («m» и «м»,
# «h» и «н») сюда не входят: подменять их значило бы гадать.
LATIN_LOOKALIKES = str.maketrans({
    'a': 'а', 'e': 'е', 'o': 'о', 'c': 'с', 'p': 'р', 'x': 'х', 'y': 'у',
})


def normalize_label(s):
    """Нормализация метки/ответа — 1-в-1 как в student.views.auto_check_submission,
    плюс сведение латинских двойников к кириллице (см. LATIN_LOOKALIKES)."""
    if not s:
        return ''
    cleaned = s.lower().strip().rstrip('.').rstrip(')').strip()
    return cleaned.translate(LATIN_LOOKALIKES)


def clean_text(s):
    """Схлопывает PDF-переносы и лишние пробелы в одну строку."""
    return WS_RE.sub(' ', s or '').strip()


def dollars_balanced(text):
    """Чётное ли число неэкранированных $ (парность формул KaTeX)."""
    unescaped = re.sub(r'\\\$', '', text)
    return unescaped.count('$') % 2 == 0


def detect_lang(text):
    """ru, если кириллицы не меньше, чем латиницы."""
    cyr = len(re.findall(r'[а-яА-ЯёЁ]', text))
    lat = len(re.findall(r'[a-zA-Z]', text))
    return 'ru' if cyr >= lat else 'en'


def heuristic_difficulty(problem, question):
    """Сложность 1–5. В базе difficulty почти не размечен (None у большинства),
    поэтому честная эвристика: верно/неверно проще, длинные условия сложнее."""
    if problem.difficulty and 1 <= problem.difficulty <= 5:
        return problem.difficulty
    if problem.problem_type == 'тест: верно/неверно':
        return 2
    if len(question) < 120:
        return 2
    if len(question) < 200:
        return 3
    return 4


def content_reason(all_text):
    """Общие проверки качества текста. Возвращает причину брака или None."""
    # корректные array-блоки вырезаем: их \hline/рамки легитимны и не должны
    # бить по фильтрам псевдотаблиц (чужой мусор вне такого блока — ловится)
    core = GOOD_ARRAY_RE.sub(' [array] ', all_text)
    if BAD_CONTENT_RE.search(core) or has_bad_environment(core):
        return 'битый LaTeX / вёрстка'
    if NEEDS_FIGURE_RE.search(all_text):
        return 'нужен рисунок'
    # ссылка на таблицу: пускаем, только если таблица реконструирована
    if NEEDS_TABLE_RE.search(all_text) and not HAS_TABLE_RE.search(all_text):
        return 'нужна таблица'
    if not dollars_balanced(all_text):
        return 'непарные $'
    return None


def reading_length(text):
    """Длина условия для лимита: markup таблицы-массива (GOOD_ARRAY_RE)
    раздувал бы счёт, хотя таблица рендерится компактно — считаем как
    плейсхолдер фиксированного веса."""
    return len(GOOD_ARRAY_RE.sub('[таблица]', text))


def clean_question(problem, max_len=MAX_QUESTION_LEN, text=None):
    """Чистит текст условия. Возвращает (question, причина_брака).

    `text` подменяет problem.statement: у источников со встроенным блоком
    «Варианты ответа:» вопросом служит только его голова, без вариантов.
    """
    source_text = problem.statement if text is None else text
    question = strip_label_debris(clean_text(source_text))
    question = normalize_formulas(question)
    if len(question) < MIN_QUESTION_LEN:
        return None, 'условие слишком короткое'
    if reading_length(question) > max_len:
        return None, f'условие длиннее {max_len}'
    return question, None


# Метка следующего варианта, приклеенная внутри текста ЭТОГО варианта — признак
# того, что импорт склеил два (или больше) подпункта в один
# («…меньше конкурентного е) Фирмы могут свободно входить…»). Склейка не всегда
# ссылается на реально существующий следующий ProblemPart (буквы «е»/«ж» часто
# вообще не заведены отдельными подпунктами) — поэтому ищем ЛЮБУЮ одиночную
# кириллическую букву-метку не в начале строки, а не только метку следующего
# по списку подпункта. Цифровые метки («1)», «2)») сюда намеренно не входят —
# слишком много ложных срабатываний на формулах вида «$(...-1) \cdot 100\%$».
GLUED_LABEL_RE = re.compile(r'\S\s+[а-яё]\)\s')


def _has_glued_label(text):
    """True, если внутри текста варианта (не в самом начале) встречается
    метка вида «е) …» — см. GLUED_LABEL_RE."""
    return bool(GLUED_LABEL_RE.search(text))


def clean_options(texts):
    """Чистит варианты ответа. Возвращает (options, причина).
    Огрызки меток срезаем только у вопроса: у вариантов ответа ведущая цифра
    часто настоящее число («-$1400», «0.75%») — срезать метку там нельзя."""
    options = [normalize_formulas(clean_text(t)) for t in texts]
    if any(not o for o in options):
        return None, 'пустой вариант'
    if any(_has_glued_label(o) for o in options):
        return None, 'glued_options'
    if any(len(o) > MAX_OPTION_LEN for o in options):
        return None, 'вариант слишком длинный'
    if len(set(o.lower() for o in options)) != len(options):
        return None, 'варианты дублируются'
    return options, None


# ── Варианты, вшитые в текст условия ────────────────────────────────────────
# Так лежит SolveHub: подпунктов ProblemPart у него нет ни у одного теста
# (2724 из 2729), а варианты стоят прямо в statement блоком «Варианты
# ответа:», и Problem.answer называет правильный номером строки («3. дохода»).
# Разбор сверен с сырой выгрузкой источника 2026-09-02: 2724 из 2729 совпали
# и по составу вариантов, и по правильному ответу, ноль конфликтов; остальные
# 5 потеряли блок вариантов ещё на импорте. Без этого разбора весь SolveHub
# отсеивался с причиной «вариантов не 2–6», сколько бы типов ему ни проставили.
INLINE_MARKER = 'Варианты ответа:'
INLINE_OPTION_RE = re.compile(r'^\s*(\d{1,2})\.\s+(.*)$')


def inline_choice(problem):
    """Вопрос, варианты и позиции правильных из встроенного блока.

    Возвращает (вопрос, options, positions) либо (None, None, None).
    Нумерация обязана идти 1, 2, 3 подряд: дыра значит, что за варианты
    принято что-то другое, и тогда честнее отказаться, чем угадывать.
    """
    statement = problem.statement or ''
    if INLINE_MARKER not in statement:
        return None, None, None
    head, _, tail = statement.partition(INLINE_MARKER)
    options = []
    expected = 1
    for line in tail.splitlines():
        if not line.strip():
            continue
        matched = INLINE_OPTION_RE.match(line)
        if not matched:
            if options:            # перенос длинного варианта
                options[-1] += ' ' + line.strip()
                continue
            return None, None, None
        if int(matched.group(1)) != expected:
            return None, None, None
        options.append(matched.group(2).strip())
        expected += 1
    if not (MIN_OPTIONS <= len(options) <= MAX_OPTIONS):
        return None, None, None

    positions = []
    for line in (problem.answer or '').splitlines():
        matched = INLINE_OPTION_RE.match(line)
        if matched:
            index = int(matched.group(1)) - 1
            if 0 <= index < len(options):
                positions.append(index)
    return head.strip(), options, sorted(set(positions))


def choice_material(problem):
    """Сырьё для вопроса с вариантами: подпункты либо встроенный блок.

    Возвращает (голова_условия, тексты_вариантов, метки, позиции_правильных).
    Голова None значит «вопрос это весь statement» (путь подпунктов),
    позиции None значат «правильный определяется по меткам подпунктов».
    """
    parts = list(problem.parts.all())  # ordering = ['order', 'label']
    if MIN_OPTIONS <= len(parts) <= MAX_OPTIONS:
        return (None, [p.statement for p in parts],
                [normalize_label(p.label) for p in parts], None)
    head, options, positions = inline_choice(problem)
    if options is None:
        return None, None, None, None
    return head, options, [str(i + 1) for i in range(len(options))], positions


def extract_question(problem):
    # single: возвращает (question, options, correct_index, reason_отказа).
    # Любое сомнение → (None, None, None, 'причина').
    head, texts, labels, positions = choice_material(problem)
    if texts is None:
        return None, None, None, 'вариантов не 2–6'

    question, reason = clean_question(problem, text=head)
    if reason:
        return None, None, None, reason

    options, reason = clean_options(texts)
    if reason:
        return None, None, None, reason

    reason = content_reason(question + ' ' + ' '.join(options))
    if reason:
        return None, None, None, reason

    if positions is not None:
        # Путь встроенного блока: правильный назван номером строки в ответе.
        if len(positions) != 1:
            return None, None, None, 'правильный ответ не определён'
        return question, options, positions[0], None

    # Правильный ответ: два независимых сигнала, при конфликте — брак.
    parts = list(problem.parts.all())
    ans = normalize_label(problem.answer)
    marks = [normalize_label(p.answer) == 'верно' for p in parts]

    idx_by_label = labels.index(ans) if ans and ans in labels else None
    idx_by_mark = marks.index(True) if marks.count(True) == 1 else None

    if idx_by_label is None and idx_by_mark is None:
        return None, None, None, 'правильный ответ не определён'
    if (idx_by_label is not None and idx_by_mark is not None
            and idx_by_label != idx_by_mark):
        return None, None, None, 'конфликт сигналов правильного ответа'

    correct = idx_by_label if idx_by_label is not None else idx_by_mark
    return question, options, correct, None


# Причина-маркер: данетка с нестандартными вариантами уходит в single.
BOOLEAN_FALLBACK = 'варианты не «Верно»/«Неверно»'


def extract_boolean(problem):
    """boolean: возвращает (question, correct_index, reason_отказа).
    Утверждение — в Problem.statement, подпункты должны быть строго
    «Верно»/«Неверно» (иначе BOOLEAN_FALLBACK → задача уйдёт в single).
    correct_index: 0 = «Верно», 1 = «Неверно» — канонический порядок options,
    независимо от порядка подпунктов в задаче."""
    parts = list(problem.parts.all())
    stmts = [normalize_label(p.statement) for p in parts]
    if not parts:
        # Данетка без подпунктов: утверждение это всё условие, а «Верно» или
        # «Неверно» стоит прямо в Problem.answer. Так лежат 531 данетка
        # SolveHub; с подпунктами их не сравнить, потому что подпунктов нет.
        plain = normalize_label(problem.answer)
        if plain not in ('верно', 'неверно'):
            return None, None, BOOLEAN_FALLBACK
        question, reason = clean_question(problem)
        if reason:
            return None, None, reason
        reason = content_reason(question)
        if reason:
            return None, None, reason
        return question, (0 if plain == 'верно' else 1), None
    if sorted(stmts) != ['верно', 'неверно']:
        return None, None, BOOLEAN_FALLBACK

    question, reason = clean_question(problem)
    if reason:
        return None, None, reason
    reason = content_reason(question)
    if reason:
        return None, None, reason

    # Правильный подпункт — по букве ответа (метка «верно» в part.answer у
    # этого подвида не встречается, но сигнал конфликтует — бракуем как в single).
    ans = normalize_label(problem.answer)
    labels = [normalize_label(p.label) for p in parts]
    if not ans or ans not in labels:
        return None, None, 'правильный ответ не определён'
    correct_stmt = stmts[labels.index(ans)]
    return question, (0 if correct_stmt == 'верно' else 1), None


ANSWER_SEPARATORS = set(' ,;.()')


def extract_multi(problem):
    """multi: возвращает (question, options, correct_indices, reason_отказа).
    Правильные — буквы из Problem.answer (строка вида «аб», «а, в»);
    любая буква без пары среди меток или ноль правильных = брак, не гадаем."""
    head, texts, labels, positions = choice_material(problem)
    if texts is None:
        return None, None, None, 'вариантов не 2–6'

    question, reason = clean_question(problem, text=head)
    if reason:
        return None, None, None, reason
    options, reason = clean_options(texts)
    if reason:
        return None, None, None, reason
    reason = content_reason(question + ' ' + ' '.join(options))
    if reason:
        return None, None, None, reason

    if len(set(labels)) != len(labels):
        return None, None, None, 'метки дублируются'

    if positions is not None:
        # Путь встроенного блока: правильные названы номерами строк в ответе.
        if not positions:
            return None, None, None, 'правильный ответ не определён'
        return question, options, positions, None

    letters = [ch for ch in normalize_label(problem.answer)
               if ch not in ANSWER_SEPARATORS]
    if not letters:
        return None, None, None, 'правильный ответ не определён'
    indices = set()
    for ch in letters:
        if ch not in labels:
            return None, None, None, 'буква ответа не сопоставилась с меткой'
        indices.add(labels.index(ch))
    return question, options, sorted(indices), None


def extract_numeric(problem):
    """numeric: возвращает (question, correct_value, reason_отказа).
    Вариантов нет; correct_value — точная каноническая запись из Problem.answer
    (целое, десятичное, дробь a/b). Обязана парситься parse_exact_number —
    той же функцией, что сверяет ввод игрока, — иначе брак."""
    question, reason = clean_question(problem, max_len=MAX_QUESTION_LEN_NUMERIC)
    if reason:
        return None, None, reason
    reason = content_reason(question)
    if reason:
        return None, None, reason

    value = (problem.answer or '').strip()
    if not value:
        return None, None, 'правильный ответ не определён'
    if len(value) > MAX_NUMERIC_ANSWER_LEN:
        return None, None, 'числовой ответ длиннее 50'
    if parse_exact_number(value) is None:
        return None, None, 'ответ не парсится в число'
    return question, value, None


class Command(BaseCommand):
    help = 'Пересобирает игровой пул Econ Rush (кэш GameQuestion) из тестов.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='ничего не писать: только посчитать и показать отчёт')
        parser.add_argument(
            '--audit-json', type=str, default='',
            help='выгрузить судьбу каждого кандидата в JSON (id, источник, '
                 'причина отказа) для разбора по источникам')

    def handle(self, *args, **options):
        dry = options.get('dry_run')
        canonical_set = set(CANONICAL)
        qs = (Problem.objects
              # ⚠️ БРАК, НАЙДЕННЫЙ ЧЕЛОВЕКОМ, В ИГРУ НЕ ИДЁТ. `human_review`
              # ставится по вердиктам ревьюера (см. human_review_mark);
              # это сильнее любого автоматического детектора качества.
              .exclude(human_review='defect')
              # ⚠️ `hidden_pending_review` НЕ ТРЕБУЕМ. Правило пула игры —
              # «опубликовано и без брака», как у конструктора домашки, а
              # НЕ правило каталога «только проверенное человеком». Иначе
              # 562 задачи Сборника АА и весь SolveHub не попали бы в игру
              # никогда: их просто ещё не смотрели глазами.
              .filter(status='published', needs_quality_review=False,
                      problem_type__in=GAME_TYPES)
              .prefetch_related('parts', 'topics', 'tags',
                                'source_references__source'))

        # ⚠️ СПОРНЫЙ ОТВЕТ ДЕРЖИМ ВНЕ ИГРЫ, ПОКА ЕГО НЕ ПОСМОТРЕЛ ЧЕЛОВЕК.
        # Модель отвечала на тест вслепую (answer_second_opinion), и её ответ
        # не сошёлся с банком. Это ещё не доказательство ошибки банка — но
        # неверный ключ бьёт по игроку молча: задача выглядит безупречно, а
        # жизнь снимается за верный ответ. Разобранные расхождения
        # (resolved=True) возвращаются в пул сами, пересборкой.
        disputed = set(
            AnswerSecondOpinion.objects
            .filter(agrees=False, resolved=False)
            .values_list('problem_id', flat=True))

        total = qs.count()
        self.stdout.write(f'Тестов-кандидатов: {total}')
        if disputed:
            self.stdout.write(
                f'Спорных ответов вне пула (второе мнение не разобрано): '
                f'{len(disputed)}')

        pool_by_key = {}      # ключ схлопывания -> (GameQuestion, raw_question)
        rejected = {}
        boolean_fallback = 0  # данетки с нестандартными вариантами, ушли в single
        duplicate_in_pool = 0  # схлопнуто повторов на сборке (в базе не трогаем)
        debris_fixed = []    # (problem_id, текст до чистки) — аудит Бага 2
        tall_formula = []    # (problem_id, вопрос) — аудит Бага 1

        # Судьба каждого кандидата: id -> (источник, тип, причина или None).
        # Нужна, чтобы разбирать отсев ПО ИСТОЧНИКАМ, а не общим счётчиком:
        # «правильный ответ не определён: 492» ничего не говорит о том, чей
        # это источник и чинить ли извлекатель.
        audit = {}
        current = {'id': None, 'source': '', 'type': ''}

        def reject(reason):
            rejected[reason] = rejected.get(reason, 0) + 1
            audit[current['id']] = (current['source'], current['type'], reason)

        for p in qs:
            qtype = GAME_TYPES[p.problem_type]
            first = next(iter(p.source_references.all()), None)
            current['id'] = p.id
            current['source'] = first.source.name if first else ''
            current['type'] = p.problem_type
            if p.id in disputed:
                reject('answer_disputed')
                continue
            correct_index = None
            correct_indices = None
            correct_value = ''

            if qtype == 'boolean':
                question, correct_index, reason = extract_boolean(p)
                if reason == BOOLEAN_FALLBACK:
                    # нестандартная данетка — честный одиночный выбор
                    boolean_fallback += 1
                    qtype = 'single'
                    question, opts, correct_index, reason = extract_question(p)
                else:
                    opts = ['Верно', 'Неверно']
            elif qtype == 'multi':
                question, opts, correct_indices, reason = extract_multi(p)
            elif qtype == 'numeric':
                question, correct_value, reason = extract_numeric(p)
                opts = []
            else:
                question, opts, correct_index, reason = extract_question(p)

            if reason:
                reject(reason)
                continue

            raw_question = clean_text(p.statement)
            topic_names = [t.name for t in p.topics.all()
                           if t.name in canonical_set and t.name != 'Тест']
            # Метаданные олимпиады: первая привязка к источнику, где хоть
            # что-то из stage/year/grade заполнено (у большинства задач — ни одной).
            stage, year, grade = '', None, ''
            unit = ''
            for ref in p.source_references.all():
                if ref.stage or ref.year or ref.grade:
                    stage, year, grade = ref.stage, ref.year, ref.grade
                    m = UNIT_NOTE_RE.search(ref.note or '')
                    if m:
                        unit = m.group(1).strip()
                    break
            # Источник — первая привязка задачи. Денормализуем ради фильтра
            # «источники» на стартовом экране: выбор вопроса читает пул
            # плоским values_list, а join на SourceReference дал бы дубли
            # строк у задач с несколькими привязками.
            source_id, source_group = None, ''
            first_ref = next(iter(p.source_references.all()), None)
            if first_ref is not None:
                source_id = first_ref.source_id
                source_group = group_of(first_ref.source.name)
            gq = GameQuestion(
                problem=p,
                part=None,
                question_type=qtype,
                question=question,
                options=opts,
                correct_index=correct_index,
                correct_indices=correct_indices,
                correct_value=correct_value,
                difficulty=heuristic_difficulty(p, question),
                topics=topic_names,
                lang=detect_lang(question),
                stage=stage,
                year=year,
                grade=grade,
                unit=unit if qtype == 'numeric' else '',
                source_id=source_id,
                source_group=source_group,
                # ⚠️ Теги — СПИСКОМ id, как темы списком названий. Не M2M:
                # выбор вопроса читает пул одним плоским values_list, и join
                # на теги дал бы дубли строк у задачи с тремя тегами — она
                # выпадала бы игроку втрое чаще прочих.
                tag_ids=sorted(t.id for t in p.tags.all()),
            )

            # Схлопывание повторов на сборке пула (контент-таблицы Problem/
            # ProblemPart не трогаем — только какие GameQuestion попадут в
            # итоговый кэш). Совпадение ключа → оставляем более свежий year,
            # при равенстве — меньший problem_id; проигравший считается в
            # duplicate_in_pool и не попадает в built.
            audit[p.id] = (current['source'], current['type'], None)
            key = pool_dedup_key(qtype, question, opts, correct_value)
            incumbent = pool_by_key.get(key)
            if incumbent is not None:
                duplicate_in_pool += 1
                if pool_dedup_wins(gq, incumbent[0]):
                    loser = incumbent[0].problem_id
                    pool_by_key[key] = (gq, raw_question)
                else:
                    loser = p.id
                was = audit.get(loser, ('', '', None))
                audit[loser] = (was[0], was[1], 'схлопнут повтор')
                continue
            pool_by_key[key] = (gq, raw_question)

        built = []
        for gq, raw_question in pool_by_key.values():
            if strip_label_debris(raw_question) != raw_question:
                debris_fixed.append((gq.problem_id, raw_question[:60]))
            if ENV_NAME_RE.search(gq.question + ' ' + ' '.join(gq.options)):
                tall_formula.append((gq.problem_id, gq.question[:60]))
            built.append(gq)

        if dry:
            deleted = GameQuestion.objects.filter(is_generated=False).count()
            self.stdout.write(self.style.WARNING(
                f'СУХОЙ ПРОГОН, база не тронута. Собралось бы {len(built)} '
                f'вопросов (сейчас {deleted}), схлопнуто повторов: '
                f'{duplicate_in_pool}.'))
        else:
            with transaction.atomic():
                # Сгенерированные вопросы (is_generated=True) — отдельный
                # слой кэша, ими управляют generate_game_questions и
                # purge_generated; пересборка пула из тестов их НЕ трогает.
                deleted, _ = GameQuestion.objects.filter(
                    is_generated=False).delete()
                GameQuestion.objects.bulk_create(built, batch_size=500)
            self.stdout.write(self.style.SUCCESS(
                f'Пул пересобран: {len(built)} вопросов (было {deleted}), '
                f'схлопнуто повторов: {duplicate_in_pool}.'))
        by_type = {}
        for g in built:
            key = (g.question_type, g.lang)
            by_type[key] = by_type.get(key, 0) + 1
        for qtype in ('boolean', 'single', 'multi', 'numeric'):
            ru = by_type.get((qtype, 'ru'), 0)
            en = by_type.get((qtype, 'en'), 0)
            self.stdout.write(f'  {qtype}: {ru + en} (ru {ru}, en {en})')
        self.stdout.write(f'  данеток ушло в single (нестандартные варианты): {boolean_fallback}')
        self.stdout.write('Отсев по причинам:')
        for reason, n in sorted(rejected.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f'  {reason}: {n}')

        audit_path = options.get('audit_json')
        if audit_path:
            folder = os.path.dirname(audit_path)
            if folder and not os.path.isdir(folder):
                os.makedirs(folder)
            with open(audit_path, 'w', encoding='utf-8') as fh:
                json.dump({str(pid): {'source': row[0], 'type': row[1],
                                      'reason': row[2]}
                           for pid, row in audit.items()},
                          fh, ensure_ascii=False)
            self.stdout.write(f'Разбор судьбы кандидатов: {audit_path}')

        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            f'Аудит (Баг 2) — огрызков меток срезано в начале вопроса: {len(debris_fixed)}'))
        for pid, text in debris_fixed:
            self.stdout.write(f'  #{pid}: {text!r}')

        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            f'Аудит (Баг 1) — вопросов с высокой формулой (\\begin{{...}}) в пуле: {len(tall_formula)}'))
        for pid, text in tall_formula:
            self.stdout.write(f'  #{pid}: {text!r}')
        if 0 < len(tall_formula) < 30:
            self.stdout.write(
                '  Мало — кандидаты на исключение из пула (вопрос на скорость с '
                'системой уравнений — сомнительный формат). Решение — за преподавателем.')

        self.stdout.write('')
        anomalies = [(g.problem_id, g.question[:60]) for g in built
                     if SUSPICIOUS_START_RE.match(g.question)
                     or SUSPICIOUS_END_RE.search(g.question)]
        self.stdout.write(self.style.WARNING(
            f'Аудит — оставшихся подозрительных начал/концов: {len(anomalies)}'))
        for pid, text in anomalies:
            self.stdout.write(f'  #{pid}: {text!r}')
