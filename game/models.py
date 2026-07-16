"""
Модели игры Econ Rush.

GameQuestion — денормализованный КЭШ игровых вопросов, собираемый командой
`build_game_pool` из тестовых задач (`Problem` с problem_type «тест: …»).
Контент-таблицы (`Problem`, `ProblemPart`) при пересборке не изменяются —
пул можно в любой момент снести и собрать заново.

Четыре типа вопросов (по режимам игры): boolean — данетка (Пуля),
single — один из вариантов (Блиц), multi — несколько из вариантов (Рапид),
numeric — числовой ответ вводом (Классика; извлечение появится с импортом
региональных тестов).
"""
import secrets

from django.db import models

# Алфавит кода публичной ссылки — Crockford base32: без I, L, O, U,
# чтобы код нельзя было спутать при чтении вслух или переписывании.
CODE_ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
CODE_LENGTH = 8


def make_result_code():
    """Случайный код публичной страницы результата.

    32^8 ≈ 1,1 трлн вариантов — угадать чужой результат перебором не выйдет,
    а порядковый id выдавал бы, сколько всего забегов сыграно."""
    return ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class GameQuestion(models.Model):
    """Один игровой вопрос: текст + варианты + правильный ответ (по типу)."""

    QUESTION_TYPES = [
        ('boolean', 'Данетка'),
        ('single', 'Один из'),
        ('multi', 'Несколько из'),
        ('numeric', 'Числовой'),
    ]

    # FK (не OneToOne): одна задача может дать несколько игровых вопросов —
    # задел под данетки-пачки из будущего импорта (разведка 2026-07-11
    # показала, что в текущей базе пачек нет, но формат приедет с регионами).
    # NULL — только у сгенерированных вопросов (is_generated=True): у них
    # нет задачи-источника, их math задаётся generator_key + gen_params.
    problem = models.ForeignKey(
        'problems.Problem', on_delete=models.CASCADE, null=True, blank=True,
        related_name='game_questions', verbose_name='Задача-источник')
    # Подпункт-источник — только для вопросов, извлечённых из конкретного
    # ProblemPart (разбивка пачек). Для вопросов «вся задача целиком» — NULL.
    part = models.ForeignKey(
        'problems.ProblemPart', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='game_questions', verbose_name='Подпункт-источник')

    question_type = models.CharField(
        'Тип вопроса', max_length=10, choices=QUESTION_TYPES,
        default='single', db_index=True)
    question = models.TextField('Текст вопроса')
    # Варианты ответа — список строк (2–5 штук), порядок как в задаче.
    # Для boolean всегда ['Верно', 'Неверно']; для numeric — пустой список.
    options = models.JSONField('Варианты ответа')
    # Правильный ответ — ровно одно из трёх полей по типу вопроса:
    # boolean/single → correct_index; multi → correct_indices; numeric → correct_value.
    correct_index = models.PositiveSmallIntegerField(
        'Индекс правильного (0-based)', null=True, blank=True)
    correct_indices = models.JSONField(
        'Индексы правильных (multi)', null=True, blank=True)
    correct_value = models.CharField(
        'Точный числовой ответ (numeric)', max_length=50, blank=True, default='')

    # Сложность 1–5. У большинства тестов difficulty в базе пуст —
    # тогда оценка эвристикой (см. build_game_pool), это честно записано в отчёте.
    difficulty = models.PositiveSmallIntegerField('Сложность (1–5)', default=3)
    # Темы денормализованы: список названий канонических тем (может быть пустым).
    topics = models.JSONField('Темы (названия)', default=list, blank=True)
    lang = models.CharField('Язык вопроса', max_length=2, default='ru')

    # Метаданные олимпиады (денормализация под будущий фильтр «только регион»;
    # заполнятся импортом региональных тестов, сейчас пустые).
    stage = models.CharField('Этап олимпиады', max_length=40, blank=True, default='')
    year = models.PositiveIntegerField('Год', null=True, blank=True)
    grade = models.CharField('Класс', max_length=20, blank=True, default='')
    # Единица измерения числового ответа («%», «руб.») — подсказка игроку
    # рядом с полем ввода Классики. Источник — SourceReference.note
    # («единица ответа: …»), денормализуется при пересборке пула.
    unit = models.CharField('Единица ответа', max_length=40, blank=True,
                            default='')

    # --- Параметрические генераторы (game/generators/) ---
    # Сгенерированные вопросы живут в том же кэше, но: build_game_pool их
    # НЕ трогает (пересобирает только is_generated=False), а полный откат —
    # команда purge_generated.
    is_generated = models.BooleanField(
        'Сгенерирован', default=False, db_index=True)
    generator_key = models.CharField(
        'Ключ генератора (архетип)', max_length=64, blank=True, default='')
    gen_params = models.JSONField(
        'Параметры генерации', null=True, blank=True)
    gen_solution = models.TextField(
        'Пошаговое решение (KaTeX)', blank=True, default='')
    # Чертёж к задаче: параметры статичного SVG (тип диаграммы + числа),
    # рисует клиент в разборе ошибок. Схема — game/generators/_figure.py.
    # NULL — у вопроса графика нет (не все архетипы графические).
    figure = models.JSONField(
        'Параметры графика', null=True, blank=True)

    created_at = models.DateTimeField('Собран', auto_now_add=True)

    class Meta:
        verbose_name = 'Игровой вопрос'
        verbose_name_plural = 'Игровые вопросы'
        constraints = [
            models.UniqueConstraint(
                fields=['problem', 'part'], name='uniq_gq_problem_part'),
        ]
        indexes = [
            models.Index(fields=['lang', 'difficulty']),
            models.Index(fields=['lang', 'question_type']),
        ]

    def __str__(self):
        return f'GameQuestion #{self.pk} (задача #{self.problem_id})'


