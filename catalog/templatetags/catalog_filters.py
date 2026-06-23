from django import template

register = template.Library()


@register.simple_tag
def filter_param(request, param, value):
    """
    Возвращает строку query-параметров: все текущие params плюс один изменённый.
    Если param уже равен value — убирает его (toggle-поведение).
    Всегда сбрасывает page, чтобы при смене фильтра начинать с 1-й страницы.
    """
    params = request.GET.copy()
    params.pop('page', None)
    if str(params.get(param, '')) == str(value):
        params.pop(param, None)
    else:
        params[param] = value
    return params.urlencode()


@register.simple_tag
def set_param(request, param, value):
    """Текущие query-параметры с явно установленным param=value (page сброшен).
    Для сортировки и переключателя вида — всегда задаёт значение (не toggle)."""
    params = request.GET.copy()
    params.pop('page', None)
    params[param] = value
    return params.urlencode()


@register.simple_tag
def remove_param(request, param):
    """Текущие query-параметры без одного param (page сброшен).
    Для крестика на чипе активного фильтра."""
    params = request.GET.copy()
    params.pop('page', None)
    params.pop(param, None)
    return params.urlencode()


@register.filter
def make_stars(value):
    """'3' → range(3) для рендера звёздочек через {% for %}."""
    try:
        return range(int(value))
    except (ValueError, TypeError):
        return range(0)


@register.filter
def spaceint(value):
    """Целое с пробелом-разделителем тысяч (рус. формат): 18643 → «18 643».

    Совпадает с _fmt_number в catalog/views.py (главная), чтобы счётчики
    каталога и главной выглядели одинаково. Только отображение; нечисловое
    значение возвращается как есть."""
    try:
        n = int(value)
    except (ValueError, TypeError):
        return value
    return f'{n:,}'.replace(',', ' ')


@register.filter
def partlabel(value):
    """Метка подпункта с РОВНО одной закрывающей скобкой.

    В базе метки в двух форматах: голые («а», «1», «A») и со скобкой («а)»).
    Шаблоны раньше дописывали «)» жёстко → у меток со скобкой выходило «а))».
    Фильтр нормализует отображение: убирает хвостовые «)» / «.», добавляет одну «)».
    Данные не меняются — только показ."""
    if value is None:
        return ''
    s = str(value).rstrip(').．。 ')
    return s + ')' if s else str(value)
