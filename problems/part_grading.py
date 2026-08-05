"""
Ответы по пунктам: приём, автопроверка, сборка балла.

⚠️ ЗАЧЕМ. Задача «а) найдите TC, б) найдите ATC» полностью автопроверяема —
в каждом пункте просят число. Но поле ответа было ОДНО на всю задачу:
машина не могла понять, где кончается ответ на «а» и начинается ответ на
«б», и задача уходила репетитору на ручную проверку. Ученик при этом не
понимал, какой из двух ответов он завалил: вердикт был один на задачу.

ГЛАВНОЕ ПРАВИЛО: ЗАДАЧА БЕЗ ПУНКТОВ — ЧАСТНЫЙ СЛУЧАЙ «ОДИН ПУНКТ».
`ProblemPart = None` означает «вся задача». Второй ветки логики нет: тот
же список, та же проверка, тот же показ. Проект уже дважды платил за
«если есть подпункты, то так, иначе эдак» расхождением экранов.

ЧАСТИЧНО ВЕРНАЯ ЗАДАЧА ПОКАЗЫВАЕТСЯ ПО ПУНКТАМ. «Всё или ничего»
оставлено ровно там, где оно осмысленно, — внутри ОДНОГО теста с
несколькими верными вариантами (`answer_check.check_option_answer`).
Между пунктами задачи такого правила нет: «а» и «б» — разные вопросы, и
верный ответ на «а» засчитывается независимо.
"""
from decimal import Decimal

from .answer_check import check_open_answer
from .assignment_rows import (
    answer_input_name,
    answer_parts,
    part_correct_answer,
    part_max_score,
)


def read_part_answers(request, item):
    """{pk пункта или None: ответ} из POST. Всегда все пункты."""
    parts = answer_parts(item)
    values = {}
    for part in parts:
        raw = request.POST.get(answer_input_name(item, part))
        values[part.pk if part is not None else None] = (raw or '').strip()
    return values


def join_answers(item, values):
    """Ответы по пунктам одной строкой — для старых экранов и списков.

    `Submission.submitted_answer` остаётся строкой: на неё смотрят таблица
    решений, экспорт и статистика. Хранить правду в двух местах нельзя,
    поэтому строка СОБИРАЕТСЯ из пунктов, а не заполняется отдельно.
    """
    parts = answer_parts(item)
    if len(parts) == 1 and parts[0] is None:
        return values.get(None, '') or ''
    chunks = []
    for part in parts:
        text = (values.get(part.pk) or '').strip()
        if text:
            chunks.append('%s) %s' % ((part.label or '').rstrip(').'), text))
    return '; '.join(chunks)


def grade_part(item, part, given, parts_count):
    """Проверка ОДНОГО пункта. Возвращает (is_correct, score, max_score).

    `is_correct = None` — машина не проверяла: решает человек. Молчаливый
    False здесь означал бы «ученик ошибся», а он не ошибся — просто
    проверить нечем.

    ⚠️ У ЗАДАЧ КАТАЛОГА АВТОПРОВЕРКА ТОЛЬКО ДЛЯ ЧИСЛОВЫХ ЭТАЛОНОВ. В банке
    поле «ответ» сплошь и рядом не ответ, а фраза целиком: «E ≈ −1,22 (по
    модулю больше 1) — спрос эластичен». Сравнить её со строкой ученика —
    значит поставить ноль за правильный ответ, потому что он написал
    «-1,22». Такие задачи честно уходят репетитору.

    У СВОЕЙ задачи репетитора словесный эталон разрешён: его писал живой
    человек ИМЕННО как эталон и знает, с чем сравнивают.
    """
    from .answer_check import parse_number

    maximum = part_max_score(item, part, parts_count)
    correct = part_correct_answer(item, part)
    if not correct:
        return None, None, maximum
    if not item.is_custom and parse_number(correct) is None:
        return None, None, maximum
    if not (given or '').strip():
        # Не ответил — это не «на проверке», это ноль баллов.
        return False, Decimal('0'), maximum
    tolerance = 0
    if item.is_custom and item.custom_problem is not None:
        tolerance = item.custom_problem.answer_tolerance
    ok = check_open_answer(correct, given, tolerance)
    return ok, (maximum if ok else Decimal('0')), maximum


