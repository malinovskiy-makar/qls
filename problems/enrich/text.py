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


def graphical_solution_signal(problem):
    """Код-признак §6.2 / 0-бис.3: у задачи есть `ProblemFigure`,
    привязанная к РЕШЕНИЮ (`source_field='solution'`).

    Особенность «Графическое решение» определена через solution
    («решение по существу опирается на построение или чтение графика»),
    но спрашивается у модели в вызове 1. Текст решения туда подаётся
    (Фаза 1, 2026-09-04, реверс §3.4), а вот САМА КАРТИНКА решения — нет:
    `images_for_call1`/`with_tikz_sources` берут только `source_field` из
    `RASTER_CALL1_SOURCE_FIELDS` («import», «statement»), «solution» там
    нет и не было — прямое доказательство графиком физически не может
    дойти до модели, только текстовое описание, если оно есть в решении.
    Картинка у УСЛОВИЯ (`statement`/`import`) сюда не считается: она
    доказывает другое — что график есть в условии, а не в решении.
    """
    return problem.figures.filter(source_field='solution').exists()


def merge_graphical_solution(features_1, problem):
    """`(итог, источник)` — особенность «графическое_решение» объединена
    по ИЛИ с `graphical_solution_signal`. `источник` — 'model' / 'code' /
    'both' / 'none', нужен для разбивки инварианта («сколько от модели,
    сколько добавил код, сколько совпало»)."""
    from_model = 'графическое_решение' in (features_1 or [])
    from_code = graphical_solution_signal(problem)
    if from_model and from_code:
        source = 'both'
    elif from_model:
        source = 'model'
    elif from_code:
        source = 'code'
    else:
        source = 'none'
    return (from_model or from_code), source


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



# ---------------------------------------------------------------------------
# Фаза 0.4 (подготовка боевого прогона, 02.09.2026): растровая картинка
# уходит В ВЫЗОВ 1 КАРТИНКОЙ — вслед за подтверждённым фактом, что
# GLM-5.3-Flash её читает (проверено реальным вызовом, токены изображения
# в usage ненулевые). Чертёж-TikZ (`looks_like_tikz`) уже ушёл текстом
# через `with_tikz_sources` — картинкой его дублировать не за чем.
# ---------------------------------------------------------------------------

#: Картинка относится к УСЛОВИЮ — только эти `source_field` идут в вызов 1.
#: `solution` тоже бывает у ProblemFigure — ТЕКСТ решения с Фазы 1
#: (2026-09-04, реверс §3.4 API_RUN_MASTER) в вызов 1 подаётся, а вот
#: картинка решения — по-прежнему нет, для понимания УСЛОВИЯ она бесполезна
#: (расширение на картинку решения — отдельное решение, не эта фаза).
RASTER_CALL1_SOURCE_FIELDS = ('import', 'statement')

#: Форматы, которые принимает `GLMProvider`/`OpenAIProvider` без конверсии.
NATIVE_IMAGE_TYPES = ('image/png', 'image/jpeg')

#: Длинная сторона и потолок байт после сжатия — ориентир, а не измеренный
#: лимит Z.AI (в документации не опубликован). Выбран с запасом: типичные
#: multimodal-эндпоинты сжимают/режут крупнее этого сами, а картинки корпуса
#: (медиана заметно меньше) под потолок почти никогда не попадают.
MAX_IMAGE_LONG_SIDE = 2048
MAX_IMAGE_BYTES = 5_000_000


def prepare_raster_image(content_type, data,
                         max_long_side=MAX_IMAGE_LONG_SIDE,
                         max_bytes=MAX_IMAGE_BYTES):
    """`(content_type, bytes, статистика)` — картинка, готовая к отправке.

    Конвертирует не-PNG/JPEG в PNG (GIF, BMP — 5 записей в банке на
    02.09.2026), уменьшает по длинной стороне, если она больше
    `max_long_side`, либо байт больше `max_bytes`. Оригинал в базе не
    трогает — работает с байтами, переданными в память.

    Статистика: `{'converted': bool, 'resized': bool}` — печатается в
    отчёте Фазы 0, чтобы не молчать о том, скольких картинок это коснулось.
    """
    from PIL import Image
    import io

    stats = {'converted': False, 'resized': False}
    needs_convert = content_type not in NATIVE_IMAGE_TYPES

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()  # ⚠️ Image.open ленивый — распознаёт заголовок, но
            # не тело; без .load() усечённый/битый файл проходит эту
            # проверку и падает позже, уже за пределами try. Тест на это
            # есть отдельно (b'...not-a-real-png').
            if not needs_convert and len(data) <= max_bytes and max(img.size) <= max_long_side:
                return content_type, data, stats

            img = img.convert('RGB') if img.mode not in ('RGB', 'RGBA') else img
            if max(img.size) > max_long_side:
                ratio = max_long_side / max(img.size)
                new_size = (max(1, int(img.width * ratio)),
                           max(1, int(img.height * ratio)))
                img = img.resize(new_size, Image.LANCZOS)
                stats['resized'] = True

            out = io.BytesIO()
            fmt = 'JPEG' if content_type == 'image/jpeg' and not needs_convert else 'PNG'
            if fmt == 'JPEG':
                img.save(out, format='JPEG', quality=90)
                new_type = 'image/jpeg'
            else:
                img.save(out, format='PNG')
                new_type = 'image/png'
            if needs_convert:
                stats['converted'] = True

            new_bytes = out.getvalue()
            if len(new_bytes) > max_bytes and not stats['resized']:
                # Ещё слишком тяжёлая (например огромный PNG без лишних
                # пикселей) — жмём по длинной стороне жёстче одним шагом,
                # не гоняясь за точным байтовым потолком итеративно.
                ratio = 0.7
                new_size = (max(1, int(img.width * ratio)),
                           max(1, int(img.height * ratio)))
                img = img.resize(new_size, Image.LANCZOS)
                stats['resized'] = True
                out = io.BytesIO()
                img.save(out, format='JPEG' if fmt == 'JPEG' else 'PNG',
                         **({'quality': 85} if fmt == 'JPEG' else {}))
                new_bytes = out.getvalue()
            return new_type, new_bytes, stats
    except Exception:
        # Битый/нераспознанный файл — не роняем прогон, картинку просто
        # не отправляем (вызывающий код увидит это по пустому результату
        # и учтёт в очереди на ручной разбор).
        return content_type, b'', stats


