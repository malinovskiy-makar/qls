"""
Статические тесты страницы игры.

Инлайн-скрипт game.html — полторы тысячи строк, которых не видит ни
`manage.py check`, ни рендер шаблона: страница отдаёт 200 с любой опечаткой
в JS, а ломается уже в браузере у игрока. Тут ловим ровно этот класс:
- скрипт вообще парсится (node --check);
- каждый getElementById имеет элемент с таким id в разметке;
- каждое поле сводки, которое читает клиент, сервер действительно кладёт
  (иначе на экране результатов молча появится «undefined»);
- мёртвых переменных и функций не осталось.

Тот же приём, что у «Штриха» (shtrikh/tests/test_page_js.py).
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from django.conf import settings
from django.test import TestCase

TEMPLATE = os.path.join(
    settings.BASE_DIR, 'game', 'templates', 'game', 'game.html')

# Заглушка конфига вместо {{ config_json|safe }} — форма как у _mode_payload.
FAKE_CONFIG = (
    '{"modes":{"blitz":{"key":"blitz","title":"Блиц","question_type":"single",'
    '"duration":120,"time_correct":5,"time_wrong":0,"time_skip":0,"lives":3}},'
    '"default_mode":"blitz","pool_counts":{"blitz":10},"base_points":100,'
    '"combo_steps":[[9,4],[6,3],[3,2]],"mistakes_run_size":10}'
)


def page_source():
    with open(TEMPLATE, encoding='utf-8') as f:
        return f.read()


def inline_js(src):
    """Инлайн-скрипт страницы с подставленным конфигом."""
    m = re.search(r'<script>\n(.*?)\n</script>', src, re.S)
    assert m, 'инлайн-скрипт не найден'
    return m.group(1).replace('{{ config_json|safe }}', FAKE_CONFIG)


class PageJsTests(TestCase):

    def setUp(self):
        self.src = page_source()
        self.js = inline_js(self.src)

    @unittest.skipIf(shutil.which('node') is None, 'node не установлен')
    def test_inline_script_parses(self):
        """node --check: опечатку в JS рендер шаблона не заметит."""
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8') as f:
            f.write(self.js)
            path = f.name
        try:
            p = subprocess.run(['node', '--check', path],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
        finally:
            os.unlink(path)

    def test_every_getElementById_has_an_element(self):
        """$('id') без элемента в разметке = молчаливый null и падение."""
        ids_html = set(re.findall(r'id="([^"]+)"', self.src))
        ids_js = set(re.findall(r"\$\('([^']+)'\)", self.js))
        self.assertEqual(sorted(ids_js - ids_html), [])

    def test_summary_fields_read_by_client_are_sent_by_server(self):
        """Клиент читает сводку по именам полей — сверяем с build_summary.

        Разъехавшееся имя даёт «undefined» на экране результатов, и ни
        один питон-тест этого не увидит."""
        from game import views
        state = {'mode': 'blitz', 'topic': None, 'seen': [], 'answered': {},
                 'lives': 3, 'score': 0, 'streak': 0, 'best_streak': 0,
                 'ended': None, 'log': []}
        served = set(views.build_summary(state).keys())
        # поля, которые клиент берёт у сводки: s.<имя>
        read = set(re.findall(r'\bs\.([a-z_]+)\b', self.js))
        # offline — поле запасной сводки клиента, сервер его не шлёт
        read.discard('offline')
        self.assertEqual(sorted(read - served), [])

    def test_no_dead_functions(self):
        """Объявленная и никем не вызванная функция — недоделка или мусор."""
        declared = set(re.findall(r'\n  function ([a-zA-Z_]\w*)\(', self.js))
        dead = []
        for name in declared:
            # объявление + хотя бы одно упоминание где-то ещё
            uses = len(re.findall(r'\b%s\b' % re.escape(name), self.js))
            if uses < 2:
                dead.append(name)
        self.assertEqual(sorted(dead), [])

    def test_mechanics_numbers_come_from_config(self):
        """Числа механики клиент не выдумывает: 3 жизни и размер целевого
        забега приходят из config.py, а не написаны в шаблоне руками."""
        self.assertIn('CFG.mistakes_run_size', self.js)
        self.assertIn('MODE.lives', self.js)
        # запас жизней не захардкожен в отрисовке сердец
        self.assertNotRegex(self.js, r'for \(var i = 0; i < 3;')
