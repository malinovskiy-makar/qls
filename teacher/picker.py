"""
Отбор задач из каталога — ОДИН механизм на домашку и на контрольную.

⚠️ ЗАЧЕМ ЭТОТ МОДУЛЬ. Конструктор контрольной предлагал выбирать задачи
ТОЛЬКО из сохранённых репетитором — это было моё решение прошлой сессии с
обоснованием «поиск по 31 тысяче задач это лотерея». Обоснование неверное:
поиск, фильтры и корзина у конструктора домашек уже есть и работают, а
сохранённые — это быстрый доступ, а не единственный путь. Ручная проверка
признала контрольную в таком виде непригодной для работы.

Второго конструктора не пишем: разъедутся не экраны, а СОСТАВ работы —
в одном будут доступны свои задачи репетитора, в другом нет, в одном
фильтр по сложности, в другом нет. Здесь живёт серверная половина отбора,
разметка — в партиалах `teacher/_picker_*.html`.
"""
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, Value, When

from problems.hw_generator import is_test_problem
from problems.text_clean import preview_title

# ⚠️ СОРТИРОВКА ОТБОРА — ТРИ ВАРИАНТА И ОДИН ИСТОЧНИК ПРАВДЫ (ревью 17.08,
# фаза 8). Ключи едут в адресе (`?sort=`), подписи рисует шаблон отсюда же:
# список из двух мест разъехался бы на первой правке.
#
# ⚠️ «Подходящие по теме» — это НЕ пустая сортировка с красивым названием.
# Считаются два признака: совпало ли слово запроса в НАЗВАНИИ (а не только
# где-то в условии) и насколько задача сосредоточена на выбранной теме —
# задача с одной темой про неё, задача с пятью темами задевает её краем.
# Ни того ни другого «по номеру задачи» не даёт.
SORTS = (
    ('fit', 'сначала подходящие по теме'),
    ('easy', 'сначала простые'),
    ('hard', 'сначала сложные'),
)
SORT_KEYS = tuple(key for key, _ in SORTS)

# ⚠️ КОРЗИНА ОДНА НА СОБИРАЕМУЮ РАБОТУ (ревью 15.08, п. 11.1). Их было две
# — `hw_cart` и `exam_cart`, — и переключатель «Домашка / Контрольная» это
# ПЕРЕХОД ПО ССЫЛКЕ: уходя на соседний экран, репетитор терял всё, что уже
# отобрал. Разделение заводилось ради «недособранная домашка не утечёт в
# контрольную», но одновременно две работы не собирают, а вид работы — это
# уточнение к той же работе, а не другая работа.
CART_KEY = 'work_cart'

# ⚠️ КОРЗИНА ПРИВЯЗАНА К ЗАНЯТИЮ. Ключ один на вид работы, но НЕ один на
# все занятия: собранное для «Экономики 10–11» не имеет права всплыть в
# индивидуальном занятии Марии — вкладка одна, а работы разные. Занятие
# неизвестно (общий конструктор домашки без `?group=`) — храним под нулём.
#
# ⚠️ ПОЧЕМУ КЛЮЧИ СОБИРАЕТ СЕРВЕР. Прежде их писали руками в четырёх
# шаблонах, и на экране «Описать словами» переменная `cart_key` в контекст
# не попадала вовсе: `{{ cart_key }}` рисовалось ПУСТОЙ строкой, а
# `sessionStorage.setItem('', …)` — законная запись в ключ с пустым именем.
# Подобранное по описанию уезжало туда, конструктор читал `work_cart` и
# показывал прошлую корзину. Экран при этом был непустой, и понять, что
# подбор пропал, было нельзя.
SETTINGS_KEY = 'hw_settings'
MANUAL_ORDER_KEY = 'hw_manual_order'

# ⚠️ БАЛЛЫ ХРАНЯТСЯ РЯДОМ С КОРЗИНОЙ, И ЭТО НЕ УДОБСТВО (ревью 17.08, ф. 1).
# До этой правки наменянные баллы жили ТОЛЬКО в памяти страницы: шаг
# «Состав» показывал их правильно, а шаг «Выдача» открывался с пустым
# списком правок и отправлял в создание работы пустое поле `problem_points`
# — балл позиции ставился заново значением по умолчанию. Репетитор видел
# «2 балла», ученик получал работу на 6.
#
# В хранилище едут ТОЛЬКО РУЧНЫЕ ПРАВКИ: наличие ключа здесь и есть признак
# «этого числа правило больше не касается». Остальные позиции считает
# правило начисления, и второй памяти о них не заводим — разошлась бы.
POINTS_KEY = 'work_points'
RULE_KEY = 'work_rule'

