"""Навигатор раздела «Олимпиады»: ЕДИНСТВЕННОЕ место, где считаются числа экранов.

Ночь 30→31.10.2026, этап Э1 (ADR 0173). Вьюхи и шаблоны чисел не считают:
они берут готовые словари отсюда. Иначе «материалов на платформе» на главной
и «заданий у нас» на странице олимпиады однажды разошлись бы — ровно так уже
спорили числа тура и числа «у нас» (карточка в Notion).

⚠️ ОСНОВНОЙ КОМПЛЕКТ — `base_variants()`. Опубликован, не повтор другого
(`duplicate_of` пусто, ADR 0171), не демонстрационный, есть в последнем
пакете. Повтор — тот же вариант из другого источника: в сетку он не идёт,
иначе одна клетка показала бы вариант дважды.

⚠️ ЧИСЛА НЕ ВБИВАЮТСЯ И НЕ ЧИНЯТСЯ. Дефект данных (задания чужого тура,
пункты дважды) экран показывает честно: в туре 8 заданий, значит 8.
Чинит отдельная сессия чистки, после неё числа пересчитаются сами.

Сетка «сезон × класс» строится по `OlympiadVariantGrade`: решение владельца
30.10 — комплект «10-11» лежит и в 10, и в 11 классе. Соседние классы одного
комплекта склеиваются в одну широкую клетку (`colspan`); комплект без
классов вовсе (ВсОШ 2016/17) — клетка на все классы без подписи.
"""
from collections import defaultdict
from datetime import date

from django.db.models import Count, Q, Sum

from .models import (Olympiad, OlympiadEvent, OlympiadVariant,
                     OlympiadVariantItem, TrainingAttempt,
                     current_academic_year)

# Подписи туров. Тур в базе — строка пакета как есть (`OlympiadVariant.tour`).
TOUR_LABELS = {
    '1': '1 тур', '2': '2 тур', 'tur1': '1 тур', 'tur3': '3 тур',
    'test': 'Тест', 'problems': 'Задачи', 'essay': 'Эссе', '': 'Тур',
}
TOUR_ORDER = {'1': 1, 'tur1': 1, '2': 2, 'tur3': 3, 'test': 4,
              'problems': 5, 'essay': 6, '': 0}

# Раздел главной «Финансовая грамотность и Основы бизнеса» (макет 30.10).
# ⚠️ Не `display_group` базы: в «смежном» там лежит и Ломоносов, а макет
# ставит его в основной список после СПбГУ. Базу ночь не правит — раздел
# выбирается здесь, явным списком профилей.
FIN_SECTION = ('vp-ob', 'vp-fingram', 'mosh-fingram', 'mosh-entrepreneurship')

# Сколько последних сезонов страница олимпиады показывает сразу.
SEASONS_VISIBLE = 10

# Порядок статусов неподтверждённых событий в ленте: сначала «как в прошлом
# сезоне» (у них есть ориентир-число словами), потом «ждём объявления».
_STATUS_ORDER = {OlympiadEvent.DateStatus.CONFIRMED: 0,
                 OlympiadEvent.DateStatus.APPROX_LAST_YEAR: 1,
                 OlympiadEvent.DateStatus.AWAITING: 2}


# ---------------------------------------------------------------------------
# Мелочи: сезон, склонения
# ---------------------------------------------------------------------------

def plural(n, one, few, many):
    """«1 задание», «3 задания», «5 заданий» — три формы, как требует русский."""
    tail, hundred = n % 10, n % 100
    if tail == 1 and hundred != 11:
        return one
    if tail in (2, 3, 4) and hundred not in (12, 13, 14):
        return few
    return many


def tasks_label(n):
    return '{} {}'.format(n, plural(n, 'задание', 'задания', 'заданий'))


def seasons_label(n):
    return '{} {}'.format(n, plural(n, 'сезон', 'сезона', 'сезонов'))


def season_start(season):
    """Год начала сезона «1999/00» → 1999; пусто или мусор → None."""
    head = (season or '').split('/')[0].strip()
    return int(head) if head.isdigit() else None


def season_text(start):
    """1999 → «1999/2000»: «/00» читается как ошибка, полный год — нет."""
    end = start + 1
    if end % 100 == 0:
        return '{}/{}'.format(start, end)
    return '{}/{:02d}'.format(start, end % 100)


def grades_text(grades):
    """[10, 11] → «10–11 классы»; [9] → «9 класс»."""
    if not grades:
        return ''
    if len(grades) == 1:
        return '{} класс'.format(grades[0])
    return '{}–{} классы'.format(grades[0], grades[-1])


# ---------------------------------------------------------------------------
# Основные комплекты
# ---------------------------------------------------------------------------

def base_variants():
    """Основные комплекты раздела: единственное определение на все экраны."""
    return OlympiadVariant.objects.filter(
        olympiad__is_published=True,
        olympiad__is_placeholder=False,
        visibility=OlympiadVariant.Visibility.PUBLISHED,
        duplicate_of__isnull=True,
        is_placeholder=False,
        absent_in_last_import=False,
    )


def visible_olympiads():
    """Олимпиады раздела: опубликованные и не заглушки.

    ⚠️ Вернадский и две МОШ на макете показаны — это решение владельца НА
    БУДУЩЕЕ; в базе они скрыты, и раздел их не открывает.
    """
    return Olympiad.objects.filter(is_published=True, is_placeholder=False)


def _annotated(queryset):
    """Комплекты со счётчиками позиций ОДНИМ запросом (без N+1 на клетку)."""
    return (queryset.select_related('stage')
            .prefetch_related('grades', 'files')
            .annotate(
                n_items=Count('items', distinct=True),
                n_solution=Count('items', filter=Q(items__has_solution=True),
                                 distinct=True),
                n_criteria=Count('items', filter=Q(items__has_criteria=True),
                                 distinct=True),
                n_unscored=Count('items', filter=Q(items__max_score__isnull=True),
                                 distinct=True),
                items_score=Sum('items__max_score')))


