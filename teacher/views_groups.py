"""
Вкладка «Группы» — рабочая поверхность репетитора.

ПРИНЦИП: вся работа с группой происходит ВНУТРИ этой вкладки. Единственное
исключение — дашборд входящих (`/teacher/`): он не рабочая поверхность,
а навигация. Проверить работу с дашборда нельзя, можно только перейти туда,
где её проверяют.
"""
import json
import logging
from datetime import timedelta

from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from problems import timefmt

from .access import group_assignment_or_404, own_group_or_404, tutor_required

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Общие подсчёты
# ---------------------------------------------------------------------------

def _pending_count(assignments):
    """Сколько СДАННЫХ РАБОТ ждёт проверки среди переданных заданий.

    ⚠️ Делегирует `stats.works_waiting` — единственной точке счёта. Раньше
    считал ЗАДАЧИ (`Submission.count()`), и карточка группы писала «6 ждёт
    проверки» там, где вкладка «Задания» писала «3»: считались разные вещи.
    """
    from problems.stats import works_waiting
    return works_waiting(assignments)


def assignment_stats(assignment):
    """Сводка по заданию: сдано / из скольких / ждёт проверки."""
    from problems.models import Submission
    from problems.timefmt import deadline_pair

    from problems.stats import works_waiting

    students = assignment.students.count()
    submitted_students = (Submission.objects
                          .filter(assignment=assignment,
                                  status__in=('submitted', 'reviewed'))
                          .values('student').distinct().count())
    # ⚠️ РАБОТЫ, А НЕ ЗАДАЧИ. Кнопка «Проверить N» показывает, сколько
    # сданных работ этого задания ждут репетитора; раньше здесь стояло число
    # непроверенных ЗАДАЧ, и оно не сходилось со счётчиком над списком.
    # Разбивка по задачам осталась на своём месте — в сводке решений.
    pending = works_waiting([assignment])
    deadline = assignment.deadline_at
    human, exact = deadline_pair(deadline)

    # ⚠️ СРЕДНИЙ БАЛЛ БОЛЬШЕ НЕ ПОКАЗЫВАЕТСЯ (поправка 4 владельца к
    # сессии 7). Он вводил в заблуждение: у разных работ разный максимум, и
    # сырое «средний балл 1,33» несопоставимо с «1,4» соседней работы. На
    # его месте теперь средняя субъективная сложность — по той же причине,
    # по которой в истории работ баллы заменены процентами.
    # Значение остаётся в словаре: по нему считается сортировка и его ждут
    # существующие проверки; из ИНТЕРФЕЙСА оно убрано.
    from django.db.models import Avg

    from problems import models_platform

    average = (Submission.objects
               .filter(assignment=assignment, feedback__score__isnull=False)
               .aggregate(value=Avg('feedback__score'))['value'])
    difficulty = models_platform.difficulty_for_work(assignment)

    # ⚠️ СРЕДНЯЯ ОЦЕНКА — В ПРОЦЕНТАХ, А НЕ В СЫРЫХ БАЛЛАХ. У разных работ
    # разный максимум, и «1,33» против «1,4» соседней работы не сравнимы
    # ничем. Тот же довод, по которому в истории работ баллы заменены
    # процентами.
    percent = _assignment_percent(assignment)
    return {
        'assignment': assignment,
        'students': students,
        'submitted': submitted_students,
        'pending': pending,
        'deadline': deadline,
        'deadline_human': human,
        'deadline_exact': exact,
        # ⚠️ «Проверено» имеет смысл ТОЛЬКО когда было что проверять.
        # Раньше бейдж «проверено» стоял у заданий, где сдали 0 из 3, — это
        # не заслуга, а пустота, и читалось как «всё в порядке».
        'avg_score': round(float(average), 2) if average is not None else None,
        # Средняя субъективная сложность работы: спрашиваем у учеников
        # (`WorkDifficulty`), вычислить её из баллов нельзя. Нет ответов —
        # пишем словами, а не нулём: ноль по шкале 1–10 означал бы оценку.
        'difficulty': difficulty,
        'difficulty_label': ('сложность %s из 10' % str(difficulty).replace('.', ',')
                             if difficulty is not None else 'нет оценок'),
        'percent': percent,
        'nobody_submitted': submitted_students == 0,
        'all_checked': submitted_students > 0 and pending == 0,
        'is_exam': assignment.is_exam,
    }


def _assignment_percent(assignment):
    """Средняя оценка за работу В ПРОЦЕНТАХ по всем сдавшим ученикам.

    Считаем «набрано ÷ максимум» отдельно по каждому ученику и усредняем:
    так работа, которую сдали двое, не перевешивается тем, у кого больше
    задач. Никто не оценён — None, и экран пишет «никто не сдал».
    """
    from decimal import Decimal

    from problems.assignment_rows import item_max_score
    from problems.models import Submission

    by_student = {}
    for sub in (Submission.objects
                .filter(assignment=assignment, feedback__score__isnull=False)
                .select_related('feedback', 'problem_item')):
        if sub.problem_item_id is None:
            continue
        got, could = by_student.setdefault(sub.student_id,
                                           [Decimal('0'), Decimal('0')])
        by_student[sub.student_id][0] = got + Decimal(str(sub.feedback.score))
        by_student[sub.student_id][1] = could + item_max_score(sub.problem_item)

    shares = [float(got / could) for got, could in by_student.values() if could]
    if not shares:
        return None
    return int(round(sum(shares) * 100.0 / len(shares)))


# ---------------------------------------------------------------------------
# Фаза 9 — список групп
# ---------------------------------------------------------------------------

@tutor_required
def groups_list(request):
    from problems.models import Assignment, StudentGroup, Submission

    groups = (StudentGroup.objects
              .filter(teacher=request.user)
              .prefetch_related('students')
              .order_by('name'))

    now = timezone.now()
    cards = []
    for group in groups:
        assignments = list(Assignment.objects.filter(group=group))
        deadlines = [a.deadline_at for a in assignments
                     if a.deadline_at and a.deadline_at >= now]
        last_submission = (Submission.objects
                           .filter(assignment__group=group)
                           .order_by('-submitted_at')
                           .values_list('submitted_at', flat=True).first())
        cards.append({
            'group': group,
            'students': group.students.count(),
            'pending': _pending_count(assignments),
            'next_deadline': min(deadlines) if deadlines else None,
            'last_activity': last_submission or group.created_at,
            'assignments': len(assignments),
        })

    return render(request, 'teacher/groups/list.html', {'cards': cards})


