"""
Модели данных платформы — Этап 1 (ядро контента).

Каждый класс ниже — это «анкета» (таблица в базе данных). Поля анкеты — это
строчки внутри класса. Комментарии объясняют каждое поле простыми словами.

Состав Этапа 1:
  User            — пользователь с ролью (преподаватель / ученик)
  Topic / Subtopic — тема / подтема (как главы и подразделы в книге)
  Tag             — свободные метки
  Source / SourceReference — источник и точная привязка задачи к нему
  FileAsset       — единое хранилище файлов (картинки, PDF, графики)
  Problem         — сама задача (центральная сущность)
  ProblemPart     — подпункты а/б/в, у каждого свой ответ
  ProblemVersion  — снимок истории задачи (для отката к прошлой версии)
"""

import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .review_categories import CATEGORY_CHOICES


# ---------------------------------------------------------------------------
# Пользователь
# ---------------------------------------------------------------------------

class User(AbstractUser):
    """Пользователь системы. Берём всё стандартное от Django (логин, пароль,
    имя, email) и добавляем одно поле — роль."""

    class Role(models.TextChoices):
        TEACHER = 'teacher', 'Преподаватель'
        STUDENT = 'student', 'Ученик'
        # Роли ниже заложены на будущее, интерфейс под них пока не делаем:
        EDITOR = 'editor', 'Редактор'
        VIEWER = 'viewer', 'Наблюдатель'
        PUBLIC = 'public', 'Публичный доступ'

    role = models.CharField(
        'Роль', max_length=20,
        choices=Role.choices, default=Role.STUDENT,
    )

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'


# ---------------------------------------------------------------------------
# Темы и теги
# ---------------------------------------------------------------------------

