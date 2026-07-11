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
from django.db import models


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
    problem = models.ForeignKey(
        'problems.Problem', on_delete=models.CASCADE,
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
