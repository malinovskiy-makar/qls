"""
Профиль пользователя: данные, сохранённое (задачи и графики), статистика.

Живёт в `problems`, а не в `teacher`/`student`: профиль есть у всех ролей,
и класть его в кабинет одной из них значило бы закрыть его для остальных.
"""
import io
import json
import re
import time

from django.utils import formats

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

# Problem нужен и в профиле (пометка «снята с публикации»), и при
# сохранении — поднимаем импорт на уровень модуля.
from .models import Problem
from .forms_accounts import AvatarForm, ProfileForm
from .models_platform import (
    CustomProblem,
    SavedFolder,
    SavedGraph,
    SavedProblem,
    UserProfile,
)


# ---------------------------------------------------------------------------
# Фаза 15 — страница профиля
# ---------------------------------------------------------------------------

def _profile_facts(user, profile_obj):
    """Полоса фактов над карточкой профиля: три-четыре числа, не больше.

    ⚠️ СВОЕГО РАСЧЁТА ЗДЕСЬ НЕТ. Берём то, что уже посчитано и закэшировано
    в `problems.stats.full_stats`; если оно почему-то недоступно, показываем
    только дату регистрации. Заводить ради шапки профиля второй счётчик
    решённых задач значило бы завести второе число, которое разойдётся с
    первым.
    """
    facts = [('на сайте с', formats.date_format(user.date_joined, 'd.m.Y'))]
    try:
        from .stats import full_stats
        data = full_stats(user, 'all') or {}
        head = data.get('profile') or {}
        overview = data.get('overview') or {}
        solved = head.get('solved', overview.get('solved'))
        if solved is not None:
            facts.append(('решено задач', str(solved)))
        streak = head.get('streak_days', head.get('streak'))
        if streak is not None:
            facts.append(('серия дней', str(streak)))
        level = head.get('level')
        if level is not None:
            facts.append(('уровень', str(level)))
    except Exception:      # noqa: BLE001
        # Статистика — украшение шапки. Её отказ не должен ронять профиль,
        # где человек, возможно, пришёл менять пароль.
        pass
    return facts


@login_required(login_url='/login/')
def password_change(request):
    """Старый адрес смены пароля — рабочий, а не редирект.

    ⚠️ ЭКРАН СМЕНЫ ПАРОЛЯ ЖИВЁТ ВО ВКЛАДКЕ «БЕЗОПАСНОСТЬ», но адрес
    `/password/change/` остаётся РАБОЧИМ: на него ведут закладки, чужие
    ссылки и, главное, существующая проверка
    `test_auth_hardening::test_password_change_kills_other_sessions`.
    Ломать её переездом экрана нельзя — она сторожит то, что смена пароля
    закрывает ВСЕ ОСТАЛЬНЫЕ сессии, а это единственная компенсация за отказ
    от старого пароля (ADR 0073).

    ⚠️ Поле `old_password`, если его прислали, форма просто не заметит:
    `SetPasswordForm` о нём не знает.
    """
    if request.method != 'POST':
        return redirect('/profile/?tab=security')
    form = SetPasswordForm(request.user, request.POST)
    if not form.is_valid():
        return render(request, 'platform/profile.html', {
            'profile': UserProfile.objects.get_or_create(user=request.user)[0],
            'form': ProfileForm(instance=request.user.profile),
            'password_form': form,
            'tab': 'security',
            'subtab': 'problems',
            'levels': [(value, label, UserProfile.LEVEL_HINTS.get(value, ''))
                       for value, label in UserProfile.Level.choices],
            'facts': _profile_facts(request.user, request.user.profile),
            'avatar_error': '',
        })
    form.save()
    update_session_auth_hash(request, request.user)
    return redirect('/profile/?tab=security&changed=1')


