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
