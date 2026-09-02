# -*- coding: utf-8 -*-
"""«Текст задачи» — одно определение, общее для Б1 (частоты) и Б2 (пилот).

Условие + подпункты, без обрезки. Здесь же живёт эвристика «английский
текст» — единственного признака стратификации выборки Б2, для которого в
базе нет своего поля (docs/TAXONOMY.md §7: «на английском» вычисляется
кодом по доле кириллицы).
"""
import re

from problems.templatetags.ru import pick

_CYRILLIC_RE = re.compile(r'[а-яёА-ЯЁ]')
_LATIN_RE = re.compile(r'[a-zA-Z]')

# Порог для эвристики английского текста — см. is_english_text().
MIN_LATIN_LETTERS = 30


def problem_full_text(statement, parts):
    """`parts` — итерируемое объектов с атрибутами `label` и `statement`
    (подходят и `ProblemPart`, и любой объект/namedtuple с теми же полями).
    """
    pieces = [statement or '']
    for part in parts:
        label = getattr(part, 'label', '') or ''
        part_statement = (getattr(part, 'statement', '') or '').strip()
        if not part_statement:
            continue
        pieces.append('(%s) %s' % (label, part_statement) if label
                      else part_statement)
    return '\n'.join(pieces)


# «График в условии» / «Табличка в условии» — особенности 11 и 12 из
# docs/TAXONOMY.md §7. Модель картинку не видит и таблицу распознаёт хуже
# регулярки — обе считаются кодом, а не спрашиваются у модели.
_GRAPH_MARKER_RE = re.compile(r'\[\[FIGURE:|\\begin\{tikzpicture\}')
_TABLE_MARKER_RE = re.compile(
    r'\\begin\{tabular\}|\\begin\{array\}|\\begin\{table\}|<table', re.IGNORECASE)


def has_graph_in_statement(text, has_problem_figure=False):
    """«График в условии» (docs/TAXONOMY.md §7, особенность 11).

    `has_problem_figure` — есть ли у задачи строка `ProblemFigure`; сюда
    передаётся вызывающим кодом, т.к. эта функция работает с голым текстом
    и к БД не обращается. Считается истиной ещё и по маркеру `[[FIGURE:`
    или сырому `tikzpicture`-блоку в тексте (задача до сборки ассета).
    """
    if has_problem_figure:
        return True
    return bool(_GRAPH_MARKER_RE.search(text or ''))


def has_table_in_statement(text):
    """«Табличка в условии» (docs/TAXONOMY.md §7, особенность 12).

    LaTeX-окружения `tabular`/`array`/`table`, HTML `<table`, либо
    markdown-таблица (строка с двумя и более символами `|`).
    """
    text = text or ''
    if _TABLE_MARKER_RE.search(text):
        return True
    return any(line.count('|') >= 2 for line in text.splitlines())


_FIGURE_MARKER_ONLY_RE = re.compile(r'\[\[FIGURE:')


def with_figure_note(text, figure_count):
    """Служебная строка `[[FIGURE: к задаче приложено N изображений]]` в
    КОНЦЕ payload — только если у задачи есть строки `ProblemFigure`
    (`figure_count > 0`), а в самом тексте нет ни одного маркера
    `[[FIGURE:` (Фаза 2, 2026-09-01: 732 задачи, 28% визуального
    множества, без этой строки модель видит «на рисунке…» без единого
    сигнала, что рисунок вообще есть).

    Правит только то, что уходит в API — `statement`/`ProblemPart.statement`
    в базе не трогает ни на байт.
    """
    if figure_count <= 0 or _FIGURE_MARKER_ONLY_RE.search(text or ''):
        return text
    note = '[[FIGURE: к задаче приложено %d %s]]' % (
        figure_count,
        pick(figure_count, 'изображение', 'изображения', 'изображений'))
    return '%s\n%s' % (text or '', note)


def is_english_text(text):
    """Эвристика, а не поле в базе — такого поля у `Problem` нет вовсе.

    Английский, если латиницы заметно (>= MIN_LATIN_LETTERS) и кириллицы
    почти нет (не больше десятой доли латиницы). Не претендует на
    лингвистическую точность — годится ровно для стратификации выборки
    пилота, не для продуктовой разметки.
    """
    text = text or ''
    latin = len(_LATIN_RE.findall(text))
    cyrillic = len(_CYRILLIC_RE.findall(text))
    if latin < MIN_LATIN_LETTERS:
        return False
    return cyrillic <= latin * 0.1


# ---------------------------------------------------------------------------
# §3.5 API_RUN_MASTER: исходник чертежа уходит в вызов 1 текстом
# ---------------------------------------------------------------------------
#
# ⚠️ `ProblemFigure.tikz_source` хранит ДВЕ РАЗНЫЕ ВЕЩИ (см. докстринг модели,
# problems/models.py): у сгенерированных из TikZ там код чертежа, а у
# импортированных растровых картинок — ССЫЛКА НА ФАЙЛ. В банке на 02.09.2026
# из 2 498 записей кодом чертежа заняты 7, ссылкой — 2 491. Поэтому критерий
# «tikz_source непустой» НЕ отделяет чертёж от картинки (он истинен для всех
# 2 498), и подставлять надо только то, что действительно похоже на TikZ:
# ссылка «https://…/file-2024-08-21.png» под заголовком «читай как описание
# графика» была бы прямым враньём модели.

