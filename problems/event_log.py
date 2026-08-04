"""
Запись учебных событий — единственная точка входа.

⚠️ ГЛАВНОЕ ПРАВИЛО: логирование НЕ ИМЕЕТ ПРАВА сломать основной сценарий.
Ученик сдаёт домашку — он должен её сдать, даже если таблица событий
переполнена, поле переименовано, а база отвечает таймаутом. Поэтому каждая
запись обёрнута в try/except: ошибка уходит в лог приложения и на этом всё.

Обратная сторона честная: часть событий может потеряться незаметно.
Для статистики учёбы это приемлемо, для оценок — нет, поэтому оценки здесь
не хранятся и никогда не будут.
"""
import logging

logger = logging.getLogger(__name__)


def log_event(source, event_type, user=None, request=None, **fields):
    """Записывает событие. Никогда не бросает исключение.

    `request` нужен только ради ключа сессии для анонимных партий игры.
    Возвращает созданное событие или None (если не получилось).
    """
    try:
        from .models_platform import LearningEvent

        if user is not None and not getattr(user, 'is_authenticated', False):
            user = None

        session_key = fields.pop('session_key', '')
        if not session_key and request is not None:
            session = getattr(request, 'session', None)
            if session is not None:
                # Ключа может ещё не быть — у анонима сессия создаётся лениво.
                if session.session_key is None:
                    session.save()
                session_key = session.session_key or ''

        return LearningEvent.objects.create(
            source=source, event_type=event_type, user=user,
            session_key=session_key or '', **fields)
    except Exception:
        logger.exception('Не удалось записать учебное событие '
                         '(%s/%s) — основной сценарий не тронут',
                         source, event_type)
        return None


def problem_facts(problem):
    """Тема и сложность задачи для денормализации в событие.

    Тема берётся первая — событий «по всем темам сразу» не бывает, а
    размазывать одно решение по трём темам значило бы утроить статистику.
    """
    facts = {'topic': None, 'difficulty': None}
    if problem is None:
        return facts
    try:
        facts['difficulty'] = getattr(problem, 'difficulty', None)
        topics = getattr(problem, 'topics', None)
        if topics is not None:
            facts['topic'] = topics.first()
        else:
            facts['topic'] = getattr(problem, 'topic', None)
    except Exception:
        logger.exception('Не удалось снять тему/сложность задачи')
    return facts


def log_problem_event(source, event_type, user, problem, request=None,
                      **fields):
    """Событие по задаче — сам разбирается, каталожная она или своя."""
    from .models_platform import CustomProblem

    facts = problem_facts(problem)
    facts.update(fields)
    if isinstance(problem, CustomProblem):
        facts['custom_problem'] = problem
    elif problem is not None:
        facts['catalog_problem'] = problem
    return log_event(source, event_type, user=user, request=request, **facts)
