"""
Панель учителя: список домашек, решения учеников, форма проверки.
"""
import json
import re
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST


# ---------------------------------------------------------------------------
# Декоратор: только учитель (или суперпользователь)
# ---------------------------------------------------------------------------

def teacher_required(view_func):
    @login_required(login_url='/login/')
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not (request.user.role == 'teacher' or request.user.is_staff):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# В4 — обновление прогресса после проверки
# ---------------------------------------------------------------------------

def update_student_progress(submission, feedback):
    """Обновляет StudentTopicProgress и StudentSkillProgress после проверки."""
    from problems.models import StudentSkillProgress, StudentTopicProgress

    problem = submission.problem
    student = submission.student

    max_score = 5.0
    try:
        rubric = problem.rubric
        criteria_max = sum(c.max_score for c in rubric.criteria.all())
        if criteria_max > 0:
            max_score = criteria_max
    except Exception:
        pass

    score_val = float(feedback.score) if feedback.score is not None else 0.0
    score_percent = min(100.0, (score_val / max_score) * 100)

    WEIGHT_NEW = 0.3

    for topic in problem.topics.all():
        progress, created = StudentTopicProgress.objects.get_or_create(
            student=student,
            topic=topic,
            defaults={'level': int(round(score_percent))}
        )
        if not created:
            new_level = progress.level * (1 - WEIGHT_NEW) + score_percent * WEIGHT_NEW
            progress.level = min(100, int(round(new_level)))
            progress.save()

    for skill in problem.skills.all():
        progress, created = StudentSkillProgress.objects.get_or_create(
            student=student,
            skill=skill,
            defaults={'level': int(round(score_percent))}
        )
        if not created:
            new_level = progress.level * (1 - WEIGHT_NEW) + score_percent * WEIGHT_NEW
            progress.level = min(100, int(round(new_level)))
            progress.save()


# ---------------------------------------------------------------------------
# В3 — Дашборд учителя
# устарело, удалить после сессии 5: маршрут `/teacher/` теперь ведёт на
# дашборд входящих (`views_groups.dashboard`). Вьюха оставлена как справка.
# ---------------------------------------------------------------------------

@teacher_required
def dashboard(request):
    from problems.models import Assignment, Submission

    assignments = Assignment.objects.filter(
        author=request.user
    ).prefetch_related('problems').order_by('-id')

    assignment_data = []
    for a in assignments:
        pending = Submission.objects.filter(assignment=a, status='submitted').count()
        total = Submission.objects.filter(assignment=a).count()
        assignment_data.append({
            'assignment': a,
            'pending': pending,
            'total': total,
        })

    return render(request, 'teacher/dashboard.html', {
        'assignment_data': assignment_data,
    })


# ---------------------------------------------------------------------------
# В3 — Список решений по домашке
# ---------------------------------------------------------------------------

@teacher_required
def assignment_detail(request, pk, group=None):
    """Таблица решений по домашке.

    Переехала под групповые URL (`/teacher/groups/<g>/assignments/<a>/
    submissions/`). Логика проверки НЕ менялась — только адрес и навигация,
    поэтому вьюха одна, а `group` определяет, куда ведут ссылки и хлебные
    крошки. Старый адрес остался редиректом.
    """
    from problems.models import Assignment, Submission

    assignment = get_object_or_404(Assignment, pk=pk, author=request.user)

    status_filter = request.GET.get('status', '')
    submissions = Submission.objects.filter(
        assignment=assignment
    ).select_related('student', 'problem').order_by('student__username', 'problem__id')

    if status_filter:
        submissions = submissions.filter(status=status_filter)

    return render(request, 'teacher/assignment_detail.html', {
        'assignment': assignment,
        'submissions': submissions,
        'status_filter': status_filter,
        'group': group or assignment.group,
    })


# ---------------------------------------------------------------------------
# В3 — Форма проверки решения
# ---------------------------------------------------------------------------

