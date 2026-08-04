"""
Модели платформы для репетиторов (сессия «Основание платформы»).

Почему отдельный файл, а не `models.py`: основной `models.py` уже 1200 строк
и его правят параллельные ветки. Модуль лежит ВНУТРИ приложения `problems`,
поэтому Django сам определяет app_label='problems' — миграции и таблицы идут
в то же приложение, что и остальные модели. Единственная связь с `models.py` —
одна строка импорта в самом его конце.

Все новые модели этой сессии живут здесь.
"""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


# ===========================================================================
# Фаза 1. Профиль пользователя и роли
# ===========================================================================

# Как роль профиля ложится на старое поле `User.role`.
#
# В проекте УЖЕ есть `User.role` (teacher/student/editor/viewer/public), на
# нём держатся декораторы `teacher_required` / `student_required` и
# `limit_choices_to` у StudentGroup. Заводить вторую независимую систему ролей
# нельзя — они разъедутся. Поэтому профиль — источник правды для новой
# платформы, а `User.role` синхронизируется с ним автоматически.
#
# Родитель получает 'viewer': прав ученика у него быть не должно
# (кабинет родителя — отдельная задача, пока это просто «наблюдатель»).
PROFILE_ROLE_TO_USER_ROLE = {
    'tutor': 'teacher',
    'student': 'student',
    'parent': 'viewer',
}

# Обратное соответствие — когда профиль создаётся уже существующему
# пользователю. Всё, что не преподаватель, считаем учеником.
USER_ROLE_TO_PROFILE_ROLE = {
    'teacher': 'tutor',
    'student': 'student',
    'viewer': 'parent',
}


class UserProfile(models.Model):
    """Профиль пользователя: роль на платформе и учебные данные.

    Имя и фамилия НЕ дублируются — они уже есть в `User` (AbstractUser),
    вторая копия неминуемо разъехалась бы с первой.

    Пароль здесь не хранится и не отображается НИКОГДА: аутентификация —
    только штатным механизмом Django (хэш в `User.password`).
    """

    class Role(models.TextChoices):
        TUTOR = 'tutor', 'Репетитор'
        STUDENT = 'student', 'Ученик'
        PARENT = 'parent', 'Родитель'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='profile', verbose_name='Пользователь',
    )
    # Одна роль на аккаунт. Совмещения (репетитор, который ещё и ученик)
    # не поддерживаем: это отдельный аккаунт.
    role = models.CharField('Роль', max_length=16,
                            choices=Role.choices, default=Role.STUDENT)

    grade = models.PositiveSmallIntegerField(
        'Класс', null=True, blank=True,
        validators=[MinValueValidator(5), MaxValueValidator(11)],
        help_text='5–11, необязательно.',
    )
    school = models.CharField('Школа', max_length=200, blank=True)
    # Телефон НЕОБЯЗАТЕЛЕН. Телефон несовершеннолетнего собираем только по
    # желанию: лишние персональные данные ребёнка — лишний риск по 152-ФЗ.
    phone = models.CharField('Телефон', max_length=32, blank=True,
                             help_text='Необязательно.')

    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Изменён', auto_now=True)

    class Meta:
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'

    def __str__(self):
        return f'{self.user} — {self.get_role_display()}'

    @property
    def is_tutor(self):
        return self.role == self.Role.TUTOR

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_parent(self):
        return self.role == self.Role.PARENT

    @property
    def display_name(self):
        """Как звать пользователя на экране."""
        full = f'{self.user.first_name} {self.user.last_name}'.strip()
        return full or self.user.username

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.sync_user_role()

    def sync_user_role(self):
        """Подтягивает старое поле `User.role` под роль профиля.

        Пишем через `queryset.update()`, а НЕ через `user.save()`: иначе
        сработает post_save на User и мы уйдём в рекурсию профиль → юзер →
        профиль. Суперпользователя не трогаем — у него роль служебная.
        """
        target = PROFILE_ROLE_TO_USER_ROLE.get(self.role)
        if not target:
            return
        user_model = type(self.user)
        if self.user.is_superuser:
            return
        if self.user.role != target:
            user_model.objects.filter(pk=self.user_id).update(role=target)
            self.user.role = target


