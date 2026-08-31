"""ПРОВЕРКА ПАЛИТРЫ WECONOMICS (redesign/palette, сессия «только _tokens.html»,
31.08.2026) — читает templates/_tokens.html КАК ТЕКСТ и проверяет контраст
WCAG 2.1 и различимость сигнального/брендового янтаря (ΔE Lab), без браузера.

Независим от scripts/palette_pick.py (та же математика продублирована здесь
намеренно): этот тест обязан пережить чистку одноразовых скриптов.
"""
import os
import re

from django.conf import settings
from django.test import SimpleTestCase

TOKENS_FILE = os.path.join(str(settings.BASE_DIR), "templates", "_tokens.html")

# Ровно пять новых токенов материализовались в фазе 1 (задание говорило
# «шесть», но перечислило явно пять — расхождение зафиксировано в отчёте
# сессии, шестого имени нигде в спецификации значений не нашлось).
NEW_TOKENS = [
    "--surface-tool",
    "--surface-info",
    "--accent-ink",
    "--brand-amber",
    "--brand-amber-ink",
]


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(rgb):
    r, g, b = rgb
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def _contrast_ratio(rgb1, rgb2):
    l1, l2 = _relative_luminance(rgb1), _relative_luminance(rgb2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _rgb_to_xyz(rgb):
    r, g, b = (_linear(c) for c in rgb)
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    return x, y, z


def _xyz_to_lab(xyz):
    xn, yn, zn = 0.95047, 1.0, 1.08883
    x, y, z = xyz[0] / xn, xyz[1] / yn, xyz[2] / zn

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _delta_e(hex1, hex2):
    lab1 = _xyz_to_lab(_rgb_to_xyz(_hex_to_rgb(hex1)))
    lab2 = _xyz_to_lab(_rgb_to_xyz(_hex_to_rgb(hex2)))
    return sum((a - b) ** 2 for a, b in zip(lab1, lab2)) ** 0.5


def _split_blocks(text):
    """Возвращает (текст :root, текст [data-theme="dark"]) по ровно одному
    вхождению каждого селектора — так же, как считает Инвариант 2 фазы 3."""
    root_start = text.index(":root {")
    dark_start = text.index('[data-theme="dark"] {')
    root_block = text[root_start:dark_start]
    dark_block = text[dark_start:]
    return root_block, dark_block


def _token_value(block, name):
    """Первое объявление `name: значение;` в блоке — без учёта rgba()-запятых."""
    m = re.search(re.escape(name) + r":\s*([^;]+);", block)
    if not m:
        raise AssertionError(f"токен {name} не найден в блоке")
    return m.group(1).strip()


def _resolve_color(block, name):
    """Значение токена как hex или сплошной rgb (не rgba — для сплошных
    поверхностей/текста этого достаточно, полупрозрачные токены в этих
    проверках не используются)."""
    value = _token_value(block, name)
    if value.startswith("#"):
        return _hex_to_rgb(value)
    raise AssertionError(f"{name} = {value!r} не hex-цвет — проверка ждёт сплошной цвет")


def _accent_rgb(block):
    """`--accent-rgb` как тройка чисел — из неё собираются заливки шкалы."""
    raw = _token_value(block, "--accent-rgb")
    return tuple(int(part) for part in raw.split(","))


def _over(top, alpha, below):
    """Полупрозрачный цвет поверх сплошного → сплошной.

    ⚠️ У `rgba(...)` яркости НЕТ, пока он не лёг на подложку. Мерить контраст
    по самой заливке значит мерить контраст с прозрачностью.
    """
    return tuple(top[i] * alpha + below[i] * (1 - alpha) for i in range(3))


class PaletteTokensTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open(TOKENS_FILE, encoding="utf-8") as fh:
            cls.text = fh.read()
        cls.root_block, cls.dark_block = _split_blocks(cls.text)

    def test_1_light_surface_lighter_than_bg(self):
        self.assertEqual(_token_value(self.root_block, "--bg"), "#f4eed2")
        self.assertEqual(_token_value(self.root_block, "--surface"), "#fffce6")
        bg = _resolve_color(self.root_block, "--bg")
        surface = _resolve_color(self.root_block, "--surface")
        self.assertGreater(
            _relative_luminance(surface), _relative_luminance(bg),
            "светлая тема: --surface обязана быть СВЕТЛЕЕ --bg (карточка светлее фона)",
        )

    def test_2_dark_surface_lighter_than_bg(self):
        """⚠️ Конкретные значения здесь БОЛЬШЕ НЕ ЗАШИТЫ (31.08.2026, вечер).

        Раньше тест требовал ровно `#191612` / `#242019`. Владелец принял
        пару дизайнера `#232322` / `#3f3f3d` — и тест покраснел, не сказав
        ни слова о читаемости: цвет поменялся, и что? Свойство, ради которого
        он писался, от значения не зависит — карточка обязана быть светлее
        фона. Его и проверяем.
        """
        bg = _resolve_color(self.dark_block, "--bg")
        surface = _resolve_color(self.dark_block, "--surface")
        self.assertGreater(
            _relative_luminance(surface), _relative_luminance(bg),
            "тёмная тема: --surface обязана быть СВЕТЛЕЕ --bg (карточка светлее фона)",
        )

    def test_3_text_on_surface_contrast(self):
        for block, theme in ((self.root_block, "светлая"), (self.dark_block, "тёмная")):
            text = _resolve_color(block, "--text")
            surface = _resolve_color(block, "--surface")
            ratio = _contrast_ratio(text, surface)
            self.assertGreaterEqual(
                ratio, 4.6, f"{theme} тема: --text на --surface даёт {ratio:.2f}, нужно ≥ 4,6"
            )

    def test_4_text3_on_bg_contrast(self):
        for block, theme in ((self.root_block, "светлая"), (self.dark_block, "тёмная")):
            text3 = _resolve_color(block, "--text3")
            bg = _resolve_color(block, "--bg")
            ratio = _contrast_ratio(text3, bg)
            self.assertGreaterEqual(
                ratio, 4.6, f"{theme} тема: --text3 на --bg даёт {ratio:.2f}, нужно ≥ 4,6"
            )

    def test_5_accent_ink_on_bg_contrast(self):
        for block, theme in ((self.root_block, "светлая"), (self.dark_block, "тёмная")):
            accent_ink = _resolve_color(block, "--accent-ink")
            bg = _resolve_color(block, "--bg")
            ratio = _contrast_ratio(accent_ink, bg)
            self.assertGreaterEqual(
                ratio, 4.6, f"{theme} тема: --accent-ink на --bg даёт {ratio:.2f}, нужно ≥ 4,6"
            )

    def test_6_brand_amber_vs_signal_amber_delta_e(self):
        for block, theme in ((self.root_block, "светлая"), (self.dark_block, "тёмная")):
            brand = _token_value(block, "--brand-amber")
            amber = _token_value(block, "--amber")
            de = _delta_e(brand, amber)
            self.assertGreaterEqual(
                de, 30,
                f"{theme} тема: ΔE(--brand-amber, --amber) = {de:.1f}, нужно ≥ 30 "
                "(иначе бренд и сигнал «сложность» путаются)",
            )

    def test_8_activity_ink_on_the_densest_fill(self):
        """Цифра дня на самой плотной ПОЛУПРОЗРАЧНОЙ заливке шкалы.

        Третий уровень — последний, где клетка ещё не сплошной акцент, и
        именно он проваливался в обеих темах сразу. Заливка полупрозрачная,
        поэтому считается композит на карточке, а не сам `rgba(...)`.
        """
        for block, theme in ((self.root_block, "светлая"), (self.dark_block, "тёмная")):
            alpha = float(_token_value(block, "--act-a3"))
            fill = _over(_accent_rgb(block), alpha, _resolve_color(block, "--surface"))
            ink = _resolve_color(block, "--act-ink")
            ratio = _contrast_ratio(ink, fill)
            self.assertGreaterEqual(
                ratio, 4.6,
                f"{theme} тема: --act-ink на заливке --act-a3 даёт {ratio:.2f}, нужно ≥ 4,6",
            )

    def test_9_signals_readable_on_both_surfaces(self):
        """Сигналы и третьестепенный текст живут И на карточке, И на фоне.

        ⚠️ Мерить только карточку — половина правды: тот же чип «частично
        верно» встречается и прямо на поле страницы, а поверхности разной
        светлоты. Ровно так и вскрылся провал янтарных чернил светлой темы.
        """
        for block, theme in ((self.root_block, "светлая"), (self.dark_block, "тёмная")):
            for name in ("--text3", "--amber", "--error"):
                colour = _resolve_color(block, name)
                for surface_name in ("--surface", "--bg"):
                    below = _resolve_color(block, surface_name)
                    ratio = _contrast_ratio(colour, below)
                    self.assertGreaterEqual(
                        ratio, 4.6,
                        f"{theme} тема: {name} на {surface_name} даёт {ratio:.2f}, нужно ≥ 4,6",
                    )

    def test_10_button_ink_meets_aaa_in_both_themes(self):
        """Текст на главной кнопке — порог AAA 7,0, в каждой теме свой.

        ⚠️ Чернила берутся из `--on-btn` СВОЕЙ темы, а не считаются белыми:
        в тёмной теме кнопка светлая и текст на ней тёмный.
        """
        for block, theme in ((self.root_block, "светлая"), (self.dark_block, "тёмная")):
            btn = _resolve_color(block, "--btn-bg")
            ink = _resolve_color(block, "--on-btn")
            ratio = _contrast_ratio(ink, btn)
            self.assertGreaterEqual(
                ratio, 7.0,
                f"{theme} тема: --on-btn на --btn-bg даёт {ratio:.2f}, нужно ≥ 7,0 (AAA)",
            )

    def test_7_new_tokens_not_duplicated(self):
        for block, theme in ((self.root_block, "светлая"), (self.dark_block, "тёмная")):
            for name in NEW_TOKENS:
                count = len(re.findall(re.escape(name) + r":", block))
                if count == 0:
                    continue  # не каждый новый токен обязан жить в обеих темах (см. Фазу 1)
                self.assertEqual(
                    count, 1,
                    f"{theme} тема: {name} объявлен {count} раз(а) в одном блоке, ожидался один",
                )
