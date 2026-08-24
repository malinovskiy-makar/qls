"""Тест-страж метки версии на статике calc2.

ЗАЧЕМ. 21.08 приёмка дала ложное отрицание: в браузере владельца лежал старый
calc2.css (104 094 байта против 105 460 на сервере), скрипты при этом были
свежие. Починенный дефект выглядел непочиненным. Лечение — общая метка версии
в адресе каждого файла статики calc2 (`calc2/templatetags/calc2_static.py`).

ЧТО СТЕРЕЖЁМ. Метку легко потерять: достаточно дописать в шаблон ещё один
`<script src="{% static 'calc2/...' %}">` по образцу соседних строк. Тест
падает на любой такой ссылке — и на голом `{% static %}`, и на отрисованном
адресе без `?v=`.
"""
import re

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from calc2.templatetags.calc2_static import STATIC_DIR, calc2_static_version
from calc2.management.commands.calc2_map import APP_DIR

TEMPLATE_PATH = APP_DIR / 'templates' / 'calc2' / 'calc2.html'

# Голая ссылка на статику calc2 — та самая, которую метка обходит стороной.
BARE_STATIC_RE = re.compile(r"\{%\s*static\s+'calc2/[^']+'\s*%\}")
# Ссылка с меткой.
TAGGED_RE = re.compile(r"\{%\s*calc2_static\s+'(calc2/[^']+)'\s*%\}")
# Адрес статики calc2 в отрисованной странице.
RENDERED_RE = re.compile(r'(?:href|src)="([^"]*?/calc2/[^"]+)"')

HINT = ('используйте {% calc2_static \'calc2/файл\' %} вместо {% static %} — '
        'иначе браузер отдаст старый файл, и починенное будет выглядеть непочиненным')


class Calc2StaticVersionTemplateTests(SimpleTestCase):
    """Разметка шаблона: ни одной ссылки без метки."""

    def test_no_bare_static_for_calc2(self):
        src = TEMPLATE_PATH.read_text(encoding='utf-8')
        bare = BARE_STATIC_RE.findall(src)
        self.assertEqual(
            bare, [],
            'В {} есть ссылки на статику calc2 без метки версии: {}. {}'.format(
                TEMPLATE_PATH.name, bare, HINT),
        )

    def test_every_static_file_of_calc2_is_linked_with_version(self):
        """Все ссылки идут через тег с меткой, и файлы на месте."""
        src = TEMPLATE_PATH.read_text(encoding='utf-8')
        tagged = TAGGED_RE.findall(src)
        self.assertGreaterEqual(len(tagged), 23, 'Ссылок на статику calc2 стало меньше 23 — проверьте шаблон')
        missing = [rel for rel in tagged if not (APP_DIR / 'static' / rel).exists()]
        self.assertEqual(missing, [], 'Ссылки ведут на несуществующие файлы: {}'.format(missing))

    def test_version_depends_on_file_contents(self):
        """Метка меняется от правки любого файла и возвращается назад."""
        before = calc2_static_version()
        victim = STATIC_DIR / 'calc2.css'
        original = victim.read_bytes()
        try:
            victim.write_bytes(original + '\n/* проверка метки версии */\n'.encode('utf-8'))
            self.assertNotEqual(before, calc2_static_version(),
                                'Метка не изменилась после правки calc2.css')
        finally:
            victim.write_bytes(original)
        self.assertEqual(before, calc2_static_version(),
                         'Метка не вернулась к прежнему значению после отката правки')


class Calc2StaticVersionRenderTests(TestCase):
    """Отрисованная страница: метка стоит у КАЖДОГО адреса статики calc2."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username='calc2-static-guard', password='x' * 12)

    def test_rendered_page_marks_every_calc2_asset(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse('calc2:calculator')).content.decode('utf-8')
        urls = RENDERED_RE.findall(html)
        self.assertGreaterEqual(len(urls), 23,
                                'В отрисованной странице меньше 23 адресов статики calc2')
        version = calc2_static_version()
        unmarked = [u for u in urls if '?v=' not in u]
        self.assertEqual(unmarked, [],
                         'Адреса статики calc2 без метки версии: {}. {}'.format(unmarked, HINT))
        wrong = [u for u in urls if not u.endswith('?v=' + version)]
        self.assertEqual(wrong, [],
                         'Метка не общая на всю страницу — расходятся: {}'.format(wrong))
