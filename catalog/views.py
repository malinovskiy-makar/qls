import hashlib
import json
import re
import time

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from problems import problem_types
from problems.enrich import features as enrich_features
from problems.templatetags.ru import plural_ru

from . import attachments, attempts, chat, filters, map_numbers, progress, search_log, seo, testplay
from .placeholder_phrases import (
    CATALOG_PHRASES, CATALOG_STOP_TEXT, HOME_PHRASES, SEARCH_BUSY_PHRASES,
)
from .preview import (
    PREVIEW_CHARS, looks_like_statement_cut, solution_is_statement_copy,
    strip_correct_repeat, strip_score_tails, strip_statement_retell, tex_preview,
)
from .topic_blocks import is_known, normalize as normalize_topic, section_of
from problems.ai import core as ai
from problems.models import (
    CatalogAttempt, Collection, FileAsset, Problem, ProblemFigure, Source, Topic,
)
from problems.management.commands.apply_topic_mapping import CANONICAL

# Сколько карточек добавляет одно нажатие «Показать ещё».
PAGE_STEP = 20
# Сколько кандидатов просим у смыслового поиска ДО фильтров. Фильтры
# срезают выдачу, и запас нужен, чтобы после трёх галочек осталось что
# показывать; больше пятисот брать незачем — дальше близость падает
# ниже порога у всех.
SEARCH_CANDIDATES = 500

# ── Утилита: убираем LaTeX для превью ──────────────────────────────────────
_RX_DISPLAY = re.compile(r'\$\$.*?\$\$|\\\[.*?\\\]', re.DOTALL)
_RX_INLINE  = re.compile(r'\$[^$\n]+?\$|\\\(.*?\\\)', re.DOTALL)
_RX_CMD_ARG = re.compile(r'\\[a-zA-Z]+\*?\{[^}]*\}')
_RX_CMD     = re.compile(r'\\[a-zA-Z]+\*?')
_RX_SPACE   = re.compile(r'\s+')


def _strip_latex(text):
    text = _RX_DISPLAY.sub('', text)
    text = _RX_INLINE.sub('', text)
    text = _RX_CMD_ARG.sub('', text)
    text = _RX_CMD.sub('', text)
    text = _RX_SPACE.sub(' ', text)
    return text.strip()


# ── Заголовок карточки «Похожие задачи» ─────────────────────────────────────
#
# ⚠️ У ЧАСТИ ЗАДАЧ `title` — ЭТО ОБРЕЗАННОЕ УСЛОВИЕ. Импортёры некоторых
# источников клали в заголовок первые ~80 символов текста, и рез приходился
# посреди формулы: «…производственные функции имеют вид $x =». Открывающий
# доллар без закрывающего формулой не считается — KaTeX его не трогает, и на
# карточке остаётся голый знак доллара с огрызком формулы.
#
# ⚠️ НО НЕ ВСЯКИЙ ОДИНОКИЙ ДОЛЛАР — ОБРЫВОК. Замер по всему банку: одиноких
# долларов 461, из них 449 действительно обрывки, а 12 — ВАЛЮТА, записанная
# без эскейпа: «Торговля рисом при мировой цене $3», «Цена продавцов при
# налоге $2». Резать их по доллару значит выкинуть из заголовка ровно то,
# ради чего он написан. Поэтому смотрим, что стоит ПОСЛЕ одинокого доллара:
# голое число — валюта, оставляем как есть; всё прочее — обрывок формулы.
_RX_PLAIN_NUMBER = re.compile(r'^\s*\d[\d\s.,%]*$')


def _last_unpaired_dollar(text):
    r"""Индекс незакрытого доллара или -1. «\$» разделителем не считается."""
    opened = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '\\' and i + 1 < len(text):
            i += 2
            continue
        if ch == '$':
            if opened:
                opened.pop()
            else:
                opened.append(i)
        i += 1
    return opened[0] if opened else -1


def similar_title(problem):
    """Заголовок для карточки похожей задачи: без обрывков формул.

    Пустой заголовок — берём начало условия без разметки, как в списке
    каталога. Заголовок с обрывком формулы — режем по незакрытому доллару.
    Целый заголовок (в том числе с валютой) отдаём как есть: формулы в нём
    KaTeX отрисует сам.
    """
    title = (problem.title or '').strip()
    if not title:
        raw = _strip_latex(problem.statement or '')
        return raw[:90] + ('…' if len(raw) > 90 else '')
    cut = _last_unpaired_dollar(title)
    if cut == -1 or _RX_PLAIN_NUMBER.match(title[cut + 1:]):
        return title
    return title[:cut].rstrip().rstrip(',;:') + '…'


def _page_range(page_obj):
    """
    Возвращает список номеров страниц для пагинации.
    0 используется как маркер «...» (многоточие).
    Показываем: первую, последнюю и ±2 вокруг текущей.
    """
    total   = page_obj.paginator.num_pages
    current = page_obj.number

    visible = set()
    visible.add(1)
    visible.add(total)
    for n in range(max(1, current - 2), min(total + 1, current + 3)):
        visible.add(n)

    result = []
    prev = None
    for n in sorted(visible):
        if prev is not None and n - prev > 1:
            result.append(0)   # «...»
        result.append(n)
        prev = n
    return result


# ── Главная страница ────────────────────────────────────────────────────────
def _fmt_number(n):
    """31488 → '31 488' (русский разделитель тысяч)."""
    return f'{n:,}'.replace(',', ' ')


# ⚠️ ВРЕМЕННО ЗАШИТО ДО ЗАЛИВКИ ТАКСОНОМИИ v2 — ВЕРНУТЬ НА ЖИВОЙ ПОДСЧЁТ.
# Решение владельца (01.09.2026): на лендинге стоят эти два числа, хотя база
# сегодня даёт другие. Оба расхождения известны и приняты осознанно:
#
#   «олимпиад 25+» — в базе 25 источников, но не все они олимпиады: там есть
#   Школково, Айлав и другие сборники. Слово поменялось на понятное посетителю,
#   а число округлено вперёд знаком «+», чтобы не обещать точность, которой у
#   новой формулировки нет.
#
#   «тем 29» — число тем таксономии v2, которая ещё НЕ ЗАЛИТА. Живой подсчёт по
#   старому списку CANONICAL даёт 23, и ровно 23 показывает фильтр каталога. То
#   есть до прогона обогащения главная и фильтр расходятся, и это ожидаемо.
#
# ЧТО СДЕЛАТЬ ПОСЛЕ ПРОГОНА ОБОГАЩЕНИЯ: удалить обе константы и вернуть в
# `home()` живые запросы — они лежат там же, строкой ниже, в комментарии.
# Знак «+» рисует шаблон отдельным span, поэтому здесь только число.
LANDING_OLYMPIADS = '25'
LANDING_TOPICS = '29'


def textbook(request):
    """«Учебник» — заглушка «Скоро».

    Раздела ещё нет, но пункт в шапке нужен уже на бете: иначе о планах
    никто не узнает. Ни формы, ни кнопки на экране нет намеренно — обещать
    там нечего (решение владельца 04.09.2026).
    """
    return render(request, 'catalog/textbook.html')


def home(request):
    """Показатели лендинга считаются ЖИВЫМ запросом, и по тем же правилам,
    что и каталог.

    ⚠️ РАНЬШЕ ЛЕНДИНГ ОБЕЩАЛ ТО, ЧЕГО НЕТ. `Problem.objects.count()` — это
    ВЕСЬ банк, вместе с непроверенным и забракованным: на этой базе 41 307.
    А пройти по ссылке человек может к 14 458 — остальное скрыто двумя
    шлюзами (`needs_quality_review` прячет плохое, `hidden_pending_review` —
    то, чего человек ещё не смотрел). Разница почти втрое, и обнаружил бы её
    первый же посетитель, нажавший «Каталог задач».

    Поэтому фильтр здесь ровно тот же, что в `problem_list`, а источники
    считаются тем же запросом, которым каталог наполняет свой список
    фильтра. Иначе числа снова разъедутся при первой правке одной из сторон.
    """
    visible = Problem.objects.filter(
        status=Problem.Status.PUBLISHED,
        needs_quality_review=False,
        hidden_pending_review=False,
        content_status=Problem.ContentStatus.OK,
    )
    context = {
        # Живое число — оно и верное, и проверяемое ссылкой «Каталог задач».
        'problems_count': _fmt_number(visible.count()),
        # ⚠️ Два числа ниже — временные константы, см. блок над функцией.
        # Живой подсчёт, к которому надо вернуться после таксономии v2:
        #   'olympiads_count': (Source.objects
        #                       .filter(references__problem__status=Problem.Status.PUBLISHED)
        #                       .distinct().count()),
        #   'topics_count':    Topic.objects.filter(name__in=CANONICAL).count(),
        'olympiads_count': LANDING_OLYMPIADS,
        'topics_count':    LANDING_TOPICS,
        # Бегущая подсказка поля — общий партиал, фразы из одной константы.
        'home_phrases':    HOME_PHRASES,
        'seo_title':       seo.HOME_TITLE,
        'seo_description': seo.HOME_DESCRIPTION,
    }
    return render(request, 'catalog/home.html', context)


# ── Случайная опубликованная задача ─────────────────────────────────────────
def random_problem(request):
    """Случайная видимая задача; понимает фильтры каталога и `exclude=<id>`.

    «Ещё тест по этой теме» на странице теста (этап 7) ведёт сюда с
    `type=test&topic=<id>&exclude=<текущая>`: те же параметры, что у
    каталога, разбирает `filters.parse`.
    """
    active = filters.parse(request.GET)
    qs = filters.apply(filters.base_queryset('catalog'), active)
    exclude = (request.GET.get('exclude') or '').strip()
    if exclude.isdigit():
        qs = qs.exclude(pk=int(exclude))
    problem = qs.order_by('?').first()
    if problem is None:
        return redirect('catalog:problem_list')
    return redirect('catalog:problem_detail', pk=problem.pk)


# ── Список задач ────────────────────────────────────────────────────────────
def _card(problem):
    """Одна карточка выдачи.

    ⚠️ НОМЕРА ЗАДАЧИ В КАРТОЧКЕ НЕТ (решение владельца 04.09.2026): он
    остаётся только в адресе. Глаз цепляется за тему и условие: цветной
    чип темы, звёзды при заданной сложности, формат теста, флаг решения.

    ⚠️ ПРАВИЛО НУЛЯ: каждое поле карточки берётся из данных задачи, и чего
    нет в данных — того нет и в разметке. Заголовок показывается, только
    если это название, а не обрезок условия (`looks_like_statement_cut`).
    """
    refs = list(problem.source_references.all())
    d = problem.difficulty or 0
    title = (problem.title or '').strip()
    is_test = problem_types.is_test(problem.problem_type)
    return {
        'problem':          problem,
        'preview':          tex_preview(problem.statement, PREVIEW_CHARS),
        # Тема несёт раздел карты — им красится чип (`--map-g-*`).
        'topics':           [{'name': t.name, 'section': section_of(t.name)}
                             for t in problem.topics.all()
                             if is_known(t.name)][:2],
        'difficulty':       d,
        'difficulty_stars': range(d),
        'difficulty_empty': range(5 - d),
        'has_solution':     bool(problem.solution)
                            and not problem.solution_needs_review
                            and not solution_is_statement_copy(problem.statement,
                                                               problem.solution),
        'source':           refs[0].source.name if refs else '',
        'grade':            refs[0].grade if refs else '',
        'is_test':          is_test,
        # «тест · один верный»: вид теста по `problem_type`, если он известен
        # словарю `problems.problem_types`; иначе просто «тест».
        'kind_label':       _kind_label(problem.problem_type) if is_test else '',
        'show_title':       bool(title) and not looks_like_statement_cut(
                                title, problem.statement),
        # Заголовок в строке ленты «Стола» — без обрывка формулы, как у «Похожих».
        # Процента близости в строке нет (решение владельца 17.09.2026).
        'title_display':    similar_title(problem) if title else '',
    }


def _is_tutor(user):
    """Репетитор ли (обе системы ролей, `teacher.access.is_tutor`)."""
    from teacher.access import is_tutor
    return is_tutor(user)


