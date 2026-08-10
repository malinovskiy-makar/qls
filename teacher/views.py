"""
Панель учителя: список домашек, решения учеников, форма проверки.
"""
import json
import re
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .access import tutor_required


# ---------------------------------------------------------------------------
# Декоратор: только учитель (или суперпользователь)
# ---------------------------------------------------------------------------

def teacher_required(view_func):
    @login_required(login_url='/login/')
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not (request.user.role == 'teacher' or request.user.is_staff):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# В4 — обновление прогресса после проверки
# ---------------------------------------------------------------------------

def update_student_progress(submission, feedback):
    """Обновляет StudentTopicProgress и StudentSkillProgress после проверки.

    ⚠️ РАБОТА БЕЗ КАТАЛОЖНОЙ ЗАДАЧИ ПРОПУСКАЕТСЯ. У своей задачи репетитора
    записи в каталоге нет вовсе, а прогресс считается по темам и навыкам
    каталожной задачи — брать их неоткуда. Раньше функция падала на такой
    работе прямо при сохранении оценки: ровно тот же класс, что ошибка 500
    на «Прогрессе ученика» (баг 7.1).

    Своя задача не попадает в прогресс по темам — это осознанная плата за
    то, что тем у неё нет. Придумывать их за репетитора нельзя.
    """
    from problems.models import StudentSkillProgress, StudentTopicProgress

    problem = submission.problem
    if problem is None:
        return
    student = submission.student

    max_score = 5.0
    try:
        rubric = problem.rubric
        criteria_max = sum(c.max_score for c in rubric.criteria.all())
        if criteria_max > 0:
            max_score = criteria_max
    except Exception:
        pass

    score_val = float(feedback.score) if feedback.score is not None else 0.0
    score_percent = min(100.0, (score_val / max_score) * 100)

    WEIGHT_NEW = 0.3

    for topic in problem.topics.all():
        progress, created = StudentTopicProgress.objects.get_or_create(
            student=student,
            topic=topic,
            defaults={'level': int(round(score_percent))}
        )
        if not created:
            new_level = progress.level * (1 - WEIGHT_NEW) + score_percent * WEIGHT_NEW
            progress.level = min(100, int(round(new_level)))
            progress.save()

    for skill in problem.skills.all():
        progress, created = StudentSkillProgress.objects.get_or_create(
            student=student,
            skill=skill,
            defaults={'level': int(round(score_percent))}
        )
        if not created:
            new_level = progress.level * (1 - WEIGHT_NEW) + score_percent * WEIGHT_NEW
            progress.level = min(100, int(round(new_level)))
            progress.save()


# ---------------------------------------------------------------------------
# В3 — Дашборд учителя
# устарело, удалить после сессии 5: маршрут `/teacher/` теперь ведёт на
# дашборд входящих (`views_groups.dashboard`). Вьюха оставлена как справка.
# ---------------------------------------------------------------------------

@teacher_required
def dashboard(request):
    from problems.models import Assignment, Submission

    assignments = Assignment.objects.filter(
        author=request.user
    ).prefetch_related('problems').order_by('-id')

    assignment_data = []
    for a in assignments:
        pending = Submission.objects.filter(assignment=a, status='submitted').count()
        total = Submission.objects.filter(assignment=a).count()
        assignment_data.append({
            'assignment': a,
            'pending': pending,
            'total': total,
        })

    return render(request, 'teacher/dashboard.html', {
        'assignment_data': assignment_data,
    })


# ---------------------------------------------------------------------------
# В3 — Список решений по домашке
# ---------------------------------------------------------------------------

