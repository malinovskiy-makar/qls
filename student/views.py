"""
Кабинет ученика: дашборд, страница домашки, отправка, просмотр проверки, прогресс.
"""
from functools import wraps


# ---------------------------------------------------------------------------
# Автопроверка тестовых задач (В2)
# ---------------------------------------------------------------------------

def auto_check_submission(submission):
    """Автоматически проверяет тестовые задачи и создаёт TeacherFeedback."""
    from problems.models import TeacherFeedback

    problem = submission.problem

    if not problem.problem_type or not problem.problem_type.startswith('тест'):
        return
    if not problem.answer:
        return

    def normalize(s):
        if not s:
            return ''
        return s.lower().strip().rstrip('.').rstrip(')').strip()

    correct = normalize(problem.answer)
    given = normalize(submission.submitted_answer or '')

    if not given:
        return

    if problem.problem_type == 'тест: все верные':
        correct_labels = set(
            normalize(p.label)
            for p in problem.parts.all()
            if normalize(p.answer) == 'верно'
        )
        given_labels = set(
            normalize(x) for x in given.replace(' ', '').split(',')
        )
        is_correct = (correct_labels == given_labels)
    else:
        is_correct = (correct == given)

    score = 1.0 if is_correct else 0.0
    comment = 'Верно ✓' if is_correct else f'Неверно. Правильный ответ: {problem.answer}'

    feedback, created = TeacherFeedback.objects.get_or_create(
        submission=submission,
        defaults={
            'score': score,
            'comment': comment,
            'reviewed_by': None,
        }
    )
    if not created:
        feedback.score = score
        feedback.comment = comment
        feedback.save()

    submission.status = 'reviewed'
    submission.save()


# ---------------------------------------------------------------------------
# Автопроверка своей задачи репетитора
# ---------------------------------------------------------------------------

def auto_check_custom(submission, item):
    """Проверяет ответ на свою задачу репетитора и ставит балл.

    Тест проверяется всегда, открытая задача — только если репетитор задал
    эталонный ответ. Иначе решение остаётся «ждёт проверки»: выдумывать за
    репетитора, что считать верным, мы не имеем права.
    """
    from problems.answer_check import check_custom_problem
    from problems.models import TeacherFeedback

    problem = item.custom_problem
    auto, is_correct = check_custom_problem(problem, submission.submitted_answer)
    if not auto:
        return

    max_points = float(item.points) if item.points is not None else 1.0
    score = max_points if is_correct else 0.0
    comment = 'Верно ✓' if is_correct else 'Неверно.'

    feedback, created = TeacherFeedback.objects.get_or_create(
        submission=submission,
        defaults={'score': score, 'comment': comment, 'reviewed_by': None})
    if not created:
        feedback.score = score
        feedback.comment = comment
        feedback.save()

    submission.status = 'reviewed'
    submission.save()


from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone


# ---------------------------------------------------------------------------
# Машинная проверка сданной задачи — ОДНА точка входа
# ---------------------------------------------------------------------------

def grade_submission(submission, item, request=None, values=None):
    """Проверяет сданную задачу тем способом, который ей подходит.

    ⚠️ ОДНА ТОЧКА на домашку и контрольную. Раньше выбор ветки («тест —
    так, своя задача — эдак») был написан в двух местах: в приёме домашки
    и в `exam_engine.grade_attempt`. Разойтись им — вопрос времени.

    Открытая задача идёт через проверку ПО ПУНКТАМ (`part_grading`): у
    задачи с «а)» и «б)» ответ на каждый пункт свой и проверяется отдельно.
    Тест остаётся на своей проверке «всё или ничего» по множеству
    выбранных вариантов.
    """
    from problems import part_grading

    if part_grading.applies(item):
        if values is None:
            values = (part_grading.read_part_answers(request, item)
                      if request is not None else {})
        part_grading.apply_to_submission(submission, item, values)
        submission.save()
        return

    if item.is_custom:
        auto_check_custom(submission, item)
    elif submission.problem_id:
        auto_check_submission(submission)


# ---------------------------------------------------------------------------
# Подсчёт статистики по домашке — раздельно для тестов и открытых задач
# ---------------------------------------------------------------------------

