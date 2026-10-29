# -*- coding: utf-8 -*-
"""Служебный просмотр задачи для проверки отображения — ЛЮБОЙ задачи, и скрытой.

Страница задачи (`catalog.views.problem_detail`) отдаёт скрытую задачу как 404
даже админу, а в охват контура входят и скрытые (`next_api_run_ids`). Здесь —
тот же контекст (`_problem_context`) и тот же шаблон `catalog/stol.html`, без
шлюза видимости и без записей (событие «открыта», прогресс). Решение на
настоящей странице приходит по клику (`api_solution`, только вошедшему); здесь
оно дорисовано тем же партиалом `_help_solution.html` в колонку шириной панели
помощи (392 px), чтобы проверить и его.

⚠️ Включается ТОЛЬКО настройкой `QUALITY_CONTOUR_PREVIEW = True` (локальный
`config/settings_quality_ro.py`, база `mode=ro`); без неё — 404. Маршрут
подключается собственным `ROOT_URLCONF` тех же настроек (`urls.py` рядом), в
`config/urls.py` его нет.
"""
from __future__ import annotations

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string

SOLUTION_SLOT = '<section id="q-solution" class="q-solution" style="max-width:392px;margin:24px auto">%s</section>'


def enabled():
    return getattr(settings, 'QUALITY_CONTOUR_PREVIEW', False) is True


def preview(request, pk):
    if not enabled():
        raise Http404
    from catalog import seo
    from catalog.views import _problem_context, _solution_block
    from problems.models import Problem

    problem = get_object_or_404(Problem, pk=pk)
    context = _problem_context(request, problem)
    context['view'] = 'stol'
    context.update(seo.problem_meta(problem, context['heading']))
    response = render(request, 'catalog/stol.html', context)
    sol = _solution_block(problem, list(problem.parts.all()))
    if sol['has_any']:
        html = render_to_string('catalog/stol/_help_solution.html', {'sol': sol, 'problem': problem},
                                request=request)
        body = response.content.decode('utf-8')
        at = body.rfind('</main>')
        if at > 0:
            body = body[:at] + SOLUTION_SLOT % html + body[at:]
            return HttpResponse(body, content_type=response['Content-Type'], status=response.status_code)
    return response
