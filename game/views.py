"""
Бэкенд Econ Rush.

Принципы:
- Страница и API публичные (без логина) — игра работает как инструмент
  привлечения.
- Вся правда о правильных ответах живёт ТОЛЬКО на сервере: эндпоинт вопроса
  никогда не отдаёт correct_index/correct_indices/correct_value; клиент
  узнаёт правильный ответ лишь после своего ответа.
- Состояние забега — в Django session (подписанные куки/бэкенд сессий):
  режим, список выданных вопросов (без повторов внутри забега). Отдельный
  ключ SEEN_KEY живёт МЕЖДУ забегами: «сначала невиданные» — вопрос не
  повторится в новых забегах, пока пул режима не исчерпан (тогда цикл
  по кругу). Время и очки считает клиент по константам config.py — сервер
  отдаёт только дельты; серверного лидерборда пока нет, поэтому
  анти-чит сводится к сокрытию правильных ответов.
"""
import json
import random
from fractions import Fraction

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from problems.management.commands.apply_topic_mapping import CANONICAL
from .models import GameQuestion
from . import config

SESSION_KEY = 'econ_rush'        # состояние текущего забега
SEEN_KEY = 'econ_rush_seen'      # {mode: [id, ...]} — виданные МЕЖДУ забегами
SEEN_LIMIT = 1500                # сколько последних id помнить на режим
# В игре пока только русские вопросы (английская часть пула лежит в базе
# на будущее — отдельный режим). Минимум вопросов на тему для чипа на старте.
GAME_LANG = 'ru'
MIN_TOPIC_POOL = 30


def parse_exact_number(s):
    """Разбор числового ответа игрока в точное значение (Fraction).

    Понимает целые, десятичные (запятая = точка), отрицательные и простые
    дроби a/b. Сравнение потом точное: 0,1 == 0.1 == 1/10, но 1/3 != 0.33.
    Непарсибельный ввод → None (трактуется как неверный ответ, не ошибка)."""
    if s is None:
        return None
    s = str(s).replace(' ', '').replace('−', '-').replace(',', '.')
    if not s:
        return None
    try:
        if '/' in s:
            num, den = s.split('/')  # ValueError, если '/' не ровно один
            return Fraction(num) / Fraction(den)
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        return None


def _mode_payload(mode_key):
    """Параметры режима для клиента (тайминги — только из config.py)."""
    m = config.MODES[mode_key]
    return {
        'key': mode_key,
        'title': m['title'],
        'question_type': m['question_type'],
        'duration': m['duration'],
        'time_correct': m['time_correct'],
        'time_wrong': m['time_wrong'],
        'time_skip': m['time_skip'],
    }


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

    # Сколько ru-вопросов доступно на каждый режим (для карточек на старте).
    type_counts = {}
    for qtype in GameQuestion.objects.filter(lang=GAME_LANG).values_list(
            'question_type', flat=True):
        type_counts[qtype] = type_counts.get(qtype, 0) + 1
    pool_counts = {key: type_counts.get(m['question_type'], 0)
                   for key, m in config.MODES.items()}

    return render(request, 'game/game.html', {
        'topics': topics,
        # JSON для JS-клиента: механика читается только из config.py
        'config_json': json.dumps({
            'modes': {key: _mode_payload(key) for key in config.MODES},
            'default_mode': config.DEFAULT_MODE,
            'pool_counts': pool_counts,
            'base_points': config.BASE_POINTS,
            'combo_steps': config.COMBO_STEPS,
            # Легаси-ключи для старого JS (значения = режим по умолчанию);
            # убрать вместе с переделкой фронтенда (Фазы 5–6).
            'start_seconds': config.MODES[config.DEFAULT_MODE]['duration'],
            'time_correct': config.MODES[config.DEFAULT_MODE]['time_correct'],
            'time_wrong': config.MODES[config.DEFAULT_MODE]['time_wrong'],
            'time_skip': config.MODES[config.DEFAULT_MODE]['time_skip'],
        }),
    })


def _question_payload(gq, number):
    """Вопрос для клиента — БЕЗ правильного ответа (анти-чит)."""
    return {
        'id': gq.id,
        'number': number,
        'type': gq.question_type,
        'question': gq.question,
        'options': gq.options,
        'topics': gq.topics,
        'problem_id': gq.problem_id,
    }


def _pick_next(request, state):
    """Выбирает следующий вопрос режима: случайный, но «сначала невиданные».

    Кандидаты = ru-вопросы нужного question_type (+ фильтр темы), минус
    показанные в ЭТОМ забеге (строго без повторов), минус виданные в прошлых
    забегах (SEEN_KEY, живёт между забегами). Если после вычета «виданных»
    ничего не осталось — список режима очищается (цикл по кругу) и выбор
    идёт из всех оставшихся. Пул забега исчерпан полностью → None.

    Фильтр по теме — в Python: JSONField.__contains не работает на SQLite,
    а пул маленький (тысячи строк), перебор дешёвый."""
    mode = state['mode']
    qtype = config.MODES[mode]['question_type']
    seen_run = set(state['seen'])
    topic = state.get('topic')

    rows = GameQuestion.objects.filter(
        lang=GAME_LANG, question_type=qtype).values_list('id', 'topics')
    candidates = [pk for pk, topics in rows
                  if pk not in seen_run and (not topic or topic in topics)]
    if not candidates:
        return None  # пул исчерпан в этом забеге

    seen_map = request.session.get(SEEN_KEY) or {}
    seen_before = set(seen_map.get(mode, []))
    fresh = [pk for pk in candidates if pk not in seen_before]
    if not fresh:
        seen_map[mode] = []  # весь пул видан — начинаем круг заново
        fresh = candidates

    gq = GameQuestion.objects.get(id=random.choice(fresh))
    state['seen'].append(gq.id)
    mode_seen = seen_map.get(mode, [])
    mode_seen.append(gq.id)
    seen_map[mode] = mode_seen[-SEEN_LIMIT:]
    request.session[SEEN_KEY] = seen_map
    return gq


