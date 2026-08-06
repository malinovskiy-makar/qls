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
from django.db import IntegrityError, transaction


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
        return 'answer_item_%d_part_%d' % (item.pk, part.pk)
    return 'answer_item_%d' % item.pk


def answer_parts(item):
    """Пункты, на которые ученик отвечает ОТДЕЛЬНО. Всегда непустой список.

    ⚠️ Задача БЕЗ пунктов — частный случай «один пункт» (`None`). Так у
    ввода, автопроверки и показа результата ровно ОДИН путь кода; ветка
    «если пунктов нет, то по-другому» — то, из-за чего половина экранов
    этого проекта уже расходилась между собой.

    Пункты теста сюда НЕ попадают: там подпункты играют роль вариантов
    ответа, и отдельного поля ввода у каждого быть не должно.
    """
    if item.is_custom or item.catalog_problem_id is None:
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


def part_max_score(item, part, parts_count):
    """Максимум баллов за пункт.

    Свой балл пункта — если задан; иначе балл задачи делится поровну.
    Делить нечего (балл задачи не задан) — считаем единицу, как везде.
    """
    from decimal import Decimal

    if part is not None and part.points is not None:
        return Decimal(part.points)
    total = Decimal(item.points) if item.points is not None else Decimal('1')
    if parts_count <= 1:
        return total
    return (total / Decimal(parts_count)).quantize(Decimal('0.01'))


def part_correct_answer(item, part):
    """Эталонный ответ на пункт (или на задачу целиком, если пункт None)."""
    if part is not None:
        return (part.answer or '').strip()
    return (item.correct_answer or '').strip()


def solution_input_name(item):
    return 'text_item_%d' % item.pk


def file_input_name(item):
    return 'file_item_%d' % item.pk


def item_answer_form(item):
    """(вид ввода, варианты) для позиции.

    Варианты — список словарей `{'value', 'label', 'is_html'}`. `value` это
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
        options = [{'value': str(o.pk), 'label': o.text, 'is_html': False}
                   for o in problem.options.all()]
        return kind, options

    problem = item.catalog_problem
    if problem is None:
        return ANSWER_TEXT, []
    ptype = problem.problem_type or ''
    parts = list(problem.parts.all())
    if not ptype.startswith('тест') or not parts:
        return ANSWER_TEXT, []

    options = [{'value': p.label, 'label': p.statement, 'is_html': True,
                'part_label': p.label}
               for p in parts]
    # «Один ответ» — переключатель; «все верные» и «верно/неверно» — галочки
    # (в обоих случаях ученик отмечает ПОДМНОЖЕСТВО утверждений).
    if ptype == 'тест: один ответ':
        return ANSWER_RADIO, options
    return ANSWER_CHECKBOX, options


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
        key = part_row['part'].pk if part_row['part'] is not None else None
        draft = drafts.get(key)
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

    items = list(
        assignment.items
        .select_related('catalog_problem', 'custom_problem', 'graph')
        .prefetch_related('catalog_problem__parts', 'catalog_problem__hints',
                          'custom_problem__options')
        .order_by('order', 'id'))

    comments_by_item = {}
    if with_comments and items:
        for comment in (ProblemComment.objects.visible_for(user)
                        .filter(assignment=assignment)
                        .select_related('author')):
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
            .prefetch_related('part_answers__part', 'feedback__mistakes')}

    rows = []
    for number, item in enumerate(items, start=1):
        submission = known.get(item.pk)
        if submission is None:
            submission = get_or_create_submission(student, assignment, item)
            stored = None
        else:
            stored = {a.part_id: a for a in submission.part_answers.all()}
        kind, options = item_answer_form(item)
        problem = item.problem
        status = work_status(submission, submission.submitted_answer,
                             submission.solution_text)
        rows.append({
            'item': item,
            'number': number,
            'problem': problem,
            'title': item.problem_title,
            'statement': item.statement,
            # Подпункты показываем только когда они НЕ варианты ответа:
            # иначе один и тот же список нарисовался бы дважды.
            'parts': (list(item.catalog_problem.parts.all())
                      if item.catalog_problem_id and kind == ANSWER_TEXT
                      else []),
            'hints': (list(item.catalog_problem.hints.all())
                      if item.catalog_problem_id else []),
            'answer_kind': kind,
            'options': options,
            # Пункты с ОТДЕЛЬНЫМ ответом на каждый. У задачи без пунктов —
            # ровно одна строка «вся задача»: один путь кода на все случаи.
            'answer_parts': _part_rows(item, submission, stored),
            'has_real_parts': _has_real_parts(item),
            # Верный ответ показываем только после сдачи — до неё это
            # подсказка, а не обратная связь.
            'show_correct': submission.status in ('submitted', 'reviewed'),
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
            'solution_visible': item.is_solution_visible_for(user),
            'solution_hint': item.solution_unlock_hint(),
            'has_solution': item.has_solution,
            'solution_text': item.solution_text,
            'graph': item.graph,
        })
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
