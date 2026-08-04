"""
Контрольные глазами репетитора: создание и результаты группы.

Проверка открытых задач сюда НЕ переезжает: она уже есть внутри группы
(`teacher:group_review_submission`), и второго интерфейса проверки быть не
должно — расходиться начнут не экраны, а оценки.
"""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from problems import exam_engine

from .access import own_group_or_404, tutor_required


@tutor_required
def exam_create(request, pk):
    """Конструктор контрольной: как у домашки плюс блок времени.

    Валидация — НА ФОРМЕ, а не 500-я: репетитор, поставивший конец окна
    раньше начала, должен увидеть подсказку, а не страницу ошибки.
    """
    from problems.models import Assignment, AssignmentItem, Problem

    group = own_group_or_404(request.user, pk)
    form = {'kind': 'window', 'show_results': True}
    errors = []

    if request.method == 'POST':
        form, errors = _read_exam_form(request)
        problem_ids = [int(value) for value in
                       request.POST.getlist('problem_ids') if value.isdigit()]
        if not problem_ids:
            errors.append('Добавьте хотя бы одну задачу.')

        if not errors:
            exam = Assignment.objects.create(
                name=form['name'], author=request.user, group=group,
                kind=Assignment.Kind.EXAM,
                exam_mode=(Assignment.ExamMode.WINDOW if form['kind'] == 'window'
                           else Assignment.ExamMode.LIMIT),
                starts_at=form['starts_at'], ends_at=form['ends_at'],
                duration_minutes=form['duration'],
                deadline=form['deadline'],
                show_results_immediately=form['show_results'])
            exam.students.set(group.students.all())
            problems = {p.pk: p for p in
                        Problem.objects.filter(pk__in=problem_ids)}
            for order, problem_id in enumerate(problem_ids):
                problem = problems.get(problem_id)
                if problem is None:
                    continue
                AssignmentItem.objects.create(assignment=exam,
                                              catalog_problem=problem,
                                              order=order)
            # Старый M2M заполняем тоже — на нём держатся прежние экраны.
            exam.problems.set([p for p in problems.values()])
            messages.success(request, f'Контрольная «{exam.name}» создана.')
            return redirect('teacher:group_exam_results', group_id=group.pk,
                            exam_id=exam.pk)

        for error in errors:
            messages.error(request, error)

    # Выбирать задачи предлагаем из СОХРАНЁННЫХ репетитором: собирать
    # контрольную поиском по 31 тысяче задач прямо в форме — не выбор, а
    # лотерея. Каталог для отбора уже есть, кнопка «Сохранить» на странице
    # задачи тоже.
    from problems.models import SavedProblem

    candidates = [saved.catalog_problem for saved in
                  SavedProblem.objects.filter(owner=request.user,
                                              is_deleted=False,
                                              catalog_problem__isnull=False)
                  .select_related('catalog_problem')]

    return render(request, 'teacher/groups/exam_create.html', {
        'group': group,
        'form': form,
        'errors': errors,
        'candidates': candidates,
        'min_window': exam_engine.MIN_WINDOW_MINUTES,
        'min_duration': exam_engine.MIN_DURATION_MINUTES,
        'max_duration': exam_engine.MAX_DURATION_MINUTES,
    })


