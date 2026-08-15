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
    if difficulty:
        parts.append('сложность %d из 5' % difficulty)
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

    return {
        'page_obj': page_obj,
        'cards': cards,
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


def cart_rows(keys, owner, manual_order=False, points=None):
    """Корзина → позиции будущей работы В ТОМ ЖЕ ПОРЯДКЕ, что увидит ученик.

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
        })
    return rows


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
