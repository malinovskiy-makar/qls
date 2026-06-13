"""
Сессия C, этап 3a — эскейп валютных долларов в англоязычных источниках.

Проблема: валютные пары «$8 ... $10» KaTeX спаривает в мат-спан → «from 8to10».
Решение: $N / $N.NN / $ N (доллар перед числом) → \\$N.

Безопасность: поле обрабатывается ТОЛЬКО если ВСЕ неэкранированные $ в нём
валютоподобны ($ + опциональный пробел + цифра). Поля с мат-спанами
($Q = 5$) или смешанные — пропускаются целиком: их $ трогать нельзя.

Запуск:
    ./venv/bin/python manage.py fix_ap_currency --dry-run
    ./venv/bin/python manage.py fix_ap_currency
"""

import random
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart
from problems.management.commands.fix_ile_formulas import append_ids_file

EN_SOURCES = [7, 8, 18, 20, 21, 22]
CHANGED_IDS_FILE_C = 'reports/quality_audit/changed_ids_C.txt'

_UNESCAPED_DOLLAR_RE = re.compile(r'(?<!\\)\$')
_CURRENCY_RE = re.compile(r'(?<!\\)\$(?= ?\d)')


def escape_currency(text: str):
    """(новый_текст | None). None — поле пропущено (мат-спаны/смешанное)."""
    if not text or '$' not in text:
        return None
    dollars = list(_UNESCAPED_DOLLAR_RE.finditer(text))
    if not dollars:
        return None                      # все уже экранированы
    currency = list(_CURRENCY_RE.finditer(text))
    if len(currency) != len(dollars):
        return None                      # есть не-валютные $ — не трогаем
    new = _CURRENCY_RE.sub(r'\\$', text)
    return new if new != text else None


class Command(BaseCommand):
    help = 'Эскейп валютных $N → \\$N в англоязычных источниках (AP/IEO)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--examples', type=int, default=20)

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('── DRY-RUN ──'))

        all_examples = []
        changed_ids = set()
        per_source = {}

        with transaction.atomic():
            for sid in EN_SOURCES:
                n_problems = n_parts = 0
                problems = (Problem.objects
                            .filter(source_references__source_id=sid)
                            .distinct().prefetch_related('parts').order_by('id'))
                for problem in problems:
                    fields = {}
                    for field in ('statement', 'answer', 'solution'):
                        new = escape_currency(getattr(problem, field) or '')
                        if new is not None:
                            fields[field] = new
                            i = new.find('\\$')
                            all_examples.append(
                                (sid, problem.id, field,
                                 (getattr(problem, field) or '')[max(0, i-60):i+60],
                                 new[max(0, i-60):i+60]))
                    if fields:
                        n_problems += 1
                        changed_ids.add(problem.id)
                        if not dry_run:
                            Problem.objects.filter(pk=problem.pk).update(**fields)
                    for part in problem.parts.all():
                        pfields = {}
                        for field in ('statement', 'answer', 'solution'):
                            new = escape_currency(getattr(part, field) or '')
                            if new is not None:
                                pfields[field] = new
                        if pfields:
                            n_parts += 1
                            changed_ids.add(problem.id)
                            if not dry_run:
                                ProblemPart.objects.filter(pk=part.pk).update(**pfields)
                per_source[sid] = (n_problems, n_parts)
                self.stdout.write(f'#{sid}: задач {n_problems}, подпунктов {n_parts}')

        rng = random.Random(42)
        sample = (rng.sample(all_examples, options['examples'])
                  if len(all_examples) > options['examples'] else all_examples)
        for sid, pid, field, b, a in sample:
            self.stdout.write(f'\n#{pid} (ист.{sid}) [{field}]')
            self.stdout.write(f'  ДО:    …{b.strip()[:120]}…')
            self.stdout.write(f'  ПОСЛЕ: …{a.strip()[:120]}…')

        total = sum(p for p, _ in per_source.values())
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'\nDRY-RUN: задач {total}. Ничего не сохранено.'))
        else:
            append_ids_file(CHANGED_IDS_FILE_C, changed_ids)
            self.stdout.write(self.style.SUCCESS(f'\nГотово: задач {total}.'))
