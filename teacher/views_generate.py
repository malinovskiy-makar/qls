"""
Подбор домашки по описанию — три шага на одном адресе.

  1. ЗАПРОС      — описание словами + параметры;
  2. СТОП-ГЕЙТ   — показываем, ЧТО НАШЛОСЬ, и даём поправить ДО сборки;
  3. РЕЗУЛЬТАТ   — найденные задачи, их можно убрать, заменить, добавить
                   свои и отправить в обычный конструктор домашки.

⚠️ СТОП-ГЕЙТ ПОКАЗЫВАЕТ ЗАДАЧИ, А НЕ ТЕМЫ. Раньше на нём стояли темы,
выбранные моделью, — а проверить их репетитор не может: нашей таксономии он
не знает, и именно там пряталась ошибка с КТВ («альтернативное название
КПВ» выглядит правдоподобно ровно до того момента, как увидишь найденное).
Теперь на экране: строка СЛОВАМИ РЕПЕТИТОРА, названия двух-трёх найденных
задач и пометка уверенности.

⚠️ ПОВТОРНЫЙ ПОИСК ПО ОДНОЙ СТРОКЕ БЕСПЛАТЕН И НЕ ХОДИТ К МОДЕЛИ. Это самый
частый сценарий: «нашлись про производственные возможности, а надо про
торговые» — поправил формулировку, переискал. Платить за это второй раз
не за что.

Обращение к модели ровно одно — на шаге 2. Всё остальное ходит в свой банк.
"""
import logging

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from problems import hw_generator

from . import picker, views_work
from .access import (
    group_id_param, group_label_param, group_param_refusal, tutor_required,
)

logger = logging.getLogger(__name__)


# ⚠️ ТРИ ТЕКСТА НА ТРИ ВИДА ОТКАЗА (сессия 7, фаза 7.4). Репетитору нужен не
# код ошибки, а ответ на вопрос «что мне теперь делать».
#
# ⚠️ ТЕКСТ ГОВОРИТ, ЧТО СЛУЧИЛОСЬ, И НЕ ПОВТОРЯЕТ ВЫХОД ИЗ ПОЛОЖЕНИЯ (ревью
# 16.08, п. 7.3). Выход один на все три отказа — собрать работу руками, — и
# он стоит СТРОКОЙ НИЖЕ, со ссылкой. Пока он был ещё и внутри текста, на
# экране выходило «…или соберите работу вручную. Соберите работу вручную:
# Ручной поиск по каталогу».
AI_ERROR_TEXTS = {
    'no_key': 'Умный поиск сейчас недоступен — не настроен доступ к модели.',
    'limit': 'На сегодня закончились обращения к умному поиску '
             '(%(limit)d в сутки).',
    'other': 'Умный поиск не ответил — можно попробовать ещё раз.',
}


def _human_error(error):
    """Отказ модели → текст для экрана. Код ошибки на экран НЕ выходит."""
    from problems import ai

    kind = getattr(error, 'kind', 'other')
    text = AI_ERROR_TEXTS.get(kind, AI_ERROR_TEXTS['other'])
    if kind == 'limit':
        text = text % {'limit': ai.daily_limit()}
    return {'kind': kind, 'text': text}



# Примеры запросов — настоящие для олимпиадной экономики. Нажатие
# подставляет текст в поле: это единственное место, где пустоту стоит
# занять полезным.
EXAMPLE_QUERIES = [
    'Домашка на КПВ и альтернативные издержки, задачи на построение и на '
    'сложение кривых двух стран',
    'Эластичность спроса по цене и по доходу: расчёт коэффициента и вывод '
    'о выручке',
    'Монополия: максимизация прибыли, сравнение с совершенной конкуренцией, '
    'потери общества',
    'Рынок труда и МРОТ, одна задача посложнее в конце',
]



def _group_or_none(user, raw):
    """Группа по номеру из адреса — или None. Чужая группа не находится."""
    from problems.models import StudentGroup

    if not raw or not str(raw).isdigit():
        return None
    return StudentGroup.objects.filter(pk=int(raw), teacher=user).first()


def _tutor_groups(user):
    """Группы репетитора — нужны на последнем шаге, кому выдать работу."""
    from problems.models import StudentGroup

    return list(StudentGroup.objects.filter(teacher=user)
                .prefetch_related('students').order_by('name'))


