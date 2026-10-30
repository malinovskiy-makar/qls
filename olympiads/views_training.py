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

from django.conf import settings
from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from problems.assignment_rows import item_max_score

from . import navigator
from . import training_engine as engine
from .criteria import split_solution
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
    """Вход в тур по доске Intro: два режима, список заданий, прошлый тур.

    ⚠️ Обещание «проверит ИИ» — только у заданий с критериями жюри и только
    при включённом флаге `OLYMPIAD_AI_CHECK`. Без критериев после сдачи —
    эталонное решение, и слов про ИИ на экране нет.
    """
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

    info = navigator.tour_info(variant)
    package = {i.problem_id: i for i in engine.package_items(variant)}
    rows = []
    for item in items:
        pos = package.get(item.catalog_problem_id)
        rows.append({'item': item, 'number': (pos.number if pos else '') or '',
                     'title': item.catalog_problem.title,
                     # У4: балл позиции пакета; неизвестен — числа нет.
                     'points': (float(pos.max_score) if pos and pos.max_score is not None
                                else None if pos else float(item_max_score(item))),
                     'criteria': bool(pos and pos.has_criteria)})
    ai_on = settings.OLYMPIAD_AI_CHECK
    with_criteria = [r for r in rows if r['criteria']]
    siblings = []
    for other in navigator.sibling_tours(variant):
        done = navigator.last_result(other, user, session_key)
        if done is not None:
            siblings.append({'variant': other, 'attempt': done,
                             'label': navigator.TOUR_LABELS.get(other.tour, other.tour),
                             'spent': navigator.spent_label(done)})
    context = _base_context(olympiad, variant, request)
    context.update({
        'info': info,
        'rows': rows,
        'blocked': blocked,
        'attempt': attempt,
        'timer_possible': bool(info['minutes']),
        'mode': request.GET.get('mode', ''),
        'ai_all': ai_on and rows and len(with_criteria) == len(rows),
        'ai_some': ai_on and with_criteria and len(with_criteria) < len(rows),
        'ai_numbers': ', '.join(r['number'] for r in with_criteria if r['number']),
        'siblings': siblings,
        'mine_last': navigator.last_result(variant, user, session_key),
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
    """Решение тура: доски TakeTimed (на время) и TakeFree (без времени).

    Задания — вкладками (`?task=<n>`, без JS — ссылки), ответ на открытое
    задание — фото листов или текст. ⚠️ ДО СДАЧИ НИ РЕШЕНИЯ, НИ ОТВЕТА, НИ
    КРИТЕРИЕВ: в режиме «Без времени» разбор и критерии показываются только
    у задания, которое уже сдано («Сдать задание»).
    """
    stub = soon_page(request)
    if stub is not None:
        return stub
    from problems import problem_types
    from problems.assignment_rows import (answer_parts, answer_input_name,
                                          display_parts, item_answer_form)

    from . import uploads
    from .criteria import split_solution

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
    package = {i.problem_id: i for i in engine.package_items(variant)}
    results = {r.problem_id: r for r in attempt.results.all()}
    checks = {c.problem_id: c for c in attempt.checks.all()}
    from . import ai_check
    sheets = {}
    for sheet in uploads.sheets(attempt):
        sheets.setdefault(sheet.problem_id, []).append(sheet)

    rows = []
    answered = 0
    for number, item in enumerate(items, start=1):
        problem = item.catalog_problem
        kind, options = item_answer_form(item)
        whole = drafts.get((problem.pk, None))
        pos = package.get(problem.pk)
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
        own_sheets = sheets.get(problem.pk, [])
        has_answer = (any(p['value'].strip() for p in parts) or bool(
            (whole.solution_draft if whole else '').strip()) or bool(own_sheets))
        answered += int(has_answer)
        # В режиме «Без времени» сданное задание закрыто для правки.
        locked = (not attempt.with_timer) and problem.pk in results
        solution, criteria = ('', '')
        if locked:
            solution, criteria = split_solution(problem.solution)
        result = results.get(problem.pk) if locked else None
        check = checks.get(problem.pk) if locked else None
        rows.append({
            'index': number,
            'number': (pos.number if pos else '') or str(number),
            'item': item,
            'problem': problem,
            'kind': kind,
            'is_test': kind in ('radio', 'checkbox'),
            'options': options,
            'chosen': [v.strip() for v in
                       ((parts[0]['value'] if parts else '') or '').split(',')],
            'parts': parts,
            'display_parts': display_parts(item),
            'solution_name': 'solution_item_%d' % item.pk,
            'solution_value': (whole.solution_draft if whole else '') or '',
            # У4: балл позиции пакета; неизвестен — числа нет.
            'points': (float(pos.max_score) if pos and pos.max_score is not None
                       else None if pos else float(item_max_score(item))),
            'answered': has_answer,
            'sheets': own_sheets,
            'sheets_left': uploads.MAX_SHEETS - len(own_sheets),
            'locked': locked,
            'result': result,
            'check': check,
            'check_parts': ai_check.by_part(check) if check else [],
            'reference': solution,
            'criteria': criteria,
            'has_criteria': bool(pos and pos.has_criteria),
            'phone': _phone_way(request, attempt, problem, kind, locked),
            # Поля краткого ответа — ТОЛЬКО У ТЕСТА (день 30.10, У2): по типу
            # задачи, а не по наличию эталона. У развёрнутой задачи ответ на
            # пункт — не обязательно число, ей — только «Решение»: фото или
            # текст; эталон уходит в ИИ-проверку (`ai_check.build_prompt`).
            'answer_fields': problem_types.is_test(problem.problem_type),
        })

    try:
        current = int(request.GET.get('task') or 1)
    except ValueError:
        current = 1
    current = min(max(current, 1), len(rows) or 1)
    # В сумму «17 из 24 за два задания» — только проверенные: «ждёт проверки» не ноль.
    done_rows = [r for r in rows if r['result'] is not None
                 and not r['result'].is_pending]
    context = _base_context(olympiad, variant, request)
    context.update({
        'attempt': attempt,
        'rows': rows,
        'current': current,
        'answered_count': answered,
        'seconds_left': engine.seconds_remaining(attempt, now),
        'info': navigator.tour_info(variant),
        'free_score': sum(float(r['result'].score or 0) for r in done_rows),
        # Максимум сданных — только если балл известен у каждого (У4).
        'free_max': (sum(r['points'] for r in done_rows)
                     if all(r['points'] is not None for r in done_rows) else None),
        'free_done': len(done_rows),
        'max_sheets': uploads.MAX_SHEETS,
        'ai_on': ai_check.enabled(),
        'dispute': _dispute_context(request, attempt, checks),
        'chat_on': _chat_available(),
        'current_str': str(current),
    })
    return render(request, 'olympiads/training_take.html', context)


def _phone_way(request, attempt, problem, kind, locked):
    """Путь «С телефона» для задания: токен и QR. Нет библиотеки QR — None."""
    from . import phone

    if locked or kind in ('radio', 'checkbox'):
        return None
    token = phone.issue(attempt, problem)
    url = request.build_absolute_uri(reverse('olympiads:phone_upload',
                                             args=[token.token]))
    svg = phone.qr_svg(url)
    if not svg:
        return None
    return {'token': token, 'url': url, 'svg': svg,
            'connected': token.used_at is not None}


def training_sheets(request, slug, pk):
    """Опрос компьютера раз в 3 с: листы задания и подключён ли телефон.

    `closed: true` — попытка сдана или задание сдано: страница перестаёт
    спрашивать. QR, которому осталось меньше пяти минут, приходит новым.
    """
    stub = soon_page(request)
    if stub is not None:
        return stub
    from problems.models import AssignmentItem

    from . import phone, uploads

    _, variant = _variant_or_404(slug, pk)
    user, session_key = _who(request)
    attempt = engine.current_attempt(variant, user, session_key)
    if attempt is None or engine.finalize_if_expired(attempt) or \
            not engine.can_accept(attempt, timezone.now()):
        return JsonResponse({'closed': True, 'sheets': []})
    item = get_object_or_404(AssignmentItem, pk=request.GET.get('item'),
                             assignment=engine.training_assignment(variant))
    problem = item.catalog_problem
    if not attempt.with_timer and problem.pk in engine.graded_problem_ids(attempt):
        return JsonResponse({'closed': True, 'sheets': []})
    way = _phone_way(request, attempt, problem, '', False)
    return JsonResponse({
        'closed': False,
        'connected': bool(way and way['connected']),
        'token': way['token'].token if way else '',
        'qr': way['svg'] if way else '',
        'sheets': [{'id': s.pk, 'page': s.page, 'source': s.source,
                    'pdf': s.mime == 'application/pdf',
                    'url': reverse('olympiads:training_sheet', args=[slug, pk, s.pk]),
                    'delete': reverse('olympiads:training_sheet_delete',
                                      args=[slug, pk, s.pk])}
                   for s in uploads.sheets(attempt, problem)],
    })


def _token_or_error(request, token):
    """(токен, None) или (токен, ответ 410); нет токена — 404."""
    from . import phone
    from .models import PhoneUploadToken

    found = (PhoneUploadToken.objects
             .select_related('attempt', 'attempt__variant',
                             'attempt__variant__olympiad', 'problem')
             .filter(token=token).first())
    if found is None:
        raise Http404
    if phone.state(found) != 'ok':
        return found, render(request, 'olympiads/phone_gone.html', {}, status=410)
    return found, None


def phone_upload(request, token):
    """Страница телефона после QR (доска UploadBPhone): без входа, только листы
    одного задания. Та же проверка файлов, что «с компьютера»."""
    stub = soon_page(request)
    if stub is not None:
        return stub
    from . import uploads

    found, gone = _token_or_error(request, token)
    if gone is not None:
        return gone
    if found.used_at is None:
        found.used_at = timezone.now()
        found.save(update_fields=['used_at'])
    attempt, problem = found.attempt, found.problem
    error = ''
    if request.method == 'POST':
        for uploaded in request.FILES.getlist('file') or [None]:
            try:
                uploads.save_sheet(attempt, problem, uploaded, source='phone')
            except uploads.UploadError as exc:
                error = str(exc)
                break
        if not error:
            return redirect('olympiads:phone_upload', token=token)
    info = navigator.tour_info(attempt.variant)
    pos = next((i for i in engine.package_items(attempt.variant)
                if i.problem_id == problem.pk), None)
    sheets = uploads.sheets(attempt, problem)
    return render(request, 'olympiads/phone_upload.html', {
        'token': found, 'info': info, 'olympiad': attempt.variant.olympiad,
        'problem': problem, 'number': (pos.number if pos else '') or '',
        'sheets': sheets, 'left': uploads.MAX_SHEETS - len(sheets),
        'error': error,
    }, status=400 if error else 200)


@require_POST
def training_item_submit(request, slug, pk):
    """«Сдать задание» в режиме «Без времени»: проверить одно задание.

    Последние значения полей приходят вместе с нажатием (как у сдачи тура).
    Сданное задание больше не правится; когда сданы все — тур сдан.
    """
    stub = soon_page(request)
    if stub is not None:
        return stub
    from problems.assignment_rows import answer_parts, part_key
    from problems.models import AssignmentItem
    from problems.part_grading import read_part_answers

    _, variant = _variant_or_404(slug, pk)
    user, session_key = _who(request)
    attempt = engine.current_attempt(variant, user, session_key)
    if attempt is None or attempt.with_timer:
        return redirect('olympiads:training_intro', slug=slug, pk=pk)
    assignment = engine.training_assignment(variant)
    item = get_object_or_404(AssignmentItem, pk=request.POST.get('item_id'),
                             assignment=assignment)
    problem = item.catalog_problem
    if problem.pk not in engine.graded_problem_ids(attempt):
        solution = request.POST.get('solution_item_%d' % item.pk)
        if solution:
            engine.save_draft(attempt, problem, None, solution)
        values = read_part_answers(request, item)
        for part in answer_parts(item):
            if values.get(part_key(part)):
                engine.save_draft(attempt, problem, values[part_key(part)], None,
                                  part=part)
        engine.grade_item(attempt, item)
        # ИИ-проверка по критериям — сразу, синхронно, с потолком времени
        # ядра. Нет флага, критериев, входа или согласия — модель не зовём.
        from . import ai_check
        ai_check.check_item(attempt, item, request.user)
    items = engine.variant_items(variant)
    if len(engine.graded_problem_ids(attempt)) >= len(items):
        engine.submit_attempt(attempt)
        return redirect('olympiads:training_result', slug=slug, pk=pk)
    index = next((n for n, i in enumerate(items, start=1) if i.pk == item.pk), 1)
    return redirect('{}?task={}'.format(
        reverse('olympiads:training_take', args=[slug, pk]), index))


@require_POST
def training_upload(request, slug, pk):
    """Лист решения «с компьютера»: один или несколько файлов к заданию.

    Отвечает JSON (`fetch` страницы) или перенаправлением обратно (без JS).
    Загружать можно, пока попытка открыта и задание не сдано.
    """
    stub = soon_page(request)
    if stub is not None:
        return stub
    from problems.models import AssignmentItem

    from . import uploads

    _, variant = _variant_or_404(slug, pk)
    user, session_key = _who(request)
    attempt = engine.current_attempt(variant, user, session_key)
    wants_json = request.headers.get('x-requested-with') == 'fetch'

    def answer(error='', status=400, sheets=()):
        if wants_json:
            return JsonResponse({'error': error, 'sheets': [
                {'id': s.pk, 'page': s.page,
                 'url': reverse('olympiads:training_sheet', args=[slug, pk, s.pk]),
                 'pdf': s.mime == 'application/pdf'} for s in sheets]},
                status=status if error else 200)
        if error:
            messages.warning(request, error)
        return redirect('{}?task={}'.format(
            reverse('olympiads:training_take', args=[slug, pk]),
            request.POST.get('task') or 1))

    if attempt is None or not engine.can_accept(attempt, timezone.now()):
        return answer('Попытка закрыта — листы больше не принимаются.', 409)
    assignment = engine.training_assignment(variant)
    item = AssignmentItem.objects.filter(pk=request.POST.get('item_id'),
                                         assignment=assignment).first()
    if item is None:
        return answer('Задание не найдено.', 404)
    if not attempt.with_timer and \
            item.catalog_problem_id in engine.graded_problem_ids(attempt):
        return answer('Задание уже сдано.', 409)
    files = request.FILES.getlist('file')
    if not files:
        return answer(uploads.WRONG_TYPE)
    saved = []
    for uploaded in files:
        try:
            saved.append(uploads.save_sheet(attempt, item.catalog_problem,
                                            uploaded, source='computer'))
        except uploads.UploadError as error:
            return answer(str(error), 400, saved)
    return answer(sheets=saved)


def _own_attempt_sheet(request, slug, pk, sheet_id):
    """Лист СВОЕЙ попытки (пользователь или гостевая сессия) — иначе 404."""
    from .models import TrainingUpload

    _, variant = _variant_or_404(slug, pk)
    user, session_key = _who(request)
    sheet = get_object_or_404(TrainingUpload.objects.select_related('attempt'),
                              pk=sheet_id, attempt__variant=variant)
    owner = sheet.attempt
    mine = (owner.user_id == user.pk) if user is not None else (
        owner.user_id is None and owner.session_key == session_key)
    if not mine:
        raise Http404
    return sheet


@require_POST
def training_sheet_delete(request, slug, pk, sheet_id):
    """Убрать лист, пока задание не сдано. Номера оставшихся листов сдвигаются."""
    stub = soon_page(request)
    if stub is not None:
        return stub
    sheet = _own_attempt_sheet(request, slug, pk, sheet_id)
    attempt = sheet.attempt
    task = request.POST.get('task') or 1
    if (attempt.submitted_at is None and
            (attempt.with_timer or sheet.problem_id not in
             engine.graded_problem_ids(attempt))):
        problem_id = sheet.problem_id
        sheet.file.delete(save=False)
        sheet.delete()
        for page, rest in enumerate(attempt.uploads.filter(problem_id=problem_id)
                                    .order_by('page', 'id'), start=1):
            if rest.page != page:
                rest.page = page
                rest.save(update_fields=['page'])
    if request.headers.get('x-requested-with') == 'fetch':
        return JsonResponse({'ok': True})
    return redirect('{}?task={}'.format(
        reverse('olympiads:training_take', args=[slug, pk]), task))


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

    if not attempt.with_timer and \
            item.catalog_problem_id in engine.graded_problem_ids(attempt):
        # Сданное задание закрыто: черновик после проверки не меняется.
        # ⚠️ НЕ 409 (день 30.10, У6). `platform/exam.js` читает любой 409 как
        # «время вышло» и сам отправляет форму на «Завершить тур»: запоздавшее
        # автосохранение только что сданного задания (страница ещё жива, пока
        # идёт проверка) сдавало весь тур. Отвечаем «принято, не записано» —
        # клиент выкинет значение из очереди, а терять нечего: последние поля
        # приехали вместе с «Сдать задание».
        return JsonResponse({'ok': True, 'locked': True, 'saved': False,
                             'seconds_remaining': None})

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
    from . import ai_check
    ai_check.enqueue(attempt)
    messages.success(request, 'Работа сдана.')
    return redirect('olympiads:training_result', slug=slug, pk=pk)


# ---------------------------------------------------------------------------
# Разбор
# ---------------------------------------------------------------------------

def training_result(request, slug, pk):
    """Результат тура по доске Result: итог, задания с баллами, критерии.

    «Как решали другие» и медианы — только из настоящих сданных попыток
    вошедших учеников на время и только от 20 человек (`navigator.others_stats`).
    Пока идёт очередь ИИ-проверки — «Проверено 2 из 4» и опрос `check-next/`.
    """
    stub = soon_page(request)
    if stub is not None:
        return stub
    from . import ai_check, dispute
    from .models import TrainingAttempt, TrainingCheck

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

    # Сдана по таймеру (автосдача) — очередь заводится здесь: идемпотентно.
    ai_check.enqueue(attempt)
    attempt.refresh_from_db()
    context = _base_context(olympiad, variant, request)
    context.update({'attempt': attempt})
    context.update(engine.attempt_result(attempt))

    info = navigator.tour_info(variant)
    package = {i.problem_id: i for i in engine.package_items(variant)}
    checks = {c.problem_id: c for c in attempt.checks.all()}
    stats = navigator.others_stats(variant, user, attempt.score) if attempt.with_timer else None
    for row in context['rows']:
        pos = package.get(row['problem'].pk)
        check = checks.get(row['problem'].pk)
        row['number_label'] = (pos.number if pos else '') or str(row['number'])
        row['check'] = check
        row['check_parts'] = ai_check.by_part(check) if check else []
        row['reference'], row['criteria'] = split_solution(row['problem'].solution)
        row['median'] = (stats['task_median'].get(row['problem'].pk)
                         if stats else None)
        row['bar'] = (round(100 * row['score'] / row['max_score'])
                      if row['score'] is not None and row['max_score'] else 0)
    waiting = [c for c in checks.values()
               if c.status in (TrainingCheck.Status.QUEUED, TrainingCheck.Status.RUNNING)]
    pair = []
    for other in navigator.sibling_tours(variant):
        done = navigator.last_result(other, user, session_key)
        if done is not None and done.score is not None:
            pair.append({'label': navigator.TOUR_LABELS.get(other.tour, other.tour),
                         'attempt': done, 'order': navigator.TOUR_ORDER.get(other.tour, 9)})
    both = None
    if pair and attempt.score is not None:
        parts = pair + [{'label': info['label'], 'attempt': attempt,
                         'order': navigator.TOUR_ORDER.get(variant.tour, 9)}]
        parts.sort(key=lambda p: p['order'])
        both = {'score': sum(float(p['attempt'].score) for p in parts),
                'max': sum(float(p['attempt'].max_score or 0) for p in parts),
                'terms': ' + '.join(navigator._fmt(p['attempt'].score) for p in parts),
                'count': len(parts)}
    open_dispute = _dispute_context(request, attempt, checks)
    context.update({
        'info': info,
        'spent': navigator.spent_label(attempt),
        'any_ai': any(c.status == TrainingCheck.Status.DONE for c in checks.values()),
        'waiting': len(waiting),
        'checks_total': len(checks),
        'checks_done': len(checks) - len(waiting),
        'stats': stats,
        'both': both,
        'solutions_pdf': info['pdfs']['solutions'],
        'dispute': open_dispute,
        'chat_on': _chat_available(),
    })
    return render(request, 'olympiads/training_result.html', context)


def _chat_available():
    from catalog import chat
    return chat.is_available()


def _dispute_context(request, attempt, checks):
    """Открытая панель «Оспорить оценку» (`?dispute=<задача>&code=<критерий>`)."""
    from . import dispute

    if not request.user.is_authenticated or attempt.user_id != request.user.pk:
        return None
    try:
        problem_id = int(request.GET.get('dispute') or 0)
    except ValueError:
        return None
    check = checks.get(problem_id)
    if check is None or check.status != check.Status.DONE:
        return None
    code = request.GET.get('code', '')
    if not code:
        # Подсвечиваем первую строку, где балл снят: о ней спорят чаще всего.
        code = next((r['code'] for r in check.criteria or []
                     if r['score'] < r['max']), '')
    pos = next((i for i in engine.package_items(attempt.variant)
                if i.problem_id == problem_id), None)
    return {'check': check, 'code': code, 'quote': dispute.quoted(check, code),
            'number': (pos.number if pos else '') or '',
            'history': dispute.history(check, request.user)}


def _dispute_check(request, variant):
    """Проверка СВОЕЙ последней попытки по задаче из POST — или None."""
    from .models import TrainingCheck

    if not request.user.is_authenticated:
        return None
    try:
        problem_id = int(request.POST.get('problem_id') or 0)
    except ValueError:
        return None
    return (TrainingCheck.objects
            .filter(attempt__variant=variant, attempt__user=request.user,
                    problem_id=problem_id, status=TrainingCheck.Status.DONE)
            .select_related('attempt', 'problem').order_by('-created_at').first())


@require_POST
def training_dispute(request, slug, pk):
    """Реплика «Оспорить оценку» — чат «Стола» в режиме `dispute`. Балл не меняет."""
    stub = soon_page(request)
    if stub is not None:
        return stub
    from catalog import chat
    from legal.guards import AI_CONSENT_TEXT, ai_consent_missing
    from problems.ai import core

    from . import dispute
    from .models import TrainingDraft

    _, variant = _variant_or_404(slug, pk)
    check = _dispute_check(request, variant)
    wants_json = request.headers.get('x-requested-with') == 'fetch'
    if check is None:
        return JsonResponse({'error': 'Оспорить можно только свою проверенную задачу.'},
                            status=404)
    back = '{}?dispute={}&code={}#dispute'.format(
        request.POST.get('back') or reverse('olympiads:training_result', args=[slug, pk]),
        check.problem_id, request.POST.get('code', ''))
    if ai_consent_missing(request.user):
        return JsonResponse({'error': AI_CONSENT_TEXT}, status=403) if wants_json \
            else redirect(back)
    message = (request.POST.get('message') or '').strip()[:chat.MESSAGE_MAX]
    if not message:
        return JsonResponse({'error': 'Напишите, с чем вы не согласны.'}, status=400) \
            if wants_json else redirect(back)
    draft = TrainingDraft.objects.filter(attempt=check.attempt, problem=check.problem,
                                         part__isnull=True).first()
    past = [{'role': role, 'text': text} for turn in dispute.history(check, request.user)
            for role, text in (('me', turn.user_text), ('ai', turn.reply))]
    try:
        reply = chat.answer(
            check.problem, message, past, request.user,
            last_attempt=dispute.CheckAsAttempt(check, draft.solution_draft if draft else ''),
            mode=dispute.MODE, quote=dispute.quoted(check, request.POST.get('code', '')),
            quote_source='criterion', extra_system=[dispute.criteria_block(check)])
    except core.AiUnavailable as exc:
        if wants_json:
            return JsonResponse({'error': str(exc)}, status=503)
        messages.warning(request, str(exc))
        return redirect(back)
    if wants_json:
        return JsonResponse({'reply': reply})
    return redirect(back)


@require_POST
def training_dispute_human(request, slug, pk):
    """«Отправить на проверку человеку»: задача ждёт человека, балл не меняется."""
    stub = soon_page(request)
    if stub is not None:
        return stub
    from . import dispute

    _, variant = _variant_or_404(slug, pk)
    check = _dispute_check(request, variant)
    if check is None:
        raise Http404
    dispute.ask_human(check)
    messages.success(request, 'Задание отправлено на проверку человеку.')
    back = request.POST.get('back') or reverse('olympiads:training_result', args=[slug, pk])
    if not url_has_allowed_host_and_scheme(back, {request.get_host()}, request.is_secure()):
        back = reverse('olympiads:training_result', args=[slug, pk])
    return redirect(back)


@require_POST
def training_check_next(request, slug, pk):
    """Очередь ИИ-проверки после тура на время: ОДНО задание за запрос.

    Без Celery и Redis: страница результата спрашивает, пока очередь не
    опустеет. Ответ — сколько проверено из скольких.
    """
    stub = soon_page(request)
    if stub is not None:
        return stub
    from . import ai_check
    from .models import TrainingAttempt, TrainingCheck

    _, variant = _variant_or_404(slug, pk)
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login'}, status=403)
    attempt = (TrainingAttempt.objects
               .filter(variant=variant, user=request.user,
                       submitted_at__isnull=False)
               .order_by('-submitted_at').first())
    if attempt is None:
        return JsonResponse({'error': 'no attempt'}, status=404)
    ai_check.run_next(attempt, request.user)
    checks = list(attempt.checks.all())
    waiting = [c for c in checks if c.status in (TrainingCheck.Status.QUEUED,
                                                 TrainingCheck.Status.RUNNING)]
    if request.headers.get('x-requested-with') != 'fetch' and \
            'application/json' not in request.headers.get('accept', ''):
        # Без JS — кнопка «Проверить следующее»: обратно на результат.
        return redirect('olympiads:training_result', slug=slug, pk=pk)
    return JsonResponse({'total': len(checks),
                         'done': len(checks) - len(waiting),
                         'finished': not waiting})
