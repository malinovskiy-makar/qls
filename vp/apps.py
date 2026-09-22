from django.apps import AppConfig


class VpConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vp'
    verbose_name = 'Высшая проба: тренажёр 1 тура'

    def ready(self):
        from vp import signals  # noqa: F401 — подключает перенос гостевых попыток
