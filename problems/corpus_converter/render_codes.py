# -*- coding: utf-8 -*-
r"""Коды читаемости из аудита 3 000 карточек (2026-08-29).

Шлюз `render_preflight_v2` отвечает на вопрос «разберётся ли формула».
Аудит показал, что этого мало: KaTeX принял ВСЕ 11 808 формул выборки
(ноль ошибок разбора), а нечитаемых карточек всё равно 390 из 3 000
(13,0 %). Весь остаток — выше уровня формул: потерянные рисунки, сырые
служебные фрагменты, склеенные строки, утечка решения в условие.

Здесь эти дефекты названы кодами реестра аудита и ищутся в том, что
ученик РЕАЛЬНО видит: в тексте вне формул после рендера. Смотреть на
исходный markdown нельзя — половина служебного синтаксиса до экрана не
доезжает, и проверка ловила бы призраков.

Приоритеты — из аудита. P0: задача неполна или нечитаема; P1:
существенный дефект; P2: косметика.
"""
import re
from html import unescape

BS = chr(92)

#: Приоритет каждого кода. Единый список для обеих частей работы —
#: легаси и новых источников: одно и то же не должно называться в двух
#: местах по-разному.
PRIORITY = {
    'INCOMP': 'P0', 'MISS': 'P0', 'RTAB': 'P0', 'BAD-TABLE': 'P0',
    'COLL': 'P0',
    'COMM': 'P1', 'LINK': 'P1', 'MD': 'P1', 'BOX': 'P1', 'SLASH': 'P1',
    'RAW-MATH': 'P1', 'OVER': 'P1', 'SOL': 'P1', 'BRACE': 'P1',
    'EMPTY-BLOCK': 'P1', 'SVG': 'P1',
    'EMPTY-MATH': 'P2', 'TABLE': 'P2', 'OVER-M': 'P2',
}

#: Человеческая расшифровка — для отчётов и очереди ручного разбора.
MEANING = {
    'INCOMP': 'карточка не является самостоятельной задачей',
    'MISS': 'нет обязательного рисунка/таблицы/диаграммы',
    'RTAB': 'сырая разметка таблицы или хвост документа',
    'BAD-TABLE': 'таблица структурно сломана',
    'COLL': 'строки cases/aligned/gathered склеены',
    'COMM': 'TeX-комментарий или редакторская помета видна читателю',
    'LINK': 'ссылка потеряна или показан placeholder «тык»',
    'MD': 'виден сырой Markdown/enumitem/кавычки',
    'BOX': 'виден float/tcolorbox-служебный синтаксис',
    'SLASH': 'виден служебный обратный слеш',
    'RAW-MATH': 'математика осталась обычным ASCII-текстом',
    'OVER': 'формула заведомо шире карточки',
    'SOL': 'решение попало в условие/подпункт',
    'BRACE': 'видны лишние фигурные скобки',
    'EMPTY-BLOCK': 'показан пустой именованный блок',
    'SVG': 'inline-SVG имеет конфликтующие id',
    'EMPTY-MATH': 'пустой math-фрагмент создаёт пустой отступ',
    'TABLE': 'HTML-таблица без читабельного оформления',
    'OVER-M': 'формула переполняет узкий экран',
}

# --- видимый текст ---------------------------------------------------------

_TAG_RE = re.compile(r'<[^>]+>')
_SCRIPTY_RE = re.compile(r'<(script|style)\b.*?</\1>', re.S | re.I)
#: Те же разделители и в том же порядке, что у боевого показа
#: (`templates/_katex_dollars.html`): `$$` раньше `$`, иначе первая же
#: одиночная пара съедает половину выключной формулы.
_MATH_SPANS = (
    ('$$', '$$'), (BS + '[', BS + ']'), (BS + '(', BS + ')'), ('$', '$'),
)
_ESCAPED_DOLLAR = BS + '$'
_SENTINEL = '\x00'


