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

    class HumanReview(models.TextChoices):
        """Что сказал ЧЕЛОВЕК, посмотревший снимок страницы задачи.

        Три состояния, и их обязательно надо различать между собой:
        NONE — человек задачу не видел (мы про неё ничего не знаем),
        APPROVED — видел и сказал «идеально»,
        DEFECT — видел и нашёл брак (сюда же попадает «Гагно»: это тоже
        осмотренная задача, просто кандидат на выброс, а не на починку).
        """

        NONE = '', 'не смотрели'
        APPROVED = 'approved', 'одобрено человеком'
        DEFECT = 'defect', 'человек нашёл брак'

    status = models.CharField('Статус', max_length=20,
                              choices=Status.choices, default=Status.DRAFT)

    class ContentFormat(models.TextChoices):
        """Как читать statement/answer/solution/ProblemPart.statement.

        PLAIN — как сейчас: автоэскейп Django + `linebreaksbr`, без единого
        байта разметки. Все 31 694 легаси-задачи стоят на PLAIN и здесь и
        останутся — рендерер их не касается.
        MARKDOWN — узкое подмножество markdown (жирный, курсив, списки,
        простые таблицы, переносы строк) через `problems/rendering.py`
        (math-aware препроцессор + `nh3`). Ставится только конвертерами
        новых источников (CORPUS-FORMAT.md §2б), вручную не проставляется.
        """

        PLAIN = 'plain', 'Обычный текст'
        MARKDOWN = 'markdown', 'Markdown'

    content_format = models.CharField(
        'Формат текста', max_length=20,
        choices=ContentFormat.choices, default=ContentFormat.PLAIN,
        help_text='PLAIN — текущее поведение (не трогать). MARKDOWN — '
                  'через math-aware рендерер, для новых источников.',
    )

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

    # --- Человеческое ревью внешнего вида (пакеты export_review_bundle) ---
    # ТРЕТИЙ, независимый признак рядом со status='hidden' и
    # needs_quality_review. Те два отвечают «скрыто, потому что ПЛОХОЕ»;
    # эти два — «что про задачу известно от ЧЕЛОВЕКА» и «скрыто, потому что
    # человек ещё НЕ СМОТРЕЛ». Смешивать их нельзя: иначе не отличить
    # «проверено и забраковано» от «не проверено».
    #
    # Источник правды — строки ReviewVerdict. Поле это денормализованный
    # свод по ним: ходить в вердикты на каждый запрос каталога дорого.
    # Проставляется командой human_review_mark (--apply / --revert).
    human_review = models.CharField(
        'Человеческое ревью',
        max_length=16, choices=HumanReview.choices,
        default=HumanReview.NONE, blank=True, db_index=True,
        help_text='Что сказал человек, посмотревший снимок страницы задачи',
    )

    # Скрытие «до проверки». Отдельный признак, а НЕ status/needs_quality_review:
    # он отвечает на вопрос «человек ещё не смотрел», а не «задача плохая».
    # Ставится и снимается командой pending_review_gate (--apply / --revert),
    # обратимо и без потери прежних состояний.
    hidden_pending_review = models.BooleanField(
        'Скрыта до проверки человеком',
        default=False, db_index=True,
        help_text='Скрыта из каталога, потому что человек её ещё не смотрел',
    )

    # Этап 5а — эмбеддинг для поиска похожих задач.
    # Хранится как bytes (numpy float32 array). Заполняется командой build_embeddings.
    embedding = models.BinaryField(blank=True, null=True)

    # С5 (22.08) — версионирование эмбеддинга. ДО этих полей «что устарело»
    # было памятью человека в файле embeddings_done_ids.txt: правишь текст
    # задачи, а её id уже в файле — пересчёт молча пропускал и писал
    # «осталось 0». Теперь build_embeddings --stale сравнивает эти четыре
    # поля с текущими константами/текстом сам, без внешнего файла.
    embedding_version = models.IntegerField(
        'Версия формулы эмбеддинга', null=True, blank=True,
        help_text='EMBEDDING_FORMULA_VERSION (problems/embedding_config.py) '
                   'на момент расчёта. NULL — вектор посчитан до версионирования.',
    )
    embedding_model_build = models.CharField(
        'Сборка модели эмбеддинга', max_length=64, blank=True, default='',
        help_text='EMBEDDING_MODEL_BUILD (problems/embedding_config.py) '
                   'на момент расчёта. Пусто — вектор посчитан до версионирования.',
    )
    embedding_source_hash = models.CharField(
        'Хеш текста эмбеддинга', max_length=32, blank=True, default='',
        help_text='MD5 текста, который реально закодирован (problem_to_text) '
                   'на момент расчёта. Пусто — вектор посчитан до версионирования.',
    )
    embedding_built_at = models.DateTimeField(
        'Когда посчитан эмбеддинг', null=True, blank=True,
        help_text='NULL у записей, чей вектор посчитан ДО этой сессии — '
                   'легаси, это ожидаемо, не баг.',
    )

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


