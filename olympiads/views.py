"""Экраны раздела «Олимпиады».

Раздел публичный и вход не требует — как каталог. Ничего не пишет: все
четыре функции только читают.
"""
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import navigator, services, training_engine
from .models import (Olympiad, OlympiadFollow,
                     RegionalCoordinator, current_academic_year)


def soon_page(request):
    u"""Заглушка раздела или None, если пускать можно.

    ⚠️ ПРОВЕРКА В КАЖДОЙ ВЬЮХЕ, А НЕ В MIDDLEWARE. Middleware ловил бы
    адреса строкой пути, а у тренировки их семь, и один забытый пускал бы
    внутрь закрытого раздела. Здесь забыть нельзя: без вызова вьюха просто
    не соберётся по образцу соседних.

    Ответ — 200, а не 403 и не 404: это не ошибка, а состояние раздела.
    """
    if settings.OLYMPIADS_PUBLIC:
        return None
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated and user.is_staff:
        return None
    return render(request, 'olympiads/soon.html')


def _has_placeholder(objects):
    """Есть ли на странице хоть один объект с выдуманными данными.

    От этого зависит плашка сверху. Плашка обязательна: без неё кто-нибудь
    примет заглушку за факт и пропустит регистрацию.
    """
    return any(getattr(obj, 'is_placeholder', False) for obj in objects)


def olympiad_list(request):
    """Главная раздела по макету 30.10 (доски Home, HomePhone; ночь, Э3).

    Фильтры — GET-параметры (`kind`, `grade`, `tasks`, `mine`): работают без
    JS и дают ссылку, которой можно поделиться. Числа — из навигатора.
    """
    stub = soon_page(request)
    if stub is not None:
        return stub
    user = request.user if request.user.is_authenticated else None
    rows = navigator.home_rows(user)
    kind = request.GET.get('kind', '')
    grade = request.GET.get('grade', '')
    tasks = request.GET.get('tasks') == '1'
    mine = request.GET.get('mine') == '1' and user is not None
    shown = navigator.filter_rows(rows, kind, grade, tasks, mine)
    for row in rows:
        row['level_chip'] = navigator.level_chip(row)
        row['logo_text'] = navigator.logo_text(row['olympiad'])
    feed = navigator.feed_rows(navigator.upcoming())
    params = {'kind': kind, 'grade': grade, 'tasks': '1' if tasks else '',
              'mine': '1' if mine else ''}

    def link(**change):
        """Адрес чипа: меняет один параметр, остальные оставляет."""
        merged = dict(params, **change)
        query = '&'.join('{}={}'.format(k, v) for k, v in merged.items() if v)
        return '?' + query if query else '?'

    return render(request, 'olympiads/list.html', {
        'main_rows': [r for r in shown if r['section'] == 'main'],
        'fin_rows': [r for r in shown if r['section'] == 'fin'],
        'total_rows': len(shown),
        'feed': feed[:navigator.FEED_VISIBLE],
        'feed_more': feed[navigator.FEED_VISIBLE:],
        'continue': navigator.home_continue(user),
        'followed': [r['olympiad'] for r in rows if r['followed']],
        'kind_chips': [{'label': 'Все', 'on': not kind, 'href': link(kind='')}]
        + [{'label': label, 'on': kind == code,
            'href': link(kind='' if kind == code else code)}
           for code, label, _value in navigator.KIND_FILTERS],
        'grade_chips': [{'label': label, 'on': grade == code,
                         'href': link(grade='' if grade == code else code)}
                        for code, label in navigator.GRADE_FILTERS],
        'tasks_chip': {'on': tasks, 'href': link(tasks='' if tasks else '1')},
        'mine_chip': {'on': mine, 'href': link(mine='' if mine else '1')},
        'filtered': any(params.values()),
        'reset_href': '?',
    })


