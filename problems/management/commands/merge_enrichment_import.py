# -*- coding: utf-8 -*-
"""merge_enrichment_import — переливка обогащения v2 ТОЛЬКО в задачи своего журнала.

Наследник `merge_enrichment_v2` для обогащения свежего импорта (сессия И2,
14.10.2026: новые задачи ВП финграмотность + основы бизнеса). Правила
переливки — те же, что у банка в 2026-09 (темы, теги, понятия, особенности,
«дано / найти», сюжет, подсказки, сложность, заголовок-кандидат), но:

* **Область — только задачи журнала `--parsed`.** У `merge_enrichment_v2`
  две операции идут по ВСЕМУ банку: перевод старых `problem_type` по таблице
  (`find_legacy_only`) и пересчёт кодовых особенностей (`iter_code_features`).
  Для свежих 85 задач это значило бы молча переписать особенности у тысяч
  чужих задач, если их тексты сдвинулись с 07.09. Здесь обе сужены до журнала.
* **Существующие поля не перезаписываются** (решение владельца на сессию):
  `title`, `problem_type`, `content_status`, `statement`, `answer`,
  `solution` возвращаются к значению до переливки. Что предлагала модель —
  в `--protect-out` (CSV): например, «серьёзные дефекты» → `needs_fix`
  спрятало бы только что автоопубликованную задачу; решает владелец.
* Ветка первого прогона (`--parsed-run1`) выключена всегда.

    manage.py merge_enrichment_import --parsed <run_parsed.jsonl> --protect-out <csv>
    manage.py merge_enrichment_import --parsed … --protect-out … --apply
"""
import csv

from django.db import transaction

from problems.management.commands import merge_enrichment_v2 as base
from problems.models import Problem

PROTECTED = ('title', 'problem_type', 'content_status', 'statement', 'answer', 'solution')


class Command(base.Command):
    help = ('Переливка обогащения v2 только в задачи своего журнала; существующие '
            'поля задачи не перезаписываются. Без --apply — только отчёт.')

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--protect-out', required=True,
                            help='CSV: что модель предложила для защищённых полей')

    def handle(self, *args, **options):
        options['no_run1'] = True
        self.protect_out = options['protect_out']
        self.scope = set()
        return super().handle(*args, **options)

    def load_rows(self):
        rows = super().load_rows()
        self.scope = {int(r['problem_id']) for r in rows}
        return rows

    def find_legacy_only(self, jsonl_ids):
        # Перевод старых problem_type по таблице — операция над всем банком; здесь не нужна.
        return [], {}

    def iter_code_features(self, only_active=False):
        for pid, keys in super().iter_code_features(only_active=only_active):
            if pid in self.scope:
                yield pid, keys

    def apply_all(self, ok_rows, legacy_only_ids, legacy_old_values, taxonomy_plan):
        before = {row['id']: row for row in Problem.objects.filter(id__in=self.scope)
                  .values('id', *PROTECTED)}
        restored = []
        with transaction.atomic():
            super().apply_all(ok_rows, legacy_only_ids, legacy_old_values, taxonomy_plan)
            for problem in Problem.objects.filter(id__in=self.scope):
                fields = []
                for field in PROTECTED:
                    old, new = before[problem.id][field], getattr(problem, field)
                    if old != new:
                        restored.append((problem.id, field, old, new))
                        setattr(problem, field, old)
                        fields.append(field)
                if fields:
                    problem.save(update_fields=fields)
        with open(self.protect_out, 'w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['problem_id', 'поле', 'оставлено', 'предлагала модель'])
            writer.writerows(restored)
        self.stdout.write(f'Защищённые поля: вернул {len(restored)} значений '
                          f'у {len({r[0] for r in restored})} задач → {self.protect_out}')
