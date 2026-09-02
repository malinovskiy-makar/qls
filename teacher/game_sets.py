"""
Конструктор игровых наборов для учителя (Econ Rush, Фаза 3).

Набор — забег с заранее зафиксированным списком вопросов: учитель сам
собирает вопросы из игрового пула, получает код и раздаёт классу. Модель
одна на три поверхности (набор / вызов дня / дуэль) — решение в Notion.

Три шага конструктора, и порядок принципиален:

1. **Режим — первым.** Набор для «Классики» может содержать только
   числовые вопросы, для «Пули» — только данетки. Дай собирать сначала —
   половина набора окажется несовместимой с режимом, и придётся выбрасывать
   уже сделанную работу.
2. Две колонки: слева пул, отфильтрованный по типу вопроса режима, справа
   собранный набор с перетаскиванием порядка.
3. Название → сохранение → код и ссылка.

⚠️ Над левой колонкой висит честная плашка: в игру конвертируется не весь
каталог. Без неё учитель решит, что сайт сломан, когда не найдёт свою
задачу.
"""
import json

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from game import config as game_config
from game import sources as game_sources
from game import stats as game_stats
from game.models import GameQuestion, GameSet, make_code, normalize_code
from game.views import _pool_qs
from problems.management.commands.apply_topic_mapping import CANONICAL

from .views import teacher_required

MAX_SET_SIZE = 60      # больше не влезет ни в один разумный урок
PAGE_SIZE = 20


def _mode_choices():
    """Режимы, у которых в пуле есть хоть один вопрос: собирать набор для
    пустого режима бессмысленно."""
    counts = {}
    for qtype in _pool_qs().values_list('question_type', flat=True):
        counts[qtype] = counts.get(qtype, 0) + 1
    out = []
    for key, m in game_config.MODES.items():
        n = counts.get(m['question_type'], 0)
        if n:
            out.append({'key': key, 'title': m['title'],
                        'question_type': m['question_type'], 'pool': n,
                        'duration': m['duration'], 'lives': m['lives']})
    return out


@teacher_required
def game_sets_list(request):
    """Мои наборы: название, режим, число вопросов, код, сколько прошло."""
    sets = (GameSet.objects
            .filter(author=request.user, kind='custom')
            .annotate(played=Count('results'))
            .order_by('-created'))
    rows = [{
        'gset': s,
        'mode_title': game_config.MODES.get(s.mode, {}).get('title', s.mode),
        'played': s.played,
    } for s in sets]
    return render(request, 'teacher/game_sets_list.html', {'rows': rows})


