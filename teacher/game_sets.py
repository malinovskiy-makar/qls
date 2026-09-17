"""
Игровые наборы учителя (Wecon Rush): список, сборка на одном экране, страница набора.

Набор — раунд с заранее зафиксированным списком вопросов: учитель собирает вопросы
из игрового пула, получает код и раздаёт классу. Модель одна на три поверхности
(набор / вызов дня / дуэль) — решение в Notion.

Решение владельца 17.09.2026 (ADR 0116, макеты TeacherSets, TeacherSetBuilder,
TeacherSetDetail):

- **Сборка — один экран.** Режим кнопками сверху, слева вопросы с фильтрами, справа
  сам набор. ⚠️ ФИЛЬТРЫ И ПОДГРУЗКА НЕ ПЕРЕЗАГРУЖАЮТ СТРАНИЦУ: список слева приходит
  из `api_game_set_pool`, а набор живёт в скрипте страницы и дублируется в
  `sessionStorage`. Прежний мастер делал фильтры формой `method="get"` и страницы
  ссылками — каждая перезагрузка стирала собранное.
- **Режим — по-прежнему первым по смыслу**: у каждого режима свой тип вопросов, и
  смена режима при непустом наборе очищает его (с вопросом в окне).
- **Срок «Открыт до»** — необязательный, московское время (как отсечка вызова дня).
- Учителю не показываются внутренние имена типов (`single`, `multi`…) и секунды:
  режим описан словами и минутами.

⚠️ Выборка пула одна на страницу и на API (`pool_rows`): две копии фильтров разошлись
бы при первой правке, и «Найдено N» на странице не совпало бы со списком.
"""
import datetime
import json
import random
import re

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from game import config as game_config
from game import daily as game_daily
from game import sources as game_sources
from game import stats as game_stats
from game.models import GameQuestion, GameSet, make_code, normalize_code
from game.views import QUESTION_TYPE_TEXT, _pool_qs, set_question_stats
from problems.management.commands.apply_topic_mapping import CANONICAL

from .views import teacher_required

MAX_SET_SIZE = 60      # больше не влезет ни в один разумный урок
PAGE_SIZE = 20
TOP_TOPICS = 5         # чипов тем над списком; остальные — в «ещё N тем»

SHORT_MONTHS = {1: 'янв.', 2: 'февр.', 3: 'марта', 4: 'апр.', 5: 'мая', 6: 'июня', 7: 'июля',
                8: 'авг.', 9: 'сент.', 10: 'окт.', 11: 'нояб.', 12: 'дек.'}


def _plural(n, one, few, many):
    from problems.templatetags.ru import pick
    return pick(n, one, few, many)


def _moscow(moment):
    return timezone.localtime(moment, game_daily.daily_tzinfo())


def _short_date(moment):
    u"""«20 сент.» по Москве."""
    local = _moscow(moment)
    return '%d %s' % (local.day, SHORT_MONTHS[local.month])


def _mode_choices():
    """Режимы, у которых в пуле есть хоть один вопрос: собирать набор для
    пустого режима бессмысленно. Подпись — словами и минутами."""
    counts = {}
    for qtype in _pool_qs().values_list('question_type', flat=True):
        counts[qtype] = counts.get(qtype, 0) + 1
    out = []
    for key, m in game_config.MODES.items():
        n = counts.get(m['question_type'], 0)
        if n:
            out.append({'key': key, 'title': m['title'], 'pool': n,
                        'sub': '%s · %d мин · %s' % (QUESTION_TYPE_TEXT.get(m['question_type'], ''),
                                                     m['duration'] // 60,
                                                     '{:,}'.format(n).replace(',', ' '))})
    return out


# ─── Ответ словами: лёгкая чистка только для показа ─────────────────────────

# Метка варианта в начале ответа, оставшаяся от источника: «(b) …», «(3) …», «a) …».
_LABEL = re.compile(r'^\s*(?:\([a-zа-яё0-9]\)|[a-zа-яё0-9]\))\s+', re.IGNORECASE)


def answer_display(text):
    u"""Ответ для показа учителю без «(b)» в начале и «;» в конце.

    ⚠️ ДАННЫЕ В БАЗЕ НЕ МЕНЯЮТСЯ — это только вид (правило «ИИ и чистки пишут новые
    поля», ADR 0005). Ответ целиком в скобках («(все перечисленное)») не трогаем:
    это не метка, а сам ответ.
    """
    s = (text or '').strip()
    if s.startswith('(') and s.endswith(')'):
        return s
    s = _LABEL.sub('', s, count=1)
    return re.sub(r'\s*[;.]\s*$', '', s) or (text or '').strip()


