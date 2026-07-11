"""
Бэкенд Econ Rush.

Принципы:
- Страница и API публичные (без логина) — игра работает как инструмент
  привлечения.
- Вся правда о правильных ответах живёт ТОЛЬКО на сервере: эндпоинт вопроса
  никогда не отдаёт correct_index; клиент узнаёт его лишь после своего ответа.
- Состояние забега — в Django session (подписанные куки/бэкенд сессий):
  список выданных вопросов (без повторов) и счётчик позиции для прогрессии
  сложности. Время и очки считает клиент по константам config.py — сервер
  отдаёт только дельты; серверного лидерборда пока нет, поэтому
  анти-чит сводится к сокрытию правильных ответов.
"""
import json
import random

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from problems.models import Topic
from problems.management.commands.apply_topic_mapping import CANONICAL
from .models import GameQuestion
from . import config

SESSION_KEY = 'econ_rush'
# В игре пока только русские вопросы (английская часть пула лежит в базе
# на будущее — отдельный режим). Минимум вопросов на тему для чипа на старте.
GAME_LANG = 'ru'
MIN_TOPIC_POOL = 30


@ensure_csrf_cookie
def game_page(request):
    """Страница игры: три экрана в одном шаблоне, управляются JS."""
    # Чипы тем: только канонические темы, по которым в пуле достаточно вопросов.
    counts = {}
    for g in GameQuestion.objects.filter(lang=GAME_LANG).values_list('topics', flat=True):
        for name in g:
            counts[name] = counts.get(name, 0) + 1
    topics = [name for name in CANONICAL
              if counts.get(name, 0) >= MIN_TOPIC_POOL]
    return render(request, 'game/game.html', {
        'topics': topics,
        # JSON для JS-клиента: механика читается только из config.py
        'config_json': json.dumps({
            'start_seconds': config.START_SECONDS,
            'time_correct': config.TIME_CORRECT,
            'time_wrong': config.TIME_WRONG,
            'time_skip': config.TIME_SKIP,
            'base_points': config.BASE_POINTS,
            'combo_steps': config.COMBO_STEPS,
        }),
    })


def _question_payload(gq, number):
    """Вопрос для клиента — БЕЗ correct_index (анти-чит)."""
    return {
        'id': gq.id,
        'number': number,
        'question': gq.question,
        'options': gq.options,
        'topics': gq.topics,
        'problem_id': gq.problem_id,
    }


def _pick_next(state):
    """Выбирает следующий вопрос: без повторов в забеге, с прогрессией
    сложности (первые EASY_PHASE_COUNT — из difficulty 1–2, дальше выше).
    Если подходящего пула нет — деградация до любого невыданного вопроса;
    исчерпан весь пул — None (без зацикливания).

    Фильтр по теме — в Python: JSONField.__contains не работает на SQLite,
    а пул маленький (тысячи строк), перебор дешёвый."""
    seen = set(state['seen'])
    topic = state.get('topic')
    rows = GameQuestion.objects.filter(lang=GAME_LANG).values_list(
        'id', 'difficulty', 'topics')
    candidates = [(pk, diff) for pk, diff, topics in rows
                  if pk not in seen and (not topic or topic in topics)]
    if not candidates:
        return None  # пул исчерпан

    if len(seen) < config.EASY_PHASE_COUNT:
        preferred = [pk for pk, d in candidates
                     if d <= config.EASY_MAX_DIFFICULTY]
    else:
        preferred = [pk for pk, d in candidates
                     if d > config.EASY_MAX_DIFFICULTY]
    pool = preferred or [pk for pk, _ in candidates]  # деградация
    gq = GameQuestion.objects.get(id=random.choice(pool))
    state['seen'].append(gq.id)
    return gq


@require_GET
def api_session_start(request):
    """Начать забег: тема (или «все») → первый вопрос."""
    topic = request.GET.get('topic', '').strip()
    if topic and topic not in CANONICAL:
        return JsonResponse({'error': 'Неизвестная тема'}, status=400)

    state = {'topic': topic or None, 'seen': [], 'answered': {}}
    gq = _pick_next(state)
    if gq is None:
        return JsonResponse({'error': 'Пул вопросов пуст'}, status=503)
    request.session[SESSION_KEY] = state
    return JsonResponse({
        'ok': True,
        'question': _question_payload(gq, 1),
    })


@require_GET
def api_question(request):
    """Следующий вопрос текущего забега."""
    state = request.session.get(SESSION_KEY)
    if not state:
        return JsonResponse({'error': 'Забег не начат'}, status=400)
    gq = _pick_next(state)
    if gq is None:
        return JsonResponse({'exhausted': True})
    request.session[SESSION_KEY] = state
    return JsonResponse({'question': _question_payload(gq, len(state['seen']))})


@require_POST
def api_answer(request):
    """Проверка ответа. Тело: {question_id, choice} (choice = индекс или null
    для пропуска). Ответ: верно/нет, правильный индекс, дельта времени."""
    state = request.session.get(SESSION_KEY)
    if not state:
        return JsonResponse({'error': 'Забег не начат'}, status=400)
    try:
        body = json.loads(request.body.decode('utf-8'))
        qid = int(body['question_id'])
        choice = body.get('choice', None)
        if choice is not None:
            choice = int(choice)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Некорректный запрос'}, status=400)

    if qid not in state['seen']:
        return JsonResponse({'error': 'Этот вопрос не выдавался'}, status=404)
    if str(qid) in state['answered']:
        return JsonResponse({'error': 'Вопрос уже отвечен'}, status=409)

    try:
        gq = GameQuestion.objects.get(id=qid)
    except GameQuestion.DoesNotExist:
        return JsonResponse({'error': 'Вопрос не найден'}, status=404)

    if choice is None:
        result = 'skip'
        delta = config.TIME_SKIP
        correct = False
    elif not (0 <= choice < len(gq.options)):
        return JsonResponse({'error': 'Нет такого варианта'}, status=400)
    else:
        correct = (choice == gq.correct_index)
        result = 'correct' if correct else 'wrong'
        delta = config.TIME_CORRECT if correct else config.TIME_WRONG

    state['answered'][str(qid)] = result
    request.session[SESSION_KEY] = state
    return JsonResponse({
        'result': result,
        'correct': correct,
        'correct_index': gq.correct_index,
        'time_delta': delta,
    })
