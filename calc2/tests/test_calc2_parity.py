"""Быстрый паритет нового экрана «Графиков» со старым (редизайн 10.2026).

Поднимает живой сервер и запускает node-раннер
calc2/tests/redesign/parity_quick.mjs: 44 модели, органы управления старта
на месте (с учётом закрытого списка замен), видимые числа старта равны
базовому снимку старого экрана (calc2/tests/redesign/baseline/).

Пропуск только там, где нет node или Playwright (раннер вернул 4 или не
нашёл пакет). Превышение времени и код 3 («calc2 не загрузился») — провал,
а не пропуск: иначе тест молча зеленел бы на сломанной странице.
Подробная сверка (шаги, жесты, геометрия) — вручную, см. calc2/tests/README.md.
"""
import os
import shutil
import subprocess

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import tag

RUNNER = os.path.join(os.path.dirname(__file__), "redesign", "parity_quick.mjs")
LIMIT_S = 120   # «прогон короче двух минут» (задание редизайна, фаза 11)


def _safe_print(text):
    import sys
    enc = (getattr(sys.stdout, "encoding", None) or "utf-8")
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(enc, "replace").decode(enc, "replace"))


# ⚠️ ПРИЧИНА МЕТКИ `serial` (без причины метку ставить запрещено, см.
# docs/TESTING.md): класс поднимает НАСТОЯЩИЙ веб-сервер и запускает против
# него Chromium отдельным процессом node — порт и браузер нельзя поделить
# между воркерами параллельного прогона, а восемь браузеров разом выводят
# раннер за предел времени по причине, не имеющей отношения к calc2.
@tag("calc2", "browser", "serial")
class Calc2ParityQuickTest(StaticLiveServerTestCase):
    """44 модели: органы старта и числа старта — как на старом экране."""

    def _loud_skip(self, reason):
        line = "=" * 72
        print(f"\n{line}\nПРОПУЩЕН быстрый паритет calc2\nПричина: {reason}\n{line}")
        self.skipTest(reason)

    def test_parity_quick(self):
        node = shutil.which("node")
        if not node:
            self._loud_skip("node не найден")
        env = dict(os.environ, CALC2_BASE_URL=self.live_server_url)
        try:
            result = subprocess.run(
                [node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=LIMIT_S,
            )
        except subprocess.TimeoutExpired:
            self.fail(f"быстрый паритет не уложился в {LIMIT_S} с")
        out = (result.stdout or "") + (result.stderr or "")
        if result.returncode == 4 or "Cannot find package 'playwright'" in out:
            self._loud_skip("Playwright недоступен:\n" + out[-400:])
        _safe_print("\n" + out)
        self.assertNotEqual(result.returncode, 3, msg="calc2 не загрузился (см. вывод выше).")
        self.assertEqual(result.returncode, 0, msg="Паритет нового экрана со старым нарушен (см. вывод выше).")
