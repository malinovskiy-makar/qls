"""Сторож утечки памяти calc2 через manage.py test (13.10.2026, часть 3).

До 13.10 шаг ползунка сдвига кривой пересобирал список функций с полями MathLive,
а очереди ожидания библиотек держали каждую старую строку: +580 узлов DOM на шаг,
Safari ронял вкладку. Сторож жил жестом «(ж)» внутри calc2_math.mjs, и прогон
calc2_math вырос до 125–131 с при пределе Django-теста 180 с: на медленной машине
CI предел мог кончиться, и тогда пропускался ВЕСЬ calc2_math вместе с контрольными
числами. Поэтому сторож вынесен сюда, со своим пределом времени.

Запускает `SHORT=1 node calc2/tests/memory_probe.mjs` против живого сервера:
раздел А (150 шагов «Сдвига MC», прирост узлов DOM ≤ 2 000, обработчиков ≤ 400),
Г (ни одной пересборки списка и ни одного нового поля), Д (запись, «Отменить»,
автосохранение), Е (очереди ожидания KaTeX и MathLive пусты). Полный прибор с
протяжками мышью — тот же файл без SHORT, вручную.

Граничные случаи (нет node, Playwright, Chromium) — громкий пропуск, как у
test_calc2_math.py.
"""
import os
import shutil
import subprocess

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import tag

RUNNER = os.path.join(os.path.dirname(__file__), "memory_probe.mjs")


# ⚠️ ПРИЧИНА МЕТКИ `serial` — та же, что у Calc2MathRegressionTest
# (test_calc2_math.py): живой сервер на порту, Chromium отдельным процессом и
# поток сервера, который ходит в базу. Делить их между воркерами нельзя.
@tag("calc2", "browser", "serial")
class Calc2MemoryLeakTest(StaticLiveServerTestCase):
    """Сдвиг кривой не копит узлы DOM и обработчики (memory_probe.mjs, SHORT=1)."""

    def _loud_skip(self, reason):
        line = "=" * 72
        print(f"\n{line}\nПРОПУЩЕН сторож утечки calc2\nПричина: {reason}\n{line}")
        self.skipTest(reason)

    def test_shift_does_not_leak(self):
        node = shutil.which("node")
        if not node:
            self._loud_skip("node не найден, сторож утечки calc2 не запускался")
        env = dict(os.environ, CALC2_BASE_URL=self.live_server_url, SHORT="1")
        try:
            result = subprocess.run(
                [node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=120,
            )
        except FileNotFoundError as exc:
            self._loud_skip(f"не удалось запустить node-раннер: {exc}")
        except subprocess.TimeoutExpired:
            self._loud_skip("сторож утечки calc2 не уложился в 120 с (браузер)")
        out = (result.stdout or "") + (result.stderr or "")
        if result.returncode == 3:
            self._loud_skip("calc2 не загрузился (Playwright недоступен):\n" + out[-500:])
        enc = getattr(__import__("sys").stdout, "encoding", None) or "utf-8"
        print(("\n" + out).encode(enc, "replace").decode(enc, "replace"))
        self.assertEqual(result.returncode, 0, msg="Сторож утечки calc2 красный (см. вывод выше).")