def images_for_call1(figures):
    """`[(content_type, bytes), ...]` — растровые картинки вызова 1.

    Только `source_field` из `RASTER_CALL1_SOURCE_FIELDS` и только НЕ
    настоящий TikZ (тот уже ушёл текстом — см. докстринг `with_tikz_sources`,
    дважды за один чертёж не платим). Битые/пустые байты и неудачная
    конверсия дают пустую строку из `prepare_raster_image` — такая картинка
    в список не попадает.
    """
    out = []
    for figure in figures:
        if getattr(figure, 'source_field', '') not in RASTER_CALL1_SOURCE_FIELDS:
            continue
        if looks_like_tikz(getattr(figure, 'tikz_source', '') or ''):
            continue
        data = getattr(figure, 'image_data', None)
        content_type = getattr(figure, 'content_type', '') or ''
        if not data:
            continue
        new_type, new_data, _stats = prepare_raster_image(content_type, bytes(data))
        if not new_data:
            continue
        out.append((new_type, new_data))
    return out


# ---------------------------------------------------------------------------
# Фаза 1 (2026-09-04, реверс §3.4 API_RUN_MASTER): решение подаётся в вызов
# 1 как подсказка об аппарате. Прежний запрет был посчитан по цене Terra
# ($2/млн) — на GLM-5.3-Flash те же ~115 токенов на задачу стоят на порядок
# дешевле, а решение показывает, каким аппаратом задача берётся, — ровно то,
# что спрашивают теги/понятия/особенности. Риск: модель может переписать в
# `given`/`find` то, что ВЫВЕДЕНО в решении, а не то, что дано/спрошено в
# условии. Общий запрет цифр в этих полях (§12.3, `pilot_enrich_v2.
# validate_call1`) уже ловит это структурно; защитная формулировка ниже —
# вторая линия для случаев без цифр (например текстовый вывод).
# ---------------------------------------------------------------------------

#: Потолок решения в вызове 1 — тот же порядок, что у чертежа (§3.5).
SOLUTION_MAX_TOKENS = 800

_SOLUTION_HEADER = (
    '[[РЕШЕНИЕ ЗАДАЧИ — ТОЛЬКО КАК ПОДСКАЗКА ОБ АППАРАТЕ.\n'
    'Решение дано тебе как подсказка о том, каким аппаратом задача решается.\n'
    'Оно нужно для тегов, понятий и особенностей — и только для них.\n'
    '`given` перечисляет то, что задано В УСЛОВИИ. Величина, выведенная\n'
    'в решении, в `given` не попадает никогда.\n'
    '`find` описывает, что ТРЕБУЕТСЯ найти, а не что найдено. Ответ, значение\n'
    'и вывод решения в `find` не попадают никогда.')
_SOLUTION_FOOTER = 'КОНЕЦ РЕШЕНИЯ]]'
_SOLUTION_CUT_NOTE = '[…РЕШЕНИЕ ОБРЕЗАНО ПО ПОТОЛКУ %d ТОКЕНОВ из %d…]'


def solution_hint_for_call1(solution, max_tokens=SOLUTION_MAX_TOKENS):
    """`(блок_или_None, статистика)` для вызова 1.

    Решения нет — блок не строится вовсе (`None`, а не пустая строка в
    промпте). Есть — оборачивается защитной формулировкой (см. модуль
    выше) и обрезается по потолку токенов, как чертёж в `with_tikz_sources`.

    Статистика — `{'sent': bool, 'tokens': int, 'truncated': bool}`,
    `tokens` — число токенов ИТОГОВОГО (возможно обрезанного) блока целиком
    — печатается в отчёте боевого прогона (Фаза 6 задания сессии)."""
    solution = (solution or '').strip()
    if not solution:
        return None, {'sent': False, 'tokens': 0, 'truncated': False}
    body, was_cut = truncate_to_tokens(solution, max_tokens)
    block = [_SOLUTION_HEADER, '', body]
    if was_cut:
        block.append(_SOLUTION_CUT_NOTE % (max_tokens, count_tokens(solution)))
    block.append(_SOLUTION_FOOTER)
    text_block = '\n'.join(block)
    return text_block, {
        'sent': True,
        'tokens': count_tokens(text_block),
        'truncated': was_cut,
    }


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