def _cards_with_marks(user, problems):
    """Карточки строк ленты со статусом ученика и звездой «сохранено» —
    по одному запросу на страницу строк, а не на строку.

    Репетитору (README §7) вместо статуса — галочка корзины (`teach`) и
    пометка «в N домашках» (`in_hw`): сколько ЕГО работ уже содержат задачу,
    тоже одним запросом на страницу строк.
    """
    from problems.models import SavedProblem
    from problems.models_platform import AssignmentItem

    problems = list(problems)
    ids = [p.pk for p in problems]
    statuses = progress.statuses_for(user, ids)
    saved = set()
    if getattr(user, 'is_authenticated', False) and ids:
        saved = set(SavedProblem.objects.filter(owner=user, is_deleted=False,
                                                catalog_problem_id__in=ids)
                    .values_list('catalog_problem_id', flat=True))
    teach = _is_tutor(user)
    in_hw = {}
    if teach and ids:
        in_hw = dict(AssignmentItem.objects.filter(assignment__author=user, catalog_problem_id__in=ids)
                     .values('catalog_problem_id').annotate(n=Count('assignment', distinct=True))
                     .values_list('catalog_problem_id', 'n'))
    cards = []
    for problem in problems:
        card = _card(problem)
        card['status'] = statuses.get(problem.pk, '')
        card['saved'] = problem.pk in saved
        card['teach'] = teach
        card['in_hw'] = in_hw.get(problem.pk, 0)
        cards.append(card)
    return cards


def _kind_label(problem_type):
    """Подпись вида теста в карточке."""
    label = problem_types.kind_label(problem_type)
    return 'тест · ' + label if label else 'тест'


def _teacher_assignments(request):
    """Активные домашки репетитора — меню «В домашку ▾» корзины (README §7).

    Название, сколько в работе задач (позиций) и кому она выдана: имя
    занятия, иначе число учеников; некому — строки «кому» нет (правило нуля).
    """
    if not _is_tutor(request.user):
        return []
    from django.utils import timezone

    from problems.models import Assignment

    active_qs = (Assignment.objects
                 .filter(author=request.user)
                 .filter(Q(deadline__isnull=True)
                         | Q(deadline__gte=timezone.now()))
                 .select_related('group')
                 .annotate(n_items=Count('items', distinct=True), n_students=Count('students', distinct=True))
                 .order_by('-id')[:50])
    rows = []
    for a in active_qs:
        if a.group_id:
            to = a.group.name
        elif a.n_students:
            to = '%d %s' % (a.n_students, plural_ru(a.n_students, 'ученик,ученика,учеников'))
        else:
            to = ''
        rows.append({'id': a.pk, 'name': a.name, 'n': a.n_items, 'to': to})
    return rows


def _search_ids(query, limit):
    """Кандидаты смыслового поиска: id по убыванию близости.

    Возвращает `(ids, scores, degraded)`. `degraded=True` — смысловой поиск
    недоступен и мы честно пошли по словам. Это ДЕГРАДАЦИЯ, А НЕ ОТКАЗ
    (правило 6.13 docs/EMBEDDINGS.md): страница обязана ответить 200 и
    что-то найти. Пятисотка и вечный спиннер — худшее, что можно сделать с
    человеком, который просто искал задачу.

    ⚠️ ФИЛЬТРЫ ЗДЕСЬ НЕ НАКЛАДЫВАЮТСЯ НАРОЧНО. У `semantic.search` есть свои
    три (тема, сложность, решение), но на экране их восемь, и все восемь
    умеет общий компонент. Две накладки одних и тех же условий — ровно то
    расхождение, ради которого компонент и заводился. Поиск отвечает на
    «что похоже», фильтры — на «что подходит».
    """
    import logging

    from django.conf import settings

    from . import hybrid, semantic
    from .search_client import SearchServiceUnavailable

    logger = logging.getLogger(__name__)
    floor = getattr(settings, 'SEMANTIC_SEARCH_MIN_SCORE', 0.0)

    def by_words():
        ids, _hits, _picked = hybrid.lexical_search(query, limit, 'all')
        return ids, {}, True

    if not semantic.is_enabled():
        return by_words()
    try:
        raw = semantic.search(query_text=query, content_kind='all',
                              limit=limit)
    except SearchServiceUnavailable as exc:
        logger.warning('search service unavailable: %s — идём по словам', exc)
        return by_words()
    except Exception as exc:                       # noqa: BLE001
        # ⚠️ ЛЮБАЯ ДРУГАЯ ПОЛОМКА ПОИСКА — ТОЖЕ ДЕГРАДАЦИЯ. Раньше здесь
        # человек получал «Ошибка поиска: …» с нашей внутренней кухней
        # вместо задач. Поиск по словам работает и без модели.
        logger.warning('смысловой поиск упал (%s) — идём по словам', exc)
        return by_words()

    # ⚠️ ПОРОГ БЛИЗОСТИ — НАСТРОЙКА, А НЕ ЧИСЛО В КОДЕ: его придётся
    # калибровать на Dataset B, и он поедет после прогона обогащения.
    scores = {item['problem'].pk: item['score'] for item in raw
              if item['score'] >= floor}
    return [pid for pid in (i['problem'].pk for i in raw) if pid in scores], \
        scores, False


def _relief(base, active, candidate_ids):
    """Какой фильтр снять, если запрос и фильтры вместе почти ничего не дали.

    Возвращает `(подпись, сколько будет без него)` для самого «дорогого»
    фильтра — или None. Экран обязан назвать причину: схлопнувшаяся выдача
    без объяснения читается как «в банке этого нет», хотя на деле сошлись
    запрос и три галочки.
    """
    best = None
    for key in ('topic', 'tag', 'difficulty', 'kind', 'source',
                'has_solution', 'character', 'feature'):
        value = active[filters.ACTIVE_KEY[key]]
        if not value:
            continue
        loose = filters.apply(base, active, skip=(key,))
        if candidate_ids is not None:
            loose = loose.filter(pk__in=candidate_ids)
        n = loose.distinct().count()
        if best is None or n > best[1]:
            n_values = len(value) if isinstance(value, list) else 1
            best = (filters.relief_label(key, n_values), n)
    if best is None or best[1] < 1:
        return None
    return {'label': best[0], 'count': best[1]}


def _numeric_query(query):
    """Чисто числовой запрос — это НОМЕР задачи, а не описание.

    У числа нет смысла, который можно с чем-то сравнить: смысловой поиск на
    «1065» вернёт мусор. Возвращает `(id найденной задачи, ненайденный
    номер)`. Видимость проверяется та же, что у самой страницы задачи,
    иначе ответ «есть/нет» стал бы оглавлением скрытого.
    """
    if not (query.isdigit() and len(query) <= 9):
        return None, ''
    found_id = (Problem.objects
                .filter(pk=int(query), status=Problem.Status.PUBLISHED,
                        needs_quality_review=False,
                        hidden_pending_review=False,
                        content_status=Problem.ContentStatus.OK)
                .values_list('pk', flat=True).first())
    return found_id, ('' if found_id else query)


def _catalog_context(request, missing_id='', paid=False):
    """Контекст каталога — ОДИН на страницу и на эндпоинт живого состояния.

    ⚠️ СТРАНИЦА И `api_filter_state` СОБИРАЮТСЯ ОДНИМ КОДОМ И РИСУЮТ ОДНИ
    ПАРТИАЛЫ (`_catalog_results.html`, `_catalog_chips.html`). Иначе список
    под окном фильтров и список после перезагрузки разошлись бы при первой
    же правке одного из них (решение владельца 04.09.2026: фильтры
    обновляют выдачу живьём, окно не закрывается).

    ⚠️ ПРИ ПУСТОМ ЗАПРОСЕ СМЫСЛОВОЙ ПОИСК НЕ ТРОГАЕТСЯ ВООБЩЕ. Модель
    грузится лениво, первый раз около семи секунд. Каталог — главный вход,
    и секунды достались бы каждому, кто просто зашёл посмотреть банк.

    `paid` — можно ли платить за переранжирование. Его ставит ТОЛЬКО
    `api_filter_state` (запрос скрипта страницы); полная загрузка страницы не
    платит никогда (24.09.2026, `catalog/rerank_gate.py`).
    """
    active = filters.parse(request.GET)
    query = active['q']

    # ⚠️ ВИД ОДИН — СТРОКИ. Таблицы нет с 04.09.2026, галереи — с 17.09.2026
    # (решение владельца: в «Столе» условие целиком показывает сама задача).
    # Старые адреса с `?view=table` и `?view=gallery` открываются строками и
    # параметр дальше не несут.
    base = filters.base_queryset('catalog')
    carry = {}
    qs, fctx = filters.build(base, active, mode='strip', carry=carry)

    # Сколько подходит под ФИЛЬТРЫ без запроса — второе число счётчика.
    filtered_total = qs.distinct().count()

    # ⚠️ «ПОКАЗАТЬ ЕЩЁ» ВМЕСТО СТРАНИЦ. Номер страницы у ранжированного
    # списка ничего не значит: «страница 7» смыслового поиска — это не
    # место в банке, а место в ответе на конкретный запрос.
    try:
        shown = int(request.GET.get('show') or PAGE_STEP)
    except (TypeError, ValueError):
        shown = PAGE_STEP
    shown = max(PAGE_STEP, min(shown, PAGE_STEP * 25))

    degraded = False
    searched = bool(query) and not missing_id
    relief = None
    capped = False

    smart_search_status = 'off'
    # Время поиска в мс — для заголовка `X-Smart-Search-Ms`: владелец меряет
    # бой одним `curl -sI`, без доступа к журналу (15.09.2026). Считаются сам
    # поиск и переранжирование, без сборки карточек; 0 — запроса не было.
    smart_search_ms = 0
    if searched:
        search_started = time.perf_counter()
        ids, _scores, degraded = _search_ids(query, SEARCH_CANDIDATES)
        search_seconds = time.perf_counter() - search_started
        # ⚠️ ПОЛУЧАЕМ СНАЧАЛА ОДНИ КЛЮЧИ, А ЗАДАЧИ — ТОЛЬКО НА СТРАНИЦУ.
        # Первый вариант тянул из базы все пятьсот кандидатов со связями
        # ради двадцати показанных карточек.
        passed = set(qs.filter(pk__in=ids).values_list('pk', flat=True))
        ranked = [pid for pid in ids if pid in passed]

        # ⚠️ ПЕРЕРАНЖИРОВАНИЕ (`catalog/rerank.py`) — ЗА ФЛАГОМ
        # `SMART_SEARCH_RERANK`, для всех посетителей, включая гостя
        # (13.09.2026: «только сотрудникам» снято). `apply()` возвращает порядок ПУЛА (собран без учёта
        # активных фильтров каталога — тема/тег/сложность и т.п.) либо
        # `None`, если менять нечего; `None` означает побайтовое совпадение
        # со старым поведением. Пул может содержать задачи, которых нет в
        # `ranked` (плотная нога пула — БЕЗ порога близости, в отличие от
        # базовой выдачи), поэтому активные фильтры накладываются здесь же
        # заново — тем же способом, что и на `ids` выше.
        # ⚠️ ПЛАТИТ ТОЛЬКО СКРИПТ СТРАНИЦЫ (24.09.2026, ADR 0128). 19.09
        # краулерам закрыли переранжирование проверкой User-Agent, но её
        # подделывает кто угодно. Теперь полная загрузка страницы не платит
        # никогда: статус `deferred`, страница показывает «ищем…» и сама
        # просит `api_filter_state` с заголовком `X-Weco-Search`. Там —
        # кука посетителя, User-Agent, квоты и потолок (`rerank_gate`).
        # Бот, который ходит по ссылкам без JS, заплатить не может.
        from . import rerank as smart_rerank
        from . import rerank_gate
        rerank_started = time.perf_counter()
        if not smart_rerank.is_available(request.user):
            pool_order, smart_search_status = None, 'off'
        elif not paid:
            pool_order = None
            smart_search_status = 'bot' if seo.is_crawler(request) else 'deferred'
        else:
            refused = rerank_gate.refusal(request)
            if refused:
                pool_order, smart_search_status = None, refused
            else:
                pool_order, smart_search_status = smart_rerank.apply(
                    request.user, query, request=request)
        search_seconds += time.perf_counter() - rerank_started
        smart_search_ms = int(round(search_seconds * 1000))
        if pool_order:
            candidates = pool_order + [pid for pid in ranked
                                       if pid not in set(pool_order)]
            still_passed = set(qs.filter(pk__in=candidates)
                               .values_list('pk', flat=True))
            ranked = [pid for pid in candidates if pid in still_passed]

        total = len(ranked)
        # ⚠️ ЧИСЛО — ОЦЕНКА СНИЗУ, КОГДА СПИСОК УПЁРСЯ В ПОТОЛОК. Мы просим
        # у индекса пятьсот лучших; если порог прошли все пятьсот, похожих
        # в банке может быть и три тысячи. Писать «500» в этом случае —
        # врать точным числом, поэтому счётчик говорит «не меньше».
        capped = len(ids) >= SEARCH_CANDIDATES
        window = ranked[:shown]
        by_id = {p.pk: p for p in
                 qs.filter(pk__in=window)
                 .prefetch_related('topics', 'parts',
                                   'source_references__source')}
        page_rows = [by_id[pid] for pid in window if pid in by_id]
        has_more = total > shown
        if total <= 2 and not filters.is_empty(active):
            relief = _relief(base, active, ids)
    else:
        ordered = (qs.prefetch_related('topics', 'parts',
                                       'source_references__source')
                   .order_by('-id').distinct())
        total = filtered_total
        page_rows = list(ordered[:shown])
        has_more = total > shown

    cards = _cards_with_marks(request.user, page_rows)

    return {
        'filters':        fctx,
        'cards':          cards,
        # Статус в строке — только у вошедшего: у гостя колонки нет (README §2).
        'show_status':    request.user.is_authenticated,
        # Чипы входа «Тема / Сложность / Задачи и тесты / С решением» рисуют
        # варианты тех же групп, что окно «Все фильтры»: одно состояние.
        'entry_groups':   {g['key']: g for g in fctx['groups']},
        'query':          query,
        'searched':       searched,
        'degraded':       degraded,
        # Статус умного поиска: заголовок `X-Smart-Search` (`problem_list`,
        # `api_filter_state`) и текст плашки поиска по словам в шаблоне.
        'smart_search_status': smart_search_status,
        'smart_search_ms': smart_search_ms,
        'missing_id':     missing_id,
        'total':          total,
        'capped':         capped,
        'filtered_total': filtered_total,
        # Подпись второго числа счётчика: «из 294 по теме „Монополия“» —
        # собирает общий модуль, у него же формы для нескольких значений.
        'scope':          fctx['scope'],
        'shown':          len(cards),
        'has_more':       has_more,
        'more_url':       fctx['total_url'] + '&show=%d' % (shown + PAGE_STEP),
        'step':           PAGE_STEP,
        'relief':         relief,
        'teacher_assignments': _teacher_assignments(request), 'is_tutor': _is_tutor(request.user),
        # Бегущая подсказка поля: фразы и текст после остановки — из
        # одной константы, партиал общий с главной.
        'catalog_phrases':   CATALOG_PHRASES,
        'catalog_stop_text': CATALOG_STOP_TEXT,
        # Фразы ожидания поиска: первая — в разметке, все — в json_script.
        'search_busy_phrases': SEARCH_BUSY_PHRASES,
        # Подпись блока карты — из данных карты, не литералом.
        'map_stats':         _map_stats(),
        # Стартовое состояние для скрипта окна «Все фильтры»: активные
        # значения (уже списками) и адреса эндпоинтов — по имени, не строкой.
        'filter_state': {
            'active': active,
            'urls': {'state': reverse('catalog:api_filter_state'),
                     'tags': reverse('catalog:api_tags'),
                     'page': reverse('catalog:problem_list')},
        },
    }


