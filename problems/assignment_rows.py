"""
Единый список задач в работе — одна сборка на все экраны.

⚠️ ЗАЧЕМ ЭТОТ МОДУЛЬ. До него страница ученика собирала список задач в два
захода: цикл по старому M2M `Assignment.problems` (задачи каталога) и
отдельный цикл по `assignment.items` (свои задачи репетитора). Ученик видел
ДВЕ домашки с ДВУМЯ разными наборами полей ответа, а репетитор — один список
(его экран уже ходил только по позициям). Список задач обязан быть один и
тот же для обеих сторон, поэтому собирается он теперь ровно здесь.

ИСТОЧНИК ПРАВДЫ — `AssignmentItem` (позиция задачи в домашке). Старый M2M
оставлен для обратной совместимости и бэкфилла, но списки по нему больше
не строятся.

НАБОР ПОЛЕЙ ОТВЕТА ОДИН ДЛЯ ВСЕХ ЗАДАЧ:
  1. «Ответ»          — краткий, для автопроверки;
  2. «Моё решение»    — развёрнутый ход, с набором формул;
  3. «Прикрепить файл» — фото или PDF.
Меняется только ЭЛЕМЕНТ УПРАВЛЕНИЯ у первого поля: у теста это переключатели
(выбор и есть ответ), у открытой задачи — строка ввода. Это одно и то же поле
на одном и том же месте с одной и той же подписью, а не разные наборы:
предлагать «краткий ответ строкой» рядом с готовыми вариантами — значит
спрашивать одно и то же дважды.
"""
from decimal import Decimal

from django.db import IntegrityError, transaction

from problems import problem_types


# Как вводится ответ.
ANSWER_TEXT = 'text'          # строка (открытая задача)
ANSWER_RADIO = 'radio'        # один вариант
ANSWER_CHECKBOX = 'checkbox'  # несколько вариантов


def answer_input_name(item, part=None):
    """Имя поля ответа. Одно на все типы задач — иначе приёмник ответов
    снова разъедется на «если каталожная, то так».

    У задачи с пунктами поле СВОЁ НА КАЖДЫЙ ПУНКТ: `..._part_<pk>`. Иначе
    ответы на «а» и «б» приходят одной строкой, и автопроверить их нельзя
    в принципе.
    """
    if part is not None:
        return 'answer_item_%d_part_%s' % (item.pk, part_key(part))
    return 'answer_item_%d' % item.pk


def is_custom_part(part):
    """Пункт своей задачи репетитора? Признак — своя таблица."""
    from .models_platform import CustomProblemPart

    return isinstance(part, CustomProblemPart)


def part_key(part):
    """Ключ пункта в словарях ответов и в именах полей формы.

    ⚠️ ДВЕ ТАБЛИЦЫ — ДВА ПРОСТРАНСТВА НОМЕРОВ. Пункт №3 каталожной задачи и
    пункт №3 своей задачи репетитора — разные пункты, и голый номер их не
    различает. Пункт своей задачи помечаем «c».
    """
    if part is None:
        return None
    return ('c%d' % part.pk) if is_custom_part(part) else part.pk


def answer_row_key(answer):
    """Тот же ключ, но у сохранённой строки ответа (`PartAnswer`/черновик)."""
    if answer.part_id:
        return answer.part_id
    if getattr(answer, 'custom_part_id', None):
        return 'c%d' % answer.custom_part_id
    return None


def part_link(part):
    """Как записать ссылку на пункт: {'part': …} или {'custom_part': …}."""
    if part is None:
        return {'part': None, 'custom_part': None}
    if is_custom_part(part):
        return {'part': None, 'custom_part': part}
    return {'part': part, 'custom_part': None}


def display_parts(item):
    """Пункты, которые ПОКАЗЫВАЮТ в составе работы. Пустой список — их нет.

    ⚠️ ЗАЧЕМ ОТДЕЛЬНАЯ ФУНКЦИЯ И ПОЧЕМУ ОНА ПОЯВИЛАСЬ ПОЗДНО. Пункты своей
    задачи живут в СВОЕЙ таблице (`CustomProblemPart`), потому что
    `ProblemPart` ссылается на каталог. Когда её заводили, про неё узнала
    только сторона ВВОДА (`answer_parts` ниже), а сторона ПОКАЗА осталась
    как была: четыре экрана независимо писали
    `item.catalog_problem.parts.all()`, то есть спрашивали пункты у той
    половины позиции, которой у своей задачи нет вовсе. Ученик получал
    задачу без вопросов — на экране, в печати и в `.tex` одновременно.
    Отсюда правило: пункты спрашивает ОДНА функция, а не каждый экран сам.

    Отличие от `answer_parts`: та отвечает «на что ученик пишет ответ» и
    задачу без пунктов считает одним безымянным пунктом (`[None]`); эта
    отвечает «что нарисовать под условием» и пустоту возвращает пустотой.

    Пункты теста сюда НЕ попадают: там подпункты играют роль вариантов
    ответа, и списком под условием они нарисовались бы во второй раз.
    """
    kind, _ = item_answer_form(item)
    if kind != ANSWER_TEXT:
        return []
    if item.is_custom:
        if item.custom_problem is None:
            return []
        parts = item.custom_problem.parts.all()
    elif item.catalog_problem_id:
        parts = item.catalog_problem.parts.all()
    else:
        return []
    # Пункт без собственного условия — не вопрос, а мусор импорта («Ответ:»
    # без содержания, ~150 таких задач в банке). То же правило, что у
    # `answer_parts`: спрашивать по нему нечего, и рисовать нечего.
    return [p for p in parts if (p.statement or '').strip()]


