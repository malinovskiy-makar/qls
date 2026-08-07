"""
Вкладка «Группы» — рабочая поверхность репетитора.

ПРИНЦИП: вся работа с группой происходит ВНУТРИ этой вкладки. Единственное
исключение — дашборд входящих (`/teacher/`): он не рабочая поверхность,
а навигация. Проверить работу с дашборда нельзя, можно только перейти туда,
где её проверяют.
"""
import json
from datetime import timedelta

from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from problems import timefmt

from .access import group_assignment_or_404, own_group_or_404, tutor_required


# ---------------------------------------------------------------------------
# Общие подсчёты
# ---------------------------------------------------------------------------

def _pending_count(assignments):
    """Сколько работ ждёт проверки среди переданных заданий."""
    from problems.models import Submission
    return Submission.objects.filter(
        assignment__in=assignments, status='submitted').count()


def assignment_stats(assignment):
    """Сводка по заданию: сдано / из скольких / ждёт проверки."""
    from problems.models import Submission
    from problems.timefmt import deadline_pair

    students = assignment.students.count()
    submitted_students = (Submission.objects
                          .filter(assignment=assignment,
                                  status__in=('submitted', 'reviewed'))
                          .values('student').distinct().count())
    pending = Submission.objects.filter(assignment=assignment,
                                        status='submitted').count()
    deadline = assignment.deadline_at
    human, exact = deadline_pair(deadline)
    return {
        'assignment': assignment,
        'students': students,
        'submitted': submitted_students,
        'pending': pending,
        'deadline': deadline,
        'deadline_human': human,
        'deadline_exact': exact,
        # ⚠️ «Проверено» имеет смысл ТОЛЬКО когда было что проверять.
        # Раньше бейдж «проверено» стоял у заданий, где сдали 0 из 3, — это
        # не заслуга, а пустота, и читалось как «всё в порядке».
        'nobody_submitted': submitted_students == 0,
        'all_checked': submitted_students > 0 and pending == 0,
        'is_exam': assignment.is_exam,
    }


# ---------------------------------------------------------------------------
# Фаза 9 — список групп
# ---------------------------------------------------------------------------

@tutor_required
def groups_list(request):
    from problems.models import Assignment, StudentGroup, Submission

    groups = (StudentGroup.objects
              .filter(teacher=request.user)
              .prefetch_related('students')
              .order_by('name'))

    now = timezone.now()
    cards = []
    for group in groups:
        assignments = list(Assignment.objects.filter(group=group))
        deadlines = [a.deadline_at for a in assignments
                     if a.deadline_at and a.deadline_at >= now]
        last_submission = (Submission.objects
                           .filter(assignment__group=group)
                           .order_by('-submitted_at')
                           .values_list('submitted_at', flat=True).first())
        cards.append({
            'group': group,
            'students': group.students.count(),
            'pending': _pending_count(assignments),
            'next_deadline': min(deadlines) if deadlines else None,
            'last_activity': last_submission or group.created_at,
            'assignments': len(assignments),
        })

    return render(request, 'teacher/groups/list.html', {'cards': cards})


@tutor_required
def group_create(request):
    from problems.models import StudentGroup

    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        if not name:
            messages.error(request, 'Название группы не может быть пустым.')
        else:
            group = StudentGroup.objects.create(
                name=name, teacher=request.user,
                description=(request.POST.get('description') or '').strip())
            messages.success(request, f'Группа «{group.name}» создана.')
            return redirect('teacher:group_detail', pk=group.pk)

    return render(request, 'teacher/groups/create.html')


# ---------------------------------------------------------------------------
# Фаза 10 — страница группы (три вкладки)
# ---------------------------------------------------------------------------