@login_required(login_url='/login/')
def avatar(request, user_id):
    """Отдаёт аватар. ПЕРВАЯ вьюха проекта, отдающая файл.

    ⚠️ ЧТО ЗДЕСЬ СДЕЛАНО, ЧТОБЫ ЭТО НЕ БЫЛО ДЫРОЙ:

    * путь к файлу берётся ИЗ ПОЛЯ МОДЕЛИ, а не из запроса. Из запроса
      приходит только целое число — номер пользователя;
    * отдаётся ровно один файл на пользователя, и он наш собственный: форма
      пересжала картинку Pillow в JPEG и сама назвала её `avatars/<id>.jpg`;
    * гостю нельзя вовсе (`login_required`): аватар — лицо ребёнка, и
      выкладывать его в открытый доступ мы не будем;
    * `Content-Type` задан жёстко, из файла не угадывается.

    Почему аватар видит любой ВОШЕДШИЙ, а не только владелец: его показывает
    шапка, доска набора, список учеников группы — то есть человек и так
    видит лица тех, с кем занимается. Сужать до владельца значило бы, что
    аватар не видно нигде, кроме собственного профиля.
    """
    profile_obj = get_object_or_404(UserProfile, user_id=user_id)
    if not profile_obj.avatar:
        raise Http404('Аватара нет')
    try:
        handle = profile_obj.avatar.open('rb')
    except (FileNotFoundError, OSError):
        # Файл потерялся (перенос, чистка media) — это не 500.
        raise Http404('Аватара нет')
    response = FileResponse(handle, content_type='image/jpeg')
    # Приватно: общий кэш (nginx, прокси) держать чужое лицо не должен.
    response['Cache-Control'] = 'private, max-age=86400'
    return response


