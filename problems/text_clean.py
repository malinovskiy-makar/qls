"""
Приведение текста задачи в порядок ПРИ ПОКАЗЕ И ЭКСПОРТЕ. В базу не пишем.

⚠️ ГЛАВНОЕ ПРАВИЛО, ЗАПИСАННОЕ В ПРОЕКТЕ: чистка НЕ МЕНЯЕТ ЧИСЛА, ЗНАКИ И
СМЫСЛ. Ни при каких обстоятельствах, даже когда «очевидно». Проект уже
дважды платил за нарушение этого правила: механическая чистка Батча 2
подменила знак в #48915 («negative» → «positive») и числа в #6118
(«40/40» → «80/3 и 0»), и вычищать пришлось 4 930 задач. Здесь правило
держится не обещанием, а проверкой: `same_numbers_and_signs()` сверяет
последовательность числовых и знаковых токенов ДО и ПОСЛЕ, и функция
`clean()` возвращает ИСХОДНЫЙ текст, если сверка не сошлась.

Что чиним автоматически (и почему это безопасно):
  * пробелы вокруг инлайновой математики — самый массовый класс
    (465 задач и 1 177 подпунктов, перепись 2026-08-06): «$x$и $y$фирма»
    вместо «$x$ и $y$ фирма». Пробел не может изменить число.
    ⚠️ Доллары спариваются ПОСЛЕДОВАТЕЛЬНО с начала текста — так же, как
    это делает KaTeX. Прикидка «регулярка $…$ перед буквой» даёт вдесятеро
    больше (4 924) и врёт: она с удовольствием спаривает ЗАКРЫВАЮЩИЙ
    доллар одной формулы с ОТКРЫВАЮЩИМ следующей и объявляет обычный текст
    между ними формулой;
  * операторы `min`/`max`/`log` внутри формулы получают обратный слеш —
    KaTeX рисует их курсивом как произведение переменных m·i·n;
(Скобку, открытую снаружи формулы и закрытую внутри — «($L)», — чинить
автоматически НЕЛЬЗЯ: замер по банку нашёл ровно один такой фрагмент, и
это оказался «($200 тыс. в год)», то есть доллар-валюта. Автоправка
превратила бы цену в формулу. Признак считается, текст не трогается.)

Чего НЕ чиним (сомнительное — в список, не в текст):
  * дефисный перенос «про-\\nизводительность». Ровно на этом стоит
    выключенный `AUTO_HYPHEN_JOIN` в `glue_pdf_lines`: «денежно-\\nкредитную»
    склеилось бы в «денежнокредитную». В условиях таких переносов всего 4;
  * сырой знак корня «√︀», вывалившийся из формулы: однозначно восстановить
    формулу нельзя, а догадка — это выдумка;
  * непарные доллары: где именно потерян разделитель, текст не сообщает.
    Более того, при нечётном числе долларов ЛЮБАЯ разметка ненадёжна —
    соседние формулы спариваются неправильно, — поэтому такой текст
    возвращается как есть целиком.
"""
import re

# Инлайновая и выключная математика. Порядок важен: `$$…$$` ищем раньше
# `$…$`, иначе двойной доллар распадётся на пустую формулу.
_MATH = re.compile(r'\$\$.+?\$\$|\$[^$\n]+?\$|\\\(.+?\\\)|\\\[.+?\\\]',
                   re.DOTALL)

# Числа и знаки — то, что чистка не имеет права трогать. Ловим ЦЕЛИКОМ
# число со знаком и дробной частью, иначе «−1,22» распадётся на «1» и «22».
_NUMBER = re.compile(r'[-−+]?\d+(?:[.,]\d+)?')
# LaTeX-запись десятичной запятой: «0{,}5» — то же число, что «0,5».
_LATEX_COMMA = re.compile(r'(?<=\d)\{,\}(?=\d)')

# Операторы, которые в математике обязаны быть командами.
_OPERATORS = ('min', 'max', 'log', 'ln', 'exp', 'lim', 'sin', 'cos', 'tan',
              'max', 'sup', 'inf')
_BARE_OPERATOR = re.compile(
    r'(?<![\\A-Za-z])(%s)(?![A-Za-z])' % '|'.join(sorted(set(_OPERATORS))))

# Признаки порчи, которые мы только СЧИТАЕМ (чинить нечем).
_HYPHEN_BREAK = re.compile(r'[А-Яа-яЁё]{2,}-\n[а-яё]{2,}')
_STRAY_ROOT = re.compile(r'√(?![\s\d(])|√︀|︀')


def number_tokens(text):
    """Последовательность чисел и знаков — отпечаток смысла текста.

    ⚠️ Сравниваем ПОСЛЕДОВАТЕЛЬНОСТЬ токенов всего поля, а не куски
    посимвольного диффа. Урок свипа Батча 2: «negative» и «positive» делят
    общий хвост «itive», и посимвольная разбивка режет слово мимо границ
    регулярки — подмена проходит незамеченной.
    """
    return _NUMBER.findall(_LATEX_COMMA.sub(',', text or ''))


def same_numbers_and_signs(before, after):
    """Не изменились ли числа и знаки. Единственный допуск к записи."""
    return number_tokens(before) == number_tokens(after)


