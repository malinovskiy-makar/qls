"""
Модели игры Econ Rush.

GameQuestion — денормализованный КЭШ игровых вопросов, собираемый командой
`build_game_pool` из тестовых задач (`Problem` с problem_type «тест: …»).
Контент-таблицы (`Problem`, `ProblemPart`) при пересборке не изменяются —
пул можно в любой момент снести и собрать заново.
"""
from django.db import models


class GameQuestion(models.Model):
    """Один игровой вопрос: текст + варианты + индекс правильного."""

    problem = models.OneToOneField(
        'problems.Problem', on_delete=models.CASCADE,
        related_name='game_question', verbose_name='Задача-источник')
    question = models.TextField('Текст вопроса')
    # Варианты ответа — список строк (2–5 штук), порядок как в задаче.
    options = models.JSONField('Варианты ответа')
    correct_index = models.PositiveSmallIntegerField('Индекс правильного (0-based)')
    # Сложность 1–5. У большинства тестов difficulty в базе пуст —
    # тогда оценка эвристикой (см. build_game_pool), это честно записано в отчёте.
    difficulty = models.PositiveSmallIntegerField('Сложность (1–5)', default=3)
    # Темы денормализованы: список названий канонических тем (может быть пустым).
    topics = models.JSONField('Темы (названия)', default=list, blank=True)
    lang = models.CharField('Язык вопроса', max_length=2, default='ru')

    created_at = models.DateTimeField('Собран', auto_now_add=True)

    class Meta:
        verbose_name = 'Игровой вопрос'
        verbose_name_plural = 'Игровые вопросы'
        indexes = [
            models.Index(fields=['lang', 'difficulty']),
        ]

    def __str__(self):
        return f'GameQuestion #{self.pk} (задача #{self.problem_id})'
