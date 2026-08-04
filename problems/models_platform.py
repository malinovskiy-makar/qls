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
from django.utils import timezone


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

    # --- Связь родитель ↔ ребёнок (Фаза 1) --------------------------------
    # Методы на профиле, а на модели связи — только данные: экраны спрашивают
    # «чьи дети» у профиля, а не собирают запрос сами.

    def children(self):
        """Дети этого родителя. У кого угодно другого — пусто."""
        from .models import User
        return User.objects.filter(parent_links__parent=self.user).distinct()

    def parents(self):
        """Родители этого ученика (их может быть несколько)."""
        from .models import User
        return User.objects.filter(children_links__student=self.user).distinct()

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


def assignment_deadline(assignment):
    """Срок сдачи работы одним понятием — `Assignment.deadline`.

    Полей срока когда-то было два (`deadline` у домашки и `due_at` у
    контрольной типа Б), и они разъехались ровно так, как и должны были:
    экран, спросивший не то поле, печатал «без срока» у работы со сроком.
    С Фазы 0.3 поле одно, а эта функция осталась единственной точкой
    вопроса — чтобы следующий такой раскол ловился в одном месте.
    """
    if assignment is None:
        return None
    return assignment.deadline


class SolutionVisibility(models.TextChoices):
    """Когда ученик увидит эталонное решение."""
    DEADLINE = 'deadline', 'После дедлайна'
    SUBMIT = 'submit', 'Сразу после сдачи'
    MANUAL = 'manual', 'Вручную'
    NEVER = 'never', 'Никогда'


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

    # --- Фаза 19. График к задаче ----------------------------------------
    # Ссылка на сохранённый график калькулятора. Пока показывается плашкой
    # с названием: формат сцены не определён (calc2 в этой сессии не
    # трогали), полноценная отрисовка появится, когда он будет известен.
    graph = models.ForeignKey(
        'problems.SavedGraph', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assignment_items', verbose_name='График')

    # --- Фаза 5. Решалка ---------------------------------------------------
    # Пусто = берём решение из каталога (или из своей задачи). Заполнено =
    # репетитор написал своё и оно главнее. Так у задач каталога без решения
    # появляется решение, а у задач с решением — возможность его заменить,
    # и при этом каталог остаётся нетронутым.
    solution_override = models.TextField('Своё решение', blank=True)
    # [{"text": "...", "result": "..."}, ...] — то же, что у своей задачи.
    solution_steps = models.JSONField('Шаги решения', null=True, blank=True)
    solution_visible_after = models.CharField(
        'Когда показать решение', max_length=16,
        choices=SolutionVisibility.choices,
        default=SolutionVisibility.DEADLINE)
    # Момент, когда репетитор нажал «Открыть решение сейчас».
    solution_released_at = models.DateTimeField(
        'Открыто вручную', null=True, blank=True)

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

    # --- Фаза 5. Решение: что показывать и кому --------------------------

    @property
    def solution_source(self):
        """Откуда решение: 'own' — своё, 'catalog' — из каталога, '' — нет."""
        if self.solution_override.strip():
            return 'own'
        problem = self.problem
        if problem is not None and (problem.solution or '').strip():
            return 'catalog' if not self.is_custom else 'own'
        return ''

    @property
    def solution_text(self):
        """Текст решения с учётом замены."""
        if self.solution_override.strip():
            return self.solution_override
        problem = self.problem
        return (problem.solution or '') if problem is not None else ''

    @property
    def has_solution(self):
        return bool(self.solution_text.strip())

    def is_tutor_for(self, user):
        """Репетитор этой домашки: её автор или преподаватель её группы."""
        if user is None or not user.is_authenticated:
            return False
        assignment = self.assignment
        if assignment.author_id == user.pk:
            return True
        group = getattr(assignment, 'group', None)
        return group is not None and group.teacher_id == user.pk

    def _student_submitted(self, user):
        """Сдал ли этот ученик эту позицию."""
        from .models import Submission
        return Submission.objects.filter(
            student=user, assignment=self.assignment,
            status__in=('submitted', 'reviewed'),
        ).filter(
            models.Q(problem_item=self)
            | models.Q(problem_item__isnull=True,
                       problem=self.catalog_problem_id)
        ).exists()

    def is_solution_visible_for(self, user, now=None):
        """Можно ли ЭТОМУ пользователю показать эталонное решение.

        Репетитор видит всегда — он его и написал. Для ученика:
        * `deadline` — после дедлайна домашки. ЕСЛИ ДЕДЛАЙНА НЕТ, решение
          НЕ показывается, пока репетитор не откроет вручную: «после
          никогда» не наступает, а показать решение раньше времени —
          необратимо (задачу уже не задать заново);
        * `submit`   — после того, как ЭТОТ ученик сдал;
        * `manual`   — только если репетитор нажал «Открыть решение»;
        * `never`    — никогда, и ручное открытие тут не работает.
        """
        if user is None or not getattr(user, 'is_authenticated', False):
            return False
        if self.is_tutor_for(user):
            return True
        if not self.has_solution:
            return False

        now = now or timezone.now()
        mode = self.solution_visible_after
        released = (self.solution_released_at is not None
                    and self.solution_released_at <= now)

        if mode == SolutionVisibility.NEVER:
            return False
        if mode == SolutionVisibility.MANUAL:
            return released
        if mode == SolutionVisibility.SUBMIT:
            return self._student_submitted(user)
        # SolutionVisibility.DEADLINE
        deadline = assignment_deadline(self.assignment)
        if deadline is None:
            return released
        return now >= deadline or released

    def solution_unlock_hint(self):
        """Человеческая подсказка «когда откроется» — вместо пустоты."""
        mode = self.solution_visible_after
        if mode == SolutionVisibility.NEVER:
            return 'Решение к этой задаче не показывается.'
        if mode == SolutionVisibility.SUBMIT:
            return 'Решение откроется сразу после того, как вы сдадите работу.'
        if mode == SolutionVisibility.MANUAL:
            return 'Решение откроет преподаватель.'
        deadline = assignment_deadline(self.assignment)
        if deadline is None:
            return 'Дедлайна нет — решение откроет преподаватель.'
        return f'Решение откроется после дедлайна {deadline:%d.%m.%Y %H:%M}.'


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


# ===========================================================================
# Фаза 5. Решалка — правила показа эталонного решения
# ===========================================================================

# ===========================================================================
# Фаза 6. Контрольные: попытка и черновики ответов
# ===========================================================================

class ExamAttempt(models.Model):
    """Попытка ученика написать контрольную.

    ⚠️ ГЛАВНОЕ: `expires_at` вычисляет СЕРВЕР в момент старта. Часам на
    устройстве ученика доверия нет — перевести системное время на час назад
    умеет любой школьник. Клиент получает готовый момент истечения и только
    рисует обратный отсчёт; решение «время вышло» принимает сервер.
    """

    assignment = models.ForeignKey(
        'problems.Assignment', on_delete=models.CASCADE,
        related_name='exam_attempts', verbose_name='Работа')
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='exam_attempts', verbose_name='Ученик')

    started_at = models.DateTimeField('Начата', auto_now_add=True)
    expires_at = models.DateTimeField('Истекает', null=True, blank=True)
    submitted_at = models.DateTimeField('Сдана', null=True, blank=True)
    is_auto_submitted = models.BooleanField('Сдана автоматически',
                                            default=False)
    # Обновляется при автосохранении черновика: видно, что ученик жив и
    # работа не брошена.
    last_heartbeat = models.DateTimeField('Последняя активность',
                                          null=True, blank=True)

    class Meta:
        verbose_name = 'Попытка контрольной'
        verbose_name_plural = 'Попытки контрольных'
        ordering = ['-started_at']
        constraints = [
            # Одна попытка на пару (работа, ученик). Вторая попытка — это
            # уже другая контрольная, а не «ещё разок».
            models.UniqueConstraint(fields=['assignment', 'student'],
                                    name='uniq_exam_attempt'),
        ]

    def __str__(self):
        return f'{self.student} — {self.assignment}'

    @classmethod
    def start(cls, assignment, student, now=None):
        """Начинает попытку (или возвращает уже начатую).

        Момент истечения считается ЗДЕСЬ, от серверного времени:
        * окно (тип A) — до конца окна;
        * лимит (тип Б) — старт + лимит, но не позже срока сдачи (иначе
          ученик, стартовавший за минуту до дедлайна, получил бы лишний час).
        """
        now = now or timezone.now()
        attempt = cls.objects.filter(assignment=assignment,
                                     student=student).first()
        if attempt is not None:
            return attempt

        expires_at = None
        mode = assignment.exam_mode
        if mode == assignment.ExamMode.WINDOW:
            expires_at = assignment.ends_at
        elif mode == assignment.ExamMode.LIMIT:
            if assignment.duration_minutes:
                expires_at = now + timezone.timedelta(
                    minutes=assignment.duration_minutes)
            due = assignment.deadline
            if due and (expires_at is None or expires_at > due):
                expires_at = due

        return cls.objects.create(assignment=assignment, student=student,
                                  expires_at=expires_at, last_heartbeat=now)

    def seconds_left(self, now=None):
        """Сколько секунд осталось (None — без ограничения)."""
        if self.expires_at is None:
            return None
        now = now or timezone.now()
        return max(0, int((self.expires_at - now).total_seconds()))

    @property
    def is_expired(self):
        left = self.seconds_left()
        return left is not None and left <= 0

    def touch(self, now=None):
        """Отметка «ученик на связи» при автосохранении."""
        self.last_heartbeat = now or timezone.now()
        self.save(update_fields=['last_heartbeat'])


