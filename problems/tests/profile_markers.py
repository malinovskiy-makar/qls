# -*- coding: utf-8 -*-
"""Профиль, заполненный маркерами, — для P0-сторожей слоя ИИ (18.09.2026).

P0 (CLAUDE.md): поля профиля НИКОГДА не уходят в модель. Сторож заполняет
ВСЕ поля профиля узнаваемыми значениями и проверяет, что ни одно значение и
ни одно имя нового поля не попало ни в системный блок, ни в текст запроса.
Новое поле профиля — строка здесь, и сторожа обоих слоёв видят его сразу.
"""
from datetime import date

MARKER_VALUES = {
    'school': 'ШколаМаркер',
    'city': 'ГородМаркер',
    'goal': 'ЦельМаркер',
    'grade': 'none',
    'level': 'final',
    'prep_mode': ['course'],
    'hours_week': 'gt6',
    'source_channel': 'friend',
    'olympiad_history': ['vsosh_final'],
    'telegram': 'tgmarker_nick',
    # Онбординг и вход через VK ID / Яндекс ID (29.10.2026).
    'main_olympiad': 'undecided',
    'teach_places': ['circle'],
    'teach_grades': ['6'],
    'birth_date': date(2001, 2, 3),
}

#: Что не должно встретиться в тексте запроса и в системном блоке.
FORBIDDEN = ('ШколаМаркер', 'ГородМаркер', 'ЦельМаркер',
             'tgmarker_nick',
             'Уже не школьник', 'vsosh_final', 'На курсах', 'Больше 6',
             'prep_mode', 'hours_week', 'source_channel', 'olympiad_history',
             'Пока не решил', 'Кружок или онлайн-школа', '2001-02-03', '03.02.2001',
             'main_olympiad', 'teach_places', 'teach_grades', 'birth_date')


def fill_profile_with_markers(user):
    profile = user.profile
    for name, value in MARKER_VALUES.items():
        setattr(profile, name, value)
    profile.save()
    return profile
