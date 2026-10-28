"""Проверки Django приложения `vp`.

`vp.W001`: стена 2 тура включена, а путь контакта не настроен (docs/VP.md,
«Выкатка стены — по шагам»). Предупреждение, а не ошибка: контейнер должен
подниматься по шагам выкатки, а `migrate` в entrypoint падает только на ошибках.
Джоб `deploy-check` гоняет `--fail-level WARNING` и это предупреждение видит.
"""
from django.conf import settings
from django.core.checks import Warning, register

_TG = ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_BOT_USERNAME', 'TELEGRAM_WEBHOOK_SECRET')


@register()
def wall_paths_configured(app_configs, **kwargs):
    """При VP_WALL_ENABLED и DEBUG=False оба пути стены обязаны быть настроены."""
    if settings.DEBUG or not getattr(settings, 'VP_WALL_ENABLED', False):
        return []
    missing = [name for name in _TG if not (getattr(settings, name, '') or '').strip()]
    if not getattr(settings, 'MAIL_ENABLED', False):
        missing.append('MAIL_ENABLED')
    if not missing:
        return []
    return [Warning(
        'Стена тренажёра ВП включена, но путь контакта не настроен: %s.' % ', '.join(missing),
        hint='Задайте в .env недостающее (docs/VP.md, «Выкатка стены — по шагам»). '
             'Тренажёр без обоих путей не выкатываем (решение 28.10.2026).',
        id='vp.W001')]
