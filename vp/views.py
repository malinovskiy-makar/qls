"""Экраны тренажёра «Высшая проба»: список → вход → прохождение → результат.

⚠️ ЧИТАТЬ МОЖНО ВСЕМ, ПРОХОДИТЬ — ТОЛЬКО ВОШЕДШЕМУ (решение владельца 22.09.2026,
отменяет прежнее «вход не требуется нигде» от 21.09). Публичны осознанно:
посадочная, список вариантов, интро, правила, таблица лучших попыток и страница
результата (владельцу — полный разбор, остальным — голый балл без ответов).
Вход требует ровно один адрес — `start`: попытка без аккаунта не попала бы в
таблицу и потерялась бы при смене браузера. `my_attempts` — свой список, он тоже
только для вошедшего. Всё остальное принадлежит владельцу попытки: чужой код
даёт 404 — как будто такой попытки нет.

⚠️ ГОСТЕВЫЕ ВЕТКИ `_owns` И `_current_attempt` ОСТАЮТСЯ И ПОСЛЕ СТЕНЫ: по ним
живут старые ссылки на результаты гостевых попыток, заведённых до 22.09.

⚠️ ВЛАДЕЛЕЦ БЕРЁТСЯ ИЗ `request.user` И СЕССИИ, НИКОГДА ИЗ ДАННЫХ ЗАПРОСА. Адрес
попытки (`public_code`) — не право доступа, а только адрес; его проверяет ровно
одна функция, `_get_attempt` (ADR 0125).

⚠️ ОТВЕТЫ НЕ УХОДЯТ КЛИЕНТУ ДО СДАЧИ. В шаблон прохождения идут строки-словари
только с безопасными полями задания, а не сами задания: эталон, верные номера и
буквы связки змейки страница не видит.
"""
import json
import logging
import secrets
from datetime import timedelta

from django.db.models import Q
from django.db import transaction
from django.http import Http404, JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from catalog import seo
from problems import exam_engine
from vp import answers, blocks, board, landing, review, scoring, tracking
from vp.config import BANDS, TOUR_DATES
from vp.models import VPAnswer, VPAttempt, VPItem, VPVariant
from vp.templatetags.vp_extras import grade_label

logger = logging.getLogger(__name__)

# Коды попыток гостя, которые помнит его сессия: по ним он находит свою работу и
# после входа в аккаунт (ключ сессии при входе меняется, данные сессии — нет).
SESSION_ATTEMPTS = 'vp_attempts'
SESSION_ATTEMPTS_LIMIT = 50

# Клиентскому «время вышло» верим, только если серверные часы с ним согласны.
AUTO_SUBMIT_TOLERANCE = timedelta(seconds=3)

# Пачка автосохранения — до 44 ответов по паре сотен знаков; больше — не наш клиент.
MAX_SAVE_BYTES = 20000
MAX_SAVE_ANSWERS = 100

# Варианты, чьи подписи умещаются в такую длину (числа, «Нет верного ответа»),
# рисуются «таблетками» в ряд, а не столбцом.
PILL_MAX_LENGTH = 22


# ------------------------------------------------------------------ доступ

def _is_staff(request):
    return request.user.is_authenticated and request.user.is_staff


def _variant_or_404(request, slug):
    """Опубликованный вариант. Черновик видит только персонал — проверить до выпуска."""
    variants = VPVariant.objects.all()
    if not _is_staff(request):
        variants = variants.filter(is_published=True)
    return get_object_or_404(variants, slug=slug)


def _remember(request, code):
    """Кладёт код попытки в сессию (последние `SESSION_ATTEMPTS_LIMIT`)."""
    codes = [c for c in request.session.get(SESSION_ATTEMPTS, []) if c != code]
    codes.append(code)
    request.session[SESSION_ATTEMPTS] = codes[-SESSION_ATTEMPTS_LIMIT:]


def _owns(request, attempt):
    """Принадлежит ли попытка тому, кто спрашивает — ЕДИНСТВЕННОЕ правило доступа.

    Владелец попытки — пользователь (если он у попытки есть), иначе тот браузер,
    код попытки которого лежит в сессии или чей ключ сессии записан в попытке.
    """
    if attempt.user_id is not None:
        return request.user.is_authenticated and attempt.user_id == request.user.pk
    key = request.session.session_key
    remembered = attempt.public_code in request.session.get(SESSION_ATTEMPTS, [])
    return bool(remembered or (key and attempt.session_key == key))


