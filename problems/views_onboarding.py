# -*- coding: utf-8 -*-
"""Онбординг после регистрации — `/welcome/` (решения владельца 29.10.2026, раунд 2).

Эталон вида — макет `docs/design/onboarding_r2/` (снимки `shots/*.png`).

Ученик: «Кто вы?» → «В каком вы классе?» + «Ваш уровень» (один экран, два этапа) →
«К чему готовитесь?» → «Где вы учитесь?» (кроме «Уже не школьник») → «Откуда вы
узнали о Weconomics?» → [«Добавьте почту»] → сборка плана → «План готов».
Преподаватель: «Кто вы?» → «Где и кого вы учите?» → «Откуда вы узнали…» →
[«Добавьте почту»] → «Первая группа».

⚠️ ВСЕ ШАГИ ОБЯЗАТЕЛЬНЫЕ, И ПРОПУСК ЗАПРЕЩЁН НА СЕРВЕРЕ. Шаг открывается, только
если в ПРОФИЛЕ уже есть ответы всех шагов перед ним; иначе — редирект на первый
незаполненный. Кнопки и автопереход — удобство, а не защита. Исключение одно —
«Добавьте почту»: её можно отложить («Позже», решение 26.10 — старых без почты не
блокировать).

⚠️ ГДЕ ВЫБОР ОДИН — ПЕРЕХОД СРАЗУ ПО НАЖАТИЮ. Плитка такого шага — кнопка отправки
формы (`name=value`): работает и без скрипта, а скрипт только показывает галочку
250–300 мс и меняет экран без перезагрузки (`static/onboarding/onboarding.js`).

⚠️ ОТВЕТЫ ПИШУТСЯ В ПРОФИЛЬ ПОСЛЕ КАЖДОГО ШАГА. Старый аккаунт видит свои ответы
выбранными заранее. Новому человеку на «Кто вы?» не выбрано ничего (`_role_preset`).

⚠️ ЭКРАН = ЗАГОЛОВОК + ЭЛЕМЕНТЫ УПРАВЛЕНИЯ (решение 29.10.2026). Текст на шагах
только там, где без него нельзя выбрать (`LEVEL_HINTS`, вторая строка цели), и где
его требует закон (сноска про Instagram). Сторож — `problems/tests/test_onboarding.py`.

`onboarded_at` ставится после шага «Откуда узнали» (у обеих ролей).
"""
import hashlib
import random
from urllib.parse import urlencode, urlsplit

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
#: Строка «Ваш профиль», которую только что заполнили: мигает один раз.
FLASH_KEY = 'onboarding_flash'
#: «Добавьте почту» → «Позже»: в этот проход шаг больше не показывается.
EMAIL_LATER_KEY = 'onboarding_email_later'
#: Код приглашения, показанный на «Первой группе» до её создания.
INVITE_KEY = 'onboarding_invite'

TITLES = {
    'role': 'Кто вы?',
    'grade': 'В каком вы классе?',
    'level': 'Ваш уровень',
    'goals': 'К чему готовитесь?',
    'school': 'Где вы учитесь?',
    'source': 'Откуда вы узнали о Weconomics?',
    'email': 'Добавьте почту',
    'teach': 'Где и кого вы учите?',
    'group': 'Первая группа',
}
ALL_STEPS = tuple(name for name in TITLES if name != 'level')
#: Адреса раунда 1: ведут на начало, а не в 404 (закладки и открытые вкладки).
OLD_STEPS = ('olympiad', 'place')

ROLE_CHOICES = (('student', 'Ученик'), ('tutor', 'Преподаватель'))
#: Три чипа на плитке роли (макет `Role.png`).
#: Крупная цифра на плитке класса. `none` — отдельная пилюля «Уже не школьник».
GRADE_NUMBER = {'le7': '≤7', '8': '8', '9': '9', '10': '10', '11': '11'}
#: Сколько столбиков «лесенки» залито у уровня.
LEVEL_BARS = {'novice': 1, 'basic': 2, 'region': 3, 'final': 4}
#: Место преподавания — подписи плиток (макет `Teach1.png`) и короткие для карточки.
TEACH_PLACE_TILE = {'school': 'Школа', 'circle': 'Кружок или онлайн-школа',
                    'private': 'Частные занятия'}
