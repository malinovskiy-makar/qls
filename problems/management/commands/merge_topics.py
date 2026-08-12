# -*- coding: utf-8 -*-
"""
Перевесить задачи и учебные данные с посторонних тем на канонические.

Таблица соответствий и правила — в `problems/topic_merge.py` (читается
глазами). Здесь только механика переноса.

    ./venv/bin/python manage.py merge_topics              # холостой прогон
    ./venv/bin/python manage.py merge_topics --confirm    # боевой

⚠️ КОМАНДА, А НЕ МИГРАЦИЯ СХЕМЫ. Это правка ДАННЫХ, её надо уметь прогнать
вхолостую, посмотреть глазами и повторить на проде отдельно от выкатки кода.

⚠️ ДВИГАЕМ ВСЕ ССЫЛКИ НА ТЕМУ, не только M2M задачи. Тема в статистике
берётся из снимка в событии (`LearningEvent.topic`), и без переноса событий
посторонняя колонка в теплокарте осталась бы на месте — то есть ровно то,
на что жаловался владелец, не починилось бы.

⚠️ СТРОКУ СТАРОЙ ТЕМЫ НЕ УДАЛЯЕМ. У `Topic` каскадные потомки (`Subtopic`,
`TheoryPage`, `StudentTopicProgress`); удаление увело бы за собой чужие
данные. Опустевшая тема просто перестаёт попадать в выдачу.

Идемпотентна: повторный прогон находит ноль связей и ничего не меняет.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from problems import topic_merge
from problems.management.commands.apply_topic_mapping import (
    CANONICAL, ensure_canonical_topics,
)
from problems.models import (
    AutoTopicAssignment, MistakeTag, Problem, Skill, StudentTopicProgress,
    Subtopic, TheoryPage, Topic,
)
from problems.models_platform import CustomProblem, LearningEvent


class Command(BaseCommand):
    help = ('Свести посторонние темы к каноническим по таблице '
            'problems/topic_merge.py. По умолчанию — холостой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='боевой прогон (без него только показываем)')

    # -- вспомогательное ---------------------------------------------------

    def _topics_with_events(self):
        """Имена НЕканонических тем, на которых висят учебные события."""
        canon = set(CANONICAL)
        names = (LearningEvent.objects.filter(topic__isnull=False)
                 .values_list('topic__name', flat=True).distinct())
        return {name for name in names if name not in canon}

    def _counts(self, topic):
        """Сколько связей висит на теме — по каждому виду отдельно."""
        return {
            'задач': topic.problems.count(),
            'событий': LearningEvent.objects.filter(topic=topic).count(),
            'прогресс': StudentTopicProgress.objects.filter(topic=topic).count(),
            'автотем': AutoTopicAssignment.objects.filter(topic=topic).count(),
            'своих задач': CustomProblem.objects.filter(topic=topic).count(),
            'навыков': topic.skills.count(),
            'ошибок': MistakeTag.objects.filter(topics=topic).count(),
            'подтем': Subtopic.objects.filter(topic=topic).count(),
            'теории': TheoryPage.objects.filter(topic=topic).count(),
        }

    # -- перенос -----------------------------------------------------------

    def _move(self, old, new):
        """Переносит все связи со старой темы на новую. Возвращает счётчики."""
        moved = {}

        # Задачи: добавляем новую тему, снимаем старую. Задача, у которой уже
        # стоит новая тема, просто теряет старую — дубля не будет (M2M).
        problems = list(old.problems.all())
        for problem in problems:
            problem.topics.add(new)
            problem.topics.remove(old)
        moved['задач'] = len(problems)

        moved['событий'] = (LearningEvent.objects.filter(topic=old)
                            .update(topic=new))
        moved['своих задач'] = (CustomProblem.objects.filter(topic=old)
                                .update(topic=new))
        moved['подтем'] = Subtopic.objects.filter(topic=old).update(topic=new)
        moved['теории'] = TheoryPage.objects.filter(topic=old).update(topic=new)

        # Навыки и ошибки — M2M, тем же приёмом.
        skills = list(Skill.objects.filter(topics=old))
        for skill in skills:
            skill.topics.add(new)
            skill.topics.remove(old)
        moved['навыков'] = len(skills)
        mistakes = list(MistakeTag.objects.filter(topics=old))
        for mistake in mistakes:
            mistake.topics.add(new)
            mistake.topics.remove(old)
        moved['ошибок'] = len(mistakes)

        # ⚠️ У прогресса по теме ключ (ученик, тема). Если у ученика уже есть
        # строка по НОВОЙ теме, простой update упёрся бы в уникальность —
        # складываем счётчики и удаляем лишнюю строку.
        merged = 0
        for row in StudentTopicProgress.objects.filter(topic=old):
            twin = (StudentTopicProgress.objects
                    .filter(student=row.student, topic=new).first())
            if twin is None:
                row.topic = new
                row.save(update_fields=['topic'])
                continue
            twin.attempted += row.attempted
            twin.solved += row.solved
            twin.solved_hard += row.solved_hard
            twin.mastery_level = max(twin.mastery_level, row.mastery_level)
            twin.level = max(twin.level, row.level)
            if row.last_activity_at and (
                    twin.last_activity_at is None
                    or row.last_activity_at > twin.last_activity_at):
                twin.last_activity_at = row.last_activity_at
            twin.save()
            row.delete()
            merged += 1
        moved['прогресс'] = (StudentTopicProgress.objects
                             .filter(topic=new).count())
        moved['прогресс слито'] = merged

        # ⚠️ У автотемы ключ (задача, тема) — та же ловушка.
        dropped = 0
        for row in AutoTopicAssignment.objects.filter(topic=old):
            if AutoTopicAssignment.objects.filter(problem=row.problem,
                                                  topic=new).exists():
                row.delete()
                dropped += 1
            else:
                row.topic = new
                row.save(update_fields=['topic'])
        moved['автотем слито'] = dropped
        return moved

    # -- точка входа -------------------------------------------------------

    def handle(self, *args, **opts):
        confirm = opts['confirm']
        write = self.stdout.write

        # Новые канонические темы должны существовать до перевешивания.
        created = []
        for name in CANONICAL:
            if not Topic.objects.filter(name=name).exists():
                created.append(name)
        if created:
            write('Будут созданы канонические темы: %s' % ', '.join(created))
            if confirm:
                ensure_canonical_topics(dry_run=False)

        rows = topic_merge.plan(self._topics_with_events())
        stuck = topic_merge.unresolved(self._topics_with_events())

        write('')
        write('%-62s %-38s %s' % ('ОТКУДА', 'КУДА', 'ПРАВИЛО'))
        write('-' * 118)

        total = {}
        real_rows = []
        for old_name, new_name, rule in rows:
            old = Topic.objects.filter(name=old_name).first()
            new = Topic.objects.filter(name=new_name).first()
            if old is None:
                write('%-62s %-38s ПРОПУСК: темы нет в базе'
                      % (old_name[:60], new_name[:36]))
                continue
            if new is None:
                write('%-62s %-38s ПРОПУСК: цели нет в базе'
                      % (old_name[:60], new_name[:36]))
                continue
            counts = self._counts(old)
            if not any(counts.values()):
                continue                       # уже перевешено
            real_rows.append((old, new))
            write('%-62s %-38s %s' % (old_name[:60], new_name[:36], rule))
            write('      ' + ', '.join('%s %s' % (v, k)
                                       for k, v in counts.items() if v))
            for key, value in counts.items():
                total[key] = total.get(key, 0) + value

        write('')
        if not real_rows:
            write('Перевешивать нечего — все темы уже канонические.')
        else:
            write('ИТОГО поедет: ' + ', '.join('%s %s' % (v, k)
                                               for k, v in total.items() if v))
        if stuck:
            write('')
            write('БЕЗ ДОМА (остаются как есть, колонка в статистике '
                  'сохранится): %s' % ', '.join(stuck))

        if not confirm:
            write('')
            write('Холостой прогон. Ничего не изменено. '
                  'Боевой запуск: --confirm')
            return

        with transaction.atomic():
            for old, new in real_rows:
                moved = self._move(old, new)
                write('перевешено «%s» → «%s»: %s'
                      % (old.name, new.name,
                         ', '.join('%s %s' % (v, k)
                                   for k, v in moved.items() if v)))

        # Контроль: после прогона на старых темах не должно остаться ничего.
        left = []
        for old, _ in real_rows:
            counts = self._counts(old)
            if any(counts.values()):
                left.append('%s: %s' % (old.name, counts))
        write('')
        if left:
            write('⚠️ ОСТАЛОСЬ: %s' % '; '.join(left))
        else:
            write('Готово. На перевешенных темах не осталось ни одной связи.')
