"""Тренировочный режим глазами решающего: до старта → решение → разбор.

⚠️ ВХОД НЕ ТРЕБУЕТСЯ НИГДЕ. Ни `@login_required`, ни `@student_required`:
решать комплект олимпиады может любой посетитель. Это решение владельца, и
оно определяет всё устройство модуля — попытка адресуется либо
пользователем, либо ключом сессии.

⚠️ ГОСТЮ СЕССИЮ СОЗДАЁМ САМИ. Без неё `session_key` пуст, и гость терял бы
ответы при первом же обновлении страницы: попытку было бы не найти.

Время везде спрашивается у СЕРВЕРА через `olympiads.training_engine`, а тот
берёт арифметику у `problems.exam_engine`. Клиенту насчёт времени здесь не
верит ни одна вьюха.
"""
import json
import logging

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import training_engine as engine
from .models import Olympiad
from .views import _has_placeholder, soon_page

logger = logging.getLogger(__name__)


def _variant_or_404(slug, pk):
    olympiad = get_object_or_404(Olympiad, slug=slug)
    variant = get_object_or_404(olympiad.variants.select_related('stage'),
                                pk=pk)
    return olympiad, variant


def _session_key(request):
    """Ключ сессии решающего. Пустую сессию создаём — иначе гостя не найти."""
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or ''


def _who(request):
    """(пользователь или None, ключ сессии) — адрес попытки."""
    user = request.user if request.user.is_authenticated else None
    return user, _session_key(request)


def _base_context(olympiad, variant, request):
    return {
        'olympiad': olympiad,
        'variant': variant,
        'has_placeholder': _has_placeholder([olympiad]),
        'is_guest': not request.user.is_authenticated,
    }


# ---------------------------------------------------------------------------
# До старта
# ---------------------------------------------------------------------------

def training_intro(request, slug, pk):
    """Что за комплект, сколько задач, сколько времени, что будет с итогом."""
    stub = soon_page(request)
    if stub is not None:
        return stub
    olympiad, variant = _variant_or_404(slug, pk)
    user, session_key = _who(request)

    try:
        items = engine.variant_items(variant)
        blocked = ''
    except engine.TrainingError as error:
        items = []
        blocked = str(error)

    attempt = engine.current_attempt(variant, user, session_key)
    if attempt is not None:
        # Истёкшую закрываем прямо здесь: показывать «продолжить» у работы,
        # время которой давно вышло, — обманывать.
        engine.finalize_if_expired(attempt)
        attempt.refresh_from_db()
        if attempt.submitted_at is not None:
            attempt = None

    context = _base_context(olympiad, variant, request)
    context.update({
        'items_count': len(items),
        'max_score': engine.variant_max_score(variant),
        'blocked': blocked,
        'attempt': attempt,
        'timer_possible': bool(variant.duration_minutes),
    })
    return render(request, 'olympiads/training_intro.html', context)


@require_POST
def training_start(request, slug, pk):
    """Начинает попытку. Таймер запускает СЕРВЕР в момент нажатия."""
    stub = soon_page(request)
    if stub is not None:
        return stub
    olympiad, variant = _variant_or_404(slug, pk)
    user, session_key = _who(request)
    with_timer = request.POST.get('timer') == '1'

    attempt = engine.current_attempt(variant, user, session_key)
    if attempt is not None:
        engine.finalize_if_expired(attempt)
        attempt.refresh_from_db()
        if attempt.submitted_at is not None:
            attempt = None

    if request.POST.get('resume') == '1':
        if attempt is not None:
            return redirect('olympiads:training_take', slug=slug, pk=pk)
    elif attempt is not None and 'timer' not in request.POST:
        # Кнопка с карточки комплекта всегда несёт `timer`; её нажатие —
        # осознанный старт. А без него спрашиваем: перерешивать можно
        # сколько угодно, но молча затирать начатое нельзя.
        return redirect('olympiads:training_intro', slug=slug, pk=pk)

    try:
        engine.start_attempt(variant, user, session_key, with_timer)
    except engine.TrainingError as error:
        messages.warning(request, str(error))
        return redirect('olympiads:training_intro', slug=slug, pk=pk)
    return redirect('olympiads:training_take', slug=slug, pk=pk)


