"""Данные посадочной страницы `/vp/`: формат варианта, пример змейки, даты тура.

⚠️ ВСЕ ЧИСЛА — ИЗ ЗАДАНИЙ ОПУБЛИКОВАННЫХ ВАРИАНТОВ В БАЗЕ, а не из шаблона и не из
констант: число заданий, баллы блоков, диапазоны номеров. Испортишь задание — число на
странице меняется (тест `test_landing`). Сезонное — даты тура — только в `vp/config.py`.

Модуль ничего не пишет и баллов не считает: правила подсчёта — в `vp/scoring.py`,
разбиение на блоки — в `vp/blocks.py`, буквы связки змейки — `vp.loader.chain_letters`.
"""
from decimal import Decimal

from django.utils import timezone

from vp import blocks, config, scoring
from vp.loader import chain_letters
from vp.models import VPAttempt, VPVariant

_ZERO = Decimal('0')

_MONTHS = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа',
           'сентября', 'октября', 'ноября', 'декабря')

#: То же, но в плитку факта: «26 и 30 сент.». Месяцы, которые не сокращаются
#: («мая», «июня», «июля»), остаются как есть – сокращать их не во что.
_MONTHS_SHORT = ('янв.', 'февр.', 'мар.', 'апр.', 'мая', 'июня', 'июля', 'авг.',
                 'сент.', 'окт.', 'нояб.', 'дек.')

#: Чей вариант показывать в примере змейки в первую очередь. Пример открывает четыре
#: настоящих ответа варианта, поэтому берём то, что не жалко: демонстрационный, потом
#: прошлых лет, и лишь в конце — авторский, по которому ещё тренируются.
_KIND_ORDER = (VPVariant.SourceKind.DEMO, VPVariant.SourceKind.PAST,
               VPVariant.SourceKind.AUTHOR)


def _join(parts):
    """['26', '30'] → «26 и 30»; ['26', '27', '30'] → «26, 27 и 30»."""
    return parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ' и ' + parts[-1]


def dates_text(dates):
    """Даты тура словами: «26 и 30 сентября 2026»; пустой список — пустая строка."""
    days = sorted(dates)
    if not days:
        return ''
    if len({(d.year, d.month) for d in days}) == 1:
        return f'{_join([str(d.day) for d in days])} {_MONTHS[days[0].month - 1]} {days[0].year}'
    return _join([f'{d.day} {_MONTHS[d.month - 1]} {d.year}' for d in days])


def dates_short(dates):
    """Даты тура в плитку факта: «26 и 30 сент.»; пустой список — пустая строка.

    Года здесь нет: плитка стоит рядом с заголовком, где год уже сказан, а
    место в ней на одну строку. Разошлись месяцы — каждая дата со своим
    («30 сент. и 2 окт.»), иначе месяц один на всех.
    """
    days = sorted(dates)
    if not days:
        return ''
    if len({(d.year, d.month) for d in days}) == 1:
        return f'{_join([str(d.day) for d in days])} {_MONTHS_SHORT[days[0].month - 1]}'
    return _join([f'{d.day} {_MONTHS_SHORT[d.month - 1]}' for d in days])


def range_text(start, end):
    """Период тура словами: «с 13 по 22 ноября 2026», «с 30 сентября по 2 октября 2026»."""
    if (start.year, start.month) == (end.year, end.month):
        return f'с {start.day} по {end.day} {_MONTHS[end.month - 1]} {end.year}'
    return f'с {start.day} {_MONTHS[start.month - 1]} по {end.day} {_MONTHS[end.month - 1]} {end.year}'


def range_short(start, end):
    """Период тура в плитку факта: «13–22 нояб.»."""
    if (start.year, start.month) == (end.year, end.month):
        return f'{start.day}–{end.day} {_MONTHS_SHORT[end.month - 1]}'
    return f'{start.day} {_MONTHS_SHORT[start.month - 1]} – {end.day} {_MONTHS_SHORT[end.month - 1]}'


def tour_dates(tour=None):
    """`(даты словами, даты в плитку)` тура из `config.TOUR_DATES`; нет дат — две пустые строки."""
    kind, days = config.TOUR_DATES.get(config.CURRENT_TOUR if tour is None else tour, ('days', ()))
    if kind == 'range' and len(days) == 2:
        return range_text(*days), range_short(*days)
    return dates_text(days), dates_short(days)


# ---------------------------------------------------------------- формат

