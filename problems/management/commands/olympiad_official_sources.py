# -*- coding: utf-8 -*-
"""Справочные строки под официальный эталон олимпиады (пилот «Высшая проба»).

Заводит, если их нет:
  * `Source` «Высшая проба: официальный архив» — источник для заданий,
    импортированных из PDF организатора (`apply_olympiad_audit --import`);
  * карточки `olympiads.Olympiad` для `vp-fingram` и `vp-ob` — слаги есть
    в `OlympiadRef`, а в справочнике олимпиад их не было.

Данные, а не миграция: справочник правится руками в админке, и строка в
миграции жила бы своей жизнью. Карточки олимпиад заводятся
НЕОПУБЛИКОВАННЫМИ — описания у них нет, показывать их на сайте решает
владелец.

⚠️ `import_olympiads_data --wipe` и `seed_olympiads_demo --wipe` сносят ВСЕ
карточки `Olympiad`. После них эту команду надо запустить снова.

    manage.py olympiad_official_sources            # сухой прогон
    manage.py olympiad_official_sources --apply    # запись

Повторный запуск ничего не создаёт и существующее не меняет.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from olympiads.models import Olympiad
from problems.models import Source
from problems.olympiad_official import (
    OFFICIAL_SOURCE_DEFAULTS, OFFICIAL_SOURCE_NAME,
)

#: Поля карточек — по образцу записи `vp` и демо-сеялки (смежный профиль).
OLYMPIADS = [
    {
        'slug': 'vp-fingram',
        'name_full': 'Высшая проба по финансовой грамотности',
        'name_short': 'ВП: финграмотность',
    },
    {
        'slug': 'vp-ob',
        'name_full': 'Высшая проба по основам бизнеса',
        'name_short': 'ВП: основы бизнеса',
    },
]
OLYMPIAD_COMMON = {
    'organizer': 'НИУ «Высшая школа экономики»',
    'official_url': 'https://olymp.hse.ru/mmo/',
    'kind': Olympiad.Kind.PERECHEN,
    'display_group': Olympiad.DisplayGroup.RELATED,
    'grade_min': 9,
    'grade_max': 11,
    'language': 'русский',
    'is_published': False,
}


class Command(BaseCommand):
    help = ('Завести Source «Высшая проба: официальный архив» и карточки '
            'олимпиад vp-fingram, vp-ob. По умолчанию сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Записать в базу (без флага — только план).')

    def handle(self, *args, **options):
        apply = options['apply']
        plan = []
        if not Source.objects.filter(name=OFFICIAL_SOURCE_NAME).exists():
            plan.append(('Source', OFFICIAL_SOURCE_NAME))
        for card in OLYMPIADS:
            if not Olympiad.objects.filter(slug=card['slug']).exists():
                plan.append(('Olympiad', card['slug']))

        self.stdout.write(f'Source: {Source.objects.count()}, '
                          f'Olympiad: {Olympiad.objects.count()}')
        if not plan:
            self.stdout.write(self.style.SUCCESS('Создавать нечего — всё уже есть.'))
            return
        for kind, name in plan:
            self.stdout.write(f'  создать {kind}: {name}')
        if not apply:
            self.stdout.write(self.style.WARNING(
                'СУХОЙ ПРОГОН — в базе ничего не изменено. Запись: --apply.'))
            return

        with transaction.atomic():
            Source.objects.get_or_create(
                name=OFFICIAL_SOURCE_NAME, defaults=OFFICIAL_SOURCE_DEFAULTS)
            for card in OLYMPIADS:
                Olympiad.objects.get_or_create(
                    slug=card['slug'],
                    defaults={**OLYMPIAD_COMMON, **card})
        self.stdout.write(self.style.SUCCESS(
            f'Создано: {len(plan)}. Source: {Source.objects.count()}, '
            f'Olympiad: {Olympiad.objects.count()}'))
