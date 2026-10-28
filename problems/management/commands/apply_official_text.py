# -*- coding: utf-8 -*-
"""Замена текста задачи банка официальным по вердиктам судьи (решение 28.10.2026, ADR 0163).

    apply_official_text --verdicts <olympiad_text_judge …jsonl> --journal <import_…json> [...]
    apply_official_text … --apply --yes-i-have-owner-approval
    apply_official_text --rollback <official_text_…json> [--apply --yes-…]

Частично пересматривает ADR 0005 — ТОЛЬКО для пар с официальным эталоном.
Меняется, если судья сказал `replace` с уверенностью ≥ 0,8 и цитатами из PDF;
задача, одобренная человеком, — только при структурной потере (таблица,
варианты, пункты, рисунок; `text_judge.replace_decision`).

Что меняется: условие → официальное (с маркерами рисунков и новыми
`ProblemFigure`), подпункты — на месте по порядку (лишние у банка остаются,
недостающие добавляются; ни один не удаляется: к подпунктам привязаны
подсказки и попытки), `content_format` → markdown. Ответ и решение — нет
(их дописывает импорт, только пустые). Перед заменой — снимок в
`ProblemVersion` с заметкой «замена официальным эталоном: <причины>».
Журнал — старые значения; откат возвращает их, если поле с тех пор никто
не менял, и удаляет созданные подпункты, рисунки и версию.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max

from problems.management.commands.olympiad_text_judge import pairs_from_journal
from problems.models import Problem, ProblemFigure, ProblemPart, ProblemVersion
from problems.olympiad_audit import reference_import as ri
from problems.olympiad_audit import registry
from problems.olympiad_audit import text_judge as tj

APPROVAL_FLAG = '--yes-i-have-owner-approval'
NOTE_PREFIX = 'замена официальным эталоном: '
_MARKER = re.compile(r'\[\[FIGURE:([0-9a-f]{64})\]\]')


def snapshot_of(problem):
    return {'title': problem.title, 'statement': problem.statement, 'answer': problem.answer,
            'solution': problem.solution, 'content_format': problem.content_format,
            'problem_type': problem.problem_type,
            'parts': [{'id': p.id, 'label': p.label, 'statement': p.statement, 'answer': p.answer,
                       'order': p.order} for p in problem.parts.order_by('order', 'id')],
            'figures': list(problem.figures.values_list('tikz_hash', flat=True))}


class Command(BaseCommand):
    help = 'Замена текста задачи банка официальным по вердиктам судьи. Сухой прогон по умолчанию.'

    def add_arguments(self, parser):
        parser.add_argument('--verdicts', help='JSONL olympiad_text_judge --kind replace')
        parser.add_argument('--journal', action='append', default=[],
                            help='журналы импорта, из которых судились пары (тексты эталона)')
        parser.add_argument('--out-dir', help='куда писать журнал; по умолчанию рядом с --verdicts')
        parser.add_argument('--rollback', metavar='JOURNAL')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument(APPROVAL_FLAG, dest='approved', action='store_true')

    def handle(self, *args, **o):
        if o['apply'] and not o['approved']:
            raise CommandError(f'--apply требует {APPROVAL_FLAG}. Ничего не записано.')
        if o['rollback']:
            return self._rollback(o['rollback'], o['apply'])
        if not o['verdicts'] or not o['journal']:
            raise CommandError('Нужны --verdicts и --journal.')
        pairs = {}
        for path in o['journal']:
            for key, pid, row, digitized, _subdir, slug in pairs_from_journal(path, 'replace'):
                pairs[(key, pid)] = (row, digitized, slug)
        plan, skipped = [], []
        for line in open(o['verdicts'], encoding='utf-8'):
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get('kind') != 'replace' or not rec.get('verdict'):
                continue
            src = pairs.get((rec['key'], rec['pid']))
            problem = Problem.objects.filter(pk=rec['pid']).first()
            if src is None or problem is None:
                skipped.append((rec['key'], rec['pid'], 'нет пары в журналах или задачи в банке'))
                continue
            ok, why = tj.replace_decision(rec['verdict'], tj.human_approved(problem))
            if not ok:
                skipped.append((rec['key'], rec['pid'], why))
                continue
            row, digitized, slug = src
            fields = ri.build_fields(row, digitized_dir=digitized, url_map=ri.UrlMap(),
                                     olympiad_short=registry.short_name(slug))
            if problem.statement == fields['statement']:
                skipped.append((rec['key'], rec['pid'], 'уже официальный текст (повтор)'))
                continue
            # Одна задача банка бывает привязана к двум заданиям (варианты соседних
            # классов): меняем один раз, иначе вторая замена затрёт первую, а повтор
            # не даст ноль. Уже заменённую прежним прогоном тоже не трогаем.
            if problem.id in {p['pid'] for p in plan} or problem.versions.filter(
                    note__startswith=NOTE_PREFIX).exists():
                skipped.append((rec['key'], rec['pid'], 'задача уже заменена по другому заданию'))
                continue
            plan.append({'key': rec['key'], 'pid': problem.id, 'why': why, 'fields': fields})
        self.stdout.write(f'Вердиктов «заменить» к записи: {len(plan)}; не меняю: {len(skipped)}')
        for key, pid, why in skipped[:20]:
            self.stdout.write(f'  — {key} → #{pid}: {why}')
        for item in plan[:10]:
            self.stdout.write(f'  + {item["key"]} → #{item["pid"]}: {item["why"][:120]}')
        out_dir = o['out_dir'] or os.path.dirname(os.path.abspath(o['verdicts']))
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        journal = {'command': 'apply_official_text', 'applied': bool(o['apply']),
                   'verdicts': os.path.abspath(o['verdicts']), 'journals': o['journal'],
                   'at': datetime.now().isoformat(timespec='seconds'),
                   'skipped': skipped, 'changes': []}
        if o['apply']:
            for item in plan:
                with transaction.atomic():
                    journal['changes'].append(self._replace(item))
        suffix = '' if o['apply'] else '_dryrun'
        path = os.path.join(out_dir, f'official_text_{stamp}{suffix}.json')
        n = 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(out_dir, f'official_text_{stamp}-{n}{suffix}.json')
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(journal, handle, ensure_ascii=False, indent=1, default=str)
        self.stdout.write(f'Журнал: {path}')
        if not o['apply']:
            self.stdout.write(self.style.WARNING('СУХОЙ ПРОГОН — в базе ничего не изменено.'))

    def _replace(self, item):
        problem = Problem.objects.select_for_update().get(pk=item['pid'])
        f = item['fields']
        old = snapshot_of(problem)
        number = (problem.versions.aggregate(n=Max('number'))['n'] or 0) + 1
        version = ProblemVersion.objects.create(
            problem=problem, number=number, snapshot=old,
            note=f'{NOTE_PREFIX}{item["why"]}'[:300])
        change = {'id': problem.id, 'key': item['key'], 'version_id': version.id, 'old': {
            'statement': problem.statement, 'content_format': problem.content_format},
            'new': {}, 'parts_old': [], 'created_part_ids': [], 'created_figure_ids': []}
        problem.statement = f['statement']
        problem.content_format = Problem.ContentFormat.MARKDOWN
        problem.save(update_fields=['statement', 'content_format'])
        change['new'] = {'statement': problem.statement, 'content_format': problem.content_format}
        have = set(problem.figures.values_list('tikz_hash', flat=True))
        for fig in f['figures']:
            if fig['field'] == 'statement' and fig['hash'] not in have and os.path.isfile(fig['path']):
                with open(fig['path'], 'rb') as handle:
                    data = handle.read()
                created = ProblemFigure.objects.create(
                    problem=problem, tikz_hash=fig['hash'], tikz_source=fig['ref'], svg='',
                    image_data=data, content_type='image/png', source_field='statement')
                change['created_figure_ids'].append(created.id)
        bank_parts = list(problem.parts.order_by('order', 'id'))
        for i, part in enumerate(f['parts']):
            if i < len(bank_parts):
                bp = bank_parts[i]
                change['parts_old'].append({'id': bp.id, 'label': bp.label, 'statement': bp.statement,
                                            'new_label': part['label'][:10],
                                            'new_statement': part['statement_md']})
                bp.label, bp.statement = part['label'][:10], part['statement_md']
                bp.save(update_fields=['label', 'statement'])
            else:
                created = ProblemPart.objects.create(
                    problem=problem, label=part['label'][:10], statement=part['statement_md'],
                    answer=part.get('answer') or '', order=i)
                change['created_part_ids'].append(created.id)
        return change

    def _rollback(self, path, apply):
        with open(path, encoding='utf-8') as handle:
            journal = json.load(handle)
        if journal.get('command') != 'apply_official_text' or not journal.get('applied'):
            raise CommandError('Это не журнал записи apply_official_text.')
        ok, conflicts = [], []
        for change in journal['changes']:
            current = Problem.objects.filter(pk=change['id']).values_list('statement', flat=True).first()
            (ok if current == change['new']['statement'] else conflicts).append(change)
        self.stdout.write(f'Откат: вернуть {len(ok)}, изменено с тех пор {len(conflicts)}')
        if not apply:
            self.stdout.write(self.style.WARNING('СУХОЙ ПРОГОН отката — ничего не изменено.'))
            return
        with transaction.atomic():
            for change in ok:
                Problem.objects.filter(pk=change['id']).update(**change['old'])
                for part in change['parts_old']:
                    ProblemPart.objects.filter(pk=part['id'], statement=part['new_statement']).update(
                        label=part['label'], statement=part['statement'])
                ProblemPart.objects.filter(pk__in=change['created_part_ids']).delete()
                ProblemFigure.objects.filter(pk__in=change['created_figure_ids']).delete()
                ProblemVersion.objects.filter(pk=change['version_id']).delete()
        self.stdout.write(self.style.SUCCESS('Откат выполнен.'))
