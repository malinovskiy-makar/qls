"""Баллы по задачам с первой страницы работы.

Путь (а) — текстовый слой PDF. Путь (б) — вырез таблички баллов →
GLM-5.3-Flash через `core.run` (единственная дверь к моделям).

⚠️ МОДЕЛИ УХОДИТ ТОЛЬКО ВЫРЕЗ ТАБЛИЧКИ, без шапки с ФИО. Вырез строится из
двух полос первой страницы — строки номеров заданий и строки «Баллы итог»
(с ячейкой «За работу»); строки с подписями/кодами жюри и вся остальная
страница в него не попадают. Каждый отправленный вырез сохраняется в папку
данных, чтобы любую строку можно было проверить глазами.
"""
import io
import json
import re

#: Схема ответа модели (GLM получает её текстом в системном блоке).
SCHEMA = {
    'type': 'object',
    'required': ['tasks', 'total', 'readable'],
    'properties': {
        'tasks': {'type': 'array', 'items': {
            'type': 'object', 'required': ['n', 'score'],
            'properties': {'n': {'type': 'integer'},
                           'score': {'type': ['string', 'null']}}}},
        'total': {'type': ['string', 'null']},
        'readable': {'type': 'boolean'},
    },
}

SYSTEM = [
    'Ты переписываешь числа с картинки. На картинке — фрагмент протокола '
    'проверки олимпиадной работы: сверху строка с номерами заданий, ниже '
    'строка итоговых баллов за каждое задание и, справа, общий балл «За '
    'работу». Баллы вписаны от руки.',
    'Перепиши числа РОВНО так, как они написаны. Ничего не считай, не '
    'складывай, не исправляй и не угадывай. Для каждого задания — '
    'отдельный элемент tasks с его номером n и баллом score строкой '
    '(дробь пиши через точку: «7.5»; ведущий ноль, как «05», убери). '
    'Если строк с баллами несколько, бери строку «Баллы итог» (или '
    'единственную строку «Баллы»). Столбцы «Сумма», «Итого», «За работу» — '
    'это total, а не задание. Пустая ячейка задания — score "" (пустая '
    'строка); нечитаемое — null. total — общий балл или null. '
    'readable=false, если таблицу на картинке прочитать нельзя вовсе.',
]

MODEL = 'glm-5.3-flash'
TOLERANCE = 0.5


# --------------------------------------------------------------- вырез
#: Полосы выреза в долях страницы (x0, y0, x1, y1) по раскладке бланка.
#: Ключ — раскладка (см. `layout_for`); у каждой две полосы: номера
#: заданий и итог. Значения сняты с образцов разведки (RECON.md).
LAYOUTS = {
    # 2013/2014: одна таблица «Задание 1…5 | Итого | Подпись» и строка
    # «Баллы» прямо под ней; столбец «Подпись» жюри и кружки итога справа не берём.
    'v1_2014': ((0.06, 0.275, 0.625, 0.385),),
    # 2016/2017–2024/2025: «Протокол проверки» — строки «Задания», «Баллы
    # 1 член жюри», «Подпись 1», «Баллы итог» (клетки-цифры), «Подпись 2»;
    # справа столбец «Сумма». Берём «Задания» и «Баллы итог».
    'v2_2017': ((0.02, 0.265, 0.98, 0.35), (0.02, 0.435, 0.98, 0.52)),
    # 2025/2026: «Баллы 1/2 член жюри» с подписями, «Баллы итог» внизу,
    # ячейка «За работу» справа от неё.
    'v3_2026': ((0.02, 0.28, 0.98, 0.355), (0.02, 0.565, 0.98, 0.64)),
}

