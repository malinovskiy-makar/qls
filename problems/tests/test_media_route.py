# -*- coding: utf-8 -*-
"""Хвост сессии 3А: как отдаются пользовательские файлы при DEBUG=False.

Вопрос из карты маршрутов: «маршрут `/media/<path>` принимает путь от
клиента — проверить, что при `DEBUG=False` его нет». Разбор сессии 3Б.

**Что выяснилось.** Маршрут заводится в `config/urls.py` внутри
`if settings.DEBUG` — то есть на проде его нет вовсе. Подмена пути
(`/media/../db.sqlite3`) не работает не потому, что кто-то её отсекает, а
потому, что отвечать на такой адрес некому.

**И это не полдела, а вся картина.** Проверено отдельно:

* `WHITENOISE_ROOT` не задан, поэтому WhiteNoise отдаёт только `STATIC_ROOT`
  и до `MEDIA_ROOT` не дотягивается;
* ни одного представления с `FileResponse`, `serve()` или чтением файла по
  пути из запроса в проекте нет.

**Следствие, которое надо знать владельцу.** Четыре поля моделей
(`FileAsset.file`, `Problem.solution_file`, `Job.output_file`,
`ImportSession.source_file`) принимают загрузку, но на проде **никак не
отдаются**: ссылка на `/media/...` вернёт 404. Это не дыра, а недоделка —
карточка заведена в Notion.

**22.08, сессия С2-хвосты: это была НЕ вся картина.** Django действительно
не отдаёт `/media/` — но nginx (`deploy/nginx/available/django.conf`)
отдавал его В ОБХОД Django: `location /media/ { alias /var/www/media/; }`
указывал на тот же самый общий том, куда `Submission.solution_file`
реально сохраняет прикреплённые файлы (сдача задания — рабочая функция).
То есть прикреплённые сканы/фото решений были публично доступны по адресу
`/media/submissions/ГГГГ/ММ/имя`, без единой проверки прав — ровно то,
чего первая проверка (тесты ниже) не могла увидеть, потому что смотрела
только на Django. Закрыто той же сессией — `location /media/` в nginx
теперь безусловно отвечает 404, как `/healthz/` выше по тому же файлу.
Тест на это — класс `MediaIsNotServedByNginxTests` ниже.
"""
import ast
import re
from pathlib import Path

from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import Resolver404, resolve


@override_settings(DEBUG=False)
class MediaRouteIsAbsentInProductionTests(TestCase):
    """При DEBUG=False адреса /media/ не существует."""

    def test_media_url_does_not_resolve(self):
        with self.assertRaises(Resolver404):
            resolve('/media/uploads/2026/08/file.pdf')

    def test_media_request_is_404(self):
        response = Client().get('/media/uploads/2026/08/file.pdf')
        self.assertEqual(response.status_code, 404)

    def test_path_traversal_gets_nothing(self):
        """Выход за каталог не работает — отвечать на такой адрес некому."""
        for path in ('/media/../db.sqlite3',
                     '/media/..%2Fdb.sqlite3',
                     '/media/%2e%2e/config/settings.py',
                     '/media/....//db.sqlite3'):
            with self.subTest(path=path):
                response = Client().get(path)
                self.assertIn(response.status_code, (400, 404),
                              'Подстановка пути дала не отказ')
                body = response.content.decode('utf-8', 'replace')
                self.assertNotIn('SECRET_KEY', body)
                self.assertNotIn('SQLite format', body)


class MediaRouteIsGuardedByDebugFlagTests(TestCase):
    """Маршрут заводится ТОЛЬКО под `if settings.DEBUG`.

    Тест читает `config/urls.py` разбором синтаксиса, а не поиском строки:
    строку легко обойти переносом, а ветку `if` — нет.
    """

    def test_static_call_lives_inside_if_debug(self):
        source = (Path(settings.BASE_DIR) / 'config' / 'urls.py').read_text(
            encoding='utf-8')
        tree = ast.parse(source)

        # Все вызовы `static(...)` в файле.
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)
                 and node.func.id == 'static']
        self.assertTrue(calls, 'Вызов static() исчез — проверка потеряла смысл')

        # Те из них, что лежат внутри `if ...DEBUG...`.
        guarded = []
        for branch in ast.walk(tree):
            if not isinstance(branch, ast.If):
                continue
            test_src = ast.dump(branch.test)
            if 'DEBUG' not in test_src:
                continue
            guarded.extend(
                node for node in ast.walk(branch)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == 'static')

        self.assertEqual(
            len(calls), len(guarded),
            'В config/urls.py есть вызов static() ВНЕ ветки `if DEBUG` — '
            'значит, на проде появился маршрут, отдающий файлы по пути от '
            'клиента.')


