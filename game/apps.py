from django.apps import AppConfig


class GameConfig(AppConfig):
    """Игровая поверхность Econ Rush — публичная игра на скорость."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'game'
    verbose_name = 'Игра Econ Rush'