def answer_gist(item):
    """Эталон одной строкой — для плашки «проверяется само» на задании.

    ⚠️ У ЗАДАЧИ С ПУНКТАМИ ЭТАЛОН ТОЖЕ ПО ПУНКТАМ. Плашка спрашивала
    `item.correct_answer` — ответ задачи ЦЕЛИКОМ, которого у задачи с
    пунктами нет по устройству (он живёт на пунктах). Пустая строка
    подставляла слова «задан разметкой», и экран уверял, что эталон есть,
    у задачи, где его вовсе не задавали.

    Пустая строка на выходе означает «эталона нет» — тогда машина проверять
    не станет (`part_grading.grade_part` возвращает «решает человек»), и
    плашка обязана говорить именно это.
    """
    pairs = []
    for part in display_parts(item):
        answer = (part.answer or '').strip()
        if answer:
            pairs.append('%s) %s' % ((part.label or '').rstrip(').'), answer))
    if pairs:
        return ' · '.join(pairs)
    answer = (item.correct_answer or '').strip()
    if answer:
        return answer
    # У теста верный вариант помечен в разметке, отдельной строкой его не
    # показать — но он ЕСТЬ, и это не то же самое, что пустой эталон.
    return 'задан разметкой' if item.is_test else ''


def answer_parts(item):
    """Пункты, на которые ученик отвечает ОТДЕЛЬНО. Всегда непустой список.

    ⚠️ Задача БЕЗ пунктов — частный случай «один пункт» (`None`). Так у
    ввода, автопроверки и показа результата ровно ОДИН путь кода; ветка
    «если пунктов нет, то по-другому» — то, из-за чего половина экранов
    этого проекта уже расходилась между собой.

    Пункты теста сюда НЕ попадают: там подпункты играют роль вариантов
    ответа, и отдельного поля ввода у каждого быть не должно.
    """
    if item.is_custom:
        # ⚠️ У СВОЕЙ ЗАДАЧИ ПУНКТЫ В СВОЕЙ ТАБЛИЦЕ (`CustomProblemPart`):
        # `ProblemPart` ссылается на каталог, куда задача репетитора не
        # попадает никогда. Поля названы одинаково, поэтому дальше по
        # конвейеру ветки «если пункт свой» нет.
        if item.custom_problem is None or item.custom_problem.is_test:
            return [None]
        parts = list(item.custom_problem.parts.all())
        parts = [p for p in parts if (p.statement or '').strip()]
        return parts or [None]
    if item.catalog_problem_id is None:
        return [None]
    kind, _ = item_answer_form(item)
    if kind != ANSWER_TEXT:
        return [None]
    parts = list(item.catalog_problem.parts.all())
    # Пункт без собственного условия — не вопрос, а мусор импорта
    # («Ответ:» без содержания, ~150 таких задач в банке). Спрашивать по
    # нему отдельный ответ не за что.
    parts = [p for p in parts if (p.statement or '').strip()]
    return parts or [None]


# ---------------------------------------------------------------------------
# Порядок задач в работе: сначала тесты, потом открытые задачи
# ---------------------------------------------------------------------------
# ⚠️ ОДНА СБОРКА НА ЭКРАН И НА ПЕЧАТЬ. Порядок задач на странице и порядок
# задач в листке обязаны совпадать: расхождение обнаружится на занятии, когда
# ученик назовёт номер задачи, а у репетитора под этим номером другая.

SECTION_TEST = 'test'
SECTION_TASK = 'task'
SECTION_TITLES = {SECTION_TEST: 'Тестовая часть', SECTION_TASK: 'Задачи'}

# Как считать содержимое части. У теста единица счёта — ВОПРОС, у открытой
# части — ЗАДАЧА: «Тестовая часть · 3 задачи» звучит так, будто в тесте
# лежат задачи, а в соседней части что-то другое.
SECTION_UNITS = {
    SECTION_TEST: ('вопрос', 'вопроса', 'вопросов'),
    SECTION_TASK: ('задача', 'задачи', 'задач'),
}
# Слово «балл» склоняется по тем же трём формам.
POINT_FORMS = ('балл', 'балла', 'баллов')