def _saved_count(user):
    """Сколько отложенных задач каталога — для подписи вкладки."""
    from problems.models import SavedProblem

    return SavedProblem.objects.filter(owner=user, is_deleted=False,
                                       catalog_problem__isnull=False).count()


def _own_new_url(request, kind):
    """Адрес «Написать свою» — с занятием, видом работы и возвратом в поток.

    ⚠️ `to_cart` и `return_to` ОБЯЗАТЕЛЬНЫ. Без первого написанная задача
    остаётся в «Моих задачах» и в собираемую работу не попадает, без
    второго редактор возвращает на свой умолчательный адрес.
    """
    state = {'group_id': group_id_param(request), 'kind': kind}
    back = reverse('teacher:work_pick') + views_work.flow_query(state)
    return (reverse('teacher:problem_new')
            + views_work.flow_query(state, to_cart='1', return_to=back))


def _catalog_size():
    """Сколько задач в каталоге СЕЙЧАС. Число не зашиваем в текст.

    Считаем ровно то, из чего идёт подбор: опубликованные и не
    зафлагованные шлюзом качества.
    """
    from problems.models import Problem

    return Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                  needs_quality_review=False).count()


@tutor_required
def assignment_generate(request):
    """Экран подбора. Шаг определяется тем, что пришло в POST."""
    # Чужое или несуществующее занятие в адресе — отказ СРАЗУ, а не
    # через три шага страницей Django (ревью 15.08, фаза 15).
    refusal = group_param_refusal(request)
    if refusal is not None:
        return refusal

    # Домашка или контрольная. Движок подбора один и тот же (фаза 19);
    # отличается только то, какие настройки спрашиваем на последнем шаге.
    kind = request.POST.get('kind') or request.GET.get('kind') or 'homework'
    is_exam = kind == 'exam'

    context = {
        'available': hw_generator.is_available(),
        'reason': hw_generator.unavailable_reason(),
        'topics': hw_generator.canonical_topics(),
        'used_today': hw_generator.used_today(request.user),
        'daily_limit': hw_generator.daily_limit(),
        # ⚠️ НА ЭКРАН — ОСТАТОК, А НЕ РАСХОД (ревью 16.08, п. 9.4). «Сколько
        # уже потрачено» требует вычитания в уме; «сколько осталось» —
        # готовый ответ на вопрос «можно ещё разок?».
        'left_today': max(0, hw_generator.daily_limit()
                          - hw_generator.used_today(request.user)),
        'step': 'ask',
        # Лента шагов: этот экран — второй шаг потока, и он единственный,
        # у кого он есть (два других пути идут из отбора прямо в состав).
        'steps': views_work.step_urls({'group_id': group_id_param(request),
                                       'kind': kind}),
        'kind_urls': views_work.kind_urls(
            {'group_id': group_id_param(request), 'kind': kind}, 'found'),
        'flow_step': 'found',
        'is_exam': is_exam,
        'kind': kind,
        'groups': _tutor_groups(request.user),
        # Группа, из которой пришли (кнопки «Создать домашку/контрольную»
        # ведут сюда с ?group=). Контрольной она обязательна: её конструктор
        # живёт внутри группы.
        'group_id': group_id_param(request),
        # ⚠️ ИМЕНА ХРАНИЛИЩ РАНЬШЕ В ЭТОТ КОНТЕКСТ НЕ КЛАЛИСЬ ВОВСЕ, и
        # `{{ cart_key }}` в шаблоне рисовалось ПУСТОЙ строкой: подобранное
        # уезжало в ключ с пустым именем, а конструктор читал соседний ключ
        # и показывал прошлую корзину.
        'storage': picker.storage_keys(group_id_param(request)),
        # Название занятия для крошки: раньше там стояло слово «занятие».
        'group_label': group_label_param(request),
        'group': _group_or_none(request.user,
                                request.POST.get('group')
                                or request.GET.get('group')),
        'problem_count': _catalog_size(),
        # Ряд способов набора на этом экране — тот же партиал, что на шаге
        # «Что кладём» (п. 2.1). Здесь вкладки — ссылки: панелей у этого
        # состояния нет, оно само одна из них.
        'pick_url': (reverse('teacher:work_pick')
                     + views_work.flow_query({'group_id': group_id_param(request),
                                              'kind': kind})),
        'own_count': len(picker.own_problem_rows(request.user)),
        'saved_count': _saved_count(request.user),
        'own_new_url': _own_new_url(request, kind),
        'form': {'count': 4, 'count_open': 4, 'count_test': 0,
                 'min_difficulty': 1, 'max_difficulty': 5,
                 'text': '', 'has_answer': False, 'topics': []},
        # Примеры запросов — кнопками под полем. Репетитор, впервые
        # открывший подбор, не знает, насколько подробно можно писать.
        'examples': EXAMPLE_QUERIES,
    }

    if request.method != 'POST':
        # ⚠️ ПРОСТО ОТКРЫТЬ ЭТОТ АДРЕС БОЛЬШЕ НЕЛЬЗЯ (визуальная сессия
        # 17.08, п. 2.1). Форма запроса — это ПАНЕЛЬ шага «Что кладём», а
        # не отдельный экран: пока у неё был свой адрес, с него уезжала
        # лента шагов и менялась ширина колонки. За этим адресом осталось
        # только второе состояние панели — разбор запроса, то есть POST.
        state = {'group_id': group_id_param(request), 'kind': kind}
        return redirect(reverse('teacher:work_pick')
                        + views_work.flow_query(state, tab='ai'))

    form = _read_form(request)
    context['form'] = form
    # ⚠️ ПОЛЕ НАЗЫВАЕТСЯ `step_action`, А НЕ `action` (сессия 7, фаза 7.1).
    # Поле формы с именем `action` затеняет свойство `form.action` в
    # JavaScript — обращение к нему отдаёт сам input вместо адреса, и
    # форма уходила на «…/generate/[object HTMLInputElement]» с 404.
    action = request.POST.get('step_action') or 'parse'

    if action == 'parse':
        try:
            plan = hw_generator.parse_request(form['text'], form, request.user)
        except hw_generator.GeneratorUnavailable as error:
            # ⚠️ ОШИБКА ПОКАЗЫВАЕТСЯ РЯДОМ С КНОПКОЙ, А НЕ ВВЕРХУ СТРАНИЦЫ
            # (сессия 7, фаза 7.2). Плашка `messages` прилипает к верху, а
            # репетитор в этот момент смотрит на кнопку внизу — на экране
            # для него не происходило НИЧЕГО.
            #
            # ⚠️ ТЕКСТ — ЧЕЛОВЕЧЕСКИЙ, КОД ОШИБКИ ОСТАЁТСЯ В ЖУРНАЛЕ
            # (фаза 7.4). «Сервис разбора вернул ошибку (401)» репетитору не
            # говорит ничего и не подсказывает, что делать дальше.
            # ⚠️ В ЖУРНАЛ — КЛАСС И СООБЩЕНИЕ, А НЕ ТО ЖЕ, ЧТО НА ЭКРАНЕ
            # (ревью 16.08, п. 7.5). Раньше здесь печаталось «Подбор по
            # описанию не удался (other): Сервис разбора запроса
            # недоступен» — ровно та фраза, которую видит человек, то есть
            # журнал не добавлял НИЧЕГО. Настоящую причину (у нас это была
            # `urllib3` v2 на LibreSSL) приходилось искать руками.
            logger.warning('Подбор по описанию не удался (%s): %s: %s',
                           getattr(error, 'kind', 'other'),
                           type(error).__name__, error, exc_info=True)
            context['ai_error'] = _human_error(error)
            return render(request, 'teacher/generate.html', context)
        # ⚠️ КВОТА ДЕЛИТСЯ ПО ТИПУ ПРЯМО ЗДЕСЬ, а не на последнем шаге.
        # Раньше репетитор видел строки модели, а деление на «открытые» и
        # «тесты» происходило потом, невидимо. Теперь он ВЫБИРАЕТ задачи
        # руками, и строка обязана честно говорить, что именно под ней
        # ищется: тип — жёсткий отбор, и кандидаты под строку-тест другие.
        rows = _split(plan['rows'], form)
        context.update(step='plan', plan_rows=rows,
                       note=plan['note'], usage=plan.get('usage'),
                       cached=plan.get('cached'))
        context['previews'] = hw_generator.preview_rows(
            rows, has_answer=form['has_answer'])
        # ⚠️ СВОДКА «ПРОСИЛИ — НАБРАЛИ» (ревью 16.08, п. 9.1). `asked` —
        # план МОДЕЛИ до деления квоты по типу: если он просил тесты, а в
        # настройках стоит «тестов 0», строк с тестами после деления нет
        # вовсе, и сказать об этом больше нечем.
        context['asked'] = hw_generator.kind_totals(plan['rows'])
        context['plan_summary'] = hw_generator.plan_summary(
            context['previews'],
            {'open': form['count_open'], 'test': form['count_test']},
            context['asked'],
            mentioned=hw_generator.tests_in_text(form['text']))
        _refresh_left(context, request.user)
        context['manual_order'] = hw_generator.describes_order(form['text'])
        return render(request, 'teacher/generate.html', context)

    if action in ('research', 'fill'):
        # Поправили формулировку строки и переискали. К модели НЕ ходим.
        rows = _read_plan(request)
        if action == 'fill':
            # ⚠️ ДОБОР НЕДОСТАЮЩЕГО ВИДА (ревью 16.08, п. 9.1). Кнопка
            # стоит рядом со строкой «тесты: 0 из 2» и добавляет в план
            # строку нужного вида по ТОЙ ЖЕ фразе запроса. К модели не
            # ходим: искать по банку она не нужна.
            rows = rows + _fill_row(request, form)
        if not rows:
            messages.error(request, 'В плане не осталось ни одной строки.')
            context['step'] = 'ask'
            return render(request, 'teacher/generate.html', context)
        context.update(step='plan', plan_rows=rows)
        context['previews'] = hw_generator.preview_rows(
            rows, has_answer=form['has_answer'])
        context['manual_order'] = hw_generator.describes_order(form['text'])
        totals = hw_generator.kind_totals(rows)
        context['asked'] = totals
        context['plan_summary'] = hw_generator.plan_summary(
            context['previews'], totals, totals)
        _refresh_left(context, request.user)
        messages.success(request, 'Доискал по вашим формулировкам — '
                                  'обращения к модели не потребовалось.'
                         if action == 'fill' else
                         'Переискал по вашим формулировкам — '
                         'обращения к модели не потребовалось.')
        return render(request, 'teacher/generate.html', context)

    if action in ('search', 'replace'):
        rows = _read_plan(request)
        if not rows:
            messages.error(request, 'В плане не осталось ни одной строки.')
            context['step'] = 'ask'
            return render(request, 'teacher/generate.html', context)

        exclude = _read_ids(request, 'exclude_ids')
        # Квота делится по типу: ровно столько тестов и ровно столько
        # открытых задач, сколько попросили. ⚠️ Если строки УЖЕ поделены
        # (шаг «Что нашлось» делит их сразу), второй раз делить нельзя —
        # получилась бы четверть квоты на строку.
        plan = _split(rows, form)
        found, short = hw_generator.find_problems(
            plan or rows, has_answer=form['has_answer'], exclude=exclude)
        cards = [hw_generator.problem_card(item['problem'],
                                           item['confidence'],
                                           item.get('how', ''))
                 for item in found]
        # ⚠️ Подпись строки берём из ТОГО ЖЕ плана, по которому искали.
        # После деления квоты по типу (`split_by_kind`) строк становится
        # больше, чем в исходном плане, и обращение к `rows` по этому
        # индексу вылетает за границу. Поймано браузером: экран третьего
        # шага падал пятисоткой.
        used = plan or rows
        for card, item in zip(cards, found):
            card['row'] = item['row']
            card['row_label'] = used[item['row']]['label']
        context['manual_order'] = hw_generator.describes_order(form['text'])
        context.update(step='result', plan_rows=rows, results=cards,
                       empty_rows=short, exclude_ids=exclude,
                       far_count=sum(1 for c in cards
                                     if c['confidence'] == 'far'))
        # ⚠️ Предупреждаем только о НАСТОЯЩЕМ недоборе. Он теперь редкость:
        # квота добирается из общего поиска, а не оставляет дыру.
        for gap in short:
            messages.warning(
                request,
                'По строке «%s» в банке не нашлось задач: %d. Поправьте '
                'формулировку и подберите ещё раз.'
                % (gap['label'], gap['missing']))
        return render(request, 'teacher/generate.html', context)

    return redirect('teacher:assignment_generate')


