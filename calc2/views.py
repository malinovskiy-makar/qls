"""
Views для собственного графического движка (Этап Е, приложение calc2).

Это НОВЫЙ калькулятор на открытых библиотеках (D3.js + Math.js), который
со временем заменит калькулятор на Desmos (приложение graphs, страница /desmos/).
Старый калькулятор не трогаем — он продолжает работать как есть.

Пока в базе ничего не сохраняем (моделей у calc2 нет): это чистый
интерактивный инструмент. Сохранение графиков — задача будущих сессий.
"""

import re

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from catalog.latex_export import compile_pdf, xelatex_available


@method_decorator(login_required, name='dispatch')
class Calc2View(TemplateView):
    """Рендерит страницу нового графического калькулятора.

    Требует входа в систему (@login_required) — как и калькулятор Desmos.
    """
    template_name = 'calc2/calc2.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Честно говорим интерфейсу, умеет ли ЭТОТ сервер собирать PDF.
        # На бесплатном тарифе Render xelatex не установлен (XELATEX_PATH=None),
        # поэтому кнопка «Скачать PDF» там не показывается вовсе — как это уже
        # сделано на странице экспорта подборок (catalog/collection_export.html).
        ctx['has_xelatex'] = xelatex_available()
        return ctx


# Команды LaTeX, которых наш генератор не выпускает и которые дают доступ
# к файловой системе или к оболочке. Файл .tex приходит с клиента, поэтому
# проверяем его перед запуском компилятора: xelatex по умолчанию идёт без
# --shell-escape, но \input умеет вклеить в PDF содержимое чужого файла.
_TEX_FORBIDDEN = re.compile(
    r'\\(write18|input|include|openin|openout|read|catcode|csname|immediate'
    r'|directlua|usepackage\s*\{\s*shellesc)',
    re.IGNORECASE,
)


@login_required
@require_POST
def export_pdf(request):
    """Компилирует присланный .tex в PDF через xelatex и отдаёт файл.

    Используется кнопкой «Скачать PDF» в окне экспорта калькулятора. Сам .tex
    собирает клиент (buildTex в calc2.html) — там же, где известны кривые,
    заливки и подписи. Здесь только компиляция.
    """
    if not xelatex_available():
        return HttpResponse(
            'На этом сервере не установлен xelatex. Скачайте .tex и '
            'скомпилируйте его в Overleaf.',
            status=503, content_type='text/plain; charset=utf-8',
        )

    tex = request.POST.get('tex', '')
    if not tex.strip():
        return HttpResponseBadRequest('Пустой файл .tex')
    if len(tex) > 400_000:
        return HttpResponseBadRequest('Файл .tex слишком большой')
    if _TEX_FORBIDDEN.search(tex):
        return HttpResponseBadRequest('В .tex есть команды, которые сервер не компилирует')

    pdf, err = compile_pdf(tex)
    if pdf is None:
        # Лог xelatex длинный; для окна экспорта хватает хвоста.
        return HttpResponse(
            'xelatex не собрал PDF:\n' + (err or '')[-1500:],
            status=500, content_type='text/plain; charset=utf-8',
        )

    name = re.sub(r'[^\w \-.]+', '', request.POST.get('name', 'график'))[:60] or 'график'
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = 'attachment; filename="{}.pdf"'.format(name)
    return resp
