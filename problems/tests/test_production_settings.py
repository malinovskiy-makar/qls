# -*- coding: utf-8 -*-
"""Продакшен-настройки безопасности держатся тестом, а не памятью.

ЗАЧЕМ ЭТОТ ФАЙЛ. Настройки безопасности ломаются тише всего: выключенная
кука `Secure` не роняет ни один экран и не пишет ни строчки в лог — сайт
работает, просто сессия ездит открытым текстом. Заметить это можно либо
проверкой, либо утечкой.

⚠️ КАК УСТРОЕНА ПРОВЕРКА. `config/settings_production.py` нельзя просто
импортировать: он намеренно падает без `SECRET_KEY` и без `ALLOWED_HOSTS`.
Поэтому модуль загружается ОТДЕЛЬНО, с подставным окружением, и его значения
читаются как обычный словарь. Активными настройками процесса он при этом не
становится — иначе тест сам себе включил бы SSL-редирект и уронил бы
остальные 2 390 проверок.
"""
import importlib
import os
import pathlib
import sys
import unittest
from contextlib import contextmanager

# ⚠️ КЛЮЧ ДЛИННЫЙ И РАЗНОБУКВЕННЫЙ НАМЕРЕННО. Короткая заглушка поднимает
# предупреждение security.W009 («ключ короче 50 символов»), и `check --deploy`
# перестаёт быть чистым — но по вине теста, а не настроек. Разбираться в таком
# выводе пришлось бы каждому следующему. На проде ключ задаётся вручную через
# переменную окружения (см. docs/MIGRATION-CHECKLIST.md — SECRET_KEY).
#
# ⚠️ REDIS_URL ЗДЕСЬ ОБЯЗАТЕЛЕН С 2026-08-21, И ЭТО НЕ ФОРМАЛЬНОСТЬ. На нём
# стоит четвёртый предохранитель боевых настроек (без Redis кэш становится
# локальным для каждого воркера — мина №2). Пока строки не было, оба класса
# этого файла падали у того, у кого переменной нет в шелле, и ПРОХОДИЛИ у
# того, у кого она есть. Тест, зелёный от окружения разработчика, не
# проверяет ничего — а «зелено у меня» здесь опаснее обычного, потому что
# файл сторожит именно настройки безопасности.
# Адрес подставной: настройки только читаются, к Redis никто не подключается
# (бэкенд Django не открывает соединение, пока у него не попросят ключ).
FAKE_ENV = {
    'SECRET_KEY': 'x7Kq2mZv9Lp4Rt6Wy8Bn3Cf5Hj1Dg0Sa-QwErTyUiOpAsDfGhJkLzXcVbNm',
    'ALLOWED_HOSTS': 'example.org,www.example.org',
    'DATABASE_URL': 'postgres://u:p@127.0.0.1:5432/db',
    'REDIS_URL': 'redis://127.0.0.1:6379',
}


MODULE = 'config.settings_production'


@contextmanager
def _production_module(drop=(), **extra):
    """Загружает продакшен-настройки с подставным окружением.

    ⚠️ ВСЕГДА СВЕЖИЙ ИМПОРТ, А НЕ `importlib.reload`. На reload полагаться
    нельзя: когда модуль падает при исполнении — а он обязан падать, на нём
    три предохранителя, — Python убирает его из `sys.modules`. Следующий
    `import` тогда исполняет файл ЗАНОВО, в чужом окружении, и роняет
    посторонний тест. Ровно это и случилось: проверка «нет SECRET_KEY»
    сломала соседнюю.

    Окружение возвращается как было: тест, оставивший после себя SECRET_KEY,
    сделал бы зелёными чужие проверки, которые обязаны краснеть.
    """
    env = dict(FAKE_ENV)
    env.update(extra)
    saved = {k: os.environ.get(k) for k in list(env) + list(drop)}
    # DJANGO_DEBUG обязан отсутствовать — на нём стоит предохранитель.
    saved['DJANGO_DEBUG'] = os.environ.get('DJANGO_DEBUG')
    previous = sys.modules.pop(MODULE, None)
    try:
        # Порядок важен: сначала убираем DJANGO_DEBUG (по умолчанию его быть
        # не должно), и только потом раскладываем окружение — иначе тест,
        # который НАРОЧНО выставляет DJANGO_DEBUG, тут же его и потеряет.
        os.environ.pop('DJANGO_DEBUG', None)
        os.environ.update(env)
        for key in drop:
            os.environ.pop(key, None)
        yield importlib.import_module(MODULE)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        # Возвращаем то, что лежало до нас: следующий тест обязан начинать
        # с того же состояния, что и мы.
        sys.modules.pop(MODULE, None)
        if previous is not None:
            sys.modules[MODULE] = previous