@teacher_required
def game_set_create(request):
    """Конструктор набора. Шаг определяется параметром `mode`:
    его нет — шаг 1 (выбор режима), есть — шаги 2–3 на одной странице."""
    if request.method == 'POST':
        return _save_set(request)

    mode = request.GET.get('mode', '').strip()
    modes = _mode_choices()
    if mode not in {m['key'] for m in modes}:
        return render(request, 'teacher/game_set_create.html',
                      {'step': 1, 'modes': modes})

    qtype = game_config.MODES[mode]['question_type']
    qs = _pool_qs().filter(question_type=qtype)

    f_q = request.GET.get('q', '').strip()
    f_topic = request.GET.get('topic', '').strip()
    f_source = request.GET.get('source', '').strip()
    f_dmin = request.GET.get('dmin', '').strip()
    f_dmax = request.GET.get('dmax', '').strip()

    if f_q:
        qs = qs.filter(question__icontains=f_q)
    if f_source:
        qs = qs.filter(source_group=f_source)
    if f_dmin.isdigit():
        qs = qs.filter(difficulty__gte=int(f_dmin))
    if f_dmax.isdigit():
        qs = qs.filter(difficulty__lte=int(f_dmax))
    qs = qs.order_by('id')

    rows = list(qs)
    if f_topic:
        # JSONField.__contains не работает на SQLite — фильтруем в Python,
        # как и везде в игре (пул маленький).
        rows = [g for g in rows if f_topic in (g.topics or [])]

    paginator = Paginator(rows, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    stat_map = game_stats.bulk_stats(list(page_obj))

    cards = []
    for g in page_obj:
        st = stat_map.get(g.id)
        pub = game_stats.public_stat(st)
        cards.append({
            'q': g,
            # Правильный ответ учителю ВИДЕН: он и так видит всё в каталоге,
            # а собирать набор вслепую невозможно.
            'answer': _answer_text(g),
            'topics': ', '.join(g.topics or []) or '—',
            'difficulty': game_stats.effective_difficulty(g, st),
            'percent': round(100 * pub['p_correct']) if pub else None,
        })

    qp = request.GET.copy()
    qp.pop('page', None)
    return render(request, 'teacher/game_set_create.html', {
        'step': 2,
        'mode': mode,
        'mode_title': game_config.MODES[mode]['title'],
        'question_type': qtype,
        'cards': cards,
        'page_obj': page_obj,
        'total': paginator.count,
        'base_query': qp.urlencode(),
        'topics': CANONICAL,
        'source_groups': game_sources.GROUPS,
        'f_q': f_q, 'f_topic': f_topic, 'f_source': f_source,
        'f_dmin': f_dmin, 'f_dmax': f_dmax,
        'max_size': MAX_SET_SIZE,
        'levels': range(game_config.DIFFICULTY_MIN,
                        game_config.DIFFICULTY_MAX + 1),
    })


def _answer_text(g):
    """Правильный ответ вопроса словами — для колонки конструктора."""
    if g.question_type == 'numeric':
        return g.correct_value + (' ' + g.unit if g.unit else '')
    opts = g.options or []
    if g.question_type == 'multi':
        idx = g.correct_indices or []
        return ', '.join(opts[i] for i in idx if 0 <= i < len(opts))
    if g.correct_index is not None and 0 <= g.correct_index < len(opts):
        return opts[g.correct_index]
    return '—'


def _save_set(request):
    """Шаг 3: сохранение набора. Порядок вопросов — как прислал конструктор."""
    mode = request.POST.get('mode', '').strip()
    if mode not in game_config.MODES:
        messages.error(request, 'Неизвестный режим набора.')
        return redirect('teacher:game_set_create')

    title = request.POST.get('title', '').strip()
    raw_ids = request.POST.get('question_ids', '')
    ids = [int(x) for x in raw_ids.split(',') if x.strip().isdigit()]
    # dict.fromkeys — уникальность С СОХРАНЕНИЕМ ПОРЯДКА: порядок часть
    # контракта набора, при разном порядке сравнение результатов нечестно.
    ids = list(dict.fromkeys(ids))[:MAX_SET_SIZE]
    if not ids:
        messages.error(request, 'Добавьте хотя бы один вопрос.')
        return redirect('/teacher/game-sets/new/?mode=' + mode)

    qtype = game_config.MODES[mode]['question_type']
    valid = set(_pool_qs().filter(id__in=ids, question_type=qtype)
                .values_list('id', flat=True))
    ids = [i for i in ids if i in valid]
    if not ids:
        messages.error(request, 'Ни один вопрос не подходит выбранному режиму.')
        return redirect('/teacher/game-sets/new/?mode=' + mode)

    try:
        attempts = max(1, int(request.POST.get('attempts', '1')))
    except (TypeError, ValueError):
        attempts = 1

    gset = GameSet.objects.create(
        code=make_code(),
        mode=mode,
        kind='custom',
        title=title or 'Набор для «%s»' % game_config.MODES[mode]['title'],
        author=request.user,
        question_ids=ids,
        filter_snapshot={},
        attempts_allowed=attempts,
    )
    messages.success(request, 'Набор создан: код %s' % gset.code)
    return redirect('teacher:game_set_detail', code=gset.code)


@teacher_required
def game_set_detail(request, code):
    """Доска набора глазами автора: кто прошёл + разбивка по вопросам.

    Чужой набор редактировать нельзя; смотреть его доску можно — она и так
    публичная (`/game/s/<код>/board/`), но из панели учителя открывается
    только своя.
    """
    from game.views import set_question_stats
    gset = get_object_or_404(GameSet, code=normalize_code(code))
    if gset.author_id != request.user.id and not request.user.is_staff:
        messages.error(request, 'Это не ваш набор.')
        return redirect('teacher:game_sets')

    results = list(gset.results.select_related('user')
                   .order_by('-score', 'created_at'))
    board = [{
        'place': i + 1,
        'name': (r.user.username if r.user else 'аноним'),
        'score': r.score,
        'accuracy': r.accuracy,
        'max_combo': r.max_combo,
        'reason': r.ended_reason,
        'at': r.created_at,
    } for i, r in enumerate(results)]

    play_url = request.build_absolute_uri('/game/s/%s/' % gset.code)
    return render(request, 'teacher/game_set_detail.html', {
        'gset': gset,
        'mode_title': game_config.MODES.get(gset.mode, {}).get('title',
                                                               gset.mode),
        'board': board,
        'questions': set_question_stats(gset),
        'play_url': play_url,
        'board_url': request.build_absolute_uri(
            '/game/s/%s/board/' % gset.code),
    })


@teacher_required
@require_POST
def api_game_set_fill(request):
    """«Добрать N случайных по текущему фильтру» — кнопка правой колонки.

    Отдаёт id и краткий текст, чтобы конструктор нарисовал строки без
    второго запроса.
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({'error': 'Некорректный запрос'}, status=400)

    mode = body.get('mode')
    if mode not in game_config.MODES:
        return JsonResponse({'error': 'Неизвестный режим'}, status=400)
    try:
        n = max(1, min(MAX_SET_SIZE, int(body.get('n', 5))))
    except (TypeError, ValueError):
        n = 5
    exclude = [int(x) for x in (body.get('exclude') or [])
               if str(x).lstrip('-').isdigit()]

    qtype = game_config.MODES[mode]['question_type']
    qs = _pool_qs().filter(question_type=qtype).exclude(id__in=exclude)
    q_text = (body.get('q') or '').strip()
    if q_text:
        qs = qs.filter(question__icontains=q_text)
    source = (body.get('source') or '').strip()
    if source:
        qs = qs.filter(source_group=source)
    rows = list(qs.order_by('?')[:n * 4])
    topic = (body.get('topic') or '').strip()
    if topic:
        rows = [g for g in rows if topic in (g.topics or [])]
    rows = rows[:n]
    return JsonResponse({'questions': [
        {'id': g.id, 'text': g.question[:160], 'answer': _answer_text(g),
         'topics': ', '.join(g.topics or []) or '—',
         'difficulty': g.difficulty}
        for g in rows]})