def _entry_context(request, context):
    """Что добавляет к контексту каталога вид «вход» единого экрана «Стол».

    Заголовок «Это умный каталог.» и крупная шапка — только пока нет ни
    запроса, ни фильтров (README §2): первый выбор сжимает шапку. «Продолжить»
    — только на чистом входе: при поиске он уводил бы от найденного.
    """
    selected = context['filters']['selected_count']
    active = context['filters']['active']
    calm = not context['query'] and not selected
    extra = {'view': 'entry', 'entry_calm': calm, 'continue_rows': [],
             # Выбранное на карте = фильтры: подсветка фона и подпись пилюли.
             'map_selected': {'topics': active['topics'], 'tags': active['tags']},
             'map_selected_n': len(active['topics']) + len(active['tags'])}
    if calm:
        problems = progress.continue_for(request.user, _visible(Problem.objects.all()))
        statuses = progress.statuses_for(request.user, [p.pk for p in problems])
        extra['continue_rows'] = [
            {'problem': p, 'status': statuses.get(p.pk, ''),
             'title': similar_title(p) if (p.title or '').strip()
             and not looks_like_statement_cut(p.title, p.statement)
             else tex_preview(p.statement, 70)}
            for p in problems]
    return extra


def _seo_context(context):
    """Метаданные входа каталога для поисковиков.

    Выдача по строке поиска — `noindex, nofollow` (страница под каждый
    запрос бесконечна и дорога). Каталог, отфильтрованный ровно одной темой и
    ничем больше, — страница темы со своим заголовком и описанием; любые
    другие сочетания фильтров заголовка не меняют.
    """
    if context['query']:
        return {'seo_noindex': True}
    active = context['filters']['active']
    if context['filters']['selected_count'] == 1 and len(active['topics']) == 1:
        topic = Topic.objects.filter(pk=active['topics'][0]).first()
        if topic and is_known(topic.name):
            return seo.topic_meta(topic.name, _fmt_number(context['total']))
    return {}


def problem_list(request):
    """Умный каталог: один экран, один поиск, восемь фильтров.

    ⚠️ ЭКРАН ОБЪЕДИНЁН С «УМНЫМ ПОИСКОМ» (решение владельца 01.09.2026).
    `/catalog/smart-search/` ведёт сюда постоянным редиректом, пункт
    «Умный поиск» ушёл из шапки: два входа в один банк заставляли человека
    выбирать способ ДО того, как он сформулировал, что ищет.

    Сборка контекста живёт в `_catalog_context`: её же зовёт эндпоинт
    живого состояния фильтров, и страница отличается от него только
    редиректом по номеру задачи.
    """
    query = (request.GET.get('q') or '').strip()
    found_id, missing_id = _numeric_query(query)
    if found_id:
        return redirect('catalog:problem_detail', pk=found_id)
    context = _catalog_context(request, missing_id)
    context.update(_entry_context(request, context))
    visitor, new_visitor = search_log.visitor_for(request)
    # Краулер в журнал поиска не пишется: 25 строк из 30 в первый день
    # журнала были от Amazonbot и Google, а не от людей.
    # ⚠️ ОТЛОЖЕННЫЙ ПОИСК (`deferred`) ЖУРНАЛ НЕ ПИШЕТ: строку запишет запрос
    # скрипта (`log=1`) — уже с настоящим статусом. Куку посетителя ставим
    # сразу: без неё запрос скрипта платить не сможет (`rerank_gate`).
    deferred = context['smart_search_status'] == 'deferred'
    context['search_log_id'] = (None if seo.is_crawler(request) or deferred
                                else search_log.log_search(request, context, visitor))
    context.update(_seo_context(context))
    response = render(request, 'catalog/stol.html', context)
    if new_visitor and (context['search_log_id'] or deferred):
        search_log.remember_visitor(response, visitor)
    response['X-Smart-Search'] = context['smart_search_status']
    response['X-Smart-Search-Ms'] = str(context['smart_search_ms'])
    return response


def _filter_counts(fctx):
    """Числа по вариантам — словарь для скрипта живого обновления.

    Ключи — группы фильтра, значения — «значение варианта → число задач
    под остальными фильтрами». Берётся из уже собранных вариантов, второй
    раз ничего не считается.
    """
    by_key = {g['key']: g for g in fctx['groups']}
    counts = {'topic': {}, 'tag': {}, 'difficulty': {}, 'kind': {},
              'test_type': {}, 'source': {}, 'has_solution': 0,
              'character': {}, 'feature': {}}
    if 'topic' in by_key:
        for block in by_key['topic']['groups']:
            for option in block['options']:
                counts['topic'][option['value']] = option['count']
    if 'tag' in by_key:
        for option in by_key['tag']['tags']['listed']:
            counts['tag'][option['value']] = option['count']
    for key in ('difficulty', 'source', 'character', 'feature'):
        if key in by_key:
            for option in by_key[key]['options']:
                counts[key][option['value']] = option['count']
    if 'kind' in by_key:
        for option in by_key['kind']['options']:
            counts['kind'][option['value']] = option['count']
        for option in by_key['kind']['test_types']:
            counts['test_type'][option['value']] = option['count']
    if 'has_solution' in by_key:
        counts['has_solution'] = by_key['has_solution']['option']['count']
    return counts


def api_filter_state(request):
    """Живое состояние каталога под текущими параметрами. GET, публично.

    Параметры те же, что у страницы (включая `q` и `view`). Ответ — числа
    по вариантам, готовые куски разметки (чипы и список) и адрес, который
    страница поставит в строку браузера. Разметку рисуют те же партиалы,
    что и страница, — из того же контекста.
    """
    context = _catalog_context(request, paid=True)
    # Журнал поиска — только по явной просьбе (`log=1`): иначе каждое
    # нажатие фильтра под тем же запросом было бы новой строкой.
    visitor, new_visitor = search_log.visitor_for(request)
    if request.GET.get(search_log.LOG_PARAM) == '1' and not seo.is_crawler(request):
        context['search_log_id'] = search_log.log_search(request, context, visitor)
    fctx = context['filters']
    response = JsonResponse({
        'total': context['total'],
        'counts': _filter_counts(fctx),
        'selected_count': fctx['selected_count'],
        'chips_html': render_to_string('catalog/_catalog_chips.html',
                                       context, request=request),
        'results_html': render_to_string('catalog/_catalog_results.html',
                                         context, request=request),
        'url': fctx['total_url'],
    })
    response['X-Smart-Search'] = context['smart_search_status']
    response['X-Smart-Search-Ms'] = str(context['smart_search_ms'])
    if new_visitor and context.get('search_log_id'):
        search_log.remember_visitor(response, visitor)
    return response


def smart_search(request):
    """Старый адрес умного поиска. Постоянный редирект в каталог.

    ⚠️ 301, А НЕ 302 (решение владельца): экрана больше нет и не вернётся,
    и поисковые системы с закладками должны узнать об этом один раз.
    Запрос переносим — человек, пришедший по своей же старой ссылке с
    `?q=…`, обязан увидеть результат, а не пустой каталог.
    """
    from django.http import HttpResponsePermanentRedirect

    url = reverse('catalog:problem_list')
    query = (request.GET.get('q') or '').strip()
    if query:
        url += '?' + urlencode({'q': query})
    return HttpResponsePermanentRedirect(url)


# ── Страница задачи ─────────────────────────────────────────────────────────
_TAG_SECTIONS = {}


def _tag_section(tag_name, fallback):
    """Раздел карты для тега: по названию из `topic_map.json`, иначе — раздел
    первой темы задачи. Теги базы с темами не связаны, а карта знает, под
    какой темой стоит тег таксономии; совпало по названию — красим им."""
    if not _TAG_SECTIONS:
        text, _etag = _topic_map_payload()
        for node in json.loads(text).get('nodes', []):
            if node.get('k') == 'tag':
                _TAG_SECTIONS[normalize_topic(node.get('l', ''))] = node.get('g', 'other')
    return _TAG_SECTIONS.get(normalize_topic(tag_name), fallback)


def _catalog_link(**changes):
    """Адрес каталога с одним фильтром — через общий модуль, не склейкой строк."""
    return reverse('catalog:problem_list') + filters.query({}, filters.parse({}), **changes)


def _kind_cloud_label(problem_type):
    if not problem_types.is_test(problem_type):
        return 'Развёрнутая задача'
    label = problem_types.kind_label(problem_type)
    return 'Тест · ' + label if label else 'Тест'


def _clouds(problem, topics, tags, sources):
    """Два ряда облачек-ссылок в каталог. Каждое — только при данных
    (правило нуля); пустой ряд не рисуется."""
    first_section = section_of(topics[0].name) if topics else 'other'
    row1 = [{'kind': 'topic', 'label': t.name, 'section': section_of(t.name),
             'url': _catalog_link(topics=[str(t.pk)])} for t in topics]
    row1 += [{'kind': 'tag', 'label': tag.name,
              'section': _tag_section(tag.name, first_section),
              'url': _catalog_link(tags=[str(tag.pk)])} for tag in tags]

    row2 = []
    d = problem.difficulty or 0
    if d:
        row2.append({'kind': 'diff', 'stars': '★' * d + '☆' * (5 - d),
                     'label': 'сложность %d' % d,
                     'url': _catalog_link(difficulties=[str(d)])})
    if problem.character in dict(filters.CHARACTERS):
        row2.append({'kind': 'char', 'label': dict(filters.CHARACTERS)[problem.character],
                     'url': _catalog_link(character=problem.character)})
    is_test = problem_types.is_test(problem.problem_type)
    kind_changes = {'kind': 'test' if is_test else 'open'}
    if is_test:
        kind_changes['test_type'] = problem_types.test_kind(problem.problem_type)
    row2.append({'kind': 'kind', 'label': _kind_cloud_label(problem.problem_type),
                 'url': _catalog_link(**kind_changes)})
    # ⚠️ Бейджики берут подпись у ВИТРИНЫ (`Problem.features`), а не у
    # фильтра. Это разные словари, и намеренно: «Есть график» на карточке
    # — объединение трёх особенностей, а в фильтре каждая из двенадцати
    # стоит отдельной строкой со своей подписью. Ссылка ведёт по ключу
    # витрины; `filters.parse` разворачивает его в те же три особенности.
    for key in problem.features or ():
        label = enrich_features.CATALOG_VIEW_LABELS.get(key)
        if label:
            row2.append({'kind': 'feat', 'label': label,
                         'url': _catalog_link(features=[key])})
    if sources:
        row2.append({'kind': 'sep'})
        for ref in sources:
            # Чип источника — ссылка на первоисточник в новой вкладке, если
            # адрес есть (решение владельца 17.09.2026); нет — чип без ссылки.
            row2.append({'kind': 'src', 'label': ref.source.name, 'url': source_url(ref)})
    return row1, row2


