"""Выгрузка графика в .tex (файл из записи при рисовании, ADR 0139).

Поднимает живой сервер и запускает node-раннер calc2/tests/tex/ci_quick.mjs:
44 старта моделей — файл строится, проверка текста без TeX проходит,
дефектов записи нет (кривая или область без записи, запись не сошлась с
нарисованным), окружений axis столько же, сколько панелей; пять моделей
разных семей дают один файл при двух окнах. Там, где есть pdflatex, те же 44
файла собираются тем же путём, что у сервера (compile_pdf_pdflatex); где его
нет — громкая строка «ПРОПУЩЕНА проверка сборки PDF», как в test_export_pdf.

Пропуск раннера только там, где нет node или Playwright (код 4 или не найден
пакет). Превышение времени и код 3 («calc2 не загрузился») — провал, а не
пропуск. Полные приборы выгрузки (1 025 состояний, листы, pgfmath) — вручную,
см. calc2/tests/README.md.
"""
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import SimpleTestCase, tag

from calc2.views import _TEX_FORBIDDEN, compile_pdf_pdflatex, pdflatex_available

HERE = os.path.dirname(__file__)
RUNNER = os.path.join(HERE, "tex", "ci_quick.mjs")
LINT = os.path.join(HERE, "tex", "lint.mjs")
LIMIT_S = 120   # «короче двух минут» (задание выгрузки .tex, фаза 4)


def _safe_print(text):
    import sys
    enc = (getattr(sys.stdout, "encoding", None) or "utf-8")
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(enc, "replace").decode(enc, "replace"))


class TexLintMatchesServerTests(SimpleTestCase):
    """Проверка текста приборов ловит запрещённые команды ТЕМ ЖЕ выражением,
    что сервер: иначе прибор пропустил бы файл, который сервер отвергнет."""

    def test_forbidden_regex_is_the_same(self):
        with open(LINT, encoding="utf-8") as fh:
            src = fh.read()
        m = re.search(r"export const TEX_FORBIDDEN = /(.+)/i;", src)
        self.assertIsNotNone(m, msg="в lint.mjs нет TEX_FORBIDDEN")
        self.assertEqual(m.group(1), _TEX_FORBIDDEN.pattern,
                         msg="выражение запрещённых команд в lint.mjs разошлось с calc2/views.py")


# ⚠️ ПРИЧИНА МЕТКИ `serial` (без причины метку ставить запрещено, см.
# docs/TESTING.md): класс поднимает НАСТОЯЩИЙ веб-сервер и запускает против
# него Chromium отдельным процессом node — порт и браузер нельзя поделить
# между воркерами параллельного прогона, а восемь браузеров разом выводят
# раннер за предел времени по причине, не имеющей отношения к выгрузке.
@tag("calc2", "browser", "serial")
class Calc2TexExportTest(StaticLiveServerTestCase):
    """44 старта: файл строится, текст чист, дефектов записи нет, сборка pdflatex."""

    def _loud_skip(self, what, reason):
        line = "=" * 72
        print(f"\n{line}\nПРОПУЩЕН{what}\nПричина: {reason}\n{line}")
        self.skipTest(reason)

    def test_tex_export(self):
        node = shutil.which("node")
        if not node:
            self._loud_skip(" быстрый прогон выгрузки .tex", "node не найден")
        out_dir = tempfile.mkdtemp(prefix="calc2tex_")
        self.addCleanup(shutil.rmtree, out_dir, True)
        env = dict(os.environ, CALC2_BASE_URL=self.live_server_url, OUT=out_dir)
        try:
            result = subprocess.run(
                [node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=LIMIT_S,
            )
        except subprocess.TimeoutExpired:
            self.fail(f"быстрый прогон выгрузки .tex не уложился в {LIMIT_S} с")
        out = (result.stdout or "") + (result.stderr or "")
        if result.returncode == 4 or "Cannot find package 'playwright'" in out:
            self._loud_skip(" быстрый прогон выгрузки .tex", "Playwright недоступен:\n" + out[-400:])
        _safe_print("\n" + out)
        self.assertNotEqual(result.returncode, 3, msg="calc2 не загрузился (см. вывод выше).")
        self.assertEqual(result.returncode, 0, msg="Выгрузка .tex нарушена (см. вывод выше).")

        files = sorted(f for f in os.listdir(out_dir) if f.endswith(".tex"))
        self.assertEqual(len(files), 44, msg="раннер записал не 44 файла")
        if not pdflatex_available():
            self._loud_skip("А проверка сборки PDF", "pdflatex не установлен на этой машине")

        def build(name):
            with open(os.path.join(out_dir, name), encoding="utf-8") as fh:
                pdf, err = compile_pdf_pdflatex(fh.read())
            return name, pdf, err

        with ThreadPoolExecutor(max_workers=4) as ex:
            built = list(ex.map(build, files))
        bad = [(n, (e or "")[-300:]) for n, pdf, e in built if not (pdf and pdf.startswith(b"%PDF"))]
        _safe_print(f"сборка pdflatex: {len(files) - len(bad)} из {len(files)}")
        self.assertFalse(bad, msg="не собрались: " + "; ".join(f"{n}: {e}" for n, e in bad))