class Topic(models.Model):
    """Тема — верхний уровень (как глава в задачнике)."""

    name = models.CharField('Название', max_length=200)
    slug = models.SlugField('Короткий код (для ссылок)', max_length=220,
                            unique=True, blank=True)
    description = models.TextField('Описание', blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Тема'
        verbose_name_plural = 'Темы'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Subtopic(models.Model):
    """Подтема — второй уровень внутри темы (как подраздел в главе)."""

    topic = models.ForeignKey(Topic, on_delete=models.CASCADE,
                              related_name='subtopics', verbose_name='Тема')
    name = models.CharField('Название', max_length=200)
    slug = models.SlugField('Короткий код', max_length=220, blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Подтема'
        verbose_name_plural = 'Подтемы'
        ordering = ['order', 'name']

    def __str__(self):
        return f'{self.topic.name} → {self.name}'


class Tag(models.Model):
    """Свободная метка (тег), которую можно повесить на любую задачу."""

    name = models.CharField('Название', max_length=100, unique=True)
    slug = models.SlugField('Короткий код', max_length=120, unique=True,
                            blank=True)

    class Meta:
        verbose_name = 'Тег'
        verbose_name_plural = 'Теги'
        ordering = ['name']

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Источники
# ---------------------------------------------------------------------------

class Source(models.Model):
    """Источник — откуда взята задача (книга, олимпиада, сборник)."""

    name = models.CharField('Название', max_length=300)
    author = models.CharField('Автор / составитель', max_length=300, blank=True)
    year = models.PositiveIntegerField('Год', null=True, blank=True)
    kind = models.CharField('Тип источника', max_length=100, blank=True,
                            help_text='Например: задачник, олимпиада, сборник')
    note = models.TextField('Заметка об авторских правах', blank=True)

    class Meta:
        verbose_name = 'Источник'
        verbose_name_plural = 'Источники'
        ordering = ['name']

    def __str__(self):
        if self.year:
            return f'{self.name} ({self.year})'
        return self.name


class SourceReference(models.Model):
    """Точная привязка конкретной задачи к источнику: этап, класс, номер,
    страница, ссылка. Одна задача может ссылаться на несколько источников."""

    problem = models.ForeignKey('Problem', on_delete=models.CASCADE,
                                related_name='source_references',
                                verbose_name='Задача')
    source = models.ForeignKey(Source, on_delete=models.PROTECT,
                               related_name='references', verbose_name='Источник')
    stage = models.CharField('Этап олимпиады', max_length=120, blank=True)
    # Год конкретного тура/варианта. Source.year — год источника-книги,
    # а у сквозных источников («ВсОШ — региональный этап») год живёт здесь.
    year = models.PositiveIntegerField('Год', null=True, blank=True)
    grade = models.CharField('Класс', max_length=50, blank=True)
    problem_number = models.CharField('Номер задачи в источнике',
                                      max_length=50, blank=True)
    page = models.CharField('Страница', max_length=50, blank=True)
    url = models.URLField('Ссылка', blank=True)
    note = models.CharField('Заметка', max_length=300, blank=True)

    class Meta:
        verbose_name = 'Привязка к источнику'
        verbose_name_plural = 'Привязки к источникам'

    def __str__(self):
        parts = [self.source.name]
        if self.problem_number:
            parts.append(f'№{self.problem_number}')
        return ' '.join(parts)


# ---------------------------------------------------------------------------
# Файлы
# ---------------------------------------------------------------------------

class FileAsset(models.Model):
    """Единое хранилище файлов: картинки, PDF, графики, вложения."""

    class Kind(models.TextChoices):
        IMAGE = 'image', 'Картинка'
        PDF = 'pdf', 'PDF'
        GRAPH = 'graph', 'График'
        SOURCE_FILE = 'source', 'Исходный файл'
        ATTACHMENT = 'attachment', 'Вложение'
        STUDENT_WORK = 'student_work', 'Работа ученика'

    file = models.FileField('Файл', upload_to='uploads/%Y/%m/')
    kind = models.CharField('Тип файла', max_length=20,
                            choices=Kind.choices, default=Kind.IMAGE)
    caption = models.CharField('Подпись', max_length=300, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                    on_delete=models.SET_NULL,
                                    null=True, blank=True,
                                    verbose_name='Загрузил')
    created_at = models.DateTimeField('Загружен', auto_now_add=True)

    class Meta:
        verbose_name = 'Файл'
        verbose_name_plural = 'Файлы'
        ordering = ['-created_at']

    def __str__(self):
        return self.caption or self.file.name


# ---------------------------------------------------------------------------
# Задача и подпункты
# ---------------------------------------------------------------------------

class Problem(models.Model):
    """Центральная сущность — задача. Хранит общее условие, сложность,
    статус публикации, владельца и связи с темами/тегами/файлами."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Черновик'
        NEEDS_REVIEW = 'needs_review', 'На проверку'
        PUBLISHED = 'published', 'Опубликована'
        ARCHIVED = 'archived', 'В архиве'
        HIDDEN = 'hidden', 'Скрыта'
        DUPLICATE = 'duplicate', 'Дубликат'

    title = models.CharField('Заголовок', max_length=300, blank=True,
                             help_text='Необязательно. Краткое имя задачи.')
    statement = models.TextField(
        'Условие',
        help_text='Основной текст задачи. Можно использовать LaTeX-формулы.',
    )
    # Ответ — ОСНОВНОЕ поле; решение — НЕобязательное (часть источников даёт
    # только ответы). Для задач без подпунктов ответ хранится здесь.
    answer = models.TextField('Ответ', blank=True)
    solution = models.TextField('Решение (необязательно)', blank=True)

    problem_type = models.CharField('Тип задачи', max_length=120, blank=True)

    # Сложность храним двумя полями: числовая шкала + «родная» метка источника.
    difficulty = models.PositiveSmallIntegerField(
        'Сложность (1–5)', null=True, blank=True)
    difficulty_native = models.CharField(
        'Сложность (метка источника)', max_length=20, blank=True,
        help_text='Например: *, **, ***')

    status = models.CharField('Статус', max_length=20,
                              choices=Status.choices, default=Status.DRAFT)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL,
                              on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='owned_problems',
                              verbose_name='Владелец')

    topics = models.ManyToManyField(Topic, blank=True, related_name='problems',
                                    verbose_name='Темы')
    subtopics = models.ManyToManyField(Subtopic, blank=True,
                                       related_name='problems',
                                       verbose_name='Подтемы')
    tags = models.ManyToManyField(Tag, blank=True, related_name='problems',
                                  verbose_name='Теги')
    files = models.ManyToManyField(FileAsset, blank=True,
                                   related_name='problems',
                                   verbose_name='Файлы')

    # --- Этап 2 (педагогический слой) ---
    # Какие навыки тренирует задача и какие типичные ошибки с ней связаны.
    # Связи объявлены здесь один раз, но доступны и со стороны Skill/MistakeTag
    # (через обратные обращения skill.problems и mistaketag.problems).
    skills = models.ManyToManyField('Skill', blank=True,
                                    related_name='problems',
                                    verbose_name='Навыки')
    mistakes = models.ManyToManyField('MistakeTag', blank=True,
                                      related_name='problems',
                                      verbose_name='Типичные ошибки')

    content_hash = models.CharField(
        'MD5-хэш условия', max_length=32, blank=True, db_index=True,
        help_text='Автоматически для дедупликации при импорте.',
    )

    # Этап 5б — дедупликация. Если задача является возможным дублём другой,
    # здесь хранится ссылка на «оригинал». Устанавливается командой process_duplicates.
    duplicate_of = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='possible_duplicates',
        verbose_name='Возможный дубликат задачи',
    )

    # Сессия B — качественный шлюз: задачи с critical-дефектами рендеринга
    # скрываются из каталога/экспорта/похожих. Ставится командой quality_gate
    # (--apply), снимается полностью: quality_gate --revert.
    # Сессия D: флаг ставится ТОЛЬКО за дефекты в условии (statement задачи
    # или подпунктов) и за мусор импорта; дефекты решения задачу не скрывают.
    needs_quality_review = models.BooleanField(
        'Требует проверки качества',
        default=False, db_index=True,
        help_text='Скрыта из каталога качественным шлюзом (битый рендер условия)',
    )

    # Сессия D: critical-дефекты в РЕШЕНИИ — задача видна, но кнопка
    # «Показать решение» скрывается (решение остаётся в базе).
    # Управляется quality_gate --apply / --revert.
    solution_needs_review = models.BooleanField(
        'Решение требует проверки',
        default=False, db_index=True,
        help_text='Кнопка «Показать решение» скрыта (битый рендер решения)',
    )

    # Этап 5а — эмбеддинг для поиска похожих задач.
    # Хранится как bytes (numpy float32 array). Заполняется командой build_embeddings.
    embedding = models.BinaryField(blank=True, null=True)

    # Этап Б3 — кеш похожих задач (топ-5 по косинусному сходству).
    # Заполняется командой cache_similar.
    similar_problems = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=False,
        related_name='similar_to',
    )

    # Батч 1 — ИИ-обогащение (Сессия 3)
    ai_blurb = models.TextField(
        blank=True, default='',
        help_text='ИИ: Дано/Найти или суть (внутреннее, для поискового отпечатка; на сайте не показывается)',
    )
    # Батч 1: задача — склейка нескольких условий в одном документе, нужен переимпорт.
    multiple_problems = models.BooleanField(
        'Склейка нескольких задач', default=False,
        help_text='ИИ-флаг: задача содержит несколько условий, требует ручного разбиения.',
    )
    # Батч 2: решение извлечено ИИ из текста условия, требует ручной проверки.
    solution_ai_extracted = models.BooleanField(
        'Решение извлечено ИИ', default=False,
        help_text='Батч 2: решение вынесено из текста задачи автоматически, требует проверки.',
    )

    created_at = models.DateTimeField('Создана', auto_now_add=True)
    updated_at = models.DateTimeField('Изменена', auto_now=True)

    class Meta:
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'
        ordering = ['-created_at']

    def __str__(self):
        if self.title:
            return self.title
        # Если заголовка нет — показываем начало условия.
        preview = self.statement[:60]
        return f'Задача #{self.pk}: {preview}'


class ProblemPart(models.Model):
    """Подпункт задачи: а, б, в. У каждого своё условие, ответ, решение,
    баллы. Ответ обязателен по смыслу, решение — необязательно."""

    problem = models.ForeignKey(Problem, on_delete=models.CASCADE,
                                related_name='parts', verbose_name='Задача')
    label = models.CharField('Метка пункта', max_length=10,
                             help_text='Например: а, б, в')
    statement = models.TextField('Условие пункта', blank=True)
    answer = models.TextField('Ответ')
    solution = models.TextField('Решение (необязательно)', blank=True)
    points = models.DecimalField('Баллы', max_digits=5, decimal_places=2,
                                 null=True, blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Подпункт'
        verbose_name_plural = 'Подпункты'
        ordering = ['order', 'label']

    def __str__(self):
        return f'{self.problem} — пункт ({self.label})'


class ProblemVersion(models.Model):
    """Снимок истории задачи: сохраняем содержимое целиком, чтобы можно было
    посмотреть, как задача выглядела раньше, и при необходимости откатиться."""

    problem = models.ForeignKey(Problem, on_delete=models.CASCADE,
                                related_name='versions', verbose_name='Задача')
    number = models.PositiveIntegerField('Номер версии', default=1)
    snapshot = models.JSONField('Снимок содержимого', default=dict, blank=True)
    note = models.CharField('Что изменилось', max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                   on_delete=models.SET_NULL,
                                   null=True, blank=True,
                                   verbose_name='Автор изменения')
    created_at = models.DateTimeField('Создана', auto_now_add=True)

    class Meta:
        verbose_name = 'Версия задачи'
        verbose_name_plural = 'Версии задач'
        ordering = ['-number']

    def __str__(self):
        return f'{self.problem} — версия {self.number}'


# ===========================================================================
# Этап 2 — педагогический слой
# ===========================================================================

class Skill(models.Model):
    """Навык — что именно умеет делать ученик (построить КПВ, найти MR и т.д.).
    Это свободный справочник: новые навыки добавляются через админку, никакого
    фиксированного списка в коде нет."""

    name = models.CharField('Название', max_length=200, unique=True)
    description = models.TextField('Описание', blank=True)
    topics = models.ManyToManyField(Topic, blank=True, related_name='skills',
                                    verbose_name='Темы')

    class Meta:
        verbose_name = 'Навык'
        verbose_name_plural = 'Навыки'
        ordering = ['name']

    def __str__(self):
        return self.name


class StudentSkillProgress(models.Model):
    """Прогресс конкретного ученика по конкретному навыку: число от 0 до 100."""

    student = models.ForeignKey(settings.AUTH_USER_MODEL,
                                on_delete=models.CASCADE,
                                related_name='skill_progress',
                                verbose_name='Ученик')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE,
                              related_name='progress_entries',
                              verbose_name='Навык')
    level = models.PositiveSmallIntegerField(
        'Уровень (0–100)', default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)])
    updated_at = models.DateTimeField('Обновлён', auto_now=True)

    class Meta:
        verbose_name = 'Прогресс по навыку'
        verbose_name_plural = 'Прогресс по навыкам'
        ordering = ['student', 'skill']
        # У одного ученика — одна запись на навык.
        unique_together = ('student', 'skill')

    def __str__(self):
        return f'{self.student} — {self.skill}: {self.level}'


class MistakeTag(models.Model):
    """Типичная ошибка — самостоятельная сущность. Связана с темами и (через
    обратное обращение problems) с задачами, где эта ошибка встречается."""

    name = models.CharField('Название', max_length=200, unique=True)
    description = models.TextField('Описание', blank=True)
    topics = models.ManyToManyField(Topic, blank=True,
                                    related_name='mistake_tags',
                                    verbose_name='Темы')

    class Meta:
        verbose_name = 'Типичная ошибка'
        verbose_name_plural = 'Типичные ошибки'
        ordering = ['name']

    def __str__(self):
        return self.name


class Hint(models.Model):
    """Подсказка. Привязывается либо к задаче целиком, либо к отдельному
    подпункту. Подсказки упорядочены по полю «Порядок»."""

    problem = models.ForeignKey(Problem, on_delete=models.CASCADE,
                                null=True, blank=True,
                                related_name='hints', verbose_name='Задача')
    part = models.ForeignKey(ProblemPart, on_delete=models.CASCADE,
                             null=True, blank=True,
                             related_name='hints', verbose_name='Подпункт')
    order = models.PositiveIntegerField('Порядок', default=1)
    text = models.TextField('Текст подсказки')

    class Meta:
        verbose_name = 'Подсказка'
        verbose_name_plural = 'Подсказки'
        ordering = ['order']

    def __str__(self):
        target = self.part or self.problem or 'без привязки'
        return f'Подсказка {self.order} ({target})'


class Rubric(models.Model):
    """Рубрика оценивания, привязанная к задаче. Состоит из критериев."""

    problem = models.ForeignKey(Problem, on_delete=models.CASCADE,
                                related_name='rubrics', verbose_name='Задача')
    name = models.CharField('Название рубрики', max_length=200,
                            blank=True, default='Критерии оценивания')

    class Meta:
        verbose_name = 'Рубрика'
        verbose_name_plural = 'Рубрики'

    def __str__(self):
        return f'{self.name} — {self.problem}'


class RubricCriterion(models.Model):
    """Отдельный критерий внутри рубрики: за что и сколько баллов."""

    rubric = models.ForeignKey(Rubric, on_delete=models.CASCADE,
                               related_name='criteria', verbose_name='Рубрика')
    name = models.CharField('Критерий', max_length=300)
    max_points = models.DecimalField('Максимальный балл', max_digits=5,
                                     decimal_places=2)
    description = models.TextField('Описание', blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Критерий'
        verbose_name_plural = 'Критерии'
        ordering = ['order']

    def __str__(self):
        return f'{self.name} (до {self.max_points})'


class TheoryPage(models.Model):
    """Мини-теория по теме: определения и формулы, плюс связи с типичными
    ошибками и задачами по этой теме."""

    topic = models.ForeignKey(Topic, on_delete=models.CASCADE,
                              related_name='theory_pages', verbose_name='Тема')
    title = models.CharField('Заголовок', max_length=300)
    body = models.TextField('Текст (определения, формулы)',
                            help_text='Можно использовать LaTeX-формулы.')
    mistakes = models.ManyToManyField(MistakeTag, blank=True,
                                      related_name='theory_pages',
                                      verbose_name='Типичные ошибки')
    problems = models.ManyToManyField(Problem, blank=True,
                                      related_name='theory_pages',
                                      verbose_name='Связанные задачи')
    created_at = models.DateTimeField('Создана', auto_now_add=True)
    updated_at = models.DateTimeField('Изменена', auto_now=True)

    class Meta:
        verbose_name = 'Страница теории'
        verbose_name_plural = 'Страницы теории'
        ordering = ['topic', 'title']

    def __str__(self):
        return self.title


# ===========================================================================
# Этап 3 — цикл «ученик ↔ преподаватель»
# ===========================================================================

class Lesson(models.Model):
    """Конструктор занятия. Преподаватель собирает занятие из трёх блоков
    задач: основные, сложные (challenge) и домашние — это три отдельных набора,
    хотя все они ссылаются на таблицу Problem."""

    name = models.CharField('Название занятия', max_length=300)
    date = models.DateField('Дата занятия', null=True, blank=True)
    goals = models.TextField('Цели занятия', blank=True)
    duration_minutes = models.PositiveIntegerField(
        'Тайминг (минут)', null=True, blank=True)
    warm_up = models.TextField('Разминка (warm-up)', blank=True)

    # Три отдельных набора задач — три M2M-поля к одной таблице Problem.
    # Django создаёт три отдельных таблицы связей, имена не пересекаются.
    main_problems = models.ManyToManyField(
        Problem, blank=True,
        related_name='lessons_as_main',
        verbose_name='Основные задачи')
    challenge_problems = models.ManyToManyField(
        Problem, blank=True,
        related_name='lessons_as_challenge',
        verbose_name='Задачи-вызов (challenge)')
    homework_problems = models.ManyToManyField(
        Problem, blank=True,
        related_name='lessons_as_homework',
        verbose_name='Домашние задачи')

    # Заметки видны только преподавателю — это подсказка для интерфейса;
    # на уровне базы никакой дополнительной защиты нет.
    teacher_notes = models.TextField('Заметки преподавателя', blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL,
                               on_delete=models.SET_NULL,
                               null=True, blank=True,
                               related_name='lessons',
                               verbose_name='Автор')
    created_at = models.DateTimeField('Создано', auto_now_add=True)

    class Meta:
        verbose_name = 'Занятие'
        verbose_name_plural = 'Занятия'
        ordering = ['-date', '-created_at']

    def __str__(self):
        date_str = self.date.strftime('%d.%m.%Y') if self.date else 'б/д'
        return f'{self.name} ({date_str})'


class Assignment(models.Model):
    """Домашка / назначение — набор задач, выданный конкретным ученикам.
    Может быть привязана к занятию (необязательно)."""

    name = models.CharField('Название', max_length=300)
    problems = models.ManyToManyField(Problem, blank=True,
                                      related_name='assignments',
                                      verbose_name='Задачи')
    # M2M к пользователям. Фильтровать по role=student удобнее в интерфейсе;
    # на уровне базы ограничить нельзя без кастомной through-таблицы.
    students = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True,
                                      related_name='assignments_received',
                                      verbose_name='Ученики')
    deadline = models.DateTimeField('Дедлайн', null=True, blank=True)
    lesson = models.ForeignKey(Lesson, on_delete=models.SET_NULL,
                               null=True, blank=True,
                               related_name='assignments',
                               verbose_name='Занятие')
    author = models.ForeignKey(settings.AUTH_USER_MODEL,
                               on_delete=models.SET_NULL,
                               null=True, blank=True,
                               related_name='assignments_created',
                               verbose_name='Автор')
    created_at = models.DateTimeField('Создано', auto_now_add=True)

    class Meta:
        verbose_name = 'Домашка / назначение'
        verbose_name_plural = 'Домашки / назначения'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Submission(models.Model):
    """Решение ученика: он открывает задачу из домашки, пишет решение,
    может загрузить файл, открывает подсказки и отправляет ответ."""

    class Status(models.TextChoices):
        NOT_STARTED = 'not_started', 'Не начато'
        IN_PROGRESS = 'in_progress', 'В процессе'
        SUBMITTED = 'submitted', 'Отправлено'
        REVIEWED = 'reviewed', 'Проверено'

    student = models.ForeignKey(settings.AUTH_USER_MODEL,
                                on_delete=models.CASCADE,
                                related_name='submissions',
                                verbose_name='Ученик')
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE,
                                   related_name='submissions',
                                   verbose_name='Домашка')
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE,
                                related_name='submissions',
                                verbose_name='Задача')
    solution_text = models.TextField('Текст решения', blank=True)
    solution_file = models.FileField(
        'Прикреплённый файл', upload_to='submissions/%Y/%m/',
        null=True, blank=True)
    submitted_answer = models.TextField('Отправленный ответ', blank=True)
    opened_hints = models.ManyToManyField(Hint, blank=True,
                                          related_name='opened_in',
                                          verbose_name='Открытые подсказки')
    status = models.CharField('Статус', max_length=20,
                              choices=Status.choices,
                              default=Status.NOT_STARTED)
    submitted_at = models.DateTimeField('Дата отправки', null=True, blank=True)

    class Meta:
        verbose_name = 'Решение ученика'
        verbose_name_plural = 'Решения учеников'
        ordering = ['-submitted_at']
        # Один ученик — одно решение на задачу в рамках одной домашки.
        unique_together = ('student', 'assignment', 'problem')

    def __str__(self):
        return f'{self.student} / {self.assignment} / {self.problem}'


class TeacherFeedback(models.Model):
    """Проверка решения ученика преподавателем: балл, ошибки, комментарий."""

    submission = models.OneToOneField(Submission, on_delete=models.CASCADE,
                                      related_name='feedback',
                                      verbose_name='Решение ученика')
    score = models.DecimalField('Балл', max_digits=6, decimal_places=2,
                                null=True, blank=True)
    mistakes = models.ManyToManyField(MistakeTag, blank=True,
                                      related_name='feedbacks',
                                      verbose_name='Отмеченные ошибки')
    comment = models.TextField('Комментарий преподавателя', blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                    on_delete=models.SET_NULL,
                                    null=True, blank=True,
                                    related_name='feedbacks_given',
                                    verbose_name='Кто проверил')
    reviewed_at = models.DateTimeField('Дата проверки', auto_now_add=True)

    class Meta:
        verbose_name = 'Проверка преподавателя'
        verbose_name_plural = 'Проверки преподавателя'
        ordering = ['-reviewed_at']

    def __str__(self):
        score_str = str(self.score) if self.score is not None else '—'
        return f'Проверка: {self.submission} (балл: {score_str})'


class StudentTopicProgress(models.Model):
    """Прогресс конкретного ученика по конкретной теме: число от 0 до 100.
    (Прогресс по навыкам — StudentSkillProgress — создан на Этапе 2.)"""

    student = models.ForeignKey(settings.AUTH_USER_MODEL,
                                on_delete=models.CASCADE,
                                related_name='topic_progress',
                                verbose_name='Ученик')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE,
                              related_name='student_progress',
                              verbose_name='Тема')
    level = models.PositiveSmallIntegerField(
        'Уровень (0–100)', default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)])
    updated_at = models.DateTimeField('Обновлён', auto_now=True)

    class Meta:
        verbose_name = 'Прогресс по теме'
        verbose_name_plural = 'Прогресс по темам'
        ordering = ['student', 'topic']
        unique_together = ('student', 'topic')

    def __str__(self):
        return f'{self.student} — {self.topic}: {self.level}'


# ===========================================================================
# Этап 4а — инфраструктура импорта/экспорта
# ===========================================================================

class Collection(models.Model):
    """Коллекция — сохранённый именованный набор задач. Удобно для экспорта
    конкретного варианта или подборки к занятию."""

    HOMEWORK = 'homework'
    TEST     = 'test'
    SHEET    = 'sheet'
    TEMPLATE_CHOICES = [
        (HOMEWORK, 'Домашнее задание'),
        (TEST,     'Контрольная работа'),
        (SHEET,    'Листок задач'),
    ]

    name          = models.CharField('Название', max_length=300)
    description   = models.TextField('Описание', blank=True)
    token         = models.CharField('Токен', max_length=16, unique=True,
                                     db_index=True, blank=True, null=True)
    template_type = models.CharField('Тип подборки', max_length=20,
                                     choices=TEMPLATE_CHOICES, default=HOMEWORK)
    problems      = models.ManyToManyField(Problem, blank=True,
                                           related_name='collections',
                                           verbose_name='Задачи')
    problem_order = models.JSONField('Порядок задач', default=list)
    author        = models.ForeignKey(settings.AUTH_USER_MODEL,
                                      on_delete=models.SET_NULL,
                                      null=True, blank=True,
                                      related_name='collections',
                                      verbose_name='Автор')
    created_at    = models.DateTimeField('Создана', auto_now_add=True)
    updated_at    = models.DateTimeField('Изменена', auto_now=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(8)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'Коллекция'
        verbose_name_plural = 'Коллекции'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Job(models.Model):
    """Фоновая задача — долгая операция, которая выполняется «в фоне»:
    импорт тысяч задач, генерация PDF, дедупликация и т.д. Здесь мы
    отслеживаем её статус и прогресс."""

    class Kind(models.TextChoices):
        IMPORT = 'import', 'Импорт'
        EXPORT = 'export', 'Экспорт'
        AI_ENRICH = 'ai_enrich', 'AI-обогащение'
        DEDUP = 'dedup', 'Дедупликация'
        BACKUP = 'backup', 'Резервная копия'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает'
        RUNNING = 'running', 'Выполняется'
        DONE = 'done', 'Завершена'
        FAILED = 'failed', 'Ошибка'

    kind = models.CharField('Тип задачи', max_length=20,
                            choices=Kind.choices)
    status = models.CharField('Статус', max_length=20,
                              choices=Status.choices, default=Status.PENDING)
    # params и result — произвольный словарь с параметрами/результатом.
    params = models.JSONField('Параметры', default=dict, blank=True)
    result = models.JSONField('Результат', default=dict, blank=True)
    progress = models.PositiveSmallIntegerField('Прогресс (%)', default=0)
    error_message = models.TextField('Сообщение об ошибке', blank=True)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                   on_delete=models.SET_NULL,
                                   null=True, blank=True,
                                   related_name='jobs',
                                   verbose_name='Кто запустил')
    created_at = models.DateTimeField('Создана', auto_now_add=True)
    finished_at = models.DateTimeField('Завершена', null=True, blank=True)

    class Meta:
        verbose_name = 'Фоновая задача'
        verbose_name_plural = 'Фоновые задачи'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_kind_display()} — {self.get_status_display()}'


class Template(models.Model):
    """LaTeX-шаблон для экспорта задач: преамбула, поля страницы, шрифт,
    нумерация, флаги «показывать ли ответы / решения»."""

    name = models.CharField('Название шаблона', max_length=200)
    preamble = models.TextField(
        'Преамбула LaTeX',
        help_text='Всё, что идёт между \\documentclass{} и \\begin{document}.',
        blank=True)
    header = models.TextField('Заголовок документа', blank=True)

    # Поля страницы в сантиметрах.
    margin_top = models.DecimalField(
        'Верхнее поле (см)', max_digits=4, decimal_places=1, default=2.5)
    margin_bottom = models.DecimalField(
        'Нижнее поле (см)', max_digits=4, decimal_places=1, default=2.5)
    margin_left = models.DecimalField(
        'Левое поле (см)', max_digits=4, decimal_places=1, default=2.0)
    margin_right = models.DecimalField(
        'Правое поле (см)', max_digits=4, decimal_places=1, default=2.0)

    font_size = models.PositiveSmallIntegerField('Размер шрифта (пт)',
                                                 default=12)
    numbering_style = models.CharField('Стиль нумерации', max_length=100,
                                       blank=True,
                                       help_text='Например: «Задача N» или «№N»')
    show_answers = models.BooleanField('Показывать ответы', default=False)
    show_solutions = models.BooleanField('Показывать решения', default=False)
    preview_html = models.TextField('HTML-превью', blank=True)

    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Изменён', auto_now=True)

    class Meta:
        verbose_name = 'Шаблон экспорта'
        verbose_name_plural = 'Шаблоны экспорта'
        ordering = ['name']

    def __str__(self):
        return self.name


class ExportRecord(models.Model):
    """Запись о каждом выполненном экспорте: что выгружали, в каком формате,
    какой файл получился."""

    class Format(models.TextChoices):
        JSON = 'json', 'JSON'
        MARKDOWN = 'markdown', 'Markdown'
        DOCX = 'docx', 'DOCX'
        ZIP = 'zip', 'ZIP-архив'
        TEX = 'tex', 'LaTeX (.tex)'
        PDF = 'pdf', 'PDF'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает'
        DONE = 'done', 'Готово'
        FAILED = 'failed', 'Ошибка'

    format = models.CharField('Формат', max_length=20,
                              choices=Format.choices)
    status = models.CharField('Статус', max_length=20,
                              choices=Status.choices, default=Status.PENDING)
    output_file = models.FileField('Файл-результат',
                                   upload_to='exports/%Y/%m/',
                                   null=True, blank=True)
    job = models.ForeignKey(Job, on_delete=models.SET_NULL,
                            null=True, blank=True,
                            related_name='export_records',
                            verbose_name='Фоновая задача')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                   on_delete=models.SET_NULL,
                                   null=True, blank=True,
                                   related_name='export_records',
                                   verbose_name='Кто создал')
    created_at = models.DateTimeField('Создана', auto_now_add=True)

    class Meta:
        verbose_name = 'Запись об экспорте'
        verbose_name_plural = 'Записи об экспортах'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_format_display()} — {self.get_status_display()}'


class ImportSession(models.Model):
    """Сессия импорта: загружаем файл (PDF, ZIP, JSON), привязываем к источнику
    и отслеживаем, сколько задач было распознано и добавлено."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает'
        PROCESSING = 'processing', 'Обрабатывается'
        DONE = 'done', 'Завершена'
        FAILED = 'failed', 'Ошибка'

    source_file = models.FileField('Исходный файл', upload_to='imports/%Y/%m/')
    source = models.ForeignKey(Source, on_delete=models.SET_NULL,
                               null=True, blank=True,
                               related_name='import_sessions',
                               verbose_name='Источник')
    status = models.CharField('Статус', max_length=20,
                              choices=Status.choices, default=Status.PENDING)
    imported_count = models.PositiveIntegerField(
        'Импортировано задач', default=0)
    job = models.ForeignKey(Job, on_delete=models.SET_NULL,
                            null=True, blank=True,
                            related_name='import_sessions',
                            verbose_name='Фоновая задача')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                   on_delete=models.SET_NULL,
                                   null=True, blank=True,
                                   related_name='import_sessions',
                                   verbose_name='Кто создал')
    created_at = models.DateTimeField('Создана', auto_now_add=True)

    class Meta:
        verbose_name = 'Сессия импорта'
        verbose_name_plural = 'Сессии импорта'
        ordering = ['-created_at']

    def __str__(self):
        return (f'Импорт {self.source_file.name} '
                f'— {self.get_status_display()}')


# ===========================================================================
# Этап 5б — дедупликация через эмбеддинги
# ===========================================================================

class DuplicateCandidate(models.Model):
    """Пара задач-кандидатов на дубликат, найденных по сходству эмбеддингов.

    Создаётся командой find_duplicates (порог similarity >= 0.95).
    Преподаватель просматривает и подтверждает или отклоняет каждую пару.
    При подтверждении задача B автоматически получает статус 'duplicate'.

    Инвариант: всегда problem_a.id < problem_b.id — чтобы пара (A,B) и (B,A)
    не дублировалась в таблице, ограничение unique_together гарантирует это.
    """

    problem_a = models.ForeignKey(
        Problem, on_delete=models.CASCADE,
        related_name='duplicates_as_a',
        verbose_name='Задача A')
    problem_b = models.ForeignKey(
        Problem, on_delete=models.CASCADE,
        related_name='duplicates_as_b',
        verbose_name='Задача B')
    similarity = models.FloatField('Сходство (0–1)')

    status = models.CharField(
        'Статус', max_length=20,
        choices=[
            ('pending',   'На проверке'),
            ('confirmed', 'Подтверждён дубль'),
            ('rejected',  'Не дубль'),
        ],
        default='pending',
    )

    created_at = models.DateTimeField('Найдено', auto_now_add=True)
    reviewed_at = models.DateTimeField('Проверено', null=True, blank=True)
    reviewed_by = models.ForeignKey(
        'User', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_duplicates',
        verbose_name='Проверил',
    )

    class Meta:
        unique_together = ('problem_a', 'problem_b')
        ordering = ['-similarity']
        verbose_name = 'Кандидат на дубликат'
        verbose_name_plural = 'Кандидаты на дубликаты'

    def __str__(self):
        return f'#{self.problem_a_id} ↔ #{self.problem_b_id} ({self.similarity:.3f})'


# ===========================================================================
# Этап 6а — Графический калькулятор Desmos
# ===========================================================================

class DesmosGraph(models.Model):
    """Сохранённый пользователем график Desmos.

    Поле `state` — полное состояние калькулятора в формате JSON
    (получается через calculator.getState() в браузере).
    Восстанавливается через calculator.setState(state).
    """

    title = models.CharField('Название', max_length=200)
    author = models.ForeignKey(
        'User', on_delete=models.CASCADE,
        related_name='desmos_graphs',
        verbose_name='Автор',
    )
    state = models.JSONField('Состояние графика (JSON)')

    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Изменён', auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'График Desmos'
        verbose_name_plural = 'Графики Desmos'

    def __str__(self):
        return f'{self.title} ({self.author})'


# ===========================================================================
# Этап Е — Группы учеников
# ===========================================================================

class StudentGroup(models.Model):
    """Группа учеников у одного учителя. Учитель может иметь несколько групп."""

    name = models.CharField(max_length=100, verbose_name='Название группы')
    teacher = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='teaching_groups',
        limit_choices_to={'role': 'teacher'},
        verbose_name='Преподаватель',
    )
    students = models.ManyToManyField(
        'User',
        blank=True,
        related_name='enrolled_groups',
        limit_choices_to={'role': 'student'},
        verbose_name='Ученики',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')

    class Meta:
        verbose_name = 'Группа учеников'
        verbose_name_plural = 'Группы учеников'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.teacher})'


