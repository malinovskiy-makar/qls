"""
Редактор своей задачи репетитора (Фазы 17–20).

Одна форма на всё: открытая задача, тест трёх подвидов, решалка, график.
Разводить их по трём страницам смысла нет — репетитор в момент набора ещё
не всегда знает, чем задача кончится, а переключение подвида не должно
терять набранный текст.
"""
import json

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from problems.models_platform import (
    CustomProblem,
    CustomProblemOption,
    SavedFolder,
    SavedGraph,
    SolutionVisibility,
)

from .access import tutor_required


def _canonical_topics():
    """21 каноническая тема. В базе тем 849 (историческое наследие импортов),
    и вываливать их все в выпадающий список нельзя."""
    from problems.management.commands.apply_topic_mapping import CANONICAL
    from problems.models import Topic

    topics = list(Topic.objects.filter(name__in=CANONICAL))
    return sorted(topics, key=lambda t: CANONICAL.index(t.name))


def _parse_options(request):
    """Собирает варианты ответа из формы.

    Поля приходят параллельными списками: option_text[] и отдельные
    флажки option_correct_<индекс>. Порядок = порядок в форме (стрелки
    вверх/вниз двигают строки прямо в DOM).
    """
    texts = request.POST.getlist('option_text')
    options = []
    for index, text in enumerate(texts):
        text = (text or '').strip()
        if not text:
            continue
        options.append({
            'text': text,
            'is_correct': request.POST.get(f'option_correct_{index}') == 'on',
            'order': len(options),
        })
    return options


def _validate(kind, statement, correct_answer, options):
    """Проверки формы. Возвращает список человеческих сообщений.

    Ошибки показываем НА ФОРМЕ, а не 500-й страницей: репетитор не должен
    гадать, что именно не понравилось, и терять набранный текст.
    """
    errors = []
    if not statement.strip():
        errors.append('Условие задачи не может быть пустым.')

    if kind == CustomProblem.Kind.OPEN:
        return errors

    if len(options) < 2:
        errors.append('У теста должно быть хотя бы два варианта ответа.')
        return errors

    correct = [o for o in options if o['is_correct']]
    if kind == CustomProblem.Kind.SINGLE and len(correct) != 1:
        errors.append('У теста «один верный вариант» должен быть ровно один '
                      f'правильный ответ (отмечено {len(correct)}).')
    if kind == CustomProblem.Kind.MULTIPLE and not correct:
        errors.append('У теста «несколько верных» надо отметить хотя бы один '
                      'правильный вариант.')
    if kind == CustomProblem.Kind.TF and len(correct) != 1:
        errors.append('У данетки правильным должен быть ровно один вариант.')
    return errors


def _parse_steps(raw):
    """Шаги решения приходят JSON-строкой из формы.

    Структура шагов нужна для будущей ИИ-проверки решения: свободный текст
    она разбирает заметно хуже, чем список «что сделали → что получилось».
    Для репетитора шаги НЕОБЯЗАТЕЛЬНЫ — свободный текст тоже принимается.
    """
    if not raw:
        return None
    try:
        steps = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(steps, list):
        return None
    cleaned = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        text = (step.get('text') or '').strip()
        result = (step.get('result') or '').strip()
        if text or result:
            cleaned.append({'text': text, 'result': result})
    return cleaned or None