def _answer_text(g):
    """Правильный ответ вопроса словами (как в базе)."""
    if g.question_type == 'numeric':
        return g.correct_value + (' ' + g.unit if g.unit else '')
    opts = g.options or []
    if g.question_type == 'multi':
        idx = g.correct_indices or []
        return ', '.join(opts[i] for i in idx if 0 <= i < len(opts))
    if g.correct_index is not None and 0 <= g.correct_index < len(opts):
        return opts[g.correct_index]
    return '–'


# ─── Выборка пула: одна на страницу сборки и на API ─────────────────────────

FILTER_KEYS = ('q', 'topic', 'source', 'dmin', 'dmax')


def _filters(data):
    return {key: (data.get(key) or '').strip() for key in FILTER_KEYS}


def pool_rows(mode, q='', topic='', source='', dmin='', dmax=''):
    """Вопросы пула для сборки набора режима `mode` под фильтрами, по порядку id."""
    qtype = game_config.MODES[mode]['question_type']
    qs = _pool_qs().filter(question_type=qtype)
    if q:
        qs = qs.filter(question__icontains=q)
    if source:
        qs = qs.filter(source_group=source)
    if str(dmin).isdigit():
        qs = qs.filter(difficulty__gte=int(dmin))
    if str(dmax).isdigit():
        qs = qs.filter(difficulty__lte=int(dmax))
    rows = list(qs.order_by('id'))
    if topic:
        # JSONField.__contains не работает на SQLite — фильтруем в Python,
        # как и везде в игре (пул маленький).
        rows = [g for g in rows if topic in (g.topics or [])]
    return rows


def pool_items(rows):
    """Карточки вопросов для левой колонки. ⚠️ Без внутреннего имени типа вопроса."""
    stat_map = game_stats.bulk_stats(rows)
    items = []
    for g in rows:
        st = stat_map.get(g.id)
        pub = game_stats.public_stat(st)
        items.append({
            'id': g.id,
            'text': g.question,
            # Правильный ответ учителю ВИДЕН: собирать набор вслепую невозможно.
            'answer': answer_display(_answer_text(g)),
            'topics': ', '.join(g.topics or []) or 'без темы',
            'difficulty': game_stats.effective_difficulty(g, st),
            'source': game_sources.GROUP_TITLES.get(g.source_group, ''),
            'percent': round(100 * pub['p_correct']) if pub else None,
        })
    return items


def _pool_page(mode, filters, offset=0):
    rows = pool_rows(mode, **filters)
    page = rows[offset:offset + PAGE_SIZE]
    return {'total': len(rows), 'items': pool_items(page),
            'next_offset': offset + PAGE_SIZE if offset + PAGE_SIZE < len(rows) else None}


def _top_topics_by_mode(modes):
    u"""Самые частые темы пула в каждом режиме — чипы над списком вопросов."""
    by_type = {}
    for qtype, topics in _pool_qs().values_list('question_type', 'topics'):
        cell = by_type.setdefault(qtype, {})
        for name in topics or []:
            cell[name] = cell.get(name, 0) + 1
    out = {}
    for m in modes:
        counts = by_type.get(game_config.MODES[m['key']]['question_type'], {})
        ranked = sorted((t for t in counts if t in CANONICAL), key=lambda t: (-counts[t], t))
        out[m['key']] = ranked[:TOP_TOPICS]
    return out


# ─── Список наборов ──────────────────────────────────────────────────────────

def _deadline(gset, now):
    if gset.closes_at is None:
        return 'бессрочно', 'open'
    if gset.closes_at > now:
        return 'открыт до ' + _short_date(gset.closes_at), 'open'
    return 'закрыт ' + _short_date(gset.closes_at), 'closed'


@teacher_required
def game_sets_list(request):
    """Мои наборы: код, срок, сколько прошли и средняя точность — агрегатами одним запросом."""
    now = timezone.now()
    today = _moscow(now).date()
    sets = (GameSet.objects
            .filter(author=request.user, kind='custom')
            .annotate(played=Count('results'), sum_correct=Sum('results__correct_count'),
                      sum_total=Sum('results__total_count'))
            .order_by('-created'))
    rows = []
    for s in sets:
        deadline, state = _deadline(s, now)
        rows.append({
            'gset': s,
            'meta': '%s · %d %s · %d %s' % (
                game_config.MODES.get(s.mode, {}).get('title', s.mode),
                s.size, _plural(s.size, 'вопрос', 'вопроса', 'вопросов'),
                s.attempts_allowed, _plural(s.attempts_allowed, 'попытка', 'попытки', 'попыток')),
            'deadline': deadline,
            'deadline_state': state,
            'played': s.played,
            'accuracy': round(100 * s.sum_correct / s.sum_total) if s.sum_total else None,
            'created': 'сегодня' if _moscow(s.created).date() == today else _short_date(s.created),
        })
    return render(request, 'teacher/game_sets_list.html', {'rows': rows})