def calc_assignment_stats(assignment, student):
    """
    Считает статистику по домашке отдельно для тестов и открытых задач.
    Возвращает словарь с двумя независимыми метриками.

    Ходит по ПОЗИЦИЯМ (`assignment.items`), а не по старому M2M: иначе свои
    задачи репетитора не попадали бы в «сдано N из M» и прогресс-полоска
    ученика врала бы ровно на их число.
    """
    from problems.models import Submission

    items = list(assignment.items.select_related('catalog_problem',
                                                 'custom_problem'))
    total = len(items)

    open_scores = []
    test_correct = 0
    test_answered = 0
    open_count = 0
    test_count = 0
    total_reviewed = 0

    for item in items:
        is_test = item.is_test

        sub = Submission.objects.filter(
            student=student, assignment=assignment,
        ).filter(
            models.Q(problem_item=item)
            | models.Q(problem_item__isnull=True,
                       problem_id=item.catalog_problem_id,
                       problem__isnull=False)
        ).first()

        if is_test:
            test_count += 1
            if sub and sub.status == 'reviewed':
                total_reviewed += 1
                test_answered += 1
                feedback = getattr(sub, 'feedback', None)
                if feedback is not None and feedback.score is not None and feedback.score >= 1.0:
                    test_correct += 1
        else:
            open_count += 1
            if sub and sub.status == 'reviewed':
                total_reviewed += 1
                feedback = getattr(sub, 'feedback', None)
                if feedback is not None and feedback.score is not None:
                    open_scores.append(float(feedback.score))

    return {
        'open_count': open_count,
        'open_reviewed': len(open_scores),
        'open_avg': round(sum(open_scores) / len(open_scores), 2) if open_scores else None,
        'test_count': test_count,
        'test_correct': test_correct,
        'test_total_answered': test_answered,
        'test_pct': round(test_correct / test_answered * 100) if test_answered > 0 else None,
        'all_reviewed': (total_reviewed == total and total > 0),
        'total': total,
        'total_reviewed': total_reviewed,
    }


# ---------------------------------------------------------------------------
# Декоратор: только ученик (или суперпользователь для отладки)
# ---------------------------------------------------------------------------

def student_required(view_func):
    @login_required(login_url='/login/')
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not (request.user.role == 'student' or request.user.is_superuser):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Задача 3 — Дашборд ученика
# ---------------------------------------------------------------------------

@student_required
def dashboard(request):
    """Список работ ученика.

    Контрольные и домашки разведены (Фаза 0.4): у контрольной другой срок
    (окно или лимит), другая цена ошибки и другой вход — «начать» вместо
    «дописать когда угодно». Смешивать их в одном списке значило бы прятать
    работу, которую нельзя пропустить, среди работ, которые можно дослать.
    """
    from problems.models import Assignment, Submission

    assignments = (Assignment.objects
                   .filter(students=request.user)
                   .prefetch_related('items')
                   .order_by('deadline'))

    now = timezone.now()
    active = []
    submitted_list = []
    completed = []
    exams_upcoming = []
    exams_open = []
    exams_done = []

    for a in assignments:
        stats = calc_assignment_stats(a, request.user)
        # Один источник срока на весь сайт — `deadline_at` (Фаза 0.3).
        deadline = a.deadline_at

        deadline_soon = False
        deadline_passed = False
        if deadline:
            delta = deadline - now
            deadline_passed = delta.total_seconds() < 0
            deadline_soon = not deadline_passed and delta.days <= 2

        item = {
            'assignment': a,
            'stats': stats,
            'deadline': deadline,
            'deadline_soon': deadline_soon,
            'deadline_passed': deadline_passed,
            'schedule': exam_schedule_label(a),
        }

        if a.is_exam:
            attempt = a.exam_attempts.filter(student=request.user).first()
            item['attempt'] = attempt
            is_open, reason = a.open_state_for(request.user, now)
            item['closed_reason'] = reason
            if attempt is not None and attempt.submitted_at is not None:
                exams_done.append(item)
            elif is_open:
                exams_open.append(item)
            else:
                # Ещё нельзя начать (окно не открылось) или уже нельзя.
                exams_upcoming.append(item)
            continue

        if stats['all_reviewed']:
            # У завершённой работы в списке показываем ИТОГОВЫЙ БАЛЛ, а не
            # «N задач проверено»: балл — то, ради чего список открывают.
            from problems.work_review import work_summary

            totals = work_summary(a, request.user)
            item['score'] = totals['scored']
            item['max_score'] = totals['max_score']
            completed.append(item)
        elif stats['total_reviewed'] > 0 or Submission.objects.filter(
            assignment=a, student=request.user, status='submitted'
        ).exists():
            submitted_list.append(item)
        else:
            active.append(item)

    return render(request, 'student/dashboard.html', {
        'active': active,
        'submitted': submitted_list,
        'completed': completed,
        'exams_open': exams_open,
        'exams_upcoming': exams_upcoming,
        'exams_done': exams_done,
        'has_exams': bool(exams_open or exams_upcoming or exams_done),
        'now': now,
    })


