import hashlib
import json
import re

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from problems.jsonsafe import dumps_for_script
from problems.models import (
    Collection, Problem, ProblemFigure, Source, Topic,
)
from problems.management.commands.apply_topic_mapping import CANONICAL

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
    )
    context = {
        'problems_count': _fmt_number(visible.count()),
        'sources_count':  (Source.objects
                           .filter(references__problem__status=Problem.Status.PUBLISHED)
                           .distinct().count()),
        'topics_count':   Topic.objects.filter(name__in=CANONICAL).count(),
    }
    return render(request, 'catalog/home.html', context)


# ── Случайная опубликованная задача ─────────────────────────────────────────
def random_problem(request):
    problem = (
        Problem.objects
        .filter(status=Problem.Status.PUBLISHED, needs_quality_review=False,
                hidden_pending_review=False)
        .order_by('?')
        .first()
    )
    if problem is None:
        return redirect('catalog:problem_list')
    return redirect('catalog:problem_detail', pk=problem.pk)


# ── Список задач ────────────────────────────────────────────────────────────
def problem_list(request):
    # Два шлюза сразу и по разным поводам: качественный прячет битый
    # рендер (quality_gate), второй — то, чего человек ещё не смотрел
    # (pending_review_gate). Оба снимаются своим --revert.
    qs = Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                needs_quality_review=False,
                                hidden_pending_review=False)

    f_q      = request.GET.get('q',           '').strip()
    f_topic  = request.GET.get('topic',        '').strip()
    f_diff   = request.GET.get('difficulty',   '').strip()
    f_type   = request.GET.get('type',         '').strip()
    f_sol    = request.GET.get('has_solution', '').strip()
    f_source = request.GET.get('source',       '').strip()
    f_sort   = request.GET.get('sort',         '').strip()

    # Режим отображения: строки (по умолчанию) / таблица / галерея
    view_mode = request.GET.get('view', 'rows').strip()
    if view_mode not in ('rows', 'table', 'gallery'):
        view_mode = 'rows'

    if f_q:
        qs = qs.filter(Q(statement__icontains=f_q) | Q(title__icontains=f_q))
    if f_topic:
        qs = qs.filter(topics__id=f_topic)
    if f_diff:
        qs = qs.filter(difficulty=f_diff)
    if f_type:
        qs = qs.filter(problem_type=f_type)
    if f_sol == '1':
        qs = qs.exclude(solution='').filter(solution_needs_review=False)
    if f_source:
        qs = qs.filter(source_references__source_id=f_source)

    # Сортировка (поверх существующих фильтров; не меняет их логику)
    order_map = {
        'diff_asc':  [F('difficulty').asc(nulls_last=True), '-id'],
        'diff_desc': [F('difficulty').desc(nulls_last=True), '-id'],
        'new':       ['-id'],
        'relevance': ['-id'],
    }
    order_by = order_map.get(f_sort, ['-id'])

    qs = (qs.prefetch_related('topics', 'source_references__source')
            .order_by(*order_by).distinct())

    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page', 1))
    total     = paginator.count

    # Карточки: превью текста + звёздочки + флаг решения
    cards = []
    for p in page_obj:
        raw     = _strip_latex(p.statement)
        preview = raw[:180] + ('…' if len(raw) > 180 else '')
        d       = p.difficulty or 0
        refs    = list(p.source_references.all())
        cards.append({
            'problem':          p,
            'preview':          preview,
            'topics':           list(p.topics.all())[:3],
            'difficulty_stars': range(d),
            'difficulty_empty': range(5 - d),
            'has_solution':     bool(p.solution) and not p.solution_needs_review,
            'source':           refs[0].source.name if refs else '',
            'grade':            refs[0].grade if refs else '',
        })

    # Типы задач среди опубликованных (для кнопок фильтра)
    problem_types = list(
        Problem.objects
        .filter(status=Problem.Status.PUBLISHED)
        .exclude(problem_type='')
        .values_list('problem_type', flat=True)
        .distinct()
        .order_by('problem_type')
    )

    # Строка параметров без page — для ссылок пагинации
    qp = request.GET.copy()
    qp.pop('page', None)
    base_query = qp.urlencode()

    # Источники с опубликованными задачами
    sources = (
        Source.objects
        .filter(references__problem__status=Problem.Status.PUBLISHED)
        .distinct()
        .order_by('name')
    )

    # Для учителя: активные домашки (без дедлайна или с будущим дедлайном)
    teacher_assignments_json = '[]'
    if request.user.is_authenticated and request.user.role == 'teacher':
        from problems.models import Assignment
        from django.utils import timezone
        active_qs = Assignment.objects.filter(
            author=request.user
        ).filter(
            Q(deadline__isnull=True) | Q(deadline__gte=timezone.now())
        ).order_by('-id')[:50]
        # Названия работ печатает репетитор, а уезжают они в <script>:
        # экранируем `<`, `>`, `&` (см. problems/jsonsafe.py).
        teacher_assignments_json = dumps_for_script([
            {'id': a.pk, 'name': a.name}
            for a in active_qs
        ])

    # 21 каноническая тема в каноническом порядке (фильтр + чипы + атлас).
    # Этап А3: микро → макро → прочее.
    canonical_topics = sorted(
        Topic.objects.filter(name__in=CANONICAL),
        key=lambda t: CANONICAL.index(t.name),
    )

    # Нулевое состояние: нет поиска и ни одного фильтра → показываем атлас тем
    # (21 каноническая тема с числом опубликованных задач) вместо списка.
    is_zero_state = not any([f_q, f_topic, f_diff, f_type, f_sol, f_source])
    atlas = []
    if is_zero_state:
        counted = (
            Topic.objects.filter(name__in=CANONICAL)
            .annotate(n=Count('problems', filter=Q(
                problems__status=Problem.Status.PUBLISHED,
                problems__needs_quality_review=False,
                problems__hidden_pending_review=False,
            )))
        )
        by_name = {t.name: t for t in counted}
        atlas = [by_name[name] for name in CANONICAL if name in by_name]

    # Подписи активных фильтров для чипов
    f_topic_name = next((t.name for t in canonical_topics
                         if str(t.id) == f_topic), '')
    f_source_name = ''
    if f_source:
        f_source_name = (Source.objects.filter(id=f_source)
                         .values_list('name', flat=True).first() or '')

    context = {
        'page_obj':      page_obj,
        'cards':         cards,
        'total':         total,
        'topics':        canonical_topics,
        'sources':       sources,
        'problem_types': problem_types,
        'page_range':    _page_range(page_obj),
        'base_query':    base_query,
        # режим отображения и сортировка
        'view_mode':     view_mode,
        'f_sort':        f_sort or 'relevance',
        # нулевое состояние и атлас тем
        'is_zero_state': is_zero_state,
        'atlas':         atlas,
        # текущие значения фильтров
        'f_q':           f_q,
        'f_topic':       f_topic,
        'f_topic_name':  f_topic_name,
        'f_diff':        f_diff,
        'f_type':        f_type,
        'f_sol':         f_sol,
        'f_source':      f_source,
        'f_source_name': f_source_name,
        # Домашки учителя для dropdown
        'teacher_assignments_json': teacher_assignments_json,
    }
    return render(request, 'catalog/problem_list.html', context)


