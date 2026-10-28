"""Тренировка записи ответа и пробник посадочной: проверка ЗАПИСИ числа вне варианта.

Внутри варианта подсказок о записи нет ни в одном режиме (решение владельца 24.10 и
28.10.2026): тренажёр ведёт себя как тур. Правилу ВШЭ учат здесь — 12 готовых чисел за
2–3 минуты (`/vp/format/`) и пробник на посадочной. Без базы и без входа.

Проверяет тот же код, что считает баллы: `scoring.explain_item` (строгий формат + сравнение
значений, как у задачи с числом) и `scoring.canonical_number` / `scoring.format_error`.
"""
from decimal import Decimal

from vp import scoring
from vp.models import VPItem

#: 12 заданий: (что получилось в решении, подпись, верная запись).
DRILL = (
    ('37.5', 'калькулятор ставит точку', '37,5'),
    ('25 000', 'выручка, рублей', '25000'),
    ('20%', 'спрашивают, на сколько процентов', '20'),
    ('−0,12', 'минус как в учебнике', '-0,12'),
    ('1,607', '', '1,61'),
    ('2/3', 'обыкновенная дробь', '0,67'),
    ('3,125', 'ровно половина сотой', '3,13'),
    ('1 200,50 ₽', '', '1200,5'),
    ('37,50', 'лишний ноль после запятой', '37,5'),
    ('−1/8', '', '-0,13'),
    ('7¼ кг', '', '7,25'),
    ('-4,5', 'минус с клавиатуры', '-4,5'),
)

#: Подписи причин для итога тренировки («Ошибки по типам: …»).
REASON_LABELS = {
    'dot': 'точка вместо запятой', 'space': 'пробел внутри числа',
    'units': 'лишние знаки или единицы', 'minus': 'длинный минус «−»',
    'decimals': 'больше двух знаков после запятой', 'other': 'не по правилам',
    'wrong': 'запись верная, но число другое',
}


def _item(right):
    """Задача с числом в памяти (в базу не пишется): эталон из таблицы тренировки."""
    return VPItem(kind=VPItem.Kind.NUMBER, block=VPItem.Block.NUMBER, number=0, statement='',
                  answer=right, accepted=[], points=Decimal('1'))


def check(i, raw):
    """Задание тренировки № `i` (1…12) и запись ученика → `{ok, reason, text, right}`."""
    _, _, right = DRILL[i - 1]
    text = '' if raw is None else str(raw).strip()
    if not text:
        return {'ok': False, 'reason': 'empty', 'text': 'Впишите число.', 'right': right}
    explain = scoring.explain_item(_item(right), text)
    if explain['is_correct']:
        extra_zero = text != right
        return {'ok': True, 'reason': 'ok', 'right': right,
                'text': ('Засчитают: лишний ноль после запятой не мешает.' if extra_zero
                         else 'Засчитают.')}
    reason = explain['format_error'] or 'wrong'
    texts = {
        'dot': f'Точка вместо запятой. Верно: «{right}».',
        'space': f'Пробел внутри числа. Верно: «{right}».',
        'units': f'Лишние знаки или единицы. Верно: «{right}».',
        'minus': f'Длинный минус «−». Наберите «-» с клавиатуры: «{right}».',
        'decimals': f'Больше двух знаков после запятой. Округлите: «{right}».',
        'wrong': f'Запись верная, но число другое. Верно: «{right}».',
        'other': f'Не по правилам: цифры, одна запятая, минус в начале. Верно: «{right}».',
    }
    return {'ok': False, 'reason': reason, 'text': texts[reason], 'right': right}


def probe(raw):
    """Пробник посадочной: засчитают ли такую запись на туре → `{ok, reason, text, fix}`,
    `fix` — `scoring.canonical_number` (как надо записать) или `None`."""
    text = '' if raw is None else str(raw).strip()
    if not text:
        return {'ok': False, 'reason': 'empty', 'fix': None,
                'text': 'Впишите число – покажем, засчитают ли его на туре.'}
    reason = scoring.format_error(text)
    if reason is None:
        return {'ok': True, 'reason': 'ok', 'fix': text,
                'text': 'Так засчитают: запятая, без пробелов и единиц.'}
    fix = scoring.canonical_number(text)
    if reason == 'minus':
        return {'ok': False, 'reason': reason, 'fix': fix,
                'text': 'Это длинный минус «−» из копирования. Наберите обычный «-» с клавиатуры.'}
    what = {'dot': 'точка вместо запятой', 'space': 'пробел внутри числа',
            'units': 'лишние знаки или единицы', 'other': 'запись не по правилам',
            'decimals': 'больше двух знаков после запятой'}[reason]
    tail = f' Нужно «{fix}».' if fix else ''
    return {'ok': False, 'reason': reason, 'fix': fix, 'text': f'0 баллов: {what}.{tail}'}


def rows(given=None):
    """Строки страницы: `{i, shown, caption, value, verdict}`; `given` — записи из формы без JS
    (`{i: raw}`), тогда у строки есть вердикт `check`."""
    result = []
    for i, (shown, caption, _) in enumerate(DRILL, start=1):
        value = (given or {}).get(i)
        result.append({'i': i, 'shown': shown, 'caption': caption, 'value': value or '',
                       'verdict': check(i, value) if given is not None else None})
    return result
