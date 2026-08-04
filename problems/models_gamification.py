"""
Модели статистики и геймификации (сессия «Статистика и контрольные»).

Отдельный модуль по той же причине, что и `models_platform.py`: `models.py`
уже за тысячу строк, а Django видит модели по расположению файла ВНУТРИ
приложения, а не по имени — app_label остаётся 'problems'.

Главный принцип этой части: НИЧЕГО НЕ СЧИТАЕТСЯ НА ЛЕТУ ИЗ ВСЕЙ ИСТОРИИ.
Событий (`LearningEvent`) у активного ученика за год набегают десятки тысяч;
считать по ним «сколько решено за месяц» на каждое открытие страницы — это
секунды ожидания и сотни запросов. Поэтому рядом с событиями живут свёртки:
дневная сводка, владение темой, профиль прогресса. События остаются
единственным ПЕРВОИСТОЧНИКОМ — свёртки всегда можно пересобрать из них
командой `recalculate_gamification`.
"""
from django.conf import settings
from django.core.cache import cache
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


# ===========================================================================
# Фаза 1. Связь «родитель — ребёнок»
# ===========================================================================

class ParentLink(models.Model):
    """Кто чей родитель.

    Отдельная модель, а не поле `UserProfile.child`: связь ДВУСТОРОННЯЯ и
    множественная с обеих сторон — у родителя бывает двое детей, у ребёнка
    двое родителей (и это самый обычный случай, а не редкость).

    Кто создал связь, хранится намеренно: доступ к учебным данным ребёнка —
    чувствительная вещь, и «кто выдал» должно быть видно без раскопок.
    Создаётся связь пока только репетитором через админку или демо-данными;
    самозаписи родителей нет — иначе достаточно знать логин ребёнка.
    """

    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='children_links', verbose_name='Родитель')
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='parent_links', verbose_name='Ученик')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='parent_links_created', verbose_name='Кто связал')
    created_at = models.DateTimeField('Создана', auto_now_add=True)

    class Meta:
        verbose_name = 'Связь родитель — ребёнок'
        verbose_name_plural = 'Связи родитель — ребёнок'
        ordering = ['parent', 'student']
        constraints = [
            models.UniqueConstraint(fields=['parent', 'student'],
                                    name='uniq_parent_student'),
        ]

    def __str__(self):
        return f'{self.parent} → {self.student}'


# ===========================================================================
# Фаза 2.1. Профиль прогресса ученика
# ===========================================================================

class StudentProgressProfile(models.Model):
    """Опыт, уровень и серия дней — один на ученика.

    Свёртка, а не расчёт: уровень выводится из `xp_total`, но хранится, чтобы
    показывать его без вычисления, а серия дней в принципе не выводится из
    одного запроса — она зависит от ПОРЯДКА дней и от потраченных заморозок.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='progress_profile', verbose_name='Ученик')

    xp_total = models.PositiveIntegerField('Всего опыта', default=0)
    level = models.PositiveSmallIntegerField('Уровень', default=1)

    current_streak = models.PositiveIntegerField('Серия дней', default=0)
    longest_streak = models.PositiveIntegerField('Лучшая серия', default=0)
    last_active_date = models.DateField('Последний зачтённый день',
                                        null=True, blank=True)

    # Заморозка спасает серию за пропущенный день. Две в месяц: больше —
    # и серия перестаёт что-либо значить, меньше — одна поездка к бабушке
    # обнуляет три месяца работы.
    freezes_available = models.PositiveSmallIntegerField('Заморозок осталось',
                                                         default=2)
    freezes_used_this_month = models.PositiveSmallIntegerField(
        'Заморозок потрачено в этом месяце', default=0)
    # Первое число месяца, к которому относится счётчик заморозок. Без него
    # «обнуляется первого числа» требовало бы фонового задания; так обнуление
    # происходит при первом же обращении в новом месяце.
    freezes_period = models.DateField('Месяц заморозок', null=True, blank=True)

    weekly_goal = models.PositiveSmallIntegerField(
        'Цель на неделю (задач)', default=20,
        validators=[MinValueValidator(1), MaxValueValidator(500)])

    updated_at = models.DateTimeField('Обновлён', auto_now=True)

    class Meta:
        verbose_name = 'Прогресс ученика'
        verbose_name_plural = 'Прогресс учеников'

    def __str__(self):
        return f'{self.user}: ур. {self.level}, {self.xp_total} опыта'


# ===========================================================================
# Фаза 2.2. Владение темой — поля добавлены в StudentTopicProgress
# ===========================================================================
#
# Второй модели «владение темой» здесь НЕТ намеренно. `StudentTopicProgress`
# (ученик × тема) уже существует с Этапа 2, на неё смотрит страница прогресса
# и панель учителя. Вторая таблица про то же самое неминуемо разошлась бы с
# первой, и «сколько решено по теме» стало бы зависеть от того, какой экран
# спросил. Новые поля (attempted / solved / solved_hard / mastery_level /
# last_activity_at) добавлены прямо в неё — см. `problems/models.py`.


class MasteryLevel(models.TextChoices):
    """Уровни владения темой. Пороги — в `problems/gamification.py`."""
    NONE = 'none', 'Не начата'
    FAMILIAR = 'familiar', 'Знаком'
    CONFIDENT = 'confident', 'Уверенно'
    MASTERED = 'mastered', 'Разобрался'


# ===========================================================================
# Фаза 2.3–2.4. Достижения
# ===========================================================================

class Achievement(models.Model):
    """Справочник достижений. Наполняется командой `seed_achievements`.

    Условие лежит в JSON, а не в питон-коде каждого достижения: правила
    заведомо будут меняться, и менять их должно быть можно, не трогая
    проверяльщик. Формат — `{"type": "...", "value": N}`, разбирается в
    `problems/gamification.py::check_achievements`.
    """

    class Category(models.TextChoices):
        DEPTH = 'depth', 'Глубина'
        CONSISTENCY = 'consistency', 'Постоянство'
        SKILL = 'skill', 'Мастерство'
        MILESTONE = 'milestone', 'Веха'

    code = models.SlugField('Код', max_length=64, unique=True)
    title = models.CharField('Название', max_length=120)
    description = models.CharField('Условие получения', max_length=300)
    icon = models.CharField('Значок', max_length=8, default='🏅')
    category = models.CharField('Категория', max_length=16,
                                choices=Category.choices,
                                default=Category.MILESTONE)
    condition = models.JSONField('Условие (машинное)', default=dict)
    order = models.PositiveSmallIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Достижение'
        verbose_name_plural = 'Достижения'
        ordering = ['category', 'order', 'id']

    def __str__(self):
        return f'{self.icon} {self.title}'

    def rarity_percent(self):
        """Доля учеников, у которых это достижение есть — как в Steam.

        Считается по ученикам, у которых ВООБЩЕ есть учебный прогресс:
        делить на всех зарегистрированных нечестно — аккаунты репетиторов и
        родителей учебных достижений не получают в принципе, и любая награда
        выглядела бы редчайшей.

        Кэш на 10 минут: цифра меняется медленно, а запрос идёт на каждую из
        двух с лишним десятков плиток экрана достижений.
        """
        key = 'achv_rarity_%s' % self.pk
        cached = cache.get(key)
        if cached is not None:
            return cached

        total = StudentProgressProfile.objects.filter(xp_total__gt=0).count()
        if not total:
            value = 0.0
        else:
            owners = EarnedAchievement.objects.filter(
                achievement=self).values('user').distinct().count()
            value = round(owners * 100.0 / total, 1)
        cache.set(key, value, 600)
        return value


class EarnedAchievement(models.Model):
    """Полученное достижение. Выдаётся один раз и не отнимается.

    Отнимать нельзя даже при пересчёте правил: награда, которую забрали, —
    худшее, что можно сделать с мотивацией. Если правило ужесточили, старые
    обладатели остаются обладателями.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='achievements', verbose_name='Ученик')
    achievement = models.ForeignKey(
        Achievement, on_delete=models.CASCADE,
        related_name='earned_by', verbose_name='Достижение')
    earned_at = models.DateTimeField('Получено', auto_now_add=True)

    class Meta:
        verbose_name = 'Полученное достижение'
        verbose_name_plural = 'Полученные достижения'
        ordering = ['-earned_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'achievement'],
                                    name='uniq_earned_achievement'),
        ]

    def __str__(self):
        return f'{self.user}: {self.achievement}'


