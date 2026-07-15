"""
Бэкенд Econ Rush.

Принципы:
- Страница и API публичные (без логина) — игра работает как инструмент
  привлечения.
- Вся правда о правильных ответах живёт ТОЛЬКО на сервере: эндпоинт вопроса
  никогда не отдаёт correct_index/correct_indices/correct_value; клиент
  узнаёт правильный ответ лишь после своего ответа.
- Состояние забега — в Django session (бэкенд сессий, не куки: в состоянии
  лежат списки id и журнал забега): режим, список выданных вопросов (без
  повторов внутри забега), жизни, очки, серия. Отдельный ключ SEEN_KEY живёт
  МЕЖДУ забегами: «сначала невиданные» — вопрос не повторится в новых
  забегах, пока пул режима не исчерпан (тогда цикл по кругу).
- Очки, комбо и жизни считает СЕРВЕР и отдаёт клиенту готовыми числами —
  один источник правды. Клиент их только рисует. У клиента остаётся ТОЛЬКО
  таймер (сервер не тикает): он владеет обратным отсчётом, применяет дельту
  времени из ответа сервера и сам сообщает конец забега по времени.
  Серверного лидерборда пока нет, поэтому анти-чит сводится к сокрытию
  правильных ответов.
"""
import json
import random
from fractions import Fraction

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
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


def _pool_qs():
    """Базовый queryset игрового пула с учётом флага GAME_GENERATED_ENABLED:
    при False сгенерированные вопросы полностью исключаются из выдачи
    (единая точка — счётчики страницы и выбор вопроса ходят только сюда)."""
    qs = GameQuestion.objects.filter(lang=GAME_LANG)
    if not getattr(settings, 'GAME_GENERATED_ENABLED', False):
        qs = qs.filter(is_generated=False)
    return qs


def _mode_payload(mode_key):
    """Параметры режима для клиента (тайминги и жизни — только из config.py)."""
    m = config.MODES[mode_key]
    return {
        'key': mode_key,
        'title': m['title'],
        'question_type': m['question_type'],
        'duration': m['duration'],
        'time_correct': m['time_correct'],
        'time_wrong': m['time_wrong'],
        'time_skip': m['time_skip'],
        'lives': m['lives'],
    }


@ensure_csrf_cookie
def game_page(request):
    """Страница игры: три экрана в одном шаблоне, управляются JS."""
    # Чипы тем: только канонические темы, по которым в пуле достаточно вопросов.
    counts = {}
    for g in _pool_qs().values_list('topics', flat=True):
        for name in g:
            counts[name] = counts.get(name, 0) + 1
    topics = [name for name in CANONICAL
              if counts.get(name, 0) >= MIN_TOPIC_POOL]

    # Сколько ru-вопросов доступно на каждый режим (для карточек на старте).
    type_counts = {}
    for qtype in _pool_qs().values_list('question_type', flat=True):
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
        }),
    })


def _question_payload(gq, number):
    """Вопрос для клиента — БЕЗ правильного ответа (анти-чит).

    У сгенерированных вопросов gen_solution сюда тоже НЕ входит: решение
    содержит ответ, клиент получает его только в ответе api_answer."""
    payload = {
        'id': gq.id,
        'number': number,
        'type': gq.question_type,
        'question': gq.question,
        'options': gq.options,
        'topics': gq.topics,
        'problem_id': gq.problem_id,     # None у сгенерированных
        'generated': gq.is_generated,    # чип «Тренировочный» на карточке
    }
    if gq.question_type == 'numeric' and gq.unit:
        # единица измерения («%», «руб.») — подсказка у поля ввода, не ответ
        payload['unit'] = gq.unit
    return payload


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

    rows = _pool_qs().filter(question_type=qtype).values_list('id', 'topics')
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


def _new_state(mode, topic):
    """Чистое состояние забега. Очки/серия/жизни — серверные, клиент их
    только рисует; ended заполняется на третьей ошибке (api_answer) либо
    при завершении забега (api_session_finish)."""
    return {
        'mode': mode,
        'topic': topic,
        'seen': [],
        'answered': {},
        'lives': config.MODES[mode]['lives'],
        'score': 0,
        'streak': 0,            # текущая серия верных подряд
        'best_streak': 0,       # лучшая серия за забег
        'ended': None,          # None | 'lives' | 'time' | 'done'
        # Журнал забега: по записи на КАЖДЫЙ сыгранный вопрос, в порядке
        # игры. Из него целиком считается сводка (см. build_summary) —
        # отдельных счётчиков «сколько ошибок в теме» не заводим, иначе
        # они разойдутся с журналом.
        'log': [],
    }


