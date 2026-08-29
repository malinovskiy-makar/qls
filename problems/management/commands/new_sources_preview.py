# -*- coding: utf-8 -*-
r"""HTML-предпросмотр трёх новых источников для глазами владельца.

Показ дословно повторяет боевой путь `catalog/problem_detail.html`:

    markdown -> render_markdown | render_figures
    plain    -> linebreaksbr

и боевой KaTeX из `catalog/base.html` + `templates/_katex_dollars.html`:
маскировка `\$`, те же четыре пары разделителей, `$$` РАНЬШЕ `$`,
`throwOnError: false`, `trust: false`. Скрипт масок берётся из самого
шаблона, а не переписывается: копия рано или поздно разойдётся с
оригиналом, и замер превратится в фикцию
(`problems/management/commands/CLAUDE.md`).

KaTeX — вендорный 0.16.9 (`problems/review_bundle_assets/vendor/katex`),
а не с CDN: та же версия, что на проде, и страница открывается без сети.

Две части:

* **случайная выборка** — доля источников как в банке, а не поровну;
* **все карточки с картинками** — новая механика показа, владельцу важно
  посмотреть именно их. Картинки вшиты в страницу как `data:`-адреса,
  поэтому файл самодостаточен; из-за этого части режутся по весу.
"""
import base64
import os
import random
import re
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.template.defaultfilters import linebreaksbr

from problems.figures import render_figures
from problems.management.commands.corpus_review_html import _esc
from problems.models import Problem, ProblemFigure, Source
from problems.rendering import render_markdown

SOURCES = {
    'shkolkovo': 'Школково — банк задач по экономике',
    'solvehub': 'SolveHub — банк задач по экономике',
    'lesh': 'ЛЭШ 2026 — Гамма',
}
OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'new_sources_preview')
VENDOR_SRC = os.path.join(settings.BASE_DIR, 'problems',
                          'review_bundle_assets', 'vendor', 'katex')
DOLLARS_TEMPLATE = os.path.join(settings.BASE_DIR, 'templates',
                                '_katex_dollars.html')
DEFAULT_SIZE = 300
DEFAULT_SEED = 20260829
#: Потолок веса части. Картинки вшиты в страницу, и без потолка все 835
#: легли бы в один файл на 50+ МБ, который браузер открывает минуту.
MAX_MB = 6.0

_SRC_RE = re.compile(r'src="/[^"]*/figure/(\d+)\.svg"')

_HEAD = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="katex/katex.min.css">
<script defer src="katex/katex.min.js"></script>
<script defer src="katex/contrib/auto-render.min.js"></script>
<style>
body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; background: #f7f7f5;
       color: #1a1a1a; margin: 0; padding: 20px; }}
