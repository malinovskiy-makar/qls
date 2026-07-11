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
Числовые вопросы (numeric, Классика) пока не извлекаются — источник появится
с импортом региональных тестов.

Правильный ответ определяется так же, как в автопроверке ученика
(student/views.py::auto_check_submission): буква из Problem.answer против
меток ProblemPart.label (с той же нормализацией) и/или метка «верно» в
ProblemPart.answer. Если оба сигнала есть и расходятся — задача бракуется.

Запуск: ./venv/bin/python manage.py build_game_pool
        (полная пересборка: пул очищается и наполняется заново)
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem
from problems.management.commands.apply_topic_mapping import CANONICAL
from game.models import GameQuestion

# Подвид теста → тип игрового вопроса.
GAME_TYPES = {
    'тест: один ответ': 'single',
    'тест: верно/неверно': 'boolean',
    'тест: все верные': 'multi',
}

MAX_QUESTION_LEN = 300   # символов после чистки переносов
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

# Вопрос ссылается на рисунок/таблицу/график, которых в игре не будет.
NEEDS_FIGURE_RE = re.compile(
    r'рисунк|диаграмм|на графике|графике ниже|в таблице|таблиц[ае]'
    r'|figure|in the table|table below|graph below|graph above|shown below'
    r'|на основе графика|по графику',
    re.IGNORECASE,
)

WS_RE = re.compile(r'\s+')


def normalize_label(s):
    """Нормализация метки/ответа — 1-в-1 как в student.views.auto_check_submission."""
    if not s:
        return ''
    return s.lower().strip().rstrip('.').rstrip(')').strip()


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
    if BAD_CONTENT_RE.search(all_text) or has_bad_environment(all_text):
        return 'битый LaTeX / вёрстка'
    if NEEDS_FIGURE_RE.search(all_text):
        return 'нужен рисунок/таблица'
    if not dollars_balanced(all_text):
        return 'непарные $'
    return None


def clean_question(problem):
    """Чистит текст условия. Возвращает (question, причина_брака)."""
    question = strip_label_debris(clean_text(problem.statement))
    question = normalize_formulas(question)
    if len(question) < MIN_QUESTION_LEN:
        return None, 'условие слишком короткое'
    if len(question) > MAX_QUESTION_LEN:
        return None, 'условие длиннее 300'
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


def clean_options(parts):
    """Чистит варианты ответа из подпунктов. Возвращает (options, причина).
    Огрызки меток срезаем только у вопроса: у вариантов ответа ведущая цифра
    часто настоящее число («-$1400», «0.75%») — срезать метку там нельзя."""
    options = [normalize_formulas(clean_text(p.statement)) for p in parts]
    if any(not o for o in options):
        return None, 'пустой вариант'
    if any(_has_glued_label(o) for o in options):
        return None, 'glued_options'
    if any(len(o) > MAX_OPTION_LEN for o in options):
        return None, 'вариант слишком длинный'
    if len(set(o.lower() for o in options)) != len(options):
        return None, 'варианты дублируются'
    return options, None


def extract_question(problem):
    # single: возвращает (question, options, correct_index, reason_отказа).
    # Любое сомнение → (None, None, None, 'причина').
    parts = list(problem.parts.all())  # ordering = ['order', 'label']
    if not (MIN_OPTIONS <= len(parts) <= MAX_OPTIONS):
        return None, None, None, 'вариантов не 2–6'

    question, reason = clean_question(problem)
    if reason:
        return None, None, None, reason

    options, reason = clean_options(parts)
    if reason:
        return None, None, None, reason

    reason = content_reason(question + ' ' + ' '.join(options))
    if reason:
        return None, None, None, reason

    # Правильный ответ: два независимых сигнала, при конфликте — брак.
    ans = normalize_label(problem.answer)
    labels = [normalize_label(p.label) for p in parts]
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
    parts = list(problem.parts.all())
    if not (MIN_OPTIONS <= len(parts) <= MAX_OPTIONS):
        return None, None, None, 'вариантов не 2–6'

    question, reason = clean_question(problem)
    if reason:
        return None, None, None, reason
    options, reason = clean_options(parts)
    if reason:
        return None, None, None, reason
    reason = content_reason(question + ' ' + ' '.join(options))
    if reason:
        return None, None, None, reason

    labels = [normalize_label(p.label) for p in parts]
    if len(set(labels)) != len(labels):
        return None, None, None, 'метки дублируются'

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


class Command(BaseCommand):
    help = 'Пересобирает игровой пул Econ Rush (кэш GameQuestion) из тестов.'

    def handle(self, *args, **options):
        canonical_set = set(CANONICAL)
        qs = (Problem.objects
              .filter(status='published', needs_quality_review=False,
                      problem_type__in=GAME_TYPES)
              .prefetch_related('parts', 'topics'))

        total = qs.count()
        self.stdout.write(f'Тестов-кандидатов: {total}')

        built = []
        rejected = {}
        boolean_fallback = 0  # данетки с нестандартными вариантами, ушли в single
        debris_fixed = []    # (problem_id, текст до чистки) — аудит Бага 2
        tall_formula = []    # (problem_id, вопрос) — аудит Бага 1

        def reject(reason):
            rejected[reason] = rejected.get(reason, 0) + 1

        for p in qs:
            qtype = GAME_TYPES[p.problem_type]
            correct_index = None
            correct_indices = None

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
            else:
                question, opts, correct_index, reason = extract_question(p)

            if reason:
                reject(reason)
                continue

            raw_question = clean_text(p.statement)
            if strip_label_debris(raw_question) != raw_question:
                debris_fixed.append((p.id, raw_question[:60]))
            if ENV_NAME_RE.search(question + ' ' + ' '.join(opts)):
                tall_formula.append((p.id, question[:60]))
            topic_names = [t.name for t in p.topics.all()
                           if t.name in canonical_set and t.name != 'Тест']
            built.append(GameQuestion(
                problem=p,
                part=None,
                question_type=qtype,
                question=question,
                options=opts,
                correct_index=correct_index,
                correct_indices=correct_indices,
                difficulty=heuristic_difficulty(p, question),
                topics=topic_names,
                lang=detect_lang(question),
            ))

        with transaction.atomic():
            deleted, _ = GameQuestion.objects.all().delete()
            GameQuestion.objects.bulk_create(built, batch_size=500)

        self.stdout.write(self.style.SUCCESS(
            f'Пул пересобран: {len(built)} вопросов (было {deleted}).'))
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
