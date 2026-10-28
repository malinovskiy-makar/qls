"""Единственное место, откуда сайт ходит в Telegram (стена 2 тура, docs/VP.md).

⚠️ ТОКЕН БОТА НЕ ПОПАДАЕТ НИ В ЛОГ, НИ В ТЕКСТ ИСКЛЮЧЕНИЯ: адрес запроса
содержит его целиком, поэтому адрес не логируется никогда.
"""
from django.conf import settings


def enabled():
    """Путь Telegram на стене включён: токен, имя бота и секрет вебхука заданы."""
    return bool(getattr(settings, 'VP_WALL_TG_ENABLED', True)
                and getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
                and getattr(settings, 'TELEGRAM_BOT_USERNAME', '')
                and getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', ''))
