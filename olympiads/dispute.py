"""«Оспорить оценку»: чат «Стола» в режиме `dispute` (ночь 30.10, Э8).

Модель получает задание (условие с пунктами — их собирает `catalog.chat`),
критерии жюри с баллами и пояснениями проверки, расшифровку решения ученика и
строку спорного критерия цитатой. ⚠️ ЧАТ БАЛЛ НЕ МЕНЯЕТ: ничего, кроме
реплики в журнале `ChatTurn`, он не пишет. Кнопка «Отправить на проверку
человеку» ставит задаче `is_pending` и пометку `TrainingCheck.human_review`.

⚠️ НАРУЖУ — БЕЗ ПРОФИЛЯ: имя, почта, логин, класс не уходят (тест читает запрос).
"""
from .ai_check import _num

MODE = 'dispute'


class CheckAsAttempt:
    """Проверка тура в виде, который понимает `catalog.chat.build_prompt`:
    «последняя попытка ученика» и «результат проверки»."""

    status = 'checked'
    first_error_step = None
    steps = ()

    def __init__(self, check, student_text):
        self.text = '\n\n'.join(t for t in (student_text, check.transcription) if t) \
            or '(решение — фото без расшифровки)'
        score = float(check.score or 0)
        self.verdict = 'ok' if score >= float(check.max_score or 0) else 'partial'
        self.score = int(score)
        self.max_score = int(float(check.max_score or 0))
        self.summary = check.summary


def criteria_block(check):
    """Системный блок: критерии жюри, баллы и пояснения проверки."""
    lines = ['ОЦЕНКА ПО КРИТЕРИЯМ ЖЮРИ (балл менять нельзя): %s из %s.' % (
        _num(check.score or 0), _num(check.max_score or 0))]
    if check.approximate:
        lines.append('Оценка ориентировочная: критерии не разобраны по баллам.')
    for row in check.criteria or []:
        lines.append('- %s%s (%s из %s): %s. Пояснение проверки: %s' % (
            (row.get('part') + ') ') if row.get('part') else '', row['code'],
            _num(row['score']), _num(row['max']), row['text'], row.get('why') or '—'))
    if check.summary:
        lines.append('Общий комментарий проверки: ' + check.summary)
    return '\n'.join(lines)


def quoted(check, code):
    """Текст строки спорного критерия — цитатой реплики («подсвечена»)."""
    for row in check.criteria or []:
        if row['code'] == code:
            return '%s · %s · %s из %s' % (row['code'], row['text'][:200],
                                           _num(row['score']), _num(row['max']))
    return ''


def history(check, user):
    """Реплики разговора об этой оценке — для показа без JS и для модели."""
    from problems.models_platform import ChatTurn

    return list(ChatTurn.objects.filter(user=user, problem_id=check.problem_id,
                                        mode=MODE, created_at__gte=check.created_at)
                .exclude(reply='').order_by('created_at')[:40])


def ask_human(check):
    """«Отправить на проверку человеку»: задача ждёт человека, балл не трогаем."""
    from .models import TrainingItemResult

    check.human_review = True
    check.save(update_fields=['human_review'])
    TrainingItemResult.objects.filter(attempt=check.attempt,
                                      problem_id=check.problem_id).update(is_pending=True)
    from . import training_engine as engine
    engine.recount(check.attempt)
