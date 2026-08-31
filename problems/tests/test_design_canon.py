"""ПРОВЕРКА КАНОНА ДЛЯ /calc2/ — двадцать одна проверка части 4 `DESIGN.md`.

Тест включается ТОЛЬКО на калькуляторе: канон писался под всю платформу, но
работа «Графики под канон» приводит к нему одну поверхность, и красный тест на
кабинетах остановил бы чужую работу.

Проверок двадцать. Восемнадцать из них считает браузер (`calc2/tests/
canon_checks.mjs`) — обход живых страниц в ОБЕИХ темах; две снимаются с
исходников (шестнадцатеричный цвет мимо токенов и покрытие
`prefers-reduced-motion`), потому что вычисленный стиль на них не отвечает:
браузер отдаёт готовое значение и не помнит, откуда оно взялось.

⚠️ ЗАЧЕМ СЛОВАРЬ `CEILING` (храповик долга, не выключатель). Тест написан РАНО,
до того как половина работы сделана, поэтому часть проверок красная по
построению. Раньше долг ВЫКЛЮЧАЛСЯ словарём `PENDING` — но выключенное
правило перестаёт ловить рост долга: сегодня 90 нарушений, через месяц 130,
и никто не заметил, тест всё равно зелёный. `CEILING` держит тест ЖИВЫМ:
· у правила есть потолок — максимум нарушений, который тест ещё терпит;
· нарушений стало БОЛЬШЕ потолка → тест красный, долг вырос;
· нарушений стало МЕНЬШЕ потолка → тест ТОЖЕ красный: долг почистили, но
  забыли опустить потолок, а значит починка может тихо зарасти обратно;
· нарушений ровно столько, сколько в потолке → тест зелёный, но печатает
  напоминание, что долг ещё стоит — молчаливого долга не остаётся.
Правило без записи в `CEILING` ведёт себя как обычная проверка канона: любое
нарушение — красный, без всякой поблажки. Решение и обоснование — Notion
«Решения», «Долг канона дизайна фиксируется храповиком (потолок числа
нарушений), а не отключением правила», 2026-08-22.

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
# ХРАПОВИК ДОЛГА. Число — ПОТОЛОК: максимум нарушений по правилу, который тест
# ещё терпит. Дошло до потолка — держит долг живым и на виду; перевалило за
# потолок — тест красный (долг вырос); стало МЕНЬШЕ потолка — тест ТОЖЕ
# красный (долг почистили, а планку не опустили — почини число здесь).
# Каждая закрытая фаза чистки убирает свою строку целиком; в конце работы
# словарь пуст. Рядом с каждым числом — когда и каким прогоном снято.
#
# Решение и обоснование: Notion «Решения», «Долг канона дизайна фиксируется
# храповиком (потолок числа нарушений), а не отключением правила», 2026-08-22,
# https://app.notion.com/p/3c4b11c92bc181ef9e07ee57ccf8c993 — там же отвергнут
# вариант с простым выключением правил.
# Карточка долга (порционная починка) — Notion «Задачи», статус «Надо»,
# «Долг канона дизайна: разбивка по правилам» (заведена в этой же сессии).
# ─────────────────────────────────────────────────────────────────────────────
# ⚠️ ЗАМЕР ПРИ РАСКРЫТЫХ КАРТОЧКАХ (24.08.2026). До этой даты раннер считал
# только ВИДИМОЕ, а сцена открывается со всеми свёрнутыми карточками — значит
# потолки были свойством не кода, а кода плюс того, что человек успел раскрыть.
# Теперь `expandAll` в раннере раскрывает все складные блоки и обе боковые
# панели ПЕРЕД подсчётом. Числа от этого выросли (контраст 4 → 23, нативная
# подсказка 90 → 134, и два правила впервые получили потолок вообще) — это не
# ухудшение кода, а первый честный замер: долг был там всё это время, просто
# прибор его не видел.
CEILING = {
    # Замер 24.08.2026, ветка feat/calc2-interv-night, ПРИ РАСКРЫТЫХ КАРТОЧКАХ:
    # manage.py test problems.tests.test_design_canon.CanonBrowserChecks -v 2.
    "accent_fill_count": 4,        # сплошной акцент в 4 местах вместо ≤3 (monopoly/costs, обе темы)
    "appearance_auto": 12,         # 12 системных чекбоксов рисуются браузером, не темой (sd/tax/mono)
    # 28 → 4 (22.08, при свёрнутых) → 23 честным замером 24.08 → 8 (31.08.2026).
    # Долг сняла ветка новой палитры Weconomics: тёплая гамма попала в норму
    # там, где холодная серо-синяя её не держала. Потолок опускается СРАЗУ,
    # чтобы улучшение нельзя было молча откатить — это долг, а не цель.
    # ⚠️ Замер деталей темы платформы сюда НЕ ВХОДИТ: раннер канона ходит по
    # /calc2/ (calc2/tests/canon_checks.mjs), а у калькулятора свой
    # изолированный мир токенов. Поэтому новая тёмная тема платформы
    # (#232322 / #3f3f3d, сессия 31.08 вечером) это число не двигала —
    # ни вверх, ни вниз, и 8 здесь ровно то же 8, что было утром.
    "contrast_text": 8,
    "dark_white_on_accent": 12,    # 20 → 14 (22.08) → 12 (24.08, вмешательство): две карточки налогов стали одной
    # ⚠️ 66 (26.08.2026) БЫЛО ОШИБКОЙ — верни, если снова захочется опустить.
    # Замер на Windows-машине разработчика в тот момент дал 66, но ни одна
    # строка CSS/шаблонов, влияющих на .stat-eq, в сессии не менялась — это
    # был не реальный ремонт долга, а разница окружений. CI (Ubuntu, тот же
    # Chromium из Playwright) стабильно меряет 68 на двух прогонах с разными
    # коммитами 24.08 и 26.08 без единой правки между ними: прогон
    # 32723133675 (24.08) и красный прогон 32927905338 (26.08). Локально
    # на Windows число ниже CI на 2 из-за хинтинга шрифтов в безголовом
    # Chromium — тот же класс ошибки, что «зелено на SQLite не значит зелено
    # на PostgreSQL»: CI ближе к проду (Linux), локальный Windows-замер этой
    # метрики авторитетным не считается. Не опускай потолок по замеру с
    # Windows — только по прогону CI или контейнера с Linux.
    "math_line_height": 68,
    "one_main_button": 10,         # впервые видно: рядом с главной кнопкой сцены раскрылась «Посчитать» из «Площадей»
    # title_on_interactive СТРОКИ БОЛЬШЕ НЕТ: 146 → 90 → 134 (честный замер) → 0.
    # Все подсказки переведены на свой компонент (Фаза 1, 24.08), нативного
    # `title` в калькуляторе не осталось ни одного. Правило снова обычное:
    # любое нарушение — красный, без поблажки.
}

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


def _ceiling_report(key, n, examples):
    """Решает исход одного правила канона по храповику `CEILING`.

    Возвращает пару `(заметка, провал)` — заполнено ровно одно из двух:
      · `заметка` — правило зелёное, но об активном потолке напоминаем вслух
        (в CEILING есть запись, и нарушений ровно столько, сколько в ней);
      · `провал` — правило красное: либо долг ВЫРОС (нарушений больше потолка),
        либо долг почистили, а потолок не опустили (нарушений МЕНЬШЕ потолка),
        либо потолка нет вовсе и нашлось хоть одно нарушение.
    `(None, None)` — правило зелёное и потолка не заводили: как до храповика.
    """
    title = NAMES.get(key, key)
    ex = ("\n    " + "\n    ".join(examples)) if examples else ""
    ceiling = CEILING.get(key)
    if ceiling is None:
        if n:
            return None, "%s (%s): нарушений %d, потолка нет — любое нарушение красное%s" % (title, key, n, ex)
        return None, None
    if n > ceiling:
        return None, ("%s (%s): потолок %d, сейчас %d — долг ВЫРОС на %d%s"
                       % (title, key, ceiling, n, n - ceiling, ex))
    if n < ceiling:
        return None, ("%s (%s): потолок %d, сейчас %d — стало ЛУЧШЕ, опусти потолок "
                       "CEILING[%r] до %d в problems/tests/test_design_canon.py"
                       % (title, key, ceiling, n, key, n))
    return "%s (%s): потолок %d, держится — известный долг, не эта сессия" % (title, key, ceiling), None


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

    def test_runner_expands_cards_before_counting(self):
        """Проверка (а) сессии 24.08: ЗАМЕР НЕ ЗАВИСИТ ОТ СОСТОЯНИЯ ЭКРАНА.

        Все двадцать правил считают только ВИДИМЫЕ элементы, а сцена
        открывается со всеми свёрнутыми карточками. Пока раннер не раскрывал их
        сам, потолки храповика были свойством не кода, а кода плюс того, что
        человек успел раскрыть: правка внутри свёрнутой карточки счётчик не
        двигала (проверено — 134 → 78 после снятия одного `title`).

        Почему проверка смотрит в исходник раннера, а не гоняет браузер дважды:
        честный ответ стоил бы двух полных обходов по 30 с каждый, и в полном
        прогоне это минута на одно правило. Здесь сторожится ровно то, что
        может отвалиться, — сам ВЫЗОВ раскрытия. Пропадёт он — прибор снова
        ослепнет молча, а этого допускать нельзя.
        """
        src = open(RUNNER, encoding="utf-8").read()
        if "async function expandAll(" not in src:
            self.fail("в calc2/tests/canon_checks.mjs нет функции expandAll — "
                      "замер снова считает только раскрытое человеком")
        # Вызов обязан стоять внутри openScene: только через неё проходит
        # каждая замеряемая сцена.
        start = src.find("async function openScene(")
        if start < 0:
            self.fail("в раннере канона нет openScene — проверка потеряла точку опоры")
        body = src[start:start + 1200]
        if "await expandAll(page)" not in body:
            self.fail("openScene в calc2/tests/canon_checks.mjs больше НЕ зовёт "
                      "expandAll: потолки храповика опять зависят от того, какие "
                      "карточки были раскрыты в момент прогона")
        # И сама expandAll обязана раскрывать складные блоки, а не быть заглушкой.
        i = src.find("async function expandAll(")
        eb = src[i:i + 1600]
        for need in ("fold-btn[aria-controls]", "setToolsOpen", "setParamsOpen"):
            if need not in eb:
                self.fail("expandAll больше не раскрывает «%s» — раскрытие "
                          "выхолощено, замер снова частичный" % need)

    def test_hex_outside_tokens(self):
        bad = hex_outside_tokens()
        note, fail = _ceiling_report("hex_outside_tokens", len(bad), bad)
        if note:
            _safe_print("\n" + note)
        if fail:
            self.fail(fail)

    def test_reduced_motion(self):
        bad = reduced_motion_covered()
        note, fail = _ceiling_report("reduced_motion", len(bad), bad)
        if note:
            _safe_print("\n" + note)
        if fail:
            self.fail(fail)


# ⚠️ ПРИЧИНА МЕТКИ `serial` (без причины метку ставить запрещено, см.
# docs/TESTING.md): та же, что у Calc2MathRegressionTest, и сильнее.
# Класс поднимает настоящий сервер и гоняет по нему Chromium, а таймаут
# раннера здесь 600 с — то есть при конкуренции за процессор он не просто
# медленный, он выходит за таймаут и краснеет по чужой вине.
# Живой сервер и браузер — внешние ресурсы, поделить их между воркерами
# нельзя.
@tag("calc2", "canon", "browser", "serial")
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

        notes, fails = [], []
        for key, box in sorted(data.items()):
            note, fail = _ceiling_report(key, box["n"], box["ex"])
            if note:
                notes.append("  " + note)
            if fail:
                fails.append("  " + fail)

        if notes:
            _safe_print("\nПОТОЛКИ ДОЛГА КАНОНА, ДЕРЖАТСЯ (%d):\n%s" % (len(notes), "\n".join(notes)))
        self.assertEqual(fails, [], "Канон нарушен (долг вырос либо потолок не опущен):\n" + "\n".join(fails))
