# -*- coding: utf-8 -*-
"""Профиль, заполненный маркерами, — для P0-сторожей слоя ИИ (18.09.2026).

P0 (CLAUDE.md): поля профиля НИКОГДА не уходят в модель. Сторож заполняет
ВСЕ поля профиля узнаваемыми значениями и проверяет, что ни одно значение и
ни одно имя нового поля не попало ни в системный блок, ни в текст запроса.
Новое поле профиля — строка здесь, и сторожа обоих слоёв видят его сразу.
"""

MARKER_VALUES = {
    'school': 'ШколаМаркер',
    'city': 'ГородМаркер',
    'goal': 'ЦельМаркер',
    'phone': '+79990001122',
    'grade': 'none',
    'level': 'final',
    'prep_mode': ['course'],
    'hours_week': 'gt6',
    'source_channel': 'friend',
    'olympiad_history': ['vsosh_final'],
    'telegram': 'tgmarker_nick',
}

#: Что не должно встретиться в тексте запроса и в системном блоке.
FORBIDDEN = ('ШколаМаркер', 'ГородМаркер', 'ЦельМаркер', '+79990001122',
             'tgmarker_nick',
             'Уже не школьник', 'vsosh_final', 'На курсах', 'Больше 6',
             'prep_mode', 'hours_week', 'source_channel', 'olympiad_history')


def fill_profile_with_markers(user):
    profile = user.profile
    for name, value in MARKER_VALUES.items():
        setattr(profile, name, value)
    profile.save()
    return profile
