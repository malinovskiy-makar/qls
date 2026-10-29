# -*- coding: utf-8 -*-
"""Онбординг после регистрации — `/welcome/` (решения владельца 29.10.2026).

Ученик: «Кто вы?» → «Класс и уровень» → «Олимпиада» → «Город и школа» → «План
готов». Преподаватель: «Кто вы?» → «Где и кого вы учите?» → «Первая группа».

⚠️ ВСЕ ШАГИ ОБЯЗАТЕЛЬНЫЕ, И ПРОПУСК ЗАПРЕЩЁН НА СЕРВЕРЕ. Шаг открывается, только
если в ПРОФИЛЕ уже есть ответы всех шагов перед ним; иначе — редирект на первый
незаполненный. Кнопка «Дальше», неактивная до выбора, — удобство, а не защита.

⚠️ ОТВЕТЫ ПИШУТСЯ В ПРОФИЛЬ ПОСЛЕ КАЖДОГО ШАГА. Старый аккаунт видит свои ответы
выбранными заранее и просто жмёт «Дальше»: отдельного «с возвращением» нет.

⚠️ ЭКРАН = ЗАГОЛОВОК + ЭЛЕМЕНТЫ УПРАВЛЕНИЯ (решение 29.10.2026). Текст на шагах
только там, где без него нельзя выбрать (`LEVEL_HINTS`), и где его требует закон
(сноска про Instagram). Сторож — `problems/tests/test_onboarding.py`.

`onboarded_at` ставится: ученику — после «Города и школы», преподавателю — после
«Где и кого вы учите?» (группа — действие, а не вопрос).
"""
import hashlib
import random
from urllib.parse import urlsplit

from django import forms
from django.contrib.auth.views import redirect_to_login
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from problems import email_codes
from problems.models_platform import UserProfile
from problems.redirects import is_safe

#: Сохранённый `next` онбординга (свой адрес, проверенный `is_safe`).
NEXT_KEY = 'onboarding_next'
#: Шаги, подтверждённые в ЭТОМ проходе: по ним `/welcome/` выбирает текущий шаг.
DONE_KEY = 'onboarding_done'

STUDENT_STEPS = ('role', 'grade', 'olympiad', 'place')
TUTOR_STEPS = ('role', 'teach', 'group')

TITLES = {
    'role': 'Кто вы?',
    'grade': 'Класс и уровень',
    'olympiad': 'Олимпиада',
    'place': 'Город и школа',
    'teach': 'Где и кого вы учите?',
    'group': 'Первая группа',
}

ROLE_CHOICES = (('student', 'Ученик'), ('tutor', 'Преподаватель'))
#: Короткие подписи сегмента класса. Коды — ровно коды профиля (решение владельца
#: 29.10.2026 «как в профиле»): `le7 · 8 · 9 · 10 · 11 · none`.
GRADE_SHORT = {'le7': '≤7', 'none': 'Не школьник'}

#: Сложность задач «Плана» по уровню (шкала `Problem.difficulty` 1–5).
DIFFICULTY_BY_LEVEL = {'novice': (1, 2), 'basic': (2, 3), 'region': (3, 4), 'final': (4, 5)}
PLAN_TASKS = 3

#: «Посадочные» адреса не считаются сохранённым `next`: регистрация без `next`
#: ведёт на `/profile/?welcome=1`, вход — в кабинет роли. После анкеты такой
#: человек видит «План готов», а не страницу, куда его отправили по умолчанию.
LANDING_PATHS = ('/', '/student/', '/teacher/')
LANDING_PREFIXES = ('/profile/', '/welcome/')


# ── Формы шагов ────────────────────────────────────────────────────────────

class RoleForm(forms.Form):
    role = forms.ChoiceField(choices=ROLE_CHOICES)


class GradeForm(forms.Form):
    grade = forms.ChoiceField(choices=UserProfile.Grade.choices)
    level = forms.ChoiceField(choices=UserProfile.Level.choices)


class OlympiadForm(forms.Form):
    main_olympiad = forms.ChoiceField(choices=UserProfile.MAIN_OLYMPIADS)
    source_channel = forms.ChoiceField(choices=UserProfile.SourceChannel.choices)


class PlaceForm(forms.Form):
    city = forms.CharField(max_length=120)
    school = forms.CharField(max_length=200)


class TeachForm(forms.Form):
    teach_places = forms.MultipleChoiceField(choices=UserProfile.TEACH_PLACES)
    teach_grades = forms.MultipleChoiceField(choices=UserProfile.TEACH_GRADES)