@tutor_required
def group_detail(request, pk):
    from problems.models import Assignment, Submission, TeacherFeedback

    group = own_group_or_404(request.user, pk)
    tab = request.GET.get('tab', 'students')
    if tab not in ('students', 'assignments', 'materials'):
        tab = 'students'

    # ⚠️ СОРТИРОВКА ПО ДЕДЛАЙНУ, БЛИЖАЙШИЕ ПЕРВЫМИ. Раньше стоял порядок по
    # дате создания, и список выглядел случайным: 08.08, 07.08, 05.08, 28.07,
    # 09.08 — ни по дате, ни по типу.
    #
    # Задания БЕЗ срока уходят в конец: у них нет места на шкале времени, и
    # ставить их первыми значило бы прятать за ними то, что горит.
    assignments = sorted(
        Assignment.objects.filter(group=group).prefetch_related('students'),
        key=lambda a: (a.deadline_at is None, a.deadline_at or a.created_at))

    student_rows = []
    if tab == 'students':
        for student in group.students.all().order_by('last_name', 'username'):
            subs = Submission.objects.filter(assignment__group=group,
                                             student=student)
            scores = [float(f.score) for f in TeacherFeedback.objects.filter(
                submission__in=subs, score__isnull=False)]
            student_rows.append({
                'student': student,
                'submitted': subs.filter(
                    status__in=('submitted', 'reviewed')).count(),
                'pending': subs.filter(status='submitted').count(),
                'avg_score': round(sum(scores) / len(scores), 2)
                if scores else None,
                'last_login': student.last_login,
            })

    return render(request, 'teacher/groups/detail.html', {
        'group': group,
        'tab': tab,
        'student_rows': student_rows,
        'assignment_rows': [assignment_stats(a) for a in assignments],
    })


# ---------------------------------------------------------------------------
# Фаза 11 — просмотр задания ДО решений
# ---------------------------------------------------------------------------

def _item_title(item):
    """Заголовок задачи для экрана. Пусто — берём начало условия.

    В банке у части задач заголовка нет вовсе, а у части он совпадает с
    условием. Показывать «Задача #40131» бессмысленно, поэтому подставляем
    первые слова условия — обрезкой ПО ГРАНИЦЕ СЛОВА, чтобы не рвать числа
    («переменные — 300…» вместо 3000).
    """
    from problems.text_clean import preview_title

    problem = item.problem
    if problem is None:
        return '(задача удалена)'
    return preview_title(problem, limit=70)


def _source_label(item):
    """Откуда задача: «своя» / «тест» / «каталог». Одно слово, мелким."""
    if item.is_custom:
        return 'своя'
    if item.is_test:
        return 'тест'
    return 'каталог'


def _answer_rows(item):
    """Строки «пункт → что предлагает каталог → что утверждено».

    Тесты и свои задачи сюда не идут: у теста верный вариант задан
    разметкой, у своей задачи эталон писал сам репетитор.
    """
    from problems.assignment_rows import (
        answer_parts, catalog_answer_for, part_max_score,
    )

    if item.is_custom or item.is_test or item.catalog_problem_id is None:
        return []

    parts = answer_parts(item)
    rows = []
    for part in parts:
        rows.append({
            'part': part,
            'key': '' if part is None else str(part.pk),
            'label': (part.label if part is not None else ''),
            'statement': (part.statement if part is not None
                          else item.statement),
            'from_catalog': catalog_answer_for(item, part),
            'approved': item.approved_answer(part),
            'max_score': part_max_score(item, part, len(parts)),
        })
    return rows


@tutor_required
def group_assignment_detail(request, group_id, assignment_id):
    """Задание целиком глазами репетитора — ещё до того, как кто-то решал.

    Ради этого экрана и заводилась позиция задачи в домашке: здесь рядом
    стоят задачи каталога и свои, у каждой своё условие, свой правильный
    ответ, своя решалка и своё обсуждение.
    """
    from problems.models import ProblemComment

    group = own_group_or_404(request.user, group_id)
    assignment = group_assignment_or_404(group, assignment_id)

    from problems.assignment_rows import ordered_items, section_marks

    # Порядок и деление на части — та же функция, что у ученика и у листка.
    items = ordered_items(assignment, list(
        assignment.items
        .select_related('catalog_problem', 'custom_problem')
        .prefetch_related('custom_problem__options',
                          'catalog_problem__parts')
        .order_by('order', 'id')))
    marks = section_marks(items)

    comments = (ProblemComment.objects.visible_for(request.user)
                .filter(assignment=assignment)
                .select_related('author'))
    by_item = {}
    for comment in comments:
        by_item.setdefault(comment.problem_item_id, []).append(comment)

    rows = []
    for index, item in enumerate(items):
        options = []
        if item.is_custom and item.custom_problem.is_test:
            options = list(item.custom_problem.options.all())
        rows.append({
            'item': item,
            'number': index + 1,
            'section_title': marks.get(index, ''),
            # ⚠️ Заголовок задачи на экране РАНЬШЕ НЕ ПОКАЗЫВАЛСЯ, хотя в
            # печатном листке был. Из-за этого страница из семи позиций
            # читалась сплошной простынёй: зацепиться глазом не за что.
            'title': _item_title(item),
            'source_label': _source_label(item),
            'options': options,
            'parts': list(item.catalog_problem.parts.all())
            if item.catalog_problem_id else [],
            'comments': by_item.get(item.pk, []),
            # Что именно уйдёт в автопроверку — по строке на пункт.
            'answer_rows': _answer_rows(item),
            'answers_approved': item.answers_approved,
            'needs_approval': not item.answers_approved,
        })

    from problems.models import SolutionVisibility

    return render(request, 'teacher/groups/assignment_detail.html', {
        'group': group,
        'assignment': assignment,
        'rows': rows,
        'stats': assignment_stats(assignment),
        'solution_visibility': SolutionVisibility.choices,
    })