# ── Страница задачи ─────────────────────────────────────────────────────────
def problem_detail(request, pk):
    problem = get_object_or_404(Problem, pk=pk, status=Problem.Status.PUBLISHED,
                                needs_quality_review=False,
                                hidden_pending_review=False)

    # Учебное событие: задачу открыли. Запись неблокирующая — см.
    # problems/event_log.py (её падение не должно ронять страницу).
    from problems.event_log import log_problem_event
    log_problem_event('catalog', 'opened', request.user, problem,
                      request=request)

    difficulty = problem.difficulty or 0

    # Похожие задачи из кеша (топ-5), без задач за качественным шлюзом
    similar_qs = (
        problem.similar_problems
        .filter(status=Problem.Status.PUBLISHED, needs_quality_review=False,
                hidden_pending_review=False)
        .prefetch_related('topics')[:5]
    )
    similar = []
    for s in similar_qs:
        d = s.difficulty or 0
        similar.append({
            'problem':          s,
            'topics':           list(s.topics.all())[:2],
            'difficulty_stars': range(d),
            'difficulty_empty': range(5 - d),
        })

    context = {
        'problem':          problem,
        'parts':            problem.parts.all(),
        'has_part_answers': problem.parts.filter(answer__gt='').exists(),
        'topics':           problem.topics.all(),
        'tags':             problem.tags.all(),
        'sources':          problem.source_references.select_related('source').all(),
        'difficulty_stars': range(difficulty),
        'difficulty_empty': range(5 - difficulty),
        'similar':          similar,
    }
    return render(request, 'catalog/problem_detail.html', context)


# ── Конструктор подборок (Этап Б1) ─────────────────────────────────────────

def _canonical_topics():
    return sorted(
        Topic.objects.filter(name__in=CANONICAL),
        key=lambda t: CANONICAL.index(t.name),
    )


