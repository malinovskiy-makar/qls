"""
Подбор домашки по описанию — три шага на одном адресе.

  1. ЗАПРОС      — описание словами + параметры;
  2. СТОП-ГЕЙТ   — показываем, ЧТО поняли, и даём поправить ДО поиска;
  3. РЕЗУЛЬТАТ   — найденные задачи, их можно убрать, заменить, добавить
                   свои и отправить в обычный конструктор домашки.

⚠️ Стоп-гейт не украшение. Неверно понятый запрос иначе превращается в пять
бессмысленных поисков и подборку, которую репетитор всё равно выбросит.

Обращение к модели ровно одно — на шаге 2. Шаг 3 ходит только в свой банк.
"""
from django.contrib import messages
from django.shortcuts import redirect, render

from problems import hw_generator

from .access import tutor_required


@tutor_required
def assignment_generate(request):
    """Экран подбора. Шаг определяется тем, что пришло в POST."""
    context = {
        'available': hw_generator.is_available(),
        'reason': hw_generator.unavailable_reason(),
        'topics': hw_generator.canonical_topics(),
        'used_today': hw_generator.used_today(request.user),
        'daily_limit': hw_generator.daily_limit(),
        'step': 'ask',
        'form': {'count': 5, 'min_difficulty': 1, 'max_difficulty': 5,
                 'text': '', 'has_solution': False, 'topics': []},
    }

    if request.method != 'POST':
        return render(request, 'teacher/generate.html', context)

    form = _read_form(request)
    context['form'] = form
    action = request.POST.get('action') or 'parse'

    if action == 'parse':
        try:
            plan = hw_generator.parse_request(form['text'], form, request.user)
        except hw_generator.GeneratorUnavailable as error:
            messages.error(request, str(error))
            return render(request, 'teacher/generate.html', context)
        context.update(step='plan', plan_rows=plan['rows'],
                       note=plan['note'], usage=plan.get('usage'),
                       cached=plan.get('cached'))
        return render(request, 'teacher/generate.html', context)

    if action in ('search', 'replace'):
        rows = _read_plan(request)
        if not rows:
            messages.error(request, 'В плане не осталось ни одной строки.')
            context['step'] = 'ask'
            return render(request, 'teacher/generate.html', context)

        exclude = _read_ids(request, 'exclude_ids')
        found, empty = hw_generator.find_problems(
            rows, has_solution=form['has_solution'], exclude=exclude)
        context.update(step='result', plan_rows=rows, results=found,
                       empty_rows=empty, exclude_ids=exclude)
        if empty:
            for gap in empty:
                messages.warning(
                    request,
                    'По строке «%s» не хватило задач: %d. Поправьте тему или '
                    'сложность и подберите ещё раз.'
                    % (gap['topic'], gap['missing']))
        return render(request, 'teacher/generate.html', context)

    return redirect('teacher:assignment_generate')


def _read_form(request):
    def number(name, default, low, high):
        raw = (request.POST.get(name) or '').strip()
        try:
            return max(low, min(high, int(raw)))
        except ValueError:
            return default

    return {
        'text': (request.POST.get('text') or '').strip(),
        'count': number('count', 5, 1, hw_generator.MAX_PROBLEMS),
        'min_difficulty': number('min_difficulty', 1, 1, 5),
        'max_difficulty': number('max_difficulty', 5, 1, 5),
        'has_solution': request.POST.get('has_solution') == 'on',
        'topics': request.POST.getlist('topics'),
    }


def _read_plan(request):
    """План со стоп-гейта — репетитор мог его поправить."""
    topics = request.POST.getlist('row_topic')
    difficulties = request.POST.getlist('row_difficulty')
    counts = request.POST.getlist('row_count')
    queries = request.POST.getlist('row_query')
    keep = set(request.POST.getlist('row_keep'))

    rows = []
    for index, topic in enumerate(topics):
        if str(index) not in keep:
            continue
        try:
            difficulty = max(1, min(5, int(difficulties[index])))
            count = max(1, min(hw_generator.MAX_PROBLEMS, int(counts[index])))
        except (ValueError, IndexError):
            continue
        rows.append({'topic': topic, 'difficulty': difficulty,
                     'count': count,
                     'query': (queries[index] if index < len(queries)
                               else topic)})
    return rows


def _read_ids(request, name):
    return [int(value) for value in request.POST.getlist(name)
            if value.isdigit()]


# ---------------------------------------------------------------------------
# Часть D — экспорт задания в .tex и PDF
# ---------------------------------------------------------------------------

@tutor_required
def assignment_export(request, group_id, assignment_id):
    """Листок для печати: `.tex` всегда, PDF — где есть TeX Live.

    Два варианта одного задания: ученику (без ответов) и преподавателю
    (с ответами и решениями). Выбор — параметром `for`, формат — `fmt`.
    """
    from django.http import HttpResponse

    from problems import assignment_export as export

    from .access import group_assignment_or_404, own_group_or_404

    group = own_group_or_404(request.user, group_id)
    assignment = group_assignment_or_404(group, assignment_id)

    for_teacher = request.GET.get('for') == 'teacher'
    tex, skipped = export.build_tex(assignment, for_teacher=for_teacher)
    stem = _safe_stem(assignment.name) + ('-ответы' if for_teacher else '')

    if request.GET.get('fmt') == 'pdf':
        pdf, error = export.compile_pdf(tex)
        if pdf is None:
            # Прод без TeX Live — честно объясняем и отдаём .tex, а не 500.
            messages.warning(request, error)
            return _tex_response(tex, stem)
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = (
            'attachment; filename*=UTF-8\'\'%s.pdf'
            % _urlquote(stem))
        return response

    if skipped:
        messages.warning(
            request, 'Пропущено задач из-за испорченной разметки: %d. '
                     'Остальные в листок вошли.' % len(skipped))
    return _tex_response(tex, stem)


def _tex_response(tex, stem):
    from django.http import HttpResponse

    response = HttpResponse(tex, content_type='application/x-tex; charset=utf-8')
    response['Content-Disposition'] = (
        'attachment; filename*=UTF-8\'\'%s.tex' % _urlquote(stem))
    return response


def _safe_stem(name):
    import re

    stem = re.sub(r'[^\w\s\-]', '', name, flags=re.UNICODE).strip()
    stem = re.sub(r'\s+', '-', stem)
    return stem[:60] or 'работа'


def _urlquote(text):
    from urllib.parse import quote

    return quote(text)