#: Сезон → раскладка. Записаны только сезоны, чью раскладку видели глазами
#: (разведка: экономика 2013/14, 2016/17, 2019/20, 2022/23, 2024/25,
#: 2025/26); промежуточные сезоны v2 приняты по одинаковому бланку соседей.
#: 2014/2015 и 2015/2016 не видели — None, в очередь review.
SEASON_LAYOUT = {
    '2013/2014': 'v1_2014',
    '2016/2017': 'v2_2017', '2017/2018': 'v2_2017', '2018/2019': 'v2_2017',
    '2019/2020': 'v2_2017', '2020/2021': 'v2_2017', '2021/2022': 'v2_2017',
    '2022/2023': 'v2_2017', '2023/2024': 'v2_2017', '2024/2025': 'v2_2017',
    '2025/2026': 'v3_2026',
}


def layout_for(season):
    """Какая раскладка бланка у сезона. None — вырезать не умеем."""
    return SEASON_LAYOUT.get(season)


def crop_scores(image, layout):
    """Склеить полосы `layout` в одну картинку (PIL.Image) сверху вниз."""
    from PIL import Image

    w, h = image.size
    parts = [image.crop((round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)))
             for x0, y0, x1, y1 in LAYOUTS[layout]]
    width = max(p.width for p in parts)
    out = Image.new('RGB', (width, sum(p.height for p in parts) + 6 * (len(parts) - 1)),
                    'white')
    y = 0
    for p in parts:
        out.paste(p, (0, y))
        y += p.height + 6
    return out


def png_bytes(image):
    buf = io.BytesIO()
    image.save(buf, format='PNG', optimize=True)
    return buf.getvalue()


# --------------------------------------------------------------- ответ

def tolerant_parse(text):
    """Разбор ответа, который НИКОГДА не падает: деньги уже потрачены.

    Обрамление ```json, текст вокруг, массив вместо объекта — чинится;
    не вышло — словарь с пометкой `_format_error` и сырым текстом.
    """
    raw = (text or '').strip()
    body = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw)
    for candidate in (body, _first_braces(body)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, list):
            data = {'tasks': data, 'total': None, 'readable': True}
        if isinstance(data, dict):
            return data
    return {'_format_error': True, '_raw': raw[:2000]}


def _first_braces(text):
    start, end = text.find('{'), text.rfind('}')
    return text[start:end + 1] if 0 <= start < end else ''


def to_number(value):
    """«7», «7,5», 7 → число; null/«—»/мусор → None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(',', '.')
    if text in ('', '-', '–', '—'):
        # Пустая ячейка/прочерк = 0 баллов; нечитаемое модель отдаёт null.
        return 0.0
    try:
        return float(text)
    except ValueError:
        return None


def verdict(data, expected_total):
    """Сверка прочитанного с баллом из списка → (status, details).

    ok — все задачи прочитаны и их сумма равна `score_before` с допуском
    0,5; иначе review с причиной. Сумму считаем МЫ, модель ничего не
    складывает.
    """
    if not isinstance(data, dict) or data.get('_format_error'):
        return 'review', {'reason': 'format', 'tasks': None}
    if data.get('readable') is False:
        return 'review', {'reason': 'unreadable', 'tasks': None}
    tasks = data.get('tasks')
    if not isinstance(tasks, list) or not tasks:
        return 'review', {'reason': 'no_tasks', 'tasks': None}
    scores = []
    for item in tasks:
        score = to_number(item.get('score')) if isinstance(item, dict) else None
        scores.append(score)
    if any(s is None for s in scores):
        return 'review', {'reason': 'task_unreadable', 'tasks': scores}
    total = sum(scores)
    details = {'tasks': scores, 'sum': total, 'model_total': to_number(data.get('total'))}
    if expected_total is None:
        return 'review', dict(details, reason='no_expected')
    if abs(total - float(expected_total)) <= TOLERANCE:
        return 'ok', dict(details, reason='')
    return 'review', dict(details, reason='sum_mismatch')


def estimate_usd(n_calls, input_tokens=1500, output_tokens=700, prices=(0.15, 0.50)):
    """Грубая смета: токены на вызов × цена за миллион (вход, выход)."""
    return n_calls * (input_tokens * prices[0] + output_tokens * prices[-1]) / 1e6