def _split(rows, form):
    """Строки плана → строки с типом. Уже поделённые не делим повторно.

    ⚠️ Повторное деление — не мелочь: `split_by_kind` раздаёт квоту по
    весам, и второй проход дал бы по четверти запрошенного на строку.
    Признак «уже поделено» — заполненный `kind` хоть у одной строки.
    """
    if any(row.get('kind') for row in rows):
        return list(rows)
    return hw_generator.split_by_kind(rows, form['count_open'],
                                      form['count_test']) or list(rows)


def _read_form(request):
    def number(name, default, low, high):
        raw = (request.POST.get(name) or '').strip()
        try:
            return max(low, min(high, int(raw)))
        except ValueError:
            return default

    # ⚠️ ДВА ОТДЕЛЬНЫХ ЧИСЛА: открытых задач и тестов. Поле было одно
    # («сколько задач»), и разделить было нельзя никак — репетитор,
    # которому нужны четыре задачи и три теста, получал семь чего попало.
    count_open = number('count_open', 4, 0, hw_generator.MAX_PROBLEMS)
    count_test = number('count_test', 0, 0, hw_generator.MAX_PROBLEMS)
    if not count_open and not count_test:
        # Ноль и ноль — это не запрос. Возвращаемся к разумному минимуму,
        # а не показываем пустой результат.
        count_open = 1
    return {
        'text': (request.POST.get('text') or '').strip(),
        'count_open': count_open,
        'count_test': count_test,
        'count': min(hw_generator.MAX_PROBLEMS, count_open + count_test),
        'min_difficulty': number('min_difficulty', 1, 1, 5),
        'max_difficulty': number('max_difficulty', 5, 1, 5),
        'has_answer': request.POST.get('has_answer') == 'on',
        'topics': request.POST.getlist('topics'),
    }