# ===========================================================================
# Фаза 2. Комментарии к задачам в домашке
# ===========================================================================

class ProblemCommentQuerySet(models.QuerySet):
    """Правила доступа к комментариям живут ЗДЕСЬ, а не в шаблоне.

    Причина простая: шаблон легко забыть. Если правило доступа записано
    один раз в queryset, то любой экран, любой JSON-эндпоинт и любой экспорт
    получают его автоматически.
    """

    def alive(self):
        """Без удалённых (удаление у нас мягкое)."""
        return self.filter(is_deleted=False)

    def visible_for(self, user):
        """Что этот пользователь имеет право видеть.

        Одним запросом на обе роли:
        * репетитор (автор домашки или преподаватель её группы) видит ВСЁ;
        * все видят комментарии с видимостью «группа»;
        * автор видит свои;
        * адресат приватного ответа видит ответ, обращённый к нему.

        Ученик Б не увидит приватный вопрос ученика А ни при каких условиях:
        он не автор, не адресат и не репетитор.
        """
        if not user or not user.is_authenticated:
            return self.none()
        return self.alive().filter(
            models.Q(assignment__author=user)
            | models.Q(assignment__group__teacher=user)
            | models.Q(visibility=ProblemComment.Visibility.GROUP)
            | models.Q(author=user)
            | models.Q(recipient=user)
        ).distinct()


class ProblemComment(models.Model):
    """Комментарий к КОНКРЕТНОЙ ЗАДАЧЕ В КОНКРЕТНОЙ ДОМАШКЕ.

    Это не мессенджер: у разговора всегда есть предмет — вот эта задача вот
    в этой домашке. Поэтому привязка идёт к ПОЗИЦИИ задачи в домашке
    (`AssignmentItem`), а не к задаче каталога: одна и та же задача может
    стоять в трёх разных домашках, и обсуждения у них разные.

    `assignment` хранится отдельно (хотя выводится из позиции) — по нему
    строятся выборки «все комментарии домашки» без лишнего JOIN, и по нему же
    работает правило доступа.
    """

    class Visibility(models.TextChoices):
        GROUP = 'group', 'Видят все в группе'
        PRIVATE = 'private', 'Только репетитор и автор'

    assignment = models.ForeignKey(
        'problems.Assignment', on_delete=models.CASCADE,
        related_name='problem_comments', verbose_name='Домашка')
    problem_item = models.ForeignKey(
        'problems.AssignmentItem', on_delete=models.CASCADE,
        related_name='comments', verbose_name='Задача в домашке')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='problem_comments', verbose_name='Автор')

    # Кому адресован приватный ответ. Нужен ровно для одного случая: репетитор
    # отвечает ученику приватно. Без этого поля ответ репетитора формально
    # «принадлежит репетитору», и ученик своего же ответа не увидел бы.
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='problem_comments_received', verbose_name='Адресат')

    text = models.TextField('Текст')
    # По умолчанию 'group': это значение для репетитора. Комментарий ученика
    # интерфейс создаёт с 'private' — публичные вопросы учеников это канал
    # списывания («а что у тебя получилось в пункте б?»).
    visibility = models.CharField('Видимость', max_length=16,
                                  choices=Visibility.choices,
                                  default=Visibility.GROUP)

    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Изменён', auto_now=True)
    # Удаление мягкое: переписка — это история проверки, физически её терять
    # нельзя (в том числе на случай спора об оценке).
    is_deleted = models.BooleanField('Удалён', default=False)

    objects = ProblemCommentQuerySet.as_manager()

    class Meta:
        verbose_name = 'Комментарий к задаче'
        verbose_name_plural = 'Комментарии к задачам'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['assignment', 'problem_item'],
                         name='idx_comment_assign_item'),
            models.Index(fields=['author', 'created_at'],
                         name='idx_comment_author_date'),
        ]

    def __str__(self):
        return f'{self.author}: {self.text[:40]}'