@tutor_required
def group_create(request):
    """Создание занятия: группы или индивидуального (сессия 9, фаза 9).

    Форм две, вьюха одна: различаются они полем «кто учится» — у группы это
    название, у индивидуального занятия ученик. Всё остальное (владелец,
    описание, права) общее, и разводить это по двум вьюхам значило бы
    поддерживать два места создания.

    ⚠️ У индивидуального занятия название по умолчанию — ИМЯ УЧЕНИКА. Поле
    названия остаётся, но обязательным не становится: заставлять
    придумывать имя занятию с одним человеком незачем.
    """
    from problems.models import StudentGroup, User

    kind = request.GET.get('kind') or request.POST.get('kind') or 'group'
    if kind not in dict(StudentGroup.Kind.choices):
        kind = 'group'
    individual = kind == StudentGroup.Kind.INDIVIDUAL

    # Кого можно взять на индивидуальное занятие: ученики этого репетитора
    # плюс те, кто пока ни в одном его занятии не состоит.
    students = User.objects.filter(role='student').order_by(
        'last_name', 'first_name', 'username')

    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        student = None
        if individual:
            student = students.filter(pk=request.POST.get('student')).first()
            if student is None:
                messages.error(request, 'Выберите ученика.')
                return render(request, 'teacher/groups/create.html',
                              {'kind': kind, 'individual': individual,
                               'students': students})
            name = name or (student.get_full_name() or student.username)
        if not name:
            messages.error(request, 'Название группы не может быть пустым.')
        else:
            group = StudentGroup.objects.create(
                name=name, teacher=request.user, kind=kind,
                description=(request.POST.get('description') or '').strip())
            if student is not None:
                group.students.add(student)
            messages.success(
                request,
                'Ученик «%s» добавлен.' % group.name if individual
                else 'Группа «%s» создана.' % group.name)
            return redirect('teacher:group_detail', pk=group.pk)

    return render(request, 'teacher/groups/create.html',
                  {'kind': kind, 'individual': individual,
                   'students': students})


# ---------------------------------------------------------------------------
# Фаза 10 — страница группы (три вкладки)
# ---------------------------------------------------------------------------

# Вкладок ТРИ. «Ученики» удалена: она была обеднённой копией таблицы со
# статистики (те же люди, но без «решено» и «доли верных»), да ещё и с
# другим числом в колонке активности — расхождение выглядело как баг.
GROUP_TABS = ('overview', 'assignments', 'materials')


@tutor_required
def group_detail(request, pk):
    from problems.models import Assignment, Submission, TeacherFeedback
    from problems import models_platform
    from problems import stats as stats_module

    group = own_group_or_404(request.user, pk)
    tab = request.GET.get('tab', 'overview')
    # ⚠️ Старый адрес `?tab=students` НЕ ломаем: он может быть в закладках и
    # в переписке. Уводим редиректом на обзор, а не показываем пустоту.
    if tab == 'students':
        return redirect(reverse('teacher:group_detail', args=[group.pk])
                        + '?tab=overview')
    if tab not in GROUP_TABS:
        tab = 'overview'

    # ⚠️ СОРТИРОВКА ПО ДЕДЛАЙНУ, БЛИЖАЙШИЕ ПЕРВЫМИ. Раньше стоял порядок по
    # дате создания, и список выглядел случайным: 08.08, 07.08, 05.08, 28.07,
    # 09.08 — ни по дате, ни по типу.
    #
    # Задания БЕЗ срока уходят в конец: у них нет места на шкале времени, и
    # ставить их первыми значило бы прятать за ними то, что горит.
    assignments = sorted(
        Assignment.objects.filter(group=group).prefetch_related('students'),
        key=lambda a: (a.deadline_at is None, a.deadline_at or a.created_at))

    rows = [assignment_stats(a) for a in assignments]
    context = {
        'group': group,
        'tab': tab,
        'assignment_rows': rows,
        'assignment_groups': group_assignments_by_state(
            rows, show_all_done=request.GET.get('all_done') == '1'),
        # Счётчик над списком и кружок у вкладки «Задания». ОДНО число на
        # оба места и на карточку группы — `stats.works_waiting`.
        # ⚠️ Раньше здесь стояло `sum(1 for row in rows if row['pending'])`,
        # то есть считались ЗАДАНИЯ, а кнопки внутри считали задачи. Сумма
        # по кнопкам не сходилась со счётчиком — это и заметил владелец.
        'waiting_total': stats_module.works_waiting(assignments),
    }

    # Обзор = прежняя статистика группы. Считаем только когда её смотрят:
    # тепловая матрица — не бесплатный запрос, а на вкладке «Задания» она
    # не нужна.
    if tab == 'overview':
        period = request.GET.get('period') or 'month'
        if period not in dict(stats_module.PERIODS):
            period = 'month'
        # ⚠️ ВЕТВЛЕНИЕ — В ШАБЛОНАХ, А НЕ КОПИЕЙ ВЬЮХИ (фаза 9). Логика у
        # группы и у индивидуального занятия одна, различается НАБОР
        # БЛОКОВ: у одного на один сравнивать не с кем, поэтому теплокарта
        # «ученики × темы», таблица учеников и строка «по группе» теряют
        # смысл. Вместо них — тот же блок «Прогресс по темам», что на
        # карточке ученика, и четыре карточки-показателя.
        solo = group.single_student
        if group.is_individual and solo is not None:
            context.update({
                'solo': solo,
                'solo_profile': getattr(solo, 'profile', None),
                'progress': stats_module.topic_progress_pairs(solo,
                                                              period=period),
                'solo_open': stats_module.accuracy_pair(
                    solo, tutor=request.user, kind='open', period=period),
                'solo_test': stats_module.accuracy_pair(
                    solo, tutor=request.user, kind='test', period=period),
                'solo_minutes': stats_module.minutes_on_site(solo, period),
                'solo_difficulty': models_platform.difficulty_for_student(solo),
            })

        context.update({
            'period': period,
            'periods': stats_module.PERIODS,
            'rows': stats_module.group_table(group, period),
            # ⚠️ ТЕПЛОКАРТА СЛУШАЕТСЯ ПЕРЕКЛЮЧАТЕЛЯ ПЕРИОДА (сессия 9,
            # фаза 6.1). Раньше здесь был прибит `'all'`, а над блоком стоял
            # переключатель День / Неделя / Месяц / Всё время: владелец
            # выбирал «Месяц», числа не менялись, и это выглядело поломкой.
            # Пометка «за всё время» у заголовка убрана — она стала враньём.
            'matrix': stats_module.group_topic_matrix(group, period),
            'attention': stats_module.needs_attention(group),
            # История работ группы (п. 11.5) — та же сборка и та же
            # разметка, что у истории в карточке ученика.
            'group_works': stats_module.group_work_history(group),
        })

    return render(request, 'teacher/groups/detail.html', context)