@login_required(login_url='/login/')
def profile(request):
    profile_obj, _ = UserProfile.objects.get_or_create(user=request.user)
    tab = request.GET.get('tab', 'data')
    # ⚠️ ВКЛАДКИ ЧЕТЫРЕ, И «СТАТИСТИКА» СРЕДИ НИХ — ССЫЛКА, А НЕ ВКЛАДКА:
    # готовый экран `/profile/stats/` переезжать не должен, у него свои
    # расчёты. Здесь она есть только для полосы вкладок.
    if tab not in ('data', 'security', 'saved'):
        tab = 'data'
    subtab = request.GET.get('sub', 'problems')
    if subtab not in ('problems', 'graphs'):
        subtab = 'problems'

    form = ProfileForm(instance=profile_obj)
    password_form = SetPasswordForm(request.user)
    avatar_error = ''

    if request.method == 'POST':
        action = request.POST.get('action') or 'data'
        if action == 'data':
            form = ProfileForm(request.POST, instance=profile_obj)
            if form.is_valid():
                form.save()
                return redirect('/profile/?saved=1')
        elif action == 'password':
            # ⚠️ БЕЗ СТАРОГО ПАРОЛЯ — решение владельца 04.09.2026 (ADR 0073).
            # Форма Django, своей проверки пароля у нас нет.
            password_form = SetPasswordForm(request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                # Иначе смена пароля выкинула бы и самого человека.
                update_session_auth_hash(request, request.user)
                return redirect('/profile/?tab=security&changed=1')
            tab = 'security'
        elif action == 'avatar':
            avatar_form = AvatarForm(request.POST, request.FILES)
            if avatar_form.is_valid():
                # Имя файла НАШЕ, а не из запроса: `avatars/<id>.jpg`.
                profile_obj.avatar.save(
                    'avatars/%d.jpg' % request.user.pk,
                    ContentFile(avatar_form.squared_jpeg().read()),
                    save=True)
                return redirect('/profile/?saved=1')
            avatar_error = ' '.join(
                avatar_form.errors.get('avatar', ['Не получилось загрузить.']))
        elif action == 'avatar_remove':
            if profile_obj.avatar:
                profile_obj.avatar.delete(save=True)
            return redirect('/profile/')

    context = {
        'profile': profile_obj,
        'form': form,
        'password_form': password_form,
        'avatar_error': avatar_error,
        'tab': tab,
        'subtab': subtab,
        # Уровень отдаём тройками (значение, название, описание): фильтра
        # «взять по ключу» в проекте нет, а заводить его ради одного экрана
        # значит завести ещё одну общую вещь.
        'levels': [(value, label, UserProfile.LEVEL_HINTS.get(value, ''))
                   for value, label in UserProfile.Level.choices],
        # Олимпиады в раскрытом списке — группами и полными подписями; закрытый
        # список рисует короткие (`OLYMPIAD_HISTORY`). Оба набора — в модели.
        'olympiad_groups': UserProfile.OLYMPIAD_GROUPS,
        'welcome': request.GET.get('welcome') == '1',
        'saved_ok': request.GET.get('saved') == '1',
        'password_changed': request.GET.get('changed') == '1',
        'facts': _profile_facts(request.user, profile_obj),
    }
    if profile_obj.is_tutor:
        from .models import User as UserModel
        context['tutor_groups'] = request.user.teaching_groups.count()
        context['tutor_students'] = (
            UserModel.objects.filter(enrolled_groups__teacher=request.user)
            .distinct().count())

    if tab == 'saved':
        kind = (SavedFolder.Kind.GRAPHS if subtab == 'graphs'
                else SavedFolder.Kind.PROBLEMS)
        folders = list(SavedFolder.objects.filter(owner=request.user,
                                                  kind=kind))
        if subtab == 'graphs':
            saved = list(SavedGraph.objects.filter(owner=request.user,
                                                   is_deleted=False)
                         .select_related('folder'))
        else:
            saved = list(SavedProblem.objects.filter(owner=request.user,
                                                     is_deleted=False)
                         .select_related('folder', 'catalog_problem',
                                         'custom_problem'))
            # ⚠️ РЕШЕНИЕ ВЛАДЕЛЬЦА (сессия 3Б): задачу, которую шлюз качества
            # забраковал ПОСЛЕ сохранения, показываем — но с пометкой.
            #
            # Молча спрятать нельзя: подборка ученика «похудеет» без всякого
            # объяснения, и он решит, что что-то потерял. Молча показать со
            # ссылкой тоже нельзя: тогда шлюз не работает — ссылка ведёт на
            # страницу, которой для него нет.
            #
            # Признак считается ЗДЕСЬ, а не в шаблоне: шаблон не должен
            # ходить в базу и не должен знать правила шлюза.
            for item in saved:
                problem = item.catalog_problem
                item.is_public = bool(
                    problem is not None
                    and problem.status == Problem.Status.PUBLISHED
                    and not problem.needs_quality_review
                )
        # Группируем по папкам; «Без папки» всегда последняя — это не папка,
        # а её отсутствие.
        groups = [{'folder': f,
                   'items': [s for s in saved if s.folder_id == f.pk]}
                  for f in folders]
        groups.append({'folder': None,
                       'items': [s for s in saved if s.folder_id is None]})
        context.update({'folders': folders, 'groups': groups})

    return render(request, 'platform/profile.html', context)


# ---------------------------------------------------------------------------
# JSON-эндпоинты «Сохранённого» (кнопка «Сохранить» работает без перезагрузки)
# ---------------------------------------------------------------------------

def _body(request):
    try:
        return json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return {}


@require_POST
@login_required(login_url='/login/')
def api_save_problem(request):
    """Сохранить/убрать задачу. Переключатель: повторный вызов снимает.

    Удаление мягкое — запись остаётся с `is_deleted=True`. Тогда «сохранил →
    убрал → сохранил снова» не спотыкается об ограничение уникальности.
    """

    data = _body(request)
    catalog_id = data.get('catalog_problem_id')
    custom_id = data.get('custom_problem_id')
    if not catalog_id and not custom_id:
        return JsonResponse({'error': 'Не указана задача'}, status=400)

    lookup = {'owner': request.user}
    if catalog_id:
        # ⚠️ ФИЛЬТР ПО ОПУБЛИКОВАННОСТИ ЗДЕСЬ ОБЯЗАТЕЛЕН. Раньше стояло просто
        # `get_object_or_404(Problem, pk=catalog_id)`, и это была утечка
        # чернового контента: любой вошедший подставлял в этот эндпоинт номер
        # черновика, скрытой или зафлагованной шлюзом задачи, она ложилась ему
        # в «Сохранённое» и оттуда показывалась на `/profile/?tab=saved`
        # вместе с условием. Каталог такие задачи не отдаёт — а этот путь
        # отдавал, в обход шлюза качества.
        lookup['catalog_problem'] = get_object_or_404(
            Problem, pk=catalog_id, status=Problem.Status.PUBLISHED,
            needs_quality_review=False)
    else:
        lookup['custom_problem'] = get_object_or_404(
            CustomProblem, pk=custom_id, owner=request.user)

    saved = SavedProblem.objects.filter(**lookup).first()
    if saved is None:
        SavedProblem.objects.create(**lookup)
        return JsonResponse({'saved': True})
    saved.is_deleted = not saved.is_deleted
    saved.save(update_fields=['is_deleted'])
    return JsonResponse({'saved': not saved.is_deleted})


@require_POST
@login_required(login_url='/login/')
def api_folder_create(request):
    data = _body(request)
    name = (data.get('name') or '').strip()
    kind = data.get('kind') or SavedFolder.Kind.PROBLEMS
    if not name:
        return JsonResponse({'error': 'Пустое название'}, status=400)
    folder, created = SavedFolder.objects.get_or_create(
        owner=request.user, kind=kind, name=name)
    return JsonResponse({'id': folder.pk, 'name': folder.name,
                         'created': created})


@require_POST
@login_required(login_url='/login/')
def api_folder_rename(request):
    data = _body(request)
    folder = get_object_or_404(SavedFolder, pk=data.get('folder_id'),
                               owner=request.user)
    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'Пустое название'}, status=400)
    folder.name = name
    folder.save(update_fields=['name'])
    return JsonResponse({'id': folder.pk, 'name': folder.name})