@teacher_required
def assignment_detail(request, pk, group=None):
    """Таблица решений по домашке.

    Переехала под групповые URL (`/teacher/groups/<g>/assignments/<a>/
    submissions/`). Логика проверки НЕ менялась — только адрес и навигация,
    поэтому вьюха одна, а `group` определяет, куда ведут ссылки и хлебные
    крошки. Старый адрес остался редиректом.
    """
    from problems.models import Assignment, Submission

    assignment = get_object_or_404(Assignment, pk=pk, author=request.user)

    status_filter = request.GET.get('status', '')
    submissions = Submission.objects.filter(
        assignment=assignment
    ).select_related('student', 'problem', 'problem_item',
                     'problem_item__catalog_problem',
                     'problem_item__custom_problem'
                     ).order_by('student__username', 'problem__id')

    if status_filter:
        submissions = submissions.filter(status=status_filter)

    # ⚠️ НОРМАЛЬНОЕ НАЗВАНИЕ ВМЕСТО «Задача #». В банке у части задач
    # заголовка нет вовсе, и таблица показывала «Задача #40131» — по такой
    # строке нельзя понять, что проверяешь. Берём заголовок, а если его
    # нет — первые слова условия, обрезкой по границе слова.
    submissions = list(submissions)
    for sub in submissions:
        sub.display_title = _submission_title(sub)

    return render(request, 'teacher/assignment_detail.html', {
        'assignment': assignment,
        'submissions': submissions,
        'status_filter': status_filter,
        'group': group or assignment.group,
    })


# ---------------------------------------------------------------------------
# В3 — Форма проверки решения
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Фаза 13 — проверка становится ПОТОКОМ
# ---------------------------------------------------------------------------
# ⚠️ ЗАЧЕМ. Экран проверял ОДНУ задачу, а не работу. Чтобы пройти работу из
# семи задач, репетитор семь раз возвращался в список и открывал заново. На
# этом же экране стояло поле «Комментарий ко всей работе» с извиняющейся
# подписью «Один на всю работу, а не на эту задачу» — сама необходимость
# такой подписи говорит, что элемент стоит не там. Он переехал на экран
# завершения работы.

def review_queue(assignment, student):
    """Решения ученика по работе В ТОМ ЖЕ ПОРЯДКЕ, что и задачи на экране.

    Порядок берём у `ordered_items` — той же функции, что рисует задание и
    печатает листок. Иначе «задача 3 из 7» на проверке означала бы не ту
    задачу, что под номером 3 у ученика.
    """
    from problems.assignment_rows import ordered_items
    from problems.models import Submission

    items = ordered_items(assignment, list(
        assignment.items.select_related('catalog_problem', 'custom_problem')
        .order_by('order', 'id')))
    subs = {s.problem_item_id: s for s in Submission.objects.filter(
        assignment=assignment, student=student).select_related('feedback')}
    return [subs[i.pk] for i in items if i.pk in subs]


def review_position(assignment, student, submission):
    """(номер с 1, всего, предыдущее, следующее, следующее НЕПРОВЕРЕННОЕ)."""
    queue = review_queue(assignment, student)
    ids = [s.pk for s in queue]
    if submission.pk not in ids:
        return 1, len(queue) or 1, None, None, None
    index = ids.index(submission.pk)
    previous = queue[index - 1] if index > 0 else None
    following = queue[index + 1] if index + 1 < len(queue) else None
    # Следующее НЕПРОВЕРЕННОЕ ищем по кругу от текущего: репетитор мог
    # начать с середины, и «дальше» обязано увести к работе, а не в конец.
    unchecked = None
    for offset in range(1, len(queue) + 1):
        candidate = queue[(index + offset) % len(queue)]
        if candidate.pk != submission.pk and candidate.status == 'submitted':
            unchecked = candidate
            break
    return index + 1, len(queue), previous, following, unchecked



def _score_presets(max_score):
    """Три кнопки: ноль, РОВНО половина, максимум задачи.

    ⚠️ ПОЛОВИНА БОЛЬШЕ НЕ ОКРУГЛЯЕТСЯ (сессия 7, фаза 3). Раньше при
    максимуме 3 кнопки давали 0 / 2 / 3: округление вверх делало среднюю
    кнопку щедрой без причины — «два из трёх» это не половина. Дробный балл
    в базе допустим и так (веса пунктов дают 1,25 и 3,75), заводить ради
    середины отдельное правило незачем.

    ⚠️ У ЗНАЧЕНИЯ И ПОДПИСИ РАЗНЫЕ ФОРМЫ ЗАПИСИ. Подпись русская, через
    запятую («1,5»); значение — с точкой, потому что его кладут в
    `<input type="number">` и разбирают на сервере через `float()`. Запятая
    в значении означала бы пустое поле в браузере и ноль на сервере — то
    есть кнопка «половина» тихо ставила бы ноль.
    """
    from decimal import Decimal

    top = Decimal(str(max_score or 0))
    half = top / 2

    def show(value):
        """Один знак после запятой, без хвостового нуля: 5, 3,5, 1,5."""
        text = ('%.1f' % value).rstrip('0').rstrip('.')
        return text or '0'

    values = []
    for value in (Decimal('0'), half, top):
        raw = show(value)              # с точкой — для поля и сервера
        if raw in [v['value'] for v in values]:
            continue
        values.append({'value': raw, 'label': raw.replace('.', ',')})
    return values


