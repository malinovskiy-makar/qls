"""Баллы по задачам с первой страницы работы МОШ: вырез таблицы → модель → сверка.

Путь один: вырез полосы `scans.BAND` → GLM-5.3-Flash через `core.run`
(единственная дверь к моделям). Текстового слоя у сканов нет (разведка
09.10.2026), поэтому пути «текст» здесь нет. Общие мелочи (терпимый разбор
ответа, число из ячейки, смета, PNG) — из `vp_works.scores`, не копии.

⚠️ МОДЕЛИ УХОДИТ ТОЛЬКО ВЫРЕЗ ТАБЛИЦЫ БАЛЛОВ: выше полосы — QR, «аудитория —
посадочное место» и номер участника, ниже — реклама; ФИО на первой странице
нет ни в одном бланке. В полосе остаются заголовок таблицы, цифры и два-три
буквенных кода членов жюри. Каждый отправленный вырез сохраняется в `crops/`.

ПРОВЕРКА — НАША, не модели. Балл в таблице призёров — ПОСЛЕ апелляции, на
скане — ДО (так видно по расхождениям 2025: скан меньше на 8–18). Поэтому
`ok` ставится не по сверке с `total_listed`, а по внутренней согласованности
скана: сумма баллов по задачам == ячейка «Сумма» той же строки (допуск 0,5).
Разница `appeal_delta = total_listed − (итог скана)` обязана быть ≥ 0.
"""
import re

from problems.vp_works.scores import (  # noqa: F401 — общий код ВП, не копия
    estimate_usd, png_bytes, tolerant_parse)

MODEL = 'glm-5.3-flash'
TOLERANCE = 0.5

#: Схема ответа модели (GLM получает её текстом в системном блоке).
SCHEMA = {
    'type': 'object',
    'required': ['tasks', 'total', 'readable'],
    'properties': {
        'tasks': {'type': 'array', 'items': {
            'type': 'object', 'required': ['n', 'score'],
            'properties': {'n': {'type': 'integer'},
                           'label': {'type': ['string', 'null']},
                           'score': {'type': ['string', 'null']}}}},
        'total': {'type': ['string', 'null']},
        'readable': {'type': 'boolean'},
    },
}

SYSTEM = [
    'Ты переписываешь числа с картинки. На картинке — таблица баллов олимпиадной '
    'работы: в верхней строке «Задача» номера столбцов (1, 2, 3, 4; у некоторых '
    'бланков «1-5», 6, 7, 8) и последний столбец «Сумма»; ниже строки «Баллы» '
    '(цифры от руки красной ручкой), «Член жюри» (две-три буквы-инициалы), снова '
    '«Баллы», «Член жюри» и строка «Итог».',
    'Какую строку брать: «Итог», если в ней есть цифры; иначе самую нижнюю '
    'заполненную строку «Баллы». Строки «Член жюри» — это НЕ баллы, их не '
    'переписывай никогда.',
    'Перепиши числа РОВНО так, как они написаны. Ничего не считай, не складывай, '
    'не исправляй и не угадывай. Для КАЖДОГО столбца задач (кроме «Сумма») — один '
    'элемент tasks: n — порядковый номер столбца слева направо (1, 2, 3…), label — '
    'заголовок столбца как напечатан («1», «1-5», «6»), score — число строкой '
    '(дробь через точку: «7.5»; ведущий ноль, как «05», убери). Пустая клетка — '
    'score "" (пустая строка); прочерк «—» значит 0 баллов — пиши "0"; клетка '
    'закрашена жёлтым или цифру прочитать нельзя — score null.',
    'Поле total — число из клетки столбца «Сумма» в ТОЙ ЖЕ строке, что ты взял для '
    'задач; клетка пустая — "", нечитаемая — null. Половину балла жюри часто '
    'пишет маленькой цифрой 5 вверху справа от числа: «20⁵» — это 20.5, а не 205 '
    'и не 25. readable=false, если таблицу прочитать нельзя вовсе.',
]

#: Подсказка для повторного прохода (`--retry-review`).
RETRY_HINT = ('Внимательнее с цифрами: «1» и «7», «4» и «9», «0» и «6» путают. '
              'Половины баллов — маленькая цифра 5 справа вверху.')

#: Причины review, которые стоит перечитать вторым проходом.
RETRYABLE = ('sum_mismatch', 'task_unreadable', 'format', 'no_tasks', 'unreadable')

MERGED_RE = re.compile(r'^\s*1\s*[-–—]\s*5\s*$')


def cell(value):
    """Ячейка → ('blank'|'num'|'bad', число|None).

    Пусто и null различаем: пустая клетка — «не вписано» (не 0!), null —
    «модель не смогла прочитать». Прочерк = 0 баллов.
    """
    if value is None or isinstance(value, bool):
        return 'bad', None
    if isinstance(value, (int, float)):
        return 'num', float(value)
    text = str(value).strip().replace(',', '.')
    if text == '':
        return 'blank', None
    if text in ('-', '–', '—'):
        return 'num', 0.0
    try:
        return 'num', float(text)
    except ValueError:
        return 'bad', None