# ---------------------------------------------------------------------------
# Фаза 11 — задания группируются ПО СОСТОЯНИЮ, а не лежат плоским списком
# ---------------------------------------------------------------------------
# ⚠️ ЗАЧЕМ. Плоский список из семи одинаковых строк не отвечает на вопрос,
# ради которого репетитор сюда зашёл: «что мне сейчас делать». Домашки и
# контрольные шли вперемешку, прошедшие и будущие — тоже. Дело не в форме
# списка: группировка по состоянию превращает его в очередь работы.

ASSIGNMENT_STATES = (
    ('needs_you', 'Требуют проверки'),
    ('running', 'Идут сейчас'),
    ('done', 'Проверены'),
)


def assignment_state(row, now=None):
    """Одно из трёх состояний задания.

    Порядок проверок важен: «требуют вас» ГЛАВНЕЕ срока. Работа с прошедшим
    сроком, где лежит непроверенное, — это всё ещё работа для репетитора, а
    не архив.
    """
    if row['pending']:
        return 'needs_you'
    deadline = row['deadline']
    now = now or timezone.now()
    if deadline is None or deadline >= now:
        return 'running'
    return 'done'


# Сколько проверенных работ показываем сразу. Остальные — по кнопке
# «Посмотреть все»: закрытая работа внимания не требует, и лента из
# двадцати таких прячет за собой то, что горит.
DONE_SHOWN = 5

# Цвет полосы состояния. Берутся классы набора деталей (`.k-mark--*`), те же
# пять состояний, что на разборе работы: два набора цветов для одного и того
# же разъехались бы на первой же правке.
STATE_MARKS = {'needs_you': 'pending', 'running': 'empty', 'done': 'correct'}


def group_assignments_by_state(rows, now=None, show_all_done=False):
    """Список групп заданий для экрана: заголовок, полоса, что показать.

    Внутри группы — по сроку, ближайшие первыми (порядок уже задан
    сортировкой в `group_detail`, здесь он только сохраняется).
    Пустые группы не возвращаются.
    """
    now = now or timezone.now()
    buckets = {key: [] for key, _ in ASSIGNMENT_STATES}
    for row in rows:
        buckets[assignment_state(row, now)].append(row)

    result = []
    for key, title in ASSIGNMENT_STATES:
        items = buckets[key]
        if not items:
            continue
        shown = items
        hidden = 0
        if key == 'done' and not show_all_done and len(items) > DONE_SHOWN:
            shown = items[:DONE_SHOWN]
            hidden = len(items) - DONE_SHOWN
        caption = ('последние %d из %d' % (len(shown), len(items))
                   if hidden else str(len(items)))
        result.append({
            'key': key,
            'title': title,
            'items': items,
            'shown': shown,
            'hidden_count': hidden,
            'caption': caption,
            'mark': STATE_MARKS[key],
        })
    return result

# ---------------------------------------------------------------------------
# Фаза 11 — просмотр задания ДО решений
# ---------------------------------------------------------------------------

def _item_title(item):
    """Заголовок задачи для экрана. Пусто — берём начало условия.

    В банке у части задач заголовка нет вовсе, а у части он совпадает с
    условием. Показывать «Задача #40131» бессмысленно, поэтому подставляем
    первые слова условия — обрезкой ПО ГРАНИЦЕ СЛОВА, чтобы не рвать числа
    («переменные — 300…» вместо 3000).
    """
    from problems.text_clean import preview_title

    problem = item.problem
    if problem is None:
        return '(задача удалена)'
    return preview_title(problem, limit=70)


def _source_label(item):
    """Откуда задача: «своя» / «тест» / «каталог». Одно слово, мелким."""
    if item.is_custom:
        return 'своя'
    if item.is_test:
        return 'тест'
    return 'каталог'


def _answer_rows(item):
    """Строки «пункт → что предлагает каталог → что утверждено».

    Тесты и свои задачи сюда не идут: у теста верный вариант задан
    разметкой, у своей задачи эталон писал сам репетитор.
    """
    from problems.assignment_rows import (
        answer_parts, catalog_answer_for, part_max_score,
    )

    if item.is_custom or item.is_test or item.catalog_problem_id is None:
        return []

    parts = answer_parts(item)
    rows = []
    for part in parts:
        catalog = catalog_answer_for(item, part)
        approved = item.approved_answer(part)
        rows.append({
            'part': part,
            'key': '' if part is None else str(part.pk),
            'label': (part.label if part is not None else ''),
            'statement': (part.statement if part is not None
                          else item.statement),
            'from_catalog': catalog,
            'approved': approved,
            # ⚠️ Подпись «в каталоге: …» показывается ТОЛЬКО когда каталог
            # говорит НЕ ТО, что стоит в поле. Совпадает — это третье место,
            # где написано одно и то же (поле, подпись и свёрнутый заголовок),
            # и глазу приходится сравнивать три одинаковые строки, чтобы
            # понять, что сравнивать нечего.
            'catalog_differs': bool(catalog) and bool(approved) \
            and catalog.strip() != approved.strip(),
            'max_score': part_max_score(item, part, len(parts)),
        })
    return rows


