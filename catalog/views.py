import json
import re

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from problems.models import Collection, Problem, Source, Topic
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
    context = {
        'problems_count': _fmt_number(Problem.objects.count()),
        'sources_count':  Source.objects.count(),
        'topics_count':   Topic.objects.filter(name__in=CANONICAL).count(),
    }
    return render(request, 'catalog/home.html', context)


# ── Случайная опубликованная задача ─────────────────────────────────────────
def random_problem(request):
    problem = (
        Problem.objects
        .filter(status=Problem.Status.PUBLISHED, needs_quality_review=False)
        .order_by('?')
        .first()
    )
    if problem is None:
        return redirect('catalog:problem_list')
    return redirect('catalog:problem_detail', pk=problem.pk)


# ── Список задач ────────────────────────────────────────────────────────────
def problem_list(request):
    # Качественный шлюз: задачи с битым рендером скрыты (quality_gate --revert снимает)
    qs = Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                needs_quality_review=False)

    f_q      = request.GET.get('q',           '').strip()
    f_topic  = request.GET.get('topic',        '').strip()
    f_diff   = request.GET.get('difficulty',   '').strip()
    f_type   = request.GET.get('type',         '').strip()
    f_sol    = request.GET.get('has_solution', '').strip()
    f_source = request.GET.get('source',       '').strip()

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

    qs = qs.prefetch_related('topics').order_by('-id').distinct()

    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page', 1))
    total     = paginator.count

    # Карточки: превью текста + звёздочки + флаг решения
    cards = []
    for p in page_obj:
        raw     = _strip_latex(p.statement)
        preview = raw[:150] + ('…' if len(raw) > 150 else '')
        d       = p.difficulty or 0
        cards.append({
            'problem':          p,
            'preview':          preview,
            'topics':           list(p.topics.all())[:3],
            'difficulty_stars': range(d),
            'difficulty_empty': range(5 - d),
            'has_solution':     bool(p.solution) and not p.solution_needs_review,
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
        teacher_assignments_json = json.dumps([
            {'id': a.pk, 'name': a.name}
            for a in active_qs
        ])

    context = {
        'page_obj':      page_obj,
        'cards':         cards,
        'total':         total,
        # В фильтре показываем только 21 каноническую тему (Этап А3),
        # в каноническом порядке: микро → макро → прочее.
        'topics':        sorted(
            Topic.objects.filter(name__in=CANONICAL),
            key=lambda t: CANONICAL.index(t.name),
        ),
        'sources':       sources,
        'problem_types': problem_types,
        'page_range':    _page_range(page_obj),
        'base_query':    base_query,
        # текущие значения фильтров
        'f_q':           f_q,
        'f_topic':       f_topic,
        'f_diff':        f_diff,
        'f_type':        f_type,
        'f_sol':         f_sol,
        'f_source':      f_source,
        # Домашки учителя для dropdown
        'teacher_assignments_json': teacher_assignments_json,
    }
    return render(request, 'catalog/problem_list.html', context)


# ── Страница задачи ─────────────────────────────────────────────────────────
def problem_detail(request, pk):
    problem = get_object_or_404(Problem, pk=pk, status=Problem.Status.PUBLISHED,
                                needs_quality_review=False)

    difficulty = problem.difficulty or 0

    # Похожие задачи из кеша (топ-5), без задач за качественным шлюзом
    similar_qs = (
        problem.similar_problems
        .filter(status=Problem.Status.PUBLISHED, needs_quality_review=False)
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

    # Каталог с теми же фильтрами что в problem_list (+ качественный шлюз)
    qs = Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                needs_quality_review=False)
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
        collection.problems.filter(needs_quality_review=False)
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
        collection.problems.filter(needs_quality_review=False)
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
                 needs_quality_review=False)
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