TEACH_PLACE_SHORT = {'school': 'школа', 'circle': 'кружок', 'private': 'частные занятия'}

#: Сложность задач «Плана» по уровню (шкала `Problem.difficulty` 1–5).
DIFFICULTY_BY_LEVEL = {'novice': (1, 2), 'basic': (2, 3), 'region': (3, 4), 'final': (4, 5)}
PLAN_TASKS = 3
#: Пример запроса для карточки «Умный поиск»: человеческими словами.
SMART_QUERY = 'задача про монополию с налогом'

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


class LevelForm(forms.Form):
    level = forms.ChoiceField(choices=UserProfile.Level.choices)


class GoalsForm(forms.Form):
    goals = forms.MultipleChoiceField(choices=UserProfile.GOALS)

    def clean_goals(self):
        goals = list(dict.fromkeys(self.cleaned_data['goals']))
        if 'undecided' in goals and len(goals) > 1:
            raise forms.ValidationError('«Пока не решил» не сочетается с другими целями.')
        return goals


class SchoolForm(forms.Form):
    """Город и школа независимы (раунд 3): школа может быть из другого города.

    Город пуст, а школа — ровно одна школа справочника (по названию из подсказки) —
    город берётся из её записи. Так же делает скрипт при выборе подсказки; здесь —
    на случай, если скрипт не сработал.
    """

    city = forms.CharField(max_length=120, required=False)
    school = forms.CharField(max_length=200)

    def clean(self):
        data = super().clean()
        if data.get('school') and not (data.get('city') or '').strip():
            from django.db.models import Q

            from problems.models import School
            name = data['school'].strip()
            cities = set(School.objects.filter(is_active=True).filter(
                Q(short_name__iexact=name) | Q(short_name='', name__iexact=name))
                .exclude(city='').values_list('city', flat=True)[:2])
            if len(cities) == 1:
                data['city'] = cities.pop()
            else:
                self.add_error('city', 'Укажите город.')
        return data


class SourceForm(forms.Form):
    source_channel = forms.ChoiceField(choices=UserProfile.SourceChannel.choices)
    source_other = forms.CharField(max_length=120, required=False)


class TeachForm(forms.Form):
    teach_places = forms.MultipleChoiceField(choices=UserProfile.TEACH_PLACES)
    teach_grades = forms.MultipleChoiceField(choices=UserProfile.TEACH_GRADES)


class GroupForm(forms.Form):
    name = forms.CharField(max_length=100)


# ── Что заполнено ──────────────────────────────────────────────────────────

def _known(value, choices):
    return value in {code for code, _label in choices}


def _valid_goals(goals):
    known = {code for code, _label in UserProfile.GOALS}
    goals = [goal for goal in (goals or []) if goal in known]
    return bool(goals) and not ('undecided' in goals and len(goals) > 1)


def step_filled(profile, step):
    """Есть ли в профиле ответ шага. Источник правды — профиль, не сессия."""
    if step == 'role':
        return profile.role in ('student', 'tutor')
    if step == 'grade':
        return (_known(profile.grade, UserProfile.Grade.choices)
                and _known(profile.level, UserProfile.Level.choices))
    if step == 'goals':
        return _valid_goals(profile.goals)
    if step == 'school':
        return bool(profile.city.strip() and profile.school.strip())
    if step == 'source':
        return _known(profile.source_channel, UserProfile.SourceChannel.choices)
    if step == 'teach':
        return bool(profile.teach_places and profile.teach_grades)
    return True        # «Почта» откладывается, «Первая группа» — действие, а не ответ