def _format_of(variant):
    """Формат одного варианта: блоки таблицы, итоги и то, что нужно для правил баллов."""
    items = list(variant.items.all())
    sections = blocks.sections(items)
    partial = [s for s in sections if s['block'] in blocks.SHARE_WITH_PENALTY]
    shared = [s for s in sections if s['block'] in blocks.SHARE_NO_PENALTY]
    whole = [s for s in sections if s not in partial and s not in shared]
    sample = next((i for s in partial for i in s['items'] if i.penalty), None)
    rows = [{
        'block': s['block'], 'range': s['range'], 'title': s['titles']['table'],
        'count': len(s['items']), 'total': s['total'],
    } for s in sections]
    fmt = {
        'rows': rows,
        'count': len(items),
        'total': sum((s['total'] for s in sections), _ZERO),
        'minutes': variant.duration_seconds // 60,
        'whole_ranges': blocks.merged_ranges(whole),
        'partial_ranges': blocks.merged_ranges(partial),
        'share_ranges': blocks.merged_ranges(shared),
        'number_ranges': blocks.merged_ranges([s for s in sections if s['block'] == 'number']),
        'partial_phrase': blocks.in_tasks(partial),
        'share_phrase': blocks.in_tasks(shared),
        'penalty_example': scoring.penalty_example(sample.points) if sample else None,
    }
    # Подпись — ровно то, что таблица и правила показывают. Баллы отдельных заданий внутри
    # блока (у 11 класса №43 и №44 по 4,5, у 9–10 – 4 и 5) и длительность в таблице не видны,
    # и две одинаковые таблицы под разными подписями были бы шумом. Длительность держит
    # `facts`: «за N минут» говорится, только если она у всех одна.
    fmt['signature'] = (fmt['count'], fmt['total'],
                        tuple((r['block'], r['range'], r['count'], r['total']) for r in rows),
                        tuple(fmt['whole_ranges']), tuple(fmt['partial_ranges']),
                        tuple(fmt['share_ranges']), fmt['penalty_example'])
    return fmt


def format_groups(published):
    """Формат опубликованных вариантов, сгруппированный: одинаковый формат — одна группа.

    Пока у 9–10 и 11 классов блоки и баллы совпадают, группа одна и подписи не нужно;
    разошлись — групп две, каждая подписана классами, как просит страница
    («расходятся по баллам — показывай по классу»).
    """
    groups = {}
    for variant in published:
        fmt = _format_of(variant)
        group = groups.setdefault(fmt['signature'], dict(fmt, bands=[], minutes_all=set()))
        group['minutes_all'].add(fmt['minutes'])
        if variant.grade_band not in group['bands']:
            group['bands'].append(variant.grade_band)
    result = list(groups.values())
    labels = config.all_band_labels()
    for group in result:
        group['label'] = ' и '.join(labels.get(b, f'{b} кл.') for b in group['bands'])
    return result


def facts(groups):
    """Число заданий, минуты и баллы «в этом году» — только если они общие для всех.

    Разные длительности или максимумы у вариантов – «не один формат», плиток нет: «за
    30 минут» тогда было бы правдой не про все. Число заданий может разниться по
    классам (2 тур: 17 у 9 класса, 18 у 10–11) — тогда оно пишется диапазоном
    `count_text` «17–18», а слово согласуется с большим (`count`).
    """
    if not groups:
        return None
    minutes = set().union(*(g['minutes_all'] for g in groups))
    totals = {g['total'] for g in groups}
    if len(minutes) != 1 or len(totals) != 1:
        return None
    counts = sorted({g['count'] for g in groups})
    return {'count': counts[-1], 'count_text': blocks.number_range(counts[0], counts[-1]),
            'minutes': next(iter(minutes)), 'total': next(iter(totals))}


# ---------------------------------------------------------------- змейка

def _marked(answer, is_last):
    """Ответ → (до, вторая буква, после): вторая буква — та, на какую начнётся следующий."""
    if is_last:
        return {'before': answer, 'mark': '', 'after': ''}
    seen = 0
    for index, char in enumerate(answer):
        if char.isalpha():
            seen += 1
            if seen == 2:
                return {'before': answer[:index], 'mark': char, 'after': answer[index + 1:]}
    return {'before': answer, 'mark': '', 'after': ''}


def _linked(items):
    """Подряд идущие задания, где вторая буква каждого — первая буква следующего."""
    for a, b in zip(items, items[1:]):
        first, second = chain_letters(a.chain_word())[1], chain_letters(b.chain_word())[0]
        if b.number != a.number + 1 or not second or first != second:
            return False
    return all(chain_letters(i.chain_word())[0] for i in items)