h1 {{ font-size: 1.3rem; }}
.meta {{ color: #777; font-size: .9rem; margin-bottom: 16px; max-width: 60em; }}
.card {{ background: #fff; border: 1px solid #ddd; border-radius: 6px;
        margin: 0 0 14px; padding: 12px 14px; }}
.card h2 {{ font-size: 1rem; margin: 0 0 6px; font-family: monospace; }}
.tags {{ color: #777; font-size: .82rem; margin-bottom: 8px; }}
.tag {{ display: inline-block; background: #eee; border: 1px solid #ccc;
       border-radius: 10px; padding: 1px 8px; margin-right: 6px; }}
.block {{ margin: 8px 0; }}
.block > .name {{ font-size: .75rem; text-transform: uppercase; color: #888; }}
.block > .body {{ border: 1px solid #eee; border-radius: 4px; padding: 8px;
                 background: #fafafa; overflow-x: auto; }}
.block table {{ border-collapse: collapse; }}
.block td, .block th {{ border: 1px solid #ccc; padding: 3px 8px; }}
img.problem-figure {{ max-width: 100%; height: auto; display: block;
                     margin: 8px 0; border: 1px solid #eee; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="meta">{meta}</div>
"""

_FOOT = """
{dollars}
<script>
document.addEventListener('DOMContentLoaded', function () {{
  maskEscapedDollars(document.body);
  renderMathInElement(document.body, {{
    delimiters: [
      {{ left: '$$',   right: '$$',   display: true  }},
      {{ left: '$',    right: '$',    display: false }},
      {{ left: '\\\\[',  right: '\\\\]',  display: true  }},
      {{ left: '\\\\(',  right: '\\\\)',  display: false }}
    ],
    throwOnError: false,
    trust: false
  }});
  fixCurrencyDollars(document.body);
}});
</script>
</body></html>
"""


def _dollars_script():
    """Скрипт масок — ДОСЛОВНО из боевого шаблона, без комментария Django."""
    with open(DOLLARS_TEMPLATE, encoding='utf-8') as f:
        text = f.read()
    start = text.find('{% endcomment %}')
    return text[start + len('{% endcomment %}'):] if start != -1 else text


class Command(BaseCommand):
    help = 'HTML-предпросмотр трёх новых источников (только чтение).'

    def add_arguments(self, parser):
        parser.add_argument('--size', type=int, default=DEFAULT_SIZE,
                            help=f'случайная выборка (по умолчанию {DEFAULT_SIZE})')
        parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
        parser.add_argument('--out-dir', help='куда класть страницы')
        parser.add_argument('--skip-figures', action='store_true',
                            help='не собирать часть с картинками (быстрее)')

    def handle(self, *args, **options):
        out_dir = options.get('out_dir') or OUT_DIR
        os.makedirs(out_dir, exist_ok=True)
        vendor_dst = os.path.join(out_dir, 'katex')
        if not os.path.isdir(VENDOR_SRC):
            raise CommandError(f'Вендорный KaTeX не найден: {VENDOR_SRC}')
        if os.path.isdir(vendor_dst):
            shutil.rmtree(vendor_dst)
        shutil.copytree(VENDOR_SRC, vendor_dst)

        sources = {slug: Source.objects.filter(name=name).first()
                   for slug, name in SOURCES.items()}
        missing = [s for s, obj in sources.items() if obj is None]
        if missing:
            raise CommandError(f'Источники не найдены в базе: {missing}')

        self.dollars = _dollars_script()
        written = []
        written += self._random_part(out_dir, sources, options)
        if not options['skip_figures']:
            written += self._figures_part(out_dir, sources)

        lines = ['', 'Собрано:']
        for path in written:
            lines.append(f'  {os.path.basename(path)} '
                         f'— {os.path.getsize(path) / 1048576:.1f} МБ')
        lines.append(f'  папка: {out_dir}')
        self.stdout.write(self.style.SUCCESS('\n'.join(lines)))

    # -- части -------------------------------------------------------------

    def _random_part(self, out_dir, sources, options):
        """Случайная выборка, доля источников как в банке."""
        size, seed = options['size'], options['seed']
        totals = {slug: Problem.objects.filter(
            source_references__source=obj).distinct().count()
            for slug, obj in sources.items()}
        grand = sum(totals.values())
        rng = random.Random(seed)
        picked, quota_note = [], []
        for slug, obj in sources.items():
            quota = round(size * totals[slug] / grand)
            ids = list(Problem.objects.filter(source_references__source=obj)
                       .distinct().order_by('id').values_list('id', flat=True))
            chosen = rng.sample(ids, min(quota, len(ids)))
            picked += chosen
            quota_note.append(f'{slug} {len(chosen)} из {totals[slug]} '
                              f'({totals[slug] * 100 // grand}% банка)')
        meta = ('Случайная выборка, доля источников как в банке, а не поровну. '
                f'Сид {seed}, воспроизводимо. Состав: ' + '; '.join(quota_note)
                + '. Показ дословно повторяет боевой шаблон: markdown → '
                'render_markdown + render_figures, plain → linebreaksbr; '
                'KaTeX 0.16.9 вендорный, конфигурация боевая.')
        path = os.path.join(out_dir, 'random_300.html')
        self._write_page(path, f'Новые источники — случайные {len(picked)}',
                         meta, picked, embed_images=True)
        return [path]

    def _figures_part(self, out_dir, sources):
        """Все карточки с картинками — новая механика показа."""
        ids = sorted(set(
            ProblemFigure.objects.filter(
                problem__source_references__source__in=list(sources.values()))
            .values_list('problem_id', flat=True)))
        if not ids:
            return []
        written = []
        chunk, chunk_bytes, index = [], 0, 1
        for problem_id in ids:
            weight = sum(
                len(bytes(f.image_data or b''))
                for f in ProblemFigure.objects.filter(problem_id=problem_id))
            if chunk and chunk_bytes + weight > MAX_MB * 1048576:
                written.append(self._write_figures_chunk(
                    out_dir, index, chunk, len(ids)))
                chunk, chunk_bytes, index = [], 0, index + 1
            chunk.append(problem_id)
            chunk_bytes += weight
        if chunk:
            written.append(self._write_figures_chunk(
                out_dir, index, chunk, len(ids)))
        return written

    def _write_figures_chunk(self, out_dir, index, ids, total):
        path = os.path.join(out_dir, f'figures_{index:02d}.html')
        meta = (f'Задачи с картинками: часть {index}, {len(ids)} из {total}. '
                'Картинка показана тем же путём, что на сайте: в тексте стоит '
                'маркер, <img> подставляется ПОСЛЕ санитайзера по первичному '
                'ключу строки ProblemFigure. Здесь адрес заменён на вшитый '
                'data:-адрес, чтобы страница открывалась без сервера — сам '
                'механизм подстановки тот же.')
        self._write_page(path, f'Новые источники — картинки, часть {index}',
                         meta, ids, embed_images=True)
        return path

    # -- отрисовка ---------------------------------------------------------

    def _render_field(self, problem, text):
        if not text:
            return ''
        if problem.content_format == Problem.ContentFormat.MARKDOWN:
            return render_figures(render_markdown(text), problem)
        return linebreaksbr(text)

    def _embed(self, html, figures_by_pk):
        """Заменить адрес картинки на вшитый `data:` — страница без сервера."""
        def repl(match):
            figure = figures_by_pk.get(int(match.group(1)))
            if figure is None:
                return match.group(0)
            if figure.image_data:
                payload = base64.b64encode(bytes(figure.image_data)).decode()
                return f'src="data:{figure.content_type};base64,{payload}"'
            payload = base64.b64encode(figure.svg.encode('utf-8')).decode()
            return f'src="data:image/svg+xml;base64,{payload}"'
        return _SRC_RE.sub(repl, html)

    def _write_page(self, path, title, meta, ids, embed_images):
        problems = (Problem.objects.filter(id__in=ids)
                    .prefetch_related('parts', 'figures', 'rubrics__criteria',
                                      'source_references__source')
                    .order_by('id'))
        parts_out = [_HEAD.format(title=_esc(title), meta=_esc(meta))]
        for problem in problems:
            figures_by_pk = {f.pk: f for f in problem.figures.all()}
            tags = [f'id {problem.id}',
                    f'формат: {problem.content_format}',
                    f'статус: {problem.status}',
                    'скрыто до ревью' if problem.hidden_pending_review else 'видно']
            names = [ref.source.name for ref in problem.source_references.all()]
            if names:
                tags.append('источник: ' + ', '.join(names))
            if figures_by_pk:
                tags.append(f'картинок: {len(figures_by_pk)}')
            rubric_criteria = [c for r in problem.rubrics.all()
                               for c in r.criteria.all()]
            if rubric_criteria:
                tags.append(f'критериев: {len(rubric_criteria)}')

            blocks = [('Условие', self._render_field(problem, problem.statement))]
            for part in problem.parts.all():
                blocks.append((f'Часть {_esc(part.label)}',
                               self._render_field(problem, part.statement)))
            if problem.answer:
                blocks.append(('Ответ', self._render_field(problem, problem.answer)))
            if problem.solution:
                blocks.append(('Решение',
                               self._render_field(problem, problem.solution)))
            if rubric_criteria:
                rows = ''.join(
                    f'<tr><td>{_esc(c.name)}</td><td>{c.max_points}</td></tr>'
                    for c in rubric_criteria)
                blocks.append(('Критерии',
                               f'<table><tr><th>критерий</th>'
                               f'<th>балл</th></tr>{rows}</table>'))

            card = [f'<div class="card"><h2>#{problem.id} '
                    f'{_esc(problem.title)}</h2>',
                    '<div class="tags">'
                    + ''.join(f'<span class="tag">{_esc(t)}</span>' for t in tags)
                    + '</div>']
            for name, body in blocks:
                if not body:
                    continue
                if embed_images:
                    body = self._embed(body, figures_by_pk)
                card.append(f'<div class="block"><div class="name">{name}</div>'
                            f'<div class="body">{body}</div></div>')
            card.append('</div>')
            parts_out.append(''.join(card))
        parts_out.append(_FOOT.format(dollars=self.dollars))
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(parts_out))
