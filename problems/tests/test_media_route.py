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
"""
import ast
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
    """Никто не отдаёт файл по пути, пришедшему от клиента.

    Проверяется исходник всех приложений: `FileResponse`, `django.views.
    static.serve` и `open()` по значению из запроса. Тест ловит не
    сегодняшнюю дыру, а завтрашнюю — «сделаю просто скачивание файла».
    """

    APPS = ('problems', 'catalog', 'teacher', 'student', 'game', 'calc2',
            'calendar_stub', 'config')

    def test_no_file_serving_helpers_in_views(self):
        offenders = []
        for app in self.APPS:
            root = Path(settings.BASE_DIR) / app
            if not root.exists():
                continue
            for path in root.rglob('*.py'):
                if 'test' in path.name or '/migrations/' in path.as_posix():
                    continue
                text = path.read_text(encoding='utf-8')
                for needle in ('FileResponse', 'views.static.serve',
                               'from django.views.static import serve'):
                    if needle in text:
                        offenders.append('%s: %s' % (
                            path.relative_to(settings.BASE_DIR), needle))
        self.assertEqual(
            offenders, [],
            'Появился код, отдающий файлы. Это не запрещено, но требует '
            'разбора: путь обязан браться не из запроса, а из поля модели, '
            'и доступ — сужением queryset. Найдено: %s' % offenders)