def _answer_state(feedback, max_score, auto_zero):
    """verdict строки: correct / partial / wrong / blank / pending.

    Совпадает по смыслу и по названиям с `work_review.work_summary`, чтобы
    экран проверки и экран разбора красили одну задачу одинаково.
    """
    if feedback is None or feedback.score is None:
        return 'blank' if auto_zero else 'pending'
    score = float(feedback.score)
    top = float(max_score or 0)
    if top and score >= top:
        return 'correct'
    if score > 0:
        return 'partial'
    return 'blank' if auto_zero else 'wrong'


def _max_score_for(submission):
    """Максимальный балл за эту задачу в этой работе.

    Вынесено отдельно, потому что число нужно ДВАЖДЫ: при показе формы (для
    пресетов и подписи «максимум N») и при приёме POST (чтобы обрезать
    введённое). Считать его в двух местах — верный способ получить два
    разных числа.
    """
    from problems import part_grading

    item = submission.problem_item
    if item is None:
        return 10
    if part_grading.applies(item):
        rows = part_grading.part_rows(item, submission)
        if rows:
            return sum(row['max_score'] for row in rows)
    if item.points is not None:
        return item.points
    return 10


def _is_auto_zero(submission, part_rows):
    """Ноль поставлен машиной ЗА ПУСТОТУ, а не за ошибку (правило фазы 3).

    Признак живёт в `part_grading` — им пользуется и разбор работы. Два
    места, решающих один вопрос, разъехались бы, и один экран писал бы
    «без ответа», а соседний «неверно» про одну и ту же задачу.
    """
    from problems import part_grading

    return part_grading.is_auto_zero(submission, part_rows)


def _solution_without_answer(submission):
    """Ответа нет, а решение написано — это НЕ пустышка, её надо прочитать."""
    from problems import part_grading

    if (submission.submitted_answer or '').strip():
        return False
    return part_grading.wrote_anything(submission)


