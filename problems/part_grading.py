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

    ⚠️ У ЗАДАЧ КАТАЛОГА АВТОПРОВЕРКА РАБОТАЕТ ТОЛЬКО ПОСЛЕ УТВЕРЖДЕНИЯ.
    В банке поле «ответ» сплошь и рядом не ответ, а фраза целиком: «E ≈
    −1,22 (по модулю больше 1) — спрос эластичен», — или число из середины
    решения. Прежний признак «это похоже на число» такие случаи не
    отличал и ставил ноль за правильный ответ. Теперь эталон подтверждает
    (или вписывает свой) живой человек на странице задания, и словесный
    эталон после утверждения тоже разрешён — за него отвечает тот, кто его
    утвердил.

    У СВОЕЙ задачи репетитора и у теста утверждение не требуется: у первой
    эталон писал он сам, у второго верный вариант задан разметкой.
    """
    maximum = part_max_score(item, part, parts_count)

    # ⚠️ У КАТАЛОЖНОЙ ЗАДАЧИ ЭТАЛОН БЕРЁТСЯ ТОЛЬКО ИЗ УТВЕРЖДЁННОГО, и
    # утверждение идёт ПО ПУНКТАМ. Раньше хватало «в поле ответа лежит
    # число», и этого мало: числом оказывается то промежуточный результат
    # из решения, то год из условия. Отката к каталожному ответу здесь нет
    # намеренно — иначе утвердив «а» репетитор молча соглашался бы и на
    # непроверенное «б». Не утверждено — задача уходит человеку целиком.
    correct = (part_correct_answer(item, part) if item.is_custom
               else item.approved_answer(part))
    if not correct:
        return None, None, maximum
    if not (given or '').strip():
        # Не ответил — это не «на проверке», это ноль баллов.
        return False, Decimal('0'), maximum
    tolerance = 0
    if item.is_custom and item.custom_problem is not None:
        tolerance = item.custom_problem.answer_tolerance
    ok = check_open_answer(correct, given, tolerance)
    return ok, (maximum if ok else Decimal('0')), maximum


def wrote_anything(submission):
    """Написал ли ученик хоть что-нибудь по этой задаче.

    Смотрим на РАЗВЁРНУТОЕ РЕШЕНИЕ и на прикреплённый файл — то есть на то,
    что репетитору можно прочитать. Поле короткого ответа сюда не входит:
    оно разбирается отдельно, по каждому пункту.

    Файл считается написанным текстом намеренно: скан тетради — это работа,
    и ставить за него автоматический ноль было бы прямой несправедливостью.
    """
    if (submission.solution_text or '').strip():
        return True
    return bool(getattr(submission, 'solution_file', None))


def save_part_answers(submission, item, values):
    """Пишет ответы по пунктам и проверяет то, что проверяется машиной.

    Возвращает (набранный балл, максимум, сколько пунктов ждёт человека).
    Идемпотентна: повторный вызов обновляет те же строки.

    ⚠️ ПУСТОЙ ПУНКТ ПОЛУЧАЕТ НОЛЬ АВТОМАТОМ И НЕ ИДЁТ В ОЧЕРЕДЬ. Если по
    пункту не написано НИЧЕГО — ни ответа, ни решения, ни файла, — читать
    репетитору нечего, и держать такую пустоту в очереди ручной проверки
    значит тратить его время на пустое место.

    Ровно одно исключение, и оно важное: ответ пуст, но решение НАПИСАНО.
    Тогда пункт идёт человеку, как раньше. Ученик рассуждал — значит есть
    что читать и есть за что ставить балл. Именно этот случай лежит в
    демо-данных (Пётр, «Эластичность спроса по цене»).
    """
    from .models import PartAnswer

    parts = answer_parts(item)
    scored = Decimal('0')
    maximum = Decimal('0')
    pending = 0
    # Решение одно на всю задачу, поэтому признак считается один раз: если
    # ученик написал разбор, ни один пункт не обнуляется автоматически.
    has_text = wrote_anything(submission)

    for part in parts:
        key = part.pk if part is not None else None
        given = (values.get(key) or '').strip()
        ok, score, part_max = grade_part(item, part, given, len(parts))
        auto_zero = False
        if score is None and not given and not has_text:
            ok, score, auto_zero = False, Decimal('0'), True
        maximum += part_max
        if score is not None:
            scored += score
        else:
            pending += 1
        PartAnswer.objects.update_or_create(
            submission=submission, part=part,
            defaults={'answer': given, 'is_correct': ok, 'score': score,
                      'max_score': part_max, 'auto_zero': auto_zero})
    return scored, maximum, pending


def part_rows(item, submission, stored=None):
    """Строки «пункт → ответ ученика → эталон → вердикт» для показа.

    Одна сборка на экран ученика и на экран репетитора: разъехавшиеся
    вердикты на двух экранах — это спор ученика с преподавателем на пустом
    месте.

    `stored` — уже загруженные ответы {id пункта: PartAnswer}. Передаётся
    сборкой строк, чтобы не делать по запросу на задачу.
    """
    from .models import PartAnswer

    parts = answer_parts(item)
    if stored is None:
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
            # Ноль за пустоту, а не за ошибку — экран проверки показывает это
            # отдельной строкой и даёт кнопку «изменить».
            'auto_zero': bool(answer.auto_zero) if answer else False,
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
    # Работа пустая целиком — говорим об этом прямо, а не «неверно,
    # правильный ответ …». Ученик ничего не отвечал, и «неверно» тут ложь.
    if rows and all(row['auto_zero'] for row in rows):
        return 'Ноль поставлен автоматически: ответа не было.'
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