@tutor_required
def group_assignment_detail(request, group_id, assignment_id):
    """Задание целиком глазами репетитора — ещё до того, как кто-то решал.

    Ради этого экрана и заводилась позиция задачи в домашке: здесь рядом
    стоят задачи каталога и свои, у каждой своё условие, свой правильный
    ответ, своя решалка и своё обсуждение.
    """
    from problems.models import ProblemComment
    from problems.models_platform import visibility_choices_for

    group = own_group_or_404(request.user, group_id)
    assignment = group_assignment_or_404(group, assignment_id)

    from problems.assignment_rows import ordered_items, section_marks

    # Порядок и деление на части — та же функция, что у ученика и у листка.
    items = ordered_items(assignment, list(
        assignment.items
        .select_related('catalog_problem', 'custom_problem')
        .prefetch_related('custom_problem__options',
                          'catalog_problem__parts')
        .order_by('order', 'id')))
    marks = section_marks(items)

    comments = (ProblemComment.objects.visible_for(request.user)
                .filter(assignment=assignment)
                .select_related('author', 'assignment', 'assignment__group'))
    by_item = {}
    for comment in comments:
        # Пометка видимости считается ЗДЕСЬ, один раз на комментарий: шаблон
        # не должен решать, кому что видно, — это правило доступа.
        comment.note = comment.note_for(request.user)
        by_item.setdefault(comment.problem_item_id, []).append(comment)

    rows = []
    for index, item in enumerate(items):
        options = []
        if item.is_custom and item.custom_problem.is_test:
            options = list(item.custom_problem.options.all())
        rows.append({
            'item': item,
            'number': index + 1,
            'section_title': marks.get(index, ''),
            # ⚠️ Заголовок задачи на экране РАНЬШЕ НЕ ПОКАЗЫВАЛСЯ, хотя в
            # печатном листке был. Из-за этого страница из семи позиций
            # читалась сплошной простынёй: зацепиться глазом не за что.
            'title': _item_title(item),
            'source_label': _source_label(item),
            'options': options,
            'parts': list(item.catalog_problem.parts.all())
            if item.catalog_problem_id else [],
            'comments': by_item.get(item.pk, []),
            # Что именно уйдёт в автопроверку — по строке на пункт.
            'answer_rows': _answer_rows(item),
            'answers_approved': item.answers_approved,
            'needs_approval': not item.answers_approved,
        })

    from problems.models import SolutionVisibility

    return render(request, 'teacher/groups/assignment_detail.html', {
        'group': group,
        'assignment': assignment,
        'rows': rows,
        # Баллы правятся ДО первой сдачи. После — цифра остаётся крупной и
        # видной, но не редактируется: оценки уже выставлены по этой шкале.
        'points_locked': assignment.points_locked,
        # Видимость комментария — от лица того, кто пишет. «Видно только
        # этому ученику» требует ученика, поэтому список тут же.
        'visibility_choices': visibility_choices_for(
            'tutor', individual=group.is_individual),
        'recipients': list(assignment.students.order_by('last_name',
                                                        'first_name')),
        'stats': assignment_stats(assignment),
        'solution_visibility': SolutionVisibility.choices,
    })


# ---------------------------------------------------------------------------
# Фаза 12 — комментарии: JSON-эндпоинт (без перезагрузки страницы)
# ---------------------------------------------------------------------------

@require_POST
def api_comment_create(request):
    """Добавить комментарий к позиции задачи.

    Доступен и репетитору, и ученику — правила видимости разные, а точка
    входа одна: два почти одинаковых эндпоинта разъехались бы.
    """
    from problems.models import AssignmentItem, ProblemComment
    from problems.models_platform import visibility_choices_for

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Нужен вход'}, status=403)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Неверный формат'}, status=400)

    text = (body.get('text') or '').strip()
    if not text:
        return JsonResponse({'error': 'Пустой комментарий'}, status=400)

    item = get_object_or_404(
        AssignmentItem.objects.select_related('assignment'),
        pk=body.get('item_id'))
    assignment = item.assignment

    tutor = item.is_tutor_for(request.user)
    if not tutor and not assignment.students.filter(
            pk=request.user.pk).exists():
        return JsonResponse({'error': 'Нет доступа'}, status=403)

    if tutor:
        # Репетитор выбирает видимость сам, по умолчанию — «видят все».
        allowed = {value for value, _ in visibility_choices_for('tutor')}
        visibility = body.get('visibility')
        if visibility not in allowed:
            visibility = ProblemComment.Visibility.GROUP
        recipient_id = body.get('recipient_id') or None

        # ⚠️ «ВИДНО ТОЛЬКО ЭТОМУ УЧЕНИКУ» ТРЕБУЕТ УЧЕНИКА. Именно отсутствие
        # адресата и было ошибкой прежней модели: комментарий репетитора «в
        # узкий круг» без адресата означал «только я и я» — ученик его не
        # видел, хотя по названию должен был. Теперь такой запрос честно
        # отвергается, а не сохраняется в состояние, которого нет.
        if visibility == ProblemComment.Visibility.PRIVATE:
            if not recipient_id or not assignment.students.filter(
                    pk=recipient_id).exists():
                return JsonResponse(
                    {'error': 'Выберите ученика, которому это видно'},
                    status=400)
        else:
            # У «всей группе» и «заметки для себя» адресата быть не может.
            recipient_id = None
    else:
        # Вопрос ученика ВСЕГДА личный: публичные вопросы учеников —
        # это канал списывания, а не обсуждение. Заметку для себя ученик
        # завести может — это его собственные пометки по задаче.
        visibility = (ProblemComment.Visibility.SELF
                      if body.get('visibility') == ProblemComment.Visibility.SELF
                      else ProblemComment.Visibility.PRIVATE)
        recipient_id = None

    comment = ProblemComment.objects.create(
        assignment=assignment, problem_item=item, author=request.user,
        text=text, visibility=visibility, recipient_id=recipient_id)

    return JsonResponse({
        'id': comment.pk,
        'author': comment.author.get_full_name() or comment.author.username,
        'text': comment.text,
        'visibility': comment.visibility,
        'visibility_display': comment.get_visibility_display(),
        'note': comment.note_for(request.user),
        'created_at': timefmt.fmt(comment.created_at),
    })