def tour_max_score(variant):
    """Максимум тура: сумма баллов позиций, если балл есть у КАЖДОЙ.

    Неполная сумма — не максимум: у позиции без балла (чаще всего задание
    чужого тура, дефект пакета) вклад неизвестен. Тогда — максимум этапа,
    а нет и его — None (на экране числа нет).
    """
    if variant.n_items and not variant.n_unscored and variant.items_score:
        return float(variant.items_score)
    stage = variant.stage
    if stage is not None and stage.max_score:
        return float(stage.max_score)
    return None


def tour_minutes(variant):
    """Время тура: своё у комплекта, иначе время этапа."""
    if variant.duration_minutes:
        return variant.duration_minutes
    stage = variant.stage
    return stage.duration_minutes if stage is not None else None


def tour_pdfs(variant):
    """PDF комплекта: сначала условия, потом решения и критерии.

    ⚠️ Ссылка — на нашу копию, только если файл РЕАЛЬНО лежит в хранилище;
    иначе на страницу источника. Строка с именем файла без самого файла (так
    на площадке ночи: тома media нет) дала бы кнопку, ведущую в 404.
    """
    from django.core.files.storage import default_storage

    out = []
    for item in variant.files.all():
        if item.file and default_storage.exists(item.file.name):
            out.append({'href': item.file.url, 'external': False,
                        'kind': item.kind, 'order': item.order, 'pk': item.pk})
        elif item.url:
            out.append({'href': item.url, 'external': True,
                        'kind': item.kind, 'order': item.order, 'pk': item.pk})
    out.sort(key=lambda f: (0 if f['kind'].startswith('условия') else 1,
                            f['external'], f['order'], f['pk']))
    return out


# ---------------------------------------------------------------------------
# Попытки решающего
# ---------------------------------------------------------------------------

def _attempts_for(variant_ids, user=None, session_key=''):
    """{id комплекта: [попытки]} этого решающего — одним запросом.

    ⚠️ Гость видит ТОЛЬКО попытки своей сессии и только гостевые: чужая
    попытка вошедшего с той же сессии сюда не попадает.
    """
    if user is not None and getattr(user, 'is_authenticated', False):
        queryset = TrainingAttempt.objects.filter(user=user)
    elif session_key:
        queryset = TrainingAttempt.objects.filter(user__isnull=True,
                                                  session_key=session_key)
    else:
        return {}
    out = defaultdict(list)
    for attempt in (queryset.filter(variant_id__in=list(variant_ids))
                    .order_by('-started_at')):
        out[attempt.variant_id].append(attempt)
    return out


def tour_state(attempts):
    """Состояние тура: не начат / начат / решён с баллом последней сдачи."""
    submitted = [a for a in attempts if a.submitted_at is not None]
    if submitted:
        last = max(submitted, key=lambda a: a.submitted_at)
        return {'status': 'done', 'attempt': last,
                'score': float(last.score) if last.score is not None else None,
                'max': float(last.max_score) if last.max_score is not None else None}
    if attempts:
        return {'status': 'started', 'attempt': attempts[0],
                'score': None, 'max': None}
    return {'status': 'none', 'attempt': None, 'score': None, 'max': None}


def _fmt(number):
    """34.0 → «34»; 34.5 → «34,5» — как пишут баллы по-русски."""
    if number is None:
        return ''
    if float(number).is_integer():
        return str(int(number))
    return ('%.1f' % number).replace('.', ',')


def cell_state(tours):
    """Сводка клетки по её турам: «1 тур из 2» или «81 из 96»."""
    total = len(tours)
    done = [t for t in tours if t['state']['status'] == 'done']
    started = [t for t in tours if t['state']['status'] == 'started']
    if total and len(done) == total:
        score = sum(t['state']['score'] or 0 for t in done)
        maximum = sum(t['state']['max'] or 0 for t in done)
        return {'status': 'done', 'label': '{} из {}'.format(_fmt(score),
                                                             _fmt(maximum))}
    if done:
        return {'status': 'started', 'label': '{} {} из {}'.format(
            len(done), plural(len(done), 'тур', 'тура', 'туров'), total)}
    if started:
        return {'status': 'started', 'label': 'начато'}
    return {'status': 'none', 'label': ''}


# ---------------------------------------------------------------------------
# Сетка «сезон × класс»
# ---------------------------------------------------------------------------

def _tour_row(variant, attempts):
    return {
        'variant': variant,
        'pk': variant.pk,
        'tour': variant.tour,
        'label': TOUR_LABELS.get(variant.tour, variant.tour or 'Тур'),
        'tasks': variant.n_items,
        'tasks_label': tasks_label(variant.n_items),
        'max_score': tour_max_score(variant),
        'max_label': _fmt(tour_max_score(variant)),
        'minutes': tour_minutes(variant),
        'with_solution': variant.n_solution,
        'with_criteria': variant.n_criteria,
        'pdfs': tour_pdfs(variant),
        'state': tour_state(attempts.get(variant.pk, [])),
    }


def _cell(variants, grades, colspan, attempts, label=True):
    tours = sorted((_tour_row(v, attempts) for v in variants),
                   key=lambda t: (TOUR_ORDER.get(t['tour'], 9), t['pk']))
    tasks = sum(t['tasks'] for t in tours)
    all_solution = bool(tours) and all(
        t['tasks'] and t['with_solution'] == t['tasks'] for t in tours)
    all_criteria = bool(tours) and all(
        t['tasks'] and t['with_criteria'] == t['tasks'] for t in tours)
    return {
        'key': 'c{}'.format(min(v.pk for v in variants)) if variants else '',
        'grades': list(grades),
        'colspan': colspan,
        'grades_label': grades_text(list(grades)) if label else '',
        'tours': tours,
        'tasks': tasks,
        'tasks_label': tasks_label(tasks) if variants else '',
        'all_solution': all_solution,
        'all_criteria': all_criteria,
        'state': cell_state(tours),
        'empty': not variants,
    }