def collection_new(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip() or 'Моя подборка'
        template_type = request.POST.get('template_type', Collection.HOMEWORK)
        if template_type not in (Collection.HOMEWORK, Collection.TEST, Collection.SHEET):
            template_type = Collection.HOMEWORK
        col = Collection.objects.create(name=name, template_type=template_type)
        return redirect('catalog:collection_detail', token=col.token)
    return render(request, 'catalog/collection_new.html', {})


def collection_detail(request, token):
    collection = get_object_or_404(Collection, token=token)

    # Каталог с теми же фильтрами что в problem_list (+ оба шлюза)
    qs = Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                needs_quality_review=False,
                                hidden_pending_review=False)
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
                                   hidden_pending_review=False)
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
    problem     = get_object_or_404(Problem, pk=problem_id,
                                    status=Problem.Status.PUBLISHED)
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
                                   hidden_pending_review=False)
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
                 hidden_pending_review=False)
        )
    except Problem.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    d = problem.difficulty or 0
    parts = [
        {
            'label':  part.label,
            'text':   part.statement,
            'points': float(part.points) if part.points is not None else None,
        }
        for part in problem.parts.all()
    ]
    topics  = list(problem.topics.values_list('name', flat=True))
    sources = [ref.source.name for ref in problem.source_references.select_related('source').all()]

    return JsonResponse({
        'id':             problem.pk,
        'title':          problem.title or f'Задача #{problem.pk}',
        'statement':      problem.statement,
        'parts':          parts,
        'difficulty':     d,
        'difficulty_str': '★' * d + '☆' * (5 - d),
        'topics':         topics,
        'problem_type':   problem.problem_type,
        'has_solution':   bool(problem.solution) and not problem.solution_needs_review,
        'sources':        sources,
    })


# ── Семантический поиск (Стадия 1, прототип) ─────────────────────────────────

def _lexical_fallback(query, topic_id, difficulty, has_solution, kind):
    """Поиск по СЛОВАМ, когда смысловой выключен.

    ⚠️ ЭТО ДЕГРАДАЦИЯ, А НЕ ОТКАЗ (правило 6.13 docs/EMBEDDINGS.md).
    Страница обязана ответить 200 и что-то найти: пятисотка и вечный
    спиннер — худшее, что можно сделать с человеком, который просто искал
    задачу. Отдаём тот же формат результатов, что и смысловой поиск,
    чтобы шаблон не пришлось раздваивать.
    """
    from problems.models import Problem

    from . import hybrid

    ids, _hits, _picked = hybrid.lexical_search(query, 20, kind)
    if not ids:
        return []

    qs = (Problem.objects.filter(pk__in=ids)
          .prefetch_related('topics', 'parts'))
    if topic_id.isdigit():
        qs = qs.filter(topics__id=int(topic_id))
    if difficulty.isdigit():
        qs = qs.filter(difficulty=int(difficulty))
    if has_solution:
        qs = qs.exclude(solution='').filter(solution__isnull=False)

    by_id = {p.pk: p for p in qs}
    результаты = []
    for pid in ids:                       # порядок задаёт лексический поиск
        problem = by_id.get(pid)
        if problem is None:
            continue
        preview = _strip_latex(problem.statement)[:200].strip()
        if not preview:
            first_part = problem.parts.first()
            if first_part:
                preview = _strip_latex(first_part.statement)[:200].strip()
        результаты.append({
            'problem': problem,
            # Балла осмысленной близости у поиска по словам нет, и врать
            # числом нельзя: шаблон показывает score только когда он есть.
            'score': None,
            'preview': preview,
            'topics_display': [t.name for t in problem.topics.all()
                               if t.name in CANONICAL][:2],
        })
    return результаты


