# -*- coding: utf-8 -*-
"""Импорт олимпиады в банк из оцифрованного эталона (v2 и дальше).

    import_olympiad_reference --olympiad vp-fingram --queue <...>\\import_queue_v2.jsonl --build-candidates
    import_olympiad_reference --olympiad vp-fingram --queue <...>\\import_queue_v2.jsonl
    import_olympiad_reference ... --apply --yes-i-have-owner-approval
    import_olympiad_reference --olympiad vp-fingram --rollback <журнал.json> [--apply --yes-…]

Вход — очередь импорта (`import_queue_vN.jsonl`) или сам эталон
(`reference_problems_vN.jsonl`): строка = задание с markdown-условием,
пунктами, рисунками, решением, ответом, критериями. Олимпиада — из реестра
(`problems/olympiad_audit/registry.py`), команда общая для всех.

Для каждой строки план — одно из четырёх:

* **создать** новую задачу. Видимой (published + `human_review=approved`
  через `ReviewVerdict` perfect от `auto:strict_check`, пакет
  `auto_import_<слаг>_<дата>`) — только если строгая автопроверка уверена
  (`auto_publish_ok`) и KaTeX новых текстов без ошибок; иначе скрытой
  (`draft` + `hidden_pending_review`) и в `human_tasks_import.csv`;
  задание-близнец соседнего класса того же сезона (текст ≥ 0,90) не
  создаёт копию — вторая привязка к той же новой задаче;
* **привязать** к задаче банка: гибрид сайта top-20 + текст ≥ 0,90 +
  числа (решения 09.10 и 02.09); новая строка `OlympiadRef` official и
  дописывание ТОЛЬКО ПУСТЫХ ответа / решения (ADR 0005);
* **на проверку** (`link_review.csv`): сходство 0,80–0,90, конфликт класса
  или олимпиады, слабый числовой отпечаток;
* **пропустить** с причиной.

Сухой прогон по умолчанию; запись — `--apply --yes-i-have-owner-approval`.
Журнал записи — id всего созданного и [{id, поле, old, new}] дописанного;
`--rollback` возвращает базу до единицы. Правила текста (пункты, критерии,
рисунки, разметка) — `problems/olympiad_audit/reference_import.py`.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
from collections import Counter, defaultdict
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from problems.corpus_converter.ingest import create_problem
from problems.models import (
    OlympiadRef, Problem, ProblemFigure, ProblemPart, ReviewVerdict, Source,
    SourceReference,
)
from problems.olympiad_audit import bank_match, registry
from problems.olympiad_audit import reference_import as ri
from problems.olympiad_grades import parse_grades
from problems.olympiad_official import (
    OLYMPIAD_NAMES, bank_academic_year, markup_free_key, read_jsonl, variant_of,
)
from problems.text_dedup import problem_identity_text

APPROVAL_FLAG = '--yes-i-have-owner-approval'
EXAMPLES = 3
AUTO_REVIEWER = 'auto:strict_check'
AUTO_COMMENT = ('Автопубликация импорта из эталона: каждая страница задания чиста по '
                'судье или по слою ≥ 0,95 и числам; есть ответ при файле решений; '
                'условие не пустое; KaTeX без ошибок; рисунки без флага; нет '
                'служебного блока (tools/p5s2_queue.py, решения владельца 13–14.10.2026).')
ORIGIN = 'import_reference_v2'
FILL_FIELDS = ('answer', 'solution')


def _counts(slug):
    from catalog.filters import base_queryset
    return {
        'Problem': Problem.objects.count(),
        'видимых в каталоге': base_queryset('catalog').count(),
        'ProblemPart': ProblemPart.objects.count(),
        'SourceReference': SourceReference.objects.count(),
        'ProblemFigure': ProblemFigure.objects.count(),
        'OlympiadRef': OlympiadRef.objects.count(),
        f'OlympiadRef({slug})': OlympiadRef.objects.filter(olympiad_slug=slug).count(),
        'ReviewVerdict': ReviewVerdict.objects.count(),
        'human_review=approved': Problem.objects.filter(
            human_review=Problem.HumanReview.APPROVED).count(),
    }


def _grades_overlap(a, b):
    if not a or not b:
        return True
    return bool(parse_grades(a) & parse_grades(b))


class Command(BaseCommand):
    help = ('Импорт олимпиады в банк из оцифрованного эталона. Сухой прогон по '
            f'умолчанию; запись — --apply {APPROVAL_FLAG}.')

    def add_arguments(self, parser):
        parser.add_argument('--olympiad', choices=sorted(registry.REGISTRY))
        parser.add_argument('--queue', metavar='JSONL',
                            help='import_queue_vN.jsonl или reference_problems_vN.jsonl')
        parser.add_argument('--digitized', metavar='DIR',
                            help='папка эталона (пути рисунков — от неё); по умолчанию '
                                 '<папка очереди>\\digitized или папка файла')
        parser.add_argument('--reference', metavar='JSONL',
                            help='весь эталон для правила близнецов; по умолчанию '
                                 'reference_problems_v2.jsonl в --digitized')
        parser.add_argument('--candidates', metavar='JSON',
                            help='кандидаты гибридного поиска; по умолчанию '
                                 '<out-dir>\\bank_candidates.json')
        parser.add_argument('--build-candidates', action='store_true',
                            help='посчитать кандидатов (модель BGE-M3 + BM25) и выйти')
        parser.add_argument('--out-dir', metavar='DIR',
                            help='журналы и таблицы; по умолчанию <папка очереди>\\import_journal')
        parser.add_argument('--bundle-date', default=datetime.now().strftime('%Y%m%d'),
                            help='дата в имени пакета автоодобрения')
        parser.add_argument('--no-katex', action='store_true',
                            help='не запускать KaTeX-проверку (только тесты/отладка)')
        parser.add_argument('--rollback', metavar='JOURNAL')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument(APPROVAL_FLAG, dest='approved', action='store_true')

    # ── Вход ────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        self.options = options
        self.apply = options['apply']
        if not options.get('olympiad'):
            raise CommandError('--olympiad <слаг> обязателен. Ничего не сделано.')
        self.olympiad = registry.get(options['olympiad'])
        self.slug = self.olympiad.slug
        if self.apply and not options['approved']:
            raise CommandError(f'--apply требует {APPROVAL_FLAG}. Ничего не записано.')
        if options['rollback']:
            return self._rollback(options['rollback'])
        queue = options['queue']
        if not queue or not os.path.isfile(queue):
            raise CommandError(f'Нет файла очереди: {queue!r} (--queue)')
        self.queue_path = os.path.abspath(queue)
        qdir = os.path.dirname(self.queue_path)
        self.digitized = options['digitized'] or (
            os.path.join(qdir, 'digitized') if os.path.isdir(os.path.join(qdir, 'digitized'))
            else qdir)
        self.subdir = os.path.dirname(self.digitized) if os.path.basename(
            self.digitized) == 'digitized' else qdir
        self.out_dir = options['out_dir'] or os.path.join(qdir, 'import_journal')
        os.makedirs(self.out_dir, exist_ok=True)
        rows = read_jsonl(self.queue_path)
        alien = {r.get('olympiad_slug') for r in rows} - {None, '', self.slug}
        if alien:
            raise CommandError(f'В очереди строки другой олимпиады: {sorted(alien)}')
        cand_path = options['candidates'] or os.path.join(self.out_dir, 'bank_candidates.json')
        if options['build_candidates']:
            meta = bank_match.build_candidates(rows, cand_path, log=self.stdout.write)
            self.stdout.write(self.style.SUCCESS(f'Кандидаты: {cand_path} {meta}'))
            return
        if not os.path.isfile(cand_path):
            raise CommandError(f'Нет кандидатов {cand_path}: сначала --build-candidates')
        self.cand_meta, self.candidates = bank_match.load_candidates(cand_path)
        self.url_map = ri.load_url_map(self.subdir)
        ref_path = options['reference'] or os.path.join(self.digitized,
                                                        'reference_problems_v2.jsonl')
        self.reference = read_jsonl(ref_path) if os.path.isfile(ref_path) else []
        self.inputs = {'olympiad': self.slug, 'queue': self.queue_path,
                       'digitized': os.path.abspath(self.digitized),
                       'candidates': os.path.abspath(cand_path),
                       'candidates_meta': self.cand_meta,
                       'reference': os.path.abspath(ref_path) if self.reference else '',
                       'bundle': self._bundle(), 'database': str(settings.DATABASES['default']['NAME'])}

        plan = self._plan(rows)
        if not options['no_katex']:
            self._katex(plan)
        self._finalize(plan)
        self._check_invariants(plan, rows)
        self._write_tables(plan)
        self._print_plan(plan, rows)
        if not self.apply:
            self._dump(self._journal(plan, applied=False), '_dryrun')
            self.stdout.write(self.style.WARNING('СУХОЙ ПРОГОН — в базе ничего не изменено.'))
            return
        if options['no_katex']:
            self.stdout.write(self.style.WARNING('KaTeX не проверялся (--no-katex).'))
        self._apply(plan)

    def _bundle(self):
        return f'auto_import_{self.slug}_{self.options["bundle_date"]}'

    # ── План ────────────────────────────────────────────────────────────

    def _plan(self, rows):
        source = Source.objects.filter(name=self.olympiad.official_source_name).first()
        self.source = source
        done = set(SourceReference.objects.filter(source=source)
                   .values_list('problem_number', flat=True)) if source else set()
        # Пары (задание эталона) → задача, уже привязанные в банке: строка с
        # официальным event_id или строка агрегатора, переведённая на него.
        events = {r['event_id'] for r in rows}
        taken = {}
        for ref in OlympiadRef.objects.filter(
                Q(event_id__in=events) | Q(raw_meta__official_event_id__in=list(events))):
            ev = (ref.raw_meta or {}).get('official_event_id') or ref.event_id
            variant = (ref.raw_meta or {}).get('official_task_variant') or ''
            if not variant and ref.source_site == 'official' and ref.record_id.count(':') >= 3:
                variant = ref.record_id.split(':', 3)[3]      # official:<ev>:<№>:<вариант>
            taken.setdefault((ev, ref.number, variant), ref.problem_id)
            for n in (ref.raw_meta or {}).get('kit_numbers') or []:
                taken.setdefault((ev, str(n), variant), ref.problem_id)
        # Банк: кандидаты всех строк + подсказки очереди (сверка 13.10).
        pids = set()
        for row in rows:
            pids.update(self.candidates.get(bank_match.row_key(row), []))
            for hint in ('best_bank_problem_id', 'containment_problem_id'):
                if row.get(hint):
                    pids.add(int(row[hint]))
        self.bank = {}
        for p in Problem.objects.filter(pk__in=pids).prefetch_related(
                'parts', 'olympiad_refs', 'source_references__source'):
            ident = problem_identity_text(p)
            self.bank[p.pk] = {'key': markup_free_key(ident), 'text': ident, 'obj': p,
                               'refs': list(p.olympiad_refs.all()),
                               'source': ', '.join(sorted({s.source.name for s in
                                                           p.source_references.all()})) or '—'}
        bank_keys = {pid: b['key'] for pid, b in self.bank.items()}
        ref_by_event = defaultdict(list)
        for r in self.reference:
            ref_by_event[(int(r['year']), r.get('stage') or 'final')].append(r)

        # Сверка всех строк заранее: «комплект одной задачей» виден только по
        # группе. Если ДВА И БОЛЕЕ задания одного комплекта целиком (≥ 0,90)
        # сидят в одной задаче банка, которая заметно длиннее задания, — это
        # комплект агрегатора (SolveHub хранит ВП-бизнес так): несколько
        # независимых текстовых совпадений сильнее числового отпечатка.
        matches, groups = {}, defaultdict(list)
        for row in rows:
            key = bank_match.row_key(row)
            cands = list(self.candidates.get(key, []))
            hints = [int(row[h]) for h in ('best_bank_problem_id', 'containment_problem_id')
                     if row.get(h)]
            pid, ratio, contain = bank_match.best_match(row, cands + hints, bank_keys)
            matches[key] = (pid, ratio, contain,
                            ('гибрид' if pid in cands else 'подсказка очереди') if pid else '')
            if pid and contain >= ri.LINK_THRESHOLD and ratio < ri.LINK_THRESHOLD \
                    and len(bank_keys[pid]) >= 1.3 * len(bank_match.task_key(row)):
                groups[(pid, row['event_id'])].append(str(row['number']))
        self.kits = {k: v for k, v in groups.items() if len(v) >= 2}

        items, linked_pairs, creates = [], {}, []
        short = registry.short_name(self.slug)
        for row in rows:
            key = bank_match.row_key(row)
            item = {'key': key, 'row': row, 'action': None, 'reason': '',
                    'pid': None, 'ratio': 0.0, 'contain': 0.0, 'via': ''}
            items.append(item)
            variant = row.get('task_variant') or ''
            if key in done:
                self._set(item, 'skip', 'уже импортировано (SourceReference)')
                continue
            if not (row.get('statement_md') or '').strip():
                self._set(item, 'skip', 'пустое условие')
                continue
            if any('служебн' in f for f in row.get('auto_publish_fail') or []):
                self._set(item, 'skip', 'служебный блок')
                continue
            owner = taken.get((row['event_id'], str(row['number']), variant))
            if owner:
                self._set(item, 'skip', f'пара уже есть (задача #{owner})')
                item['pid'] = owner
                continue
            pid, ratio, contain, via = matches[key]
            item.update(pid=pid, ratio=round(ratio, 4), contain=round(contain, 4), via=via)
            score = max(ratio, contain)
            if score >= ri.LINK_THRESHOLD:
                self._plan_link(item, row, linked_pairs, ref_by_event, bank_keys)
            elif score >= ri.DOUBT_THRESHOLD:
                self._set(item, 'review', f'сомнительное сходство {score:.2f} (0,80–0,90)')
            else:
                item['fields'] = ri.build_fields(row, digitized_dir=self.digitized,
                                                 url_map=self.url_map, olympiad_short=short)
                twin = self._twin_of(row, creates)
                if twin:
                    self._set(item, 'twin', f'близнец задания {twin["key"]} (тот же текст '
                                            'в комплекте соседнего класса)')
                    item['twin_of'] = twin['key']
                else:
                    self._set(item, 'create', '')
                    creates.append(item)
        return items

    @staticmethod
    def _set(item, action, reason):
        item['action'], item['reason'] = action, reason

    def _twin_of(self, row, creates):
        """Уже запланированная новая задача того же сезона и этапа с тем же
        текстом (≥ 0,90, числа согласны) в комплекте другого класса."""
        key = bank_match.task_key(row)
        for other in creates:
            o = other['row']
            if (o['year'], o.get('stage')) != (row['year'], row.get('stage')) \
                    or o['event_id'] == row['event_id']:
                continue
            ratio, _c = bank_match.scores(key, bank_match.task_key(o))
            if ratio >= ri.LINK_THRESHOLD and bank_match.numbers_compatible(
                    bank_match.task_text(row), bank_match.task_text(o)):
                return other
        return None

    def _plan_link(self, item, row, linked_pairs, ref_by_event, bank_keys):
        pid = item['pid']
        bank = self.bank[pid]
        event_id, year = row['event_id'], int(row['year'])
        stage = row.get('stage') or 'final'
        for ref in bank['refs']:
            ev = (ref.raw_meta or {}).get('official_event_id') or ref.event_id
            if ev == event_id:
                self._set(item, 'skip', f'пара уже есть (задача #{pid}, ref {ref.id})')
                return
        other = [r for r in bank['refs'] if r.olympiad_slug != self.slug]
        if other:
            r = other[0]
            self._set(item, 'review', f'у задачи банка строка другой олимпиады '
                                      f'({r.olympiad_slug} {r.year})')
            return
        same = [r for r in bank['refs'] if r.olympiad_slug == self.slug]
        if any(r.year and r.year != year for r in same):
            r = next(r for r in same if r.year and r.year != year)
            self._set(item, 'review', f'у задачи банка строка этой олимпиады другого года ({r.year})')
            return
        clash = [r for r in same if r.year == year and not _grades_overlap(r.grade, row['grade'])]
        if clash:
            # Близнец: то же задание есть в комплекте класса строки банка.
            g = clash[0].grade
            twins = [t for t in ref_by_event.get((year, stage), [])
                     if _grades_overlap(t['grade'], g) and t['event_id'] != event_id
                     and max(bank_match.scores(bank_match.task_key(t), bank_keys[pid]))
                     >= ri.LINK_THRESHOLD]
            if not twins:
                self._set(item, 'review', f'конфликт класса: задача банка — {g} кл., '
                                          f'задание — {row["grade"]} кл., близнеца нет')
                return
        kit = self.kits.get((pid, event_id)) if item['ratio'] < ri.LINK_THRESHOLD else None
        if kit is None or str(row['number']) not in kit:
            signal = bank_match.numbers_signal(bank_match.task_text(row))
            if signal != 'ok':
                self._set(item, 'review', f'weak_numeric_signal (чисел: {signal}) — '
                                          'текст один не доказательство')
                return
            if not bank_match.numbers_compatible(bank_match.task_text(row), bank['text']):
                self._set(item, 'review', 'числа задания и задачи банка не согласуются')
                return
        first = linked_pairs.get((pid, event_id))
        if first:
            self._set(item, 'skip', f'входит в ту же задачу банка #{pid}, что и задание '
                                    f'{first["row"]["number"]} (комплект одной задачей)')
            return
        linked_pairs[(pid, event_id)] = item
        if kit and str(row['number']) in kit:
            item['kit_numbers'] = kit
            self._set(item, 'link', f'комплект одной задачей: внутри заданий {len(kit)} '
                                    f'({", ".join(kit)})')
        else:
            self._set(item, 'link', 'сходство' if item['ratio'] >= ri.LINK_THRESHOLD
                      else 'вхождение')
        item['fill'], item['fill_skipped'] = self._fills(item, row, bank['obj'])

    def _fills(self, item, row, problem):
        """Пустые поля задачи банка, которые дописываются из эталона.

        Только при совпадении ЦЕЛОГО текста (сходство ≥ 0,90): при вхождении
        задача банка — комплект или кусок, и ответ одного задания ей чужой.
        Только у markdown-задач: plain покажет разметку эталона буквально."""
        fills, skipped = {}, []
        fields = ri.build_fields(row, digitized_dir=self.digitized, url_map=self.url_map,
                                 olympiad_short=registry.short_name(self.slug))
        item['fields'] = fields
        new = {'answer': (row.get('answer') and ri.adapt_markup(row['answer'])[0].strip()) or '',
               'solution': fields['solution']}
        for field in FILL_FIELDS:
            if (getattr(problem, field) or '').strip() or not new[field]:
                continue
            if item['ratio'] < ri.LINK_THRESHOLD:
                skipped.append(f'{field}: только вхождение — не дописываю')
            elif problem.content_format != Problem.ContentFormat.MARKDOWN:
                skipped.append(f'{field}: задача в формате {problem.content_format} — не дописываю')
            elif '[[FIGURE:' in new[field]:
                skipped.append(f'{field}: в тексте рисунок — не дописываю')
            else:
                fills[field] = new[field]
        return fills, skipped

    # ── KaTeX и видимость ───────────────────────────────────────────────

    def _texts(self, item):
        f = item['fields']
        if item['action'] == 'create':
            yield 'statement', f['statement']
            yield 'answer', f['answer']
            yield 'solution', f['solution']
            for p in f['parts']:
                yield f'part {p["label"]}', p['statement_md'] + '\n' + p['answer']
        elif item['action'] == 'link':
            for field, value in item.get('fill', {}).items():
                yield field, value

    def _katex(self, plan):
        queue = []
        for i, item in enumerate(plan):
            if item['action'] in ('create', 'link') and 'fields' in item:
                for field, text in self._texts(item):
                    if '$' in text or '\\(' in text or '\\[' in text:
                        queue.append({'kind': field, 'pid': i, 'pk': item['key'],
                                      'old': '', 'new': text})
        qpath = os.path.join(self.out_dir, 'katex_queue.json')
        opath = os.path.join(self.out_dir, 'katex_result.json')
        with open(qpath, 'w', encoding='utf-8') as handle:
            json.dump(queue, handle, ensure_ascii=False)
        if queue:
            script = os.path.join(settings.BASE_DIR, 'scripts', 'katex_render_check.js')
            done = subprocess.run(['node', script, '--queue', qpath, '--out', opath],
                                  cwd=settings.BASE_DIR, capture_output=True, text=True,
                                  encoding='utf-8')
            if done.returncode != 0:
                raise CommandError(f'KaTeX-проверка упала: {done.stderr[-800:]}')
            with open(opath, encoding='utf-8') as handle:
                results = json.load(handle)
        else:
            results = []
        bad = Counter()
        for r in results:
            if r['errors_new'] or r['red_new']:
                bad[r['pid']] += 1
        self.katex = {'fields': len(queue), 'bad_items': len(bad)}
        for i, n in bad.items():
            plan[i]['katex_errors'] = n

    def _finalize(self, plan):
        """Видимость новых задач и строки «человеку»."""
        for item in plan:
            if item['action'] == 'link' and item.get('katex_errors'):
                item['fill_skipped'] = item.get('fill_skipped', []) + [
                    f'KaTeX: {item["katex_errors"]} пол. с ошибкой — не дописываю']
                item['fill'] = {}
            if item['action'] != 'create':
                continue
            row = item['row']
            why = list(row.get('auto_publish_fail') or [])
            if item.get('katex_errors'):
                why.append(f'KaTeX новых текстов: {item["katex_errors"]} пол. с ошибкой')
            for fig in item['fields']['figures']:
                if not os.path.isfile(fig['path']):
                    why.append(f'нет файла рисунка {fig["path"]}')
            item['visible'] = bool(row.get('auto_publish_ok')) and not why
            item['hidden_why'] = why

    # ── Инварианты ──────────────────────────────────────────────────────

    def _check_invariants(self, plan, rows):
        actions = Counter(i['action'] for i in plan)
        refs_pairs = Counter()
        for i in plan:
            if i['action'] == 'link':
                refs_pairs[(i['pid'], i['row']['event_id'])] += 1
        figures = Counter(f['hash'] for i in plan if i['action'] == 'create'
                          for f in i['fields']['figures'])
        missing = [f['path'] for i in plan if i['action'] == 'create'
                   for f in i['fields']['figures'] if not os.path.isfile(f['path'])]
        nonempty = [(i['pid'], f) for i in plan if i['action'] == 'link'
                    for f in i.get('fill', {})
                    if (getattr(self.bank[i['pid']]['obj'], f) or '').strip()]
        self.invariants = {
            'строк очереди': len(rows),
            'создать + близнец + привязать + пропустить + на проверку': sum(actions.values()),
            'сумма сходится': sum(actions.values()) == len(rows),
            'дописывание непустого поля': len(nonempty),
            'две новые OlympiadRef на пару (задача, event_id)': sum(1 for n in refs_pairs.values() if n > 1),
            'рисунок в двух задачах': sum(1 for n in figures.values() if n > 1),
            'рисунков у новых задач': sum(figures.values()),
            'рисунков без файла': len(missing),
            'KaTeX': getattr(self, 'katex', 'не проверялся (--no-katex)'),
        }
        broken = (not self.invariants['сумма сходится'] or nonempty
                  or self.invariants['две новые OlympiadRef на пару (задача, event_id)']
                  or self.invariants['рисунок в двух задачах'])
        if broken:
            raise CommandError(f'Нарушен инвариант плана: {self.invariants}')

    # ── Таблицы и печать ────────────────────────────────────────────────

    def _write_tables(self, plan):
        def write(name, header, lines):
            path = os.path.join(self.out_dir, name)
            with open(path, 'w', encoding='utf-8-sig', newline='') as handle:
                w = csv.writer(handle)
                w.writerow(header)
                w.writerows(lines)
            return path

        def start(text, n=160):
            return ' '.join((text or '').split())[:n]

        def src(i):
            return self.bank[i['pid']]['source'] if i['pid'] in self.bank else ''

        write('plan.csv', ['key', 'действие', 'причина', 'видимо', 'задача банка',
                           'источник задачи банка', 'сходство', 'вхождение', 'кандидат из',
                           'дописать', 'не дописано'],
              [[i['key'], i['action'], i['reason'],
                i.get('visible', '') if i['action'] == 'create' else '',
                i['pid'] or '', src(i), i['ratio'], i['contain'], i['via'],
                ' '.join(i.get('fill', {})), '; '.join(i.get('fill_skipped', []))]
               for i in plan])
        write('human_tasks_import.csv',
              ['key', 'почему скрыта', 'страницы условия', 'начало условия'],
              [[i['key'], '; '.join(i['hidden_why']),
                ' '.join(os.path.basename(p) for p in i['row'].get('source_pages') or []),
                start(i['row'].get('statement_md'))]
               for i in plan if i['action'] == 'create' and not i['visible']])
        write('link_review.csv',
              ['key', 'причина', 'задача банка', 'источник задачи банка', 'сходство',
               'вхождение', 'кандидат из', 'начало задания', 'начало задачи банка'],
              [[i['key'], i['reason'], i['pid'] or '', src(i), i['ratio'], i['contain'], i['via'],
                start(i['row'].get('statement_md')),
                start(self.bank[i['pid']]['text']) if i['pid'] in self.bank else '']
               for i in plan if i['action'] == 'review'])

    def _print_plan(self, plan, rows):
        w = self.stdout.write
        w(f'\n=== import_olympiad_reference {self.slug}: '
          f'{"ЗАПИСЬ" if self.apply else "сухой прогон"} ===')
        w(f'Очередь: {self.queue_path} ({len(rows)} строк)')
        w(f'База: {settings.DATABASES["default"]["NAME"]}')
        w(f'Source «{self.olympiad.official_source_name}»: '
          f'{"id " + str(self.source.id) if self.source else "НЕ ЗАВЕДЁН"}')
        for name, value in _counts(self.slug).items():
            w(f'  {name}: {value}')
        a = Counter(i['action'] for i in plan)
        vis = sum(1 for i in plan if i['action'] == 'create' and i['visible'])
        fills = Counter(f for i in plan if i['action'] == 'link' for f in i.get('fill', {}))
        crit = sum(1 for i in plan if i['action'] == 'link'
                   and 'ритерии оценивания' in i.get('fill', {}).get('solution', ''))
        w('')
        w(f'создать, видимо       : {vis}')
        w(f'создать, скрыто       : {a["create"] - vis}')
        w(f'близнец (к новой)     : {a["twin"]}')
        w(f'привязать             : {a["link"]}  (дописать ответ {fills["answer"]}, '
          f'решение {fills["solution"]}, из них с критериями {crit})')
        w(f'на проверку           : {a["review"]}')
        w(f'пропустить            : {a["skip"]}')
        for action in ('create', 'twin', 'link', 'review', 'skip'):
            reasons = Counter(i['reason'] for i in plan if i['action'] == action)
            if not reasons:
                continue
            w(f'— {action}:')
            for reason, n in reasons.most_common(12):
                w(f'    {n} — {reason or "(новая задача)"}')
                for i in [x for x in plan if x['action'] == action and x['reason'] == reason][:EXAMPLES]:
                    extra = ''
                    if i['pid'] and action != 'twin':
                        extra = (f' → #{i["pid"]} [{self.bank.get(i["pid"], {}).get("source", "")}] '
                                 f'(сходство {i["ratio"]}, вхождение {i["contain"]}, {i["via"]})')
                    if action == 'create':
                        f = i['fields']
                        extra = (f' «{f["title"][:60]}» видимо={i["visible"]} пунктов {len(f["parts"])} '
                                 f'рисунков {len(f["figures"])}')
                    w(f'        {i["key"]}{extra}')
        by_src = Counter(self.bank[i['pid']]['source'] for i in plan if i['action'] == 'link')
        w(f'Привязки по источнику задачи банка: {dict(by_src)}')
        markup = Counter()
        for i in plan:
            if i['action'] == 'create':
                markup.update(i['fields']['markup'])
        w(f'Разметка приведена (новые задачи): {dict(markup)}')
        w(f'Инварианты: {self.invariants}')

    # ── Журнал ──────────────────────────────────────────────────────────

    def _journal(self, plan, applied):
        return {
            'command': 'import_olympiad_reference', 'olympiad': self.slug, 'applied': applied,
            'started_at': datetime.now().isoformat(timespec='seconds'),
            'inputs': self.inputs, 'counts_before': _counts(self.slug),
            'invariants': self.invariants,
            'plan': [{'key': i['key'], 'action': i['action'], 'reason': i['reason'],
                      'visible': i.get('visible'), 'pid': i['pid'], 'ratio': i['ratio'],
                      'contain': i['contain'], 'fill': sorted(i.get('fill', {})),
                      'hidden_why': i.get('hidden_why', [])} for i in plan],
            'created_problem_ids': [], 'created_part_ids': [], 'created_sourceref_ids': [],
            'created_figure_ids': [], 'created_ref_ids': [], 'created_verdict_ids': [],
            'filled': [], 'visible_problem_ids': [],
            'how_to_revert': ('manage.py import_olympiad_reference --olympiad <слаг> '
                              '--rollback <этот файл> [--apply --yes-i-have-owner-approval]'),
        }

    def _dump(self, journal, suffix):
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(self.out_dir, f'import_{self.slug}_{stamp}{suffix}.json')
        n = 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(self.out_dir, f'import_{self.slug}_{stamp}-{n}{suffix}.json')
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(journal, handle, ensure_ascii=False, indent=1, default=str)
        self.stdout.write(f'Журнал: {path}')
        return path

    # ── Запись ──────────────────────────────────────────────────────────

    def _apply(self, plan):
        if self.source is None:
            raise CommandError(f'Нет Source «{self.olympiad.official_source_name}»: '
                               f'olympiad_official_sources --olympiad {self.slug} --apply')
        journal = self._journal(plan, applied=True)
        by_key = {}
        try:
            for item in plan:
                if item['action'] == 'create':
                    created = defaultdict(list)
                    with transaction.atomic():
                        pid = self._create(item, created)
                    by_key[item['key']] = pid
                    for k, ids in created.items():
                        journal[k].extend(ids)
            for item in plan:
                if item['action'] == 'twin':
                    created = defaultdict(list)
                    with transaction.atomic():
                        self._twin(item, by_key[item['twin_of']], created)
                    for k, ids in created.items():
                        journal[k].extend(ids)
                elif item['action'] == 'link':
                    created = defaultdict(list)
                    with transaction.atomic():
                        self._link(item, created)
                    for k, ids in created.items():
                        journal[k].extend(ids)
        except Exception as error:
            journal['error'] = repr(error)
            raise
        finally:
            journal['counts_after'] = _counts(self.slug)
            journal['finished_at'] = datetime.now().isoformat(timespec='seconds')
            path = self._dump(journal, '')
        self.stdout.write(self.style.SUCCESS(
            f'ЗАПИСАНО: задач {len(journal["created_problem_ids"])} (видимых '
            f'{len(journal["visible_problem_ids"])}), строк OlympiadRef '
            f'{len(journal["created_ref_ids"])}, дописано полей {len(journal["filled"])}.'))
        for name, value in journal['counts_after'].items():
            self.stdout.write(f'  {name}: {value} ({value - journal["counts_before"][name]:+d})')
        self.stdout.write(f'Откат: import_olympiad_reference --olympiad {self.slug} --rollback {path}')

    @staticmethod
    def _with_variant(meta, row):
        if row.get('task_variant'):
            meta['official_task_variant'] = row['task_variant']
        return meta

    def _ref_fields(self, row, url):
        event_id, number = row['event_id'], str(row['number'])
        variant = row.get('task_variant') or ''
        return dict(
            source_site='official', olympiad_slug=self.slug,
            olympiad_name=OLYMPIAD_NAMES[self.slug],
            academic_year=bank_academic_year(row.get('academic_year')),
            year=int(row['year']), stage=row.get('stage') or 'final', grade=row['grade'],
            variant=variant_of(event_id), number=number, event_id=event_id,
            record_id=f'official:{event_id}:{number}' + (f':{variant}' if variant else ''),
            official_url=url, reviewed_by_human=False)

    def _sref(self, problem, row, fields, created):
        number = str(row['number'])
        sref = SourceReference.objects.create(
            problem=problem, source=self.source, problem_number=bank_match.row_key(row)[:50],
            stage=fields['stage_label'], grade=row['grade'], year=int(row['year']),
            url=fields['source_url'],
            note=(f'{fields["stage_label"]}, {row["grade"]} класс, задание {number}; '
                  f'максимум {row.get("max_score")} баллов')[:300])
        created['created_sourceref_ids'].append(sref.id)

    def _create(self, item, created):
        row, f = item['row'], item['fields']
        problem = create_problem(
            source=self.source, external_id=bank_match.row_key(row), title=f['title'],
            statement_md=f['statement'], answer_md=f['answer'], solution_md=f['solution'],
            parts=[{'label': p['label'], 'statement_md': p['statement_md'], 'answer': p['answer']}
                   for p in f['parts']],
            reference_note=(f'{f["stage_label"]}, {row["grade"]} класс, задание {row["number"]}; '
                            f'максимум {row.get("max_score")} баллов'),
            reference_url=f['source_url'], reference_year=int(row['year']))
        created['created_problem_ids'].append(problem.id)
        parts = list(problem.parts.order_by('order'))
        for part, plan_part in zip(parts, f['parts']):
            if plan_part['points'] is not None:
                part.points = plan_part['points']
                part.save(update_fields=['points'])
        created['created_part_ids'].extend(p.id for p in parts)
        sref = problem.source_references.get(source=self.source)
        sref.stage, sref.grade = f['stage_label'], row['grade']
        sref.save(update_fields=['stage', 'grade'])
        created['created_sourceref_ids'].append(sref.id)
        problem.content_format = Problem.ContentFormat.MARKDOWN
        problem.problem_type = f['problem_type']
        if item['visible']:
            problem.status = Problem.Status.PUBLISHED
            problem.hidden_pending_review = False
            problem.human_review = Problem.HumanReview.APPROVED
        problem.save(update_fields=['content_format', 'problem_type', 'status',
                                    'hidden_pending_review', 'human_review'])
        for fig in f['figures']:
            with open(fig['path'], 'rb') as handle:
                data = handle.read()
            figure = ProblemFigure.objects.create(
                problem=problem, tikz_hash=fig['hash'], tikz_source=fig['ref'], svg='',
                image_data=data, content_type='image/png', source_field=fig['field'])
            created['created_figure_ids'].append(figure.id)
        meta = {'origin': ORIGIN, 'max_score': row.get('max_score'),
                'auto_publish': {'ok': bool(row.get('auto_publish_ok')), 'visible': item['visible'],
                                 'fail': item['hidden_why'], 'notes': row.get('auto_publish_notes') or [],
                                 'bundle': self._bundle() if item['visible'] else ''},
                'rules': f['notes'], 'markup': f['markup'],
                'figures': [{'hash': x['hash'], 'placed': x['placed'], 'from': x['from']}
                            for x in f['figures']]}
        if not f['source_url_official']:
            meta['statement_mirror'] = True
        ref = OlympiadRef.objects.create(problem=problem, match_method='url_exact', match_score=1.0,
                                         raw_meta=self._with_variant(meta, row), **self._ref_fields(row, f['source_url']))
        created['created_ref_ids'].append(ref.id)
        if item['visible']:
            verdict = ReviewVerdict.objects.create(
                problem=problem, bundle=self._bundle(), category='perfect',
                comment=AUTO_COMMENT, reviewer=AUTO_REVIEWER)
            created['created_verdict_ids'].append(verdict.id)
            created['visible_problem_ids'].append(problem.id)
        return problem.id

    def _twin(self, item, problem_id, created):
        row = item['row']
        fields = item['fields']
        problem = Problem.objects.get(pk=problem_id)
        self._sref(problem, row, fields, created)
        ref = OlympiadRef.objects.create(
            problem=problem, match_method='text_fuzzy_numeric', match_score=1.0,
            raw_meta=self._with_variant({'origin': ORIGIN, 'twin_of': item['twin_of'],
                                        'max_score': row.get('max_score')}, row),
            **self._ref_fields(row, fields['source_url']))
        created['created_ref_ids'].append(ref.id)

    def _link(self, item, created):
        row = item['row']
        fields = item['fields']
        meta = {'origin': ORIGIN + '_link', 'confirm': item['reason'],
                'fuzzy': item['ratio'], 'containment': item['contain'], 'candidate_from': item['via'],
                'max_score': row.get('max_score')}
        if item.get('kit_numbers'):
            meta['kit_numbers'] = [str(n) for n in item['kit_numbers']]
        ref = OlympiadRef.objects.create(
            problem_id=item['pid'], match_method='text_fuzzy_numeric',
            match_score=max(item['ratio'], item['contain']),
            raw_meta=self._with_variant(meta, row),
            **self._ref_fields(row, fields['source_url']))
        created['created_ref_ids'].append(ref.id)
        for field, value in item.get('fill', {}).items():
            # Условная правка: только если поле всё ещё пустое (ADR 0005).
            n = Problem.objects.filter(pk=item['pid']).filter(
                Q(**{field: ''})).update(**{field: value})
            if n:
                created['filled'].append({'id': item['pid'], 'field': field, 'old': '', 'new': value})

    # ── Откат ───────────────────────────────────────────────────────────

    def _rollback(self, path):
        with open(path, encoding='utf-8') as handle:
            journal = json.load(handle)
        if not journal.get('applied'):
            raise CommandError('Это журнал сухого прогона — откатывать нечего.')
        if journal.get('olympiad') != self.slug:
            raise CommandError(f'Журнал записан для {journal.get("olympiad")}, а не {self.slug}.')
        restore, conflicts = [], []
        for change in journal['filled']:
            current = Problem.objects.filter(pk=change['id']).values_list(
                change['field'], flat=True).first()
            if current == change['new']:
                restore.append(change)
            else:
                conflicts.append(f'#{change["id"]}.{change["field"]}: изменилось после записи')
        w = self.stdout.write
        w(f'Откат {path}: задач {len(journal["created_problem_ids"])}, строк OlympiadRef '
          f'{len(journal["created_ref_ids"])}, вердиктов {len(journal["created_verdict_ids"])}, '
          f'вернуть пустыми полей {len(restore)}, конфликтов {len(conflicts)}')
        for line in conflicts[:10]:
            w(f'  ⚠ {line}')
        if not self.apply:
            w(self.style.WARNING('СУХОЙ ПРОГОН отката — ничего не изменено.'))
            return
        before = _counts(self.slug)
        with transaction.atomic():
            for change in restore:
                Problem.objects.filter(pk=change['id']).update(**{change['field']: ''})
            ReviewVerdict.objects.filter(pk__in=journal['created_verdict_ids']).delete()
            OlympiadRef.objects.filter(pk__in=journal['created_ref_ids']).delete()
            ProblemFigure.objects.filter(pk__in=journal['created_figure_ids']).delete()
            SourceReference.objects.filter(pk__in=journal['created_sourceref_ids']).delete()
            ProblemPart.objects.filter(pk__in=journal['created_part_ids']).delete()
            Problem.objects.filter(pk__in=journal['created_problem_ids']).delete()
        after = _counts(self.slug)
        report = {'journal': os.path.abspath(path), 'restored': len(restore),
                  'conflicts': conflicts, 'counts_before': before, 'counts_after': after}
        out = os.path.join(os.path.dirname(os.path.abspath(path)),
                           'rollback_' + os.path.basename(path))
        with open(out, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, ensure_ascii=False, indent=1)
        w(self.style.SUCCESS(f'Откат выполнен. Отчёт: {out}'))
        for name, value in after.items():
            w(f'  {name}: {value} ({value - before[name]:+d})')
