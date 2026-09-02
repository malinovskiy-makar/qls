"""Объединение классов у привязок к олимпиадам.

Зачем. Одну и ту же задачу олимпиада часто даёт нескольким параллелям
сразу, и источники записывают это по-разному: SolveHub кладёт готовый
диапазон одной строкой («7-11»), ILE — по строке на класс («10» в одной,
«11» в другой). Проверенный случай — `https://iloveeconomics.ru/z/2438`
(«Коэффициент Джини и рокировка»): у ILE она числится записями
`ile-proba-2011-10-1` и `ile-proba-2011-11-2`, потому что «Пробу» 2011
года с этой задачей писали и десятые, и одиннадцатые классы.

⚠️ РАСХОЖДЕНИЕ ТОЛЬКО ПО КЛАССУ — ЭТО НЕ КОНФЛИКТ. Пока `olympiad_slug`,
`year` и `stage` совпадают, разные `grade` описывают одну и ту же реальную
задачу и объединяются в диапазон. Конфликтом остаётся расхождение по
олимпиаде, году или этапу — там источники спорят о факте, и решать за
владельца нельзя.

⚠️ ЗНАЧЕНИЕ СЧИТАЕТСЯ НА ЛЕТУ, ОТДЕЛЬНОГО ПОЛЯ В БАЗЕ НЕТ. Причины — в
`docs/adr/0058-olympiad-grade-range.md`; коротко: источник правды живёт в
строках `OlympiadRef`, а они прибавляются при каждом прогоне пропагации,
и денормализованное поле устаревало бы молча.
"""
import re

# Классы записаны либо числом («9»), либо диапазоном через дефис («7-11»).
# Дефис уже приведён к обычному: значения приходят из экспорта, где
# юникодных тире не встречается (проверено по всем 18 различным значениям).
_GRADE_RANGE = re.compile(r'^\s*(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*$')
_GRADE_ONE = re.compile(r'^\s*(\d{1,2})\s*$')


def parse_grades(value) -> set:
    """Строка класса → множество чисел. «7-11» → {7,…,11}, «9» → {9}.

    Непонятное значение даёт пустое множество, а не исключение: класс —
    справочное поле, и незнакомый формат не повод ронять прогон по банку.
    Пустое множество отличимо от «класс не указан» только по контексту —
    оба случая означают «сказать про класс нечего».
    """
    text = (value or '').strip()
    if not text:
        return set()
    match = _GRADE_RANGE.match(text)
    if match:
        low, high = int(match.group(1)), int(match.group(2))
        if low > high:
            low, high = high, low
        return set(range(low, high + 1))
    match = _GRADE_ONE.match(text)
    if match:
        return {int(match.group(1))}
    return set()


def format_grades(numbers) -> str:
    """Множество чисел → читаемая запись: «10-11», «9-11», «5-7, 9».

    Подряд идущие классы схлопываются в диапазон, разрывы разделяются
    запятой. Два подряд идущих числа пишутся диапазоном («10-11»), а не
    «10, 11» — так их пишут сами олимпиады.
    """
    nums = sorted(set(numbers))
    if not nums:
        return ''
    runs = []
    start = previous = nums[0]
    for number in nums[1:]:
        if number == previous + 1:
            previous = number
            continue
        runs.append((start, previous))
        start = previous = number
    runs.append((start, previous))
    return ', '.join(
        str(low) if low == high else f'{low}-{high}' for low, high in runs)


def event_key(ref) -> tuple:
    """Что считаем «одним и тем же туром»: олимпиада, год, этап.

    Класс в ключ НЕ входит — в этом весь смысл: строки, различающиеся
    только классом, обязаны попасть в одну группу и слиться в диапазон.
    """
    return (ref.olympiad_slug, ref.year, ref.stage)


def merge_grades_by_event(refs) -> dict:
    """Строки `OlympiadRef` → {(слаг, год, этап): «объединённый класс»}.

    Принимает любой итерируемый набор строк — очередь одной задачи,
    выборку по нескольким задачам роли не играет, группировка идёт по
    ключу тура.
    """
    collected = {}
    for ref in refs:
        collected.setdefault(event_key(ref), set()).update(parse_grades(ref.grade))
    return {key: format_grades(nums) for key, nums in collected.items()}


def classify_refs(refs) -> str:
    """Как расходятся строки одной задачи: 'single' / 'agree' / 'grade_only' / 'conflict'.

    * `single`      — строка одна, сравнивать не с чем;
    * `agree`       — тур один и класс один, различаются только `event_id`
                      и прочая учётная мелочь;
    * `grade_only`  — тур один, классы разные. НЕ конфликт: объединяем;
    * `conflict`    — расходятся олимпиада, год или этап. Решает владелец.
    """
    refs = list(refs)
    if len(refs) < 2:
        return 'single'
    if len({event_key(r) for r in refs}) > 1:
        return 'conflict'
    if len({frozenset(parse_grades(r.grade)) for r in refs}) > 1:
        return 'grade_only'
    return 'agree'