def visible_text(html):
    """Текст, который ученик читает ВНЕ формул.

    Формулы вырезаются: внутри них служебные символы законны, и искать
    там «лишний обратный слеш» значило бы браковать исправные задачи."""
    if not html:
        return ''
    text = _SCRIPTY_RE.sub(' ', html)
    text = _TAG_RE.sub(' ', text)
    text = unescape(text)
    text = text.replace(_ESCAPED_DOLLAR, _SENTINEL)
    out = []
    i = 0
    while i < len(text):
        span = _math_end(text, i)
        if span is None:
            out.append(text[i])
            i += 1
        else:
            i = span
    return ''.join(out).replace(_SENTINEL, '$')


def _math_end(text, i):
    for open_, close in _MATH_SPANS:
        if not text.startswith(open_, i):
            continue
        end = text.find(close, i + len(open_))
        if end == -1:
            continue
        return end + len(close)
    return None


# --- отдельные детекторы ---------------------------------------------------

#: Комментарий, доехавший до экрана. `%` перед буквой и НЕ после цифры:
#: «20 % от выручки» — обычный текст, «%нижняя огибающая» и «% бета лш
#: 57 2024» — забытая помета автора.
_COMM_RE = re.compile(r'(?<!\d)(?<!\d )%\s?[A-Za-zА-Яа-яЁё(\[]')

#: Служебный синтаксис плавающих объектов и рамок. `[htpb]` без слеша не
#: ловится ни одной проверкой на команды — у новых источников он утёк на
#: экран в 296 задачах.
_BOX_RE = re.compile(
    r'\[(?:h|H|t|b|p|!)+\]|\[colback=|\[colframe=|tcolorbox|'
    r'\[width=[0-9.]|\[breakable|\[sharp corners|'
    r'\{[0-9.]+' + re.escape(BS) + r'(?:text|line|column)width\}')

#: Сырая разметка таблицы или хвост документа.
_RTAB_RE = re.compile(
    r'p\{[0-9.]+\s*(?:cm|mm|in|pt)\}|\*\{\d+\}\{|@\{\}|'
    r'(?:^|\s)&(?:\s|$)|' + re.escape(BS) + r'(?:hline|toprule|midrule|'
    r'bottomrule|multicolumn|multirow|cline)')

#: Сырой Markdown, enumitem и незакрытые кавычки LaTeX.
_MD_RE = re.compile(
    r'<<|>>|\[label=|\[leftmargin|\[noitemsep|\[resume|\[itemsep|'
    r'(?:^|\s)\*(?:\s|$)|\*{2,}|(?:^|\s)#{1,6}\s')

#: ASCII-математика, не доехавшая до KaTeX.
_RAWMATH_RE = re.compile(
    r'\bsqrt\s*\(|=>|<=|>=|!=|(?<![-<>=])->(?![->])|'
    r'[A-Za-zА-Яа-я]\^\s*\d|\b[A-Za-z]_[A-Za-z0-9]\b')

def empty_math_spans(text):
    """Формулы без содержимого: `$$$$`, `$ $`, `\\[\\]`.

    Регуляркой это не ищется, и проверено на живых данных: `\\$\\s*\\$`
    совпадает с ОТКРЫВАЮЩИМ `$$` выключной формулы, и 46 исправных задач
    получали код на ровном месте. Разделители надо разбирать парами, как
    это делает показ."""
    if not text:
        return []
    text = text.replace(_ESCAPED_DOLLAR, _SENTINEL)
    found = []
    i = 0
    while i < len(text):
        hit = None
        for open_, close in _MATH_SPANS:
            if not text.startswith(open_, i):
                continue
            end = text.find(close, i + len(open_))
            if end == -1:
                continue
            hit = (open_, close, text[i + len(open_):end], end + len(close))
            break
        if hit is None:
            i += 1
            continue
        open_, close, body, nxt = hit
        if not body.strip():
            found.append(open_ + close)
        i = nxt
    return found

#: Многострочные окружения, где склейка строк реально видна.
_MULTILINE_ENVS = ('cases', 'aligned', 'gathered', 'align', 'split',
                   'alignat')

_LINK_RE = re.compile(r'\bтык\b|https?://|\bпо\s+ссылк', re.I)