# ---------------------------------------------------------------------------
# Вкладка «Проверка» удалена (сессия 9, фаза 3)
# ---------------------------------------------------------------------------
# Владелец: смысл был только для репетитора с несколькими группами, а всё то
# же видно через открытие каждого занятия. Дашборд входящих был ЧЕТВЁРТЫМ
# местом, где считаются ждущие проверки работы, и считал он их по-своему —
# именно из-за таких копий три экрана показывали три разных числа (фаза 4).
#
# ⚠️ Адрес `/teacher/` оставлен редиректом НЕ ради закладок: после входа
# преподаватель попадает ровно сюда (`problems/views_auth.py`). Удалить
# насухо значило встретить вошедшего четырёхсотой.


@tutor_required
def teacher_home(request):
    """Корень кабинета. Своего экрана у него больше нет — уводим к ученикам."""
    return redirect('teacher:groups')


# ---------------------------------------------------------------------------
# Фаза 13 — проверка решений переехала под групповые URL
# ---------------------------------------------------------------------------
#
# Логику проверки НЕ меняли: те же вьюхи и те же шаблоны, просто адрес теперь
# начинается с группы. Смысл переезда — принцип «вся работа с группой внутри
# вкладки Группы»: раньше репетитор из группы проваливался в /teacher/
# assignment/<pk>/ и терял контекст, в какой он вообще группе.

# ---------------------------------------------------------------------------
# Фаза 12 — сводка решений: вид «по ученикам»
# ---------------------------------------------------------------------------
# ⚠️ ЗАЧЕМ. Таблица «ученик × задача» на трёх учениках и семи задачах — это
# 21 строка, из которых действия требует ОДНА. Остальные двадцать — «не
# начато» с прочерком, и занимают они столько же места.
#
# Строки и раньше шли по ученикам, но этого не было ВИДНО: имя повторялось в
# каждой строке, между учениками не было границы. Проблема в подаче, а не в
# данных, поэтому таблица никуда не делась — она осталась вторым видом.

SUBMISSIONS_VIEW_KEY = 'submissions_view'


def _machine_totals(subs, items_by_id):
    """(насчитала машина, могла насчитать). Считаем только МАШИННЫЕ проверки.

    Признак машинной проверки — `reviewed_by is None`: человек, поставивший
    оценку, всегда записан. Смешивать их нельзя, иначе подпись «машина уже
    насчитала» будет включать в себя и то, что поставил репетитор.
    """
    from decimal import Decimal

    from problems.assignment_rows import item_max_score

    got = Decimal('0')
    could = Decimal('0')
    for sub in subs:
        feedback = getattr(sub, 'feedback', None)
        if feedback is None or feedback.reviewed_by_id is not None:
            continue
        item = items_by_id.get(sub.problem_item_id)
        if item is None:
            continue
        got += Decimal(str(feedback.score or 0))
        could += item_max_score(item)
    return got, could


def student_cards(assignment, group):
    """Карточка на каждого ученика: что сдал, что насчитала машина, что делать.

    Содержимое намеренно скупое — владелец просил не захламлять.
    """
    from decimal import Decimal

    from django.urls import reverse

    from problems.models import Submission

    items = list(assignment.items.select_related('catalog_problem',
                                                 'custom_problem'))
    items_by_id = {i.pk: i for i in items}
    total = len(items)

    subs_by_student = {}
    for sub in (Submission.objects
                .filter(assignment=assignment)
                .select_related('feedback', 'student')
                .order_by('problem_item__order', 'pk')):
        subs_by_student.setdefault(sub.student_id, []).append(sub)

    cards = []
    for student in assignment.students.all().order_by('last_name', 'username'):
        subs = subs_by_student.get(student.pk, [])
        done = [s for s in subs if s.status in ('submitted', 'reviewed')]
        pending = [s for s in subs if s.status == 'submitted']
        checked = [s for s in subs if s.status == 'reviewed']
        got, could = _machine_totals(subs, items_by_id)

        if not done:
            state = 'not_started'
            state_label = 'не начата'
        elif pending:
            state = 'partial'
            state_label = 'проверено %d из %d' % (len(checked), len(done))
        else:
            state = 'checked'
            state_label = 'проверено'

        # Ссылка «глазами ученика» — тихая и ОТДЕЛЬНАЯ. Главная кнопка ведёт
        # туда, где работают, а не туда, где смотрят.
        student_view = None

        if pending:
            button = {'label': 'Проверить %d %s' % (len(pending),
                                                    _tasks_word(len(pending))),
                      'kind': 'main',
                      'url': reverse('teacher:group_review_submission',
                                     args=[group.pk, pending[0].pk])}
            student_view = reverse('teacher:student_work_review',
                                   args=[group.pk, assignment.pk, student.pk])
        elif done:
            # ⚠️ «СМОТРЕТЬ РАБОТУ» ВЕДЁТ НА ПРОВЕРКУ, А НЕ НА РАЗБОР ГЛАЗАМИ
            # УЧЕНИКА. Раньше кнопка открывала экран ученика, где сверху
            # написано «оценки ставятся на странице проверки», — то есть
            # честно сообщала, что привела не туда.
            button = {'label': 'Смотреть работу', 'kind': 'quiet',
                      'url': reverse('teacher:group_review_submission',
                                     args=[group.pk, done[0].pk])}
            student_view = reverse('teacher:student_work_review',
                                   args=[group.pk, assignment.pk, student.pk])
        else:
            # Написать ученику сегодня можно ровно одним способом —
            # комментарием к задаче на странице задания. Отдельной переписки
            # в продукте нет, и выдумывать кнопку, которая никуда не ведёт,
            # нельзя.
            button = {'label': 'Написать', 'kind': 'quiet',
                      'url': reverse('teacher:group_assignment',
                                     args=[group.pk, assignment.pk])}

        # ⚠️ ИТОГОВЫЙ БАЛЛ — ВТОРОЕ КРУПНОЕ ЧИСЛО КАРТОЧКИ (сессия 7, фаза 4).
        # Считается ТАК ЖЕ, как на экране итогов проверки (`work_done`): в
        # числителе всё выставленное — и машиной, и человеком, — в
        # знаменателе сумма максимумов позиций. Иначе два экрана об одной
        # работе показывали бы два разных итога.
        from problems.assignment_rows import item_max_score

        scored = Decimal('0')
        scored_max = Decimal('0')
        for sub in done:
            feedback = getattr(sub, 'feedback', None)
            if feedback is not None and feedback.score is not None:
                scored += Decimal(str(feedback.score))
            if sub.problem_item_id and sub.problem_item_id in items_by_id:
                scored_max += item_max_score(items_by_id[sub.problem_item_id])

        submitted_at = max([s.submitted_at for s in done if s.submitted_at]
                           or [None])
        cards.append({
            'student': student,
            'submitted': len(done),
            'total': total,
            'submitted_at': submitted_at,
            'submitted_human': timefmt.fmt(submitted_at, timefmt.SHORT),
            'scored': _clean_points(scored),
            'scored_max': _clean_points(scored_max),
            'has_scored': scored_max > 0,
            'machine_got': _clean_points(got),
            'machine_could': _clean_points(could),
            'has_machine': could > 0,
            'pending': len(pending),
            'state': state,
            'state_label': state_label,
            'button': button,
            'student_view': student_view,
        })

    # Сначала требующие проверки, потом проверенные, в конце не приступавшие:
    # порядок карточек — это и есть очередь работы.
    order = {'partial': 0, 'checked': 1, 'not_started': 2}
    cards.sort(key=lambda c: (0 if c['pending'] else 1, order[c['state']],
                              (c['student'].last_name or '').lower()))
    return cards


