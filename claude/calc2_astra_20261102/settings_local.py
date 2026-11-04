"""Только изолированные проверки calc2, без данных и служб владельца."""

from config.settings import *  # noqa: F401,F403
from config.settings import BASE_DIR, CACHES as BASE_CACHES

SECRET_KEY = 'calc2-astra-local-synthetic-checks-only-20261102'
DEBUG = True
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / '.calc2-astra-local' / 'synthetic.sqlite3',
        'OPTIONS': {'timeout': 20},
    },
}
CACHES = {
    name: {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': f'calc2-astra-{name}',
    }
    for name in BASE_CACHES
}
CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
MAIL_ENABLED = False
TELEGRAM_BOT_TOKEN = ''
TELEGRAM_WEBHOOK_SECRET = ''
AI_PROVIDER = 'fake'
CATALOG_CHAT_PROVIDER = 'fake'
OLYMPIAD_AI_CHECK = False
REDIS_URL = ''
SITE_ENV = 'dev'
YANDEX_METRIKA_ID = ''
SMART_SEARCH_WARMUP = False
