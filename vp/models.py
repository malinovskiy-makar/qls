"""Модели тренажёра «Высшей пробы», 1 и 2 тур отборочного этапа (ADR 0124).

⚠️ Эти модели НАМЕРЕННО не ссылаются на `problems.Problem`: пункты теста чужого
формата не должны попасть в каталог, поиск, эмбеддинги и статистику банка, а
правка банка не смеет менять журнал попыток школьника.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from problems.models_platform import UserProfile


class VPVariant(models.Model):
    """Один вариант тура: 1 тур — 44 задания и 30 минут, 2 тур — 17 или 18 заданий
    и 70 минут; всегда 100 баллов. Правила по турам — `vp.loader.TOUR_RULES`."""

    class SourceKind(models.TextChoices):
        DEMO = 'demo', 'Демонстрационный'
        AUTHOR = 'author', 'Авторский'
        PAST = 'past', 'Прошлых лет'

    slug = models.SlugField('Слаг', max_length=80, unique=True)
    title = models.CharField('Название', max_length=200)
    olympiad_slug = models.CharField(
        'Слаг олимпиады', max_length=60, default='vysshaya-proba')
    tour = models.PositiveSmallIntegerField('Тур', default=1)
    grade_band = models.CharField('Классы', max_length=10)  # 1 тур: '9-10'/'11'; 2 тур: '9'/'10'/'11'
    year = models.PositiveSmallIntegerField('Год')
    source_kind = models.CharField(
        'Происхождение', max_length=10, choices=SourceKind.choices)
    source_note = models.CharField('Примечание', max_length=300, blank=True)
    author = models.CharField('Автор', max_length=200, blank=True)
    # Правообладатель (Олмат и т.п.): подпись рисуется гиперссылкой на карточке
    # и на интро. Источников будет больше одного, так что это поле у варианта,
    # а не константа в шаблоне — подпись едет вместе с данными.
    source_label = models.CharField('Подпись источника', max_length=64, blank=True)
    source_url = models.URLField('Ссылка на источник', blank=True)
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

    def clean(self):
        super().clean()
        if bool(self.source_label) != bool(self.source_url):
            raise ValidationError(
                'source_label и source_url заполняются оба или оба пусты')
        if self.source_url and not self.source_url.startswith('https://'):
            raise ValidationError('source_url должен начинаться с https://')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class VPItem(models.Model):
    """Задание варианта. Балл хранится в данных, а не выводится из блока:
    у 11 класса задания 43 и 44 стоят по 4,5 балла."""

    class Block(models.TextChoices):
        SNAKE = 'snake', 'Змейка'
        GAPFILL = 'gapfill', 'Пропуск в тексте'
        MULTI = 'multi', 'Несколько верных'
        ANALYTIC = 'analytic', 'Аналитическое'
        SINGLE = 'single', 'Один верный'
        # 2 тур
        NUMBER = 'number', 'Ввод числа'
        GAPTEXT = 'gaptext', 'Текст с пропусками'
        MATCHING = 'matching', 'Соотнесение'

    class Kind(models.TextChoices):
        SHORT_TEXT = 'short_text', 'Короткий ответ'
        SINGLE = 'single', 'Один вариант'
        MULTI = 'multi', 'Несколько вариантов'
        MATCH = 'match', 'Сопоставление'
        NUMBER = 'number', 'Число'

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
    options = models.JSONField('Варианты', default=list, blank=True)
    # [2] | [1, 3, 5] | {"а": 3, "б": 1}
    correct = models.JSONField('Верные', default=list, blank=True)
    # Соотнесение (2 тур): тексты утверждений слева, по порядку ключей «1»…«N»
    # в `correct`; справа — категории из `options`.
    rows = models.JSONField('Строки соотнесения', default=list, blank=True)
    # Пара задач с общим условием (2 тур): одинаковый номер группы у подряд
    # идущих заданий варианта; условие первого — общее.
    group = models.PositiveSmallIntegerField(
        'Пара с общим условием', null=True, blank=True)
    answer = models.CharField('Эталон короткого ответа', max_length=200,
                              blank=True)
    accepted = models.JSONField('Также засчитываем', default=list, blank=True)
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
    # ⚠️ СТАВИТСЯ ОДИН РАЗ, В `views.start`, И БОЛЬШЕ НЕ ПЕРЕСЧИТЫВАЕТСЯ.
    # Зачётная = попытка с таймером, у которой у этого пользователя по этому
    # варианту нет более ранней попытки с таймером (сданной или нет). Гостевая
    # попытка зачётной не бывает никогда: у неё нет пользователя.
    # Правило записано в данные в момент старта, а не вычисляется задним числом:
    # будущая смена правила не должна переписать уже сыгранную историю.
    # Что с этим флагом делает таблица лучших попыток — `vp/board.py`.
    is_ranked = models.BooleanField('Зачётная', default=False, db_index=True)
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


# ------------------------------------------------------------------ стена 2 тура
#
# Правило «пускать ли в вариант» — ТОЛЬКО `vp/wall.py`; здесь только хранение
# (docs/VP.md, «Стена 2 тура», ADR 0168). Порядок и подписи вариантов ответа —
# порядок кнопок анкеты на экране.

class VPWall(models.Model):
    """Пройденное человеком на стене 2 тура: контакт и анкета. Одна строка на аккаунт.

    ⚠️ КОНТАКТ ПОСТОЯННЫЙ. Отписка от канала после прохода стены его не отбирает:
    во время тура человек не должен внезапно упереться в стену посреди недели.
    """

    CONTACT_CHOICES = (('', 'Нет'), ('tg', 'Telegram'), ('email', 'Почта'))
    GRADE_CHOICES = (('9', '9'), ('10', '10'), ('11', '11'))
    TOUR2_CHOICES = (
        ('passed', 'Да, прошёл'),
        ('waiting', 'Жду результатов'),
        ('future', 'Нет, готовлюсь на будущее'),
        ('no_tour1', 'Не писал 1 тур'),
    )
    # «Откуда узнали» — ОДИН список на сайт (раунд 2): коды и подписи живут в
    # `UserProfile.SourceChannel`, стена берёт их оттуда, а не держит копию.
    SOURCE_CHOICES = tuple(UserProfile.SourceChannel.choices)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vp_wall',
        verbose_name='Аккаунт')
    contact_via = models.CharField(
        'Контакт', max_length=8, choices=CONTACT_CHOICES, blank=True, default='')
    contact_at = models.DateTimeField('Контакт получен', null=True, blank=True)
    grade = models.CharField('Класс', max_length=2, choices=GRADE_CHOICES, blank=True)
    tour2_status = models.CharField(
        'Прошёл во 2 тур', max_length=10, choices=TOUR2_CHOICES, blank=True)
    source = models.CharField(
        'Откуда узнал', max_length=10, choices=SOURCE_CHOICES, blank=True)
    survey_at = models.DateTimeField('Анкета', null=True, blank=True)
    created_at = models.DateTimeField('Дошёл до стены', auto_now_add=True)

    class Meta:
        verbose_name = 'Стена ВП: человек'
        verbose_name_plural = 'Стена ВП: люди'

    def __str__(self):
        return f'{self.user_id}: {self.contact_via or "без контакта"}'


class VPTelegramLink(models.Model):
    """Привязка Telegram к аккаунту — НЕ вход на сайт: сессию по ней не открывает никто."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vp_telegram',
        verbose_name='Аккаунт')
    tg_user_id = models.BigIntegerField('ID в Telegram', unique=True)
    tg_username = models.CharField('Ник в Telegram', max_length=64, blank=True)
    linked_at = models.DateTimeField('Привязан', auto_now_add=True)
    checked_at = models.DateTimeField('Подписка проверена', null=True, blank=True)
    subscribed = models.BooleanField('Подписан', default=False)
    last_error = models.CharField('Последняя ошибка', max_length=32, blank=True)

    class Meta:
        verbose_name = 'Стена ВП: привязка Telegram'
        verbose_name_plural = 'Стена ВП: привязки Telegram'

    def __str__(self):
        return f'{self.user_id} ↔ tg'


class VPTelegramToken(models.Model):
    """Одноразовый код привязки из ссылки `t.me/<бот>?start=<код>`.

    ⚠️ САМ КОД В БАЗЕ НЕ ХРАНИТСЯ — только отпечаток HMAC-SHA256 на `SECRET_KEY`,
    как у кодов почты (`problems/models_mail.py`).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vp_tg_tokens',
        verbose_name='Аккаунт')
    token_hash = models.CharField('Отпечаток кода', max_length=64, unique=True)
    slug = models.SlugField('Вариант', max_length=80, blank=True)
    created_at = models.DateTimeField('Выдан', auto_now_add=True)
    used_at = models.DateTimeField('Погашен', null=True, blank=True)

    class Meta:
        verbose_name = 'Стена ВП: код привязки'
        verbose_name_plural = 'Стена ВП: коды привязки'
        indexes = [models.Index(fields=['user', 'created_at'])]

    def __str__(self):
        return f'{self.user_id}: код от {self.created_at:%d.%m %H:%M}'