def snake_example(published, length=4):
    """Живая цепочка из `length` слов из опубликованного варианта или `None`.

    Задания идут подряд, связка между соседями настоящая. Из подходящих цепочек
    берётся та, где меньше ответов из нескольких слов: пример про «четыре слова» не
    должен читаться как четыре фразы.
    """
    def rank(variant):
        kind = variant.source_kind
        return (_KIND_ORDER.index(kind) if kind in _KIND_ORDER else len(_KIND_ORDER),
                variant.order, variant.pk)

    for variant in sorted(published, key=rank):
        snake = [i for i in variant.items.all() if i.block == 'snake' and i.answer]
        runs = [snake[i:i + length] for i in range(len(snake) - length + 1)
                if _linked(snake[i:i + length])]
        if runs:
            best = min(runs, key=lambda run: sum(len(i.answer.split()) > 1 for i in run))
            return {
                'variant': variant,
                'words': [_marked(i.answer, n == len(best) - 1) for n, i in enumerate(best)],
            }
    return None


# ------------------------------------------------------- «моё» на странице

def _lapsed_finalized(attempt):
    """Сдаёт попытку, если её время вышло, и говорит, жива ли она ещё.

    ⚠️ ЛЕНИВЫЙ ИМПОРТ `views` НАМЕРЕННО: `views` импортирует этот модуль, и
    импорт наверху файла замкнул бы круг. Правило автосдачи одно на весь
    раздел и живёт в `views` вместе с самой сдачей — второй копии не заводим.
    """
    from vp import views

    if views._lapsed(attempt):
        views._finalize(attempt, auto=True)
        return False
    return True


def current_attempt_any(request):
    """Живая несданная попытка этого человека по ЛЮБОМУ варианту или `None`.

    То же правило, что у `views._current_attempt`, но без фильтра по варианту:
    посадочная зовёт человека продолжить ту работу, которую он бросил, какой бы
    вариант это ни был. Просроченная сдаётся здесь же — показывать «продолжить»
    у работы, время которой вышло, значило бы обманывать.
    """
    if not request.user.is_authenticated:
        return None
    attempts = (VPAttempt.objects
                .filter(user=request.user, submitted_at__isnull=True)
                .select_related('variant')
                .order_by('-started_at', '-id'))
    for attempt in attempts:
        if _lapsed_finalized(attempt):
            return attempt
    return None


def answered_count(attempt):
    """Сколько заданий отвечено. «Пусто» — по правилу подсчёта баллов."""
    return sum(1 for a in attempt.answers.all() if not scoring.is_blank(a.raw))


def variant_status(user, variant):
    """Что показать про вариант конкретному человеку.

    Ключи: `kind` (`none` / `live` / `ranked` / `done`), `live` (несданная живая
    попытка), `answered`, `count` (заданий в варианте), `best` (лучший балл среди
    сданных), `ranked` (зачётная сданная попытка), `seconds`.

    Гостю статуса нет вовсе: `None`. Он видит формат варианта, а не свою историю.
    """
    from vp import board

    if user is None or not getattr(user, 'is_authenticated', False):
        return None
    attempts = list(VPAttempt.objects.filter(user=user, variant=variant)
                    .prefetch_related('answers'))
    live = next((a for a in sorted(attempts, key=lambda a: (a.started_at, a.pk), reverse=True)
                 if a.submitted_at is None and _lapsed_finalized(a)), None)
    submitted = [a for a in attempts if a.submitted_at is not None]
    ranked = next((a for a in submitted if a.is_ranked), None)
    best = max((a.score for a in submitted if a.score is not None), default=None)
    if live is not None:
        kind = 'live'
    elif ranked is not None:
        kind = 'ranked'
    elif submitted:
        kind = 'done'
    else:
        kind = 'none'
    return {
        'kind': kind,
        'live': live,
        'answered': answered_count(live) if live is not None else 0,
        'count': variant.items.count(),
        'best': best,
        'ranked': ranked,
        'seconds': board.spent_seconds(ranked) if ranked is not None else None,
        'started': bool(attempts),
    }


def _plural(n, one, few, many):
    n = abs(int(n)) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    return one if n == 1 else few if 2 <= n <= 4 else many


def variant_meta(variant, parts=('count', 'minutes')):
    """Строка меты варианта — ОДНА на раздел: «Демоверсия ВШЭ · 2026/27 · 18 заданий · 70 мин»
    (карточка экрана вариантов) или с `parts=('count', 'points')` — «… · 18 заданий ·
    100 баллов» (интро). Происхождение: демонстрационный — «Демоверсия ВШЭ», иначе
    подпись вида; учебный год из `year`: 2026 → «2026/27». Числа — из заданий варианта."""
    from vp.templatetags.vp_extras import points_word

    items = list(variant.items.all())
    bits = ['Демоверсия ВШЭ' if variant.source_kind == VPVariant.SourceKind.DEMO
            else variant.get_source_kind_display()]
    if variant.year:
        bits.append(f'{variant.year}/{(int(variant.year) + 1) % 100:02d}')
    for part in parts:
        if part == 'count':
            bits.append(f'{len(items)} {_plural(len(items), "задание", "задания", "заданий")}')
        elif part == 'minutes':
            bits.append(f'{variant.duration_seconds // 60} мин')
        elif part == 'points':
            bits.append(points_word(sum((i.points for i in items), _ZERO)))
    return ' · '.join(bits)


