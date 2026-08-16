"""
Поток создания работы — четыре шага на четырёх адресах.

    1. «Что кладём»   /teacher/work/           — вкладки: каталог, описать
                                                 словами, написать свою,
                                                 мои задачи, отложенные;
    2. «Что нашлось»  /teacher/assignment/generate/ — ТОЛЬКО у подбора
                                                 (сделан ревью 16.08, фаза 9);
    3. «Состав»       /teacher/work/compose/   — порядок, баллы, предпросмотры;
    4. «Выдача»       /teacher/work/give/      — название, срок, кому.

⚠️ ЗАЧЕМ НОВЫЕ АДРЕСА, А НЕ ПРАВКА СТАРЫХ. Прежние три способа набора —
`assignment_create`, `assignment_generate`, `problem_new` — жили по разным
правилам: у одного конструктор с баллами и порядком, у другого корзина без
баллов, третий вообще форма, после которой терялось занятие. Перестройка
их «на месте» означала бы, что в любой момент на сайте лежит наполовину
переехавший поток. Новый поток строится рядом; входные точки переключаются
одним отдельным шагом, когда все четыре экрана работают.

⚠️ РАБОТУ СОЗДАЁТ НЕ ЭТОТ МОДУЛЬ. Шаг «Выдача» отправляет форму в те же
`assignment_create` / `exam_create`, что и прежние конструкторы: второй
точки создания работы в проекте нет и не заводится — расходятся не экраны,
а правила (сегодня в одной появится проверка срока, завтра в другой нет).

⚠️ СОСТОЯНИЕ ПОТОКА ЖИВЁТ В КОРЗИНЕ ЗАНЯТИЯ (`sessionStorage`, имена
собирает `picker.storage_keys`). Сервер шагов не помнит намеренно: корзина
и так привязана к занятию, а вторая память о том же разъехалась бы с ней.
"""
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

from problems import exam_engine

from . import picker
from .access import (
    group_id_param, group_label_param, group_param_refusal, tutor_required,
)

# Порядок шагов на ленте. «Что нашлось» показывается только на пути подбора:
# рисовать его всем значило бы обещать экран, которого у двух путей нет.
STEPS = ('pick', 'found', 'compose', 'give')


def flow_state(request):
    """Общее для всех шагов: занятие, вид работы, имена хранилищ.

    ⚠️ ЗАНЯТИЕ ЖИВЁТ В АДРЕСЕ КАЖДОГО ШАГА (фаза 12.1). Держать его в
    сессии было бы удобнее ровно до первой второй вкладки: две собираемые
    работы в двух вкладках делили бы одно занятие и путали крошку.
    """
    from problems.models import StudentGroup

    group_id = group_id_param(request)
    kind = request.GET.get('kind') or request.POST.get('kind') or 'homework'
    group = None
    if group_id:
        group = StudentGroup.objects.filter(pk=group_id,
                                            teacher=request.user).first()
    return {
        'group': group,
        'group_id': group_id or '',
        'group_label': group_label_param(request),
        'kind': 'exam' if kind == 'exam' else 'homework',
        'is_exam': kind == 'exam',
        'storage': picker.storage_keys(group_id),
    }


def flow_query(state, **extra):
    """Хвост адреса шага: занятие и вид работы. Одна сборка на весь поток."""
    from urllib.parse import urlencode

    query = {}
    if state.get('group_id'):
        query['group'] = state['group_id']
    if state.get('kind') == 'exam':
        query['kind'] = 'exam'
    query.update({key: value for key, value in extra.items() if value})
    return ('?' + urlencode(query)) if query else ''


def step_urls(state):
    """Адреса всех шагов с занятием и видом работы — для ленты и кнопок."""
    tail = flow_query(state)
    return {
        'pick': reverse('teacher:work_pick') + tail,
        'found': reverse('teacher:assignment_generate') + tail,
        'compose': reverse('teacher:work_compose') + tail,
        'give': reverse('teacher:work_give') + tail,
    }