class AnswerDraft(models.Model):
    """Черновик ответа — автосохранение во время контрольной.

    Требование, ради которого модель существует: при обрыве связи или
    закрытии вкладки написанное НЕ теряется. Ученик возвращается, видит свои
    ответы, а таймер идёт от `expires_at` попытки — не от нуля и не от того,
    сколько он реально просидел за экраном.
    """

    attempt = models.ForeignKey(
        ExamAttempt, on_delete=models.CASCADE,
        related_name='drafts', verbose_name='Попытка')
    problem_item = models.ForeignKey(
        'problems.AssignmentItem', on_delete=models.CASCADE,
        related_name='drafts', verbose_name='Задача в домашке')
    answer_draft = models.TextField('Черновик ответа', blank=True)
    # Развёрнутый ход решения. Отдельным полем, а не в одном с ответом:
    # набор полей ответа един для всех задач (ответ + решение + файл), и
    # черновик обязан сохранять ровно то же, что покажет форма при возврате.
    # Файл не автосохраняем — его нельзя переслать «по ходу набора»;
    # прикреплённое уезжает при сдаче.
    solution_draft = models.TextField('Черновик решения', blank=True)
    updated_at = models.DateTimeField('Сохранён', auto_now=True)

    class Meta:
        verbose_name = 'Черновик ответа'
        verbose_name_plural = 'Черновики ответов'
        constraints = [
            models.UniqueConstraint(fields=['attempt', 'problem_item'],
                                    name='uniq_answer_draft'),
        ]

    def __str__(self):
        return f'{self.attempt}: позиция {self.problem_item_id}'