def section_detail(kind, count, points):
    """Состав части без названия: «3 вопроса · 6 баллов».

    ⚠️ СТРОКА СОБИРАЕТСЯ В ПИТОНЕ, А НЕ В ШАБЛОНЕ. Её показывают четыре
    экрана (задание, разбор работы, конструктор подборки, сводка решений)
    плюс печатный листок и `.tex`; собранная в шаблоне, она существовала бы
    в шести чуть разных видах, а в `.tex` шаблонных фильтров нет вовсе.

    Склонение — общая `templatetags.ru.pick`: в русском три формы, и
    «3 вопросов» на экране разрушает доверие к остальным числам.
    """
    from problems.scorefmt import ball
    from problems.templatetags.ru import pick

    unit = pick(count, *SECTION_UNITS.get(kind, SECTION_UNITS[SECTION_TASK]))
    parts = ['%s %s' % (count, unit)]
    if points is not None:
        # Балл печатает единственная точка (`scorefmt.ball`): «6», а не
        # «6,00». Ноль баллов — законное состояние, прочерк был бы враньём.
        #
        # ⚠️ У ДРОБНОГО ЧИСЛА ФОРМА ВСЕГДА РОДИТЕЛЬНАЯ: «1,5 балла», а не
        # «1,5 балл». Отбросить дробную часть и склонять по целому нельзя —
        # именно так и вышло бы «1,5 балл».
        parts.append(points_text(points))
    return ' · '.join(parts)


def point_word(points):
    """«балл» / «балла» / «баллов» под это число — ОДНО правило на проект.

    ⚠️ У ДРОБНОГО ЧИСЛА ФОРМА ВСЕГДА РОДИТЕЛЬНАЯ. Отбросить дробную часть
    и склонять по целому нельзя: именно так и выходило «1,5 балл».

    ⚠️ ВЫНЕСЕНО ИЗ `points_text` (ревью 17.08, п. 2.4). Там, где число и
    слово стоят РАЗНЫМИ элементами разметки (крупная цифра балла и подпись
    под ней), готовая строка не годится, и слово писали руками: на странице
    задания у позиции в три балла стояло «3 баллов». Правило склонения
    осталось одно, у него просто появился второй вход.
    """
    from problems.templatetags.ru import pick

    number = Decimal(str(points or 0))
    if number != number.to_integral_value():
        return POINT_FORMS[1]
    return pick(int(number), *POINT_FORMS)


def points_text(points):
    """«6 баллов» / «1,5 балла» — ЕДИНСТВЕННАЯ точка на весь проект."""
    from problems.scorefmt import ball

    number = Decimal(str(points))
    return '%s %s' % (ball(number, '0'), point_word(number))


def section_caption(kind, count, points):
    """То же с названием: «Тестовая часть · 3 вопроса · 6 баллов».

    Нужна там, где заголовок печатается ОДНОЙ строкой и разложить его на
    подпись и состав нечем: `.tex` и печатный листок.
    """
    return '%s · %s' % (SECTION_TITLES[kind],
                        section_detail(kind, count, points))


def item_section(item):
    """К какой части работы относится позиция."""
    return SECTION_TEST if item.is_test else SECTION_TASK


# Слово типа для чипа на карточке. В единственном числе: чип подписывает
# ОДНУ задачу, а заголовок части — сколько их («3 вопроса»).
KIND_LABELS = {SECTION_TEST: 'Тест', SECTION_TASK: 'Задача'}


def kind_label(item):
    """«Тест» или «Задача» — подпись типа у одной позиции."""
    return KIND_LABELS[item_section(item)]


def ordered_items(assignment, items=None):
    """Позиции работы в том порядке, в котором их видит человек.

    По умолчанию тесты идут первыми, открытые задачи — следом. Внутри
    каждой части сохраняется порядок, заданный репетитором (`order`, `id`):
    перестановка групповая, а не сортировка всего подряд.

    Если у работы поднят `manual_order` — не трогаем НИЧЕГО. Репетитор
    расставил задачи сам, и «умная» перестановка сломала бы замысел урока.
    """
    if items is None:
        items = list(assignment.items.order_by('order', 'id'))
    if getattr(assignment, 'manual_order', False):
        return list(items)
    tests = [i for i in items if item_section(i) == SECTION_TEST]
    tasks = [i for i in items if item_section(i) == SECTION_TASK]
    return tests + tasks


def section_marks(items):
    """Заголовки частей: {индекс первой позиции части: словарь состава}.

    Словарь: `kind` («test» / «task»), `title` («Тестовая часть»), `count`,
    `points`, `caption` («Тестовая часть · 3 вопроса · 6 баллов»).

    ⚠️ ВОЗВРАЩАЕТ СЛОВАРЬ, А НЕ СТРОКУ (ревью 15.08, фаза 7). Раньше здесь
    была одна подпись, и разделение частей читалось как мелкая серая черта
    посреди списка: владелец на приёмке сказал, что «изначально не видно,
    что у нас вообще существует такое разделение». Состав части — то, что
    делает подпись заголовком: сколько там вопросов и сколько это стоит.
    Считается ЗДЕСЬ, потому что здесь уже известны обе части целиком.

    Заголовок выдаётся ТОЛЬКО первой позиции каждой части и ТОЛЬКО когда
    список ДЕЙСТВИТЕЛЬНО поделён на две сплошные части.

    ⚠️ Проверяем сам список, а не флаг `manual_order`. Причина конкретная:
    при ручном порядке тесты и задачи чередуются, и подпись «Тестовая
    часть» встала бы посреди списка перед одним-единственным тестом, обещая
    часть, которой нет. Подпись обязана быть правдой о том, что под ней
    лежит, а не о том, какое правило мы применяли.

    Одни тесты или одни задачи — делить нечего, ни подписи, ни линии.
    """
    sections = [item_section(i) for i in items]
    if SECTION_TEST not in sections or SECTION_TASK not in sections:
        return {}
    # Две сплошные части — значит ровно одна смена признака по списку.
    switches = sum(1 for a, b in zip(sections, sections[1:]) if a != b)
    if switches != 1:
        return {}
    totals = {}
    for item, section in zip(items, sections):
        count, points = totals.get(section, (0, Decimal('0')))
        totals[section] = (count + 1, points + item_max_score(item))

    marks = {}
    seen = set()
    for index, section in enumerate(sections):
        if section not in seen:
            seen.add(section)
            count, points = totals[section]
            marks[index] = {
                'kind': section,
                'title': SECTION_TITLES[section],
                'count': count,
                'points': points,
                # «3 вопроса · 6 баллов» — для экрана, где название стоит
                # отдельным словом и набрано крупнее.
                'detail': section_detail(section, count, points),
                # Вся строка целиком — для печати и `.tex`.
                'caption': section_caption(section, count, points),
            }
    return marks