def _tasks_word(number):
    if number % 10 == 1 and number % 100 != 11:
        return 'задачу'
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return 'задачи'
    return 'задач'


@tutor_required
def group_submissions(request, group_id, assignment_id):
    """Сводка решений: два вида — по ученикам и по задачам."""
    from .views import assignment_detail

    group = own_group_or_404(request.user, group_id)
    assignment = group_assignment_or_404(group, assignment_id)

    # ⚠️ СПИСОК ИЗ ОДНОГО УЧЕНИКА ВЫРОЖДАЕТСЯ (сессия 9, фаза 9). У занятия
    # один на один эта страница — одна карточка с одной кнопкой; открывать
    # её ради того, чтобы нажать единственное, что на ней есть, значит
    # ставить лишний клик на каждом заходе. Уводим сразу к работе.
    # ⚠️ Прямой адрес не ломаем: `?view=problems` и `?list=1` продолжают
    # показывать сводку — она остаётся рабочей поверхностью.
    solo = group.single_student
    if (solo is not None and request.GET.get('view') != 'problems'
            and request.GET.get('list') != '1'):
        cards = student_cards(assignment, group)
        card = next((c for c in cards if c['student'].pk == solo.pk), None)
        if card and card.get('button', {}).get('url'):
            return redirect(card['button']['url'])

    # ⚠️ ВИД ПО УЧЕНИКАМ — ЕДИНСТВЕННЫЙ В ИНТЕРФЕЙСЕ (сессия 7, фаза 1).
    # Переключатель убран по ревью владельца, поэтому выбор БОЛЬШЕ НЕ
    # ЗАПОМИНАЕТСЯ: запомненный «по задачам» открывал бы таблицу, с которой
    # некуда вернуться — кнопки-то нет. Таблица остаётся рабочей и
    # открывается прямой ссылкой `?view=problems`.
    view = request.GET.get('view')

    if view == 'problems':
        return assignment_detail(request, assignment.pk, group=group)

    return render(request, 'teacher/groups/submissions_by_student.html', {
        'group': group,
        'assignment': assignment,
        'cards': student_cards(assignment, group),
        'view': 'students',
        'stats': assignment_stats(assignment),
    })


@tutor_required
def student_work_review(request, assignment_id, student_id, group_id=None):
    """Разбор работы ученика — ТОТ ЖЕ экран, что видит ученик.

    ⚠️ Именно тот же, а не «похожий»: если ученик спорит с оценкой, спорить
    надо об одном экране. Отдельная «версия для преподавателя» разошлась бы
    с ученической на первой же правке.

    ⚠️ ГРУППА НЕОБЯЗАТЕЛЬНА. Раньше адрес был только групповым, и у работы
    без группы (а такие есть — их создаёт старый конструктор домашек)
    кнопка «посмотреть глазами ученика» просто ИСЧЕЗАЛА со страницы
    проверки: `work_review_url` считался `None`. Пропавшая кнопка для
    пользователя неотличима от сломанной, поэтому у экрана появился второй,
    безгрупповой адрес, а права проверяются по автору работы.
    """
    from django.urls import reverse

    from problems.models import Assignment, User

    from student.views import work_review_context

    if group_id is not None:
        group = own_group_or_404(request.user, group_id)
        assignment = group_assignment_or_404(group, assignment_id)
        student = get_object_or_404(User, pk=student_id,
                                    enrolled_groups=group)
        back_url = reverse('teacher:group_submissions',
                           args=[group.pk, assignment.pk])
    else:
        assignment = get_object_or_404(Assignment, pk=assignment_id)
        if not (request.user.is_staff or assignment.author_id == request.user.pk
                or (assignment.group_id
                    and assignment.group.teacher_id == request.user.pk)):
            raise Http404
        student = get_object_or_404(User, pk=student_id,
                                    assignments_received=assignment)
        back_url = reverse('teacher:assignment_detail', args=[assignment.pk])

    # Какую задачу раскрыть: приходит с экрана проверки (`?open=<позиция>`).
    try:
        open_item = int(request.GET.get('open') or 0) or None
    except ValueError:
        open_item = None

    context = work_review_context(
        assignment, student, viewer=request.user, for_tutor=True,
        back_url=back_url, back_label='К решениям', open_item=open_item)
    return render(request, 'student/work_review.html', context)


