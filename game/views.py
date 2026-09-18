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
import logging
import random
import re
import time
from fractions import Fraction
from urllib.parse import quote

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
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
from problems.models import Problem
from problems.management.commands.apply_topic_mapping import CANONICAL
from . import sources as game_sources
from .sources import GROUP_KEYS
from .models import (ArchetypeStat, GameQuestion, GameResult, GameSet,
                     make_result_code)
from . import (config, daily as daily_mod, filters as game_filters,
               leaderboard as lb, scoring, state as run_state,
               stats as stats_mod)
from .figures import base as figures_base
from .figures.base import QUESTION_TYPE as FIGURE_AUDIT

# ⚠️ СОСТОЯНИЕ ЗАБЕГА БОЛЬШЕ НЕ В СЕССИИ. Оно живёт в кэше под своим
# `run_id` (game/state.py): дуэли в реальном времени нужен счёт
# соперника, а состояние соперника лежало бы в ЕГО куке и до сервера
# не доходило. Имя ниже осталось ради ОДНОГО релиза совместимости —
# забег, начатый до выкатки, доигрывается (state._legacy).
logger = logging.getLogger(__name__)

SESSION_KEY = run_state.LEGACY_SESSION_KEY
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
    # Состояние текста задачи-источника (чистка корпуса 03.09.2026). Пул —
    # КЭШ: он пересобирается командой build_game_pool, и между пересборками
    # содержит вопросы по задачам, чей текст с тех пор признали битым.
    # Фильтр стоит и здесь, и на сборке: у сгенерированных вопросов задачи
    # нет вовсе (problem is NULL), и их exclude не задевает.
    qs = qs.exclude(problem__content_status__in=(
        Problem.ContentStatus.NEEDS_FIX, Problem.ContentStatus.JUNK))
    return qs