class ProblemFigure(models.Model):
    """Картинка, СГЕНЕРИРОВАННАЯ этой системой из TikZ/PGFPlots-блока.

    Зачем отдельная таблица, а не тег прямо в тексте задачи.
    Общий санитайзер показа (`problems/rendering.py`, `nh3` с allow-list)
    намеренно не пропускает ни `img`, ни `svg`, ни один атрибут — и
    остаётся таким ([ADR 0031](../docs/adr/0031-tikz-svg-blocked-by-sanitizer.md)).
    Расширить его значило бы дать ЛЮБОМУ тексту задачи право подставить
    произвольный `src`: внешние запросы из браузера ученика,
    трекинг-пиксели. Периметр XSS не расширяется ни на пиксель.

    Поэтому картинка живёт здесь, а в тексте задачи остаётся только
    маркер `[[FIGURE:<hash>]]` — чистый текст без единого атрибута,
    который санитайзер спокойно пропускает как обычные символы. На
    показе маркер заменяется на `<img>` ПОСЛЕ санитайзера, и `src`
    строится по первичному ключу СТРОКИ ЭТОЙ ТАБЛИЦЫ, никогда — по
    тому, что написано в тексте задачи.

    Ключевое свойство безопасности: подставить свой `src` через текст
    задачи невозможно в принципе, потому что из текста берётся только
    hex-хеш, а адрес картинки собирается из объекта БД.
    """

    problem = models.ForeignKey(Problem, on_delete=models.CASCADE,
                                related_name='figures', verbose_name='Задача')
    #: Подпункт, если блок пришёл из него. Нужен для отладки и пересборки,
    #: на безопасность не влияет: поиск всё равно идёт по задаче.
    part = models.ForeignKey(ProblemPart, on_delete=models.CASCADE,
                             null=True, blank=True, related_name='figures',
                             verbose_name='Подпункт')
    #: Поле-источник: statement / answer / solution / part.
    source_field = models.CharField('Поле-источник', max_length=20, blank=True)

    #: SHA-256 исходного TikZ-блока. Он же — тело маркера в тексте.
    #: Хеш, а не автоинкремент: один и тот же блок не компилируется дважды,
    #: а изменение исходника даёт другой хеш и, значит, новую картинку.
    tikz_hash = models.CharField('Хеш TikZ-блока', max_length=64, db_index=True)
    #: Исходный TikZ — хранится, чтобы картинку можно было пересобрать и
    #: чтобы человек мог понять, из чего она получилась.
    tikz_source = models.TextField('Исходный TikZ-блок')
    #: Уже САНИТИЗИРОВАННЫЙ SVG (script/foreignObject/on*/внешние ссылки
    #: сняты до записи — см. problems/corpus_converter/tikz_render.py).
    svg = models.TextField('SVG (санитизированный)')

    created_at = models.DateTimeField('Сгенерирована', auto_now_add=True)

    class Meta:
        verbose_name = 'Сгенерированная картинка'
        verbose_name_plural = 'Сгенерированные картинки'
        # Один блок на задачу — один раз. Повторная генерация обновляет
        # существующую строку, а не плодит копии.
        constraints = [
            models.UniqueConstraint(fields=['problem', 'tikz_hash'],
                                    name='uniq_problem_figure_hash'),
        ]

    def __str__(self):
        return f'Картинка #{self.pk} задачи #{self.problem_id}'



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

    # --- Платформа репетиторов: привязка к группе ------------------------
    # Раньше домашка адресовалась списком учеников (`students`) и к группе
    # отношения не имела. Вкладке «Группы» нужен обратный ход «группа → её
    # задания», поэтому появилась прямая ссылка. Nullable: старые домашки
    # выданы до появления групп.
    group = models.ForeignKey('StudentGroup', on_delete=models.SET_NULL,
                              null=True, blank=True,
                              related_name='assignments',
                              verbose_name='Группа')

    # --- Контрольные (Фаза 6) --------------------------------------------
    class Kind(models.TextChoices):
        HOMEWORK = 'homework', 'Домашка'
        EXAM = 'exam', 'Контрольная'

    class ExamMode(models.TextChoices):
        # Тип A: все пишут одновременно, окно задано жёстко.
        WINDOW = 'window', 'Окно (все одновременно)'
        # Тип Б: сдать до момента X, на выполнение N минут с момента старта.
        LIMIT = 'limit', 'Дедлайн с лимитом времени'

    kind = models.CharField('Тип работы', max_length=16,
                            choices=Kind.choices, default=Kind.HOMEWORK)
    exam_mode = models.CharField('Режим контрольной', max_length=16,
                                 choices=ExamMode.choices,
                                 null=True, blank=True)
    starts_at = models.DateTimeField('Начало окна', null=True, blank=True)
    ends_at = models.DateTimeField('Конец окна', null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(
        'Лимит времени (минут)', null=True, blank=True)
    # ⚠️ УСТАРЕЛО (Фаза 0.3). Источник правды по сроку — `deadline`, одно
    # поле на домашку и на контрольную. Два поля уже дали видимый баг: список
    # ученика печатал «без срока» у контрольной, у которой время было задано,
    # просто в другом поле. Данные перенесены миграцией 0026; поле оставлено
    # (не удаляем ничего, что может быть в чужой ветке), но НЕ читается и
    # НЕ пишется нигде. Спрашивать срок — только через `deadline_at`.
    due_at = models.DateTimeField('Сдать до (устарело)', null=True, blank=True)
    show_results_immediately = models.BooleanField(
        'Показывать результат сразу', default=True,
        help_text='Тесты проверяются автоматически; на контрольной результат '
                  'иногда лучше придержать до проверки открытых задач.')
    # Порядок задач расставил ЧЕЛОВЕК — автоматическая перестановка отменяется.
    #
    # ⚠️ Обычно работа показывается «сначала все тесты, потом все задачи»
    # (`assignment_rows.ordered_items`). Но если репетитор в описании прямо
    # сказал «вторая задача — тест на то-то, первая и третья — обычные», его
    # порядок главнее нашего правила: он расставлял задачи по смыслу урока,
    # а мы — по формальному признаку.
    manual_order = models.BooleanField(
        'Порядок задан вручную', default=False,
        help_text='Не перестраивать задачи «сначала тесты, потом задачи».')

    class Meta:
        verbose_name = 'Домашка / назначение'
        verbose_name_plural = 'Домашки / назначения'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    # --- Контрольные: когда работа открыта ------------------------------

    @property
    def is_exam(self):
        return self.kind == self.Kind.EXAM

    @property
    def deadline_at(self):
        """Срок сдачи. ЕДИНСТВЕННЫЙ способ его спросить.

        Поле одно — `deadline`. Свойство оставлено (а не заменено на прямое
        обращение к полю) намеренно: весь код уже ходит через него, и если
        завтра срок снова усложнится, менять придётся одну строку, а не сорок.
        """
        return self.deadline

    @property
    def points_locked(self):
        """Заперты ли баллы за задачи этой работы.

        ⚠️ ПРАВИЛО: МЕНЯТЬ МОЖНО ДО ПЕРВОЙ СДАЧИ. Как только хотя бы один
        ученик отправил работу, максимальные баллы всех позиций запираются:
        оценки уже выставлены по старой шкале, и смена максимума задним
        числом делает бессмысленными и балл ученика, и итог работы, и
        проценты в статистике. Ученик, получивший «2 из 2», после правки
        максимума на 5 обнаружил бы у себя «2 из 5», ничего не сделав.

        Запирается ВСЯ работа целиком, а не отдельная позиция: итог работы —
        сумма, и подвинутый максимум одной задачи меняет знаменатель у всех.
        """
        return self.submissions.filter(
            status__in=('submitted', 'reviewed')).exists()

    def open_state_for(self, user, now=None):
        """(открыта ли, человеческая причина). Причина нужна экрану: «закрыто»
        без объяснения выглядит как поломка."""
        from django.utils import timezone as _tz
        now = now or _tz.now()

        # Домашку сдают когда угодно — дедлайн лишь помечает опоздание.
        # Так работало до появления контрольных, и менять это нельзя:
        # половина смысла домашки в том, что её можно дослать.
        if not self.is_exam:
            return True, ''

        if self.exam_mode == self.ExamMode.WINDOW:
            if self.starts_at and now < self.starts_at:
                # Через `timefmt`: f-строка напечатала бы UTC (см. модуль).
                from .timefmt import fmt

                return False, 'Начало %s.' % fmt(self.starts_at)
            if self.ends_at and now > self.ends_at:
                return False, 'Окно контрольной закрыто.'
            return True, ''

        if self.exam_mode == self.ExamMode.LIMIT:
            if self.deadline and now > self.deadline:
                return False, 'Срок сдачи прошёл.'
            attempt = None
            if user is not None and getattr(user, 'is_authenticated', False):
                attempt = self.exam_attempts.filter(student=user).first()
            if attempt is not None:
                if attempt.submitted_at is not None:
                    return False, 'Работа уже сдана.'
                if attempt.expires_at and now >= attempt.expires_at:
                    return False, 'Время на выполнение вышло.'
            return True, ''

        # Контрольная без режима — считаем обычной работой, не запираем.
        return True, ''

    def is_open_for(self, user, now=None):
        return self.open_state_for(user, now)[0]


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
    # Задача каталога. Стала необязательной: домашка может содержать и
    # СВОЮ задачу репетитора, у которой записи в Problem нет вовсе.
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE,
                                null=True, blank=True,
                                related_name='submissions',
                                verbose_name='Задача')
    # Позиция задачи в домашке — новый, точный адрес решения (одна и та же
    # задача может стоять в домашке дважды, и это разные позиции).
    # Старые решения ссылаются только на `problem`, поэтому поле nullable.
    problem_item = models.ForeignKey('problems.AssignmentItem',
                                     on_delete=models.CASCADE,
                                     null=True, blank=True,
                                     related_name='submissions',
                                     verbose_name='Задача в домашке')
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
        constraints = [
            # То же правило для нового адреса (позиции в домашке). Отдельным
            # ограничением, а не расширением unique_together: у старых записей
            # problem_item пустой, а NULL в уникальности не участвует.
            models.UniqueConstraint(
                fields=['student', 'problem_item'],
                condition=models.Q(problem_item__isnull=False),
                name='uniq_submission_per_item'),
        ]

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

    # --- Владение темой (Фаза 2.2) ---------------------------------------
    # Второй модели «владение темой» не заводим: она разошлась бы с этой.
    # Счётчики свёрнуты из учебных событий, пересобираются командой
    # `recalculate_gamification`. Пороги перехода — в `problems/
    # gamification.py` (MASTERY_RULES), там же и объяснение цифр.
    attempted = models.PositiveIntegerField('Попыток', default=0)
    solved = models.PositiveIntegerField('Решено верно', default=0)
    # Решено верно среди задач сложности 4–5. Нужен отдельно: «разобрался»
    # без единой трудной задачи — это не разобрался, а натренировался
    # на лёгких.
    solved_hard = models.PositiveIntegerField('Из них сложных', default=0)
    mastery_level = models.CharField(
        'Владение', max_length=16, default='none',
        choices=[('none', 'Не начата'), ('familiar', 'Знаком'),
                 ('confident', 'Уверенно'), ('mastered', 'Разобрался')])
    last_activity_at = models.DateTimeField('Последняя активность',
                                            null=True, blank=True)

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