# ---------------------------------------------------------------------------
# Фаза 12 — комментарии: JSON-эндпоинт (без перезагрузки страницы)
# ---------------------------------------------------------------------------

@require_POST
def api_comment_create(request):
    """Добавить комментарий к позиции задачи.

    Доступен и репетитору, и ученику — правила видимости разные, а точка
    входа одна: два почти одинаковых эндпоинта разъехались бы.
    """
    from problems.models import AssignmentItem, ProblemComment

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Нужен вход'}, status=403)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Неверный формат'}, status=400)

    text = (body.get('text') or '').strip()
    if not text:
        return JsonResponse({'error': 'Пустой комментарий'}, status=400)

    item = get_object_or_404(
        AssignmentItem.objects.select_related('assignment'),
        pk=body.get('item_id'))
    assignment = item.assignment

    tutor = item.is_tutor_for(request.user)
    if not tutor and not assignment.students.filter(
            pk=request.user.pk).exists():
        return JsonResponse({'error': 'Нет доступа'}, status=403)

    if tutor:
        # Репетитор выбирает видимость сам, по умолчанию — «видят все».
        visibility = (ProblemComment.Visibility.PRIVATE
                      if body.get('visibility') == 'private'
                      else ProblemComment.Visibility.GROUP)
        recipient_id = body.get('recipient_id') or None
    else:
        # Вопрос ученика ВСЕГДА приватный: публичные вопросы учеников —
        # это канал списывания, а не обсуждение.
        visibility = ProblemComment.Visibility.PRIVATE
        recipient_id = None

    comment = ProblemComment.objects.create(
        assignment=assignment, problem_item=item, author=request.user,
        text=text, visibility=visibility, recipient_id=recipient_id)

    return JsonResponse({
        'id': comment.pk,
        'author': comment.author.get_full_name() or comment.author.username,
        'text': comment.text,
        'visibility': comment.visibility,
        'visibility_display': comment.get_visibility_display(),
        'created_at': timefmt.fmt(comment.created_at),
    })


# ---------------------------------------------------------------------------
# Фаза 14 — дашборд входящих
# ---------------------------------------------------------------------------

@tutor_required
def dashboard(request):
    """Где что ждёт. Только НАВИГАЦИЯ: проверять и оценивать отсюда нельзя.

    Соблазн «проверю прямо здесь» велик, но тогда работа с группой уехала
    бы из вкладки «Группы» и разъехалась по двум местам.
    """
    from problems.models import Assignment, StudentGroup, Submission

    now = timezone.now()
    groups = list(StudentGroup.objects.filter(teacher=request.user))
    assignments = list(Assignment.objects.filter(group__in=groups)
                       .select_related('group'))

    # 1. Ждёт проверки.
    pending_rows = []
    for assignment in assignments:
        count = Submission.objects.filter(assignment=assignment,
                                          status='submitted').count()
        if count:
            pending_rows.append({'assignment': assignment,
                                 'group': assignment.group, 'count': count})
    pending_rows.sort(key=lambda r: -r['count'])

    # 2. Просроченные дедлайны — кто не сдал вовремя.
    overdue_rows = []
    for assignment in assignments:
        deadline = assignment.deadline_at
        if not deadline or deadline >= now:
            continue
        done = set(Submission.objects
                   .filter(assignment=assignment,
                           status__in=('submitted', 'reviewed'))
                   .values_list('student_id', flat=True))
        missing = [s for s in assignment.students.all() if s.pk not in done]
        if missing:
            overdue_rows.append({'assignment': assignment,
                                 'group': assignment.group,
                                 'students': missing,
                                 'deadline': deadline})
    overdue_rows.sort(key=lambda r: r['deadline'], reverse=True)

    # 3. Ближайшие дедлайны — на неделю вперёд.
    week = now + timedelta(days=7)
    upcoming = sorted(
        ({'assignment': a, 'group': a.group, 'deadline': a.deadline_at}
         for a in assignments
         if a.deadline_at and now <= a.deadline_at <= week),
        key=lambda r: r['deadline'])

    # 4. Давно не заходили — больше 14 дней.
    threshold = now - timedelta(days=14)
    quiet = []
    seen = set()
    for group in groups:
        for student in group.students.all():
            if student.pk in seen:
                continue
            seen.add(student.pk)
            if student.last_login is None or student.last_login < threshold:
                quiet.append({'student': student, 'group': group,
                              'last_login': student.last_login})

    return render(request, 'teacher/dashboard_inbox.html', {
        'pending_rows': pending_rows,
        'overdue_rows': overdue_rows,
        'upcoming_rows': upcoming,
        'quiet_rows': quiet,
        'groups_count': len(groups),
    })


