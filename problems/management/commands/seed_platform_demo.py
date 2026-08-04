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
    Problem,
    StudentGroup,
    Submission,
    Topic,
    User,
)
from problems.models_platform import (
    AssignmentItem,
    CustomProblem,
    CustomProblemOption,
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
PARENT = 'parent@test.local'


class Command(BaseCommand):
    help = 'Создаёт демо-данные платформы (идемпотентно).'

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()

        tutor = self._user(TUTOR, 'Марина', 'Петрова', 'tutor')
        students = [
            self._user(login, name, 'Иванов', 'student', grade=grade)
            for login, name, grade in zip(
                STUDENTS, ['Пётр', 'Анна', 'Сергей'], [10, 11, 9])
        ]
        self._user(PARENT, 'Ольга', 'Иванова', 'parent')

        group, _ = StudentGroup.objects.get_or_create(
            name='Экономика 10–11, вторник', teacher=tutor)
        group.students.set(students)

        catalog = self._catalog_problems()
        custom = self._custom_problem(tutor)

        homework = self._homework(tutor, group, students, catalog, custom, now)
        self._exam_window(tutor, group, students, catalog, now)
        self._exam_limit(tutor, group, students, catalog, now)
        self._comments(homework, tutor, students[0])
        self._saved(tutor, catalog, custom)

        self.stdout.write(self.style.SUCCESS('\nДемо-данные готовы.'))
        self.stdout.write('Вход (пароль у всех одинаковый):')
        self.stdout.write(f'  репетитор: {TUTOR} / {DEMO_PASSWORD}')
        for login in STUDENTS:
            self.stdout.write(f'  ученик:    {login} / {DEMO_PASSWORD}')
        self.stdout.write(f'  родитель:  {PARENT} / {DEMO_PASSWORD}')

    # -- кирпичики ---------------------------------------------------------

    def _user(self, username, first_name, last_name, role, grade=None):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': username, 'first_name': first_name,
                      'last_name': last_name})
        if created:
            user.set_password(DEMO_PASSWORD)
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
                'correct_answer': '-0,54',
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
        """entries: [(catalog_problem|None, custom_problem|None, points)]"""
        items = []
        for order, (catalog, custom, points) in enumerate(entries):
            item, _ = AssignmentItem.objects.get_or_create(
                assignment=assignment, order=order,
                defaults={'catalog_problem': catalog,
                          'custom_problem': custom, 'points': points})
            items.append(item)
        # Старый M2M заполняем тоже — на нём держатся существующие экраны.
        assignment.problems.set([c for c, _, _ in entries if c is not None])
        return items

    def _homework(self, tutor, group, students, catalog, custom, now):
        homework, _ = Assignment.objects.get_or_create(
            name='Домашка №3: спрос, предложение, эластичность',
            author=tutor,
            defaults={'group': group,
                      'deadline': now + timezone.timedelta(days=5)})
        homework.group = group
        homework.deadline = homework.deadline or now + timezone.timedelta(days=5)
        homework.save()
        homework.students.set(students)

        items = self._items(homework, [
            (catalog[0], None, 2),
            (catalog[1], None, 3),
            (None, custom, 5),
        ])
        # У своей задачи решение открываем после дедлайна (значение по
        # умолчанию), у первой каталожной — сразу после сдачи.
        items[0].solution_visible_after = SolutionVisibility.SUBMIT
        items[0].save()

        # Один ученик уже сдал первую задачу — чтобы дашборд репетитора не
        # был пустым и было что проверять.
        Submission.objects.get_or_create(
            student=students[0], assignment=homework,
            problem=catalog[0],
            defaults={'problem_item': items[0],
                      'submitted_answer': '30',
                      'solution_text': 'Приравнял спрос и предложение.',
                      'status': 'submitted', 'submitted_at': now})
        return homework

    def _exam_window(self, tutor, group, students, catalog, now):
        exam, _ = Assignment.objects.get_or_create(
            name='Контрольная №1 (окно, все одновременно)', author=tutor,
            defaults={
                'group': group,
                'kind': Assignment.Kind.EXAM,
                'exam_mode': Assignment.ExamMode.WINDOW,
                'starts_at': now - timezone.timedelta(minutes=10),
                'ends_at': now + timezone.timedelta(hours=1),
            })
        exam.group = group
        exam.save()
        exam.students.set(students)
        self._items(exam, [(catalog[0], None, 5), (catalog[1], None, 5)])
        return exam

    def _exam_limit(self, tutor, group, students, catalog, now):
        exam, _ = Assignment.objects.get_or_create(
            name='Контрольная №2 (дедлайн + 40 минут)', author=tutor,
            defaults={
                'group': group,
                'kind': Assignment.Kind.EXAM,
                'exam_mode': Assignment.ExamMode.LIMIT,
                'due_at': now + timezone.timedelta(days=2),
                'duration_minutes': 40,
                'show_results_immediately': False,
            })
        exam.group = group
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

        SavedGraph.objects.get_or_create(
            owner=tutor, name='Равновесие с налогом на продавца',
            defaults={'folder': folder_g,
                      'scene': {'note': 'формат сцены калькулятора пока '
                                        'не определён — см. Фазу 19'}})