#: Условие прямо ссылается на объект, которого может не быть.
#: Формулировки собраны по живым карточкам реестра: авторы пишут и «на
#: рисунке ниже», и «вам даны несколько графиков», и «по графику».
_NEEDS_FIGURE_RE = re.compile(
    r'на\s+рисунк|на\s+график|рисунк[еа]\s+ниже|график\s+ниже|'
    r'таблиц[аеы]\s+(?:ниже|приведена|дана|представлена)|см\.\s*рис|'
    r'рис\.\s*\d|изображен|на\s+диаграмме|на\s+картинке|'
    r'дан[ыо]?\s+(?:несколько\s+)?график|по\s+график|'
    r'график[еиа]?\s+(?:зависимост|функци|спроса|предложения)|'
    r'приведен[ыао]?\s+(?:ниже|график|диаграмм|таблиц)|'
    r'следующ[а-я]+\s+(?:график|диаграмм|таблиц|рисун)|'
    r'ниже\s+(?:приведен|изображ|представлен|дан)', re.I)

#: Ученику ВЕЛЕНО нарисовать самому — значит картинки в оригинале и не
#: было. «Покажите его на графике», «изобразите на графике излишки» —
#: `_NEEDS_FIGURE_RE` видит здесь «на график» и объявляет пропажу, хотя
#: пропадать было нечему (живые #43780 и #43791, названы владельцем).
#:
#: Ловится ИМЕННО повелительное наклонение. Страдательные и прошедшие
#: формы («на рисунке изображён», «приведён график») — наоборот, признак
#: того, что картинка была: их сюда пускать нельзя.
_DRAW_YOURSELF_RE = re.compile(
    r'(?:покажите|покажи|изобразите|изобрази|нарисуйте|нарисуй|'
    r'постройте|построй|начертите|начерти|отметьте|отметь|'
    r'проиллюстрируйте|проиллюстрируй|отобразите|отобрази)'
    r'[^.!?;]{0,120}?'
    r'(?:на\s+график|на\s+рисунк|на\s+диаграмм|на\s+чертеж|график)', re.I)

#: Твёрдый признак того, что картинка БЫЛА и потерялась: ссылка на номер
#: рисунка, «см. рис», уцелевшая команда включения картинки. При любом из
#: них поблажка «ученик рисует сам» не действует.
_FIGURE_WAS_THERE_RE = re.compile(
    r'см\.\s*рис|рис\.\s*\d|рисунк[еа]\s+ниже|график\s+ниже|'
    r'\\includegraphics|!\[|ниже\s+(?:приведен|изображ|представлен|дан)|'
    r'таблиц[аеы]\s+(?:ниже|приведена|дана|представлена)', re.I)

#: Утечка разбора в условие.
_SOL_RE = re.compile(r'(?:^|\s)(РЕШЕНИЕ|Решение:|РАЗБОР|Критерии:|КРИТЕРИИ)')

#: Обложка, шапка бланка, ключ ответов, редакторская заметка — всё, что
#: попало в банк отдельной карточкой, но задачей не является. Список
#: собран по живым карточкам реестра аудита (#3986, #5003, #5053).
_NOT_A_PROBLEM_RE = re.compile(
    r'^\s*(?:краткий\s+ответ|ответ\s*:?|критерии|решение|разбор|'
    r'стр\.?\s*\d+|см\.\s|тык|имя\s+и\s+фамилия|фамилия|класс\s*:|'
    r'вариант\s*\d*|школа\s*:|выберите\s+единственный\s+верный\s+ответ)'
    r'[\s:.\d]*$', re.I)
#: Редакторская заметка «как это делать», а не условие.
_EDITOR_NOTE_RE = re.compile(
    r'^\s*(?:а\s+)?вот\s+так\b|^\s*пример\s+(?:того|как)\b|'
    r'^\s*(?:это\s+)?шаблон\b|^\s*тут\s+(?:будет|надо)\b', re.I)
#: Ниже этого числа видимых символов условие не может быть условием.
#: 40, а не 25: «А вот так добавить картинку» — 27 символов и всё ещё не
#: задача (живая #3986).
MIN_STATEMENT = 40