class ProductionSecurityValuesTests(unittest.TestCase):
    """Каждое значение проверяется поимённо, а не «настройки на месте»."""

    @classmethod
    def setUpClass(cls):
        cls._ctx = _production_module()
        cls.settings = cls._ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    # -- отладка и ключ ---------------------------------------------------
    def test_debug_off(self):
        self.assertFalse(self.settings.DEBUG)

    # -- HTTPS ------------------------------------------------------------
    def test_ssl_redirect_on(self):
        self.assertTrue(self.settings.SECURE_SSL_REDIRECT)

    def test_proxy_ssl_header(self):
        self.assertEqual(self.settings.SECURE_PROXY_SSL_HEADER,
                         ('HTTP_X_FORWARDED_PROTO', 'https'))

    def test_hsts_deliberately_zero(self):
        """HSTS отложен ОСОЗНАННО — ноль, а не «настройки нет».

        Разница существенная: отсутствующая настройка читается как
        забывчивость, и следующий человек включит HSTS не разобравшись.
        Причина отсрочки написана рядом со значением в самом файле.
        """
        self.assertEqual(self.settings.SECURE_HSTS_SECONDS, 0)

    # -- куки -------------------------------------------------------------
    def test_session_cookie_secure(self):
        self.assertTrue(self.settings.SESSION_COOKIE_SECURE)

    def test_csrf_cookie_secure(self):
        self.assertTrue(self.settings.CSRF_COOKIE_SECURE)

    def test_session_cookie_httponly(self):
        self.assertTrue(self.settings.SESSION_COOKIE_HTTPONLY)

    def test_session_cookie_samesite(self):
        self.assertEqual(self.settings.SESSION_COOKIE_SAMESITE, 'Lax')

    def test_csrf_cookie_samesite(self):
        self.assertEqual(self.settings.CSRF_COOKIE_SAMESITE, 'Lax')

    # -- заголовки --------------------------------------------------------
    def test_content_type_nosniff(self):
        self.assertTrue(self.settings.SECURE_CONTENT_TYPE_NOSNIFF)

    def test_referrer_policy(self):
        self.assertEqual(self.settings.SECURE_REFERRER_POLICY, 'same-origin')

    def test_frame_options_deny(self):
        self.assertEqual(self.settings.X_FRAME_OPTIONS, 'DENY')

    # -- хосты ------------------------------------------------------------
    def test_allowed_hosts_from_env(self):
        self.assertEqual(self.settings.ALLOWED_HOSTS,
                         ['example.org', 'www.example.org'])

    def test_no_wildcard_host(self):
        """Звёздочка отключает проверку Host целиком — запрещена."""
        self.assertNotIn('*', self.settings.ALLOWED_HOSTS)

    def test_csrf_trusted_origins_default_empty(self):
        """Без переменной список пуст — доверяем только своему домену."""
        self.assertEqual(self.settings.CSRF_TRUSTED_ORIGINS, [])

    # -- глушилки проверок ------------------------------------------------
    def test_only_hsts_check_silenced(self):
        """Глушится ровно W004 (HSTS), и ничего больше.

        Глушилка, пережившая свою причину, — это способ, каким
        `check --deploy` перестаёт что-либо значить. W008 (SSL-редирект)
        убран из списка, когда редирект включили по-настоящему.
        """
        self.assertEqual(self.settings.SILENCED_SYSTEM_CHECKS,
                         ['security.W004'])


class ProductionFusesTests(unittest.TestCase):
    """Предохранители: прод обязан падать при старте, а не молча."""

    def test_empty_allowed_hosts_raises(self):
        """Пустой ALLOWED_HOSTS — падение с внятным текстом.

        Django на пустом списке при DEBUG=False просто отвечает 400 на
        каждый запрос. Снаружи это неотличимо от «сайт сломался».
        """
        with self.assertRaises(RuntimeError) as ctx:
            with _production_module(ALLOWED_HOSTS=''):
                pass
        self.assertIn('ALLOWED_HOSTS', str(ctx.exception))

    def test_debug_env_raises(self):
        """DJANGO_DEBUG на проде запрещён — предохранитель с сессии 1."""
        with self.assertRaises(RuntimeError) as ctx:
            with _production_module(DJANGO_DEBUG='1'):
                pass
        self.assertIn('DJANGO_DEBUG', str(ctx.exception))

    def test_missing_secret_key_raises(self):
        """Без SECRET_KEY сервис не имеет права подняться.

        Именно KeyError, а не RuntimeError: ключ читается через
        `os.environ['SECRET_KEY']` намеренно — квадратные скобки роняют
        сервис сами, без нашей проверки.
        """
        with self.assertRaises(KeyError):
            with _production_module(drop=('SECRET_KEY',)):
                pass

    def test_redis_url_required(self):
        """Без REDIS_URL сервис не имеет права подняться.

        Без предохранителя `config/settings.py` молча подставил бы
        LocMemCache: сайт поднялся бы, страницы открылись бы, и на девяти
        воркерах вышло бы девять независимых кэшей — попадание примерно один
        раз из девяти, счётчик неудачных входов у каждого воркера свой,
        сброс кэша доходит до одного воркера из девяти. Тихая деградация
        ищется неделями по жалобам, падение при старте — минуты.
        Обоснование — docs/adr/0011-redis-cache-and-sessions.md.
        """
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            with _production_module(drop=('REDIS_URL',)):
                pass


