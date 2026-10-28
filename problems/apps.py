from django.apps import AppConfig


class ProblemsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'problems'

    def ready(self):
        # Подключаем сигналы (автосоздание профиля пользователя).
        from . import signals  # noqa: F401
        # Регистрирует проверку канала почты (`mail.E001`).
        from . import checks  # noqa: F401