def whole_caption(items):
    """Состав работы ОДНОЙ строкой, когда делить её не на что.

    ⚠️ ЗАЧЕМ ОТДЕЛЬНАЯ ФУНКЦИЯ, А НЕ ПРАВКА `section_marks` (ревью 17.08,
    фаза 14). Та отвечает на вопрос «где проходит граница частей», и у
    работы из одних тестов границы нет — она честно молчит. Но у печатного
    листка и `.tex` от этого пропадала ВСЯКАЯ подпись состава: контрольная
    из одних тестов начиналась строкой «Вопрос 1.» сразу после названия, и
    понять, сколько там вопросов и сколько это стоит, было нельзя, пока не
    досчитаешь до конца. Здесь другой вопрос — «что это за работа целиком»,
    и ответ на него есть всегда.

    Возвращает такой же словарь, что и `section_marks`, или None, если
    работа смешанная (там подписи ставит `section_marks`) либо пуста.
    """
    if not items:
        return None
    sections = {item_section(i) for i in items}
    if len(sections) != 1:
        return None
    section = sections.pop()
    points = sum((item_max_score(i) for i in items), Decimal('0'))
    return {
        'kind': section,
        'title': SECTION_TITLES[section],
        'count': len(items),
        'points': points,
        'detail': section_detail(section, len(items), points),
        'caption': section_caption(section, len(items), points),
    }


def part_max_score(item, part, parts_count):
    """Максимум баллов за пункт.

    ⚠️ БАЛЛ ПОЗИЦИИ — ЕДИНСТВЕННАЯ ПРАВДА, А `ProblemPart.points` — ТОЛЬКО
    ВЕС ПУНКТА ВНУТРИ НЕЁ. Раньше балл пункта, если он был задан в
    каталоге, брался КАК ЕСТЬ и молча перебивал то, что поставил репетитор:
    демо-задача «Издержки фирмы» стоила на карточке 3 балла, а в сумме
    работы — 2, потому что у обоих её пунктов в каталоге стоит по единице.
    Крупная цифра на экране и итог работы расходились, а поле «максимум»
    из фазы 4 запирало бы число, которым система не пользуется.

    Каталог общий на всех репетиторов, позиция — решение конкретного
    человека для конкретной работы; спорить им нельзя, и выигрывает
    позиция. Веса при этом уважаются: если у «а» в каталоге стоит 1, а у
    «б» — 3, то из пяти баллов позиции пункты возьмут 1,25 и 3,75.

    Веса заданы не у всех пунктов — делим поровну: половина размеченных
    весов означает, что размечавший до конца не дошёл, и достраивать за
    него мы не имеем права.
    """
    from decimal import Decimal

    total = item_max_score(item)
    if parts_count <= 1 or part is None:
        return total

    parts = [p for p in answer_parts(item) if p is not None]
    if len(parts) != parts_count:
        return (total / Decimal(parts_count)).quantize(Decimal('0.01'))

    weights = [p.points for p in parts]
    if all(w is not None for w in weights) and sum(weights) > 0:
        shares = [Decimal(w) / Decimal(sum(weights)) for w in weights]
    else:
        # Вес есть не у всех пунктов — делим поровну, а не достраиваем за
        # того, кто размечал каталог и не дошёл до конца.
        shares = [Decimal(1) / Decimal(parts_count)] * parts_count

    # ⚠️ ОСТАТОК ОКРУГЛЕНИЯ ОТДАЁМ ПОСЛЕДНЕМУ ПУНКТУ. Иначе задача на 10
    # баллов из трёх пунктов складывается в «9,99 б.» — ровно это и стояло
    # на экране разбора работы.
    values = [(total * share).quantize(Decimal('0.01')) for share in shares]
    values[-1] = total - sum(values[:-1])
    return values[parts.index(part)]