@teacher_required
def review_submission(request, pk, group=None):
    """Форма оценки решения. Переехала под групповые URL; логика оценки
    не менялась."""
    from problems.models import (
        MistakeTag, Submission, TeacherFeedback, WorkFeedback,
    )

    submission = get_object_or_404(Submission, pk=pk)
    if submission.assignment.author != request.user and not request.user.is_staff:
        raise PermissionDenied

    problem = submission.problem
    existing_feedback = getattr(submission, 'feedback', None)
    mistake_tags = MistakeTag.objects.all().order_by('name')

    if request.method == 'POST':
        score_str = request.POST.get('score', '').strip()
        comment = request.POST.get('comment', '').strip()
        mistake_ids = request.POST.getlist('mistakes')

        try:
            score = float(score_str)
        except ValueError:
            score = 0.0

        # ⚠️ БАЛЛ ОБРЕЗАЕТСЯ ПО МАКСИМУМУ ЗАДАЧИ, И ЭТО ДЕЛАЕТ СЕРВЕР.
        # В базе нашлась оценка «9 из 5»: поле «своё» принимало любое число,
        # а разметке (`max=`) верить нельзя — форму можно отправить в обход
        # браузера. Балл выше максимума ломает и сумму работы, и проценты в
        # статистике; отрицательный означал бы штраф, которого в правилах нет.
        top = float(_max_score_for(submission) or 0)
        score = max(0.0, min(score, top))

        if existing_feedback:
            existing_feedback.score = score
            existing_feedback.comment = comment
            existing_feedback.reviewed_by = request.user
            existing_feedback.save()
            existing_feedback.mistakes.set(mistake_ids)
            feedback = existing_feedback
        else:
            feedback = TeacherFeedback.objects.create(
                submission=submission,
                score=score,
                comment=comment,
                reviewed_by=request.user,
            )
            feedback.mistakes.set(mistake_ids)

        submission.status = 'reviewed'
        submission.save()

        # Комментарий КО ВСЕЙ РАБОТЕ. Пишется здесь же (репетитор уже на
        # этом экране), но относится к работе целиком и показывается
        # ученику сразу под итоговым баллом, а не в последней задаче.
        work_comment = (request.POST.get('work_comment') or '').strip()
        if work_comment or WorkFeedback.objects.filter(
                assignment=submission.assignment,
                student=submission.student).exists():
            WorkFeedback.objects.update_or_create(
                assignment=submission.assignment, student=submission.student,
                defaults={'comment': work_comment, 'author': request.user})

        update_student_progress(submission, feedback)

        group_obj = group or submission.assignment.group

        # ⚠️ «Сохранить и дальше» ведёт к СЛЕДУЮЩЕЙ НЕПРОВЕРЕННОЙ задаче
        # этого же ученика, а не обратно в список. Возврат в список после
        # каждой задачи и был тем, из-за чего работа из семи задач стоила
        # семи заходов.
        if request.POST.get('go') == 'next' and group_obj is not None:
            _, _, _, _, unchecked = review_position(
                submission.assignment, submission.student, submission)
            if unchecked is not None:
                return redirect('teacher:group_review_submission',
                                group_id=group_obj.pk,
                                submission_id=unchecked.pk)
            # Непроверенного больше нет — работа пройдена насквозь.
            return redirect('teacher:work_done', group_id=group_obj.pk,
                            assignment_id=submission.assignment_id,
                            student_id=submission.student_id)

        messages.success(request, f'Решение проверено. Балл: {score}')
        if group_obj is not None:
            return redirect('teacher:group_submissions',
                            group_id=group_obj.pk,
                            assignment_id=submission.assignment.pk)
        return redirect('teacher:assignment_detail', pk=submission.assignment.pk)

    # Ответы по пунктам — рядом с эталонными. Та же сборка, что у ученика:
    # разъехавшиеся вердикты на двух экранах — это спор на пустом месте.
    from problems import part_grading

    item = submission.problem_item
    part_rows = []
    auto_score = None
    max_score = _max_score_for(submission)
    if item is not None and part_grading.applies(item):
        part_rows = part_grading.part_rows(item, submission)
        scored = [row['score'] for row in part_rows
                  if row['score'] is not None]
        auto_score = sum(scored) if scored else None

    group_obj = group or submission.assignment.group
    number, total, previous, following, unchecked = review_position(
        submission.assignment, submission.student, submission)

    # ⚠️ Условие собираем ЗДЕСЬ, а не цепочкой фильтров в шаблоне.
    # `{{ a.statement|default:problem.statement }}` падает, когда `problem`
    # пуст (работа по своей задаче репетитора): аргумент фильтра, в отличие
    # от самой переменной, Django молча не проглатывает.
    statement = ''
    if item is not None:
        statement = item.statement or ''
    if not statement and problem is not None:
        statement = problem.statement or ''

    return render(request, 'teacher/review.html', {
        'submission': submission,
        'problem': problem,
        'statement': statement,
        'existing_feedback': existing_feedback,
        'group': group_obj,
        'part_rows': part_rows,
        'max_score': max_score,
        'auto_score': auto_score,
        # Поток проверки: где мы в работе и куда идти дальше.
        'number': number,
        'total': total,
        'prev_sub': previous,
        'next_sub': following,
        'has_unchecked': unchecked is not None,
        # Балл ставится НАЖАТИЕМ: 0, половина, максимум. Двадцать одна
        # оценка за работу — это двадцать одно набранное руками число,
        # если оставить только поле ввода.
        'score_presets': _score_presets(max_score),
        # Пусто и в ответе, и в решении → ноль поставила машина, и это
        # надо сказать прямо, а не показывать «неверно».
        'auto_zero': _is_auto_zero(submission, part_rows),
        # ⚠️ СОСТОЯНИЕ СТРОКИ — ТЕ ЖЕ ПЯТЬ, ЧТО В РАЗБОРЕ РАБОТЫ (фаза 14.3).
        # Цвета и названия берутся из набора деталей (.k-mark--*, .k-flag--*):
        # два набора состояний для одного и того же разошлись бы на первой
        # же правке, и репетитор с учеником спорили бы, глядя на разные
        # экраны об одной задаче.
        'answer_state': _answer_state(
            existing_feedback, max_score,
            _is_auto_zero(submission, part_rows)),
        'wrote_solution_without_answer': _solution_without_answer(submission),
        'work_feedback': WorkFeedback.objects.filter(
            assignment=submission.assignment,
            student=submission.student).first(),
        # ⚠️ Кнопка «глазами ученика» есть ВСЕГДА. Раньше её адрес считался
        # только для работы в группе, и у работы без группы кнопка молча
        # исчезала со страницы — для пользователя это неотличимо от
        # «ведёт не туда».
        'work_review_url': (
            reverse('teacher:student_work_review',
                    args=[group_obj.pk, submission.assignment_id,
                          submission.student_id])
            if group_obj else
            reverse('teacher:student_work_review_plain',
                    args=[submission.assignment_id, submission.student_id])),
        'work_review_student': submission.student,
    })