def _dots(user, published):
    """Квадратики «пройдено»: по одному на опубликованный вариант.

    `ok` — есть сданная попытка, `half` — вариант начат, но не сдан, пусто —
    не трогали. Порядок тот же, что в списке вариантов: по классам и `order`.
    """
    submitted = set(VPAttempt.objects
                    .filter(user=user, submitted_at__isnull=False)
                    .values_list('variant_id', flat=True))
    started = set(VPAttempt.objects.filter(user=user).values_list('variant_id', flat=True))
    dots, done = [], 0
    for variant in published:
        if variant.pk in submitted:
            dots.append('ok')
            done += 1
        elif variant.pk in started:
            dots.append('half')
        else:
            dots.append('')
    return dots, done


def student_band(request):
    """Класс ученика для всего раздела — ЕДИНСТВЕННЫЙ источник: код из `config.bands()`
    или `None`. Посадочная (вкладка таблицы, «моё»), экран вариантов и «что дальше»
    спрашивают только её.

    Порядок:
    1. явный выбор в запросе: `?band=` (экран вариантов) или `?board=` (вкладка таблицы
       без JS) — известный код запоминается в `request.session['vp_band']`;
    2. (место под будущий источник «класс из анкеты» — сессия стены: он встанет сюда,
       сразу после явного выбора);
    3. `request.session['vp_band']` (туда же пишет `views.remember_band` — вкладка с JS);
    4. класс последней попытки вошедшего в текущем туре;
    5. `None`.
    """
    codes = [code for code, _ in config.bands()]
    for key in ('band', 'board'):
        asked = request.GET.get(key)
        if asked in codes:
            request.session['vp_band'] = asked
            return asked
    remembered = request.session.get('vp_band')
    if remembered in codes:
        return remembered
    if request.user.is_authenticated:
        last = (VPAttempt.objects.filter(user=request.user, variant__tour=config.CURRENT_TOUR)
                .order_by('-started_at', '-id').select_related('variant').first())
        if last is not None and last.variant.grade_band in codes:
            return last.variant.grade_band
    return None


def _ordered(published):
    """Опубликованные варианты в порядке страницы выбора: по классам, потом `order`."""
    order = {code: n for n, (code, _) in enumerate(config.bands())}
    return sorted(published, key=lambda v: (order.get(v.grade_band, len(order)), v.order, v.pk))


def my_block(request, published):
    """Полоса «моё» под сеткой: начатая работа, лучшая попытка, пройдено.

    Гостю полоса не нужна — вернётся `None`, и шаблон покажет приглашение
    зарегистрироваться. Все числа — из попыток этого человека, не из сессии.
    «Следующий вариант» и «пройдено» — по вариантам СВОЕГО класса (`student_band`);
    класса нет — по всем.
    """
    from problems import exam_engine
    from vp import board

    user = request.user
    if not user.is_authenticated:
        return None
    band = student_band(request)
    ordered = _ordered(published)
    if band is not None:
        ordered = [v for v in ordered if v.grade_band == band]

    current = current_attempt_any(request)
    dots, done = _dots(user, ordered)
    untouched = [v for v, dot in zip(ordered, dots) if dot == '']
    best_attempt, place = board.my_best(user)

    return {
        'current': current,
        'current_answered': answered_count(current) if current is not None else 0,
        'current_count': current.variant.items.count() if current is not None else 0,
        # Остаток времени считает `exam_engine`, как везде в разделе: своей
        # арифметики остатка в проекте нет и заводить её нельзя.
        'current_left': (exam_engine.seconds_remaining(current, timezone.now())
                         if current is not None and current.with_timer else None),
        # Следующий вариант — первый, которого человек ещё не открывал.
        'next_variant': untouched[0] if untouched else None,
        'best': best_attempt,
        'best_place': place,
        'best_seconds': board.spent_seconds(best_attempt) if best_attempt else None,
        'dots': dots,
        'done': done,
        'total': len(ordered),
        'all_done': not untouched,
        'band': band,
        'band_label': dict(config.bands()).get(band, ''),
    }