def item_max_score(item):
    """Сколько стоит задача целиком. ЕДИНСТВЕННАЯ точка вопроса.

    ⚠️ Из-за отсутствия этой точки сессия 3 уехала в самый дорогой класс
    ошибки — несправедливую оценку. Автопроверка каталожного теста
    (`student/views.py::auto_check_submission`) была написана до появления
    `AssignmentItem` и ставила за верный ответ жёстко зашитую ЕДИНИЦУ,
    а максимум везде читался из `points`. Полностью верный ответ на тест
    ценой 3 балла давал «1 / 3» и вердикт «ЧАСТИЧНО» — при комментарии
    «Верно ✓» в той же карточке.

    Балл не задан — задача стоит единицу: так считает вся остальная
    система (`part_max_score`, `work_review._item_max`). После миграции
    0032 пустых баллов в базе нет (новым позициям балл проставляет
    `AssignmentItem.save()`: 10 задаче, 3 тесту), но запасной путь оставлен —
    позиция может прийти из старой фикстуры.
    """
    from decimal import Decimal

    from .models_platform import LEGACY_POINTS

    if item.points is not None:
        return Decimal(str(item.points))
    return LEGACY_POINTS


def part_correct_answer(item, part):
    """Эталонный ответ на пункт (или на задачу целиком, если пункт None).

    ⚠️ УТВЕРЖДЁННЫЙ РЕПЕТИТОРОМ ОТВЕТ ГЛАВНЕЕ КАТАЛОЖНОГО. Каталог
    остаётся нетронутым, но проверяется то, что подтвердил живой человек
    (`AssignmentItem.answer_override`). Так задача без ответа становится
    автопроверяемой, а задача с «ответом», который на самом деле фраза из
    решения, — перестаёт калечить оценку.
    """
    approved = item.approved_answer(part)
    if approved:
        return approved
    if part is not None:
        return (part.answer or '').strip()
    return (item.correct_answer or '').strip()


def part_tolerance(item, part):
    """Допуск сравнения. У пункта СВОЙ, у задачи целиком — общий.

    ⚠️ Допуск спрашиваем только у СВОЕЙ задачи: там его писал живой человек
    именно как допуск. У каталожной задачи такого поля нет вовсе.
    """
    if not item.is_custom:
        return 0
    if part is not None and is_custom_part(part):
        return part.answer_tolerance
    if item.custom_problem is not None:
        return item.custom_problem.answer_tolerance
    return 0


def catalog_answer_for(item, part):
    """Что предлагает КАТАЛОГ — для показа рядом с полем утверждения."""
    if part is not None:
        return (part.answer or '').strip()
    return (item.correct_answer or '').strip()


def solution_input_name(item):
    return 'text_item_%d' % item.pk


def file_input_name(item):
    return 'file_item_%d' % item.pk


def item_answer_form(item):
    """(вид ввода, варианты) для позиции.

    Варианты — список словарей `{'value', 'label'}`. `value` это
    то, что уедет в `Submission.submitted_answer`: у каталожного теста —
    метка подпункта («а»), у своей задачи — id варианта. Так автопроверка
    в обоих случаях сравнивает ровно то, что хранит.
    """
    if item.is_custom:
        problem = item.custom_problem
        if problem is None or not problem.is_test:
            return ANSWER_TEXT, []
        kind = (ANSWER_CHECKBOX
                if problem.kind == problem.Kind.MULTIPLE else ANSWER_RADIO)
        options = [{'value': str(o.pk), 'label': o.text}
                   for o in problem.options.all()]
        return kind, options

    problem = item.catalog_problem
    if problem is None:
        return ANSWER_TEXT, []
    parts = list(problem.parts.all())
    if not problem_types.is_test(problem.problem_type) or not parts:
        return ANSWER_TEXT, []

    # ⚠️ Флага `is_html` здесь БОЛЬШЕ НЕТ (сессия 3Б, фаза 2). Он стоял в
    # True у текста подпункта каталожной задачи, и шаблоны из-за него
    # выводили корпусный текст через `|safe`. Тот же текст на публичной
    # странице каталога всегда рисовался экранированным — значит, сырой
    # HTML корпусу не нужен, а флаг лишь открывал дорогу нагрузке.
    options = [{'value': p.label, 'label': p.statement,
                'part_label': p.label}
               for p in parts]
    # ⚠️ ГАЛОЧКИ ТОЛЬКО У «ВСЕХ ВЕРНЫХ». «Верно/неверно» раньше тоже рисовался
    # галочками — и ученик мог отметить «Верно» И «Неверно» одновременно.
    # Замер по банку: из 455 задач этого типа 454 устроены как ОДНО
    # утверждение с двумя вариантами «Верно»/«Неверно», то есть это выбор
    # ОДНОГО варианта, а не подмножества. Единственное исключение —
    # наша собственная демо-задача с враньём в типе (починена в seed).
    if problem_types.test_kind(problem.problem_type) == problem_types.MULTI:
        return ANSWER_CHECKBOX, options
    return ANSWER_RADIO, options


