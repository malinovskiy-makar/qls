"""Блоки варианта: как они называются и как делятся на разделы страницы.

Только показ. Сколько баллов у задания, решает `points` в данных, а не блок
(у 11 класса задания 43 и 44 стоят по 4,5): здесь баллы блока лишь складываются
для подписи. Правила подсчёта — в `vp/scoring.py`.
"""
from decimal import Decimal

#: Названия блока: `table` — таблица на входе, `heading` — заголовок раздела на
#: странице прохождения, `short` — строка «По блокам» на экране результата, `nav` —
#: подпись группы номеров в навигации прохождения («Пропуски · 3»).
TITLES = {
    'snake': {'table': 'Змейка, короткий ответ',
              'heading': 'Змейка',
              'short': 'Змейка',
              'nav': 'Змейка'},
    'gapfill': {'table': 'Пропущенные слова',
                'heading': 'Пропущенные слова',
                'short': 'Пропущенные слова',
                'nav': 'Пропущенные слова'},
    'multi': {'table': 'Все верные утверждения',
              'heading': 'Все верные утверждения',
              'short': 'Все верные',
              'nav': 'Все верные'},
    'analytic': {'table': 'Анализ графика и таблицы',
                 'heading': 'Анализ рисунка или таблицы',
                 'short': 'Рисунок и таблица',
                 'nav': 'Рисунок и таблица'},
    'single': {'table': 'Расчётные, один ответ',
               'heading': 'Расчётные, один ответ',
               'short': 'Расчётные',
               'nav': 'Расчётные'},
    # 2 тур
    'number': {'table': 'Задачи с вводом числа',
               'heading': 'Задачи с вводом числа',
               'short': 'Задачи с числом',
               'nav': 'Задачи с числом'},
    'gaptext': {'table': 'Текст с пропусками',
                'heading': 'Текст с пропусками',
                'short': 'Текст с пропусками',
                'nav': 'Пропуски'},
    'matching': {'table': 'Соотнесение',
                 'heading': 'Соотнесение',
                 'short': 'Соотнесение',
                 'nav': 'Соотнесение'},
}

#: Правило ВШЭ для ответа-числа — ДОСЛОВНО (рекомендации 2026/27). Стоит перед первым
#: заданием блока «Ввод числа» и в окне правил. Ответ не по нему ВШЭ оценивает в 0.
NUMBER_RULE = ('Ответ в виде числа запишите без пробелов, без единиц измерения и каких-либо '
               'знаков (если ответ является дробным числом, то его необходимо записать с '
               'помощью десятичной дроби, округлив до сотых, например, «1,23»).')

#: Что сказано в начале блока, если файл варианта своего вступления не дал.
DEFAULT_HINTS = {
    'snake': ('Ответ — одно слово или словосочетание в именительном падеже, '
              'строчными буквами, в единственном числе. Каждый следующий ответ '
              'начинается со второй буквы предыдущего.'),
}

ZERO = Decimal('0')

#: Как считается блок — для фраз «как считаются баллы» на входе и на посадочной.
#: Доля за верные и штраф за лишние (если у задания `penalty`):
SHARE_WITH_PENALTY = ('multi', 'analytic')
#: Доля за верные ключи, штрафа нет никогда (пропуски и соотнесение 2 тура):
SHARE_NO_PENALTY = ('gaptext', 'matching')

#: Короткая подпись «как считается» у шапки раздела прохождения: «9 баллов · каждая
#: строка – своя доля». У числа подпись своя («по 5 баллов: полный балл или ноль»).
SECTION_HOW = {
    'gaptext': 'каждый пропуск – своя доля',
    'matching': 'каждая строка – своя доля',
}


def number_range(first, last):
    """«1–30» или «44» для блока из одного задания (короткое тире)."""
    return str(first) if first == last else f'{first}–{last}'


def sections(items):
    """Подряд идущие задания одного блока → разделы страницы.

    Возвращает список словарей: `block`, `items`, `first`, `last`, `range`,
    `total` (сумма баллов), `uniform` (одинаковые баллы за задание или None),
    `points_min` / `points_max`,
    `penalty` (есть ли штраф за лишнее), `intro` (вступление блока: `intro` его
    первого задания, а если пусто — подпись по умолчанию для блока), `how`
    (короткое «как считается» для шапки раздела, `SECTION_HOW`).
    """
    result = []
    for item in sorted(items, key=lambda i: i.number):
        if result and result[-1]['block'] == item.block:
            result[-1]['items'].append(item)
        else:
            result.append({'block': item.block, 'items': [item]})
    for section in result:
        items_ = section['items']
        points = {i.points for i in items_}
        section.update(
            first=items_[0].number,
            last=items_[-1].number,
            range=number_range(items_[0].number, items_[-1].number),
            total=sum((i.points for i in items_), ZERO),
            uniform=next(iter(points)) if len(points) == 1 else None,
            points_min=min(points), points_max=max(points),
            penalty=any(i.penalty for i in items_),
            intro=(items_[0].intro or DEFAULT_HINTS.get(section['block'], '')),
            titles=TITLES.get(section['block'], {
                'table': section['block'], 'heading': section['block'],
                'short': section['block'], 'nav': section['block']}),
            how=SECTION_HOW.get(section['block'], ''),
        )
    return result


def _spans(sections_):
    spans = []
    for section in sorted(sections_, key=lambda s: s['first']):
        if spans and section['first'] == spans[-1][1] + 1:
            spans[-1][1] = section['last']
        else:
            spans.append([section['first'], section['last']])
    return spans


def in_tasks(sections_):
    """Фраза «В заданиях 3 и 4» / «В задании 4» / «В заданиях 1–3» / «В заданиях 1–35 и 43–44»
    для интро и окна правил — ОДНА на раздел. Слово — по числу ЗАДАНИЙ, а не диапазонов
    («В задании 3–4» было бы ошибкой); диапазон ровно из двух соседних номеров — «3 и 4».
    Пустой список — пустая строка."""
    spans = _spans(sections_)
    if not spans:
        return ''
    count = sum(last - first + 1 for first, last in spans)
    if len(spans) == 1 and spans[0][1] == spans[0][0] + 1:
        numbers = f'{spans[0][0]} и {spans[0][1]}'
    else:
        numbers = ' и '.join(number_range(first, last) for first, last in spans)
    return f'В {"задании" if count == 1 else "заданиях"} {numbers}'


def merged_ranges(sections_):
    """Разделы → диапазоны номеров, где соседние склеены: 1–30 и 31–35 → «1–35»."""
    return [number_range(first, last) for first, last in _spans(sections_)]
