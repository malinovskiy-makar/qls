# -*- coding: utf-8 -*-
"""Онбординг, раунд 2 (решения 29.10.2026): цели вместо «главной олимпиады»,
«Откуда узнали → Другое» своими словами.

`0084` не переписывается: она уже применена в локальных базах. Перевод старых
ответов — здесь же, до удаления поля (тестовые данные ветки, на бою поля ещё нет):
`hse` / `mosh` / `listed` → `listed`, `vsosh` → `vsosh`, `ieo` → `international`,
`undecided` → `undecided`. Обратный ход переводит первую цель назад.
"""
from django.db import migrations, models

FORWARD = {'vsosh': 'vsosh', 'hse': 'listed', 'mosh': 'listed', 'listed': 'listed',
           'ieo': 'international', 'undecided': 'undecided'}
BACKWARD = {'vsosh': 'vsosh', 'listed': 'listed', 'international': 'ieo',
            'undecided': 'undecided'}


def goals_from_main_olympiad(apps, schema_editor):
    UserProfile = apps.get_model('problems', 'UserProfile')
    for profile in UserProfile.objects.exclude(main_olympiad='').only('pk', 'main_olympiad'):
        goal = FORWARD.get(profile.main_olympiad)
        if goal:
            UserProfile.objects.filter(pk=profile.pk).update(goals=[goal])


def main_olympiad_from_goals(apps, schema_editor):
    UserProfile = apps.get_model('problems', 'UserProfile')
    for profile in UserProfile.objects.only('pk', 'goals'):
        for goal in profile.goals or []:
            if goal in BACKWARD:
                UserProfile.objects.filter(pk=profile.pk).update(main_olympiad=BACKWARD[goal])
                break


class Migration(migrations.Migration):

    dependencies = [
        ('problems', '0084_login_onboarding'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='goals',
            field=models.JSONField(blank=True, default=list, verbose_name='К чему готовится'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='source_other',
            field=models.CharField(blank=True, default='', max_length=120,
                                   verbose_name='Откуда узнали: другое'),
        ),
        migrations.RunPython(goals_from_main_olympiad, main_olympiad_from_goals),
        migrations.RemoveField(
            model_name='userprofile',
            name='main_olympiad',
        ),
    ]