def correct_option_values(item):
    """Множество ЗНАЧЕНИЙ верных вариантов — в той же системе, что `value`
    у `item_answer_form`. У каталожного теста это метки («а»), у своей
    задачи — id вариантов.

    Одна функция на оба вида: разбор работы, автопроверка и экспорт обязаны
    считать «верное» одинаково, иначе ученик увидит зелёную галочку там, где
    ему поставили ноль.
    """
    from .answer_check import catalog_test_correct_labels, normalize_label

    if item.is_custom:
        problem = item.custom_problem
        if problem is None:
            return set()
        return {str(pk) for pk in problem.correct_option_ids()}
    problem = item.catalog_problem
    if problem is None:
        return set()
    return {normalize_label(label)
            for label in catalog_test_correct_labels(problem)}


def option_review(item, submission):
    """Варианты глазами разбора: что ученик выбрал и что было верным.

    ⚠️ ЗАЧЕМ. В разборе ответ ученика показывался ТЕКСТОМ («Технология
    производства, Цены на ресурсы»), а верный ответ — БУКВАМИ («а, б, г»).
    Сверить это глазами невозможно: чтобы понять, где ошибся, ученику надо
    было держать в голове соответствие «буква ↔ формулировка».

    Возвращает список вариантов с полем `state`, у которого ровно четыре
    значения — по числу настоящих исходов:
      `hit`    — выбрал, и это верный вариант;
      `wrong`  — выбрал, а вариант неверный;
      `missed` — не выбрал, а надо было;
      `skip`   — не выбрал, и правильно сделал.
    Пустой список означает «у задачи нет вариантов» — тогда разбор рисует
    обычный ответ строкой.
    """
    from .answer_check import normalize_label

    kind, options = item_answer_form(item)
    if kind == ANSWER_TEXT or not options:
        return []

    raw = (submission.submitted_answer or '') if submission is not None else ''
    chosen = selected_values(raw)
    if not item.is_custom:
        # У каталожного теста значение — метка, и она приходит из формы в
        # том виде, в каком её напечатал шаблон: «б» и «Б)» это один вариант.
        chosen = {normalize_label(value) for value in chosen}
    correct = correct_option_values(item)

    rows = []
    for option in options:
        value = (normalize_label(option['value']) if not item.is_custom
                 else str(option['value']))
        is_chosen = value in chosen
        is_correct = value in correct
        if is_chosen and is_correct:
            state = 'hit'
        elif is_chosen:
            state = 'wrong'
        elif is_correct:
            state = 'missed'
        else:
            state = 'skip'
        rows.append({
            'label': option.get('part_label') or '',
            'text': option['label'],
            'chosen': is_chosen,
            'correct': is_correct,
            'state': state,
        })
    return rows


def get_or_create_submission(student, assignment, item):
    """Решение ученика по ПОЗИЦИИ. Никогда не заводит вторую запись.

    Порядок поиска именно такой:
    1. по позиции — точный адрес;
    2. по задаче каталога без позиции — так адресовались решения ДО появления
       позиций; такую запись мы усыновляем (проставляем `problem_item`),
       а не заводим рядом вторую, иначе прошлые ответы ученика исчезли бы
       с экрана.
    """
    from .models import Submission

    sub = Submission.objects.filter(student=student, problem_item=item).first()
    if sub is not None:
        return sub

    if item.catalog_problem_id:
        legacy = Submission.objects.filter(
            student=student, assignment=assignment,
            problem_id=item.catalog_problem_id,
            problem_item__isnull=True).first()
        if legacy is not None:
            legacy.problem_item = item
            legacy.save(update_fields=['problem_item'])
            return legacy

    # Обычный случай — записи ещё нет. `problem` заполняем ради старого кода
    # (он ищет решения по задаче), но если эта же задача уже занимает пару
    # (ученик, домашка, задача) другой позицией — оставляем пустым: адрес
    # решения всё равно даёт позиция.
    try:
        with transaction.atomic():
            return Submission.objects.create(
                student=student, assignment=assignment, problem_item=item,
                problem_id=item.catalog_problem_id, status='not_started')
    except IntegrityError:
        return Submission.objects.create(
            student=student, assignment=assignment, problem_item=item,
            problem=None, status='not_started')


def submitted_display(item, submission):
    """Ответ ученика человеческими словами.

    В базе у теста лежат id вариантов или метки подпунктов — показывать их
    ученику бессмысленно («вы ответили: 47»).
    """
    raw = (submission.submitted_answer or '').strip() if submission else ''
    if not raw:
        return ''
    kind, options = item_answer_form(item)
    if kind == ANSWER_TEXT or not options:
        return raw
    chosen = {v.strip() for v in raw.split(',') if v.strip()}
    labels = [o['label'] for o in options if o['value'] in chosen]
    return ', '.join(labels) if labels else raw


# Как называется состояние задачи для ученика. Ключи — те же, что у
# `Submission.status`, плюс правило для «в работе».
STATUS_LABELS = {
    'not_started': 'Не начата',
    'in_progress': 'В работе',
    'submitted': 'Отправлено',
    'reviewed': 'Проверено',
}