@teacher_required
def review_submission(request, pk, group=None):
    """Форма оценки решения. Переехала под групповые URL; логика оценки
    не менялась."""
    from problems.models import MistakeTag, Submission, TeacherFeedback

    submission = get_object_or_404(Submission, pk=pk)
    if submission.assignment.author != request.user and not request.user.is_staff:
        raise PermissionDenied

    problem = submission.problem
    existing_feedback = getattr(submission, 'feedback', None)
    mistake_tags = MistakeTag.objects.all().order_by('name')

    if request.method == 'POST':
        score_str = request.POST.get('score', '').strip()
        comment = request.POST.get('comment', '').strip()
        mistake_ids = request.POST.getlist('mistakes')

        try:
            score = float(score_str)
        except ValueError:
            score = 0.0

        if existing_feedback:
            existing_feedback.score = score
            existing_feedback.comment = comment
            existing_feedback.reviewed_by = request.user
            existing_feedback.save()
            existing_feedback.mistakes.set(mistake_ids)
            feedback = existing_feedback
        else:
            feedback = TeacherFeedback.objects.create(
                submission=submission,
                score=score,
                comment=comment,
                reviewed_by=request.user,
            )
            feedback.mistakes.set(mistake_ids)

        submission.status = 'reviewed'
        submission.save()

        update_student_progress(submission, feedback)

        messages.success(request, f'Решение проверено. Балл: {score}')
        group_obj = group or submission.assignment.group
        if group_obj is not None:
            return redirect('teacher:group_submissions',
                            group_id=group_obj.pk,
                            assignment_id=submission.assignment.pk)
        return redirect('teacher:assignment_detail', pk=submission.assignment.pk)

    return render(request, 'teacher/review.html', {
        'submission': submission,
        'problem': problem,
        'existing_feedback': existing_feedback,
        'mistake_tags': mistake_tags,
        'group': group or submission.assignment.group,
    })


# ---------------------------------------------------------------------------
# Этап Е — Группы учеников
# устарело, удалить после сессии 5: экраны групп переехали в
# `teacher/views_groups.py` (список, страница группы, создание).
# ---------------------------------------------------------------------------

@teacher_required
def groups_list(request):
    from problems.models import StudentGroup
    groups = StudentGroup.objects.filter(
        teacher=request.user
    ).prefetch_related('students').order_by('-created_at')
    return render(request, 'teacher/groups_list.html', {
        'groups': groups,
    })


@teacher_required
def group_create(request):
    from problems.models import StudentGroup, User as PlatformUser
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        student_ids = request.POST.getlist('students')
        if name:
            group = StudentGroup.objects.create(
                name=name,
                teacher=request.user,
            )
            if student_ids:
                students = PlatformUser.objects.filter(
                    pk__in=student_ids, role='student'
                )
                group.students.set(students)
            messages.success(request, f'Группа «{name}» создана.')
            return redirect('teacher:groups')

    all_students = (
        PlatformUser.objects.filter(role='student')
        .order_by('last_name', 'first_name', 'username')
    )
    return render(request, 'teacher/group_create.html', {
        'all_students': all_students,
    })


@teacher_required
def group_detail(request, pk):
    from problems.models import StudentGroup, Submission
    group = get_object_or_404(StudentGroup, pk=pk, teacher=request.user)

    students_data = []
    for student in group.students.all():
        reviewed = Submission.objects.filter(
            student=student,
            status='reviewed',
            assignment__author=request.user,
        )
        open_reviewed = reviewed.exclude(problem__problem_type__startswith='тест')
        test_reviewed = reviewed.filter(problem__problem_type__startswith='тест')

        open_scores = [
            float(s.feedback.score)
            for s in open_reviewed.select_related('feedback')
            if hasattr(s, 'feedback') and s.feedback
        ]
        test_scores = [
            float(s.feedback.score)
            for s in test_reviewed.select_related('feedback')
            if hasattr(s, 'feedback') and s.feedback
        ]

        students_data.append({
            'student': student,
            'open_count': len(open_scores),
            'open_avg': round(sum(open_scores) / len(open_scores), 1) if open_scores else None,
            'test_count': len(test_scores),
            'test_pct': round(sum(test_scores) / len(test_scores) * 100) if test_scores else None,
        })

    return render(request, 'teacher/group_detail.html', {
        'group': group,
        'students_data': students_data,
    })


# ---------------------------------------------------------------------------
# Этап Е — Прогресс ученика глазами учителя
# ---------------------------------------------------------------------------