def _get_attempt(request, code):
    """Попытка владельца или 404. Именно 404, а не 403: чужую попытку не должно быть
    видно даже по факту существования. Правило — в `_owns`, других проверок нет.
    """
    attempt = get_object_or_404(
        VPAttempt.objects.select_related('variant'), public_code=code)
    if not _owns(request, attempt):
        raise Http404
    return attempt


def _current_attempt(request, variant):
    """Несданная попытка этого человека по варианту (самая свежая) или None."""
    attempts = VPAttempt.objects.filter(variant=variant, submitted_at__isnull=True)
    if request.user.is_authenticated:
        attempts = attempts.filter(user=request.user)
    else:
        key = request.session.session_key
        mine = Q(public_code__in=request.session.get(SESSION_ATTEMPTS, []))
        if key:
            mine |= Q(session_key=key)
        attempts = attempts.filter(user__isnull=True).filter(mine)
    attempt = attempts.order_by('-started_at', '-id').first()
    if attempt is not None and _lapsed(attempt):
        # Показывать «продолжить» у работы, время которой вышло, значило бы обманывать.
        _finalize(attempt, auto=True)
        return None
    return attempt


def _new_code():
    """Код попытки: 12 знаков, с повтором при коллизии."""
    while True:
        code = secrets.token_urlsafe(9)[:12]
        if not VPAttempt.objects.filter(public_code=code).exists():
            return code


# ------------------------------------------------------ время и сдача

def _lapsed(attempt, now=None):
    """Время попытки вышло: срок и запас (`exam_engine.GRACE_SECONDS`) прошли.

    Запас нужен ради последнего ответа, который летит по сети в момент, когда таймер
    дошёл до нуля: «всё, что введено, засчитается» — обещание экрана, и оно
    выполняется только с запасом. Арифметику остатка не пишем: `can_accept` берём
    у `problems.exam_engine` — там же защита «остаток не больше выданного».
    """
    if attempt.submitted_at is not None or attempt.expires_at is None:
        return False
    return not exam_engine.can_accept(attempt, now or timezone.now())


def _finalize(attempt, auto, now=None):
    """Сдаёт попытку: баллы по КАЖДОМУ заданию, итог, момент сдачи. Одна функция на
    ручную и на автосдачу. Идемпотентна: сданную не пересчитывает и не трогает.

    Возвращает True, если именно этот вызов сдал попытку.
    """
    now = now or timezone.now()
    with transaction.atomic():
        locked = VPAttempt.objects.select_for_update().select_related('variant').get(pk=attempt.pk)
        if locked.submitted_at is not None:
            done = False
        else:
            _grade(locked)
            locked.score = scoring.score_attempt(locked)
            locked.max_score = locked.variant.max_score
            moment = now
            if locked.expires_at is not None and (auto or moment > locked.expires_at):
                # Время автосдачи — срок, а не «когда заметили»: участник уснул над
                # работой — сдано ровно по истечении, клиент нажал на долю секунды
                # раньше серверных часов — тоже.
                moment = locked.expires_at
            locked.submitted_at = moment
            locked.is_auto_submitted = bool(auto)
            locked.save(update_fields=['score', 'max_score', 'submitted_at', 'is_auto_submitted'])
            done = True
    attempt.refresh_from_db()
    return done


def _grade(attempt):
    """Баллы, максимум и «верно/нет/не отвечено» по каждому заданию варианта.

    Неотвеченные тоже получают строку: `score=0`, `is_correct=None`. Всё считает
    `scoring.score_item`.
    """
    existing = {a.item_id: a for a in attempt.answers.all()}
    fresh, changed = [], []
    for item in attempt.variant.items.all():
        answer = existing.get(item.pk)
        if answer is None:
            answer = VPAnswer(attempt=attempt, item=item)
            fresh.append(answer)
        else:
            changed.append(answer)
        answer.score, answer.is_correct = scoring.score_item(item, answer.raw)
        answer.max_score = item.points
    VPAnswer.objects.bulk_create(fresh)
    VPAnswer.objects.bulk_update(changed, ['score', 'max_score', 'is_correct'])


def _load_attempt(request, code):
    """Попытка владельца; если время вышло — сначала сдана автоматически.

    Через неё идут `take`, `save`, `time_left` и `finish`: любое обращение по
    истёкшей попытке закрывает её. Фонового задания, которое ходило бы и
    закрывало, нет, и на нашем хостинге быть не может.
    """
    attempt = _get_attempt(request, code)
    if _lapsed(attempt):
        _finalize(attempt, auto=True)
    return attempt


# --------------------------------------------------------- список и вход

def _published(request=None):
    """Опубликованные варианты с заданиями. Черновики сюда не попадают никогда:
    числа страницы не должны меняться от того, кто её открыл."""
    return list(VPVariant.objects.filter(is_published=True).prefetch_related('items'))


