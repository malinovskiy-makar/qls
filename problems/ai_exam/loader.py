"""Задачи экзамена из банка: объекты для промпта и свежий хеш условия.

ТОЛЬКО ЧТЕНИЕ. Видимость — `catalog.filters.base_queryset('catalog')`, как
при отборе (`bank.py`): задача, которую убрали из каталога, из экзамена
выпадает с пометкой «нет в банке».

Подпункты для промпта — `problem.parts.all()` в порядке модели, ровно как
их берёт чат на сайте (`catalog/chat.py::answer`). Для хеша — порядок
отбора (`order`, `label`, `id`), иначе хеш не сойдётся с candidates.jsonl.
"""
from catalog.filters import base_queryset
from problems.ai_exam.sampling import statement_hash


def load_tasks(ids):
    """id → {'problem', 'parts', 'hash'} для видимых задач из `ids`.

    Вызывать в главном потоке: дальше в рабочих потоках к базе не ходят.
    """
    out = {}
    qs = base_queryset('catalog').filter(id__in=list(ids)).prefetch_related('parts')
    for problem in qs:
        parts = list(problem.parts.all())
        ordered = sorted(parts, key=lambda p: (p.order, p.label or '', p.id))
        record = {'statement': problem.statement, 'answer': problem.answer,
                  'parts': [{'label': p.label, 'statement': p.statement, 'answer': p.answer}
                            for p in ordered]}
        out[problem.id] = {'problem': problem, 'parts': parts, 'hash': statement_hash(record)}
    return out
