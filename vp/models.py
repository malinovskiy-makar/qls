"""Модели тренажёра 1 тура «Высшей пробы» (ADR 0124).

⚠️ Эти модели НАМЕРЕННО не ссылаются на `problems.Problem`: пункты теста чужого
формата не должны попасть в каталог, поиск, эмбеддинги и статистику банка, а
правка банка не смеет менять журнал попыток школьника.
"""
from django.conf import settings
from django.db import models


class VPVariant(models.Model):
    """Один вариант 1 тура: 44 задания, 100 баллов, 30 минут."""

    class SourceKind(models.TextChoices):
        DEMO = 'demo', 'Демонстрационный'
        AUTHOR = 'author', 'Авторский'
        PAST = 'past', 'Прошлых лет'

    slug = models.SlugField('Слаг', max_length=80, unique=True)
    title = models.CharField('Название', max_length=200)
    olympiad_slug = models.CharField(
        'Слаг олимпиады', max_length=60, default='vysshaya-proba')
    tour = models.PositiveSmallIntegerField('Тур', default=1)
    grade_band = models.CharField('Классы', max_length=10)  # '9-10' или '11'
    year = models.PositiveSmallIntegerField('Год')
    source_kind = models.CharField(
        'Происхождение', max_length=10, choices=SourceKind.choices)
    source_note = models.CharField('Примечание', max_length=300, blank=True)
    author = models.CharField('Автор', max_length=200, blank=True)
    duration_seconds = models.PositiveIntegerField(
        'Длительность, с', default=1800)
    # ⚠️ Считается загрузчиком из суммы points, а не читается из файла.
    max_score = models.DecimalField(
        'Максимум баллов', max_digits=6, decimal_places=2, default=0)
    is_published = models.BooleanField('Опубликован', default=False)
    order = models.IntegerField('Порядок', default=0)
    created_at = models.DateTimeField('Создан', auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Вариант ВП'
        verbose_name_plural = 'Варианты ВП'

    def __str__(self):
        return self.title


class VPItem(models.Model):
    """Задание варианта. Балл хранится в данных, а не выводится из блока:
    у 11 класса задания 43 и 44 стоят по 4,5 балла."""

    class Block(models.TextChoices):
        SNAKE = 'snake', 'Змейка'
        GAPFILL = 'gapfill', 'Пропуск в тексте'
        MULTI = 'multi', 'Несколько верных'
        ANALYTIC = 'analytic', 'Аналитическое'
        SINGLE = 'single', 'Один верный'

    class Kind(models.TextChoices):
        SHORT_TEXT = 'short_text', 'Короткий ответ'
        SINGLE = 'single', 'Один вариант'
        MULTI = 'multi', 'Несколько вариантов'
        MATCH = 'match', 'Сопоставление'

    variant = models.ForeignKey(
        VPVariant, on_delete=models.CASCADE, related_name='items',
        verbose_name='Вариант')
    number = models.PositiveSmallIntegerField('Номер')
    block = models.CharField('Блок', max_length=10, choices=Block.choices)
    kind = models.CharField('Вид', max_length=12, choices=Kind.choices)
    # Общий текст перед первым заданием блока.
    intro = models.TextField('Вводный текст блока', blank=True)
    statement = models.TextField('Условие')
    # Часть ответа, уже напечатанная в условии: змейка идёт от слова,
    # которое вводит участник, а не от напечатанного.
    prefix = models.CharField('Напечатано до пропуска', max_length=120,
                              blank=True)
    suffix = models.CharField('Напечатано после пропуска', max_length=120,
                              blank=True)
    # [{"n": 1, "text": "ОПЕК"}, ...] — нумерация с единицы.
    options = models.JSONField('Варианты', default=list)
    # [2] | [1, 3, 5] | {"а": 3, "б": 1}
    correct = models.JSONField('Верные', default=list)
    answer = models.CharField('Эталон короткого ответа', max_length=200,
                              blank=True)
    accepted = models.JSONField('Также засчитываем', default=list)
    points = models.DecimalField('Баллы', max_digits=5, decimal_places=2)
    wrong_penalty = models.DecimalField(
        'Штраф за неверный', max_digits=5, decimal_places=2, default=0)
    # Пропорциональный штраф за лишние отметки в multi.
    penalty = models.BooleanField('Штраф за лишнее', default=False)
    figure = models.CharField('Рисунок', max_length=200, blank=True)
    figure_caption = models.CharField('Подпись к рисунку', max_length=300,
                                      blank=True)
    figure_source = models.CharField('Источник рисунка', max_length=200,
                                     blank=True)
    table_html = models.TextField('Таблица (HTML)', blank=True)
    solution = models.TextField('Решение', blank=True)
    # Первая и вторая буквы вводимого слова; заполняет загрузчик, не save().
    chain_first = models.CharField(
        'Первая буква', max_length=1, blank=True, db_index=True)
    chain_second = models.CharField(
        'Вторая буква', max_length=1, blank=True, db_index=True)

    class Meta:
        unique_together = [('variant', 'number')]
        ordering = ['number']
        verbose_name = 'Задание ВП'
        verbose_name_plural = 'Задания ВП'

    def __str__(self):
        return f'{self.variant.slug} №{self.number}'

    def chain_word(self):
        """Слово, которое вводит участник: первое слово эталона.

        Связка змейки идёт от него, а если ответ — словосочетание, то от
        ПЕРВОГО слова.
        """
        parts = (self.answer or '').split()
        return parts[0] if parts else ''


class VPAttempt(models.Model):
    """Попытка прорешать вариант. Гостю вход не нужен.

    ⚠️ ИМЕНА `started_at` / `expires_at` / `submitted_at` / `is_auto_submitted`
    СОВПАДАЮТ С `problems.ExamAttempt` НАМЕРЕННО: благодаря этому
    `exam_engine.seconds_remaining` и `can_accept` работают с этой попыткой
    без единой правки (тот же приём, что у `olympiads.TrainingAttempt`).
    Арифметику остатка времени здесь НЕ переписывать.
    """

    class Mode(models.TextChoices):
        FULL = 'full', 'Весь вариант'
        BLOCK = 'block', 'Один блок'
        ENDLESS = 'endless', 'Бесконечный'

    variant = models.ForeignKey(
        VPVariant, on_delete=models.CASCADE, related_name='attempts',
        verbose_name='Вариант')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name='Пользователь')
    session_key = models.CharField(
        'Ключ сессии', max_length=40, blank=True, db_index=True)
    mode = models.CharField('Режим', max_length=8, choices=Mode.choices,
                            default=Mode.FULL)
    block = models.CharField('Блок', max_length=10, blank=True)
    with_timer = models.BooleanField('На время', default=True)
    started_at = models.DateTimeField('Начата', auto_now_add=True)
    expires_at = models.DateTimeField('Истекает', null=True, blank=True)
    submitted_at = models.DateTimeField('Сдана', null=True, blank=True)
    is_auto_submitted = models.BooleanField('Сдана автоматически',
                                            default=False)
    score = models.DecimalField('Балл', max_digits=6, decimal_places=2,
                                null=True, blank=True)
    max_score = models.DecimalField('Максимум', max_digits=6,
                                    decimal_places=2, null=True, blank=True)
    public_code = models.CharField('Публичный код', max_length=12,
                                   unique=True, db_index=True)

    class Meta:
        verbose_name = 'Попытка ВП'
        verbose_name_plural = 'Попытки ВП'

    def __str__(self):
        return f'{self.variant.slug} · {self.public_code}'


class VPAnswer(models.Model):
    """Ответ на задание. Черновика отдельной моделью нет: автосохранение
    пишет `raw` в эту же строку, баллы проставляются при сдаче."""

    attempt = models.ForeignKey(
        VPAttempt, on_delete=models.CASCADE, related_name='answers',
        verbose_name='Попытка')
    item = models.ForeignKey(VPItem, on_delete=models.CASCADE,
                             verbose_name='Задание')
    raw = models.JSONField('Что ввёл или выбрал', null=True, blank=True)
    score = models.DecimalField('Балл', max_digits=5, decimal_places=2,
                                null=True, blank=True)
    max_score = models.DecimalField('Максимум', max_digits=5,
                                    decimal_places=2, null=True, blank=True)
    is_correct = models.BooleanField('Верно', null=True, blank=True)
    updated_at = models.DateTimeField('Обновлён', auto_now=True)

    class Meta:
        unique_together = [('attempt', 'item')]
        verbose_name = 'Ответ ВП'
        verbose_name_plural = 'Ответы ВП'
