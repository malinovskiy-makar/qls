# -*- coding: utf-8 -*-
"""Запись итогов аудита олимпиады по официальному эталону (пилот «Высшая проба»).

Читает файлы сессии 2 аудита (docs/OLYMPIAD_AUDIT.md) и пишет в базу
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
    --rollback <журнал.json>
        вернуть всё, что записал прогон с этим журналом.

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
from problems.olympiad_grades import parse_grades
from problems.olympiad_official import (
    OFFICIAL_SOURCE_NAME, OLYMPIAD_NAMES, TWIN_THRESHOLD, Reference,
    bank_academic_year, bank_norm_text, clean_pdf_task, formula_suspect,
    parse_claude_review, parse_other_event_reason, read_csv, read_jsonl,
    variant_of,
)
from problems.text_dedup import fuzzy_ratio

APPROVAL_FLAG = '--yes-i-have-owner-approval'
SESSION = 'vp3'
REVIEWED_BY = 'claude-chat-20261008'
VP_FAMILY = ('vp', 'vp-fingram', 'vp-ob')
EXAMPLES = 10


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
    }


class Plan:
    """Что команда собирается сделать: создать, обновить, пропустить."""

    def __init__(self):
        self.creates = []                 # dict полей новой OlympiadRef
        self.updates = {}                 # ref_id -> {field: new}
        self.update_kinds = Counter()     # вид правки -> число строк
        self.update_examples = defaultdict(list)
        self.imports = []                 # подготовленные задания
        self.skips = []                   # (ключ, причина)
        self.notes = []                   # строки для отчёта

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
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument('--new-refs', metavar='CSV')
        mode.add_argument('--update-existing', metavar='CSV')
        mode.add_argument('--import', dest='import_queue', metavar='JSONL')
        mode.add_argument('--rollback', metavar='JOURNAL')
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
        if self.apply and not options['approved']:
            raise CommandError(
                f'--apply пишет в боевые таблицы и требует {APPROVAL_FLAG} '
                '(владелец сказал «да» на стоп-гейте). Ничего не записано.')
        if options['rollback']:
            return self._rollback(options['rollback'])

        source_file = (options['new_refs'] or options['update_existing']
                       or options['import_queue'])
        if not os.path.isfile(source_file):
            raise CommandError(f'Нет файла: {source_file}')
        self.input_dir = os.path.dirname(os.path.abspath(source_file))
        self.out_dir = options['out_dir'] or os.path.join(
            os.path.dirname(self.input_dir), 'session3')
        os.makedirs(self.out_dir, exist_ok=True)
        ref_path = options['reference'] or os.path.join(
            self.input_dir, 'reference_problems_full.jsonl')
        if not os.path.isfile(ref_path):
            raise CommandError(f'Нет эталона: {ref_path} (--reference)')
        self.reference = Reference.load(ref_path)

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
        self.inputs = {'file': os.path.abspath(source_file),
                       'reference': os.path.abspath(ref_path),
                       'confirmed_by': options['confirmed_by'] or '',
                       'include_eyeball': options['include_eyeball']}
        if not self.apply:
            self._write_journal(plan, applied=False)
            self.stdout.write(self.style.WARNING(
                'СУХОЙ ПРОГОН — в базе ничего не изменено.'))
            return
        self._apply(plan)

    # ── Новые привязки ──────────────────────────────────────────────────

    def _new_ref_rows(self, path, tier):
        rows = read_csv(path)
        if tier == 'auto':
            for row in rows:
                yield {
                    'problem_id': int(row['problem_id']),
                    'event_id': row['event_id'], 'number': row['number'],
                    'raw_meta': {'session': SESSION,
                                 'fuzzy': float(row['match_score']),
                                 'margin': float(row['margin_vs_other_ref']),
                                 'reference_number': row['number']},
                    'match_method': 'text_fuzzy_numeric',
                    'match_score': float(row['match_score']),
                    'reviewed_by_human': False,
                }
            return
        if not self.options['confirmed_by']:
            raise CommandError('--tier high требует --confirmed-by <файл проверки>')
        confirmed, _eyeball = parse_claude_review(self.options['confirmed_by'])
        self.stdout.write(f'Подтверждено в файле проверки: {len(confirmed)} пар')
        for row in rows:
            if not row['review_tier'].startswith('высокий'):
                continue
            pid = int(row['problem_id'])
            key = (pid, row['ref_event_id'], row['ref_number'])
            if key not in confirmed:
                yield {'problem_id': pid, 'unconfirmed': True,
                       'event_id': row['ref_event_id'],
                       'number': row['ref_number']}
                continue
            yield {
                'problem_id': pid,
                'event_id': row['ref_event_id'], 'number': row['ref_number'],
                'raw_meta': {'session': SESSION,
                             'fuzzy': float(row['fuzzy']),
                             'margin': float(row['margin']),
                             'reference_number': row['ref_number'],
                             'reviewed_by': REVIEWED_BY},
                'match_method': 'manual',
                'match_score': float(row['fuzzy']),
                'reviewed_by_human': True,
            }

    def _plan_new_refs(self, plan, path, tier):
        rows = list(self._new_ref_rows(path, tier))
        pids = {r['problem_id'] for r in rows}
        existing = defaultdict(list)
        for ref in OlympiadRef.objects.filter(problem_id__in=pids):
            existing[ref.problem_id].append(ref)
        problems = set(Problem.objects.filter(pk__in=pids).values_list('pk', flat=True))
        seen = set()
        for row in rows:
            pid, event_id, number = row['problem_id'], row['event_id'], row['number']
            key = f'{pid}/{event_id}#{number}'
            if row.get('unconfirmed'):
                plan.skip(key, 'нет в таблице подтверждений файла проверки')
                continue
            task = self.reference.tasks.get((event_id, number))
            if task is None:
                plan.skip(key, 'задания нет в эталоне')
                continue
            if pid not in problems:
                plan.skip(key, 'задачи нет в базе')
                continue
            if (pid, event_id) in seen or any(
                    r.event_id == event_id for r in existing[pid]):
                plan.skip(key, 'у задачи уже есть строка с этим event_id')
                continue
            year, grade = int(task['year']), task['grade']
            same = [r for r in existing[pid] if r.olympiad_slug in VP_FAMILY
                    and r.year == year and _grades_overlap(r.grade, grade)]
            if same:
                # Вторую строку ВП того же тура не заводим — дописываем первую.
                ref = same[0]
                meta = dict(ref.raw_meta or {})
                if ref.official_url != task['source_url']:
                    meta.setdefault('aggregator_url', ref.official_url)
                    plan.update(ref, 'official_url', task['source_url'],
                                'вместо новой: ссылка на PDF')
                if ref.number != number:
                    meta.setdefault('aggregator_number', ref.number)
                    plan.update(ref, 'number', number, 'вместо новой: номер')
                meta['official_event_id'] = event_id
                plan.update(ref, 'raw_meta', meta, 'вместо новой: raw_meta')
                plan.notes.append(f'{key}: уже есть строка ВП ref {ref.id} '
                                  f'того же года и класса — обновляется она')
                continue
            other = [r for r in existing[pid] if r.olympiad_slug not in VP_FAMILY
                     and r.year != year]
            if other:
                plan.skip(key, 'у задачи строка другой олимпиады другого года '
                               f'({other[0].olympiad_slug} {other[0].year})')
                continue
            seen.add((pid, event_id))
            plan.creates.append({
                'problem_id': pid,
                'source_site': 'official',
                'olympiad_slug': 'vp',
                'olympiad_name': OLYMPIAD_NAMES['vp'],
                'academic_year': bank_academic_year(task['academic_year']),
                'year': year,
                'stage': 'final',
                'grade': grade,
                'variant': variant_of(event_id),
                'number': number,
                'event_id': event_id,
                'record_id': f'official:{event_id}:{number}',
                'match_method': row['match_method'],
                'match_score': row['match_score'],
                'official_url': task['source_url'],
                'raw_meta': row['raw_meta'],
                'reviewed_by_human': row['reviewed_by_human'],
            })

    # ── Правки существующих строк ───────────────────────────────────────

    def _plan_updates(self, plan, path):
        if not self.options['confirmed_by']:
            raise CommandError('--update-existing требует --confirmed-by '
                               '(список перенумеровок «на глаза»)')
        _high, eyeball = parse_claude_review(self.options['confirmed_by'])
        rows = read_csv(path)
        refs = OlympiadRef.objects.in_bulk([int(r['ref_id']) for r in rows])
        need_text = {int(r['problem_id']) for r in rows
                     if r['coord_status'] in ('other_event', 'number_shifted_same_event')}
        texts = {p.pk: bank_norm_text(p) for p in
                 Problem.objects.filter(pk__in=need_text).prefetch_related('parts')}
        siblings = defaultdict(list)
        for ref in OlympiadRef.objects.filter(
                problem_id__in={int(r['problem_id']) for r in rows},
                olympiad_slug__in=VP_FAMILY):
            siblings[ref.problem_id].append(ref)
        self.twin_stats = Counter()

        for row in rows:
            ref = refs.get(int(row['ref_id']))
            key = f'ref {row["ref_id"]} (задача {row["problem_id"]})'
            action = row['action']
            if ref is None or ref.problem_id != int(row['problem_id']):
                plan.skip(key, 'строки нет или она о другой задаче')
                continue
            if action.startswith('move_slug'):
                plan.update(ref, 'olympiad_slug', row['proposed_slug'], 'move_slug')
                plan.update(ref, 'olympiad_name',
                            OLYMPIAD_NAMES[row['proposed_slug']], 'move_slug: название')
                continue
            if ref.olympiad_slug != 'vp':
                plan.skip(key, f'слаг строки {ref.olympiad_slug}, а не vp')
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
                self._plan_renumber(plan, ref, row, key, eyeball, texts)
            elif status == 'other_event':
                self._plan_twin(plan, ref, row, key, texts, siblings)
            else:
                plan.skip(key, f'неизвестный coord_status {status!r}')

    def _official_fields(self, plan, ref, event_id, url, grade, kind, meta):
        """Общая часть: этап, класс (если пуст), ссылка на PDF, id комплекта."""
        if not ref.stage:
            plan.update(ref, 'stage', 'final', f'{kind}: этап')
        if not ref.grade and grade:
            plan.update(ref, 'grade', grade, f'{kind}: класс')
        if url and ref.official_url != url:
            if ref.official_url and 'hse.ru' not in ref.official_url:
                meta.setdefault('aggregator_url', ref.official_url)
            plan.update(ref, 'official_url', url, f'{kind}: ссылка на PDF')
        meta['official_event_id'] = event_id

    def _plan_coords_ok(self, plan, ref, row):
        meta = dict(ref.raw_meta or {})
        event_id = row['official_event_id']
        action = row['action']
        if 'set_stage' in action and not ref.stage:
            plan.update(ref, 'stage', row['proposed_stage'] or 'final', 'coords_ok: этап')
        if 'fill_grade' in action and not ref.grade and row['proposed_grade']:
            plan.update(ref, 'grade', row['proposed_grade'], 'coords_ok: класс')
        url = row['proposed_official_url']
        if 'set_official_url' in action and url and ref.official_url != url:
            if ref.official_url and 'hse.ru' not in ref.official_url:
                meta.setdefault('aggregator_url', ref.official_url)
            plan.update(ref, 'official_url', url, 'coords_ok: ссылка на PDF')
        if event_id:
            meta['official_event_id'] = event_id
        plan.update(ref, 'raw_meta', meta, 'coords_ok: raw_meta')

    def _plan_renumber(self, plan, ref, row, key, eyeball, texts):
        event_id, new = row['official_event_id'], row['proposed_number']
        if ref.problem_id in eyeball and not self.options['include_eyeball']:
            if ref.number != new:
                plan.skip(key, 'перенумеровка «на глаза» — нужен --include-eyeball')
            return
        old = ref.number
        if old != new:
            # Сверка текста: под новым номером сходство обязано быть выше.
            bank = texts.get(ref.problem_id, '')
            new_task = self.reference.tasks.get((event_id, new))
            old_task = self.reference.tasks.get((event_id, old))
            if new_task is None:
                plan.skip(key, f'в эталоне нет {event_id} №{new}')
                return
            s_new = fuzzy_ratio(bank, new_task['norm_text'])
            s_old = fuzzy_ratio(bank, old_task['norm_text']) if old_task else 0.0
            if s_new <= s_old:
                plan.skip(key, f'сверка текста не подтвердила №{new} '
                               f'({s_new:.3f} против {s_old:.3f})')
                return
        meta = dict(ref.raw_meta or {})
        if old != new:
            meta.setdefault('aggregator_number', old)
            plan.update(ref, 'number', new, 'renumber: номер')
        task = self.reference.tasks[(event_id, new)]
        self._official_fields(plan, ref, event_id, task['source_url'],
                              task['grade'], 'renumber', meta)
        plan.update(ref, 'raw_meta', meta, 'renumber: raw_meta')

    def _plan_twin(self, plan, ref, row, key, texts, siblings):
        parsed = parse_other_event_reason(row['reason'])
        if not parsed:
            plan.skip(key, 'не разобрана причина other_event')
            return
        found_ev, found_no, own_ev, _own_no = parsed
        bank = texts.get(ref.problem_id, '')
        number, score = self.reference.best_in_event(bank, own_ev)
        if score < TWIN_THRESHOLD and self.options['twin_pdf_to_pdf']:
            # Текст банка не дотянул до своего комплекта (шапка «(20 баллов)»
            # против «(25 баллов)», вёрстка PDF) — сравниваем найденное
            # задание соседнего класса с заданиями своего: два PDF одной
            # вёрстки между собой.
            found_text = self.reference.tasks[(found_ev, found_no)]['norm_text']
            number, score = self.reference.best_in_event(found_text, own_ev)
        meta = dict(ref.raw_meta or {})
        if score >= TWIN_THRESHOLD:
            self.twin_stats['класс верен (близнец)'] += 1
            event_id = own_ev
        else:
            # Класс неверен: переводим строку на комплект, где нашёлся текст.
            event_id, number = found_ev, found_no
            new_grade = self.reference.tasks[(found_ev, found_no)]['grade']
            clash = [r for r in siblings[ref.problem_id] if r.id != ref.id
                     and r.year == ref.year and _grades_overlap(r.grade, new_grade)
                     and r.grade]
            if clash:
                plan.skip(key, f'исправление класса на {new_grade} дало бы вторую '
                               f'строку ВП того же тура (ref {clash[0].id})')
                self.twin_stats['класс исправить — пропущено (вторая строка)'] += 1
                return
            self.twin_stats['класс исправить'] += 1
            if ref.grade != new_grade:
                meta.setdefault('aggregator_grade', ref.grade)
                plan.update(ref, 'grade', new_grade, 'близнец: класс исправлен')
        task = self.reference.tasks[(event_id, number)]
        if ref.number != number:
            meta.setdefault('aggregator_number', ref.number)
            plan.update(ref, 'number', number, 'близнец: номер по PDF')
        self._official_fields(plan, ref, event_id, task['source_url'],
                              task['grade'], 'близнец', meta)
        plan.update(ref, 'raw_meta', meta, 'близнец: raw_meta')

    # ── Импорт недостающих заданий ─────────────────────────────────────

    def _plan_import(self, plan, path):
        source = Source.objects.filter(name=OFFICIAL_SOURCE_NAME).first()
        if source is None:
            plan.notes.append(f'Source «{OFFICIAL_SOURCE_NAME}» не заведён — '
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
        self.invariants = {
            'две новые строки на одну пару (задача, event_id)': len(doubled),
            'новая строка при существующей паре (задача, event_id)': len(clash),
        }
        if doubled or clash:
            raise CommandError(f'Нарушен инвариант: {self.invariants}')

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
        source = Source.objects.filter(name=OFFICIAL_SOURCE_NAME).first()
        if source is None:
            raise CommandError(f'Нет Source «{OFFICIAL_SOURCE_NAME}»: '
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
        note = (f'Заключительный этап, {row["grade"]} класс, задание {number}; '
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
        sref.stage, sref.grade = 'Заключительный этап', row['grade']
        sref.save(update_fields=['stage', 'grade'])
        journal['created_sourceref_ids'].append(sref.id)
        if figure:
            fig = ProblemFigure.objects.create(
                problem=problem, tikz_hash=figure[0], tikz_source=figure[1],
                svg='', image_data=figure[2], content_type='image/png',
                source_field='statement')
            journal['created_figure_ids'].append(fig.id)
        ref = OlympiadRef.objects.create(
            problem=problem, source_site='official', olympiad_slug='vp',
            olympiad_name=OLYMPIAD_NAMES['vp'],
            academic_year=bank_academic_year(row.get('academic_year')),
            year=year, stage='final', grade=row['grade'],
            variant=variant_of(event_id), number=number, event_id=event_id,
            record_id=f'official:{event_id}:{number}',
            # Ссылка источника задачи и ссылка привязки — один и тот же PDF.
            match_method='url_exact', match_score=1.0,
            official_url=row['source_url'],
            raw_meta={'session': SESSION, 'origin': 'import_official_pdf',
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

    # ── Откат ───────────────────────────────────────────────────────────

    def _rollback(self, path):
        with open(path, encoding='utf-8') as handle:
            journal = json.load(handle)
        if not journal.get('applied'):
            raise CommandError('Это журнал сухого прогона — откатывать нечего.')
        restore, conflicts = [], []
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
        w(f'  вернуть полей: {len(restore)}; конфликтов: {len(conflicts)}')
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
        after = _counts()
        out = os.path.join(os.path.dirname(os.path.abspath(path)),
                           'rollback_' + os.path.basename(path))
        with open(out, 'w', encoding='utf-8') as handle:
            json.dump({'journal': os.path.abspath(path), 'restored': len(restore),
                       'conflicts': conflicts, 'deleted_problems': str(deleted),
                       'counts_before': before, 'counts_after': after},
                      handle, ensure_ascii=False, indent=1)
        w(self.style.SUCCESS(f'Откат выполнен. Отчёт: {out}'))
        for name, value in after.items():
            w(f'  {name}: {value} ({value - before[name]:+d})')


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
