"""
Экран статистики ученика — с геймификацией.

Разделение по ролям зафиксировано здесь и в `teacher/views_stats.py`:
УЧЕНИКУ — опыт, уровни, серии, достижения, рекорды; РЕПЕТИТОРУ И РОДИТЕЛЮ —
только диагностика. Причина простая: геймификация это инструмент мотивации
того, кто учится. Родителю «серия 12 дней» не говорит ничего полезного, а
«эластичность просела» говорит; репетитору чужой уровень не нужен вовсе.

Что стало со старой страницей «Прогресс»: она ПОГЛОЩЕНА. `/student/progress/`
теперь ведёт сюда редиректом. Двух похожих разделов быть не должно — а всё,
что там было (владение темами, навыки, замечания преподавателя), здесь есть,
и с историей вдобавок.
"""
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import stats as stats_module


def _period(request):
    """Период из адреса. Неизвестный — месяц, а не 500-я."""
    period = request.GET.get('period') or 'month'
    return period if period in dict(stats_module.PERIODS) else 'month'


@login_required
def student_stats(request):
    """Своя статистика. Открывает любой вошедший — она про него самого."""
    data = _student_payload(request.user, _period(request))
    return render(request, 'platform/stats.html', data)


@login_required
def student_stats_json(request):
    """Тот же расчёт для переключателя периода — без перезагрузки страницы."""
    data = stats_module.full_stats(request.user, _period(request))
    return JsonResponse(_chart_payload(data))


@require_POST
@login_required
def set_weekly_goal(request):
    """Недельную цель ставит САМ ученик.

    Цель, назначенная сверху, — это уже не цель, а норма выработки; она
    мотивирует ровно наоборот.
    """
    from .models import StudentProgressProfile

    try:
        goal = int(request.POST.get('weekly_goal') or 0)
    except ValueError:
        goal = 0
    goal = max(1, min(500, goal))
    profile, _ = StudentProgressProfile.objects.get_or_create(user=request.user)
    profile.weekly_goal = goal
    profile.save(update_fields=['weekly_goal', 'updated_at'])
    stats_module.invalidate(request.user)
    return redirect('student_stats')


def _records(queryset):
    """Личные рекорды с человеческой датой.

    ⚠️ Дата лежит в `payload` СТРОКОЙ («2026-08-04»), поэтому шаблонный
    фильтр `date` к ней неприменим — он ждёт объект. Переводим здесь:
    «7» без дня это не рекорд, а число, а «2026-08-04» посреди русского
    экрана читается как код.
    """
    from datetime import date as date_cls

    rows = []
    for record in queryset:
        raw = (record.payload or {}).get('date')
        record.when = None
        if raw:
            try:
                record.when = date_cls(*[int(part) for part in raw.split('-')])
            except (TypeError, ValueError):
                record.when = None
        rows.append(record)
    return rows


def _student_payload(user, period):
    """Контекст экрана ученика: статистика + геймификация."""
    from .models import (Achievement, EarnedAchievement, PersonalRecord,
                         StudentSkillProgress, TeacherFeedback)

    data = stats_module.full_stats(user, period)

    earned = {row.achievement_id: row for row in
              EarnedAchievement.objects.filter(user=user)
              .select_related('achievement')}
    achievements = []
    for achievement in Achievement.objects.all():
        row = earned.get(achievement.pk)
        achievements.append({
            'achievement': achievement,
            'earned': row is not None,
            'earned_at': row.earned_at if row else None,
            'rarity': achievement.rarity_percent(),
        })

    # Замечания преподавателя и навыки — переехали со старой страницы
    # «Прогресс». Не выбрасываем: это единственное место, где видно, ЧТО
    # именно преподаватель отмечает раз за разом.
    from django.db.models import Count
    mistakes = (TeacherFeedback.objects
                .filter(submission__student=user, mistakes__isnull=False)
                .values('mistakes__name')
                .annotate(count=Count('mistakes'))
                .order_by('-count')[:8])
    skills = (StudentSkillProgress.objects.filter(student=user)
              .select_related('skill').order_by('-level')[:8])

    return {
        'data': data,
        'period': period,
        'periods': stats_module.PERIODS,
        'achievements': achievements,
        'achievements_earned': sum(1 for a in achievements if a['earned']),
        'records': _records(PersonalRecord.objects.filter(user=user)),
        'mistakes': mistakes,
        'skills': skills,
        'chart_json': json.dumps(_chart_payload(data), ensure_ascii=False),
        'mastery_labels': MASTERY_LABELS,
    }


MASTERY_LABELS = {
    'none': 'не начата',
    'familiar': 'знаком',
    'confident': 'уверенно',
    'mastered': 'разобрался',
}


def _chart_payload(data):
    """Только то, что рисуют графики. Отдаётся и в шаблон, и в JSON."""
    return {
        'period': data['period'],
        'overview': data['overview'],
        'weekly': data['weekly'],
        'radar': data['radar'],
        'ring': data['ring'],
        'byWeekday': data['by_weekday'],
        'byHour': data['by_hour'],
        'sources': data['sources'],
        'timeHint': data['time_hint'],
        'levelHistory': [
            {'date': point['date'].strftime('%d.%m'), 'xp': point['xp'],
             'level': point['level']}
            for point in data.get('level_history', [])
        ],
        'topics': [
            {'name': t['name'], 'accuracy': t['accuracy'],
             'attempted': t['attempted'], 'mastery': t['mastery']}
            for t in data['topics']
        ],
    }