def _source_links(published):
    """Различные пары (подпись, ссылка) правообладателей — по одной ссылке на источник.

    Для окна правил. Из данных: сегодня это один Олмат, завтра может быть два, а
    без Олмата — ни одного, и раздел ссылок просто короче.
    """
    seen, links = set(), []
    for variant in published:
        pair = (variant.source_label, variant.source_url)
        if all(pair) and pair not in seen:
            seen.add(pair)
            links.append({'label': pair[0], 'url': pair[1]})
    return links


def index(request):
    """Посадочная: тур слева, таблица лучших попыток справа, полоса «моё» внизу.

    ⚠️ ЭКРАН БЕЗ ПРОКРУТКИ НА 1440×800 (образец — главная Wecon Rush). Всё, что не
    влезает, живёт в окне «Правила и формат», а не растит страницу. Числа формата и
    пример змейки — из ОПУБЛИКОВАННЫХ вариантов; список вариантов уехал на
    отдельный экран `/vp/variants/`, здесь на него только ссылка.
    """
    published = _published()
    groups = landing.format_groups(published)
    facts = landing.facts(groups)
    snake = landing.snake_example(published)
    rows, my_row, humans, attempts = board.top(me=request.user)
    has_demo = any(v.source_kind == VPVariant.SourceKind.DEMO for v in published)

    # Диапазон номеров змейки — из таблицы блоков, а не из головы.
    snake_row = next((r for g in groups for r in g['rows'] if r['block'] == 'snake'), None)
    snake_total = 0
    if snake is not None:
        snake_total = sum(1 for i in snake['variant'].items.all() if i.block == 'snake')

    guest_next = urlencode({'next': reverse('vp:index')})
    return render(request, 'vp/index.html', {
        'groups': groups,
        'facts': facts,
        'tour_dates': landing.dates_text(TOUR_DATES),
        'tour_dates_short': landing.dates_short(TOUR_DATES),
        'has_snake': snake_row is not None,
        'snake_range': snake_row['range'] if snake_row else '',
        'snake': snake,
        'snake_total': snake_total,
        'rows': rows, 'my_row': my_row, 'board_humans': humans, 'board_attempts': attempts,
        'mine': landing.my_block(request, published),
        'source_links': _source_links(published),
        'register_url': '' if request.user.is_authenticated else f"{reverse('register')}?{guest_next}",
        'login_url': '' if request.user.is_authenticated else f"{reverse('login')}?{guest_next}",
        'vp_events': [tracking.event('vp_landing_open')],
        **seo.vp_landing_meta(has_demo),
    })


def _variant_eyebrow(variant, published):
    """Надпись над названием карточки: «Демоверсия ВШЭ» или «Пробный · вариант k».

    Номер k – порядковый номер АВТОРСКОГО варианта внутри своего класса, по
    `order`. Он не хранится: список вариантов меняется, а номер должен идти
    подряд от единицы в том порядке, в каком карточки стоят на экране.
    """
    if variant.source_kind == VPVariant.SourceKind.DEMO:
        return 'Демоверсия ВШЭ'
    same = [v for v in published
            if v.grade_band == variant.grade_band
            and v.source_kind != VPVariant.SourceKind.DEMO]
    same.sort(key=lambda v: (v.order, v.pk))
    return f'Пробный · вариант {same.index(variant) + 1}' if variant in same else 'Пробный'


def variants(request):
    """Экран выбора класса и варианта.

    Публичный: гость видит карточки и формат, но вместо своего статуса – состав
    варианта. Персонал видит и черновики, с плашкой. Класс выбирается ссылкой
    `?band=`, без JS; неизвестное значение – первый класс, у которого есть варианты.
    """
    everything = VPVariant.objects.all()
    if not _is_staff(request):
        everything = everything.filter(is_published=True)
    everything = list(everything.prefetch_related('items'))
    published = [v for v in everything if v.is_published]

    bands = []
    for code, label in BANDS:
        chosen = sorted((v for v in everything if v.grade_band == code),
                        key=lambda v: (v.order, v.pk))
        if chosen:
            bands.append({'code': code, 'label': label, 'variants': chosen,
                          'count': len(chosen)})
    chosen_code = request.GET.get('band') or ''
    current = next((b for b in bands if b['code'] == chosen_code), bands[0] if bands else None)

    cards = []
    for variant in (current['variants'] if current else []):
        cards.append({
            'variant': variant,
            'eyebrow': _variant_eyebrow(variant, published),
            'status': landing.variant_status(request.user, variant),
            'count': variant.items.count(),
            'minutes': variant.duration_seconds // 60,
        })

    return render(request, 'vp/variants.html', {
        'bands': bands, 'current': current, 'cards': cards,
        'vp_events': [tracking.event('vp_variants_open')],
        **seo.vp_variants_meta(),
    })


