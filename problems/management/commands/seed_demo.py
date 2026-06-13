"""
Скрипт-наполнитель для Этапов 1–3.

Запускается командой:  python manage.py seed_demo

Что делает:
  1. Создаёт учётную запись преподавателя-администратора (если её ещё нет).
  2. Создаёт несколько тем, тегов и источник.
  3. Добавляет 2–3 задачи-примера по олимпиадной экономике.
  4. (Этап 2) Добавляет примеры навыков и типичных ошибок.
  5. (Этап 3) Создаёт тестового ученика, занятие, домашку, решение и проверку.

Скрипт безопасно запускать повторно: он не плодит дубликаты, а находит уже
созданные записи по ключевым полям.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

import datetime

from problems.models import (
    Assignment,
    CalendarEvent,
    Lesson,
    MistakeTag,
    Problem,
    ProblemPart,
    Skill,
    Source,
    SourceReference,
    StudentGroup,
    Submission,
    Subtopic,
    Tag,
    TeacherFeedback,
    Topic,
    User,
)

# Данные для учётной записи преподавателя. Это ЛОКАЛЬНЫЙ сайт у тебя на
# компьютере, поэтому простой пароль допустим. Позже его можно сменить.
ADMIN_LOGIN = 'admin'
ADMIN_PASSWORD = 'admin12345'


class Command(BaseCommand):
    help = ('Создаёт учётку преподавателя, задачи-примеры (Этап 1), '
            'навыки и типичные ошибки (Этап 2), '
            'занятие / домашку / решение / проверку (Этап 3).')

    @transaction.atomic
    def handle(self, *args, **options):
        teacher = self._create_teacher()
        teacher1 = self._create_teacher1()
        topics = self._create_topics()
        tags = self._create_tags()
        source = self._create_source()
        self._create_problems(teacher, topics, tags, source)
        self._create_pedagogy(topics)  # Этап 2: навыки и типичные ошибки
        self._create_lesson_cycle(teacher, teacher1)  # Этап 3: занятие → домашка → решение → проверка
        group = self._create_student_group(teacher1)  # Этап Е: группа учеников
        self._create_calendar_events(teacher, teacher1, group)  # Этап Ж: события календаря
        self.stdout.write(self.style.SUCCESS(
            '\nГотово! Данные-примеры созданы.\n'
            f'Вход в админку:  логин «{ADMIN_LOGIN}», пароль «{ADMIN_PASSWORD}».'
        ))

    # --- учётная запись teacher1 (не-admin преподаватель) ---
    def _create_teacher1(self):
        teacher, created = User.objects.get_or_create(
            username='teacher1',
            defaults={
                'role': 'teacher',
                'first_name': 'Анна',
                'last_name': 'Петрова',
                'email': 'teacher1@example.com',
                'is_staff': False,
                'is_superuser': False,
            },
        )
        if created:
            teacher.set_password('teacher12345')
            teacher.save()
            self.stdout.write('  + создан teacher1 / teacher12345')
        else:
            self.stdout.write('  · teacher1 уже существует')
        return teacher

    # --- группа учеников для teacher1 ---
    def _create_student_group(self, teacher1):
        group, _ = StudentGroup.objects.get_or_create(
            name='Тестовая группа',
            teacher=teacher1,
        )
        student = User.objects.filter(username='student1').first()
        if student:
            group.students.add(student)
            self.stdout.write('  + student1 добавлен в «Тестовую группу» teacher1')
        return group

    # --- учётная запись преподавателя ---
    def _create_teacher(self):
        teacher, created = User.objects.get_or_create(
            username=ADMIN_LOGIN,
            defaults={
                'role': User.Role.TEACHER,
                'is_staff': True,      # доступ в админку
                'is_superuser': True,  # полные права
                'first_name': 'Преподаватель',
            },
        )
        if created:
            teacher.set_password(ADMIN_PASSWORD)
            teacher.save()
            self.stdout.write(f'  + создан преподаватель «{ADMIN_LOGIN}»')
        else:
            self.stdout.write(f'  · преподаватель «{ADMIN_LOGIN}» уже есть')
        return teacher

    # --- темы и подтемы ---
    def _create_topics(self):
        data = {
            'Спрос и предложение': ['Эластичность', 'Рыночное равновесие'],
            'Издержки фирмы': ['Виды издержек', 'Кривая производственных возможностей'],
            'Теория игр': ['Равновесие Нэша'],
        }
        topics = {}
        for order, (name, subs) in enumerate(data.items(), start=1):
            topic, _ = Topic.objects.get_or_create(
                name=name, defaults={'slug': self._slug(name), 'order': order})
            for s_order, sub_name in enumerate(subs, start=1):
                Subtopic.objects.get_or_create(
                    topic=topic, name=sub_name,
                    defaults={'slug': self._slug(sub_name), 'order': s_order})
            topics[name] = topic
        self.stdout.write(f'  + темы: {", ".join(topics)}')
        return topics

    # --- теги ---
    def _create_tags(self):
        names = ['базовая', 'с графиком', 'с подпунктами']
        tags = {}
        for name in names:
            tag, _ = Tag.objects.get_or_create(
                name=name, defaults={'slug': self._slug(name)})
            tags[name] = tag
        return tags

    # --- источник ---
    def _create_source(self):
        source, _ = Source.objects.get_or_create(
            name='Задачник Бахарева',
            defaults={'kind': 'задачник',
                      'note': 'Учебный сборник по олимпиадной экономике.'},
        )
        return source

    # --- задачи-примеры ---
    def _create_problems(self, teacher, topics, tags, source):
        # Задача 1 — простая, ответ без подпунктов.
        # owner=teacher гарантирует уникальность даже если в базе
        # есть импортированные задачи с тем же названием.
        p1, created1 = Problem.objects.get_or_create(
            title='Эластичность спроса по цене',
            owner=teacher,
            defaults={
                'statement': (
                    'Цена товара выросла с 100 до 120 рублей, а объём спроса '
                    'упал с 50 до 40 единиц. Найдите коэффициент ценовой '
                    'эластичности спроса (по средней точке) и определите, '
                    'эластичен спрос или нет.'
                ),
                'answer': (
                    'E ≈ −1,22 (по модулю больше 1) — спрос эластичен.'
                ),
                'solution': (
                    'По формуле средней точки: '
                    'E = (ΔQ/среднее Q) / (ΔP/среднее P) = '
                    '(−10/45) / (20/110) ≈ −1,22.'
                ),
                'difficulty': 2,
                'difficulty_native': '*',
                'problem_type': 'расчётная',
                'status': Problem.Status.PUBLISHED,
                'owner': teacher,
            },
        )
        if created1:
            p1.topics.add(topics['Спрос и предложение'])
            p1.tags.add(tags['базовая'])
            SourceReference.objects.create(
                problem=p1, source=source, problem_number='1', page='12')

        # Задача 2 — с подпунктами а/б, у каждого свой ответ.
        p2, created2 = Problem.objects.get_or_create(
            title='Издержки фирмы',
            owner=teacher,
            defaults={
                'statement': (
                    'Фирма за месяц произвела 100 единиц продукции. '
                    'Постоянные издержки равны 2000 руб., переменные — 3000 руб.'
                ),
                'difficulty': 2,
                'difficulty_native': '*',
                'problem_type': 'расчётная',
                'status': Problem.Status.PUBLISHED,
                'owner': teacher,
            },
        )
        if created2:
            p2.topics.add(topics['Издержки фирмы'])
            p2.tags.add(tags['с подпунктами'])
            ProblemPart.objects.create(
                problem=p2, label='а', order=1,
                statement='Найдите общие издержки (TC).',
                answer='TC = 2000 + 3000 = 5000 руб.', points=1)
            ProblemPart.objects.create(
                problem=p2, label='б', order=2,
                statement='Найдите средние общие издержки (ATC).',
                answer='ATC = 5000 / 100 = 50 руб. за единицу.', points=1)
            SourceReference.objects.create(
                problem=p2, source=source, problem_number='2', page='45')

        # Задача 3 — теория игр, только ответ (решение не приводим).
        p3, created3 = Problem.objects.get_or_create(
            title='Равновесие Нэша в «дилемме заключённого»',
            owner=teacher,
            defaults={
                'statement': (
                    'В классической «дилемме заключённого» у каждого игрока две '
                    'стратегии: молчать или сознаться. Найдите равновесие Нэша.'
                ),
                'answer': (
                    'Равновесие Нэша — оба игрока сознаются: «сознаться» — '
                    'доминирующая стратегия для каждого.'
                ),
                'difficulty': 3,
                'difficulty_native': '**',
                'problem_type': 'теоретическая',
                'status': Problem.Status.PUBLISHED,
                'owner': teacher,
            },
        )
        if created3:
            p3.topics.add(topics['Теория игр'])
            p3.tags.add(tags['базовая'])

        created_count = sum([created1, created2, created3])
        self.stdout.write(
            f'  + задачи-примеры: создано {created_count}, '
            f'уже было {3 - created_count}')

    # --- Этап 2: навыки и типичные ошибки ---
    def _create_pedagogy(self, topics):
        # 4–5 примеров навыков. Пользователь сам добавит свои через админку —
        # это лишь стартовый набор, никакого фиксированного списка в коде нет.
        skills_data = [
            ('Построить КПВ', 'Изобразить кривую производственных возможностей.',
             ['Издержки фирмы']),
            ('Найти MR', 'Вывести предельный доход из функции спроса.',
             ['Спрос и предложение']),
            ('Посчитать DWL', 'Найти чистые потери общества (deadweight loss).',
             ['Спрос и предложение']),
            ('Проверить NE', 'Проверить, является ли исход равновесием Нэша.',
             ['Теория игр']),
            ('Написать интерпретацию', 'Словами объяснить экономический смысл '
             'полученного результата.', []),
        ]
        skills = {}
        for name, desc, topic_names in skills_data:
            skill, _ = Skill.objects.get_or_create(
                name=name, defaults={'description': desc})
            for tname in topic_names:
                if tname in topics:
                    skill.topics.add(topics[tname])
            skills[name] = skill

        # 2–3 типичные ошибки.
        mistakes_data = [
            ('Эластичность без модуля',
             'Ученик забывает, что эластичность спроса сравнивают по модулю.',
             ['Спрос и предложение']),
            ('Путает сдвиг и движение вдоль кривой',
             'Сдвиг всей кривой спроса путают с движением вдоль неё.',
             ['Спрос и предложение']),
            ('Игнорирует доминирующую стратегию',
             'В теории игр не проверяет наличие доминирующей стратегии.',
             ['Теория игр']),
        ]
        mistakes = {}
        for name, desc, topic_names in mistakes_data:
            mistake, _ = MistakeTag.objects.get_or_create(
                name=name, defaults={'description': desc})
            for tname in topic_names:
                if tname in topics:
                    mistake.topics.add(topics[tname])
            mistakes[name] = mistake

        # Привяжем навыки/ошибки к уже созданным задачам (если они есть).
        p_elastic = Problem.objects.filter(
            title='Эластичность спроса по цене').first()
        if p_elastic:
            p_elastic.skills.add(skills['Написать интерпретацию'])
            p_elastic.mistakes.add(mistakes['Эластичность без модуля'])

        p_game = Problem.objects.filter(
            title='Равновесие Нэша в «дилемме заключённого»').first()
        if p_game:
            p_game.skills.add(skills['Проверить NE'])
            p_game.mistakes.add(mistakes['Игнорирует доминирующую стратегию'])

        self.stdout.write(
            f'  + навыки: {len(skills)}, типичные ошибки: {len(mistakes)}')

    # --- Этап 3: занятие → домашка → решение → проверка ---
    def _create_lesson_cycle(self, teacher, lesson_author=None):
        # 1. Тестовый ученик.
        student, s_created = User.objects.get_or_create(
            username='student1',
            defaults={
                'role': User.Role.STUDENT,
                'first_name': 'Иван',
                'last_name': 'Иванов',
                'email': 'student1@example.com',
            },
        )
        if s_created:
            student.set_password('student12345')
            student.save()
            self.stdout.write('  + создан ученик «student1» (пароль: student12345)')
        else:
            self.stdout.write('  · ученик «student1» уже есть')

        # Берём именно seed-задачи (созданные в _create_problems с owner=teacher).
        p_elastic = Problem.objects.filter(
            title='Эластичность спроса по цене', owner=teacher).first()
        p_costs = Problem.objects.filter(
            title='Издержки фирмы', owner=teacher).first()
        if not p_elastic or not p_costs:
            self.stdout.write('  ! задачи-примеры не найдены, пропускаю Этап 3')
            return

        # lesson_author — тот, кто «ведёт» занятие (teacher1); teacher — владелец задач (admin).
        if lesson_author is None:
            lesson_author = teacher

        # 2. Занятие.
        lesson, _ = Lesson.objects.get_or_create(
            name='Занятие 1: Спрос, предложение и издержки',
            defaults={
                'date': datetime.date(2026, 9, 1),
                'goals': 'Повторить ценовую эластичность. '
                         'Разобрать виды издержек фирмы.',
                'duration_minutes': 90,
                'warm_up': 'Быстрый опрос: что такое эластичный спрос?',
                'teacher_notes': 'Обратить внимание на задачу 1 — '
                                 'ученики часто забывают брать по модулю.',
                'author': lesson_author,
            },
        )
        if lesson.author != lesson_author:
            lesson.author = lesson_author
            lesson.save()
        lesson.main_problems.add(p_elastic)
        lesson.challenge_problems.add(p_costs)
        lesson.homework_problems.add(p_elastic, p_costs)

        # 3. Домашка.
        assignment, _ = Assignment.objects.get_or_create(
            name='Домашка к занятию 1',
            defaults={
                'lesson': lesson,
                'author': lesson_author,
                'deadline': datetime.datetime(2026, 9, 8, 23, 59,
                                              tzinfo=datetime.timezone.utc),
            },
        )
        if assignment.author != lesson_author:
            assignment.author = lesson_author
            assignment.save()
        assignment.problems.add(p_elastic, p_costs)
        assignment.students.add(student)

        # 4а. Решение ученика по задаче 1 (эластичность) — проверено.
        submission, sub_created = Submission.objects.get_or_create(
            student=student,
            assignment=assignment,
            problem=p_elastic,
            defaults={
                'solution_text': (
                    'Вычислю коэффициент по формуле средней точки.\n'
                    'ΔQ = 40 − 50 = −10, среднее Q = 45.\n'
                    'ΔP = 120 − 100 = 20, среднее P = 110.\n'
                    'E = (−10/45) / (20/110) = −0,222 / 0,182 ≈ −1,22.\n'
                    'Так как |E| > 1, спрос эластичен.'
                ),
                'submitted_answer': 'E ≈ −1,22, спрос эластичен.',
                'status': Submission.Status.REVIEWED,
                'submitted_at': datetime.datetime(2026, 9, 5, 18, 0,
                                                  tzinfo=datetime.timezone.utc),
            },
        )
        # Обновляем статус если запись уже существовала со старым статусом
        if not sub_created and submission.status != Submission.Status.REVIEWED:
            submission.status = Submission.Status.REVIEWED
            submission.save()

        # 5. Проверка преподавателя.
        if sub_created or not TeacherFeedback.objects.filter(
                submission=submission).exists():
            feedback, _ = TeacherFeedback.objects.get_or_create(
                submission=submission,
                defaults={
                    'score': 4.5,
                    'comment': (
                        'Верный ход. Молодец, что взял по модулю и написал '
                        'вывод словами. Небольшое замечание: запиши '
                        'промежуточные шаги аккуратнее.'
                    ),
                    'reviewed_by': teacher,
                },
            )
            # Отмечаем ошибку для примера обратной связи.
            err = MistakeTag.objects.filter(
                name='Эластичность без модуля').first()
            if err:
                feedback.mistakes.add(err)

        # 4б. Решение по задаче 2 (издержки) — отправлено, ждёт проверки.
        Submission.objects.get_or_create(
            student=student,
            assignment=assignment,
            problem=p_costs,
            defaults={
                'solution_text': 'FC = 500, VC = 200*Q. При Q=10: TC = 2500.',
                'submitted_answer': 'TC = 2500 руб.',
                'status': Submission.Status.SUBMITTED,
                'submitted_at': datetime.datetime(2026, 9, 5, 19, 30,
                                                  tzinfo=datetime.timezone.utc),
            },
        )

        self.stdout.write(
            f'  + занятие, домашка, решения и проверка — готово '
            f'(ученик: student1 / пароль: student12345)')

    # --- Этап Ж: события календаря ---
    def _create_calendar_events(self, admin_user, teacher1, group):
        """
        Создаёт три тестовых события:
         1. Занятие «МОШ 10–11» каждый понедельник в 18:00 на 4 недели.
         2. Домашка «Налоги и субсидии» с дедлайном через 2 недели.
         3. Олимпиада «МОШ отборочный этап» через 3 недели (глобальная).
        """
        # Даты привязаны к реальному расписанию (июнь–июль 2026).
        # Понедельники после 2026-06-11: 15, 22, 29 июня и 6 июля.
        mon1 = datetime.datetime(2026, 6, 15, 18, 0, tzinfo=datetime.timezone.utc)
        mon1_end = datetime.datetime(2026, 6, 15, 19, 30, tzinfo=datetime.timezone.utc)

        # --- 1. Повторяющееся занятие (4 недели) ---
        lesson_ev, lesson_created = CalendarEvent.objects.get_or_create(
            title='МОШ 10–11',
            start_datetime=mon1,
            defaults={
                'event_type': 'lesson',
                'color': '#3b82f6',
                'end_datetime': mon1_end,
                'description': 'Онлайн-занятие по микроэкономике',
                'author': teacher1,
                'is_global': False,
                'is_recurring': True,
                'recur_weeks': 4,
            },
        )
        if lesson_created:
            lesson_ev.groups.add(group)
            # Создаём повторения: +1, +2, +3 недели
            for week in range(1, 4):
                delta = datetime.timedelta(weeks=week)
                copy, _ = CalendarEvent.objects.get_or_create(
                    title='МОШ 10–11',
                    start_datetime=mon1 + delta,
                    defaults={
                        'event_type': 'lesson',
                        'color': '#3b82f6',
                        'end_datetime': mon1_end + delta,
                        'description': 'Онлайн-занятие по микроэкономике',
                        'author': teacher1,
                        'is_global': False,
                        'is_recurring': True,
                        'recur_weeks': 4,
                        'parent_event': lesson_ev,
                    },
                )
                copy.groups.add(group)
            self.stdout.write('  + занятие «МОШ 10–11» × 4 недели создано')
        else:
            self.stdout.write('  · занятие «МОШ 10–11» уже существует')

        # --- 2. Домашка «Налоги и субсидии» ---
        hw_deadline = datetime.datetime(2026, 6, 25, 23, 59, tzinfo=datetime.timezone.utc)
        hw_start    = datetime.datetime(2026, 6, 25, 23, 59, tzinfo=datetime.timezone.utc)
        assignment  = Assignment.objects.filter(name='Домашка к занятию 1').first()

        hw_ev, hw_created = CalendarEvent.objects.get_or_create(
            title='Налоги и субсидии',
            start_datetime=hw_start,
            defaults={
                'event_type': 'homework',
                'color': '#f97316',
                'description': 'Дедлайн сдачи домашки',
                'assignment': assignment,
                'author': teacher1,
                'is_global': False,
            },
        )
        if hw_created:
            hw_ev.groups.add(group)
            self.stdout.write('  + домашка «Налоги и субсидии» создана (дедлайн 25 июня)')
        else:
            self.stdout.write('  · домашка «Налоги и субсидии» уже существует')

        # --- 3. Олимпиада «МОШ отборочный этап» (глобальная, от admin) ---
        olympiad_start = datetime.datetime(2026, 7, 2, 9, 0, tzinfo=datetime.timezone.utc)
        olympiad_end   = datetime.datetime(2026, 7, 2, 13, 0, tzinfo=datetime.timezone.utc)

        ol_ev, ol_created = CalendarEvent.objects.get_or_create(
            title='МОШ отборочный этап',
            start_datetime=olympiad_start,
            defaults={
                'event_type': 'olympiad',
                'color': '#10b981',
                'end_datetime': olympiad_end,
                'description': 'Московская олимпиада школьников, отборочный этап по экономике',
                'author': admin_user,
                'is_global': True,
            },
        )
        if ol_created:
            self.stdout.write('  + олимпиада «МОШ отборочный этап» создана (2 июля, глобальная)')
        else:
            self.stdout.write('  · олимпиада «МОШ отборочный этап» уже существует')

    @staticmethod
    def _slug(text):
        """Простой транслит-слаг для русских названий (латиницей)."""
        table = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
            'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
            'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
            'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
            'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
            'э': 'e', 'ю': 'yu', 'я': 'ya', ' ': '-',
        }
        result = ''.join(table.get(ch, ch) for ch in text.lower())
        return ''.join(c for c in result if c.isalnum() or c == '-')[:200]