def work_status(submission, answer='', solution=''):
    """Состояние задачи ГЛАЗАМИ УЧЕНИКА.

    ⚠️ «В работе» считается по НАПИСАННОМУ, а не по отправленному. Во время
    контрольной ответы лежат в черновике и `Submission.status` остаётся
    `not_started` до самой сдачи — ученик видел «Не начата» над задачей, в
    которую только что вписал ответ. Ничего страшнее непонимания это не
    вызывало, но доверие к экрану ломало сразу.
    """
    status = submission.status if submission is not None else 'not_started'
    if status in ('submitted', 'reviewed'):
        return status
    if (answer or '').strip() or (solution or '').strip():
        return 'in_progress'
    return status if status in STATUS_LABELS else 'not_started'


def apply_draft(row, drafts):
    """Кладёт черновики контрольной в строку и пересчитывает состояние.

    `drafts` — словарь {id пункта или None: черновик} по ЭТОЙ позиции.
    Одна точка: иначе экран прохождения и счётчик в шапке начнут считать
    «начато» по разным правилам.
    """
    drafts = drafts or {}
    whole = drafts.get(None)
    row['prefill_solution'] = whole.solution_draft if whole else ''

    # Ответы по пунктам. У задачи без пунктов в списке ровно одна строка
    # с `part = None` — тот же код, что и для «а)/б)».
    answers = []
    for part_row in row.get('answer_parts') or []:
        draft = drafts.get(part_key(part_row['part']))
        part_row['given'] = draft.answer_draft if draft else ''
        answers.append(part_row['given'])

    if row.get('answer_parts'):
        row['prefill_answer'] = '; '.join(a for a in answers if a.strip())
    else:
        row['prefill_answer'] = whole.answer_draft if whole else ''
    row['selected'] = selected_values(row['prefill_answer'])
    row['answered'] = bool((row['prefill_answer'] or '').strip()
                           or (row['prefill_solution'] or '').strip())
    row['status'] = work_status(row['sub'], row['prefill_answer'],
                                row['prefill_solution'])
    row['status_label'] = STATUS_LABELS[row['status']]
    return row


def selected_values(answer):
    """Множество выбранных вариантов из строки ответа.

    Нужно, чтобы при возврате на страницу отметки в переключателях стояли
    там же, где их поставил ученик.
    """
    return {value.strip() for value in (answer or '').split(',')
            if value.strip()}


def _part_rows(item, submission, stored=None):
    """Строки пунктов. Тестам не нужны — у них подпункты это варианты."""
    from .part_grading import applies, part_rows

    if not applies(item):
        return []
    return part_rows(item, submission, stored=stored)


def _has_real_parts(item):
    """Настоящие пункты «а)/б)», а не единственный «вся задача»."""
    from .part_grading import applies, has_parts

    return applies(item) and has_parts(item)


