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


@register.filter
def make_stars(value):
    """'3' → range(3) для рендера звёздочек через {% for %}."""
    try:
        return range(int(value))
    except (ValueError, TypeError):
        return range(0)


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