def _refresh_left(context, user):
    """Пересчитать «осталось разборов» ПЕРЕД отрисовкой.

    ⚠️ Контекст собирается в начале вьюхи, а обращение к модели случается
    позже — и на экране плана стояло число, каким оно было ДО этого самого
    разбора. Человек видел «осталось 27» сразу после того, как потратил
    двадцать седьмой.
    """
    context['used_today'] = hw_generator.used_today(user)
    context['left_today'] = max(0, hw_generator.daily_limit()
                                - context['used_today'])


def _fill_row(request, form):
    """Строка плана для добора недостающего вида. Пустой список — нечего."""
    kind = request.POST.get('fill_kind')
    if kind not in ('open', 'test'):
        return []
    try:
        missing = int(request.POST.get('fill_count') or 0)
    except (TypeError, ValueError):
        return []
    if missing <= 0:
        return []
    return [{
        'label': 'Тесты' if kind == 'test' else 'Задачи',
        # Ищем по ФРАЗЕ ЦЕЛИКОМ: своей формулировки у этой строки нет — её
        # никто не писал, она появилась из расхождения настроек и запроса.
        'query': (form.get('text') or '').strip()[:300],
        'topic': '',
        'difficulty': form.get('min_difficulty') or 3,
        'count': min(missing, 30),
        'kind': kind,
    }]


