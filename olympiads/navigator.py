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
    """Залитые PDF комплекта: сначала условия, потом решения и критерии."""
    files = [f for f in variant.files.all() if f.file]
    files.sort(key=lambda f: (0 if f.kind.startswith('условия') else 1,
                              f.order, f.pk))
    return files


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
    return {
        'grids': grids,
        'facts': {
            'problems': problems_count(v.pk for v in variants),
            'seasons': len(seasons),
            'first_season': season_text(min(seasons)) if seasons else '',
            'stages': len(stages),
            'nearest': nearest_stage_event(events, today),
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