# Хранилища прошлых версий. `hw_cart`/`exam_cart` — две корзины до их
# слияния; пустое имя — след того самого дефекта. Ни одно из них больше
# не читается, и держать их в сессии незачем.
JUNK_KEYS = ('hw_cart', 'exam_cart', '')


def storage_keys(group_id=None):
    """Имена хранилищ этого занятия — ОДНА точка на весь клиент.

    `migrate` — пары «откуда → куда»: общие ключи прошлой версии могли
    держать корзину прямо сейчас, и она обязана переехать, а не пропасть.
    `junk` — то, что не читает никто и можно стирать сразу.
    """
    suffix = ':%s' % (group_id or 0)
    keys = {
        'cart': CART_KEY + suffix,
        'order': CART_KEY + suffix + '_order',
        'settings': SETTINGS_KEY + suffix,
        'manual': MANUAL_ORDER_KEY + suffix,
        # Ручные баллы позиций и правило начисления — той же привязкой к
        # занятию, что корзина: две собираемые работы не имеют права делить
        # ни состав, ни цены позиций.
        'points': POINTS_KEY + suffix,
        'rule': RULE_KEY + suffix,
    }
    keys['migrate'] = [
        [CART_KEY, keys['cart']],
        [CART_KEY + '_order', keys['order']],
        [SETTINGS_KEY, keys['settings']],
        [MANUAL_ORDER_KEY, keys['manual']],
    ]
    keys['junk'] = list(JUNK_KEYS)
    return keys


# ── Правило начисления баллов ────────────────────────────────────────────
# ⚠️ ОДНО МЕСТО, ГДЕ РЕШАЕТСЯ «СКОЛЬКО СТОИТ ПОЗИЦИЯ» (решение владельца от
# 17.08). Правило задаётся на шаге «Выдача» и применяется СЕРВЕРОМ — и при
# показе состава, и при записи работы. Клиент правило только выбирает: пока
# он считал баллы сам, экран и запись расходились молча.
RULE_DIFFICULTY = 'difficulty'
RULE_FLAT = 'flat'
DEFAULT_FLAT_POINTS = 3


def parse_rule(raw):
    """Разбор правила начисления: «difficulty» или «flat:2» → словарь.

    Мусор и пустая строка дают правило по сложности задачи — то же, что
    видит репетитор, открывший поток и не трогавший настройку.
    """
    from decimal import Decimal, InvalidOperation

    mode, _, value = (raw or '').strip().partition(':')
    value = value.strip().replace(',', '.')
    # ⚠️ ПУСТОЕ ЧИСЛО — ЭТО НЕ НОЛЬ. «flat:» без числа означает, что правило
    # не задано; прочти его как «одинаково по 0 б.» — и вся работа молча
    # стала бы работой на ноль баллов.
    if mode != RULE_FLAT or not value:
        return {'mode': RULE_DIFFICULTY}
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        return {'mode': RULE_DIFFICULTY}
    if number < 0 or number > 1000:
        return {'mode': RULE_DIFFICULTY}
    return {'mode': RULE_FLAT, 'value': number}


def rule_points(rule, is_test, difficulty):
    """Балл позиции по действующему правилу. Возвращает Decimal."""
    from problems.models_platform import suggested_points

    if rule and rule.get('mode') == RULE_FLAT:
        return rule['value']
    return suggested_points(is_test, difficulty)



def card_meta(topics, problem_type, difficulty):
    """Тема · тип · сложность СЛОВАМИ — одной тихой строкой.

    ⚠️ Сложность словами, а не звёздочками: «сложность 2 из 5» читается
    сразу, а пять символов ★☆☆☆☆ приходится пересчитывать глазами. Ряд
    цветных тегов рядом с ними перетягивал внимание с кнопки «Добавить»,
    которая и есть главное действие экрана.
    """
    parts = []
    if topics:
        parts.append(topics[0].name)
    if problem_type:
        parts.append(problem_type)
    # ⚠️ НОЛЬ — ЭТО «НЕ УКАЗАНА», А НЕ «САМАЯ ЛЁГКАЯ» (ревью 16.08, п. 7.2).
    # Молчать о ней тоже нельзя: строка «тема · тип» без третьего слова
    # читается как «сложность где-то есть, просто не поместилась».
    parts.append('сложность %d из 5' % difficulty if difficulty
                 else 'сложность не указана')
    return ' · '.join(parts)