_ID_RE = re.compile(r'\bid\s*=\s*"([^"]+)"')
_SVG_RE = re.compile(r'<svg\b.*?</svg>', re.S | re.I)
_TABLE_RE = re.compile(r'<table\b.*?</table>', re.S | re.I)
_ROW_RE = re.compile(r'<tr\b.*?</tr>', re.S | re.I)
_CELL_RE = re.compile(r'<t[dh]\b', re.I)


def _collapsed_environments(canonical):
    """Окружения с логическими строками, но без `\\\\` между ними."""
    hits = []
    for env in _MULTILINE_ENVS:
        pattern = re.compile(
            re.escape(BS + 'begin{' + env + '}') + r'(.*?)'
            + re.escape(BS + 'end{' + env + '}'), re.S)
        for m in pattern.finditer(canonical or ''):
            body = m.group(1)
            if BS + BS in body:
                continue
            rows = [ln for ln in body.split('\n') if ln.strip()]
            if len(rows) >= 2:
                hits.append(env)
    return hits


#: Столбик markdown-таблицы, доехавший до экрана как текст. Живые
#: #4374 и #4376: разметка `| a | b |` не собралась в таблицу, и `|`
#: остались в тексте.
#: Достаточно ОДНОЙ вертикальной черты. Вне формулы `|` в русской прозе
#: не встречается: у #4374 разметка `| a | b |` частью собралась в
#: таблицу, а частью осталась абзацем `<p>|</p>`, и двух черт подряд в
#: видимом тексте уже не было.
_PIPE_TABLE_RE = re.compile(r'\|')


def _broken_table(html):
    """Таблица со строками разной длины — её колонки не читаются."""
    for table in _TABLE_RE.findall(html or ''):
        counts = [len(_CELL_RE.findall(row)) for row in _ROW_RE.findall(table)]
        counts = [c for c in counts if c]
        if len(counts) >= 2 and len(set(counts)) > 1:
            return counts
    return None


def _duplicate_svg_ids(html):
    for svg in _SVG_RE.findall(html or ''):
        ids = _ID_RE.findall(svg)
        seen, dupes = set(), set()
        for value in ids:
            if value in seen:
                dupes.add(value)
            seen.add(value)
        if dupes:
            return sorted(dupes)[:5]
    return None


def analyze_block(name, canonical, html, seen_text=None):
    """`[(код, подробность)]` для одного блока задачи."""
    text = seen_text if seen_text is not None else visible_text(html)
    found = []

    def add(code, detail):
        found.append((code, '%s: %s' % (name, detail)))

    m = _COMM_RE.search(text)
    if m:
        add('COMM', _around(text, m.start()))
    m = _BOX_RE.search(text)
    if m:
        add('BOX', _around(text, m.start()))
    m = _RTAB_RE.search(text)
    if m:
        add('RTAB', _around(text, m.start()))
    m = _MD_RE.search(text)
    if m:
        add('MD', _around(text, m.start()))
    m = _RAWMATH_RE.search(text)
    if m:
        add('RAW-MATH', _around(text, m.start()))
    if BS in text:
        add('SLASH', _around(text, text.index(BS)))
    if '{' in text or '}' in text:
        idx = text.index('{') if '{' in text else text.index('}')
        add('BRACE', _around(text, idx))
    empties = empty_math_spans(canonical)
    if empties:
        add('EMPTY-MATH', 'пустые разделители %r' % empties[0])
    envs = _collapsed_environments(canonical)
    if envs:
        add('COLL', 'без разделителя строк: %s' % ', '.join(sorted(set(envs))))
    if _LINK_RE.search(text) and '<a' not in (html or ''):
        add('LINK', _around(text, _LINK_RE.search(text).start()))
    dupes = _duplicate_svg_ids(html)
    if dupes:
        add('SVG', 'повторяющиеся id: %s' % ', '.join(dupes))
    counts = _broken_table(html)
    if counts:
        add('BAD-TABLE', 'разное число ячеек в строках: %s' % counts)
    elif _PIPE_TABLE_RE.search(text):
        add('BAD-TABLE', 'разметка таблицы осталась текстом: %s'
            % _around(text, _PIPE_TABLE_RE.search(text).start()))
    if '<table' in (html or '') and not counts:
        add('TABLE', 'таблица без оформления (чинится шаблоном, не задачей)')
    if name.startswith(('Условие', 'Часть')) and _SOL_RE.search(text):
        add('SOL', _around(text, _SOL_RE.search(text).start()))
    return found