@require_GET
def api_session_start(request):
    """Начать забег: режим + тема (или «все») → первый вопрос и тайминги."""
    mode = request.GET.get('mode', '').strip() or config.DEFAULT_MODE
    if mode not in config.MODES:
        return JsonResponse({'error': 'Неизвестный режим'}, status=400)
    topic = request.GET.get('topic', '').strip()
    if topic and topic not in CANONICAL:
        return JsonResponse({'error': 'Неизвестная тема'}, status=400)

    state = _new_state(mode, topic or None)
    gq = _pick_next(request, state)
    if gq is None:
        return JsonResponse({'error': 'Пул вопросов пуст'}, status=503)
    request.session[SESSION_KEY] = state
    return JsonResponse({
        'ok': True,
        'mode': _mode_payload(mode),
        'lives': state['lives'],
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


def _parse_elapsed(body):
    """Сколько миллисекунд игрок думал над вопросом (клиент знает момент
    показа карточки). Поле необязательное — старый клиент его не шлёт,
    тогда 0. Мусор, отрицательные и неправдоподобно большие значения — тоже
    0: сводка не должна падать из-за подсунутого поля."""
    try:
        v = int(body.get('elapsed_ms') or 0)
    except (TypeError, ValueError):
        return 0
    return v if 0 <= v <= 3600000 else 0


# Корзины гистограммы времени: (левая граница сек, правая или None = ∞, подпись).
TIME_BUCKETS = [
    (0, 2, '0–2 с'),
    (2, 4, '2–4 с'),
    (4, 6, '4–6 с'),
    (6, 8, '6–8 с'),
    (8, 10, '8–10 с'),
    (10, 15, '10–15 с'),
    (15, 30, '15–30 с'),
    (30, None, '>30 с'),
]

# Сложность GameQuestion 1–5 → три группы для кольцевой диаграммы.
DIFFICULTY_GROUPS = [('easy', 'Лёгкие', (1, 2)),
                     ('medium', 'Средние', (3,)),
                     ('hard', 'Сложные', (4, 5))]


def build_summary(state):
    """Сводка забега — чистая функция журнала (state['log']).

    Ничего не берёт из базы и не считает заново того, что уже записано:
    журнал — единственный источник. Точность считается от ПОПЫТОК
    (верные + неверные): пропуск не ответ, и портить им точность нечестно —
    иначе честный пропуск наказывался бы сильнее угадывания.
    """
    log = state.get('log') or []
    correct = sum(1 for r in log if r['outcome'] == 'correct')
    wrong = sum(1 for r in log if r['outcome'] == 'wrong')
    skipped = sum(1 for r in log if r['outcome'] == 'skip')
    attempts = correct + wrong

    # Разбивка по темам. Вопрос без тем идёт в «Без темы» — иначе его
    # ошибки просто исчезли бы из работы над ошибками.
    topics = {}
    for r in log:
        for name in (r['topics'] or ['Без темы']):
            cell = topics.setdefault(name, {'correct': 0, 'wrong': 0, 'skip': 0})
            cell[r['outcome']] += 1
    topic_rows = []
    for name, cell in topics.items():
        tries = cell['correct'] + cell['wrong']
        topic_rows.append({
            'topic': name,
            'correct': cell['correct'],
            'wrong': cell['wrong'],
            'skip': cell['skip'],
            'total': cell['correct'] + cell['wrong'] + cell['skip'],
            'accuracy': round(100 * cell['correct'] / tries) if tries else 0,
        })
    # Сначала темы с ошибками (главное на экране), потом по объёму.
    topic_rows.sort(key=lambda t: (-t['wrong'], -t['total'], t['topic']))

    difficulty = []
    for key, title, levels in DIFFICULTY_GROUPS:
        rows = [r for r in log if r['difficulty'] in levels]
        difficulty.append({
            'key': key,
            'title': title,
            'total': len(rows),
            'correct': sum(1 for r in rows if r['outcome'] == 'correct'),
        })

    buckets = []
    for lo, hi, title in TIME_BUCKETS:
        n = 0
        for r in log:
            sec = (r['elapsed_ms'] or 0) / 1000.0
            if sec >= lo and (hi is None or sec < hi):
                n += 1
        buckets.append({'title': title, 'count': n})

    best_streak = state.get('best_streak', 0)
    return {
        'mode': state['mode'],
        'mode_title': config.MODES[state['mode']]['title'],
        'topic': state.get('topic'),
        'score': state.get('score', 0),
        'correct': correct,
        'wrong': wrong,
        'skipped': skipped,
        'total': attempts,
        'accuracy': round(100 * correct / attempts) if attempts else 0,
        'best_streak': best_streak,
        'max_multiplier': config.combo_multiplier(best_streak),
        'lives_left': state.get('lives', 0),
        'lives_max': config.MODES[state['mode']]['lives'],
        'ended_reason': state.get('ended') or 'time',
        # номер вопроса, на котором выбыли (нужен плашке экрана результатов)
        'last_number': log[-1]['number'] if log else 0,
        'topic_rows': topic_rows,
        'difficulty': difficulty,
        'time_buckets': buckets,
        # кривые для графиков: значение по номеру вопроса
        'score_curve': [r['running_score'] for r in log],
        'combo_curve': [r['running_combo'] for r in log],
        'played_at': timezone.now().isoformat(timespec='seconds'),
    }


@require_POST
def api_answer(request):
    """Проверка ответа. Тело: {question_id, choice|choices|value}
    (null/отсутствие = пропуск). Ответ: верно/нет, правильный ответ
    (по типу вопроса), дельта времени, а также посчитанные СЕРВЕРОМ очки,
    серия и жизни. Когда жизни кончились — game_over с причиной 'lives'."""
    state = request.session.get(SESSION_KEY)
    if not state:
        return JsonResponse({'error': 'Забег не начат'}, status=400)
    if state.get('ended'):
        return JsonResponse({'error': 'Забег уже завершён'}, status=409)
    try:
        body = json.loads(request.body.decode('utf-8'))
        qid = int(body['question_id'])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Некорректный запрос'}, status=400)
    elapsed_ms = _parse_elapsed(body)

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
    points = 0
    if is_skip:
        # Пропуск безопасен: жизнь цела, комбо цело, время не трогаем.
        result = 'skip'
        delta = mode_cfg['time_skip']
    elif correct:
        result = 'correct'
        delta = mode_cfg['time_correct']
        state['streak'] += 1
        state['best_streak'] = max(state['best_streak'], state['streak'])
        points = config.BASE_POINTS * config.combo_multiplier(state['streak'])
        state['score'] += points
    else:
        # Ошибка: минус жизнь и комбо в ноль. Время НЕ трогаем —
        # наказание одно, а не два.
        result = 'wrong'
        delta = mode_cfg['time_wrong']
        state['streak'] = 0
        state['lives'] = max(0, state['lives'] - 1)

    state['answered'][str(qid)] = result
    number = state['seen'].index(qid) + 1   # номер вопроса в забеге
    if state['lives'] <= 0:
        state['ended'] = 'lives'

    # Журнал: всё, из чего потом считается сводка забега. Темы и сложность
    # берём из GameQuestion (они там денормализованы) — сводке не придётся
    # ходить в базу за вопросами, которых к тому времени может уже не быть
    # (пул пересобирается командой build_game_pool).
    state['log'].append({
        'question_id': qid,
        'number': number,
        'topics': gq.topics or [],
        'difficulty': gq.difficulty,
        'question_type': gq.question_type,
        'outcome': result,
        'elapsed_ms': elapsed_ms,
        'running_score': state['score'],
        'running_combo': state['streak'],
        'lives_after': state['lives'],
    })
    request.session[SESSION_KEY] = state

    payload = {
        'result': result,
        'correct': correct,
        'time_delta': delta,
        'points': points,           # очки именно за этот ответ
        'score': state['score'],
        'streak': state['streak'],
        'best_streak': state['best_streak'],
        'lives': state['lives'],
    }
    if state['ended'] == 'lives':
        payload['game_over'] = {'reason': 'lives', 'question_number': number}
    # Правда о правильном ответе — только теперь, когда вопрос сыгран.
    if gq.question_type == 'multi':
        payload['correct_indices'] = gq.correct_indices
    elif gq.question_type == 'numeric':
        payload['correct_value'] = gq.correct_value
    else:
        payload['correct_index'] = gq.correct_index
    # Сгенерированный вопрос: пошаговое решение для «Разобрать ошибки»
    # (в каталог его не откроешь — задачи-источника нет).
    if gq.is_generated and gq.gen_solution:
        payload['solution'] = gq.gen_solution
    return JsonResponse(payload)


@require_POST
def api_session_finish(request):
    """Завершить забег и получить сводку.

    Причину конца сообщает клиент ('time' — вышло время, 'done' — кончились
    вопросы), но слово клиента НЕ перебивает сервер: если сервер уже сам
    закрыл забег по жизням, причина остаётся 'lives'. Про время сервер
    знать не может — таймер живёт на клиенте.

    Идемпотентен: повторный вызов просто пересчитает ту же сводку.
    """
    state = request.session.get(SESSION_KEY)
    if not state:
        return JsonResponse({'error': 'Забег не начат'}, status=400)
    try:
        body = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        body = {}
    if not state.get('ended'):
        reason = body.get('reason')
        state['ended'] = reason if reason in ('time', 'done') else 'time'
    request.session[SESSION_KEY] = state
    return JsonResponse({'summary': build_summary(state)})