@login_required
def smart_search(request):
    """Поиск задач по текстовому описанию через эмбеддинги.

    Стадия 1: нет HyDE, нет новых моделей — только уже посчитанные векторы.
    Загрузка модели и индекса происходит лениво при первом запросе (~7 с),
    последующие запросы мгновенны (всё в памяти).
    """
    import logging

    from . import semantic
    from .search_client import SearchServiceUnavailable
    from .semantic import search as semantic_search

    logger = logging.getLogger(__name__)

    # 21 каноническая тема для фильтра (тот же порядок, что в каталоге).
    canonical_topics = sorted(
        Topic.objects.filter(name__in=CANONICAL),
        key=lambda t: CANONICAL.index(t.name),
    )

    query = request.GET.get('q', '').strip()
    topic_id = request.GET.get('topic_id', '')
    difficulty = request.GET.get('difficulty', '')
    has_solution = request.GET.get('has_solution', '') == '1'
    kind = request.GET.get('kind', 'problems')

    results = []
    error = None
    searched = False
    # Смысловой поиск выключен настройкой — работаем по словам и говорим
    # об этом. Не «ошибка»: человек ничего не сделал не так.
    degraded = not semantic.is_enabled()

    if query and degraded:
        searched = True
        results = _lexical_fallback(query, topic_id, difficulty,
                                    has_solution, kind)
    elif query:
        searched = True
        try:
            raw = semantic_search(
                query_text=query,
                topic_id=int(topic_id) if topic_id.isdigit() else None,
                difficulty=int(difficulty) if difficulty.isdigit() else None,
                has_solution=has_solution,
                content_kind=kind,
                limit=20,
            )
            # Обогащаем каждый результат превью-текстом без LaTeX.
            for item in raw:
                p = item['problem']
                preview = _strip_latex(p.statement)[:200].strip()
                if not preview:
                    # Берём первый подпункт если условие пустое.
                    first_part = p.parts.first()
                    if first_part:
                        preview = _strip_latex(first_part.statement)[:200].strip()
                item['preview'] = preview
                # Канонические темы задачи для отображения.
                item['topics_display'] = [
                    t.name for t in p.topics.all() if t.name in CANONICAL
                ][:2]
            results = raw
        except SearchServiceUnavailable as exc:
            # ⚠️ СЕРВИС ЛЁГ — ЭТО ДЕГРАДАЦИЯ, А НЕ ОШИБКА ЧЕЛОВЕКА.
            # Раньше этот случай попадал в `except Exception` ниже и человек
            # видел «Ошибка поиска: нет связи с сервисом…» — то есть нашу
            # внутреннюю кухню вместо результатов, хотя поиск по словам
            # прекрасно работает и без сервиса. Ведём себя ровно так же, как
            # при выключенном флаге выше: ищем словами и честно говорим об
            # этом плашкой. Ни пятисотки, ни пустого экрана, ни адреса
            # внутреннего сервиса наружу.
            logger.warning('search service unavailable: %s — идём по словам',
                           exc)
            degraded = True
            results = _lexical_fallback(query, topic_id, difficulty,
                                        has_solution, kind)
        except ImportError:
            error = (
                'Модель эмбеддингов не установлена. '
                'Запустите: pip install sentence-transformers'
            )
        except Exception as exc:
            error = f'Ошибка поиска: {exc}'

    return render(request, 'catalog/smart_search.html', {
        'query': query,
        'topic_id': topic_id,
        'difficulty': difficulty,
        'has_solution': has_solution,
        'kind': kind,
        'results': results,
        'error': error,
        'degraded': degraded,
        'searched': searched,
        'canonical_topics': canonical_topics,
        'difficulty_choices': range(1, 6),
    })


def problem_figure_svg(request, pk):
    """Отдать СГЕНЕРИРОВАННУЮ системой картинку (ProblemFigure).

    Отдаётся только то, что лежит в нашей таблице: адрес собирается по
    первичному ключу, из текста задачи сюда не попадает ничего (см.
    problems/figures.py). SVG уже санитизирован при генерации.

    Заголовки — третий, независимый рубеж поверх чистки SVG и того, что
    картинка вставляется тегом <img> (в <img> скрипты не исполняются):
    CSP запрещает картинке вообще любые внешние обращения и скрипты,
    nosniff не даёт браузеру передумать про тип, а Content-Disposition
    inline исключает трактовку как загрузку.
    """
    figure = get_object_or_404(ProblemFigure, pk=pk)
    response = HttpResponse(figure.svg, content_type='image/svg+xml')
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


def topic_map(request):
    """Страница карты. Разметка — самостоятельный блок: позже он переедет
    во всплывающее окно переработанного поиска без переделки."""
    text, _etag = _topic_map_payload()
    data = json.loads(text)
    themes = [n for n in data['nodes'] if n['k'] == 'theme']
    tags = [n for n in data['nodes'] if n['k'] == 'tag']
    counted = [t for t in tags if t['c'] is not None]

    tags_by_theme = {}
    for t in tags:
        tags_by_theme.setdefault(t['n'], []).append(t)

    # Навигатор «Темы» справа: тот же список, но сгруппированный по разделам.
    # Считается на сервере — на клиенте это была бы та же работа каждый раз.
    sections = []
    by_n = {t['n']: t for t in themes}
    for g in data['groups']:
        rows = []
        for n in g['themes']:
            th = by_n[n]
            rows.append({'n': n, 'title': th['l'],
                         'tags': len(tags_by_theme.get(n, []))})
        sections.append({'key': g['k'], 'label': g['l'], 'themes': rows})

    return render(request, 'catalog/topic_map.html', {
        'theme_count': len(themes),
        'tag_count': len(tags),
        'counted_tags': len(counted),
        'sections': sections,
    })


def topic_map_data(request):
    """JSON карты. Кэш на сутки и ETag: файл меняется только с деплоем."""
    text, etag = _topic_map_payload()
    if request.headers.get('If-None-Match') == etag:
        response = HttpResponse(status=304)
    else:
        response = HttpResponse(text, content_type='application/json')
    response['ETag'] = etag
    response['Cache-Control'] = 'public, max-age=86400'
    return response