def _around(text, index, width=60):
    start = max(0, index - width // 3)
    return ' '.join(text[start:start + width].split())


def analyze_problem(blocks, htmls, seen_texts=None, figure_svgs=()):
    """`{код: подробность}` по всей задаче.

    `blocks` — `[(имя, исходник, канонический markdown)]`, `htmls` — их
    HTML в том же порядке. `seen_texts` можно передать из браузера: он
    считает видимый текст точнее, чем разбор строки.

    `figure_svgs` — содержимое собранных SVG. Проверять их надо ОТДЕЛЬНО,
    а не в HTML страницы: боевой показ отдаёт картинку как
    `<img src="/catalog/figure/N.svg">`, то есть отдельным документом.
    Столкнуться идентификаторами двух РАЗНЫХ картинок там физически
    негде — это дефект инструмента предпросмотра, который вклеивал SVG
    в одну страницу. А вот повторы ВНУТРИ одного SVG портят саму
    картинку, и вот их здесь и ищем."""
    found = {}
    for svg in figure_svgs or ():
        dupes = _duplicate_svg_ids(svg if '<svg' in (svg or '')
                                   else '<svg>%s</svg>' % (svg or ''))
        if dupes:
            found.setdefault(
                'SVG', 'повторяющиеся id внутри картинки: %s'
                       % ', '.join(dupes))
            break
    visible_all = []
    for i, (name, _raw, canonical) in enumerate(blocks):
        html = htmls[i] if i < len(htmls) else ''
        seen = seen_texts[i] if seen_texts and i < len(seen_texts) else None
        text = seen if seen is not None else visible_text(html)
        visible_all.append((name, text, html))
        for code, detail in analyze_block(name, canonical, html, seen):
            found.setdefault(code, detail)

    # --- дефекты уровня задачи, а не блока ------------------------------
    for name, text, html in visible_all:
        if not text.strip() and not html.strip():
            found.setdefault('EMPTY-BLOCK', '%s: пустой блок' % name)

    whole = ' '.join(t for _n, t, _h in visible_all).strip()
    body = ' '.join(h for _n, _t, h in visible_all)

    # INCOMP считается по УСЛОВИЮ и подпунктам, а не по всей карточке.
    # Иначе задача с пустым условием, но длинным разбором, выглядит
    # полноценной — а ученику показывать нечего (живая #5003).
    task_text = ' '.join(
        t for name, t, _h in visible_all
        if name.startswith(('Условие', 'Часть'))).strip()
    if (len(task_text) < MIN_STATEMENT
            or _NOT_A_PROBLEM_RE.match(task_text)
            or _EDITOR_NOTE_RE.match(task_text)):
        found.setdefault(
            'INCOMP', 'условие из %d видимых символов: %r'
                      % (len(task_text), task_text[:80]))
    if (_NEEDS_FIGURE_RE.search(whole) and not _has_object(body)
            and not _draws_it_himself(whole)):
        found.setdefault(
            'MISS', 'условие ссылается на объект, которого нет на экране')
    return found


def _draws_it_himself(text):
    """Правда ли, что рисовать велено УЧЕНИКУ, а картинки и не было.

    Условие снимает `MISS` только когда сходятся оба: есть повелительное
    «покажите/изобразите/постройте … на графике» И нет ни одного твёрдого
    признака пропавшей картинки (`см. рис`, `рис. 2`, уцелевший
    `\\includegraphics`). Сомнение трактуется в пользу дефекта: показать
    битое хуже, чем задержать хорошее."""
    if _FIGURE_WAS_THERE_RE.search(text):
        return False
    return bool(_DRAW_YOURSELF_RE.search(text))


def _has_object(html):
    """Есть ли на экране то, на что можно сослаться словом «рисунок»."""
    lowered = (html or '').lower()
    return ('<img' in lowered or '<svg' in lowered or '<table' in lowered
            or '[[figure:' in lowered)