def _row_cells(variants, columns, attempts):
    """Клетки одной строки сезона.

    Склейка — только когда комплекты строки делят классы без пересечений
    и каждый занимает сплошной кусок колонок. Иначе (пересечения, «дыра»
    посреди классов) — клетка на колонку, и общий вариант виден в каждой
    своей колонке: потерять его хуже, чем показать дважды.
    """
    groups = defaultdict(list)
    for variant in variants:
        key = tuple(sorted({g.grade for g in variant.grades.all()}))
        groups[key].append(variant)

    if not columns:
        return [_cell(variants, (), 1, attempts, label=False)]

    if set(groups) == {()}:
        # Классов нет ни у одного комплекта строки — одна клетка на все.
        return [_cell(groups[()], columns, len(columns), attempts, label=False)]

    disjoint = () not in groups
    seen = set()
    for key in groups:
        if not key:
            continue
        if seen & set(key):
            disjoint = False
        seen |= set(key)
        positions = [columns.index(g) for g in key if g in columns]
        if positions != list(range(positions[0], positions[0] + len(positions))):
            disjoint = False

    cells = []
    if disjoint:
        by_grade = {g: key for key in groups for g in key}
        index = 0
        while index < len(columns):
            key = by_grade.get(columns[index])
            if key is None:
                cells.append(_cell([], (columns[index],), 1, attempts))
                index += 1
                continue
            span = len(key)
            cells.append(_cell(groups[key], key, span, attempts,
                               label=span > 1))
            index += span
        return cells

    for grade in columns:
        chosen = [v for key, vs in groups.items()
                  if not key or grade in key for v in vs]
        cells.append(_cell(chosen, (grade,), 1, attempts))
    return cells


def stage_grid(stage, variants, attempts):
    """Сетка одного этапа: колонки-классы и строки сезонов, новые сверху.

    ⚠️ Сезон без комплектов ВНУТРИ диапазона (ВсОШ 2019/20) — пустая строка
    «—», а не пропуск: пропуск выглядел бы как опечатка в годах. Комплект
    без сезона идёт последней строкой «сезон не указан» — молча выбросить
    его значило бы спрятать настоящие задания.
    """
    columns = sorted({g.grade for v in variants for g in v.grades.all()})
    by_season = defaultdict(list)
    undated = []
    for variant in variants:
        start = season_start(variant.season)
        if start is None:
            undated.append(variant)
        else:
            by_season[start].append(variant)

    rows = []
    if by_season:
        for start in range(max(by_season), min(by_season) - 1, -1):
            found = by_season.get(start, [])
            rows.append({
                'start': start,
                'label': season_text(start),
                'empty': not found,
                'cells': _row_cells(found, columns, attempts) if found else [],
            })
    if undated:
        rows.append({'start': None, 'label': 'сезон не указан', 'empty': False,
                     'cells': _row_cells(undated, columns, attempts)})

    for row in rows:
        # Для телефона: какая клетка показывается во вкладке класса.
        row['by_grade'] = {}
        for cell in row['cells']:
            for grade in (cell['grades'] or columns):
                row['by_grade'][grade] = cell

    first = min(by_season) if by_season else None
    return {
        'stage': stage,
        'code': stage.code if stage is not None else '',
        'name': stage.name if stage is not None else 'Без этапа',
        'short': stage_short(stage),
        'columns': columns,
        'rows': rows,
        'seasons': len(by_season),
        'seasons_label': seasons_label(len(by_season)),
        'first_label': season_text(first) if first is not None else '',
        'cells': [c for r in rows for c in r['cells'] if not c['empty']],
    }


# ---------------------------------------------------------------------------
# Страница олимпиады
# ---------------------------------------------------------------------------

def problems_count(variant_ids):
    """Различных задач банка в комплектах — «Заданий у нас»."""
    return (OlympiadVariantItem.objects.filter(variant_id__in=list(variant_ids))
            .values('problem_id').distinct().count())


def nearest_stage_event(events, today=None):
    """Ближайший этап: первая подтверждённая будущая дата; иначе первый по
    порядку этап с ориентиром текущего сезона. Числа без даты не выдумываем."""
    today = today or date.today()
    stage_events = [e for e in events
                    if e.kind == OlympiadEvent.Kind.STAGE and e.stage_id]
    dated = [e for e in stage_events
             if e.is_confirmed and e.date_start and
             (e.date_end or e.date_start) >= today]
    if dated:
        return min(dated, key=lambda e: e.date_start)
    rest = [e for e in stage_events if not e.is_confirmed]
    rest.sort(key=lambda e: (e.stage.order, e.pk))
    return rest[0] if rest else None


def olympiad_page(olympiad, user=None, session_key='', today=None):
    """Всё, что считается на странице олимпиады: плашка фактов и сетки этапов."""
    variants = list(_annotated(base_variants().filter(olympiad=olympiad))
                    .order_by('stage__order', 'pk'))
    attempts = _attempts_for([v.pk for v in variants], user, session_key)

    by_stage = defaultdict(list)
    for variant in variants:
        by_stage[variant.stage_id].append(variant)
    stages = list(olympiad.stages.all())
    grids = [stage_grid(stage, by_stage[stage.pk], attempts)
             for stage in stages if by_stage.get(stage.pk)]
    if by_stage.get(None):
        grids.append(stage_grid(None, by_stage[None], attempts))

    seasons = {season_start(v.season) for v in variants} - {None}
    year = current_academic_year(today)
    events = [e for e in olympiad.events.all() if e.academic_year == year]
    nearest = nearest_stage_event(events, today)
    return {
        'grids': grids,
        'facts': {
            'problems': problems_count(v.pk for v in variants),
            'seasons': len(seasons),
            'first_season': season_text(min(seasons)) if seasons else '',
            'stages': len(stages),
            'nearest': nearest,
            'nearest_name': stage_short(nearest.stage) if nearest else '',
        },
        'variants_count': len(variants),
    }


