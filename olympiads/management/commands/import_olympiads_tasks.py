"""Заливка заданий пакета олимпиад в банк задач (`Problem`) и позиции комплектов.

    manage.py import_olympiads_tasks <папка пакета>              # сухой прогон
    manage.py import_olympiads_tasks <папка пакета> --only vseros
    manage.py import_olympiads_tasks <папка пакета> --apply      # запись

⚠️ ПО УМОЛЧАНИЮ — СУХОЙ ПРОГОН: план считается целиком, в базу не пишется
ни строки. Запись — только с `--apply`, одной транзакцией; любой нарушенный
инвариант (изменилась прежняя задача, сдвинулся счётчик каталога, не
сошлись числа) откатывает её целиком.

Комплекты должны быть уже залиты (`import_olympiads_kits`). Эмбеддинги
команда не считает: скрытые задачи в поиске не участвуют. Логика и
причины — `olympiads/tasks_import.py`, сопоставление с банком —
`olympiads/bank_match.py`.
"""
import datetime
import html
import json
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max

from olympiads import kits_import as ki
from olympiads import tasks_import as ti

PREVIEW_SIZE = 20


class Command(BaseCommand):
    help = ('Задания пакета олимпиад → скрытые задачи банка и позиции '
            'комплектов. Без --apply — сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('package', help='Папка пакета (где лежат */kits/).')
        parser.add_argument('--only', default='',
                            help='Только один слаг, например vseros.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Сухой прогон (по умолчанию и так он).')
        parser.add_argument('--apply', action='store_true',
                            help='Записать в базу.')
        parser.add_argument('--report-dir', default='',
                            help='Куда класть отчёт и предпросмотр '
                                 '(по умолчанию reports/).')

    def handle(self, *args, **options):
        from olympiads.models import OlympiadVariantItem
        from problems.models import Problem

        if options['dry_run'] and options['apply']:
            raise CommandError('--dry-run и --apply вместе нельзя.')
        apply = options['apply']
        root = os.path.abspath(options['package'])
        report = ki.Report()
        before = {'problems': Problem.objects.count(),
                  'items': OlympiadVariantItem.objects.count(),
                  **ti.catalog_counts()}

        plan = ti.make_plan(root, options['only'])
        summary = ti.summarize(plan)

        if apply:
            max_id = Problem.objects.aggregate(m=Max('id'))['m'] or 0
            digest = ti.existing_digest(max_id)
            with transaction.atomic():
                created = ti.apply_plan(plan, root, report)
                after = {'problems': Problem.objects.count(),
                         'items': OlympiadVariantItem.objects.count(),
                         **ti.catalog_counts()}
                self._check(before, after, summary, created, digest, max_id)
        else:
            after = {}

        self._print(summary, report, before, after, apply)
        directory = options['report_dir'] or os.path.join(settings.BASE_DIR, 'reports')
        os.makedirs(directory, exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(directory, 'olympiads_tasks_{}.json'.format(stamp))
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'package': root, 'only': options['only'],
                       'applied': apply, 'summary': summary,
                       'before': before, 'after': after,
                       **report.as_dict(),
                       'matched': plan['matched'],
                       'new_groups': [[e['task']['ref_key'] for e in g]
                                      for g in plan['new_groups']]},
                      fh, ensure_ascii=False, indent=1, default=str)
        self.stdout.write('Отчёт: {}'.format(path))
        if plan['new_groups']:
            preview = os.path.join(directory,
                                   'olympiads_tasks_{}.html'.format(stamp))
            self._preview(plan, preview)
            self.stdout.write('Предпросмотр: {}'.format(preview))

    def _check(self, before, after, summary, created, digest, max_id):
        """Инварианты записи. Нарушен любой — транзакция откатывается."""
        from problems.models import Problem
        problems = []
        if after['problems'] != before['problems'] + summary['новых задач будет создано']:
            problems.append('число задач: было {}, стало {}, план +{}'.format(
                before['problems'], after['problems'],
                summary['новых задач будет создано']))
        if after['items'] != before['items'] + summary['позиций будет создано']:
            problems.append('число позиций не сошлось с планом')
        for gate in ('catalog', 'tutor'):
            if after[gate] != before[gate]:
                problems.append('видимых задач ({}): было {}, стало {}'.format(
                    gate, before[gate], after[gate]))
        if ti.existing_digest(max_id) != digest:
            problems.append('изменилась хотя бы одна прежняя задача банка')
        hidden = Problem.objects.filter(id__in=created, status='draft',
                                        hidden_pending_review=True).count()
        if hidden != len(created):
            problems.append('не все новые задачи draft + hidden_pending_review')
        if problems:
            raise CommandError('ИНВАРИАНТ НАРУШЕН, запись откачена: ' +
                               '; '.join(problems))

    def _print(self, summary, report, before, after, apply):
        mode = 'ЗАПИСАНО' if apply else 'СУХОЙ ПРОГОН (в базе ничего не изменено)'
        self.stdout.write(self.style.SUCCESS(mode))
        for name, value in summary.items():
            self.stdout.write('  {:<58} {}'.format(name, value))
        self.stdout.write('До → после:')
        for name, value in before.items():
            self.stdout.write('  {:<12} {} → {}'.format(
                name, value, after.get(name, '—')))
        for name, value in sorted(report.counts.items()):
            self.stdout.write('  {:<30} {}'.format(name, value))

    def _preview(self, plan, path):
        """Пары «задание пакета → задача банка» глазами: случайные и края.

        Края — самое длинное и самое короткое решение, тест, задание с
        дописанным вступлением и почищенными критериями: ломается обычно там.
        """
        from problems.rendering import render_markdown
        groups = plan['new_groups']
        rng = random.Random(20261030)
        picked = rng.sample(groups, min(PREVIEW_SIZE - 6, len(groups)))
        edges = [
            max(groups, key=lambda g: len(g[0]['payload']['solution'])),
            min(groups, key=lambda g: len(g[0]['task']['statement_md'])),
            next((g for g in groups if g[0]['payload']['problem_type']), None),
            next((g for g in groups if g[0]['payload']['section_added']), None),
            next((g for g in groups if g[0]['payload']['criteria_rule']), None),
            next((g for g in groups if g[0]['payload']['figures']), None),
        ]
        rows = []
        for group in [g for g in edges if g] + picked:
            entry = group[0]
            task, payload = entry['task'], entry['payload']
            parts = ''.join('<li><b>{}</b> {} <i>{}</i></li>'.format(
                html.escape(p['label']), render_markdown(p['statement']),
                html.escape(p['answer'])) for p in payload['parts'])
            rows.append(
                '<section><h2>{ref}</h2><p class=m>позиций: {n} · тип: {kind} · '
                'критерии: {rule} · вступление дописано: {sec} · рисунков: {figs}</p>'
                '<div class=g><div><h3>Пакет (как есть)</h3><pre>{raw}</pre></div>'
                '<div><h3>Задача банка (как покажется)</h3>{st}<ol>{parts}</ol>'
                '<p><b>Ответ:</b> {ans}</p><h4>Решение</h4>{sol}</div></div></section>'
                .format(ref=html.escape(task['ref_key']), n=len(group),
                        kind=html.escape(payload['problem_type'] or 'не тест'),
                        rule=payload['criteria_rule'] or '—',
                        sec=payload['section_added'], figs=len(payload['figures']),
                        raw=html.escape(json.dumps(
                            {k: task.get(k) for k in (
                                'statement_md', 'section_md', 'parts', 'test',
                                'answer', 'solution_md', 'criteria_md')},
                            ensure_ascii=False, indent=1)),
                        st=render_markdown(payload['statement']), parts=parts,
                        ans=html.escape(payload['answer']),
                        sol=render_markdown(payload['solution'])))
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('<!doctype html><meta charset=utf-8><title>Задания пакета → банк'
                     '</title><style>body{font:14px system-ui;margin:16px}'
                     '.g{display:grid;grid-template-columns:1fr 1fr;gap:16px}'
                     'pre{white-space:pre-wrap;background:#f4f4f4;padding:8px;'
                     'max-height:600px;overflow:auto}.m{color:#666}'
                     'section{border-top:2px solid #ccc;margin-top:24px}</style>'
                     '<script>MathJax={tex:{inlineMath:[["$","$"]]}}</script>'
                     '<script src="https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js">'
                     '</script>' + ''.join(rows))