# ===========================================================================
# Этап Ж — Календарь
# ===========================================================================

class CalendarEvent(models.Model):
    """Событие в учебном календаре: занятие, домашка, олимпиада и т.д."""

    class EventType(models.TextChoices):
        LESSON = 'lesson', 'Занятие'
        HOMEWORK = 'homework', 'Домашка'
        OLYMPIAD = 'olympiad', 'Олимпиада'
        OTHER = 'other', 'Другое'

    title = models.CharField('Название', max_length=300)
    event_type = models.CharField(
        'Тип', max_length=20,
        choices=EventType.choices,
        default=EventType.LESSON,
    )
    color = models.CharField('Цвет (hex)', max_length=7, blank=True, default='')
    start_datetime = models.DateTimeField('Начало')
    end_datetime = models.DateTimeField('Конец', null=True, blank=True)
    description = models.TextField('Описание / ссылка', blank=True)

    assignment = models.ForeignKey(
        'Assignment',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='calendar_events',
        verbose_name='Домашка',
    )
    author = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='calendar_events',
        verbose_name='Автор',
    )
    groups = models.ManyToManyField(
        'StudentGroup',
        blank=True,
        related_name='calendar_events',
        verbose_name='Группы',
    )
    is_global = models.BooleanField('Видно всем', default=False)
    is_recurring = models.BooleanField('Повторяющееся', default=False)
    recur_weeks = models.IntegerField('Повторений (недель)', default=4)
    parent_event = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='recurrences',
        verbose_name='Родительское событие',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_datetime']
        verbose_name = 'Событие календаря'
        verbose_name_plural = 'События календаря'

    def __str__(self):
        dt = self.start_datetime.strftime('%d.%m.%Y')
        return f'{self.get_event_type_display()} — {self.title} ({dt})'