def word_cut(text, limit):
    """Обрезка по границе слова. Пусто/коротко — возвращаем как есть.

    Отдельной функцией, потому что нужна в нескольких местах, а рвать числа
    посередине нельзя нигде.
    """
    text = (text or '').strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(' ')
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(' ,;:.-–—') + '…'

def strip_latex(text):
    """Условие без формул — для превью в карточке."""
    from .views import _strip_latex

    return _strip_latex(text)


def source_label(problem):
    """Откуда задача — одной строкой: «ВсОШ · регион · 2019 · 9–11 класс».

    ⚠️ ПЕЧАТАЕМ ТОЛЬКО ТО, ЧТО ЕСТЬ В ДАННЫХ (ревью 17.08, фаза 8). У части
    банка заполнен один источник без года и класса, у ВсОШ — всё четыре
    поля. Подставлять недостающее нечем, а строка «источник · — · — » хуже
    короткой: она обещает сведения, которых нет.
    """
    reference = None
    for candidate in problem.source_references.all():
        reference = candidate
        break
    if reference is None:
        return ''
    parts = [reference.source.name]
    for value in (reference.stage, reference.year, reference.grade):
        text = str(value or '').strip()
        if not text:
            continue
        # ⚠️ ЭТАП НЕ ПОВТОРЯЕМ, ЕСЛИ ОН УЖЕ В НАЗВАНИИ ИСТОЧНИКА (ревью
        # 17.08, п. 7.4). Выходило «ВсОШ — региональный этап · региональный
        # · 2016 · 9, 10, 11 класс»: сравнение шло на ПОЛНОЕ совпадение
        # строки, а «региональный» и «ВсОШ — региональный этап» не равны.
        if any(text.lower() in known.lower() for known in parts):
            continue
        parts.append(text + (' класс' if value is reference.grade else ''))
    return ' · '.join(parts)


def card_facts(problem, is_test, parts_count):
    """Чипы карточки отбора: тип, сложность, решение — и справка о пунктах.

    Возвращает список словарей `{kind, text}`. Условие «печатаем только то,
    что есть» то же, что у `source_label`: «0 пунктов» не бывает, задача
    без пунктов просто не имеет этой записи.

    ⚠️ ВИД ЗАПИСИ ВЫБИРАЕТ СЕРВЕР, А НЕ ШАБЛОН (визуальная сессия 17.08,
    п. 1.2). До правки функция отдавала плоский список строк, и все четыре
    записи рисовались одним серым чипом: тип, число пунктов, сложность и
    наличие решения весили на экране одинаково. Реши это шаблон — записи
    разошлись бы между карточкой отбора, составом и «Что нашлось», где та
    же строка печатается по-своему.

    `kind`:
      `type` — контурный чип: тип задачи;
      `diff` — янтарный чип со звездой: сложность (цвет ВСЕГДА со знаком);
      `sol`  — зелёный чип с галкой: есть разбор;
      `note` — обычный текст: число пунктов. Это справка, а не сигнал.
    """
    facts = [{'kind': 'type', 'text': 'тест' if is_test else 'задача'}]
    if problem.difficulty:
        facts.append({'kind': 'diff',
                      'text': '★ %d' % problem.difficulty,
                      'hint': 'сложность %d из 5' % problem.difficulty})
    if getattr(problem, 'solution', ''):
        facts.append({'kind': 'sol', 'text': '✓ решение'})
    if parts_count:
        from problems.templatetags.ru import count_ru

        facts.append({'kind': 'note',
                      'text': count_ru(parts_count, 'пункт,пункта,пунктов')})
    return facts


