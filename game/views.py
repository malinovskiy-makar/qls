"""
Бэкенд Wecon Rush.

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
import datetime
import json
import random
import time
from fractions import Fraction
from urllib.parse import quote

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import IntegrityError
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_safe

from problems.jsonsafe import dumps_for_script
from problems.management.commands.apply_topic_mapping import CANONICAL
from . import sources as game_sources
from .sources import GROUP_KEYS
from .models import (ArchetypeStat, GameQuestion, GameResult, GameSet,
                     make_result_code)
from . import config, filters as game_filters, scoring, stats as stats_mod
from .figures import base as figures_base
from .figures.base import QUESTION_TYPE as FIGURE_AUDIT

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
HAS_DAILY = True     # Фаза 4 — /game/daily/
HAS_DUEL = True      # Фаза 5 — /game/duel/new/ и /game/d/<код>/


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
    """Базовый queryset игрового пула — ЕДИНАЯ точка входа в пул.

    Здесь же живут оба флага выдачи. Все поверхности (счётчики стартовой
    страницы, чипы тем, выбор вопроса, очередь работы над ошибками, наборы)
    ходят только сюда — это и делает флаги герметичными.

    ⚠️ Флага два, и они НЕЗАВИСИМЫ:
    - `GAME_GENERATED_ENABLED` — семнадцать архетипов (`game/generators/`);
    - `GAME_FIGURE_ENABLED` — сюжеты режима «График» (`game/figures/`).

    Вопросы аудита обязаны иметь `is_generated=True`, иначе `build_game_pool`
    снесёт их при первой же пересборке пула (она удаляет все строки с
    is_generated=False). Отсюда и исключение ниже: без него выключенный
    `GAME_GENERATED_ENABLED` гасил бы и «График», и флаги перестали бы быть
    независимыми.

    ⚠️ Вопросы прежнего типа `figure_choice` не выдаются НИКОГДА: слот
    режима «График» занял аудит чужого решения. Строки в базе остаются.
    """
    qs = GameQuestion.objects.filter(lang=GAME_LANG).exclude(
        question_type='figure_choice')
    if not getattr(settings, 'GAME_FIGURE_ENABLED', False):
        qs = qs.exclude(question_type=FIGURE_AUDIT)
    if not getattr(settings, 'GAME_GENERATED_ENABLED', False):
        qs = qs.filter(Q(is_generated=False) | Q(question_type=FIGURE_AUDIT))
    return qs


def _mode_enabled(mode):
    """Есть ли у режима вообще вопросы в пуле — БЕЗ учёта фильтра забега.

    Отличает две разные пустоты, которые раньше были слиты в одну
    (`pool_empty`): режим, выключенный флагом (сегодня — «График» при
    `GAME_FIGURE_ENABLED=False`), не наберёт вопросов ни под каким
    фильтром — это НЕДОСТИЖИМОСТЬ режима. Пустой пул ПОД ФИЛЬТРОМ у
    режима, у которого вопросы вообще есть, — другая вещь (см.
    `_candidate_rows` в `api_session_start`)."""
    qtype = config.MODES[mode]['question_type']
    return _pool_qs().filter(question_type=qtype).exists()


def empty_filter():
    """Фильтр «ничего не выбрано» = играем всем пулом режима.

    ⚠️ СЛОЖНОСТЬ — МНОЖЕСТВО, А НЕ ОТРЕЗОК. Ползунок «от…до» умел выбрать
    только непрерывный диапазон: «1★ и 5★, без середины» им не задать, а
    именно так и хотят готовиться (лёгкие на разгон, сложные на разбор).
    Пустой список значит «любая» — так фильтр не превращается в запрет.
    Старые `dmin`/`dmax` из ссылок по-прежнему понимаются (см. parse_filter).
    """
    return {'topics': [], 'tags': [], 'sources': [], 'stars': [],
            'features': [], 'character': ''}


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

    tags = []
    for raw in request.GET.getlist('tags'):
        raw = (raw or '').strip()
        if raw.isdigit() and int(raw) not in tags:
            tags.append(int(raw))
    f['tags'] = tags

    # Звёзды: любое подмножество из пяти (`stars=1&stars=3`).
    stars = set()
    for raw in request.GET.getlist('stars'):
        raw = (raw or '').strip()
        if raw.isdigit() and config.DIFFICULTY_MIN <= int(raw) <= config.DIFFICULTY_MAX:
            stars.add(int(raw))
    # ⚠️ СТАРЫЕ `dmin`/`dmax` ПОНИМАЕМ И ПРЕВРАЩАЕМ В МНОЖЕСТВО. Ссылками с
    # ними могли уже поделиться, а «работа над ошибками» наследует фильтр
    # прошлого забега — сломать их значит молча сменить человеку выбор.
    if not stars and ('dmin' in request.GET or 'dmax' in request.GET):
        def _level(name, default):
            try:
                v = int(request.GET.get(name, default))
            except (TypeError, ValueError):
                return default
            return min(max(v, config.DIFFICULTY_MIN), config.DIFFICULTY_MAX)
        lo = _level('dmin', config.DIFFICULTY_MIN)
        hi = _level('dmax', config.DIFFICULTY_MAX)
        if lo > hi:                      # ползунок перевернули — не спорим
            lo, hi = hi, lo
        stars = set(range(lo, hi + 1))
    # Выбраны все пять — это то же самое, что не выбрано ничего.
    if len(stars) == config.DIFFICULTY_MAX - config.DIFFICULTY_MIN + 1:
        stars = set()
    f['stars'] = sorted(stars)

    # Группы-заготовки: разбираем, но пока их варианты пусты (см. filters.py).
    f['features'] = [x for x in dict.fromkeys(
        v.strip() for v in request.GET.getlist('features') if v.strip())
        if x in dict(game_filters.FEATURES)]
    ch = (request.GET.get('character') or '').strip()
    f['character'] = ch if ch in dict(game_filters.CHARACTERS) else ''
    return f


def is_empty_filter(f):
    """Забег БЕЗ ЕДИНОГО фильтра — по всем измерениям сразу.

    ⚠️ Именно это, а не «фильтр не передали в адресе», даёт множитель
    SCOPE_MULTIPLIER. Адрес подделывается, состояние забега — нет.
    """
    f = normalize_filter(f)
    return not any((f['topics'], f['tags'], f['sources'], f['stars'],
                    f['features'], f['character']))


def is_difficulty_filtered(f):
    """Выбирал ли игрок себе сложность.

    ⚠️ ЭТО ДЕЛАЕТ ЗАБЕГ ТРЕНИРОВОЧНЫМ (решение владельца по симуляции).
    Подобрать сложность можно — так готовятся, — но обгонять кого-то в
    таблице на подобранном пуле нельзя: симуляция показала, что «только 5★»
    даёт более высокий удачный забег, чем честный (см. ADR 0055).
    Темы, теги и источники зачётности НЕ лишают: они меняют, ЧТО решаешь,
    а не КАК ТРУДНО.
    """
    return bool(normalize_filter(f)['stars'])


def normalize_filter(f):
    """Фильтр из состояния забега → в нормальную форму.

    ⚠️ Состояние могло лечь в сессию ДО этой правки — там были `dmin`/`dmax`
    вместо `stars`. Переводим молча: у человека посреди сессии не должен
    сброситься выбор.
    """
    base = empty_filter()
    if isinstance(f, dict):
        base.update({k: f[k] for k in base if k in f})
        if not base['stars'] and ('dmin' in f or 'dmax' in f):
            lo = int(f.get('dmin') or config.DIFFICULTY_MIN)
            hi = int(f.get('dmax') or config.DIFFICULTY_MAX)
            lo = min(max(lo, config.DIFFICULTY_MIN), config.DIFFICULTY_MAX)
            hi = min(max(hi, config.DIFFICULTY_MIN), config.DIFFICULTY_MAX)
            if lo > hi:
                lo, hi = hi, lo
            span = set(range(lo, hi + 1))
            if len(span) < config.DIFFICULTY_MAX - config.DIFFICULTY_MIN + 1:
                base['stars'] = sorted(span)
    base['stars'] = sorted({int(x) for x in (base['stars'] or [])
                            if str(x).isdigit()
                            or isinstance(x, int)})
    base['tags'] = [int(x) for x in (base['tags'] or [])
                    if str(x).lstrip('-').isdigit()]
    return base


def _filter_matches(f, topics, source_group, difficulty, tag_ids=()):
    """Подходит ли вопрос под фильтр. Пустой список любого измерения значит
    «любые» — так фильтр не превращается в запрет."""
    if f['topics'] and not (set(topics or []) & set(f['topics'])):
        return False
    if f['tags'] and not (set(tag_ids or []) & set(f['tags'])):
        return False
    if f['sources'] and (source_group or 'other') not in f['sources']:
        return False
    if f['stars'] and difficulty not in f['stars']:
        return False
    return True


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
        'problem_id', 'part_id', 'generator_key', 'tag_ids')
    out = []
    for (pk, topics, group, difficulty, problem_id, part_id, gen_key,
         tag_ids) in rows:
        if problem_id is not None:
            difficulty = bank_map.get((problem_id, part_id), difficulty)
        elif gen_key:
            difficulty = arch_map.get(gen_key, difficulty)
        if _filter_matches(f, topics, group, difficulty, tag_ids):
            out.append((pk, difficulty, topics or []))
    return out


def pool_counts_for(f):
    u"""Сколько вопросов доступно каждому режиму под фильтром `f`.

    ⚠️ СЧИТАЕТСЯ ТОЙ ЖЕ ФУНКЦИЕЙ, ЧТО ВЫБИРАЕТ ВОПРОСЫ (`_candidate_rows`).
    Отдельный запрос «сколько подходит» разошёлся бы с выдачей при первой
    же правке фильтра, и экран обещал бы игроку не то, что даёт сервер.
    """
    out = {}
    for key in config.MODES:
        out[key] = len(_candidate_rows({'mode': key, 'filter': f}))
    return out


def pool_tags(f=None):
    u"""Теги, у которых В ПУЛЕ есть хотя бы один вопрос.

    Показывать тег, по которому ничего не найдётся, — значит обещать выбор,
    которого нет. Считаем по всему пулу (без учёта режима): игрок выбирает
    теги до выбора режима.
    """
    from problems.models import Tag
    used = set()
    for tag_ids in _pool_qs().values_list('tag_ids', flat=True):
        used.update(tag_ids or [])
    if not used:
        return []
    rows = Tag.objects.filter(id__in=used).values_list('id', 'name')
    counts = {}
    for tag_ids in _pool_qs().values_list('tag_ids', flat=True):
        for t in (tag_ids or []):
            counts[t] = counts.get(t, 0) + 1
    return sorted(
        ({'id': pk, 'name': name, 'count': counts.get(pk, 0)}
         for pk, name in rows),
        key=lambda r: (-r['count'], r['name']))


def topic_counts():
    u"""Сколько вопросов в пуле по каждой теме — число рядом с темой в окне."""
    counts = {}
    for topics in _pool_qs().values_list('topics', flat=True):
        for name in (topics or []):
            counts[name] = counts.get(name, 0) + 1
    return counts


@require_GET
def api_pool_counts(request):
    u"""Живые счётчики окна фильтров: «Пуля N · Блиц N · Рапид N · Классика N».

    Клиент зовёт с дебаунсом: считать на каждое нажатие галочки незачем.
    """
    f = parse_filter(request)
    counts = pool_counts_for(f)
    return JsonResponse({
        'counts': counts,
        'total': sum(counts.values()),
        # Режим, у которого под фильтром меньше этого числа, играть нельзя:
        # забег из трёх вопросов — не забег.
        'min_playable': config.MIN_PLAYABLE,
        'unfiltered': is_empty_filter(f),
        'ranked': not is_difficulty_filtered(f),
    })


def escalation_slice(rows, streak):
    """Кандидаты из целевой полосы сложности — МЯГКО.

    rows — [(id, difficulty), ...] уже под пользовательским фильтром
    (он жёсткая рамка, эскалация ходит только внутри неё).

    Полоса задаётся комбо (config.ESCALATION_BANDS). Если в ней пусто,
    полоса РАСШИРЯЕТСЯ на шаг в обе стороны, пока кто-нибудь не найдётся;
    расширять больше нечего — отдаём всё, что есть. Забег из-за эскалации
    кончиться не может: она делает игру интереснее, а не короче.
    """
    if not rows:
        return []
    lo, hi = config.escalation_band(streak)
    while True:
        band = [r for r in rows if lo <= r[1] <= hi]
        if band:
            return band
        if lo <= config.DIFFICULTY_MIN and hi >= config.DIFFICULTY_MAX:
            return rows          # полоса уже во весь диапазон — берём всё
        lo = max(config.DIFFICULTY_MIN, lo - 1)
        hi = min(config.DIFFICULTY_MAX, hi + 1)


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
    return render(request, 'game/game.html', _game_page_context(request))


def _game_page_context(request):
    """Контекст страницы игры. Общий у обычного входа и забега по набору
    (`/game/s/<код>/`): страница одна, набор лишь подставляет очередь.

    ⚠️ Счётчиков у тем и источников на экране НЕТ, и «пустые» сочетания
    фильтров не гасятся — прямое указание Макара: фильтр работает так,
    будто задач по каждой теме и источнику неограниченно. Единственный
    счётчик, который считается по пулу, — пустой ли пул РЕЖИМА: режим без
    единого вопроса на экране не показывается вовсе (играть в него нечем).
    """
    _tc = topic_counts()
    # Сколько ru-вопросов доступно на каждый режим (для карточек на старте).
    type_counts = {}
    for qtype in _pool_qs().values_list('question_type', flat=True):
        type_counts[qtype] = type_counts.get(qtype, 0) + 1
    pool_counts = {key: type_counts.get(m['question_type'], 0)
                   for key, m in config.MODES.items()}

    return {
        'auto_set': None,
        'auto_set_json': 'null',
        # Темы — все канонические, разделами окна фильтров, СО СВОИМИ
        # числами: сколько вопросов пула лежит по каждой. Считает сервер —
        # шаблону нечем складывать словарь с ключом-строкой.
        'topic_groups': [
            {'key': key, 'title': title,
             'topics': [{'name': n, 'count': _tc.get(n, 0)} for n in names]}
            for key, title, names in config.TOPIC_GROUPS],
        'source_groups': [{'key': key, 'title': title}
                          for key, title in game_sources.GROUPS],
        # Теги пула с числами и счётчики тем — для окна фильтров.
        'pool_tags': pool_tags(),
        # Квота зачётных забегов на сегодня — вошедшему. Аноним её не видит:
        # у него зачётных забегов не бывает вовсе.
        'ranked_quota': _quota_line(request),
        # Группы-заготовки: показываются, ТОЛЬКО если у них есть варианты.
        # Серый переключатель, который не нажимается, хуже его отсутствия.
        'feature_options': game_filters.feature_options(),
        'character_options': game_filters.character_options(),
        # «Вопросов из реальных олимпиад» — считаем ТОЛЬКО вопросы банка:
        # сгенерированные тренировочные из олимпиад не приходили, и врать
        # в цифре на первом экране нельзя.
        'pool_total': _pool_qs().filter(is_generated=False).count(),
        # JSON для JS-клиента: механика читается только из config.py
        # Здесь лежат только константы из game/config.py, но правило
        # одно на проект: JSON внутри <script> собирается помощником.
        'config_json': dumps_for_script({
            'modes': {key: _mode_payload(key) for key in config.MODES},
            'default_mode': config.DEFAULT_MODE,
            'pool_counts': pool_counts,
            'economy_version': config.ECONOMY_VERSION,
            'base_by_difficulty': config.BASE_BY_DIFFICULTY,
            'combo_steps': config.COMBO_STEPS,
            'scope_multiplier': config.SCOPE_MULTIPLIER,
            'speed_bonus_max': config.SPEED_BONUS_MAX,
            'accuracy_full_at': config.ACCURACY_FULL_AT,
            'accuracy_floor_at': config.ACCURACY_FLOOR_AT,
            'accuracy_min_mult': config.ACCURACY_MIN_MULT,
            'mistakes_run_size': config.MISTAKES_RUN_SIZE,
            'last_life_multiplier': config.LAST_LIFE_MULTIPLIER,
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
            'min_playable': config.MIN_PLAYABLE,
            'pool_tags': pool_tags(),
            'topic_counts': topic_counts(),
        }),
    }


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
        # ⚠️ `problem_id` СЮДА НЕ ВХОДИТ. По нему задача открывается в
        # каталоге вместе с ответом и решением — то есть ответ можно было
        # посмотреть ДО того, как ответишь. Ссылку «в каталог» клиент
        # собирает из ответа api_answer, когда отвечать уже поздно.
        'generated': gq.is_generated,    # строка «Вопрос сгенерирован ИИ»
    }
    if gq.question_type == 'numeric' and gq.unit:
        # единица измерения («%», «руб.») — подсказка у поля ввода, не ответ
        payload['unit'] = gq.unit
    if gq.question_type == FIGURE_AUDIT:
        # ⚠️ Показанный чертёж — это САМ ВОПРОС, без него играть нечем,
        # поэтому он входит в payload. А вот эталонный чертёж (figure_ref),
        # верный вариант и вид внедрённой ошибки (gen_params['_inject'])
        # сюда не попадают НИКОГДА: по ним ответ вычисляется мгновенно.
        payload['figure'] = gq.figure
        payload['prompt'] = figures_base.QUESTION_PROMPT
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

    rows = [(pk, d) for pk, d, _t in _candidate_rows(state)
            if pk not in seen_run]
    candidates = [pk for pk, _d in escalation_slice(rows, state.get('streak', 0))]
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
    # Момент выдачи — серверными часами. Отсюда считается время ответа.
    state.setdefault('issued_at', {})[str(gq.id)] = time.time()
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
        # ⚠️ {id вопроса: момент выдачи}. Время ответа считает СЕРВЕР, а не
        # клиент: клиентское `elapsed_ms` приходит из браузера игрока и в
        # очки входить не может — его подделывает любой, кто откроет консоль.
        # Клиентское остаётся только для показа в статистике.
        'issued_at': {},
        # Момент старта СЕРВЕРНЫМИ часами. Из него считается длительность
        # забега — по ней ловится «забег на паузе» (см. _rank_run).
        'started_at': time.time(),
        # Сколько секунд забег уже получил прибавкой за верные ответы.
        # Нужно для потолка: без него Классика становится бесконечной.
        'bonus_total': 0,
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

    ⚠️ Панель фильтра НЕ гасит сочетания заранее и не показывает счётчики —
    прямое указание Макара: фильтр работает так, будто задач по каждой теме
    и источнику неограниченно. Но забег из НУЛЯ вопросов не существует
    (решение 2026-07-27): если под режимом или под конкретным фильтром не
    нашлось ни одного вопроса, сессия не создаётся вовсе, и клиент остаётся
    на стартовом экране с честной строкой. Раньше сервер стартовал такой
    забег и сразу сам его завершал причиной `pool_empty` — с точки зрения
    игрока это неотличимо от настоящего конца забега (тот же экран
    результатов, «Вопросы кончились», 0/0, и даже плашка «Чисто!»).
    `pool_empty` остаётся как причина конца ПОСРЕДИ забега, когда вопросы
    уже были и пул под фильтром исчерпался в процессе (см. `_end_reason`).
    """
    mode = request.GET.get('mode', '').strip() or config.DEFAULT_MODE
    if mode not in config.MODES:
        return JsonResponse({'error': 'Неизвестный режим'}, status=400)

    # Режим существует в конфиге, но у него сейчас нет ни одного вопроса —
    # либо погашен своим флагом (сегодня «График» при
    # GAME_FIGURE_ENABLED=False), либо пуст сам по себе. Ни под каким
    # фильтром вопросов не появится — это НЕДОСТИЖИМОСТЬ режима, а не
    # пустой результат конкретного фильтра (см. _mode_enabled).
    if not _mode_enabled(mode):
        return JsonResponse({'ok': False, 'reason': 'mode_unavailable',
                             'error': 'Этот режим пока недоступен'})

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
    if gq is None:
        # Под этим конкретным фильтром вопросов нет — забег не начинается
        # (в отличие от _mode_enabled выше, у режима вопросы ЕСТЬ, просто не
        # под этими темами/источниками/сложностью). Состояние в сессию не
        # пишем — начинать и сразу же хоронить забег незачем.
        return JsonResponse({
            'ok': False, 'reason': 'pool_empty',
            'error': 'Под этими настройками вопросов нет. Измените фильтры'})
    request.session[SESSION_KEY] = state
    return JsonResponse({
        'ok': True,
        'mode': _mode_payload(mode),
        'lives': state['lives'],
        'filter': run_filter,
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

    # boolean / single / figure_audit (везде один выбранный вариант)
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


# ⚠️ ПОЛЯ, КОТОРЫЕ ДОБАВЛЯЕТ УЖЕ `api_session_finish`, А НЕ `build_summary`.
# Сводка — чистая функция журнала и о зачётности знать не может: та решается
# при сохранении результата. Список нужен, чтобы тест «клиент не читает
# несуществующего поля» видел обе половины сводки, а не одну.
FINISH_EXTRA_FIELDS = ('ranked', 'unranked_reason', 'unranked_text',
                       'ranked_today', 'ranked_per_day')


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
    # ⚠️ ТРИ РАЗНЫХ ЧИСЛА, И ПУТАТЬ ИХ НЕЛЬЗЯ. `raw_score` — то, что игрок
    # видел в HUD во время забега (сумма очков за ответы). `accuracy_mult` —
    # множитель за точность. `score` — ИТОГ, он и идёт в рекорд и в таблицу.
    raw = state.get('score', 0)
    acc_mult = scoring.accuracy_multiplier(correct, wrong)
    final = scoring.final_score(raw, correct, wrong)
    return {
        'mode': state['mode'],
        'mode_title': config.MODES[state['mode']]['title'],
        'topic': state.get('topic'),
        'economy_version': config.ECONOMY_VERSION,
        'raw_score': raw,
        'accuracy_mult': round(acc_mult, 3),
        'score': final,
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
    mode_key = state['mode']
    points = 0
    # Эффективная сложность: измеренная, если попыток набралось, иначе
    # хранимая. Пишем в журнал ОБЕ — по хранимой строится разбор, по
    # эффективной начислены очки, и они могут расходиться.
    diff_eff = stats_mod.effective_difficulty(gq)
    # ⚠️ Время ответа — СЕРВЕРНОЕ. Отсутствие метки (старая сессия, ответ
    # на вопрос из прошлого забега) трактуем как «долго»: бонуса нет.
    issued = (state.get('issued_at') or {}).get(str(qid))
    elapsed_server = (time.time() - issued) if issued else None
    # ⚠️ Забег без ЕДИНОГО фильтра получает ×1,3. Проверяем по состоянию, а
    # не по адресу старта: адрес можно подделать, состояние — нет.
    unfiltered = is_empty_filter(state.get('filter'))
    lives_before = state['lives']
    if is_skip:
        # Пропуск безопасен: жизнь цела, комбо цело, время не трогаем.
        result = 'skip'
        delta = mode_cfg['time_skip']
    elif correct:
        result = 'correct'
        state['streak'] += 1
        state['best_streak'] = max(state['best_streak'], state['streak'])
        # Очки считает СЕРВЕР по game/scoring.py, клиент только рисует.
        points = scoring.question_points(
            mode_key, diff_eff, gq.question, elapsed_server,
            state['streak'], lives_before, unfiltered)
        state['score'] += points
        # Прибавка времени — со скидкой за лёгкость и с потолком на забег.
        delta = scoring.time_bonus(mode_key, diff_eff,
                                   state.get('bonus_total', 0))
        state['bonus_total'] = state.get('bonus_total', 0) + delta
    else:
        # Ошибка: минус жизнь и комбо в ноль. Время НЕ трогаем —
        # наказание одно, а не два.
        result = 'wrong'
        delta = mode_cfg['time_wrong']
        state['streak'] = 0
        state['lives'] = max(0, state['lives'] - 1)
    state['wrong_count'] = state.get('wrong_count', 0) + (1 if result == 'wrong' else 0)
    state['skip_count'] = state.get('skip_count', 0) + (1 if result == 'skip' else 0)

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
        # Сложность, по которой НАЧИСЛЕНЫ очки. Может отличаться от
        # хранимой: измеренная перебивает её при STATS_MIN_ATTEMPTS попыток.
        'difficulty_effective': diff_eff,
        'question_type': gq.question_type,
        'outcome': result,
        # Клиентское время — ТОЛЬКО для показа в статистике; в очки идёт
        # серверное (elapsed_server_ms).
        'elapsed_ms': elapsed_ms,
        'elapsed_server_ms': (int(elapsed_server * 1000)
                              if elapsed_server is not None else None),
        'points': points,
        'running_score': state['score'],
        'running_combo': state['streak'],
        'lives_after': state['lives'],
    })
    # Счётчики вопроса — в той же точке, что и журнал: разъехаться им
    # нельзя. Только первая встреча игрока с вопросом (см. _remember_seen):
    # повторный ответ того же человека уже знает правильный вариант.
    if (state.get('first_seen') or {}).get(str(qid)):
        stat = stats_mod.record_answer(gq, result, elapsed_ms)
        # У «Графика» второй счётчик — по ВИДУ внедрённой ошибки: экземпляры
        # у сюжета каждый раз новые, а вид ошибки устойчив, и знать, какая из
        # них чаще обманывает, полезнее средней доли по сюжету.
        stats_mod.record_variant(gq, result, elapsed_ms)
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
    # Ссылка «в каталог» собирается клиентом ОТСЮДА: в payload вопроса
    # `problem_id` нет намеренно (по нему открывалась задача с ответом).
    payload['problem_id'] = gq.problem_id      # None у сгенерированных
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
    # Режим «График»: разбор показывает ДВА чертежа рядом — «как было в
    # решении» (он у клиента уже есть, это сам вопрос) и «как правильно».
    # Эталон уходит только сейчас, после ответа: до ответа он и есть ответ.
    if gq.question_type == FIGURE_AUDIT and gq.figure_ref:
        payload['figure_ref'] = gq.figure_ref
        payload['injected_step'] = (gq.gen_params or {}).get('_step', '')
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


# ---------------------------------------------------------------------------
# Забег по НАБОРУ (вызов дня, набор учителя, дуэль — одна механика)
# ---------------------------------------------------------------------------

ATTEMPTS_KEY = 'econ_rush_sets_played'   # коды сыгранных наборов (сессия)


def played_set_codes(request):
    return request.session.get(ATTEMPTS_KEY) or []


def mark_set_played(request, code):
    codes = played_set_codes(request)
    if code not in codes:
        codes.append(code)
        request.session[ATTEMPTS_KEY] = codes[-200:]


def attempts_used(request, gset):
    """Сколько попыток по набору уже израсходовано этим игроком.

    Авторизованный — считаем по базе (надёжно). Аноним — по сессии и
    localStorage клиента; ⚠️ это заведомо слабая защита, обходится чисткой
    браузера. Так решено сознательно (решение в Notion): требование
    регистрации убило бы публичность игры, ради которой она и делалась.
    """
    if request.user.is_authenticated:
        return GameResult.objects.filter(game_set=gset,
                                         user=request.user).count()
    return 1 if gset.code in played_set_codes(request) else 0


def set_run_allowed(request, gset):
    """(можно ли играть, причина отказа)."""
    now = timezone.now()
    if gset.opens_at and now < gset.opens_at:
        return False, 'Набор ещё не открыт'
    if gset.closes_at and now >= gset.closes_at:
        return False, 'Набор уже закрыт'
    if attempts_used(request, gset) >= gset.attempts_allowed:
        return False, 'Попытка уже использована'
    return True, ''


def start_set_state(request, gset):
    """Состояние забега по набору: очередь = список набора целиком.

    Добор из общего пула ЗАПРЕЩЁН (_pick_from_queue не добирает), значит
    все игроки получат ровно те же вопросы в том же порядке. Вопрос мог
    исчезнуть из кэша (пул пересобрали) — он молча пропускается, забег
    станет короче: это не ошибка, а честное поведение кэша.
    """
    state = _new_state(gset.mode, None, gset.filter_snapshot)
    state['queue'] = list(gset.question_ids or [])
    state['set_code'] = gset.code
    state['curated'] = True     # эскалации сложности тут нет: список задан
    return state


@require_GET
def api_session_start_set(request, code):
    """Начать забег по набору. Код нечувствителен к регистру и пробелам."""
    gset = get_object_or_404(GameSet, code=make_code_lookup(code))
    if gset.mode not in config.MODES:
        return JsonResponse({'error': 'Неизвестный режим набора'}, status=400)
    allowed, why = set_run_allowed(request, gset)
    if not allowed:
        return JsonResponse({'error': why}, status=409)

    state = start_set_state(request, gset)
    gq = _pick_next(request, state)
    if gq is None:
        # Все вопросы набора исчезли из кэша между сборкой очереди и стартом
        # (пул пересобрали) — забег из нуля вопросов не начинается (Задача 3
        # действует и на наборы, не только на свободный выбор режима).
        return JsonResponse({
            'ok': False, 'reason': 'pool_empty',
            'error': 'В этом наборе не осталось доступных вопросов'})
    request.session[SESSION_KEY] = state
    return JsonResponse({
        'ok': True,
        'mode': _mode_payload(gset.mode),
        'lives': state['lives'],
        'filter': normalize_filter(gset.filter_snapshot),
        'set': {'code': gset.code, 'kind': gset.kind, 'title': gset.title,
                'size': gset.size},
        'question': _question_payload(gq, 1),
    })


def make_code_lookup(raw):
    """Код из адреса — в нормальную форму (регистр и пробелы не значат)."""
    from .models import normalize_code
    return normalize_code(raw)


@ensure_csrf_cookie
@require_safe
def set_page(request, code):
    """Страница забега по набору `/game/s/<код>/`.

    Это та же страница игры: набор просто подставляет курированную очередь.
    Отдельного экрана с превью вопросов НЕТ и быть не может — иначе автор
    дуэли увидел бы задания до игры.

    ⚠️ ensure_csrf_cookie обязателен: со страницы уходят POST-ы ответов, и
    без куки они получают 403 (ловилось в браузере — забег молча вставал
    на первом же ответе).
    """
    gset = get_object_or_404(GameSet, code=make_code_lookup(code))
    allowed, why = set_run_allowed(request, gset)
    ctx = _game_page_context(request)
    ctx['auto_set'] = {
        'code': gset.code,
        'kind': gset.kind,
        'title': gset.title or dict(GameSet.KINDS).get(gset.kind, 'Набор'),
        'size': gset.size,
        'mode': gset.mode,
        'mode_title': config.MODES.get(gset.mode, {}).get('title', gset.mode),
        'allowed': allowed,
        'why': why,
        'board_url': reverse('game:set_board', args=[gset.code]),
    }
    # ?auto=1 — начать сразу, без карточки-заставки: так уходит играть
    # автор дуэли, который вопросов ещё не видел (и не должен увидеть).
    ctx['auto_set']['autostart'] = (request.GET.get('auto') == '1'
                                    and allowed)
    ctx['auto_set_json'] = json.dumps(ctx['auto_set'])
    return render(request, 'game/game.html', ctx)


@require_safe
def set_board(request, code):
    """Доска набора: кто прошёл и на каких вопросах посыпался класс.

    ⚠️ Тексты вопросов показываются НЕ ВСЕМ. Доска публичная, и ученик,
    который ещё не играл контрольную, мог бы прочитать её вопросы отсюда —
    это нашёл тест дуэли (первая версия доски выдавала весь список ДО
    игры). Тексты видят: автор набора, персонал и тот, кто уже сыграл.
    Остальным — «Вопрос N»: доля верных остаётся видна, содержание нет.
    """
    gset = get_object_or_404(GameSet, code=make_code_lookup(code))
    if gset.kind == 'duel':
        # У дуэли своя страница, и на ней вопросов нет вовсе.
        return redirect('game:duel', code=gset.code)
    rows = list(gset.results.select_related('user').order_by(
        '-score', 'created_at'))
    board = [{
        'place': i + 1,
        'name': (r.user.username if r.user else 'аноним'),
        'score': r.score,
        'accuracy': r.accuracy,
        'max_combo': r.max_combo,
        'reason': r.ended_reason,
        'at': r.created_at,
        'is_me': bool(request.user.is_authenticated
                      and r.user_id == request.user.id),
    } for i, r in enumerate(rows)]
    show_text = bool(
        request.user.is_authenticated
        and (request.user.is_staff or gset.author_id == request.user.id)
    ) or my_result_for(request, gset) is not None
    return render(request, 'game/set_board.html', {
        'gset': gset,
        'mode_title': config.MODES.get(gset.mode, {}).get('title', gset.mode),
        'board': board,
        'questions': set_question_stats(gset, show_text=show_text),
        'show_text': show_text,
        'play_url': reverse('game:set_page', args=[gset.code]),
    })


def set_question_stats(gset, show_text=True):
    """Разбивка по вопросам НАБОРА — самое ценное для учителя.

    Доля верных считается ВНУТРИ набора (по журналам его забегов), а не по
    всему сайту: учителю важно, на чём посыпался его класс, а не средний
    игрок интернета.

    Журналы забегов лежат в сессиях игроков и до нас не доходят — поэтому
    считаем по сохранённым результатам: у каждого результата есть разбивка
    по вопросам (question_outcomes), которую кладёт finish.

    show_text=False — вместо текста «Вопрос N»: доска публичная, и тому,
    кто набор ещё не играл, содержание вопросов знать рано.
    """
    counts = {}
    for r in gset.results.all():
        for item in (r.question_outcomes or []):
            cell = counts.setdefault(item.get('question_id'),
                                     {'correct': 0, 'wrong': 0, 'skip': 0})
            outcome = item.get('outcome')
            if outcome in cell:
                cell[outcome] += 1
    rows = []
    order = list(gset.question_ids or [])
    texts = dict(GameQuestion.objects.filter(id__in=order)
                 .values_list('id', 'question'))
    for i, qid in enumerate(order):
        cell = counts.get(qid, {'correct': 0, 'wrong': 0, 'skip': 0})
        tries = cell['correct'] + cell['wrong']
        rows.append({
            'number': i + 1,
            'id': qid,
            'text': ((texts.get(qid) or '(вопрос исчез из пула)')[:160]
                     if show_text else 'Вопрос %d' % (i + 1)),
            'correct': cell['correct'],
            'wrong': cell['wrong'],
            'skip': cell['skip'],
            'percent': round(100 * cell['correct'] / tries) if tries else None,
        })
    return rows


# ---------------------------------------------------------------------------
# Асинхронная дуэль по ссылке
# ---------------------------------------------------------------------------

MY_RESULTS_KEY = 'econ_rush_set_results'   # {код набора: код результата}


def remember_my_result(request, set_code, result_code):
    """Запомнить свой результат по набору — чтобы страница дуэли узнала
    анонимного игрока (у авторизованного есть user, у анонима только
    сессия)."""
    mine = request.session.get(MY_RESULTS_KEY) or {}
    mine[set_code] = result_code
    request.session[MY_RESULTS_KEY] = mine


def my_result_for(request, gset):
    """Мой результат по этому набору — или None."""
    if request.user.is_authenticated:
        r = gset.results.filter(user=request.user).first()
        if r:
            return r
    code = (request.session.get(MY_RESULTS_KEY) or {}).get(gset.code)
    return gset.results.filter(code=code).first() if code else None


@require_GET
def duel_new(request):
    """Создать дуэль и СРАЗУ уйти играть.

    ⚠️ Набор дуэли собирается СЛУЧАЙНО под выбранные фильтры, и автор
    вызова НЕ ВИДИТ вопросы до игры: он играет их вслепую первым, наравне
    с соперником. Поэтому экрана «вот твой набор, поехали» не существует —
    ни одна вьюха не отдаёт список вопросов до того, как игрок их сыграл.
    """
    mode = request.GET.get('mode', '').strip() or config.DEFAULT_MODE
    if mode not in config.MODES:
        return JsonResponse({'error': 'Неизвестный режим'}, status=400)
    run_filter = parse_filter(request)
    probe = _new_state(mode, None, run_filter)
    ids = [pk for pk, _d, _t in _candidate_rows(probe)]
    if not ids:
        # Под фильтром пусто — не создаём пустую дуэль, а честно говорим.
        return render(request, 'game/duel_empty.html', {
            'mode_title': config.MODES[mode]['title']}, status=200)
    random.shuffle(ids)
    gset = GameSet.objects.create(
        code=make_result_code(), mode=mode, kind='duel',
        title='Дуэль · %s' % config.MODES[mode]['title'],
        author=request.user if request.user.is_authenticated else None,
        question_ids=ids[:config.DUEL_SIZE],
        filter_snapshot=run_filter, attempts_allowed=1)
    return redirect(reverse('game:set_page', args=[gset.code]) + '?auto=1')


@require_safe
def duel_page(request, code):
    """Страница дуэли `/game/d/<код>/`.

    Соперник видит: кто вызвал, режим, фильтры, число вопросов, результат
    вызвавшего — и кнопку «Играть». ВОПРОСЫ НЕ ПОКАЗЫВАЮТСЯ.

    Ссылку могут открыть больше двух человек — тогда страница показывает
    всех сыгравших доской, автор помечен. Это надмножество сравнения двоих
    и стоит ровно ничего.
    """
    gset = get_object_or_404(GameSet, code=make_code_lookup(code), kind='duel')
    results = list(gset.results.select_related('user').order_by('created_at'))
    mine = my_result_for(request, gset)

    author_result = None
    for r in results:
        if gset.author_id and r.user_id == gset.author_id:
            author_result = r
            break
    if author_result is None and results:
        author_result = results[0]   # аноним-автор: первый сыгравший

    rows = []
    for r in sorted(results, key=lambda x: (-x.score, x.created_at)):
        rows.append({
            'name': (r.user.username if r.user else 'аноним'),
            'score': r.score,
            'accuracy': r.accuracy,
            'max_combo': r.max_combo,
            'reason': r.ended_reason,
            'is_author': author_result is not None and r.id == author_result.id,
            'is_me': mine is not None and r.id == mine.id,
        })

    allowed, why = set_run_allowed(request, gset)
    compare = _duel_compare(gset, author_result, mine) \
        if (mine and author_result and mine.id != author_result.id) else None

    f = normalize_filter(gset.filter_snapshot)
    return render(request, 'game/duel.html', {
        'gset': gset,
        'mode_title': config.MODES.get(gset.mode, {}).get('title', gset.mode),
        'author_name': (gset.author.username if gset.author else 'аноним'),
        'author_result': author_result,
        'rows': rows,
        'mine': mine,
        'compare': compare,
        'allowed': allowed,
        'why': why,
        'play_url': reverse('game:set_page', args=[gset.code]),
        'again_url': (reverse('game:duel_new') + '?mode=' + gset.mode
                      + _filter_query(f)),
        'filter_text': _filter_text(f),
        'page_url': request.build_absolute_uri(
            reverse('game:duel', args=[gset.code])),
    })


def _filter_query(f):
    f = normalize_filter(f)
    parts = ['&topics=' + quote(t) for t in f['topics']]
    parts += ['&tags=%d' % t for t in f['tags']]
    parts += ['&sources=' + quote(s) for s in f['sources']]
    parts += ['&stars=%d' % d for d in f['stars']]
    return ''.join(parts)


def _filter_text(f):
    """Фильтр словами — соперник должен понимать, во что его зовут.

    ⚠️ Нормализуем на входе: в базе лежат снимки фильтров дуэлей и наборов,
    сделанные ДО перехода на множество звёзд (там `dmin`/`dmax`). Упасть на
    чужой старой дуэли — худший из возможных ответов.
    """
    f = normalize_filter(f)
    topics = ', '.join(f['topics']) if f['topics'] else 'все темы'
    if f['sources']:
        sources = ', '.join(game_sources.group_title(s) for s in f['sources'])
    else:
        sources = 'все источники'
    if not f['stars']:
        diff = 'любая сложность'
    else:
        diff = 'сложность ' + ', '.join('%d★' % d for d in f['stars'])
    return '%s · %s · %s' % (topics, sources, diff)


def _duel_compare(gset, a, b):
    """Сравнение двух забегов лоб в лоб: метрики и полоса «кто что взял».

    Полоса строится по question_outcomes: у каждого вопроса набора два
    значка — верно / неверно / пропуск / не дошёл.
    """
    def by_qid(result):
        return {item.get('question_id'): item.get('outcome')
                for item in (result.question_outcomes or [])}

    ma, mb = by_qid(a), by_qid(b)
    strip = []
    for i, qid in enumerate(gset.question_ids or []):
        strip.append({'number': i + 1,
                      'a': ma.get(qid, 'none'),
                      'b': mb.get(qid, 'none')})
    if a.score > b.score:
        verdict = 'Побеждает %s' % (a.user.username if a.user else 'вызвавший')
    elif b.score > a.score:
        verdict = 'Побеждает %s' % (b.user.username if b.user else 'соперник')
    else:
        verdict = 'Ничья'
    return {
        'a': {'name': (a.user.username if a.user else 'вызвавший'),
              'score': a.score, 'accuracy': a.accuracy,
              'max_combo': a.max_combo, 'reason': a.ended_reason},
        'b': {'name': (b.user.username if b.user else 'соперник'),
              'score': b.score, 'accuracy': b.accuracy,
              'max_combo': b.max_combo, 'reason': b.ended_reason},
        'strip': strip,
        'verdict': verdict,
    }


# ---------------------------------------------------------------------------
# Вызов дня
# ---------------------------------------------------------------------------

@require_safe
def daily_page(request):
    """Четыре карточки вызова дня — по одной на режим."""
    from . import daily as daily_mod
    day = daily_mod.today()
    cards = []
    for key, m in config.MODES.items():
        gset = daily_mod.get_daily_set(key, day)
        if gset is None:
            continue     # в пуле нет вопросов этого типа — вызова нет
        mine = None
        if request.user.is_authenticated:
            mine = gset.results.filter(user=request.user).first()
        played = bool(mine) or gset.code in played_set_codes(request)
        cards.append({
            'mode': key,
            'title': m['title'],
            'size': gset.size,
            'code': gset.code,
            'played': played,
            'my_score': mine.score if mine else None,
            'play_url': reverse('game:set_page', args=[gset.code]),
            'board_url': reverse('game:daily_board', args=[key]),
        })
    return render(request, 'game/daily.html', {
        'cards': cards,
        'day': day,
        'reset_at': daily_mod.next_reset().isoformat(),
    })


@require_safe
def daily_board(request, mode, day=None):
    """Доска вызова дня: топ-50 + твоё место, если ты вне топа."""
    from . import daily as daily_mod
    if mode not in config.MODES:
        raise Http404('Неизвестный режим')
    if day:
        try:
            day_obj = datetime.datetime.strptime(day, '%Y-%m-%d').date()
        except ValueError:
            raise Http404('Неверная дата')
    else:
        day_obj = daily_mod.today()
    # Вчерашнюю доску показываем, но задним числом наборы не создаём:
    # архив дальше вчера не требуется, а плодить наборы за прошлое нечестно.
    create = day_obj == daily_mod.today()
    gset = daily_mod.get_daily_set(mode, day_obj, create=create)
    if gset is None:
        raise Http404('Вызова на этот день нет')

    me = request.user if request.user.is_authenticated else None
    top, my_row, total = daily_mod.board_rows(gset, me)
    yesterday = day_obj - datetime.timedelta(days=1)
    return render(request, 'game/daily_board.html', {
        'gset': gset,
        'mode': mode,
        'mode_title': config.MODES[mode]['title'],
        'day': day_obj,
        'is_today': day_obj == daily_mod.today(),
        'top': top,
        'my_row': my_row,
        'total': total,
        'play_url': reverse('game:set_page', args=[gset.code]),
        'yesterday_url': reverse('game:daily_board_day',
                                 args=[mode, yesterday.isoformat()]),
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
    _log_learning_events(request, state)
    # ⚠️ Зачётность добавляем ПОСЛЕ сохранения и ЧИТАЕМ ИЗ БАЗЫ: решает её
    # `_save_result`, и пересчёт здесь завёл бы второй ответ на один вопрос.
    # Имена полей перечислены в FINISH_EXTRA_FIELDS — по этому же списку
    # тест сверяет, что клиент не читает у сводки несуществующего.
    code = state.get('result_code')
    saved = GameResult.objects.filter(code=code).first() if code else None
    summary['ranked'] = bool(saved and saved.ranked)
    summary['unranked_reason'] = saved.unranked_reason if saved else ''
    summary['unranked_text'] = config.UNRANKED_TEXT.get(
        summary['unranked_reason'], '')
    if saved is not None and saved.ranked and saved.user_id:
        summary['ranked_today'] = _ranked_today(saved.user, saved.mode)
        summary['ranked_per_day'] = config.RANKED_RUNS_PER_DAY
    return JsonResponse({'summary': summary, 'share': share})


def _log_learning_events(request, state):
    """Учебные события по завершённому забегу — по одному на вопрос.

    Пишем ОДИН раз, в момент завершения, а не на каждый ответ: журнал забега
    и так лежит целиком в сессии, а сорок отдельных вставок посреди игры
    добавили бы задержку туда, где меряют секунды.

    Игра работает без входа, поэтому у анонимной партии `user=None`, а
    привязка идёт по ключу сессии (команда link_anonymous_events свяжет её
    с аккаунтом позже). Запись неблокирующая: сломанный лог не должен
    отнимать у игрока результат забега.
    """
    from problems.event_log import log_event

    OUTCOME_TO_EVENT = {
        'correct': 'solved',
        'wrong': 'failed',
        'skip': 'skipped',
    }
    log = state.get('log') or []
    if not log or state.get('events_logged'):
        return
    state['events_logged'] = True
    request.session[SESSION_KEY] = state

    try:
        from problems.models import Topic
        # Темы в журнале лежат ИМЕНАМИ (денормализованы в GameQuestion).
        # Достаём их одним запросом, а не по одному на вопрос.
        names = {t for entry in log for t in (entry.get('topics') or [])}
        by_name = {t.name: t for t in Topic.objects.filter(name__in=names)}
    except Exception:
        by_name = {}

    user = request.user if request.user.is_authenticated else None
    for entry in log:
        topics = entry.get('topics') or []
        elapsed = entry.get('elapsed_ms') or 0
        log_event(
            'game', OUTCOME_TO_EVENT.get(entry.get('outcome'), 'attempted'),
            user=user, request=request,
            topic=by_name.get(topics[0]) if topics else None,
            difficulty=entry.get('difficulty'),
            time_spent_seconds=int(elapsed / 1000) if elapsed else None,
            payload={
                'mode': state.get('mode'),
                'question_id': entry.get('question_id'),
                'number': entry.get('number'),
                'question_type': entry.get('question_type'),
                'running_combo': entry.get('running_combo'),
            },
        )

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


def _quota_line(request):
    u"""Строка «Зачётных забегов сегодня: 7 из 10» — или пусто анониму.

    Считается по режиму по умолчанию: на стартовом экране режим ещё не
    выбран, а показывать четыре строки ради одной цифры незачем.
    """
    if not request.user.is_authenticated:
        return ''
    used = _ranked_today(request.user, config.DEFAULT_MODE)
    return 'Зачётных забегов сегодня: %d из %d' % (
        min(used, config.RANKED_RUNS_PER_DAY), config.RANKED_RUNS_PER_DAY)


def _moscow_day(when=None):
    u"""Календарный день по Москве.

    ⚠️ Квота считается по МОСКОВСКИМ суткам, а не по UTC. Сервер живёт в
    Москве, игроки тоже; по UTC «сегодня» кончалось бы в три часа ночи, и
    человек, играющий вечером, получал бы два дневных лимита подряд.
    """
    from zoneinfo import ZoneInfo
    when = when or timezone.now()
    return when.astimezone(ZoneInfo('Europe/Moscow')).date()


def _ranked_today(user, mode):
    u"""Сколько ЗАЧЁТНЫХ забегов режима человек уже сыграл сегодня.

    Считаем по самим результатам — отдельной таблицы счётчиков не заводим:
    она немедленно разошлась бы с фактом при любой правке или откате.
    """
    from zoneinfo import ZoneInfo
    msk = ZoneInfo('Europe/Moscow')
    today = _moscow_day()
    start = datetime.datetime.combine(today, datetime.time.min, tzinfo=msk)
    end = start + datetime.timedelta(days=1)
    return GameResult.objects.filter(
        user=user, mode=mode, ranked=True,
        created_at__gte=start, created_at__lt=end).count()


def _rank_run(request, state, summary, wall_ms):
    u"""Идёт ли забег в таблицу, и если нет — почему.

    ⚠️ РЕШАЕТСЯ ОДИН РАЗ, ПРИ СОХРАНЕНИИ. Причина пишется полем, а не
    вычисляется на лету: иначе смена правил задним числом переписывала бы
    чужие рекорды.

    Порядок проверок — из `config.UNRANKED_REASONS`, сверху вниз: игроку
    показывается ПЕРВАЯ сработавшая, самая понятная.
    """
    user = request.user if request.user.is_authenticated else None
    if user is None:
        return False, 'anonymous'
    if state.get('mistakes_run'):
        return False, 'mistakes_run'
    if state.get('set_code'):
        return False, 'set_run'
    if is_difficulty_filtered(state.get('filter')):
        return False, 'difficulty_filter'
    if summary['correct'] < config.RANKED_MIN_CORRECT:
        return False, 'too_few_correct'
    # ⚠️ ПОТОЛОК ДЛИТЕЛЬНОСТИ. Забег не может идти дольше, чем запас режима
    # плюс вся возможная прибавка за верные ответы, плюс минута на сетевые
    # задержки. Больше — значит вкладку держали на паузе или подкручивали
    # клиентский таймер: очки-то считает сервер, а вот времени на подумать
    # так можно взять сколько угодно.
    limit_ms = int((config.MODES[state['mode']]['duration']
                    * (1 + config.TIME_BONUS_CAP_FACTOR) + 60) * 1000)
    if wall_ms is not None and wall_ms > limit_ms:
        return False, 'time_overrun'
    if _ranked_today(user, state['mode']) >= config.RANKED_RUNS_PER_DAY:
        return False, 'quota_exceeded'
    return True, ''


def _save_result(request, state, summary):
    """Сохранить результат забега и отдать ссылку на публичную страницу.

    Ссылка АБСОЛЮТНАЯ (build_absolute_uri): её вставляют в Telegram и VK,
    а относительный путь там просто не откроется.

    Идемпотентность: код забега запоминается в состоянии, повторный вызов
    finish отдаёт ту же строку, а не плодит новые.
    """
    code = state.get('result_code')
    result = GameResult.objects.filter(code=code).first() if code else None
    # Забег по набору попадает на его доску. Попытка засчитывается ровно
    # здесь, при сохранении результата: начатый и брошенный забег попытку
    # не тратит.
    gset = None
    if state.get('set_code'):
        gset = GameSet.objects.filter(code=state['set_code']).first()

    # ⚠️ Средним считаем СЕРВЕРНОЕ время верных ответов. Клиентское приходит
    # из браузера игрока и в доску «Скорость» не пускается — её выиграл бы
    # тот, кто первым откроет консоль.
    server_ms = [r['elapsed_server_ms'] for r in (state.get('log') or [])
                 if r['outcome'] == 'correct' and r.get('elapsed_server_ms')]
    avg_correct_ms = int(sum(server_ms) / len(server_ms)) if server_ms else None
    started = state.get('started_at')
    wall_ms = int((time.time() - started) * 1000) if started else None
    ranked, unranked_reason = _rank_run(request, state, summary, wall_ms)

    if result is None:
        for _ in range(5):   # коллизия кода почти невероятна, но не 500
            try:
                result = GameResult.objects.create(
                    code=make_result_code(),
                    mode=state['mode'],
                    score=summary['score'],
                    raw_score=summary.get('raw_score', summary['score']),
                    accuracy_mult=summary.get('accuracy_mult', 1.0),
                    economy_version=config.ECONOMY_VERSION,
                    correct_count=summary['correct'],
                    total_count=summary['total'],
                    wrong_count=summary['wrong'],
                    skip_count=summary['skipped'],
                    avg_correct_ms=avg_correct_ms,
                    wall_ms=wall_ms,
                    filters=normalize_filter(state.get('filter')),
                    is_unfiltered=is_empty_filter(state.get('filter')),
                    ranked=ranked,
                    unranked_reason=unranked_reason,
                    max_combo=summary['max_multiplier'],
                    ended_reason=summary['ended_reason'],
                    topic_breakdown=summary['topic_rows'],
                    difficulty_breakdown=summary['difficulty'],
                    score_curve=summary['score_curve'],
                    question_outcomes=[
                        {'question_id': r['question_id'],
                         'number': r['number'],
                         'outcome': r['outcome']}
                        for r in (state.get('log') or [])],
                    game_set=gset,
                    user=request.user if request.user.is_authenticated else None,
                )
                break
            except IntegrityError:
                continue
        if result is None:
            return None      # не смогли сохранить — забег важнее ссылки
        state['result_code'] = result.code
        request.session[SESSION_KEY] = state
        if gset is not None:
            mark_set_played(request, gset.code)
            remember_my_result(request, gset.code, result.code)
    out = {
        'code': result.code,
        'url': request.build_absolute_uri(
            reverse('game:result', args=[result.code])),
    }
    if gset is not None:
        # У дуэли «доска» — это её страница сравнения, а не общая доска
        # набора: соперника интересует счёт лоб в лоб.
        board = reverse('game:duel', args=[gset.code]) if gset.kind == 'duel' \
            else reverse('game:set_board', args=[gset.code])
        out['set'] = {
            'code': gset.code,
            'kind': gset.kind,
            'title': gset.title,
            'board_url': request.build_absolute_uri(board),
        }
    return out


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
        'og_title': f'{result.score} очков в Wecon Rush – обгонишь?',
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
