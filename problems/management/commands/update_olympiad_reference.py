# -*- coding: utf-8 -*-
"""Обновить СВОИ импортированные задачи из новой версии эталона (ночь 28.10.2026, ADR 0163).

    update_olympiad_reference --olympiad vp --journal <import_…json> [--journal …] \\
        --old <reference_v6.jsonl> --new <reference_v7.jsonl> [--old-digitized D] [--new-digitized D]
    … --apply --yes-i-have-owner-approval
    update_olympiad_reference --olympiad vp --rollback <update_…json> [--apply --yes-…]

Область — только задачи, созданные импортом (`created_problem_ids` журналов
`import_olympiad_reference`), задание узнаётся по `SourceReference.problem_number`
= ключ эталона. Поля задачи собираются тем же `reference_import.build_fields`
из СТАРОЙ и НОВОЙ строки; меняется только поле, которое изменилось в эталоне,
и только если в базе оно всё ещё равно старой сборке (никто не правил руками
и обогащение его не трогало) — иначе конфликт в отчёт. Подпункты — на месте;
если их в новой версии меньше — конфликт (удалять не берусь: к подпунктам
привязаны подсказки). Перед изменением — снимок в `ProblemVersion`. Журнал;
откат возвращает поле, если его с тех пор не меняли.

Заголовок: заглушку импорта к этому времени мог заменить `import_reference_titles`
— тогда заголовок не трогается (это не «равно старой сборке»).
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max

from problems.management.commands.apply_official_text import snapshot_of
from problems.models import Problem, ProblemFigure, ProblemPart, ProblemVersion, Source, SourceReference
from problems.olympiad_audit import bank_match, registry
from problems.olympiad_audit import reference_import as ri
from problems.olympiad_official import read_jsonl

APPROVAL_FLAG = '--yes-i-have-owner-approval'
FIELDS = ('title', 'statement', 'answer', 'solution', 'problem_type')


def _parts(fields):
    return [(p['label'][:10], p['statement_md'], p.get('answer') or '') for p in fields['parts']]


class Command(BaseCommand):
    help = 'Обновить свои импортированные задачи из новой версии эталона. Сухой прогон по умолчанию.'

    def add_arguments(self, parser):
        parser.add_argument('--olympiad', required=True, choices=sorted(registry.REGISTRY))
        parser.add_argument('--journal', action='append', default=[])
        parser.add_argument('--old')
        parser.add_argument('--new')
        parser.add_argument('--old-digitized')
        parser.add_argument('--new-digitized')
        parser.add_argument('--out-dir')
        parser.add_argument('--rollback', metavar='JOURNAL')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument(APPROVAL_FLAG, dest='approved', action='store_true')

    def handle(self, *args, **o):
        if o['apply'] and not o['approved']:
            raise CommandError(f'--apply требует {APPROVAL_FLAG}. Ничего не записано.')
        if o['rollback']:
            return self._rollback(o['rollback'], o['apply'])
        if not (o['journal'] and o['old'] and o['new']):
            raise CommandError('Нужны --journal, --old и --new.')
        entry = registry.get(o['olympiad'])
        short = registry.short_name(entry.slug)
        old_dig = o['old_digitized'] or os.path.dirname(os.path.abspath(o['old']))
        new_dig = o['new_digitized'] or os.path.dirname(os.path.abspath(o['new']))
        old_rows = {bank_match.row_key(r): r for r in read_jsonl(o['old'])}
        new_rows = {bank_match.row_key(r): r for r in read_jsonl(o['new'])}
        ids = set()
        for path in o['journal']:
            with open(path, encoding='utf-8') as handle:
                j = json.load(handle)
            if j.get('command') != 'import_olympiad_reference' or not j.get('applied'):
                raise CommandError(f'{path}: не журнал записи import_olympiad_reference')
            ids.update(j['created_problem_ids'])
        source = Source.objects.filter(name=entry.official_source_name).first()
        by_key = {}
        for pid, key in SourceReference.objects.filter(source=source, problem_id__in=ids).values_list(
                'problem_id', 'problem_number'):
            by_key.setdefault(key, pid)
        plan, conflicts, same = [], [], 0
        for key, pid in sorted(by_key.items()):
            if key not in old_rows or key not in new_rows:
                continue
            of = ri.build_fields(old_rows[key], digitized_dir=old_dig, url_map=ri.UrlMap(), olympiad_short=short)
            nf = ri.build_fields(new_rows[key], digitized_dir=new_dig, url_map=ri.UrlMap(), olympiad_short=short)
            problem = Problem.objects.get(pk=pid)
            change = {'id': pid, 'key': key, 'fields': {}, 'parts': None, 'new_fields': nf}
            for field in FIELDS:
                old, new = of[field], nf[field]
                if old == new:
                    continue
                current = getattr(problem, field) or ''
                if current == new:
                    continue
                if current != old:
                    conflicts.append((key, pid, field, 'поле в базе уже не равно старой сборке'))
                    continue
                change['fields'][field] = {'old': current, 'new': new}
            if _parts(of) != _parts(nf):
                current = [(p.label, p.statement, p.answer) for p in problem.parts.order_by('order', 'id')]
                if current == _parts(nf):
                    pass
                elif current != _parts(of):
                    conflicts.append((key, pid, 'parts', 'подпункты в базе уже не равны старой сборке'))
                elif len(nf['parts']) < len(current):
                    conflicts.append((key, pid, 'parts', 'в новой версии подпунктов меньше'))
                else:
                    change['parts'] = _parts(nf)
            if change['fields'] or change['parts']:
                plan.append(change)
            else:
                same += 1
        w = self.stdout.write
        w(f'Своих задач в области: {len(by_key)}; без изменений {same}; обновить {len(plan)}; '
          f'конфликтов {len(conflicts)}')
        for c in plan[:10]:
            w(f'  + {c["key"]} #{c["id"]}: {", ".join(c["fields"])}{" подпункты" if c["parts"] else ""}')
        for c in conflicts[:10]:
            w(f'  ⚠ {c[0]} #{c[1]} {c[2]}: {c[3]}')
        journal = {'command': 'update_olympiad_reference', 'olympiad': entry.slug,
                   'applied': bool(o['apply']), 'old': o['old'], 'new': o['new'],
                   'at': datetime.now().isoformat(timespec='seconds'), 'conflicts': conflicts,
                   'changes': []}
        if o['apply']:
            for c in plan:
                with transaction.atomic():
                    journal['changes'].append(self._update(c))
        out_dir = o['out_dir'] or os.path.dirname(os.path.abspath(o['journal'][0]))
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        suffix = '' if o['apply'] else '_dryrun'
        path = os.path.join(out_dir, f'update_{entry.slug}_{stamp}{suffix}.json')
        n = 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(out_dir, f'update_{entry.slug}_{stamp}-{n}{suffix}.json')
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(journal, handle, ensure_ascii=False, indent=1, default=str)
        w(f'Журнал: {path}')
        if not o['apply']:
            w(self.style.WARNING('СУХОЙ ПРОГОН — в базе ничего не изменено.'))

    def _update(self, c):
        problem = Problem.objects.select_for_update().get(pk=c['id'])
        number = (problem.versions.aggregate(n=Max('number'))['n'] or 0) + 1
        version = ProblemVersion.objects.create(
            problem=problem, number=number, snapshot=snapshot_of(problem),
            note=f'обновление из новой версии эталона: {", ".join(c["fields"]) or "подпункты"}'[:300])
        rec = {'id': problem.id, 'key': c['key'], 'version_id': version.id, 'fields': c['fields'],
               'parts_old': [], 'created_part_ids': [], 'created_figure_ids': []}
        for field, v in c['fields'].items():
            setattr(problem, field, v['new'])
        if c['fields']:
            problem.save(update_fields=list(c['fields']))
        have = set(problem.figures.values_list('tikz_hash', flat=True))
        for fig in c['new_fields']['figures']:
            if fig['hash'] not in have and os.path.isfile(fig['path']):
                with open(fig['path'], 'rb') as handle:
                    data = handle.read()
                created = ProblemFigure.objects.create(
                    problem=problem, tikz_hash=fig['hash'], tikz_source=fig['ref'], svg='',
                    image_data=data, content_type='image/png', source_field=fig['field'])
                rec['created_figure_ids'].append(created.id)
        if c['parts']:
            bank = list(problem.parts.order_by('order', 'id'))
            for i, (label, statement, answer) in enumerate(c['parts']):
                if i < len(bank):
                    bp = bank[i]
                    rec['parts_old'].append({'id': bp.id, 'label': bp.label, 'statement': bp.statement,
                                             'answer': bp.answer, 'new_statement': statement})
                    bp.label, bp.statement, bp.answer = label, statement, answer
                    bp.save(update_fields=['label', 'statement', 'answer'])
                else:
                    rec['created_part_ids'].append(ProblemPart.objects.create(
                        problem=problem, label=label, statement=statement, answer=answer, order=i).id)
        return rec

    def _rollback(self, path, apply):
        with open(path, encoding='utf-8') as handle:
            journal = json.load(handle)
        if journal.get('command') != 'update_olympiad_reference' or not journal.get('applied'):
            raise CommandError('Это не журнал записи update_olympiad_reference.')
        self.stdout.write(f'Откат: задач {len(journal["changes"])}')
        if not apply:
            self.stdout.write(self.style.WARNING('СУХОЙ ПРОГОН отката — ничего не изменено.'))
            return
        with transaction.atomic():
            for rec in journal['changes']:
                for field, v in rec['fields'].items():
                    Problem.objects.filter(pk=rec['id'], **{field: v['new']}).update(**{field: v['old']})
                for part in rec['parts_old']:
                    ProblemPart.objects.filter(pk=part['id'], statement=part['new_statement']).update(
                        label=part['label'], statement=part['statement'], answer=part['answer'])
                ProblemPart.objects.filter(pk__in=rec['created_part_ids']).delete()
                ProblemFigure.objects.filter(pk__in=rec['created_figure_ids']).delete()
                ProblemVersion.objects.filter(pk=rec['version_id']).delete()
        self.stdout.write(self.style.SUCCESS('Откат выполнен.'))