def picker_context(request, per_page=20, sortable=False):
    """Контекст списка задач каталога: фильтры, карточки, пагинация.

    Возвращает готовый словарь — конструктор кладёт его в свой контекст
    как есть.

    ⚠️ ФИЛЬТРЫ СОБИРАЕТ ОБЩИЙ МОДУЛЬ `catalog.filters`, А НЕ ЭТОТ ФАЙЛ.
    Здесь жила ВТОРАЯ копия разбора параметров и построения запроса, и она
    уже разошлась с каталогом: там был фильтр «Источник», здесь его не
    было. В таксономии v2 будет 29 тем, 343 тега и 11 особенностей —
    каждое добавление пришлось бы делать дважды (решение владельца
    01.09.2026, https://app.notion.com/p/3ceb11c92bc1817d89e1c7274fd0a88c).

    ⚠️ НАБОР ЗАДАЧ У РЕПЕТИТОРА ДРУГОЙ, И ЭТО СОХРАНЕНО. Каталог показывает
    только проверенное человеком (14 458 задач), экран домашки — всё
    опубликованное без брака (28 593): репетитор собирает работу из более
    широкого набора. Сведение этих правил в одно молча поменяло бы ему
    список, поэтому шлюз назван параметром: `gate='tutor'`.

    ⚠️ «ЕСТЬ РЕШЕНИЕ» ЗДЕСЬ МЯГЧЕ, ЧЕМ В КАТАЛОГЕ, И ТОЖЕ НАРОЧНО. Каталог
    прячет непроверенные решения (`solution_needs_review`), конструктор —
    нет, так было всегда. `solution_strict=False` называет это различие
    вслух вместо того, чтобы прятать его в двух разных `filter(...)`.

    ⚠️ `sortable` ВЫКЛЮЧЕН ПО УМОЛЧАНИЮ НАРОЧНО. Порядок выдачи — это
    поведение, а не оформление: включив сортировку всем, я поменял бы
    список на прежних экранах отбора, которых эта сессия не касается.
    """
    from catalog import filters as F

    from problems.models import CustomProblem

    active = F.parse(request.GET)
    base = F.base_queryset('tutor')

    # «Чужие» параметры экрана, которые обязаны пережить смену фильтра:
    # занятие, вид работы и открытая вкладка. Без них поиск по каталогу
    # молча выбрасывал бы репетитора из занятия (фаза 12.1).
    carry = {}
    for name in ('group', 'kind', 'tab'):
        value = (request.GET.get(name) or '').strip()
        if value:
            carry[name] = value

    qs, filters_ctx = F.build(base, active, mode='panel',
                              carry=carry, solution_strict=False)

    f_q = active['q']
    if f_q:
        qs = qs.filter(Q(statement__icontains=f_q) | Q(title__icontains=f_q))

    # ⚠️ ПОРЯДОК ПО УМОЛЧАНИЮ — ТОТ ЖЕ, ЧТО БЫЛ (`-id`). «Сначала
    # подходящие по теме» и есть естественный порядок отфильтрованного
    # списка: тема и слова запроса уже отобрали, что подходит, а внутри
    # отобранного сверху идут те, у кого слово нашлось в НАЗВАНИИ, а не
    # только где-то в условии. Две другие сортировки перекладывают список
    # по сложности и о фильтрах не знают — это честно написано в подсказке.
    f_sort = (request.GET.get('sort') or '').strip() if sortable else ''
    if f_sort not in SORT_KEYS:
        f_sort = 'fit'
    order = ['-id']
    if f_sort == 'easy':
        order = ['difficulty', '-id']
    elif f_sort == 'hard':
        order = ['-difficulty', '-id']
    elif f_q:
        qs = qs.annotate(title_hit=Case(
            When(title__icontains=f_q, then=Value(0)),
            default=Value(1), output_field=IntegerField()))
        order = ['title_hit', '-id']

    # ⚠️ ПУНКТЫ СЧИТАЕМ ПРЕДЗАГРУЗКОЙ, А НЕ `annotate(Count(...))`. Число
    # нужно двадцати карточкам страницы, а `Count` заставил бы базу
    # сгруппировать все восемнадцать тысяч ДО пагинации — ради чипа.
    qs = (qs.prefetch_related('topics', 'parts', 'source_references__source')
          .order_by(*order).distinct())

    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    cards = []
    for problem in page_obj:
        # ⚠️ ОБРЕЗКА ПО СЛОВАМ. Резать по символам нельзя: `raw[:100]` рвёт
        # числа посередине, и в карточке появлялось «переменные — 300…»
        # вместо 3000. Число, обрезанное на цифре, — это не «немного
        # короче», это ДРУГОЕ ЧИСЛО.
        preview = word_cut(strip_latex(problem.statement), 100)
        difficulty = problem.difficulty or 0
        topics = list(problem.topics.all())[:3]
        is_test = is_test_problem(problem)
        cards.append({
            # Чипы и источник — только для нового потока; прежние шаблоны
            # этих ключей не читают, и добавление их ничего не меняет.
            'facts': card_facts(problem, is_test, len(problem.parts.all())),
            'source': source_label(problem),
            'problem': problem,
            'preview': preview,
            # Название задачи — общей функцией: она умеет и по границе слова
            # обрезать, и подставлять начало условия вместо «Задача #123».
            'card_title': preview_title(problem, limit=60),
            'topics': topics,
            # Одна тихая строка вместо ряда тегов и звёздочек.
            'meta': card_meta(topics, problem.problem_type, difficulty),
            'difficulty_stars': range(difficulty),
            'difficulty_empty': range(5 - difficulty),
            # Тип красит полосу слева у карточки (фаза 10.3). Признак тот
            # же, что везде в проекте: «тест: …» в `problem_type`.
            'is_test': is_test,
        })

    query = request.GET.copy()
    query.pop('page', None)

    # Возврат из редактора своей задачи: ?add_custom=<id> — задача сразу
    # ложится в собираемую корзину (та же вкладка, sessionStorage жив).
    add_custom = None
    add_custom_id = request.GET.get('add_custom', '').strip()
    if add_custom_id.isdigit():
        add_custom = CustomProblem.objects.filter(
            pk=int(add_custom_id), owner=request.user,
            is_deleted=False).first()

    from .access import group_id_param

    return {
        'page_obj': page_obj,
        'cards': cards,
        # Имена хранилищ — из ОДНОЙ точки (`storage_keys`). Пока их писал
        # каждый экран сам, один писал пустую строку, и подобранное уезжало
        # в ключ с пустым именем. Занятие тут же в ключе: вкладка одна,
        # занятий много.
        'storage': storage_keys(group_id_param(request)),
        'total': paginator.count,
        # Общий компонент фильтров — та же сборка, что у каталога.
        'filters': filters_ctx,
        # ⚠️ Был ли ЗАПРОС. Число «найдено» показываем только после него:
        # при пустом поиске это просто размер каталога, и на экране сборки
        # домашки оно читается как «в домашке 18865 задач».
        'has_query': bool(f_q) or not F.is_empty(active),
        'base_query': query.urlencode(),
        'f_q': f_q,
        'f_sort': f_sort,
        'sorts': SORTS,
        'preselect_id': request.GET.get('preselect', '').strip(),
        'add_custom': add_custom,
    }