# ---------------------------------------------------------------------------
# Этап Е — Группы учеников
# устарело, удалить после сессии 5: экраны групп переехали в
# `teacher/views_groups.py` (список, страница группы, создание).
# ---------------------------------------------------------------------------

@teacher_required
def groups_list(request):
    from problems.models import StudentGroup
    groups = StudentGroup.objects.filter(
        teacher=request.user
    ).prefetch_related('students').order_by('-created_at')
    return render(request, 'teacher/groups_list.html', {
        'groups': groups,
    })


@teacher_required
def group_create(request):
    from problems.models import StudentGroup, User as PlatformUser
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        student_ids = request.POST.getlist('students')
        if name:
            group = StudentGroup.objects.create(
                name=name,
                teacher=request.user,
            )
            if student_ids:
                students = PlatformUser.objects.filter(
                    pk__in=student_ids, role='student'
                )
                group.students.set(students)
            messages.success(request, f'Группа «{name}» создана.')
            return redirect('teacher:groups')

    all_students = (
        PlatformUser.objects.filter(role='student')
        .order_by('last_name', 'first_name', 'username')
    )
    return render(request, 'teacher/group_create.html', {
        'all_students': all_students,
    })


@teacher_required
def group_detail(request, pk):
    from problems.models import StudentGroup, Submission
    group = get_object_or_404(StudentGroup, pk=pk, teacher=request.user)

    students_data = []
    for student in group.students.all():
        reviewed = Submission.objects.filter(
            student=student,
            status='reviewed',
            assignment__author=request.user,
        )
        open_reviewed = reviewed.exclude(problem__problem_type__startswith='тест')
        test_reviewed = reviewed.filter(problem__problem_type__startswith='тест')

        open_scores = [
            float(s.feedback.score)
            for s in open_reviewed.select_related('feedback')
            if hasattr(s, 'feedback') and s.feedback
        ]
        test_scores = [
            float(s.feedback.score)
            for s in test_reviewed.select_related('feedback')
            if hasattr(s, 'feedback') and s.feedback
        ]

        students_data.append({
            'student': student,
            'open_count': len(open_scores),
            'open_avg': round(sum(open_scores) / len(open_scores), 1) if open_scores else None,
            'test_count': len(test_scores),
            'test_pct': round(sum(test_scores) / len(test_scores) * 100) if test_scores else None,
        })

    return render(request, 'teacher/group_detail.html', {
        'group': group,
        'students_data': students_data,
    })


# ---------------------------------------------------------------------------
# Этап Е — Прогресс ученика глазами учителя
# ---------------------------------------------------------------------------

def _submission_title(submission):
    """Читаемое название сданной задачи. Никаких «Задача #123»."""
    from problems.text_clean import preview_title

    item = submission.problem_item
    problem = (item.problem if item is not None else None) or submission.problem
    if problem is None:
        return '(задача удалена)'
    return preview_title(problem, limit=70)


