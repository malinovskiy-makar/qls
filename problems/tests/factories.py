"""
Фабрики тестовых данных для автотестов платформы (ночная сессия 2026-06-12).

Все тесты создают данные ТОЛЬКО через эти функции в тестовой базе
(Django сам создаёт и удаляет её при manage.py test) — боевая база не трогается.
"""

from django.contrib.auth import get_user_model

from problems.models import (
    Assignment, AssignmentItem, Problem, Source, SourceReference, Submission,
    Topic,
)

User = get_user_model()


def make_user(username, role='student', password='pass12345', **kwargs):
    user = User.objects.create_user(username=username, password=password,
                                    **kwargs)
    user.role = role
    user.save()
    return user


def make_topic(name, **kwargs):
    kwargs.setdefault('slug', name.lower().replace(' ', '-')[:50])
    return Topic.objects.create(name=name, **kwargs)


def make_problem(statement='Условие тестовой задачи: $MC = 2Q$.',
                 status=Problem.Status.PUBLISHED, topic=None, flagged=False,
                 **kwargs):
    problem = Problem.objects.create(
        statement=statement, status=status,
        needs_quality_review=flagged, **kwargs)
    if topic is not None:
        problem.topics.add(topic)
    return problem


def make_source(name='Тестовый источник', **kwargs):
    return Source.objects.create(name=name, **kwargs)


def link_source(problem, source, **kwargs):
    return SourceReference.objects.create(problem=problem, source=source,
                                          **kwargs)


def make_assignment(teacher, students=(), problems=(), name='Тестовая домашка',
                    **kwargs):
    """Домашка с задачами.

    Заполняет И старый M2M, И позиции (`AssignmentItem`): источник правды —
    позиции, а M2M оставлен для обратной совместимости. Если заполнять только
    M2M, тесты будут создавать домашку, которой на экране нет ни одной задачи.
    """
    assignment = Assignment.objects.create(name=name, author=teacher, **kwargs)
    assignment.students.set(students)
    assignment.problems.set(problems)
    for order, problem in enumerate(problems):
        AssignmentItem.objects.create(assignment=assignment,
                                      catalog_problem=problem, order=order)
    return assignment


def make_item(assignment, catalog_problem=None, custom_problem=None, **kwargs):
    """Одна позиция задачи в домашке."""
    kwargs.setdefault('order', assignment.items.count())
    return AssignmentItem.objects.create(
        assignment=assignment, catalog_problem=catalog_problem,
        custom_problem=custom_problem, **kwargs)


def approve_answers(item):
    """Утвердить каталожные ответы позиции — как это делает репетитор.

    С Фазы 0.6 машина проверяет каталожную задачу ТОЛЬКО после утверждения
    (`AssignmentItem.answer_override`): в банке «ответом» слишком часто
    записана фраза целиком или число из середины решения. Тестам, которые
    проверяют саму автопроверку, нужен утверждённый эталон — иначе они
    честно упираются в «задача ушла человеку».
    """
    from problems.assignment_rows import answer_parts, catalog_answer_for

    answers = {}
    for part in answer_parts(item):
        value = catalog_answer_for(item, part)
        if value:
            answers['' if part is None else str(part.pk)] = value
    item.answer_override = answers or None
    item.save(update_fields=['answer_override'])
    return item


def make_submission(student, assignment, problem, **kwargs):
    return Submission.objects.create(student=student, assignment=assignment,
                                     problem=problem, **kwargs)