#: Потолок из §3.5. Длиннее — обрезаем и говорим об этом модели.
TIKZ_MAX_TOKENS = 800

_TIKZ_CODE_RE = re.compile(
    r'\\begin\{tikzpicture\}|\\begin\{axis\}|\\addplot|\\draw\b|\\pgfplots')
_FIGURE_HASH_MARKER_TEMPLATE = '[[FIGURE:%s]]'

_TIKZ_HEADER = (
    '[[ЧЕРТЁЖ К ЗАДАЧЕ. Ниже — исходный код TikZ этого рисунка. Читай его '
    'как ОПИСАНИЕ ГРАФИКА: какие оси, что на них отложено, где подписи, '
    'какие линии проведены и где они пересекаются. Это рисунок, который '
    'видит ученик, а не формула для вычислений.')
_TIKZ_FOOTER = 'КОНЕЦ ЧЕРТЕЖА]]'
_TIKZ_CUT_NOTE = '[…ЧЕРТЁЖ ОБРЕЗАН ПО ПОТОЛКУ %d ТОКЕНОВ из %d…]'


def looks_like_tikz(source):
    """Правда ли в `tikz_source` код чертежа, а не ссылка на файл."""
    return bool(_TIKZ_CODE_RE.search(source or ''))


def count_tokens(text):
    """Токены по `tiktoken` (кодировка `o200k_base`, семейство GPT-5), а без
    неё — по приближению «4 символа на токен», тому же, что уже живёт в
    `problems/ai/providers.py`.

    Мягкий импорт, а не жёсткий: `tiktoken` стоит только в локальном
    окружении (`requirements/local.in` тянет `openai`), в боевом образе его
    нет. Жёсткий импорт уронил бы сбор management-команд на проде ради
    подсчёта, который нужен одному пилоту.
    """
    try:
        import tiktoken
    except ImportError:
        return len(text or '') // 4
    return len(tiktoken.get_encoding('o200k_base').encode(text or ''))


def truncate_to_tokens(source, max_tokens):
    """`(текст, обрезали ли)`. Обрезка идёт по токенам, а не по символам:
    потолок в §3.5 задан в токенах, и на LaTeX символы к токенам не сводятся."""
    try:
        import tiktoken
    except ImportError:
        limit = max_tokens * 4
        if len(source) <= limit:
            return source, False
        return source[:limit], True
    enc = tiktoken.get_encoding('o200k_base')
    pieces = enc.encode(source)
    if len(pieces) <= max_tokens:
        return source, False
    return enc.decode(pieces[:max_tokens]), True


def with_tikz_sources(text, figures, max_tokens=TIKZ_MAX_TOKENS):
    """Маркер `[[FIGURE:<хеш>]]` заменяется исходником чертежа в обёртке
    «читай как описание графика» — §3.5 API_RUN_MASTER.

    `figures` — итерируемое объектов с `tikz_hash` и `tikz_source`
    (`ProblemFigure` или любой объект с теми же полями). База НЕ трогается:
    функция правит только строку, которая уйдёт в API.

    Возвращает `(текст, статистика)`, где статистика —
    `{'replaced': сколько чертежей подставлено,
      'truncated': сколько из них обрезано по потолку}`.

    Три правила, каждое со своим тестом:

    * подставляется ТОЛЬКО настоящий TikZ (`looks_like_tikz`) и ТОЛЬКО там,
      где в тексте есть маркер этого чертежа. Нет маркера — ничего не
      дописываем: за такие задачи отвечает `with_figure_note`, и порядок
      важен — сначала она, потом эта функция, иначе съеденный маркер
      заставил бы её приписать лишнее «приложено N изображений»;
    * длиннее `max_tokens` — обрезаем и ГОВОРИМ об этом прямо в тексте, а не
      молча;
    * один чертёж подставляется ОДИН раз: если тот же маркер стоит в тексте
      дважды, исходник встанет на место первого вхождения, остальные
      останутся маркерами. Дублировать 800 токенов LaTeX за деньги незачем.
    """
    text = text or ''
    replaced = 0
    truncated = 0
    for figure in figures:
        source = (getattr(figure, 'tikz_source', '') or '').strip()
        if not looks_like_tikz(source):
            continue
        marker = _FIGURE_HASH_MARKER_TEMPLATE % getattr(figure, 'tikz_hash', '')
        if marker not in text:
            continue
        body, was_cut = truncate_to_tokens(source, max_tokens)
        block = [_TIKZ_HEADER, body]
        if was_cut:
            block.append(_TIKZ_CUT_NOTE % (max_tokens, count_tokens(source)))
            truncated += 1
        block.append(_TIKZ_FOOTER)
        text = text.replace(marker, '\n'.join(block), 1)
        replaced += 1
    return text, {'replaced': replaced, 'truncated': truncated}