class AutoTopicAssignment(models.Model):
    """Ночная сессия 2026-06-12 — журнал автоназначений тем.

    Тема при автоназначении пишется в обычный M2M Problem.topics (чтобы фильтры
    каталога работали без изменений), а здесь фиксируется ФАКТ автоназначения:
    пара задача↔тема + метрики kNN. Всё, чего нет в этой таблице, — ручное
    назначение. Команда auto_assign_topics --revert удаляет связь из M2M
    по записям этой таблицы и очищает её. Минимально инвазивный вариант:
    существующая M2M-таблица и её строки не меняются.
    """

    problem = models.ForeignKey(Problem, on_delete=models.CASCADE,
                                related_name='auto_topic_assignments',
                                verbose_name='Задача')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE,
                              related_name='auto_assignments',
                              verbose_name='Тема')
    neighbor_votes = models.PositiveSmallIntegerField(
        'Голосов соседей (из 10)', default=0)
    mean_similarity = models.FloatField('Средняя близость соседей', default=0.0)
    created_at = models.DateTimeField('Назначено', auto_now_add=True)

    class Meta:
        verbose_name = 'Автоназначение темы'
        verbose_name_plural = 'Автоназначения тем'
        unique_together = ('problem', 'topic')

    def __str__(self):
        return f'#{self.problem_id} → {self.topic} ({self.neighbor_votes}/10)'