#: Главная страница источника — когда у привязки своей ссылки нет. Адрес дал
#: владелец 17.09.2026 только для ILE: у SolveHub и Школково ссылка есть у
#: каждой привязки, у МатЭк и «Сборника тестов АА» ссылок нет — чип без ссылки.
SOURCE_HOMEPAGES = (('ILE', 'https://iloveeconomics.ru/'),)


def source_url(ref):
    """Внешний адрес задачи в источнике или ''. Только http(s): адрес приходит
    из данных импорта, а `javascript:` в ссылке — исполняемый код."""
    url = (ref.url or '').strip()
    if url.startswith(('https://', 'http://')):
        return url
    for prefix, home in SOURCE_HOMEPAGES:
        if ref.source.name.startswith(prefix):
            return home
    return ''


def _norm_answer(text):
    return re.sub(r'[\s$,.;:]+', '', (text or '').casefold())


def _solution_block(problem, parts):
    """Ответ и решение — раздельно, по правилам владельца (04.09.2026).

    `problem.answer` → «Ответ:» в шапке; `problem.solution` → тело. Решение
    короче 30 знаков или совпадающее с ответом — это ответ, а не решение
    (случай «Вмешательство — 5», где в решении лежит «1800»).
    `solution_needs_review` по-прежнему прячет решение (и решения пунктов).
    Нет ни того ни другого — кнопки «Показать решение» нет.
    """
    answer = (problem.answer or '').strip()
    solution = '' if problem.solution_needs_review else (problem.solution or '').strip()
    # Аудит P0 «Стола»: пересказ условия в начале срезается, копия условия —
    # это не решение (данные не трогаем, правило действует при показе).
    solution = strip_statement_retell(problem.statement, solution)
    if solution_is_statement_copy(problem.statement, solution):
        solution = ''
    if solution and (len(solution) < 30 or _norm_answer(solution) == _norm_answer(answer)):
        if not answer:
            answer = solution
        solution = ''
    part_rows = []
    for part in parts:
        part_solution = '' if problem.solution_needs_review else (part.solution or '').strip()
        if part.answer or part_solution:
            part_rows.append({'label': part.label, 'answer': part.answer,
                              'solution': part_solution})
    return {'answer': answer, 'solution': solution, 'parts': part_rows,
            'has_any': bool(answer or solution or part_rows)}


#: Строк в ленте «Похожие» и «Мои» рядом с задачей.
RAIL_MAX = 20


def _visible(qs):
    """Шлюз качества для новых выдач «Стола»: то же, что у страницы задачи."""
    return qs.filter(status=Problem.Status.PUBLISHED, needs_quality_review=False,
                     hidden_pending_review=False, content_status=Problem.ContentStatus.OK)


def _rail_response(request, problems, current_id=None):
    """Строки ленты одним ответом: `{rows_html, total}`; статусы — одним запросом."""
    show_status = request.user.is_authenticated
    rows = [render_to_string('catalog/stol/_rail_row.html', {
        'card': card, 'status': card['status'], 'show_status': show_status,
        'current_id': current_id}, request=request) for card in _cards_with_marks(request.user, problems)]
    return JsonResponse({'rows_html': ''.join(rows), 'total': len(rows)})


def api_rail_similar(request, problem_id):
    """«Похожие» для ленты рядом с задачей — нынешний кэш M2M, за шлюзом."""
    problem = _visible_problem(problem_id)
    rows = (_visible(problem.similar_problems.all())
            .prefetch_related('topics', 'parts', 'source_references__source')[:RAIL_MAX])
    return _rail_response(request, rows, current_id=problem.pk)


def api_rail_saved(request):
    """«Мои ★» — сохранённые задачи каталога. Только вход (гостю 401 JSON)."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login'}, status=401)
    saved = (_visible(Problem.objects.filter(saved_by__owner=request.user,
                                             saved_by__is_deleted=False))
             .order_by('-saved_by__created_at').distinct()
             .prefetch_related('topics', 'parts', 'source_references__source')[:RAIL_MAX])
    return _rail_response(request, saved)


NEEDS_HUMAN_TEXT = ('Модель не ставит балл: ход решения нестандартный. Можно '
                    'исправить и отправить снова или открыть решение.')
LIMIT_TEXT = 'Лимит проверок на сегодня исчерпан: завтра снова %d'


def _attempt_view(attempt, can_chat=False):
    """Что нужно партиалу `_attempt_result.html` сверх самой попытки."""
    if attempt.status == 'error':
        return {'css': 'wait', 'word': 'Проверка не удалась', 'sub': attempt.summary,
                'bars': 0, 'confidence_word': '', 'ask': '', 'can_chat': can_chat}
    css = {'ok': 'ok', 'partial': 'part', 'wrong': 'bad'}.get(attempt.verdict, 'wait')
    word = {'ok': 'Верно', 'partial': 'Частично верно', 'wrong': 'Неверно'}.get(
        attempt.verdict, 'Балл не поставлен')
    sub = NEEDS_HUMAN_TEXT if attempt.status == 'needs_human' else attempt.summary
    bars = {'high': 3, 'medium': 2, 'low': 1}.get(attempt.confidence, 1)
    confidence_word = {'high': 'высокая', 'medium': 'средняя', 'low': 'низкая'}.get(
        attempt.confidence, 'низкая')
    ask = ''
    if attempt.first_error_step:
        title = next((s.get('title', '') for s in attempt.steps
                      if s.get('n') == attempt.first_error_step), '')
        ask = 'Объясни, почему в шаге %d ошибка%s' % (
            attempt.first_error_step, (': ' + title) if title else '')
    return {'css': css, 'word': word, 'sub': sub, 'bars': bars,
            'confidence_word': confidence_word, 'ask': ask, 'can_chat': can_chat}


def _json_body(request):
    try:
        return json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return {}


def _visible_problem(pk):
    return get_object_or_404(Problem, pk=pk, status=Problem.Status.PUBLISHED,
                             needs_quality_review=False, hidden_pending_review=False,
                             content_status=Problem.ContentStatus.OK)


def _test_game_or_400(problem_id):
    problem = _visible_problem(problem_id)
    game = testplay.game_of(problem)
    if game is None:
        return problem, None, JsonResponse(
            {'error': 'no_game', 'message': 'У этого теста нет вариантов для проверки.'},
            status=400)
    return problem, game, None


@require_POST
def api_test_check(request, problem_id):
    """Проверка отмеченных вариантов теста: всё или ничего (этап 7.2).

    Гость допускается: попытки считаются в сессии. Ответ —
    `{correct, attempt}`; при неверном ответе начиная с третьей попытки
    (после двух неудач) добавляется `correct_count`: сколько верных, но не
    какие. Верный ответ сбрасывает счётчик, у вошедшего он записывается
    попыткой `CatalogAttempt` с итогом «тест: решено с N-й попытки».
    """
    problem, game, error = _test_game_or_400(problem_id)
    if error:
        return error
    data = _json_body(request)
    raw = data.get('labels') if isinstance(data, dict) else None
    if not isinstance(raw, list) or not raw:
        return JsonResponse({'error': 'empty', 'message': 'Отметьте хотя бы один вариант.'},
                            status=400)
    known = {opt['label'] for opt in game['options']}
    given = {testplay.answer_check.normalize_label(str(x)) for x in raw}
    if not given or not given <= known:
        return JsonResponse({'error': 'labels', 'message': 'Такого варианта нет.'}, status=400)
    attempt = testplay.record_attempt(request.session, problem.pk)
    correct = testplay.check(game, given)
    out = {'correct': correct, 'attempt': attempt}
    if correct:
        testplay.reset_attempts(request.session, problem.pk)
        progress.note_test_result(request.user, problem, first_try=attempt == 1)
        if request.user.is_authenticated:
            CatalogAttempt.objects.create(
                user=request.user, problem=problem, text='',
                status=CatalogAttempt.Status.CHECKED, verdict=CatalogAttempt.Verdict.OK,
                steps=[], summary=testplay.solved_summary(attempt))
    elif attempt + 1 >= testplay.COUNT_FROM_ATTEMPT:
        out['correct_count'] = len(game['correct'])
    return JsonResponse(out)


@require_POST
def api_test_reveal(request, problem_id):
    """Показать ответ: верные метки; счётчик попыток сбрасывается.

    ⚠️ Только вошедшему (24.09.2026, ADR 0129): верный вариант — это ответ.
    Гость проверяет свой выбор («верно / не то»), но правильный вариант не
    получает; интерфейс показывает ему приглашение к регистрации.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login'}, status=403)
    problem, game, error = _test_game_or_400(problem_id)
    if error:
        return error
    testplay.reset_attempts(request.session, problem.pk)
    progress.note_test_revealed(request.user, problem)
    return JsonResponse({'correct_labels': sorted(game['correct'])})


@require_POST
def api_solution(request, problem_id):
    """Полное решение или ответ к одному пункту — только вошедшему (ADR 0129).

    Тело JSON: пусто — полное решение (карточка `_help_solution.html`);
    `{"part": n}` — ответ к n-му пункту из тех, у которых ответ заполнен
    (порядок — как у кнопок «Ответ к какому пункту»). Ответ — `{html}`:
    разметку рисует сервер теми же партиалами, что рисовали её раньше
    внутри страницы. Гостю — 403: интерфейс показывает приглашение.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login'}, status=403)
    problem = _visible_problem(problem_id)
    parts = list(problem.parts.all())
    data = _json_body(request)
    part = data.get('part') if isinstance(data, dict) else None
    if part is None:
        sol = _solution_block(problem, parts)
        if not sol['has_any']:
            return JsonResponse({'error': 'none'}, status=404)
        html = render_to_string('catalog/stol/_help_solution.html',
                                {'sol': sol, 'problem': problem}, request=request)
        return JsonResponse({'html': html})
    answers = [p for p in parts if (p.answer or '').strip()]
    try:
        chosen = answers[int(part)]
    except (TypeError, ValueError, IndexError):
        return JsonResponse({'error': 'part'}, status=400)
    html = render_to_string('catalog/stol/_help_part_answer.html',
                            {'p': chosen, 'index': int(part), 'problem': problem},
                            request=request)
    return JsonResponse({'html': html})


@require_POST
def api_progress(request, problem_id):
    """«Как прошло?» и следы помощи (каталог «Стол», ADR 0119). Только вход.

    Тело JSON: `status` (`self` | `hint` | `failed` | `null`), `hints_opened`,
    `solution_viewed`. Гостю 401 JSON; задача за шлюзом — 404; «решил сам»
    после открытого решения — 400 с текстом. Правила — `catalog/progress.py`.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login'}, status=401)
    problem = _visible_problem(problem_id)
    try:
        data = _json_body(request)
        row = progress.update(request.user, problem, data if isinstance(data, dict) else {})
    except progress.ProgressError as exc:
        return JsonResponse({'error': 'progress', 'message': str(exc)}, status=400)
    return JsonResponse(progress.as_json(row))