# ---------------------------------------------------------------------------
# Решение
# ---------------------------------------------------------------------------

def training_take(request, slug, pk):
    """Сам процесс: задачи, поля ответов, таймер, автосохранение."""
    stub = soon_page(request)
    if stub is not None:
        return stub
    from problems.assignment_rows import (answer_parts, answer_input_name,
                                          display_parts, item_answer_form,
                                          item_max_score)

    olympiad, variant = _variant_or_404(slug, pk)
    user, session_key = _who(request)
    attempt = engine.current_attempt(variant, user, session_key)
    if attempt is None:
        return redirect('olympiads:training_intro', slug=slug, pk=pk)

    now = timezone.now()
    if engine.finalize_if_expired(attempt, now):
        messages.warning(request, 'Время вышло — работа сдана автоматически.')
        return redirect('olympiads:training_result', slug=slug, pk=pk)

    items = engine.variant_items(variant)
    drafts = engine.drafts_map(attempt)

    rows = []
    answered = 0
    for number, item in enumerate(items, start=1):
        problem = item.catalog_problem
        kind, options = item_answer_form(item)
        whole = drafts.get((problem.pk, None))
        parts = []
        for part in answer_parts(item):
            key = part.pk if part is not None else None
            draft = drafts.get((problem.pk, key))
            parts.append({
                'part': part,
                'label': (part.label if part is not None else '') or '',
                'statement': (part.statement if part is not None else '') or '',
                'name': answer_input_name(item, part),
                'value': (draft.answer_draft if draft else '') or '',
            })
        has_answer = any(p['value'].strip() for p in parts) or bool(
            (whole.solution_draft if whole else '').strip())
        answered += int(has_answer)
        rows.append({
            'number': number,
            'item': item,
            'problem': problem,
            'kind': kind,
            'options': options,
            'chosen': [v.strip() for v in
                       ((parts[0]['value'] if parts else '') or '').split(',')],
            'parts': parts,
            'display_parts': display_parts(item),
            'has_parts': len(parts) > 1 or (parts and parts[0]['part']
                                            is not None),
            'solution_name': 'solution_item_%d' % item.pk,
            'solution_value': (whole.solution_draft if whole else '') or '',
            'points': float(item_max_score(item)),
            'answered': has_answer,
        })

    context = _base_context(olympiad, variant, request)
    context.update({
        'attempt': attempt,
        'rows': rows,
        'answered_count': answered,
        'seconds_left': engine.seconds_remaining(attempt, now),
    })
    return render(request, 'olympiads/training_take.html', context)


def training_time(request, slug, pk):
    """«Сколько осталось» — самый дешёвый запрос страницы.

    Существует ради того же, ради чего у контрольной: сверка идёт по
    таймеру, а не только вместе с автосохранением. Тот, кто смотрит на
    часы и не печатает, обязан сверяться с сервером тоже.
    """
    stub = soon_page(request)
    if stub is not None:
        return stub
    _, variant = _variant_or_404(slug, pk)
    user, session_key = _who(request)
    attempt = engine.current_attempt(variant, user, session_key)
    if attempt is None:
        return JsonResponse({'expired': True, 'seconds_remaining': 0})

    now = timezone.now()
    expired = (engine.finalize_if_expired(attempt, now)
               or attempt.submitted_at is not None)
    left = engine.seconds_remaining(attempt, now)
    return JsonResponse({'expired': bool(expired),
                         'seconds_remaining': 0 if expired else left})