def wants_email_step(request, user):
    """Шаг «Добавьте почту»: старому аккаунту без подтверждённой почты (решение
    раунда 2). Аккаунты из сервисов сюда не попадают: их почту требует `_guard`."""
    return (email_codes.mail_enabled() and not email_codes.has_verified_email(user)
            and not request.session.get(EMAIL_LATER_KEY))


def steps_for(request, profile):
    """Шаги этого человека — по роли и ответам. «Уже не школьник» — без «школы»."""
    if profile.role == 'tutor':
        steps = ['role', 'teach', 'source']
    else:
        steps = ['role', 'grade', 'goals']
        if profile.grade != 'none':
            steps.append('school')
        steps.append('source')
    if wants_email_step(request, profile.user):
        steps.append('email')
    if profile.role == 'tutor':
        steps.append('group')
    return steps


# ── Служебное ──────────────────────────────────────────────────────────────

def _profile(user):
    profile, _created = UserProfile.objects.get_or_create(user=user)
    return profile


def needs_service_email(user):
    """Аккаунт создан через VK ID / Яндекс ID и почта ещё не подтверждена.

    Почта обязательна только таким аккаунтам (решение 26.10.2026): старых без
    почты не блокируем — им шаг «Добавьте почту» с «Позже».
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


def _guard(request):
    """Вошёл? Почта аккаунта из сервиса есть? Иначе — куда увести."""
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path(), '/login/')
    if needs_service_email(request.user):
        return redirect('%s?next=%s' % (reverse('account_email'), reverse('onboarding')))
    return None


def _step_url(step, **query):
    url = reverse('onboarding_step', args=[step])
    return url + ('?' + urlencode(query) if query else '')


# ── Карточка «Ваш профиль» ─────────────────────────────────────────────────

def _display_name(user):
    full = ' '.join(part for part in (user.first_name, user.last_name) if part).strip()
    return full or user.username


def _initials(user):
    letters = [part[0] for part in (user.first_name, user.last_name) if part]
    return (''.join(letters) or user.username[:1]).upper()


def _goals_text(goals):
    labels = [UserProfile.GOAL_SHORT[g] for g in goals or [] if g in UserProfile.GOAL_SHORT]
    return ', '.join([labels[0]] + [label[0].lower() + label[1:] if label != 'ВсОШ' else label
                                    for label in labels[1:]]) if labels else ''


#: Родовое слово в начале названия школы пишется в карточке со строчной:
#: «Москва, школа № 57». Имя собственное («Интеллектуал») не трогаем.
SCHOOL_WORDS = ('Школа', 'Лицей', 'Гимназия', 'Колледж', 'Центр')


def _school_text(profile):
    city, school = profile.city.strip(), profile.school.strip()
    if not city:
        return ''
    if not school:
        return city
    if school.split(' ', 1)[0] in SCHOOL_WORDS:
        school = school[0].lower() + school[1:]
    return '%s, %s' % (city, school)


def _source_text(profile):
    if profile.source_channel == 'other' and profile.source_other.strip():
        return profile.source_other.strip()
    return profile.get_source_channel_display() if profile.source_channel else ''


def profile_rows(profile, current, flash=''):
    """Строки карточки «Ваш профиль»: (подпись, значение, текущая, только что заполнена)."""
    if profile.role == 'tutor':
        rows = [
            ('role', 'Роль', 'Преподаватель' if current != 'role' else ''),
            ('teach', 'Где', ', '.join(
                [TEACH_PLACE_SHORT[p] for p in profile.teach_places if p in TEACH_PLACE_SHORT]
            ).capitalize()),
            ('teach_grades', 'Классы', ', '.join(profile.teach_grades)),
            ('source', 'Откуда', _source_text(profile)),
            ('group', 'Группа', ''),
        ]
        now = {'teach': 'teach'}.get(current, current)
    else:
        grade = profile.get_grade_display() if profile.grade else ''
        rows = [
            ('role', 'Роль', 'Ученик' if profile.role == 'student' and current != 'role' else ''),
            ('grade', 'Класс', grade),
            ('level', 'Уровень', profile.get_level_display() if profile.level else ''),
            ('goals', 'Цели', _goals_text(profile.goals)),
        ]
        if profile.grade != 'none':
            rows.append(('school', 'Школа', _school_text(profile)))
        rows.append(('source', 'Откуда', _source_text(profile)))
        now = current
    return [{'key': key, 'label': label, 'value': value, 'now': key == now,
             'new': key == flash and bool(value)} for key, label, value in rows]


# ── Каркас шага ────────────────────────────────────────────────────────────

def _frame(request, profile, step, **extra):
    """Общий контекст: заголовок, прогресс «N из M», «Назад», карточка профиля."""
    steps = steps_for(request, profile)
    index = steps.index(step) if step in steps else 0
    stage = extra.pop('stage', step)
    flash = request.session.pop(FLASH_KEY, '')
    context = {
        'step': step,
        'stage': stage,
        'title': TITLES[stage],
        'step_n': index + 1,
        'step_total': len(steps),
        'progress': round(100 * index / len(steps)),
        'back_url': _step_url(steps[index - 1]) if index else '',
        'me_name': _display_name(profile.user),
        'me_initials': _initials(profile.user),
        'me_rows': profile_rows(profile, 'level' if stage == 'level' else step, flash),
        'seo_noindex': True,
    }
    context.update(extra)
    return context


def _role_preset(profile):
    """Роль подсвечена только у того, кто уже ответил о себе: у преподавателя (роль
    не бывает выставлена по умолчанию) или у ученика с ответами в профиле. Новый
    аккаунт (роль `student` по умолчанию, пустой профиль) не видит выбора заранее."""
    if profile.role == 'tutor':
        return 'tutor'
    if profile.role == 'student' and (profile.onboarded_at or profile.grade or profile.level
                                      or profile.goals or profile.source_channel):
        return 'student'
    return ''


# ── Адреса ─────────────────────────────────────────────────────────────────

@require_http_methods(['GET', 'HEAD'])
def entry(request):
    """`/welcome/`: сам выбирает текущий шаг."""
    stop = _guard(request)
    if stop:
        return stop
    _remember_next(request)
    profile = _profile(request.user)
    steps = steps_for(request, profile)
    if profile.onboarded_at is not None:
        if 'email' in steps and 'email' not in _done(request):
            return redirect('onboarding_step', step='email')
        if profile.role == 'tutor':
            return redirect(request.session.pop(NEXT_KEY, None) or '/teacher/')
        return redirect(_finish_url(request))
    done = _done(request)
    for name in steps:
        if name not in done or not step_filled(profile, name):
            return redirect('onboarding_step', step=name)
    return redirect('onboarding_step', step=steps[0])


@require_http_methods(['GET', 'HEAD', 'POST'])
def step(request, step):
    stop = _guard(request)
    if stop:
        return stop
    profile = _profile(request.user)
    steps = steps_for(request, profile)
    if step not in steps:
        if step in ALL_STEPS or step in OLD_STEPS:
            return redirect('onboarding')
        raise Http404
    # Пропуск запрещён: шаг открывается, только когда ответы всех шагов до него есть.
    for earlier in steps[:steps.index(step)]:
        if not step_filled(profile, earlier):
            return redirect('onboarding_step', step=earlier)
    handler = {'role': _role_step, 'grade': _grade_step, 'goals': _goals_step,
               'school': _school_step, 'source': _source_step, 'email': _email_step,
               'teach': _teach_step, 'group': _group_step}[step]
    return handler(request, profile)


def _render(request, profile, step, **extra):
    return render(request, 'onboarding/step.html', _frame(request, profile, step, **extra))


def _after(request, profile, step):
    """Куда дальше после сохранённого шага."""
    _mark_done(request, step)
    steps = steps_for(request, profile)
    if step == 'source':
        if all(step_filled(profile, name) for name in steps) and profile.onboarded_at is None:
            profile.onboarded_at = timezone.now()
            profile.save(update_fields=['onboarded_at'])
    if step in steps and steps.index(step) + 1 < len(steps):
        return redirect('onboarding_step', step=steps[steps.index(step) + 1])
    return redirect(_finish_url(request))


def _save(request, profile, flash, **fields):
    for name, value in fields.items():
        setattr(profile, name, value)
    # `save()` профиля сам подтягивает `User.role` под роль (models_platform).
    profile.save()
    request.session[FLASH_KEY] = flash


def _role_step(request, profile):
    from problems import signup_source
    from problems.models import StudentGroup
    from problems.models_platform import SignupSource

    form = RoleForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        role = form.cleaned_data['role']
        # У кого есть свои группы, тот остаётся преподавателем: иначе он потерял бы
        # кабинет с группами и работами учеников одним нажатием.
        if (role == 'student' and profile.role == 'tutor'
                and StudentGroup.objects.filter(teacher=profile.user).exists()):
            form.add_error('role', 'У вас есть группы, поэтому роль преподавателя остаётся.')
        else:
            _save(request, profile, 'role', role=role)
            signup_source.confirm_role(request, profile.user, SignupSource.Kind.TEACHER
                                       if role == 'tutor' else SignupSource.Kind.STUDENT)
            return _after(request, profile, 'role')
    chosen = request.POST.get('role') if request.method == 'POST' else _role_preset(profile)
    tiles = [{'code': code, 'label': label, 'on': code == chosen}
             for code, label in ROLE_CHOICES]
    return _render(request, profile, 'role', form=form, tiles=tiles)


def _grade_step(request, profile):
    """Один экран, два этапа: класс (плитки), затем уровень (плитки 2×2)."""
    if request.method == 'POST':
        if 'grade' in request.POST:
            form = GradeForm(request.POST)
            if form.is_valid():
                grade = form.cleaned_data['grade']
                _save(request, profile, 'grade', grade=grade)
                if 'level' not in request.POST:
                    return redirect('onboarding_step', step='grade')
        form = LevelForm(request.POST)
        if form.is_valid() and _known(profile.grade, UserProfile.Grade.choices):
            _save(request, profile, 'level', level=form.cleaned_data['level'])
            return _after(request, profile, 'grade')
        stage = 'level' if _known(profile.grade, UserProfile.Grade.choices) else 'grade'
    else:
        form = None
        changing = request.GET.get('change') == '1'
        stage = ('level' if _known(profile.grade, UserProfile.Grade.choices) and not changing
                 else 'grade')
    grades = [{'code': code, 'number': GRADE_NUMBER[code], 'on': code == profile.grade}
              for code, _label in UserProfile.Grade.choices if code in GRADE_NUMBER]
    levels = [{'code': code, 'label': label, 'hint': UserProfile.LEVEL_HINTS.get(code, ''),
               'bars': [i < LEVEL_BARS[code] for i in range(4)], 'on': code == profile.level}
              for code, label in UserProfile.Level.choices]
    return _render(request, profile, 'grade', stage=stage, form=form, grades=grades,
                   not_pupil_on=profile.grade == 'none', levels=levels,
                   picked=profile.get_grade_display() if profile.grade else '')


#: У всех пяти целей — логотип без плашки (решение владельца 29.10.2026, раунд 3):
#: олимпиады — свои логотипы (`olymp`: в тёмной теме под ними светлая подложка,
#: иначе чёрные буквы ВсОШ не видны), «Разобраться в экономике» — знак W
#: Weconomics, «Пока не решил» — веер из четырёх бледных логотипов.
_LOGOS = 'onboarding/logos/'
GOAL_PLATES = {
    'vsosh': {'logo': _LOGOS + 'vsosh_econ_top.png', 'olymp': True},
    'listed': {'logo': _LOGOS + 'vp_logo.png', 'olymp': True,
               'badges': (_LOGOS + 'ranepa_mark.png', _LOGOS + 'nes_mark.png')},
    'international': {'logo': _LOGOS + 'ieo_mark.png', 'olymp': True},
    'knowledge': {'logo': _LOGOS + 'weconomics_w.svg', 'mark': True},
    'undecided': {'fan': (_LOGOS + 'vsosh_econ_top.png', _LOGOS + 'vp_logo.png',
                          _LOGOS + 'ieo_mark.png', _LOGOS + 'ranepa_mark.png')},
}


def _goals_step(request, profile):
    form = GoalsForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        _save(request, profile, 'goals', goals=form.cleaned_data['goals'])
        return _after(request, profile, 'goals')
    chosen = set(request.POST.getlist('goals') if request.method == 'POST' else profile.goals)
    tiles = [dict(GOAL_PLATES[code], code=code, label=label, on=code in chosen,
                  note=UserProfile.GOAL_NOTES.get(code, ''), wide=code == 'undecided')
             for code, label in UserProfile.GOALS]
    return _render(request, profile, 'goals', form=form, tiles=tiles)


def _school_step(request, profile):
    form = SchoolForm(request.POST if request.method == 'POST' else None, initial={'city': profile.city, 'school': profile.school})
    if request.method == 'POST' and form.is_valid():
        _save(request, profile, 'school', city=form.cleaned_data['city'].strip(),
              school=form.cleaned_data['school'].strip())
        return _after(request, profile, 'school')
    return _render(request, profile, 'school', form=form)


def _source_step(request, profile):
    form = SourceForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        channel = form.cleaned_data['source_channel']
        other = form.cleaned_data['source_other'].strip() if channel == 'other' else ''
        _save(request, profile, 'source', source_channel=channel, source_other=other)
        return _after(request, profile, 'source')
    chosen = request.POST.get('source_channel') if request.method == 'POST' \
        else profile.source_channel
    pills = [{'code': code, 'label': label, 'on': code == chosen}
             for code, label in UserProfile.SourceChannel.choices]
    return _render(request, profile, 'source', form=form, pills=pills,
                   other_value=(request.POST.get('source_other', '') if request.method == 'POST'
                                else profile.source_other),
                   other_on=chosen == 'other')


def _email_step(request, profile):
    """«Добавьте почту»: адрес уходит на страницу «Почта» (код из письма там, логика
    Анича); «Позже» — дальше без почты, в этот проход шаг больше не встанет."""
    if request.method == 'POST' and request.POST.get('later'):
        request.session[EMAIL_LATER_KEY] = True
        _mark_done(request, 'email')
        if profile.role == 'tutor':
            return redirect('onboarding_step', step='group')
        return redirect(_finish_url(request))
    from legal import consent

    after = _step_url('group') if profile.role == 'tutor' else reverse('onboarding')
    # Согласие на рассылку едет скрытым полем: страница «Почта» иначе отозвала бы его.
    return _render(request, profile, 'email', email_action=reverse('account_email'),
                   email_next=after, email_keep_mail=consent.wants_mail(profile.user))


def _teach_step(request, profile):
    form = TeachForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        _save(request, profile, 'teach', teach_places=list(form.cleaned_data['teach_places']),
              teach_grades=list(form.cleaned_data['teach_grades']))
        return _after(request, profile, 'teach')
    if request.method == 'POST':
        places, grades = request.POST.getlist('teach_places'), request.POST.getlist('teach_grades')
    else:
        places, grades = profile.teach_places, profile.teach_grades
    return _render(request, profile, 'teach', form=form,
                   places=[{'code': code, 'label': TEACH_PLACE_TILE[code], 'on': code in places}
                           for code, _label in UserProfile.TEACH_PLACES],
                   grades=[{'code': code, 'label': label, 'on': code in grades}
                           for code, label in UserProfile.TEACH_GRADES])


def _group_step(request, profile):
    """Группа создаётся той же моделью, что в кабинете (`StudentGroup`). Код
    приглашения показан ДО создания (макет `Teach2.png`): его заранее выдаёт
    `StudentGroup._free_invite_code()` и держит сессия, из формы он не берётся."""
    from problems.models import StudentGroup

    done_url = request.session.get(NEXT_KEY) or '/teacher/'
    code = request.session.get(INVITE_KEY)
    if not code or StudentGroup.objects.filter(invite_code=code).exists():
        code = StudentGroup._free_invite_code()
        request.session[INVITE_KEY] = code
    form = GroupForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        StudentGroup.objects.create(name=form.cleaned_data['name'].strip(),
                                    teacher=request.user, kind='group', invite_code=code)
        for key in (NEXT_KEY, DONE_KEY, INVITE_KEY):
            request.session.pop(key, None)
        return redirect(done_url)
    return _render(request, profile, 'group', form=form, invite_code=code, done_url=done_url)


# ── Сборка плана и «План готов» ────────────────────────────────────────────

def _finish_url(request):
    """Конец анкеты ученика: экран сборки плана, а с ним — дальше в `next` или план."""
    request.session.pop(DONE_KEY, None)
    target = request.session.pop(NEXT_KEY, None)
    url = reverse('onboarding_build')
    return url + ('?' + urlencode({'to': target}) if target else '')


@require_http_methods(['GET', 'HEAD'])
def build(request):
    """Экран-переход «собираем план» (макет `Build.png`). Анимацию ведёт скрипт;
    без скрипта или при «уменьшить движение» страница сразу уходит дальше."""
    stop = _guard(request)
    if stop:
        return stop
    profile = _profile(request.user)
    if profile.onboarded_at is None:
        return redirect('onboarding')
    target = request.GET.get('to') or ''
    if not (target and is_safe(request, target)):
        target = ''
    if profile.grade in GRADE_NUMBER:
        first = 'Подбираем задачи для %s класса' % (
            '7 и младше' if profile.grade == 'le7' else profile.grade)
    else:
        first = 'Подбираем задачи под ваш уровень'
    lines = [first, 'Собираем план'] if target else [first, 'Смотрим ближайшие туры',
                                                     'Собираем план']
    return render(request, 'onboarding/build.html', {
        'title': 'Собираем план', 'lines': lines, 'target': target or reverse('onboarding_plan'),
        'progress': 100, 'done': True, 'seo_noindex': True,
    })


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
        level = problem.difficulty or 0
        rows.append({'url': reverse('catalog:problem_detail', args=[problem.pk]),
                     'title': title, 'topic': topic.name if topic else '',
                     'section': section_of(topic.name) if topic else 'other',
                     'stars': [i < level for i in range(5)] if level else [],
                     'level': level})
    return rows


def _tour_days():
    from vp import config as vp_config

    _kind, value = vp_config.TOUR_DATES.get(vp_config.CURRENT_TOUR, (None, None))
    if not value:
        return None
    left = (value[0] - timezone.localdate()).days
    return left if left > 0 else None


def _olympiad_card(profile):
    """Олимпиадная карточка по целям (раунд 2): тренажёр ВП, «Задачи ВсОШ» или карта."""
    from vp import config as vp_config
    from vp.visibility import visible_variants

    goals = set(profile.goals or [])
    if 'listed' in goals or profile.grade in ('9', '10', '11'):
        variant = (visible_variants().filter(grade_band=profile.grade).order_by('order', 'pk')
                   .first() if profile.grade in ('9', '10', '11') else None)
        return {
            'kind': 'vp', 'title': 'Тренажёр %d тура «Высшей пробы»' % vp_config.CURRENT_TOUR,
            'days': _tour_days(),
            'url': reverse('vp:intro', args=[variant.slug]) if variant else reverse('vp:variants'),
            'button': ('Открыть вариант %s класса' % profile.grade) if variant
            else 'Открыть варианты',
        }
    if 'vsosh' in goals:
        return {'kind': 'vsosh', 'title': 'Задачи ВсОШ', 'url': _vsosh_url(profile),
                'button': 'Открыть'}
    return {'kind': 'map', 'title': 'Карта тем', 'url': reverse('catalog:topic_map'),
            'button': 'Открыть карту'}


def _vsosh_url(profile):
    """Каталог с источниками ВсОШ и сложностью по уровню; нет таких источников —
    каталог с поиском по названию олимпиады."""
    from django.db.models import Q

    from problems.models import Source

    low, high = DIFFICULTY_BY_LEVEL.get(profile.level, (1, 5))
    query = [('difficulty', str(d)) for d in range(low, high + 1)]
    ids = list(Source.objects.filter(Q(name__icontains='ВсОШ') | Q(name__icontains='Всеросс'))
               .order_by('pk').values_list('pk', flat=True)[:30])
    query = [('source', str(pk)) for pk in ids] + query if ids else [('q', 'ВсОШ')] + query
    return reverse('catalog:problem_list') + '?' + urlencode(query)


def plan_cards(profile):
    """Состав плана: только то, что сайт умеет сегодня. Порядок — порядок сетки."""
    return {
        'olympiad': _olympiad_card(profile),
        'daily_url': reverse('game:daily'),
        'search_query': SMART_QUERY,
        'search_url': reverse('catalog:problem_list') + '?' + urlencode({'q': SMART_QUERY}),
    }


def _chips(profile):
    chips = []
    if profile.grade:
        chips.append(profile.get_grade_display())
    if profile.level:
        chips.append(profile.get_level_display())
    chips += [UserProfile.GOAL_SHORT[g] for g in profile.goals or [] if g in UserProfile.GOAL_SHORT]
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
    return render(request, 'onboarding/plan.html', dict(plan_cards(profile), **{
        'title': 'План готов',
        'heading': ('%s, план готов' % profile.user.first_name) if profile.user.first_name
        else 'План готов',
        'chips': _chips(profile),
        'tasks': tasks,
        'start_url': tasks[0]['url'] if tasks else reverse('catalog:problem_list'),
        'progress': 100,
        'done': True,
        'seo_noindex': True,
    }))


# ── Подсказки городов и школ (фаза 4 раунда 2) ─────────────────────────────

#: Сколько запросов подсказок в минуту на человека. Поле шлёт запрос не чаще
#: раза в 150 мс, так что живой человек упирается в потолок только при наборе
#: без пауз дольше минуты; перебор справочника — упирается сразу.
SUGGEST_PER_MINUTE = 120


def _suggest_guard(request):
    """Только вошедшим и не чаще потолка; иначе готовый отказ JSON."""
    from django.core.cache import cache
    from django.http import JsonResponse

    if not request.user.is_authenticated:
        return JsonResponse({'results': [], 'error': 'login'}, status=403)
    key = 'onb_suggest:%s:%s' % (request.user.pk, int(timezone.now().timestamp() // 60))
    count = cache.get_or_set(key, 0, 70)
    if count >= SUGGEST_PER_MINUTE:
        return JsonResponse({'results': [], 'error': 'rate'}, status=429)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, 70)
    return None


@require_http_methods(['GET'])
def cities_api(request):
    """`GET /welcome/api/cities/?q=` → `{"results": [{value, label, sub}]}`."""
    from django.http import JsonResponse

    from problems import school_search

    stop = _suggest_guard(request)
    if stop:
        return stop
    return JsonResponse({'results': school_search.cities(request.GET.get('q', '')[:60])})


@require_http_methods(['GET'])
def schools_api(request):
    """`GET /welcome/api/schools/?q=&city=` → школы по всей стране; `city` необязателен
    и влияет только на порядок (школы этого города — первыми)."""
    from django.http import JsonResponse

    from problems import school_search

    stop = _suggest_guard(request)
    if stop:
        return stop
    return JsonResponse({'results': school_search.schools(request.GET.get('city', '')[:120],
                                                          request.GET.get('q', '')[:80],
                                                          asker_id=request.user.pk)})