# ===========================================================================
# Фаза 3. Собственные задачи репетитора, варианты ответа, позиция в домашке
# ===========================================================================

class CustomProblem(models.Model):
    """Задача, написанная самим репетитором. ПРИВАТНАЯ.

    В общий каталог не попадает НИКОГДА: каталог — это выверенный банк
    олимпиадных задач, туда нельзя подмешивать чужой непроверенный контент.
    Видят её автор и его ученики — и только в составе выданной домашки.

    Отдельная модель, а не `Problem` с флагом: у `Problem` 30 полей импорта,
    эмбеддинги, шлюз качества, дедупликация — всё это к задаче репетитора
    отношения не имеет, а любой недосмотр в фильтрах вывалил бы её в каталог.
    """

    class Kind(models.TextChoices):
        OPEN = 'open', 'Открытая задача'
        TF = 'tf', 'Верно / неверно'
        SINGLE = 'single', 'Один верный вариант'
        MULTIPLE = 'multiple', 'Несколько верных вариантов'

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='custom_problems', verbose_name='Автор')
    title = models.CharField('Название', max_length=300, blank=True,
                             help_text='Необязательно.')
    statement = models.TextField(
        'Условие',
        help_text='Формулы в долларах: $Q_d = 100 - P$. Рендерит KaTeX.')
    kind = models.CharField('Тип', max_length=16,
                            choices=Kind.choices, default=Kind.OPEN)

    # Только для открытых задач.
    correct_answer = models.TextField('Правильный ответ', blank=True)
    # Допуск числового сравнения. По умолчанию 0 — точное совпадение.
    # ⚠️ Сравнение чисел идёт через fractions.Fraction (как в «Классике»
    # Econ Rush), а НЕ через float: 0,1 + 0,2 во float даёт 0.30000000000000004
    # и честный ответ ученика был бы засчитан неверным.
    answer_tolerance = models.DecimalField(
        'Допуск', max_digits=12, decimal_places=6, default=0)

    solution = models.TextField('Эталонное решение', blank=True)
    # [{"text": "...", "result": "..."}, ...] — разбивка решения на шаги.
    # Необязательна: свободный текст решения тоже принимается.
    solution_steps = models.JSONField('Шаги решения', null=True, blank=True)

    topic = models.ForeignKey(
        'problems.Topic', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='custom_problems', verbose_name='Тема')
    difficulty = models.PositiveSmallIntegerField(
        'Сложность (1–5)', null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)])

    created_at = models.DateTimeField('Создана', auto_now_add=True)
    updated_at = models.DateTimeField('Изменена', auto_now=True)
    is_deleted = models.BooleanField('Удалена', default=False)

    class Meta:
        verbose_name = 'Своя задача репетитора'
        verbose_name_plural = 'Свои задачи репетиторов'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', '-created_at'],
                         name='idx_customprob_owner'),
        ]

    def __str__(self):
        return self.title or f'Своя задача #{self.pk}'

    @property
    def is_test(self):
        """Тест это или открытая задача (тесты проверяются автоматически)."""
        return self.kind != self.Kind.OPEN

    def correct_option_ids(self):
        return set(self.options.filter(is_correct=True)
                   .values_list('id', flat=True))


class CustomProblemOption(models.Model):
    """Вариант ответа у теста репетитора (tf / single / multiple)."""

    problem = models.ForeignKey(
        CustomProblem, on_delete=models.CASCADE,
        related_name='options', verbose_name='Задача')
    text = models.CharField('Текст варианта', max_length=500)
    is_correct = models.BooleanField('Правильный', default=False)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Вариант ответа'
        verbose_name_plural = 'Варианты ответа'
        ordering = ['order', 'id']

    def __str__(self):
        mark = '✓' if self.is_correct else '·'
        return f'{mark} {self.text[:40]}'


