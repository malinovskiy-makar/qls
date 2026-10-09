# -*- coding: utf-8 -*-
"""Запись итогов аудита олимпиады по официальному эталону (ВП, МОШ, …).

Олимпиада задаётся ЯВНО: `--olympiad vp|mosh|…` (реестр
`problems/olympiad_audit/registry.py`: название строк, официальный
`Source`, этапы, папка журналов). Без флага — отказ.

Читает файлы сверки аудита (docs/OLYMPIAD_AUDIT.md) и пишет в базу
ТОЛЬКО то, что владелец утвердил на стоп-гейте:

    --new-refs proposed_new_refs.csv --tier auto
        новые строки OlympiadRef (source_site='official'), метод
        text_fuzzy_numeric, без проверки человеком;
    --new-refs review_queue.csv --tier high --confirmed-by claude_review.md
        только «высокий» ярус И только пары из таблицы подтверждений:
        метод manual, reviewed_by_human=True;
    --update-existing proposed_updates_existing.csv --confirmed-by … [--include-eyeball]
        правки существующих строк ВП: этап, класс, ссылка на PDF, номер,
        слаг финграмотности, правило близнецов;
    --import import_queue_vp.jsonl [--figures-dir DIR]
        недостающие задания эталона как новые скрытые задачи;
    --delete-refs ID,ID
        снять ошибочные строки этой олимпиады (полная копия строки — в
        журнале, `--rollback` возвращает её с тем же id);
    --rollback <журнал.json>
        вернуть всё, что записал прогон с этим журналом.

Флаги МОШ (многоэтапной олимпиады): `--stage-from catalog_vs_official.csv`
— пустой этап заполняется только у комплектов агрегатора с доказанным
этапом (`stage_established` без «?»); `--renumber-by-containment` —
сомнительные перенумеровки из файла проверки применяются, только если
текст банка входит в задание под новым номером (≥ 0,90) и не входит под
текущим; `--text-check existing_refs_text_check.csv` — откуда брать
найденный комплект для правила близнецов, если в CSV правок нет причины.

По умолчанию — СУХОЙ ПРОГОН: план, таблица «создать / обновить /
пропустить, почему» и журнал с суффиксом `_dryrun`. Запись — только
`--apply --yes-i-have-owner-approval` вместе.

Каждый `--apply` пишет журнал `session3/apply_<время>_<режим>.json`:
id созданных строк и [{id, field, old, new}] по каждой правке — по нему
`--rollback` возвращает базу до единицы.

⚠️ НОМЕР SOLVEHUB — НЕ ОФИЦИАЛЬНЫЙ НОМЕР (позиция в их списке). Старый
номер при перенумерации уходит в `raw_meta['aggregator_number']`, старая
ссылка агрегатора — в `raw_meta['aggregator_url']`.

⚠️ БЛИЗНЕЦЫ. Одно задание часто дают двум соседним классам. Строка, чей
текст совпал с комплектом ДРУГОГО класса, не ошибка, если то же задание
(сходство ≥ 0,90) есть и в комплекте её класса — тогда класс остаётся,
дописываются номер и ссылка своего PDF. Иначе класс исправляется на
найденный.

Защиты: строка с той же парой (задача, event_id) не создаётся; если у
задачи уже есть строка ВП того же года и класса — она обновляется
(ссылка, номер), вторая не заводится; задача со строкой другой олимпиады
и другого года не трогается. Существующие statement / answer / solution
не меняются никогда (ADR 0005).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from problems.corpus_converter.ingest import create_problem
from problems.models import (
    OlympiadRef, Problem, ProblemFigure, ProblemPart, Source, SourceReference,
)
from problems.olympiad_audit import registry
from problems.olympiad_grades import parse_grades
from problems.olympiad_official import (
    OLYMPIAD_NAMES, TWIN_THRESHOLD, Reference, bank_academic_year,
    bank_norm_text, clean_pdf_task, containment, formula_suspect,
    markup_free_key, parse_claude_review, parse_other_event_reason, read_csv,
    read_jsonl, variant_of,
)
from problems.text_dedup import fuzzy_ratio, problem_identity_text

APPROVAL_FLAG = '--yes-i-have-owner-approval'
EXAMPLES = 10
#: Человеческие названия этапов для привязки к источнику при импорте.
STAGE_LABELS = {'final': 'Заключительный этап', 'qualifying': 'Отборочный этап'}
#: Поля строки OlympiadRef, которые копируются в журнал при снятии строки.
_REF_FIELDS = [f.attname for f in OlympiadRef._meta.concrete_fields]


def _grades_overlap(a, b):
    """Пустой класс считается «тем же»: строка без класса — та же
    встреча с туром, только недописанная."""
    if not a or not b:
        return True
    return bool(parse_grades(a) & parse_grades(b))


def _counts():
    refs = OlympiadRef.objects
    return {
        'Problem': Problem.objects.count(),
        'ProblemPart': ProblemPart.objects.count(),
        'SourceReference': SourceReference.objects.count(),
        'ProblemFigure': ProblemFigure.objects.count(),
        'OlympiadRef': refs.count(),
        'OlympiadRef(vp)': refs.filter(olympiad_slug='vp').count(),
        'OlympiadRef(official)': refs.filter(source_site='official').count(),
        'OlympiadRef(vp-fingram)': refs.filter(olympiad_slug='vp-fingram').count(),
        'OlympiadRef(mosh)': refs.filter(olympiad_slug='mosh').count(),
    }


class Plan:
    """Что команда собирается сделать: создать, обновить, пропустить."""

    def __init__(self):
        self.creates = []                 # dict полей новой OlympiadRef
        self.updates = {}                 # ref_id -> {field: new}
        self.update_kinds = Counter()     # вид правки -> число строк
        self.update_examples = defaultdict(list)
        self.imports = []                 # подготовленные задания
        self.deletes = []                 # строки OlympiadRef под снятие
        self.skips = []                   # (ключ, причина)
        self.notes = []                   # строки для отчёта
        self.stage_counts = Counter()     # этап: поставлен / нет доказательства

    def update(self, ref, field, new, kind):
        if getattr(ref, field) == new:
            return False
        self.updates.setdefault(ref.id, {})[field] = new
        self.update_kinds[kind] += 1
        if len(self.update_examples[kind]) < EXAMPLES:
            self.update_examples[kind].append(
                f'ref {ref.id} (задача {ref.problem_id}) {field}: '
                f'{getattr(ref, field)!r} → {new!r}')
        return True

    def skip(self, key, reason):
        self.skips.append((key, reason))


class Command(BaseCommand):
    help = ('Записать итоги аудита олимпиады по официальному эталону. '
            'По умолчанию сухой прогон; запись — --apply '
            f'{APPROVAL_FLAG}.')

    def add_arguments(self, parser):
        parser.add_argument('--olympiad', choices=sorted(registry.REGISTRY),
                            help='Слаг олимпиады из реестра аудита (обязателен).')
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument('--new-refs', metavar='CSV')
        mode.add_argument('--update-existing', metavar='CSV')
        mode.add_argument('--import', dest='import_queue', metavar='JSONL')
        mode.add_argument('--delete-refs', metavar='ID,ID',
                          help='Снять строки OlympiadRef этой олимпиады (копия — в журнале).')
        mode.add_argument('--rollback', metavar='JOURNAL')
        parser.add_argument('--stage-from', metavar='CSV',
                            help='catalog_vs_official.csv: пустой этап — только у '
                                 'комплектов с доказанным этапом.')
        parser.add_argument('--renumber-by-containment', action='store_true',
                            help='Сомнительные перенумеровки — только при вхождении '
                                 'текста под новым номером (≥ 0,90) и не под текущим.')
        parser.add_argument('--text-check', metavar='CSV',
                            help='existing_refs_text_check.csv: найденный комплект '
                                 'для близнецов; по умолчанию — рядом с входным файлом.')
        parser.add_argument('--tier', choices=['auto', 'high'])
        parser.add_argument('--confirmed-by', metavar='MD',
                            help='Файл проверки Claude (claude_review_*.md).')
        parser.add_argument('--include-eyeball', action='store_true',
                            help='Применить и перенумеровки «на глаза».')
        parser.add_argument('--twin-pdf-to-pdf', action='store_true',
                            help='Близнец, если задание своего класса похоже '
                                 '(≥ 0,90) на найденное задание соседнего — '
                                 'сравниваются два PDF между собой, а не '
                                 'текст банка с PDF.')
        parser.add_argument('--assume-updates', metavar='JOURNAL', nargs='+',
                            help='Только сухой прогон импорта: считать новые '
                                 'строки и правки из журналов сухих прогонов '
                                 '--new-refs / --update-existing уже записанными.')
        parser.add_argument('--reference', metavar='JSONL',
                            help='Эталон (reference_problems_full.jsonl); по '
                                 'умолчанию — рядом с входным файлом.')
        parser.add_argument('--figures-dir', metavar='DIR',
                            help='Вырезанные картинки <event_id>_<номер>.png.')
        parser.add_argument('--out-dir', metavar='DIR',
                            help='Куда писать журналы; по умолчанию session3 '
                                 'рядом с папкой входного файла.')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument(APPROVAL_FLAG, dest='approved', action='store_true',
                            help='Подтверждение, что владелец сказал «да».')

    # ── Вход ────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        self.options = options
        self.apply = options['apply']
        if not options.get('olympiad'):
            raise CommandError(
                '--olympiad <слаг> обязателен (vp, mosh, …): название строк, '
                'Source и этапы берутся из реестра аудита. Ничего не сделано.')
        self.olympiad = registry.get(options['olympiad'])
        if self.apply and not options['approved']:
            raise CommandError(
                f'--apply пишет в боевые таблицы и требует {APPROVAL_FLAG} '
                '(владелец сказал «да» на стоп-гейте). Ничего не записано.')
        if options['rollback']:
            return self._rollback(options['rollback'])
        if options['delete_refs']:
            return self._delete_refs(options['delete_refs'])

        source_file = (options['new_refs'] or options['update_existing']
                       or options['import_queue'])
        if not os.path.isfile(source_file):
            raise CommandError(f'Нет файла: {source_file}')
        self.input_dir = os.path.dirname(os.path.abspath(source_file))
        self.out_dir = options['out_dir'] or os.path.join(
            os.path.dirname(self.input_dir), self.olympiad.journal_dir)
        os.makedirs(self.out_dir, exist_ok=True)
        ref_path = options['reference'] or os.path.join(
            self.input_dir, 'reference_problems_full.jsonl')
        if not os.path.isfile(ref_path):
            raise CommandError(f'Нет эталона: {ref_path} (--reference)')
        self.reference = Reference.load(ref_path)
        self._ref_keys = {}
        self.stage_evidence = (_read_stage_evidence(options['stage_from'],
                                                    self.olympiad.stages)
                               if options['stage_from'] else None)

        plan = Plan()
        if options['new_refs']:
            if not options['tier']:
                raise CommandError('--new-refs требует --tier auto|high')
            self.mode = f'new_refs_{options["tier"]}'
            self._plan_new_refs(plan, options['new_refs'], options['tier'])
        elif options['update_existing']:
            self.mode = 'update_existing'
            self._plan_updates(plan, options['update_existing'])
        else:
            self.mode = 'import'
            self._plan_import(plan, options['import_queue'])

        self._check_invariants(plan)
        self._print_plan(plan)
        self.inputs = {'olympiad': self.olympiad.slug,
                       'file': os.path.abspath(source_file),
                       'reference': os.path.abspath(ref_path),
                       'confirmed_by': options['confirmed_by'] or '',
                       'include_eyeball': options['include_eyeball'],
                       'stage_from': options['stage_from'] or '',
                       'renumber_by_containment': options['renumber_by_containment'],
                       'twin_pdf_to_pdf': options['twin_pdf_to_pdf']}
        if not self.apply:
            self._write_journal(plan, applied=False)
            self.stdout.write(self.style.WARNING(
                'СУХОЙ ПРОГОН — в базе ничего не изменено.'))
            return
        if self.new_duplicates:
            raise CommandError(
                f'План даёт {len(self.new_duplicates)} задач с двумя строками на один '
                'официальный комплект — запись запрещена. Ничего не записано.')
        self._apply(plan)

    # ── Новые привязки ──────────────────────────────────────────────────

    def _new_ref_rows(self, path, tier):
        rows = read_csv(path)
        session = self.olympiad.session
        if tier == 'auto':
            for row in rows:
                variant = row.get('task_variant') or ''
                meta = {'session': session,
                        'fuzzy': float(row['match_score']),
                        'margin': float(row['margin_vs_other_ref']),
                        'reference_number': row['number']}
                if variant:
                    meta['task_variant'] = variant
                yield {
                    'problem_id': int(row['problem_id']),
                    'event_id': row['event_id'], 'number': row['number'],
                    'task_variant': variant, 'raw_meta': meta,
                    'match_method': 'text_fuzzy_numeric',
                    'match_score': float(row['match_score']),
                    'reviewed_by_human': False,
                }
            return
        if not self.options['confirmed_by']:
            raise CommandError('--tier high требует --confirmed-by <файл проверки>')
        review = parse_claude_review(self.options['confirmed_by'])
        self.stdout.write(f'Подтверждено в файле проверки: {len(review.high)} пар; '
                          f'на глаза (не пишутся): {len(review.high_eyeball)}')
        for row in rows:
            if not row['review_tier'].startswith('высокий'):
                continue
            pid = int(row['problem_id'])
            variant = row.get('task_variant') or ''
            key = (pid, row['ref_event_id'], row['ref_number'], variant)
            if key not in review.high:
                yield {'problem_id': pid, 'task_variant': variant,
                       'unconfirmed': ('на глаза в файле проверки'
                                       if key in review.high_eyeball else
                                       'нет в таблице подтверждений файла проверки'),
                       'event_id': row['ref_event_id'],
                       'number': row['ref_number']}
                continue
            meta = {'session': session,
                    'fuzzy': float(row['fuzzy']),
                    'margin': float(row['margin']),
                    'reference_number': row['ref_number'],
                    'reviewed_by': self.olympiad.reviewed_by}
            if variant:
                meta['task_variant'] = variant
            yield {
                'problem_id': pid,
                'event_id': row['ref_event_id'], 'number': row['ref_number'],
                'task_variant': variant, 'raw_meta': meta,
                'match_method': 'manual',
                'match_score': float(row['fuzzy']),
                'reviewed_by_human': True,
                'is_test': row.get('is_test') == 'True',
            }

    def _same_tour(self, ref, year, grade, stage):
        """Строка этой олимпиады того же тура: год, класс (пустой — «тот
        же»), а у многоэтапной олимпиады ещё и этап (пустой — «тот же»)."""
        if ref.olympiad_slug not in self.olympiad.family or ref.year != year:
            return False
        if not _grades_overlap(ref.grade, grade):
            return False
        return not self.olympiad.multi_stage or ref.stage in ('', stage)

    def _plan_new_refs(self, plan, path, tier):
        rows = list(self._new_ref_rows(path, tier))
        pids = {r['problem_id'] for r in rows}
        existing = defaultdict(list)
        for ref in OlympiadRef.objects.filter(problem_id__in=pids):
            existing[ref.problem_id].append(ref)
        problems = set(Problem.objects.filter(pk__in=pids).values_list('pk', flat=True))
        family, slug = self.olympiad.family, self.olympiad.slug
        seen = set()
        self.tests_written = 0
        for row in rows:
            pid, event_id, number = row['problem_id'], row['event_id'], row['number']
            variant = row.get('task_variant') or ''
            key = f'{pid}/{event_id}#{number}' + (f'/{variant}' if variant else '')
            if row.get('unconfirmed'):
                plan.skip(key, row['unconfirmed'])
                continue
            task = self.reference.task(event_id, number, variant)
            if task is None:
                plan.skip(key, 'задания нет в эталоне')
                continue
            if pid not in problems:
                plan.skip(key, 'задачи нет в базе')
                continue
            if (pid, event_id) in seen or any(
                    r.event_id == event_id
                    or (r.raw_meta or {}).get('official_event_id') == event_id
                    for r in existing[pid]):
                plan.skip(key, 'у задачи уже есть строка с этим event_id')
                continue
            year, grade = int(task['year']), task['grade']
            stage = task.get('stage') or 'final'
            if stage not in self.olympiad.stages:
                plan.skip(key, f'этап эталона {stage!r} не из реестра олимпиады')
                continue
            same = [r for r in existing[pid] if self._same_tour(r, year, grade, stage)]
            if same:
                # Вторую строку того же тура не заводим — дописываем первую.
                ref = same[0]
                meta = dict(ref.raw_meta or {})
                if ref.official_url != task['source_url']:
                    meta.setdefault('aggregator_url', ref.official_url)
                    plan.update(ref, 'official_url', task['source_url'],
                                'вместо новой: ссылка на PDF')
                if ref.number != number:
                    meta.setdefault('aggregator_number', ref.number)
                    plan.update(ref, 'number', number, 'вместо новой: номер')
                if self.olympiad.multi_stage and not ref.stage:
                    self._set_stage(plan, ref, stage, 'вместо новой: этап')
                meta['official_event_id'] = event_id
                if variant:
                    meta['official_task_variant'] = variant
                plan.update(ref, 'raw_meta', meta, 'вместо новой: raw_meta')
                seen.add((pid, event_id))
                plan.notes.append(f'{key}: уже есть строка {ref.olympiad_slug} '
                                  f'ref {ref.id} того же тура — обновляется она')
                continue
            other = [r for r in existing[pid] if r.olympiad_slug not in family
                     and r.year != year]
            if other:
                plan.skip(key, 'у задачи строка другой олимпиады другого года '
                               f'({other[0].olympiad_slug} {other[0].year})')
                continue
            seen.add((pid, event_id))
            meta = dict(row['raw_meta'])
            tour = variant_of(event_id)
            if tour.startswith('tour'):
                meta['tour'] = tour
            self.tests_written += bool(row.get('is_test'))
            plan.creates.append({
                'problem_id': pid,
                'source_site': 'official',
                'olympiad_slug': slug,
                'olympiad_name': OLYMPIAD_NAMES[slug],
                'academic_year': bank_academic_year(task['academic_year']),
                'year': year,
                'stage': stage,
                'grade': grade,
                'variant': variant_of(event_id),
                'number': number,
                'event_id': event_id,
                'record_id': (f'official:{event_id}:{number}'
                              + (f':{variant}' if variant else '')),
                'match_method': row['match_method'],
                'match_score': row['match_score'],
                'official_url': task['source_url'],
                'raw_meta': meta,
                'reviewed_by_human': row['reviewed_by_human'],
            })

    # ── Правки существующих строк ───────────────────────────────────────

    def _plan_updates(self, plan, path):
        if not self.options['confirmed_by']:
            raise CommandError('--update-existing требует --confirmed-by '
                               '(список перенумеровок «на глаза»)')
        review = parse_claude_review(self.options['confirmed_by'])
        rows = read_csv(path)
        refs = OlympiadRef.objects.in_bulk([int(r['ref_id']) for r in rows])
        need_text = {int(r['problem_id']) for r in rows
                     if r['coord_status'] in ('other_event', 'number_shifted_same_event')}
        texts = {p.pk: self._bank_text(p) for p in
                 Problem.objects.filter(pk__in=need_text).prefetch_related('parts')}
        siblings = defaultdict(list)
        for ref in OlympiadRef.objects.filter(
                problem_id__in={int(r['problem_id']) for r in rows},
                olympiad_slug__in=self.olympiad.family):
            siblings[ref.problem_id].append(ref)
        self.twin_stats = Counter()
        self.renumber_stats = Counter()
        self.text_check = self._load_text_check()
        # Класс, который правки этого же прогона ставят строкам: защита от
        # двух строк одной задачи, переведённых в один и тот же комплект.
        self.planned_grades = {}

        for row in rows:
            ref = refs.get(int(row['ref_id']))
            key = f'ref {row["ref_id"]} (задача {row["problem_id"]})'
            action = row['action']
            if ref is None or ref.problem_id != int(row['problem_id']):
                plan.skip(key, 'строки нет или она о другой задаче')
                continue
            if action.startswith('move_slug'):
                target = row['proposed_slug']
                if target not in self.olympiad.family:
                    plan.skip(key, f'перенос в другую олимпиаду ({target}) не делается: '
                                   'там уже есть своя строка — снять --delete-refs')
                    continue
                plan.update(ref, 'olympiad_slug', target, 'move_slug')
                plan.update(ref, 'olympiad_name',
                            OLYMPIAD_NAMES[target], 'move_slug: название')
                continue
            if ref.olympiad_slug != self.olympiad.slug:
                plan.skip(key, f'слаг строки {ref.olympiad_slug}, а не '
                               f'{self.olympiad.slug}')
                continue
            status = row['coord_status']
            if action.startswith('нет_эталона') or not status:
                plan.skip(key, 'нет эталона (до 2012) — этап и класс не дописываются')
                continue
            if status == 'no_text_match_anywhere':
                plan.skip(key, 'текст не найден в эталоне — не трогаем')
                continue
            if status == 'coords_ok':
                self._plan_coords_ok(plan, ref, row)
            elif status == 'number_shifted_same_event':
                self._plan_renumber(plan, ref, row, key, review, texts)
            elif status == 'other_event':
                self._plan_twin(plan, ref, row, key, texts, siblings)
            else:
                plan.skip(key, f'неизвестный coord_status {status!r}')

    # ── Сравнение текста ────────────────────────────────────────────────

    def _bank_text(self, problem):
        """Текст задачи банка в виде, в котором его сравнивает эта олимпиада."""
        if self.olympiad.compare == 'markup_free':
            return markup_free_key(problem_identity_text(problem))
        return bank_norm_text(problem)

    def _task_text(self, row):
        """Текст задания эталона: у ВП — `norm_text` сессии 2, у МОШ — ключ
        без разметки по условию после чистки шапки (как у сверки МОШ-1)."""
        if self.olympiad.compare != 'markup_free':
            return row['norm_text']
        key = (row['event_id'], str(row['number']), row.get('task_variant') or '')
        if key not in self._ref_keys:
            _title, _pts, statement, _sol = clean_pdf_task(row.get('raw_text', ''), '')
            self._ref_keys[key] = markup_free_key(
                re.sub(r'\\([*_>#])', r'\1', statement), pdf=True)
        return self._ref_keys[key]

    def _score(self, text, row):
        return fuzzy_ratio(text, self._task_text(row))

    # ── Этап ────────────────────────────────────────────────────────────

    def _set_stage(self, plan, ref, official_stage, kind):
        """Пустой этап строки. Одноэтапная олимпиада (ВП) — `final`, как
        было. Многоэтапная — только по доказательству (`--stage-from`):
        комплект агрегатора с этапом, установленным текстом его задач; этап
        официального комплекта должен с ним совпасть. Иначе этап остаётся
        пустым — «скорее всего final» не пишем (решение владельца 09.10)."""
        if ref.stage:
            return
        if not self.olympiad.multi_stage:
            plan.update(ref, 'stage', official_stage or 'final', kind)
            return
        if self.stage_evidence is None:
            plan.stage_counts['этап не ставится: нет --stage-from'] += 1
            return
        base = (ref.event_id or '').split('__')[0]
        proven = self.stage_evidence.get(base)
        if not proven:
            plan.stage_counts['этап остаётся пустым: нет доказательства'] += 1
            return
        if official_stage and official_stage != proven:
            plan.stage_counts['этап остаётся пустым: доказанный ≠ этапу комплекта'] += 1
            return
        if plan.update(ref, 'stage', proven, kind):
            plan.stage_counts[f'этап поставлен: {proven}'] += 1

    def _official_fields(self, plan, ref, event_id, url, grade, kind, meta,
                         official_stage=None):
        """Общая часть: этап, класс (если пуст), ссылка на PDF, id комплекта."""
        self._set_stage(plan, ref, official_stage, f'{kind}: этап')
        if not ref.grade and grade:
            plan.update(ref, 'grade', grade, f'{kind}: класс')
        if url and ref.official_url != url:
            if ref.official_url and not self._is_official_url(ref.official_url):
                meta.setdefault('aggregator_url', ref.official_url)
            plan.update(ref, 'official_url', url, f'{kind}: ссылка на PDF')
        meta['official_event_id'] = event_id

    def _is_official_url(self, url):
        return any(host in url for host in self.olympiad.official_hosts)

    def _event_stage(self, event_id):
        rows = self.reference.by_event.get(event_id) or []
        return (rows[0].get('stage') or None) if rows else None

    def _plan_coords_ok(self, plan, ref, row):
        meta = dict(ref.raw_meta or {})
        event_id = row['official_event_id']
        action = row['action']
        if 'set_stage' in action and not ref.stage:
            self._set_stage(plan, ref, row['proposed_stage'] or self._event_stage(event_id),
                            'coords_ok: этап')
        if 'fill_grade' in action and not ref.grade and row['proposed_grade']:
            plan.update(ref, 'grade', row['proposed_grade'], 'coords_ok: класс')
        url = row['proposed_official_url']
        if 'set_official_url' in action and url and ref.official_url != url:
            if ref.official_url and not self._is_official_url(ref.official_url):
                meta.setdefault('aggregator_url', ref.official_url)
            plan.update(ref, 'official_url', url, 'coords_ok: ссылка на PDF')
        if event_id:
            meta['official_event_id'] = event_id
        plan.update(ref, 'raw_meta', meta, 'coords_ok: raw_meta')

    def _plan_renumber(self, plan, ref, row, key, review, texts):
        event_id, new = row['official_event_id'], row['proposed_number']
        old = ref.number
        doubtful = review.is_renumber_eyeball(ref.problem_id, event_id)
        if not new:
            # Текст банка входит в задание эталона целиком: нарезка
            # агрегатора склеила или разрезала задания — номера нет.
            plan.skip(key, 'предложенного номера нет (текст банка — кусок '
                           'задания эталона) — строка не трогается')
            self.renumber_stats['нет предложенного номера'] += 1
            return
        if doubtful and not self.options['include_eyeball']:
            if old == new:
                return
            if not self.options['renumber_by_containment']:
                plan.skip(key, 'перенумеровка «на глаза» — нужен --include-eyeball')
                self.renumber_stats['на глаза: пропущено'] += 1
                return
            # Сомнительная: только если текст банка ВХОДИТ в задание под
            # новым номером и НЕ входит под текущим.
            bank = texts.get(ref.problem_id, '')
            new_task = self.reference.task(event_id, new)
            old_task = self.reference.task(event_id, old)
            c_new = containment(bank, self._task_text(new_task)) if new_task else 0.0
            c_old = containment(bank, self._task_text(old_task)) if old_task else 0.0
            if c_new < TWIN_THRESHOLD or c_old >= TWIN_THRESHOLD:
                plan.skip(key, f'сомнительная перенумеровка не подтверждена '
                               f'вхождением (№{new}: {c_new:.2f}, №{old}: {c_old:.2f})')
                self.renumber_stats['сомнительная: вхождение не подтвердило'] += 1
                return
            self.renumber_stats['сомнительная: принята по вхождению'] += 1
        elif old != new:
            # Сверка текста: под новым номером сходство обязано быть выше.
            bank = texts.get(ref.problem_id, '')
            new_task = self.reference.task(event_id, new)
            old_task = self.reference.task(event_id, old)
            if new_task is None:
                plan.skip(key, f'в эталоне нет {event_id} №{new}')
                return
            s_new = self._score(bank, new_task)
            s_old = self._score(bank, old_task) if old_task else 0.0
            if s_new <= s_old:
                plan.skip(key, f'сверка текста не подтвердила №{new} '
                               f'({s_new:.3f} против {s_old:.3f})')
                self.renumber_stats['сверка текста не подтвердила'] += 1
                return
            self.renumber_stats['принята'] += 1
        task = self.reference.task(event_id, new)
        if task is None:
            plan.skip(key, f'в эталоне нет {event_id} №{new}')
            return
        meta = dict(ref.raw_meta or {})
        if old != new:
            meta.setdefault('aggregator_number', old)
            plan.update(ref, 'number', new, 'renumber: номер')
        self._official_fields(plan, ref, event_id, task['source_url'],
                              task['grade'], 'renumber', meta,
                              official_stage=task.get('stage'))
        plan.update(ref, 'raw_meta', meta, 'renumber: raw_meta')

    def _load_text_check(self):
        path = self.options['text_check'] or os.path.join(
            self.input_dir, 'existing_refs_text_check.csv')
        if not os.path.isfile(path):
            return {}
        return {row['ref_id']: row for row in read_csv(path)}

    def _own_events(self, ref, stage):
        """Комплекты эталона класса строки: тот же год и этап, класс
        пересекается (общий комплект `8-9` подходит и 8, и 9 классу)."""
        if not ref.grade:
            return []
        return sorted(ev for ev, row in self.reference.events().items()
                      if int(row['year']) == ref.year
                      and (row.get('stage') or 'final') == stage
                      and _grades_overlap(ref.grade, row['grade']))

    def _twin_target(self, ref, row):
        """(найденный комплект, №, вариант, свои комплекты) или None.

        Причина в CSV правок (ВП) — «текст совпал с X №N … координаты строки
        ведут в Y №M»; у МОШ причина пуста, и найденное берётся из файла
        сверки `existing_refs_text_check.csv`, а свои комплекты — по году,
        этапу найденного и классу строки."""
        parsed = parse_other_event_reason(row['reason'])
        if parsed:
            found_ev, found_no, own_ev, _own_no = parsed
            return found_ev, found_no, '', [own_ev]
        check = self.text_check.get(str(ref.id))
        if not check or not check.get('best_any_event'):
            return None
        found_ev = check['best_any_event']
        stage = self._event_stage(found_ev) or 'final'
        return (found_ev, check['best_any_number'], check.get('best_any_variant') or '',
                self._own_events(ref, stage))

    def _plan_twin(self, plan, ref, row, key, texts, siblings):
        target = self._twin_target(ref, row)
        if not target:
            plan.skip(key, 'не разобрана причина other_event')
            return
        found_ev, found_no, found_variant, own_events = target
        found_task = self.reference.task(found_ev, found_no, found_variant)
        if found_task is None:
            plan.skip(key, f'найденного задания {found_ev} №{found_no} нет в эталоне')
            return
        if not own_events or not any(self.reference.by_event.get(e) for e in own_events):
            # Комплекта класса строки нет в эталоне (у МОШ — финал 2017/18
            # 8, 9, 11 кл.): близнеца не проверить, а исправить класс на
            # соседний значило бы угадать.
            plan.skip(key, 'комплекта класса строки нет в эталоне — класс не '
                           'проверить, строка не трогается')
            self.twin_stats['своего комплекта нет в эталоне — пропущено'] += 1
            return
        bank = texts.get(ref.problem_id, '')
        best = max((self.reference.best_in_event_by(bank, ev, self._score) + (ev,)
                    for ev in own_events), key=lambda b: b[2])
        if best[2] < TWIN_THRESHOLD and self.options['twin_pdf_to_pdf']:
            # Текст банка не дотянул до своего комплекта (шапка «(20 баллов)»
            # против «(25 баллов)», вёрстка PDF) — сравниваем найденное
            # задание соседнего класса с заданиями своего: два PDF одной
            # вёрстки между собой.
            found_text = self._task_text(found_task)
            best = max((self.reference.best_in_event_by(found_text, ev, self._score) + (ev,)
                        for ev in own_events), key=lambda b: b[2])
        number, variant, score, own_ev = best
        meta = dict(ref.raw_meta or {})
        if score >= TWIN_THRESHOLD:
            self.twin_stats['класс верен (близнец)'] += 1
            event_id = own_ev
        else:
            # Класс неверен: переводим строку на комплект, где нашёлся текст.
            event_id, number, variant = found_ev, found_no, found_variant
            new_grade = found_task['grade']
            clash = [r for r in siblings[ref.problem_id] if r.id != ref.id
                     and r.year == ref.year and r.grade
                     and _grades_overlap(self.planned_grades.get(r.id, r.grade),
                                         new_grade)]
            if clash:
                plan.skip(key, f'исправление класса на {new_grade} дало бы вторую '
                               f'строку того же тура (ref {clash[0].id})')
                self.twin_stats['класс исправить — пропущено (вторая строка)'] += 1
                return
            self.twin_stats['класс исправить'] += 1
            if ref.grade != new_grade:
                meta.setdefault('aggregator_grade', ref.grade)
                plan.update(ref, 'grade', new_grade, 'близнец: класс исправлен')
                self.planned_grades[ref.id] = new_grade
        task = self.reference.task(event_id, number, variant)
        if ref.number != number:
            meta.setdefault('aggregator_number', ref.number)
            plan.update(ref, 'number', number, 'близнец: номер по PDF')
        if variant:
            meta['official_task_variant'] = variant
        self._official_fields(plan, ref, event_id, task['source_url'],
                              task['grade'], 'близнец', meta,
                              official_stage=task.get('stage'))
        plan.update(ref, 'raw_meta', meta, 'близнец: raw_meta')

    # ── Импорт недостающих заданий ─────────────────────────────────────

    def _plan_import(self, plan, path):
        source_name = self.olympiad.official_source_name
        source = Source.objects.filter(name=source_name).first()
        if source is None:
            plan.notes.append(f'Source «{source_name}» не заведён — '
                              'сначала olympiad_official_sources --apply')
        done = set(SourceReference.objects.filter(source=source)
                   .values_list('problem_number', flat=True)) if source else set()
        assumed = {}
        if self.options['assume_updates']:
            if self.apply:
                raise CommandError('--assume-updates — только для сухого прогона')
            for journal_path in self.options['assume_updates']:
                assumed.update(_assumed_official_tasks(journal_path))
            plan.notes.append(f'журналы сухих прогонов считаются записанными '
                              f'({len(self.options["assume_updates"])}): '
                              f'{len(assumed)} заданий эталона будут привязаны')
        figures_dir = self.options['figures_dir'] or os.path.join(
            os.path.dirname(self.input_dir), 'session3', 'figures')
        for row in read_jsonl(path):
            event_id, number = row['event_id'], str(row['number'])
            external_id = f'{event_id}:{number}'
            if external_id in done:
                plan.skip(external_id, 'уже импортировано (SourceReference)')
                continue
            # Задание уже привязано к задаче банка — строкой с официальным
            # event_id или строкой агрегатора, переведённой на официальный
            # комплект правками (raw_meta['official_event_id']). Поэтому
            # импорт идёт ПОСЛЕ --update-existing.
            taken = OlympiadRef.objects.filter(
                Q(event_id=event_id) | Q(raw_meta__official_event_id=event_id),
                number=number).values_list('problem_id', flat=True)
            if taken:
                plan.skip(external_id, f'в банке уже есть задача с этим заданием '
                                       f'(#{taken[0]})')
                continue
            if (event_id, number) in assumed:
                plan.skip(external_id, 'задание закроет новая строка или правка '
                                       f'(задача #{assumed[(event_id, number)]})')
                continue
            figure_path, drop_lines = None, []
            if _truthy(row.get('has_figure')):
                candidate = os.path.join(figures_dir, f'{event_id}_{number}.png')
                figure_path = candidate if os.path.isfile(candidate) else None
                sidecar = os.path.join(figures_dir, f'{event_id}_{number}.json')
                if figure_path and os.path.isfile(sidecar):
                    # Подписи внутри вырезки: на картинке они есть, в тексте лишние.
                    with open(sidecar, encoding='utf-8') as handle:
                        drop_lines = json.load(handle).get('drop_lines', [])
            title, points, statement, solution = clean_pdf_task(
                row['raw_text'], row.get('solution_text', ''),
                combined=row.get('tasks_pdf') == row.get('solutions_pdf'),
                drop_lines=drop_lines)
            plan.imports.append({
                'row': row, 'external_id': external_id, 'title': title,
                'points': points, 'statement': statement, 'solution': solution,
                'has_figure': _truthy(row.get('has_figure')),
                'figure_path': figure_path,
                'formula_suspect': formula_suspect(
                    row['raw_text'] + '\n' + row.get('solution_text', '')),
            })

    # ── Инварианты и печать ─────────────────────────────────────────────

    def _check_invariants(self, plan):
        pairs = Counter((c['problem_id'], c['event_id']) for c in plan.creates)
        doubled = [k for k, n in pairs.items() if n > 1]
        clash = OlympiadRef.objects.filter(
            problem_id__in={c['problem_id'] for c in plan.creates},
            event_id__in={c['event_id'] for c in plan.creates})
        clash = [(r.problem_id, r.event_id) for r in clash if (r.problem_id, r.event_id) in pairs]
        before, after = self._official_duplicates(plan)
        self.new_duplicates = sorted(after - before)
        self.invariants = {
            'две новые строки на одну пару (задача, event_id)': len(doubled),
            'новая строка при существующей паре (задача, event_id)': len(clash),
            'задач с двумя строками на один официальный комплект: до': len(before),
            'то же после плана': len(after),
            'новых таких задач (запись запрещена, если > 0)': len(self.new_duplicates),
        }
        if doubled or clash:
            raise CommandError(f'Нарушен инвариант: {self.invariants}')

    def _official_duplicates(self, plan):
        """Пары (задача, официальный комплект), на которые указывают две и
        более строки этой олимпиады — до плана и после него. Официальный
        комплект строки — `raw_meta['official_event_id']` или её собственный
        `event_id`, если строка `official`."""
        pids = ({c['problem_id'] for c in plan.creates}
                | set(OlympiadRef.objects.filter(pk__in=list(plan.updates))
                      .values_list('problem_id', flat=True)))
        refs = list(OlympiadRef.objects.filter(
            problem_id__in=pids, olympiad_slug__in=self.olympiad.family))

        def official(ref, meta):
            event = (meta or {}).get('official_event_id')
            return event or (ref.event_id if ref.source_site == 'official' else None)

        def duplicates(entries):
            counts = Counter(e for e in entries if e[1])
            return {e for e, n in counts.items() if n > 1}

        before = duplicates((r.problem_id, official(r, r.raw_meta)) for r in refs)
        after = [(r.problem_id, official(
            r, plan.updates.get(r.id, {}).get('raw_meta', r.raw_meta))) for r in refs]
        after += [(c['problem_id'], c['event_id']) for c in plan.creates]
        return before, duplicates(after)

    def _print_plan(self, plan):
        w = self.stdout.write
        w('')
        w(f'=== {self.mode}: {"ЗАПИСЬ" if self.apply else "сухой прогон"} ===')
        for name, value in _counts().items():
            w(f'  {name}: {value}')
        w('')
        if plan.creates:
            by_method = Counter(c['match_method'] for c in plan.creates)
            w(f'СОЗДАТЬ строк OlympiadRef: {len(plan.creates)} {dict(by_method)}')
            for c in plan.creates[:EXAMPLES]:
                w(f'  задача {c["problem_id"]} → {c["event_id"]} №{c["number"]} '
                  f'({c["match_method"]}, {c["match_score"]})')
        if plan.updates:
            fields = Counter(f for ch in plan.updates.values() for f in ch)
            w(f'ОБНОВИТЬ строк: {len(plan.updates)}; полей по видам: {dict(fields)}')
            for kind, n in sorted(plan.update_kinds.items()):
                w(f'  {kind}: {n}')
            for kind in sorted(plan.update_examples):
                if 'raw_meta' in kind:
                    continue
                w(f'  — примеры «{kind}»:')
                for line in plan.update_examples[kind]:
                    w(f'      {line}')
        if getattr(self, 'twin_stats', None):
            w(f'БЛИЗНЕЦЫ (other_event): {dict(self.twin_stats)}')
        if getattr(self, 'renumber_stats', None):
            w(f'ПЕРЕНУМЕРОВКА: {dict(self.renumber_stats)}')
        if plan.stage_counts:
            w(f'ЭТАП: {dict(plan.stage_counts)}')
        if getattr(self, 'tests_written', 0):
            w(f'Из новых строк — тесты: {self.tests_written}')
        for pid, event in self.new_duplicates[:EXAMPLES]:
            w(f'  ⚠ две строки на один комплект после плана: задача {pid}, {event}')
        if plan.imports:
            w(f'ИМПОРТ заданий: {len(plan.imports)}; с рисунком '
              f'{sum(i["has_figure"] for i in plan.imports)}, из них картинка '
              f'вырезана {sum(bool(i["figure_path"]) for i in plan.imports)}; '
              f'подозрение на битые формулы {sum(i["formula_suspect"] for i in plan.imports)}')
            for item in plan.imports:
                w(f'  {item["external_id"]}: «{item["title"] or "—"}», '
                  f'{item["row"].get("max_score")} баллов, решение '
                  f'{"есть" if item["solution"] else "НЕТ"}, рисунок '
                  f'{"вырезан" if item["figure_path"] else ("НЕ вырезан" if item["has_figure"] else "нет")}'
                  f'{", формулы?" if item["formula_suspect"] else ""}')
                w(f'      {item["statement"][:200]!r}')
        reasons = Counter(r for _k, r in plan.skips)
        w(f'ПРОПУСТИТЬ: {len(plan.skips)}')
        for reason, n in reasons.most_common():
            w(f'  {n} — {reason}')
            for k, r in [s for s in plan.skips if s[1] == reason][:EXAMPLES]:
                w(f'      {k}')
        for note in plan.notes:
            w(f'  ⚠ {note}')
        w(f'Инварианты: {self.invariants}')

    # ── Запись ──────────────────────────────────────────────────────────

    def _apply(self, plan):
        journal = self._empty_journal(applied=True)
        journal['counts_before'] = _counts()
        try:
            if self.mode == 'import':
                self._apply_import(plan, journal)
            else:
                with transaction.atomic():
                    self._apply_refs(plan, journal)
        except Exception as error:
            journal['error'] = repr(error)
            if self.mode != 'import':
                # Общая транзакция откатилась — ничего из списка не записано.
                journal['created_ref_ids'], journal['updated_refs'] = [], []
            raise
        finally:
            journal['counts_after'] = _counts()
            journal['finished_at'] = datetime.now().isoformat(timespec='seconds')
            path = self._dump(journal, suffix='')
        self.stdout.write(self.style.SUCCESS(
            f'ЗАПИСАНО. Создано строк OlympiadRef: {len(journal["created_ref_ids"])}, '
            f'правок полей: {len(journal["updated_refs"])}, задач: '
            f'{len(journal["created_problem_ids"])}.'))
        for name, value in journal['counts_after'].items():
            delta = value - journal['counts_before'][name]
            self.stdout.write(f'  {name}: {value} ({delta:+d})')
        self.stdout.write(f'Журнал отката: {path}')

    def _apply_refs(self, plan, journal):
        for fields in plan.creates:
            ref = OlympiadRef.objects.create(**fields)
            journal['created_ref_ids'].append(ref.id)
        refs = OlympiadRef.objects.in_bulk(list(plan.updates))
        for ref_id, changes in plan.updates.items():
            ref = refs[ref_id]
            for field, new in changes.items():
                journal['updated_refs'].append(
                    {'id': ref_id, 'field': field,
                     'old': getattr(ref, field), 'new': new})
                setattr(ref, field, new)
            ref.save(update_fields=list(changes))

    def _apply_import(self, plan, journal):
        source_name = self.olympiad.official_source_name
        source = Source.objects.filter(name=source_name).first()
        if source is None:
            raise CommandError(f'Нет Source «{source_name}»: '
                               'запустите olympiad_official_sources --apply')
        for item in plan.imports:
            # Своя транзакция на задание: сбой одного не откатывает уже
            # записанные, и журнал знает их все (запись в finally выше).
            created = defaultdict(list)
            with transaction.atomic():
                self._import_one(source, item, created)
            # В журнал — только после успешной транзакции задания.
            for key, ids in created.items():
                journal[key].extend(ids)

    def _import_one(self, source, item, journal):
        row = item['row']
        event_id, number = row['event_id'], str(row['number'])
        year = int(row['year'])
        statement = item['statement']
        figure = None
        if item['figure_path']:
            reference = f'official-pdf:{row.get("tasks_pdf", "")}#{event_id}:{number}'
            digest = hashlib.sha256(reference.encode('utf-8')).hexdigest()
            statement = _place_marker(statement, f'[[FIGURE:{digest}]]')
            with open(item['figure_path'], 'rb') as handle:
                figure = (digest, reference, handle.read())
        parts = [{'label': p.get('label', ''), 'statement_md': p.get('statement', ''),
                  'answer': p.get('answer', ''), 'solution': p.get('solution', '')}
                 for p in row.get('parts') or []]
        stage = row.get('stage') or 'final'
        note = (f'{STAGE_LABELS.get(stage, stage)}, {row["grade"]} класс, задание {number}; '
                f'максимум {row.get("max_score")} баллов')
        problem = create_problem(
            source=source, external_id=f'{event_id}:{number}',
            title=item['title'], statement_md=statement, answer_md='',
            solution_md=item['solution'], parts=parts,
            reference_note=note, reference_url=row['source_url'],
            reference_year=year)
        # Формат markdown — как у копий Школково той же олимпиады; без него
        # маркер картинки не превращается в изображение.
        problem.content_format = Problem.ContentFormat.MARKDOWN
        problem.needs_quality_review = item['has_figure'] and figure is None
        problem.save(update_fields=['content_format', 'needs_quality_review'])
        journal['created_problem_ids'].append(problem.id)
        journal['created_part_ids'].extend(problem.parts.values_list('id', flat=True))
        sref = problem.source_references.get(source=source)
        sref.stage, sref.grade = STAGE_LABELS.get(stage, stage), row['grade']
        sref.save(update_fields=['stage', 'grade'])
        journal['created_sourceref_ids'].append(sref.id)
        if figure:
            fig = ProblemFigure.objects.create(
                problem=problem, tikz_hash=figure[0], tikz_source=figure[1],
                svg='', image_data=figure[2], content_type='image/png',
                source_field='statement')
            journal['created_figure_ids'].append(fig.id)
        ref = OlympiadRef.objects.create(
            problem=problem, source_site='official',
            olympiad_slug=self.olympiad.slug,
            olympiad_name=OLYMPIAD_NAMES[self.olympiad.slug],
            academic_year=bank_academic_year(row.get('academic_year')),
            year=year, stage=stage, grade=row['grade'],
            variant=variant_of(event_id), number=number, event_id=event_id,
            record_id=f'official:{event_id}:{number}',
            # Ссылка источника задачи и ссылка привязки — один и тот же PDF.
            match_method='url_exact', match_score=1.0,
            official_url=row['source_url'],
            raw_meta={'session': self.olympiad.session, 'origin': 'import_official_pdf',
                      'max_score': row.get('max_score'),
                      'formula_suspect': item['formula_suspect']},
            reviewed_by_human=False)
        journal['created_ref_ids'].append(ref.id)

    # ── Журнал ──────────────────────────────────────────────────────────

    def _empty_journal(self, applied):
        return {
            'mode': self.mode, 'applied': applied,
            'started_at': datetime.now().isoformat(timespec='seconds'),
            'inputs': self.inputs,
            'created_ref_ids': [], 'updated_refs': [],
            'created_problem_ids': [], 'created_part_ids': [],
            'created_sourceref_ids': [], 'created_figure_ids': [],
            'deleted_refs': [],
            'how_to_revert': (
                'manage.py apply_olympiad_audit --rollback <этот файл> — сухой '
                'прогон; с --apply --yes-i-have-owner-approval — откат: '
                'удаляются созданные строки и задачи, у изменённых строк '
                'поля возвращаются к old (только если сейчас там new).'),
        }

    def _write_journal(self, plan, applied):
        journal = self._empty_journal(applied)
        journal['counts_before'] = _counts()
        journal['planned_creates'] = plan.creates
        journal['planned_updates'] = [
            {'id': ref_id, 'field': f, 'new': v}
            for ref_id, ch in plan.updates.items() for f, v in ch.items()]
        journal['planned_imports'] = [
            {k: v for k, v in item.items() if k != 'row'} for item in plan.imports]
        journal['skipped'] = [{'key': k, 'reason': r} for k, r in plan.skips]
        journal['update_kinds'] = dict(plan.update_kinds)
        journal['twin_stats'] = dict(getattr(self, 'twin_stats', {}) or {})
        journal['renumber_stats'] = dict(getattr(self, 'renumber_stats', {}) or {})
        journal['stage_counts'] = dict(plan.stage_counts)
        journal['invariants'] = self.invariants
        journal['new_duplicates'] = self.new_duplicates
        journal['notes'] = plan.notes
        path = self._dump(journal, suffix='_dryrun')
        self.stdout.write(f'Журнал сухого прогона: {path}')

    def _dump(self, journal, suffix):
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(self.out_dir, f'apply_{stamp}_{self.mode}{suffix}.json')
        n = 1
        while os.path.exists(path):   # два прогона в одну секунду
            n += 1
            path = os.path.join(self.out_dir,
                                f'apply_{stamp}-{n}_{self.mode}{suffix}.json')
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(journal, handle, ensure_ascii=False, indent=1, default=str)
        return path

    # ── Снятие ошибочных строк ──────────────────────────────────────────

    def _delete_refs(self, spec):
        """Снять строки OlympiadRef этой олимпиады по id. Полная копия каждой
        строки — в журнале; `--rollback` создаёт её заново с тем же id."""
        ids = [int(x) for x in re.split(r'[,\s]+', spec.strip()) if x]
        if not self.options['out_dir']:
            raise CommandError('--delete-refs требует --out-dir (папка журналов). '
                               'Ничего не сделано.')
        self.out_dir = self.options['out_dir']
        os.makedirs(self.out_dir, exist_ok=True)
        self.mode = 'delete_refs'
        self.inputs = {'olympiad': self.olympiad.slug, 'delete_refs': ids}
        refs = OlympiadRef.objects.in_bulk(ids)
        missing = [i for i in ids if i not in refs]
        alien = [r.id for r in refs.values()
                 if r.olympiad_slug not in self.olympiad.family]
        if missing or alien:
            raise CommandError(f'Снимаются только существующие строки этой олимпиады: '
                               f'нет строк {missing}, чужой слаг у {alien}. '
                               'Ничего не сделано.')
        copies = [_ref_copy(refs[i]) for i in ids]
        w = self.stdout.write
        w(f'=== delete_refs ({self.olympiad.slug}): '
          f'{"ЗАПИСЬ" if self.apply else "сухой прогон"} ===')
        for copy in copies:
            w(f'  снять ref {copy["id"]}: задача {copy["problem_id"]}, '
              f'{copy["olympiad_slug"]} {copy["year"]} {copy["stage"] or "—"} '
              f'{copy["grade"]} кл. №{copy["number"]} ({copy["source_site"]}, '
              f'{copy["event_id"]})')
        if not self.apply:
            journal = self._empty_journal(applied=False)
            journal['counts_before'] = _counts()
            journal['planned_deletes'] = copies
            path = self._dump(journal, suffix='_dryrun')
            w(f'Журнал сухого прогона: {path}')
            w(self.style.WARNING('СУХОЙ ПРОГОН — в базе ничего не изменено.'))
            return
        journal = self._empty_journal(applied=True)
        journal['counts_before'] = _counts()
        with transaction.atomic():
            OlympiadRef.objects.filter(pk__in=ids).delete()
        journal['deleted_refs'] = copies
        journal['counts_after'] = _counts()
        journal['finished_at'] = datetime.now().isoformat(timespec='seconds')
        path = self._dump(journal, suffix='')
        w(self.style.SUCCESS(f'СНЯТО строк: {len(ids)}. Журнал отката: {path}'))

    # ── Откат ───────────────────────────────────────────────────────────

    def _rollback(self, path):
        with open(path, encoding='utf-8') as handle:
            journal = json.load(handle)
        if not journal.get('applied'):
            raise CommandError('Это журнал сухого прогона — откатывать нечего.')
        recorded = (journal.get('inputs') or {}).get('olympiad')
        if recorded and recorded != self.olympiad.slug:
            raise CommandError(f'Журнал записан для --olympiad {recorded}, а не '
                               f'{self.olympiad.slug}. Ничего не сделано.')
        removed = journal.get('deleted_refs') or []
        taken = set(OlympiadRef.objects.filter(
            pk__in=[c['id'] for c in removed]).values_list('pk', flat=True))
        restore, conflicts = [], []
        recreate = [c for c in removed if c['id'] not in taken]
        conflicts += [f'ref {c["id"]}: строка с этим id уже есть — не восстанавливаю'
                      for c in removed if c['id'] in taken]
        refs = OlympiadRef.objects.in_bulk({u['id'] for u in journal['updated_refs']})
        for change in journal['updated_refs']:
            ref = refs.get(change['id'])
            if ref is None:
                conflicts.append(f'ref {change["id"]}: строки больше нет')
            elif getattr(ref, change['field']) != change['new']:
                conflicts.append(f'ref {change["id"]}.{change["field"]}: значение '
                                 'изменилось после записи — не трогаю')
            else:
                restore.append(change)
        w = self.stdout.write
        w(f'Откат журнала {path} ({journal["mode"]}):')
        w(f'  удалить строк OlympiadRef: {len(journal["created_ref_ids"])}, '
          f'задач: {len(journal["created_problem_ids"])} (с подпунктами '
          f'{len(journal["created_part_ids"])}, привязками к источнику '
          f'{len(journal["created_sourceref_ids"])}, картинками '
          f'{len(journal["created_figure_ids"])})')
        w(f'  вернуть полей: {len(restore)}; восстановить снятых строк: '
          f'{len(recreate)}; конфликтов: {len(conflicts)}')
        for line in conflicts[:EXAMPLES]:
            w(f'    ⚠ {line}')
        if not self.apply:
            w(self.style.WARNING('СУХОЙ ПРОГОН отката — ничего не изменено.'))
            return
        before = _counts()
        with transaction.atomic():
            for change in restore:
                OlympiadRef.objects.filter(pk=change['id']).update(
                    **{change['field']: change['old']})
            OlympiadRef.objects.filter(pk__in=journal['created_ref_ids']).delete()
            ProblemFigure.objects.filter(pk__in=journal['created_figure_ids']).delete()
            SourceReference.objects.filter(pk__in=journal['created_sourceref_ids']).delete()
            ProblemPart.objects.filter(pk__in=journal['created_part_ids']).delete()
            deleted = Problem.objects.filter(pk__in=journal['created_problem_ids']).delete()
            for copy in recreate:
                _restore_ref(copy)
        after = _counts()
        out = os.path.join(os.path.dirname(os.path.abspath(path)),
                           'rollback_' + os.path.basename(path))
        with open(out, 'w', encoding='utf-8') as handle:
            json.dump({'journal': os.path.abspath(path), 'restored': len(restore),
                       'recreated_refs': [c['id'] for c in recreate],
                       'conflicts': conflicts, 'deleted_problems': str(deleted),
                       'counts_before': before, 'counts_after': after},
                      handle, ensure_ascii=False, indent=1)
        w(self.style.SUCCESS(f'Откат выполнен. Отчёт: {out}'))
        for name, value in after.items():
            w(f'  {name}: {value} ({value - before[name]:+d})')


def _ref_copy(ref):
    """Полная копия строки OlympiadRef для журнала (все поля, с id)."""
    copy = {}
    for name in _REF_FIELDS:
        value = getattr(ref, name)
        copy[name] = value.isoformat() if isinstance(value, datetime) else value
    return copy


def _restore_ref(copy):
    """Вернуть снятую строку с тем же id и теми же полями. Дата создания
    ставится отдельным update: при create её перезаписал бы auto_now_add."""
    fields = dict(copy)
    created_at = fields.pop('created_at', None)
    ref = OlympiadRef(**fields)
    ref.save(force_insert=True)
    if created_at:
        OlympiadRef.objects.filter(pk=ref.pk).update(
            created_at=datetime.fromisoformat(created_at))


def _read_stage_evidence(path, stages):
    """catalog_vs_official.csv → {комплект агрегатора: доказанный этап}.
    Берутся только этапы реестра без «?»: `final?` (этап по умолчанию, без
    текста-доказательства) — не доказательство."""
    evidence = {}
    for row in read_csv(path):
        stage = (row.get('stage_established') or '').strip()
        if stage in stages:
            evidence[row['catalog_event_id']] = stage
    return evidence


def _assumed_official_tasks(path):
    """(event_id, номер) → задача: куда укажут новые строки и строки после
    правок из журнала сухого прогона --new-refs / --update-existing."""
    with open(path, encoding='utf-8') as handle:
        journal = json.load(handle)
    result = {(c['event_id'], c['number']): c['problem_id']
              for c in journal.get('planned_creates', [])}
    planned = defaultdict(dict)
    for change in journal.get('planned_updates', []):
        planned[change['id']][change['field']] = change['new']
    refs = OlympiadRef.objects.in_bulk(list(planned))
    for ref_id, changes in planned.items():
        ref = refs.get(ref_id)
        meta = changes.get('raw_meta') or (ref.raw_meta if ref else None) or {}
        event_id = meta.get('official_event_id')
        if ref and event_id:
            result[(event_id, changes.get('number', ref.number))] = ref.problem_id
    return result


def _truthy(value):
    return value is True or str(value).strip().lower() in ('true', '1', 'yes')


_FIGURE_HINT = re.compile(r'рис\.|рисун|график|диаграмм', re.IGNORECASE)


def _place_marker(statement, marker):
    """Маркер картинки — после первого абзаца, где упомянут рисунок или
    график; если такого нет — в конце условия."""
    paragraphs = statement.split('\n\n')
    for i, para in enumerate(paragraphs):
        if _FIGURE_HINT.search(para):
            paragraphs.insert(i + 1, marker)
            return '\n\n'.join(paragraphs)
    return statement + '\n\n' + marker