ATTEMPT_FILTERS = (
    ('all', 'Все'),
    ('ranked', 'В таблице'),
    ('training', 'Тренировка'),
    ('open', 'Не сдана'),
)


def _attempt_kind(attempt, earlier):
    """Что написать в колонке «Статус»: `ranked` / `training` / `open`.

    `earlier` – есть ли у человека более ранняя попытка по этому же варианту:
    от неё зависит, повтор это или просто тренировка без таймера.
    """
    if attempt.submitted_at is None:
        return 'open'
    return 'ranked' if attempt.is_ranked else 'training'


@login_required
def my_attempts(request):
    """Свои попытки с разбором: всё, что человек прорешал, одним списком.

    Только вошедшему: чужой истории тут нет и быть не может. Перед выборкой
    просроченные попытки закрываются – иначе список врал бы про «не сдана».
    """
    live = (VPAttempt.objects
            .filter(user=request.user, submitted_at__isnull=True)
            .select_related('variant'))
    for attempt in live:
        if _lapsed(attempt):
            _finalize(attempt, auto=True)

    attempts = list(VPAttempt.objects
                    .filter(user=request.user)
                    .select_related('variant')
                    .prefetch_related('answers')
                    .order_by('-started_at', '-id'))

    best_attempt, best_place = board.my_best(request.user)
    seen = set()
    rows = []
    # Идём от старых к новым: «повтор» – это попытка, перед которой по тому же
    # варианту уже была другая.
    for attempt in reversed(attempts):
        repeat = attempt.variant_id in seen
        seen.add(attempt.variant_id)
        kind = _attempt_kind(attempt, repeat)
        rows.append({
            'attempt': attempt,
            'variant': attempt.variant,
            'kind': kind,
            'repeat': repeat,
            'answered': _answered_count(attempt),
            'count': attempt.variant.items.count(),
            'seconds': board.spent_seconds(attempt) if attempt.submitted_at else None,
            'place': (best_place if best_attempt is not None
                      and attempt.pk == best_attempt.pk else None),
        })
    rows.reverse()

    counts = {'all': len(rows)}
    for code, _ in ATTEMPT_FILTERS[1:]:
        counts[code] = sum(1 for r in rows if r['kind'] == code)
    chosen = request.GET.get('f') or 'all'
    if chosen not in counts:
        chosen = 'all'
    shown = rows if chosen == 'all' else [r for r in rows if r['kind'] == chosen]

    return render(request, 'vp/my.html', {
        'rows': shown, 'chosen': chosen,
        'filters': [{'code': c, 'label': label, 'count': counts[c]}
                    for c, label in ATTEMPT_FILTERS],
        'seo_noindex': True,
        'vp_events': [tracking.event('vp_my_open')],
    })


def _answered_count(attempt):
    """Сколько заданий отвечено. «Пусто» — по правилу подсчёта баллов."""
    return sum(1 for a in attempt.answers.all() if not scoring.is_blank(a.raw))


def intro(request, slug):
    """Что за вариант, из чего состоит, как считаются баллы, режим и старт.

    Числа — количество заданий по блокам и суммы баллов — считаются из заданий
    варианта в базе, в шаблоне их нет.
    """
    variant = _variant_or_404(request, slug)
    items = list(variant.items.all())
    sections = blocks.sections(items)
    partial = [s for s in sections if s['block'] in ('multi', 'analytic')]
    whole = [s for s in sections if s not in partial]

    example = None
    sample = next((i for s in partial for i in s['items'] if i.penalty), None)
    if sample is not None:
        example = scoring.penalty_example(sample.points)

    attempt = _current_attempt(request, variant)

    # Прошлые попытки по ЭТОМУ варианту: короткий список над выбором режима.
    # Порядок и содержание строк те же, что на `/vp/my/` – два разных вида
    # одного списка были бы двумя правдами.
    own = []
    has_ranked = False
    if request.user.is_authenticated:
        for done in (VPAttempt.objects
                     .filter(user=request.user, variant=variant, submitted_at__isnull=False)
                     .order_by('-started_at', '-id')):
            has_ranked = has_ranked or done.is_ranked
            own.append({'attempt': done, 'seconds': board.spent_seconds(done),
                        'kind': 'ranked' if done.is_ranked else 'training'})

    return render(request, 'vp/intro.html', {
        'variant': variant,
        'own_attempts': own,
        'has_ranked': has_ranked,
        'sections': sections,
        'items_count': len(items),
        'whole_ranges': blocks.merged_ranges(whole),
        'partial_ranges': blocks.merged_ranges(partial),
        'penalty_example': example,
        'attempt': attempt,
        'attempt_answered': _answered_count(attempt) if attempt else 0,
        # Гостю — адреса стены регистрации; вошедшему они не нужны и в HTML не идут.
        'register_url': '' if request.user.is_authenticated else _register_url(slug),
        'login_url': '' if request.user.is_authenticated else _login_url(slug),
        'vp_events': [tracking.event('vp_intro_open', variant=variant.slug)],
        **seo.vp_variant_meta(variant.title, grade_label(variant.grade_band), variant.year),
    })


