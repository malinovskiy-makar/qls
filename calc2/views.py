"""
Views для собственного графического движка (Этап Е, приложение calc2).

Это НОВЫЙ калькулятор на открытых библиотеках (D3.js + Math.js), который
со временем заменит калькулятор на Desmos (приложение graphs, страница /desmos/).
Старый калькулятор не трогаем — он продолжает работать как есть.

Пока в базе ничего не сохраняем (моделей у calc2 нет): это чистый
интерактивный инструмент. Сохранение графиков — задача будущих сессий.
"""

from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView


@method_decorator(login_required, name='dispatch')
class Calc2View(TemplateView):
    """Рендерит страницу нового графического калькулятора.

    Требует входа в систему (@login_required) — как и калькулятор Desmos.
    """
    template_name = 'calc2/calc2.html'
