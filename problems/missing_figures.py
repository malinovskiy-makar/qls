"""Поиск задач, которые ссылаются на картинку, которой у нас нет.

Зачем. Решение владельца от 2026-08-24: задача с текстом «см. рисунок» без
самого рисунка не даёт пользователю решить задачу и выглядит как брак сайта.
Такие задачи скрываем (``status='hidden'``), пока для них не подберут файл.

Два независимых детектора:

* **Метод А — явная разметка.** Markdown ``![](...)``, LaTeX
  ``\\includegraphics{...}``, HTML ``<img>``, голый URL на файл картинки.
  Ловит источники, где картинка была настоящей ссылкой.
* **Метод Б — словесная отсылка.** Текст ссылается на приложенное
  изображение словами: «см. рисунок», «на графике ниже», «Figure 1».
  Нужен для источников вроде AP Economics, которые перебивали из PDF
  руками, — там машинной разметки нет вообще.

⚠️ Главная ловушка метода Б. Слово «график» в экономических текстах почти
всегда — обычный термин, а не отсылка к вложенной картинке: «постройте
график спроса», «на графике функции предложения». Поэтому каждый паттерн
метода Б обязан требовать **указатель на конкретное изображение**: «ниже»,
«выше», номер, «см.», «приведённом». Голого слова «график» недостаточно.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Метод А — явная разметка картинки
# ---------------------------------------------------------------------------

#: Расширения файлов, которые считаем картинкой в голом URL.
IMAGE_EXTENSIONS = ('png', 'jpg', 'jpeg', 'gif', 'svg', 'bmp', 'webp',
                    'tif', 'tiff', 'ico', 'avif')

_EXT_ALTERNATION = '|'.join(IMAGE_EXTENSIONS)

METHOD_A_PATTERNS: dict[str, re.Pattern[str]] = {
    # ![подпись](адрес) — markdown-картинка (SolveHub и всё markdown-семейство)
    'markdown': re.compile(r'!\[[^\]\n]*\]\([^)\n]*\)'),
    # \includegraphics[опции]{файл} — LaTeX (Школково, ЛЭШ Гамма)
    'includegraphics': re.compile(r'\\includegraphics\b'),
    # <img ...> — HTML
    'html_img': re.compile(r'<img[\s/>]', re.IGNORECASE),
    # Голый адрес, который заканчивается файлом картинки. Хвост ?query и
    # #anchor допускаем: без него не поймать ссылки с параметрами CDN.
    'bare_url': re.compile(
        r'(?:https?://|www\.)\S*?\.(?:' + _EXT_ALTERNATION + r')\b',
        re.IGNORECASE),
}


def method_a_hits(text: str) -> dict[str, int]:
    """Сколько раз каждый вид явной разметки картинки встретился в тексте."""
    if not text:
        return {}
    hits = {}
    for name, pattern in METHOD_A_PATTERNS.items():
        found = len(pattern.findall(text))
        if found:
            hits[name] = found
    return hits


def has_explicit_image_markup(text: str) -> bool:
    """Есть ли в тексте явная разметка картинки (метод А)."""
    return bool(method_a_hits(text))


# ---------------------------------------------------------------------------
# Метод Б — словесная отсылка к приложенному изображению
# ---------------------------------------------------------------------------

# Русские слова-носители изображения. «Таблица» сюда НЕ входит: таблица в
# наших источниках живёт текстом внутри условия, а не отдельным файлом.
_RU_VISUAL = (r'(?:рисунк\w*|рис\.|рисунок|график\w*|диаграмм\w*|схем\w*|'
              r'черт[ёе]ж\w*|чертеж\w*)')
_EN_VISUAL = r'(?:figure|fig\.|graph|diagram|chart|exhibit|picture|image)'

#: То же без «схемы». «Схема» в экономических условиях чаще всего означает
#: порядок действий, а не чертёж: «взял кредит по следующей схеме» (задача
#: 33568) — ручная выборка поймала ровно этот случай. Там, где рядом стоит
#: жёсткий указатель («на схеме ниже»), «схема» остаётся в _RU_VISUAL.
_RU_VISUAL_NO_SCHEME = (r'(?:рисунк\w*|рис\.|рисунок|график\w*|диаграмм\w*|'
                        r'черт[ёе]ж\w*|чертеж\w*)')

#: Предлоги, после которых носитель изображения читается как «вот эта
#: картинка», а не как абстрактный термин.
_RU_PREP = r'(?:на|в|по|под|над|из|с|со)'

#: Указатели, которые превращают общее слово «график» в отсылку к картинке.
#: Каждый паттерн обязан содержать хотя бы один такой указатель.
METHOD_B_PATTERNS: dict[str, re.Pattern[str]] = {
    # «см. рис. 2», «см. рисунок», «смотри на графике».
    # ⚠️ Граница слова слева обязательна: без неё «Рассмотрим график»
    # содержит «смотрим график» и уезжает в ложные срабатывания
    # (задача 52561, найдена ручной выборкой).
    'ru_see': re.compile(
        r'\b(?:см\.|см\b|смотри\w*|посмотри\w*)\s*(?:на\s+|в\s+)?' + _RU_VISUAL,
        re.IGNORECASE),
    # «рис. 3», «рисунок 1», «на рисунке 2» — носитель с НОМЕРОМ.
    # «Схема 1 / Схема 2» сюда НЕ входит: у задачи 3519 это два варианта
    # выплаты приза, а не два чертежа (найдено ручной выборкой).
    'ru_numbered': re.compile(
        r'(?:рис\.\s*|рисунк\w*\s+|рисунок\s+|график\w*\s+|диаграмм\w*\s+)'
        r'(?:№\s*)?\d{1,2}\b',
        re.IGNORECASE),
    # «на рисунке ниже», «на графике выше», «на диаграмме справа»
    'ru_deictic': re.compile(
        _RU_PREP + r'\s+(?:\w+\s+){0,2}?' + _RU_VISUAL +
        r'\s*(?:ниже|выше|справа|слева|далее)\b',
        re.IGNORECASE),
    # «на приведённом рисунке», «из приведённых ниже графиков», «на данной
    # диаграмме». Указатель («ниже»/«выше») может стоять и между
    # прилагательным и существительным — «приведённых ниже графиков», —
    # поэтому в середине разрешена одна необязательная позиция.
    'ru_pointed': re.compile(
        _RU_PREP + r'\s+(?:как\w+\s+из\s+|котор\w+\s+из\s+)?'
        r'(?:приведённ\w+|привед[её]нн\w+|изображённ\w+|'
        r'изображ[ёе]нн\w+|представленн\w+|показанн\w+|следующ\w+|'
        r'нижеприведённ\w+|нижепривед[её]нн\w+|указанн\w+|'
        r'построенн\w+|данн\w+|рассматриваем\w+)\s+(?:ниже\s+|выше\s+)?' +
        _RU_VISUAL_NO_SCHEME,
        re.IGNORECASE),
    # «изображён на рисунке», «представлен на графике», «показано на схеме»
    'ru_depicted': re.compile(
        r'(?:изображен\w*|изображ[ёе]н\w*|представлен\w*|показан\w*|'
        r'приведен\w*|привед[ёе]н\w*|отражен\w*|отраж[ёе]н\w*)\s+'
        r'(?:на|в)\s+' + _RU_VISUAL,
        re.IGNORECASE),
    # «по рисунку определите», «пользуясь графиком ниже» — уже покрыто выше,
    # здесь отдельный случай «по рисунку» без указателя: «рисунок» сам по
    # себе всегда означает вложение, в отличие от «графика».
    'ru_figure_word': re.compile(
        r'(?:на|по|в|под|над|из)\s+рисунк\w+', re.IGNORECASE),
    # Figure 1, Fig. 2, Graph 3, Exhibit A
    'en_numbered': re.compile(
        r'\b' + _EN_VISUAL + r'\s*(?:no\.\s*)?[\d]{1,2}\b', re.IGNORECASE),
    # the graph below, in the figure above, diagram below
    'en_deictic': re.compile(
        r'\b(?:the|this|following|accompanying)\s+' + _EN_VISUAL +
        r'\s+(?:below|above|shown|provided)\b', re.IGNORECASE),
    # see the graph, refer to the diagram, based on the figure
    'en_see': re.compile(
        r'\b(?:see|refer\s+to|according\s+to|based\s+on|use|using|'
        r'consider|examine)\s+the\s+' + _EN_VISUAL + r'\b', re.IGNORECASE),
    # shown in the graph, depicted in the figure, presented in the diagram
    'en_shown_in': re.compile(
        r'\b(?:shown|depicted|presented|illustrated|displayed|given)\s+'
        r'in\s+the\s+' + _EN_VISUAL + r'\b', re.IGNORECASE),
}

#: Формулировки, которые выглядят как отсылка, но ей не являются: это
#: ЗАДАНИЕ ученику нарисовать график самому. Атлас насчитал их сотнями
#: (Archive 3 — 373, ILE — 388, МатЭк — 403), и смешивать их с потерянными
#: картинками нельзя.
METHOD_B_EXCLUSIONS: tuple[re.Pattern[str], ...] = (
    # «постройте график ниже приведённых функций» — задание, а не отсылка
    re.compile(r'(?:постро\w+|изобраз\w+|начерт\w+|нарису\w+|отобраз\w+)\s+'
               r'(?:\w+\s+){0,2}?' + _RU_VISUAL, re.IGNORECASE),
    re.compile(r'\b(?:draw|sketch|plot|construct|graph)\s+(?:a|an|the)\s+' +
               _EN_VISUAL, re.IGNORECASE),
    # «укажите на рисунках координаты», «отметьте на графике выручки» —
    # ученик рисует сам и сам же помечает (задача 30335).
    re.compile(r'(?:укажите|укажи|отметьте|отметь|покажите|покажи|обозначьте)\s+'
               r'(?:на|в)\s+' + _RU_VISUAL, re.IGNORECASE),
    # «посмотрите на график, который вы построили в предыдущем пункте» —
    # это график САМОГО УЧЕНИКА, а не потерянное вложение (задача 2490).
    re.compile(_RU_VISUAL + r'[,\s]+котор\w+\s+(?:вы|ты)\s+'
               r'(?:построил|начертил|нарисовал|получил)\w*', re.IGNORECASE),
)

#: «Рисунок» как единица измерения текста, а не картинка — ложный друг
#: паттерна ``ru_numbered``: «график 1-го порядка» и подобное.
_NUMBERED_FALSE_FRIENDS = re.compile(
    r'график\w*\s+\d+[-\s]?(?:го|й|м|ой|ом)\b', re.IGNORECASE)


def method_b_hits(text: str) -> dict[str, list[str]]:
    """Совпадения метода Б по видам паттернов.

    Возвращает ``{имя_паттерна: [найденные куски текста]}``. Пустой словарь
    означает «отсылки к вложенной картинке не найдено».

    Отсекание ложных срабатываний идёт в два шага: сперва вырезаем из текста
    формулировки-задания («постройте график»), потом ищем отсылки в том, что
    осталось. Так «постройте график спроса» не превращается в «потерянную
    картинку», а «постройте график по данным рисунка 2» — превращается,
    потому что отсылка стоит вне вырезанного куска.
    """
    if not text:
        return {}
    cleaned = text
    for pattern in METHOD_B_EXCLUSIONS:
        cleaned = pattern.sub(' ', cleaned)
    cleaned = _NUMBERED_FALSE_FRIENDS.sub(' ', cleaned)

    hits: dict[str, list[str]] = {}
    for name, pattern in METHOD_B_PATTERNS.items():
        found = pattern.findall(cleaned)
        if found:
            hits[name] = found
    return hits


def references_missing_figure(text: str) -> bool:
    """Ссылается ли текст на приложенное изображение словами (метод Б)."""
    return bool(method_b_hits(text))


# ---------------------------------------------------------------------------
# Критичность: можно ли решить задачу без картинки
# ---------------------------------------------------------------------------

#: Числа в условии. Два вычета, оба найдены ручной выборкой:
#: * год (4 цифры) — «2015)» стоит префиксом у 248 задач Archive 3 и данными
#:   не является (атлас, §Archive 3);
#: * цифра, приклеенная к букве, — это ПОДПИСЬ НА ПОТЕРЯННОМ ГРАФИКЕ, а не
#:   данные: «Output Q1, Price P4», «S1, S2 и S3 — площади». Без этого вычета
#:   тестовые вопросы с вариантами-подписями считались «решаемыми без
#:   картинки», хотя решить их нельзя вообще никак (задачи 48310, 48483).
_NUMBER = re.compile(r'(?<![\w.,])\d{1,3}(?:[.,]\d+)?(?![\w])')
#: Признаки того, что данные лежат в самом тексте: формула, функция, таблица.
_FORMULA_HINTS = (
    re.compile(r'[QPYCTS]\s*[dsвнп]?\s*=', re.IGNORECASE),   # Qd = 100 - 2P
    re.compile(r'\\begin\{(?:tabular|array|matrix)'),         # таблица
    re.compile(r'^\s*\|.*\|', re.MULTILINE),                  # markdown-таблица
)


def has_own_data(text: str, *, min_numbers: int = 3) -> bool:
    """Хватает ли текста, чтобы решить задачу без картинки.

    Грубая, намеренно снисходительная оценка: если в условии есть формула,
    таблица или хотя бы ``min_numbers`` чисел — считаем, что картинка была
    иллюстрацией, а не единственным носителем данных. Ошибаемся в сторону
    «не скрывать»: задержать показ рабочей задачи хуже, чем показать
    сломанную, только когда речь о браке; здесь наоборот — лишнее скрытие
    прячет годную задачу.
    """
    if not text:
        return False
    for hint in _FORMULA_HINTS:
        if hint.search(text):
            return True
    return len(_NUMBER.findall(text)) >= min_numbers


# ---------------------------------------------------------------------------
# Сканирование банка
# ---------------------------------------------------------------------------

#: Слаг тега, которым помечаем задачи, скрытые из-за пропавшей картинки.
#: По нему Фаза «сопоставить картинки» найдёт их одним запросом:
#: ``Problem.objects.filter(tags__slug='missing-figure')``.
MISSING_FIGURE_TAG_SLUG = 'missing-figure'
MISSING_FIGURE_TAG_NAME = 'нет картинки'


def scan_problems(queryset=None):
    """Пройти по банку и найти задачи, ссылающиеся на недоступную картинку.

    Возвращает словарь ``{problem_id: находка}``, где находка — словарь с
    ключами ``source``, ``status``, ``method_a``, ``method_b_statement``,
    ``method_b_solution``, ``has_data``.

    Условие и решение разделены намеренно. Отсылка в УСЛОВИИ означает, что
    задачу нельзя решить; отсылка только в РЕШЕНИИ означает, что потеряна
    иллюстрация к разбору — это брак, но задача остаётся решаемой, и
    прятать её из-за этого нельзя.

    ⚠️ Задачи, у которых есть привязанные файлы (``Problem.files``), из
    выборки исключаются: картинка у них на месте, ссылка не битая.
    """
    from collections import defaultdict

    from problems.models import Problem, ProblemPart, SourceReference

    if queryset is None:
        queryset = Problem.objects.all()
    ids = set(queryset.values_list('id', flat=True))

    source_of = {}
    for pid, name in SourceReference.objects.values_list(
            'problem_id', 'source__name').iterator(chunk_size=5000):
        source_of.setdefault(pid, name)

    part_text = defaultdict(list)
    for pid, statement in ProblemPart.objects.values_list(
            'problem_id', 'statement').iterator(chunk_size=5000):
        if statement:
            part_text[pid].append(statement)

    with_files = set(
        Problem.files.through.objects.values_list('problem_id', flat=True))

    found = {}
    for pid, status, title, statement, answer, solution in (
            Problem.objects.filter(id__in=ids).values_list(
                'id', 'status', 'title', 'statement', 'answer', 'solution'
            ).iterator(chunk_size=2000)):
        if pid in with_files:
            continue
        stmt_blob = '\n'.join(
            x for x in (title, statement, '\n'.join(part_text.get(pid, ()))) if x)
        sol_blob = '\n'.join(x for x in (answer, solution) if x)

        method_a = {}
        for blob in (stmt_blob, sol_blob):
            for key, count in method_a_hits(blob).items():
                method_a[key] = method_a.get(key, 0) + count
        b_stmt = method_b_hits(stmt_blob)
        b_sol = method_b_hits(sol_blob)
        if not (method_a or b_stmt or b_sol):
            continue
        found[pid] = {
            'source': source_of.get(pid, '(без источника)'),
            'status': status,
            'method_a': method_a,
            'method_b_statement': b_stmt,
            'method_b_solution': b_sol,
            'has_data': has_own_data(stmt_blob),
        }
    return found


def unsolvable_ids(found):
    """Из находок ``scan_problems`` — те, что без картинки не решаются.

    Это явная разметка картинки где угодно ЛИБО словесная отсылка в условии.
    Отсылка только в решении сюда не входит.
    """
    return {pid for pid, hit in found.items()
            if hit['method_a'] or hit['method_b_statement']}