class DeployCheckTests(unittest.TestCase):
    """`manage.py check --deploy` не должен выдавать предупреждений.

    ⚠️ Проверка запускается ОТДЕЛЬНЫМ ПРОЦЕССОМ. Настройки продакшена нельзя
    активировать внутри идущего прогона: они переключают базу, кэш шаблонов и
    SSL-редирект, и остальные тесты после этого проверяли бы не тот сайт.
    """

    def test_check_deploy_is_clean(self):
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        env = dict(os.environ)
        env.update(FAKE_ENV)
        env.pop('DJANGO_DEBUG', None)
        # ⚠️ Вывод команды по-русски: без явной кодировки Windows отдаёт его
        # в cp1251, и текст превращается в «РѕР±С‹С‡РЅС‹Р№».
        env['PYTHONIOENCODING'] = 'utf-8'

        result = subprocess.run(
            [sys.executable, 'manage.py', 'check', '--deploy',
             '--settings=config.settings_production'],
            cwd=str(root), env=env, capture_output=True,
            encoding='utf-8', errors='replace', timeout=180)

        output = (result.stdout or '') + (result.returncode and
                                          (result.stderr or '') or '')
        self.assertEqual(
            result.returncode, 0,
            'check --deploy вернул %s:\n%s\n%s'
            % (result.returncode, result.stdout, result.stderr))
        self.assertIn('System check identified no issues', output)


class NginxDoesNotDuplicateDjangoHeadersTests(unittest.TestCase):
    """X-Frame-Options/X-Content-Type-Options/Referrer-Policy — владелец
    Django (см. классы выше), nginx их ставить не должен вовсе.

    22.08.2026: все три дублировались (ADR 0013, ADR 0014) — у
    Referrer-Policy расхождение было хуже, чем просто шум: при повторении
    заголовка побеждает ПОСЛЕДНЕЕ значение, а nginx дописывал своё ПОСЛЕ
    Django, то есть реально действовала более слабая nginx-политика, пока
    Django-настройка молча простаивала. Тест читает конфиг текстом —
    `manage.py test` nginx не поднимает.
    """

    _ROOT = pathlib.Path(__file__).resolve().parents[2]
    CONF_PATHS = (
        _ROOT / 'deploy' / 'nginx' / 'available' / 'django.conf',
        _ROOT / 'deploy' / 'nginx' / 'conf.d' / 'weconomics.conf',
    )
    OWNED_BY_DJANGO = ('X-Frame-Options', 'X-Content-Type-Options',
                       'Referrer-Policy')

    def test_conf_files_exist(self):
        for path in self.CONF_PATHS:
            self.assertTrue(path.exists(), 'Не нашёл %s' % path)

    def test_no_add_header_for_django_owned_headers(self):
        """Ищет только РЕАЛЬНЫЕ директивы, не упоминания в комментариях.

        Комментарии рядом сознательно цитируют убранные строки (объясняют,
        что и почему сняли) — наивный поиск подстроки по всему файлу ловил
        бы своё же объяснение. Поэтому смотрим только на строки, не
        начинающиеся с `#` после отступа.
        """
        for path in self.CONF_PATHS:
            code_lines = [
                line for line in path.read_text(encoding='utf-8').splitlines()
                if not line.strip().startswith('#')
            ]
            code_text = '\n'.join(code_lines).lower()
            for header in self.OWNED_BY_DJANGO:
                needle = ('add_header %s' % header).lower()
                self.assertNotIn(
                    needle, code_text,
                    '%s: снова появилась ДЕЙСТВУЮЩАЯ директива '
                    '`add_header %s` (не в комментарии) — значит, '
                    'заголовок опять будет приходить дважды (или, для '
                    'Referrer-Policy, побеждать будет более слабое '
                    'nginx-значение). Владелец — Django, см. ADR 0013/0014.'
                    % (path.name, header))
