# -*- coding: utf-8 -*-
r"""TikZ/PGFPlots → SVG: извлечение, компиляция в песочнице, чистка SVG.

Контекст. [ADR 0031](../../docs/adr/0031-tikz-svg-blocked-by-sanitizer.md)
зафиксировал: сама песочница выполнима и ЗАМЕРЕНА на этой машине, а
блокером было то, что готовый SVG некуда положить — общий санитайзер
(`nh3` в `problems/rendering.py`) не пропускает ни `img`, ни `svg`, а
`attributes={}` снимает все атрибуты. Владелец решил санитайзер НЕ
трогать и сделать отдельный контролируемый путь: картинка живёт в
`ProblemFigure`, в тексте задачи остаётся только маркер
`[[FIGURE:<sha256>]]`, а `<img>` подставляется ПОСЛЕ санитайзера по
первичному ключу строки БД (`problems/figures.py`).

Замеренные параметры песочницы (ADR 0031, воспроизведено):
* компиляция офлайн — `-disable-installer` (MiKTeX иначе лезет в сеть
  за недостающими пакетами);
* `-no-shell-escape` — `\write18` (запуск произвольных команд) закрыт;
* таймаут 10 с убивает зациклившийся документ начисто, процессов-сирот
  не остаётся;
* переполнение памяти TeX обрывает сам за ~1 с внутренним лимитом
  `main_memory` — на Windows нет `setrlimit`, и это единственная
  доступная защита, но она реально работает;
* свой временный каталог на каждую компиляцию, удаляется целиком.

⚠️ Чего этот модуль НЕ делает: не пишет в базу и не решает, показывать
ли картинку. Он только «TeX → чистый SVG». Хранение — модель
`ProblemFigure`, показ — `problems/figures.py`.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile

#: Маркер в тексте задачи. Тело — РОВНО 64 hex-символа в нижнем регистре.
#: Строгость здесь не косметика: это единственное, что попадает в текст
#: задачи, и по нему потом ищется строка в БД. Ни путь, ни URL, ни
#: верхний регистр в маркер не пролезут (тесты `SecurityPerimeterTests`).
MARKER_RE = re.compile(r'\[\[FIGURE:([0-9a-f]{64})\]\]')
_MARKER_TEMPLATE = '[[FIGURE:{}]]'

#: Полное окружение картинки.
_TIKZPICTURE_RE = re.compile(
    r'\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}', re.DOTALL)

#: Осиротевшая команда графика без обёртки (живой #30164): обёртку
#: `tikzpicture`/`axis` потерял импорт.
#:
#: ⚠️ Построчной регуляркой тут НЕЛЬЗЯ, и это выяснено прогоном, а не
#: рассуждением: у #30172 команда разложена на несколько строк
#: (открывающая скобка, `domain=0:1.8,`, `samples=100,`, закрывающая),
#: построчный захват рвал её посередине, и latex падал с
#: «File ended while scanning use of pgfplots@addplot». Поэтому команда
#: читается целиком — до `;` на нулевой глубине скобок.
_ADDPLOT_START_RE = re.compile(r'\\addplot\b')

#: Преамбула компиляции. `standalone` даёт картинку по размеру
#: содержимого, без полей страницы.
_TEX_TEMPLATE = r"""\documentclass[border=2pt]{standalone}
\usepackage[utf8]{inputenc}
\usepackage[T2A]{fontenc}
\usepackage[russian]{babel}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{tikz}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usetikzlibrary{arrows,arrows.meta,positioning,patterns}
%(preamble)s
\begin{document}
%(body)s
\end{document}
"""

COMPILE_TIMEOUT_SEC = 10

_MIKTEX_BIN = os.path.join(
    os.path.expanduser('~'), 'AppData', 'Local', 'Programs', 'MiKTeX',
    'miktex', 'bin', 'x64')


class TikzCompileError(RuntimeError):
    """Компиляция не удалась. Карточка обязана уйти в ручной разбор —
    сырой TikZ-код читателю не показывается ни при каких условиях."""


def block_hash(tikz_source):
    """SHA-256 исходного блока. Хеш, а не счётчик: один и тот же блок не
    компилируется дважды, а правка исходника даёт новую картинку."""
    return hashlib.sha256(tikz_source.encode('utf-8')).hexdigest()


def make_marker(digest):
    return _MARKER_TEMPLATE.format(digest)


def _wrap_bare_addplot(run_text):
    """Осиротевшие команды графика → полноценная картинка.

    Реконструкция, а не догадка о смысле: сами команды не меняются, им
    возвращается обёртка, без которой они не компилируются в принципе.
    Если реконструкция неверна, компиляция упадёт и карточка уйдёт в
    ручной разбор — тихого «PASS» тут быть не может."""
    body = run_text.strip('\n')
    return ('\\begin{tikzpicture}\n\\begin{axis}[axis lines=left]\n'
            + body + '\n\\end{axis}\n\\end{tikzpicture}')


def _addplot_statement_end(text, start):
    """Индекс сразу за `;`, закрывающей одну команду графика.

    Глубина считается по квадратным и фигурным скобкам: `;` внутри
    аргумента командой не заканчивает. `-1`, если `;` нет вовсе — тогда
    блок не берётся, гадать о границе нельзя."""
    depth_sq = depth_br = 0
    i, n = start, len(text)
    while i < n:
        ch = text[i]
        if ch == '\\' and i + 1 < n:
            i += 2
            continue
        if ch == '[':
            depth_sq += 1
        elif ch == ']':
            depth_sq -= 1
        elif ch == '{':
            depth_br += 1
        elif ch == '}':
            depth_br -= 1
        elif ch == ';' and depth_sq <= 0 and depth_br <= 0:
            return i + 1
        i += 1
    return -1


def _replace_bare_addplot_runs(text, take):
    """Подряд идущие осиротевшие команды графика — в ОДНУ картинку.

    Именно подряд: две группы, разделённые обычным текстом, это два
    разных графика, склеивать их значило бы соврать о данных."""
    out = []
    pos = 0
    while True:
        match = _ADDPLOT_START_RE.search(text, pos)
        if match is None:
            break
        run_start = match.start()
        end = _addplot_statement_end(text, match.end())
        if end == -1:
            break
        while True:
            nxt = _ADDPLOT_START_RE.search(text, end)
            if nxt is None or text[end:nxt.start()].strip():
                break
            nxt_end = _addplot_statement_end(text, nxt.end())
            if nxt_end == -1:
                break
            end = nxt_end
        out.append(text[pos:run_start])
        out.append(take(_wrap_bare_addplot(text[run_start:end])))
        pos = end
    out.append(text[pos:])
    return ''.join(out)


def extract_tikz_blocks(text):
    """`(текст_с_маркерами, [(хеш, исходник_блока), ...])`.

    Чистая функция: ни базы, ни компиляции. Идемпотентна — на тексте,
    где TikZ уже заменён маркерами, находит ноль блоков."""
    if not text:
        return text, []
    blocks = []

    def take(source):
        digest = block_hash(source)
        if not any(d == digest for d, _ in blocks):
            blocks.append((digest, source))
        return make_marker(digest)

    out = _TIKZPICTURE_RE.sub(lambda m: take(m.group(0)), text)
    # Осиротевшие команды графика ищем ПОСЛЕ полных окружений: то, что
    # уже уехало в картинку, вторично захватываться не должно.
    out = _replace_bare_addplot_runs(out, take)
    return out, blocks


# ---------------------------------------------------------------------------
# Чистка SVG — второй рубеж, не единственный
# ---------------------------------------------------------------------------

#: Целиком, вместе с содержимым: внутри лежит исполняемый код или
#: внешнее содержимое, показывать которое незачем ни в каком виде.
#:
#: ⚠️ `use` здесь НЕТ, и это выяснено визуальной проверкой, а не
#: рассуждением. dvisvgm рисует каждую цифру и подпись как
#: `<use xlink:href='#g1-49'/>`, ссылаясь на `<path>` внутри `<defs>`
#: того же файла. Пока `use` вырезался, у всех 118 картинок на странице
#: предпросмотра `naturalWidth` был 0 — санитайзер «обезопасил» их до
#: полной нечитаемости. `use` — структурный элемент, ничего не
#: исполняет; опасна не он, а ссылка НАРУЖУ, и её ловит `_href_is_safe`.
_SVG_DROP_ELEMENTS = ('script', 'foreignObject', 'foreignobject',
                      'animate', 'animateTransform', 'set', 'handler',
                      'iframe', 'image')
#: `<a>` не вырезается вместе с содержимым — внутри может лежать сама
#: картинка. Снимается только сам тег, графика остаётся.
_UNWRAP_A_RE = re.compile(r'</?a\b[^>]*>', re.IGNORECASE)
#: Любой обработчик события.
_ON_ATTR_RE = re.compile(r'\son[a-zA-Z]+\s*=\s*(".*?"|\'.*?\'|[^\s>]+)',
                         re.DOTALL)
#: Ссылки. Внутренние (`#g1-49`) — законная механика SVG и остаются;
#: всё остальное снимается: `data:` тащит произвольное содержимое,
#: `javascript:` исполняется, внешний адрес выдаёт ученика третьей
#: стороне (трекинг-пиксель).
_HREF_ATTR_RE = re.compile(
    r'\s(?:xlink:href|href|src)\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)')
_STYLE_URL_RE = re.compile(r'url\s*\(\s*(?!["\']?#)[^)]*\)', re.IGNORECASE)


def _href_is_safe(raw_value):
    """Ссылка ведёт внутрь ЭТОГО же файла (`#id`) и никуда больше."""
    value = raw_value.strip().strip('"\'').strip()
    return value.startswith('#') and '\n' not in value


def _drop_element(svg, name):
    pattern = re.compile(
        r'<' + name + r'\b.*?</' + name + r'\s*>|<' + name + r'\b[^>]*/\s*>',
        re.DOTALL | re.IGNORECASE)
    return pattern.sub('', svg)


def sanitize_svg(svg):
    """Убрать из SVG всё исполняемое и всё, что тянется наружу.

    Это ВТОРОЙ рубеж, а не единственный. Первый — то, что картинка
    отдаётся браузеру тегом `<img>`: содержимое `<img>` не исполняет
    скрипты, даже если они там окажутся. Третий — заголовки ответа
    (`Content-Security-Policy: default-src 'none'`, `nosniff`) во
    `catalog.views.problem_figure_svg`. Каждый рубеж самостоятелен."""
    if not svg:
        return ''
    for name in _SVG_DROP_ELEMENTS:
        svg = _drop_element(svg, name)
    svg = _UNWRAP_A_RE.sub('', svg)
    svg = _ON_ATTR_RE.sub('', svg)
    svg = _HREF_ATTR_RE.sub(
        lambda m: m.group(0) if _href_is_safe(m.group(1)) else '', svg)
    svg = _STYLE_URL_RE.sub('', svg)
    # DOCTYPE/ENTITY — вектор XXE у некоторых парсеров; в SVG от dvisvgm
    # они не нужны.
    svg = re.sub(r'<!DOCTYPE.*?>', '', svg, flags=re.DOTALL | re.IGNORECASE)
    svg = re.sub(r'<!ENTITY.*?>', '', svg, flags=re.DOTALL | re.IGNORECASE)
    svg = re.sub(r'<\?xml-stylesheet.*?\?>', '', svg, flags=re.DOTALL)
    return svg.strip()


# ---------------------------------------------------------------------------
# Компиляция в песочнице
# ---------------------------------------------------------------------------

def _binary(name):
    candidate = os.path.join(_MIKTEX_BIN, name + '.exe')
    return candidate if os.path.exists(candidate) else name


def toolchain_available():
    """Есть ли latex и dvisvgm. Без них компиляция честно не начинается."""
    return all(shutil.which(_binary(n)) or os.path.exists(_binary(n))
               for n in ('latex', 'dvisvgm'))


def compile_tikz_to_svg(tikz_source, timeout=COMPILE_TIMEOUT_SEC,
                        preamble=''):
    """TikZ-блок → санитизированный SVG. Бросает `TikzCompileError`.

    Каждая компиляция — в собственном временном каталоге, который
    удаляется целиком, что бы ни случилось.

    `preamble` — объявления из ИСХОДНОГО проекта (\\tikzset,
    \\newcommand, \\definecolor). Без них падает всё, что
    опирается на домашние стили автора: живые отказы — `style=style1`
    и `\\circled{1}`. Песочница от этого не меняется:
    `-no-shell-escape` и `-disable-installer` остаются, а преамбула —
    такой же текст из архива, как и сам блок."""
    if not toolchain_available():
        raise TikzCompileError('latex/dvisvgm не найдены — компиляция невозможна')

    workdir = tempfile.mkdtemp(prefix='tikz_')
    try:
        tex_path = os.path.join(workdir, 'figure.tex')
        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write(_TEX_TEMPLATE % {'body': tikz_source,
                                     'preamble': preamble or ''})

        try:
            proc = subprocess.run(
                [_binary('latex'),
                 '-no-shell-escape',        # запуск команд из документа закрыт
                 '-disable-installer',      # никакой сети во время сборки
                 '-interaction=nonstopmode',
                 '-halt-on-error',
                 '-output-directory=' + workdir,
                 tex_path],
                cwd=workdir, timeout=timeout,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
        except subprocess.TimeoutExpired:
            raise TikzCompileError(
                f'компиляция не уложилась в {timeout} с — блок зациклился')

        dvi_path = os.path.join(workdir, 'figure.dvi')
        if proc.returncode != 0 or not os.path.exists(dvi_path):
            tail = (proc.stdout or b'').decode('utf-8', 'replace')[-300:]
            raise TikzCompileError('latex вернул ошибку: '
                                   + ' '.join(tail.split()))

        svg_path = os.path.join(workdir, 'figure.svg')
        try:
            svg_proc = subprocess.run(
                [_binary('dvisvgm'), '--no-fonts', '--exact-bbox',
                 '--output=' + svg_path, dvi_path],
                cwd=workdir, timeout=timeout,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
        except subprocess.TimeoutExpired:
            raise TikzCompileError(f'dvisvgm не уложился в {timeout} с')

        if svg_proc.returncode != 0 or not os.path.exists(svg_path):
            tail = (svg_proc.stdout or b'').decode('utf-8', 'replace')[-300:]
            raise TikzCompileError('dvisvgm вернул ошибку: '
                                   + ' '.join(tail.split()))

        with open(svg_path, encoding='utf-8', errors='replace') as f:
            raw_svg = f.read()
        clean = sanitize_svg(raw_svg)
        if '<svg' not in clean:
            raise TikzCompileError('после чистки SVG не осталось картинки')
        return clean
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
