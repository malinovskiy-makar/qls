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
