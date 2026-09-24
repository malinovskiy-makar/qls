from django import template

from problems.figures import render_figures as _render_figures
from problems.jsonsafe import dumps_for_script
from problems.rendering import render_markdown as _render_markdown

register = template.Library()


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


@register.filter(name='render_markdown')
def render_markdown_filter(value):
    """Обёртка над problems.rendering.render_markdown для content_format='markdown'.

    ⚠️ Результат НЕ помечается mark_safe здесь — `|safe` ставится явно в
    шаблоне (`_math_text.html`), чтобы каждое использование оставалось
    видно текстом при поиске по `|safe` (docs/SECURITY.md держит список
    `|safe` в проекте коротким и проверяемым grep'ом; спрятанный внутри
    фильтра mark_safe в этот список не попал бы).

    Санитайзер (nh3) уже отработал внутри render_markdown — сюда
    ЛЮБОЙ текст можно передавать как есть, включая произвольный
    пользовательский ввод; безопасность гарантирует сама функция.
    """
    return _render_markdown(value)


@register.filter(name='render_figures')
def render_figures_filter(html, problem):
    """Подставить сгенерированные картинки ПОСЛЕ санитайзера.

    В шаблоне обязательно стоит вторым:
        {{ problem.statement|render_markdown|render_figures:problem|safe }}

    Порядок виден прямо в разметке и это намеренно: сначала `nh3`
    вычищает вообще всё, включая любой `<img>`/`<svg>` из текста задачи,
    и только потом маркер `[[FIGURE:<hex>]]` превращается в картинку,
    адрес которой берётся из строки `ProblemFigure` ЭТОЙ задачи.
    Расширять allow-list санитайзера при этом не нужно —
    см. `problems/figures.py` и ADR 0031.
    """
    return _render_figures(html, problem)


@register.filter(name='script_json')
def script_json(value):
    """JSON для тега `<script type="application/json">` — кириллица как есть.

    Штатный `json_script` пишет не-ASCII как `\\uXXXX`: страница переставала
    содержать русские фразы буквально, и проверка «HTML содержит фразу» их
    не находила. `dumps_for_script` держит кириллицу и экранирует только
    `<`, `>`, `&` — выйти из тега таким значением нельзя. Выводить через
    `|safe` в шаблоне (как и остальные вызовы `dumps_for_script`), иначе
    автоэкранирование превратит кавычки JSON в `&quot;`.
    """
    return dumps_for_script(value)