def _read_plan(request):
    """План со стоп-гейта — репетитор мог его поправить.

    Ведущее поле теперь `row_query` (формулировка строки), а не тема:
    тема стала подсказкой ранжированию и может быть пустой, а вот без
    формулировки искать нечего.
    """
    queries = request.POST.getlist('row_query')
    labels = request.POST.getlist('row_label')
    topics = request.POST.getlist('row_topic')
    difficulties = request.POST.getlist('row_difficulty')
    counts = request.POST.getlist('row_count')
    kinds = request.POST.getlist('row_kind')
    keep = set(request.POST.getlist('row_keep'))

    def at(values, index, default=''):
        return values[index] if index < len(values) else default

    rows = []
    for index, query in enumerate(queries):
        if str(index) not in keep:
            continue
        query = (query or '').strip()
        if not query:
            continue
        try:
            difficulty = max(1, min(5, int(at(difficulties, index, '3'))))
            count = max(1, min(hw_generator.MAX_PROBLEMS,
                               int(at(counts, index, '1'))))
        except ValueError:
            continue
        row = {'query': query,
               'label': (at(labels, index) or query).strip(),
               'topic': at(topics, index).strip(),
               'difficulty': difficulty, 'count': count}
        # ⚠️ Тип строки едет через форму. Без него «Переискать» превращало
        # строку-тест в обычную, и под ней находились открытые задачи —
        # ровно та подмена, которую чинили в прошлой сессии.
        kind = at(kinds, index).strip()
        if kind in ('open', 'test'):
            row['kind'] = kind
        rows.append(row)
    return rows


