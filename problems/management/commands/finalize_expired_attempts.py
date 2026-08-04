"""
Закрывает контрольные, у которых вышло время.

⚠️ ЭТО СТРАХОВКА, А НЕ ОСНОВНОЙ МЕХАНИЗМ. Основной — ЛЕНИВЫЙ: попытка
закрывается при любом обращении к ней (`exam_engine.finalize_if_expired`).
Так сделано намеренно: на бесплатном хостинге нет ни Shell, ни планировщика,
и полагаться на фоновое задание значило бы получить работы, которые «идут»
третий месяц.

Команда нужна для двух случаев:
* ученик закрыл вкладку и больше не вернулся — его работа висит незакрытой,
  и репетитор видит «пишет сейчас» вместо оценки;
* репетитор хочет увидеть готовую таблицу результатов, не дожидаясь, пока
  каждый ученик зайдёт.

Время сдачи ставится `expires_at`, а не «сейчас»: работа окончена тогда,
когда кончилось время, а не когда мы это заметили.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from problems import exam_engine


class Command(BaseCommand):
    help = ('Помечает сданными истёкшие попытки контрольных и оценивает их. '
            'Идемпотентна.')

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Показать, ничего не менять.')

    def handle(self, *args, **options):
        from problems.models import ExamAttempt

        now = timezone.now()
        loud = options.get('verbosity', 1) >= 1
        expired = (ExamAttempt.objects
                   .filter(submitted_at__isnull=True,
                           expires_at__isnull=False,
                           expires_at__lt=now)
                   .select_related('assignment', 'student'))

        closed = 0
        for attempt in expired:
            if loud:
                self.stdout.write(
                    f'  {attempt.student} — «{attempt.assignment.name}»: '
                    f'время вышло {attempt.expires_at:%d.%m.%Y %H:%M}')
            if not options['dry_run']:
                exam_engine.finalize_if_expired(attempt, now)
            closed += 1

        if loud:
            prefix = '[dry-run] ' if options['dry_run'] else ''
            self.stdout.write(self.style.SUCCESS(
                f'{prefix}Закрыто попыток: {closed}.'))
