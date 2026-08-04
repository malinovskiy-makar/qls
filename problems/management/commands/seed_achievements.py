"""
Справочник достижений. Идемпотентна: правит существующие по `code`,
не плодит дубли, ничего не удаляет.

ПРИНЦИП НАБОРА: награждаем ГЛУБИНУ и КАЧЕСТВО, а не количество кликов.

Чего здесь НЕТ и не будет:
* достижений за заходы на сайт без учебной работы — они поощряют пустой
  заход, а нам нужен решённый пример;
* достижений за СКОРОСТЬ ответа — быстрее всего отвечает тот, кто гадает,
  и награда за скорость учит именно гадать.
"""
from django.core.management.base import BaseCommand

# (код, значок, название, условие для человека, категория, машинное условие)
ACHIEVEMENTS = [
    # --- Глубина: разобрался в теме, взял трудное ------------------------
    ('first_topic_mastered', '🧭', 'Первая освоенная тема',
     'Довести одну тему до уровня «разобрался»',
     'depth', {'type': 'topics_mastered', 'value': 1}),
    ('five_topics_mastered', '🗺️', 'Пять тем на «разобрался»',
     'Довести пять тем до уровня «разобрался»',
     'depth', {'type': 'topics_mastered', 'value': 5}),
    ('ten_topics_confident', '📚', 'Широкий охват',
     'Десять тем на уровне «уверенно» или выше',
     'depth', {'type': 'topics_confident', 'value': 10}),
    ('ten_hard', '⛰️', 'Десять трудных',
     'Решить 10 задач повышенной сложности (4–5)',
     'depth', {'type': 'hard_solved', 'value': 10}),
    ('fifty_hard', '🏔️', 'Полсотни трудных',
     'Решить 50 задач повышенной сложности (4–5)',
     'depth', {'type': 'hard_solved', 'value': 50}),
    ('max_difficulty', '💎', 'Пятая сложность',
     'Решить задачу максимальной сложности',
     'depth', {'type': 'hardest_solved', 'value': 5}),

    # --- Постоянство: серия дней и недельная цель ------------------------
    ('streak_3', '🌱', 'Три дня подряд',
     'Заниматься три дня подряд',
     'consistency', {'type': 'streak', 'value': 3}),
    ('streak_7', '🔥', 'Неделя без пропусков',
     'Серия из 7 дней',
     'consistency', {'type': 'streak', 'value': 7}),
    ('streak_30', '🌟', 'Месяц без пропусков',
     'Серия из 30 дней',
     'consistency', {'type': 'streak', 'value': 30}),
    ('streak_100', '👑', 'Сто дней',
     'Серия из 100 дней',
     'consistency', {'type': 'streak', 'value': 100}),
    ('weekly_goal_4', '🎯', 'Месяц по плану',
     'Выполнить недельную цель четыре недели подряд',
     'consistency', {'type': 'weekly_goal_streak', 'value': 4}),
    ('weekly_goal_12', '🎖️', 'Квартал по плану',
     'Выполнить недельную цель двенадцать недель подряд',
     'consistency', {'type': 'weekly_goal_streak', 'value': 12}),
    ('active_days_50', '📅', 'Пятьдесят учебных дней',
     'Пятьдесят дней с настоящей работой',
     'consistency', {'type': 'active_days', 'value': 50}),

    # --- Мастерство: верные подряд, чистые работы ------------------------
    ('row_10', '🎣', 'Десять подряд',
     'Десять верных ответов подряд',
     'skill', {'type': 'correct_in_row', 'value': 10}),
    ('row_25', '🏹', 'Двадцать пять подряд',
     'Двадцать пять верных ответов подряд',
     'skill', {'type': 'correct_in_row', 'value': 25}),
    ('row_50', '🎯', 'Полсотни подряд',
     'Пятьдесят верных ответов подряд',
     'skill', {'type': 'correct_in_row', 'value': 50}),
    ('level_5', '📈', 'Пятый уровень',
     'Достичь пятого уровня',
     'skill', {'type': 'level', 'value': 5}),
    ('level_10', '🚀', 'Десятый уровень',
     'Достичь десятого уровня',
     'skill', {'type': 'level', 'value': 10}),
    ('level_20', '🛰️', 'Двадцатый уровень',
     'Достичь двадцатого уровня',
     'skill', {'type': 'level', 'value': 20}),

    # --- Вехи: первые разы и круглые числа -------------------------------
    ('first_solved', '✅', 'Первая решённая',
     'Решить первую задачу верно',
     'milestone', {'type': 'problems_solved', 'value': 1}),
    ('solved_25', '🥉', 'Двадцать пять задач',
     'Решить 25 задач',
     'milestone', {'type': 'problems_solved', 'value': 25}),
    ('solved_100', '🥈', 'Сотня',
     'Решить 100 задач',
     'milestone', {'type': 'problems_solved', 'value': 100}),
    ('solved_500', '🥇', 'Пятьсот',
     'Решить 500 задач',
     'milestone', {'type': 'problems_solved', 'value': 500}),
    ('first_homework', '📗', 'Первая домашка',
     'Сдать первую домашнюю работу',
     'milestone', {'type': 'homeworks_submitted', 'value': 1}),
    ('homework_10', '📚', 'Десять домашек',
     'Сдать десять домашних работ',
     'milestone', {'type': 'homeworks_submitted', 'value': 10}),
    ('first_exam', '📝', 'Первая контрольная',
     'Написать первую контрольную',
     'milestone', {'type': 'exams_taken', 'value': 1}),
    ('exam_5', '🗂️', 'Пять контрольных',
     'Написать пять контрольных',
     'milestone', {'type': 'exams_taken', 'value': 5}),
    ('xp_1000', '⚡', 'Тысяча опыта',
     'Набрать 1 000 опыта',
     'milestone', {'type': 'xp', 'value': 1000}),
    ('xp_5000', '🔋', 'Пять тысяч опыта',
     'Набрать 5 000 опыта',
     'milestone', {'type': 'xp', 'value': 5000}),
]


class Command(BaseCommand):
    help = 'Заполняет справочник достижений. Идемпотентна.'

    def handle(self, *args, **options):
        from problems.models import Achievement

        created = updated = 0
        for order, (code, icon, title, description, category,
                    condition) in enumerate(ACHIEVEMENTS):
            obj, is_new = Achievement.objects.update_or_create(
                code=code,
                defaults={'icon': icon, 'title': title,
                          'description': description, 'category': category,
                          'condition': condition, 'order': order})
            created += int(is_new)
            updated += int(not is_new)

        if options.get('verbosity', 1) >= 1:
            self.stdout.write(self.style.SUCCESS(
                f'Достижений: всего {len(ACHIEVEMENTS)}, '
                f'создано {created}, обновлено {updated}.'))
