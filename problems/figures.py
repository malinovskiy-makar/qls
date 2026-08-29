# -*- coding: utf-8 -*-
"""Показ сгенерированных картинок — отдельный контролируемый путь.

Живёт РЯДОМ с `problems/rendering.py`, а не внутри него, и это
принципиально. `rendering.py` — общий санитайзер показа для всего текста
задач; его allow-list (`p, strong, em, ul, ol, li, br, code, pre, table,
thead, tbody, tr, th, td`, `attributes={}`) остаётся ровно таким, как
есть. Здесь — узкая дорожка ТОЛЬКО для картинок, которые сгенерировала
сама система.

Порядок обязателен:

    render_markdown(text)   -> санитайзер снял ВСЁ опасное, включая любой
                               <img>/<svg>, написанный в тексте задачи
    render_figures(html, p) -> и только теперь маркеры заменяются на <img>

Почему подстановка безопасна — три независимых свойства:

1. **Из текста задачи берётся только hex.** Маркер — `[[FIGURE:<64 hex>]]`
   и ничего больше: `MARKER_RE` не примет ни путь, ни URL, ни верхний
   регистр. Подставить свой `src` через текст физически нечем.
2. **Адрес строится из объекта БД.** `src` — это `reverse()` по
   первичному ключу строки `ProblemFigure`, никогда не строка из текста.
3. **Поиск ограничен ЭТОЙ задачей.** Даже настоящий хеш чужой картинки
   не разрешится: выбираются только `problem.figures`. Иначе автор одной
   задачи мог бы показать картинку из другой.

Неизвестный или чужой маркер не оставляет следа — он просто исчезает.
Показывать «сломанную картинку» ученику незачем.
"""
from __future__ import annotations

from django.urls import reverse
from django.utils.html import escape

from problems.corpus_converter.tikz_render import MARKER_RE
from problems.models import ProblemFigure


def figure_url(figure):
    """Адрес картинки. Строится по pk строки БД, не по тексту задачи."""
    return reverse('catalog:problem_figure_svg', args=[figure.pk])


def render_figures(html, problem):
    """Заменить маркеры на `<img>`. Вызывать ПОСЛЕ `render_markdown`.

    `problem` может быть `None` (например при рендере фрагмента вне
    контекста задачи) — тогда ни один маркер не разрешается, что
    безопасно по умолчанию."""
    if not html or '[[FIGURE:' not in html:
        return html or ''
    if problem is None or not getattr(problem, 'pk', None):
        return MARKER_RE.sub('', html)

    figures = {f.tikz_hash: f for f in
               ProblemFigure.objects.filter(problem=problem)}
    if not figures:
        return MARKER_RE.sub('', html)

    def repl(match):
        figure = figures.get(match.group(1))
        if figure is None:
            # Хеш правильного вида, но не наш: чужая задача, устаревший
            # блок или подделка в тексте. Ничего не показываем.
            return ''
        return (f'<img src="{escape(figure_url(figure))}" '
                f'alt="График к задаче" class="problem-figure" '
                f'loading="lazy">')

    return MARKER_RE.sub(repl, html)