# ---------------------------------------------------------------------------
# Фаза 13 — проверка решений переехала под групповые URL
# ---------------------------------------------------------------------------
#
# Логику проверки НЕ меняли: те же вьюхи и те же шаблоны, просто адрес теперь
# начинается с группы. Смысл переезда — принцип «вся работа с группой внутри
# вкладки Группы»: раньше репетитор из группы проваливался в /teacher/
# assignment/<pk>/ и терял контекст, в какой он вообще группе.

@tutor_required
def group_submissions(request, group_id, assignment_id):
    """Таблица решений по заданию — внутри группы."""
    from .views import assignment_detail

    group = own_group_or_404(request.user, group_id)
    assignment = group_assignment_or_404(group, assignment_id)
    return assignment_detail(request, assignment.pk, group=group)


@tutor_required
def student_work_review(request, assignment_id, student_id, group_id=None):
    """Разбор работы ученика — ТОТ ЖЕ экран, что видит ученик.

    ⚠️ Именно тот же, а не «похожий»: если ученик спорит с оценкой, спорить
    надо об одном экране. Отдельная «версия для преподавателя» разошлась бы
    с ученической на первой же правке.

    ⚠️ ГРУППА НЕОБЯЗАТЕЛЬНА. Раньше адрес был только групповым, и у работы
    без группы (а такие есть — их создаёт старый конструктор домашек)
    кнопка «посмотреть глазами ученика» просто ИСЧЕЗАЛА со страницы
    проверки: `work_review_url` считался `None`. Пропавшая кнопка для
    пользователя неотличима от сломанной, поэтому у экрана появился второй,
    безгрупповой адрес, а права проверяются по автору работы.
    """
    from django.urls import reverse

    from problems.models import Assignment, User

    from student.views import work_review_context

    if group_id is not None:
        group = own_group_or_404(request.user, group_id)
        assignment = group_assignment_or_404(group, assignment_id)
        student = get_object_or_404(User, pk=student_id,
                                    enrolled_groups=group)
        back_url = reverse('teacher:group_submissions',
                           args=[group.pk, assignment.pk])
    else:
        assignment = get_object_or_404(Assignment, pk=assignment_id)
        if not (request.user.is_staff or assignment.author_id == request.user.pk
                or (assignment.group_id
                    and assignment.group.teacher_id == request.user.pk)):
            raise Http404
        student = get_object_or_404(User, pk=student_id,
                                    assignments_received=assignment)
        back_url = reverse('teacher:assignment_detail', args=[assignment.pk])

    context = work_review_context(
        assignment, student, viewer=request.user, for_tutor=True,
        back_url=back_url, back_label='К решениям')
    return render(request, 'student/work_review.html', context)


@tutor_required
def group_review_submission(request, group_id, submission_id):
    """Форма оценки решения — внутри группы."""
    from problems.models import Submission

    from .views import review_submission

    group = own_group_or_404(request.user, group_id)
    submission = get_object_or_404(Submission, pk=submission_id,
                                   assignment__group=group)
    return review_submission(request, submission.pk, group=group)


# ---------------------------------------------------------------------------
# Фаза 20 — решалка прямо на странице задания
# ---------------------------------------------------------------------------

