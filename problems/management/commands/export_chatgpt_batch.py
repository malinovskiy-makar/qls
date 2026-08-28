# -*- coding: utf-8 -*-
r"""Пакет случайной выборки задач для ревью моделью (Фаза 5 брифа).

ТОЛЬКО ЧИТАЕТ. В базу не пишет ничего.

Собирает случайную выборку по ВСЕМУ банку (не только по новым
источникам) и показывает каждую задачу так, как её реально увидит
ученик. Пакет никуда не отправляется — команда только кладёт файлы на
диск, отправка это отдельное решение человека.

**Показ дословно повторяет ветку боевого шаблона.**
`catalog/templates/catalog/problem_detail.html` выбирает по
`content_format`:

    markdown -> {{ поле|render_markdown|render_figures:problem|safe }}
    plain    -> {{ поле|linebreaksbr }}

Здесь ровно то же и теми же функциями. Прогонять `plain`-задачу через
markdown-рендерер было бы удобнее (единый путь), но пакет тогда
показывал бы не то, что на сайте: у 31 507 задач банка звёздочки и
подчёркивания — обычные символы, а не разметка.

Математику дорисовывает KaTeX — конфигурация берётся из
`corpus_review_html._HTML_FOOT_TEMPLATE`, буквальной копии
`catalog/base.html` + `templates/_katex_dollars.html` (те же разделители,
`$$` раньше `$`, маскировка `\$`, `throwOnError: false`). Второй конвейер
не заводится: разойдясь с боевым, он показывал бы фикцию.

**Размер.** Один файл на 2000 задач нечитаемо велик. Задачи идут
источник за источником и складываются в файл, пока не упрутся в один из
двух потолков: `--max-mb` (5 МБ) или `--max-problems` (250 задач).
Второй потолок обязателен: 2000 задач весят всего ~4,7 МБ, и по одним
байтам всё легло бы в единственный файл. Граница всегда между задачами —
задача целиком лежит в одном файле, это проверено тестом.

Строго по источнику не режем: получилось бы 27 файлов, восемь из них по
одной задаче.

    manage.py export_chatgpt_batch --size 2000 --seed 20260828
"""
import json
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.template.defaultfilters import linebreaksbr

from problems.figures import render_figures
from problems.management.commands.corpus_review_html import (
    _HTML_FOOT_TEMPLATE, _esc,
)
from problems.models import Problem
from problems.rendering import render_markdown

DEFAULT_SIZE = 2000
DEFAULT_SEED = 20260828
DEFAULT_MAX_MB = 5.0
#: 2000 задач весят всего ~5 МБ, поэтому байтового лимита мало: без
#: потолка по числу задач всё легло бы в один нечитаемо длинный файл.
DEFAULT_MAX_PROBLEMS = 250
DEFAULT_OUT = os.path.join(
    settings.BASE_DIR, 'reports', 'chatgpt_batch_20260828')

_HEAD = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
<style>
body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; background: #f7f7f5;
       color: #1a1a1a; margin: 0; padding: 20px; }}