@require_POST
@login_required(login_url='/login/')
def api_saved_move(request):
    """Переместить сохранённое в папку (или «без папки»)."""
    data = _body(request)
    folder_id = data.get('folder_id') or None
    folder = None
    if folder_id:
        folder = get_object_or_404(SavedFolder, pk=folder_id,
                                   owner=request.user)

    if data.get('kind') == 'graph':
        obj = get_object_or_404(SavedGraph, pk=data.get('id'),
                                owner=request.user)
    else:
        obj = get_object_or_404(SavedProblem, pk=data.get('id'),
                                owner=request.user)
    obj.folder = folder
    obj.save(update_fields=['folder'])
    return JsonResponse({'ok': True,
                         'folder': folder.name if folder else 'Без папки'})


@require_POST
@login_required(login_url='/login/')
def api_saved_delete(request):
    """Мягкое удаление из сохранённого."""
    data = _body(request)
    model = SavedGraph if data.get('kind') == 'graph' else SavedProblem
    obj = get_object_or_404(model, pk=data.get('id'), owner=request.user)
    obj.is_deleted = True
    obj.save(update_fields=['is_deleted'])
    return JsonResponse({'ok': True})


# ---------------------------------------------------------------------------
# Фаза 19.2 — приём графика от калькулятора
# ---------------------------------------------------------------------------

@require_POST
@login_required(login_url='/login/')
def api_graph_save(request):
    """Сохранить график: {name, scene, preview}.

    ⚠️ Серверная половина функции «создать новый график». Формат `scene`
    здесь НЕ разбирается и НЕ проверяется по существу: calc2 в этой сессии
    не трогали, и что именно он положит в сцену — вопрос отдельной задачи.
    Эндпоинт готов принять её, как только калькулятор научится отдавать.
    """
    data = _body(request)
    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'Нужно название графика'}, status=400)

    scene = data.get('scene')
    if not isinstance(scene, dict):
        return JsonResponse({'error': 'Сцена должна быть объектом'},
                            status=400)

    graph = SavedGraph.objects.create(
        owner=request.user, name=name, scene=scene,
        preview=(data.get('preview') or '')[:500])
    return JsonResponse({'id': graph.pk, 'name': graph.name})


# ═══════════════════════════════════════════════════════════════════════
# Обратная связь беты (04.09.2026, ADR 0076)
# ═══════════════════════════════════════════════════════════════════════

FEEDBACK_SCOPE = 'feedback'
FEEDBACK_MAX_SCREENSHOT = 5_000_000     # 5 МБ
# Длинная сторона снимка: выше SIDE_MAX уменьшаем, выше SIDE_HARD_MAX не
# открываем вовсе — такой файл разворачивается в памяти в сотни мегабайт.
FEEDBACK_SHOT_SIDE_MAX = 4000
FEEDBACK_SHOT_SIDE_HARD_MAX = 12000
FEEDBACK_SHOT_WIDTH = 1600