@require_POST
@tutor_required
def api_item_answers(request):
    """Утвердить (или заменить своим) то, что будет проверяться машиной.

    Пишем в ПОЗИЦИЮ задания, а не в каталог: каталог общий на всех
    репетиторов, а утверждение — решение конкретного человека для
    конкретной работы. `answers = {}` или `null` снимает утверждение и
    возвращает задачу на ручную проверку.
    """
    from problems.assignment_rows import answer_parts
    from problems.models import AssignmentItem

    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Неверный формат'}, status=400)

    item = get_object_or_404(
        AssignmentItem.objects.select_related('assignment', 'catalog_problem',
                                              'custom_problem'),
        pk=body.get('item_id'))
    if not item.is_tutor_for(request.user):
        return JsonResponse({'error': 'Нет доступа'}, status=403)

    if body.get('clear'):
        item.answer_override = None
        item.save(update_fields=['answer_override'])
        return JsonResponse({'ok': True, 'approved': item.answers_approved,
                             'answers': {}})

    incoming = body.get('answers') or {}
    if not isinstance(incoming, dict):
        return JsonResponse({'error': 'Неверный формат'}, status=400)

    # Ключи принимаем ТОЛЬКО те, что есть у этой задачи: чужой pk в JSON не
    # должен превращаться в невидимую запись, которую потом никто не найдёт.
    allowed = {('' if part is None else str(part.pk))
               for part in answer_parts(item)}
    answers = {key: str(value or '').strip()
               for key, value in incoming.items() if key in allowed}
    answers = {key: value for key, value in answers.items() if value}
    item.answer_override = answers or None
    item.save(update_fields=['answer_override'])
    return JsonResponse({'ok': True, 'approved': item.answers_approved,
                         'answers': item.answer_override or {}})


@tutor_required
@require_POST
def api_item_points(request):
    """Максимальный балл за позицию — правится прямо на странице задания.

    Балл и есть максимум: два отдельных элемента «показать балл» и «задать
    максимум» были бы одним и тем же числом в двух местах, а два места для
    одного числа всегда расходятся.

    Отрицательный балл не принимаем: за задачу нельзя получить меньше нуля,
    и такое число сломало бы и сумму работы, и проценты.
    """
    from decimal import Decimal, InvalidOperation

    from problems.models import AssignmentItem

    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Неверный формат'}, status=400)

    item = get_object_or_404(
        AssignmentItem.objects.select_related('assignment'),
        pk=body.get('item_id'))
    if not item.is_tutor_for(request.user):
        return JsonResponse({'error': 'Нет доступа'}, status=403)

    raw = str(body.get('points', '')).strip().replace(',', '.')
    try:
        points = Decimal(raw)
    except (InvalidOperation, ValueError):
        return JsonResponse({'error': 'Нужно число'}, status=400)
    if points < 0:
        return JsonResponse({'error': 'Балл не может быть меньше нуля'},
                            status=400)
    if points > 1000:
        return JsonResponse({'error': 'Слишком большой балл'}, status=400)

    item.points = points
    item.save(update_fields=['points'])

    from problems.assignment_export import total_points, print_rows

    rows, _ = print_rows(item.assignment)
    return JsonResponse({'ok': True,
                         'points': _clean_points(item.points),
                         'total': _clean_points(total_points(rows))})


def _clean_points(value):
    """«3.00» → «3», «2.50» → «2.5». Хвостовые нули на экране — шум."""
    if value is None:
        return ''
    text = ('%s' % value)
    return text.rstrip('0').rstrip('.') if '.' in text else text


@require_POST
@tutor_required
def api_item_solution(request):
    """Сохранить решение позиции и правило его показа.

    Отдельным эндпоинтом, а не общей формой задания: решений в задании
    может быть десять, и отправлять их все ради правки одного — верный
    способ затереть чужую правку, сделанную в соседней вкладке.
    """
    from problems.models import AssignmentItem, SolutionVisibility

    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Неверный формат'}, status=400)

    item = get_object_or_404(
        AssignmentItem.objects.select_related('assignment'),
        pk=body.get('item_id'))
    if not item.is_tutor_for(request.user):
        return JsonResponse({'error': 'Нет доступа'}, status=403)

    if 'solution_override' in body:
        item.solution_override = body.get('solution_override') or ''

    mode = body.get('solution_visible_after')
    if mode in dict(SolutionVisibility.choices):
        item.solution_visible_after = mode

    if body.get('release_now'):
        # «Открыть решение сейчас» — момент фиксирует СЕРВЕР.
        item.solution_released_at = timezone.now()

    item.save()
    return JsonResponse({
        'ok': True,
        'source': item.solution_source,
        'mode': item.solution_visible_after,
        'mode_display': item.get_solution_visible_after_display(),
        'released_at': timefmt.fmt(item.solution_released_at, empty=None),
    })