def kind_urls(state, step):
    """Куда ведёт переключатель «Домашка / Контрольная» с ЭТОГО шага.

    ⚠️ ВОЗВРАЩАЕТ АДРЕС ТОГО ЖЕ ШАГА. Прежний переключатель уводил на
    другой экран (и другой способ набора), и человек, уточнивший вид
    работы, начинал сборку заново.
    """
    route = {'pick': 'teacher:work_pick', 'compose': 'teacher:work_compose',
             'give': 'teacher:work_give',
             'found': 'teacher:assignment_generate'}.get(step,
                                                         'teacher:work_pick')
    base = reverse(route)
    return {
        'homework': base + flow_query(dict(state, kind='homework')),
        'exam': base + flow_query(dict(state, kind='exam')),
    }


def _tutor_groups(user):
    from problems.models import StudentGroup

    return list(StudentGroup.objects.filter(teacher=user)
                .prefetch_related('students').order_by('name'))


@tutor_required
def work_pick(request):
    """Шаг 1 «Что кладём»: пять вкладок, корзина внизу экрана.

    ⚠️ ПЯТЬ ВКЛАДОК, А НЕ ПЯТЬ ЭКРАНОВ (решение владельца). Способ набора —
    это не разные работы: часть задач берут из каталога, часть подбирают
    словами, одну пишут сами. Пока способы были экранами, переход между
    ними означал потерю набранного.

    ⚠️ ПРАВАЯ КОЛОНКА ЗДЕСЬ ПУСТА НАРОЧНО. Настройки работы уехали на шаг
    «Выдача»: пока они висели справа с первого шага, каталог занимал две
    трети ширины, а спрашивали их за три экрана до того, как они нужны.
    """
    refusal = group_param_refusal(request)
    if refusal is not None:
        return refusal

    from problems.models import SavedProblem

    state = flow_state(request)
    context = picker.picker_context(request, sortable=True)
    saved = [item.catalog_problem for item in
             SavedProblem.objects.filter(owner=request.user, is_deleted=False,
                                         catalog_problem__isnull=False)
             .select_related('catalog_problem')
             .prefetch_related('catalog_problem__topics',
                               'catalog_problem__parts',
                               'catalog_problem__source_references__source')]
    context.update(state)
    context.update({
        'steps': step_urls(state),
        'kind_urls': kind_urls(state, 'pick'),
        'step': 'pick',
        'saved_rows': [_saved_row(problem) for problem in saved],
        'own_problems': picker.own_problem_rows(request.user),
        'reset_url': reverse('teacher:work_pick') + flow_query(state),
        # ⚠️ «Написать свою» уносит занятие и вид работы с собой и просит
        # положить готовую задачу в корзину (`to_cart=1`). Без этого задача
        # создавалась, оставалась в «Моих задачах» и в собираемую работу не
        # попадала — кнопка обещала пополнить работу и не пополняла.
        # ⚠️ `return_to` ОБЯЗАТЕЛЕН. Без него редактор задачи возвращает на
        # свой умолчательный адрес — прежний конструктор домашки, — и
        # написанная задача уезжает мимо собираемой работы.
        'own_new_url': (reverse('teacher:problem_new')
                        + flow_query(state, to_cart='1',
                                     return_to=(reverse('teacher:work_pick')
                                                + flow_query(state)))),
        'groups': _tutor_groups(request.user),
    })
    return render(request, 'teacher/work/pick.html', context)


def _saved_row(problem):
    """Отложенная задача карточкой отбора — тем же набором полей."""
    from problems.hw_generator import is_test_problem
    from problems.text_clean import preview_title

    is_test = is_test_problem(problem)
    topics = list(problem.topics.all())[:3]
    return {
        'problem': problem,
        'key': str(problem.pk),
        'title': preview_title(problem, limit=60),
        'meta': picker.card_meta(topics, problem.problem_type,
                                 problem.difficulty or 0),
        'facts': picker.card_facts(problem, is_test,
                                   len(problem.parts.all())),
        'source': picker.source_label(problem),
        'preview': picker.word_cut(picker.strip_latex(problem.statement), 100),
        'is_test': is_test,
    }


@tutor_required
def work_compose(request):
    """Шаг 3 «Состав»: порядок, баллы, раскрытие позиции целиком.

    ⚠️ КОНСТРУКТОР СТАЛ ОБЩИМ. Он существовал только у пути «описать
    словами»: собранное руками уходило ученику, минуя экран, где видно
    состав. Список позиций строит сервер (`teacher:api_cart_rows`) — тот
    же, что рисует работу ученику, репетитору, печати и `.tex`.
    """
    refusal = group_param_refusal(request)
    if refusal is not None:
        return refusal

    state = flow_state(request)
    context = dict(state)
    context.update({
        'steps': step_urls(state),
        'kind_urls': kind_urls(state, 'compose'),
        'step': 'compose',
    })
    return render(request, 'teacher/work/compose.html', context)