@require_POST
def api_attempt_file(request):
    """Фото или файл к будущей попытке (этап 6.2). Только вход.

    Один файл на запрос: jpg/png/webp/pdf до 10 МБ, не больше трёх на
    попытку (`pending` — id уже загруженных). Хранится `FileAsset` вида
    «работа ученика», к попытке привязывается при отправке решения.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login', 'message': 'Войдите, чтобы прикрепить файл.'},
                            status=403)
    pending = [x for x in (request.POST.get('pending') or '').split(',') if x.strip().isdigit()]
    if len(pending) >= attachments.MAX_FILES:
        return JsonResponse({'error': 'many', 'message': attachments.TOO_MANY}, status=400)
    if attachments.uploads_today(request.user) >= attachments.UPLOADS_PER_DAY:
        return JsonResponse({'error': 'many', 'message': attachments.TOO_MANY_TODAY},
                            status=429)
    uploaded = request.FILES.get('file')
    media_type, error = attachments.validate_upload(uploaded)
    if error:
        return JsonResponse({'error': 'file', 'message': error}, status=400)
    asset = FileAsset.objects.create(file=uploaded, kind=FileAsset.Kind.STUDENT_WORK,
                                     caption=(uploaded.name or '')[:300],
                                     uploaded_by=request.user)
    return JsonResponse({'id': asset.pk, 'name': asset.caption, 'kind': media_type})


@require_POST
def api_attempt(request):
    """Отправить решение на проверку ИИ (этап 5, ADR 0079).

    Только для вошедших: анониму страница показывает ссылку на вход вместо
    кнопки. Проверка идёт синхронно; `AiUnavailable` — это 200 с человеческим
    сообщением, а не ошибка сервера: ключа нет, лимит, таймаут — всё это
    штатные состояния, о которых ученику надо сказать словами.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login',
                             'message': 'Войдите, чтобы отправить решение на проверку.'},
                            status=403)
    data = _json_body(request)
    try:
        problem = _visible_problem(int(data.get('problem_id') or 0))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'problem', 'message': 'Задача не указана.'}, status=400)
    text = (data.get('text') or '').strip()
    raw_ids = data.get('file_ids') or []
    if not isinstance(raw_ids, list) or len(raw_ids) > attachments.MAX_FILES:
        return JsonResponse({'error': 'many', 'message': attachments.TOO_MANY}, status=400)
    file_ids = [int(x) for x in raw_ids if str(x).isdigit()]
    files = list(FileAsset.objects.filter(pk__in=file_ids, uploaded_by=request.user,
                                          kind=FileAsset.Kind.STUDENT_WORK)) if file_ids else []
    if len(files) != len(set(file_ids)):
        return JsonResponse({'error': 'file', 'message': 'Файл не найден: прикрепите его заново.'},
                            status=400)
    if not text and not files:
        return JsonResponse({'error': 'empty',
                             'message': 'Напишите решение или приложите фото, прежде чем отправлять.'},
                            status=400)
    if len(text) > 20000:
        return JsonResponse({'error': 'long',
                             'message': 'Слишком длинный текст: сократите решение.'}, status=400)
    if not ai.is_available():
        return JsonResponse({'error': 'no_key', 'message': ai.unavailable_reason()})
    if ai.remaining_today(request.user) <= 0:
        return JsonResponse({'error': 'limit', 'message': LIMIT_TEXT % ai.daily_limit()})

    attempt = CatalogAttempt.objects.create(
        user=request.user, problem=problem, text=text,
        solution_viewed_before=bool(data.get('solution_viewed_before')))
    if files:
        attempt.files.set(files)
    try:
        if files:
            # Сначала текст с фото, потом проверка по тексту и распознанному.
            attachments.recognise_attempt(attempt, request.user)
            attempt.save(update_fields=['ocr_text'])
        attempts.check_attempt(attempt, request.user)
    except ai.AiUnavailable as exc:
        attempt.status = CatalogAttempt.Status.ERROR
        attempt.summary = str(exc)[:300]
        attempt.save(update_fields=['status', 'summary'])
        message = LIMIT_TEXT % ai.daily_limit() if exc.kind == 'limit' else str(exc)
        return JsonResponse({'error': exc.kind, 'message': message, 'attempt_id': attempt.pk})

    html = render_to_string('catalog/_attempt_result.html',
                            {'attempt': attempt,
                             'chk': _attempt_view(attempt, can_chat=chat.is_available())},
                            request=request)
    return JsonResponse({'attempt_id': attempt.pk, 'status': attempt.status, 'html': html,
                         'remaining': ai.remaining_today(request.user)})


@require_POST
def api_chat(request):
    """Одна реплика помощника по задаче (ADR 0080, решение владельца 15.09.2026).

    Только вход. `mode` — режим реплики (`free`, `theory`, `method`, `check`),
    `attachment_id` — СВОЁ вложение к ЭТОЙ задаче, `thread` — номер разговора
    вкладки. История приходит от клиента, каждая реплика пишется в `ChatTurn`
    (`chat.answer`), лимит обращений общий с проверкой. `AiUnavailable` —
    человеческое сообщение в чате, а не ошибка сервера.
    """
    import uuid

    from problems.models_platform import ChatAttachment

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login', 'reply': 'Войдите, чтобы спросить помощника.'},
                            status=403)
    data = _json_body(request)
    try:
        problem = _visible_problem(int(data.get('problem_id') or 0))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'problem', 'reply': 'Задача не указана.'}, status=400)
    mode = data.get('mode') if data.get('mode') in chat.MODES else 'free'
    # `attachment_ids` — до трёх файлов (18.09.2026); старый `attachment_id`
    # по-прежнему понимается: открытые вкладки со старым скриптом живут до вечера.
    raw_ids = data.get('attachment_ids')
    if raw_ids is None and data.get('attachment_id') is not None:
        raw_ids = [data.get('attachment_id')]
    if not isinstance(raw_ids, list):
        raw_ids = []
    if len(raw_ids) > chat.FILES_PER_TURN:
        return JsonResponse({'error': 'files', 'reply': chat.TOO_MANY_FILES}, status=400)
    wanted = [int(str(i)) if str(i).isdigit() else 0 for i in raw_ids]
    # Номер из запроса — не право: только свои вложения и только к этой задаче.
    found = {a.pk: a for a in ChatAttachment.objects.filter(
        pk__in=wanted, user=request.user, problem=problem)}
    if len(found) != len(set(wanted)):
        return JsonResponse({'error': 'file', 'reply': 'Файл не найден: прикрепите его заново.'},
                            status=400)
    attachments = [found[pk] for pk in dict.fromkeys(wanted)]
    quote = str(data.get('quote') or '').strip()
    if len(quote) > chat.QUOTE_MAX:
        return JsonResponse({'error': 'quote', 'reply': 'Слишком длинный фрагмент: выделите короче.'},
                            status=400)
    # Откуда цитата: условие или ответ помощника («Ответить», 24.09.2026).
    quote_source = data.get('quote_source') or 'statement'
    if quote_source not in chat.QUOTE_SOURCES:
        return JsonResponse({'error': 'quote_source', 'reply': 'Непонятно, откуда цитата.'},
                            status=400)
    message = str(data.get('message') or '').strip()
    if not message:
        return JsonResponse({'error': 'empty',
                             'reply': chat.CHECK_EMPTY_TEXT if mode == 'check' else 'Напишите вопрос.'},
                            status=400)
    if len(message) > chat.MESSAGE_MAX:
        return JsonResponse({'error': 'long', 'reply': 'Слишком длинный вопрос: сократите его.'},
                            status=400)
    if not chat.is_available():
        return JsonResponse({'error': 'no_key', 'reply': 'Помощник сейчас выключен.'})
    try:
        thread = uuid.UUID(str(data.get('thread') or ''))
    except ValueError:
        thread = None
    last_attempt = CatalogAttempt.objects.filter(user=request.user, problem=problem)
    since = progress.reset_at(request.user, problem)
    if since:
        # После «Решить заново» прежняя попытка — не часть нового разговора.
        last_attempt = last_attempt.filter(created_at__gt=since)
    last_attempt = last_attempt.order_by('-created_at').first()
    try:
        reply = chat.answer(problem, message, data.get('history'), request.user,
                            last_attempt=last_attempt, mode=mode, attachments=attachments,
                            thread=thread, quote=quote, quote_source=quote_source)
    except ai.AiUnavailable as exc:
        # Дневной денежный потолок чата и суточный лимит обращений — оба «limit»,
        # а сказать ученику надо разное.
        if exc.kind == 'limit' and ai.budget_exceeded(chat.PROFILE):
            return JsonResponse({'error': 'budget', 'reply': chat.BUDGET_TEXT})
        message_text = LIMIT_TEXT % ai.daily_limit() if exc.kind == 'limit' else str(exc)
        return JsonResponse({'error': exc.kind, 'reply': message_text})
    answer = {'reply': reply, 'remaining': ai.remaining_today(request.user)}
    note = chat.pages_note(attachments)
    if note:
        answer['note'] = note
    return JsonResponse(answer)


@require_POST
def api_chat_upload(request):
    """Фото или PDF решения к реплике чата (решение владельца 15.09.2026). Только вход.

    Один файл на запрос: jpg/png/webp/pdf до 10 МБ — та же проверка, что у
    файла к попытке (`attachments.validate_upload`: расширение, сигнатура PDF,
    картинка открывается Pillow); не больше 10 файлов в сутки на человека. PDF
    сразу раскладывается на картинки для модели, большая картинка уменьшается
    (`chat.save_attachment`). Наружу файл не отдаётся никому.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login', 'message': 'Войдите, чтобы прикрепить файл.'},
                            status=403)
    try:
        problem = _visible_problem(int(request.POST.get('problem_id') or 0))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'problem', 'message': 'Задача не указана.'}, status=400)
    if chat.uploads_today(request.user) >= chat.UPLOADS_PER_DAY:
        return JsonResponse({'error': 'many', 'message': chat.TOO_MANY_UPLOADS}, status=429)
    uploaded = request.FILES.get('file')
    media_type, error = attachments.validate_upload(uploaded)
    if error:
        return JsonResponse({'error': 'file', 'message': error}, status=400)
    name = (uploaded.name or '')[:80]
    try:
        attachment = chat.save_attachment(uploaded, media_type, request.user, problem,
                                          name=name)
    except ValueError as exc:
        return JsonResponse({'error': 'file', 'message': str(exc)}, status=400)
    return JsonResponse({'id': attachment.pk, 'name': name, 'mime': media_type,
                         'pages': attachment.pages,
                         'url': reverse('catalog:chat_attachment', args=[attachment.pk])})


#: Сколько реплик отдаёт история чата — последние, удачные.
CHAT_HISTORY_MAX = 200


def api_chat_history(request, problem_id):
    """История СВОЕГО разговора по ЭТОЙ задаче: удачные реплики по времени.

    ⚠️ ВСЯ ИСТОРИЯ, А НЕ ПОСЛЕДНИЕ 20 (24.09.2026): длинный разговор после
    перезагрузки обрывался на середине. Предел — CHAT_HISTORY_MAX (200), от
    самых новых; отдаются в хронологическом порядке, с цитатами. После
    «Решить заново» — только реплики новее сброса. Гостю 401; чужие реплики
    не отдаются никогда."""
    from problems.models_platform import ChatTurn, ProblemProgress

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login'}, status=401)
    turns = (ChatTurn.objects.filter(user=request.user, problem_id=problem_id, error='')
             .exclude(reply='').prefetch_related('attachments'))
    since = (ProblemProgress.objects.filter(user=request.user, problem_id=problem_id)
             .values_list('reset_at', flat=True).first())
    if since:
        turns = turns.filter(created_at__gt=since)
    turns = turns.order_by('-created_at', '-pk')[:CHAT_HISTORY_MAX]
    return JsonResponse({'turns': [
        {'message': t.user_text, 'reply': t.reply, 'mode': t.mode,
         'quote': t.quote, 'quote_source': t.quote_source,
         'ts': t.created_at.isoformat(),
         'attachments': [{'id': a.pk, 'name': a.name, 'mime': a.mime,
                          'url': reverse('catalog:chat_attachment', args=[a.pk])}
                         for a in t.attachments.all()]}
        for t in reversed(list(turns))]})


def _has_chat(user, problem, since=None):
    """Есть ли у человека удачные реплики чата по задаче (после сброса)."""
    from problems.models_platform import ChatTurn

    if not getattr(user, 'is_authenticated', False):
        return False
    turns = ChatTurn.objects.filter(user=user, problem=problem, error='').exclude(reply='')
    if since:
        turns = turns.filter(created_at__gt=since)
    return turns.exists()


@require_POST
def api_progress_reset(request, problem_id):
    """«Решить заново» (решение владельца 24.09.2026, ADR 0130). Только вход.

    Чистит экран ученика: подсказки, «смотрел решение», статус, чат и
    попытки на экране. У репетитора в статистике — как было; в базе не
    удаляется ничего (`catalog/progress.reset`). Повтор безопасен.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login'}, status=403)
    problem = _visible_problem(problem_id)
    row = progress.reset(request.user, problem)
    return JsonResponse(progress.as_json(row))


def _ordered_hints(problem):
    """Подсказки задачи по уровням: сначала общие, потом к подпунктам."""
    hints = list(problem.hints.select_related('part').order_by('order', 'pk'))
    general = [h for h in hints if h.part_id is None]
    by_part = [h for h in hints if h.part_id is not None]
    by_part.sort(key=lambda h: (h.part.order, h.part.label, h.order, h.pk))
    return general + by_part


def _hint_view(n, hint, total):
    """Подсказка для ленты помощи — одна форма у ответа API и у перезагрузки."""
    return {
        'n': n, 'total': total, 'text': hint.text,
        'ai': hint.generated_by_ai, 'reviewed': hint.reviewed,
        'part': (hint.part.label or '').strip().rstrip(').') if hint.part_id else '',
    }


