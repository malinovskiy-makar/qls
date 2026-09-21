"""Блоки варианта: как они называются и как делятся на разделы страницы.

Только показ. Сколько баллов у задания, решает `points` в данных, а не блок
(у 11 класса задания 43 и 44 стоят по 4,5): здесь баллы блока лишь складываются
для подписи. Правила подсчёта — в `vp/scoring.py`.
"""
from decimal import Decimal

#: Названия блока: `table` — таблица на входе, `heading` — заголовок раздела на
#: странице прохождения, `short` — строка «По блокам» на экране результата.
TITLES = {
    'snake': {'table': 'Змейка, короткий ответ',
              'heading': 'Змейка',
              'short': 'Змейка'},
    'gapfill': {'table': 'Пропущенные слова',
                'heading': 'Пропущенные слова',
                'short': 'Пропущенные слова'},
    'multi': {'table': 'Все верные утверждения',
              'heading': 'Все верные утверждения',
              'short': 'Все верные'},
    'analytic': {'table': 'Анализ графика и таблицы',
                 'heading': 'Анализ рисунка или таблицы',
                 'short': 'Рисунок и таблица'},
    'single': {'table': 'Расчётные, один ответ',
               'heading': 'Расчётные, один ответ',
               'short': 'Расчётные'},
}

#: Что сказано в начале блока, если файл варианта своего вступления не дал.
DEFAULT_HINTS = {
    'snake': ('Ответ — одно слово или словосочетание в именительном падеже, '
              'строчными буквами, в единственном числе. Каждый следующий ответ '
              'начинается со второй буквы предыдущего.'),
}

ZERO = Decimal('0')


def number_range(first, last):
    """«1–30» или «44» для блока из одного задания (короткое тире)."""
    return str(first) if first == last else f'{first}–{last}'


def sections(items):
    """Подряд идущие задания одного блока → разделы страницы.

    Возвращает список словарей: `block`, `items`, `first`, `last`, `range`,
    `total` (сумма баллов), `uniform` (одинаковые баллы за задание или None),
    `points_min` / `points_max`,
    `penalty` (есть ли штраф за лишнее), `intro` (вступление блока: `intro` его
    первого задания, а если пусто — подпись по умолчанию для блока).
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
                'short': section['block']}),
        )
    return result


def merged_ranges(sections_):
    """Разделы → диапазоны номеров, где соседние склеены: 1–30 и 31–35 → «1–35»."""
    spans = []
    for section in sorted(sections_, key=lambda s: s['first']):
        if spans and section['first'] == spans[-1][1] + 1:
            spans[-1][1] = section['last']
        else:
            spans.append([section['first'], section['last']])
    return [number_range(first, last) for first, last in spans]
