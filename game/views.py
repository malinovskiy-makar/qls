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
from django.contrib.admin.views.decorators import staff_member_required
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_safe

from problems.management.commands.apply_topic_mapping import CANONICAL
from . import sources as game_sources
from .sources import GROUP_KEYS
from .models import ArchetypeStat, GameQuestion, GameResult, make_result_code
from . import config, stats as stats_mod

SESSION_KEY = 'econ_rush'        # состояние текущего забега
SEEN_KEY = 'econ_rush_seen'      # {mode: [id, ...]} — виданные МЕЖДУ забегами
SEEN_LIMIT = 1500                # сколько последних id помнить на режим
COUNTED_KEY = 'econ_rush_counted'  # id вопросов, уже учтённых в статистике
COUNTED_LIMIT = 6000               # столько последних помним (id пула
                                   # меняются при каждой пересборке кэша)
LAST_KEY = 'econ_rush_last'      # {mode, log} завершённого забега — для
                                 # «работы над ошибками» (переживает старт
                                 # нового забега, в отличие от SESSION_KEY)
NO_TOPIC = 'Без темы'            # вопрос без канонических тем
# В игре пока только русские вопросы (английская часть пула лежит в базе
# на будущее — отдельный режим). Минимум вопросов на тему для чипа на старте.
GAME_LANG = 'ru'
MIN_TOPIC_POOL = 30

# Готовность поверхностей нижнего ряда стартового экрана. Ставится в TRUE
# той фазой, которая приносит соответствующую страницу; до этого вход
# помечен «скоро» и никуда не ведёт.
HAS_DAILY = False
HAS_DUEL = False


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


def empty_filter():
    """Фильтр «ничего не выбрано» = играем всем пулом режима."""
    return {'topics': [], 'sources': [],
            'dmin': config.DIFFICULTY_MIN, 'dmax': config.DIFFICULTY_MAX}


def parse_filter(request):
    """Фильтр забега из query-параметров.

    Понимает и новый мульти-выбор (`topics=A&topics=B`, `sources=vsosh`,
    `dmin`/`dmax`), и старый одиночный `topic=` — ссылками со старым
    параметром могли уже поделиться, ломать их незачем.

    Неизвестные значения молча отбрасываются: фильтр — это удобство, а не
    контракт, и падать из-за подсунутой темы забег не должен.
    """
    f = empty_filter()
    topics = [t.strip() for t in request.GET.getlist('topics') if t.strip()]
    legacy = request.GET.get('topic', '').strip()
    if legacy:
        topics.append(legacy)
    # dict.fromkeys — уникальность с сохранением порядка выбора
    f['topics'] = [t for t in dict.fromkeys(topics) if t in CANONICAL]

    sources = [s.strip() for s in request.GET.getlist('sources') if s.strip()]
    f['sources'] = [s for s in dict.fromkeys(sources) if s in GROUP_KEYS]

    def _level(name, default):
        try:
            v = int(request.GET.get(name, default))
        except (TypeError, ValueError):
            return default
        return min(max(v, config.DIFFICULTY_MIN), config.DIFFICULTY_MAX)

    f['dmin'] = _level('dmin', config.DIFFICULTY_MIN)
    f['dmax'] = _level('dmax', config.DIFFICULTY_MAX)
    if f['dmin'] > f['dmax']:            # ползунок перевернули — не спорим
        f['dmin'], f['dmax'] = f['dmax'], f['dmin']
    return f


def normalize_filter(f):
    """Фильтр из состояния забега → в нормальную форму (на случай старого
    состояния в сессии, где его ещё не было)."""
    base = empty_filter()
    if isinstance(f, dict):
        base.update({k: f[k] for k in base if k in f})
    return base


def _filter_matches(f, topics, source_group, difficulty):
    """Подходит ли вопрос под фильтр. Пустой список тем/источников значит
    «любые» — так фильтр не превращается в запрет."""
    if f['topics'] and not (set(topics or []) & set(f['topics'])):
        return False
    if f['sources'] and (source_group or 'other') not in f['sources']:
        return False
    return f['dmin'] <= difficulty <= f['dmax']