def olympiad_detail(request, slug):
    """Страница одной олимпиады."""
    stub = soon_page(request)
    if stub is not None:
        return stub
    # ⚠️ Скрытая олимпиада и заглушка — 404: в раздел они не попадают
    # (ночь 30.10, Э2). Числа страницы — только из навигатора.
    olympiad = get_object_or_404(
        navigator.visible_olympiads().prefetch_related(
            'levels', 'events', 'events__stage', 'events__source', 'stages'),
        slug=slug,
    )
    user = request.user if request.user.is_authenticated else None
    page = navigator.olympiad_page(
        olympiad, user, request.session.session_key or '')
    try:
        grade = int(request.GET.get('grade') or 0)
    except ValueError:
        grade = None
    view = navigator.page_view(page, request.GET.get('stage', ''),
                               request.GET.get('open', ''),
                               request.GET.get('all') == '1', grade)
    benefits = list(
        olympiad.benefits.select_related('program', 'source')
        .order_by('-admission_year', 'program__order')
    )
    score_rows, score_years = services.pass_score_rows(olympiad)
    show_regions = olympiad.kind == Olympiad.Kind.VSOSH
    sources = {}
    for holder in ([olympiad] + list(olympiad.stages.all())
                   + list(olympiad.events.all()) + benefits):
        if holder.source_id and holder.source:
            sources[holder.source_id] = holder.source
    return render(request, 'olympiads/detail.html', {
        'olympiad': olympiad,
        'page': page,
        'facts': page['facts'],
        'view': view,
        'stages_summary': navigator.stages_summary(olympiad, page),
        'continue': navigator.continue_cell(page),
        'tours_done': navigator.tours_done(page),
        'admission': navigator.admission_summary(
            olympiad, benefits, navigator.last_approved_level(olympiad)),
        'score_rows': score_rows,
        'score_years': score_years,
        'regions': list(RegionalCoordinator.objects.all()) if show_regions else [],
        'sources': sorted(sources.values(), key=lambda s: (s.publisher, s.title)),
        'level': navigator.last_approved_level(olympiad),
        'logo_text': navigator.logo_text(olympiad),
        'academic_year': current_academic_year(),
        'followed': bool(user) and OlympiadFollow.objects.filter(
            user=user, olympiad=olympiad).exists(),
    })


@require_POST
def follow(request, slug):
    """«В мои олимпиады» / «Убрать» — POST с CSRF, только для вошедших.

    ⚠️ Гость в базу не пишет НИЧЕГО: его отправляем на вход с возвратом на
    страницу олимпиады. Звёздочка гостя — ссылка на вход, а не форма; сюда
    гость попадает, только если прислал POST руками.
    """
    stub = soon_page(request)
    if stub is not None:
        return stub
    olympiad = get_object_or_404(navigator.visible_olympiads(), slug=slug)
    back = request.POST.get('next') or reverse('olympiads:detail',
                                               args=[olympiad.slug])
    if not url_has_allowed_host_and_scheme(back, {request.get_host()},
                                           request.is_secure()):
        back = reverse('olympiads:detail', args=[olympiad.slug])
    if not request.user.is_authenticated:
        return redirect_to_login(back)
    if request.POST.get('action') == 'remove':
        OlympiadFollow.objects.filter(user=request.user,
                                      olympiad=olympiad).delete()
    else:
        OlympiadFollow.objects.get_or_create(user=request.user,
                                             olympiad=olympiad)
    followed = OlympiadFollow.objects.filter(user=request.user,
                                             olympiad=olympiad).exists()
    if request.headers.get('x-requested-with') == 'fetch':
        return JsonResponse({'followed': followed})
    return redirect(back)


def calendar(request):
    """Собственный календарь раздела — учебный год с сентября по август.

    Отдельный от `calendar_stub` намеренно, решением владельца: тот
    календарь про занятия репетитора, этот про туры. Заготовка связки —
    `services.events_for_external_calendar()`.
    """
    stub = soon_page(request)
    if stub is not None:
        return stub
    year = current_academic_year()
    chosen = (request.GET.get('olympiad') or '').strip()
    olympiads = list(
        Olympiad.objects.filter(is_published=True).order_by('name_short')
    )
    known = {o.slug for o in olympiads}
    if chosen not in known:
        chosen = ''
    months, undated, outside = services.calendar_months(year, chosen or None)
    return render(request, 'olympiads/calendar.html', {
        'academic_year': year,
        'months': months,
        'undated': undated,
        'outside': outside,
        'olympiads': olympiads,
        'chosen': chosen,
        'has_placeholder': any(o.is_placeholder for o in olympiads),
    })


def compare(request):
    """Сравнение до трёх олимпиад: `?slugs=vseros,mosh,vp`.

    Слагов пришло больше трёх — берём первые три и говорим об этом, а не
    падаем: ссылку могли прислать из чата, и ошибка вместо экрана здесь
    хуже, чем усечение.
    """
    stub = soon_page(request)
    if stub is not None:
        return stub
    raw = [s for s in (request.GET.get('slugs') or '').split(',') if s.strip()]
    wanted = [s.strip() for s in raw]
    trimmed = len(wanted) > services.COMPARE_LIMIT
    wanted = wanted[:services.COMPARE_LIMIT]

    found = {
        o.slug: o for o in
        services.published_olympiads().filter(slug__in=wanted)
    }
    # Порядок задаёт адрес, а не база: пользователь выбирал именно так.
    olympiads = [found[slug] for slug in wanted if slug in found]
    return render(request, 'olympiads/compare.html', {
        'olympiads': olympiads,
        'rows': services.compare_rows(olympiads) if olympiads else [],
        'trimmed': trimmed,
        'limit': services.COMPARE_LIMIT,
        'has_placeholder': _has_placeholder(olympiads),
    })