def api_hint(request, problem_id, n):
    """Подсказка номер `n` (с единицы) к видимой задаче; за пределом — 404.

    Подсказки — часть задачи, как решение: доступны без входа. Порядок —
    поле `order`; подсказки к подпунктам идут после общих с пометкой пункта.
    """
    problem = _visible_problem(problem_id)
    hints = _ordered_hints(problem)
    if n < 1 or n > len(hints):
        raise Http404('такой подсказки нет')
    progress.note_hint(request.user, problem, n)
    return JsonResponse(_hint_view(n, hints[n - 1], len(hints)))


def _neighbours(request, problem, similar_rows):
    """Позиция задачи и соседи по выдаче — для строки «3 из 506» и «Дальше».

    Выдача без запроса — это фильтры адреса, упорядоченные по `-id`, как у
    входа: считается двумя запросами без поиска. С запросом `q` порядок задаёт
    смысловой поиск (секунды), и повторять его ради соседей нельзя — тогда
    соседей и позицию считает сценарий по своему списку строк. Без выдачи
    (прямая ссылка без фильтров) «следующая» — первая похожая.
    """
    active = filters.parse(request.GET)
    if active['q']:
        return {'position': None, 'total': None, 'prev': None, 'next': None, 'from': 'client'}
    if not filters.is_empty(active):
        qs = filters.apply(filters.base_queryset('catalog'), active).distinct()
        if qs.filter(pk=problem.pk).exists():
            before = qs.filter(pk__gt=problem.pk)
            prev = before.order_by('id').values_list('id', flat=True).first()
            nxt = qs.filter(pk__lt=problem.pk).order_by('-id').values_list('id', flat=True).first()
            return {'position': before.count() + 1, 'total': qs.count(),
                    'prev': prev, 'next': nxt, 'from': 'filters'}
    nxt = similar_rows[0].pk if similar_rows else None
    return {'position': None, 'total': None, 'prev': None, 'next': nxt, 'from': 'similar'}


def _neighbour_titles(meta):
    """Названия соседей для кнопок «← предыдущая / следующая →» (README §3)."""
    ids = [pk for pk in (meta['prev'], meta['next']) if pk]
    titles = {}
    for p in _visible(Problem.objects.filter(pk__in=ids)):
        card = _card(p)
        titles[p.pk] = card['title_display'] if card['show_title'] else card['preview']
    return {'prev_title': titles.get(meta['prev'], ''), 'next_title': titles.get(meta['next'], '')}


def _problem_context(request, problem):
    """Всё, что рисуют партиалы задачи «Стола» (`stol/_stol_center.html`,
    `stol/_stol_help.html`) — и при прямой ссылке, и в ответе `?pane=1`.

    Заголовок — только если это название, а не обрезок условия; номер задачи
    нигде, кроме адреса. Всё на экране — из данных (правило нуля): нет тегов —
    нет «Теги · N», нет сложности — нет звёзд, нет решения и ответа — нет кнопки.
    """
    topics = [t for t in problem.topics.all() if is_known(t.name)]
    tags = list(problem.tags.all())
    sources = list(problem.source_references.select_related('source').all())
    parts = list(problem.parts.all())
    title = (problem.title or '').strip()
    show_title = bool(title) and not looks_like_statement_cut(title, problem.statement)
    heading = title if show_title else ('Задача: ' + topics[0].name if topics else 'Задача')
    row1, row2 = _clouds(problem, topics, tags, sources)

    saved = False
    if request.user.is_authenticated:
        from problems.models_platform import SavedProblem
        saved = SavedProblem.objects.filter(owner=request.user, catalog_problem=problem,
                                            is_deleted=False).exists()

    # Проверка ИИ: кнопка — только при доступной модели и только для вошедших
    # (правило нуля: без ключа её нет вовсе).
    ai_available = ai.is_available()
    last_attempt = None
    since = progress.reset_at(request.user, problem)
    if ai_available and request.user.is_authenticated:
        last_attempt = (CatalogAttempt.objects
                        .filter(user=request.user, problem=problem)
                        .exclude(status=CatalogAttempt.Status.ERROR))
        if since:
            # «Решить заново»: экран — как у новой задачи (ADR 0130).
            last_attempt = last_attempt.filter(created_at__gt=since)
        last_attempt = last_attempt.order_by('-created_at').first()
    hint_total = len(_ordered_hints(problem))
    game = testplay.game_of(problem, parts)
    test = _test_context(problem, game, topics) if game else None
    cfg = {'problemId': problem.pk}
    if test:
        cfg['test'] = {
            'checkUrl':  reverse('catalog:api_test_check', args=[problem.pk]),
            'revealUrl': reverse('catalog:api_test_reveal', args=[problem.pk]),
            'multi':     game['multi'],
            'labels':    [opt['label'] for opt in game['options']],
        }
    if hint_total:
        cfg['hintUrl'] = reverse('catalog:api_hint', args=[problem.pk, 1])[:-2]
        cfg['hintTotal'] = hint_total
    # Решение и ответы — запросом и только вошедшему (ADR 0129); гостю вместо
    # них приглашение (`help-invite-tpl`).
    if request.user.is_authenticated:
        cfg['solutionUrl'] = reverse('catalog:api_solution', args=[problem.pk])
    else:
        cfg['guest'] = True
    if ai_available:
        cfg['attemptUrl'] = reverse('catalog:api_attempt')
        if request.user.is_authenticated:
            # Файлы принимаются только от вошедших: гостю адрес не нужен.
            cfg['fileUrl'] = reverse('catalog:api_attempt_file')
            cfg['maxFiles'] = attachments.MAX_FILES
    # Чат живёт на своём поставщике (решение 15.09.2026): его карточка и кнопки,
    # которые в него пишут, зависят от чата, а не от модели проверки.
    chat_available = chat.is_available()
    # Строка лимита (решение владельца 24.09.2026): счётчик ОБЩИЙ на все
    # обращения к ИИ — и проверку, и чат, поэтому считается и тогда, когда
    # доступен только чат. Видна при остатке ≤ `LIMIT_WARN_AT`.
    remaining = (ai.remaining_today(request.user)
                 if (ai_available or chat_available) and request.user.is_authenticated else 0)
    cfg['limitWarnAt'] = ai.LIMIT_WARN_AT
    if chat_available:
        cfg['chatUrl'] = reverse('catalog:api_chat')
        cfg['chatCheckEmpty'] = chat.CHECK_EMPTY_TEXT
        if request.user.is_authenticated:
            cfg['chatUploadUrl'] = reverse('catalog:api_chat_upload')
            cfg['chatHistoryUrl'] = reverse('catalog:api_chat_history', args=[problem.pk])

    # Лента «Похожие» рисуется сервером — прямая ссылка работает без скрипта.
    similar_rows = list(_visible(problem.similar_problems.all())
                        .prefetch_related('topics', 'parts', 'source_references__source')
                        [:RAIL_MAX])
    my_progress = None
    if request.user.is_authenticated:
        from problems.models_platform import ProblemProgress
        my_progress = ProblemProgress.objects.filter(user=request.user, problem=problem).first()
        cfg['progressUrl'] = reverse('catalog:api_progress', args=[problem.pk])
        cfg['resetUrl'] = reverse('catalog:api_progress_reset', args=[problem.pk])
    # «Как прошло?» — не у тестов (статус ставит сам тест) и не у учителя.
    # У репетитора блока «Как прошло?» нет (README §7).
    show_how = request.user.is_authenticated and not game and not _is_tutor(request.user)
    meta = _neighbours(request, problem, similar_rows)
    meta.update(_neighbour_titles(meta))

    # Панель помощи (README §4) переживает перезагрузку: открытые подсказки и
    # факт открытого решения — из прогресса ученика, разговор — из `ChatTurn`.
    hints = _ordered_hints(problem) if hint_total else []
    opened = min(my_progress.hints_opened, hint_total) if my_progress else 0
    opened_hints = [_hint_view(n, hint, hint_total) for n, hint in enumerate(hints[:opened], 1)]
    sol = _solution_block(problem, parts)
    # Ступень «Ответ по одному пункту» — только при ответах в данных (решение 17.09).
    part_answers = ([{'label': part.label, 'answer': part.answer} for part in parts
                     if (part.answer or '').strip()] if not game else [])

    return {
        'problem':      problem,
        'similar_cards': _cards_with_marks(request.user, similar_rows),
        'my_progress':  my_progress,
        'show_how':     show_how,
        'ai_available': ai_available,
        'chat_available': chat_available,
        'hint_total':   hint_total,
        'test':         test,
        'remaining':    remaining,
        'limit_warn_at': ai.LIMIT_WARN_AT,
        'last_attempt': last_attempt,
        'last_chk':     (_attempt_view(last_attempt, can_chat=chat_available)
                         if last_attempt else None),
        'task_cfg':     cfg,
        'parts':        parts,
        'is_test':      problem_types.is_test(problem.problem_type),
        'heading':      heading,
        'show_title':   show_title,
        'clouds_1':     row1,
        'tags_total':   sum(1 for c in row1 if c['kind'] == 'tag'),
        'clouds_2':     row2,
        'sol':          sol,
        'saved':        saved,
        'meta':         meta,
        'opened_hints': opened_hints,
        'hints_left':   hint_total - opened,
        'next_hint':    opened + 1,
        'solution_viewed': bool(my_progress and my_progress.solution_viewed and sol['has_any']),
        'part_answers': part_answers,
        # Приглашение гостю: вход и регистрация с возвратом на эту задачу.
        'login_next_url': '%s?%s' % (reverse('login'), urlencode(
            {'next': reverse('catalog:problem_detail', args=[problem.pk])})),
        'register_next_url': '%s?%s' % (reverse('register'), urlencode(
            {'next': reverse('catalog:problem_detail', args=[problem.pk])})),
        # Лестница пуста, только пока человек ничем не пользовался. Реплики чата
        # тоже в счёт (24.09.2026): у кого разговор уже есть, стартовый блок не
        # мелькает до прихода истории.
        'help_used':    bool(opened or (my_progress and my_progress.solution_viewed) or last_attempt
                             or _has_chat(request.user, problem, since)),
        'teacher_assignments': _teacher_assignments(request), 'is_tutor': _is_tutor(request.user),
        # Как эту задачу решают в игре (строка под условием и в тесте).
        'game_stat':    _game_stat(problem.pk),
    }


def problem_detail(request, pk):
    """Задача на экране «Стол»: прямая ссылка — весь экран, `?pane=1` — панель.

    Прямая ссылка рисует `catalog/stol.html` в виде `stol` целиком на сервере
    (работает без скрипта). `?pane=1` отдаёт JSON с теми же партиалами центра и
    помощи — им сценарий `stol.js` подменяет задачу без перезагрузки (решение
    владельца 18.09.2026: клик со входа и любая смена задачи — на месте).
    Шлюз качества один на оба ответа: скрытая задача — 404.
    """
    problem = get_object_or_404(Problem, pk=pk, status=Problem.Status.PUBLISHED,
                                needs_quality_review=False,
                                hidden_pending_review=False, content_status=Problem.ContentStatus.OK)

    # ⚠️ Квота РАЗНЫХ задач (24.09.2026, ADR 0129, `catalog/scrape_guard.py`):
    # выгрузка банка подряд упирается здесь, человек её не замечает.
    from . import scrape_guard
    if scrape_guard.check(request, problem.pk):
        if request.GET.get('pane') == '1':
            return JsonResponse({'error': 'scrape'}, status=429)
        return render(request, '429.html', status=429)

    # Учебное событие и прогресс: задачу открыли — и прямой ссылкой, и на месте.
    # Записи неблокирующие (problems/event_log.py, catalog/progress.py).
    from problems.event_log import log_problem_event
    log_problem_event('catalog', 'opened', request.user, problem, request=request)
    progress.note_opened(request.user, problem)

    context = _problem_context(request, problem)
    if request.GET.get('pane') == '1':
        meta = context['meta']
        return JsonResponse({
            'id': problem.pk,
            'title': context['heading'],
            'url': reverse('catalog:problem_detail', args=[problem.pk]),
            'center_html': render_to_string('catalog/stol/_stol_center.html', context, request=request),
            'help_html': render_to_string('catalog/stol/_stol_help.html', context, request=request),
            'similar_html': render_to_string('catalog/stol/_stol_similar_rows.html', context, request=request),
            'meta': {'position': meta['position'], 'total': meta['total'],
                     'prev': meta['prev'], 'next': meta['next'],
                     'saved': context['saved'],
                     'status': context['my_progress'].status if context['my_progress'] else '',
                     'is_test': bool(context['test'])},
        })
    context['view'] = 'stol'
    context.update(seo.problem_meta(problem, context['heading']))
    return render(request, 'catalog/stol.html', context)