@teacher_required
def student_progress(request, pk):
    from problems.models import (
        Assignment,
        StudentGroup,
        StudentSkillProgress,
        StudentTopicProgress,
        Submission,
        TeacherFeedback,
        User as PlatformUser,
    )
    from django.db.models import Count

    student = get_object_or_404(PlatformUser, pk=pk, role='student')

    in_group = StudentGroup.objects.filter(
        teacher=request.user,
        students=student,
    ).exists()
    if not in_group and not request.user.is_staff:
        raise PermissionDenied

    topic_progress = (
        StudentTopicProgress.objects.filter(student=student)
        .select_related('topic')
        .order_by('-level')
    )
    skill_progress = (
        StudentSkillProgress.objects.filter(student=student)
        .select_related('skill')
        .order_by('-level')
    )

    mistake_counts = (
        TeacherFeedback.objects.filter(
            submission__student=student,
            reviewed_by=request.user,
        )
        .values('mistakes__name')
        .annotate(count=Count('mistakes'))
        .filter(mistakes__name__isnull=False)
        .order_by('-count')[:5]
    )

    all_reviewed = Submission.objects.filter(
        student=student,
        status='reviewed',
        assignment__author=request.user,
    )
    open_reviewed = all_reviewed.exclude(problem__problem_type__startswith='тест')
    test_reviewed = all_reviewed.filter(problem__problem_type__startswith='тест')

    open_scores = [
        float(s.feedback.score)
        for s in open_reviewed.select_related('feedback')
        if hasattr(s, 'feedback') and s.feedback
    ]
    test_scores = [
        float(s.feedback.score)
        for s in test_reviewed.select_related('feedback')
        if hasattr(s, 'feedback') and s.feedback
    ]

    assignments = Assignment.objects.filter(
        author=request.user,
        students=student,
    ).order_by('-id')

    homework_history = []
    for a in assignments:
        subs = Submission.objects.filter(
            student=student,
            assignment=a,
            status='reviewed',
        ).select_related('feedback', 'problem')

        open_s = [s for s in subs if not (s.problem.problem_type or '').startswith('тест')]
        test_s = [s for s in subs if (s.problem.problem_type or '').startswith('тест')]

        o_scores = [
            float(s.feedback.score)
            for s in open_s
            if hasattr(s, 'feedback') and s.feedback
        ]
        t_scores = [
            float(s.feedback.score)
            for s in test_s
            if hasattr(s, 'feedback') and s.feedback
        ]

        homework_history.append({
            'assignment': a,
            'open_avg': round(sum(o_scores) / len(o_scores), 1) if o_scores else None,
            'test_pct': round(sum(t_scores) / len(t_scores) * 100) if t_scores else None,
        })

    return render(request, 'teacher/student_progress.html', {
        'student': student,
        'topic_progress': topic_progress,
        'skill_progress': skill_progress,
        'mistake_counts': mistake_counts,
        'open_count': len(open_scores),
        'open_avg': round(sum(open_scores) / len(open_scores), 1) if open_scores else None,
        'test_count': len(test_scores),
        'test_pct': round(sum(test_scores) / len(test_scores) * 100) if test_scores else None,
        'homework_history': homework_history,
    })


# ---------------------------------------------------------------------------
# Сессия 2 Этапа Е — Конструктор домашек
# ---------------------------------------------------------------------------

_RX_DISPLAY = re.compile(r'\$\$.*?\$\$|\\\[.*?\\\]', re.DOTALL)
_RX_INLINE  = re.compile(r'\$[^$\n]+?\$|\\\(.*?\\\)', re.DOTALL)
_RX_CMD     = re.compile(r'\\[a-zA-Z]+\*?(?:\{[^}]*\})?')
_RX_SPACE   = re.compile(r'\s+')


def _strip_latex(text):
    text = _RX_DISPLAY.sub('', text)
    text = _RX_INLINE.sub('', text)
    text = _RX_CMD.sub('', text)
    return _RX_SPACE.sub(' ', text).strip()


