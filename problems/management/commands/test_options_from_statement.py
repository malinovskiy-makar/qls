# -*- coding: utf-8 -*-
"""`test_options_from_statement` — варианты теста из текста условия в подпункты.

Решение владельца 15.09.2026 (Notion «Решения»): у тестов без подпунктов
варианты вписаны в хвост условия текстом, и виджет теста в каталоге и в игре
их не видит. Команда переносит варианты в `ProblemPart` и вырезает блок из
условия — данные становятся такими же, как у живых виджетов.

Порядок работы (правила `weco-content-integrity`):
* по умолчанию СУХОЙ ПРОГОН: счётчики по причинам, `REPORT.md` и
  `preview.html` с парами «было / стало», база не меняется;
* `--apply` — одной транзакцией; снимок `snapshot_<время>.json` ложится на
  диск ДО фиксации; инварианты — задач столько же, подпунктов ровно на
  созданное больше, у каждой применённой задачи собирается виджет
  (`catalog.testplay.game_of`); нарушен любой — откат всей транзакции;
* `--revert <снимок>` возвращает условие побайтно и удаляет ровно созданные
  подпункты; что с тех пор правили руками — не трогает и называет;
* повторный `--apply` кандидатов не находит: у применённых подпункты есть.

Что пишется: подпункты (`label`, `statement` = текст варианта, `answer` =
«верно» у верных и пусто у остальных, `order` с нуля, `points` пусто) и
`statement` = условие без блока — только у `single`/`multi`. У «верно/неверно»
условие не меняется, подпункты — «а» Верно, «б» Неверно, как у живых.

⚠️ ВЕРНЫЕ ОТМЕЧАЮТСЯ В ПОДПУНКТАХ, А НЕ В `Problem.answer`. Ответ трогать
нельзя, а у большинства одиночных он хранит строку варианта целиком
(«2. (b) Центральный банк…»), которую `label_set` не разберёт. Разметка
подпунктов у `answer_check.catalog_test_correct_labels` главнее ответа.
⚠️ `content_hash` НЕ пересчитывается: это отпечаток условия ИСТОЧНИКА для
дедупликации при повторном импорте.
⚠️ Эмбеддинги переписанных условий устаревают — их подхватит
`build_embeddings --stale`; команда их не трогает.
⚠️ `answer`, `solution`, `status`, `human_review`, `content_status` не трогаются.

Запуск:
    manage.py test_options_from_statement                        # сухой прогон
    manage.py test_options_from_statement --apply
    manage.py test_options_from_statement --revert reports/night_20260915/test_options/snapshot_<время>.json
"""
import html
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from catalog import testplay
from problems import problem_types
from problems.models import Problem, ProblemPart
from problems.test_options_parse import (
    BOOLEAN_PARTS, boolean_correct_label, correct_labels, formula_worse,
    parse_with_reason,
)

DEFAULT_IDS = 'reports/corpus_transfer_20260913/dead_test_widget_ids.txt'
DEFAULT_REPORT = 'reports/night_20260915/test_options'
KINDS = (problem_types.SINGLE, problem_types.MULTI, problem_types.BOOLEAN)
REASONS = ('parsed', 'boolean_synthetic', 'no_block', 'mixed_style',
           'verb_like_subquestion', 'empty_stem', 'answer_mismatch',
           'single_multi_correct', 'formula_balance')
CORRECT = 'верно'
EXAMPLES = 20
EDGES = 5
SEED = 20260915
#: `filter(pk__in=…)` с тысячами значений роняет SQLite — читаем порциями.
ID_CHUNK = 900


def read_ids(path):
    """id из файла вида «id<TAB>причина»; строки с «#» — шапка."""
    with open(path, encoding='utf-8') as handle:
        return [int(line.split('\t')[0]) for line in handle
                if line.strip() and not line.startswith('#')]