class AssignmentItem(models.Model):
    """Позиция задачи в домашке.

    Зачем нужна отдельная модель, а не просто M2M `Assignment.problems`:
    в домашке рядом стоят задачи каталога и свои задачи репетитора, и у
    КАЖДОЙ ПОЗИЦИИ своя обвязка — порядок, балл, комментарии, решалка,
    график. Повесить это на M2M некуда, а на задачу каталога вешать нельзя:
    одна и та же задача стоит в разных домашках с разными баллами и разными
    обсуждениями.

    Ровно одна из двух ссылок заполнена — это проверяется на уровне БАЗЫ
    (CheckConstraint), а не только в коде: позиция без задачи или с двумя
    задачами сразу — это порча данных, её надо ловить до записи.
    """

    assignment = models.ForeignKey(
        'problems.Assignment', on_delete=models.CASCADE,
        related_name='items', verbose_name='Домашка')
    order = models.PositiveIntegerField('Порядок', default=0)

    catalog_problem = models.ForeignKey(
        'problems.Problem', on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='assignment_items', verbose_name='Задача каталога')
    custom_problem = models.ForeignKey(
        CustomProblem, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='assignment_items', verbose_name='Своя задача')

    points = models.DecimalField('Балл', max_digits=6, decimal_places=2,
                                 null=True, blank=True)

    class Meta:
        verbose_name = 'Задача в домашке'
        verbose_name_plural = 'Задачи в домашке'
        ordering = ['order', 'id']
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(catalog_problem__isnull=False,
                             custom_problem__isnull=True)
                    | models.Q(catalog_problem__isnull=True,
                               custom_problem__isnull=False)
                ),
                name='assignment_item_exactly_one_problem',
            ),
        ]

    def __str__(self):
        return f'{self.assignment}: {self.order}. {self.problem_title}'

    # -- Единая точка доступа к задаче, какой бы она ни была ---------------
    # Экраны не должны каждый раз писать «если каталожная — то так, если
    # своя — то эдак»: расхождение в одном шаблоне и половина страницы пустая.

    @property
    def problem(self):
        """Сама задача — каталожная или своя."""
        return self.catalog_problem or self.custom_problem

    @property
    def is_custom(self):
        return self.custom_problem_id is not None

    @property
    def problem_title(self):
        problem = self.problem
        if problem is None:
            return '(задача удалена)'
        return problem.title or f'Задача #{problem.pk}'

    @property
    def statement(self):
        problem = self.problem
        return problem.statement if problem is not None else ''

    @property
    def is_test(self):
        """Тест ли это (тесты проверяются автоматически, сразу после сдачи)."""
        if self.custom_problem_id is not None:
            return self.custom_problem.is_test
        if self.catalog_problem_id is None:
            return False
        ptype = self.catalog_problem.problem_type or ''
        return ptype.startswith('тест')

    @property
    def correct_answer(self):
        """Правильный ответ в человекочитаемом виде (для страницы репетитора)."""
        if self.custom_problem_id is not None:
            if self.custom_problem.is_test:
                return ', '.join(
                    o.text for o in self.custom_problem.options.filter(
                        is_correct=True))
            return self.custom_problem.correct_answer
        if self.catalog_problem_id is None:
            return ''
        return self.catalog_problem.answer


# ===========================================================================
# Фаза 4. Сохранённое и папки
# ===========================================================================

class SavedFolder(models.Model):
    """Папка «Сохранённого». ПЛОСКАЯ — вложенности нет.

    Дерево папок соблазнительно, но у него всегда одна и та же судьба:
    пользователь строит иерархию один раз, а потом не может вспомнить, куда
    что положил. Плоский список + поиск закрывает задачу и не требует
    ни хлебных крошек, ни перетаскивания, ни разрешения циклов.
    """

    class Kind(models.TextChoices):
        PROBLEMS = 'problems', 'Задачи'
        GRAPHS = 'graphs', 'Графики'

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='saved_folders', verbose_name='Владелец')
    name = models.CharField('Название', max_length=120)
    # Папки задач и папки графиков не смешиваются: список «переместить в
    # папку» на странице задачи не должен предлагать папки для графиков.
    kind = models.CharField('Для чего', max_length=16,
                            choices=Kind.choices, default=Kind.PROBLEMS)
    order = models.PositiveIntegerField('Порядок', default=0)
    created_at = models.DateTimeField('Создана', auto_now_add=True)

    class Meta:
        verbose_name = 'Папка сохранённого'
        verbose_name_plural = 'Папки сохранённого'
        ordering = ['order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['owner', 'kind', 'name'],
                                    name='uniq_saved_folder_name'),
        ]

    def __str__(self):
        return f'{self.name} ({self.get_kind_display()})'


