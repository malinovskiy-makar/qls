"""Регрессия математики калькулятора calc2 через manage.py test.

Математика calc2 написана на JS (Math.js в браузере), поэтому самый надёжный
способ её проверить — прогнать РЕАЛЬНЫЕ функции в настоящем браузере. Этот тест
поднимает живой сервер, создаёт суперпользователя и запускает node-раннер
calc2_math.mjs (Playwright) против /calc2/, проверяя контрольные числа.

Граничные случаи (Playwright/Node/CDN недоступны) → тест ПРОПУСКАЕТСЯ (skip),
а не падает: это не ломает остальные тесты в офлайн-CI. Сам node-раннер можно
запускать и отдельно: `node calc2/tests/calc2_math.mjs` (нужен живой dev-сервер).

ВАЖНО про базовый класс. Обычный LiveServerTestCase отдаёт статику только из
STATIC_ROOT, а в разработке он не задан: обработчик падал на document_root=None,
страница приходила без скриптов, раннер честно возвращал 3, и тест МОЛЧА
пропускался. То есть «тесты зелёные» значило «браузерная регрессия не
запускалась». StaticLiveServerTestCase отдаёт статику через finders, и STATIC_ROOT
ему не нужен. Причину любого пропуска печатаем ГРОМКО (_loud_skip): молчаливый
skip выглядит как «всё хорошо» и потому хуже красного теста.
"""
import os
import shutil
import subprocess

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import tag

RUNNER = os.path.join(os.path.dirname(__file__), "calc2_math.mjs")


@tag("calc2", "browser")
class Calc2MathRegressionTest(StaticLiveServerTestCase):
    """Все контрольные числа математики calc2 (равновесие, налог, монополия,
    дискриминация 1/3, ломаный, эластичность, Пигу, КПВ-сумма, труд, неравенство,
    торговля Б) — через реальные функции в браузере."""

    def setUp(self):
        User = get_user_model()
        # Суперпользователь-учитель для логина раннера (/calc2/ — login_required).
        self.user = User.objects.create_superuser(
            username="calc2_test", password="calc2_test_pw", email=""
        )
        if hasattr(self.user, "role"):
            self.user.role = "teacher"
            self.user.save(update_fields=["role"])

    def _loud_skip(self, reason):
        """Пропуск с громкой причиной прямо в выводе прогона.

        Молчаливый skip хуже красного теста: он выглядит как «всё хорошо».
        Печатаем рамку, чтобы пропуск нельзя было проглядеть в общей ленте.
        """
        line = "=" * 72
        print(f"\n{line}\nПРОПУЩЕНА браузерная регрессия calc2\nПричина: {reason}\n{line}")
        self.skipTest(reason)

    def test_calc2_control_numbers(self):
        node = shutil.which("node")
        if not node:
            self._loud_skip("node не найден, JS-регрессия calc2 не запускалась")
        if not os.path.exists(RUNNER):
            self._loud_skip(f"раннер не найден: {RUNNER}")

        env = dict(
            os.environ,
            CALC2_BASE_URL=self.live_server_url,
            CALC2_USER="calc2_test",
            CALC2_PASS="calc2_test_pw",
        )
        try:
            result = subprocess.run(
                [node, RUNNER],
                env=env,
                cwd=str(settings.BASE_DIR),
                capture_output=True,
                text=True,
                timeout=180,
            )
        except FileNotFoundError as exc:
            self._loud_skip(f"не удалось запустить node-раннер: {exc}")
        except subprocess.TimeoutExpired:
            self._loud_skip("node-раннер calc2 не уложился в 180с (браузер или CDN)")

        out = (result.stdout or "") + (result.stderr or "")
        # Код 3 — calc2 не загрузился (нет Playwright/Chromium или CDN Math.js/D3).
        if result.returncode == 3:
            self._loud_skip("calc2 не загрузился (Playwright или CDN недоступны):\n" + out[-500:])
        # Печатаем вывод раннера, чтобы при провале было видно конкретные числа.
        print("\n" + out)
        self.assertEqual(
            result.returncode,
            0,
            msg="Регрессия математики calc2 провалена (см. вывод выше).",
        )