def plan_for(problem, kind):
    """(план, причина) или (None, причина отказа).

    План: `stem` — новое условие (None — условие не меняется), `parts` —
    [(метка, текст, ответ)], `correct` — верные метки.
    """
    if kind == problem_types.BOOLEAN:
        label = boolean_correct_label(problem.answer, problem.statement)
        if label is None:
            return None, 'answer_mismatch'
        parts = [(key, text, CORRECT if key == label else '')
                 for key, text in BOOLEAN_PARTS]
        return {'stem': None, 'parts': parts, 'correct': [label]}, 'boolean_synthetic'
    parsed, reason = parse_with_reason(problem.statement)
    if parsed is None:
        return None, reason
    correct = correct_labels(problem.answer, parsed)
    if not correct:
        return None, 'answer_mismatch'
    if kind == problem_types.SINGLE and len(correct) != 1:
        return None, 'single_multi_correct'
    if (formula_worse(problem.statement, parsed.stem)
            or any(formula_worse('', text) for _label, text in parsed.options)):
        return None, 'formula_balance'
    parts = [(label, text, CORRECT if label in correct else '')
             for label, text in parsed.options]
    return {'stem': parsed.stem, 'parts': parts, 'correct': sorted(correct)}, 'parsed'


class Command(BaseCommand):
    help = ('Варианты теста из текста условия — в подпункты (по умолчанию сухой '
            'прогон с отчётом; --apply пишет со снимком; --revert откатывает).')

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--dry-run', action='store_true',
                          help='Только счётчики и отчёт (так и по умолчанию).')
        mode.add_argument('--apply', action='store_true',
                          help='Записать одной транзакцией со снимком.')
        mode.add_argument('--revert', metavar='SNAPSHOT',
                          help='Откатить по снимку прошлого --apply.')
        parser.add_argument('--ids-file', default=DEFAULT_IDS,
                            help='Файл id кандидатов (по умолчанию %(default)s); '
                                 'объём сверяется с базой заново.')
        parser.add_argument('--limit', type=int, default=0,
                            help='Не больше N кандидатов (0 — все).')
        parser.add_argument('--report', default=DEFAULT_REPORT,
                            help='Куда писать отчёт и снимок (%(default)s).')

    def handle(self, *args, **options):
        if options['revert']:
            return self._revert(Path(options['revert']))
        report_dir = Path(options['report'])
        report_dir.mkdir(parents=True, exist_ok=True)
        ids = read_ids(options['ids_file'])
        plans, reasons, kinds, rejected = [], Counter(), Counter(), defaultdict(list)
        for problem, kind in self._candidates(ids, options['limit']):
            kinds[kind] += 1
            plan, reason = plan_for(problem, kind)
            reasons[reason] += 1
            if plan is None:
                rejected[reason].append(problem.pk)
                continue
            plan.update(id=problem.pk, kind=kind, statement=problem.statement,
                        answer=problem.answer or '')
            plans.append(plan)
        plans.sort(key=lambda plan: plan['id'])

        self.stdout.write('Файл id: %s — строк %d; кандидатов (тест без подпунктов): %d %s'
                          % (options['ids_file'], len(ids), sum(kinds.values()),
                             dict(kinds)))
        for reason in REASONS:
            self.stdout.write('   %-24s %d' % (reason, reasons.get(reason, 0)))
        self.stdout.write('   к записи: задач %d, подпунктов %d, условий переписать %d'
                          % (len(plans), sum(len(p['parts']) for p in plans),
                             sum(1 for p in plans if p['stem'] is not None)))
        snapshot = self._apply(plans, report_dir) if options['apply'] and plans else None
        self._report(report_dir, ids, kinds, reasons, plans, rejected, options, snapshot)
        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                'Сухой прогон: база не менялась. Отчёт: %s' % (report_dir / 'REPORT.md')))
        return None

    def _candidates(self, ids, limit):
        """(задача, вид) — тесты single/multi/boolean из файла без подпунктов."""
        found = 0
        for start in range(0, len(ids), ID_CHUNK):
            chunk = (Problem.objects.filter(pk__in=ids[start:start + ID_CHUNK])
                     .annotate(parts_count=Count('parts')).filter(parts_count=0)
                     .only('id', 'problem_type', 'statement', 'answer')
                     .order_by('pk'))
            for problem in chunk:
                kind = problem_types.test_kind(problem.problem_type)
                if kind not in KINDS:
                    continue
                yield problem, kind
                found += 1
                if limit and found >= limit:
                    return

    def _apply(self, plans, report_dir):
        path = report_dir / ('snapshot_%s.json' % timezone.now().strftime('%Y%m%d_%H%M%S'))
        problems_before = Problem.objects.count()
        parts_before = ProblemPart.objects.count()
        created_total = sum(len(plan['parts']) for plan in plans)
        try:
            with transaction.atomic():
                snapshot = {}
                for plan in plans:
                    created = []
                    for order, (label, text, answer) in enumerate(plan['parts']):
                        part = ProblemPart.objects.create(
                            problem_id=plan['id'], label=label, statement=text,
                            answer=answer, order=order)
                        created.append({'id': part.pk, 'label': label, 'statement': text,
                                        'answer': answer, 'order': order})
                    if plan['stem'] is not None:
                        Problem.objects.filter(pk=plan['id']).update(statement=plan['stem'])
                    snapshot[str(plan['id'])] = {
                        'statement_before': plan['statement'],
                        'statement_after': (plan['statement'] if plan['stem'] is None
                                            else plan['stem']),
                        'part_ids': [row['id'] for row in created],
                        'parts': created,
                    }
                # ⚠️ Снимок ложится на диск ДО фиксации: не записался файл —
                # откатится и база. Применения без снимка не бывает.
                path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1),
                                encoding='utf-8')
                self._check_invariants(plans, problems_before,
                                       parts_before + created_total)
        except Exception:
            if path.exists():
                path.rename(path.with_name(path.stem + '_rolled_back.json'))
            raise
        self.stdout.write('   задач в базе: было %d, стало %d; подпунктов: было %d, стало %d'
                          % (problems_before, Problem.objects.count(), parts_before,
                             ProblemPart.objects.count()))
        self.stdout.write(self.style.SUCCESS(
            'Записано: задач %d, подпунктов %d, условий переписано %d. Снимок: %s'
            % (len(plans), created_total, sum(1 for p in plans if p['stem'] is not None),
               path)))
        return path

    def _check_invariants(self, plans, problems_expected, parts_expected):
        problems_now, parts_now = Problem.objects.count(), ProblemPart.objects.count()
        if problems_now != problems_expected or parts_now != parts_expected:
            raise CommandError(
                'ИНВАРИАНТ: задач %d (ждали %d), подпунктов %d (ждали %d) — '
                'транзакция отменена.' % (problems_now, problems_expected, parts_now,
                                          parts_expected))
        dead = [plan['id'] for plan in plans if testplay.game_of(
            Problem.objects.prefetch_related('parts').get(pk=plan['id'])) is None]
        if dead:
            raise CommandError(
                'ИНВАРИАНТ: виджет теста не собрался у %d задач (%s) — транзакция '
                'отменена.' % (len(dead), dead[:20]))

    def _revert(self, path):
        data = json.loads(path.read_text(encoding='utf-8'))
        restored = deleted = 0
        edited_parts, edited_statements, missing = [], [], []
        with transaction.atomic():
            for key, entry in data.items():
                pk = int(key)
                for row in entry['parts']:
                    part = ProblemPart.objects.filter(pk=row['id'], problem_id=pk).first()
                    if part is None:
                        missing.append(row['id'])
                        continue
                    if (part.label, part.statement, part.answer, part.order) != (
                            row['label'], row['statement'], row['answer'], row['order']):
                        edited_parts.append(row['id'])
                        continue
                    part.delete()
                    deleted += 1
                current = (Problem.objects.filter(pk=pk)
                           .values_list('statement', flat=True).first())
                if current is None or current == entry['statement_before']:
                    continue
                # ⚠️ Условие правили после --apply: не затираем чужую правку.
                if current != entry['statement_after']:
                    edited_statements.append(pk)
                    continue
                Problem.objects.filter(pk=pk).update(statement=entry['statement_before'])
                restored += 1
        self.stdout.write('Откат по %s: задач в снимке %d' % (path, len(data)))
        self.stdout.write('   условий возвращено: %d; подпунктов удалено: %d'
                          % (restored, deleted))
        self.stdout.write('   подпункты правили после записи — оставлены: %s' % edited_parts)
        self.stdout.write('   условия правили после записи — оставлены: %s' % edited_statements)
        self.stdout.write('   подпунктов из снимка уже нет: %s' % missing[:50])
        return None

    def _report(self, report_dir, ids, kinds, reasons, plans, rejected, options, snapshot):
        mode = 'запись' if options['apply'] else 'сухой прогон'
        rewritten = [plan for plan in plans if plan['stem'] is not None]
        lines = ['# Варианты теста из условия — отчёт (%s, %s)'
                 % (mode, timezone.localtime().strftime('%d.%m.%Y %H:%M')), '',
                 'Файл id: `%s` — строк %d. Кандидатов по базе (тест single/multi/'
                 'boolean без подпунктов): %d — %s.'
                 % (options['ids_file'], len(ids), sum(kinds.values()), dict(kinds))]
        if options['limit']:
            lines.append('⚠️ Охват ограничен `--limit %d`.' % options['limit'])
        lines += ['', '## Причины', '', '| причина | задач |', '|---|---:|']
        lines += ['| `%s` | %d |' % (reason, reasons.get(reason, 0)) for reason in REASONS]
        lines += ['', 'К записи: задач %d, подпунктов %d, условий переписать %d.'
                  % (len(plans), sum(len(p['parts']) for p in plans), len(rewritten))]
        if snapshot:
            lines += ['', '**Записано.** Снимок для отката: `%s`' % snapshot]
        lines += ['', '## Число вариантов (single/multi)', '']
        lines += ['- %d: %d задач' % item
                  for item in sorted(Counter(len(p['parts']) for p in rewritten).items())]
        sample = random.Random(SEED).sample(plans, min(EXAMPLES, len(plans)))
        by_cut = sorted(rewritten, key=lambda p: len(p['statement']) - len(p['stem']))
        edges = by_cut if len(by_cut) <= 2 * EDGES else by_cut[:EDGES] + by_cut[-EDGES:]
        lines += ['', '## %d случайных примеров' % len(sample), '']
        for plan in sample:
            lines += _example(plan)
        lines += ['## Края: самые короткие и самые длинные вырезанные блоки', '']
        for plan in edges:
            lines += _example(plan)
        lines += ['## Отклонённые id (первые 50 по причине)', '']
        lines += ['- `%s` (%d): %s' % (reason, len(pks), ', '.join(map(str, pks[:50])))
                  for reason, pks in sorted(rejected.items())]
        (report_dir / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        (report_dir / 'preview.html').write_text(_preview_html(sample, edges),
                                                 encoding='utf-8')


def _example(plan):
    after = plan['stem'] if plan['stem'] is not None else '(условие не меняется)'
    rows = ['### Задача %d — %s' % (plan['id'], plan['kind']), '', 'Было:', '', '```',
            plan['statement'], '```', '', 'Стало:', '', '```', after, '```', '',
            'Подпункты:', '']
    rows += ['- `%s` %s%s' % (label, text, ' — **верный**' if answer == CORRECT else '')
             for label, text, answer in plan['parts']]
    rows += ['', 'Ответ задачи (не меняется): `%s`' % plan['answer'].replace('\n', ' / '), '']
    return rows


def _preview_html(sample, edges):
    def card(plan):
        after = plan['stem'] if plan['stem'] is not None else '(условие не меняется)'
        parts = ''.join('<li%s>%s) %s</li>' % (' class="ok"' if answer == CORRECT else '',
                                               html.escape(label), html.escape(text))
                        for label, text, answer in plan['parts'])
        return ('<section><h3>Задача %d — %s</h3><div class="pair"><pre>%s</pre>'
                '<pre>%s</pre></div><ol>%s</ol><p>Ответ задачи: %s</p></section>'
                % (plan['id'], plan['kind'], html.escape(plan['statement']),
                   html.escape(after), parts, html.escape(plan['answer'])))

    style = ('body{font:14px/1.45 system-ui,sans-serif;margin:24px;max-width:1200px}'
             'pre{white-space:pre-wrap;background:WhiteSmoke;padding:8px;margin:0}'
             '.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}'
             'ol{list-style:none;padding:0}.ok{font-weight:700}')
    return ('<!doctype html><meta charset="utf-8"><title>Варианты теста: было и стало'
            '</title><style>%s</style><h1>Варианты теста из условия: было / стало</h1>'
            '<h2>Случайные примеры</h2>%s<h2>Края</h2>%s'
            % (style, ''.join(map(card, sample)), ''.join(map(card, edges))))