class ReviewVerdict(models.Model):
    """Вердикт ручного ревью внешнего вида задачи (офлайн-пакеты снимков).

    Ревьюер смотрит офлайн-снимок боевой страницы задачи (reviewer.html из
    пакета export_review_bundle) и жмёт клавишу вердикта. Вердикты приезжают
    JSON-файлом и импортируются командой import_review_verdicts.

    СТРОКА НА ПАРУ «задача × категория». У задачи может быть несколько
    дефектов сразу (оболочка v2 разрешает множественный выбор) — тогда это
    несколько строк с одним и тем же комментарием: комментарий относится ко
    всей задаче, а не к отдельной категории. Существующие 2 401 вердикт по
    ILE устроены ровно так же (по одной категории на задачу), поэтому после
    перехода на множественный выбор они остаются валидными без конвертации.

    Ключ идемпотентности — (bundle, problem, category): повторный импорт того
    же файла ничего не дублирует. Пакет в ключе потому, что одна и та же
    задача может попасть в разные пакеты ревью, и это разные измерения, а не
    переголосование. Категории — problems/review_categories.py.
    """

    problem = models.ForeignKey(Problem, on_delete=models.CASCADE,
                                related_name='review_verdicts',
                                verbose_name='Задача')
    # Идентификатор пакета ревью (manifest.bundle_id), напр. 'ile_20260721'.
    bundle = models.CharField('Пакет', max_length=64, blank=True, db_index=True)
    category = models.CharField('Категория', max_length=32,
                                choices=CATEGORY_CHOICES)
    comment = models.TextField('Комментарий', blank=True)
    reviewer = models.CharField('Ревьюер', max_length=64, blank=True)
    # Не auto_now_add: при импорте сюда пишется момент вердикта из JSON
    # (когда ревьюер нажал клавишу), а не момент импорта.
    created_at = models.DateTimeField('Когда вынесен', default=timezone.now)

    class Meta:
        verbose_name = 'Вердикт ревью'
        verbose_name_plural = 'Вердикты ревью'
        constraints = [
            models.UniqueConstraint(fields=['bundle', 'problem', 'category'],
                                    name='uniq_review_verdict_per_category'),
        ]

    def __str__(self):
        return f'#{self.problem_id}: {self.get_category_display()} ({self.reviewer or "аноним"})'


# ===========================================================================
# Платформа для репетиторов — модели вынесены в отдельный модуль.
# Импорт в самом конце, чтобы Django их увидел (app_label='problems').
# Файл: problems/models_platform.py
# ===========================================================================

from .models_platform import (  # noqa: E402,F401
    AssignmentItem,
    CustomProblem,
    CustomProblemOption,
    ProblemComment,
    UserProfile,
)
