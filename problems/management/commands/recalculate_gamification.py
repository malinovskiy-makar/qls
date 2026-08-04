"""
Полный пересчёт опыта, уровней, серий, владения темами и достижений.

Зачем нужен обязательно: правила начисления будут меняться (числа в
`problems/gamification.py` поставлены расчётом, а не замером), а начисление
неблокирующее — часть событий могла не доехать. Первоисточник — только
`LearningEvent`; всё остальное это свёртки, и они должны пересобираться.

ИДЕМПОТЕНТНА: два прогона подряд дают одинаковый результат. Достигается не
аккуратностью, а сбросом: свёртки ученика стираются и собираются заново из
событий. Достижения при этом НЕ отнимаются — награда, которую забрали, хуже,
чем неполученная (см. `EarnedAchievement`).

Правила берутся из тех же чистых функций, что и накопление по одному
(`xp_for_solved`, `mastery_for`, `day_counts_for_streak`), иначе «пересчитали»
и «накопилось» разошлись бы — а разошедшись, спорить было бы не о чем.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from problems.gamification import (
    HARD_DIFFICULTY, check_achievements, day_counts_for_streak, easy_decay,
    is_easy, level_for_xp, mastery_for, month_start, update_records,
    xp_for_solved,
)


class Command(BaseCommand):
    help = ('Пересобирает опыт, уровни, серии, владение темами и достижения '
            'из журнала учебных событий. Идемпотентна.')

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int, default=None,
                            help='Только один ученик.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Посчитать и показать, в базу не писать.')

    def handle(self, *args, **options):
        from problems.models import (DailySummary, LearningEvent,
                                     StudentProgressProfile,
                                     StudentTopicProgress, User)

        users = User.objects.all()
        if options['user_id']:
            users = users.filter(pk=options['user_id'])
        else:
            # Только те, у кого вообще есть события — иначе перебираем
            # весь список пользователей ради нулей.
            ids = LearningEvent.objects.filter(user__isnull=False) \
                .values_list('user_id', flat=True).distinct()
            users = users.filter(pk__in=list(ids))

        dry = options['dry_run']
        loud = options.get('verbosity', 1) >= 1
        total = 0
        with transaction.atomic():
            for user in users:
                result = self._recalc_user(user)
                total += 1
                if loud:
                    self.stdout.write(
                        f'  {user.username}: {result["xp"]} опыта, '
                        f'ур. {result["level"]}, серия {result["streak"]} '
                        f'(лучшая {result["longest"]}), дней {result["days"]}, '
                        f'тем {result["topics"]}')
            if dry:
                transaction.set_rollback(True)

        prefix = '[dry-run] ' if dry else ''
        if loud:
            self.stdout.write(self.style.SUCCESS(
                f'{prefix}Пересчитано учеников: {total}.'))

    # -- сам пересчёт ------------------------------------------------------

    def _recalc_user(self, user):
        from problems.models import (DailySummary, LearningEvent,
                                     StudentProgressProfile,
                                     StudentTopicProgress, Submission)

        DailySummary.objects.filter(user=user).delete()
        StudentTopicProgress.objects.filter(student=user).update(
            attempted=0, solved=0, solved_hard=0, mastery_level='none',
            last_activity_at=None, level=0)

        events = (LearningEvent.objects
                  .filter(user=user)
                  .order_by('created_at', 'pk')
                  .values('event_type', 'source', 'difficulty', 'topic_id',
                          'catalog_problem_id', 'custom_problem_id',
                          'assignment_id', 'time_spent_seconds', 'created_at',
                          'payload'))

        days = {}                       # дата → счётчики дня
        easy_today = defaultdict(int)   # дата → сколько лёгких уже засчитано
        seen_problems = set()           # чтобы повтор не давал опыт снова
        topics = defaultdict(lambda: {'a': 0, 's': 0, 'h': 0, 'at': None})
        bonus_seen = set()
        xp_total = 0

        for event in events:
            day = timezone.localtime(event['created_at']).date()
            row = days.setdefault(day, {'xp': 0, 'att': 0, 'solved': 0,
                                        'sec': 0})
            if event['time_spent_seconds']:
                row['sec'] += int(event['time_spent_seconds'])

            key = ('c', event['catalog_problem_id']) \
                if event['catalog_problem_id'] \
                else (('u', event['custom_problem_id'])
                      if event['custom_problem_id'] else None)

            # Служебная отметка «работа сдана целиком» — не задача.
            bonus = (event['payload'] or {}).get('homework_bonus')
            if bonus is not None:
                if bonus not in bonus_seen:
                    bonus_seen.add(bonus)
                    from problems.gamification import (EXAM_MULTIPLIER,
                                                       XP_HOMEWORK_COMPLETE)
                    amount = XP_HOMEWORK_COMPLETE
                    if event['source'] == 'exam':
                        amount = int(round(amount * EXAM_MULTIPLIER))
                    row['xp'] += amount
                    xp_total += amount
                continue

            if event['event_type'] in ('attempted', 'failed', 'solved'):
                row['att'] += 1

            if event['topic_id'] and event['event_type'] in ('solved', 'failed'):
                bucket = topics[event['topic_id']]
                bucket['a'] += 1
                if event['event_type'] == 'solved':
                    bucket['s'] += 1
                    if event['difficulty'] and \
                            int(event['difficulty']) >= HARD_DIFFICULTY:
                        bucket['h'] += 1
                bucket['at'] = event['created_at']

            if event['event_type'] != 'solved':
                continue
            row['solved'] += 1

            if key is not None and key in seen_problems:
                continue        # ту же задачу второй раз опытом не кормим
            if key is not None:
                seen_problems.add(key)

            gained = xp_for_solved(event['difficulty'], event['source'],
                                   easy_solved_today=easy_today[day])
            if is_easy(event['difficulty']):
                easy_today[day] += 1
            row['xp'] += gained
            xp_total += gained

        # --- записываем дневные сводки и считаем серию --------------------
        submitted_days = set(
            Submission.objects.filter(
                student=user, status__in=('submitted', 'reviewed'),
                submitted_at__isnull=False)
            .values_list('submitted_at', flat=True))
        submitted_days = {timezone.localtime(d).date() for d in submitted_days}

        summaries = []
        counted_days = []
        for day in sorted(days):
            row = days[day]
            counts = day_counts_for_streak(row['att'], day in submitted_days)
            if counts:
                counted_days.append(day)
            summaries.append(DailySummary(
                user=user, date=day, xp_earned=row['xp'],
                problems_attempted=row['att'], problems_solved=row['solved'],
                time_spent_seconds=row['sec'], counted_for_streak=counts))
        DailySummary.objects.bulk_create(summaries)

        streak, longest, freezes, used, period = self._streak(counted_days)

        profile, _ = StudentProgressProfile.objects.get_or_create(user=user)
        profile.xp_total = xp_total
        profile.level = level_for_xp(xp_total)
        profile.current_streak = streak
        profile.longest_streak = longest
        profile.last_active_date = counted_days[-1] if counted_days else None
        profile.freezes_available = freezes
        profile.freezes_used_this_month = used
        profile.freezes_period = period
        profile.save()

        for topic_id, bucket in topics.items():
            row, _ = StudentTopicProgress.objects.get_or_create(
                student=user, topic_id=topic_id)
            row.attempted = bucket['a']
            row.solved = bucket['s']
            row.solved_hard = bucket['h']
            row.mastery_level = mastery_for(bucket['s'], bucket['a'],
                                            bucket['h'])
            row.last_activity_at = bucket['at']
            row.level = min(100, int(round(
                bucket['s'] * 100.0 / max(bucket['a'], 1))))
            row.save()

        update_records(user)
        check_achievements(user)

        return {'xp': xp_total, 'level': profile.level, 'streak': streak,
                'longest': longest, 'days': len(counted_days),
                'topics': len(topics)}

    @staticmethod
    def _streak(counted_days):
        """Серия по списку зачтённых дней, с тратой заморозок по ходу.

        Заморозки считаются ПОМЕСЯЧНО и в хронологии, а не «две на всё
        время»: иначе пересчёт задним числом раздал бы ученику заморозки,
        которых у него в тот месяц не было.
        """
        from problems.gamification import FREEZES_PER_MONTH

        if not counted_days:
            return 0, 0, FREEZES_PER_MONTH, 0, None

        streak = longest = 0
        period = None
        freezes = FREEZES_PER_MONTH
        used = 0
        previous = None
        for day in counted_days:
            current_period = month_start(day)
            if current_period != period:
                period = current_period
                freezes = FREEZES_PER_MONTH
                used = 0
            if previous is None:
                streak = 1
            else:
                gap = (day - previous).days
                if gap == 1:
                    streak += 1
                elif gap > 1:
                    missed = gap - 1
                    if missed <= freezes:
                        freezes -= missed
                        used += missed
                        streak += 1
                    else:
                        streak = 1
            longest = max(longest, streak)
            previous = day

        # Серия жива, только если последний зачтённый день — сегодня или
        # вчера (с поправкой на заморозки). Иначе она уже прервалась, просто
        # событие «прерывания» никто не записывал: его и не бывает.
        today = timezone.localdate()
        gap = (today - counted_days[-1]).days
        if gap > 1 + freezes:
            streak = 0
        return streak, longest, freezes, used, period