def _read_exam_form(request):
    """Разбор и проверка формы контрольной. Возвращает (значения, ошибки)."""
    import datetime

    def moment(name):
        raw = (request.POST.get(name) or '').strip()
        if not raw:
            return None
        try:
            value = datetime.datetime.fromisoformat(raw)
        except ValueError:
            return None
        if timezone.is_naive(value):
            value = timezone.make_aware(value)
        return value

    def number(name):
        raw = (request.POST.get(name) or '').strip()
        try:
            return int(raw)
        except ValueError:
            return None

    form = {
        'name': (request.POST.get('name') or '').strip(),
        'kind': 'limit' if request.POST.get('kind') == 'limit' else 'window',
        'starts_at': moment('starts_at'),
        'ends_at': moment('ends_at'),
        'deadline': moment('deadline'),
        'duration': number('duration'),
        'show_results': request.POST.get('show_results') == 'on',
    }

    errors = []
    now = timezone.now()
    if not form['name']:
        errors.append('Название не может быть пустым.')

    if form['kind'] == 'window':
        if form['starts_at'] is None or form['ends_at'] is None:
            errors.append('Для окна нужны и начало, и конец.')
        else:
            if form['ends_at'] <= form['starts_at']:
                errors.append('Конец окна должен быть позже начала.')
            elif (form['ends_at'] - form['starts_at']).total_seconds() < \
                    exam_engine.MIN_WINDOW_MINUTES * 60:
                errors.append('Окно короче %d минут — за это время работу '
                              'не написать.' % exam_engine.MIN_WINDOW_MINUTES)
            if form['ends_at'] <= now:
                errors.append('Окно должно заканчиваться в будущем.')
        # У окна крайний срок совпадает с концом окна: два разных срока —
        # ровно та путаница, из-за которой в Части 0 чинили «без срока».
        form['deadline'] = form['ends_at']
        form['duration'] = None
    else:
        if form['deadline'] is None:
            errors.append('Для дедлайна с лимитом нужен крайний срок.')
        elif form['deadline'] <= now:
            errors.append('Крайний срок должен быть в будущем.')
        if form['duration'] is None:
            errors.append('Укажите лимит времени в минутах.')
        elif not (exam_engine.MIN_DURATION_MINUTES <= form['duration']
                  <= exam_engine.MAX_DURATION_MINUTES):
            errors.append('Лимит времени — от %d до %d минут.'
                          % (exam_engine.MIN_DURATION_MINUTES,
                             exam_engine.MAX_DURATION_MINUTES))
        form['starts_at'] = None
        form['ends_at'] = None

    return form, errors


@tutor_required
def exam_results(request, group_id, exam_id):
    """Таблица «ученик × задача»: сразу видно проваленную всеми задачу."""
    from problems.models import Assignment, ExamAttempt

    group = own_group_or_404(request.user, group_id)
    exam = get_object_or_404(Assignment, pk=exam_id, group=group,
                             kind=Assignment.Kind.EXAM)

    items = list(exam.items.select_related('catalog_problem', 'custom_problem')
                 .order_by('order', 'id'))
    attempts = {a.student_id: a for a in
                ExamAttempt.objects.filter(assignment=exam)
                .select_related('student')}

    rows = []
    per_item_correct = [0] * len(items)
    per_item_graded = [0] * len(items)

    for student in exam.students.all().order_by('last_name', 'username'):
        attempt = attempts.get(student.pk)
        if attempt is None:
            rows.append({'student': student, 'attempt': None, 'cells': [],
                         'started': False, 'scored': None})
            continue
        exam_engine.finalize_if_expired(attempt)
        summary = exam_engine.attempt_summary(attempt)
        for index, cell in enumerate(summary['rows']):
            if cell['state'] in ('correct', 'wrong'):
                per_item_graded[index] += 1
                if cell['state'] == 'correct':
                    per_item_correct[index] += 1
        rows.append({
            'student': student, 'attempt': attempt, 'started': True,
            'cells': summary['rows'], 'scored': summary['scored'],
            'max_score': summary['graded_max'], 'pending': summary['pending'],
        })

    # Процент верных ПО ЗАДАЧЕ — ради этой строки таблица и существует.
    footer = []
    for index, item in enumerate(items):
        graded = per_item_graded[index]
        footer.append({
            'item': item,
            'percent': round(per_item_correct[index] * 100.0 / graded)
            if graded else None,
            'graded': graded,
        })

    return render(request, 'teacher/groups/exam_results.html', {
        'group': group,
        'exam': exam,
        'items': items,
        'rows': rows,
        'footer': footer,
        'not_started': [r['student'] for r in rows if not r['started']],
    })