@tutor_required
def group_review_submission(request, group_id, submission_id):
    """Форма оценки решения — внутри группы."""
    from problems.models import Submission

    from .views import review_submission

    group = own_group_or_404(request.user, group_id)
    submission = get_object_or_404(Submission, pk=submission_id,
                                   assignment__group=group)
    return review_submission(request, submission.pk, group=group)


# ---------------------------------------------------------------------------
# Фаза 20 — решалка прямо на странице задания
# ---------------------------------------------------------------------------

@require_POST
@tutor_required
def api_item_answers(request):
    """Утвердить (или заменить своим) то, что будет проверяться машиной.

    Пишем в ПОЗИЦИЮ задания, а не в каталог: каталог общий на всех
    репетиторов, а утверждение — решение конкретного человека для
    конкретной работы. `answers = {}` или `null` снимает утверждение и
    возвращает задачу на ручную проверку.
    """
    from problems.assignment_rows import answer_parts
    from problems.models import AssignmentItem

    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Неверный формат'}, status=400)

    item = get_object_or_404(
        AssignmentItem.objects.select_related('assignment', 'catalog_problem',
                                              'custom_problem'),
        pk=body.get('item_id'))
    if not item.is_tutor_for(request.user):
        return JsonResponse({'error': 'Нет доступа'}, status=403)

    if body.get('clear'):
        item.answer_override = None
        item.save(update_fields=['answer_override'])
        return JsonResponse({'ok': True, 'approved': item.answers_approved,
                             'answers': {}})

    incoming = body.get('answers') or {}
    if not isinstance(incoming, dict):
        return JsonResponse({'error': 'Неверный формат'}, status=400)

    # Ключи принимаем ТОЛЬКО те, что есть у этой задачи: чужой pk в JSON не
    # должен превращаться в невидимую запись, которую потом никто не найдёт.
    allowed = {('' if part is None else str(part.pk))
               for part in answer_parts(item)}
    answers = {key: str(value or '').strip()
               for key, value in incoming.items() if key in allowed}
    answers = {key: value for key, value in answers.items() if value}
    item.answer_override = answers or None
    item.save(update_fields=['answer_override'])
    return JsonResponse({'ok': True, 'approved': item.answers_approved,
                         'answers': item.answer_override or {}})


@tutor_required
@require_POST
def api_item_points(request):
    """Максимальный балл за позицию — правится прямо на странице задания.

    Балл и есть максимум: два отдельных элемента «показать балл» и «задать
    максимум» были бы одним и тем же числом в двух местах, а два места для
    одного числа всегда расходятся.

    Отрицательный балл не принимаем: за задачу нельзя получить меньше нуля,
    и такое число сломало бы и сумму работы, и проценты.
    """
    from decimal import Decimal, InvalidOperation

    from problems.models import AssignmentItem

    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Неверный формат'}, status=400)

    item = get_object_or_404(
        AssignmentItem.objects.select_related('assignment'),
        pk=body.get('item_id'))
    if not item.is_tutor_for(request.user):
        return JsonResponse({'error': 'Нет доступа'}, status=403)

    # ⚠️ ЗАЩИТА СТОИТ НА СЕРВЕРЕ, А НЕ ТОЛЬКО В РАЗМЕТКЕ. Спрятать поле мало:
    # запрос можно отправить в обход браузера, а балл, изменённый после
    # первой сдачи, переписывает знаменатель уже выставленным оценкам.
    if item.assignment.points_locked:
        return JsonResponse(
            {'error': 'Баллы заперты — работу уже сдавали'}, status=409)

    raw = str(body.get('points', '')).strip().replace(',', '.')
    try:
        points = Decimal(raw)
    except (InvalidOperation, ValueError):
        return JsonResponse({'error': 'Нужно число'}, status=400)
    if points < 0:
        return JsonResponse({'error': 'Балл не может быть меньше нуля'},
                            status=400)
    if points > 1000:
        return JsonResponse({'error': 'Слишком большой балл'}, status=400)

    item.points = points
    item.save(update_fields=['points'])

    from problems.assignment_export import total_points, print_rows

    rows, _ = print_rows(item.assignment)
    return JsonResponse({'ok': True,
                         'points': _clean_points(item.points),
                         'total': _clean_points(total_points(rows))})


def _clean_points(value):
    """«3.00» → «3», «2.50» → «2.5». Хвостовые нули на экране — шум."""
    if value is None:
        return ''
    text = ('%s' % value)
    return text.rstrip('0').rstrip('.') if '.' in text else text


@require_POST
@tutor_required
def api_item_solution(request):
    """Сохранить решение позиции и правило его показа.

    Отдельным эндпоинтом, а не общей формой задания: решений в задании
    может быть десять, и отправлять их все ради правки одного — верный
    способ затереть чужую правку, сделанную в соседней вкладке.
    """
    from problems.models import AssignmentItem, SolutionVisibility

    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Неверный формат'}, status=400)

    item = get_object_or_404(
        AssignmentItem.objects.select_related('assignment'),
        pk=body.get('item_id'))
    if not item.is_tutor_for(request.user):
        return JsonResponse({'error': 'Нет доступа'}, status=403)

    if 'solution_override' in body:
        item.solution_override = body.get('solution_override') or ''

    mode = body.get('solution_visible_after')
    if mode in dict(SolutionVisibility.choices):
        item.solution_visible_after = mode

    if body.get('release_now'):
        # «Открыть решение сейчас» — момент фиксирует СЕРВЕР.
        item.solution_released_at = timezone.now()

    item.save()
    return JsonResponse({
        'ok': True,
        'source': item.solution_source,
        'mode': item.solution_visible_after,
        'mode_display': item.get_solution_visible_after_display(),
        'released_at': timefmt.fmt(item.solution_released_at, empty=None),
    })


# ---------------------------------------------------------------------------
# Фаза 13 — экран завершения работы
# ---------------------------------------------------------------------------

