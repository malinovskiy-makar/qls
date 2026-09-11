"""Общее для генераторов страниц Фазы 2 (razmetka.html, vydachi.html).

ТОЛЬКО ЧИТАЕТ файлы с диска — банк не трогает.
"""
import base64
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # C:\Users\shipu\qls
KATEX_DIR = ROOT / 'static' / 'vendor' / 'katex-0.16.9'


def load_pool():
    with open(ROOT / 'reports/formula_choice/pool.json', encoding='utf-8') as fh:
        return json.load(fh)


def load_problems_data():
    with open(ROOT / 'reports/formula_choice/problems_data.json', encoding='utf-8') as fh:
        return json.load(fh)


def katex_css_inline():
    """katex.min.css с font-face, ссылающимися на data: URI (только woff2).

    Оффлайн-страница не может ходить за шрифтами по относительному пути
    fonts/*.woff2 — файла katex.min.css рядом с ней не будет, есть только
    один .html. Вырезаем woff/ttf-фоллбэки (лишний вес, современный браузер
    woff2 отрисует всегда) и заменяем src на base64.
    """
    css = (KATEX_DIR / 'katex.min.css').read_text(encoding='utf-8')

    def _replace(m):
        family_decl = m.group(0)
        font_file = m.group(1)
        data = (KATEX_DIR / 'fonts' / font_file).read_bytes()
        b64 = base64.b64encode(data).decode('ascii')
        # Заменяем весь список src=... на единственный data: URI (woff2).
        new_src = f'src:url(data:font/woff2;base64,{b64}) format("woff2")'
        return re.sub(r'src:url\([^)]+\)[^;{}]*', new_src, family_decl)

    css = re.sub(
        r'@font-face\{[^}]*url\(fonts/([^)]+\.woff2)\)[^}]*\}',
        _replace, css,
    )
    return css


def katex_js_inline():
    return (KATEX_DIR / 'katex.min.js').read_text(encoding='utf-8')


def katex_autorender_js_inline():
    return (KATEX_DIR / 'contrib' / 'auto-render.min.js').read_text(encoding='utf-8')


def katex_dollars_js_inline():
    """JS-тело templates/_katex_dollars.html (maskEscapedDollars/
    fixCurrencyDollars) без обёртки Django {% comment %}/<script>."""
    text = (ROOT / 'templates' / '_katex_dollars.html').read_text(encoding='utf-8')
    m = re.search(r'<script>(.*)</script>', text, re.DOTALL)
    if not m:
        raise RuntimeError('Не нашёл <script> в _katex_dollars.html')
    return m.group(1)


def json_for_script(obj):
    """JSON, безопасный для вставки в <script>: экранирует "</" и U+2028/29."""
    s = json.dumps(obj, ensure_ascii=False)
    s = s.replace('</', '<\\/')
    s = s.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    return s