def _register_url(slug):
    """Регистрация с возвратом на интро этого варианта."""
    return '%s?%s' % (reverse('register'),
                      urlencode({'next': reverse('vp:intro', args=[slug])}))


def _login_url(slug):
    """Вход с возвратом на интро этого варианта."""
    return '%s?%s' % (reverse('login'),
                      urlencode({'next': reverse('vp:intro', args=[slug])}))


@require_POST
def start(request, slug):
    """Начинает попытку. Таймер запускает сервер в момент нажатия.

    ⚠️ ЗДЕСЬ СТОИТ СТЕНА РЕГИСТРАЦИИ, И ПРОВЕРКА ИМЕННО СЕРВЕРНАЯ. Окно на интро —
    только вежливое объяснение; без JS форма доедет сюда и получит этот редирект.
    Гостю не заводится ни попытки, ни записи в сессии: он уходит на регистрацию и
    возвращается на тот же вариант.

    Несданная попытка этого же человека не дублируется: нажатие возвращает в неё
    (двойной клик не плодит попыток).
    """
    if not request.user.is_authenticated:
        return redirect(_register_url(slug))
    variant = _variant_or_404(request, slug)
    if not variant.items.exists():
        raise Http404
    attempt = _current_attempt(request, variant)
    if attempt is None:
        with_timer = request.POST.get('with_timer', '1') == '1'
        user = request.user if request.user.is_authenticated else None
        if user is None and not request.session.session_key:
            request.session.create()
        # Зачётность решается ОДИН РАЗ, здесь, и в базу уезжает вместе с попыткой:
        # первая попытка человека по этому варианту с таймером. Считать её задним
        # числом нельзя — смена правила переписала бы уже сыгранное (`vp/board.py`).
        is_ranked = True
        attempt = VPAttempt.objects.create(
            variant=variant,
            user=user,
            session_key='' if user else request.session.session_key,
            with_timer=with_timer,
            is_ranked=is_ranked,
            expires_at=(timezone.now() + timedelta(seconds=variant.duration_seconds)
                        if with_timer else None),
            max_score=variant.max_score,
            public_code=_new_code(),
        )
        tracking.defer(request, 'vp_start', variant=variant.slug, with_timer=with_timer)
    _remember(request, attempt.public_code)
    return redirect('vp:take', code=attempt.public_code)


# ------------------------------------------------------------ прохождение

def _figure_url(path):
    """Адрес рисунка в статике приложения или пусто.

    ⚠️ На боевом хранилище (`Manifest…`) `static()` бросает ValueError для файла,
    которого нет в манифесте. Опечатка в пути рисунка не должна ронять страницу
    прохождения пятисоткой посреди тура: рисунок пропускаем, в лог — предупреждение.
    """
    if not path:
        return ''
    try:
        return static(path)
    except ValueError:
        logger.warning('Рисунок ВП не найден в статике: %s', path)
        return ''


def _row(item, raw):
    """Задание для страницы прохождения — ТОЛЬКО то, что участнику можно видеть.

    Сами `VPItem` в шаблон не уходят: эталон, `correct`, `accepted`, решение и буквы
    связки страница не получает (тест `test_take_hides_answers`). Для `match` наружу
    идут только подписи пар (ключи `correct`), но не значения.
    """
    options = [{'n': o['n'], 'text': o['text']} for o in (item.options or [])
               if isinstance(o, dict) and 'n' in o]
    chosen = []
    if item.kind == VPItem.Kind.MULTI and isinstance(raw, list):
        chosen = [n for n in raw if isinstance(n, int)]
    elif item.kind == VPItem.Kind.SINGLE and isinstance(raw, int):
        chosen = [raw]
    pairs = []
    if item.kind == VPItem.Kind.MATCH and isinstance(item.correct, dict):
        given = raw if isinstance(raw, dict) else {}
        pairs = [{'key': key, 'value': given.get(key)} for key in item.correct]
    return {
        'number': item.number,
        'kind': item.kind,
        'statement': item.statement,
        'prefix': item.prefix,
        'suffix': item.suffix,
        'options': options,
        'pills': bool(options) and all(len(o['text']) <= PILL_MAX_LENGTH for o in options),
        'chosen': chosen,
        'text': raw if (item.kind == VPItem.Kind.SHORT_TEXT and isinstance(raw, str)) else '',
        'pairs': pairs,
        'figure_url': _figure_url(item.figure),
        'figure_caption': item.figure_caption,
        'figure_source': item.figure_source,
        'table_html': item.table_html,
        'points': item.points,
        'answered': not scoring.is_blank(raw),
    }


