"""Превью моделей экрана выбора (ADR 0141) — дешёвый сторож без браузера.

Файл calc2/static/calc2/previews.json собирает заранее
calc2/tests/previews/make_previews.mjs из записи при рисовании стандартного
старта каждой модели. Здесь сверяется только СОСТАВ: ключи файла — ровно
рабочие карточки .scard экрана выбора в шаблоне (42), ни одной лишней, ни
одной недостающей, у «скоро» превью нет; у каждого превью есть пути, нет
текста, цвета — именами токенов; ручных схем .scard-spec в шаблоне нет.
Свежесть (старт модели поменялся, а превью нет) сторожит браузерный
tex/ci_quick.mjs: он и так открывает все старты.
"""
import json
import os
import re

from django.test import SimpleTestCase

HERE = os.path.dirname(__file__)
APP = os.path.dirname(HERE)
TEMPLATE = os.path.join(APP, "templates", "calc2", "calc2.html")
PREVIEWS = os.path.join(APP, "static", "calc2", "previews.json")
REBUILD = "node calc2/tests/previews/make_previews.mjs"
WORKING = 42
LIMIT = 150 * 1024


def _picker_cards():
    """(рабочие, «скоро») ключи карточек окна выбора в шаблоне."""
    with open(TEMPLATE, encoding="utf-8") as fh:
        src = fh.read()
    start = src.index('id="scene-picker"')
    end = src.index('id="model-head"', start)
    working, soon = [], []
    for m in re.finditer(r'<button class="scard( soon)?" data-scene="([^"]+)"', src[start:end]):
        (soon if m.group(1) else working).append(m.group(2))
    return working, soon, src


class PickerPreviewsTests(SimpleTestCase):
    def setUp(self):
        with open(PREVIEWS, encoding="utf-8") as fh:
            self.raw = fh.read()
        self.data = json.loads(self.raw)
        self.working, self.soon, self.src = _picker_cards()

    def test_keys_are_exactly_the_working_cards(self):
        self.assertEqual(len(self.working), WORKING, msg="рабочих карточек в шаблоне не 42")
        keys = set(self.data)
        missing = sorted(set(self.working) - keys)
        extra = sorted(keys - set(self.working))
        self.assertFalse(missing, msg="нет превью у моделей: %s — пересоберите командой %s" % (", ".join(missing), REBUILD))
        self.assertFalse(extra, msg="превью без рабочей карточки: %s — пересоберите командой %s" % (", ".join(extra), REBUILD))
        self.assertEqual(len(self.data), WORKING)
        self.assertFalse(set(self.soon) & keys, msg="у модели «скоро» есть превью")

    def test_every_preview_is_drawable_and_textless(self):
        token = re.compile(r"^(curve-[a-z]+|cost-[a-z]+|c-(warn|bad|profit|price)|sum-g\d|ink|ink-soft)$")
        for key, pv in self.data.items():
            self.assertRegex(pv.get("vb", ""), r"^0 0 [\d.]+ [\d.]+$", msg=key)
            self.assertRegex(pv.get("fp", ""), r"^[0-9a-f]{16}$", msg=key)
            self.assertTrue(pv.get("p"), msg="%s: в превью нет ни одного пути" % key)
            for q in pv["p"]:
                self.assertTrue(q.get("d", "").startswith("M"), msg=key)
                for k in ("s", "f"):
                    if k in q:
                        self.assertRegex(q[k], token, msg="%s: цвет не токен темы: %s" % (key, q[k]))
        self.assertNotRegex(self.raw, r'"(text|tspan)"|<text', msg="в превью текстовый узел")
        self.assertLessEqual(len(self.raw.encode("utf-8")), LIMIT, msg="previews.json больше 150 КБ")

    def test_no_hand_drawn_schemes_left(self):
        self.assertEqual(self.src.count("scard-spec"), 0, msg="в шаблоне снова ручная схема .scard-spec")

    def test_page_knows_where_previews_live(self):
        self.assertIn("data-previews=\"{% calc2_static 'calc2/previews.json' %}\"", self.src)