class GameResult(models.Model):
    """Сохранённый результат забега — для публичной страницы `/game/r/<код>/`.

    Отдельная таблица, ничего в игре от неё не зависит: строка создаётся при
    завершении забега и живёт сама по себе. Это НЕ лидерборд — записи ничьи,
    сравнивать их между собой нельзя (авторизации у игры нет, счёт приходит
    из сессии игрока). Смысл один: у ссылки, которой делятся, должно быть
    что показать.

    Разбивки лежат JSON-полями (Django 4.2 умеет их и на SQLite, и на
    Postgres): страница read-only, запросов «по темам» к ним не будет.
    """
    code = models.CharField('Код ссылки', max_length=16, unique=True,
                            default=make_result_code, db_index=True)
    mode = models.CharField('Режим', max_length=16)
    score = models.PositiveIntegerField('Счёт', default=0)
    correct_count = models.PositiveSmallIntegerField('Верных', default=0)
    total_count = models.PositiveSmallIntegerField('Попыток', default=0)
    max_combo = models.PositiveSmallIntegerField('Макс. множитель', default=1)
    ended_reason = models.CharField('Чем кончился', max_length=8, default='time')
    # [{topic, correct, wrong, skip, total, accuracy}, ...]
    topic_breakdown = models.JSONField('Разбивка по темам', default=list, blank=True)
    # [{key, title, total, correct}, ...]
    difficulty_breakdown = models.JSONField('Разбивка по сложности',
                                            default=list, blank=True)
    # счёт по номеру вопроса — мини-график на публичной странице
    score_curve = models.JSONField('Кривая счёта', default=list, blank=True)
    created_at = models.DateTimeField('Сыгран', auto_now_add=True)

    class Meta:
        verbose_name = 'Результат забега'
        verbose_name_plural = 'Результаты забегов'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.code}: {self.score} очков ({self.mode})'

    @property
    def accuracy(self):
        return round(100 * self.correct_count / self.total_count) if self.total_count else 0
