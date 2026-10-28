# -*- coding: utf-8 -*-
"""Заголовки задач импорта эталона: заглушка → название от ИИ (решение 15.10.2026).

    import_reference_titles --journal <import_…json> [--journal …]
    import_reference_titles --journal … --apply --yes-i-have-owner-approval
    import_reference_titles --rollback <titles_…json> [--apply --yes-…]

Область — ТОЛЬКО задачи, созданные импортом (`created_problem_ids` журналов
`import_olympiad_reference`): их заголовки написал импорт, а не человек,
поэтому замена не нарушает ADR 0005. Правило — `olympiad_audit/title_rule.py`:
настоящее официальное название остаётся; заглушка («ВП по … задание 3»,
«Задача 2», «СПРАВКА») заменяется на `title_candidate` обогащения, если тот
годен; «начало текста» короче 80 знаков остаётся (гейт 1 И3, 28.10).
`title_source` ставится по принятому способу (`model-empty` — была
заглушка, `model-firstline` — было эхо начала условия).

Запускать после `merge_enrichment_import`: без кандидата заглушка ждёт.
Повтор даёт ноль (заголовок уже равен кандидату). Журнал — старые
`title` / `title_source`; откат возвращает их, если заголовок с тех пор
никто не менял.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.models import Problem
from problems.olympiad_audit import title_rule

APPROVAL_FLAG = '--yes-i-have-owner-approval'


class Command(BaseCommand):
    help = 'Заголовки-заглушки задач импорта → title_candidate. Сухой прогон по умолчанию.'

    def add_arguments(self, parser):
        parser.add_argument('--journal', action='append', default=[],
                            help='журнал import_olympiad_reference (можно несколько)')
        parser.add_argument('--out', help='куда писать журнал заголовков; по умолчанию рядом с первым')
        parser.add_argument('--rollback', metavar='JOURNAL')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument(APPROVAL_FLAG, dest='approved', action='store_true')

    def handle(self, *args, **options):
        if options['apply'] and not options['approved']:
            raise CommandError(f'--apply требует {APPROVAL_FLAG}. Ничего не записано.')
        if options['rollback']:
            return self._rollback(options['rollback'], options['apply'])
        if not options['journal']:
            raise CommandError('--journal обязателен: область — только задачи журнала импорта.')
        ids = []
        for path in options['journal']:
            with open(path, encoding='utf-8') as handle:
                journal = json.load(handle)
            if journal.get('command') != 'import_olympiad_reference' or not journal.get('applied'):
                raise CommandError(f'{path}: не журнал записи import_olympiad_reference')
            ids.extend(journal['created_problem_ids'])
        plan = []
        for p in Problem.objects.filter(pk__in=ids).only(
                'id', 'title', 'title_candidate', 'title_source', 'statement').order_by('id'):
            d = title_rule.decide(p.title, p.title_candidate, p.statement)
            source = ''
            if d['changed']:
                source = (Problem.TitleSource.MODEL_FIRSTLINE if d['flag']
                          else Problem.TitleSource.MODEL_EMPTY)
            plan.append({'id': p.id, 'old': p.title, 'new': d['new'], 'rule': d['rule'],
                         'flag': d['flag'], 'changed': d['changed'],
                         'old_source': p.title_source, 'new_source': source or p.title_source})
        changes = [x for x in plan if x['changed']]
        from collections import Counter
        w = self.stdout.write
        w(f'Задач в области: {len(plan)} (журналов {len(options["journal"])}); '
          f'заголовок меняется у {len(changes)}')
        for rule, n in Counter(x['rule'] for x in plan).most_common():
            w(f'  {n} — {rule}')
        for x in changes[:5]:
            w(f'    #{x["id"]}: «{x["old"][:60]}» → «{x["new"]}»')
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        out = options['out'] or os.path.join(os.path.dirname(os.path.abspath(options['journal'][0])),
                                             f'titles_{stamp}{"" if options["apply"] else "_dryrun"}.json')
        n = 1
        while os.path.exists(out):
            n += 1
            out = out.replace('.json', f'-{n}.json') if n == 2 else out.replace(f'-{n - 1}.json', f'-{n}.json')
        record = {'command': 'import_reference_titles', 'applied': bool(options['apply']),
                  'journals': [os.path.abspath(j) for j in options['journal']],
                  'at': datetime.now().isoformat(timespec='seconds'), 'changes': changes,
                  'kept': [x for x in plan if not x['changed']]}
        if options['apply']:
            with transaction.atomic():
                for x in changes:
                    Problem.objects.filter(pk=x['id'], title=x['old']).update(
                        title=x['new'], title_source=x['new_source'])
        with open(out, 'w', encoding='utf-8') as handle:
            json.dump(record, handle, ensure_ascii=False, indent=1)
        w(f'Журнал: {out}')
        if not options['apply']:
            w(self.style.WARNING('СУХОЙ ПРОГОН — в базе ничего не изменено.'))
        else:
            w(self.style.SUCCESS(f'ЗАПИСАНО заголовков: {len(changes)}. Откат: '
                                 f'import_reference_titles --rollback {out} --apply {APPROVAL_FLAG}'))

    def _rollback(self, path, apply):
        with open(path, encoding='utf-8') as handle:
            record = json.load(handle)
        if record.get('command') != 'import_reference_titles' or not record.get('applied'):
            raise CommandError('Это не журнал записи import_reference_titles.')
        ok = [x for x in record['changes']
              if Problem.objects.filter(pk=x['id'], title=x['new']).exists()]
        conflicts = len(record['changes']) - len(ok)
        self.stdout.write(f'Откат: вернуть {len(ok)} заголовков, изменено с тех пор {conflicts}')
        if not apply:
            self.stdout.write(self.style.WARNING('СУХОЙ ПРОГОН отката — ничего не изменено.'))
            return
        with transaction.atomic():
            for x in ok:
                Problem.objects.filter(pk=x['id'], title=x['new']).update(
                    title=x['old'], title_source=x['old_source'])
        self.stdout.write(self.style.SUCCESS('Откат выполнен.'))