def own_problem_rows(owner):
    """Свои задачи репетитора карточками отбора — третья вкладка.

    ⚠️ КЛЮЧ «c<номер>», А НЕ НОМЕР (ревью 15.08, п. 11.2). Тот же словарь
    ключей, что у корзины и у эндпоинта предпросмотра: свою задачу №3 и
    каталожную №3 голый номер не различает, и в работу уехала бы чужая.

    Строка «тема · тип · сложность» собирается ТОЙ ЖЕ `card_meta`, что у
    каталожной карточки: вкладки обязаны выглядеть одинаково — это одно
    место, где выбирают задачи, а не два.
    """
    from problems.models import CustomProblem

    rows = []
    for problem in (CustomProblem.objects
                    .filter(owner=owner, is_deleted=False)
                    .select_related('topic').order_by('-updated_at', '-pk')):
        topics = [problem.topic] if problem.topic_id else []
        rows.append({
            'problem': problem,
            'key': 'c%d' % problem.pk,
            'title': preview_title(problem, limit=60),
            'meta': card_meta(topics, problem.get_kind_display(),
                              problem.difficulty or 0),
            'preview': word_cut(strip_latex(problem.statement), 100),
            'is_test': problem.is_test,
        })
    return rows


def parse_cart(raw):
    """Разбор корзины «12,45,c7» → (id каталожных, id своих) с порядком.

    Возвращает список сырых ключей в порядке корзины — порядок в корзине
    становится порядком задач в работе.
    """
    keys = [value.strip() for value in (raw or '').split(',') if value.strip()]
    catalog = [int(key) for key in keys if key.isdigit()]
    custom = [int(key[1:]) for key in keys
              if key.startswith('c') and key[1:].isdigit()]
    return keys, catalog, custom


