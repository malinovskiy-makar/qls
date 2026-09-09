"""Тянет из банка полные данные задач пула (Фаза 2, подготовка страницы).

ТОЛЬКО ЧИТАЕТ. Источник списка id — reports/formula_choice/pool.json
(Фаза 1). Пишет reports/formula_choice/problems_data.json: id → карточка
для разметки, с текстом УЖЕ отрендеренным ровно тем же путём, что и
страница задачи на сайте (problems/rendering.render_markdown для
content_format='markdown', escape+переносы для 'plain'), плюс картинки
раскрыты в <img>/<svg> с data: URI — на офлайн-странице нет эндпоинта
catalog:problem_figure_svg, который отдаёт их на сайте.

Формулы и ранги сюда НЕ попадают — слепота разметки хранится в pool.json
и подмешивается сборщиком страницы отдельно.
"""
import base64
import json
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils.html import escape  # noqa: E402
from django.utils.text import normalize_newlines  # noqa: E402

from catalog.semantic import index_queryset  # noqa: E402
from problems.corpus_converter.tikz_render import MARKER_RE  # noqa: E402
from problems.models import Problem, ProblemFigure  # noqa: E402
from problems.rendering import render_markdown  # noqa: E402


def linebreaksbr(text):
    """То же, что django.template.defaultfilters.linebreaksbr, но на уже
    экранированном тексте: escape потом \n -> <br>, как делает |linebreaksbr
    в шаблоне ПОСЛЕ автоэкранирования Django."""
    text = normalize_newlines(escape(text))
    return text.replace('\n', '<br>')


def render_figures_offline(html, problem, figures_by_hash):
    """Как problems.figures.render_figures, но <img src="data:..."> вместо
    ссылки на catalog:problem_figure_svg — офлайн-страница эндпоинт сайта
    не видит."""
    if not html or '[[FIGURE:' not in html:
        return html or ''

    def repl(match):
        figure = figures_by_hash.get(match.group(1))
        if figure is None:
            return ''
        if figure.svg:
            return figure.svg
        if figure.image_data:
            b64 = base64.b64encode(bytes(figure.image_data)).decode('ascii')
            ct = figure.content_type or 'image/png'
            return (f'<img src="data:{ct};base64,{b64}" '
                    f'alt="График к задаче" class="problem-figure" loading="lazy">')
        return ''

    return MARKER_RE.sub(repl, html)


def render_field(text, content_format, problem, figures_by_hash):
    if not text:
        return ''
    if content_format == Problem.ContentFormat.MARKDOWN:
        html = render_markdown(text)
        html = render_figures_offline(html, problem, figures_by_hash)
        return html
    return linebreaksbr(text)


def visibility_reason(p):
    """Почему задача не видна в каталоге (срез prod), или '' если видна."""
    reasons = []
    if p.status != Problem.Status.PUBLISHED:
        reasons.append(f'статус «{p.get_status_display()}»')
    if p.needs_quality_review:
        reasons.append('забракована детектором качества')
    if p.hidden_pending_review:
        reasons.append('не проверена человеком')
    if p.content_status != Problem.ContentStatus.OK:
        reasons.append(f'текст: «{p.get_content_status_display()}»')
    return '; '.join(reasons)


def main():
    with open('reports/formula_choice/pool.json', encoding='utf-8') as fh:
        pool = json.load(fh)

    all_ids = set()
    for merged in pool['pool_per_query'].values():
        all_ids.update(int(pid) for pid in merged.keys())
    all_ids = sorted(all_ids)
    print(f'Уникальных id в пуле: {len(all_ids)}')

    prod_ids = set(index_queryset('prod').filter(pk__in=all_ids).values_list('id', flat=True))

    problems = (
        Problem.objects
        .filter(pk__in=all_ids)
        .prefetch_related('topics', 'tags', 'parts', 'figures')
    )
    by_id = {p.pk: p for p in problems}

    missing = set(all_ids) - set(by_id.keys())
    if missing:
        print(f'!!! {len(missing)} id из пула не найдены в базе: {sorted(missing)[:20]}')

    n_figures = 0
    out = {}
    for pid in all_ids:
        p = by_id.get(pid)
        if p is None:
            continue
        figures_by_hash = {f.tikz_hash: f for f in p.figures.all()}
        if figures_by_hash:
            n_figures += 1

        statement_html = render_field(p.statement, p.content_format, p, figures_by_hash)
        parts = []
        for part in p.parts.all():
            parts.append({
                'label': part.label,
                'statement_html': render_field(part.statement, p.content_format, p, figures_by_hash),
            })

        out[str(pid)] = {
            'id': pid,
            'title': p.title,
            'statement_html': statement_html,
            'parts': parts,
            'difficulty': p.difficulty,
            'topics': [t.name for t in p.topics.all()],
            'tags': [t.name for t in p.tags.all()],
            'visible_in_catalog': pid in prod_ids,
            'hidden_reason': '' if pid in prod_ids else visibility_reason(p),
        }

    out_path = 'reports/formula_choice/problems_data.json'
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print('Записано:', out_path, '—', len(out), 'задач,', n_figures, 'с картинками.')


if __name__ == '__main__':
    main()