def exam_schedule_label(assignment):
    """Время контрольной человеческими словами.

    Ровно то, чего не хватало на карточке: у контрольной срок задан не
    одним моментом, а окном или лимитом, и «до 20.03» без слова «90 минут»
    вводит в заблуждение.
    """
    from problems import timefmt

    if not assignment.is_exam:
        return ''
    mode = assignment.exam_mode
    if mode == assignment.ExamMode.WINDOW:
        # ⚠️ Через `timefmt`, а не f-строкой: в базе время в UTC, и
        # `f'{dt:%H:%M}'` печатает UTC, тогда как шаблонный фильтр `date`
        # переводит в пояс проекта сам. Отсюда и брались две строки на
        # одной странице с разницей в три часа.
        start, end = timefmt.local(assignment.starts_at), \
            timefmt.local(assignment.ends_at)
        if start and end:
            if start.date() == end.date():
                return ('окно %s %s–%s'
                        % (start.strftime('%d.%m'), start.strftime('%H:%M'),
                           end.strftime('%H:%M')))
            return 'окно %s — %s' % (start.strftime(timefmt.SHORT),
                                     end.strftime(timefmt.SHORT))
        if end:
            return 'до %s' % end.strftime(timefmt.SHORT)
        return 'окно не задано'
    if mode == assignment.ExamMode.LIMIT:
        parts = []
        if assignment.deadline_at:
            parts.append('до %s' % timefmt.fmt(assignment.deadline_at,
                                               timefmt.SHORT))
        if assignment.duration_minutes:
            parts.append(f'на решение {assignment.duration_minutes} мин')
        return ', '.join(parts) or 'срок не задан'
    return ''


# ---------------------------------------------------------------------------
# Задача 4 — Страница домашки
# ---------------------------------------------------------------------------

@student_required
def assignment_detail(request, pk):
    """Страница домашки — ОДИН список задач, ОДИН набор полей ответа.

    Список строит `problems.assignment_rows.build_rows` — тот же модуль, что
    и у репетитора. Двух сборок больше нет: они и разъехались.
    """
    from problems.assignment_rows import build_rows
    from problems.models import Assignment

    assignment = get_object_or_404(Assignment, pk=pk, students=request.user)

    # Контрольная живёт на своей странице: у неё таймер, автосохранение и
    # запрет дописывать после сдачи (Часть C).
    if assignment.is_exam:
        return redirect('student:exam_intro', pk=assignment.pk)

    rows = build_rows(assignment, request.user)

    statuses = [row['sub'].status for row in rows]
    all_reviewed = bool(statuses) and all(s == 'reviewed' for s in statuses)
    all_submitted_or_reviewed = bool(statuses) and all(
        s in ('submitted', 'reviewed') for s in statuses)
    done_count = sum(1 for s in statuses if s in ('submitted', 'reviewed'))

    is_open, closed_reason = assignment.open_state_for(request.user)

    return render(request, 'student/assignment_detail.html', {
        'assignment': assignment,
        'rows': rows,
        'total': len(rows),
        'done_count': done_count,
        'all_reviewed': all_reviewed,
        'all_submitted_or_reviewed': all_submitted_or_reviewed,
        'deadline': assignment.deadline_at,
        'is_open': is_open,
        'closed_reason': closed_reason,
    })


# ---------------------------------------------------------------------------
# Задача 5 — Отправка домашки
# ---------------------------------------------------------------------------

@student_required
def submit_assignment(request, pk):
    if request.method != 'POST':
        return redirect('student:assignment_detail', pk=pk)

    from problems.models import Assignment, Submission

    assignment = get_object_or_404(Assignment, pk=pk, students=request.user)

    saved = accept_answers(request, assignment, request.user)

    if saved:
        messages.success(request, 'Домашка отправлена! Преподаватель скоро проверит.')
    else:
        messages.warning(request, 'Нет новых ответов для отправки.')

    return redirect('student:dashboard')


def accept_answers(request, assignment, student, source_item=None):
    """Принимает ответы по ВСЕМ позициям работы одинаково.

    Одна точка приёма на домашку и контрольную. Раньше их было две (каталог
    и свои задачи), и поля у них назывались по-разному — отсюда и брались
    «разные формы» на экране.

    Возвращает число сохранённых позиций.
    """
    from problems.assignment_rows import get_or_create_submission, read_answer

    items = list(assignment.items.select_related('catalog_problem',
                                                 'custom_problem')
                 .prefetch_related('catalog_problem__parts',
                                   'custom_problem__options')
                 .order_by('order', 'id'))
    if source_item is not None:
        items = [i for i in items if i.pk == source_item.pk]

    saved = 0
    for item in items:
        sub = get_or_create_submission(student, assignment, item)
        if sub.status in ('submitted', 'reviewed'):
            continue

        answer, text, file = read_answer(request, item)
        if not (answer or text or file):
            continue

        sub.submitted_answer = answer
        sub.solution_text = text
        if file:
            sub.solution_file = file
        sub.status = 'submitted'
        sub.submitted_at = timezone.now()
        sub.save()

        grade_submission(sub, item, request=request)
        saved += 1
        _log_submission_event(request, assignment, sub, item.problem)

    return saved