# ─── Сборка набора ───────────────────────────────────────────────────────────

@teacher_required
def game_set_create(request):
    """Сборка набора на одном экране; POST — сохранение."""
    if request.method == 'POST':
        return _save_set(request)
    modes = _mode_choices()
    keys = [m['key'] for m in modes]
    mode = request.GET.get('mode', '').strip()
    if mode not in keys:
        mode = 'blitz' if 'blitz' in keys else (keys[0] if keys else '')
    initial = _pool_page(mode, _filters({})) if mode else {'total': 0, 'items': [], 'next_offset': None}
    top = _top_topics_by_mode(modes)
    return render(request, 'teacher/game_set_create.html', {
        'modes': modes,
        'mode': mode,
        'builder_json': {
            'mode': mode,
            'max': MAX_SET_SIZE,
            'page_size': PAGE_SIZE,
            'pool': initial,
            'top_topics': top,
            'topics': list(CANONICAL),
            'pool_url': reverse('teacher:api_game_set_pool'),
            'fill_url': reverse('teacher:api_game_set_fill'),
        },
        'source_groups': game_sources.GROUPS,
        'levels': range(game_config.DIFFICULTY_MIN, game_config.DIFFICULTY_MAX + 1),
        'max_size': MAX_SET_SIZE,
    })


def _parse_deadline(raw):
    u"""«2026-09-20T23:59» из поля `datetime-local` — московское время.

    Возвращает (момент или None, ошибка или ''). Пусто — срока нет. ⚠️ Прошедший
    срок — ошибка: набор, закрытый в момент создания, ученик открыть уже не сможет.
    """
    raw = (raw or '').strip()
    if not raw:
        return None, ''
    try:
        moment = datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None, 'Не получилось прочитать срок.'
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=game_daily.daily_tzinfo())
    if moment <= timezone.now():
        return None, 'Срок уже прошёл.'
    return moment, ''


def _save_set(request):
    """Сохранение набора. Порядок вопросов — как прислала сборка."""
    mode = request.POST.get('mode', '').strip()
    if mode not in game_config.MODES:
        messages.error(request, 'Неизвестный режим набора.')
        return redirect('teacher:game_set_create')
    back = reverse('teacher:game_set_create') + '?mode=' + mode

    title = request.POST.get('title', '').strip()
    raw_ids = request.POST.get('question_ids', '')
    ids = [int(x) for x in raw_ids.split(',') if x.strip().isdigit()]
    # dict.fromkeys — уникальность С СОХРАНЕНИЕМ ПОРЯДКА: порядок часть
    # контракта набора, при разном порядке сравнение результатов нечестно.
    ids = list(dict.fromkeys(ids))[:MAX_SET_SIZE]
    if not ids:
        messages.error(request, 'Добавьте хотя бы один вопрос.')
        return redirect(back)

    qtype = game_config.MODES[mode]['question_type']
    valid = set(_pool_qs().filter(id__in=ids, question_type=qtype)
                .values_list('id', flat=True))
    ids = [i for i in ids if i in valid]
    if not ids:
        messages.error(request, 'Ни один вопрос не подходит выбранному режиму.')
        return redirect(back)

    closes_at, problem = _parse_deadline(request.POST.get('closes_at'))
    if problem:
        messages.error(request, problem)
        return redirect(back)

    try:
        attempts = max(1, min(10, int(request.POST.get('attempts', '1'))))
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
        closes_at=closes_at,
    )
    messages.success(request, 'Набор создан: код %s' % gset.code)
    # ?created=1 — страница набора очистит черновик сборки в sessionStorage.
    return redirect(reverse('teacher:game_set_detail', args=[gset.code]) + '?created=1')


@teacher_required
@require_GET
def api_game_set_pool(request):
    u"""Список вопросов для левой колонки сборки — без перезагрузки страницы.

    `GET ?mode=&q=&topic=&source=&dmin=&dmax=&offset=` → `{total, items, next_offset}`.
    Та же выборка, что у первой порции страницы (`pool_rows`).
    """
    mode = request.GET.get('mode', '')
    if mode not in game_config.MODES:
        return JsonResponse({'error': 'Неизвестный режим'}, status=400)
    try:
        offset = max(0, int(request.GET.get('offset', 0)))
    except (TypeError, ValueError):
        offset = 0
    return JsonResponse(_pool_page(mode, _filters(request.GET), offset))