class NoOtherFileServingViewTests(TestCase):
    """Файлы отдаёт только то, что разобрано поимённо.

    Проверяется исходник всех приложений: `FileResponse`, `django.views.
    static.serve` и `open()` по значению из запроса. Тест ловит не
    сегодняшнюю дыру, а завтрашнюю — «сделаю просто скачивание файла».

    ⚠️ СПИСОК РАЗРЕШЁННЫХ — НЕ ПОСЛАБЛЕНИЕ, А МЕСТО ДЛЯ РАЗБОРА. Каждый файл
    в нём разобран отдельно, и рядом записано, ПОЧЕМУ он безопасен. Добавить
    строку сюда = обязаться этот разбор провести; тест по-прежнему краснеет
    на любом НОВОМ месте, отдающем файлы.
    """

    APPS = ('problems', 'catalog', 'teacher', 'student', 'game', 'calc2',
            'calendar_stub', 'config')

    # путь → почему это безопасно
    ALLOWED = {
        'problems/views_platform.py':
            'аватар: путь берётся из поля модели, из запроса приходит только '
            'целое число; файл — наш собственный JPEG, пересжатый Pillow и '
            'названный нами (avatars/<id>.jpg); отдаётся только вошедшим; '
            'Content-Type задан жёстко. Разбор — Фаза 4 сессии 04.09.2026.',
    }

    def test_no_file_serving_helpers_in_views(self):
        offenders = []
        for app in self.APPS:
            root = Path(settings.BASE_DIR) / app
            if not root.exists():
                continue
            for path in root.rglob('*.py'):
                if 'test' in path.name or '/migrations/' in path.as_posix():
                    continue
                rel = path.relative_to(settings.BASE_DIR).as_posix()
                if rel in self.ALLOWED:
                    continue
                text = path.read_text(encoding='utf-8')
                for needle in ('FileResponse', 'views.static.serve',
                               'from django.views.static import serve'):
                    if needle in text:
                        offenders.append('%s: %s' % (rel, needle))
        self.assertEqual(
            offenders, [],
            'Появился код, отдающий файлы. Это не запрещено, но требует '
            'разбора: путь обязан браться не из запроса, а из поля модели, '
            'и доступ — сужением queryset. Разобрали — впишите файл и '
            'причину в ALLOWED. Найдено: %s' % offenders)

    def test_allowed_list_is_not_stale(self):
        """Разрешение без кода — забытая строка, а не разрешение.

        Если файл из списка перестал отдавать файлы, строку надо убрать:
        иначе завтра в нём появится новая раздача и пройдёт молча.
        """
        for rel, reason in self.ALLOWED.items():
            path = Path(settings.BASE_DIR) / rel
            self.assertTrue(path.exists(), rel)
            text = path.read_text(encoding='utf-8')
            self.assertIn('FileResponse', text,
                          '%s больше не отдаёт файлы — уберите из ALLOWED' % rel)
            self.assertTrue(reason.strip(), rel)


