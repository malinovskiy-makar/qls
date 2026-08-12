"""
Демо-данные платформы для репетиторов: репетитор, ученики, родитель, группа,
домашка, две контрольные, комментарии, папки и сохранённые задачи.

Команда ИДЕМПОТЕНТНА: повторный запуск ничего не дублирует — всё создаётся
через get_or_create по устойчивым ключам (логин, название, позиция).

    ./venv/bin/python manage.py seed_platform_demo
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from problems.models import (
    Assignment,
    ParentLink,
    Problem,
    ProblemPart,
    StudentGroup,
    Submission,
    Topic,
    User,
)
from problems.models_platform import (
    AnswerDraft,
    AssignmentItem,
    CustomProblem,
    CustomProblemOption,
    ExamAttempt,
    ProblemComment,
    SavedFolder,
    SavedProblem,
    SavedGraph,
    SolutionVisibility,
    UserProfile,
)

DEMO_PASSWORD = 'demo12345'

TUTOR = 'tutor@test.local'
STUDENTS = ['student1@test.local', 'student2@test.local', 'student3@test.local']
# Индивидуальные ученики (сессия 9, фаза 9): экран занятия один на один
# должно быть на чём смотреть, и «пустой ученик» этого не даёт.
SOLO_STUDENTS = ['solo1@test.local', 'solo2@test.local']
PARENT = 'parent@test.local'


# ---------------------------------------------------------------------------
# Эталонные решения демо-задач
# ---------------------------------------------------------------------------
# ⚠️ Ключ — НАЗВАНИЕ задачи, а не номер позиции. Демо-домашка собирается из
# первых задач банка, и её состав со временем меняется; решение, привязанное
# к «первой позиции», рано или поздно ложится под чужое условие. Витрина,
# где под задачей стоит разбор другой задачи, читается как поломка кода.

SOLUTIONS_BY_TITLE = {
    'Эластичность спроса по цене': {
        'text': (
            'Считаем по средней точке (дуговая эластичность): '
            '$E = \\frac{\\Delta Q}{\\Delta P} \\cdot '
            '\\frac{P_1+P_2}{Q_1+Q_2}$. Здесь '
            '$\\Delta Q = 40-50 = -10$, $\\Delta P = 120-100 = 20$, '
            'сумма цен $220$, сумма количеств $90$. Подставляем: '
            '$E = \\frac{-10}{20}\\cdot\\frac{220}{90} \\approx -1{,}22$. '
            'По модулю больше единицы — спрос эластичен: покупатели реагируют '
            'на цену сильнее, чем она меняется, и рост цены снизит выручку.'),
        'steps': [
            {'text': 'Найти изменения', 'result': 'ΔQ = −10, ΔP = 20'},
            {'text': 'Взять средние', 'result': '(P₁+P₂)=220, (Q₁+Q₂)=90'},
            {'text': 'Подставить в формулу', 'result': 'E ≈ −1,22'},
            {'text': 'Сделать вывод', 'result': '|E| > 1 — спрос эластичен'},
        ],
    },
    # Задача из запасного набора (`_catalog_problems`, когда банк пуст).
    # Именно ей и принадлежал разбор равновесия — раньше он лежал под
    # «первой позицией» и попадал под чужое условие.
    'Равновесие на рынке кофе': {
        'text': (
            'Приравниваем спрос и предложение: $120-2P = 3P-30$, откуда '
            '$5P = 150$ и $P^*=30$. Подставляем в любую из функций: '
            '$Q^* = 120 - 2\\cdot 30 = 60$. Проверка по второй функции '
            'даёт то же самое — значит, решение верное.'),
        'steps': [
            {'text': 'Приравнять Qd и Qs', 'result': '120-2P = 3P-30'},
            {'text': 'Решить уравнение', 'result': 'P* = 30'},
            {'text': 'Найти количество', 'result': 'Q* = 60'},
        ],
    },
    'Издержки фирмы': {
        'text': (
            'Общие издержки — это сумма постоянных и переменных: '
            '$TC = FC + VC = 2000 + 3000 = 5000$ руб. Средние общие издержки '
            'получаем делением на выпуск: '
            '$ATC = \\frac{TC}{Q} = \\frac{5000}{100} = 50$ руб. за единицу.'),
        'steps': [
            {'text': 'Сложить FC и VC', 'result': 'TC = 5000 руб.'},
            {'text': 'Разделить на выпуск', 'result': 'ATC = 50 руб./ед.'},
        ],
    },
}

# По какому слову ищем задачу, к которой график уместен по смыслу.
GRAPH_TITLE_HINTS = ('равновес', 'спрос', 'предлож', 'эластич')


class Command(BaseCommand):
    help = 'Создаёт демо-данные платформы (идемпотентно).'

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()

        tutor = self._user(TUTOR, 'Марина', 'Петрова', 'tutor')
        # ⚠️ Фамилии РАЗНЫЕ. Три Иванова подряд на любом экране выглядят
        # как ошибка выборки: непонятно, три это человека или один и тот же,
        # размноженный багом. Родитель оставлен однофамильцем Петра —
        # у него в демо есть связь именно с ним.
        students = [
            self._user(login, name, surname, 'student', grade=grade)
            for login, name, surname, grade in zip(
                STUDENTS, ['Пётр', 'Анна', 'Сергей'],
                ['Иванов', 'Соколова', 'Дмитриев'], [10, 11, 9])
        ]
        self._user(PARENT, 'Ольга', 'Иванова', 'parent')

        group, _ = StudentGroup.objects.get_or_create(
            name='Экономика 10–11, вторник', teacher=tutor)
        group.students.set(students)
        # Существующая группа могла быть заведена до появления типа занятия.
        if group.kind != StudentGroup.Kind.GROUP:
            group.kind = StudentGroup.Kind.GROUP
            group.save(update_fields=['kind'])

        solo_groups = self._solo_lessons(tutor, now)

        catalog = self._catalog_problems()
        catalog_tests = self._catalog_tests()
        costs = self._costs_problem()
        custom = self._custom_problem(tutor)

        homework = self._homework(tutor, group, students, catalog, custom,
                                  catalog_tests, costs, now)
        self._exam_window(tutor, group, students, catalog, catalog_tests, now)
        self._exam_limit(tutor, group, students, catalog, now)
        self._comments(homework, tutor, students[0])
        graph = self._saved(tutor, catalog, custom)
        self._solutions_and_graph(homework, graph)
        self._partly_correct_submission(homework, students[1], costs)
        self._submitted_tests(homework, students[0])
        self._four_states(homework, students[0], catalog, custom, costs, now)
        self._parent_links(tutor, students)
        self._history(students, now)
        self._history([g.students.first() for g in solo_groups], now,
                      seed_offset=50)
        self._finished_exam(tutor, group, students, now)
        self._work_difficulty(tutor, students)

        self.stdout.write(self.style.SUCCESS('\nДемо-данные готовы.'))
        self.stdout.write('Вход (пароль у всех одинаковый):')
        self.stdout.write(f'  репетитор: {TUTOR} / {DEMO_PASSWORD}')
        for login in STUDENTS:
            self.stdout.write(f'  ученик:    {login} / {DEMO_PASSWORD}')
        for login in SOLO_STUDENTS:
            self.stdout.write(f'  индивид.:  {login} / {DEMO_PASSWORD}')
        self.stdout.write(f'  родитель:  {PARENT} / {DEMO_PASSWORD}')

    # -- кирпичики ---------------------------------------------------------

    def _solo_lessons(self, tutor, now):
        """Два индивидуальных занятия с историей (сессия 9, фаза 9).

        ⚠️ У каждого СВОЯ работа: экран занятия один на один показывает
        историю работ со столбцом «Сдано», и без сданных работ проверять
        там нечего. Одна работа сдана вовремя, вторая — после срока: обе
        пометки должны быть видны глазами.

        Идемпотентно: занятия и работы ищутся по имени.
        """
        from problems.models import (Assignment, AssignmentItem, StudentGroup,
                                     Submission, TeacherFeedback)

        catalog = self._catalog_problems()
        if len(catalog) < 2:
            self.stdout.write('  индивидуальные занятия пропущены: '
                              'в банке мало задач')
            return []

        people = [
            (SOLO_STUDENTS[0], 'Мария', 'Ким', 11, 'Санкт-Петербург',
             'заключительный этап ВсОШ'),
            (SOLO_STUDENTS[1], 'Тимур', 'Ахметов', 9, 'Казань',
             'призёр регионального этапа'),
        ]
        lessons = []
        for index, (login, name, surname, grade, city, goal) in enumerate(people):
            student = self._user(login, name, surname, 'student', grade=grade)
            profile = student.profile
            profile.city = city
            profile.goal = goal
            profile.save(update_fields=['city', 'goal'])

            lesson, _ = StudentGroup.objects.get_or_create(
                name=f'{name} {surname}', teacher=tutor,
                defaults={'kind': StudentGroup.Kind.INDIVIDUAL})
            lesson.kind = StudentGroup.Kind.INDIVIDUAL
            lesson.save(update_fields=['kind'])
            lesson.students.set([student])
            lessons.append(lesson)

            work, created = Assignment.objects.get_or_create(
                name=f'Занятие {index + 1}: разбор задач', author=tutor,
                group=lesson,
                defaults={'deadline': now - timezone.timedelta(days=2)})
            work.students.set([student])
            if created:
                for order, problem in enumerate(catalog[:2]):
                    AssignmentItem.objects.create(
                        assignment=work, order=order, catalog_problem=problem,
                        points=10)
            for item in work.items.all():
                sub, made = Submission.objects.get_or_create(
                    student=student, assignment=work, problem_item=item,
                    defaults={'status': 'reviewed',
                              'submitted_answer': '42',
                              'solution_text': 'Решение ученика.'})
                if made:
                    # ⚠️ Первый сдал ВОВРЕМЯ, второй ПОСЛЕ СРОКА: обе пометки
                    # столбца «Сдано» должны быть видны на демо-экране.
                    late = timezone.timedelta(days=1 if index else -1)
                    sub.submitted_at = (work.deadline_at or now) + late
                    sub.status = 'reviewed'
                    sub.save()
                    TeacherFeedback.objects.get_or_create(
                        submission=sub,
                        defaults={'score': 8 - index * 3,
                                  'comment': 'Разобрали на занятии.',
                                  'reviewed_by': tutor})
        self.stdout.write('  заведены два индивидуальных занятия '
                          '(вовремя и после срока)')
        return lessons

    def _user(self, username, first_name, last_name, role, grade=None):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': username, 'first_name': first_name,
                      'last_name': last_name})
        if created:
            user.set_password(DEMO_PASSWORD)
        # ⚠️ Имя и фамилию ОБНОВЛЯЕМ, а не только задаём при создании.
        # `defaults` срабатывает лишь один раз, поэтому правка демо-данных
        # (три Иванова подряд) не доезжала до уже заведённых логинов.
        # Трогаем ТОЛЬКО демо-логины — их список зашит константами выше.
        if (user.first_name, user.last_name) != (first_name, last_name):
            user.first_name = first_name
            user.last_name = last_name
        user.save()
        profile = getattr(user, 'profile', None)
        if profile is None:
            profile = UserProfile.objects.create(user=user, role=role)
        profile.role = role
        if grade:
            profile.grade = grade
        profile.save()
        return user

    def _catalog_problems(self):
        """Две задачи из каталога. Если банк пуст — создаём свои."""
        found = list(Problem.objects.filter(
            status=Problem.Status.PUBLISHED,
            needs_quality_review=False).order_by('pk')[:2])
        if len(found) == 2:
            return found

        topic, _ = Topic.objects.get_or_create(
            name='Спрос и предложение', defaults={'slug': 'demand-supply'})
        made = []
        for title, statement, answer in [
            ('Равновесие на рынке кофе',
             'Спрос на кофе задан функцией $Q_d = 120 - 2P$, предложение — '
             '$Q_s = 3P - 30$. Найдите равновесную цену.',
             '30'),
            ('Излишек потребителя',
             'При равновесной цене $P^* = 30$ и спросе $Q_d = 120 - 2P$ '
             'найдите излишек потребителя.',
             '900'),
        ]:
            problem, _ = Problem.objects.get_or_create(
                title=title,
                defaults={'statement': statement, 'answer': answer,
                          'status': Problem.Status.PUBLISHED,
                          'difficulty': 2})
            problem.topics.add(topic)
            made.append(problem)
        return made

    def _custom_problem(self, tutor):
        problem, created = CustomProblem.objects.get_or_create(
            owner=tutor, title='Эластичность спроса на проездные',
            defaults={
                'statement':
                    'Городской перевозчик поднял цену проездного с 800 до '
                    '1000 рублей. Число проданных проездных упало с 50 000 '
                    'до 44 000 в месяц. Посчитайте дуговую эластичность '
                    'спроса по цене и скажите, вырастет ли выручка.',
                'kind': CustomProblem.Kind.OPEN,
                # ⚠️ Ответ был «-0,54», а решение под ним даёт −0,57.
                # Пересчёт: (−6000 / 200) × (1800 / 94000) = −0,5745.
                # В витрине расхождение ответа и решения читается как
                # ошибка проверки, а не как опечатка в данных.
                'correct_answer': '-0,57',
                'answer_tolerance': '0.01',
                'solution':
                    'Дуговая эластичность считается по средним значениям: '
                    '$E = \\frac{\\Delta Q}{\\Delta P} \\cdot '
                    '\\frac{P_1+P_2}{Q_1+Q_2}$. Подставляем: '
                    '$E = \\frac{-6000}{200}\\cdot\\frac{1800}{94000} '
                    '\\approx -0{,}57$. По модулю меньше единицы — спрос '
                    'неэластичен, значит рост цены увеличит выручку.',
                'difficulty': 3,
            })
        if created:
            self.stdout.write('  создана своя задача репетитора')
        # ⚠️ Ответ ОБНОВЛЯЕМ: он был «-0,54» и не сходился с собственным
        # решением задачи (−0,57). `defaults` у get_or_create правит только
        # новые записи, поэтому исправление не доезжало до уже созданной.
        if problem.correct_answer != '-0,57':
            problem.correct_answer = '-0,57'
            problem.save(update_fields=['correct_answer'])

        # Тест каждого типа — чтобы было что показать в конструкторе.
        self._custom_test(
            tutor, 'Верно ли, что при росте цены выручка всегда растёт?',
            CustomProblem.Kind.TF,
            [('Верно', False), ('Неверно', True)])
        self._custom_test(
            tutor, 'Что произойдёт с кривой спроса при росте доходов?',
            CustomProblem.Kind.SINGLE,
            [('Сдвинется вправо', True), ('Сдвинется влево', False),
             ('Станет вертикальной', False), ('Не изменится', False)])
        self._custom_test(
            tutor, 'Какие факторы сдвигают кривую предложения?',
            CustomProblem.Kind.MULTIPLE,
            [('Технология производства', True), ('Цены на ресурсы', True),
             ('Мода на товар', False), ('Налог на производителя', True)])
        return problem

    def _costs_problem(self):
        """Задача С ПУНКТАМИ и числовым ответом на каждый.

        Ровно та, на которой споткнулась ручная проверка: «а) TC, б) ATC» —
        оба ответа числа, то есть задача полностью автопроверяема, а поле
        ответа было одно на всю задачу.
        """
        topic, _ = Topic.objects.get_or_create(
            name='Издержки фирмы', defaults={'slug': 'costs'})
        problem, created = Problem.objects.get_or_create(
            title='Демо: издержки фирмы по пунктам',
            defaults={
                'statement': 'Фирма за месяц произвела 100 единиц продукции. '
                             'Постоянные издержки равны 2000 руб., '
                             'переменные — 3000 руб.',
                'answer': '', 'status': Problem.Status.PUBLISHED,
                'difficulty': 2})
        problem.topics.add(topic)
        if created:
            ProblemPart.objects.create(
                problem=problem, label='а', order=0,
                statement='Найдите общие издержки (TC).',
                answer='5000', points='1')
            ProblemPart.objects.create(
                problem=problem, label='б', order=1,
                statement='Найдите средние издержки (ATC).',
                answer='50', points='1')
        return problem

    def _catalog_tests(self):
        """Тесты КАТАЛОЖНОГО вида — по одному на каждый подвид.

        ⚠️ Зачем отдельно от тестов репетитора. У каталожной задачи варианты
        ответа — это `ProblemPart` (подпункты), и ветка автопроверки у неё
        своя (`auto_check_submission` против `auto_check_custom`). Именно в
        каталожной ветке жил дефект «разметка пишет `answer_<pk>_<метка>`, а
        приёмник читает `answer_<pk>`», и проверить починку было не на чем:
        в демо-данных тестов с множественным выбором не было вообще.
        """
        topic, _ = Topic.objects.get_or_create(
            name='Спрос и предложение', defaults={'slug': 'demand-supply'})
        made = []
        for title, ptype, statement, answer, parts in [
            # ⚠️ НАСТОЯЩИЙ «верно/неверно»: ОДНО утверждение и два варианта.
            # Раньше здесь стояло «Отметьте верные утверждения» с тремя
            # галочками — то есть множественный выбор под именем данетки.
            # Название врало, и по этой демо-задаче человек делал выводы о
            # работающем коде. Так устроены 454 из 455 таких задач банка.
            ('Демо-тест: верно/неверно', 'тест: верно/неверно',
             'При росте ставки процента цены облигаций будут повышаться.',
             'б',
             [('а', 'Верно', 'неверно'),
              ('б', 'Неверно', 'верно')]),
            ('Демо-тест: один ответ', 'тест: один ответ',
             'Доходы покупателей выросли. Что произойдёт с кривой спроса на '
             'нормальный товар?',
             'б',
             [('а', 'Сдвинется влево', ''),
              ('б', 'Сдвинется вправо', ''),
              ('в', 'Станет вертикальной', ''),
              ('г', 'Не изменится', '')]),
            ('Демо-тест: все верные', 'тест: все верные',
             'Какие факторы сдвигают кривую предложения?',
             'а, б, г',
             [('а', 'Технология производства', 'верно'),
              ('б', 'Цены на ресурсы', 'верно'),
              ('в', 'Мода на товар', 'неверно'),
              ('г', 'Налог на производителя', 'верно')]),
        ]:
            problem, created = Problem.objects.get_or_create(
                title=title,
                defaults={'statement': statement, 'answer': answer,
                          'problem_type': ptype,
                          'status': Problem.Status.PUBLISHED,
                          'difficulty': 2})
            problem.topics.add(topic)
            # ⚠️ ДЕМО-ЗАДАЧУ ПРИВОДИМ К СПЕЦИФИКАЦИИ, а не только создаём.
            # `get_or_create` находит запись по названию и молча оставляет
            # старое содержимое — так неверный тип «верно/неверно» и жил в
            # базе после починки семечка. Ошибка в демо-данных стоит дорого:
            # по ним человек проверяет продукт и делает выводы о коде.
            expected = [(label, text, part_answer)
                        for label, text, part_answer in parts]
            actual = [(p.label, p.statement, p.answer)
                      for p in problem.parts.order_by('order', 'id')]
            if (created or problem.problem_type != ptype
                    or problem.answer != answer or actual != expected):
                problem.statement = statement
                problem.answer = answer
                problem.problem_type = ptype
                problem.save(update_fields=['statement', 'answer',
                                            'problem_type'])
                problem.parts.all().delete()
                for order, (label, text, part_answer) in enumerate(parts):
                    ProblemPart.objects.create(
                        problem=problem, label=label, statement=text,
                        answer=part_answer, order=order)
                if not created:
                    self.stdout.write(
                        '  демо-тест «%s» приведён к своему типу' % title)
            made.append(problem)
        return made

    def _custom_test(self, tutor, statement, kind, options):
        problem, created = CustomProblem.objects.get_or_create(
            owner=tutor, statement=statement,
            defaults={'kind': kind, 'difficulty': 2})
        if created:
            for order, (text, is_correct) in enumerate(options):
                CustomProblemOption.objects.create(
                    problem=problem, text=text,
                    is_correct=is_correct, order=order)
        return problem

    def _items(self, assignment, entries):
        """entries: [(catalog_problem|None, custom_problem|None, points)]

        ⚠️ Ключ идемпотентности — ЗАДАЧА, а не порядковый номер. По номеру
        было так: в существующей работе позиция №1 уже занята, новая задача
        «попадает» в неё и молча не добавляется. Именно поэтому после
        дополнения демо-данных тест «верно/неверно» не появился в
        контрольной, хотя команда отработала без единой ошибки.
        """
        items = []
        used = set(assignment.items.values_list('order', flat=True))
        for order, (catalog, custom, points) in enumerate(entries):
            item = assignment.items.filter(catalog_problem=catalog,
                                           custom_problem=custom).first()
            if item is None:
                free = order
                while free in used:
                    free += 1
                item = AssignmentItem.objects.create(
                    assignment=assignment, order=free, catalog_problem=catalog,
                    custom_problem=custom, points=points)
                used.add(free)
            items.append(item)
        # Старый M2M заполняем тоже — на нём держатся существующие экраны.
        assignment.problems.set([c for c, _, _ in entries if c is not None])
        return items

    def _homework(self, tutor, group, students, catalog, custom,
                  catalog_tests, costs, now):
        homework, _ = Assignment.objects.get_or_create(
            name='Домашка №3: спрос, предложение, эластичность',
            author=tutor,
            defaults={'group': group,
                      'deadline': now + timezone.timedelta(days=5)})
        homework.group = group
        homework.deadline = homework.deadline or now + timezone.timedelta(days=5)
        homework.save()
        homework.students.set(students)

        # ⚠️ В домашке есть тест КАЖДОГО вида: верно/неверно, один ответ,
        # множественный выбор. Без них проверять автопроверку было не на чем.
        items = self._items(homework, [
            (catalog[0], None, 2),
            (catalog[1], None, 3),
            (None, custom, 5),
            (catalog_tests[0], None, 2),
            (catalog_tests[1], None, 1),
            (catalog_tests[2], None, 3),
            (costs, None, 2),
        ])
        # У своей задачи решение открываем после дедлайна (значение по
        # умолчанию), у первой каталожной — сразу после сдачи.
        items[0].solution_visible_after = SolutionVisibility.SUBMIT
        items[0].save()

        # Сданные работы первого ученика собирает `_four_states`: там они
        # стоят все рядом и видно, что состояний ровно четыре. Здесь их
        # заводить нельзя — получилось бы два места, задающих одно и то же.
        return homework

    def _exam_window(self, tutor, group, students, catalog, catalog_tests,
                     now):
        exam, _ = Assignment.objects.get_or_create(
            name='Контрольная №1 (окно, все одновременно)', author=tutor,
            defaults={
                'group': group,
                'kind': Assignment.Kind.EXAM,
                'exam_mode': Assignment.ExamMode.WINDOW,
                'starts_at': now - timezone.timedelta(minutes=10),
                'ends_at': now + timezone.timedelta(hours=1),
            })
        # ⚠️ Окно ПЕРЕСЧИТЫВАЕТСЯ на каждом запуске. Иначе демо-контрольная
        # «живёт» ровно час после первого прогона seed, а потом навсегда
        # закрыта — и посмотреть прохождение уже нельзя.
        exam.group = group
        exam.starts_at = now - timezone.timedelta(minutes=10)
        exam.ends_at = now + timezone.timedelta(hours=1)
        exam.deadline = exam.ends_at
        exam.save()
        exam.students.set(students)
        # Те же три вида тестов и в контрольной: автопроверка там идёт
        # другим путём (через `grade_attempt`), и проверять её нужно тоже.
        self._items(exam, [
            (catalog[0], None, 5),
            (catalog_tests[0], None, 2),
            (catalog_tests[1], None, 1),
            (catalog_tests[2], None, 3),
        ])
        return exam

    def _exam_limit(self, tutor, group, students, catalog, now):
        exam, _ = Assignment.objects.get_or_create(
            name='Контрольная №2 (дедлайн + 40 минут)', author=tutor,
            defaults={
                'group': group,
                'kind': Assignment.Kind.EXAM,
                'exam_mode': Assignment.ExamMode.LIMIT,
                'deadline': now + timezone.timedelta(days=2),
                'duration_minutes': 40,
                'show_results_immediately': False,
            })
        # Срок тоже освежаем — по той же причине, что и окно у №1.
        exam.group = group
        exam.deadline = now + timezone.timedelta(days=2)
        exam.save()
        exam.students.set(students)
        self._items(exam, [(catalog[1], None, 10)])
        return exam

    def _comments(self, homework, tutor, student):
        first = homework.items.order_by('order').first()
        if first is None:
            return
        ProblemComment.objects.get_or_create(
            assignment=homework, problem_item=first, author=tutor,
            text='Обратите внимание на единицы измерения: цена в рублях, '
                 'количество в штуках.',
            defaults={'visibility': ProblemComment.Visibility.GROUP})
        ProblemComment.objects.get_or_create(
            assignment=homework, problem_item=first, author=student,
            text='А равновесие искать приравниванием функций?',
            defaults={'visibility': ProblemComment.Visibility.PRIVATE})
        ProblemComment.objects.get_or_create(
            assignment=homework, problem_item=first, author=tutor,
            text='Да, приравняйте Qd и Qs и решите уравнение.',
            defaults={'visibility': ProblemComment.Visibility.PRIVATE,
                      'recipient': student})
        # Третий вариант видимости — иначе «заметку для себя» негде увидеть
        # глазами, а видеть её надо: она не видна НИКОМУ, кроме автора.
        ProblemComment.objects.get_or_create(
            assignment=homework, problem_item=first, author=tutor,
            text='На занятии разобрать среднюю точку — путаются каждый раз.',
            defaults={'visibility': ProblemComment.Visibility.SELF})

    def _saved(self, tutor, catalog, custom):
        folder_p, _ = SavedFolder.objects.get_or_create(
            owner=tutor, kind=SavedFolder.Kind.PROBLEMS,
            name='К контрольной по спросу')
        folder_g, _ = SavedFolder.objects.get_or_create(
            owner=tutor, kind=SavedFolder.Kind.GRAPHS,
            name='Графики для урока')

        SavedProblem.objects.get_or_create(
            owner=tutor, catalog_problem=catalog[0],
            defaults={'folder': folder_p, 'note': 'Хороший вход в тему'})
        SavedProblem.objects.get_or_create(
            owner=tutor, catalog_problem=catalog[1],
            defaults={'folder': None})
        SavedProblem.objects.get_or_create(
            owner=tutor, custom_problem=custom,
            defaults={'folder': folder_p})

        # ⚠️ Имя графика подобрано под задачи демо-домашки. Прежнее
        # «Равновесие с налогом на продавца» не подходило ни одной из них,
        # и плашка «вклейте здесь» стояла под задачей про эластичность.
        graph, _ = SavedGraph.objects.get_or_create(
            owner=tutor, name='Кривая спроса и предложения',
            defaults={'folder': folder_g,
                      'scene': {'note': 'формат сцены калькулятора пока '
                                        'не определён — см. Фазу 19'}})
        return graph

    def _solutions_and_graph(self, homework, graph):
        """Решалка и график у позиций домашки — чтобы было что смотреть."""
        items = list(homework.items.order_by('order'))
        if not items:
            return

        # ⚠️ РЕШЕНИЕ ПРИВЯЗАНО К ЗАДАЧЕ, А НЕ К НОМЕРУ ПОЗИЦИИ. Раньше сюда
        # был вписан разбор равновесия ($120-2P = 3P-30$), и он ложился на
        # «первую позицию» — какой бы она ни была. В витрине это выглядело
        # как поломка кода: под задачей про эластичность стоял разбор
        # совсем другой задачи.
        first = items[0]
        recipe = SOLUTIONS_BY_TITLE.get((first.problem_title or '').strip())
        if recipe and not first.solution_override:
            first.solution_override = recipe['text']
            first.solution_steps = recipe['steps']
            first.save()

        # ⚠️ ГРАФИК ВЕШАЕТСЯ РОВНО НА ОДНУ ПОЗИЦИЮ, И КОМАНДА ЭТО СТЕРЕЖЁТ.
        # Раньше он цеплялся на «первую» и «последнюю», а состав домашки за
        # сессии менялся: каждый новый прогон делал «последней» новую
        # позицию и вешал на неё тот же график, со старых его никто не
        # снимал. Так одна плашка оказалась на четырёх задачах.
        #
        # Теперь сначала снимаем график со ВСЕХ позиций этой домашки, потом
        # вешаем на ту, где он уместен по смыслу, — задачу про равновесие
        # с налогом. Не нашлась по смыслу — вешаем на первую открытую.
        homework.items.filter(graph=graph).update(graph=None)
        target = next(
            (i for i in items
             if not i.is_test
             and any(h in (i.problem_title or '').lower()
                     for h in GRAPH_TITLE_HINTS)),
            None)
        # Не нашлось задачи, к которой график уместен, — НЕ вешаем никуда.
        # Плашка «вклейте здесь» под чужой задачей хуже её отсутствия.
        if target is not None:
            target.graph = graph
            target.save(update_fields=['graph'])

    def _finished_exam(self, tutor, group, students, now):
        """ЗАВЕРШЁННАЯ контрольная «Окно» с результатами.

        Без неё таблицу результатов репетитора не на чем посмотреть: две
        существующие контрольные либо ещё идут, либо ещё не начались.
        """
        from problems import exam_engine

        exam, created = Assignment.objects.get_or_create(
            name='Контрольная №0 (прошедшая, с результатами)', author=tutor,
            defaults={
                'group': group,
                'kind': Assignment.Kind.EXAM,
                'exam_mode': Assignment.ExamMode.WINDOW,
                'starts_at': now - timezone.timedelta(days=7, hours=1),
                'ends_at': now - timezone.timedelta(days=7),
                'deadline': now - timezone.timedelta(days=7),
                'show_results_immediately': True,
            })
        exam.group = group
        exam.save()
        exam.students.set(students)
        # Берём ТЕСТЫ репетитора, а не открытые задачи каталога: открытые
        # ждут проверки человеком, и таблица результатов вышла бы сплошным
        # «ждёт проверки» — то есть не показала бы ровно того, ради чего
        # существует (какую задачу провалили все).
        tests = list(CustomProblem.objects.filter(
            owner=tutor, kind__in=[CustomProblem.Kind.SINGLE,
                                   CustomProblem.Kind.TF]).order_by('pk')[:2])
        if len(tests) < 2:
            return
        self._items(exam, [(None, tests[0], 3), (None, tests[1], 2)])
        if not created:
            return

        items = list(exam.items.order_by('order'))
        correct = [str(next(iter(t.correct_option_ids()), '')) for t in tests]
        wrong = [str(o.pk) for t in tests
                 for o in t.options.filter(is_correct=False)[:1]]
        # Разные ответы у разных учеников — иначе таблица «ученик × задача»
        # выйдет одноцветной и ничего не покажет.
        answers = [
            (students[0], [correct[0], correct[1]]),
            (students[1], [correct[0], wrong[1]]),
            (students[2], [wrong[0], wrong[1]]),
        ]
        for student, values in answers:
            attempt = ExamAttempt.objects.create(
                assignment=exam, student=student,
                expires_at=exam.ends_at,
                submitted_at=exam.ends_at - timezone.timedelta(minutes=8))
            for item, value in zip(items, values):
                AnswerDraft.objects.create(attempt=attempt, problem_item=item,
                                           answer_draft=value,
                                           solution_draft='Разбор ученика.')
            exam_engine.grade_attempt(attempt)
        self.stdout.write('  создана завершённая контрольная с результатами')

    # -- Фаза 18: связь родителя и история за 90 дней ----------------------

    def _partly_correct_submission(self, homework, student, costs):
        """Сданная работа с ОДНИМ верным пунктом и одним неверным.

        Без неё показ «а) верно, б) неверно» негде посмотреть глазами.
        """
        from problems.assignment_rows import answer_parts, get_or_create_submission
        from problems.part_grading import apply_to_submission

        item = homework.items.filter(catalog_problem=costs).first()
        if item is None:
            return
        submission = get_or_create_submission(student, homework, item)
        if submission.status in ('submitted', 'reviewed'):
            return
        parts = answer_parts(item)
        values = {parts[0].pk: '5000', parts[1].pk: '60'}
        submission.status = 'submitted'
        submission.submitted_at = timezone.now()
        submission.solution_text = ('TC = FC + VC = 2000 + 3000 = 5000. '
                                    'ATC = TC / Q, посчитал 60.')
        apply_to_submission(submission, item, values)
        submission.save()
        self.stdout.write('  создана частично верная сдача (а — верно, '
                          'б — неверно)')

    def _submitted_tests(self, homework, student):
        """Сданные ТЕСТЫ — иначе разбор вариантов негде посмотреть глазами.

        ⚠️ Разбор вариантов («что выбрал» × «что было верно») собирается
        только ПОСЛЕ сдачи: до неё это выдача ответов. Пока в демо-данных
        ни один тест не был сдан, экран разбора нечем было проверить, и
        браузерная проверка честно показывала пустоту.

        Ответы подобраны так, чтобы на одном экране встретились ВСЕ ЧЕТЫРЕ
        исхода варианта: выбрал и верно, выбрал и неверно, не выбрал а надо
        было, не выбрал и правильно.
        """
        from problems.assignment_rows import (
            answer_input_name, get_or_create_submission, item_answer_form,
        )
        from student.views import grade_submission

        # Каким будет ответ: у «все верные» намеренно ошибочный набор
        # (взят лишний вариант и пропущен нужный), остальные — верные.
        wanted = {
            'Демо-тест: все верные': ['а', 'в'],       # верно «а, б, г»
            'Демо-тест: один ответ': ['б'],            # верно
            'Демо-тест: верно/неверно': ['б'],         # верно
        }
        made = 0
        for item in homework.items.select_related('catalog_problem'):
            problem = item.catalog_problem
            if problem is None or problem.title not in wanted:
                continue
            submission = get_or_create_submission(student, homework, item)
            if submission.status in ('submitted', 'reviewed'):
                continue
            kind, _ = item_answer_form(item)
            submission.submitted_answer = ', '.join(wanted[problem.title])
            submission.status = 'submitted'
            submission.submitted_at = timezone.now()
            submission.save()
            grade_submission(submission, item, values={})
            submission.save()
            made += 1
        if made:
            self.stdout.write('  сданы демо-тесты (%d): на экране разбора '
                              'видны все четыре исхода варианта' % made)

    def _four_states(self, homework, student, catalog, custom, costs, now):
        """ЧЕТЫРЕ СОСТОЯНИЯ ПРОВЕРКИ НА ОДНОМ ЭКРАНЕ.

        ⚠️ ЗАЧЕМ. Без этой сборки правило автонуля и янтарный вид карточки
        нельзя было увидеть глазами вовсе: счётчик «Ждёт проверки» показывал
        ноль, а неутверждённую позицию владелец получил только после того,
        как снял утверждение руками. Демо обязано показывать всё, что умеет
        продукт, иначе приёмка проверяет не продукт, а везение.

        Состояния (все — у первого ученика, в одной домашке):

        1. пусто и в ответе, и в решении → автоматический ноль, помечен
           автоматическим, в очередь ручной проверки НЕ идёт;
        2. ответ пуст, а решение написано → ЖДЁТ ЧЕЛОВЕКА (то самое
           исключение, ради которого правило и писалось);
        3. каталожная задача с НЕутверждённым эталоном → человеку же,
           карточка позиции янтарная;
        4. неверный ответ на задачу с эталоном → ноль, проверено машиной.

        Метод ПЕРЕЗАПИСЫВАЕТ решения этого ученика в этой домашке: демо —
        витрина, и её состояние задаётся здесь, а не накапливается от
        случайных прогонов браузерных сценариев. Именно так в базе завелась
        оценка «2 из 2» за неверный ответ `30`: её поставил ночной сценарий
        проверки экрана, нажав кнопку «максимум».
        """
        from problems.assignment_rows import get_or_create_submission
        from problems.models import TeacherFeedback
        from problems.part_grading import close_blank_position
        from student.views import grade_submission

        by_problem = {}
        for item in homework.items.select_related('catalog_problem',
                                                  'custom_problem'):
            key = ('c', item.catalog_problem_id) if item.catalog_problem_id \
                else ('u', item.custom_problem_id)
            by_problem[key] = item

        elasticity = by_problem.get(('c', catalog[0].pk))
        firm = by_problem.get(('c', catalog[1].pk))
        own = by_problem.get(('u', custom.pk))
        by_parts = by_problem.get(('c', costs.pk))
        if not all([elasticity, firm, own, by_parts]):
            return

        # Чистим прошлое состояние ЭТОГО ученика в ЭТОЙ домашке. Оценки
        # других учеников и других работ не трогаем.
        wiped = Submission.objects.filter(assignment=homework, student=student,
                                          problem_item__in=[elasticity, firm,
                                                            own, by_parts])
        TeacherFeedback.objects.filter(submission__in=wiped).delete()
        wiped.update(status='not_started', submitted_answer='',
                     solution_text='', submitted_at=None)

        # Состояние 3: каталожная задача, эталон НЕ утверждён. Ответ неверный
        # (`30` — это ответ на задачу про равновесие, а не про эластичность),
        # но судить об этом машина не имеет права: в поле «ответ» каталога
        # лежит фраза целиком, а не ответ.
        for item in (elasticity, firm):
            item.answer_override = None
            item.save(update_fields=['answer_override'])
        sub = get_or_create_submission(student, homework, elasticity)
        sub.submitted_answer = '30'
        sub.solution_text = 'Приравнял спрос и предложение.'
        sub.status = 'submitted'
        sub.submitted_at = now
        sub.save()

        # Состояние 2: ответа нет, а решение написано — ученик рассуждал,
        # значит человеку есть что читать.
        sub = get_or_create_submission(student, homework, firm)
        sub.submitted_answer = ''
        sub.solution_text = ('Постоянные не зависят от выпуска, переменные '
                             'растут вместе с ним. Дальше запутался в '
                             'единицах и не досчитал.')
        sub.status = 'submitted'
        sub.submitted_at = now
        sub.save()

        # Состояние 4: у своей задачи репетитора эталон писал он сам —
        # машина проверяет сразу и ставит ноль за неверный ответ.
        sub = get_or_create_submission(student, homework, own)
        sub.submitted_answer = '-0,3'
        sub.solution_text = 'Поделил проценты, кажется, не в ту сторону.'
        sub.status = 'submitted'
        sub.submitted_at = now
        sub.save()
        grade_submission(sub, own, values={None: sub.submitted_answer})

        # Состояние 1: не написано НИЧЕГО. Эталон по пунктам утверждаем —
        # иначе нечем показать, что утверждённая позиция считается сама.
        by_parts.answer_override = {'': ''}
        parts = list(by_parts.problem.parts.order_by('order')) \
            if by_parts.problem else []
        if len(parts) >= 2:
            by_parts.answer_override = {str(parts[0].pk): '5000',
                                        str(parts[1].pk): '50'}
            by_parts.save(update_fields=['answer_override'])
        sub = get_or_create_submission(student, homework, by_parts)
        close_blank_position(sub, by_parts)

        self.stdout.write('  собраны четыре состояния проверки: '
                          'автоноль, решение-без-ответа, неутверждённый '
                          'эталон, неверный ответ')

    def _work_difficulty(self, tutor, students):
        """Оценки субъективной сложности работ (сессия 7, фаза 9).

        ⚠️ Без них два места показа стоят пустыми: карточка «Средняя
        сложность работ» у ученика и правая часть проверенной работы в
        списке заданий. На презентации пустое место читается как
        недоделанная функция.

        Значения правдоподобные (3–8) и РАЗНЫЕ: одинаковые пятёрки везде
        выглядят как заглушка, которой они и были бы.
        """
        from problems.models_platform import WorkDifficulty

        works = list(Assignment.objects.filter(author=tutor).order_by('pk'))
        if not works or not students:
            return
        # Одна оценка на пару (работа, ученик); ученик отвечает не всегда —
        # часть работ намеренно остаётся без оценки, чтобы на экране было
        # видно и состояние «нет оценок».
        pattern = [4, 7, 3, 8, 5, 6, None, 5, 4, None, 7, 3]
        created = 0
        index = 0
        for work in works:
            for student in students:
                value = pattern[index % len(pattern)]
                index += 1
                if value is None:
                    continue
                # ⚠️ Оценку ставит только тот, кто РАБОТУ СДАВАЛ. Иначе на
                # экране выходит «никто не сдал · сложность 4,7 из 10» —
                # оценка работы, которую никто не открывал.
                if not Submission.objects.filter(
                        assignment=work, student=student,
                        status__in=('submitted', 'reviewed')).exists():
                    continue
                _, made = WorkDifficulty.objects.get_or_create(
                    assignment=work, student=student,
                    defaults={'value': value})
                created += int(made)
        if created:
            self.stdout.write('  проставлены оценки сложности работ (%d)'
                              % created)

    def _parent_links(self, tutor, students):
        """Родитель связан с ДВУМЯ учениками — чтобы кабинет родителя было
        на чём проверить (список детей, а не одна карточка)."""
        parent = User.objects.get(username=PARENT)
        for student in students[:2]:
            ParentLink.objects.get_or_create(
                parent=parent, student=student,
                defaults={'created_by': tutor})

    # Три ученика с РАЗНЫМ поведением. Ради этого история и нужна: на
    # одинаковых данных графики выглядят одинаково, и понять, показывают ли
    # они что-нибудь, нельзя.
    #   1. занимается регулярно, доля верных высокая;
    #   2. рывками — неделя работы, неделя тишины;
    #   3. бросил месяц назад.
    HISTORY_PROFILES = [
        {'name': 'регулярный', 'active': lambda d: d % 7 not in (5, 6),
         'accuracy': 0.85, 'per_day': (3, 6), 'stop_days_ago': 0},
        {'name': 'рывками', 'active': lambda d: (d // 7) % 2 == 0,
         'accuracy': 0.6, 'per_day': (2, 9), 'stop_days_ago': 0},
        {'name': 'бросил', 'active': lambda d: d % 3 == 0,
         'accuracy': 0.5, 'per_day': (1, 4), 'stop_days_ago': 30},
    ]

    def _history(self, students, now, seed_offset=0):
        """История учебных событий за 90 дней.

        ⚠️ Пишем СОБЫТИЯ, а не сразу свёртки: события — первоисточник, и
        демо-данные обязаны проходить тот же путь, что боевые. Иначе
        `recalculate_gamification` на демо-базе выдал бы другие числа, и
        мы бы гонялись за несуществующим расхождением.

        Случайность зафиксирована seed'ом: демо-данные обязаны быть
        одинаковыми при каждом прогоне, иначе идемпотентность мнимая.
        """
        import random

        from problems.models import LearningEvent

        problems = list(Problem.objects.filter(
            status=Problem.Status.PUBLISHED, needs_quality_review=False,
            topics__isnull=False).distinct()[:60])
        if len(problems) < 5:
            self.stdout.write('  история пропущена: в банке мало задач '
                              'с темами')
            return

        for index, student in enumerate(students[:3]):
            if student is None:
                continue
            if LearningEvent.objects.filter(
                    user=student, payload__demo_history=True).exists():
                continue        # идемпотентность: история уже насыпана

            profile = self.HISTORY_PROFILES[index]
            rng = random.Random(1000 + index + seed_offset)
            events = []
            # ⚠️ Задуманные даты держим ОТДЕЛЬНЫМ списком. `created_at` —
            # auto_now_add, и bulk_create перетирает его прямо в переданных
            # объектах: если потом читать дату из них же, вычитаешь то, что
            # сам и хотел исправить (наступали 2026-08-04 — вся история
            # схлопнулась в один день).
            stamps = []
            for days_ago in range(90, profile['stop_days_ago'], -1):
                if not profile['active'](days_ago):
                    continue
                moment = now - timezone.timedelta(days=days_ago)
                # Вечерние занятия — так у графика «по часам» появляется
                # форма, а не ровная полка.
                moment = moment.replace(hour=rng.choice([16, 17, 18, 19, 20]),
                                        minute=rng.randint(0, 59))
                count = rng.randint(*profile['per_day'])
                for number in range(count):
                    problem = rng.choice(problems)
                    correct = rng.random() < profile['accuracy']
                    topic = problem.topics.first()
                    events.append(LearningEvent(
                        user=student, source=rng.choice(
                            ['catalog', 'homework', 'homework', 'exam']),
                        event_type='solved' if correct else 'failed',
                        catalog_problem=problem, topic=topic,
                        difficulty=problem.difficulty or rng.randint(1, 4),
                        time_spent_seconds=rng.randint(60, 900),
                        payload={'demo_history': True}))
                    stamps.append(moment + timezone.timedelta(
                        minutes=number * 7))

            created = LearningEvent.objects.bulk_create(events)
            for event, stamp in zip(created, stamps):
                LearningEvent.objects.filter(pk=event.pk).update(
                    created_at=stamp)
            self.stdout.write(
                f'  история «{profile["name"]}» для {student.username}: '
                f'{len(events)} событий')

        # Партии игры — чтобы блок Econ Rush не был пустым.
        for index, student in enumerate(students[:2]):
            if LearningEvent.objects.filter(user=student,
                                            source='game').exists():
                continue
            rng = random.Random(2000 + index)
            for _ in range(rng.randint(20, 40)):
                LearningEvent.objects.create(
                    user=student, source='game',
                    event_type='solved' if rng.random() < 0.7 else 'failed',
                    payload={'mode': rng.choice(['bullet', 'blitz', 'rapid',
                                                 'classic'])})