class GroupForm(forms.Form):
    KINDS = (('group', 'Группа'), ('individual', 'Индивидуально'))
    name = forms.CharField(max_length=100)
    kind = forms.ChoiceField(choices=KINDS)


FORMS = {'role': RoleForm, 'grade': GradeForm, 'olympiad': OlympiadForm,
         'place': PlaceForm, 'teach': TeachForm}


# ── Что заполнено ──────────────────────────────────────────────────────────

def _known(value, choices):
    return value in {code for code, _label in choices}


def step_filled(profile, step):
    """Есть ли в профиле ответ шага. Источник правды — профиль, не сессия."""
    if step == 'role':
        return profile.role in ('student', 'tutor')
    if step == 'grade':
        return (_known(profile.grade, UserProfile.Grade.choices)
                and _known(profile.level, UserProfile.Level.choices))
    if step == 'olympiad':
        return (_known(profile.main_olympiad, UserProfile.MAIN_OLYMPIADS)
                and _known(profile.source_channel, UserProfile.SourceChannel.choices))
    if step == 'place':
        return bool(profile.city.strip() and profile.school.strip())
    if step == 'teach':
        return bool(profile.teach_places and profile.teach_grades)
    return True                               # «Первая группа» — действие, не ответ


def steps_for(profile):
    return TUTOR_STEPS if profile.role == 'tutor' else STUDENT_STEPS


def _initial(profile, step):
    """Ответы профиля для предвыбора. Неизвестный код — как пусто."""
    names = {'role': ('role',), 'grade': ('grade', 'level'),
             'olympiad': ('main_olympiad', 'source_channel'), 'place': ('city', 'school'),
             'teach': ('teach_places', 'teach_grades')}[step]
    initial = {name: getattr(profile, name) for name in names}
    if step == 'role' and profile.role not in ('student', 'tutor'):
        initial['role'] = ''
    return initial


# ── Служебное ──────────────────────────────────────────────────────────────

def _profile(user):
    profile, _created = UserProfile.objects.get_or_create(user=user)
    return profile


def needs_service_email(user):
    """Аккаунт создан через VK ID / Яндекс ID и почта ещё не подтверждена.

    Почта обязательна только таким аккаунтам (решение 26.10.2026): старых без
    почты не блокируем.
    """
    if not email_codes.mail_enabled() or email_codes.has_verified_email(user):
        return False
    return user.social_accounts.filter(created_user=True).exists()


def is_landing(target):
    path = urlsplit(target).path
    return path in LANDING_PATHS or path.startswith(LANDING_PREFIXES)


def _remember_next(request):
    target = request.GET.get('next') or ''
    if target and is_safe(request, target) and not is_landing(target):
        request.session[NEXT_KEY] = target


def _done(request):
    return list(request.session.get(DONE_KEY) or [])


def _mark_done(request, step):
    done = _done(request)
    if step not in done:
        done.append(step)
    request.session[DONE_KEY] = done


def _finish_target(request, default):
    """Конец анкеты: сохранённый `next` или экран по умолчанию."""
    request.session.pop(DONE_KEY, None)
    return request.session.pop(NEXT_KEY, None) or default


def _guard(request):
    """Вошёл? Почта аккаунта из сервиса есть? Иначе — куда увести."""
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path(), '/login/')
    if needs_service_email(request.user):
        return redirect('%s?next=%s' % (reverse('account_email'), reverse('onboarding')))
    return None


def _frame(profile, step, **extra):
    """Общий контекст каркаса шага: заголовок, полоска, «Назад»."""
    steps = steps_for(profile)
    index = steps.index(step)
    context = {
        'step': step,
        'title': TITLES[step],
        'segments': [i <= index for i in range(len(steps))],
        'back_url': (reverse('onboarding_step', args=[steps[index - 1]]) if index else ''),
        'seo_noindex': True,
    }
    context.update(extra)
    return context


# ── Адреса ─────────────────────────────────────────────────────────────────

@require_http_methods(['GET', 'HEAD'])
def entry(request):
    """`/welcome/`: сам выбирает текущий шаг."""
    stop = _guard(request)
    if stop:
        return stop
    _remember_next(request)
    profile = _profile(request.user)
    if profile.onboarded_at is not None:
        if profile.role == 'tutor':
            return redirect(_finish_target(request, '/teacher/'))
        return redirect(_finish_target(request, reverse('onboarding_plan')))
    done = _done(request)
    for name in steps_for(profile):
        if name not in done or not step_filled(profile, name):
            return redirect('onboarding_step', step=name)
    return redirect('onboarding_step', step=steps_for(profile)[0])