def _submission_is_test(submission):
    """Тест ли эта сданная работа.

    ⚠️ ЭТО ЧИНИТ ОШИБКУ 500 НА «ПРОГРЕССЕ УЧЕНИКА». Раньше здесь стояло
    `submission.problem.problem_type`, а поле `problem` с появлением своих
    задач репетитора стало необязательным: у работы по своей задаче ссылки
    на каталог нет вовсе, и страница падала на первой же такой записи.

    Спрашиваем ПОЗИЦИЮ задания — она знает про оба вида задач. Старое поле
    остаётся запасным путём для работ, сданных до появления позиций.
    """
    item = submission.problem_item
    if item is not None:
        return item.is_test
    problem = submission.problem
    if problem is None:
        return False
    return (problem.problem_type or '').startswith('тест')


@teacher_required
def student_progress(request, pk):
    """Карточка ученика глазами репетитора — ЕДИНСТВЕННЫЙ такой экран.

    ⚠️ РЕШЕНИЕ СТОП-ГЕЙТА ФАЗЫ 10.1: экранов об одном ученике было ДВА —
    этот и `/teacher/students/<id>/stats/`. Основным оставлен ЭТОТ, потому
    что на него ведёт кнопка «открыть» из таблицы учеников и именно его
    ревьюил владелец (все требования фаз 10.2–10.6 описывают его вёрстку).
    Со второго перенесено то, чего здесь не было, — «сильные и слабые
    стороны» и теплокарта активности за полгода; сам он стал редиректом.
    Третьего экрана нет и не будет.
    """
    from problems import stats as stats_module
    from problems.models import StudentGroup, User as PlatformUser
    from problems.models_platform import TutorNote, difficulty_for_student

    student = get_object_or_404(PlatformUser, pk=pk, role='student')

    in_group = StudentGroup.objects.filter(
        teacher=request.user, students=student).exists()
    if not in_group and not request.user.is_staff:
        raise PermissionDenied

    # Заметка репетитора — сохраняется без перезагрузки, но и обычную
    # отправку формы принимаем: без JavaScript экран обязан работать.
    if request.method == 'POST':
        text = (request.POST.get('note') or '').strip()
        TutorNote.objects.update_or_create(
            tutor=request.user, student=student, defaults={'text': text})
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        return redirect('teacher:student_progress', pk=student.pk)

    profile = getattr(student, 'profile', None)
    note = TutorNote.objects.filter(tutor=request.user,
                                    student=student).first()

    # ⚠️ ДВА ЧИСЛА В КАЖДОЙ КАРТОЧКЕ: по всему сайту и по работам ЭТОГО
    # репетитора. Игра не входит ни в одно из них (поправка 3 владельца).
    open_pair = stats_module.accuracy_pair(student, tutor=request.user,
                                           kind='open')
    test_pair = stats_module.accuracy_pair(student, tutor=request.user,
                                           kind='test')

    return render(request, 'teacher/student_progress.html', {
        'student': student,
        'profile': profile,
        'note': note,
        'open_pair': open_pair,
        'test_pair': test_pair,
        # Формат «4,3 из 10» — русская запятая. Собираем строку ЗДЕСЬ:
        # шаблонный `floatformat` даёт запятую только при русской локали,
        # и полагаться на неё ради одного числа не стоит.
        'difficulty': _difficulty_label(difficulty_for_student(student)),
        # Две карточки прогресса: по задачам и по тестам. Устроены ОДИНАКОВО
        # и собираются одной функцией — различаются только числами.
        'progress_cards': [
            {'title': 'Прогресс по задачам',
             'data': stats_module.topic_progress(student, kind='open')},
            {'title': 'Прогресс по тестам',
             'data': stats_module.topic_progress(student, kind='test')},
        ],
        'works': _work_history(student, request.user),
        # Перенесено со второго экрана (см. решение стоп-гейта выше).
        'ranking': stats_module.strongest_weakest(student, 'all'),
        'calendar': stats_module.activity_calendar(student),
    })


def _difficulty_label(value):
    """«4,3 из 10» или None. Нет оценок — None, а не ноль."""
    if value is None:
        return None
    return ('%.1f' % value).replace('.', ',') + ' из 10'