class SavedProblem(models.Model):
    """Задача, отложенная пользователем «к себе».

    Как и позиция в домашке, ссылается либо на каталожную задачу, либо на
    свою — ровно одну из двух (проверяется базой).
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='saved_problems', verbose_name='Владелец')
    catalog_problem = models.ForeignKey(
        'problems.Problem', on_delete=models.CASCADE, null=True, blank=True,
        related_name='saved_by', verbose_name='Задача каталога')
    custom_problem = models.ForeignKey(
        CustomProblem, on_delete=models.CASCADE, null=True, blank=True,
        related_name='saved_by', verbose_name='Своя задача')
    # null = «Без папки». Отдельной служебной папки не заводим: она была бы
    # неудаляемой и всё равно означала бы «не в папке».
    folder = models.ForeignKey(
        SavedFolder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='problems', verbose_name='Папка')
    note = models.TextField('Заметка', blank=True)
    created_at = models.DateTimeField('Сохранена', auto_now_add=True)
    is_deleted = models.BooleanField('Удалена', default=False)

    class Meta:
        verbose_name = 'Сохранённая задача'
        verbose_name_plural = 'Сохранённые задачи'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(catalog_problem__isnull=False,
                             custom_problem__isnull=True)
                    | models.Q(catalog_problem__isnull=True,
                               custom_problem__isnull=False)
                ),
                name='saved_problem_exactly_one_problem',
            ),
            # Одну и ту же задачу нельзя сохранить дважды.
            models.UniqueConstraint(
                fields=['owner', 'catalog_problem'],
                condition=models.Q(catalog_problem__isnull=False),
                name='uniq_saved_catalog_problem'),
            models.UniqueConstraint(
                fields=['owner', 'custom_problem'],
                condition=models.Q(custom_problem__isnull=False),
                name='uniq_saved_custom_problem'),
        ]

    def __str__(self):
        return f'{self.owner}: {self.problem_title}'

    @property
    def problem(self):
        return self.catalog_problem or self.custom_problem

    @property
    def problem_title(self):
        problem = self.problem
        if problem is None:
            return '(задача удалена)'
        return problem.title or f'Задача #{problem.pk}'


class SavedGraph(models.Model):
    """График, сохранённый пользователем из калькулятора.

    ⚠️ Формат `scene` в этой сессии НЕ выясняется и calc2 НЕ трогается.
    Здесь заведено только место для хранения: JSON произвольной формы.
    Что именно в него кладёт калькулятор — вопрос отдельной задачи после
    слияния ветки feat/calc2-shipu.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='saved_graphs', verbose_name='Владелец')
    name = models.CharField('Название', max_length=200)
    scene = models.JSONField('Сцена калькулятора', default=dict, blank=True)
    # Путь к картинке-превью (например, PNG, снятый калькулятором).
    preview = models.CharField('Превью (путь)', max_length=500, blank=True)
    folder = models.ForeignKey(
        SavedFolder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='graphs', verbose_name='Папка')
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Изменён', auto_now=True)
    is_deleted = models.BooleanField('Удалён', default=False)

    class Meta:
        verbose_name = 'Сохранённый график'
        verbose_name_plural = 'Сохранённые графики'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', '-created_at'],
                         name='idx_savedgraph_owner'),
        ]

    def __str__(self):
        return self.name