def verdict(data, total_listed):
    """Сверка прочитанного → (status, details).

    status: ok / partial / review (hidden_by_stickers решает вызывающий —
    до модели). details: reason, tasks [{n,label,score}], tasks_sum,
    total_read, appeal_delta, verified_by ('total_cell'|'listed'|None),
    merged_1_5, missing [n…].
    """
    empty = {'tasks': None, 'tasks_sum': None, 'total_read': None, 'appeal_delta': None,
             'verified_by': None, 'merged_1_5': False, 'missing': []}
    if not isinstance(data, dict) or data.get('_format_error'):
        return 'review', dict(empty, reason='format')
    if data.get('readable') is False:
        return 'review', dict(empty, reason='unreadable')
    raw = data.get('tasks')
    if not isinstance(raw, list) or not raw:
        return 'review', dict(empty, reason='no_tasks')

    tasks, kinds = [], []
    for i, item in enumerate(raw, 1):
        item = item if isinstance(item, dict) else {}
        kind, value = cell(item.get('score'))
        n = item.get('n') if isinstance(item.get('n'), int) else i
        tasks.append({'n': n, 'label': item.get('label'), 'score': value})
        kinds.append(kind)
    merged = any(isinstance(t['label'], str) and MERGED_RE.match(t['label']) for t in tasks)
    details = dict(empty, tasks=tasks, merged_1_5=merged)
    found = [t['score'] for t, k in zip(tasks, kinds) if k == 'num']
    details['tasks_sum'] = sum(found) if found else None

    if 'bad' in kinds:
        return 'review', dict(details, reason='task_unreadable')
    if not found:
        return 'review', dict(details, reason='empty_table')
    total_kind, total_value = cell(data.get('total'))
    details['total_read'] = total_value if total_kind == 'num' else None
    if 'blank' in kinds:
        # Не все задачи вписаны (например, нет задачи 4 в 2022): перечисляем
        # найденные и недостающие, сумму не сверяем — сверять не с чем.
        details['missing'] = [t['n'] for t, k in zip(tasks, kinds) if k == 'blank']
        return 'partial', dict(details, reason='tasks_missing')

    tasks_sum = details['tasks_sum']
    if details['total_read'] is not None:
        if abs(tasks_sum - details['total_read']) > TOLERANCE:
            return 'review', dict(details, reason='sum_mismatch')
        base, verified_by = details['total_read'], 'total_cell'
    elif total_listed is not None and abs(tasks_sum - total_listed) <= TOLERANCE:
        base, verified_by = tasks_sum, 'listed'
    else:
        # Клетка «Сумма» пуста/нечитаема и сверить с таблицей нечем: балл в ней
        # после апелляции. Разницу пишем, но «ok» не ставим — решает человек.
        delta = None if total_listed is None else _num(total_listed - tasks_sum)
        return 'review', dict(details, reason='no_total_cell', appeal_delta=delta)
    delta = None if total_listed is None else _num(total_listed - base)
    details.update({'appeal_delta': delta, 'verified_by': verified_by})
    if delta is not None and delta < -TOLERANCE:
        return 'review', dict(details, reason='appeal_negative')
    return 'ok', dict(details, reason='')


def _num(value):
    return int(value) if float(value).is_integer() else round(value, 2)


# ------------------------------------------------------------------ 2021

#: Бланк 2021: две проверки («Баллы» сверху и снизу) или одна («Балл» у бланка
#: «Задание №1…№5»); часть клеток закрыта жёлтыми пятнами. Правила владельца
#: (13.10.2026): строки читаются ОТДЕЛЬНО, закрытое пятном — null; итог по
#: задаче — последняя непустая из строк; `ok` — только если значение есть у
#: ВСЕХ задач и сумма == total_listed; иначе `partial` (найденное хранится);
#: закрыто всё — `hidden_by_stickers`.
SCHEMA_ROWS = {
    'type': 'object',
    'required': ['rows', 'total', 'readable'],
    'properties': {
        'form': {'type': ['string', 'null']},
        'rows': {'type': 'array', 'items': {
            'type': 'object', 'required': ['cells'],
            'properties': {'label': {'type': ['string', 'null']},
                           'cells': {'type': 'array', 'items': {'type': ['string', 'null']}}}}},
        'total': {'type': ['string', 'null']},
        'readable': {'type': 'boolean'},
    },
}