def _split_math(text):
    """Текст → список кусков `(это_математика, кусок)`."""
    pieces = []
    position = 0
    for match in _MATH.finditer(text):
        if match.start() > position:
            pieces.append((False, text[position:match.start()]))
        pieces.append((True, match.group(0)))
        position = match.end()
    if position < len(text):
        pieces.append((False, text[position:]))
    return pieces


def _fix_operators(chunk):
    """`min` внутри формулы → `\\min`. Вне формулы не трогаем."""
    body = chunk
    return _BARE_OPERATOR.sub(lambda m: '\\' + m.group(1), body)


def _fix_spacing(pieces):
    """Пробел между формулой и словом. Самый массовый класс порчи.

    Пробел не меняет ни одного числа и ни одного знака — поэтому это
    единственная правка, которую можно делать не задумываясь.
    """
    out = []
    for index, (is_math, chunk) in enumerate(pieces):
        if is_math:
            previous = out[-1] if out else ''
            if previous and previous[-1].isalpha():
                out.append(' ')
            out.append(chunk)
            continue
        if index and chunk and (chunk[0].isalnum() or chunk[0] in '«("'):
            chunk = ' ' + chunk
        out.append(chunk)
    return ''.join(out)


def clean(text):
    """Привести текст в порядок. При любом сомнении возвращает исходный."""
    if not text or '$' not in text:
        return text or ''
    original = text
    # ⚠️ Нечётное число долларов — разметке верить нельзя: формулы
    # спариваются не с теми соседями, и «пробел после формулы» встаёт
    # посреди обычного текста. Такой текст не трогаем совсем.
    if text.count('$') % 2:
        return original
    try:
        pieces = [(is_math, _fix_operators(chunk) if is_math else chunk)
                  for is_math, chunk in _split_math(text)]
        result = _fix_spacing(pieces)
        result = re.sub(r'[ \t]{2,}', ' ', result)
    except Exception:  # чистка не имеет права уронить показ задачи
        return original
    # ⚠️ Последний рубеж: правка, изменившая хоть одно число или знак,
    # отменяется целиком. Дешевле показать грязный текст, чем неверный.
    if not same_numbers_and_signs(original, result):
        return original
    return result


def defects(text):
    """Какие признаки порчи есть в тексте. Для замера, не для правки."""
    text = text or ''
    found = set()
    pieces = _split_math(text)
    plain = ''.join(chunk for is_math, chunk in pieces if not is_math)
    for index, (is_math, chunk) in enumerate(pieces):
        if is_math:
            if _BARE_OPERATOR.search(chunk):
                found.add('bare_operator')
            previous = pieces[index - 1][1] if index else ''
            if previous and previous[-1:].isalpha():
                found.add('glued_math')
            following = (pieces[index + 1][1]
                         if index + 1 < len(pieces) else '')
            if following[:1].isalnum():
                found.add('glued_math')
    if _HYPHEN_BREAK.search(plain):
        found.add('hyphen_break')
    if _STRAY_ROOT.search(plain):
        found.add('stray_root')
    if text.count('$') % 2:
        found.add('odd_dollars')
    # Скобка открылась снаружи формулы, а закрылась внутри: «($L)».
    # Признак виден только при непарных долларах — иначе это обычное
    # «(см. $x$)». Отдельная метка нужна, чтобы отличить эти 1–2 случая
    # от общей кучи «непарных долларов».
    if text.count('$') % 2 and re.search(r'\(\$[^$()\n]{1,25}\)', text):
        found.add('bracket_across_math')
    return found


# Человеческие названия признаков — одни и те же в отчёте и в интерфейсе.
DEFECT_NAMES = {
    'glued_math': 'нет пробела между формулой и словом',
    'bare_operator': 'оператор в формуле без обратного слеша (min, log)',
    'hyphen_break': 'дефисный перенос строки посреди слова',
    'stray_root': 'сырой знак корня, вывалившийся из формулы',
    'odd_dollars': 'непарное число знаков доллара',
    'bracket_across_math': 'скобка открывается снаружи формулы, а закрывается внутри',
}

# Что чинится на лету, а что только считается. Список — не украшение:
# по нему видно, какая часть замера уже закрыта, а какая ждёт своей
# отдельной работы со стоп-гейтом.
FIXED_AUTOMATICALLY = ('glued_math', 'bare_operator')
REPORTED_ONLY = ('hyphen_break', 'stray_root', 'odd_dollars',
                'bracket_across_math')


def preview_title(problem, limit=90):
    """Название задачи для списков. Пусто — берём начало условия.

    ⚠️ Обрезаем ПО ГРАНИЦЕ СЛОВА. Раньше в подборе задач показывалось
    «...Всего в шта-» — обрубок посреди слова, да ещё с дефисом переноса:
    понять, что берёшь, по такой строке нельзя.
    """
    title = (getattr(problem, 'title', '') or '').strip()
    source = title or clean((getattr(problem, 'statement', '') or '').strip())
    source = re.sub(r'\s+', ' ', source).strip()
    if not source:
        return 'Задача #%s' % getattr(problem, 'pk', '')
    if len(source) <= limit:
        return source
    cut = source[:limit]
    space = cut.rfind(' ')
    if space > limit // 2:
        cut = cut[:space]
    # Дефис на срезе — остаток переноса, а не часть слова.
    return cut.rstrip(' ,;:.-–—') + '…'