h1 {{ font-size: 1.3rem; }}
.meta {{ color: #777; font-size: .9rem; margin-bottom: 16px; }}
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
</style>
</head>
<body>
<h1>{title}</h1>
<div class="meta">{meta}</div>
"""


def render_field(problem, text):
    """Одно поле задачи так, как его покажет боевой шаблон."""
    if not text:
        return ''
    if problem.content_format == Problem.ContentFormat.MARKDOWN:
        return render_figures(render_markdown(text), problem)
    return linebreaksbr(text)


def render_card(problem, parts, source_names):
    tags = [
        f'id {problem.id}',
        f'формат: {problem.content_format}',
        f'статус: {problem.status}',
        f'ревью: {problem.human_review or "не смотрели"}',
    ]
    if problem.difficulty:
        tags.append(f'сложность: {problem.difficulty}')
    if source_names:
        tags.append('источник: ' + ', '.join(source_names))

    blocks = [('Условие', render_field(problem, problem.statement))]
    for part in parts:
        blocks.append((f'Часть {_esc(part.label)}',
                       render_field(problem, part.statement)))
        if part.answer:
            blocks.append((f'Ответ на часть {_esc(part.label)}',
                           render_field(problem, part.answer)))
    if problem.answer:
        blocks.append(('Ответ', render_field(problem, problem.answer)))
    if problem.solution:
        blocks.append(('Решение', render_field(problem, problem.solution)))

    out = [f'<div class="card"><h2>#{problem.id} {_esc(problem.title)}</h2>',
           '<div class="tags">'
           + ''.join(f'<span class="tag">{_esc(t)}</span>' for t in tags)
           + '</div>']
    for name, body in blocks:
        if not body:
            continue
        out.append(f'<div class="block"><div class="name">{name}</div>'
                   f'<div class="body">{body}</div></div>')
    out.append('</div>')
    return '\n'.join(out)


class Command(BaseCommand):
    help = ('Read-only: пакет случайной выборки задач по всему банку, '
            'показанных боевым конвейером. Никуда не отправляется.')

    def add_arguments(self, parser):
        parser.add_argument('--size', type=int, default=DEFAULT_SIZE)
        parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
        parser.add_argument('--max-mb', type=float, default=DEFAULT_MAX_MB)
        parser.add_argument('--max-problems', type=int, default=DEFAULT_MAX_PROBLEMS,
                            help='потолок задач на файл — 2000 задач весят ~5 МБ '
                                 'и по одним байтам легли бы в один файл')
        parser.add_argument('--out', default=DEFAULT_OUT)
        parser.add_argument('--ids', help='явный список id через запятую '
                                          '(вместо случайной выборки)')

    def handle(self, *args, **options):
        out_dir = options['out']
        max_bytes = int(options['max_mb'] * 1024 * 1024)
        os.makedirs(out_dir, exist_ok=True)

        all_ids = sorted(Problem.objects.values_list('id', flat=True))
        if not all_ids:
            raise CommandError('в банке нет ни одной задачи')

        notes = []
        if options['ids']:
            wanted = [int(x) for x in options['ids'].split(',') if x.strip()]
            ids = [i for i in all_ids if i in set(wanted)]
            notes.append(f'явный список id: {len(ids)}')
        else:
            size = options['size']
            if size > len(all_ids):
                notes.append(f'запрошено {size}, в банке всего {len(all_ids)} — '
                             f'взяты все')
                size = len(all_ids)
            ids = sorted(random.Random(options['seed']).sample(all_ids, size))
            notes.append(f'сид {options["seed"]}, выборка {len(ids)} '
                         f'из {len(all_ids)}')

        problems = (
            Problem.objects.filter(id__in=ids)
            .prefetch_related('parts', 'source_references__source')
            if len(ids) < 900 else None)
        if problems is None:
            # SQLite не переваривает многотысячный IN — идём по всей таблице
            # и фильтруем множеством. Та же ловушка, что в
            # import_invariants_check («too many SQL variables»).
            wanted = set(ids)
            problems = [
                p for p in Problem.objects
                .prefetch_related('parts', 'source_references__source')
                .iterator(chunk_size=500)
                if p.id in wanted
            ]

        by_source = {}
        cards = {}
        for problem in problems:
            names = sorted({
                ref.source.name for ref in problem.source_references.all()})
            key = names[0] if names else 'Без источника'
            by_source.setdefault(key, []).append(problem.id)
            cards[problem.id] = render_card(
                problem, list(problem.parts.all()), names)

        # Раскладка по файлам. Источники идут подряд и не перемешиваются
        # без нужды, но мелкие складываются в один файл: группировка строго
        # по источнику дала бы 27 файлов, из них 8 по одной задаче — читать
        # такое неудобно. Файл закрывается по ЛЮБОМУ из двух лимитов:
        # байты (--max-mb) и число задач (--max-problems). Второй нужен
        # потому, что 2000 задач весят всего ~5 МБ и по байтам легли бы в
        # один нечитаемо длинный файл.
        max_problems = options['max_problems']
        files = []
        chunk, chunk_bytes, chunk_sources, part_no = [], 0, [], 1

        def close():
            nonlocal chunk, chunk_bytes, chunk_sources, part_no
            if not chunk:
                return
            files.append(self._write(
                out_dir, chunk_sources, part_no, chunk, cards, notes))
            part_no += 1
            chunk, chunk_bytes, chunk_sources = [], 0, []

        for source_name in sorted(by_source):
            for problem_id in sorted(by_source[source_name]):
                card_bytes = len(cards[problem_id].encode('utf-8'))
                too_big = chunk and chunk_bytes + card_bytes > max_bytes
                too_many = chunk and len(chunk) >= max_problems
                if too_big or too_many:
                    close()
                chunk.append(problem_id)
                chunk_bytes += card_bytes
                if source_name not in chunk_sources:
                    chunk_sources.append(source_name)
        close()

        manifest = {
            'seed': options['seed'],
            'size_requested': options['size'],
            'bank_total': len(all_ids),
            'ids': ids,
            'by_source': {k: len(v) for k, v in sorted(by_source.items())},
            'files': files,
            'notes': notes,
        }
        with open(os.path.join(out_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        self._write_readme(out_dir, manifest, options)

        lines = ['Пакет выборки на ревью (только чтение, ничего не отправлено)',
                 f'  папка: {out_dir}']
        lines += [f'  {note}' for note in notes]
        lines.append(f'  файлов: {len(files)}, '
                     f'суммарно {sum(f["bytes"] for f in files) / 1024 / 1024:.1f} МБ')
        for entry in files:
            lines.append(f'    {entry["file"]}: задач {len(entry["ids"])}, '
                         f'{entry["bytes"] / 1024 / 1024:.2f} МБ')
        lines.append(f'  по источникам: {manifest["by_source"]}')
        self.stdout.write(self.style.SUCCESS('\n'.join(lines)))

    def _write(self, out_dir, source_names, part_no, ids, cards, notes):
        name = f'batch_{part_no:02d}.html'
        title = f'Часть {part_no}: ' + ', '.join(source_names)
        meta = (f'{len(ids)} задач · показано боевым конвейером '
                f'(render_markdown/linebreaksbr + KaTeX 0.16.9) · '
                + '; '.join(notes))
        body = _HEAD.format(title=_esc(title), meta=_esc(meta))
        body += '\n'.join(cards[i] for i in ids)
        body += _HTML_FOOT_TEMPLATE
        path = os.path.join(out_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(body)
        return {'file': name, 'sources': source_names, 'ids': ids,
                'bytes': os.path.getsize(path)}

    def _write_readme(self, out_dir, manifest, options):
        text = f"""# Пакет выборки на ревью внешнего вида

Собран командой `manage.py export_chatgpt_batch`. **Никуда не отправлен** —
это просто файлы на диске.

- Выборка: {len(manifest['ids'])} задач из {manifest['bank_total']},
  случайно, сид `{options['seed']}`. Повторный запуск с тем же сидом даёт
  ту же выборку (`manifest.json` -> `ids`).
- Охват: ВЕСЬ банк, а не только новые источники — легаси включён.
- Показ: дословно ветка боевого шаблона `catalog/problem_detail.html`
  (`markdown` -> `render_markdown` + `render_figures`, `plain` ->
  `linebreaksbr`), математика — KaTeX 0.16.9 с той же конфигурацией, что
  на сайте. То есть страница показывает то, что реально увидит ученик.
- Разбивка: по источникам, крупная группа — на части не больше
  {options['max_mb']} МБ. Задача целиком лежит в одном файле.

## Файлы

| файл | задач | МБ |
|---|---:|---:|
"""
        for entry in manifest['files']:
            text += (f'| {entry["file"]} | {len(entry["ids"])} | '
                     f'{entry["bytes"] / 1024 / 1024:.2f} |\n')
        text += '\n## Состав выборки по источникам\n\n'
        for name, count in manifest['by_source'].items():
            text += f'- {name}: {count}\n'
        with open(os.path.join(out_dir, 'README.md'), 'w', encoding='utf-8') as f:
            f.write(text)
