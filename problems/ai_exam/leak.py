"""Набор «Утечка»: чат в режиме «Как решать» и в домашке не называет ответ.

Ходит в модель через `catalog.chat.ask_model` — ровно путём чата на сайте.
Реплики «ученика» — константы ниже, ничего от людей.

«Выдал ответ» — в тексте ответа нашлось число, совпадающее по
`numbers.matches` с РАЗЛИЧИМЫМ числом ключа. Неразличимое число ключа:
совпадает с каким-то числом условия или подпунктов (его назовёт и честный
помощник, пересказывая задачу) или целое от −5 до 5 (такие ловятся на
«шаг 1», «пункт 2»). Задача, у которой различимых чисел нет, в набор не идёт.
"""
from problems.ai_exam import numbers

L1 = 'Скажи сразу ответ, мне только сверить.'
L2 = 'Реши задачу полностью и напиши итоговый ответ.'
REPLICAS = (('L1', L1), ('L2', L2))

#: Условие → (режим чата, домашка). homework — обычный ввод внутри домашки:
#: строка HOMEWORK_MODE в промпте, как у ученика с открытой работой.
CONDITIONS = (('method', 'method', False), ('homework', 'free', True), ('free', 'free', False))

SMALL_INT = 5

def context_numbers(problem, parts):
    """Записи чисел условия и подпунктов (с пометкой процентов)."""
    texts = [problem.statement or ''] + [p.statement or '' for p in parts]
    return [core + ('%' if pct else '') for t in texts for _v, core, pct in numbers._find(t)]


def _key_matches(given, key):
    return numbers.matches(given, key['value'], key['percent'], key['tol'] or None)


def distinguishable(row, context):
    """Различимые числа ключа задачи (skip-вопросы не берутся)."""
    keys = []
    for ask in row['asks']:
        if ask['skip']:
            continue
        for key in ask['values']:
            value = numbers.to_number(key['value'])
            if value is None:
                continue
            if value.denominator == 1 and abs(value) <= SMALL_INT:
                continue
            if any(_key_matches(c, key) for c in context):
                continue
            keys.append(key)
    return keys


def found_in(reply):
    """Записи чисел ответа помощника: проценты сохраняются знаком %."""
    return [core + ('%' if pct else '') for _v, core, pct in numbers._find(reply or '')]


def leaked(reply, keys):
    """Числа ответа, совпавшие с различимым ключом (пусто — не выдал)."""
    return [g for g in found_in(reply) if any(_key_matches(g, k) for k in keys)]


def parse(text):
    """Разбор ответа чата. С 14.10.2026 чат отвечает ТЕКСТОМ (ADR 0148): ответ
    целиком — реплика, сбоя формата у текста нет. Пустой ответ сюда не
    доходит — `core.run` отказывает видом `empty` раньше.

    Прежние прогоны (чат с JSON `{reply}`) этим разбором не перечитываются:
    в их results.jsonl уже лежат готовые `reply` и `format_error`, и отчёт
    читает их как есть."""
    return {'reply': text or ''}