def build_rows(assignment, student, user=None, with_comments=True):
    """Единый список позиций домашки — то, что рисуют обе стороны.

    `student` — чьи решения показываем; `user` — кто смотрит (от него зависит
    видимость решалки и комментариев). У ученика это один и тот же человек.
    """
    from .models import ProblemComment

    user = user or student

    items = ordered_items(assignment, list(
        assignment.items
        .select_related('catalog_problem', 'custom_problem', 'graph')
        .prefetch_related('catalog_problem__parts', 'catalog_problem__hints',
                          'custom_problem__options', 'custom_problem__parts')
        .order_by('order', 'id')))
    marks = section_marks(items)

    comments_by_item = {}
    if with_comments and items:
        for comment in (ProblemComment.objects.visible_for(user)
                        .filter(assignment=assignment)
                        .select_related('author', 'assignment',
                                        'assignment__group')):
            # Пометка видимости — ТА ЖЕ функция, что у репетитора. Два
            # места, решающих «как это подписать», разошлись бы, и один
            # экран говорил бы про сообщение не то, что соседний.
            comment.note = comment.note_for(user)
            comments_by_item.setdefault(comment.problem_item_id,
                                        []).append(comment)

    # ⚠️ Решения, проверки и ответы по пунктам подтягиваем ОДНИМ заходом.
    # Без этого экран разбора делал по три запроса на задачу и упирался в
    # потолок 30 запросов на восьми задачах (поймано тестом бюджета).
    known = {}
    if items:
        from .models import Submission

        known = {s.problem_item_id: s for s in Submission.objects.filter(
            student=student, assignment=assignment,
            problem_item__in=[i.pk for i in items])
            .select_related('feedback')
            .prefetch_related('part_answers__part', 'part_answers__custom_part',
            'feedback__mistakes')}

    rows = []
    for number, item in enumerate(items, start=1):
        submission = known.get(item.pk)
        if submission is None:
            submission = get_or_create_submission(student, assignment, item)
            stored = None
        else:
            stored = {answer_row_key(a): a
                      for a in submission.part_answers.all()}
        kind, options = item_answer_form(item)
        problem = item.problem
        status = work_status(submission, submission.submitted_answer,
                             submission.solution_text)
        # Считаем ОДИН раз: значение нужно и флагу для шаблона, и решению
        # о том, класть ли сам текст решения в контекст.
        solution_visible = item.is_solution_visible_for(user)
        rows.append({
            'item': item,
            'number': number,
            # Подпись части («Тестовая часть» / «Задачи») стоит у ПЕРВОЙ
            # позиции части и только когда частей две. Пусто — рисовать
            # нечего.
            'section': item_section(item),
            'section_head': marks.get(number - 1),
            'problem': problem,
            'title': item.problem_title,
            'statement': item.statement,
            # Подпункты показываем только когда они НЕ варианты ответа:
            # иначе один и тот же список нарисовался бы дважды. Спрашивает
            # их ОДНА функция — она знает и про свои задачи репетитора.
            'parts': display_parts(item),
            'hints': (list(item.catalog_problem.hints.all())
                      if item.catalog_problem_id else []),
            'answer_kind': kind,
            'options': options,
            # Пункты с ОТДЕЛЬНЫМ ответом на каждый. У задачи без пунктов —
            # ровно одна строка «вся задача»: один путь кода на все случаи.
            'answer_parts': _part_rows(item, submission, stored),
            'has_real_parts': _has_real_parts(item),
            # Верный ответ показываем только после сдачи — до неё это
            # подсказка, а не обратная связь. По той же причине разбор
            # вариантов СОБИРАЕТСЯ только после сдачи: положить его в
            # контекст страницы решения значило бы отдать ответы браузеру.
            'show_correct': submission.status in ('submitted', 'reviewed'),
            'option_review': (option_review(item, submission)
                              if submission.status in ('submitted', 'reviewed')
                              else []),
            'answer_name': answer_input_name(item),
            'solution_name': solution_input_name(item),
            'file_name': file_input_name(item),
            'sub': submission,
            # Чем заполнить поля. Обычно это уже отправленный ответ, но на
            # контрольной сюда кладётся ЧЕРНОВИК: ученик, вернувшийся после
            # обрыва связи, обязан увидеть написанное, а не пустую форму.
            'prefill_answer': submission.submitted_answer or '',
            'prefill_solution': submission.solution_text or '',
            'feedback': getattr(submission, 'feedback', None),
            'answer_display': submitted_display(item, submission),
            'is_done': submission.status in ('submitted', 'reviewed'),
            'status': status,
            'status_label': STATUS_LABELS[status],
            'answered': bool((submission.submitted_answer or '').strip()
                             or (submission.solution_text or '').strip()),
            'selected': selected_values(submission.submitted_answer),
            'comments': comments_by_item.get(item.pk, []),
            'solution_visible': solution_visible,
            'solution_hint': item.solution_unlock_hint(),
            'has_solution': item.has_solution,
            # ⚠️ ТЕКСТ РЕШЕНИЯ КЛАДЁТСЯ, ТОЛЬКО ЕСЛИ ЕГО МОЖНО ПОКАЗАТЬ.
            # Раньше здесь стояло безусловное `item.solution_text`, а прятал
            # решение шаблон — по соседнему флагу `solution_visible`. Проверено
            # опытом: достаточно убрать один `{% if %}` в `_problem_card.html`,
            # и эталонное решение уезжает ученику прямо посреди контрольной.
            # Шаблонов, рисующих эту строку, четыре, и забыть условие можно в
            # любом из них.
            #
            # Теперь правило серверное: не видно — не отдаём. `has_solution` и
            # `solution_hint` рядом остаются намеренно: ученику надо сказать,
            # что решение существует и когда откроется, не показывая его.
            'solution_text': item.solution_text if solution_visible else '',
            'graph': item.graph,
        })
    # ⚠️ ВЕРДИКТ СЧИТАЕТ ОДНА ФУНКЦИЯ (ревью 15.08, фаза 6). Плашка результата
    # красится по состоянию задачи, а не по признаку «проверил человек», и
    # состояние ей нужно на КАЖДОМ экране, где она стоит: и в разборе работы,
    # и на карточке домашки у ученика. Разбор считает состояние точнее (он
    # знает баллы по пунктам) и своё значение перебивает — но формула у обоих
    # одна, `work_review.state_of`.
    from decimal import Decimal

    from .work_review import state_of, state_word

    for row in rows:
        feedback = row['feedback']
        score = (Decimal(str(feedback.score))
                 if feedback is not None and feedback.score is not None
                 else None)
        if row['sub'].status not in ('submitted', 'reviewed') or score is None:
            row['fb_state'] = ''
            row['fb_verdict'] = ''
            continue
        row['fb_state'] = state_of(score, item_max_score(row['item']))
        row['fb_verdict'] = state_word(row['fb_state'])
    return rows


def read_answer(request, item):
    """Ответ, решение и файл из POST — одинаково для любой задачи.

    Галочки приходят несколькими значениями под одним именем, поэтому
    `getlist`; для строки и переключателя список из одного элемента.

    У задачи с пунктами ответ СОБИРАЕТСЯ из полей пунктов — строка нужна
    старым экранам (таблица решений, экспорт), а правда живёт в
    `PartAnswer`. Двух независимых источников ответа не заводим.
    """
    kind, _ = item_answer_form(item)
    if kind == ANSWER_CHECKBOX:
        answer = ', '.join(v.strip() for v in
                           request.POST.getlist(answer_input_name(item))
                           if v.strip())
    else:
        from .part_grading import join_answers, read_part_answers

        answer = join_answers(item, read_part_answers(request, item))
    text = (request.POST.get(solution_input_name(item)) or '').strip()
    file = request.FILES.get(file_input_name(item))
    return answer, text, file