@require_POST
def api_feedback(request):
    """Принять «Проблема или предложение».

    ⚠️ ГОСТЮ МОЖНО, И ЭТО НЕ НЕДОСМОТР. Половина беты — люди, которые ещё
    не завели аккаунт; именно у них ломается вход. Требовать логин, чтобы
    пожаловаться на форму входа, — способ не узнать о поломке.

    ⚠️ CSRF ОБЯЗАТЕЛЕН (декоратора `csrf_exempt` здесь нет и не будет):
    иначе чужая страница смогла бы слать нам записи от имени наших
    посетителей.

    ⚠️ СНИМОК ЭКРАНА — ПРИЯТНОЕ ДОПОЛНЕНИЕ, А НЕ УСЛОВИЕ. Битый, слишком
    большой или отсутствующий снимок НЕ отменяет запись: текст жалобы
    ценнее картинки, и терять его из-за картинки нельзя.
    """
    from problems import ratelimit
    from problems import pulse
    from problems.feedback_options import OTHER_CHOICE, options_for, page_key_for
    from problems.models_platform import Feedback

    wait = ratelimit.check(FEEDBACK_SCOPE, request, None)
    if wait:
        return JsonResponse(
            {'ok': False, 'error': 'Слишком часто. Попробуйте позже.'},
            status=429)

    kind = (request.POST.get('kind') or '').strip()
    if kind not in dict(Feedback.Kind.choices):
        return JsonResponse({'ok': False, 'error': 'Выберите, что это.'},
                            status=400)

    # ⚠️ ЭКРАН ОПРЕДЕЛЯЕТ СЕРВЕР ПО АДРЕСУ, А НЕ КЛИЕНТ СВОИМ ПОЛЕМ: иначе
    # в `page_key` приехало бы что угодно и группировка жалоб развалилась.
    url = (request.POST.get('url') or '')[:500]
    page_key = page_key_for(url if url.startswith('/') else
                            _path_of(url))

    allowed = set(options_for(page_key)) | {OTHER_CHOICE}
    chosen = [c for c in request.POST.getlist('choices') if c in allowed]
    other_text = (request.POST.get('other_text') or '').strip()[:4000]
    comment = (request.POST.get('comment') or '').strip()[:4000]

    # Правило окна (решение владельца 17.09.2026): хотя бы одна галочка, а
    # у «Другое, своими словами» ещё и непустой текст. Та же проверка — в окне.
    if kind == Feedback.Kind.PROBLEM and not chosen:
        return JsonResponse({'ok': False, 'error': 'Отметьте, что случилось.'},
                            status=400)
    if kind == Feedback.Kind.PROBLEM and OTHER_CHOICE in chosen and not other_text:
        return JsonResponse({'ok': False, 'error': 'Опишите своими словами.'},
                            status=400)
    if kind == Feedback.Kind.IDEA and not other_text:
        return JsonResponse({'ok': False, 'error': 'Напишите предложение.'},
                            status=400)
    if kind == Feedback.Kind.PULSE:
        verdict = pulse.validate(request.POST)
        if isinstance(verdict, str):
            return JsonResponse({'ok': False, 'error': verdict}, status=400)
        (chosen, comment), other_text = verdict, ''

    entry = Feedback(
        user=request.user if request.user.is_authenticated else None,
        kind=kind, page_key=page_key, url=url,
        choices=chosen, other_text=other_text, comment=comment,
        viewport=(request.POST.get('viewport') or '')[:32],
        theme=(request.POST.get('theme') or '')[:16],
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:300],
        # Почему нет снимка — со слов браузера; только режем по длине поля.
        screenshot_note=(request.POST.get('screenshot_note') or '')[:16],
    )

    # Сервер не принял снимок — пишет почему сам (big | tall | bad). Иначе в
    # поле оставалось клиентское «ok», и пустой снимок в админке врал.
    shot = request.FILES.get('screenshot')
    if shot is not None:
        if shot.size > FEEDBACK_MAX_SCREENSHOT:
            entry.screenshot_note = 'big'
        else:
            blob, note = _feedback_screenshot(shot)
            if blob is None:
                entry.screenshot_note = note
            else:
                entry.screenshot.save('shot.jpg', ContentFile(blob), save=False)

    entry.save()
    ratelimit.note_failure(FEEDBACK_SCOPE + ':ip',
                           ratelimit.client_ip(request), multiplier=2)
    return JsonResponse({'ok': True, 'id': entry.pk})