# ===========================================================================
# Фаза 7. Логирование учебных событий
# ===========================================================================

class LearningEvent(models.Model):
    """Одно учебное событие: кто, что, где, сколько времени.

    Зачем собирать это ДО того, как появились экраны статистики: историю
    нельзя восстановить задним числом. Экран можно нарисовать в любой
    момент, а данные за прошлый месяц взять неоткуда.

    Тема и сложность продублированы прямо в событии — намеренно. Статистика
    «сколько верных по теме N за квартал» иначе требовала бы join через
    задачу к M2M-темам на каждой строке; к тому же тема у задачи может
    смениться, а событие должно остаться таким, каким было в момент решения.
    """

    class Source(models.TextChoices):
        CATALOG = 'catalog', 'Каталог'
        HOMEWORK = 'homework', 'Домашка'
        EXAM = 'exam', 'Контрольная'
        GAME = 'game', 'Игра'

    class EventType(models.TextChoices):
        OPENED = 'opened', 'Открыл'
        ATTEMPTED = 'attempted', 'Попытался'
        SOLVED = 'solved', 'Решил верно'
        FAILED = 'failed', 'Ошибся'
        HINT_USED = 'hint_used', 'Открыл подсказку'
        SKIPPED = 'skipped', 'Пропустил'

    # Пусто у анонимных партий игры — игра работает без входа.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='learning_events', verbose_name='Пользователь')
    session_key = models.CharField('Ключ сессии', max_length=64,
                                   blank=True, db_index=True)

    source = models.CharField('Откуда', max_length=16, choices=Source.choices)
    event_type = models.CharField('Событие', max_length=16,
                                  choices=EventType.choices)

    catalog_problem = models.ForeignKey(
        'problems.Problem', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='learning_events', verbose_name='Задача каталога')
    custom_problem = models.ForeignKey(
        CustomProblem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='learning_events', verbose_name='Своя задача')
    assignment = models.ForeignKey(
        'problems.Assignment', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='learning_events', verbose_name='Работа')

    topic = models.ForeignKey(
        'problems.Topic', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='learning_events', verbose_name='Тема')
    difficulty = models.PositiveSmallIntegerField('Сложность',
                                                  null=True, blank=True)
    time_spent_seconds = models.PositiveIntegerField('Секунд потрачено',
                                                     null=True, blank=True)
    # Режим игры, комбо, номер вопроса — всё, что специфично для источника.
    payload = models.JSONField('Подробности', default=dict, blank=True)

    created_at = models.DateTimeField('Когда', auto_now_add=True,
                                      db_index=True)

    class Meta:
        verbose_name = 'Учебное событие'
        verbose_name_plural = 'Учебные события'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at'],
                         name='idx_event_user_date'),
            models.Index(fields=['user', 'topic'], name='idx_event_user_topic'),
            models.Index(fields=['source', '-created_at'],
                         name='idx_event_source_date'),
        ]

    def __str__(self):
        who = self.user or f'аноним({self.session_key[:8]})'
        return f'{who}: {self.get_event_type_display()} ({self.source})'