@require_POST
def training_autosave(request, slug, pk):
    """Автосохранение одного поля. В ответе ВСЕГДА `seconds_remaining`."""
    stub = soon_page(request)
    if stub is not None:
        return stub
    from problems.models import AssignmentItem, ProblemPart

    _, variant = _variant_or_404(slug, pk)
    user, session_key = _who(request)
    attempt = engine.current_attempt(variant, user, session_key)
    if attempt is None:
        return JsonResponse({'error': 'Попытка не начата'}, status=400)

    now = timezone.now()
    if engine.finalize_if_expired(attempt, now) or \
            not engine.can_accept(attempt, now):
        return JsonResponse({'error': 'Время вышло', 'expired': True,
                             'seconds_remaining': 0}, status=409)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Неверный формат'}, status=400)

    assignment = engine.training_assignment(variant)
    item = get_object_or_404(AssignmentItem, pk=body.get('item_id'),
                             assignment=assignment)
    part = None
    raw_part = body.get('part_id')
    if raw_part:
        part = ProblemPart.objects.filter(
            pk=raw_part, problem_id=item.catalog_problem_id).first()
        if part is None:
            return JsonResponse({'error': 'Неизвестный пункт'}, status=400)

    try:
        left = engine.save_draft(
            attempt, item.catalog_problem,
            answer=body['answer'] if 'answer' in body else None,
            solution=body['solution'] if 'solution' in body else None,
            part=part)
    except Exception:
        # ⚠️ Автосохранение НИКОГДА не отвечает пятисоткой: для клиента она
        # неотличима от «сохранилось», и он выбросил бы значение из очереди.
        # Отвечаем «попробуй ещё» — написанное остаётся на странице.
        logger.exception('Автосохранение тренировки не удалось '
                         '(попытка %s, позиция %s)', attempt.pk, item.pk)
        return JsonResponse(
            {'error': 'Не удалось сохранить, пробуем ещё', 'retry': True,
             'seconds_remaining': engine.seconds_remaining(attempt, now)},
            status=200)

    return JsonResponse({'ok': True, 'seconds_remaining': left})


@require_POST
def training_finish(request, slug, pk):
    """Сдача. Последние значения полей принимаем вместе с нажатием.

    Форма шлёт содержимое ещё раз: последняя порция набранного могла не
    успеть уехать автосохранением, а терять её нельзя.
    """
    stub = soon_page(request)
    if stub is not None:
        return stub
    from problems.assignment_rows import answer_parts, part_key
    from problems.part_grading import read_part_answers

    _, variant = _variant_or_404(slug, pk)
    user, session_key = _who(request)
    attempt = engine.current_attempt(variant, user, session_key)
    if attempt is None:
        return redirect('olympiads:training_intro', slug=slug, pk=pk)

    now = timezone.now()
    if engine.finalize_if_expired(attempt, now):
        messages.warning(request, 'Время вышло — работа сдана автоматически.')
        return redirect('olympiads:training_result', slug=slug, pk=pk)

    if engine.can_accept(attempt, now):
        for item in engine.variant_items(variant):
            problem = item.catalog_problem
            solution = request.POST.get('solution_item_%d' % item.pk)
            # ⚠️ `None` тому полю, которое НЕ трогаем: пустая строка
            # означала бы «очистить», и решение стёрлось бы вместе с
            # сохранением ответа.
            if solution:
                engine.save_draft(attempt, problem, None, solution)
            values = read_part_answers(request, item)
            for part in answer_parts(item):
                if values.get(part_key(part)):
                    engine.save_draft(attempt, problem, values[part_key(part)],
                                      None, part=part)

    engine.submit_attempt(attempt, now)
    messages.success(request, 'Работа сдана.')
    return redirect('olympiads:training_result', slug=slug, pk=pk)


# ---------------------------------------------------------------------------
# Разбор
# ---------------------------------------------------------------------------

def training_result(request, slug, pk):
    """Разбор последней сданной попытки: балл, ответы, эталоны, решения."""
    stub = soon_page(request)
    if stub is not None:
        return stub
    from .models import TrainingAttempt

    olympiad, variant = _variant_or_404(slug, pk)
    user, session_key = _who(request)

    queryset = TrainingAttempt.objects.filter(variant=variant,
                                              submitted_at__isnull=False)
    if user is not None:
        queryset = queryset.filter(user=user)
    else:
        queryset = queryset.filter(user__isnull=True,
                                   session_key=session_key)
    attempt = queryset.order_by('-submitted_at').first()
    if attempt is None:
        return redirect('olympiads:training_intro', slug=slug, pk=pk)

    context = _base_context(olympiad, variant, request)
    context.update({'attempt': attempt})
    context.update(engine.attempt_result(attempt))
    return render(request, 'olympiads/training_result.html', context)