@never_cache
def take(request, code):
    """Страница прохождения: все задания варианта сразу, с сохранёнными ответами."""
    attempt = _load_attempt(request, code)
    if attempt.submitted_at is not None:
        return redirect('vp:result', code=code)
    variant = attempt.variant
    raw = {a.item_id: a.raw for a in attempt.answers.all()}
    items = list(variant.items.all())
    sections = blocks.sections(items)
    for section in sections:
        section['rows'] = [_row(item, raw.get(item.pk)) for item in section['items']]
        del section['items']          # в шаблон — только безопасные строки

    numbers = [item.number for item in items]
    answered = [row['number'] for s in sections for row in s['rows'] if row['answered']]
    seconds_left = exam_engine.seconds_remaining(attempt, timezone.now())
    config = {
        'saveUrl': reverse('vp:save', args=[code]),
        'timeUrl': reverse('vp:time', args=[code]),
        'numbers': numbers,
        'textNumbers': [i.number for i in items if i.kind == VPItem.Kind.SHORT_TEXT],
        'timed': attempt.with_timer,
        'seconds': seconds_left,
    }
    return render(request, 'vp/take.html', {
        'attempt': attempt, 'variant': variant, 'sections': sections,
        'numbers': numbers, 'answered_numbers': answered,
        'answered_count': len(answered), 'total': len(numbers),
        'seconds_left': seconds_left, 'config': config, 'seo_noindex': True,
        'finish_url': reverse('vp:finish', args=[code]),
        'vp_events': tracking.take_deferred(request),
    })


# ------------------------------------------------------- автосохранение

def _json(data, status=200):
    response = JsonResponse(data, status=status)
    response['Cache-Control'] = 'no-store'
    return response


def _read_save_body(request):
    """Тело сохранения → словарь или None.

    Обычный путь — JSON. `navigator.sendBeacon` на уходе со страницы не умеет ни
    заголовка `X-CSRFToken`, ни JSON-типа, поэтому он шлёт форму с полями
    `csrfmiddlewaretoken` и `payload` (тот же JSON строкой).
    """
    try:
        if request.content_type == 'application/json':
            body = json.loads(request.body.decode('utf-8'))
        else:
            body = json.loads(request.POST.get('payload', ''))
    except (ValueError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) else None


@require_POST
def save(request, code):
    """Автосохранение пачкой: `{"answers": [{"item": 12, "raw": "лаг"}, …]}`.

    Пишет только `raw` (upsert по паре попытка + задание), баллов не считает.
    Ответ: `{"saved": N, "seconds_remaining": M}`.
    """
    attempt = _load_attempt(request, code)
    now = timezone.now()
    if attempt.submitted_at is not None:
        return _json({'error': 'Работа сдана', 'expired': True,
                      'seconds_remaining': 0}, status=409)
    try:
        too_big = int(request.META.get('CONTENT_LENGTH') or 0) > MAX_SAVE_BYTES
    except ValueError:
        too_big = True
    if too_big:
        return _json({'error': 'Слишком большой запрос'}, status=400)
    body = _read_save_body(request)
    entries = body.get('answers') if body else None
    if not isinstance(entries, list) or len(entries) > MAX_SAVE_ANSWERS:
        return _json({'error': 'Неверный формат'}, status=400)

    by_number = {item.number: item for item in attempt.variant.items.all()}
    cleaned = {}                                   # повтор номера: побеждает последний
    for entry in entries:
        number = entry.get('item') if isinstance(entry, dict) else None
        item = by_number.get(number) if isinstance(number, int) and not isinstance(number, bool) else None
        if item is None:
            return _json({'error': 'Нет такого задания'}, status=400)
        try:
            cleaned[item.number] = (item, answers.clean_answer(item, entry.get('raw')))
        except answers.AnswerError as error:
            return _json({'error': f'Задание {number}: {error}'}, status=400)
    try:
        with transaction.atomic():
            answers.save_answers(attempt, list(cleaned.values()))
    except Exception:
        # ⚠️ Автосохранение НИКОГДА не отвечает пятисоткой: для клиента она
        # неотличима от «сохранилось», и он выбросил бы значения из очереди.
        # Отвечаем «попробуй ещё» — написанное остаётся на странице.
        logger.exception('Автосохранение ВП не удалось (попытка %s)', attempt.pk)
        return _json({'error': 'Не удалось сохранить, пробуем ещё', 'retry': True,
                      'seconds_remaining': exam_engine.seconds_remaining(attempt, now)})
    return _json({'saved': len(cleaned),
                  'seconds_remaining': exam_engine.seconds_remaining(attempt, now)})


