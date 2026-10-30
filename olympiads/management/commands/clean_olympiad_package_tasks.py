"""Чистка грязи оцифровки в задачах, залитых из пакета олимпиад (S4, ADR 0172).

    manage.py clean_olympiad_package_tasks                 # сухой прогон
    manage.py clean_olympiad_package_tasks --only vseros
    manage.py clean_olympiad_package_tasks --apply         # снимок и запись

Три беды — A (условие дважды), B (ответ или решение внутри условия),
C (решение — копия условия). Правила и их границы — `olympiads/package_clean.py`.

⚠️ ПО УМОЛЧАНИЮ — СУХОЙ ПРОГОН. Запись — только с `--apply`, одной
транзакцией, и ТОЛЬКО в задачи, созданные заливкой S4, и в позиции
комплектов на них. Прежние задачи банка и задачи с непустым `human_review`
не меняются никогда: после записи это сверяется отпечатком (тем же
`existing_digest`, что у заливки S4). Любой нарушенный инвариант откатывает
транзакцию целиком. Задачи, позиции и комплекты команда не удаляет.

Перед `--apply` делается снимок базы (SQLite — копия файла рядом с базой);
без снимка запись не начинается. Повторный прогон — 0 изменений.
"""
import collections
import datetime
import html
import json
import os
import random
import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from olympiads import package_clean as pc
from olympiads import tasks_import as ti

PREVIEW_PER_BUG = 10
BUG_TITLES = {
    'A': 'A. Условие записано дважды: оставлена первая редакция',
    'B': 'B. Ответ или решение внутри условия: отрезано',
    'C': 'C. Решение — копия условия: копия убрана',
}


def counters():
    """То, что команда менять не смеет (число строк)."""
    from olympiads.models import (OlympiadVariant, OlympiadVariantFile,
                                  OlympiadVariantItem)
    from problems.models import Problem, ProblemFigure, ProblemPart
    return {
        'problems': Problem.objects.count(),
        'parts': ProblemPart.objects.count(),
        'figures': ProblemFigure.objects.count(),
        'variants': OlympiadVariant.objects.count(),
        'files': OlympiadVariantFile.objects.count(),
        'items': OlympiadVariantItem.objects.count(),
        **ti.catalog_counts(),
    }


def flag_totals():
    """Сколько позиций с «есть решение / критерии / эталон ответа» и «под вопросом»."""
    from olympiads.models import OlympiadVariantItem as Item
    qs = Item.objects.all()
    return {
        'есть решение': qs.filter(has_solution=True).count(),
        'есть критерии': qs.filter(has_criteria=True).count(),
        'есть эталон ответа': qs.filter(has_answer=True).count(),
        'под вопросом': qs.filter(quality=Item.Quality.FLAGGED).count(),
    }


def snapshot_database():
    """Копия базы перед записью. Только SQLite; путь — в вывод команды."""
    if connection.vendor != 'sqlite':
        raise CommandError('Снимок автоматически делается только для SQLite. '
                           'Сделайте дамп базы руками и повторите запуск.')
    name = str(connection.settings_dict['NAME'])
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    base, ext = os.path.splitext(name)
    target = '{}.before_clean_{}{}'.format(base, stamp, ext or '.sqlite3')
    source = sqlite3.connect(name)
    try:
        dest = sqlite3.connect(target)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    return target