def _work_history(student, tutor):
    """История работ ученика: семь столбцов (фаза 10.5).

    ⚠️ ОЦЕНКА — ПРОЦЕНТ, А НЕ СЫРЫЕ БАЛЛЫ. У разных работ разный максимум, и
    «12» за одну работу и «8» за другую несопоставимы ничем.

    ⚠️ СРОК СПРАШИВАЕМ ТОЛЬКО ЧЕРЕЗ `deadline_at`. Поле `due_at` устарело и
    не читается нигде — два поля уже давали видимый баг «без срока» у работы
    со сроком.
    """
    from decimal import Decimal

    from problems.assignment_rows import item_max_score
    from problems.models import Assignment, Submission

    works = (Assignment.objects.filter(author=tutor, students=student)
             .order_by('-id'))
    rows = []
    for work in works:
        subs = list(Submission.objects
                    .filter(student=student, assignment=work)
                    .select_related('feedback', 'problem_item',
                                    'problem_item__catalog_problem',
                                    'problem_item__custom_problem'))
        got = {'open': Decimal('0'), 'test': Decimal('0')}
        could = {'open': Decimal('0'), 'test': Decimal('0')}
        submitted_at = None
        for sub in subs:
            item = sub.problem_item
            if item is None:
                continue
            if sub.submitted_at and (submitted_at is None
                                     or sub.submitted_at > submitted_at):
                submitted_at = sub.submitted_at
            feedback = getattr(sub, 'feedback', None)
            if feedback is None or feedback.score is None:
                continue
            key = 'test' if item.is_test else 'open'
            got[key] += Decimal(str(feedback.score))
            could[key] += item_max_score(item)

        def share(key):
            return (int(round(float(got[key] / could[key]) * 100))
                    if could[key] else None)

        total_got = got['open'] + got['test']
        total_could = could['open'] + could['test']
        rows.append({
            'work': work,
            'is_exam': work.is_exam,
            'open_percent': share('open'),
            'test_percent': share('test'),
            'mark': (int(round(float(total_got / total_could) * 100))
                     if total_could else None),
            'submitted_at': submitted_at,
            'deadline': work.deadline_at,
            'not_submitted': submitted_at is None,
        })
    return rows


# ---------------------------------------------------------------------------
# Сессия 2 Этапа Е — Конструктор домашек
# ---------------------------------------------------------------------------

_RX_DISPLAY = re.compile(r'\$\$.*?\$\$|\\\[.*?\\\]', re.DOTALL)
_RX_INLINE  = re.compile(r'\$[^$\n]+?\$|\\\(.*?\\\)', re.DOTALL)
_RX_CMD     = re.compile(r'\\[a-zA-Z]+\*?(?:\{[^}]*\})?')
_RX_SPACE   = re.compile(r'\s+')


def _strip_latex(text):
    text = _RX_DISPLAY.sub('', text)
    text = _RX_INLINE.sub('', text)
    text = _RX_CMD.sub('', text)
    return _RX_SPACE.sub(' ', text).strip()


@teacher_required
def assignment_create(request):
    """Конструктор домашки. Отбор задач — общий модуль `teacher/picker.py`."""
    from problems.models import Assignment, StudentGroup

    from .picker import create_items, parse_cart, picker_context

    if request.method == 'POST':
        title = request.POST.get('name', '').strip()
        deadline_str = request.POST.get('deadline', '').strip()
        group_ids = request.POST.getlist('groups')
        keys, catalog_ids, custom_ids = parse_cart(
            request.POST.get('problem_ids'))

        if not title:
            messages.error(request, 'Укажите название домашки.')
            return redirect('teacher:assignment_create')
        if not (catalog_ids or custom_ids):
            messages.error(request, 'Добавьте хотя бы одну задачу.')
            return redirect('teacher:assignment_create')
        if not group_ids:
            messages.error(request, 'Выберите хотя бы одну группу.')
            return redirect('teacher:assignment_create')

        import datetime

        from django.utils import timezone

        deadline = None
        if deadline_str:
            try:
                deadline = datetime.datetime.fromisoformat(deadline_str)
                if timezone.is_naive(deadline):
                    deadline = timezone.make_aware(deadline)
            except ValueError:
                deadline = None

        groups = list(StudentGroup.objects.filter(pk__in=group_ids,
                                                  teacher=request.user))

        assignment = Assignment.objects.create(
            name=title,
            deadline=deadline,
            author=request.user,
            # Домашка привязывается к группе: без этого вкладка «Группы»
            # её не увидит, а вся работа с группой живёт именно там.
            # Если выбрано несколько групп — берём первую, остальные всё
            # равно получают домашку через список учеников.
            group=groups[0] if groups else None,
            # ⚠️ Порядок задан репетитором словами («вторая задача — тест»)
            # → автоматическая перестановка «сначала тесты» отменяется
            # (правило фазы 4). Признак приезжает из подбора по описанию.
            manual_order=request.POST.get('manual_order') == '1',
        )
        create_items(assignment, request.user, keys, catalog_ids, custom_ids)

        for group in groups:
            assignment.students.add(*group.students.all())

        messages.success(request, f'Домашка «{title}» создана.')
        return redirect('teacher:dashboard')

    from problems.models import SavedProblem

    saved = [item.catalog_problem for item in
             SavedProblem.objects.filter(owner=request.user, is_deleted=False,
                                         catalog_problem__isnull=False)
             .select_related('catalog_problem')]

    context = picker_context(request)
    context.update({
        'groups': StudentGroup.objects.filter(
            teacher=request.user).prefetch_related('students'),
        'show_saved': True,
        'saved_problems': saved,
        'picker_reset_url': reverse('teacher:assignment_create'),
    })
    return render(request, 'teacher/assignment_create.html', context)