def _read_ids(request, name):
    return [int(value) for value in request.POST.getlist(name)
            if value.isdigit()]


@tutor_required
def api_cart_rows(request):
    """Корзина → позиции работы в порядке, который увидит ученик.

    Корзина живёт в `sessionStorage` (один механизм на все конструкторы),
    поэтому названия и порядок приходится спрашивать у сервера: на клиенте
    нет ни тем, ни признака «тест», ни правила расстановки частей.
    """
    from django.http import JsonResponse

    from .picker import cart_rows, parse_points, parse_rule

    if request.method != 'POST':
        return JsonResponse({'error': 'only POST'}, status=405)
    keys = [key.strip() for key in
            (request.POST.get('keys') or '').split(',') if key.strip()]
    # ⚠️ БАЛЛЫ ЕДУТ НА СЕРВЕР ВМЕСТЕ С КОРЗИНОЙ. Состав части («3 вопроса ·
    # 6 баллов») считает питон, а балл репетитор правит прямо на экране;
    # без этого заголовок показывал бы баллы по умолчанию, пока в строках
    # стоят исправленные. Складывать их на клиенте нельзя: склонение
    # «балл / балла / баллов» тогда существовало бы в двух местах.
    # ⚠️ ПОДСКАЗКА БАЛЛА ПРОСИТСЯ ЯВНО. Новый поток предлагает балл по
    # сложности задачи, прежние конструкторы — прежнее значение по
    # умолчанию; молча поменять его всем значило бы переоценить работы,
    # собираемые на старых экранах прямо сейчас.
    # ⚠️ ПРАВИЛО НАЧИСЛЕНИЯ ПРИЕЗЖАЕТ ВМЕСТЕ С НИМИ (ревью 17.08, ф. 1).
    # `points` — только РУЧНЫЕ правки; остальным позициям цену считает
    # правило, и считает её сервер: пока это делал экран, шаг «Состав» и
    # запись работы расходились молча.
    rows = cart_rows(keys, request.user,
                     manual_order=request.POST.get('manual_order') == '1',
                     points=parse_points(request.POST.get('points')),
                     suggest=request.POST.get('suggest') == '1',
                     rule=(parse_rule(request.POST.get('rule'))
                           if request.POST.get('rule') is not None else None))
    return JsonResponse({'rows': rows})


@tutor_required
def api_more_candidates(request):
    """«Показать ещё 5» — СЛЕДУЮЩАЯ порция кандидатов под одну строку.

    ⚠️ К МОДЕЛИ НЕ ХОДИМ И СЧЁТЧИК НЕ ТРОГАЕМ. Поиск по своему банку
    обращений не стоит, и расходовать на него суточный лимит было бы
    прямым обманом: репетитор увидел бы «использовано 7 из 30» после
    единственного разбора запроса.
    """
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'only POST'}, status=405)

    def number(name, default, low, high):
        try:
            return max(low, min(high, int(request.POST.get(name) or default)))
        except ValueError:
            return default

    query = (request.POST.get('query') or '').strip()
    if not query:
        return JsonResponse({'error': 'пустая строка запроса'}, status=400)
    kind = (request.POST.get('kind') or '').strip()
    row = {
        'query': query,
        'label': (request.POST.get('label') or query).strip(),
        'topic': (request.POST.get('topic') or '').strip(),
        'difficulty': number('difficulty', 3, 1, 5),
        'count': number('count', 1, 1, hw_generator.MAX_PROBLEMS),
    }
    if kind in ('open', 'test'):
        row['kind'] = kind

    offset = number('offset', 0, 0, 500)
    cards, has_more = hw_generator.row_candidates(
        row, has_answer=request.POST.get('has_answer') == 'on',
        offset=offset)
    return JsonResponse({
        'has_more': has_more,
        # ⚠️ ДОГРУЖЕННАЯ КАРТОЧКА НЕСЁТ ТО ЖЕ, ЧТО СЕРВЕРНАЯ (ревью 15.08,
        # фаза 13): условие целиком, пункты, ответ, есть ли решение. Иначе
        # задачи из «Показать ещё 5» раскрывались бы беднее соседних, и
        # выбирать пришлось бы по разному объёму сведений.
        'cards': [{
            'id': card['id'],
            'title': card['title'],
            'meta': card['meta'],
            'body': card['body'],
            'parts': card['parts'],
            'answer': card['answer'],
            'has_solution': card['has_solution'],
            'is_test': card['is_test'],
            'confidence': card['confidence'],
            'confidence_label': card['confidence_label'],
        } for card in cards],
    })


