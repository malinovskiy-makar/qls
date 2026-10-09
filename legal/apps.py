# -*- coding: utf-8 -*-
from django.apps import AppConfig


class LegalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'legal'
    verbose_name = 'Правовые документы и согласия'

    def ready(self):
        # Регистрирует проверку реквизитов (`legal.E001`).
        from . import checks  # noqa: F401