@require_GET
def api_session_start(request):
    """Начать забег: режим + тема (или «все») → первый вопрос и тайминги."""
    mode = request.GET.get('mode', '').strip() or config.DEFAULT_MODE
    if mode not in config.MODES:
        return JsonResponse({'error': 'Неизвестный режим'}, status=400)
    topic = request.GET.get('topic', '').strip()
    if topic and topic not in CANONICAL:
        return JsonResponse({'error': 'Неизвестная тема'}, status=400)

    state = {'mode': mode, 'topic': topic or None, 'seen': [], 'answered': {}}
    gq = _pick_next(request, state)
    if gq is None:
        return JsonResponse({'error': 'Пул вопросов пуст'}, status=503)
    request.session[SESSION_KEY] = state
    return JsonResponse({
        'ok': True,
        'mode': _mode_payload(mode),
        'question': _question_payload(gq, 1),
    })


@require_GET
def api_question(request):
    """Следующий вопрос текущего забега."""
    state = request.session.get(SESSION_KEY)
    if not state:
        return JsonResponse({'error': 'Забег не начат'}, status=400)
    gq = _pick_next(request, state)
    if gq is None:
        return JsonResponse({'exhausted': True})
    request.session[SESSION_KEY] = state
    return JsonResponse({'question': _question_payload(gq, len(state['seen']))})


def _check_answer(gq, body):
    """Проверяет ответ по типу вопроса.

    Возвращает (is_skip, correct) или JsonResponse с ошибкой 400.
    boolean/single: {'choice': int|null}; multi: {'choices': [int, ...]};
    numeric: {'value': str}. null/отсутствие = пропуск."""
    if gq.question_type == 'multi':
        choices = body.get('choices', None)
        if choices in (None, []):
            return True, False
        if (not isinstance(choices, list)
                or any(not isinstance(c, int) or isinstance(c, bool) for c in choices)):
            return JsonResponse({'error': 'Некорректный запрос'}, status=400)
        if any(not (0 <= c < len(gq.options)) for c in choices):
            return JsonResponse({'error': 'Нет такого варианта'}, status=400)
        # Засчитываем ТОЛЬКО полное совпадение множеств.
        return False, set(choices) == set(gq.correct_indices)

    if gq.question_type == 'numeric':
        value = body.get('value', None)
        if value is None or not str(value).strip():
            return True, False
        given = parse_exact_number(value)
        expected = parse_exact_number(gq.correct_value)
        # Непарсибельный ввод = неверный ответ (не 400 — игрок мог опечататься).
        return False, (given is not None and expected is not None
                       and given == expected)

    # boolean / single
    choice = body.get('choice', None)
    if choice is None:
        return True, False
    if not isinstance(choice, int) or isinstance(choice, bool):
        return JsonResponse({'error': 'Некорректный запрос'}, status=400)
    if not (0 <= choice < len(gq.options)):
        return JsonResponse({'error': 'Нет такого варианта'}, status=400)
    return False, choice == gq.correct_index


@require_POST
def api_answer(request):
    """Проверка ответа. Тело: {question_id, choice|choices|value}
    (null/отсутствие = пропуск). Ответ: верно/нет, правильный ответ
    (по типу вопроса), дельта времени из конфига режима."""
    state = request.session.get(SESSION_KEY)
    if not state:
        return JsonResponse({'error': 'Забег не начат'}, status=400)
    try:
        body = json.loads(request.body.decode('utf-8'))
        qid = int(body['question_id'])
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

    checked = _check_answer(gq, body)
    if isinstance(checked, JsonResponse):
        return checked
    is_skip, correct = checked

    mode_cfg = config.MODES[state['mode']]
    if is_skip:
        result = 'skip'
        delta = mode_cfg['time_skip']
    else:
        result = 'correct' if correct else 'wrong'
        delta = mode_cfg['time_correct'] if correct else mode_cfg['time_wrong']

    state['answered'][str(qid)] = result
    request.session[SESSION_KEY] = state

    payload = {'result': result, 'correct': correct, 'time_delta': delta}
    # Правда о правильном ответе — только теперь, когда вопрос сыгран.
    if gq.question_type == 'multi':
        payload['correct_indices'] = gq.correct_indices
    elif gq.question_type == 'numeric':
        payload['correct_value'] = gq.correct_value
    else:
        payload['correct_index'] = gq.correct_index
    return JsonResponse(payload)