# ---------------------------------------------------------------------------
# Учебные события при сдаче домашки (запись неблокирующая)
# ---------------------------------------------------------------------------

def _log_submission_event(request, assignment, submission, problem):
    """Пишет событие сдачи. Тест проверен автоматически — знаем сразу, верно
    или нет; открытая задача ждёт репетитора, поэтому только «попытался»."""
    from problems.event_log import log_problem_event

    source = 'exam' if getattr(assignment, 'is_exam', False) else 'homework'
    event_type = 'attempted'
    feedback = getattr(submission, 'feedback', None)
    if submission.status == 'reviewed' and feedback is not None:
        score = feedback.score
        if score is not None:
            event_type = 'solved' if float(score) >= 1.0 else 'failed'

    log_problem_event(source, event_type, request.user, problem,
                      request=request, assignment=assignment,
                      payload={'submission_id': submission.pk})


# ---------------------------------------------------------------------------
# Задача 6 — Просмотр проверенной работы
# ---------------------------------------------------------------------------

@student_required
def submission_detail(request, pk):
    """⚠️ УСТАРЕЛА. Разбор ОДНОЙ задачи поглощён разбором всей работы.

    Двух похожих экранов результата быть не должно: этот показывал одну
    задачу и не показывал ни итогового балла, ни остальных задач. Адрес
    оставлен редиректом ради закладок.
    """
    from problems.models import Submission

    submission = get_object_or_404(Submission, pk=pk, student=request.user)
    return redirect('student:work_review', pk=submission.assignment_id)


@student_required
def work_review(request, pk):
    """Разбор сданной работы — ОДИН экран на домашку и контрольную.

    Главное на экране — БАЛЛ. Никакой геймификации: это разбор работы, а
    не награда.
    """
    from problems import work_review as review
    from problems.models import Assignment

    assignment = get_object_or_404(Assignment, pk=pk, students=request.user)
    if not review.is_submitted(assignment, request.user):
        # Разбирать нечего, а верные ответы стали бы подсказкой.
        target = ('student:exam_intro' if assignment.is_exam
                  else 'student:assignment_detail')
        return redirect(target, pk=assignment.pk)

    return render(request, 'student/work_review.html',
                  work_review_context(assignment, request.user))


def work_review_context(assignment, student, viewer=None, for_tutor=False,
                        back_url=None, back_label=None):
    """Контекст экрана разбора. Общий для ученика и репетитора: обе стороны
    обязаны видеть ОДНО И ТО ЖЕ — иначе спор об оценке превращается в спор
    о том, у кого что на экране."""
    from django.urls import reverse

    from problems import work_review as review

    submitted_at = None
    if assignment.is_exam:
        attempt = assignment.exam_attempts.filter(student=student).first()
        submitted_at = attempt.submitted_at if attempt else None
    else:
        from problems.models import Submission

        last = Submission.objects.filter(
            assignment=assignment, student=student,
            submitted_at__isnull=False).order_by('-submitted_at').first()
        submitted_at = last.submitted_at if last else None

    summary = review.work_summary(assignment, student, viewer=viewer or student)
    # ⚠️ «Не показывать результат сразу» относится к АВТОПРОВЕРКЕ. Как
    # только преподаватель проверил хоть одну задачу руками, баллы
    # показываем: он их для ученика и ставил. Репетитор видит всегда.
    show_scores = (for_tutor or not assignment.is_exam
                   or assignment.show_results_immediately
                   or summary['reviewed_by_teacher'] > 0)

    return {
        'assignment': assignment,
        'student': student,
        'for_tutor': for_tutor,
        'show_scores': show_scores,
        'summary': summary,
        'spent_minutes': review.spent_minutes(assignment, student),
        'submitted_at': submitted_at,
        'back_url': back_url or reverse('student:dashboard'),
        'back_label': back_label or 'Все работы',
    }


# ---------------------------------------------------------------------------
# Задача 7 — Страница прогресса
# ---------------------------------------------------------------------------

@student_required
def progress(request):
    """⚠️ УСТАРЕЛА. Страница «Прогресс» ПОГЛОЩЕНА экраном `/profile/stats/`.

    Двух похожих разделов быть не должно: старая страница показывала владение
    темами, навыки и замечания преподавателя — всё это есть на новом экране,
    плюс история, теплокарта, достижения и переключатель периода. Адрес
    оставлен редиректом ради закладок и старых ссылок.
    """
    return redirect('student_stats')


