"""
Фабрики тестовых данных для автотестов платформы (ночная сессия 2026-06-12).

Все тесты создают данные ТОЛЬКО через эти функции в тестовой базе
(Django сам создаёт и удаляет её при manage.py test) — боевая база не трогается.
"""

from django.contrib.auth import get_user_model

from problems.models import (
    Assignment, Problem, Source, SourceReference, Submission, Topic,
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
    assignment = Assignment.objects.create(name=name, author=teacher, **kwargs)
    assignment.students.set(students)
    assignment.problems.set(problems)
    return assignment


def make_submission(student, assignment, problem, **kwargs):
    return Submission.objects.create(student=student, assignment=assignment,
                                     problem=problem, **kwargs)