# ===========================================================================
# Фаза 2.5. Личные рекорды
# ===========================================================================

class PersonalRecord(models.Model):
    """Личный рекорд ученика — по одному на вид.

    `value` числовой у всех видов, чтобы «побит ли рекорд» проверялось одним
    сравнением; всё остальное (какая именно задача, какой день) — в payload.
    """

    class Kind(models.TextChoices):
        BEST_CORRECT_STREAK = 'best_correct_streak', 'Верных подряд'
        HARDEST_SOLVED = 'hardest_solved', 'Самая сложная решённая'
        MOST_PRODUCTIVE_DAY = 'most_productive_day', 'Лучший день'
        FASTEST_HOMEWORK = 'fastest_homework', 'Быстрее всего сдал домашку'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='records', verbose_name='Ученик')
    kind = models.CharField('Вид', max_length=32, choices=Kind.choices)
    value = models.FloatField('Значение', default=0)
    payload = models.JSONField('Подробности', default=dict, blank=True)
    achieved_at = models.DateTimeField('Когда', auto_now=True)

    class Meta:
        verbose_name = 'Личный рекорд'
        verbose_name_plural = 'Личные рекорды'
        ordering = ['user', 'kind']
        constraints = [
            models.UniqueConstraint(fields=['user', 'kind'],
                                    name='uniq_personal_record'),
        ]

    def __str__(self):
        return f'{self.user}: {self.get_kind_display()} = {self.value}'


# ===========================================================================
# Фаза 2.6. Дневная сводка
# ===========================================================================

class DailySummary(models.Model):
    """Один день учёбы одного ученика — свёрнутый.

    Ради неё всё и затевалось: теплокарта за год это 365 строк вместо десятков
    тысяч событий, а «сколько занимался в марте» — одно `SUM` вместо перебора.
    Пересобирается из событий и потому не является первоисточником: потерять
    её не страшно, `recalculate_gamification` соберёт заново.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='daily_summaries', verbose_name='Ученик')
    date = models.DateField('День')

    xp_earned = models.PositiveIntegerField('Опыта за день', default=0)
    problems_attempted = models.PositiveIntegerField('Попыток', default=0)
    problems_solved = models.PositiveIntegerField('Решено верно', default=0)
    time_spent_seconds = models.PositiveIntegerField('Секунд', default=0)
    # Засчитан ли день в серию. Хранится, а не выводится: правило зачёта
    # («сдал работу ИЛИ ≥3 попыток») может измениться, и старые дни должны
    # остаться зачтёнными по правилу, действовавшему тогда.
    counted_for_streak = models.BooleanField('Зачтён в серию', default=False)

    class Meta:
        verbose_name = 'Дневная сводка'
        verbose_name_plural = 'Дневные сводки'
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(fields=['user', 'date'],
                                    name='uniq_daily_summary'),
        ]
        indexes = [
            models.Index(fields=['user', 'date'], name='idx_daily_user_date'),
        ]

    def __str__(self):
        return f'{self.user} — {self.date}: {self.xp_earned} опыта'