@tutor_required
def work_give(request):
    """Шаг 4 «Выдача»: название, срок, кому — и лист, который уйдёт."""
    refusal = group_param_refusal(request)
    if refusal is not None:
        return refusal

    state = flow_state(request)
    groups = _tutor_groups(request.user)
    context = dict(state)
    context.update({
        'steps': step_urls(state),
        'kind_urls': kind_urls(state, 'give'),
        'step': 'give',
        'groups': groups,
        'has_groups': bool(groups),
        'min_window': exam_engine.MIN_WINDOW_MINUTES,
        'min_duration': exam_engine.MIN_DURATION_MINUTES,
        'max_duration': exam_engine.MAX_DURATION_MINUTES,
        'form': {'kind': 'window', 'show_results': True},
    })
    return render(request, 'teacher/work/give.html', context)


def tally(rows, students=0):
    """Сводка собранного: числа и ГОТОВАЯ строка для полосы внизу.

    ⚠️ СТРОКУ СОБИРАЕТ ПИТОН. Склонения «задача / задачи / задач» и
    «балл / балла / баллов» живут в `templatetags.ru`; собери эту фразу
    клиент — они существовали бы в двух местах, и первое же «1 задачи»
    показало бы, в каком именно.
    """
    from problems.assignment_rows import points_text
    from problems.templatetags.ru import count_ru

    tests = sum(1 for row in rows if row['is_test'])
    points = sum(row['points'] for row in rows)
    parts = [count_ru(len(rows), 'задача,задачи,задач'), points_text(points)]
    if tests:
        parts.append('из них %s' % count_ru(tests, 'тест,теста,тестов'))
    if students:
        parts.append('выдаётся %s'
                     % count_ru(students, 'ученику,ученикам,ученикам'))
    return {
        'count': len(rows),
        'tests': tests,
        'tasks': len(rows) - tests,
        'points': float(points),
        'text': 'В работе: ' + ' · '.join(parts),
    }


@tutor_required
def api_work_tally(request):
    """Сводка корзины для полосы внизу экрана. Только читает.

    Баллы приходят те, что репетитор наменял на шаге состава; чего нет —
    подставляется подсказкой по сложности задачи (`suggest=True`).
    """
    keys = [key.strip() for key in
            (request.GET.get('keys') or '').split(',') if key.strip()]
    raw = (request.GET.get('students') or '').strip()
    students = int(raw) if raw.isdigit() else 0
    rows = picker.cart_rows(keys, request.user,
                            points=picker.parse_points(
                                request.GET.get('points')),
                            suggest=True)
    return JsonResponse(tally(rows, students))


@tutor_required
def api_work_full(request, key):
    """Задача ЦЕЛИКОМ: условие, пункты с ответами, ответ, решение.

    ⚠️ ОКНО «ЦЕЛИКОМ» ОДНО НА ВЕСЬ ПОТОК (требование владельца). Тот же
    набор полей показывают шаг «Что кладём», шаг «Что нашлось» и раскрытая
    позиция в составе: собирает его `picker.cart_rows` — та самая функция,
    что готовит позиции работы. Второй сборки нет намеренно: окно, которое
    показывает не то, что уедет в работу, хуже отсутствия окна.
    """
    rows = picker.cart_rows([str(key)], request.user)
    if not rows:
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse({'row': rows[0]})


@tutor_required
def work_start(request):
    """Вход в поток из занятия: очистить корзину и открыть первый шаг.

    ⚠️ ОТДЕЛЬНЫЙ АДРЕС, А НЕ ССЫЛКА НА `work_pick`. «Создание работы» из
    занятия обязано начинать с чистого листа: иначе брошенная неделю назад
    корзина того же занятия оживает в новой работе, и репетитор выдаёт
    задачи, которых не выбирал. Возврат НАЗАД на первый шаг корзину не
    трогает — это разные события.
    """
    refusal = group_param_refusal(request)
    if refusal is not None:
        return refusal
    state = flow_state(request)
    return render(request, 'teacher/work/start.html', {
        'next_url': reverse('teacher:work_pick') + flow_query(state),
        'storage': state['storage'],
    })