class OlympiadRef(models.Model):
    """Привязка задачи банка к конкретному туру реальной олимпиады,
    найденная сопоставлением по прямой ссылке (SourceReference.url) с
    внешним индексом SolveHub/ILE. Ничего не меняет в Problem/SourceReference —
    чисто дополнительная информация, источник на сайте не переключает.

    Одна Problem может встречаться в НЕСКОЛЬКИХ турах одной или разных
    олимпиад (задачу могли переиздать) — поэтому problem не unique сама
    по себе, unique пара (problem, event_id).
    """

    problem = models.ForeignKey(
        Problem, on_delete=models.CASCADE,
        related_name='olympiad_refs', verbose_name='Задача')

    source_site = models.CharField(
        'Откуда взято сопоставление', max_length=20,
        choices=[('solvehub', 'SolveHub'), ('ile', 'ILE / iloveeconomics.ru')])

    olympiad_slug = models.CharField('Слаг олимпиады', max_length=50)
    olympiad_name = models.CharField('Название олимпиады', max_length=300, blank=True)
    academic_year = models.CharField('Учебный год', max_length=20, blank=True)
    year = models.PositiveIntegerField('Год тура', null=True, blank=True)
    stage = models.CharField('Этап', max_length=50, blank=True)
    grade = models.CharField('Класс', max_length=50, blank=True)
    variant = models.CharField('Вариант', max_length=100, blank=True)
    number = models.CharField('Номер в туре', max_length=50, blank=True)

    event_id = models.CharField('ID тура в источнике', max_length=200)
    record_id = models.CharField('ID записи в источнике', max_length=300)

    match_method = models.CharField(
        'Метод сопоставления', max_length=30,
        choices=[('url_exact', 'Точное совпадение ссылки')],
        default='url_exact')
    match_score = models.FloatField('Уверенность сопоставления', default=1.0)
    official_url = models.URLField('Ссылка-источник сопоставления', max_length=500, blank=True)

    raw_meta = models.JSONField('Прочие поля из экспорта', null=True, blank=True)

    reviewed_by_human = models.BooleanField('Проверено человеком', default=False)
    created_at = models.DateTimeField('Найдено', auto_now_add=True)

    class Meta:
        unique_together = ('problem', 'event_id')
        ordering = ['olympiad_slug', 'year', 'stage']
        verbose_name = 'Привязка к олимпиаде'
        verbose_name_plural = 'Привязки к олимпиадам'

    def __str__(self):
        return f'#{self.problem_id} → {self.olympiad_slug} {self.year} {self.stage}'


