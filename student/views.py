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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone


# ---------------------------------------------------------------------------
# Подсчёт статистики по домашке — раздельно для тестов и открытых задач
# ---------------------------------------------------------------------------

def calc_assignment_stats(assignment, student):
    """
    Считает статистику по домашке отдельно для тестов и открытых задач.
    Возвращает словарь с двумя независимыми метриками.
    """
    from problems.models import Submission

    problems = list(assignment.problems.all())
    total = len(problems)

    open_scores = []
    test_correct = 0
    test_answered = 0
    open_count = 0
    test_count = 0
    total_reviewed = 0

    for problem in problems:
        is_test = bool(problem.problem_type and problem.problem_type.startswith('тест'))

        sub = Submission.objects.filter(
            student=student,
            assignment=assignment,
            problem=problem,
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
    from problems.models import Assignment, Submission

    assignments = Assignment.objects.filter(
        students=request.user
    ).prefetch_related('problems').order_by('deadline')

    now = timezone.now()
    active = []
    submitted_list = []
    completed = []

    for a in assignments:
        stats = calc_assignment_stats(a, request.user)

        deadline_soon = False
        deadline_passed = False
        if a.deadline:
            delta = a.deadline - now
            deadline_passed = delta.total_seconds() < 0
            deadline_soon = not deadline_passed and delta.days <= 2

        item = {
            'assignment': a,
            'stats': stats,
            'deadline': a.deadline,
            'deadline_soon': deadline_soon,
            'deadline_passed': deadline_passed,
        }

        if stats['all_reviewed']:
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
        'now': now,
    })


# ---------------------------------------------------------------------------
# Задача 4 — Страница домашки
# ---------------------------------------------------------------------------

@student_required
def assignment_detail(request, pk):
    from problems.models import Assignment, Submission

    assignment = get_object_or_404(Assignment, pk=pk, students=request.user)
    problems = assignment.problems.prefetch_related('parts', 'hints').order_by('id')

    submissions = {}
    for problem in problems:
        sub, _ = Submission.objects.get_or_create(
            student=request.user,
            assignment=assignment,
            problem=problem,
            defaults={'status': 'not_started'},
        )
        submissions[problem.pk] = sub

    # Собираем feedback для проверенных работ
    feedbacks = {}
    for pk_p, sub in submissions.items():
        if sub.status == 'reviewed':
            feedbacks[pk_p] = getattr(sub, 'feedback', None)

    all_reviewed = all(
        sub.status == 'reviewed' for sub in submissions.values()
    ) if submissions else False

    all_submitted_or_reviewed = all(
        sub.status in ('submitted', 'reviewed') for sub in submissions.values()
    ) if submissions else False

    return render(request, 'student/assignment_detail.html', {
        'assignment': assignment,
        'problems': problems,
        'submissions': submissions,
        'feedbacks': feedbacks,
        'all_reviewed': all_reviewed,
        'all_submitted_or_reviewed': all_submitted_or_reviewed,
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
    problems = assignment.problems.all()

    saved = 0
    for problem in problems:
        sub = Submission.objects.filter(
            student=request.user,
            assignment=assignment,
            problem=problem,
        ).first()

        if not sub or sub.status in ('submitted', 'reviewed'):
            continue

        answer = request.POST.get(f'answer_{problem.pk}', '').strip()
        text = request.POST.get(f'text_{problem.pk}', '').strip()
        file = request.FILES.get(f'file_{problem.pk}')

        if answer or text or file:
            sub.submitted_answer = answer
            sub.solution_text = text
            if file:
                sub.solution_file = file
            sub.status = 'submitted'
            sub.submitted_at = timezone.now()
            sub.save()
            auto_check_submission(sub)
            saved += 1

    if saved:
        messages.success(request, 'Домашка отправлена! Преподаватель скоро проверит.')
    else:
        messages.warning(request, 'Нет новых ответов для отправки.')

    return redirect('student:dashboard')


# ---------------------------------------------------------------------------
# Задача 6 — Просмотр проверенной работы
# ---------------------------------------------------------------------------

@student_required
def submission_detail(request, pk):
    from problems.models import Submission

    submission = get_object_or_404(Submission, pk=pk, student=request.user)
    feedback = getattr(submission, 'feedback', None)

    return render(request, 'student/submission_detail.html', {
        'submission': submission,
        'feedback': feedback,
        'problem': submission.problem,
    })


# ---------------------------------------------------------------------------
# Задача 7 — Страница прогресса
# ---------------------------------------------------------------------------

@student_required
def progress(request):
    from django.db.models import Count
    from problems.models import (
        StudentSkillProgress, StudentTopicProgress, Submission, TeacherFeedback,
    )

    topic_progress = (
        StudentTopicProgress.objects
        .filter(student=request.user)
        .select_related('topic')
        .order_by('-level')
    )

    skill_progress = (
        StudentSkillProgress.objects
        .filter(student=request.user)
        .select_related('skill')
        .order_by('-level')
    )

    mistake_counts = (
        TeacherFeedback.objects
        .filter(submission__student=request.user)
        .values('mistakes__name')
        .annotate(count=Count('mistakes'))
        .filter(mistakes__isnull=False)
        .order_by('-count')[:10]
    )

    # Открытые задачи (не тесты)
    open_reviewed = Submission.objects.filter(
        student=request.user,
        status='reviewed',
    ).exclude(problem__problem_type__startswith='тест').count()

    total_submitted = Submission.objects.filter(
        student=request.user, status='submitted'
    ).count()

    # Статистика по тестам
    test_subs = list(
        Submission.objects.filter(
            student=request.user,
            status='reviewed',
            problem__problem_type__startswith='тест',
        ).select_related('problem', 'feedback').prefetch_related('problem__topics')
    )

    test_by_topic = {}
    for sub in test_subs:
        feedback = getattr(sub, 'feedback', None)
        is_correct = feedback is not None and feedback.score is not None and feedback.score >= 1.0
        for topic in sub.problem.topics.all():
            if topic.name not in test_by_topic:
                test_by_topic[topic.name] = {'correct': 0, 'total': 0}
            test_by_topic[topic.name]['total'] += 1
            if is_correct:
                test_by_topic[topic.name]['correct'] += 1

    test_topic_stats = []
    for name, data in test_by_topic.items():
        pct = round(data['correct'] / data['total'] * 100) if data['total'] > 0 else 0
        test_topic_stats.append({
            'topic': name,
            'correct': data['correct'],
            'total': data['total'],
            'pct': pct,
        })
    test_topic_stats.sort(key=lambda x: -x['pct'])

    total_test_subs = len(test_subs)
    total_test_correct = sum(
        1 for sub in test_subs
        if getattr(sub, 'feedback', None) is not None
        and sub.feedback.score is not None
        and sub.feedback.score >= 1.0
    )
    test_overall_pct = (
        round(total_test_correct / total_test_subs * 100) if total_test_subs > 0 else None
    )

    return render(request, 'student/progress.html', {
        'topic_progress': topic_progress,
        'skill_progress': skill_progress,
        'mistake_counts': mistake_counts,
        'open_reviewed': open_reviewed,
        'total_submitted': total_submitted,
        'test_topic_stats': test_topic_stats,
        'total_test_subs': total_test_subs,
        'total_test_correct': total_test_correct,
        'test_overall_pct': test_overall_pct,
    })