def _test_context(problem, game, topics):
    """Блок игры теста для шаблона (этап 7.3): варианты, правило, ссылки.

    «Ещё тест по этой теме» — только если по первой теме задачи есть другой
    видимый тест; «Почему так» — только при решении (правило нуля).
    """
    more_url = ''
    if topics:
        active = filters.parse({'type': 'test', 'topic': str(topics[0].pk)})
        others = (filters.apply(filters.base_queryset('catalog'), active)
                  .exclude(pk=problem.pk).exists())
        if others:
            more_url = reverse('catalog:random_problem') + '?' + urlencode(
                {'type': 'test', 'topic': topics[0].pk, 'exclude': problem.pk})
    return {
        'multi':    game['multi'],
        'rule':     game['rule'],
        'options':  game['options'],
        'more_url': more_url,
        # «Почему так» — без разбалловки жюри и без повтора верного варианта
        # (README §5; оба среза только при показе, данные не трогаем).
        'expl':     strip_correct_repeat(strip_score_tails(problem.solution), game),
        'stat':     _game_stat(problem.pk),
    }


def _game_stat(problem_id):
    """Статистика задачи в игре — мягко, без жёсткой связи каталога с игрой.

    Приложение `game` может быть выключено или его таблиц может не быть на
    свежей базе: страница задачи из-за этого падать не должна."""
    try:
        from game.stats import problem_stat_summary
        return problem_stat_summary(problem_id)
    except Exception:
        return None


# ── Конструктор подборок (Этап Б1) ─────────────────────────────────────────

def _canonical_topics():
    return sorted(
        Topic.objects.filter(name__in=CANONICAL),
        key=lambda t: CANONICAL.index(t.name),
    )


#: Больше задач в одной подборке не бывает (24.09.2026, ADR 0129): подборка —
#: лист для урока, а не выгрузка банка.
COLLECTION_MAX = 50
#: Выгрузок подборки С ОТВЕТАМИ ИЛИ РЕШЕНИЯМИ в сутки на аккаунт.
EXPORTS_WITH_ANSWERS_PER_DAY = 20


def _answers_export_refusal(request, show_answers, show_solutions):
    """Ответ-отказ, если выгрузка с ответами/решениями нельзя, иначе None.

    ⚠️ ЗАЧЕМ (24.09.2026). Подборка анонимна (по ссылке), а `.tex` с флагами
    `show_answers`/`show_solutions` отдавал ответы и решения всем — это та же
    выгрузка банка, что и страница задачи. Теперь: только вошедшему и не
    больше 20 выгрузок в сутки на аккаунт (счётчик в кэше, до конца суток).
    Условия без ответов — как раньше, всем.
    """
    if not (show_answers or show_solutions):
        return None
    if not request.user.is_authenticated:
        return HttpResponse('Ответы и решения в файле – после входа на сайт.',
                            status=403, content_type='text/plain; charset=utf-8')
    from datetime import timedelta
    from django.core.cache import cache
    from django.utils import timezone

    now = timezone.localtime(timezone.now())
    ttl = int(((now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
               - now).total_seconds()) + 3600
    key = 'colexp:%s:%s' % (now.strftime('%Y%m%d'), request.user.pk)
    if not cache.add(key, 1, ttl):
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, ttl)
            count = 1
        if count > EXPORTS_WITH_ANSWERS_PER_DAY:
            return HttpResponse('На сегодня выгрузок с ответами достаточно: '
                                'попробуйте завтра.', status=429,
                                content_type='text/plain; charset=utf-8')
    return None


def collection_new(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip() or 'Моя подборка'
        template_type = request.POST.get('template_type', Collection.HOMEWORK)
        if template_type not in (Collection.HOMEWORK, Collection.TEST, Collection.SHEET):
            template_type = Collection.HOMEWORK
        col = Collection.objects.create(name=name, template_type=template_type)
        return redirect('catalog:collection_detail', token=col.token)
    return render(request, 'catalog/collection_new.html', {})


@require_POST
def collection_from_basket(request):
    """Корзина репетитора → подборка → существующий конструктор (README §7).

    Только репетитору; остальным адреса «нет» (404). Задачи — в порядке
    корзины, за шлюзом качества; не прошедшие называются в `refused`. Сборку
    PDF здесь не трогаем: конструктор тот же (карточка Notion …8154).
    """
    if not _is_tutor(request.user):
        raise Http404('Нет такой страницы')
    try:
        raw = json.loads(request.body).get('problem_ids')
    except (ValueError, AttributeError):
        raw = None
    from teacher.views import BASKET_MAX
    if not isinstance(raw, list) or not raw or len(raw) > BASKET_MAX:
        return JsonResponse({'error': 'problem_ids required'}, status=400)
    wanted = list(dict.fromkeys(int(i) for i in raw if str(i).isdigit()))
    visible = set(_visible(Problem.objects.filter(pk__in=wanted)).values_list('pk', flat=True))
    order = [pk for pk in wanted if pk in visible]
    if not order:
        return JsonResponse({'error': 'empty', 'refused': wanted}, status=400)
    if len(order) > COLLECTION_MAX:
        return JsonResponse({'error': 'many', 'message': 'В подборке не больше %d задач.'
                             % COLLECTION_MAX}, status=400)
    collection = Collection.objects.create(name='Из корзины каталога', author=request.user,
                                           template_type=Collection.HOMEWORK, problem_order=order)
    collection.problems.add(*order)
    return JsonResponse({'ok': True, 'url': reverse('catalog:collection_detail', args=[collection.token]),
                         'refused': [pk for pk in wanted if pk not in visible]})


def collection_detail(request, token):
    collection = get_object_or_404(Collection, token=token)

    # Каталог с теми же фильтрами что в problem_list (+ оба шлюза)
    qs = Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                needs_quality_review=False,
                                hidden_pending_review=False, content_status=Problem.ContentStatus.OK)
    f_q      = request.GET.get('q', '').strip()
    f_topic  = request.GET.get('topic', '').strip()
    f_diff   = request.GET.get('difficulty', '').strip()
    f_source = request.GET.get('source', '').strip()

    if f_q:
        qs = qs.filter(Q(statement__icontains=f_q) | Q(title__icontains=f_q))
    if f_topic:
        qs = qs.filter(topics__id=f_topic)
    if f_diff:
        qs = qs.filter(difficulty=f_diff)
    if f_source:
        qs = qs.filter(source_references__source_id=f_source)

    qs = qs.prefetch_related('topics').order_by('-id').distinct()

    paginator = Paginator(qs, 15)
    page_obj  = paginator.get_page(request.GET.get('page', 1))

    # Задачи подборки в нужном порядке (шлюз: как в экспорте — скрываем)
    added_ids = set(collection.problems.values_list('id', flat=True))
    order_map = {pid: i for i, pid in enumerate(collection.problem_order)}
    coll_problems = sorted(
        collection.problems.filter(needs_quality_review=False,
                                   hidden_pending_review=False, content_status=Problem.ContentStatus.OK)
        .prefetch_related('topics'),
        key=lambda p: order_map.get(p.pk, 9999),
    )

    # Карточки каталога с флагом «уже в подборке»
    catalog_cards = []
    for p in page_obj:
        raw     = _strip_latex(p.statement)
        preview = raw[:120] + ('…' if len(raw) > 120 else '')
        d       = p.difficulty or 0
        catalog_cards.append({
            'problem':          p,
            'preview':          preview,
            'topics':           list(p.topics.all())[:2],
            'difficulty_stars': range(d),
            'difficulty_empty': range(5 - d),
            'in_collection':    p.pk in added_ids,
        })

    sources = (
        Source.objects
        .filter(references__problem__status=Problem.Status.PUBLISHED)
        .distinct()
        .order_by('name')
    )

    qp = request.GET.copy()
    qp.pop('page', None)

    context = {
        'collection':     collection,
        'coll_problems':  coll_problems,
        'added_ids_json': json.dumps(list(added_ids)),
        'page_obj':       page_obj,
        'catalog_cards':  catalog_cards,
        'total':          paginator.count,
        'page_range':     _page_range(page_obj),
        'base_query':     qp.urlencode(),
        'topics':         _canonical_topics(),
        'sources':        sources,
        'f_q':            f_q,
        'f_topic':        f_topic,
        'f_diff':         f_diff,
        'f_source':       f_source,
    }
    return render(request, 'catalog/collection_detail.html', context)


def _parse_problem_id(request):
    """Достаём problem_id из JSON-тела или form-data."""
    try:
        data = json.loads(request.body)
        return int(data.get('problem_id', 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        try:
            return int(request.POST.get('problem_id', 0))
        except (ValueError, TypeError):
            return 0


@require_POST
def collection_add(request, token):
    collection  = get_object_or_404(Collection, token=token)
    problem_id  = _parse_problem_id(request)
    # ⚠️ (24.09.2026) Шлюз страницы задачи, а не «опубликована»: иначе в
    # подборку попадала скрытая и непроверенная задача и уезжала в `.tex`.
    problem     = _visible_problem(problem_id)
    if (problem.pk not in collection.problem_order
            and collection.problems.count() >= COLLECTION_MAX):
        return JsonResponse({'status': 'error', 'error': 'many',
                             'message': 'В подборке не больше %d задач.' % COLLECTION_MAX},
                            status=400)
    collection.problems.add(problem)
    if problem_id not in collection.problem_order:
        collection.problem_order.append(problem_id)
        collection.save(update_fields=['problem_order', 'updated_at'])
    return JsonResponse({'status': 'ok', 'count': collection.problems.count()})


@require_POST
def collection_remove(request, token):
    collection = get_object_or_404(Collection, token=token)
    problem_id = _parse_problem_id(request)
    collection.problems.remove(problem_id)
    collection.problem_order = [pid for pid in collection.problem_order
                                 if pid != problem_id]
    collection.save(update_fields=['problem_order', 'updated_at'])
    return JsonResponse({'status': 'ok', 'count': collection.problems.count()})


@require_POST
def collection_reorder(request, token):
    collection = get_object_or_404(Collection, token=token)
    try:
        data  = json.loads(request.body)
        order = [int(x) for x in data.get('order', [])]
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'status': 'error'}, status=400)
    valid = set(collection.problems.values_list('id', flat=True))
    collection.problem_order = [pid for pid in order if pid in valid]
    collection.save(update_fields=['problem_order', 'updated_at'])
    return JsonResponse({'status': 'ok', 'count': len(collection.problem_order)})


# ── Экспорт подборки (Этап Б2) ──────────────────────────────────────────────

def collection_export(request, token):
    from catalog.latex_export import xelatex_available
    collection = get_object_or_404(Collection, token=token)

    order_map = {pid: i for i, pid in enumerate(collection.problem_order)}
    problems  = sorted(
        collection.problems.filter(needs_quality_review=False,
                                   hidden_pending_review=False, content_status=Problem.ContentStatus.OK)
        .prefetch_related('topics'),
        key=lambda p: order_map.get(p.pk, 9999),
    )

    context = {
        'collection':  collection,
        'problems':    problems,
        'has_xelatex': xelatex_available(),
    }
    return render(request, 'catalog/collection_export.html', context)


@require_POST
def collection_download_pdf(request, token):
    from catalog.latex_export import compile_pdf, generate_latex
    collection     = get_object_or_404(Collection, token=token)
    show_answers   = request.POST.get('show_answers') == '1'
    show_solutions = request.POST.get('show_solutions') == '1'
    refusal = _answers_export_refusal(request, show_answers, show_solutions)
    if refusal:
        return refusal

    tex       = generate_latex(collection, show_answers, show_solutions)
    pdf_bytes, error = compile_pdf(tex)

    if pdf_bytes:
        resp = HttpResponse(pdf_bytes, content_type='application/pdf')
        resp['Content-Disposition'] = 'attachment; filename="collection.pdf"'
        return resp

    # Fallback: отдаём .tex с заголовком-предупреждением
    resp = HttpResponse(tex, content_type='text/plain; charset=utf-8')
    resp['Content-Disposition'] = 'attachment; filename="collection.tex"'
    resp['X-Export-Warning'] = 'PDF compilation failed'
    return resp


def collection_download_tex(request, token):
    from catalog.latex_export import generate_latex
    collection     = get_object_or_404(Collection, token=token)
    show_answers   = request.GET.get('show_answers') == '1'
    show_solutions = request.GET.get('show_solutions') == '1'
    refusal = _answers_export_refusal(request, show_answers, show_solutions)
    if refusal:
        return refusal

    tex  = generate_latex(collection, show_answers, show_solutions)
    resp = HttpResponse(tex, content_type='text/plain; charset=utf-8')
    resp['Content-Disposition'] = 'attachment; filename="collection.tex"'
    return resp


# ── Публичный API для модального окна просмотра условия ─────────────────────