SYSTEM_ROWS = [
    'Ты переписываешь числа с картинки. На картинке — таблица баллов олимпиадной '
    'работы. Бывает два вида. Вид «tasks4»: заголовок «Задача | 1 | 2 | 3 | 4 | Сумма» '
    'и строки «Баллы», «Член жюри», «Баллы», «Член жюри» (две проверки; вторая '
    'может быть пустой). Вид «tasks5»: заголовок «Задание | №1 | №2 | №3 | №4 | №5 | '
    'Сумма» и одна строка «Балл». Поле form — «tasks4», «tasks5» или «other».',
    'Верни rows — ТОЛЬКО строки «Баллы»/«Балл», сверху вниз, каждую отдельно: label '
    'как напечатано, cells — по одному значению на КАЖДЫЙ столбец задачи слева '
    'направо (столбец «Сумма» в cells не входит). Строки «Член жюри» (инициалы) '
    'не переписывай никогда. Если проверок две, а вторая строка пустая, всё равно '
    'верни обе (пустую — как строку из "").',
    'Значение клетки — число строкой (дробь через точку: «7.5»; ведущий ноль, как '
    '«05», убери). Пустая клетка, где ничего не написано, — "" (пустая строка). '
    'Клетка закрыта жёлтой заливкой (маркер) или цифру прочитать нельзя — null. '
    'Часть клеток закрыта жёлтым — это нормально: закрытое — null, остальное '
    'читай как обычно. Ничего не считай, не складывай, не исправляй и не угадывай. '
    'Половину балла жюри часто пишет маленькой цифрой 5 вверху справа: «20⁵» — '
    'это 20.5, а не 205.',
    'Поле total — число из клетки столбца «Сумма» (в любой из строк); пусто — "", '
    'закрыто или нечитаемо — null. readable=false, если таблицу прочитать нельзя вовсе.',
]

#: Закрытие полосы таблицы, выше которого работа 2021 считается закрытой целиком
#: без вызова модели; ниже — модель читает видимое (закрытая вся — тоже hidden).
HIDDEN_ALL_BAND_PCT = 8.0


def verdict_rows(data, total_listed):
    """Бланк 2021: строки «Баллы» отдельно → итог по задаче → статус.

    Итог по задаче — последняя непустая (число) из строк сверху вниз; клетка
    null (закрыта) в расчёте не участвует. details как у `verdict`, плюс
    `rows` (что прочитано по строкам), `closed` и `blank` — номера задач,
    `form`, `sum_matches_listed`.
    """
    empty = {'tasks': None, 'tasks_sum': None, 'total_read': None, 'appeal_delta': None,
             'verified_by': None, 'merged_1_5': False, 'missing': [], 'closed': [],
             'blank': [], 'rows': None, 'form': None, 'sum_matches_listed': None}
    if not isinstance(data, dict) or data.get('_format_error'):
        return 'review', dict(empty, reason='format')
    if data.get('readable') is False:
        return 'review', dict(empty, reason='unreadable')
    raw_rows = data.get('rows')
    rows = [r.get('cells') for r in raw_rows if isinstance(r, dict)
            and isinstance(r.get('cells'), list)] if isinstance(raw_rows, list) else []
    if not rows or not max(len(r) for r in rows):
        return 'review', dict(empty, reason='no_tasks')
    width = max(len(r) for r in rows)
    tasks, closed, blank = [], [], []
    for j in range(width):
        kinds = [cell(r[j] if j < len(r) else '') for r in rows]
        nums = [v for k, v in kinds if k == 'num']
        value = nums[-1] if nums else None
        if value is None:
            (closed if any(k == 'bad' for k, _ in kinds) else blank).append(j + 1)
        tasks.append({'n': j + 1, 'label': None, 'score': value,
                      'rows': [v if k == 'num' else ('' if k == 'blank' else None)
                               for k, v in kinds]})
    found = [t['score'] for t in tasks if t['score'] is not None]
    total_kind, total_value = cell(data.get('total'))
    details = dict(empty, tasks=tasks, closed=closed, blank=blank, form=data.get('form'),
                   rows=[[c for c in r] for r in rows],
                   tasks_sum=sum(found) if found else None,
                   total_read=total_value if total_kind == 'num' else None)
    if not found:
        if closed:
            return 'hidden_by_stickers', dict(details, reason='all_closed')
        return 'review', dict(details, reason='empty_table')
    if total_listed is not None and details['tasks_sum'] is not None:
        details['sum_matches_listed'] = abs(details['tasks_sum'] - total_listed) <= TOLERANCE
    if closed or blank:
        details['missing'] = closed + blank
        return 'partial', dict(details, reason='tasks_closed' if closed else 'tasks_blank')
    if details['total_read'] is not None \
            and abs(details['tasks_sum'] - details['total_read']) > TOLERANCE:
        return 'review', dict(details, reason='sum_mismatch')
    if total_listed is None or not details['sum_matches_listed']:
        delta = None if total_listed is None else _num(total_listed - details['tasks_sum'])
        return 'review', dict(details, reason='sum_mismatch', appeal_delta=delta)
    return 'ok', dict(details, reason='', verified_by='listed', appeal_delta=0)
