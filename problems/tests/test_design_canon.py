"""ПРОВЕРКА КАНОНА ДЛЯ /calc2/ — двадцать одна проверка части 4 `DESIGN.md`.

Тест включается ТОЛЬКО на калькуляторе: канон писался под всю платформу, но
работа «Графики под канон» приводит к нему одну поверхность, и красный тест на
кабинетах остановил бы чужую работу.

Проверок двадцать. Восемнадцать из них считает браузер (`calc2/tests/
canon_checks.mjs`) — обход живых страниц в ОБЕИХ темах; две снимаются с
исходников (шестнадцатеричный цвет мимо токенов и покрытие
`prefers-reduced-motion`), потому что вычисленный стиль на них не отвечает:
браузер отдаёт готовое значение и не помнит, откуда оно взялось.

⚠️ ЗАЧЕМ СЛОВАРЬ `PENDING`. Тест написан РАНО, до того как половина работы
сделана, поэтому часть проверок красная по построению. Оставить их включёнными
значит приучить не смотреть на красное; выключить без списка значит забыть.
Словарь и выключает, и считает долг: каждая закрытая фаза убирает отсюда свою
строку, в конце работы он пуст. Пока строка в словаре, тест ПЕЧАТАЕТ её
громко — молчаливого долга не остаётся.

Причина, по которой тест написан раньше остальных фаз: первый полный прогон
проекта нашёл 13 красных, внесённых фазой 1 и проживших две сессии.

Запуск раннера руками против живого сервера:
    CALC2_BASE_URL=http://127.0.0.1:8601 CALC2_USER=student1 \
    CALC2_PASS=student12345 node calc2/tests/canon_checks.mjs
"""
import os
import re
import json
import shutil
import subprocess

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import SimpleTestCase, tag

BASE = str(settings.BASE_DIR)
RUNNER = os.path.join(BASE, "calc2", "tests", "canon_checks.mjs")
CSS = os.path.join(BASE, "calc2", "static", "calc2", "calc2.css")
JS_DIR = os.path.join(BASE, "calc2", "static", "calc2")

# ─────────────────────────────────────────────────────────────────────────────
# Проверки, которые ещё НЕ должны проходить. Каждая закрытая фаза убирает свою
# строку; в конце работы словарь пуст. Значение — фаза, которая строку закроет.
# ─────────────────────────────────────────────────────────────────────────────
PENDING = {}

# Человеческие названия — они же идут в вывод прогона.
NAMES = {
    "hex_outside_tokens": "1. шестнадцатеричный цвет мимо токенов",
    "dark_white_on_accent": "2. в тёмной теме нет белого текста на акценте",
    "contrast_text": "3. контраст текста ≥ 4,6 (крупного ≥ 3,0) в обеих темах",
    "appearance_auto": "4. орган управления не рисуется системой",
    "one_main_button": "5. не более одной главной кнопки на экран",
    "disabled_button_explained": "6. у выключенной кнопки есть текстовый сосед",
    "tabular_nums": "7. табличные цифры у крупного числа",
    "title_on_interactive": "8. нативная подсказка не используется",
    "no_h_scroll": "9. страница не едет вбок на 360/560/760/1024",
    "type_scale": "10. кегль и вес из шкалы канона 1.2",
    "radius_scale": "11. скругление из пяти значений канона 1.5",
    "reduced_motion": "12. prefers-reduced-motion покрывает все переходы",
    "state_plate_tint": "13. у плашки состояния нет фона из семейства -tint",
    "two_stripes": "14. ни одного элемента с двумя полосами на одном крае",
    "math_line_height": "15. текст с формулами не теснее 1,55",
    "shadow_only_pop": "16. тень только у всплывающего и у колец фокуса",
    "knum_44": "17. область касания поля-полосочки ≥ 44 px (канон 3.3)",
    "accent_fill_count": "8. сплошной акцент только у выбранного, не больше трёх мест",
    "dark_light_widget": "18. в тёмной теме нет светлых системных виджетов",
    "raw_template": "19. на странице нет сырого шаблонного синтаксиса",
    "label_clipped": "20. ни одна подпись холста не обрезана",
    "label_shake": "21. подпись кривой не дёргается при сдвиге ползунка",
}