@require_POST
def api_search_rating(request):
    """Оценка выдачи поиска: «Нашли, что искали?» (18.09.2026, ADR 0117).

    Поля: `log` (номер строки журнала), `rating` (yes | no), `text` (до 300).
    Своя строка — по куке посетителя или вошедшему; чужая и несуществующая
    отвечают одинаково 404. CSRF обязателен, как у `api_feedback`.
    """
    from catalog import search_log
    from problems.models_platform import SearchLog

    rating = request.POST.get('rating') or ''
    text = (request.POST.get('text') or '').strip()
    if rating not in SearchLog.Rating.values:
        return JsonResponse({'ok': False, 'error': 'rating'}, status=400)
    if len(text) > search_log.RATING_TEXT_MAX:
        return JsonResponse({'ok': False, 'error': 'text'}, status=400)
    try:
        log_id = int(request.POST.get('log') or '')
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'log'}, status=400)
    if not search_log.rate(request, log_id, rating, text):
        return JsonResponse({'ok': False}, status=404)
    return JsonResponse({'ok': True})


PROBLEM_REPORT_SCOPE = 'problem_report'
PROBLEM_REPORT_TEXT_MAX = 2000
_INT_MAX = 2_147_483_647                 # потолок PositiveIntegerField в PostgreSQL


def _positive_int(value):
    """Номер из формы: None — не прислан, False — прислан не номером."""
    if value in (None, ''):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return False
    return number if 0 < number <= _INT_MAX else False


@require_POST
def api_problem_report(request):
    """Принять «Плохая задача?» из каталога или из Wecon Rush.

    ⚠️ ПУБЛИЧНЫЙ ЭНДПОИНТ, И ЭТО ОСОЗНАННО: битую задачу видит любой школьник,
    в том числе без аккаунта (решение владельца 15.09.2026). Защита — CSRF
    (декоратора `csrf_exempt` здесь нет) и тот же лимит частоты, что у
    обратной связи, со своим счётчиком.

    ⚠️ АВТОР — ТОЛЬКО `request.user`. Поля «кто» в запросе нет и быть не может.

    ⚠️ ЗАДАЧУ ИГРОВОГО ВОПРОСА НАХОДИТ СЕРВЕР И НАРУЖУ ЕЁ НЕ ОТДАЁТ. До ответа
    клиент игры `problem_id` не знает намеренно (анти-чит: по нему в каталоге
    открывались ответ и решение), поэтому в ответе только номер жалобы.
    """
    from django.apps import apps
    from problems import ratelimit
    from problems.models import Problem
    from problems.models_platform import ProblemReport

    wait = ratelimit.check(PROBLEM_REPORT_SCOPE, request, None)
    if wait:
        return JsonResponse(
            {'ok': False, 'error': 'Слишком часто. Попробуйте позже.'}, status=429)

    source = (request.POST.get('source') or '').strip()
    if source not in dict(ProblemReport.Source.choices):
        return JsonResponse({'ok': False, 'error': 'Непонятно, откуда жалоба.'},
                            status=400)
    kind = (request.POST.get('kind') or '').strip()
    if kind not in dict(ProblemReport.Kind.choices):
        return JsonResponse({'ok': False, 'error': 'Выберите, что не так.'}, status=400)
    text = (request.POST.get('text') or '').strip()
    if len(text) > PROBLEM_REPORT_TEXT_MAX:
        return JsonResponse({'ok': False, 'error': 'Слишком длинно: до 2 000 знаков.'},
                            status=400)
    if kind == ProblemReport.Kind.OTHER and not text:
        return JsonResponse({'ok': False, 'error': 'Напишите, что не так'}, status=400)

    problem_id = _positive_int(request.POST.get('problem_id'))
    question_id = _positive_int(request.POST.get('game_question_id'))
    if problem_id is False or question_id is False:
        return JsonResponse({'ok': False, 'error': 'Номер задачи — целое число.'},
                            status=400)
    if problem_id is None and question_id is None:
        return JsonResponse({'ok': False, 'error': 'Непонятно, о какой задаче речь.'},
                            status=400)

    problem = None
    if question_id is not None:
        # Модель игры — через реестр приложений, а не импортом: у `problems`
        # нет зависимости от `game` в коде, связь живёт только в этом запросе.
        # Номер задачи, присланный рядом с вопросом, не нужен: сервер знает её сам.
        GameQuestion = apps.get_model('game', 'GameQuestion')
        row = GameQuestion.objects.filter(pk=question_id).values('problem_id').first()
        if row is None:
            return JsonResponse({'ok': False, 'error': 'Вопрос не найден.'}, status=400)
        if row['problem_id']:
            problem = Problem.objects.filter(pk=row['problem_id']).first()
    else:
        problem = Problem.objects.filter(pk=problem_id).first()
        if problem is None:
            return JsonResponse({'ok': False, 'error': 'Задача не найдена.'}, status=400)

    report = ProblemReport.objects.create(
        user=request.user if request.user.is_authenticated else None,
        problem=problem, game_question_id=question_id,
        source=source, kind=kind, text=text,
        url=(request.POST.get('url') or '')[:500],
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:300],
    )
    ratelimit.note_failure(PROBLEM_REPORT_SCOPE + ':ip',
                           ratelimit.client_ip(request), multiplier=2)
    return JsonResponse({'ok': True, 'id': report.pk})