def save_part_answers(submission, item, values):
    """Пишет ответы по пунктам и проверяет то, что проверяется машиной.

    Возвращает (набранный балл, максимум, сколько пунктов ждёт человека).
    Идемпотентна: повторный вызов обновляет те же строки.
    """
    from .models import PartAnswer

    parts = answer_parts(item)
    scored = Decimal('0')
    maximum = Decimal('0')
    pending = 0

    for part in parts:
        key = part.pk if part is not None else None
        given = (values.get(key) or '').strip()
        ok, score, part_max = grade_part(item, part, given, len(parts))
        maximum += part_max
        if score is not None:
            scored += score
        else:
            pending += 1
        PartAnswer.objects.update_or_create(
            submission=submission, part=part,
            defaults={'answer': given, 'is_correct': ok, 'score': score,
                      'max_score': part_max})
    return scored, maximum, pending


def part_rows(item, submission):
    """Строки «пункт → ответ ученика → эталон → вердикт» для показа.

    Одна сборка на экран ученика и на экран репетитора: разъехавшиеся
    вердикты на двух экранах — это спор ученика с преподавателем на пустом
    месте.
    """
    from .models import PartAnswer

    parts = answer_parts(item)
    stored = {}
    if submission is not None and submission.pk:
        stored = {answer.part_id: answer
                  for answer in PartAnswer.objects.filter(
                      submission=submission).select_related('part')}

    rows = []
    for number, part in enumerate(parts, start=1):
        key = part.pk if part is not None else None
        answer = stored.get(key)
        rows.append({
            'part': part,
            'label': (part.label if part is not None else ''),
            'statement': (part.statement if part is not None else ''),
            'number': number,
            'name': answer_input_name(item, part),
            'given': answer.answer if answer else '',
            'correct': part_correct_answer(item, part),
            'is_correct': answer.is_correct if answer else None,
            'score': answer.score if answer else None,
            'max_score': (answer.max_score if answer
                          else part_max_score(item, part, len(parts))),
            'auto': bool(part_correct_answer(item, part)),
        })
    return rows


def has_parts(item):
    """Есть ли у задачи настоящие пункты (а не единственный «вся задача»)."""
    parts = answer_parts(item)
    return len(parts) > 1 or parts[0] is not None


def applies(item):
    """Идёт ли эта задача через проверку по пунктам.

    ТЕСТЫ — НЕТ, и признак тут `item.is_test` (тип задачи), а НЕ «есть ли
    переключатели на экране». Тест без размеченных вариантов рисуется
    строкой ввода, но проверять его надо по-прежнему сравнением метки
    («б» против «Б»), а не как число — иначе верный ответ на тест уходит
    репетитору «на проверку». Наступил на это сразу же: три теста
    покраснели.
    """
    if item.problem is None:
        return False
    return not item.is_test


def apply_to_submission(submission, item, values):
    """Сохранить ответы по пунктам и выставить машинный балл за задачу.

    Балл задачи = СУММА баллов за пункты. Частично верная задача получает
    частичный балл: «а» и «б» — разные вопросы, и правильный ответ на «а»
    не перестаёт быть правильным из-за ошибки в «б».

    Если хоть один пункт машина проверить не смогла — задача остаётся
    «ждёт проверки»: показывать «3 из 5» там, где человек ещё не смотрел,
    значит обещать итог, которого нет.
    """
    from .models import TeacherFeedback

    scored, maximum, pending = save_part_answers(submission, item, values)
    submission.submitted_answer = join_answers(item, values)
    if pending:
        return scored, maximum, pending

    feedback = getattr(submission, 'feedback', None)
    if feedback is not None and feedback.reviewed_by_id:
        # Преподаватель уже проверил руками — машина его не перебивает.
        return scored, maximum, pending

    comment = _auto_comment(item, submission)
    if feedback is None:
        TeacherFeedback.objects.create(submission=submission, score=scored,
                                       comment=comment, reviewed_by=None)
    else:
        feedback.score = scored
        feedback.comment = comment
        feedback.save(update_fields=['score', 'comment'])
    submission.status = 'reviewed'
    return scored, maximum, pending


def _auto_comment(item, submission):
    """Что машина пишет ученику: по пунктам, а не одним вердиктом."""
    rows = part_rows(item, submission)
    if len(rows) == 1 and rows[0]['part'] is None:
        row = rows[0]
        if row['is_correct']:
            return 'Верно ✓'
        return 'Неверно. Правильный ответ: %s' % row['correct']

    chunks = []
    for row in rows:
        label = (row['label'] or '').rstrip(').')
        if row['is_correct']:
            chunks.append('%s) верно' % label)
        else:
            chunks.append('%s) неверно, правильный ответ: %s'
                          % (label, row['correct']))
    return '; '.join(chunks)