@teacher_required
@require_POST
def api_game_set_fill(request):
    """«Добрать N случайных» под текущие фильтры, без уже выбранных."""
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
    exclude = {int(x) for x in (body.get('exclude') or []) if str(x).lstrip('-').isdigit()}
    rows = [g for g in pool_rows(mode, **_filters(body)) if g.id not in exclude]
    random.shuffle(rows)
    return JsonResponse({'questions': pool_items(rows[:n])})


# ─── Страница набора ─────────────────────────────────────────────────────────

def _own_set(request, code):
    gset = get_object_or_404(GameSet, code=normalize_code(code))
    if gset.author_id != request.user.id and not request.user.is_staff:
        return gset, False
    return gset, True


@teacher_required
def game_set_detail(request, code):
    """Страница набора глазами автора: код для класса, кто прошёл и где ошибся класс.

    Учитель видит всех (и анонимов), время сдачи, тексты вопросов и верные ответы.
    Чужой набор — как раньше: «Это не ваш набор».
    """
    gset, mine = _own_set(request, code)
    if not mine:
        messages.error(request, 'Это не ваш набор.')
        return redirect('teacher:game_sets')

    results = list(gset.results.select_related('user').order_by('-score', 'created_at'))
    board = [{
        'place': i + 1,
        'name': r.user.username if r.user_id else 'аноним',
        'anon': not r.user_id,
        'score': r.score,
        'accuracy': r.accuracy,
        'combo': '×' + ('%g' % (r.max_combo or 1)).replace('.', ','),
        'ending': game_daily.ENDING_TEXT.get(r.ended_reason, game_daily.ENDING_TEXT['time']),
        'when': _moscow(r.created_at).strftime('%d.%m %H:%M'),
    } for i, r in enumerate(results)]
    tries = sum(r.total_count for r in results)

    questions = set_question_stats(gset, show_text=True)
    answers = {g.id: answer_display(_answer_text(g))
               for g in GameQuestion.objects.filter(id__in=gset.question_ids or [])}
    for q in questions:
        q['answer'] = answers.get(q['id'], '')
        q['hard'] = q['percent'] is not None and q['percent'] < 40
    measured = [q for q in questions if q['percent'] is not None]
    hardest = min(measured, key=lambda q: (q['percent'], q['number'])) if measured else None
    by_order = request.GET.get('sort') == 'order'
    if not by_order:
        questions = sorted(questions, key=lambda q: (q['percent'] is None,
                                                     q['percent'] if q['percent'] is not None else 0,
                                                     q['number']))

    play_path = reverse('game:set_page', args=[gset.code])
    mode_cfg = game_config.MODES.get(gset.mode, {})
    return render(request, 'teacher/game_set_detail.html', {
        'gset': gset,
        'mode_title': mode_cfg.get('title', gset.mode),
        'type_text': QUESTION_TYPE_TEXT.get(mode_cfg.get('question_type'), ''),
        'closes_text': (_moscow(gset.closes_at).strftime('%d.%m.%Y %H:%M') if gset.closes_at else ''),
        'closes_long': (_short_date(gset.closes_at) + _moscow(gset.closes_at).strftime(', %H:%M')
                        if gset.closes_at else ''),
        'closes_value': (_moscow(gset.closes_at).strftime('%Y-%m-%dT%H:%M') if gset.closes_at else ''),
        'board': board,
        'played': len(results),
        'anonymous': sum(1 for r in results if not r.user_id),
        'avg_accuracy': round(100 * sum(r.correct_count for r in results) / tries) if tries else None,
        'avg_score': round(sum(r.score for r in results) / len(results)) if results else None,
        'hardest': hardest,
        'questions': questions,
        'by_order': by_order,
        'code_spaced': '%s %s' % (gset.code[:4], gset.code[4:]),
        'play_url': request.build_absolute_uri(play_path),
        'play_path': play_path,
        'host': request.get_host(),
    })


@teacher_required
@require_POST
def game_set_deadline(request, code):
    u"""«Изменить срок»: новый момент «открыт до» или снять срок. Только автор или персонал."""
    gset, mine = _own_set(request, code)
    if not mine:
        raise PermissionDenied('Это не ваш набор.')
    if request.POST.get('clear'):
        gset.closes_at = None
        messages.success(request, 'Срок снят: набор открыт бессрочно.')
    else:
        closes_at, problem = _parse_deadline(request.POST.get('closes_at'))
        if problem or closes_at is None:
            messages.error(request, problem or 'Укажите дату и время или снимите срок.')
            return redirect('teacher:game_set_detail', code=gset.code)
        gset.closes_at = closes_at
        messages.success(request, 'Срок изменён.')
    gset.save(update_fields=['closes_at'])
    return redirect('teacher:game_set_detail', code=gset.code)