@tutor_required
def work_done(request, group_id, assignment_id, student_id):
    """Работа пройдена насквозь: итог, общий комментарий, следующий ученик.

    ⚠️ ЗДЕСЬ ЖИВЁТ «КОММЕНТАРИЙ КО ВСЕЙ РАБОТЕ». Раньше он стоял на экране
    проверки ОДНОЙ задачи с извиняющейся подписью «Один на всю работу, а не
    на эту задачу» — сама необходимость такой подписи говорила, что элемент
    стоит не там. Написать про работу целиком можно только тогда, когда она
    прочитана целиком, то есть ровно здесь.
    """
    from problems.models import User, WorkFeedback

    group = own_group_or_404(request.user, group_id)
    assignment = group_assignment_or_404(group, assignment_id)
    student = get_object_or_404(User, pk=student_id)

    if request.method == 'POST':
        comment = (request.POST.get('work_comment') or '').strip()
        WorkFeedback.objects.update_or_create(
            assignment=assignment, student=student,
            defaults={'comment': comment, 'author': request.user})
        messages.success(request, 'Работа проверена.')
        following = _next_student_to_check(assignment, student)
        if following is not None:
            return redirect('teacher:group_submissions',
                            group_id=group.pk, assignment_id=assignment.pk)
        return redirect('teacher:group_submissions',
                        group_id=group.pk, assignment_id=assignment.pk)

    # ⚠️ СБОРКА СТРОК ОДНА НА ВСЕ ЭКРАНЫ (сессия 7, фаза 4). Раньше здесь
    # был собственный цикл по очереди проверки: он знал только балл и не
    # знал СОСТОЯНИЯ строки, поэтому справа стояло одинокое число без
    # признака «верно / частично / неверно / не отвечал». Теперь берём то
    # же `work_summary`, что кормит разбор глазами ученика, — и цвета, и
    # знаменатель приходят оттуда же, без второго вычисления.
    from problems.work_review import work_summary

    summary = work_summary(assignment, student, viewer=request.user)

    return render(request, 'teacher/groups/work_done.html', {
        'group': group,
        'assignment': assignment,
        'student': student,
        'rows': summary['rows'],
        'total': summary['scored'],
        'maximum': summary['max_score'],
        'work_feedback': WorkFeedback.objects.filter(
            assignment=assignment, student=student).first(),
        'next_student': _next_student_to_check(assignment, student),
    })


def _next_student_to_check(assignment, current):
    """Следующий ученик, у которого есть что проверять. None — все пройдены."""
    from problems.models import Submission

    pending = (Submission.objects
               .filter(assignment=assignment, status='submitted')
               .exclude(student=current)
               .select_related('student')
               .order_by('student__last_name', 'student__username'))
    first = pending.first()
    return first.student if first is not None else None


# ---------------------------------------------------------------------------
# Оценка ПРЯМО В РАЗБОРЕ РАБОТЫ глазами ученика (сессия 8, п. 14.4)
# ---------------------------------------------------------------------------
# ⚠️ ЗАЧЕМ. Режим «глазами ученика» был только для чтения, и репетитор,
# заметивший ошибку оценки, уходил на другой экран, искал там ту же задачу и
# возвращался. Балл ставится там, где смотрят работу.

@tutor_required
@require_POST
def api_grade_submission(request):
    """Балл и комментарий за ОДНУ задачу. Возвращает JSON, страницу не рвёт.

    ⚠️ БАЛЛ ОБРЕЗАЕТСЯ ПО МАКСИМУМУ ЗАДАЧИ, И ЭТО ДЕЛАЕТ СЕРВЕР — той же
    функцией `_max_score_for`, что и обычный экран проверки. В базе однажды
    нашлась оценка «9 из 5»: разметке (`max=`) верить нельзя, запрос можно
    отправить в обход браузера.

    ⚠️ `Assignment.points_locked` тут НИ ПРИ ЧЁМ: он про МАКСИМУМ позиции, а
    не про выставляемую оценку. Проверять работы после первой сдачи — это и
    есть обычный ход дела.
    """
    from problems.models import Submission, TeacherFeedback

    from .views import _max_score_for, update_student_progress

    submission = get_object_or_404(
        Submission.objects.select_related('assignment', 'problem_item'),
        pk=request.POST.get('submission') or 0)
    assignment = submission.assignment
    allowed = (request.user.is_staff
               or assignment.author_id == request.user.pk
               or (assignment.group_id
                   and assignment.group.teacher_id == request.user.pk))
    if not allowed:
        raise Http404

    # Запятая — законный ввод: нормализует её ОДНА функция на форму и на
    # этот эндпоинт (`teacher.views.normalize_decimal`).
    from .views import normalize_decimal

    try:
        score = float(normalize_decimal(request.POST.get('score')))
    except ValueError:
        return JsonResponse({'error': 'балл не число'}, status=400)
    top = float(_max_score_for(submission) or 0)
    score = max(0.0, min(score, top))
    comment = (request.POST.get('comment') or '').strip()

    feedback = getattr(submission, 'feedback', None)
    if feedback is None:
        feedback = TeacherFeedback.objects.create(
            submission=submission, score=score, comment=comment,
            reviewed_by=request.user)
    else:
        feedback.score = score
        feedback.comment = comment
        feedback.reviewed_by = request.user
        feedback.save(update_fields=['score', 'comment', 'reviewed_by'])

    submission.status = 'reviewed'
    submission.save(update_fields=['status'])
    try:
        update_student_progress(submission, feedback)
    except Exception:      # прогресс по темам не имеет права уронить оценку
        logger.exception('Прогресс по темам не обновился — оценка сохранена')

    # ⚠️ `label` уезжает ОБРАТНО В ПОЛЕ, а поле показывает число по-русски —
    # значит и здесь запятая. С точкой сервер возвращал бы «1.5» туда, где
    # репетитор только что набрал «1,5», и число дёргалось бы после каждого
    # сохранения.
    label = ('%.2f' % score).rstrip('0').rstrip('.').replace('.', ',')
    return JsonResponse({'score': score, 'max': top, 'label': label})
