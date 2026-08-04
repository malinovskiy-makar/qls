"""
Сигналы приложения `problems`.

Пока здесь одно: у каждого пользователя автоматически появляется профиль
(`UserProfile`). Без этого любой экран, который обращается к `user.profile`,
падал бы на пользователях, созданных в обход формы регистрации — из админки,
через `createsuperuser`, seed-командами.
"""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models_platform import USER_ROLE_TO_PROFILE_ROLE, UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL,
          dispatch_uid='problems.create_user_profile')
def create_user_profile(sender, instance, created, **kwargs):
    """Создаёт профиль новому пользователю.

    Роль профиля выводим из старого `User.role`: преподаватель → репетитор,
    всё остальное → ученик. Существующему профилю ничего не переписываем —
    источник правды это профиль, а не поле пользователя.
    """
    if not created:
        return
    role = USER_ROLE_TO_PROFILE_ROLE.get(
        getattr(instance, 'role', ''), UserProfile.Role.STUDENT)
    UserProfile.objects.get_or_create(user=instance, defaults={'role': role})
