# -*- coding: utf-8 -*-
r"""Очередь ручного разбора по трём новым источникам.

Собирает в один markdown то, что автоматика чинить НЕ должна, с
машинным кодом причины у каждой задачи. Пара к
`corpus_manual_review_queue` (легаси); только чтение, в базу не пишет.

Что сюда попадает и почему именно человек:

* **Ссылка на картинку, которой нет в выгрузке.** У Школково 298 задач
  ссылаются на `ela.png`, `7.png` и подобные, и НИ ОДНОГО из этих файлов
  в выгрузке нет: `QuestionFiles` пуст у всех 3 414 записей, а 453
  скачанные картинки принадлежат 328 ДРУГИМ задачам (пересечение
  идентификаторов — ноль). Вырезать ссылку значило бы показать ученику
  задачу «по графику ниже» без графика — молча и без следа.
* **Отказы шлюза** (`render_new_sources`) — с кодом причины.
* **ЛЭШ без решения** — подбор по смыслу запрещён.
* **Мёртвые ссылки на картинки** — придумывать замену нечем.

По каждому пункту в файле стоит id, внешний id источника и короткая
выдержка, чтобы разбирать можно было не открывая базу.
"""
import json
import os
import re

from django.conf import settings
from django.core.management.base import BaseCommand

from problems.corpus_converter.images import INCLUDEGRAPHICS_RE, MD_IMAGE_RE
from problems.corpus_converter.reconvert import LOADERS
from problems.models import Problem, Source

OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'import_new_sources')
DIAGNOSIS = 'fails_diagnosis.json'


class Command(BaseCommand):
    help = 'Собрать очередь ручного разбора по трём новым источникам (только чтение).'

    def add_arguments(self, parser):
        parser.add_argument('--report-dir',
                            help='откуда брать fails_diagnosis.json и куда класть '
                                 'очередь; тесты обязаны давать временную папку')

    def handle(self, *args, **options):
        out_dir = options.get('report_dir') or OUT_DIR
        os.makedirs(out_dir, exist_ok=True)

        diagnosis_path = os.path.join(out_dir, DIAGNOSIS)
        rows = []
        if os.path.exists(diagnosis_path):
            with open(diagnosis_path, encoding='utf-8') as f:
                rows = json.load(f)['rows']
        else:
            self.stdout.write(self.style.WARNING(
                f'{DIAGNOSIS} нет — раздел отказов шлюза будет пуст. '
                f'Сначала diagnose_new_sources.'))

        sections = []
        sections.append(self._gate_failures(rows))
        sections.append(self._images_without_files())
        sections.append(self._lesh_without_solution())

        total = sum(count for _title, count, _body in sections)
        head = [
            '# Очередь ручного разбора — три новых источника',
            '',
            'Собрано командой `new_sources_manual_queue` (только чтение).',
            'Сюда попадает то, что автоматика чинить НЕ должна: у одних задач',
            'нет исходного материала (картинки), у других дефект в самом',
            'материале. **Автоматической правки по этому списку нет и быть',
            'не должно.**',
            '',
            '## Сводка',
            '',
            '| Раздел | Задач |',
            '|---|---:|',
        ]
        for title, count, _body in sections:
            head.append(f'| {title} | {count} |')
        head.append(f'| **Всего строк очереди** | **{total}** |')
        head.append('')
        head.append('⚠️ Одна задача может попасть в несколько разделов — '
                    'это строки очереди, а не уникальные задачи.')
        head.append('')

        body = []
        for title, count, text in sections:
            body.append(f'## {title} — {count}')
            body.append('')
            body.append(text)
            body.append('')

        path = os.path.join(out_dir, 'manual_review_queue.md')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(head + body))
        self.stdout.write(self.style.SUCCESS(
            f'Очередь собрана: {path}\n  строк всего: {total}\n'
            + '\n'.join(f'    {t}: {c}' for t, c, _b in sections)))

    # -- разделы -----------------------------------------------------------

    def _gate_failures(self, rows):
        """Отказы шлюза, сгруппированные по коду."""
        if not rows:
            return ('Отказы шлюза рендера', 0, '_нет данных_')
        by_code = {}
        for row in rows:
            key = '+'.join(sorted(row['codes']))
            by_code.setdefault(key, []).append(row)
        lines = []
        for key in sorted(by_code, key=lambda k: -len(by_code[k])):
            group = by_code[key]
            lines.append(f'### `{key}` — {len(group)}')
            lines.append('')
            lines.append('| id | источник | что увидел шлюз |')
            lines.append('|---|---|---|')
            for row in group:
                detail = (row['details'][0] if row['details'] else '')[:160]
                detail = detail.replace('|', '\\|').replace('\n', ' ')
                lines.append(f'| {row["id"]} | {row["source"]} | {detail} |')
            lines.append('')
        return ('Отказы шлюза рендера', len(rows), '\n'.join(lines))

    def _images_without_files(self):
        """Ссылки на картинки, для которых файла нет нигде."""
        names = [name for name, _loader in LOADERS.values()]
        sources = {s.name: s for s in Source.objects.filter(name__in=names)}
        lines = ['| id | источник | ссылка в тексте |', '|---|---|---|']
        count = 0
        for name, source in sources.items():
            qs = (Problem.objects.filter(source_references__source=source)
                  .distinct().prefetch_related('parts', 'source_references')
                  .order_by('id'))
            for problem in qs:
                refs = []
                texts = [problem.statement, problem.answer, problem.solution]
                texts += [p.statement for p in problem.parts.all()]
                for text in texts:
                    refs += MD_IMAGE_RE.findall(text or '')
                    refs += INCLUDEGRAPHICS_RE.findall(text or '')
                if not refs:
                    continue
                count += 1
                shown = ', '.join(sorted({r[:70] for r in refs})[:3])
                shown = shown.replace('|', '\\|')
                lines.append(f'| {problem.id} | {name.split("—")[0].strip()} '
                             f'| `{shown}` |')
        note = (
            'Ссылка осталась в тексте ЦЕЛОЙ и видна на экране — это сделано '
            'намеренно. Маркер `[[FIGURE:…]]` без строки `ProblemFigure` на '
            'экране просто исчезает, то есть картинка пропала бы молча.\n\n'
            'Для Школково файлов нет в принципе: `QuestionFiles` пуст у всех '
            '3 414 записей выгрузки, а 453 скачанные картинки принадлежат 328 '
            'другим задачам (пересечение идентификаторов — ноль). Нужна '
            'повторная выгрузка картинок с сайта источника по этим id.\n')
        return ('Ссылка на картинку без файла', count,
                note + '\n' + '\n'.join(lines))

    def _lesh_without_solution(self):
        """ЛЭШ: задачи без решения — сопоставление по смыслу запрещено."""
        source = Source.objects.filter(name=LOADERS['lesh'][0]).first()
        if source is None:
            return ('ЛЭШ без решения', 0, '_источника нет в базе_')
        qs = (Problem.objects.filter(source_references__source=source)
              .filter(solution='').distinct()
              .prefetch_related('source_references').order_by('id'))
        lines = ['Подбор решения по смыслу запрещён — пары id↔id ставит человек.',
                 '', '| id | название | первые слова условия |', '|---|---|---|']
        count = 0
        for problem in qs:
            count += 1
            title = (problem.title or '')[:60].replace('|', '\\|')
            head = re.sub(r'\s+', ' ', (problem.statement or ''))[:90]
            head = head.replace('|', '\\|')
            lines.append(f'| {problem.id} | {title} | {head} |')
        return ('ЛЭШ без решения', count, '\n'.join(lines))