def find_cell(page, key):
    """Клетка по ключу из `?open=` — или None (ключ чужой или устарел)."""
    for grid in page['grids']:
        for cell in grid['cells']:
            if cell['key'] == key:
                return grid, cell
    return None


# ---------------------------------------------------------------------------
# Главная раздела
# ---------------------------------------------------------------------------

def last_approved_level(olympiad):
    """Уровень по последнему УТВЕРЖДЁННОМУ перечню: (год, уровень) или None."""
    approved = [lv for lv in olympiad.levels.all()
                if lv.approval_status == lv.ApprovalStatus.APPROVED]
    if not approved:
        return None
    latest = max(approved, key=lambda lv: lv.academic_year)
    return latest


def home_rows(user=None, today=None):
    """Строки таблицы олимпиад главной: по группе показа и ручному рангу.

    Числа «сезонов · задач» — те же функции, что у страницы олимпиады:
    `base_variants` и подсчёт различных задач по позициям.
    """
    olympiads = list(visible_olympiads().prefetch_related('levels', 'events',
                                                          'events__stage'))
    base = base_variants()
    seasons = defaultdict(set)
    for olympiad_id, season in base.values_list('olympiad_id', 'season'):
        start = season_start(season)
        if start is not None:
            seasons[olympiad_id].add(start)
    problems = dict(
        OlympiadVariantItem.objects.filter(variant__in=base)
        .values('variant__olympiad_id')
        .annotate(n=Count('problem_id', distinct=True))
        .values_list('variant__olympiad_id', 'n'))
    followed = set()
    if user is not None and getattr(user, 'is_authenticated', False):
        followed = set(user.olympiad_follows.values_list('olympiad_id',
                                                         flat=True))
    year = current_academic_year(today)

    rows = []
    for olympiad in olympiads:
        events = [e for e in olympiad.events.all() if e.academic_year == year]
        level = last_approved_level(olympiad)
        n_seasons = len(seasons.get(olympiad.pk, ()))
        rows.append({
            'olympiad': olympiad,
            'section': 'fin' if olympiad.slug in FIN_SECTION else 'main',
            'level': level.level if level else None,
            'level_year': level.academic_year if level else '',
            'grades': olympiad.grades_label,
            'seasons': n_seasons,
            'problems': problems.get(olympiad.pk, 0),
            'has_tasks': bool(problems.get(olympiad.pk)),
            'nearest': next_event(events, today),
            'followed': olympiad.pk in followed,
        })
        row = rows[-1]
        row['seasons_label'] = seasons_label(n_seasons)
        count = row['problems']
        row['problems_label'] = '{} {}'.format(
            '{:,}'.format(count).replace(',', '\u00a0'),
            plural(count, 'задача', 'задачи', 'задач'))
        nearest = row['nearest']
        row['nearest_what'] = ''
        if nearest is not None:
            row['nearest_what'] = (stage_short(nearest.stage).lower()
                                   if nearest.stage else
                                   nearest.chip_label.lower())
    rows.sort(key=lambda r: (r['section'] != 'main',
                             -r['olympiad'].manual_rank,
                             r['olympiad'].name_short))
    return rows


def next_event(events, today=None):
    """Ближайшее событие олимпиады любого вида (для строки главной)."""
    ordered = feed_order(events, today)
    return ordered[0] if ordered else None


def feed_order(events, today=None):
    """Порядок ленты: подтверждённые будущие по дате, затем без даты —
    «по прошлому сезону», потом «ждём объявления», внутри — по ориентиру."""
    today = today or date.today()
    dated = sorted((e for e in events if e.is_confirmed and e.date_start
                    and (e.date_end or e.date_start) >= today),
                   key=lambda e: (e.date_start, e.pk))
    undated = sorted((e for e in events if not e.is_confirmed),
                     key=lambda e: (_STATUS_ORDER.get(e.date_status, 3),
                                    e.approx_text, e.pk))
    return dated + undated


def upcoming(today=None):
    """Лента «Ближайшее» главной: все события сезона у олимпиад раздела."""
    year = current_academic_year(today)
    events = list(OlympiadEvent.objects
                  .filter(academic_year=year,
                          olympiad__in=visible_olympiads())
                  .select_related('olympiad', 'stage'))
    return feed_order(events, today)


