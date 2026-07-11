"""
build_game_pool — сборка игрового пула Econ Rush из тестовых задач.

Идея: GameQuestion — это КЭШ. Команда проходит по published-тестам без флага
качества и КОНСЕРВАТИВНО отбирает пригодные для игры: короткое условие,
2–5 внятных вариантов, однозначно известный правильный ответ, без
картинок/таблиц/битого LaTeX. Не уверены → не берём: качество пула важнее
размера. Контент-таблицы (Problem/ProblemPart) не изменяются.

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

# Подвиды тестов, пригодные для игры. «тест: все верные» исключён:
# там несколько правильных вариантов, в механику одного клика не ложится.
GAME_TYPES = ['тест: один ответ', 'тест: верно/неверно']

MAX_QUESTION_LEN = 300   # символов после чистки переносов
MIN_QUESTION_LEN = 15
MAX_OPTION_LEN = 160
MIN_OPTIONS = 2
MAX_OPTIONS = 5

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


def extract_question(problem):
    # Возвращает (question, options, correct_index, reason_отказа).
    # Любое сомнение → (None, None, None, 'причина').
    parts = list(problem.parts.all())  # ordering = ['order', 'label']
    if not (MIN_OPTIONS <= len(parts) <= MAX_OPTIONS):
        return None, None, None, 'вариантов не 2–5'

    question = strip_label_debris(clean_text(problem.statement))
    question = normalize_formulas(question)
    if len(question) < MIN_QUESTION_LEN:
        return None, None, None, 'условие слишком короткое'
    if len(question) > MAX_QUESTION_LEN:
        return None, None, None, 'условие длиннее 300'

    # Огрызки меток срезаем только у вопроса: у вариантов ответа ведущая цифра
    # часто настоящее число («-$1400», «0.75%») — срезать метку там нельзя.
    options = [normalize_formulas(clean_text(p.statement)) for p in parts]
    if any(not o for o in options):
        return None, None, None, 'пустой вариант'
    if any(len(o) > MAX_OPTION_LEN for o in options):
        return None, None, None, 'вариант слишком длинный'
    if len(set(o.lower() for o in options)) != len(options):
        return None, None, None, 'варианты дублируются'

    all_text = question + ' ' + ' '.join(options)
    if BAD_CONTENT_RE.search(all_text) or has_bad_environment(all_text):
        return None, None, None, 'битый LaTeX / вёрстка'
    if NEEDS_FIGURE_RE.search(all_text):
        return None, None, None, 'нужен рисунок/таблица'
    if not dollars_balanced(all_text):
        return None, None, None, 'непарные $'

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
        debris_fixed = []    # (problem_id, текст до чистки) — аудит Бага 2
        tall_formula = []    # (problem_id, вопрос) — аудит Бага 1
        for p in qs:
            raw_question = clean_text(p.statement)
            question, opts, correct, reason = extract_question(p)
            if reason:
                rejected[reason] = rejected.get(reason, 0) + 1
                continue
            if strip_label_debris(raw_question) != raw_question:
                debris_fixed.append((p.id, raw_question[:60]))
            if ENV_NAME_RE.search(question + ' ' + ' '.join(opts)):
                tall_formula.append((p.id, question[:60]))
            topic_names = [t.name for t in p.topics.all()
                           if t.name in canonical_set and t.name != 'Тест']
            built.append(GameQuestion(
                problem=p,
                question=question,
                options=opts,
                correct_index=correct,
                difficulty=heuristic_difficulty(p, question),
                topics=topic_names,
                lang=detect_lang(question),
            ))

        with transaction.atomic():
            deleted, _ = GameQuestion.objects.all().delete()
            GameQuestion.objects.bulk_create(built, batch_size=500)

        self.stdout.write(self.style.SUCCESS(
            f'Пул пересобран: {len(built)} вопросов (было {deleted}).'))
        ru = sum(1 for g in built if g.lang == 'ru')
        self.stdout.write(f'  русских: {ru}, английских: {len(built) - ru}')
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