# ---------------------------------------------------------------------------
# Часть D — экспорт задания в .tex и PDF
# ---------------------------------------------------------------------------

@tutor_required
def assignment_export(request, group_id, assignment_id):
    """Листок для печати: `.tex` всегда, PDF — где есть TeX Live.

    Два варианта одного задания: ученику (без ответов) и преподавателю
    (с ответами и решениями). Выбор — параметром `for`, формат — `fmt`.
    """
    from django.http import HttpResponse

    from problems import assignment_export as export

    from .access import group_assignment_or_404, own_group_or_404

    group = own_group_or_404(request.user, group_id)
    assignment = group_assignment_or_404(group, assignment_id)

    for_teacher = request.GET.get('for') == 'teacher'
    stem = _safe_stem(assignment.name) + ('-ответы' if for_teacher else '')

    if request.GET.get('fmt') == 'browser-pdf':
        # Печать той же страницы, что и «Версия для печати», настоящим
        # браузером. За выключенным по умолчанию флагом — см.
        # `assignment_export.pdf_button_enabled`.
        from django.template.loader import render_to_string

        rows, skipped = export.print_rows(assignment, for_teacher=for_teacher)
        html = render_to_string('teacher/assignment_print.html', {
            'assignment': assignment, 'group': group, 'rows': rows,
            'skipped': skipped, 'for_teacher': for_teacher,
            'deadline': assignment.deadline_at,
            'total_points': export.total_points(rows),
            'back_url': '', 'other_url': '', 'other_label': '',
        }, request=request)
        pdf, error = export.browser_pdf(html)
        if pdf is None:
            messages.warning(request, error)
            return redirect(reverse('teacher:assignment_print',
                                    args=[group.pk, assignment.pk])
                            + ('?for=teacher' if for_teacher else ''))
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = (
            'attachment; filename*=UTF-8\'\'%s.pdf' % _urlquote(stem))
        return response

    tex, skipped = export.build_tex(assignment, for_teacher=for_teacher)

    if request.GET.get('fmt') == 'pdf':
        pdf, error = export.compile_pdf(tex)
        if pdf is None:
            # Прод без TeX Live — честно объясняем и отдаём .tex, а не 500.
            messages.warning(request, error)
            return _tex_response(tex, stem)
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = (
            'attachment; filename*=UTF-8\'\'%s.pdf'
            % _urlquote(stem))
        return response

    if skipped:
        messages.warning(
            request, 'Пропущено задач из-за испорченной разметки: %d. '
                     'Остальные в листок вошли.' % len(skipped))
    return _tex_response(tex, stem)


@tutor_required
@require_POST
def cart_print(request):
    """Печатный лист ДО создания работы — по корзине конструктора.

    ⚠️ ТА ЖЕ СБОРКА, ЧТО У СОЗДАННОЙ РАБОТЫ (`assignment_export.print_rows`)
    и тот же шаблон. Предпросмотр, собранный своим кодом, показывал бы не
    то, что напечатается потом, — а это ровно та ошибка, ради которой
    предпросмотр и заводится.

    Работы ещё нет, поэтому вместо неё — оболочка с теми полями, которые
    читает шаблон. В базу не пишем НИЧЕГО.
    """
    from types import SimpleNamespace

    from problems import assignment_export as export

    from .picker import cart_items, parse_points, parse_rule

    keys = [key.strip() for key in
            (request.POST.get('keys') or '').split(',') if key.strip()]
    items, _ = cart_items(keys, request.user,
                          manual_order=request.POST.get('manual_order') == '1',
                          points=parse_points(request.POST.get('points')),
                          rule=(parse_rule(request.POST.get('rule'))
                                if request.POST.get('rule') is not None
                                else None))
    is_exam = request.POST.get('kind') == 'exam'
    shell = SimpleNamespace(
        pk=None,
        name=(request.POST.get('work_name') or '').strip()
             or 'Новая работа',
        is_exam=is_exam, manual_order=request.POST.get('manual_order') == '1',
        group=None, group_id=None, deadline_at=None)
    for_teacher = request.POST.get('for') == 'teacher'
    rows, skipped = export.print_rows(shell, for_teacher=for_teacher,
                                      items=items)
    return render(request, 'teacher/assignment_print.html', {
        'assignment': shell,
        'group': None,
        'rows': rows,
        'skipped': skipped,
        'for_teacher': for_teacher,
        'deadline': None,
        'total_points': export.total_points(rows),
        'site_home': request.build_absolute_uri('/'),
        # Возврата и переключателя вариантов у предпросмотра нет: он
        # открывается отдельной вкладкой и закрывается ею же.
        'back_url': '',
        'other_url': '',
        'other_label': '',
        'pdf_enabled': False,
        'pdf_url': '',
        'is_preview': True,
    })


