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
# LaTeX-окружения, картинки, ссылки, остатки PDF-вёрстки, псевдотаблицы.
BAD_CONTENT_RE = re.compile(
    r'\\begin\{|\\end\{|\\includegraphics|\\hline|\\url\{|\\iffalse'
    r'|\\item\b|\\footnote'
    r'|Scoring Guide|Page \d+ of'
    r'|\|\s*\|'          # двойная вертикальная черта — псевдотаблица
)

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

    question = clean_text(problem.statement)
    if len(question) < MIN_QUESTION_LEN:
        return None, None, None, 'условие слишком короткое'
    if len(question) > MAX_QUESTION_LEN:
        return None, None, None, 'условие длиннее 300'

    options = [clean_text(p.statement) for p in parts]
    if any(not o for o in options):
        return None, None, None, 'пустой вариант'
    if any(len(o) > MAX_OPTION_LEN for o in options):
        return None, None, None, 'вариант слишком длинный'
    if len(set(o.lower() for o in options)) != len(options):
        return None, None, None, 'варианты дублируются'

    all_text = question + ' ' + ' '.join(options)
    if BAD_CONTENT_RE.search(all_text):
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
        for p in qs:
            question, opts, correct, reason = extract_question(p)
            if reason:
                rejected[reason] = rejected.get(reason, 0) + 1
                continue
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
