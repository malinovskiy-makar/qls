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

from problems.text_clean import preview_title


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
        cards.append({
            'problem': problem,
            'preview': preview,
            # Название задачи — общей функцией: она умеет и по границе слова
            # обрезать, и подставлять начало условия вместо «Задача #123».
            'card_title': preview_title(problem, limit=60),
            'topics': list(problem.topics.all())[:3],
            'difficulty_stars': range(difficulty),
            'difficulty_empty': range(5 - difficulty),
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


def create_items(assignment, owner, keys, catalog_ids, custom_ids):
    """Создаёт позиции работы в порядке корзины. Возвращает их число.

    Одна точка на домашку и контрольную: раньше контрольная умела класть
    только каталожные задачи, и своя задача репетитора в неё не попадала.
    """
    from problems.models import AssignmentItem, CustomProblem, Problem

    catalog = {p.pk: p for p in Problem.objects.filter(pk__in=catalog_ids)}
    custom = {c.pk: c for c in CustomProblem.objects.filter(
        pk__in=custom_ids, owner=owner, is_deleted=False)}

    order = 0
    for key in keys:
        if key.isdigit() and int(key) in catalog:
            AssignmentItem.objects.create(assignment=assignment, order=order,
                                          catalog_problem=catalog[int(key)])
            order += 1
        elif key.startswith('c') and key[1:].isdigit() \
                and int(key[1:]) in custom:
            AssignmentItem.objects.create(assignment=assignment, order=order,
                                          custom_problem=custom[int(key[1:])])
            order += 1

    # Старый M2M заполняем тоже — на нём держатся прежние экраны.
    if catalog:
        assignment.problems.set(catalog.values())
    return order
