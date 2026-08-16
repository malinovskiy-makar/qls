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
from django.db.models import Q

from problems.hw_generator import is_test_problem
from problems.text_clean import preview_title

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
    }
    keys['migrate'] = [
        [CART_KEY, keys['cart']],
        [CART_KEY + '_order', keys['order']],
        [SETTINGS_KEY, keys['settings']],
        [MANUAL_ORDER_KEY, keys['manual']],
    ]
    keys['junk'] = list(JUNK_KEYS)
    return keys



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


def picker_context(request, per_page=20):
    """Контекст списка задач каталога: фильтры, карточки, пагинация.

    Возвращает готовый словарь — оба конструктора кладут его в свой
    контекст как есть.
    """
    from problems.management.commands.apply_topic_mapping import CANONICAL
    from problems.models import CustomProblem, Problem, Topic

    qs = Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                needs_quality_review=False)

    f_q = request.GET.get('q', '').strip()
    f_topic = request.GET.get('topic', '').strip()
    f_diff = request.GET.get('difficulty', '').strip()
    f_type = request.GET.get('type', '').strip()
    f_sol = request.GET.get('has_solution', '').strip()

    if f_q:
        qs = qs.filter(Q(statement__icontains=f_q) | Q(title__icontains=f_q))
    if f_topic:
        qs = qs.filter(topics__id=f_topic)
    if f_diff:
        qs = qs.filter(difficulty=f_diff)
    if f_type:
        qs = qs.filter(problem_type=f_type)
    if f_sol == '1':
        qs = qs.exclude(solution='')

    qs = qs.prefetch_related('topics').order_by('-id').distinct()

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
        cards.append({
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
            'is_test': is_test_problem(problem),
        })

    problem_types = list(
        Problem.objects.filter(status=Problem.Status.PUBLISHED)
        .exclude(problem_type='')
        .values_list('problem_type', flat=True)
        .distinct().order_by('problem_type'))

    topics = sorted(Topic.objects.filter(name__in=CANONICAL),
                    key=lambda t: CANONICAL.index(t.name))

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
        # ⚠️ Был ли ЗАПРОС. Число «найдено» показываем только после него:
        # при пустом поиске это просто размер каталога, и на экране сборки
        # домашки оно читается как «в домашке 18865 задач».
        'has_query': bool(f_q or f_topic or f_diff or f_type or f_sol),
        'topics': topics,
        'problem_types': problem_types,
        'base_query': query.urlencode(),
        'f_q': f_q,
        'f_topic': f_topic,
        'f_diff': f_diff,
        'f_type': f_type,
        'f_sol': f_sol,
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


def cart_items(keys, owner, manual_order=False, points=None):
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
    стоит десять. `points` — то, что репетитор уже наменял на экране;
    чего там нет, стоит по умолчанию (10 задаче, 3 тесту).
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
        item.points = (Decimal(str(chosen)) if chosen is not None
                       else default_points(item.is_test))
        items.append(item)
        by_item[id(item)] = key

    shell = SimpleNamespace(manual_order=bool(manual_order))
    ordered = assignment_rows.ordered_items(shell, items)
    return ordered, by_item


def cart_rows(keys, owner, manual_order=False, points=None):
    """Строки для правой колонки конструктора: всё, что показывает экран.

    ⚠️ ПОЗИЦИЯ ОТДАЁТ ЗАДАЧУ ЦЕЛИКОМ (ревью 15.08, фаза 12). Блок назывался
    «Работа глазами ученика», а показывал название, тему и балл — то есть
    ровно то, чего ученик как раз не видит. Условие, ВСЕ пункты, ответы,
    наличие эталонного решения, тип и сложность приходят сюда сразу: без
    них проверить собранную работу можно только создав её.
    """
    from problems import assignment_rows

    ordered, by_item = cart_items(keys, owner, manual_order, points)
    marks = assignment_rows.section_marks(ordered)

    rows = []
    for index, item in enumerate(ordered):
        problem = item.problem
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
            'section': marks.get(index),
            # ⚠️ Полное содержимое задачи — ниже. Санитайзер `text_clean`
            # здесь НЕ зовём: он живёт на показе и экспорте готовой работы,
            # а тут задача ещё выбирается; менять текст «по дороге» в
            # конструкторе значило бы показать не то, что уедет в работу.
            'statement': item.statement or '',
            'parts': _cart_parts(item),
            'options': _cart_options(item),
            'answer': _cart_answer(item),
            'has_solution': bool(getattr(problem, 'solution', '')),
            'difficulty': problem.difficulty or 0,
            'kind_label': assignment_rows.kind_label(item),
        })
    return rows


def _cart_parts(item):
    """Пункты задачи для превью: буква, вопрос, эталонный ответ."""
    from problems import assignment_rows

    out = []
    for part in assignment_rows.answer_parts(item):
        if part is None:
            continue
        out.append({'label': part.label or '',
                    'text': part.statement or '',
                    'answer': (part.answer or '')})
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
                 points=None):
    """Создаёт позиции работы в порядке корзины. Возвращает их число.

    Одна точка на домашку и контрольную: раньше контрольная умела класть
    только каталожные задачи, и своя задача репетитора в неё не попадала.

    `points` — {ключ корзины: балл} из конструктора подборки. Не задан —
    балл проставит `AssignmentItem.save()` по умолчанию.
    """
    from decimal import Decimal

    from problems.models import AssignmentItem, CustomProblem, Problem

    catalog = {p.pk: p for p in Problem.objects.filter(pk__in=catalog_ids)}
    custom = {c.pk: c for c in CustomProblem.objects.filter(
        pk__in=custom_ids, owner=owner, is_deleted=False)}
    points = points or {}

    def score(key):
        value = points.get(key)
        return None if value is None else Decimal(str(value))

    order = 0
    for key in keys:
        if key.isdigit() and int(key) in catalog:
            AssignmentItem.objects.create(assignment=assignment, order=order,
                                          catalog_problem=catalog[int(key)],
                                          points=score(key))
            order += 1
        elif key.startswith('c') and key[1:].isdigit() \
                and int(key[1:]) in custom:
            AssignmentItem.objects.create(assignment=assignment, order=order,
                                          custom_problem=custom[int(key[1:])],
                                          points=score(key))
            order += 1

    # Старый M2M заполняем тоже — на нём держатся прежние экраны.
    if catalog:
        assignment.problems.set(catalog.values())
    return order