def cart_items(keys, owner, manual_order=False, points=None, suggest=False,
               rule=None):
    """Корзина → ПОЗИЦИИ будущей работы в памяти, в порядке показа.

    Отдаёт `(позиции, {id(позиции): ключ корзины})`. Нужна и правой колонке
    конструктора, и предпросмотру печатного листка: листок собирается той
    же `assignment_export.print_rows`, что и у созданной работы, — второй
    сборки печати не заводим.

    ⚠️ СБОРКА ОДНА НА ВСЕХ. Порядок и подписи частей считает
    `assignment_rows.ordered_items` + `section_marks` — те же функции, что
    рисуют работу ученику, репетитору, печатному листку и `.tex`. Второй
    сборки нет намеренно: превью, которое расходится с готовой работой,
    хуже отсутствия превью.

    Позиции создаются В ПАМЯТИ (никаких записей в базу): работы ещё нет,
    а порядок показать надо.

    ⚠️ БАЛЛ ПРОСТАВЛЯЕТСЯ ПОЗИЦИИ ЗДЕСЬ ЖЕ. Заголовок части считает состав
    («3 вопроса · 6 баллов») через `item_max_score`, то есть смотрит в
    `item.points`; у позиции в памяти это поле пусто, и без подстановки
    заголовок обещал бы по одному баллу за задачу, пока рядом в строке
    стоит десять.

    ⚠️ ПОРЯДОК СТАРШИНСТВА ОДИН НА ВЕСЬ ПОТОК: ручная правка репетитора
    (`points`) → правило начисления шага «Выдача» (`rule`) → прежнее
    значение по умолчанию. Ручная правка выигрывает всегда: правило меняет
    цену тех позиций, к которым человек не притрагивался.
    """
    from decimal import Decimal
    from types import SimpleNamespace

    from problems import assignment_rows
    from problems.models import AssignmentItem, CustomProblem, Problem
    from problems.models_platform import default_points

    keys = [key for key in keys if key]
    catalog_ids = [int(k) for k in keys if k.isdigit()]
    custom_ids = [int(k[1:]) for k in keys
                  if k.startswith('c') and k[1:].isdigit()]
    catalog = {p.pk: p for p in Problem.objects.filter(pk__in=catalog_ids)
               .prefetch_related('topics', 'source_references__source')}
    custom = {c.pk: c for c in CustomProblem.objects.filter(
        pk__in=custom_ids, owner=owner, is_deleted=False)}

    items, by_item = [], {}
    for order, key in enumerate(keys):
        item = None
        if key.isdigit() and int(key) in catalog:
            item = AssignmentItem(order=order,
                                  catalog_problem=catalog[int(key)])
        elif key.startswith('c') and key[1:].isdigit() \
                and int(key[1:]) in custom:
            item = AssignmentItem(order=order,
                                  custom_problem=custom[int(key[1:])])
        if item is None:
            continue
        chosen = (points or {}).get(key)
        if chosen is not None:
            item.points = Decimal(str(chosen))
        elif rule or suggest:
            # Новый поток считает балл правилом начисления (по умолчанию —
            # по сложности задачи); прежние конструкторы просят прежнее
            # значение по умолчанию.
            item.points = rule_points(
                rule, item.is_test, getattr(item.problem, 'difficulty', 0))
        else:
            item.points = default_points(item.is_test)
        items.append(item)
        by_item[id(item)] = key

    shell = SimpleNamespace(manual_order=bool(manual_order))
    ordered = assignment_rows.ordered_items(shell, items)
    return ordered, by_item