def continue_attempt(user):
    """Последняя незаконченная попытка вошедшего — блок «Продолжить».

    Истёкшая по времени — уже не «продолжить», её сдаёт движок при открытии.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return None
    from django.utils import timezone

    now = timezone.now()
    return (TrainingAttempt.objects
            .filter(user=user, submitted_at__isnull=True,
                    variant__in=base_variants())
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .select_related('variant', 'variant__olympiad', 'variant__stage')
            .order_by('-started_at').first())


# ---------------------------------------------------------------------------
# Страница олимпиады: что раскрыто, что видно, сводка этапов (Э2)
# ---------------------------------------------------------------------------

def stage_title(stage):
    """«Заключительный этап (два тура)» → «Заключительный этап».

    Макет 30.10: «2 тура» живёт в строке этапа, а не в названии. Базу не
    правим — приписку в скобках снимает показ.
    """
    if stage is None:
        return 'Без этапа'
    return stage.name.split(' (')[0].strip()


def stage_short(stage):
    """«Заключительный этап» → «Заключительный» — для плашек и вкладок."""
    title = stage_title(stage)
    for tail in (' этап', ' тур'):
        if title.endswith(tail):
            return title[:-len(tail)]
    return title


def _place_cells(grid):
    """У клетки — центр по колонкам для уголка панели (`--x` в шаблоне)."""
    total = max(len(grid['columns']), 1)
    for row in grid['rows']:
        start = 0
        for cell in row['cells']:
            cell['x_num'] = 2 * start + cell['colspan']
            cell['x_den'] = 2 * total
            start += cell['colspan']


def page_view(page, stage_code='', open_key='', show_all=False, grade=None):
    """Что показывает страница: этап, раскрытая клетка, видимые строки, класс.

    Ключи приходят из адреса (`?stage=`, `?open=`, `?all=1`, `?grade=`) —
    так раскрытие работает без JS. Чужой или устаревший ключ — просто
    ничего не раскрыто, не ошибка.
    """
    grids = page['grids']
    if not grids:
        return {'grid': None}
    by_code = {g['code']: g for g in grids}
    found = find_cell(page, open_key) if open_key else None
    if found is not None:
        grid, cell = found
    else:
        grid = by_code.get(stage_code) or grids[-1]
        cell = None
    _place_cells(grid)

    rows = grid['rows']
    open_index = None
    if cell is not None:
        for index, row in enumerate(rows):
            if cell in row['cells']:
                open_index = index
    show_all = show_all or (open_index is not None
                            and open_index >= SEASONS_VISIBLE)
    visible = rows if show_all else rows[:SEASONS_VISIBLE]
    hidden = [] if show_all else rows[SEASONS_VISIBLE:]

    columns = grid['columns']
    if grade not in columns:
        # Телефон: по умолчанию старший класс — как на макете (вкладка 11).
        if cell is not None and cell['grades']:
            grade = cell['grades'][-1]
        else:
            grade = columns[-1] if columns else None
    hidden_dated = [r for r in hidden if r['start'] is not None]
    return {
        'grid': grid,
        'cell': cell,
        'rows': visible,
        'hidden_rows': hidden,
        'more_label': ('Ещё {} · с {}'.format(
            seasons_label(len(hidden)), hidden_dated[-1]['label'])
            if hidden_dated else
            ('Ещё {}'.format(seasons_label(len(hidden))) if hidden else '')),
        'grade': grade,
    }


def stages_summary(olympiad, page, today=None):
    """Блок «Этапы»: номер, название, статус даты сезона, устройство, сезоны.

    ⚠️ Строка устройства собирается ТОЛЬКО из полей этапа и комплектов:
    сколько туров — по турам «1»/«2» основных комплектов, минуты и максимум —
    из `OlympiadStage`. Нет данных — строки нет.
    """
    year = current_academic_year(today)
    grids = {g['code']: g for g in page['grids']}
    events = {}
    for event in olympiad.events.all():
        if (event.academic_year == year and event.stage_id
                and event.kind == OlympiadEvent.Kind.STAGE):
            events.setdefault(event.stage_id, event)
    out = []
    for number, stage in enumerate(olympiad.stages.all(), start=1):
        grid = grids.get(stage.code)
        tours = set()
        if grid is not None:
            # Устройство этапа — по ПОСЛЕДНЕМУ сезону: у регионального ВсОШ
            # два тура были до 2019/20, а сейчас тур один.
            latest = next((r for r in grid['rows'] if not r['empty']
                           and r['start'] is not None), None)
            if latest is not None:
                tours = {t['tour'] for c in latest['cells'] for t in c['tours']
                         if t['tour'] in ('1', '2')}
        parts = []
        many = len(tours) > 1
        if many:
            parts.append('{} {}'.format(len(tours), plural(len(tours), 'тур',
                                                          'тура', 'туров')))
        if stage.duration_minutes:
            parts.append('{} мин{}'.format(stage.duration_minutes,
                                           ' на тур' if many else ''))
        if stage.max_score:
            parts.append('максимум {} {}{}'.format(
                stage.max_score, plural(stage.max_score, 'балл', 'балла',
                                        'баллов'),
                ' за тур' if many else ''))
        if stage.has_test_part is True:
            parts.append('есть тестовая часть')
        elif stage.has_test_part is False:
            parts.append('без тестовой части')
        regional_format = (olympiad.kind == Olympiad.Kind.VSOSH
                           and stage.code in ('sch', 'mun'))
        out.append({
            'number': number,
            'stage': stage,
            'title': stage_title(stage),
            'event': events.get(stage.pk),
            'meta': ' · '.join(parts),
            'regional_format': regional_format,
            'law_note': (olympiad.kind == Olympiad.Kind.VSOSH
                         and stage.code == 'final'),
            'grid': grid,
            'last': number == len(olympiad.stages.all()),
        })
    return out


def continue_cell(page):
    """«Продолжить» на странице олимпиады: последняя начатая, но не решённая
    клетка. Строки «1 тур — 34 из 48 · остался 2 тур» — из её туров."""
    best = None
    for grid in page['grids']:
        for cell in grid['cells']:
            if cell['state']['status'] != 'started':
                continue
            moments = [t['state']['attempt'].started_at for t in cell['tours']
                       if t['state']['attempt'] is not None]
            if moments and (best is None or max(moments) > best[0]):
                best = (max(moments), grid, cell)
    if best is None:
        return None
    _, grid, cell = best
    done = [t for t in cell['tours'] if t['state']['status'] == 'done']
    going = [t for t in cell['tours'] if t['state']['status'] == 'started']
    left = [t for t in cell['tours'] if t['state']['status'] == 'none']
    parts = ['{} — {} из {}'.format(t['label'], _fmt(t['state']['score']),
                                     _fmt(t['state']['max'])) for t in done]
    parts += ['идёт {}'.format(t['label']) for t in going]
    if left:
        parts.append('остался {}'.format(', '.join(t['label'] for t in left)))
    target = (going or left or cell['tours'])[0]
    row_label = next((r['label'] for r in grid['rows'] if cell in r['cells']),
                     '')
    grades = cell['grades_label'] or grades_text(cell['grades']) or 'все классы'
    total = len(cell['tours'])
    return {
        'title': '{} {} · {}'.format(stage_short(grid['stage']), row_label,
                                     grades),
        'stage_season': '{} {}'.format(stage_short(grid['stage']).lower(),
                                       row_label),
        'grades': grades,
        'sub': ' · '.join(parts),
        'tour': target,
        'resume': target['state']['status'] == 'started',
        'progress': round(100 * len(done) / total) if total else 0,
    }


def tours_done(page):
    """Сколько туров решающий сдал на этой олимпиаде — «решено 5 туров»."""
    return sum(1 for grid in page['grids'] for cell in grid['cells']
               for tour in cell['tours'] if tour['state']['status'] == 'done')


ROMAN = {1: 'I', 2: 'II', 3: 'III'}


def admission_summary(olympiad, benefits, level=None):
    """Плашка «Поступление» и блок «Что это даёт» — из льгот в базе.

    ВсОШ — льгота по закону (`Kind.VSOSH`), у остальных — по правилам вузов
    и уровню перечня. Нет льгот в базе — блока нет, слова в плашке нет.
    """
    real = [b for b in benefits if b.benefit_type != b.BenefitType.NONE]
    none = [b for b in benefits if b.benefit_type == b.BenefitType.NONE]
    if not real:
        return None
    bvi = any(b.benefit_type == b.BenefitType.BVI for b in real)
    law = olympiad.kind == Olympiad.Kind.VSOSH
    no_confirm = {b.confirm_label for b in real} == {'Не требуется'}
    if law:
        title = ('Без вступительных испытаний — в любом вузе России' if bvi
                 else real[0].gives_label)
        note = 'Право даёт закон об образовании' + (
            ', подтверждать баллом ЕГЭ не нужно' if no_confirm else '')
    else:
        title = ('{} уровень перечня {}'.format(ROMAN[level.level],
                                                 level.academic_year)
                 if level is not None and level.level in ROMAN
                 else real[0].gives_label)
        note = 'Льготу назначает вуз' + (
            '' if no_confirm else '; результат подтверждают баллом ЕГЭ')
    return {
        'short': 'БВИ' if bvi else '100 баллов',
        'law': law,
        'title': title,
        'note': note,
        'chip': 'диплом заключительного этапа' if law else '',
        'examples': real[:4],
        'none_names': ', '.join(b.program.university_short for b in none),
        'year': real[0].admission_year,
    }


# ---------------------------------------------------------------------------
# Главная: фильтры, лента, «Продолжить» (Э3)
# ---------------------------------------------------------------------------

KIND_FILTERS = (('vsosh', 'ВсОШ', Olympiad.Kind.VSOSH),
                ('perechen', 'Перечневые', Olympiad.Kind.PERECHEN),
                ('international', 'Международные', Olympiad.Kind.INTERNATIONAL),
                ('other', 'Другие', Olympiad.Kind.OTHER))
GRADE_FILTERS = (('le7', '≤7'), ('8', '8'), ('9', '9'), ('10', '10'),
                 ('11', '11'))
FEED_VISIBLE = 4


def logo_text(olympiad):
    """Текст квадрата на месте логотипа: «ВсОШ», «СПбГУ» — короткое
    название целиком, если оно не длиннее пяти знаков, иначе буквы."""
    short = (olympiad.name_short or '').strip()
    return short if 0 < len(short) <= 5 else olympiad.abbr


def level_chip(row):
    """Чип «Уровень» строки главной: ВсОШ, I–III уровень, международная…"""
    kind = row['olympiad'].kind
    if kind == Olympiad.Kind.VSOSH:
        return 'ВсОШ'
    if row['level'] in ROMAN:
        return '{} уровень'.format(ROMAN[row['level']])
    if kind == Olympiad.Kind.INTERNATIONAL:
        return 'международная'
    if kind == Olympiad.Kind.OTHER:
        return 'вне перечня'
    return ''


def grade_matches(olympiad, code):
    """Олимпиада принимает класс. «≤7» — `grade_min ≤ 7`.

    ⚠️ Классы неизвестны (оба поля пусты) — под фильтр класса олимпиада не
    попадает: сказать «тебе подходит» без данных нельзя.
    """
    low, high = olympiad.grade_min, olympiad.grade_max
    if low is None and high is None:
        return False
    if code == 'le7':
        return low is not None and low <= 7
    grade = int(code)
    return (low is None or low <= grade) and (high is None or grade <= high)


def filter_rows(rows, kind='', grade='', tasks=False, mine=False):
    kinds = {code: value for code, _label, value in KIND_FILTERS}
    out = rows
    if kind in kinds:
        out = [r for r in out if r['olympiad'].kind == kinds[kind]]
    if grade in dict(GRADE_FILTERS):
        out = [r for r in out if grade_matches(r['olympiad'], grade)]
    if tasks:
        out = [r for r in out if r['has_tasks']]
    if mine:
        out = [r for r in out if r['followed']]
    return out


def event_title(event):
    """«ВсОШ · школьный этап», «Высшая проба · открывается регистрация»."""
    what = {OlympiadEvent.Kind.REGISTRATION_OPEN: 'открывается регистрация',
            OlympiadEvent.Kind.REGISTRATION_CLOSE: 'закрывается регистрация',
            OlympiadEvent.Kind.RESULTS: 'результаты'}.get(event.kind)
    if what is None:
        what = stage_title(event.stage).lower() if event.stage else 'тур'
    return '{} · {}'.format(event.olympiad.name_short, what)


def event_date_label(event):
    """Короткая дата слева в ленте: «24 сентября» или «—» без даты."""
    from .models import MONTHS_GENITIVE
    if event.is_confirmed and event.date_start:
        day = event.date_start
        return '{} {}'.format(day.day, MONTHS_GENITIVE[day.month - 1])
    return '—'


STATUS_SHORT = {OlympiadEvent.DateStatus.CONFIRMED: ('confirmed', 'объявлено'),
                OlympiadEvent.DateStatus.APPROX_LAST_YEAR: ('approx', 'оценка'),
                OlympiadEvent.DateStatus.AWAITING: ('awaiting', 'ждём')}


def feed_rows(events):
    return [{'event': e, 'title': event_title(e), 'date': event_date_label(e),
             'sub': '' if e.is_confirmed else e.approx_text,
             'status': STATUS_SHORT.get(e.date_status, ('awaiting', 'ждём'))}
            for e in events]


def home_continue(user):
    """Блок «Продолжить» главной — та же сводка, что на странице олимпиады."""
    attempt = continue_attempt(user)
    if attempt is None:
        return None
    olympiad = attempt.variant.olympiad
    summary = continue_cell(olympiad_page(olympiad, user))
    if summary is None:
        return None
    summary['olympiad'] = olympiad
    return summary


# ---------------------------------------------------------------------------
# Календарь сезона полосами (Э4)
# ---------------------------------------------------------------------------

# Сетка календаря — август…май (доска Calendar): десять месяцев.
CAL_MONTHS = (8, 9, 10, 11, 12, 1, 2, 3, 4, 5)
CAL_MONTH_SHORT = {1: 'Янв', 2: 'Фев', 3: 'Мар', 4: 'Апр', 5: 'Май',
                   8: 'Авг', 9: 'Сен', 10: 'Окт', 11: 'Ноя', 12: 'Дек'}
_MONTH_STEMS = ('январ', 'феврал', 'март', 'апрел', 'ма[йя]', 'июн', 'июл',
                'август', 'сентябр', 'октябр', 'ноябр', 'декабр')


def _cal_bounds(year):
    from datetime import date as d
    start = int(year.split('/')[0])
    return d(start, 8, 1), d(start + 1, 6, 1)


def _month_date(year, month, last=False):
    """Число месяца сезона: август–декабрь — первый год, январь–май — второй."""
    import calendar as cal
    from datetime import date as d
    start = int(year.split('/')[0])
    real = start if month >= 8 else start + 1
    day = cal.monthrange(real, month)[1] if last else 1
    return d(real, month, day)


def months_in_text(text, year):
    """Где на сетке ориентир словами: (начало, конец) или None.

    ⚠️ ЧИСЕЛ НЕ ВЫДУМЫВАЕМ: берём только то, что ориентир в базе называет
    сам. «19 ноября» — точка в этот день; «обычно в ноябре», «в марте–апреле» —
    месяц целиком. Месяца в тексте нет — места на сетке нет.
    """
    import re
    low = (text or '').lower()
    point = re.search(r'(\d{1,2})\s+(' + '|'.join(_MONTH_STEMS) + r')', low)
    if point:
        month = next(i for i, s in enumerate(_MONTH_STEMS, 1)
                     if re.match(s, point.group(2)))
        if month in CAL_MONTHS:
            day = _month_date(year, month).replace(day=int(point.group(1)))
            return day, day
    found = []
    for match in re.finditer('|'.join(_MONTH_STEMS), low):
        month = next(i for i, s in enumerate(_MONTH_STEMS, 1)
                     if re.match(s, match.group(0)))
        if month in CAL_MONTHS:
            found.append(month)
    if not found:
        return None
    order = [CAL_MONTHS.index(m) for m in found]
    first, last = CAL_MONTHS[min(order)], CAL_MONTHS[max(order)]
    return _month_date(year, first), _month_date(year, last, last=True)


def _pct(day, lo, hi):
    return round(100 * (day - lo).days / (hi - lo).days, 2)


def _event_word(event):
    if event.kind == OlympiadEvent.Kind.STAGE:
        return stage_short(event.stage) if event.stage else 'Тур'
    return {OlympiadEvent.Kind.REGISTRATION_OPEN: 'Регистрация',
            OlympiadEvent.Kind.REGISTRATION_CLOSE: 'Конец регистрации',
            OlympiadEvent.Kind.RESULTS: 'Результаты'}[event.kind]


def _short_day(day):
    from .models import MONTHS_GENITIVE
    return '{} {}'.format(day.day, MONTHS_GENITIVE[day.month - 1][:3])


def calendar_season(year=None, today=None, user=None, only_mine=False):
    """Сезон полосами: дорожка на олимпиаду, полоса на событие.

    Регистрация «открылась + закрылась» с подтверждёнными датами — одна
    полоса «Регистрация 20 авг — 21 сен» (как на доске). Событие без
    подтверждённой даты рисуется НЕ сплошной: пунктир — по прошлому сезону,
    штриховка — ждём объявления (по обычным срокам). Без месяца в
    ориентире — строкой «без даты» под дорожкой.
    """
    today = today or date.today()
    year = year or current_academic_year(today)
    lo, hi = _cal_bounds(year)
    olympiads = list(visible_olympiads().prefetch_related('levels', 'stages'))
    events = list(OlympiadEvent.objects
                  .filter(academic_year=year, olympiad__in=visible_olympiads())
                  .select_related('stage').order_by('date_start', 'pk'))
    by_olympiad = defaultdict(list)
    for event in events:
        by_olympiad[event.olympiad_id].append(event)
    followed = set()
    if user is not None and getattr(user, 'is_authenticated', False):
        followed = set(user.olympiad_follows.values_list('olympiad_id', flat=True))

    lanes, without = [], []
    for olympiad in sorted(olympiads, key=lambda o: (-o.manual_rank, o.name_short)):
        own = by_olympiad.get(olympiad.pk, [])
        if only_mine and olympiad.pk not in followed:
            continue
        if not own and olympiad.pk not in followed:
            without.append(olympiad)
            continue
        bars, undated = [], []
        opened = {e.kind: e for e in own if e.is_confirmed and e.date_start}
        pair = None
        if {OlympiadEvent.Kind.REGISTRATION_OPEN,
                OlympiadEvent.Kind.REGISTRATION_CLOSE} <= set(opened):
            pair = (opened[OlympiadEvent.Kind.REGISTRATION_OPEN],
                    opened[OlympiadEvent.Kind.REGISTRATION_CLOSE])
        for event in own:
            if pair and event is pair[1]:
                continue
            if event.is_confirmed and event.date_start:
                start = event.date_start
                end = (pair[1].date_start if pair and event is pair[0]
                       else event.date_end or event.date_start)
                kind = 'ok'
                sub = (_short_day(start) if start == end
                       else '{} — {}'.format(_short_day(start), _short_day(end)))
                events_in = [event] + ([pair[1]] if pair and event is pair[0] else [])
            else:
                span = months_in_text(event.approx_text, year)
                if span is None:
                    undated.append({'event': event, 'word': _event_word(event),
                                    'status': event.status_word})
                    continue
                start, end = span
                kind = ('est' if event.date_status ==
                        OlympiadEvent.DateStatus.APPROX_LAST_YEAR else 'rule')
                sub = event.approx_text
                events_in = [event]
            if end < lo or start >= hi:
                undated.append({'event': event, 'word': _event_word(event),
                                'status': 'вне сетки сезона'})
                continue
            start, end = max(start, lo), min(end, hi)
            left = _pct(start, lo, hi)
            width = max(_pct(end, lo, hi) - left, 0)
            bars.append({'events': events_in, 'kind': kind,
                         # Подпись не шире места до правого края дорожки.
                         'label_room': round(100 - left, 2),
                         'past': (event.date_end or end) < today and kind == 'ok',
                         'left': left, 'width': width,
                         'point': start == end,
                         'word': 'Регистрация' if len(events_in) == 2
                         else _event_word(event),
                         'sub': sub})
        lanes.append({
            'olympiad': olympiad,
            'sub': ('{} {}'.format(len(olympiad.stages.all()),
                                   plural(len(olympiad.stages.all()), 'этап',
                                          'этапа', 'этапов'))
                    if olympiad.kind == Olympiad.Kind.VSOSH
                    else level_chip({'olympiad': olympiad,
                                     'level': getattr(last_approved_level(olympiad),
                                                      'level', None)})),
            'bars': bars,
            'undated': undated,
            'followed': olympiad.pk in followed,
        })

    today_pct = _pct(today, lo, hi) if lo <= today < hi else None
    seasons = sorted(set(OlympiadEvent.objects
                         .filter(olympiad__in=visible_olympiads())
                         .values_list('academic_year', flat=True)) | {year})
    from .models import MONTHS_GENITIVE
    return {
        'year': year,
        'seasons': seasons,
        'months': [CAL_MONTH_SHORT[m] for m in CAL_MONTHS],
        'lanes': lanes,
        'without': without,
        'today_pct': today_pct,
        'today_label': 'сегодня, {} {}'.format(today.day,
                                              MONTHS_GENITIVE[today.month - 1]),
        'events_total': sum(len(by_olympiad.get(l['olympiad'].pk, []))
                            for l in lanes),
    }


def calendar_search(query, user=None):
    """«Добавить олимпиаду»: поиск по названию среди олимпиад раздела."""
    query = (query or '').strip().lower()
    if not query:
        return []
    followed = set()
    if user is not None and getattr(user, 'is_authenticated', False):
        followed = set(user.olympiad_follows.values_list('olympiad_id', flat=True))
    out = []
    for olympiad in visible_olympiads().prefetch_related('levels'):
        if query in olympiad.name_short.lower() or query in olympiad.name_full.lower():
            out.append({'olympiad': olympiad, 'followed': olympiad.pk in followed,
                        'level': level_chip({'olympiad': olympiad, 'level': getattr(
                            last_approved_level(olympiad), 'level', None)}),
                        'grades': ('{}–{}'.format(olympiad.grade_min,
                                                  olympiad.grade_max)
                                   if olympiad.grade_min and olympiad.grade_max
                                   else '')})
    return out[:8]


# ---------------------------------------------------------------------------
# Тур: вход и решение (Э5)
# ---------------------------------------------------------------------------

def minutes_label(minutes):
    """210 → «3 ч 30 мин», 180 → «3 ч», 45 → «45 мин»."""
    if not minutes:
        return ''
    hours, rest = divmod(int(minutes), 60)
    if not hours:
        return '{} мин'.format(rest)
    return '{} ч'.format(hours) + (' {} мин'.format(rest) if rest else '')


def tour_info(variant):
    """Шапка тура: что за тур, сколько заданий, максимум, время, PDF.

    Те же функции, что в панели тура страницы олимпиады (`_tour_row`):
    число на входе и число в панели не могут разойтись.
    """
    annotated = _annotated(OlympiadVariant.objects.filter(pk=variant.pk)).get()
    grades = sorted(g.grade for g in annotated.grades.all())
    start = season_start(annotated.season)
    maximum = tour_max_score(annotated)
    minutes = tour_minutes(annotated)
    return {
        'variant': annotated,
        'label': TOUR_LABELS.get(annotated.tour, annotated.tour or 'Тур'),
        'stage_short': stage_short(annotated.stage),
        'stage_title': stage_title(annotated.stage),
        'season': season_text(start) if start is not None else 'сезон не указан',
        'grades': grades_text(grades) or 'все классы',
        'tasks': annotated.n_items,
        'tasks_label': tasks_label(annotated.n_items),
        'max_score': maximum,
        'max_label': _fmt(maximum),
        'minutes': minutes,
        'minutes_label': minutes_label(minutes),
        'pdfs': tour_pdfs(annotated),
        'with_criteria': annotated.n_criteria,
    }


def sibling_tours(variant):
    """Другие туры той же клетки (этап, сезон, те же классы) — «1 тур»."""
    grades = sorted(g.grade for g in variant.grades.all())
    out = []
    for other in (base_variants().filter(olympiad_id=variant.olympiad_id,
                                         stage_id=variant.stage_id,
                                         season=variant.season)
                  .exclude(pk=variant.pk).prefetch_related('grades')):
        if sorted(g.grade for g in other.grades.all()) == grades:
            out.append(other)
    out.sort(key=lambda v: (TOUR_ORDER.get(v.tour, 9), v.pk))
    return out


def last_result(variant, user=None, session_key=''):
    """Последняя сданная попытка решающего по комплекту — или None."""
    attempts = _attempts_for([variant.pk], user, session_key).get(variant.pk, [])
    done = [a for a in attempts if a.submitted_at is not None]
    return max(done, key=lambda a: a.submitted_at) if done else None


def spent_label(attempt):
    """Сколько решал: «3 ч 12 мин» — от начала до сдачи."""
    if attempt is None or attempt.submitted_at is None:
        return ''
    minutes = int((attempt.submitted_at - attempt.started_at).total_seconds() // 60)
    return minutes_label(max(minutes, 1))
