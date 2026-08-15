"""
Разбор сданной работы — ОДНА сборка на ученика и на репетитора.

⚠️ ЗАЧЕМ ОДНА. Экранов результата было два: у контрольной свой
(`exam_result`), у домашки — карточки на той же странице, где вводят
ответы. Оба показывали разное, и ни один не показывал главного — сколько
ученик получил и почему. Теперь экран один
(`/student/work/<pk>/`), и он же открывается репетитору по конкретному
ученику: если ученик спорит с оценкой, спорить надо об одном и том же
экране, а не о двух похожих.

ГЛАВНОЕ НА ЭКРАНЕ — БАЛЛ. Не геймификация, не серии, не опыт: это разбор
работы, а не награда.
"""
from decimal import Decimal


# ⚠️ СЛОВО ВЕРДИКТА — ОДНА ТОЧКА (ревью 15.08, фаза 6). Чип в шапке задачи и
# плашка под ответом обязаны говорить ОДНО И ТО ЖЕ: до правки чип писал
# «частично», а плашка рядом оставалась зелёной со словами «Верно ✓».
STATE_WORDS = {
    'correct': 'верно',
    'partial': 'частично',
    'wrong': 'неверно',
    'blank': 'без ответа',
    'pending': 'на проверке',
    'empty': 'без ответа',
}


def state_word(state):
    """Вердикт словом. Незнакомое состояние молча не выдумываем."""
    return STATE_WORDS.get(state, '')


def state_of(score, points, blank=False):
    """Состояние задачи по баллу. ТА ЖЕ формула, что в `work_summary`.

    Нужна отдельно, потому что после сохранения оценки состояние строки
    пересчитывает эндпоинт, а второй формулы быть не должно.
    """
    if score is None:
        return 'pending'
    if points > 0 and score >= points:
        return 'correct'
    if score > 0:
        return 'partial'
    return 'blank' if blank else 'wrong'


def score_presets(max_score):
    """Три кнопки балла: ноль, РОВНО половина, максимум задачи.

    ⚠️ ЕДИНСТВЕННАЯ ТОЧКА. Тот же список рисует экран проверки
    (`teacher/views.py::_score_presets` делегирует сюда): расхождение
    «половины» на двух экранах — это две разные оценки за одну работу.

    ⚠️ У ЗНАЧЕНИЯ И ПОДПИСИ РАЗНЫЕ ФОРМЫ ЗАПИСИ. Подпись русская, через
    запятую («1,5»); значение — с точкой, потому что его кладут в
    `<input type="number">` и разбирают на сервере через `float()`. Запятая
    в значении означала бы пустое поле в браузере и ноль на сервере — то
    есть кнопка «половина» тихо ставила бы ноль.
    """
    top = Decimal(str(max_score or 0))
    half = top / 2

    def show(value):
        """Один знак после запятой, без хвостового нуля: 5, 3,5, 1,5."""
        text = ('%.1f' % value).rstrip('0').rstrip('.')
        return text or '0'

    values = []
    for value in (Decimal('0'), half, top):
        if any(abs(value - other) < Decimal('0.001') for other in values):
            continue
        values.append(value)
    return [{'value': show(value).replace(',', '.'),
             'label': show(value).replace('.', ',')} for value in values]