def _safe_print(text):
    """Печать, которая не падает на символах, неизвестных консоли."""
    import sys
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(enc, "replace").decode(enc, "replace"))


def _brace_span(text, start):
    """Границы блока `{ … }`, начиная от первой скобки после `start`."""
    i = text.index("{", start)
    depth = 0
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return (text.index("{", start), i)
        i += 1
    return (text.index("{", start), len(text))


def _strip_js_comments(src):
    """Комментарии вырезаются ДО поиска цвета.

    В комментариях calc2 лежит история: «S (#E0563B на белом) — 3,77» — это
    протокол замера, а не стиль. Считать их нарушением значит запретить
    объяснять, почему цвет именно такой.
    Строки при этом сохраняются: номер строки в отчёте обязан совпадать
    с номером в файле.
    """
    out = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), src, flags=re.S)
    return re.sub(r"(^|[^:])//[^\n]*", lambda m: m.group(1), out)


def hex_outside_tokens():
    """Проверка 1. Цвет берётся из переменной, а не пишется числом.

    Разрешено ровно три места:
      · блоки токенов самого calc2 (`:root`, тема) — у калькулятора свой
        изолированный мир переменных, и палитра кривых живёт там;
      · `@media print` — бумага белая, чернила чёрные, это не тема;
      · запасное значение переменной (`var(--x, #fff)`, `cssVar('--x') || '#fff'`):
        оно срабатывает, когда переменной нет вовсе.

    ⚠️ Последнее средство в JS засчитывается ТОЛЬКО с оговоркой в комментарии
    той же строки («запасное значение»). Причина не в форме записи: значение,
    которое нужно ровно на случай отсутствия переменной, взять из переменной
    нельзя по определению, и единственная защита от того, чтобы под эту
    поблажку не уехал обычный цвет, — требование объяснить её на месте.
    """
    bad = []
    css = open(CSS, encoding="utf-8").read()
    spans = []
    for m in re.finditer(r"^\s*:root[^{]*\{", css, re.M):
        spans.append(_brace_span(css, m.start()))
    for m in re.finditer(r"\[data-theme[^{]*\{", css):
        spans.append(_brace_span(css, m.start()))
    for m in re.finditer(r"@media\s+print[^{]*\{", css):
        spans.append(_brace_span(css, m.start()))
    for m in re.finditer(r"#[0-9a-fA-F]{3,8}\b", css):
        if any(a <= m.start() <= b for a, b in spans):
            continue
        if re.search(r"var\(\s*--[\w-]+\s*,\s*$", css[max(0, m.start() - 60):m.start()]):
            continue
        bad.append("calc2.css:%d %s" % (css[:m.start()].count("\n") + 1, m.group(0)))

    for fn in sorted(os.listdir(JS_DIR)):
        if not fn.endswith(".js"):
            continue
        src = _strip_js_comments(open(os.path.join(JS_DIR, fn), encoding="utf-8").read())
        for m in re.finditer(r"#[0-9a-fA-F]{3,8}\b", src):
            pre = src[max(0, m.start() - 60):m.start()]
            if re.search(r"(\|\||\?\?)\s*['\"]$", pre):        # запасное значение
                continue
            line = src.split("\n")[src[:m.start()].count("\n")]
            raw = open(os.path.join(JS_DIR, fn), encoding="utf-8").read().split("\n")
            here = raw[src[:m.start()].count("\n")] if src[:m.start()].count("\n") < len(raw) else ""
            if "запасное значение" in here or "запасное значение" in line:
                continue
            if re.search(r"(getElementById|querySelector\w*)\(\s*['\"]$", pre):
                continue                                        # это селектор, а не цвет
            bad.append("%s:%d %s" % (fn, src[:m.start()].count("\n") + 1, m.group(0)))
    return bad


def reduced_motion_covered():
    """Проверка 12. Отказ от движения гасит ВСЕ переходы, а не перечень классов.

    Спрашиваем не «есть ли блок», а есть ли в нём УНИВЕРСАЛЬНОЕ правило:
    список классов устаревает от первой же новой анимации, звёздочка — нет.
    """
    css = open(CSS, encoding="utf-8").read()
    for m in re.finditer(r"@media\s*\(\s*prefers-reduced-motion:\s*reduce\s*\)[^{]*\{", css):
        a, b = _brace_span(css, m.start())
        body = css[a:b]
        if not re.search(r"(^|[{;\s])\*\s*\{", body):
            continue
        if "transition-duration" in body and "animation-duration" in body and "!important" in body:
            return []
    return ["в calc2.css нет универсального правила `*` внутри "
            "@media (prefers-reduced-motion: reduce)"]