def _mode_enabled(mode):
    """Есть ли у режима вообще вопросы в пуле — БЕЗ учёта фильтра забега.

    Отличает две разные пустоты, которые раньше были слиты в одну
    (`pool_empty`): режим, выключенный флагом (сегодня — «График» при
    `GAME_FIGURE_ENABLED=False`), не наберёт вопросов ни под каким
    фильтром — это НЕДОСТИЖИМОСТЬ режима. Пустой пул ПОД ФИЛЬТРОМ у
    режима, у которого вопросы вообще есть, — другая вещь (см.
    `_candidate_rows` в `api_session_start`)."""
    if mode == config.PRACTICE['key']:
        return any(_mode_enabled(key) for key in config.practice_modes())
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

    ⚠️ ДЛИНА УСЛОВИЯ РЕЖЕТСЯ ЗДЕСЬ, А НЕ В ПУЛЕ. У Пули на вопрос уходят
    секунды, у Классики — минута, и один порог на всех отсекал бы либо
    слишком много, либо слишком мало (config.MODE_MAX_CHARS). Сборщик пула
    считает длину чуть иначе — таблицу как плейсхолдер (reading_length), —
    и здесь длинная таблица честно засчитывается целиком: на замере это
    разошлось у 2 вопросов из 10 076, и всегда в СТРОГУЮ сторону.
    """
    if state['mode'] == config.PRACTICE['key']:
        # «Бесконечные тесты» — кандидаты режимов их типов вместе, с порогами
        # длины этих режимов: тогда счётчик практики ровно сумма их счётчиков,
        # и экран не обещает больше, чем даст выдача.
        out = []
        for key in config.practice_modes():
            out.extend(_candidate_rows(dict(state, mode=key)))
        return out
    f = normalize_filter(state.get('filter'))
    mode = state['mode']
    qtype = config.MODES[mode]['question_type']
    max_chars = config.MODE_MAX_CHARS.get(mode)
    bank_map, arch_map = stats_mod.difficulty_overrides()
    rows = _pool_qs().filter(question_type=qtype).values_list(
        'id', 'topics', 'source_group', 'difficulty',
        'problem_id', 'part_id', 'generator_key', 'tag_ids', 'question')
    out = []
    for (pk, topics, group, difficulty, problem_id, part_id, gen_key,
         tag_ids, question) in rows:
        if max_chars is not None and len(question or '') > max_chars:
            continue
        if problem_id is not None:
            difficulty = bank_map.get((problem_id, part_id), difficulty)
        elif gen_key:
            difficulty = arch_map.get(gen_key, difficulty)
        if _filter_matches(f, topics, group, difficulty, tag_ids):
            out.append((pk, difficulty, topics or [], bool(gen_key)))
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

    ⚠️ ТОЛЬКО КАНОНИЧЕСКИЕ (18.09.2026), как в фильтре каталога: legacy-теги,
    убранные из каталога 17.09, в окне игры не показываются. Данные пула не
    трогаются — вопрос с legacy-тегом по-прежнему считается по своей теме
    (`pool_counts_for` этой правкой не задет).

    `topics` — темы вопросов с этим тегом: окно показывает «теги выбранных
    тем», как каталог.
    """
    from problems.models import Tag
    counts, topics_of = {}, {}
    for tag_ids, topics in _pool_qs().values_list('tag_ids', 'topics'):
        for t in (tag_ids or []):
            counts[t] = counts.get(t, 0) + 1
            topics_of.setdefault(t, set()).update(topics or [])
    if not counts:
        return []
    rows = Tag.objects.filter(id__in=counts, kind='canonical').values_list('id', 'name')
    return sorted(
        ({'id': pk, 'name': name, 'count': counts[pk], 'topics': sorted(topics_of[pk])}
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
def api_leaderboard(request):
    u"""Доска лидеров: топ-20 плюс строка «я».

    ⚠️ ЭНДПОИНТ ПУБЛИЧНЫЙ ОСОЗНАННО. Таблицу видно всем, включая анонимов, —
    в этом её смысл (решение владельца). Наружу уходит ровно то, что доска
    и обещает: имя, значение, дата. Внутренних идентификаторов, почты и
    любых других полей профиля в выдаче НЕТ.
    """
    mode = request.GET.get('mode') or config.DEFAULT_MODE
    if mode not in config.MODES:
        mode = config.DEFAULT_MODE
    period = request.GET.get('period')
    period = period if period in lb.PERIODS else 'all'
    metric = request.GET.get('metric')
    metric = metric if metric in lb.METRICS else 'score'
    user = request.user if request.user.is_authenticated else None
    return JsonResponse({
        'mode': mode, 'period': period, 'metric': metric,
        # ⚠️ Пометка «это я» ставится ПОСЛЕ кэша: сами строки общие на всех.
        'rows': lb.mark_me(lb.top(mode, period, metric), user),
        # ⚠️ Строка «я» считается живым запросом и в кэш не кладётся: попади
        # она в общий ключ — один игрок увидел бы чужое место как своё.
        'me': lb.my_row(user, mode, period, metric),
        'total_players': lb.total_players(mode, period, metric),
        'generated_at': timezone.now().isoformat(timespec='seconds'),
    })


@login_required
@require_GET
def api_my_stats(request):
    u"""Личная статистика игрока. ВИДНА ТОЛЬКО ЕМУ САМОМУ.

    ⚠️ ПОЛЬЗОВАТЕЛЬ БЕРЁТСЯ ИЗ `request.user` И БОЛЬШЕ НИОТКУДА. Параметра
    «чей» здесь нет и не будет: он немедленно превратил бы личную статистику
    в публичную по перебору номеров. Аноним сюда не проходит вовсе.
    """
    mode = request.GET.get('mode') or config.DEFAULT_MODE
    if mode not in config.MODES:
        mode = config.DEFAULT_MODE
    # ⚠️ ПАНЕЛЬ «МОИ РЕКОРДЫ» ЖИВЁТ ЗДЕСЬ, А НЕ В СВОЁМ ЭНДПОИНТЕ
    # (08.09.2026). Это ровно «личная статистика, только про себя», и
    # граница у неё та же самая — она уже описана в этой вьюхе и закрыта
    # тестами `MyStatsBoundaryTests`. Второй эндпоинт означал бы второе
    # место, где ту же границу надо не забыть удержать. (Отдельный
    # `api_my_history` существует по другой причине: он про ОДИН режим и
    # про порядок последних забегов — его зовёт экран результата.)
    #
    # `panel_mode` может быть 'all': панель умеет показывать все режимы
    # сразу, а `stats` — нет, счёт Пули и Классики несравним.
    panel_mode = request.GET.get('panel_mode') or mode
    if panel_mode != 'all' and panel_mode not in config.MODES:
        panel_mode = mode
    return JsonResponse({
        'mode': mode,
        'stats': lb.personal_stats(request.user, mode),
        # ⚠️ Дуэли считаются по НАБОРАМ и результатам, новых таблиц нет:
        # вторая таблица разъехалась бы с фактом при первом же удалении
        # забега руками (тот же довод, что у лидерборда, ADR 0056).
        'duels': lb.duel_stats(request.user),
        'panel': lb.records_panel(request.user, panel_mode),
    })


@require_GET
def api_my_history(request):
    u"""История забегов игрока в режиме. ВИДНА ТОЛЬКО ЕМУ САМОМУ.

    ⚠️ ПОЛЬЗОВАТЕЛЬ БЕРЁТСЯ ИЗ `request.user` И БОЛЬШЕ НИОТКУДА. Параметра
    «чей» здесь нет и не будет — то же правило, что у `api_my_stats`: он
    немедленно превратил бы личную историю в публичную по перебору номеров.

    ⚠️ ИСТОРИЯ ПЕРЕЕХАЛА С localStorage НА СЕРВЕР (08.09.2026). Прежний
    ключ `econ_rush_history` жил в браузере: рекорды и история терялись при
    смене браузера, а два источника истории разъехались бы при первом же
    расхождении. Источник теперь один — `GameResult`.

    ⚠️ АНОНИМУ ОТВЕЧАЕМ 403, А НЕ РЕДИРЕКТОМ НА ВХОД. Эндпоинт зовёт
    fetch, и редирект вернул бы ему HTML страницы входа: клиент получил бы
    200 и мусор вместо JSON. Экран в этом случае показывает графики без
    сравнения, а не выдуманные числа.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Только для вошедших'}, status=403)
    mode = request.GET.get('mode') or config.DEFAULT_MODE
    if mode not in config.MODES:
        mode = config.DEFAULT_MODE
    return JsonResponse(lb.run_history(request.user, mode))


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
        # «Бесконечные тесты»: сумма режимов их типов — ровно столько даст выдача.
        'practice': sum(counts[key] for key in config.practice_modes()),
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


def _practice_payload():
    """«Бесконечные тесты» для клиента: времени и жизней у практики нет вовсе."""
    return {'key': config.PRACTICE['key'], 'title': config.PRACTICE['title'],
            'question_types': list(config.PRACTICE['question_types']), 'practice': True}


def _choice_numbers(indices):
    u"""Номера вариантов словами игрока: [0, 2] → «1, 3»."""
    return ', '.join(str(i + 1) for i in sorted(indices))


def practice_summary(state):
    u"""Итог «Бесконечных тестов» (решение владельца 17.09.2026, ADR 0114).

    Числа: отвечено (верные и ошибки, без пропусков), верных, ошибок, пропущено,
    точность. `mistakes` — ошибки и пропуски по порядку открытия: текст, тема,
    ответ игрока и верный ответ номерами вариантов, `problem_id` и решение
    (есть только у сгенерированного). `topics` — по образцу `topic_rows` итога
    раунда: верно / ошибка / пропуск на тему.

    ⚠️ Пропуск, на который потом ответили, пропуском не считается: в журнале
    один исход на вопрос — последний (`_practice_answer`).
    """
    outcomes = list((state.get('answered') or {}).values())
    correct = outcomes.count('correct')
    wrong = outcomes.count('wrong')
    answered = correct + wrong
    log = sorted(state.get('log') or [], key=lambda e: e.get('number') or 0)
    missed = [e for e in log if e.get('outcome') in ('wrong', 'skip')]
    questions = (GameQuestion.objects.in_bulk([e['question_id'] for e in missed])
                 if missed else {})
    mistakes = []
    for e in missed:
        gq = questions.get(e['question_id'])
        right = []
        if gq is not None:
            right = (gq.correct_indices or []) if gq.question_type == 'multi' else [gq.correct_index]
        mistakes.append({
            'number': e.get('number'),
            'outcome': e['outcome'],
            'question_id': e['question_id'],
            'text': gq.question if gq is not None else '(вопрос исчез из пула)',
            'topic': (e.get('topics') or [NO_TOPIC])[0],
            'your': _choice_numbers(e.get('chosen') or []),
            'right': _choice_numbers(right),
            'problem_id': gq.problem_id if gq is not None else None,
            'solution': (gq.gen_solution if gq is not None and gq.is_generated
                         and gq.gen_solution else ''),
        })
    topics = {}
    for e in log:
        for name in (e.get('topics') or [NO_TOPIC]):
            cell = topics.setdefault(name, {'topic': name, 'correct': 0, 'wrong': 0, 'skip': 0})
            if e.get('outcome') in cell:
                cell[e['outcome']] += 1
    topic_rows = []
    for cell in topics.values():
        cell['total'] = cell['correct'] + cell['wrong'] + cell['skip']
        topic_rows.append(cell)
    topic_rows.sort(key=lambda t: (-t['total'], t['topic']))
    return {'answered': answered, 'correct': correct, 'wrong': wrong,
            'skipped': outcomes.count('skip'),
            'accuracy': round(100 * correct / answered) if answered else 0,
            'mistakes': mistakes, 'topics': topic_rows}


def _practice_answer(request, state, gq, is_skip, correct, body):
    u"""Ответ в «Бесконечных тестах» (решение владельца 15.09.2026).

    Ни очков, ни времени, ни жизней: только исход — для сводки и подсветки.
    ⚠️ `correct_choices` ОТДАЁТСЯ ТОЛЬКО ЗДЕСЬ: в раунде верный вариант
    приходит своими полями по типу вопроса. ⚠️ Статистику вопроса практика НЕ
    пишет: ответ без часов, и доля верных вместе с ним стала бы легче, чем в
    раунде, по которому считается измеренная сложность.

    ⚠️ ПРОПУСК ОБРАТИМ (решение 17.09.2026): на пропущенный вопрос можно
    ответить позже, и в журнале остаётся ОДИН исход на вопрос — последний.
    Выбранные варианты и темы лежат в записи журнала: по ним итог строит
    список ошибок и точность по темам, не спрашивая клиента.
    """
    result = 'skip' if is_skip else ('correct' if correct else 'wrong')
    state['answered'][str(gq.id)] = result
    if is_skip:
        chosen = []
    elif gq.question_type == 'multi':
        chosen = sorted(body.get('choices') or [])
    else:
        chosen = [body.get('choice')]
    entry = {'question_id': gq.id, 'number': state['seen'].index(gq.id) + 1,
             'question_type': gq.question_type, 'outcome': result,
             'chosen': chosen, 'topics': list(gq.topics or [])}
    state['log'] = [e for e in state['log'] if e.get('question_id') != gq.id] + [entry]
    run_state.save_run(request, state)
    payload = {'result': result, 'correct': correct, 'practice': True}
    # ⚠️ ВЕРНЫЙ ОТВЕТ, ЗАДАЧА И РЕШЕНИЕ — ТОЛЬКО С ОТВЕТОМ, НЕ С ПРОПУСКОМ. Пропуск
    # обратим: пришли они с пропуском — вернуться и «ответить» мог бы любой.
    if not is_skip:
        payload['correct_choices'] = (list(gq.correct_indices or []) if gq.question_type == 'multi'
                                      else [gq.correct_index])
        payload['problem_id'] = gq.problem_id
        if gq.is_generated and gq.gen_solution:
            payload['solution'] = gq.gen_solution
    return JsonResponse(payload)


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
    # Сколько ru-вопросов доступно на каждый режим (для вкладок на старте).
    type_counts = {}
    for qtype in _pool_qs().values_list('question_type', flat=True):
        type_counts[qtype] = type_counts.get(qtype, 0) + 1
    pool_counts = {key: type_counts.get(m['question_type'], 0)
                   for key, m in config.MODES.items()}
    user = request.user if request.user.is_authenticated else None
    # Ячейка «Вызов дня» на главной (решение владельца 17.09.2026): вызовов
    # столько, сколько режимов с непустым пулом, — ровно столько карточек
    # рисует `/game/daily/` (режим без вопросов вызова не получает).
    daily_cell = daily_mod.daily_cell(user)
    daily_cell['total'] = sum(1 for key in config.MODES if pool_counts[key])

    return {
        'auto_set': None,
        'auto_set_json': 'null',
        # ⚠️ КАРТОЧКА ССЫЛКИ НУЖНА И СТАРТОВОМУ ЭКРАНУ, а не только странице
        # результата. Ссылкой на сам тренажёр делятся чаще, чем ссылкой на
        # чужой забег, и без og:image мессенджер показывал голый адрес.
        # Картинка одна и та же (game/static/game/og_default.png), рисует её
        # `make_og_image`.
        'og_image': request.build_absolute_uri(static('game/og_default.png')),
        'og_title': 'Wecon Rush · игра на скорость по экономике',
        'og_description': ('Три жизни, четыре режима, вопросы из реальных '
                           'олимпиад. Сколько наберёшь?'),
        'page_url': request.build_absolute_uri(),
        # Панель прослушивания звука — служебная: только staff и только по
        # явному ?sound_check=1. Обычному игроку блока нет в разметке вовсе.
        'sound_check': (request.GET.get('sound_check') == '1'
                        and request.user.is_authenticated
                        and request.user.is_staff),
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
        'ranked_quota': _quota_payload(request),
        'daily_cell': daily_cell,
        # Вкладки режимов стартового экрана (ADR 0108): режим без единого
        # вопроса не рисуется вовсе. Подпись времени — как у клиента
        # (`durationText`), числа под фильтром клиент обновит сам.
        'start_modes': [
            {'key': key, 'title': m['title'], 'pool': pool_counts[key],
             'duration': duration_text(m['duration'])}
            for key, m in config.MODES.items() if pool_counts[key]],
        # Числа поповера «Как считаются очки» — из конфига, а не текстом:
        # поменяют экономику, и поповер не соврёт.
        'score_rules': {
            'base_min': min(config.BASE_BY_DIFFICULTY.values()),
            'base_max': max(config.BASE_BY_DIFFICULTY.values()),
            'scope': ('%g' % config.SCOPE_MULTIPLIER).replace('.', ','),
            'accuracy_full_pct': int(round(config.ACCURACY_FULL_AT * 100)),
        },
        # Группы-заготовки: показываются, ТОЛЬКО если у них есть варианты.
        # Серый переключатель, который не нажимается, хуже его отсутствия.
        'feature_options': game_filters.feature_options(),
        'character_options': game_filters.character_options(),
        # JSON для JS-клиента: механика читается только из config.py
        # Здесь лежат только константы из game/config.py, но правило
        # одно на проект: JSON внутри <script> собирается помощником.
        'config_json': dumps_for_script({
            'modes': {key: _mode_payload(key) for key in config.MODES},
            'default_mode': config.DEFAULT_MODE,
            'pool_counts': pool_counts,
            # «Бесконечные тесты»: полоса на старте. Число — весь пул их типов;
            # под фильтром его обновляет refreshCounts (api_pool_counts).
            'practice': {'title': config.PRACTICE['title'],
                         'count': sum(pool_counts[key] for key in config.practice_modes())},
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
            # Разбор ошибки и отсчёт перед стартом (ADR 0109): числа — только
            # из конфига, клиент их не выдумывает.
            'reveal_wrong_ms': config.REVEAL_WRONG_MS,
            'round_countdown_s': config.ROUND_COUNTDOWN_S,
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
            # ⚠️ ПЕРВАЯ ВКЛАДКА ДОСКИ ЕДЕТ ВМЕСТЕ СО СТРАНИЦЕЙ. Иначе экран
            # показывает пустую таблицу и через полсекунды дёргается — а
            # доска стоит на первом экране, это первое, что видит человек.
            'leaderboard': {
                'mode': config.DEFAULT_MODE, 'period': 'all',
                'metric': 'score',
                'rows': lb.mark_me(
                    lb.top(config.DEFAULT_MODE, 'all', 'score'),
                    request.user if request.user.is_authenticated else None),
                'me': lb.my_row(
                    request.user if request.user.is_authenticated else None,
                    config.DEFAULT_MODE, 'all', 'score'),
                'total_players': lb.total_players(config.DEFAULT_MODE, 'all',
                                                  'score'),
            },
            # Вошёл ли человек. С 08.09.2026 этим живёт ещё и правая
            # карточка табло: анониму она говорит «войдите, чтобы рекорды
            # сохранялись», а вошедшему без рекорда — «первый раунд в этом
            # режиме». Два разных факта, и выдуманного числа нет ни в одном.
            'is_authenticated': request.user.is_authenticated,
            'pool_tags': pool_tags(),
            'topic_counts': topic_counts(),
            # Стартовый экран (ADR 0108): квота зачётных по режимам и серверные
            # рекорды вошедшего. Аноним получает None и {}: его рекорды живут
            # в localStorage этого устройства.
            'ranked_quota': _quota_payload(request),
            'my_best': lb.best_scores(user) if user else {},
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
        # Сложность над карточкой вопроса (ADR 0110): «сложность 3 из 5» и
        # «очков за верный – до N». Та же эффективная сложность, по которой
        # сервер начислит очки; ответа она не выдаёт.
        'difficulty': stats_mod.effective_difficulty(gq),
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


def _cap_generated(state, band):
    u"""Отсечь сгенерированные, если их доля в забеге уже дошла до потолка.

    band — [(id, difficulty, сгенерирован), ...]. Правило простое: очередной
    вопрос может быть машинным, только если ПОСЛЕ него доля не превысит
    config.GENERATED_SHARE_MAX. При потолке 0,25 это «не чаще одного из
    четырёх», и первый вопрос забега всегда из банка.

    ⚠️ Потолок ОТСТУПАЕТ, если банковских кандидатов не осталось: иначе
    забег кончался бы не по жизням и не по времени, а по квоте, и игрок не
    понял бы почему. По той же причине правило не касается «Графика»: там
    все вопросы сгенерированы по устройству.
    """
    if config.MODES.get(state['mode'], {}).get('question_type') == FIGURE_AUDIT:
        return band
    served = len(state.get('seen') or [])
    gen_served = int(state.get('generated_served') or 0)
    if gen_served + 1 <= config.GENERATED_SHARE_MAX * (served + 1):
        return band
    from_bank = [r for r in band if not r[2]]
    return from_bank or band


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

    rows = [(pk, d, gen) for pk, d, _t, gen in _candidate_rows(state)
            if pk not in seen_run]
    # В практике серии нет: эскалация по комбо держала бы её на лёгких вечно.
    band = rows if state.get('practice') else escalation_slice(rows, state.get('streak', 0))
    candidates = [pk for pk, _d, _g in _cap_generated(state, band)]
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
    # Счётчик машинных вопросов забега — им живёт потолок доли
    # (config.GENERATED_SHARE_MAX, см. _cap_generated).
    if gq.is_generated:
        state['generated_served'] = int(state.get('generated_served') or 0) + 1
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
    practice = mode == config.PRACTICE['key']
    return {
        # ⚠️ У КАЖДОГО ЗАБЕГА СВОЙ ИДЕНТИФИКАТОР, а не один на сессию.
        # Дуэль адресует чужой забег по нему (state.load_by_id), и если бы
        # id переиспользовался, «сыграть ещё раз» подменяло бы соперника
        # табло уже другого забега.
        'run_id': run_state.new_run_id(),
        'mode': mode,
        'topic': topic,
        # Фильтр забега живёт в состоянии, а не только в URL старта: его
        # НАСЛЕДУЮТ «сыграть ещё раз» и «работа над ошибками». Раньше они
        # сбрасывали выбор игрока молча.
        'filter': normalize_filter(run_filter),
        'seen': [],
        'answered': {},
        # «Бесконечные тесты» (решение 15.09.2026): без времени, жизней и очков.
        'practice': practice,
        'duration': None if practice else config.MODES[mode]['duration'],
        'lives': None if practice else config.MODES[mode]['lives'],
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
        # Паузы раунда СЕРВЕРНЫМИ часами: [[начало_мс, конец_мс|None], …].
        # Окно поверх раунда ставит его на паузу; зачтённая пауза вычитается
        # из длительности в `_rank_run` (см. «Пауза раунда»).
        'pauses': [],
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
    practice = mode == config.PRACTICE['key']
    if mode not in config.MODES and not practice:
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
    run_state.save_run(request, state)
    return JsonResponse({
        'ok': True,
        'mode': _practice_payload() if practice else _mode_payload(mode),
        'lives': state['lives'],
        'filter': run_filter,
        'question': _question_payload(gq, 1),
        # ⚠️ ЛИЧНЫЙ РЕКОРД ОТДАЁТСЯ ВМЕСТЕ СО СТАРТОМ, А НЕ ОТДЕЛЬНЫМ
        # ЗАПРОСОМ. Правая карточка табло нужна ровно в тот момент, когда
        # забег начинается: вторым запросом она подъезжала бы после первого
        # вопроса, и игрок успевал бы увидеть пустое место. Здесь же
        # рекорд приходит из БАЗЫ, а не из localStorage: рекорды не должны
        # теряться при смене браузера (решение владельца про «Мои
        # рекорды»). У анонима рекордов нет — там None, и табло честно
        # говорит словами.
        'best': (lb.best_run(request.user, mode)
                 if request.user.is_authenticated and not practice else None),
    })


@require_GET
def api_question(request):
    """Следующий вопрос текущего забега."""
    state = run_state.load_run(request)
    if not state:
        # ⚠️ ПРИЧИНА МАШИНОЧИТАЕМАЯ. Забега нет по двум причинам — его не
        # начинали или состояние истекло по TTL, — и для игрока они
        # неразличимы. Клиенту нужен признак, а не разбор текста ошибки.
        return JsonResponse({'error': 'Забег не начат', 'reason': 'no_run'},
                            status=400)
    if _close_pause(state, _now_ms()):
        run_state.save_run(request, state)
        return _paused_response()
    gq = _pick_next(request, state)
    if gq is None:
        return JsonResponse({'exhausted': True})
    run_state.save_run(request, state)
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
                       'ranked_today', 'ranked_per_day',
                       # итог по макету 17.09.2026 (ADR 0111), см. _finish_extras
                       'places', 'record', 'daily', 'attempts_left', 'duel',
                       'avg_correct_ms')


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
            cell = topics.setdefault(name, {'correct': 0, 'wrong': 0, 'skip': 0,
                                            'points': 0})
            cell[r['outcome']] += 1
            # «Где набрано» на итоге (ADR 0111). Вопрос с двумя темами кладёт
            # очки в обе: карточка показывает вклад темы, а не делит итог.
            cell['points'] += r.get('points') or 0
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
            'points': cell['points'],
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

    # «Держите ли сложное» на итоге (ADR 0111): полоски по звёздам вместо
    # трёх групп. Звёзды — ЭФФЕКТИВНАЯ сложность, та же, что над карточкой
    # вопроса и в очках; у старой записи журнала её нет — берём хранимую.
    stars = {}
    for r in log:
        level = r.get('difficulty_effective') or r.get('difficulty')
        if not level:
            continue
        level = max(1, min(5, int(round(level))))
        cell = stars.setdefault(level, {'stars': level, 'total': 0, 'correct': 0,
                                        'wrong': 0, 'skip': 0})
        cell['total'] += 1
        cell[r['outcome']] += 1

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
        'stars': [stars[k] for k in sorted(stars)],
        'time_buckets': buckets,
        # кривые для графиков: значение по номеру вопроса
        'score_curve': [r['running_score'] for r in log],
        'combo_curve': [r['running_combo'] for r in log],
        # Лента раунда: по записи на вопрос, в порядке игры. Экран рисует из
        # неё и ленту исходов, и график времени, и график очков — три графика
        # из одного места, а не три счётчика одного и того же.
        'outcome_seq': [r['outcome'] for r in log],
        'time_seq': [r.get('elapsed_ms') or 0 for r in log],
        'points_seq': [r.get('points') or 0 for r in log],
        'played_at': timezone.now().isoformat(timespec='seconds'),
    }


@require_POST
def api_answer(request):
    """Проверка ответа. Тело: {question_id, choice|choices|value}
    (null/отсутствие = пропуск). Ответ: верно/нет, правильный ответ
    (по типу вопроса), дельта времени, а также посчитанные СЕРВЕРОМ очки,
    серия и жизни. Когда жизни кончились — game_over с причиной 'lives'."""
    state = run_state.load_run(request)
    if not state:
        # ⚠️ ПРИЧИНА МАШИНОЧИТАЕМАЯ. Забега нет по двум причинам — его не
        # начинали или состояние истекло по TTL, — и для игрока они
        # неразличимы. Клиенту нужен признак, а не разбор текста ошибки.
        return JsonResponse({'error': 'Забег не начат', 'reason': 'no_run'},
                            status=400)
    if state.get('ended'):
        return JsonResponse({'error': 'Забег уже завершён'}, status=409)
    if _close_pause(state, _now_ms()):
        run_state.save_run(request, state)
        return _paused_response()
    try:
        body = json.loads(request.body.decode('utf-8'))
        qid = int(body['question_id'])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Некорректный запрос'}, status=400)
    elapsed_ms = _parse_elapsed(body)

    if qid not in state['seen']:
        return JsonResponse({'error': 'Этот вопрос не выдавался'}, status=404)
    # ⚠️ В «Бесконечных тестах» пропуск обратим: на пропущенный вопрос можно
    # ответить позже (решение 17.09.2026). В раунде — нет: там пропуск
    # засчитан, и второй ответ на тот же вопрос был бы вторым шансом.
    previous = state['answered'].get(str(qid))
    if previous is not None and not (state.get('practice') and previous == 'skip'):
        return JsonResponse({'error': 'Вопрос уже отвечен'}, status=409)

    try:
        gq = GameQuestion.objects.get(id=qid)
    except GameQuestion.DoesNotExist:
        return JsonResponse({'error': 'Вопрос не найден'}, status=404)

    checked = _check_answer(gq, body)
    if isinstance(checked, JsonResponse):
        return checked
    is_skip, correct = checked
    if state.get('practice'):
        return _practice_answer(request, state, gq, is_skip, correct, body)

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
    run_state.save_run(request, state)
    _duel_broadcast(request, state)

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
        return JsonResponse({'error': 'Нет завершённого раунда'}, status=400)
    mode = last.get('mode')
    if mode not in config.MODES:
        return JsonResponse({'error': 'Неизвестный режим'}, status=400)

    counts = mistakes_by_topic(last['log'])
    if not counts:
        return JsonResponse({'error': 'В этом раунде не было ошибок'}, status=400)

    # Фильтр наследуется от разбираемого забега: игрок выбрал источники и
    # сложность не для того, чтобы разбор ошибок молча вернул ему весь пул.
    run_filter = normalize_filter(last.get('filter'))
    probe = _new_state(mode, None, run_filter)
    rows = [(pk, topics)
            for pk, _d, topics, _g in _candidate_rows(probe)]
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
    run_state.save_run(request, state)
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
    # ⚠️ ДУЭЛЬ ИГРАЕТСЯ ТОЛЬКО ВОШЕДШИМ. Она сравнивает двух людей по
    # имени; у анонима имени нет, и на доске он был бы «кто-то». Отказ
    # даётся ЗДЕСЬ, а не на странице: страницу дуэли открывают все, чтобы
    # увидеть, во что зовут, — и об этом там сказано заранее.
    if gset.kind == 'duel' and not request.user.is_authenticated:
        return False, 'Принять вызов могут только вошедшие'
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
    state['duel'] = gset.kind == 'duel'
    state['curated'] = True     # эскалации сложности тут нет: список задан
    # ⚠️ ЗАБЕГ ДУЭЛИ ЗАПИСЫВАЕТСЯ В КОМНАТУ. Сокет соперника знает
    # только код набора и id игрока; связку «дуэль + игрок -> его
    # забег» держит запись комнаты (game/state.py), и без неё живого
    # табло не собрать: GameResult появляется только по окончании.
    if state['duel'] and request.user.is_authenticated:
        run_state.duel_register_run(gset.code, request.user.id,
                                    state['run_id'])
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
    run_state.save_run(request, state)
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


# Лестница задержек за промахи проверки кода — общая с входом и кодом
# занятия (`problems/ratelimit.py`), своя область.
SET_CHECK_SCOPE = 'game_set_check'


@require_GET
def api_set_check(request):
    u"""Есть ли набор с таким кодом: ячейка «Играть по коду» на главной.

    Ответ `{exists, url}`. Решение владельца 17.09.2026: неверный код
    оставляет игрока на главной со строкой под полем, а не уводит на общий
    404 сайта. Дуэль ведёт на свою страницу `/game/d/<код>/`, остальные
    наборы — на `/game/s/<код>/`.

    ⚠️ НОВОГО НАРУЖУ НЕ УХОДИТ. Существует ли код, и раньше было видно по
    ответу `/game/s/<код>/` (404 или страница); здесь то же знание, только
    без ухода со страницы. Пространство кодов 32^8, перебор вслепую
    бессмыслен, но промахи всё равно двигают лестницу задержек по адресу —
    так же, как у кода занятия.
    """
    from problems import ratelimit
    wait = ratelimit.check(SET_CHECK_SCOPE, request, None)
    if wait:
        return JsonResponse({
            'exists': False, 'url': '', 'wait': wait,
            'error': 'Слишком много попыток. Попробуйте через %d с.' % wait,
        }, status=429)
    code = make_code_lookup(request.GET.get('code'))
    gset = (GameSet.objects.filter(code=code).only('code', 'kind').first()
            if code else None)
    if gset is None:
        if code:
            ratelimit.register_failure(SET_CHECK_SCOPE, request, None)
        return JsonResponse({'exists': False, 'url': ''})
    name = 'game:duel' if gset.kind == 'duel' else 'game:set_page'
    return JsonResponse({'exists': True,
                         'url': reverse(name, args=[gset.code])})


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
    gset = GameSet.objects.filter(code=make_code_lookup(code)).first()
    if gset is None:
        return set_missing(request, code)
    allowed, why = set_run_allowed(request, gset)
    auto = request.GET.get('auto') == '1'
    # ⚠️ СТРАНИЦА ИГРЫ ЗДЕСЬ — ТОЛЬКО ДЛЯ ДУЭЛИ И ДЛЯ ЗАПУСКА `?auto=1` (P6,
    # решение 17.09.2026). Приглашение набора учителя — своя страница
    # (`set_page.html`), у вызова дня страница — `/game/daily/`: без
    # автостарта или когда играть нельзя, человек идёт туда, где видно почему.
    if gset.kind == 'daily' and not (auto and allowed):
        return redirect('game:daily')
    if gset.kind not in ('daily', 'duel') and not (auto and allowed):
        return set_invitation(request, gset, allowed, why)
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
        'board_url': (daily_mod.board_url(gset.mode, gset.day) if gset.kind == 'daily'
                      else reverse('game:set_page', args=[gset.code])),
        # Лобби дуэли: автору «Ждём соперника…», сопернику «Соперник: <автор>».
        # Имя автора и так видно на странице дуэли — нового наружу не уходит.
        'author': gset.author.username if gset.author_id else '',
        'is_author': bool(request.user.is_authenticated
                          and gset.author_id == request.user.id),
    }
    # ?auto=1 — начать сразу, без карточки-заставки. Механизм остаётся у
    # наборов другого рода (вызов дня, учительские): там его смысл в том,
    # чтобы не показывать лишний экран перед известным заданием.
    #
    # ⚠️ У ДУЭЛИ АВТОСТАРТА НЕТ, И ЭТО ЗАПРЕТ, А НЕ УМОЛЧАНИЕ (08.09.2026).
    # Раньше `duel_new` уводила автора сюда с `?auto=1`, забег начинался
    # немедленно, и автор не видел ни лобби, ни ссылки-приглашения. Соперник
    # приходил позже — в одном забеге они практически никогда не
    # пересекались, и живого табло не видел никто. Условие стоит здесь, а не
    # только в `duel_new`: иначе адрес с `?auto=1`, набранный руками или
    # оставшийся в чьей-то закладке, вернул бы прежнее поведение.
    ctx['auto_set']['autostart'] = (request.GET.get('auto') == '1'
                                    and allowed
                                    and gset.kind != 'duel')
    # Ссылка-приглашение для лобби дуэли. Ведёт на страницу дуэли, а не на
    # забег: соперник должен сначала увидеть, во что его зовут.
    ctx['duel_url'] = request.build_absolute_uri(
        reverse('game:duel', args=[gset.code])) if gset.kind == 'duel' else ''
    if gset.kind == 'duel':
        # Лобби дуэли по макету DuelLobby (ADR 0112): условия словами и два
        # слота. ⚠️ Имена — логины, как на досках: страница дуэли публичная,
        # и полное имя ученика по ссылке уходить не должно.
        mode_cfg = config.MODES.get(gset.mode, {})
        me = request.user.username if request.user.is_authenticated else ''
        ctx['auto_set'].update({
            'lives': mode_cfg.get('lives', 0),
            'duration_text': duration_text(mode_cfg.get('duration', 0)),
            'filter_text': ('без фильтров' if is_empty_filter(gset.filter_snapshot)
                            else _filter_text(gset.filter_snapshot)),
            'author_initials': initials(ctx['auto_set']['author']),
            'me': me,
            'me_initials': initials(me),
        })
    ctx['auto_set_json'] = json.dumps(ctx['auto_set'])
    return render(request, 'game/game.html', ctx)


def duration_text(seconds):
    u"""«1 мин», «2 мин», «45 с» — как `durationText` клиента."""
    return ('%g мин' % (seconds / 60)) if seconds >= 60 else '%d с' % seconds


def initials(name):
    u"""Инициалы для кружка игрока: «Макар Малиновский» → «ММ», «lengler» → «L»."""
    parts = [p for p in re.split(r'[\s_.\-]+', name or '') if p]
    return ''.join(p[0] for p in parts[:2]).upper()


@require_safe
def set_board(request, code):
    """Старый адрес доски набора `/game/s/<код>/board/` — только переход.

    Доска живёт на странице набора (P6), у вызова дня — доска дня (P4), у
    дуэли — её страница сравнения. Неверный код — та же страница «нет такого
    набора», что и у `/game/s/<код>/`.
    """
    gset = GameSet.objects.filter(code=make_code_lookup(code)).first()
    if gset is None:
        return set_missing(request, code)
    if gset.kind == 'duel':
        # У дуэли своя страница, и на ней вопросов нет вовсе.
        return redirect('game:duel', code=gset.code)
    if gset.kind == 'daily' and gset.day:
        return redirect(daily_mod.board_url(gset.mode, gset.day))
    return redirect('game:set_page', code=gset.code)


# Как отвечают в режиме — строкой приглашения: «Блиц · один верный ответ».
QUESTION_TYPE_TEXT = {'boolean': 'верно / неверно', 'single': 'один верный ответ',
                      'multi': 'несколько верных', 'numeric': 'числовой ответ',
                      'figure_audit': 'найти неверный шаг'}


def _moscow_text(moment, fmt='j E, H:i'):
    u"""«20 сентября, 23:59» — по Москве, как отсечка вызова дня."""
    from django.utils.formats import date_format
    return date_format(timezone.localtime(moment, daily_mod.daily_tzinfo()), fmt) if moment else ''


def set_invitation(request, gset, allowed, why):
    u"""Страница набора ученика `/game/s/<код>/` (решение 17.09.2026, ADR 0115).

    Приглашение (что за набор, одна кнопка «Играть» → `?auto=1`) и доска набора:
    «Кто прошёл» с анонимами и «Где ошиблись». Кто уже сыграл — видит свой
    результат и место. ⚠️ Тексты вопросов — автору, персоналу и сыгравшим: иначе
    контрольную можно прочитать заранее.
    """
    me = request.user if request.user.is_authenticated else None
    mine = my_result_for(request, gset)
    top, my_row, total = daily_mod.board_rows(gset, me, limit=10, with_anonymous=True,
                                              mine_code=mine.code if mine else None)
    my_place = next((r['place'] for r in top if r['is_me']), my_row['place'] if my_row else None)
    show_text = mine is not None or bool(me and (me.is_staff or gset.author_id == me.id))
    questions = set_question_stats(gset, show_text=show_text)
    for q in questions:
        q['hard'] = q['percent'] is not None and q['percent'] < 40
    mode_cfg = config.MODES.get(gset.mode, {})
    why_text = {'Попытка уже использована': 'Попытки закончились',
                'Набор ещё не открыт': 'Набор откроется ' + _moscow_text(gset.opens_at),
                'Набор уже закрыт': 'Набор закрыт ' + _moscow_text(gset.closes_at)}.get(why, why)
    own = reverse('game:set_page', args=[gset.code])
    return render(request, 'game/set_page.html', {
        'gset': gset,
        'kind_label': gset.get_kind_display(),
        'title': gset.title or 'Набор %s' % gset.code,
        'author': gset.author.username if gset.author_id else '',
        'mode_title': mode_cfg.get('title', gset.mode),
        'type_text': QUESTION_TYPE_TEXT.get(mode_cfg.get('question_type'), ''),
        'minutes': mode_cfg.get('duration', 0) // 60,
        'lives': mode_cfg.get('lives', 0),
        'closes_text': _moscow_text(gset.closes_at),
        'allowed': allowed,
        'why_text': why_text,
        'attempts_left': max(0, gset.attempts_allowed - attempts_used(request, gset)),
        'mine': mine,
        'my_place': my_place,
        'played_text': _moscow_text(mine.created_at, 'j E') if mine else '',
        'result_url': reverse('game:result', args=[mine.code]) if mine else '',
        'play_url': own + '?auto=1',
        'login_url': '/login/?next=' + own,
        'top': top,
        'my_row': my_row,
        'total': total,
        'more': max(0, total - len(top)),
        'board_title': 'Кто прошёл · %d' % total,
        'questions': questions,
        'show_text': show_text,
        'has_stats': any(q['correct'] or q['wrong'] or q['skip'] for q in questions),
    })


def set_missing(request, code):
    u"""Неверный код набора — страница игры со статусом 404, а не общий 404 сайта.

    Проверка кода та же, что на главной (`api/set_check`): ввёл верный —
    переход на его страницу без перезагрузки этой.
    """
    return render(request, 'game/set_missing.html', {
        'code': make_code_lookup(code)[:16],
    }, status=404)


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


def _wants_json(request):
    u"""Запрос пришёл из окна вызова (fetch), а не из адресной строки.

    Нужно ровно для одного: на пустой пул отвечать по-разному. Окну нужна
    строка ошибки, а человеку, набравшему адрес руками, — страница
    `duel_empty.html`. Одно и то же условие в двух видах — не дубль:
    получатели разные.
    """
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    return 'application/json' in (request.headers.get('Accept') or '')


@require_GET
def duel_new(request):
    """Создать дуэль и вернуть ссылку-приглашение. ТОЛЬКО ДЛЯ ВОШЕДШИХ.

    ⚠️ ВХОД ОБЯЗАТЕЛЕН, И ЭТО НЕ ФОРМАЛЬНОСТЬ. Дуэль — это сравнение двух
    людей по имени; у анонима имени нет, и на доске он был бы «кто-то».
    Результат дуэли вдобавок пишется с `user`, иначе «процент побед» и
    «самый частый соперник» посчитать не из чего.

    ⚠️ ГОСТЮ ИЗ ОКНА ВЫЗОВА: JSON 403 `{'ok': False, 'error': 'login'}`, А НЕ
    РЕДИРЕКТ (15.09.2026). Под `@login_required` fetch получал страницу
    входа, и гость читал «Не удалось создать вызов» вместо окна «Дуэль
    только с аккаунтом». Адрес, набранный руками, по-прежнему ведёт на вход.

    ⚠️ Набор дуэли собирается СЛУЧАЙНО под выбранные фильтры, и автор
    вызова НЕ ВИДИТ вопросы до игры: он играет их вслепую, наравне с
    соперником. Поэтому экрана «вот твой набор, поехали» не существует —
    ни одна вьюха не отдаёт список вопросов до того, как игрок их сыграл.

    ⚠️ В ИГРУ НЕ РЕДИРЕКТИТ (08.09.2026, решение владельца). Раньше вьюха
    уводила автора на `/game/s/<код>/?auto=1`, а `auto=1` запускает забег
    сразу: автор не видел ни лобби, ни ссылки-приглашения, и живого табло
    не видел никто. Ответ — JSON; окно вызова уводит автора в лобби
    (`play_url`), и с 15.09.2026 оба стартуют там по общему отсчёту.
    """
    if not request.user.is_authenticated:
        if _wants_json(request):
            return JsonResponse({'ok': False, 'error': 'login'}, status=403)
        return redirect_to_login(request.get_full_path())
    mode = request.GET.get('mode', '').strip() or config.DEFAULT_MODE
    if mode not in config.MODES:
        return JsonResponse({'error': 'Неизвестный режим'}, status=400)
    run_filter = parse_filter(request)
    probe = _new_state(mode, None, run_filter)
    ids = [pk for pk, _d, _t, _g in _candidate_rows(probe)]
    if not ids:
        # Под фильтром пусто — не создаём пустую дуэль, а честно говорим.
        if _wants_json(request):
            return JsonResponse({
                'ok': False,
                'error': 'Под этим фильтром вопросов нет: дуэль не из '
                         'чего собрать.'})
        return render(request, 'game/duel_empty.html', {
            'mode_title': config.MODES[mode]['title']}, status=200)
    random.shuffle(ids)
    # ⚠️ РЕВАНШ — ЭТО ЗАГОЛОВОК, А НЕ ОСОБЫЙ МЕХАНИЗМ. Набор всё равно
    # собирается заново: играть второй раз ТЕ ЖЕ вопросы значило бы
    # соревноваться в памяти, а не в экономике. Единственное, что несёт
    # `rematch`, — понятное название, чтобы соперник по ссылке видел, во что
    # его зовут. Несуществующий код молча игнорируется: это украшение.
    rematch = (GameSet.objects.filter(
        code=make_code_lookup(request.GET.get('rematch', '')), kind='duel')
        .first() if request.GET.get('rematch') else None)
    title = ('Реванш · %s' if rematch else 'Дуэль · %s')         % config.MODES[mode]['title']
    gset = GameSet.objects.create(
        code=make_result_code(), mode=mode, kind='duel',
        title=title,
        author=request.user if request.user.is_authenticated else None,
        # ⚠️ Это ЗАПАС ОЧЕРЕДИ, а не длина раунда: раунд кончается по
        # времени и жизням. Вопросов под фильтром меньше запаса — берём
        # сколько есть, и тогда `set_done` теоретически возможен. Это
        # честно: обещать бесконечную очередь на сорока вопросах нельзя.
        question_ids=ids[:config.DUEL_QUEUE_LIMIT],
        filter_snapshot=run_filter, attempts_allowed=1)
    return JsonResponse({
        'ok': True,
        'code': gset.code,
        # ⚠️ БЕЗ `?auto=1`. Окно вызова уводит автора сюда, в лобби: там код,
        # ссылка и общий отсчёт. Автостарт остаётся у наборов другого рода
        # (вызов дня, учительские) — там его смысл другой.
        'play_url': reverse('game:set_page', args=[gset.code]),
        'duel_url': request.build_absolute_uri(
            reverse('game:duel', args=[gset.code])),
        'mode': mode,
        'mode_title': config.MODES[mode]['title'],
        'filter_text': _filter_text(run_filter),
        'size': gset.size,
    })


@require_safe
def duel_page(request, code):
    """Страница дуэли `/game/d/<код>/` — одна для всех, в трёх видах (ADR 0112).

    - **Приглашение** (макет DuelInvite): ещё не играл и не автор — кто зовёт,
      условия пилюлями, «Принять вызов» (гостю — «Войти, чтобы принять»). Автор
      до своего раунда видит то же с «Вернуться в лобби».
    - **Ожидание**: свой результат есть, второго нет — «lengler ещё играет» или
      «ещё не пришёл», без таблицы.
    - **Сравнение** (макет DuelResult): оба отыграли — вердикт, двое карточками,
      «По цифрам» с лучшим в каждой строке, «Кто что взял», «Реванш».

    ВОПРОСЫ НЕ ПОКАЗЫВАЮТСЯ НИКОГДА: набор собран вслепую для обоих.
    """
    gset = get_object_or_404(GameSet, code=make_code_lookup(code), kind='duel')
    results = list(gset.results.select_related('user').order_by('created_at'))
    viewer = request.user if request.user.is_authenticated else None
    is_author = bool(viewer and gset.author_id == viewer.id)
    mine = my_result_for(request, gset)

    # ⚠️ РЕЗУЛЬТАТ АВТОРА — ТОЛЬКО РЕЗУЛЬТАТ АВТОРА. Прежняя подмена «первый
    # сыгравший» делала вызвавшим соперника, который просто закончил раньше
    # автора. Подмена осталась для старых дуэлей без автора.
    author_result = next((r for r in results
                          if gset.author_id and r.user_id == gset.author_id), None)
    if author_result is None and not gset.author_id and results:
        author_result = results[0]

    # ⚠️ ПАРА СРАВНЕНИЯ — АВТОР И ОДИН ДРУГОЙ РЕЗУЛЬТАТ (бой 17.09.2026: автор
    # не видел сравнения, потому что пара строилась «автор + я», а у автора
    # «я» и есть автор). Смотрит сыгравший соперник — второй его; остальным —
    # первый сыгравший после автора.
    if mine is not None and (author_result is None or mine.id != author_result.id):
        rival_result = mine
    else:
        rival_result = next((r for r in results
                             if author_result is None or r.id != author_result.id), None)
    compare = (_duel_compare(gset, author_result, rival_result, mine)
               if author_result and rival_result else None)

    allowed, why = set_run_allowed(request, gset)
    f = normalize_filter(gset.filter_snapshot)
    mode_cfg = config.MODES.get(gset.mode, {})
    author_name = gset.author.username if gset.author else 'аноним'
    ctx = {
        'gset': gset,
        'mode_title': mode_cfg.get('title', gset.mode),
        'mode_icon': DUEL_MODE_ICON.get(gset.mode, 'bolt'),
        'duration_text': duration_text(mode_cfg.get('duration', 0)),
        'time_correct': mode_cfg.get('time_correct', 0),
        'lives': mode_cfg.get('lives', 0),
        'author_name': author_name,
        'author_initials': initials(author_name),
        'is_author': is_author,
        'mine': mine,
        'compare': compare,
        'allowed': allowed,
        'why': why,
        'play_url': reverse('game:set_page', args=[gset.code]),
        'login_url': '/login/?next=' + quote(reverse('game:duel', args=[gset.code])),
        'challenge_url': '/game/?duel=' + gset.mode,
        'rematch_url': (reverse('game:duel_new') + '?mode=' + gset.mode
                        + _filter_query(f) + '&rematch=' + gset.code),
        'filter_text': 'без фильтров' if is_empty_filter(f) else _filter_text(f),
        'page_url': request.build_absolute_uri(reverse('game:duel', args=[gset.code])),
        # Больше двоих сыграло по ссылке — остальные строкой-доской под сравнением.
        'others': [{'name': r.user.username if r.user else 'аноним', 'score': r.score,
                    'accuracy': r.accuracy}
                   for r in sorted(results, key=lambda x: (-x.score, x.created_at))
                   if compare is None or r.id not in (author_result.id, rival_result.id)],
    }
    if compare is None and mine is not None:
        ctx['waiting'] = _duel_waiting(gset, viewer, is_author)
        ctx['my_mistakes'] = mine.wrong_count + mine.skip_count
    if compare is None and mine is None and gset.author_id:
        ctx['author_line'] = _duel_author_line(gset)
    return render(request, 'game/duel.html', ctx)


# Значки режимов на странице дуэли — те же, что у вкладок главной (MODE_META
# в game.html), и «в Пуле» для строки об авторе приглашения.
DUEL_MODE_ICON = {'bullet': 'bolt', 'blitz': 'flame', 'rapid': 'target',
                  'classic': 'keypad', 'figure': 'chart'}
MODE_IN = {'bullet': 'в Пуле', 'blitz': 'в Блице', 'rapid': 'в Рапиде',
           'classic': 'в Классике', 'figure': 'в Графике'}


def _duel_author_line(gset):
    u"""«дуэлей: 3 · побед 1 · лучший счёт в Пуле 957» — из журнала дуэлей и
    рекордов автора; данных нет — части нет, пустая строка — строки нет."""
    parts = []
    stats = lb.duel_stats(gset.author)
    if stats['played']:
        parts.append('дуэлей: %d · побед %d' % (stats['played'], stats['wins']))
    best = lb.best_scores(gset.author).get(gset.mode)
    if best:
        parts.append('лучший счёт %s %s' % (MODE_IN.get(gset.mode, ''), _thousands(best)))
    return ' · '.join(parts)


def _duel_waiting(gset, viewer, is_author):
    u"""«lengler ещё играет» или «ещё не пришёл» — пока второго результата нет.

    Играет ли второй, знает комната дуэли (game/state.py): его забег записан при
    старте и ещё не закрыт. Комната живёт полчаса — дальше «не пришёл».
    """
    if is_author:
        run_ids = [rid for _uid, rid in run_state.duel_rivals(gset.code, viewer.id)]
        who = 'Соперник'
    else:
        rid = run_state.duel_run_of(gset.code, gset.author_id) if gset.author_id else None
        run_ids = [rid] if rid else []
        who = gset.author.username if gset.author_id else 'Автор вызова'
    playing = False
    for rid in run_ids:
        st = run_state.load_by_id(rid)
        if st and not st.get('ended'):
            playing = True
    return '%s %s' % (who, 'ещё играет' if playing else 'ещё не пришёл')


def _thousands(n):
    return '{:,}'.format(n).replace(',', '\u00a0')


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



def _duel_broadcast(request, state, finished=False):
    u"""Разослать табло сопернику. Ошибка слоя каналов забег не роняет.

    ⚠️ ЗОВЁТСЯ ИЗ HTTP, А НЕ ИЗ СОКЕТА, И ЭТО НЕ СЛУЧАЙНОСТЬ. Счёт считает
    `api_answer`; он же и единственный, кто вправе о нём объявить. Клиентское
    сообщение `score` консьюмер игнорирует.

    ⚠️ ПАДАТЬ ЗДЕСЬ НЕЛЬЗЯ. Слой каналов может быть недоступен (Redis лёг,
    процесс `ws` не поднят) — тогда пропадает ТАБЛО, а забег продолжается.
    Пятисотка на ответе из-за украшения недопустима.
    """
    code = state.get('set_code')
    if not state.get('duel') or not code:
        return
    if not request.user.is_authenticated:
        return
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from game.consumers import duel_score_event, room_name

        layer = get_channel_layer()
        if layer is None:
            return
        event = duel_score_event(state, request.user)
        if finished:
            event = dict(event, type='duel.finished')
        async_to_sync(layer.group_send)(room_name(code), event)
    except Exception:            # noqa: BLE001 — украшение забег не роняет
        logger.warning('дуэль %s: табло не разослано', code, exc_info=True)

def _duel_compare(gset, a, b, mine=None):
    """Сравнение двоих по макету DuelResult (ADR 0112): `a` — автор, `b` — соперник.

    Смотрящий участник стоит слева и зовётся «Вы». Таблица «По цифрам» — только
    то, что хранит `GameResult` (решение 15.09.2026): среднего времени ВСЕХ
    ответов в базе нет, и строки с ним нет; нет замера — «–». ⚠️ ЛУЧШИЙ
    ВЫДЕЛЯЕТСЯ В КАЖДОЙ СТРОКЕ, а не весь столбец победителя: по очкам
    выиграл один, а быстрее отвечал, может быть, другой. Равные значения — без
    выделения.

    «Кто что взял» — по `question_outcomes`, только до последнего вопроса, до
    которого дошёл хоть кто-то (запас очереди дуэли — 150 вопросов).
    """
    left, right = (b, a) if (mine is not None and mine.id == b.id) else (a, b)
    me_id = mine.id if mine is not None else None

    def name(r, fallback):
        return r.user.username if r.user else fallback

    def combo(value):
        return '×' + ('%g' % (value or 1)).replace('.', ',')

    def secs(ms):
        return '–' if ms is None else ('%.1f' % (ms / 1000)).replace('.', ',')

    def clock(ms):
        if ms is None:
            return '–'
        minutes, rest = divmod(round(ms / 1000), 60)
        return '%d:%02d' % (minutes, rest)

    names = {a.id: name(a, 'автор'), b.id: name(b, 'соперник')}
    cards = []
    for r in (left, right):
        answered = r.correct_count + r.wrong_count + r.skip_count
        cards.append({'name': names[r.id], 'initials': initials(names[r.id]),
                      'is_me': r.id == me_id, 'score': r.score,
                      'sub': 'верных %d из %d · точность %d %% · комбо %s' % (
                          r.correct_count, answered, r.accuracy, combo(r.max_combo)),
                      'win': False})
    if left.score != right.score:
        winner = 0 if left.score > right.score else 1
        cards[winner]['win'] = True
        verdict = 'Вы победили' if cards[winner]['is_me'] else 'Победа за ' + cards[winner]['name']
    else:
        verdict = 'Ничья'
    hi, lo = max(left.score, right.score), min(left.score, right.score)
    line = ['%s : %s' % (_thousands(hi), _thousands(lo))]
    if hi != lo:
        gap = hi - lo
        line.append('разрыв %s %s' % (_thousands(gap), _plural(gap, 'очко', 'очка', 'очков')))
    line.append(_duel_endings(left, right, cards))

    # [подпись, значение, лучше больше?, как писать]
    metrics = (
        ('Очки', lambda r: r.score, True, _thousands),
        ('Верных', lambda r: r.correct_count, True, str),
        ('Ошибок', lambda r: r.wrong_count, False, str),
        ('Пропусков', lambda r: r.skip_count, False, str),
        ('Точность', lambda r: r.accuracy, True, lambda v: '%d %%' % v),
        ('Лучшее комбо', lambda r: r.max_combo or 1, True, combo),
        ('Секунд на верный', lambda r: r.avg_correct_ms, False, secs),
        ('Продержался', lambda r: r.wall_ms, True, clock),
    )
    rows = []
    for label, value, more_is_better, fmt in metrics:
        va, vb = value(left), value(right)
        best = ''
        if va is not None and vb is not None and va != vb:
            best = 'a' if (va > vb) == more_is_better else 'b'
        rows.append({'label': label, 'a': fmt(va) if va is not None else '–',
                     'b': fmt(vb) if vb is not None else '–', 'best': best})

    def by_qid(result):
        return {item.get('question_id'): item.get('outcome')
                for item in (result.question_outcomes or [])}

    ma, mb = by_qid(left), by_qid(right)
    reached = max(len(left.question_outcomes or []), len(right.question_outcomes or []))
    strip = [{'number': n + 1, 'a': ma.get(qid, 'none'), 'b': mb.get(qid, 'none')}
             for n, qid in enumerate((gset.question_ids or [])[:reached])]
    return {'cards': cards, 'verdict': verdict, 'line': ' · '.join(line),
            'rows': rows, 'strip': strip,
            'story': _duel_story(strip, cards)}


ENDING_BOTH = {'lives': 'оба выбыли по жизням', 'time': 'у обоих вышло время',
               'set_done': 'оба прошли все вопросы', 'pool_empty': 'у обоих кончились вопросы'}
ENDING_ONE = {'lives': 'жизни кончились', 'time': 'время вышло',
              'set_done': 'все вопросы пройдены', 'pool_empty': 'вопросы кончились'}


def _duel_endings(left, right, cards):
    u"""Чем кончились оба раунда — словами: «оба выбыли по жизням»."""
    ra, rb = left.ended_reason or 'time', right.ended_reason or 'time'
    if ra == rb and ra in ENDING_BOTH:
        return ENDING_BOTH[ra]
    who = ['у вас' if c['is_me'] else c['name'] for c in cards]
    return '%s: %s, %s: %s' % (who[0], ENDING_ONE.get(ra, ra), who[1], ENDING_ONE.get(rb, rb))


ORDINALS = ('первый', 'второй', 'третий', 'четвёртый', 'пятый', 'шестой', 'седьмой',
            'восьмой', 'девятый', 'десятый', 'одиннадцатый', 'двенадцатый',
            'тринадцатый', 'четырнадцатый', 'пятнадцатый', 'шестнадцатый',
            'семнадцатый', 'восемнадцатый', 'девятнадцатый', 'двадцатый')


def _duel_story(strip, cards):
    u"""Одна фраза-вывод под «Кто что взял» (макет DuelResult).

    «Первый взяли оба. Третий – только вы; второй и пятый – только lengler.
    Дальше вас уже не было.» Номера после двадцатого — «№21».
    """
    def words(numbers):
        items = [ORDINALS[n - 1] if n <= len(ORDINALS) else '№%d' % n for n in numbers]
        return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' и ' + items[-1]

    def who(card, case):
        if card['is_me']:
            return 'вы' if case == 'nom' else 'вас'
        return card['name']

    both = [c['number'] for c in strip if c['a'] == 'correct' and c['b'] == 'correct']
    only_a = [c['number'] for c in strip if c['a'] == 'correct' and c['b'] != 'correct']
    only_b = [c['number'] for c in strip if c['b'] == 'correct' and c['a'] != 'correct']
    out = []
    if both:
        out.append('%s взяли оба' % words(both))
    parts = []
    if only_a:
        parts.append('%s – только %s' % (words(only_a), who(cards[0], 'nom')))
    if only_b:
        parts.append('%s – только %s' % (words(only_b), who(cards[1], 'nom')))
    if parts:
        out.append('; '.join(parts))
    if not out:
        out.append('Верных не было ни у кого')
    reached_a = sum(1 for c in strip if c['a'] != 'none')
    reached_b = sum(1 for c in strip if c['b'] != 'none')
    if reached_a != reached_b:
        out.append('Дальше %s уже не было' % who(cards[0] if reached_a < reached_b else cards[1], 'gen'))
    return '. '.join(p[0].upper() + p[1:] for p in out) + '.'


def _plural(n, one, few, many):
    if n % 100 in (11, 12, 13, 14):
        return many
    return one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many


# ---------------------------------------------------------------------------
# Вызов дня
# ---------------------------------------------------------------------------

@require_safe
def daily_page(request):
    """Вызов дня `/game/daily/` (P4, решение владельца 17.09.2026, макет Daily).

    Серия дней и отсчёт до новой полуночи сверху, ниже карточка на каждый
    режим: число сыгравших, топ-5 доски, вчерашний победитель, «Играть» сразу
    в раунд (`?auto=1`) или, если уже сыграно, свой счёт и место.

    ⚠️ БЕЗ ЗАПРОСА НА ИГРОКА И НА КАРТОЧКУ. Наборы сегодня и вчера — одной
    выборкой, результаты всех восьми — второй; топ-5, число сыгравших, моё
    место и вчерашний победитель считаются из неё. Число запросов страницы
    не растёт с числом игроков — держит тест.
    """
    day = daily_mod.today()
    yesterday = day - datetime.timedelta(days=1)
    user = request.user if request.user.is_authenticated else None
    known = {(s.mode, s.day): s for s in
             GameSet.objects.filter(kind='daily', day__in=(day, yesterday))}
    today_sets = []
    for key in config.MODES:
        gset = known.get((key, day)) or daily_mod.get_daily_set(key, day)
        if gset is not None:        # в пуле нет вопросов этого типа — вызова нет
            today_sets.append(gset)
    yesterday_sets = {mode: s for (mode, d), s in known.items() if d == yesterday}

    board = {}
    set_ids = [s.id for s in today_sets] + [s.id for s in yesterday_sets.values()]
    for r in (GameResult.objects.filter(game_set_id__in=set_ids, user__isnull=False)
              .order_by('-score', 'created_at')
              .values('game_set_id', 'user_id', 'user__username', 'score')):
        board.setdefault(r['game_set_id'], []).append(r)
    # Свой результат анонима (и вошедшего, сыгравшего до входа) — по сессии.
    session_codes = request.session.get(MY_RESULTS_KEY) or {}
    wanted = [session_codes[s.code] for s in today_sets if s.code in session_codes]
    by_session = {r.game_set_id: r.score for r in
                  GameResult.objects.filter(code__in=wanted).only('game_set', 'score')
                  } if wanted else {}
    played_codes = set(played_set_codes(request))

    cards = []
    for gset in today_sets:
        rows = board.get(gset.id, [])
        my_place = my_score = None
        if user is not None:
            for i, r in enumerate(rows):
                if r['user_id'] == user.id:
                    my_place, my_score = i + 1, r['score']
                    break
        if my_score is None:
            my_score = by_session.get(gset.id)
        yset = yesterday_sets.get(gset.mode)
        yrows = board.get(yset.id, []) if yset else []
        cards.append({
            'mode': gset.mode,
            'title': config.MODES[gset.mode]['title'],
            'icon': DUEL_MODE_ICON.get(gset.mode, 'bolt'),
            'meta': daily_mod.set_line(gset.mode, gset.size),
            'count': len(rows),
            'top': [{'place': i + 1, 'name': r['user__username'], 'score': r['score'],
                     'is_me': bool(user and r['user_id'] == user.id)}
                    for i, r in enumerate(rows[:5])],
            'yesterday_winner': ({'name': yrows[0]['user__username'],
                                  'score': yrows[0]['score']} if yrows else None),
            'yesterday_url': daily_mod.board_url(gset.mode, yesterday),
            'played': my_score is not None or gset.code in played_codes,
            'my_score': my_score,
            'my_place': my_place,
            'play_url': reverse('game:set_page', args=[gset.code]) + '?auto=1',
            'board_url': daily_mod.board_url(gset.mode, day),
        })
    return render(request, 'game/daily.html', {
        'cards': cards,
        'day': day,
        'played_count': sum(1 for c in cards if c['played']),
        'streak': daily_mod.streak_for(user, today=day) if user is not None else None,
        'reset_at': daily_mod.next_reset().isoformat(),
    })


@require_safe
def daily_board(request, mode, day=None):
    """Доска дня `/game/daily/<режим>/[<день>/]` (P4, макет DailyBoard).

    Одна на вызов: страница вызова, итог раунда и старый адрес доски набора
    ведут сюда. Сводка сверху, «Таблица» (первые 10 и своя строка) и «Где
    ошиблись» по вопросам; режим и день переключаются ссылками.

    ⚠️ ДНЯ БЕЗ НАБОРА В ВИДЕ 404 НЕ БЫВАЕТ. Наборы создаются лениво: если в
    прошедший день на страницу вызова никто не заходил, набора нет, и доска
    честно пустая — «В этот день вызов никто не сыграл». Задним числом наборы
    НЕ создаются. 404 — только неизвестный режим, кривая дата и будущее.

    ⚠️ ТЕКСТЫ ВОПРОСОВ: пока вызов открыт (сегодня), их видят персонал и тот,
    кто вызов уже сыграл, — иначе набор можно подсмотреть до попытки. После
    закрытия дня тексты открыты всем (дополнение к решению 17.09.2026).
    """
    if mode not in config.MODES:
        raise Http404('Неизвестный режим')
    today = daily_mod.today()
    if day:
        try:
            day_obj = datetime.datetime.strptime(day, '%Y-%m-%d').date()
        except ValueError:
            raise Http404('Неверная дата')
        if day_obj > today:
            raise Http404('Этот день ещё не наступил')
    else:
        day_obj = today
    is_today = day_obj == today
    gset = daily_mod.get_daily_set(mode, day_obj, create=is_today)

    me = request.user if request.user.is_authenticated else None
    top, my_row, total, mine, my_place = [], None, 0, None, None
    questions, show_text = [], not is_today
    if gset is not None:
        top, my_row, total = daily_mod.board_rows(gset, me, limit=10)
        mine = my_result_for(request, gset)
        my_place = next((r['place'] for r in top if r['is_me']),
                        my_row['place'] if my_row else None)
        show_text = (not is_today or mine is not None
                     or bool(me and (me.is_staff or gset.author_id == me.id)))
        questions = set_question_stats(gset, show_text=show_text)
    for q in questions:
        q['hard'] = q['percent'] is not None and q['percent'] < 40

    one = datetime.timedelta(days=1)
    first = daily_mod.first_day()
    prev_day = day_obj - one if first is not None and day_obj - one >= first else None
    next_day = day_obj + one if day_obj < today else None
    enabled = set(_pool_qs().order_by().values_list('question_type', flat=True).distinct())
    tabs = [{'title': m['title'], 'on': key == mode,
             'url': daily_mod.board_url(key, day_obj)}
            for key, m in config.MODES.items()
            if m['question_type'] in enabled or key == mode]
    return render(request, 'game/daily_board.html', {
        'gset': gset,
        'mode': mode,
        'mode_title': config.MODES[mode]['title'],
        'set_line': daily_mod.set_line(mode, gset.size if gset else None),
        'tabs': tabs,
        'day': day_obj,
        'is_today': is_today,
        'is_yesterday': day_obj == today - one,
        'show_year': day_obj.year != today.year,
        'prev_url': daily_mod.board_url(mode, prev_day) if prev_day else '',
        'next_url': daily_mod.board_url(mode, next_day) if next_day else '',
        'reset_at': daily_mod.next_reset().isoformat() if is_today else '',
        'top': top,
        'my_row': my_row,
        'total': total,
        'more': max(0, total - len(top)),
        'mine': mine,
        'my_place': my_place,
        'result_url': reverse('game:result', args=[mine.code]) if mine else '',
        'play_url': (reverse('game:set_page', args=[gset.code]) + '?auto=1'
                     if gset is not None else ''),
        'questions': questions,
        'show_text': show_text,
        'has_stats': any(q['correct'] or q['wrong'] or q['skip'] for q in questions),
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
    state = run_state.load_run(request)
    if not state:
        # ⚠️ ПРИЧИНА МАШИНОЧИТАЕМАЯ. Забега нет по двум причинам — его не
        # начинали или состояние истекло по TTL, — и для игрока они
        # неразличимы. Клиенту нужен признак, а не разбор текста ошибки.
        return JsonResponse({'error': 'Забег не начат', 'reason': 'no_run'},
                            status=400)
    try:
        body = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        body = {}
    if state.get('practice'):
        # «Бесконечные тесты»: сводка без рекорда, без GameResult и без «работы
        # над ошибками» (LAST_KEY не пишется) — решение владельца 15.09.2026.
        state['ended'] = state.get('ended') or 'done'
        run_state.save_run(request, state)
        return JsonResponse({'summary': practice_summary(state), 'practice': True})
    # ⚠️ БРОШЕННЫЙ РАУНД СОХРАНЯЕТСЯ ТОЛЬКО БЕЗ НАБОРА (решение 17.09.2026).
    # У набора, вызова дня и дуэли в зачёт идёт только доигранный раунд:
    # сохрани мы брошенный — выход сжёг бы единственную попытку. Раунд без
    # единого ответа сохранять нечего. Клиент эти случаи сам не шлёт; здесь
    # вторая защита от старой вкладки и ручного запроса.
    if body.get('reason') == 'quit' and not state.get('ended'):
        if state.get('set_code') or not state.get('log'):
            return JsonResponse({'error': 'Этот раунд не сохраняется',
                                 'reason': 'quit_not_saved'}, status=400)
    # Открытая пауза (окно не успело сказать «закрыто») закрывается моментом
    # финиша — иначе её длительность не попала бы в зачёт.
    _close_pause(state, _now_ms())
    if not state.get('ended'):
        state['ended'] = _end_reason(state, body.get('reason'))
    run_state.save_run(request, state)
    # ⚠️ СОПЕРНИКУ ГОВОРИМ, ЧТО ЗАБЕГ КОНЧЕН. Без этого события его табло
    # застывало бы на последнем счёте и выглядело как «завис», а не как
    # «финишировал»: разницы игрок не видит, а она вся.
    _duel_broadcast(request, state, finished=True)
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
    if saved is not None:
        # Момент раунда — момент сохранения результата, а не повторного
        # вызова finish: иначе дата итога «ехала» бы с каждым обновлением.
        summary['played_at'] = saved.created_at.isoformat(timespec='seconds')
        summary.update(_finish_extras(request, saved))
    return JsonResponse({'summary': summary, 'share': share})


def _finish_extras(request, saved):
    u"""Поля итога раунда по макету 17.09.2026 (ADR 0111), читаются из базы.

    - `places` — места игрока в таблице режима за неделю и за всё время;
      только у зачётного раунда вошедшего.
    - `record` — {is_record, prev_best}: ⚠️ ЛИЧНЫЙ РЕКОРД — ЛУЧШИЙ ЗАЧЁТНЫЙ
      РАУНД РЕЖИМА (решение 17.09.2026, то же правило у чипа рекорда на
      раунде и в «Моей статистике»). У незачётного раунда плашки нет вовсе:
      «личный рекорд» рядом с «Не в таблице» читался бы как противоречие.
    - `daily` — место на доске дня, серия дней и следующий несыгранный вызов.
    - `attempts_left` — остаток попыток набора учителя.
    - `duel` — страница сравнения, отыграл ли соперник и адрес реванша.
    """
    out = {'avg_correct_ms': saved.avg_correct_ms}
    user = request.user if request.user.is_authenticated else None
    if saved.ranked and user is not None:
        week = lb.my_row(user, saved.mode, 'week', 'score')
        whole = lb.my_row(user, saved.mode, 'all', 'score')
        out['places'] = {'week': week['place'] if week else None,
                         'all': whole['place'] if whole else None}
        prev = (GameResult.objects
                .filter(user=user, mode=saved.mode, ranked=True,
                        economy_version=config.ECONOMY_VERSION,
                        created_at__lt=saved.created_at)
                .exclude(pk=saved.pk)
                .order_by('-score').values_list('score', flat=True).first())
        out['record'] = {'is_record': prev is not None and saved.score > prev,
                         'prev_best': prev}
    gset = saved.game_set
    if gset is None:
        return out
    if gset.kind == 'daily':
        out['daily'] = _daily_extras(request, saved, gset, user)
    elif gset.kind == 'duel':
        others = gset.results.exclude(pk=saved.pk)
        if user is not None:
            others = others.exclude(user=user)
        out['duel'] = {
            'url': reverse('game:duel', args=[gset.code]),
            'rival_done': others.exists(),
            # Реванш — тот же режим и фильтр, новые вопросы; окно зовёт этот
            # адрес запросом и уходит в лобби новой дуэли.
            'rematch_url': (reverse('game:duel_new') + '?mode=' + gset.mode
                            + _filter_query(gset.filter_snapshot)
                            + '&rematch=' + gset.code),
        }
    else:
        out['attempts_left'] = max(0, gset.attempts_allowed
                                   - attempts_used(request, gset))
    return out


def _daily_extras(request, saved, gset, user):
    u"""Итог вызова дня: место на доске дня, серия и следующий вызов.

    Место считается тем же порядком, что у доски (`daily.board_rows`): по
    счёту, при равенстве выше тот, кто закончил раньше. Аноним на доску не
    попадает — места у него нет, это итог и скажет словами.
    """
    ranked = gset.results.filter(user__isnull=False)
    info = {'board_url': daily_mod.board_url(gset.mode, gset.day),
            'total': ranked.count(), 'place': None, 'streak': 0, 'next': None}
    if user is not None and saved.user_id == user.id:
        ahead = ranked.filter(Q(score__gt=saved.score)
                              | Q(score=saved.score,
                                  created_at__lt=saved.created_at)).count()
        info['place'] = ahead + 1
        pairs = daily_mod.played_pairs(user)
        info['streak'] = daily_mod.streak_for(user, pairs=pairs)['current']
    else:
        pairs = set()
    day0 = daily_mod.today()
    played_codes = set(played_set_codes(request))
    for mode in config.MODES:
        if mode == gset.mode and gset.day == day0:
            continue
        if (day0, mode) in pairs:
            continue
        nxt = daily_mod.get_daily_set(mode, day0)
        if nxt is None or nxt.code in played_codes:
            continue
        info['next'] = {'mode': mode, 'title': config.MODES[mode]['title'],
                        'url': reverse('game:set_page', args=[nxt.code]) + '?auto=1'}
        break
    return info


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
    run_state.save_run(request, state)

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
    if claimed == 'quit':
        # Игрок вышел крестиком или Esc (решение 17.09.2026). Сохраняется
        # только раунд без набора — это проверяет `api_session_finish`.
        return 'quit'
    if claimed == 'time':
        return 'time'
    if claimed in ('done', 'pool_empty', 'set_done'):
        return 'set_done' if state.get('queue') is not None else 'pool_empty'
    return 'time'


def _quota_payload(request):
    u"""Квота зачётных раундов на сегодня по режимам — или None анониму.

    `{'used': {режим: N}, 'max': M}`. Стартовый экран показывает «N из M»
    у выбранного режима и меняет число вместе с режимом (ADR 0108): квота
    считается по режиму (`_ranked_today`), и одна цифра режима по умолчанию
    врала бы у остальных. Один запрос на все режимы.
    """
    if not request.user.is_authenticated:
        return None
    from django.db.models import Count
    from zoneinfo import ZoneInfo
    msk = ZoneInfo('Europe/Moscow')
    start = datetime.datetime.combine(_moscow_day(), datetime.time.min,
                                      tzinfo=msk)
    rows = (GameResult.objects
            .filter(user=request.user, ranked=True, created_at__gte=start,
                    created_at__lt=start + datetime.timedelta(days=1))
            .values('mode').annotate(n=Count('id')))
    used = {key: 0 for key in config.MODES}
    for row in rows:
        if row['mode'] in used:
            used[row['mode']] = min(row['n'], config.RANKED_RUNS_PER_DAY)
    return {'used': used, 'max': config.RANKED_RUNS_PER_DAY}


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


# ─── Пауза раунда (решение владельца 15.09.2026) ─────────────────────────
#
# ⚠️ ПАУЗУ ФИКСИРУЕТ СЕРВЕР, А НЕ КЛИЕНТ. Окно поверх раунда (обратная связь,
# «Плохая задача?», выход) останавливает клиентский таймер, а потолок
# длительности в `_rank_run` меряет стенные часы и снимал такой раунд с
# таблицы. Учесть паузу «со слов клиента» значит разрешить подкрутку
# таймера. Поэтому клиент только сообщает «окно открыто / закрыто», а начало
# и конец паузы сервер пишет СВОИМИ часами в `state['pauses']`. В зачёт идёт
# не больше `PAUSE_CAP_SECONDS` за раунд и не больше `PAUSE_MAX_COUNT` пауз;
# сверх потолка пауза принимается (игрок честно стоит), но не вычитается.
# Отвечать на паузе нельзя: ответ или вопрос, заставший паузу открытой
# (resume мог потеряться в сети), закрывает её своим моментом и получает
# 409 `paused` — клиент повторит запрос уже без паузы.

def _now_ms():
    return int(time.time() * 1000)


def _open_pause(state):
    pauses = state.get('pauses') or []
    return pauses[-1] if pauses and pauses[-1][1] is None else None


def _close_pause(state, now_ms):
    """Закрыть открытую паузу моментом `now_ms`. True — пауза была открыта."""
    pause = _open_pause(state)
    if pause is None:
        return False
    pause[1] = max(now_ms, pause[0])
    return True


def credited_pause_ms(state):
    """Сколько закрытой паузы вычитается из стенного времени раунда."""
    total = sum(end - start for start, end
                in (state.get('pauses') or [])[:config.PAUSE_MAX_COUNT]
                if end is not None)
    return min(total, config.PAUSE_CAP_SECONDS * 1000)


def paused_ms_now(state, now_ms=None):
    u"""Сколько раунд простоял на паузе к моменту `now_ms` — для часов
    соперника в дуэли (`consumers.seconds_left_for`).

    Те же правила зачёта, что у `credited_pause_ms`, плюс пауза, открытая
    прямо сейчас (разбор ошибки, окно), если она из первых PAUSE_MAX_COUNT.
    """
    now_ms = _now_ms() if now_ms is None else now_ms
    pauses = (state.get('pauses') or [])[:config.PAUSE_MAX_COUNT]
    total = sum((end if end is not None else max(now_ms, start)) - start
                for start, end in pauses)
    return min(total, config.PAUSE_CAP_SECONDS * 1000)


def _paused_response():
    return JsonResponse({'error': 'paused', 'reason': 'paused'}, status=409)


@require_POST
def api_pause(request):
    """Окно поверх раунда открылось: начало паузы по часам сервера."""
    state = run_state.load_run(request)
    if not state:
        return JsonResponse({'error': 'Забег не начат', 'reason': 'no_run'},
                            status=400)
    if state.get('ended'):
        return JsonResponse({'error': 'Забег уже завершён'}, status=409)
    if _open_pause(state) is None:
        pauses = state.setdefault('pauses', [])
        # Паузы сверх PAUSE_MAX_COUNT в зачёт не идут, поэтому хранить их все
        # незачем: последняя незачётная перезаписывается, и состояние в кэше
        # не растёт от щелчков по окну.
        if len(pauses) > config.PAUSE_MAX_COUNT:
            pauses[-1] = [_now_ms(), None]
        else:
            pauses.append([_now_ms(), None])
        run_state.save_run(request, state)
    return JsonResponse({'ok': True, 'paused': True})


@require_POST
def api_resume(request):
    """Окно закрылось: конец паузы по часам сервера."""
    state = run_state.load_run(request)
    if not state:
        return JsonResponse({'error': 'Забег не начат', 'reason': 'no_run'},
                            status=400)
    if _close_pause(state, _now_ms()):
        run_state.save_run(request, state)
    return JsonResponse({'ok': True, 'paused': False})


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
    if state.get('ended') == 'quit':
        return False, 'quit'
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
    # ⚠️ Зачтённая пауза вычитается ДО сравнения (решение владельца
    # 15.09.2026): окно поверх раунда не снимает его с таблицы. В базу
    # (`GameResult.wall_ms`) по-прежнему пишется настоящее стенное время.
    if wall_ms is not None and wall_ms - credited_pause_ms(state) > limit_ms:
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
        run_state.save_run(request, state)
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
        if gset.kind == 'duel':
            board = reverse('game:duel', args=[gset.code])
        elif gset.kind == 'daily':
            # У вызова дня одна доска — доска дня его режима и ЕГО дня (P4):
            # раунд вчерашнего набора, законченный после полуночи, ведёт на
            # вчерашнюю доску, а не на сегодняшнюю.
            board = daily_mod.board_url(gset.mode, gset.day)
        else:
            # Доска набора учителя живёт на его странице (P6).
            board = reverse('game:set_page', args=[gset.code])
        out['set'] = {
            'code': gset.code,
            'kind': gset.kind,
            'title': gset.title,
            'board_url': request.build_absolute_uri(board),
        }
    return out


# Чем кончился раунд — словами публичной страницы (P6): каждый исход своим, а не
# «время вышло» для всего, что не жизни.
RESULT_ENDING = {'lives': 'жизни кончились', 'time': 'время вышло',
                 'set_done': 'прошёл набор до конца', 'pool_empty': 'вопросы кончились',
                 'quit': 'вышел из раунда'}
# «Сыграть в Блиц», «в Пулю»: режим в винительном падеже.
MODE_TO = {'bullet': 'в Пулю', 'blitz': 'в Блиц', 'rapid': 'в Рапид',
           'classic': 'в Классику', 'figure': 'в График'}
# «1-е место в таблице Блица»: режим в родительном.
MODE_OF = {'bullet': 'Пули', 'blitz': 'Блица', 'rapid': 'Рапида',
           'classic': 'Классики', 'figure': 'Графика'}


def points_word(score):
    u"""«очко / очка / очков» по числу: 1 очко, 22 очка, 25 очков, 111 очков."""
    from problems.templatetags.ru import pick
    return pick(score, 'очко', 'очка', 'очков')


@require_safe
def result_page(request, code):
    """Публичная страница результата — то, что видит человек по ссылке.

    Без логина и read-only: чужой забег нельзя ни продолжить, ни изменить.
    require_safe, а не require_GET: HEAD должен отвечать как везде на сайте
    (мессенджеры дёргают HEAD перед разворачиванием превью).

    По решению 17.09.2026 (ADR 0115): ник игрока (у анонимного — «Игрок»),
    место в таблице режима у зачётного, исход словами для всех пяти причин и
    две кнопки — «Сыграть в <режим>» (или этот же набор) и «Вызвать на дуэль».
    ⚠️ Страница ничего не пишет; запросов — постоянное число, место считает та
    же функция, что строку «я» в лидерборде.
    """
    result = get_object_or_404(GameResult.objects.select_related('user', 'game_set'), code=code)
    mode_cfg = config.MODES.get(result.mode) or {}
    mode_title = mode_cfg.get('title', result.mode)
    name = result.user.username if result.user_id else ''
    gset = result.game_set
    place = None
    if result.ranked and result.user_id:
        row = lb.my_row(result.user, result.mode, 'all', 'score')
        place = row['place'] if row else None

    set_line = ''
    primary = {'text': 'Сыграть ' + MODE_TO.get(result.mode, mode_title),
               'sub': 'обогнать %s' % result.score if result.score else '',
               'url': reverse('game:page') + '?mode=' + result.mode}
    if gset is not None and gset.kind == 'daily':
        set_line = 'вызов дня · ' + _moscow_text(gset.opens_at or result.created_at, 'j E')
        if gset.day == daily_mod.today():
            primary = {'text': 'Сыграть этот же вызов', 'sub': '',
                       'url': reverse('game:set_page', args=[gset.code]) + '?auto=1'}
        else:
            primary = {'text': 'Сегодняшний вызов дня', 'sub': '', 'url': reverse('game:daily')}
    elif gset is not None and gset.kind == 'custom':
        set_line = 'набор «%s»' % (gset.title or gset.code)
        primary = {'text': 'Сыграть этот же набор', 'sub': '',
                   'url': reverse('game:set_page', args=[gset.code])}
    elif gset is not None and gset.kind == 'duel':
        set_line = 'дуэль'

    duel_target = reverse('game:page') + '?duel=' + result.mode
    viewer = request.user if request.user.is_authenticated else None
    rival = name if name and not (viewer and viewer.id == result.user_id) else ''
    lives = mode_cfg.get('lives') or 0
    lives_left = None
    if lives and result.ended_reason != 'lives' and 0 <= lives - result.wrong_count <= lives:
        lives_left = lives - result.wrong_count
    points = points_word(result.score)
    page_url = request.build_absolute_uri(reverse('game:result', args=[result.code]))
    return render(request, 'game/result.html', {
        'r': result,
        'name': name,
        'initials': initials(name),
        'mode_title': mode_title,
        'type_text': QUESTION_TYPE_TEXT.get(mode_cfg.get('question_type'), ''),
        'points_word': points,
        'place': place,
        'mode_of': MODE_OF.get(result.mode, mode_title),
        'set_line': set_line,
        'unranked_text': ('' if result.ranked or set_line
                          else config.UNRANKED_TEXT.get(result.unranked_reason, '')),
        'combo': '×' + ('%g' % (result.max_combo or 1)).replace('.', ','),
        'ending': RESULT_ENDING.get(result.ended_reason, RESULT_ENDING['time']),
        'lives': lives,
        'lives_left': lives_left,
        'primary': primary,
        'duel_url': duel_target if viewer else '/login/?next=' + quote(duel_target, safe='/'),
        'duel_text': 'Вызвать %s на дуэль' % rival if rival else 'Вызвать на дуэль',
        'pool_total': _pool_qs().count(),
        'topics': [t for t in (result.topic_breakdown or []) if t.get('total')],
        'page_url': page_url,
        'game_url': request.build_absolute_uri(reverse('game:page')),
        'og_image': request.build_absolute_uri(static('game/og_default.png')),
        'og_title': '%s%d %s в Wecon Rush – обгонишь?' % (name + ': ' if name else '', result.score, points),
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
    raw_tab = request.GET.get('tab')
    tab = raw_tab if raw_tab in ('arch', 'econ') else 'pool'
    min_attempts = config.STATS_MIN_ATTEMPTS

    if tab == 'econ':
        # Прибор для тюнинга экономики. Считает ТА ЖЕ функция, что и
        # команда game_economy_report: второй расчёт того же самого
        # разошёлся бы с первым при первой правке.
        from game.economy_report import report as economy_report
        data = economy_report(min_attempts)
        for row in data['by_difficulty']:
            row['base'] = config.BASE_BY_DIFFICULTY.get(row['star'])
        return render(request, 'game/stats.html', {
            'tab': tab, 'econ': data, 'rows': [], 'arch_rows': [],
            'min_attempts': min_attempts,
            'broken_pct': round(100 * config.STATS_BROKEN_BELOW),
            'trivial_pct': round(100 * config.STATS_TRIVIAL_ABOVE),
        })

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
            'topics': ', '.join(gq.topics or []) or '–',
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