# ═══════════════════════════════════════════════════════════════════════
# Аналитика беты: сырые события (решение владельца 15.09.2026)
# ═══════════════════════════════════════════════════════════════════════

TRACK_MAX_EVENTS = 50          # событий в одном запросе
TRACK_MAX_PROPS = 2000         # символов props после сериализации
TRACK_LIMIT = 600              # событий с посетителя за окно
TRACK_WINDOW = 600             # секунд в окне
TRACK_COOKIE = 'weco_vid'
_VISITOR_RE = re.compile(r'[0-9A-Za-z-]{8,40}')


def _own_origin(request):
    """Origin (или Referer, если Origin нет) — наш хост из ALLOWED_HOSTS.

    Та же проверка хоста, что у самого Django (`validate_host`), с тем же
    запасным списком для разработки при пустом ALLOWED_HOSTS.
    """
    from urllib.parse import urlparse

    from django.conf import settings
    from django.http.request import split_domain_port, validate_host

    source = request.META.get('HTTP_ORIGIN') or request.META.get('HTTP_REFERER') or ''
    try:
        netloc = urlparse(source).netloc
    except ValueError:
        return False
    domain, _port = split_domain_port(netloc)
    allowed = settings.ALLOWED_HOSTS
    if settings.DEBUG and not allowed:
        allowed = ['.localhost', '127.0.0.1', '[::1]']
    return bool(domain) and validate_host(domain, allowed)


def _track_props(props):
    """props не длиннее TRACK_MAX_PROPS: строки режутся, лишние ключи отбрасываются."""
    out = {}
    if not isinstance(props, dict):
        return out
    for key, value in props.items():
        if value is not None and not isinstance(value, (str, int, float, bool)):
            value = json.dumps(value, ensure_ascii=False)
        if isinstance(value, str):
            value = value[:300]
        key = str(key)[:48]
        out[key] = value
        if len(json.dumps(out, ensure_ascii=False)) > TRACK_MAX_PROPS:
            del out[key]
            break
    return out