# ------------------------------------------------------------------ время

@never_cache
@require_GET
def time_left(request, code):
    """«Сколько осталось» — самый дешёвый запрос страницы (клиент — раз в 20 секунд)."""
    attempt = _load_attempt(request, code)
    if attempt.submitted_at is not None:
        return _json({'expired': True, 'seconds_remaining': 0})
    left = exam_engine.seconds_remaining(attempt, timezone.now())
    return _json({'expired': left == 0, 'seconds_remaining': left})


# ------------------------------------------------------------------ сдача

def _final_answer(request, item):
    """Значение поля из формы сдачи или `_MISSING`, если поля в форме нет."""
    prefix = f'item-{item.number}'
    if item.kind == VPItem.Kind.MATCH:
        pairs = {key[len(prefix) + 1:]: value for key, value in request.POST.items()
                 if key.startswith(prefix + '.')}
        return pairs or _MISSING
    if prefix not in request.POST:
        return _MISSING
    sent = [v for v in request.POST.getlist(prefix) if v != '']
    if item.kind == VPItem.Kind.MULTI:
        return sent
    if item.kind == VPItem.Kind.SINGLE:
        return sent[-1] if sent else None
    return request.POST.get(prefix, '')


_MISSING = object()


@require_POST
def finish(request, code):
    """Сдача по кнопке (и по «времени вышло» — клиент шлёт `auto=1`).

    Форма везёт содержимое ВСЕХ полей ещё раз: последняя порция набранного могла
    не успеть уехать автосохранением, а терять её нельзя. Побеждает последний.

    ⚠️ ПУСТОЕ ЗНАЧЕНИЕ ИЗ ФОРМЫ НИЧЕГО НЕ СТИРАЕТ. Страница, отрисованная раньше, чем
    дошла последняя запись автосохранения (перезагрузка, вторая вкладка), несёт
    устаревшие пустые поля; «побеждает последний» затёр бы ими сохранённое. Стирание
    ответа идёт только через `save`: клиент шлёт там лишь то, что участник менял.
    Повторная сдача сданной попытки ничего не пересчитывает: идёт на результат.
    """
    attempt = _load_attempt(request, code)
    now = timezone.now()
    if attempt.submitted_at is None:
        if exam_engine.can_accept(attempt, now):
            for item in attempt.variant.items.all():
                value = _final_answer(request, item)
                if value is _MISSING:
                    continue
                try:
                    cleaned = answers.clean_answer(item, value)
                except answers.AnswerError:
                    continue        # мусорное поле не должно ронять сдачу всей работы
                if cleaned is None:
                    continue        # пустое из формы ответ не стирает (см. docstring)
                answers.save_answers(attempt, [(item, cleaned)])
        timed_out = attempt.expires_at is not None and (
            now >= attempt.expires_at
            or (request.POST.get('auto') == '1' and now >= attempt.expires_at - AUTO_SUBMIT_TOLERANCE))
        _finalize(attempt, auto=timed_out, now=now)
    return redirect('vp:result', code=code)


# --------------------------------------------------------------- результат

def _limit_seconds(attempt):
    """Лимит времени попытки на время, секунды. Считает `vp.board`."""
    return board.limit_seconds(attempt)


def _spent_seconds(attempt):
    """Сколько секунд ушло на попытку. Считает `vp.board`: там же этим меряется таблица."""
    return board.spent_seconds(attempt)


def _time_text(attempt):
    """Строка под баллом: «28:41 из 30:00» или «без таймера»."""
    if not attempt.with_timer or attempt.expires_at is None:
        return 'без таймера'
    limit, spent = _limit_seconds(attempt), _spent_seconds(attempt)
    return f'{spent // 60:02d}:{spent % 60:02d} из {limit // 60:02d}:{limit % 60:02d}'


def _percent(got, top):
    return max(0, min(100, round(float(got) / float(top) * 100))) if top else 0