def cart_rows(keys, owner, manual_order=False, points=None, suggest=False,
              rule=None):
    """Строки для правой колонки конструктора: всё, что показывает экран.

    ⚠️ ПОЗИЦИЯ ОТДАЁТ ЗАДАЧУ ЦЕЛИКОМ (ревью 15.08, фаза 12). Блок назывался
    «Работа глазами ученика», а показывал название, тему и балл — то есть
    ровно то, чего ученик как раз не видит. Условие, ВСЕ пункты, ответы,
    наличие эталонного решения, тип и сложность приходят сюда сразу: без
    них проверить собранную работу можно только создав её.
    """
    from problems import assignment_rows

    ordered, by_item = cart_items(keys, owner, manual_order, points, suggest,
                                  rule)
    marks = assignment_rows.section_marks(ordered)

    rows = []
    for index, item in enumerate(ordered):
        problem = item.problem
        parts = _cart_parts(item)
        # ⚠️ У своей задачи репетитора тема ОДНА (`topic`), у каталожной —
        # набор (`topics`). Одна строка «тема · тип · сложность» на обе,
        # чтобы превью не разъезжалось по виду задачи.
        if item.is_custom:
            topics = [problem.topic] if problem.topic_id else []
            kind = problem.get_kind_display()
        else:
            topics = list(problem.topics.all())[:1]
            kind = problem.problem_type
        rows.append({
            'key': by_item[id(item)],
            'title': preview_title(problem, limit=90),
            'meta': card_meta(topics, kind, problem.difficulty or 0),
            'is_test': item.is_test,
            'points': float(item.points),
            # ⚠️ СКЛОНЕНИЕ СЧИТАЕТ ПИТОН, КЛИЕНТ ПЕЧАТАЕТ ГОТОВУЮ СТРОКУ
            # (ревью 17.08, п. 6.1). Правило трёх русских форм живёт в
            # `assignment_rows.point_word`; вторая его копия на клиенте
            # разошлась бы с печатным листком на первом же дробном балле.
            'points_text': assignment_rows.points_text(item.points),
            # ⚠️ ПРИЗНАК РУЧНОЙ ПРАВКИ СЧИТАЕТ СЕРВЕР, а не экран. Правило
            # начисления и ручные баллы применяет одна функция; спроси
            # клиент об этом сам — «вручную» появлялось бы там, где балл
            # просто совпал с подсказкой.
            'manual': by_item[id(item)] in (points or {}),
            'section': marks.get(index),
            # ⚠️ Полное содержимое задачи — ниже. Санитайзер `text_clean`
            # здесь НЕ зовём: он живёт на показе и экспорте готовой работы,
            # а тут задача ещё выбирается; менять текст «по дороге» в
            # конструкторе значило бы показать не то, что уедет в работу.
            'statement': item.statement or '',
            'parts': parts,
            # Подзаголовок позиции в составе: тип · пункты · сложность.
            # Собирает та же функция, что чипы карточки отбора, — иначе
            # одна и та же задача описывалась бы на двух шагах по-разному.
            'facts': card_facts(problem, item.is_test, len(parts)),
            'options': _cart_options(item),
            'answer': _cart_answer(item),
            'has_solution': bool(getattr(problem, 'solution', '')),
            # ⚠️ РЕШЕНИЕ ЦЕЛИКОМ, А НЕ ТОЛЬКО ПРИЗНАК «ОНО ЕСТЬ» (ревью
            # 17.08, фазы 8 и 10). Окно «Целиком» обязано показать то же,
            # что уедет в вариант листка с ответами: пометка «решение
            # есть» не даёт проверить, что оно про эту задачу.
            'solution': getattr(problem, 'solution', '') or '',
            'source': ('своя задача' if item.is_custom
                       else source_label(problem)),
            'difficulty': problem.difficulty or 0,
            'kind_label': assignment_rows.kind_label(item),
        })
    return rows


def _cart_parts(item):
    """Пункты задачи для превью: буква, вопрос, эталонный ответ, вес.

    ⚠️ ПУНКТЫ СПРАШИВАЕТ ОДНА ФУНКЦИЯ (`assignment_rows.answer_parts`) —
    у своей задачи репетитора они лежат в своей таблице, и обращение к
    `catalog_problem.parts` отдало бы пустоту (ревью 16.08, фаза 1).
    """
    from problems import assignment_rows

    out = []
    for part in assignment_rows.answer_parts(item):
        if part is None:
            continue
        points = getattr(part, 'points', None)
        out.append({'label': part.label or '',
                    'text': part.statement or '',
                    'answer': (part.answer or ''),
                    # Вес пункта, а НЕ балл: балл считает позиция работы
                    # (`assignment_rows.part_max_score`), и печатать здесь
                    # каталожное число значило бы обещать не тот балл.
                    'weight': float(points) if points is not None else None})
    return out