@tutor_required
def problem_form(request, pk=None):
    problem = None
    if pk is not None:
        problem = get_object_or_404(CustomProblem, pk=pk,
                                    owner=request.user, is_deleted=False)

    errors = []
    if request.method == 'POST':
        kind = request.POST.get('kind') or CustomProblem.Kind.OPEN
        if kind not in dict(CustomProblem.Kind.choices):
            kind = CustomProblem.Kind.OPEN
        statement = request.POST.get('statement') or ''
        correct_answer = (request.POST.get('correct_answer') or '').strip()
        options = _parse_options(request)
        errors = _validate(kind, statement, correct_answer, options)

        if not errors:
            tolerance = (request.POST.get('answer_tolerance') or '0').strip()
            tolerance = tolerance.replace(',', '.')
            try:
                float(tolerance)
            except ValueError:
                tolerance = '0'

            difficulty = (request.POST.get('difficulty') or '').strip()
            topic_id = (request.POST.get('topic') or '').strip()

            fields = {
                'title': (request.POST.get('title') or '').strip(),
                'statement': statement,
                'kind': kind,
                'correct_answer': correct_answer,
                'answer_tolerance': tolerance,
                'solution': request.POST.get('solution') or '',
                'solution_steps': _parse_steps(
                    request.POST.get('solution_steps')),
                'difficulty': int(difficulty) if difficulty.isdigit() else None,
                'topic_id': int(topic_id) if topic_id.isdigit() else None,
            }

            if problem is None:
                problem = CustomProblem.objects.create(owner=request.user,
                                                       **fields)
            else:
                for name, value in fields.items():
                    setattr(problem, name, value)
                problem.save()

            # Варианты переписываем целиком: сопоставлять старые с новыми
            # по порядку — верный способ незаметно переставить правильный
            # ответ, если репетитор двигал строки.
            problem.options.all().delete()
            for option in options:
                CustomProblemOption.objects.create(problem=problem, **option)

            messages.success(request, 'Задача сохранена.')
            if request.POST.get('to_cart'):
                # Возврат в ТОТ конструктор, откуда пришли — домашки или
                # контрольной: задача сразу ляжет в собираемую корзину (та
                # же вкладка, sessionStorage жив). Раньше адрес возврата был
                # прибит к домашке, и своя задача в контрольную не попадала.
                back = _safe_return(request.POST.get('return_to'))
                joiner = '&' if '?' in back else '?'
                return redirect('%s%sadd_custom=%d'
                                % (back, joiner, problem.pk))
            return redirect('teacher:problem_edit', pk=problem.pk)

    # Сохранённые графики — для модального окна «Добавить график».
    graphs = list(SavedGraph.objects.filter(owner=request.user,
                                            is_deleted=False)
                  .select_related('folder'))
    folders = list(SavedFolder.objects.filter(owner=request.user,
                                              kind=SavedFolder.Kind.GRAPHS))
    graph_groups = [{'folder': f,
                     'graphs': [g for g in graphs if g.folder_id == f.pk]}
                    for f in folders]
    graph_groups.append({'folder': None,
                         'graphs': [g for g in graphs if g.folder_id is None]})

    # Значения формы собираем ЗДЕСЬ, а не в шаблоне: цепочка вида
    # `posted.title|default:problem.title` падает, когда задачи ещё нет
    # (Django поднимает VariableDoesNotExist на аргументе фильтра).
    def value(name, fallback=''):
        if request.method == 'POST':
            return request.POST.get(name, '')
        if problem is not None:
            return getattr(problem, name, fallback)
        return fallback

    form = {
        'title': value('title'),
        'statement': value('statement'),
        'kind': value('kind', CustomProblem.Kind.OPEN)
        or CustomProblem.Kind.OPEN,
        'correct_answer': value('correct_answer'),
        'answer_tolerance': value('answer_tolerance', '0') or '0',
        'solution': value('solution'),
        'topic_id': int(request.POST['topic'])
        if request.method == 'POST' and (request.POST.get('topic') or '').isdigit()
        else (problem.topic_id if problem else None),
        'difficulty': int(request.POST['difficulty'])
        if request.method == 'POST' and (request.POST.get('difficulty') or '').isdigit()
        else (problem.difficulty if problem else None),
        'solution_steps': json.dumps(problem.solution_steps, ensure_ascii=False)
        if problem is not None and problem.solution_steps else '',
    }

    if request.method == 'POST':
        shown_options = _parse_options(request)
    elif problem is not None:
        shown_options = [{'text': o.text, 'is_correct': o.is_correct}
                         for o in problem.options.all()]
    else:
        shown_options = []

    return render(request, 'platform/problem_form.html', {
        'problem': problem,
        'form': form,
        'options': shown_options,
        'errors': errors,
        'topics': _canonical_topics(),
        'difficulties': range(1, 6),
        'kinds': CustomProblem.Kind.choices,
        'graph_groups': graph_groups,
        'to_cart': request.GET.get('to_cart') or request.POST.get('to_cart'),
        'return_to': _safe_return(request.GET.get('return_to')
                                  or request.POST.get('return_to')),
        'solution_visibility': SolutionVisibility.choices,
    })


def _safe_return(value):
    """Куда вернуться после «Сохранить и в корзину».

    ⚠️ Адрес приходит из строки запроса, поэтому проверяем: только свой
    путь внутри `/teacher/`. Иначе это открытый редирект — ссылку с чужим
    адресом можно подсунуть репетитору.
    """
    default = '/teacher/assignment/create/'
    value = (value or '').strip()
    if not value.startswith('/teacher/') or value.startswith('//'):
        return default
    return value


@tutor_required
def problem_list(request):
    """Свои задачи репетитора — чтобы их можно было найти и поправить."""
    problems = (CustomProblem.objects
                .filter(owner=request.user, is_deleted=False)
                .select_related('topic')
                .prefetch_related('options'))
    return render(request, 'platform/problem_list.html',
                  {'problems': problems})