@never_cache
def result(request, code):
    """Результат попытки. Адрес публичен, содержимое — по владельцу.

    ⚠️ ДВА ВИДА, РАЗВЕДЕНЫ НА УРОВНЕ ДАННЫХ. Владелец получает полный разбор: змейку
    цепочкой, арифметику тестов, решения. Всем остальным в контекст не попадает ни
    строка разбора: только балл, блоки, время и процентиль, без имени автора. Прятать чужому
    эталоны стилями нельзя — они не должны попасть в HTML (`test_review`). Несданную
    попытку видит только владелец, и его ведёт обратно к заданиям.
    """
    attempt = get_object_or_404(
        VPAttempt.objects.select_related('variant'), public_code=code)
    owner = _owns(request, attempt)
    if attempt.submitted_at is None:
        if not owner:
            raise Http404
        return redirect('vp:take', code=code)

    totals = scoring.block_totals(attempt)
    sections = blocks.sections(list(attempt.variant.items.all()))
    rows = []
    for section in sections:
        got, top = totals.get(section['block'], (0, section['total']))
        percent = _percent(got, top)
        rows.append({'name': section['titles']['short'], 'range': section['range'],
                     'score': got, 'max': top, 'percent': percent,
                     'tone': 'good' if percent >= 75 else 'mid' if percent >= 50 else 'bad'})
    top_score = attempt.max_score or attempt.variant.max_score
    slug = attempt.variant.slug
    events = []
    if owner and tracking.first_submit_view(request, code):
        events.append(tracking.event(
            'vp_submit', variant=slug, score=float(attempt.score or 0),
            answered=_answered_count(attempt), seconds_used=_spent_seconds(attempt),
            auto=attempt.is_auto_submitted))
    events.append(tracking.event('vp_result_open', variant=slug, own=owner))
    context = {
        'attempt': attempt, 'variant': attempt.variant, 'seo_noindex': True,
        'score': attempt.score, 'max': top_score, 'score_percent': _percent(attempt.score, top_score),
        'time_text': _time_text(attempt), 'auto': attempt.is_auto_submitted,
        'blocks': rows, 'is_owner': owner, 'vp_events': events,
    }
    comparison = review.comparison(attempt)
    if comparison is not None:
        comparison['median_percent'] = _percent(comparison['median'], top_score)
    context['comparison'] = comparison
    if owner:
        tests = review.tests_review(attempt)
        for row in tests:
            row['figure_url'] = _figure_url(row['figure'])
        context.update(
            chain=review.chain_review(attempt), tests=tests,
            practice_url=reverse('vp:practice', args=[code]),
            offer_signup=not request.user.is_authenticated)
    else:
        # ⚠️ ВЛАДЕЛЬЦА НЕ НАЗЫВАЕМ НИКОМУ, КРОМЕ НЕГО САМОГО — ни имя, ни логин, вошёл
        # автор или нет (ADR 0127, отмена части ADR 0126). Ссылка открывается кем угодно,
        # отдельного ника в проекте нет, логин обычно совпадает с именем, аудитория —
        # школьники.
        context['author'] = 'Участник'
        context['again_url'] = (reverse('vp:intro', args=[attempt.variant.slug])
                                if attempt.variant.is_published else '')
    return render(request, 'vp/result.html', context)


@require_POST
def practice_check(request, code):
    """«Дорешать вне зачёта»: проверка ответа на лету, `{"item": 27, "raw": "…"}`.

    ⚠️ НИЧЕГО НЕ ПИШЕТ: ни `VPAnswer`, ни балл попытки. Только владельцу и только по
    СДАННОЙ попытке (иначе 404, как чужая): балл уже записан и не меняется. Доступ
    через `_get_attempt`, а не `_load_attempt` — тот способен сдать просроченную
    попытку, то есть записать.
    """
    attempt = _get_attempt(request, code)
    if attempt.submitted_at is None:
        raise Http404
    try:
        too_big = int(request.META.get('CONTENT_LENGTH') or 0) > MAX_SAVE_BYTES
    except ValueError:
        too_big = True
    body = None if too_big else _read_save_body(request)
    number = body.get('item') if body else None
    item = None
    if isinstance(number, int) and not isinstance(number, bool):
        item = attempt.variant.items.filter(number=number).first()
    if item is None:
        return _json({'error': 'Нет такого задания'}, status=400)
    try:
        cleaned = answers.clean_answer(item, body.get('raw'))
    except answers.AnswerError as error:
        return _json({'error': str(error)}, status=400)
    if cleaned is None:
        return _json({'error': 'Пустой ответ'}, status=400)
    _, is_correct = scoring.score_item(item, cleaned)
    return _json({'is_correct': bool(is_correct), 'right': review.right_answer(item)})