class Command(BaseCommand):
    help = ('Чистка задач пакета олимпиад: условие дважды, ответ в условии, '
            'решение — копия условия. Без --apply — сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--only', default='',
                            help='Только одна олимпиада по слагу, например vseros.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Сухой прогон (по умолчанию и так он).')
        parser.add_argument('--apply', action='store_true',
                            help='Снимок и запись в базу.')
        parser.add_argument('--no-snapshot', action='store_true',
                            help='Не делать снимок (только для тестов).')
        parser.add_argument('--report-dir', default='',
                            help='Куда класть отчёт и предпросмотр (по умолчанию reports/).')

    # ── вычисление правок ────────────────────────────────────────────────

    def _changes(self, plan):
        """(правки задач, правки позиций, сводка). Базу не трогает."""
        from olympiads.models import OlympiadVariantItem as Item
        editable = [e for e in plan['problems']]
        item_rows = {i.pk: i for i in Item.objects.filter(
            pk__in=[pk for e in editable for pk in e['items']])}
        problem_edits, item_edits = [], []
        s = collections.Counter()
        solution_flag_change = collections.Counter()
        for e in editable:
            bugs = {(ev['bug'], ev['action']) for ev in e['events']}
            for bug, action in bugs:
                s[(bug, action)] += 1
            if ('B', 'fixed') in bugs:
                if e['detached']:
                    s['B_report_only'] += 1
                else:
                    s['B_to_solution'] += 1
            if ('C', 'fixed') in bugs:
                has_sol, _crit = pc.item_flags(e['solution_after'])
                if not has_sol:
                    s['C_empty'] += 1
            statement_changed = e['statement_after'] != e['statement_before']
            solution_changed = e['solution_after'] != e['solution_before']
            if statement_changed or solution_changed:
                problem_edits.append(e)
            has_sol, has_crit = pc.item_flags(e['solution_after'])
            for pk in e['items']:
                item = item_rows[pk]
                reasons = list(item.quality_reasons or [])
                new_reasons = reasons + [r for r in e['reasons'] if r not in reasons]
                edit = {'pk': pk, 'problem': e['id'],
                        'has_solution': (item.has_solution, has_sol),
                        'has_criteria': (item.has_criteria, has_crit),
                        'quality': (item.quality,
                                    'flagged' if (e['reasons'] or item.quality == 'flagged')
                                    else 'clean'),
                        'reasons': (reasons, new_reasons)}
                if (edit['has_solution'][0] != has_sol or edit['has_criteria'][0] != has_crit
                        or edit['quality'][0] != edit['quality'][1] or reasons != new_reasons):
                    item_edits.append(edit)
        return problem_edits, item_edits, s

    # ── основной ход ─────────────────────────────────────────────────────

    def handle(self, *args, **options):
        from olympiads.models import OlympiadVariantItem as Item
        from problems.corpus_converter.ingest import content_hash_for
        from problems.models import Problem

        if options['dry_run'] and options['apply']:
            raise CommandError('--dry-run и --apply вместе нельзя.')
        apply = options['apply']

        plan = pc.build_plan(options['only'])
        problem_edits, item_edits, s = self._changes(plan)
        editable_ids = pc.s4_problem_ids(options['only'])
        everything = pc.s4_problem_ids()
        # Всё, что ниже самой ранней задачи S4, — прежний банк; его отпечаток
        # обязан не измениться. Нет задач S4 — прежним считается весь банк.
        old_max = (min(everything) - 1 if everything
                   else Problem.objects.order_by('-id').values_list('id', flat=True).first() or 0)

        # Инварианты текста по плану: метки рисунков целы, парность не хуже.
        markers_lost = [e['id'] for e in plan['problems']
                        if set(pc.figure_markers(e['statement_before']))
                        - set(pc.figure_markers(e['statement_after']))]
        worse_text = [e['id'] for e in problem_edits
                      if pc.worse(e['statement_before'], e['statement_after'])
                      or pc.worse(e['solution_before'], e['solution_after'])]

        before_counters, before_flags = counters(), flag_totals()
        digest = ti.existing_digest(old_max)
        snapshot = ''

        if apply:
            if markers_lost or worse_text:
                raise CommandError('План нарушает инварианты (метки рисунков: {}, '
                                   'парность $ и {{}}: {}). Запись не начата.'
                                   .format(markers_lost[:10], worse_text[:10]))
            if not options['no_snapshot']:
                snapshot = snapshot_database()
                self.stdout.write('Снимок базы: {}'.format(snapshot))
            now = timezone.now()
            with transaction.atomic():
                for e in problem_edits:
                    fields = {'statement': e['statement_after'],
                              'solution': e['solution_after'], 'updated_at': now}
                    if e['statement_after'] != e['statement_before']:
                        fields['content_hash'] = content_hash_for(e['statement_after'])
                    Problem.objects.filter(pk=e['id'], pk__in=editable_ids).update(**fields)
                rows = {i.pk: i for i in Item.objects.filter(pk__in=[x['pk'] for x in item_edits])}
                for edit in item_edits:
                    item = rows[edit['pk']]
                    item.has_solution = edit['has_solution'][1]
                    item.has_criteria = edit['has_criteria'][1]
                    item.quality = edit['quality'][1]
                    item.quality_reasons = edit['reasons'][1]
                    item.updated_at = now
                Item.objects.bulk_update(
                    list(rows.values()), ['has_solution', 'has_criteria', 'quality',
                                          'quality_reasons', 'updated_at'], batch_size=500)
                after_counters, after_flags = counters(), flag_totals()
                self._check(before_counters, after_counters, before_flags, after_flags,
                            digest, old_max, plan, item_edits)
        else:
            after_counters, after_flags = before_counters, None
            after_flags = self._simulate_flags(before_flags, item_edits)

        self._print(plan, s, problem_edits, item_edits, before_counters,
                    after_counters, before_flags, after_flags, markers_lost,
                    worse_text, apply, snapshot)
        directory = options['report_dir'] or os.path.join(settings.BASE_DIR, 'reports')
        os.makedirs(directory, exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(directory, 'olympiads_clean_{}.json'.format(stamp))
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({
                'only': options['only'], 'applied': apply, 'snapshot': snapshot,
                'summary': {str(k): v for k, v in s.items()},
                'problems_changed': len(problem_edits), 'items_changed': len(item_edits),
                'counters_before': before_counters, 'counters_after': after_counters,
                'flags_before': before_flags, 'flags_after': after_flags,
                'legacy_found_not_touched': [
                    {'id': e['id'], 'events': [ev['bug'] + ':' + ev['action']
                                               for ev in e['events']]}
                    for e in plan['legacy']],
                'problems': [{
                    'id': e['id'], 'olympiads': e['olympiads'],
                    'bugs': sorted({ev['bug'] + ':' + ev['action'] for ev in e['events']}),
                    'reasons': e['reasons'],
                    'statement_before': e['statement_before'],
                    'statement_after': e['statement_after'],
                    'solution_before': e['solution_before'],
                    'solution_after': e['solution_after'],
                    'detached_in_report_only': e['detached'],
                    'events': e['events'],
                } for e in plan['problems']],
            }, fh, ensure_ascii=False, indent=1, default=str)
        self.stdout.write('Отчёт: {}'.format(path))
        preview = os.path.join(directory, 'olympiads_clean_preview_{}.html'.format(stamp))
        self._preview(plan, preview)
        self.stdout.write('Предпросмотр: {}'.format(preview))

    # ── вспомогательное ──────────────────────────────────────────────────

    @staticmethod
    def _simulate_flags(before, item_edits):
        """Что покажут флаги позиций после записи (сухой прогон)."""
        after = dict(before)
        for edit in item_edits:
            after['есть решение'] += int(edit['has_solution'][1]) - int(edit['has_solution'][0])
            after['есть критерии'] += int(edit['has_criteria'][1]) - int(edit['has_criteria'][0])
            after['под вопросом'] += int(edit['quality'][1] == 'flagged') - int(
                edit['quality'][0] == 'flagged')
        return after

    def _check(self, before, after, flags_before, flags_after, digest, old_max,
               plan, item_edits):
        """Инварианты записи. Нарушен любой — транзакция откатывается."""
        problems = []
        if before != after:
            problems.append('счётчики сдвинулись: {} → {}'.format(before, after))
        if ti.existing_digest(old_max) != digest:
            problems.append('изменилась хотя бы одна прежняя задача банка')
        if flags_after['есть эталон ответа'] != flags_before['есть эталон ответа']:
            problems.append('сдвинулся «есть эталон ответа»')
        expected = self._simulate_flags(flags_before, item_edits)
        if expected != flags_after:
            problems.append('флаги позиций не сошлись с планом: {} ≠ {}'.format(
                expected, flags_after))
        if problems:
            raise CommandError('ИНВАРИАНТ НАРУШЕН, запись откачена: ' + '; '.join(problems))

    def _print(self, plan, s, problem_edits, item_edits, before, after,
               flags_before, flags_after, markers_lost, worse_text, apply, snapshot):
        mode = 'ЗАПИСАНО' if apply else 'СУХОЙ ПРОГОН (в базе ничего не изменено)'
        self.stdout.write(self.style.SUCCESS(mode))
        out = self.stdout.write
        out('Задач S4 в проверке: {}; найдено: {}; прежних задач с находкой (не тронуты): {}'
            .format(plan['editable_total'], len(plan['problems']), len(plan['legacy'])))
        out('  A: починено {} / помечено {}'.format(s[('A', 'fixed')], s[('A', 'flagged')]))
        out('  B: починено {} / помечено {} / отрезанное ушло в решение {} / '
            'отрезанное только в отчёт {}'.format(
                s[('B', 'fixed')], s[('B', 'flagged')], s['B_to_solution'],
                s['B_report_only']))
        out('  C: починено {} / из них решение стало пустым {}'.format(
            s[('C', 'fixed')], s['C_empty']))
        newly = sum(1 for e in item_edits if e['quality'][0] != 'flagged'
                    and e['quality'][1] == 'flagged')
        extra = sum(1 for e in item_edits if e['quality'][0] == 'flagged'
                    and e['reasons'][0] != e['reasons'][1])
        out('  позиций, получивших «под вопросом»: {} (+{} получили новую причину)'
            .format(newly, extra))
        out('  задач с правкой текста: {}; позиций с правкой: {}'.format(
            len(problem_edits), len(item_edits)))
        for name in ('есть решение', 'есть критерии', 'есть эталон ответа', 'под вопросом'):
            out('  {:<20} {} → {}'.format(name, flags_before[name], flags_after[name]))
        out('  изменено прежних задач банка: {}'.format(
            len([e for e in problem_edits if not e['editable']])))
        out('  потеряно меток рисунков (задач): {}; хуже по $ и {{}}: {}'.format(
            len(markers_lost), len(worse_text)))
        reasons = collections.Counter(r for e in plan['problems'] for r in e['reasons'])
        out('Причины пометок (задач):')
        for reason, n in reasons.most_common():
            out('  {:<4} {}'.format(n, reason))
        out('Счётчики до: {}'.format(before))
        out('Счётчики после: {}'.format(after))

    def _preview(self, plan, path):
        """«До и после» глазами: по 10 случаев на беду + все пометки."""
        from problems.rendering import render_markdown
        rng = random.Random(20261030)

        def has(e, bug, action):
            return any(ev['bug'] == bug and ev['action'] == action for ev in e['events'])

        def block(title, entries, show_after=True):
            rows = []
            for e in entries:
                cols = ['<div><h3>До</h3>{}</div>'.format(
                    render_markdown(e['statement_before']))]
                if show_after:
                    cols.append('<div><h3>После</h3>{}</div>'.format(
                        render_markdown(e['statement_after'])))
                extra = ''
                if show_after and has(e, 'B', 'fixed'):
                    extra += ('<p class=m><b>Конец условия после (последние 400 знаков):'
                              '</b></p><pre>{}</pre>'.format(
                                  html.escape(e['statement_after'][-400:])))
                if e['solution_after'] != e['solution_before']:
                    extra = ('<div class=g><div><h4>Решение до</h4>{}</div>'
                             '<div><h4>Решение после</h4>{}</div></div>'.format(
                                 render_markdown(e['solution_before'][:3000]) or '<i>пусто</i>',
                                 render_markdown(e['solution_after'][:3000]) or '<i>пусто</i>'))
                if e['detached']:
                    extra += ('<p class=m><b>Отрезанное (ушло только в отчёт, у задачи '
                              'есть настоящее решение):</b></p><pre>{}</pre>'.format(
                                  html.escape(e['detached'][:3000])))
                reasons = '; '.join(e['reasons']) or '—'
                rows.append(
                    '<section><h2>№ {id}</h2><p class=m>{olymp} · причина пометки: {why}</p>'
                    '<div class=g>{cols}</div>{extra}</section>'.format(
                        id=e['id'], olymp=html.escape(', '.join(e['olympiads'])),
                        why=html.escape(reasons), cols=''.join(cols), extra=extra))
            return '<h1>{} ({})</h1>{}'.format(html.escape(title), len(entries), ''.join(rows))

        parts = []
        for bug in 'ABC':
            fixed = [e for e in plan['problems'] if has(e, bug, 'fixed')]
            sample = rng.sample(fixed, min(PREVIEW_PER_BUG, len(fixed)))
            edges = []
            if fixed:
                edges = [max(fixed, key=lambda e: len(e['statement_before'])),
                         min(fixed, key=lambda e: len(e['statement_before']))]
            picked = list({e['id']: e for e in sample + edges}.values())
            parts.append(block('{} — {} из {}'.format(BUG_TITLES[bug], len(picked), len(fixed)),
                               picked))
        residual = [e for e in plan['problems'] if pc.REASON_RESIDUAL in e['reasons']]
        parts.append('<h1>Детектор «в условии осталось решение»: {} задач, 10 примеров</h1>'
                     .format(len(residual)) + ''.join(
                         '<section><h2>№ {}</h2><p class=m>последние 400 знаков условия</p>'
                         '<pre>{}</pre></section>'.format(
                             e['id'], html.escape(e['statement_after'][-400:]))
                         for e in rng.sample(residual, min(10, len(residual)))))
        flagged = [e for e in plan['problems'] if e['reasons']]
        parts.append(block('Не починено, позиция «под вопросом» — все случаи', flagged,
                           show_after=False))
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('<!doctype html><meta charset=utf-8><title>Чистка задач пакета: до и после'
                     '</title><style>body{font:14px system-ui;margin:16px}'
                     '.g{display:grid;grid-template-columns:1fr 1fr;gap:16px}'
                     'pre{white-space:pre-wrap;background:#f4f4f4;padding:8px;'
                     'max-height:400px;overflow:auto}.m{color:#666}'
                     'section{border-top:2px solid #ccc;margin-top:24px}'
                     'h1{margin-top:48px;border-top:4px solid #333;padding-top:12px}</style>'
                     '<script>MathJax={tex:{inlineMath:[["$","$"]]}}</script>'
                     '<script src="https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js">'
                     '</script>' + ''.join(parts))