def _candidate_rows(state):
    """Кандидаты режима под фильтром забега: [(id, difficulty, topics), ...].

    Читается плоским values_list по трём причинам: JSONField.__contains не
    работает на SQLite, пул маленький (тысячи строк), а join на источники
    дал бы дубли строк у задач с несколькими привязками.

    Сложность берётся через измеренную, если она есть (см. game/stats.py):
    пользовательский фильтр сложности обязан опираться на ту же величину,
    что и всё остальное в игре.
    """
    f = normalize_filter(state.get('filter'))
    qtype = config.MODES[state['mode']]['question_type']
    bank_map, arch_map = stats_mod.difficulty_overrides()
    rows = _pool_qs().filter(question_type=qtype).values_list(
        'id', 'topics', 'source_group', 'difficulty',
        'problem_id', 'part_id', 'generator_key')
    out = []
    for pk, topics, group, difficulty, problem_id, part_id, gen_key in rows:
        if problem_id is not None:
            difficulty = bank_map.get((problem_id, part_id), difficulty)
        elif gen_key:
            difficulty = arch_map.get(gen_key, difficulty)
        if _filter_matches(f, topics, group, difficulty):
            out.append((pk, difficulty, topics or []))
    return out


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
    """Страница игры: три экрана в одном шаблоне, управляются JS.

    ⚠️ Счётчиков у тем и источников на экране НЕТ, и «пустые» сочетания
    фильтров не гасятся — прямое указание Макара: фильтр работает так,
    будто задач по каждой теме и источнику неограниченно. Единственный
    счётчик, который считается по пулу, — пустой ли пул РЕЖИМА: режим без
    единого вопроса на экране не показывается вовсе (играть в него нечем).
    """
    # Сколько ru-вопросов доступно на каждый режим (для карточек на старте).
    type_counts = {}
    for qtype in _pool_qs().values_list('question_type', flat=True):
        type_counts[qtype] = type_counts.get(qtype, 0) + 1
    pool_counts = {key: type_counts.get(m['question_type'], 0)
                   for key, m in config.MODES.items()}

    return render(request, 'game/game.html', {
        # Темы — все 21 каноническая, сгруппированы по колонкам панели.
        'topic_groups': [{'key': key, 'title': title, 'topics': names}
                         for key, title, names in config.TOPIC_GROUPS],
        'source_groups': [{'key': key, 'title': title}
                          for key, title in game_sources.GROUPS],
        # «Вопросов из реальных олимпиад» — считаем ТОЛЬКО вопросы банка:
        # сгенерированные тренировочные из олимпиад не приходили, и врать
        # в цифре на первом экране нельзя.
        'pool_total': _pool_qs().filter(is_generated=False).count(),
        # JSON для JS-клиента: механика читается только из config.py
        'config_json': json.dumps({
            'modes': {key: _mode_payload(key) for key in config.MODES},
            'default_mode': config.DEFAULT_MODE,
            'pool_counts': pool_counts,
            'base_points': config.BASE_POINTS,
            'combo_steps': config.COMBO_STEPS,
            'mistakes_run_size': config.MISTAKES_RUN_SIZE,
            'difficulty_min': config.DIFFICULTY_MIN,
            'difficulty_max': config.DIFFICULTY_MAX,
            'topic_groups': [{'key': key, 'title': title, 'topics': names}
                             for key, title, names in config.TOPIC_GROUPS],
            'source_groups': [{'key': key, 'title': title}
                              for key, title in game_sources.GROUPS],
            # Входы нижнего ряда включаются, когда их страницы появляются
            # (отдельными фазами). Кнопка в никуда хуже честной пометки
            # «скоро», поэтому знание о готовности приходит с сервера.
            'has_daily': HAS_DAILY,
            'has_duel': HAS_DUEL,
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

    У целевого забега («работа над ошибками», набор, дуэль, вызов дня)
    вопросы заданы списком заранее — тогда просто выдаём их по очереди.

    Фильтр (темы, источники, сложность) применяется в _candidate_rows."""
    mode = state['mode']
    seen_run = set(state['seen'])

    if state.get('queue') is not None:
        return _pick_from_queue(request, state)

    candidates = [pk for pk, _d, _t in _candidate_rows(state)
                  if pk not in seen_run]
    if not candidates:
        return None  # пул исчерпан в этом забеге

    seen_map = request.session.get(SEEN_KEY) or {}
    seen_before = set(seen_map.get(mode, []))
    fresh = [pk for pk in candidates if pk not in seen_before]
    if not fresh:
        seen_map[mode] = []  # весь пул видан — начинаем круг заново
        fresh = candidates

    gq = GameQuestion.objects.get(id=random.choice(fresh))
    _remember_seen(request, state, gq)
    return gq


def _remember_seen(request, state, gq):
    """Пометить вопрос выданным — и запомнить, ПЕРВАЯ ли это встреча.

    Статистика вопроса (game/stats.py) считает только первые встречи:
    второй раз тот же человек отвечает уже зная ответ, и складывать это
    с чужими первыми ответами значит портить выборку.

    ⚠️ Список SEEN_KEY для этого НЕ годится: он умышленно очищается, когда
    пул режима пройден целиком («цикл по кругу», см. _pick_next), — иначе
    игра кончилась бы у того, кто прошёл весь пул. Поэтому у статистики
    свой список COUNTED_KEY, который не чистится никогда. Он плоский (без
    разбивки по режимам): один и тот же вопрос в двух режимах не окажется,
    типы разные.
    """
    mode = state['mode']
    counted = request.session.get(COUNTED_KEY) or []
    state.setdefault('first_seen', {})[str(gq.id)] = gq.id not in counted

    state['seen'].append(gq.id)
    seen_map = request.session.get(SEEN_KEY) or {}
    mode_seen = list(seen_map.get(mode, [])) + [gq.id]
    seen_map[mode] = mode_seen[-SEEN_LIMIT:]
    request.session[SEEN_KEY] = seen_map


def _mark_counted(request, qid):
    """Запомнить, что ответ на этот вопрос уже учтён в статистике.

    Помечаем при ОТВЕТЕ, а не при выдаче: игрок мог закрыть вкладку, не
    ответив, — тогда вопрос обязан остаться «первой встречей» на будущее.
    Список ограничен: id пула всё равно меняются при каждой пересборке
    кэша, помнить их вечно бессмысленно.
    """
    counted = request.session.get(COUNTED_KEY) or []
    if qid in counted:
        return
    counted.append(qid)
    request.session[COUNTED_KEY] = counted[-COUNTED_LIMIT:]


def _pick_from_queue(request, state):
    """Следующий вопрос курированного забега: список собран заранее
    (build_mistakes_run), берём по очереди. Список кончился — забег
    кончился. Вопрос мог исчезнуть из базы между сборкой очереди и выдачей
    (пул пересобирают командой) — молча идём к следующему."""
    while state['queue']:
        pk = state['queue'].pop(0)
        try:
            gq = GameQuestion.objects.get(id=pk)
        except GameQuestion.DoesNotExist:
            continue
        _remember_seen(request, state, gq)
        return gq
    return None


def _new_state(mode, topic, run_filter=None):
    """Чистое состояние забега. Очки/серия/жизни — серверные, клиент их
    только рисует; ended заполняется на третьей ошибке (api_answer) либо
    при завершении забега (api_session_finish)."""
    return {
        'mode': mode,
        'topic': topic,
        # Фильтр забега живёт в состоянии, а не только в URL старта: его
        # НАСЛЕДУЮТ «сыграть ещё раз» и «работа над ошибками». Раньше они
        # сбрасывали выбор игрока молча.
        'filter': normalize_filter(run_filter),
        'seen': [],
        'answered': {},
        'lives': config.MODES[mode]['lives'],
        'score': 0,
        'streak': 0,            # текущая серия верных подряд
        'best_streak': 0,       # лучшая серия за забег
        'ended': None,          # None | 'lives' | 'time' | 'done'
        # {id вопроса: True/False} — первая ли это встреча игрока с вопросом.
        # Ставится при выдаче (см. _remember_seen), читается при ответе:
        # в статистику вопроса идут ТОЛЬКО первые встречи.
        'first_seen': {},
        # Журнал забега: по записи на КАЖДЫЙ сыгранный вопрос, в порядке
        # игры. Из него целиком считается сводка (см. build_summary) —
        # отдельных счётчиков «сколько ошибок в теме» не заводим, иначе
        # они разойдутся с журналом.
        'log': [],
    }


@require_GET
def api_session_start(request):
    """Начать забег: режим + фильтр (темы, источники, сложность).

    Старый одиночный `topic=` продолжает работать — ссылками с ним могли
    поделиться. Пустой фильтр = весь пул режима.

    ⚠️ Пул под фильтром может оказаться пустым — это НЕ ошибка и не 503:
    забег стартует и сразу честно кончается причиной `pool_empty`
    («вопросы под твоими настройками кончились»). Проверять пул ДО старта
    и гасить сочетания фильтров запрещено — прямое указание Макара:
    фильтр работает так, будто задач по каждой теме и источнику
    неограниченно.
    """
    mode = request.GET.get('mode', '').strip() or config.DEFAULT_MODE
    if mode not in config.MODES:
        return JsonResponse({'error': 'Неизвестный режим'}, status=400)

    # Мусор среди выбранных значений отбрасываем молча (одна кривая тема
    # не должна ронять забег), но если не уцелело НИ ОДНОГО из явно
    # запрошенных — это опечатка, и молчать нечестно: игрок получил бы
    # весь пул вместо того, что просил.
    asked_topics = [t for t in (request.GET.getlist('topics')
                                + [request.GET.get('topic', '')]) if t.strip()]
    asked_sources = [s for s in request.GET.getlist('sources') if s.strip()]
    run_filter = parse_filter(request)
    if asked_topics and not run_filter['topics']:
        return JsonResponse({'error': 'Неизвестная тема'}, status=400)
    if asked_sources and not run_filter['sources']:
        return JsonResponse({'error': 'Неизвестный источник'}, status=400)
    legacy_topic = request.GET.get('topic', '').strip() or None
    state = _new_state(mode, legacy_topic, run_filter)
    gq = _pick_next(request, state)
    request.session[SESSION_KEY] = state
    payload = {
        'ok': True,
        'mode': _mode_payload(mode),
        'lives': state['lives'],
        'filter': run_filter,
        'question': _question_payload(gq, 1) if gq else None,
    }
    if gq is None:
        payload['pool_empty'] = True
    return JsonResponse(payload)


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
        for name in (r['topics'] or [NO_TOPIC]):
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
        # Темы, по которым РЕАЛЬНО соберётся работа над ошибками — тем же
        # подсчётом, каким её собирает api_session_start_mistakes. Экран
        # рисует полосу пропорции отсюда, а не считает сам: иначе он обещал
        # бы игроку одно, а сервер собирал другое. Отличается от topic_rows:
        # «Без темы» сюда не попадает — целиться в неё нечем.
        'mistake_topics': [{'topic': t, 'wrong': c} for t, c in
                           sorted(mistakes_by_topic(log).items(),
                                  key=lambda kv: (-kv[1], kv[0]))],
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
    # Счётчики вопроса — в той же точке, что и журнал: разъехаться им
    # нельзя. Только первая встреча игрока с вопросом (см. _remember_seen):
    # повторный ответ того же человека уже знает правильный вариант.
    if (state.get('first_seen') or {}).get(str(qid)):
        stat = stats_mod.record_answer(gq, result, elapsed_ms)
        _mark_counted(request, qid)
    else:
        stat = stats_mod.get_stat(gq)
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
    # Чертёж к задаче — туда же, в разбор. Как и решение, он содержит ответ
    # (на графике отмечены оптимум и цены), поэтому в payload вопроса его
    # нет: игрок получает его только после того, как вопрос сыгран.
    if gq.is_generated and gq.figure:
        payload['figure'] = gq.figure
    # Как этот вопрос решают остальные — чип на карточке обратной связи.
    # Именно в ОТВЕТЕ, а не в payload вопроса: доля верных у данетки почти
    # выдавала бы правильный вариант. Ниже порога попыток поля нет вовсе —
    # клиенту нечего рисовать, и он чипа не покажет.
    pub = stats_mod.public_stat(stat)
    if pub:
        payload['p_correct'] = pub['p_correct']
        payload['attempts'] = pub['attempts']
    return JsonResponse(payload)


def mistakes_by_topic(log):
    """Сколько ошибок в каждой теме — по журналу забега.

    Вопрос с двумя темами даёт ошибку обеим: какая из них подвела, мы не
    знаем, и делить ошибку пополам было бы выдумкой. Вопросы без тем
    в подсчёт не идут: целиться в «Без темы» нечем (см. build_mistakes_run).
    """
    counts = {}
    for r in log:
        if r['outcome'] != 'wrong':
            continue
        for name in (r['topics'] or []):
            counts[name] = counts.get(name, 0) + 1
    return counts


def allocate_quotas(counts, size):
    """Раздать ровно `size` мест по темам пропорционально числу ошибок —
    методом наибольшего остатка.

    Пропорция по сырому числу ошибок: при трёх жизнях ошибок мало, зато
    они точные. Пример: 2 ошибки в A и 1 в B на 10 мест → A получает
    6 целых мест (10·2/3 = 6,67) и B — 3 (10·1/3 = 3,33); девять роздано,
    десятое уходит теме с бо́льшим остатком, то есть A → 7/3.

    Ничья остатков решается числом ошибок, затем именем темы: результат
    обязан быть один и тот же при одинаковом входе.
    """
    pairs = [(t, c) for t, c in counts.items() if c > 0]
    total = sum(c for _, c in pairs)
    if not pairs or total <= 0 or size <= 0:
        return {}
    quotas, remainders = {}, []
    for topic, cnt in pairs:
        exact = size * cnt / total
        base = int(exact)
        quotas[topic] = base
        remainders.append((exact - base, cnt, topic))
    left = size - sum(quotas.values())
    remainders.sort(key=lambda r: (-r[0], -r[1], r[2]))
    for i in range(left):
        quotas[remainders[i % len(remainders)][2]] += 1
    return quotas


def build_mistakes_run(rows, quotas, size, seen_before=()):
    """Список id вопросов для целевого забега.

    rows — кандидаты нужного типа и языка: [(id, [темы]), ...].
    Сначала каждой теме выдаём её квоту. Не хватило вопросов в теме —
    недобор добираем сначала из других тем ошибок, потом из любых вопросов
    того же типа. Если и тогда меньше size — забег будет короче: это не
    ошибка, а честный конец пула (клиент завершит его причиной 'done').

    Один вопрос дважды не берём (он мог попасть в две темы ошибок сразу),
    и внутри каждой выборки действует то же правило «сначала невиданные»,
    что в обычном забеге.
    """
    seen_before = set(seen_before)
    taken, used = [], set()

    def pick(pool, n):
        if n <= 0:
            return
        pool = [pk for pk in dict.fromkeys(pool) if pk not in used]
        fresh = [pk for pk in pool if pk not in seen_before]
        old = [pk for pk in pool if pk in seen_before]
        random.shuffle(fresh)
        random.shuffle(old)
        for pk in (fresh + old)[:n]:
            used.add(pk)
            taken.append(pk)

    by_topic = {}
    for pk, topics in rows:
        for name in (topics or []):
            by_topic.setdefault(name, []).append(pk)

    # Крупные квоты первыми: если вопросов в обрез, их получит тема,
    # где игрок ошибался больше.
    for topic, quota in sorted(quotas.items(), key=lambda kv: (-kv[1], kv[0])):
        pick(by_topic.get(topic, []), quota)
    if len(taken) < size:  # недобор — из любых тем ошибок
        pick([pk for t in quotas for pk in by_topic.get(t, [])], size - len(taken))
    if len(taken) < size:  # и уже из любых вопросов этого типа
        pick([pk for pk, _ in rows], size - len(taken))

    random.shuffle(taken)  # темы вперемешку, а не блоками
    return taken[:size]


@require_GET
def api_session_start_mistakes(request):
    """Начать целевой забег «работа над ошибками».

    Темы и пропорция — из журнала ПРЕДЫДУЩЕГО забега (LAST_KEY), режим —
    его же: разбирать ошибки «Пули» вопросами «Классики» бессмысленно,
    это другой тип вопроса.
    """
    last = request.session.get(LAST_KEY)
    if not last or not last.get('log'):
        return JsonResponse({'error': 'Нет завершённого забега'}, status=400)
    mode = last.get('mode')
    if mode not in config.MODES:
        return JsonResponse({'error': 'Неизвестный режим'}, status=400)

    counts = mistakes_by_topic(last['log'])
    if not counts:
        return JsonResponse({'error': 'В этом забеге не было ошибок'}, status=400)

    # Фильтр наследуется от разбираемого забега: игрок выбрал источники и
    # сложность не для того, чтобы разбор ошибок молча вернул ему весь пул.
    run_filter = normalize_filter(last.get('filter'))
    probe = _new_state(mode, None, run_filter)
    rows = [(pk, topics) for pk, _d, topics in _candidate_rows(probe)]
    quotas = allocate_quotas(counts, config.MISTAKES_RUN_SIZE)
    seen_map = request.session.get(SEEN_KEY) or {}
    queue = build_mistakes_run(rows, quotas, config.MISTAKES_RUN_SIZE,
                               seen_map.get(mode, []))
    if not queue:
        return JsonResponse({'error': 'Вопросов по этим темам не нашлось'},
                            status=503)

    state = _new_state(mode, None, run_filter)
    state['queue'] = queue
    state['mistakes_run'] = True
    gq = _pick_next(request, state)
    request.session[SESSION_KEY] = state
    return JsonResponse({
        'ok': True,
        'mode': _mode_payload(mode),
        'lives': state['lives'],
        'mistakes_run': True,
        'topics': sorted(quotas, key=lambda t: (-quotas[t], t)),
        'question': _question_payload(gq, 1),
    })


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
        state['ended'] = _end_reason(state, body.get('reason'))
    request.session[SESSION_KEY] = state
    # Журнал завершённого забега — отдельным ключом: с него живёт «работа
    # над ошибками», а SESSION_KEY затрётся, как только начнётся новый
    # забег. Храним нужное ей: режим, журнал и фильтр (его наследует
    # целевой забег — иначе выбор игрока молча сбрасывался бы).
    request.session[LAST_KEY] = {'mode': state['mode'], 'log': state['log'],
                                 'filter': normalize_filter(state.get('filter'))}

    summary = build_summary(state)
    share = _save_result(request, state, summary)
    return JsonResponse({'summary': summary, 'share': share})


def _end_reason(state, claimed):
    """Чем кончился забег. Слово клиента НЕ перебивает сервер.

    Четыре исхода:
      lives      — выбыл, кончились жизни (ставит сам сервер в api_answer);
      time       — вышло время (знает только клиент, у него таймер);
      pool_empty — вопросы под фильтром игрока кончились;
      set_done   — курированный список пройден до конца (набор, дуэль,
                   вызов дня, работа над ошибками).

    Клиент знает про конец вопросов, но НЕ знает, курированный это забег
    или свободный, — а сервер знает. Поэтому он присылает нейтральное
    'done' (и старые клиенты тоже), а разделение делает сервер.
    """
    if claimed == 'time':
        return 'time'
    if claimed in ('done', 'pool_empty', 'set_done'):
        return 'set_done' if state.get('queue') is not None else 'pool_empty'
    return 'time'


def _save_result(request, state, summary):
    """Сохранить результат забега и отдать ссылку на публичную страницу.

    Ссылка АБСОЛЮТНАЯ (build_absolute_uri): её вставляют в Telegram и VK,
    а относительный путь там просто не откроется.

    Идемпотентность: код забега запоминается в состоянии, повторный вызов
    finish отдаёт ту же строку, а не плодит новые.
    """
    code = state.get('result_code')
    result = GameResult.objects.filter(code=code).first() if code else None
    if result is None:
        for _ in range(5):   # коллизия кода почти невероятна, но не 500
            try:
                result = GameResult.objects.create(
                    code=make_result_code(),
                    mode=state['mode'],
                    score=summary['score'],
                    correct_count=summary['correct'],
                    total_count=summary['total'],
                    max_combo=summary['max_multiplier'],
                    ended_reason=summary['ended_reason'],
                    topic_breakdown=summary['topic_rows'],
                    difficulty_breakdown=summary['difficulty'],
                    score_curve=summary['score_curve'],
                )
                break
            except IntegrityError:
                continue
        if result is None:
            return None      # не смогли сохранить — забег важнее ссылки
        state['result_code'] = result.code
        request.session[SESSION_KEY] = state
    return {
        'code': result.code,
        'url': request.build_absolute_uri(
            reverse('game:result', args=[result.code])),
    }


@require_safe
def result_page(request, code):
    """Публичная страница результата — то, что видит человек по ссылке.

    Без логина и read-only: чужой забег нельзя ни продолжить, ни изменить.
    require_safe, а не require_GET: HEAD должен отвечать как везде на сайте
    (мессенджеры дёргают HEAD перед разворачиванием превью).
    """
    result = get_object_or_404(GameResult, code=code)
    mode_title = (config.MODES.get(result.mode) or {}).get('title', result.mode)
    # Ссылки в мета-тегах — абсолютные: относительный путь мессенджер
    # не развернёт.
    page_url = request.build_absolute_uri(
        reverse('game:result', args=[result.code]))
    return render(request, 'game/result.html', {
        'r': result,
        'mode_title': mode_title,
        'accuracy': result.accuracy,
        'topics': [t for t in (result.topic_breakdown or []) if t.get('total')],
        'page_url': page_url,
        'game_url': request.build_absolute_uri(reverse('game:page')),
        'og_image': request.build_absolute_uri(static('game/og_default.png')),
        'og_title': f'{result.score} очков в Econ Rush — обгонишь?',
        'og_description': (f'Режим «{mode_title}» · точность {result.accuracy}% '
                           f'· комбо ×{result.max_combo}'),
        'curve_points': _curve_points(result.score_curve),
    })


@staff_member_required
@require_safe
def stats_page(request):
    """Служебная страница статистики пула — только для персонала.

    Смотрят её ради двух хвостов распределения: вопросы с долей верных
    ниже STATS_BROKEN_BELOW почти наверняка сломаны (не тот ключ ответа,
    потерялась формула при импорте), выше STATS_TRIVIAL_ABOVE — тривиальны
    и только разбавляют пул. Середина интересна как измеренная сложность.

    Вопросы без набранных попыток внизу списка: у них ещё нечего смотреть.
    """
    tab = 'arch' if request.GET.get('tab') == 'arch' else 'pool'
    min_attempts = config.STATS_MIN_ATTEMPTS

    if tab == 'arch':
        rows = []
        for st in ArchetypeStat.objects.all():
            rows.append({
                'key': st.generator_key,
                'shown': st.shown,
                'attempts': st.attempts,
                'skipped': st.skipped,
                'percent': (round(100 * st.p_correct)
                            if st.attempts >= min_attempts else None),
                'avg_ms': st.avg_ms,
            })
        rows.sort(key=lambda r: (r['percent'] is None,
                                 r['percent'] if r['percent'] is not None else 0,
                                 r['key']))
        return render(request, 'game/stats.html', {
            'tab': tab, 'arch_rows': rows, 'rows': [],
            'min_attempts': min_attempts,
            'broken_pct': round(100 * config.STATS_BROKEN_BELOW),
            'trivial_pct': round(100 * config.STATS_TRIVIAL_ABOVE),
        })

    questions = list(_pool_qs().order_by('id'))
    by_id = stats_mod.bulk_stats(questions)
    rows = []
    for gq in questions:
        st = by_id.get(gq.id)
        attempts = st.attempts if st else 0
        percent = (round(100 * st.p_correct)
                   if st and attempts >= min_attempts else None)
        rows.append({
            'id': gq.id,
            'text': gq.question[:140],
            'type': gq.get_question_type_display(),
            'topics': ', '.join(gq.topics or []) or '—',
            'shown': st.shown if st else 0,
            'attempts': attempts,
            'percent': percent,
            'avg_ms': st.avg_ms if st else 0,
            'difficulty': stats_mod.effective_difficulty(gq, st),
            'measured': percent is not None,
            'problem_id': gq.problem_id,
            'generated': gq.is_generated,
            'broken': percent is not None and percent < 100 * config.STATS_BROKEN_BELOW,
            'trivial': percent is not None and percent > 100 * config.STATS_TRIVIAL_ABOVE,
        })
    # Сортировка по доле верных: сломанные — вверху, вопросы без данных —
    # внизу (у них смотреть пока нечего).
    rows.sort(key=lambda r: (r['percent'] is None,
                             r['percent'] if r['percent'] is not None else 0,
                             r['id']))
    return render(request, 'game/stats.html', {
        'tab': tab,
        'rows': rows,
        'arch_rows': [],
        'total': len(rows),
        'measured': sum(1 for r in rows if r['measured']),
        'min_attempts': min_attempts,
        'broken_pct': round(100 * config.STATS_BROKEN_BELOW),
        'trivial_pct': round(100 * config.STATS_TRIVIAL_ABOVE),
    })


def _curve_points(curve):
    """Точки мини-графика счёта для публичной страницы: «x,y x,y …» под
    <polyline>. Считаем в питоне — на публичной странице JS не нужен вовсе.
    Меньше двух точек — графика нет (рисовать нечего)."""
    if not curve or len(curve) < 2:
        return ''
    w, h, pad = 300.0, 60.0, 3.0
    top = max(curve) or 1
    step = (w - 2 * pad) / (len(curve) - 1)
    return ' '.join(
        '%.1f,%.1f' % (pad + i * step, h - pad - (v / top) * (h - 2 * pad))
        for i, v in enumerate(curve))
