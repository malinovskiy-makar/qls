"""Экраны раздела «Олимпиады».

Раздел публичный и вход не требует — как каталог. Ничего не пишет: все
четыре функции только читают.
"""
from django.db.models import F
from django.shortcuts import get_object_or_404, render

from . import services
from .models import TAG_LABELS, Olympiad, current_academic_year


def _has_placeholder(objects):
    """Есть ли на странице хоть один объект с выдуманными данными.

    От этого зависит плашка сверху. Плашка обязательна: без неё кто-нибудь
    примет заглушку за факт и пропустит регистрацию.
    """
    return any(getattr(obj, 'is_placeholder', False) for obj in objects)


def olympiad_list(request):
    """Главный экран раздела: лента ближайших дат, фильтры, карточки."""
    olympiads = list(
        Olympiad.objects.filter(is_published=True)
        .prefetch_related('levels', 'events', 'variants')
    )
    main = sorted(
        [o for o in olympiads if o.display_group == Olympiad.DisplayGroup.MAIN],
        key=lambda o: o.sort_key(),
    )
    related = sorted(
        [o for o in olympiads
         if o.display_group == Olympiad.DisplayGroup.RELATED],
        key=lambda o: o.sort_key(),
    )
    feed_events, feed_has_confirmed = services.upcoming_events(limit=5)
    return render(request, 'olympiads/list.html', {
        'main': main,
        'related': related,
        'feed_events': feed_events,
        'feed_has_confirmed': feed_has_confirmed,
        'tag_labels': TAG_LABELS,
        'has_placeholder': _has_placeholder(olympiads),
    })


def olympiad_detail(request, slug):
    """Страница одной олимпиады."""
    olympiad = get_object_or_404(
        Olympiad.objects.prefetch_related('levels', 'events', 'stages'),
        slug=slug,
    )
    stages = list(olympiad.stages.all())
    benefits = list(
        olympiad.benefits.select_related('program')
        .order_by('-admission_year', 'program__order')
    )
    year = current_academic_year()
    events = list(
        olympiad.events.filter(academic_year=year)
        .select_related('stage', 'source')
        .order_by(F('stage__order').asc(nulls_first=True), 'date_start', 'kind')
    )
    return render(request, 'olympiads/detail.html', {
        'olympiad': olympiad,
        'stages': stages,
        'events': events,
        'academic_year': year,
        'stats': services.problem_stats(olympiad),
        'benefits': benefits,
        # Год берётся из данных, а не зашивается в шаблон: правила приёма
        # пересматриваются каждый год, и подпись обязана ехать за ними.
        'benefit_year': benefits[0].admission_year if benefits else None,
        'has_placeholder': _has_placeholder([olympiad]),
    })


def calendar(request):
    """Собственный календарь раздела — учебный год с сентября по август."""
    return render(request, 'olympiads/calendar.html', {
        'academic_year': current_academic_year(),
        'has_placeholder': Olympiad.objects.filter(
            is_placeholder=True, is_published=True).exists(),
    })


def compare(request):
    """Сравнение до трёх олимпиад: `?slugs=vseros,mosh,vp`."""
    return render(request, 'olympiads/compare.html', {
        'has_placeholder': False,
    })