# ===========================================================================
# Этап Е — Группы учеников
# ===========================================================================

class StudentGroup(models.Model):
    """Занятие: группа или один на один.

    ⚠️ ИНДИВИДУАЛЬНЫЙ УЧЕНИК — ЭТО ТА ЖЕ МОДЕЛЬ, А НЕ ВТОРАЯ СУЩНОСТЬ
    (сессия 9, фаза 9). В олимпиадной экономике многие репетиторы ведут один
    на один, и вся платформа была построена вокруг группы. Заводить рядом
    вторую модель значило бы удвоить всё, что к группе привязано: задания,
    комментарии, статистику, права доступа, экспорт.

    ⚠️ ТИП ВЫБИРАЕТСЯ ПРИ СОЗДАНИИ И НЕ ВЫЧИСЛЯЕТСЯ ИЗ ЧИСЛА УЧЕНИКОВ.
    Группа, из которой ушли двое, не должна сама превратиться в
    индивидуальную и потерять теплокарту со сравнениями; и наоборот — к
    индивидуальному можно подсадить второго (брат, друг), и история при
    этом не теряется. Проверка «учеников ровно один» выглядит проще, но
    молча меняет вид экрана за спиной у репетитора.
    """

    class Kind(models.TextChoices):
        GROUP = 'group', 'Группа'
        INDIVIDUAL = 'individual', 'Индивидуально'

    kind = models.CharField('Тип занятия', max_length=16,
                            choices=Kind.choices, default=Kind.GROUP,
                            db_index=True)
    name = models.CharField(max_length=100, verbose_name='Название группы')
    # Добавлено вместе с вкладкой «Группы»: форма создания просит название
    # и описание, а хранить описание было негде.
    description = models.TextField('Описание', blank=True)
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

    # Внутригрупповой рейтинг — ПО ВЫБОРУ РЕПЕТИТОРА и по умолчанию выключен.
    # Соревнование помогает не всем: отстающему публичное место в таблице
    # мешает, а решает это не платформа, а человек, который знает группу.
    # Публичного рейтинга между группами нет и не планируется.
    leaderboard_enabled = models.BooleanField(
        'Показывать рейтинг в группе', default=False,
        help_text='Ученик увидит топ-3 и своё место. Полный список '
                  'с аутсайдерами не показывается никогда.')

    class Meta:
        verbose_name = 'Группа учеников'
        verbose_name_plural = 'Группы учеников'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.teacher})'

    @property
    def is_individual(self):
        """Занятие один на один. Ветвление экранов идёт ТОЛЬКО через него."""
        return self.kind == self.Kind.INDIVIDUAL

    @property
    def single_student(self):
        """Единственный ученик индивидуального занятия — или None.

        ⚠️ Возвращает None и у индивидуального занятия, к которому подсадили
        второго. Тип при этом НЕ меняется: шапка просто перестаёт показывать
        имя, а всё остальное продолжает работать. Молча превращать занятие
        в группу нельзя — историю и вид экрана выбирает человек.
        """
        if not self.is_individual:
            return None
        students = list(self.students.all()[:2])
        return students[0] if len(students) == 1 else None

    @property
    def kind_label(self):
        """Подпись чипа типа на карточке: «группа» / «индивидуально»."""
        return 'индивидуально' if self.is_individual else 'группа'

    @property
    def display_name(self):
        """Как занятие называется в ОДНУ строку — крошки, ссылки, подписи.

        У индивидуального это ИМЯ УЧЕНИКА. Название по умолчанию с ним и
        совпадает, но переименовать занятие никто не мешает, а репетитор
        ищет глазами человека, а не выдуманное слово.
        """
        solo = self.single_student
        if solo is not None:
            return solo.get_full_name() or solo.username
        return self.name


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
    # Цитаты: куски текста, выделенные ревьюером прямо на экране, с
    # комментарием к каждому. Список словарей {text, note, side, view,
    # field, at}. Лежат ОДИНАКОВО на всех строках одной задачи — ровно как
    # `comment`: цитата относится к задаче, а не к отдельной категории.
    # Пустой список означает «цитат нет», а не «формат без цитат»: файлы v2
    # тоже импортируются, просто оставляют поле пустым.
    quotes = models.JSONField('Цитаты', default=list, blank=True)
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

from .models_gamification import (  # noqa: E402,F401
    Achievement,
    DailySummary,
    EarnedAchievement,
    MasteryLevel,
    ParentLink,
    PersonalRecord,
    StudentProgressProfile,
)
from .models_platform import (  # noqa: E402,F401
    AiUsageLog,
    AnswerDraft,
    AssignmentItem,
    CustomProblem,
    CustomProblemOption,
    ExamAttempt,
    LearningEvent,
    PartAnswer,
    ProblemComment,
    SolutionVisibility,
    SavedFolder,
    SavedGraph,
    SavedProblem,
    UserProfile,
    WorkFeedback,
)
