from django.core.management.base import BaseCommand

from problems.models import Problem


class Command(BaseCommand):
    help = (
        "Снимает флаг needs_quality_review у конкретных задач (точечно, "
        "без полного пересчёта quality_gate --apply)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--ids', required=True,
            help='id через запятую, напр. 150,991,1221'
        )
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        ids = [int(x) for x in opts['ids'].split(',') if x.strip()]
        found = {p.id: p for p in Problem.objects.filter(id__in=ids)}
        for i in ids:
            p = found.get(i)
            if not p:
                self.stdout.write(f'НЕ найдена: {i}')
                continue
            before = p.needs_quality_review
            if opts['dry_run']:
                self.stdout.write(
                    f'[dry] #{i} [{p.status}] nqr: {before} → False'
                )
                continue
            p.needs_quality_review = False
            p.save(update_fields=['needs_quality_review'])
            self.stdout.write(
                f'OK #{i} [{p.status}]: needs_quality_review {before} → False'
            )