def _cart_options(item):
    """Варианты ответа у теста — с пометкой верного."""
    if item.is_custom and item.custom_problem is not None:
        return [{'label': o.label, 'text': o.text, 'right': o.is_correct}
                for o in item.custom_problem.options.all()]
    if item.catalog_problem_id is None:
        return []
    # У каталожного теста варианты — это подпункты, а верный записан
    # буквой в поле «ответ». Разбирать её здесь не будем: в превью
    # достаточно показать варианты и сам ответ отдельной строкой.
    return [{'label': p.label or '', 'text': p.statement or '', 'right': False}
            for p in item.catalog_problem.parts.all()] if item.is_test else []


def _cart_answer(item):
    """Ответ на задачу целиком (если он один на всю задачу)."""
    problem = item.problem
    return (getattr(problem, 'answer', '') or '')


def parse_points(raw):
    """Разбор строки «12:3,c7:10» → {ключ корзины: балл}.

    Пустая строка и мусор дают пустой словарь: балл позиции тогда ставит
    `AssignmentItem.save()` по умолчанию (10 задаче, 3 тесту). Отдельного
    правила «сколько стоит задача» здесь нет и быть не должно.
    """
    points = {}
    for chunk in (raw or '').split(','):
        key, _, value = chunk.partition(':')
        key = key.strip()
        value = value.strip().replace(',', '.')
        if not key or not value:
            continue
        try:
            number = float(value)
        except ValueError:
            continue
        if number < 0 or number > 1000:
            continue
        points[key] = number
    return points


def create_items(assignment, owner, keys, catalog_ids, custom_ids,
                 points=None, rule=None):
    """Создаёт позиции работы в порядке корзины. Возвращает их число.

    Одна точка на домашку и контрольную: раньше контрольная умела класть
    только каталожные задачи, и своя задача репетитора в неё не попадала.

    `points` — {ключ корзины: балл}, ручные правки репетитора. `rule` —
    правило начисления с шага «Выдача»; по нему считаются позиции, которых
    человек не касался.

    ⚠️ ТО ЖЕ СТАРШИНСТВО, ЧТО В `cart_items` (ревью 17.08, ф. 1): ручная
    правка → правило → значение по умолчанию. Пока правило знал только
    экран, конструктор показывал балл по сложности задачи, а запись работы
    ставила прежнюю константу: работа из двух тестов уходила ученику на
    шесть баллов вместо двух.
    """
    from decimal import Decimal

    from problems.models import AssignmentItem, CustomProblem, Problem

    catalog = {p.pk: p for p in Problem.objects.filter(pk__in=catalog_ids)}
    custom = {c.pk: c for c in CustomProblem.objects.filter(
        pk__in=custom_ids, owner=owner, is_deleted=False)}
    points = points or {}

    def score(key, item):
        """Балл позиции. ⚠️ «Тест ли это» спрашиваем У САМОЙ ПОЗИЦИИ.

        У `AssignmentItem.is_test` своё определение (тип задачи начинается
        со слова «тест»), и второй предикат рядом с ним разъехался бы с
        конструктором на первой же задаче с необычным типом.
        """
        value = points.get(key)
        if value is not None:
            return Decimal(str(value))
        if rule is None:
            # Прежние экраны правила не присылают — там балл по-прежнему
            # ставит `AssignmentItem.save()` значением по умолчанию.
            return None
        return rule_points(rule, item.is_test,
                           getattr(item.problem, 'difficulty', 0))

    order = 0
    for key in keys:
        item = None
        if key.isdigit() and int(key) in catalog:
            item = AssignmentItem(assignment=assignment, order=order,
                                  catalog_problem=catalog[int(key)])
        elif key.startswith('c') and key[1:].isdigit() \
                and int(key[1:]) in custom:
            item = AssignmentItem(assignment=assignment, order=order,
                                  custom_problem=custom[int(key[1:])])
        if item is None:
            continue
        item.points = score(key, item)
        item.save()
        order += 1

    # Старый M2M заполняем тоже — на нём держатся прежние экраны.
    if catalog:
        assignment.problems.set(catalog.values())
    return order