@require_http_methods(['GET', 'HEAD', 'POST'])
def step(request, step):
    stop = _guard(request)
    if stop:
        return stop
    profile = _profile(request.user)
    steps = steps_for(profile)
    if step not in steps:
        if step in STUDENT_STEPS + TUTOR_STEPS:
            return redirect('onboarding')
        raise Http404
    # Пропуск запрещён: шаг открывается, только когда ответы всех шагов до него есть.
    for earlier in steps[:steps.index(step)]:
        if not step_filled(profile, earlier):
            return redirect('onboarding_step', step=earlier)
    if step == 'group':
        return _group_step(request, profile)

    form_class = FORMS[step]
    if request.method == 'POST':
        form = form_class(request.POST)
        if step == 'role' and form.is_valid():
            _check_role_change(profile, form)
        if form.is_valid():
            return _save_step(request, profile, step, form.cleaned_data)
    else:
        form = form_class(initial=_initial(profile, step))
    return render(request, 'onboarding/step.html', _frame(
        profile, step, form=form, choices=_choices(step, form)))


def _check_role_change(profile, form):
    """У кого есть свои группы, тот остаётся преподавателем: иначе он потерял бы
    кабинет с группами и работами учеников одним нажатием."""
    from problems.models import StudentGroup

    if (form.cleaned_data['role'] == 'student' and profile.role == 'tutor'
            and StudentGroup.objects.filter(teacher=profile.user).exists()):
        form.add_error('role', 'У вас есть группы, поэтому роль преподавателя остаётся.')


def _save_step(request, profile, step, data):
    if step == 'role':
        profile.role = data['role']
    elif step == 'grade':
        profile.grade, profile.level = data['grade'], data['level']
    elif step == 'olympiad':
        profile.main_olympiad = data['main_olympiad']
        profile.source_channel = data['source_channel']
    elif step == 'place':
        profile.city, profile.school = data['city'].strip(), data['school'].strip()
    elif step == 'teach':
        profile.teach_places = list(data['teach_places'])
        profile.teach_grades = list(data['teach_grades'])
    _mark_done(request, step)

    steps = steps_for(profile)
    final = {'tutor': 'teach'}.get(profile.role, 'place')
    if step == final and all(step_filled(profile, name) for name in steps):
        if profile.onboarded_at is None:
            profile.onboarded_at = timezone.now()
    # `save()` профиля сам подтягивает `User.role` под роль (models_platform).
    profile.save()

    if step == final and profile.onboarded_at is not None:
        if profile.role == 'tutor':
            return redirect('onboarding_step', step='group')
        return redirect(_finish_target(request, reverse('onboarding_plan')))
    return redirect('onboarding_step', step=steps[steps.index(step) + 1])


def _choices(step, form):
    """Варианты шага с отметкой «выбрано» — для плиток с `aria-pressed`."""

    def mark(name, choices, notes=None):
        value = form[name].value()
        chosen = set(value) if isinstance(value, (list, tuple)) else {value or ''}
        chosen = {str(code) for code in chosen}
        return [{'code': code, 'label': label, 'on': code in chosen,
                 'note': (notes or {}).get(code, '')} for code, label in choices]

    if step == 'role':
        return {'role': mark('role', ROLE_CHOICES)}
    if step == 'grade':
        grades = [(code, GRADE_SHORT.get(code, code)) for code, _label in UserProfile.Grade.choices]
        return {'grade': mark('grade', grades),
                'level': mark('level', UserProfile.Level.choices, UserProfile.LEVEL_HINTS)}
    if step == 'olympiad':
        return {'main_olympiad': mark('main_olympiad', UserProfile.MAIN_OLYMPIADS),
                'source_channel': mark('source_channel', UserProfile.SourceChannel.choices)}
    if step == 'teach':
        return {'teach_places': mark('teach_places', UserProfile.TEACH_PLACES),
                'teach_grades': mark('teach_grades', UserProfile.TEACH_GRADES)}
    return {}


# ── Преподаватель: первая группа ───────────────────────────────────────────