def catalog_api_problem(request, pk):
    """Публичный JSON-эндпоинт: данные задачи для модала. Без авторизации."""
    try:
        problem = (
            Problem.objects
            .prefetch_related('topics', 'parts', 'source_references__source')
            .get(pk=pk, status=Problem.Status.PUBLISHED,
                 needs_quality_review=False,
                 hidden_pending_review=False, content_status=Problem.ContentStatus.OK)
        )
    except Problem.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    # Тот же счёт разных задач, что у страницы задачи (ADR 0129).
    from . import scrape_guard
    if scrape_guard.check(request, problem.pk):
        return JsonResponse({'error': 'scrape'}, status=429)

    d = problem.difficulty or 0

    # ⚠️ ТЕКСТ ОТРИСОВЫВАЕТ СЕРВЕР ТЕМ ЖЕ ПАРТИАЛОМ, ЧТО СТРАНИЦУ ЗАДАЧИ
    # (решение 17.09.2026): markdown — через санитайзер `problems/rendering.py`
    # с картинками по маркеру `[[FIGURE:…]]`, plain — экранирование и переносы.
    # Скрипт модалки вставляет готовое `*_html` и зовёт KaTeX; сырой текст
    # в `innerHTML` не попадает никогда.
    def html(text):
        return render_to_string('catalog/_math_text.html', {'text': text, 'problem': problem}).strip()

    parts = [
        {
            'label':  part.label,
            'text':   part.statement,
            'html':   html(part.statement),
            'points': float(part.points) if part.points is not None else None,
        }
        for part in problem.parts.all()
    ]
    topics  = list(problem.topics.values_list('name', flat=True))
    refs = list(problem.source_references.select_related('source').all())

    return JsonResponse({
        'id':             problem.pk,
        'title':          problem.title or f'Задача #{problem.pk}',
        'statement':      problem.statement,
        'statement_html': html(problem.statement),
        'parts':          parts,
        'difficulty':     d,
        'difficulty_str': '★' * d + '☆' * (5 - d),
        'topics':         topics,
        'problem_type':   problem.problem_type,
        'has_solution':   bool(problem.solution) and not problem.solution_needs_review,
        'sources':        [ref.source.name for ref in refs],
        'source_links':   [{'name': ref.source.name, 'url': source_url(ref)} for ref in refs],
    })


def problem_figure_svg(request, pk):
    """Отдать картинку задачи (ProblemFigure).

    Два вида в одной таблице: СГЕНЕРИРОВАННАЯ из TikZ (лежит в `svg`) и
    ИМПОРТИРОВАННАЯ вместе с задачей растровая (лежит в `image_data`,
    тип — в `content_type`). Путь показа у них общий.

    Отдаётся только то, что лежит в нашей таблице: адрес собирается по
    первичному ключу, из текста задачи сюда не попадает ничего (см.
    problems/figures.py). SVG уже санитизирован при генерации; растровый
    файл исполняемого содержимого не несёт в принципе.

    Заголовки — третий, независимый рубеж поверх чистки SVG и того, что
    картинка вставляется тегом <img> (в <img> скрипты не исполняются):
    CSP запрещает картинке вообще любые внешние обращения и скрипты,
    nosniff не даёт браузеру передумать про тип, а Content-Disposition
    inline исключает трактовку как загрузку.

    ⚠️ Адрес по-прежнему кончается на `.svg` — это ИМЯ маршрута, а не
    обещание формата: тип определяет заголовок `Content-Type`, а
    `nosniff` запрещает браузеру гадать по расширению. Менять адрес
    значило бы менять ссылки на уже показанных страницах.
    """
    figure = get_object_or_404(ProblemFigure, pk=pk)
    if figure.image_data:
        body = bytes(figure.image_data)
        content_type = figure.content_type or 'application/octet-stream'
    else:
        body, content_type = figure.svg, 'image/svg+xml'
    response = HttpResponse(body, content_type=content_type)
    response['Content-Security-Policy'] = (
        "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    )
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Disposition'] = 'inline'
    response['Cache-Control'] = 'public, max-age=86400'
    return response


# ═══════════════════════════════════════════════════════════════════════
# Карта тем и тегов — /catalog/map/
# ═══════════════════════════════════════════════════════════════════════
#
# Данные берутся из справочника в репозитории, а не из базы: новой
# таксономии в таблице `Tag` ещё нет (см. catalog/taxonomy_map.py).
# Файл читается ОДИН РАЗ при первом запросе в модульную переменную —
# 69 КБ JSON на каждый запрос это лишняя работа диска на ровном месте.

_TOPIC_MAP_CACHE = {'text': None, 'etag': None}


def _topic_map_payload():
    """Отдаёт (текст JSON, ETag), читая файл один раз на процесс."""
    if _TOPIC_MAP_CACHE['text'] is None:
        from catalog.taxonomy_map import JSON_PATH
        text = JSON_PATH.read_text(encoding='utf-8')
        _TOPIC_MAP_CACHE['text'] = text
        _TOPIC_MAP_CACHE['etag'] = '"%s"' % hashlib.sha256(
            text.encode('utf-8')).hexdigest()[:32]
    return _TOPIC_MAP_CACHE['text'], _TOPIC_MAP_CACHE['etag']


def _map_stats():
    """Сколько тем и тегов на карте — для подписи блока карты в каталоге.

    ⚠️ СЧИТАЕТСЯ ИЗ ДАННЫХ КАРТЫ, А НЕ ПИШЕТСЯ ЛИТЕРАЛОМ (правило нуля,
    решение владельца 04.09.2026): подпись «29 тем, 343 тега» жила в
    шаблоне руками и разошлась бы с картой при первой правке справочника.
    Читается через тот же кэш, что отдаёт JSON карты; пересчёт — только
    когда сменился ETag файла.
    """
    text, etag = _topic_map_payload()
    if _TOPIC_MAP_CACHE.get('stats_etag') != etag:
        nodes = json.loads(text).get('nodes', [])
        themes = sum(1 for n in nodes if n.get('k') == 'theme')
        _TOPIC_MAP_CACHE['stats'] = {'themes': themes,
                                     'tags': len(nodes) - themes}
        _TOPIC_MAP_CACHE['stats_etag'] = etag
    return _TOPIC_MAP_CACHE['stats']


def _map_context():
    """Дерево разделов и числа шапки карты тем — для партиала `_stol_map.html`."""
    text, _etag = _topic_map_payload()
    data = json.loads(text)
    themes = [n for n in data['nodes'] if n['k'] == 'theme']
    tags = [n for n in data['nodes'] if n['k'] == 'tag']

    tags_by_theme = {}
    for t in tags:
        tags_by_theme.setdefault(t['n'], []).append(t)

    # Навигатор справа — дерево: разделы, внутри темы, внутри теги.
    # Считается на сервере целиком: 372 строки это 30 КБ разметки, а на
    # клиенте пришлось бы держать вторую копию справочника и собирать те же
    # строки при каждом раскрытии.
    #
    # ⚠️ ЧИСЛО РЯДОМ СО СТРОКОЙ — ЭТО ЧИСЛО ЗАДАЧ, А НЕ ЧИСЛО ДЕТЕЙ. У темы
    # оно есть не всегда (складывается из счётчиков её тегов, а те заданы у
    # 180 из 343), и тогда вместо него ставится прочерк — канон 2.3:
    # отсутствие числа это прочерк и причина, а не пустое место.
    sections = []
    by_n = {t['n']: t for t in themes}
    for g in data['groups']:
        rows = []
        for n in g['themes']:
            th = by_n[n]
            rows.append({
                'n': n,
                'title': th['l'],
                'count': _fmt_number(th['c']) if th['c'] is not None else None,
                'tags': [
                    {'id': t['id'], 'label': t['l'],
                     'count': _fmt_number(t['c']) if t['c'] is not None else None}
                    for t in tags_by_theme.get(n, [])
                ],
            })
        sections.append({'key': g['k'], 'label': g['l'], 'themes': rows})

    return {'theme_count': len(themes), 'tag_count': len(tags), 'sections': sections}


def topic_map(request):
    """`/catalog/map/` — «Стол» сразу в режиме карты (README §1, §6).

    Под картой лежит вход с теми же фильтрами: любой выход с карты
    возвращает на него без перезагрузки. `?pane=1` отдаёт одну разметку
    карты — её берёт `stol_map.js`, когда карту открывают со входа.
    Выбор на карте — фильтр каталога, поэтому ссылки выхода несут фильтры
    адреса (`filters_query`).
    """
    active = filters.parse(request.GET)
    map_ctx = _map_context()
    map_ctx['filters_query'] = filters.query({}, active)[1:]
    if request.GET.get('pane') == '1':
        map_ctx.update({'map_selected': {'topics': active['topics'], 'tags': active['tags']},
                        'map_selected_n': len(active['topics']) + len(active['tags'])})
        return JsonResponse({'html': render_to_string('catalog/stol/_stol_map.html', map_ctx, request=request)})
    context = _catalog_context(request, None)
    context.update(_entry_context(request, context))
    context.update(map_ctx)
    context['view'] = 'map'
    # Выдача по строке поиска — `noindex` и здесь (24.09.2026): карта с `?q=`
    # была единственным адресом поиска без запрета индекса.
    if context['query']:
        context['seo_noindex'] = True
    response = render(request, 'catalog/stol.html', context)
    visitor, new_visitor = search_log.visitor_for(request)
    if (new_visitor and context['smart_search_status'] == 'deferred'):
        search_log.remember_visitor(response, visitor)
    response['X-Smart-Search'] = context['smart_search_status']
    return response


def topic_map_preview_demo(request):
    """Стенд встраиваемого предпросмотра карты — ТОЛЬКО ДЛЯ ПРИЁМКИ.

    В навигации страницы нет: она нужна, чтобы проверить поведение блока
    (нет подписей, медленное вращение, безразличие к курсору, остановка вне
    экрана и при prefers-reduced-motion) до того, как его смонтируют в
    «Умный каталог». Данных ей не нужно — блок сам идёт за map/data.json.
    """
    return render(request, 'catalog/topic_map_preview_demo.html')


def topic_map_data(request):
    """JSON карты с живыми числами и ключами справочника (`map_numbers`).

    Числа меняются вместе с банком, поэтому кэш браузера — те же 10 минут,
    что у сервера, а не сутки, как было у статичного файла; ETag — от текста
    с числами.
    """
    text, etag = map_numbers.live_payload(*_topic_map_payload())
    if request.headers.get('If-None-Match') == etag:
        response = HttpResponse(status=304)
    else:
        response = HttpResponse(text, content_type='application/json')
    response['ETag'] = etag
    response['Cache-Control'] = 'public, max-age=%d' % map_numbers.CACHE_SECONDS
    return response


# ── Подсказки тегов для поля фильтра ─────────────────────────────────────

def api_tags(request):
    """Подсказки тегов по двум и более символам. Публично, только чтение.

    ⚠️ ТОЛЬКО ТЕГИ ВИДИМЫХ ЗАДАЧ. Тег, висящий на скрытой задаче, не должен
    даже подсказываться: иначе поле подсказок становится оглавлением того,
    что каталог намеренно не показывает.

    ⚠️ БАЗУ ТЕГОВ ЗДЕСЬ НЕ ЧИСТИМ. Она засорена импортом (ссылки на чужие
    комментарии, фамилии составителей — 22 и 5 записей среди видимых), и
    это отдельная задача владельца, а не побочная правка этой сессии.
    Порядок по числу задач держит мусор внизу: у всего найденного хлама
    ровно по одной задаче.
    """
    from problems.models import Tag

    visible = Q(problems__status=Problem.Status.PUBLISHED,
                problems__needs_quality_review=False,
                problems__hidden_pending_review=False,
                problems__content_status=Problem.ContentStatus.OK)

    # Режим «теги темы» (`?topic=<id>`): все теги видимых задач этой темы
    # с числами, по убыванию, без нулей и без ограничения длины — окно
    # фильтров показывает их группой под заголовком темы.
    topic_id = (request.GET.get('topic') or '').strip()
    if topic_id.isdigit():
        of_topic = visible & Q(problems__topics__id=int(topic_id))
        rows = (Tag.objects.filter(kind='canonical')
                .annotate(n=Count('problems', filter=of_topic, distinct=True))
                .filter(n__gt=0)
                .order_by('-n', 'name'))
        return JsonResponse({'tags': [{'id': t.pk, 'name': t.name, 'count': t.n}
                                      for t in rows]})

    needle = (request.GET.get('q') or '').strip()
    if len(needle) < 2:
        return JsonResponse({'tags': []})
    # Только канонические теги (решение 17.09.2026): legacy в подсказках нет.
    rows = (Tag.objects
            .filter(name__icontains=needle, kind='canonical')
            .annotate(n=Count('problems', filter=visible, distinct=True))
            .filter(n__gt=0)
            .order_by('-n', 'name')[:10])
    return JsonResponse({'tags': [{'id': t.pk, 'name': t.name, 'count': t.n}
                                  for t in rows]})
