"""Экраны раздела «Олимпиады».

Раздел публичный и вход не требует — как каталог. Ничего не пишет: все
четыре функции только читают.
"""
from django.db.models import F
from django.shortcuts import get_object_or_404, render

from . import services, training_engine
from .models import (TAG_LABELS, Olympiad, RegionalCoordinator,
                     current_academic_year)


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
    variants = list(
        olympiad.variants.select_related('stage')
        .order_by('-year', 'stage__order', 'grade')
    )
    # Кнопки «Решать» живут только у комплектов, задачи которых есть в банке.
    # Спрашиваем ОДНИМ запросом: заводить «задание» на каждый комплект ради
    # проверки кнопки — значит создавать работы, которые никто не откроет.
    linked = training_engine.linked_event_ids(variants)
    for variant in variants:
        variant.is_trainable = (variant.ref_event_id or '').strip() in linked
    # Блок региональных организаторов есть только у ВсОШ: школьный и
    # муниципальный этапы назначает субъект, и только у неё это так.
    show_regions = olympiad.kind == Olympiad.Kind.VSOSH
    regions = list(RegionalCoordinator.objects.all()) if show_regions else []
    score_rows, score_years = services.pass_score_rows(olympiad)
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
        'score_rows': score_rows,
        'score_years': score_years,
        'variants': variants,
        'variant_stages': stages,
        'variant_grades': sorted({v.grade for v in variants if v.grade}),
        'variant_years': sorted({v.year for v in variants}, reverse=True),
        'regions': regions,
        'show_regions': show_regions,
        # Год берётся из данных, а не зашивается в шаблон: правила приёма
        # пересматриваются каждый год, и подпись обязана ехать за ними.
        'benefit_year': benefits[0].admission_year if benefits else None,
        'has_placeholder': _has_placeholder([olympiad]),
    })


def calendar(request):
    """Собственный календарь раздела — учебный год с сентября по август.

    Отдельный от `calendar_stub` намеренно, решением владельца: тот
    календарь про занятия репетитора, этот про туры. Заготовка связки —
    `services.events_for_external_calendar()`.
    """
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