@teacher_required
def api_problem_detail(request, pk):
    from problems.models import Problem

    try:
        problem = Problem.objects.prefetch_related('topics', 'parts', 'source_references__source').get(pk=pk)
    except Problem.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    d = problem.difficulty or 0
    parts = [
        {
            'label':  part.label,
            'text':   part.statement,
            'points': float(part.points) if part.points is not None else None,
        }
        for part in problem.parts.all()
    ]
    topics  = list(problem.topics.values_list('name', flat=True))
    sources = [ref.source.name for ref in problem.source_references.select_related('source').all()]

    return JsonResponse({
        'id':             problem.pk,
        'title':          problem.title or f'Задача #{problem.pk}',
        'statement':      problem.statement,
        'parts':          parts,
        'difficulty':     d,
        'difficulty_str': '★' * d + '☆' * (5 - d),
        'topics':         topics,
        'problem_type':   problem.problem_type,
        'has_solution':   bool(problem.solution),
        'sources':        sources,
    })


@teacher_required
@require_POST
def api_assignment_add_problem(request, pk):
    from problems.models import Assignment, Problem

    assignment = get_object_or_404(Assignment, pk=pk, author=request.user)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    problem_id = data.get('problem_id')
    if not problem_id:
        return JsonResponse({'error': 'problem_id required'}, status=400)

    problem = get_object_or_404(Problem, pk=problem_id)
    assignment.problems.add(problem)

    return JsonResponse({'ok': True, 'problem_id': problem.pk, 'assignment_id': assignment.pk})


# ---------------------------------------------------------------------------
# устарело, удалить после сессии 5
# Старые адреса проверки решений. Ведут на новые (внутри группы). Оставлены
# редиректом, а не удалены, чтобы не сломать закладки и ссылки в письмах.
# ---------------------------------------------------------------------------

@teacher_required
def legacy_assignment_detail(request, pk):
    """устарело, удалить после сессии 5 → teacher:group_submissions"""
    from problems.models import Assignment

    assignment = get_object_or_404(Assignment, pk=pk)
    if assignment.group_id:
        return redirect('teacher:group_submissions',
                        group_id=assignment.group_id, assignment_id=pk)
    # Задание вне группы (выдано до появления групп) — показываем как раньше.
    return assignment_detail(request, pk)


@teacher_required
def legacy_review_submission(request, pk):
    """устарело, удалить после сессии 5 → teacher:group_review_submission"""
    from problems.models import Submission

    submission = get_object_or_404(Submission, pk=pk)
    group_id = submission.assignment.group_id
    if group_id:
        return redirect('teacher:group_review_submission',
                        group_id=group_id, submission_id=pk)
    return review_submission(request, pk)


@tutor_required
def styleguide(request):
    """Демонстрация набора деталей интерфейса (_kit.html).

    Нужна для приёмки владельцем и для самопроверки: все повторяющиеся
    элементы кабинета видны рядом и переключаются вместе с темой сайта.
    """
    return render(request, 'teacher/styleguide.html')
