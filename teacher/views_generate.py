"""
Подбор домашки по описанию — три шага на одном адресе.

  1. ЗАПРОС      — описание словами + параметры;
  2. СТОП-ГЕЙТ   — показываем, ЧТО НАШЛОСЬ, и даём поправить ДО сборки;
  3. РЕЗУЛЬТАТ   — найденные задачи, их можно убрать, заменить, добавить
                   свои и отправить в обычный конструктор домашки.

⚠️ СТОП-ГЕЙТ ПОКАЗЫВАЕТ ЗАДАЧИ, А НЕ ТЕМЫ. Раньше на нём стояли темы,
выбранные моделью, — а проверить их репетитор не может: нашей таксономии он
не знает, и именно там пряталась ошибка с КТВ («альтернативное название
КПВ» выглядит правдоподобно ровно до того момента, как увидишь найденное).
Теперь на экране: строка СЛОВАМИ РЕПЕТИТОРА, названия двух-трёх найденных
задач и пометка уверенности.

⚠️ ПОВТОРНЫЙ ПОИСК ПО ОДНОЙ СТРОКЕ БЕСПЛАТЕН И НЕ ХОДИТ К МОДЕЛИ. Это самый
частый сценарий: «нашлись про производственные возможности, а надо про
торговые» — поправил формулировку, переискал. Платить за это второй раз
не за что.

Обращение к модели ровно одно — на шаге 2. Всё остальное ходит в свой банк.
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
        context['previews'] = hw_generator.preview_rows(
            plan['rows'], has_solution=form['has_solution'])
        return render(request, 'teacher/generate.html', context)

    if action == 'research':
        # Поправили формулировку строки и переискали. К модели НЕ ходим.
        rows = _read_plan(request)
        if not rows:
            messages.error(request, 'В плане не осталось ни одной строки.')
            context['step'] = 'ask'
            return render(request, 'teacher/generate.html', context)
        context.update(step='plan', plan_rows=rows)
        context['previews'] = hw_generator.preview_rows(
            rows, has_solution=form['has_solution'])
        messages.success(request, 'Переискал по вашим формулировкам — '
                                  'обращения к модели не потребовалось.')
        return render(request, 'teacher/generate.html', context)

    if action in ('search', 'replace'):
        rows = _read_plan(request)
        if not rows:
            messages.error(request, 'В плане не осталось ни одной строки.')
            context['step'] = 'ask'
            return render(request, 'teacher/generate.html', context)

        exclude = _read_ids(request, 'exclude_ids')
        found, short = hw_generator.find_problems(
            rows, has_solution=form['has_solution'], exclude=exclude)
        cards = [hw_generator.problem_card(item['problem'],
                                           item['confidence'],
                                           item.get('how', ''))
                 for item in found]
        for card, item in zip(cards, found):
            card['row'] = item['row']
            card['row_label'] = rows[item['row']]['label']
        context.update(step='result', plan_rows=rows, results=cards,
                       empty_rows=short, exclude_ids=exclude,
                       far_count=sum(1 for c in cards
                                     if c['confidence'] == 'far'))
        # ⚠️ Предупреждаем только о НАСТОЯЩЕМ недоборе. Он теперь редкость:
        # квота добирается из общего поиска, а не оставляет дыру.
        for gap in short:
            messages.warning(
                request,
                'По строке «%s» в банке не нашлось задач: %d. Поправьте '
                'формулировку и подберите ещё раз.'
                % (gap['label'], gap['missing']))
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
    """План со стоп-гейта — репетитор мог его поправить.

    Ведущее поле теперь `row_query` (формулировка строки), а не тема:
    тема стала подсказкой ранжированию и может быть пустой, а вот без
    формулировки искать нечего.
    """
    queries = request.POST.getlist('row_query')
    labels = request.POST.getlist('row_label')
    topics = request.POST.getlist('row_topic')
    difficulties = request.POST.getlist('row_difficulty')
    counts = request.POST.getlist('row_count')
    keep = set(request.POST.getlist('row_keep'))

    def at(values, index, default=''):
        return values[index] if index < len(values) else default

    rows = []
    for index, query in enumerate(queries):
        if str(index) not in keep:
            continue
        query = (query or '').strip()
        if not query:
            continue
        try:
            difficulty = max(1, min(5, int(at(difficulties, index, '3'))))
            count = max(1, min(hw_generator.MAX_PROBLEMS,
                               int(at(counts, index, '1'))))
        except ValueError:
            continue
        rows.append({'query': query,
                     'label': (at(labels, index) or query).strip(),
                     'topic': at(topics, index).strip(),
                     'difficulty': difficulty, 'count': count})
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
