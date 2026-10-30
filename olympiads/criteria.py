"""Критерии жюри в задаче банка: раздел «## Критерии оценивания» в конце решения.

Импорт пакета (`olympiads/tasks_import.py`, решение владельца 14.10) кладёт
критерии хвостом `Problem.solution` после заголовка `CRITERIA_HEADING`.
Здесь — только чтение: разделить решение и критерии. Разбор критериев по
баллам — `olympiads/ai_check.py` (Э7).

⚠️ ТЕКСТ НЕ ПРАВИТСЯ: функция возвращает куски как есть.
"""
from .tasks_import import CRITERIA_HEADING


def split_solution(solution):
    """(разбор без критериев, текст критериев) — оба могут быть пустыми."""
    text = solution or ''
    index = text.find(CRITERIA_HEADING)
    if index < 0:
        return text.strip(), ''
    return (text[:index].strip(),
            text[index + len(CRITERIA_HEADING):].strip())


def has_criteria(problem):
    return bool(split_solution(problem.solution)[1])
