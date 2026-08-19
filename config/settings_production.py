"""
Настройки для продакшена на Render.com.
Наследует от settings.py и переопределяет нужные параметры.
"""
from .settings import *
import os
import dj_database_url

# ─── Безопасность ────────────────────────────────────────────────────────────

DEBUG = False

# Предохранитель: прод не имеет права подняться в отладочном режиме.
# При DEBUG=True Django показывает трассировки с кусками кода и значениями
# переменных прямо в браузере, а ALLOWED_HOSTS перестаёт работать.
# Падение при старте лучше, чем утечка внутренностей наружу.
if os.environ.get('DJANGO_DEBUG', '').lower() in ('1', 'true', 'yes', 'on'):
    raise RuntimeError(
        'DJANGO_DEBUG выставлен, а на проде отладочный режим запрещён. '
        'Уберите переменную окружения DJANGO_DEBUG.'
    )

# Именно [ ], а не .get(): без ключа сервис обязан упасть при старте,
# а не подняться с тихим значением по умолчанию.
SECRET_KEY = os.environ['SECRET_KEY']

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '.onrender.com').split(',')

# Render завершает SSL на своём прокси и передаёт нам HTTP
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# Render сам делает HTTPS-редирект — не надо дублировать в Django
SECURE_SSL_REDIRECT = False
# Куки только по HTTPS
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# ─── База данных (PostgreSQL) ─────────────────────────────────────────────────

DATABASES = {
    'default': dj_database_url.config(
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ─── Статика через WhiteNoise ─────────────────────────────────────────────────

MIDDLEWARE = ['whitenoise.middleware.WhiteNoiseMiddleware'] + MIDDLEWARE

STATIC_ROOT = BASE_DIR / 'staticfiles'

# Настройка хранилищ одним словарём. Отдельные STATICFILES_STORAGE и
# DEFAULT_FILE_STORAGE объявлены устаревшими в Django 4.2 и удалены в 5.1:
# два ключа вместо одного места давали разное поведение у файлов и статики.
# Ключ 'default' задаём явно — иначе он потеряется вместе со словарём.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# ─── Шаблоны: кэшированный загрузчик на продакшене ───────────────────────────

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': False,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
            'loaders': [
                ('django.template.loaders.cached.Loader', [
                    'django.template.loaders.filesystem.Loader',
                    'django.template.loaders.app_directories.Loader',
                ]),
            ],
        },
    },
]

# Эти предупреждения ожидаемы: Render обрабатывает SSL-редиректы и HSTS сам
SILENCED_SYSTEM_CHECKS = ['security.W004', 'security.W008']

# ─── xelatex: недоступен на Render без Docker ────────────────────────────────

XELATEX_PATH = None

# ─── sentence-transformers: не грузим на сервере ─────────────────────────────

LOAD_EMBEDDINGS_MODEL = False

# ─── Econ Rush: сгенерированные вопросы выключены до решения о выкатке ──────

GAME_GENERATED_ENABLED = False