def work_summary(assignment, student, viewer=None):
    """Всё, что нужно экрану разбора: строки задач, итог, состояние проверки.

    `viewer` — кто смотрит (от него зависит видимость решалки и
    комментариев). У ученика это он сам.
    """
    from . import part_grading
    from .assignment_rows import build_rows
    from .models import WorkFeedback

    viewer = viewer or student
    rows = build_rows(assignment, student, user=viewer)

    scored = Decimal('0')
    maximum = Decimal('0')
    graded_max = Decimal('0')
    pending = 0
    wrong = 0
    by_teacher = 0

    for number, row in enumerate(rows, start=1):
        item = row['item']
        feedback = row['feedback']
        points = _item_max(item, row)
        maximum += points
        row['max_points'] = points

        score = None
        if feedback is not None and feedback.score is not None:
            score = Decimal(str(feedback.score))
        row['score'] = score
        row['by_teacher'] = bool(feedback is not None
                                 and feedback.reviewed_by_id)
        if row['by_teacher']:
            by_teacher += 1

        if row['sub'].status not in ('submitted', 'reviewed'):
            row['state'] = 'empty'
        else:
            # ⚠️ НОЛЬ ЗА ПУСТОТУ — ЭТО НЕ «НЕВЕРНО». Балл одинаковый (ноль
            # за «не брался» и ноль за ошибку не различаются — решение
            # владельца), но писать «неверно» тому, кто ничего не отвечал,
            # неправда: ошибиться он не успел.
            row['state'] = state_of(score, points, blank=_is_blank(row))
            if row['state'] == 'pending':
                pending += 1

        if score is not None:
            scored += score
            graded_max += points
        if row['state'] in ('wrong', 'partial'):
            wrong += 1
        # Задачи с ошибкой должны бросаться в глаза: с них начинается разбор.
        row['needs_attention'] = row['state'] in ('wrong', 'partial')
        # Пресеты балла — ТЕ ЖЕ, что на экране проверки (`_score_presets`),
        # чтобы «половина» на двух экранах не разошлась.
        row['score_presets'] = score_presets(points)
        row['verdict'] = state_word(row['state'])
        # ⚠️ В ПОЛЕ ПРАВКИ — ТОЛЬКО СЛОВА ЧЕЛОВЕКА. Вердикт машины («Верно ✓»)
        # не комментарий, который правят: подставленный в поле, он уезжал
        # обратно в базу вместе с новой оценкой, и рядом с «ЧАСТИЧНО»
        # оставалось зелёное «Верно ✓».
        raw = (feedback.comment if feedback is not None else '') or ''
        row['comment'] = '' if part_grading.is_machine_comment(raw) else raw

    work_comment = WorkFeedback.objects.filter(assignment=assignment,
                                               student=student).first()

    return {
        'rows': rows,
        'scored': _clean(scored),
        'max_score': _clean(maximum),
        'graded_max': _clean(graded_max),
        'pending': pending,
        'wrong': wrong,
        'is_final': pending == 0,
        'reviewed_by_teacher': by_teacher,
        'work_comment': work_comment,
    }


def _is_blank(row):
    """Ноль поставлен машиной за пустоту. Признак общий с экраном проверки."""
    from . import part_grading

    return part_grading.is_auto_zero(row['sub'], row.get('answer_parts'))


def _item_max(item, row):
    """Максимум баллов за задачу.

    Если баллы заданы по пунктам — сумма по ним; иначе балл позиции;
    иначе единица (так считает вся остальная система).
    """
    from .assignment_rows import item_max_score

    part_rows = row.get('answer_parts') or []
    if part_rows and any(part['max_score'] is not None for part in part_rows):
        return sum((Decimal(str(part['max_score'] or 0))
                    for part in part_rows), Decimal('0'))
    return item_max_score(item)


def _clean(value):
    """Дробь без хвостовых нулей: «8», а не «8,00». Одна запись на платформу.

    ⚠️ Раньше возвращался Decimal, и хвостовой нуль срезался ТОЛЬКО у целых:
    «0.50» уходило в шаблон как есть и печаталось «0,50». Правила записи —
    в `problems/scorefmt.py`.
    """
    from . import scorefmt

    return scorefmt.ball(value)


def spent_minutes(assignment, student):
    """Сколько заняла работа. Для домашки понятия «затрачено» нет."""
    if not assignment.is_exam:
        return None
    attempt = assignment.exam_attempts.filter(student=student).first()
    if attempt is None or not (attempt.started_at and attempt.submitted_at):
        return None
    return int((attempt.submitted_at - attempt.started_at).total_seconds() // 60)


def is_submitted(assignment, student):
    """Сдана ли работа. Разбор до сдачи не показываем — там нечего
    разбирать, а верные ответы стали бы подсказкой."""
    from .models import Submission

    if assignment.is_exam:
        attempt = assignment.exam_attempts.filter(student=student).first()
        return attempt is not None and attempt.submitted_at is not None
    return Submission.objects.filter(
        assignment=assignment, student=student,
        status__in=('submitted', 'reviewed')).exists()
