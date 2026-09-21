"""Данные посадочной страницы `/vp/`: формат варианта, пример змейки, даты тура.

⚠️ ВСЕ ЧИСЛА — ИЗ ЗАДАНИЙ ОПУБЛИКОВАННЫХ ВАРИАНТОВ В БАЗЕ, а не из шаблона и не из
констант: число заданий, баллы блоков, диапазоны номеров. Испортишь задание — число на
странице меняется (тест `test_landing`). Сезонное — даты тура — только в `vp/config.py`.

Модуль ничего не пишет и баллов не считает: правила подсчёта — в `vp/scoring.py`,
разбиение на блоки — в `vp/blocks.py`, буквы связки змейки — `vp.loader.chain_letters`.
"""
from decimal import Decimal

from vp import blocks, scoring
from vp.config import BANDS
from vp.loader import chain_letters
from vp.models import VPVariant

_ZERO = Decimal('0')
_BAND_LABELS = dict(BANDS)

_MONTHS = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа',
           'сентября', 'октября', 'ноября', 'декабря')

#: Чей вариант показывать в примере змейки в первую очередь. Пример открывает четыре
#: настоящих ответа варианта, поэтому берём то, что не жалко: демонстрационный, потом
#: прошлых лет, и лишь в конце — авторский, по которому ещё тренируются.
_KIND_ORDER = (VPVariant.SourceKind.DEMO, VPVariant.SourceKind.PAST,
               VPVariant.SourceKind.AUTHOR)


def _join(parts):
    """['26', '30'] → «26 и 30»; ['26', '27', '30'] → «26, 27 и 30»."""
    return parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ' и ' + parts[-1]


def dates_text(dates):
    """Даты тура словами: «26 и 30 сентября 2026»; пустой список — пустая строка."""
    days = sorted(dates)
    if not days:
        return ''
    if len({(d.year, d.month) for d in days}) == 1:
        return f'{_join([str(d.day) for d in days])} {_MONTHS[days[0].month - 1]} {days[0].year}'
    return _join([f'{d.day} {_MONTHS[d.month - 1]} {d.year}' for d in days])


# ---------------------------------------------------------------- формат

def _format_of(variant):
    """Формат одного варианта: блоки таблицы, итоги и то, что нужно для правил баллов."""
    items = list(variant.items.all())
    sections = blocks.sections(items)
    partial = [s for s in sections if s['block'] in ('multi', 'analytic')]
    whole = [s for s in sections if s not in partial]
    sample = next((i for s in partial for i in s['items'] if i.penalty), None)
    rows = [{
        'block': s['block'], 'range': s['range'], 'title': s['titles']['table'],
        'count': len(s['items']), 'total': s['total'],
    } for s in sections]
    fmt = {
        'rows': rows,
        'count': len(items),
        'total': sum((s['total'] for s in sections), _ZERO),
        'minutes': variant.duration_seconds // 60,
        'whole_ranges': blocks.merged_ranges(whole),
        'partial_ranges': blocks.merged_ranges(partial),
        'penalty_example': scoring.penalty_example(sample.points) if sample else None,
    }
    # Подпись — ровно то, что страница показывает. Баллы отдельных заданий внутри блока
    # (у 11 класса №43 и №44 по 4,5, у 9–10 – 4 и 5) на странице не видны, и две
    # одинаковые таблицы под разными подписями были бы шумом.
    fmt['signature'] = (fmt['count'], fmt['total'], fmt['minutes'],
                        tuple((r['block'], r['range'], r['count'], r['total']) for r in rows),
                        tuple(fmt['whole_ranges']), tuple(fmt['partial_ranges']),
                        fmt['penalty_example'])
    return fmt


def format_groups(published):
    """Формат опубликованных вариантов, сгруппированный: одинаковый формат — одна группа.

    Пока у 9–10 и 11 классов блоки и баллы совпадают, группа одна и подписи не нужно;
    разошлись — групп две, каждая подписана классами, как просит страница
    («расходятся по баллам — показывай по классу»).
    """
    groups = {}
    for variant in published:
        fmt = _format_of(variant)
        group = groups.setdefault(fmt['signature'], dict(fmt, bands=[]))
        if variant.grade_band not in group['bands']:
            group['bands'].append(variant.grade_band)
    result = list(groups.values())
    for group in result:
        group['label'] = ' и '.join(_BAND_LABELS.get(b, f'{b} кл.') for b in group['bands'])
    return result


def facts(groups):
    """Число заданий, минуты и баллы «в этом году» — только если формат один на всех."""
    if len(groups) != 1:
        return None
    group = groups[0]
    return {'count': group['count'], 'minutes': group['minutes'], 'total': group['total']}


# ---------------------------------------------------------------- змейка

def _marked(answer, is_last):
    """Ответ → (до, вторая буква, после): вторая буква — та, на какую начнётся следующий."""
    if is_last:
        return {'before': answer, 'mark': '', 'after': ''}
    seen = 0
    for index, char in enumerate(answer):
        if char.isalpha():
            seen += 1
            if seen == 2:
                return {'before': answer[:index], 'mark': char, 'after': answer[index + 1:]}
    return {'before': answer, 'mark': '', 'after': ''}


def _linked(items):
    """Подряд идущие задания, где вторая буква каждого — первая буква следующего."""
    for a, b in zip(items, items[1:]):
        first, second = chain_letters(a.chain_word())[1], chain_letters(b.chain_word())[0]
        if b.number != a.number + 1 or not second or first != second:
            return False
    return all(chain_letters(i.chain_word())[0] for i in items)


def snake_example(published, length=4):
    """Живая цепочка из `length` слов из опубликованного варианта или `None`.

    Задания идут подряд, связка между соседями настоящая. Из подходящих цепочек
    берётся та, где меньше ответов из нескольких слов: пример про «четыре слова» не
    должен читаться как четыре фразы.
    """
    def rank(variant):
        kind = variant.source_kind
        return (_KIND_ORDER.index(kind) if kind in _KIND_ORDER else len(_KIND_ORDER),
                variant.order, variant.pk)

    for variant in sorted(published, key=rank):
        snake = [i for i in variant.items.all() if i.block == 'snake' and i.answer]
        runs = [snake[i:i + length] for i in range(len(snake) - length + 1)
                if _linked(snake[i:i + length])]
        if runs:
            best = min(runs, key=lambda run: sum(len(i.answer.split()) > 1 for i in run))
            return {
                'variant': variant,
                'words': [_marked(i.answer, n == len(best) - 1) for n, i in enumerate(best)],
            }
    return None