def _track_duration(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = int(value)
    return value if 0 <= value <= _INT_MAX else None


@csrf_exempt
@require_POST
def api_track(request):
    """Принять пачку событий беты от `static/track.js`. Гостю можно.

    ⚠️ CSRF_EXEMPT — ОСОЗНАННО. `navigator.sendBeacon` не ставит заголовков,
    а без него событие ухода со страницы на закрытии вкладки не доходит вовсе.
    Вместо CSRF-токена — две проверки: `Origin` (или `Referer`) обязан быть
    нашим хостом из ALLOWED_HOSTS — чужая страница из браузера такой не
    пришлёт, — и счётчик на посетителя (не больше TRACK_LIMIT событий за
    TRACK_WINDOW секунд). Худшее, что остаётся, — мусор в своей же таблице
    аналитики: данных пользователя вьюха не меняет и ничего не отдаёт
    (docs/SECURITY.md).
    ⚠️ `problems/ratelimit.py` не подходит: там лестница штрафов за промахи на
    сутки, а здесь нужен простой счётчик окна.
    """
    from django.core.cache import cache

    from problems.feedback_options import page_key_for
    from problems.models_platform import Event

    if not _own_origin(request):
        return JsonResponse({'ok': False, 'error': 'origin'}, status=403)
    visitor = request.COOKIES.get(TRACK_COOKIE, '')
    if not _VISITOR_RE.fullmatch(visitor):
        return JsonResponse({'ok': False, 'error': 'visitor'}, status=400)
    data = _body(request)
    events = data.get('events') if isinstance(data, dict) else None
    if not isinstance(events, list) or not events:
        return JsonResponse({'ok': False, 'error': 'events'}, status=400)
    if len(events) > TRACK_MAX_EVENTS:
        return JsonResponse({'ok': False, 'error': 'too_many'}, status=400)

    key = 'track:%s:%d' % (visitor, int(time.time()) // TRACK_WINDOW)
    cache.add(key, 0, TRACK_WINDOW)
    try:
        count = cache.incr(key, len(events))
    except ValueError:                  # ключ истёк между add и incr
        count = len(events)
        cache.set(key, count, TRACK_WINDOW)
    if count > TRACK_LIMIT:
        return JsonResponse({'ok': False, 'error': 'rate'}, status=429)

    user = request.user if request.user.is_authenticated else None
    session_key = (request.session.session_key or '')[:40]
    agent = request.META.get('HTTP_USER_AGENT', '')[:200]
    rows = []
    for raw in events:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get('name') or '').strip()[:48]
        if not name:
            continue
        # Путь без строки запроса: текст поиска в аналитику не пишем.
        path = _path_of(str(raw.get('path') or '/'))[:500]
        rows.append(Event(
            user=user, visitor=visitor, session_key=session_key,
            page_key=page_key_for(path), path=path, name=name,
            props=_track_props(raw.get('props')),
            duration_ms=_track_duration(raw.get('duration_ms')),
            viewport=str(raw.get('viewport') or '')[:16], user_agent=agent))
    Event.objects.bulk_create(rows)
    return JsonResponse({'ok': True, 'saved': len(rows)})


def _path_of(url):
    """Путь из абсолютного адреса. Чужой домен нас не интересует."""
    from urllib.parse import urlparse
    try:
        return urlparse(url).path or '/'
    except ValueError:
        return '/'


def _feedback_screenshot(uploaded):
    """Пересжать снимок в JPEG → (байты | None, note).

    note — 'ok', 'tall' (длинная сторона больше FEEDBACK_SHOT_SIDE_HARD_MAX)
    или 'bad' (не открывается как картинка). Высокий снимок УМЕНЬШАЕТСЯ, а
    не выбрасывается: раньше всё выше 4 000 px молча пропадало, и до админки
    доживали только короткие страницы.

    Та же осторожность, что у аватара: сначала целостность, потом размеры в
    пикселях, и только потом обработка — иначе мелкий файл разворачивается в
    памяти в сотню мегабайт.
    """
    from PIL import Image, UnidentifiedImageError

    try:
        probe = Image.open(uploaded)
        probe.verify()
        uploaded.seek(0)
        image = Image.open(uploaded)
        if max(image.size) > FEEDBACK_SHOT_SIDE_HARD_MAX:
            return None, 'tall'
        uploaded.seek(0)
        image = Image.open(uploaded).convert('RGB')
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None, 'bad'

    if max(image.size) > FEEDBACK_SHOT_SIDE_MAX:
        image.thumbnail((FEEDBACK_SHOT_SIDE_MAX, FEEDBACK_SHOT_SIDE_MAX), Image.LANCZOS)
    if image.width > FEEDBACK_SHOT_WIDTH:
        height = max(1, round(image.height * FEEDBACK_SHOT_WIDTH / image.width))
        image = image.resize((FEEDBACK_SHOT_WIDTH, height), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=80, optimize=True)
    return buffer.getvalue(), 'ok'