@tutor_required
def assignment_print(request, group_id, assignment_id):
    """Версия для печати: браузер печатает то, что уже умеет рисовать.

    ⚠️ ДЕКОРАТОРА ЗДЕСЬ НЕ БЫЛО — единственный маршрут кабинета без проверки
    роли. Внутри стоит `own_group_or_404`, и для ВОШЕДШЕГО репетитора этого
    достаточно. Но для гостя `request.user` — это `AnonymousUser`, а фильтр
    `teacher=AnonymousUser` не «не находит», а падает несравнимым типом:

        TypeError: Field 'id' expected a number but got <AnonymousUser>

    То есть гость получал 500 вместо 403 — и вместе с ней трассировку, если
    отладочный режим включён. Данные не утекали (до базы дело не доходило),
    но пятисотая на месте проверки прав — это и шум в мониторинге, и
    подсказка сканеру, что маршрут живой и обрабатывается иначе остальных.

    ⚠️ ЭТО ОСНОВНОЙ СПОСОБ ПОЛУЧИТЬ ЛИСТОК, а `.tex` — для тех, кто хочет
    его доработать. Причина простая: сайт уже рисует эти формулы верно, а
    собранный не тем компилятором `.tex` молча теряет всю кириллицу.
    Функция, результат которой зависит от того, угадал ли пользователь
    движок, сломана.
    """
    from problems import assignment_export as export

    from .access import group_assignment_or_404, own_group_or_404

    group = own_group_or_404(request.user, group_id)
    assignment = group_assignment_or_404(group, assignment_id)
    for_teacher = request.GET.get('for') == 'teacher'
    rows, skipped = export.print_rows(assignment, for_teacher=for_teacher)

    here = reverse('teacher:assignment_print', args=[group.pk, assignment.pk])
    return render(request, 'teacher/assignment_print.html', {
        'assignment': assignment,
        'group': group,
        'rows': rows,
        'skipped': skipped,
        'for_teacher': for_teacher,
        'deadline': assignment.deadline_at,
        'total_points': export.total_points(rows),
        # Подвал листка ведёт на ГЛАВНУЮ, а не на этот раздел: листок
        # попадает к ученику и родителю, и адрес внутренней страницы
        # кабинета им бесполезен. Собираем абсолютный — распечатанный
        # относительный путь никуда не ведёт.
        'site_home': request.build_absolute_uri('/'),
        'back_url': reverse('teacher:group_assignment',
                            args=[group.pk, assignment.pk]),
        'other_url': here + ('' if for_teacher else '?for=teacher'),
        'other_label': ('вариант ученикам' if for_teacher
                        else 'вариант с ответами'),
        'pdf_enabled': export.pdf_button_enabled(),
        'pdf_url': (reverse('teacher:assignment_export',
                            args=[group.pk, assignment.pk])
                    + '?fmt=browser-pdf'
                    + ('&for=teacher' if for_teacher else '')),
    })


def _tex_response(tex, stem):
    from django.http import HttpResponse

    response = HttpResponse(tex, content_type='application/x-tex; charset=utf-8')
    response['Content-Disposition'] = (
        'attachment; filename*=UTF-8\'\'%s.tex' % _urlquote(stem))
    return response


def _safe_stem(name):
    import re

    stem = re.sub(r'[^\w\s\-]', '', name, flags=re.UNICODE).strip()
    stem = re.sub(r'\s+', '-', stem)
    return stem[:60] or 'работа'


def _urlquote(text):
    from urllib.parse import quote

    return quote(text)
