from django.core.management.base import BaseCommand

from problems.models import Problem


class Command(BaseCommand):
    help = "Возвращает скрытые задачи в опубликованные по списку id; опционально очищает solution."

    def add_arguments(self, parser):
        parser.add_argument('--ids', required=True, help='id через запятую, напр. 635,2174')
        parser.add_argument('--clear-solution', action='store_true', help='очистить solution в пустую строку')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        ids = [int(x) for x in opts['ids'].split(',') if x.strip()]
        found = {p.id: p for p in Problem.objects.filter(id__in=ids)}
        PUBLISHED = Problem.Status.PUBLISHED
        for i in ids:
            p = found.get(i)
            if not p:
                self.stdout.write('НЕ найдена: ' + str(i))
                continue
            before = p.status
            if opts['dry_run']:
                msg = '[dry] ' + str(i) + ': ' + str(before) + ' → ' + PUBLISHED
                if opts['clear_solution']:
                    msg += ' + solution=""'
                self.stdout.write(msg)
                continue
            p.status = PUBLISHED
            fields = ['status']
            if opts['clear_solution']:
                p.solution = ''
                fields.append('solution')
            p.save(update_fields=fields)
            self.stdout.write('OK ' + str(i) + ': ' + str(before) + ' → ' + PUBLISHED
                              + (' (solution очищен)' if opts['clear_solution'] else ''))