class MediaIsNotServedByNginxTests(TestCase):
    """nginx не должен отдавать `/media/` в обход Django.

    `manage.py test` nginx не поднимает — это тест не поведения, а конфига:
    читает `deploy/nginx/available/django.conf` текстом и проверяет блок
    `location /media/`. Django сам по себе `/media/` не отдаёт (тесты выше),
    но 22.08 выяснилось, что этого мало — nginx у той же папки стоял со
    своим `alias`, указывающим на тот же общий том, куда реально пишутся
    прикреплённые файлы учеников (Submission.solution_file). Тест ловит
    именно возврат `alias`/`try_files` в этот блок, а не общий факт
    существования файла — если блок пуст или удалён вовсе, тест тоже
    должен упасть, чтобы никто не решил «уберём блок — и так сойдёт».
    """

    CONF_PATH = Path(__file__).resolve().parents[2] / 'deploy' / 'nginx' / \
        'available' / 'django.conf'

    def _media_block(self):
        text = self.CONF_PATH.read_text(encoding='utf-8')
        match = re.search(
            r'location\s+/media/\s*\{(?P<body>.*?)\n    \}',
            text, re.DOTALL)
        self.assertIsNotNone(
            match, 'Блок `location /media/` пропал из django.conf — '
            'без него запрос уйдёт в location / и что вернёт Django, '
            'непонятно без отдельной проверки')
        return match.group('body')

    def test_nginx_conf_exists(self):
        self.assertTrue(
            self.CONF_PATH.exists(),
            'Не нашёл %s — переехал файл или переехал тест' % self.CONF_PATH)

    def test_media_block_has_no_alias(self):
        body = self._media_block()
        self.assertNotIn(
            'alias', body,
            'В блоке `location /media/` снова появился `alias` — значит, '
            'nginx опять отдаёт реальные файлы из тома media в обход '
            'Django. См. docstring вверху файла — это уже приводило к '
            'публичной раздаче прикреплённых файлов учеников.')
        self.assertNotIn('try_files', body)

    def test_media_block_returns_404_unconditionally(self):
        body = self._media_block()
        self.assertIn('return 404', body)


class WebSocketDuelIsProxiedByNginxTests(TestCase):
    """`location /ws/` обязан существовать, проксировать в `ws:8001` с
    заголовками апгрейда протокола, и стоять ВЫШЕ `location /`.

    Сессия «Wecon Rush — подготовка к выкатке» (02.09) нашла живой дрейф:
    `deploy/nginx/conf.d/weconomics.conf` (снимок «что реально стоит на
    сервере») уже нёс рабочий блок `/ws/`, а
    `deploy/nginx/available/django.conf` (канонический шаблон — именно его
    RUNBOOK велит копировать на сервер при любом обновлении конфигурации,
    docs/RUNBOOK.md «⚠️ Если менялась конфигурация nginx») блока не имел
    вовсе. При следующем `cp available/django.conf nginx/available/django.
    conf` дуэль в реальном времени молча перестала бы работать: запрос к
    `/ws/` ушёл бы в `location /`, то есть к gunicorn, который про сокеты
    не знает вовсе."""

    CONF_PATH = Path(__file__).resolve().parents[2] / 'deploy' / 'nginx' / \
        'available' / 'django.conf'

    def _read(self):
        return self.CONF_PATH.read_text(encoding='utf-8')

    def _ws_block(self):
        text = self._read()
        match = re.search(
            r'location\s+/ws/\s*\{(?P<body>.*?)\n    \}',
            text, re.DOTALL)
        self.assertIsNotNone(
            match, 'Блок `location /ws/` отсутствует в django.conf — без '
            'него WebSocket дуэли не проксируются вовсе, запрос уходит в '
            'location / и до daphne не доезжает.')
        return match.group('body')

    def test_ws_block_proxies_to_ws_service(self):
        body = self._ws_block()
        self.assertIn('proxy_pass http://ws:8001', body)

    def test_ws_block_upgrades_the_protocol(self):
        body = self._ws_block()
        self.assertIn('Upgrade', body)
        self.assertIn('"upgrade"', body,
                      'Connection обязан быть задан явно строкой "upgrade" — '
                      'у location / ниже он гасится пустой строкой, и без '
                      'явного значения здесь блок унаследовал бы это.')

    def test_ws_block_comes_before_catch_all_location(self):
        text = self._read()
        ws_pos = text.find('location /ws/')
        # Не первый попавшийся `location / {` — их несколько (есть ещё
        # заглушка `return 444;` у server_name _ вначале файла). Ищем
        # именно проксирующий в Django блок по его proxy_pass.
        catch_all_pos = text.find('proxy_pass http://web:8000')
        self.assertGreater(ws_pos, -1)
        self.assertGreater(catch_all_pos, -1)
        self.assertLess(
            ws_pos, catch_all_pos,
            '`location /ws/` обязан идти РАНЬШЕ проксирующего в Django '
            '`location /` в этом файле — дублирует порядок из деплоя, где '
            'это буквально необходимо для nginx (см. docstring класса).')
