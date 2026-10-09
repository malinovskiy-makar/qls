"""Баллы по задачам с первой страницы работы.

Путь (а) — текстовый слой PDF. Путь (б) — вырез «Протокола проверки» →
GLM-5.3-Flash через `core.run` (единственная дверь к моделям).

⚠️ МОДЕЛИ УХОДИТ ТОЛЬКО ВЫРЕЗ ПРОТОКОЛА ПРОВЕРКИ — полоса первой страницы
между блоком «Заполняется участником» (класс, листы) и «Итоговым баллом» со
штрихкодом. ФИО на первой странице нет вовсе (шапку отрезают по «линии
отреза» до сканирования), подписи участника тоже; в полосу попадают только
таблица жюри (баллы, подписи/коды и номера членов жюри). Каждый
отправленный вырез сохраняется в папку данных и проверяется глазами.
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
    'Ты переписываешь числа с картинки. На картинке — протокол проверки '
    'олимпиадной работы: таблица, в первой строке номера заданий, ниже '
    'строки с баллами и подписями членов жюри, справа может быть столбец '
    '«Итого»/«Сумма»/«Итого за работу». Баллы вписаны от руки, иногда '
    'цифрами-шаблонами в клетках.',
    'Какую строку брать: «Баллы итог», если она есть и заполнена; иначе '
    '«Средний балл», если заполнена; иначе первую заполненную строку «Баллы» '
    '(«Балл 1 член жюри»). Строки «Подпись/код члена жюри» и «Номер члена '
    'жюри» — это НЕ баллы, их не переписывай никогда.',
    'Перепиши числа РОВНО так, как они написаны. Ничего не считай, не '
    'складывай, не исправляй и не угадывай. Для каждого задания (каждого '
    'столбца с номером) — элемент tasks с номером n и баллом score строкой '
    '(дробь через точку: «7.5»; ведущий ноль, как «05», убери). Пустая '
    'ячейка или прочерк — score "" (пустая строка); нечитаемое — null. '
    'Столбцы «Итого», «Сумма», «За работу» — это total, а не задание. '
    'readable=false, если таблицу прочитать нельзя вовсе.',
]

MODEL = 'glm-5.3-flash'
TOLERANCE = 0.5


# --------------------------------------------------------------- вырез
#: Полосы выреза в долях страницы (x0, y0, x1, y1). Одна раскладка на все
#: бланки: таблицы протокола у предметов и сезонов разные (4–7 заданий,
#: малая таблица «Баллы» или большая с двумя членами жюри и «Баллы итог»),
#: но все лежат между y≈0,27 и y≈0,74 при скане со сдвигом ±2 %; выше —
#: «Заполняется участником», ниже (от y≈0,80) — «Итоговый балл» и штрихкод.
LAYOUTS = {
    'protocol': ((0.02, 0.25, 0.98, 0.77),),
}

#: Пары (сезон, предмет), чьи вырезы просмотрены глазами (разведка и
#: выборка по 2 работы на сезон и предмет, REPORT.md). Пара без проверки —
#: None: её работы идут в review, а не в модель.
#: ⚠️ 2020/2021 и 2021/2022 НЕ здесь и не будут: олимпиада шла онлайн, работа —
#: распечатка страниц системы тестирования, на первой странице логин участника
#: («Олимпиада <номер>»). Эти сезоны читаются только из текста
#: (`moodle_scores`), их вырезы в модель не уходят никогда.
VERIFIED = {
    (season, 'economics') for season in (
        '2013/2014', '2014/2015', '2015/2016', '2016/2017', '2017/2018', '2018/2019',
        '2019/2020', '2022/2023', '2023/2024', '2024/2025', '2025/2026')
} | {
    (season, subject) for subject in ('fingram', 'business') for season in (
        '2017/2018', '2018/2019', '2019/2020', '2022/2023', '2023/2024', '2024/2025',
        '2025/2026')
}


def layout_for(season, subject):
    """Раскладка выреза. None — вырез этой пары глазами не проверен."""
    return 'protocol' if (season, subject) in VERIFIED else None


def crop_scores(image, layout):
    """Вырезать полосы `layout` и склеить сверху вниз (PIL.Image)."""
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


MOODLE_RE = re.compile(r'Вопрос\s*(\d+)[\s\S]{0,120}?Баллов:\s*([\d.,]+)\s*из\s*([\d.,]+)')


def moodle_scores(text):
    """Путь (а) для онлайн-сезонов: «Вопрос N … Баллов: 7,00 из 25,00».

    Работа 2020/21 и 2021/22 — распечатка страниц системы тестирования, балл
    за каждый вопрос стоит текстом рядом с его номером; заодно известен
    максимум. Вопрос без балла (не отвечал) — пустая ячейка, сумма всё равно
    сверяется с баллом из списка. Ничего не нашлось — None.
    """
    found = {}
    for m in MOODLE_RE.finditer(text or ''):
        found.setdefault(int(m.group(1)), (m.group(2), m.group(3)))
    if not found:
        return None
    last = max(found)
    tasks = [{'n': n, 'score': found.get(n, ('', ''))[0], 'max': found.get(n, ('', ''))[1]}
             for n in range(1, last + 1)]
    return {'tasks': tasks, 'total': None, 'readable': True}


def text_scores(words, page_height):
    """Путь (а): баллы из текстового слоя первой страницы.

    Встречается у бланков, где жюри впечатало цифры в клетки на компьютере
    (основы бизнеса 2024/25): текст есть, подписей строк нет. Разбор по
    положению: цифры протокола (0,3–0,6 высоты страницы) → ряды по высоте;
    верхний ряд — баллы; цифры одной ячейки стоят вплотную (зазор < 12 pt,
    между ячейками ≥ 28),
    правая группа — «Итого». `words` — `page.get_text('words')` PyMuPDF.
    Не похоже на таблицу — None (тогда работает путь (б)).
    """
    digits = [(w[0], w[1], w[2], w[3], w[4]) for w in words
              if w[4].isdigit() and 0.3 * page_height <= (w[1] + w[3]) / 2 <= 0.6 * page_height]
    if len(digits) < 3:
        return None
    digits.sort(key=lambda w: (w[1] + w[3]) / 2)
    rows, row = [], [digits[0]]
    for w in digits[1:]:
        if (w[1] + w[3]) / 2 - (row[-1][1] + row[-1][3]) / 2 > 10:
            rows.append(row)
            row = [w]
        else:
            row.append(w)
    rows.append(row)
    top = sorted(rows[0], key=lambda w: w[0])
    groups = [[top[0]]]
    for w in top[1:]:
        if w[0] - groups[-1][-1][2] < 12:
            groups[-1].append(w)
        else:
            groups.append([w])
    if len(groups) < 3:
        return None
    values = [''.join(w[4] for w in g) for g in groups]
    centers = [(g[0][0] + g[-1][2]) / 2 for g in groups]
    tasks_c, task_v = centers[:-1], values[:-1]
    # Шаг столбца — наименьший зазор: пустая ячейка его только увеличивает.
    gaps = [b - a for a, b in zip(tasks_c, tasks_c[1:])]
    step = min(gaps) if gaps else 1.0
    numbers = [1 + round((c - tasks_c[0]) / step) for c in tasks_c]
    by_n = dict(zip(numbers, task_v))
    tasks = [{'n': n, 'score': by_n.get(n, '')} for n in range(1, max(numbers) + 1)]
    return {'tasks': tasks, 'total': values[-1], 'readable': True}


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