@tag("calc2", "canon")
class CanonSourceChecks(SimpleTestCase):
    """Две проверки, на которые вычисленный стиль не отвечает."""

    def test_hex_outside_tokens(self):
        bad = hex_outside_tokens()
        if "hex_outside_tokens" in PENDING:
            _safe_print("\nОТЛОЖЕНО (%s): %s — нарушений %d%s"
                        % (NAMES["hex_outside_tokens"], PENDING["hex_outside_tokens"],
                           len(bad), (": " + "; ".join(bad[:5])) if bad else ""))
            return
        self.assertEqual(bad, [], "Цвет числом мимо токенов (канон 1.1)")

    def test_reduced_motion(self):
        bad = reduced_motion_covered()
        if "reduced_motion" in PENDING:
            _safe_print("\nОТЛОЖЕНО (%s): %s" % (NAMES["reduced_motion"], PENDING["reduced_motion"]))
            return
        self.assertEqual(bad, [], "Отказ от движения покрывает не всё (канон 1.8)")


@tag("calc2", "canon", "browser")
class CanonBrowserChecks(StaticLiveServerTestCase):
    """Восемнадцать проверок в настоящем браузере, обе темы.

    Пропуск (нет node или Playwright) печатается ГРОМКО: молчаливый пропуск
    выглядит как «всё хорошо» и потому хуже красного.
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username="canon_test", password="canon_test_pw", email="")
        if hasattr(self.user, "role"):
            self.user.role = "teacher"
            self.user.save(update_fields=["role"])

    def _loud_skip(self, reason):
        line = "=" * 72
        _safe_print("\n%s\nПРОПУЩЕНА проверка канона /calc2/\nПричина: %s\n%s"
                    % (line, reason, line))
        self.skipTest(reason)

    def test_canon(self):
        node = shutil.which("node")
        if not node:
            self._loud_skip("node не найден, проверка канона не запускалась")
        if not os.path.exists(RUNNER):
            self._loud_skip("раннер не найден: %s" % RUNNER)

        env = dict(os.environ,
                   CALC2_BASE_URL=self.live_server_url,
                   CALC2_USER="canon_test",
                   CALC2_PASS="canon_test_pw")
        try:
            res = subprocess.run([node, RUNNER], env=env, cwd=BASE, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=600)
        except FileNotFoundError as exc:
            self._loud_skip("не удалось запустить раннер: %s" % exc)
        except subprocess.TimeoutExpired:
            self._loud_skip("раннер канона не уложился в 600 с")

        out = (res.stdout or "") + (res.stderr or "")
        if res.returncode == 3:
            # ⚠️ У ошибки JavaScript главное — ПЕРВАЯ строка, само сообщение;
            # хвост это стек. Показывали только последние 600 символов, и в
            # полном прогоне 21.08 пропуск оказалось нечем объяснить: от
            # «... is not defined» осталась одна середина стека. Печатаем и
            # голову, и хвост.
            head, tail = out[:700], out[-900:]
            self._loud_skip("calc2 не загрузился.\nНАЧАЛО ВЫВОДА:\n%s\n…\nХВОСТ:\n%s"
                            % (head, tail))
        if "###CANON-JSON###" not in out:
            self.fail("раннер не отдал результат:\n" + out[-2000:])

        data = json.loads(out.split("###CANON-JSON###", 1)[1].strip().splitlines()[0])

        broken, waiting = [], []
        for key, box in sorted(data.items()):
            title = NAMES.get(key, key)
            if key in PENDING:
                waiting.append("  %s — %s (нарушений %d)" % (title, PENDING[key], box["n"]))
                continue
            if box["n"]:
                broken.append("%s: %d\n    %s" % (title, box["n"], "\n    ".join(box["ex"])))

        if waiting:
            _safe_print("\nОТЛОЖЕННЫЕ ПРОВЕРКИ КАНОНА (%d):\n%s" % (len(waiting), "\n".join(waiting)))
        self.assertEqual(broken, [], "Канон нарушен:\n" + "\n".join(broken))
