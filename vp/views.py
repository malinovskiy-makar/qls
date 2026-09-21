"""Экраны тренажёра «Высшая проба»: список → вход → прохождение → результат.

⚠️ ВХОД НЕ ТРЕБУЕТСЯ НИГДЕ, И ЭТО РЕШЕНИЕ, А НЕ ПРОПУСК: тренажёр открыт любому
посетителю. Вошедшего узнаём по пользователю, гостя — по сессии. Публичны
осознанно: список и вход (только опубликованные варианты), старт попытки и
страница результата (голый балл, без ответов). Всё остальное принадлежит
владельцу попытки: чужой код даёт 404 — как будто такой попытки нет.

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
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.urls import reverse
from django.views.decorators.http import require_POST

from problems import exam_engine
from vp import answers, blocks, scoring
from vp.models import VPAttempt, VPItem, VPVariant

logger = logging.getLogger(__name__)

# Коды попыток гостя, которые помнит его сессия: по ним он находит свою работу и
# после входа в аккаунт (ключ сессии при входе меняется, данные сессии — нет).
SESSION_ATTEMPTS = 'vp_attempts'
SESSION_ATTEMPTS_LIMIT = 50

# Раздел «Классы» на странице списка: (значение `grade_band`, подпись).
BANDS = (('9-10', '9–10 классы'), ('11', '11 класс'))

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


def _get_attempt(request, code):
    """Попытка владельца или 404 — ЕДИНСТВЕННОЕ место, где проверяется доступ.

    Владелец попытки — пользователь (если он у попытки есть), иначе тот браузер,
    код попытки которого лежит в сессии или чей ключ сессии записан в попытке.
    Именно 404, а не 403: чужую попытку не должно быть видно даже по факту
    существования.
    """
    attempt = get_object_or_404(
        VPAttempt.objects.select_related('variant'), public_code=code)
    if attempt.user_id is not None:
        if not (request.user.is_authenticated and attempt.user_id == request.user.pk):
            raise Http404
        return attempt
    key = request.session.session_key
    remembered = code in request.session.get(SESSION_ATTEMPTS, [])
    if not (remembered or (key and attempt.session_key == key)):
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
    return attempts.order_by('-started_at', '-id').first()


def _new_code():
    """Код попытки: 12 знаков, с повтором при коллизии."""
    while True:
        code = secrets.token_urlsafe(9)[:12]
        if not VPAttempt.objects.filter(public_code=code).exists():
            return code


# --------------------------------------------------------- список и вход

def index(request):
    """Опубликованные варианты по классам. Публичный экран."""
    variants = VPVariant.objects.all()
    if not _is_staff(request):
        variants = variants.filter(is_published=True)
    variants = list(variants)
    bands = []
    for code, label in BANDS:
        chosen = [v for v in variants if v.grade_band == code]
        if chosen:
            bands.append({'label': label, 'variants': chosen})
    return render(request, 'vp/index.html', {'bands': bands})


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
    return render(request, 'vp/intro.html', {
        'variant': variant,
        'sections': sections,
        'items_count': len(items),
        'whole_ranges': blocks.merged_ranges(whole),
        'partial_ranges': blocks.merged_ranges(partial),
        'penalty_example': example,
        'attempt': attempt,
        'attempt_answered': _answered_count(attempt) if attempt else 0,
    })


@require_POST
def start(request, slug):
    """Начинает попытку. Таймер запускает сервер в момент нажатия.

    Несданная попытка этого же человека не дублируется: нажатие возвращает в неё
    (двойной клик не плодит попыток).
    """
    variant = _variant_or_404(request, slug)
    if not variant.items.exists():
        raise Http404
    attempt = _current_attempt(request, variant)
    if attempt is None:
        with_timer = request.POST.get('with_timer', '1') == '1'
        user = request.user if request.user.is_authenticated else None
        if user is None and not request.session.session_key:
            request.session.create()
        attempt = VPAttempt.objects.create(
            variant=variant,
            user=user,
            session_key='' if user else request.session.session_key,
            with_timer=with_timer,
            expires_at=(timezone.now() + timedelta(seconds=variant.duration_seconds)
                        if with_timer else None),
            max_score=variant.max_score,
            public_code=_new_code(),
        )
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
    attempt = _get_attempt(request, code)
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
    attempt = _get_attempt(request, code)
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