def _group_step(request, profile):
    """Группа создаётся той же моделью, что в кабинете (`StudentGroup`: код
    приглашения выдаёт её `save()`). Индивидуальное занятие — тоже без ученика:
    у нового преподавателя учеников ещё нет, человек придёт по коду."""
    from problems.models import StudentGroup

    created = None
    if request.method == 'POST':
        form = GroupForm(request.POST)
        if form.is_valid():
            created = StudentGroup.objects.create(
                name=form.cleaned_data['name'].strip(), teacher=request.user,
                kind=form.cleaned_data['kind'])
    else:
        form = GroupForm(initial={'kind': 'group'})
    kinds = [{'code': code, 'label': label, 'on': code == (form['kind'].value() or 'group')}
             for code, label in GroupForm.KINDS]
    done_url = request.session.get(NEXT_KEY) or '/teacher/'
    if created is not None:
        request.session.pop(NEXT_KEY, None)
        request.session.pop(DONE_KEY, None)
    return render(request, 'onboarding/group.html', _frame(
        profile, 'group', form=form, kinds=kinds, created=created, done_url=done_url))


# ── «План готов» ───────────────────────────────────────────────────────────

def plan_problems(profile, today=None):
    """Три видимые задачи под уровень; с решением — в приоритете.

    Набор детерминирован для человека и дня: зерно — номер пользователя и дата.
    """
    from catalog.filters import base_queryset

    low, high = DIFFICULTY_BY_LEVEL.get(profile.level, (1, 5))
    today = today or timezone.localdate()
    seed = int(hashlib.sha256(('%s:%s' % (profile.user_id, today)).encode()).hexdigest()[:12], 16)
    rng = random.Random(seed)
    visible = base_queryset('catalog').filter(difficulty__gte=low, difficulty__lte=high)
    with_solution = sorted(visible.exclude(solution='').values_list('pk', flat=True))
    rng.shuffle(with_solution)
    chosen = with_solution[:PLAN_TASKS]
    if len(chosen) < PLAN_TASKS:
        rest = sorted(visible.filter(solution='').values_list('pk', flat=True))
        rng.shuffle(rest)
        chosen += rest[:PLAN_TASKS - len(chosen)]
    by_pk = {p.pk: p for p in visible.filter(pk__in=chosen).prefetch_related('topics')}
    return [by_pk[pk] for pk in chosen if pk in by_pk]


def _task_rows(problems):
    from catalog.preview import looks_like_statement_cut
    from problems.sections import section_of

    rows = []
    for problem in problems:
        topic = next(iter(problem.topics.all()), None)
        title = problem.title.strip()
        if not title or looks_like_statement_cut(title, problem.statement):
            title = 'Задача: %s' % topic.name if topic else 'Задача'
        rows.append({'url': reverse('catalog:problem_detail', args=[problem.pk]),
                     'title': title, 'topic': topic.name if topic else '',
                     'section': section_of(topic.name) if topic else 'other',
                     'stars': range(problem.difficulty or 0)})
    return rows


def _vp_card(profile):
    """Карточка «Высшей пробы» — тем, кто её выбрал или учится в 9–11 классе."""
    from vp import config as vp_config
    from vp.visibility import visible_variants

    if profile.main_olympiad != 'hse' and profile.grade not in ('9', '10', '11'):
        return None
    variant = (visible_variants().filter(grade_band=profile.grade).order_by('order', 'pk').first()
               if profile.grade in ('9', '10', '11') else None)
    url = reverse('vp:intro', args=[variant.slug]) if variant else reverse('vp:variants')
    days = None
    kind, value = vp_config.TOUR_DATES.get(vp_config.CURRENT_TOUR, (None, None))
    if value:
        first_day = value[0]
        left = (first_day - timezone.localdate()).days
        days = left if left > 0 else None
    return {'url': url, 'tour': vp_config.CURRENT_TOUR, 'days': days}


def _chips(profile):
    chips = []
    if profile.grade:
        chips.append(profile.get_grade_display())
    if profile.level:
        chips.append(profile.get_level_display())
    if profile.main_olympiad:
        chips.append(profile.get_main_olympiad_display())
    if profile.city:
        chips.append(profile.city)
    return chips


@require_http_methods(['GET', 'HEAD'])
def plan(request):
    stop = _guard(request)
    if stop:
        return stop
    profile = _profile(request.user)
    if profile.onboarded_at is None:
        return redirect('onboarding')
    if profile.role == 'tutor':
        return redirect('/teacher/')
    tasks = _task_rows(plan_problems(profile))
    return render(request, 'onboarding/plan.html', {
        'title': 'План готов',
        'chips': _chips(profile),
        'tasks': tasks,
        'vp': _vp_card(profile),
        'daily_url': reverse('game:daily'),
        'start_url': tasks[0]['url'] if tasks else reverse('catalog:problem_list'),
        'seo_noindex': True,
    })