@teacher_required
def assignment_create(request):
    """Конструктор домашки. Отбор задач — общий модуль `teacher/picker.py`."""
    from problems.models import Assignment, StudentGroup

    from .picker import create_items, parse_cart, picker_context

    if request.method == 'POST':
        title = request.POST.get('name', '').strip()
        deadline_str = request.POST.get('deadline', '').strip()
        group_ids = request.POST.getlist('groups')
        keys, catalog_ids, custom_ids = parse_cart(
            request.POST.get('problem_ids'))

        if not title:
            messages.error(request, 'Укажите название домашки.')
            return redirect('teacher:assignment_create')
        if not (catalog_ids or custom_ids):
            messages.error(request, 'Добавьте хотя бы одну задачу.')
            return redirect('teacher:assignment_create')
        if not group_ids:
            messages.error(request, 'Выберите хотя бы одну группу.')
            return redirect('teacher:assignment_create')

        import datetime

        from django.utils import timezone

        deadline = None
        if deadline_str:
            try:
                deadline = datetime.datetime.fromisoformat(deadline_str)
                if timezone.is_naive(deadline):
                    deadline = timezone.make_aware(deadline)
            except ValueError:
                deadline = None

        groups = list(StudentGroup.objects.filter(pk__in=group_ids,
                                                  teacher=request.user))

        assignment = Assignment.objects.create(
            name=title,
            deadline=deadline,
            author=request.user,
            # Домашка привязывается к группе: без этого вкладка «Группы»
            # её не увидит, а вся работа с группой живёт именно там.
            # Если выбрано несколько групп — берём первую, остальные всё
            # равно получают домашку через список учеников.
            group=groups[0] if groups else None,
        )
        create_items(assignment, request.user, keys, catalog_ids, custom_ids)

        for group in groups:
            assignment.students.add(*group.students.all())

        messages.success(request, f'Домашка «{title}» создана.')
        return redirect('teacher:dashboard')

    from problems.models import SavedProblem

    saved = [item.catalog_problem for item in
             SavedProblem.objects.filter(owner=request.user, is_deleted=False,
                                         catalog_problem__isnull=False)
             .select_related('catalog_problem')]

    context = picker_context(request)
    context.update({
        'groups': StudentGroup.objects.filter(
            teacher=request.user).prefetch_related('students'),
        'show_saved': True,
        'saved_problems': saved,
        'picker_reset_url': reverse('teacher:assignment_create'),
    })
    return render(request, 'teacher/assignment_create.html', context)


@teacher_required
def api_problem_detail(request, pk):
    from problems.models import Problem

    try:
        problem = Problem.objects.prefetch_related('topics', 'parts', 'source_references__source').get(pk=pk)
    except Problem.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    d = problem.difficulty or 0
    parts = [
        {
            'label':  part.label,
            'text':   part.statement,
            'points': float(part.points) if part.points is not None else None,
        }
        for part in problem.parts.all()
    ]
    topics  = list(problem.topics.values_list('name', flat=True))
    sources = [ref.source.name for ref in problem.source_references.select_related('source').all()]

    return JsonResponse({
        'id':             problem.pk,
        'title':          problem.title or f'Задача #{problem.pk}',
        'statement':      problem.statement,
        'parts':          parts,
        'difficulty':     d,
        'difficulty_str': '★' * d + '☆' * (5 - d),
        'topics':         topics,
        'problem_type':   problem.problem_type,
        'has_solution':   bool(problem.solution),
        'sources':        sources,
    })


@teacher_required
@require_POST
def api_assignment_add_problem(request, pk):
    from problems.models import Assignment, Problem

    assignment = get_object_or_404(Assignment, pk=pk, author=request.user)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    problem_id = data.get('problem_id')
    if not problem_id:
        return JsonResponse({'error': 'problem_id required'}, status=400)

    problem = get_object_or_404(Problem, pk=problem_id)
    assignment.problems.add(problem)

    return JsonResponse({'ok': True, 'problem_id': problem.pk, 'assignment_id': assignment.pk})


# ---------------------------------------------------------------------------
# устарело, удалить после сессии 5
# Старые адреса проверки решений. Ведут на новые (внутри группы). Оставлены
# редиректом, а не удалены, чтобы не сломать закладки и ссылки в письмах.
# ---------------------------------------------------------------------------

@teacher_required
def legacy_assignment_detail(request, pk):
    """устарело, удалить после сессии 5 → teacher:group_submissions"""
    from problems.models import Assignment

    assignment = get_object_or_404(Assignment, pk=pk)
    if assignment.group_id:
        return redirect('teacher:group_submissions',
                        group_id=assignment.group_id, assignment_id=pk)
    # Задание вне группы (выдано до появления групп) — показываем как раньше.
    return assignment_detail(request, pk)


@teacher_required
def legacy_review_submission(request, pk):
    """устарело, удалить после сессии 5 → teacher:group_review_submission"""
    from problems.models import Submission

    submission = get_object_or_404(Submission, pk=pk)
    group_id = submission.assignment.group_id
    if group_id:
        return redirect('teacher:group_review_submission',
                        group_id=group_id, submission_id=pk)
    return review_submission(request, pk)
