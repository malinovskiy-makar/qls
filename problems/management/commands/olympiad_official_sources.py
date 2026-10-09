# -*- coding: utf-8 -*-
"""Справочные строки под официальный эталон олимпиады (`--olympiad vp|mosh`).

Заводит, если их нет:
  * `Source` «<олимпиада>: официальный архив» из реестра аудита
    (`problems/olympiad_audit/registry.py`) — источник для заданий,
    импортированных из PDF организатора (`apply_olympiad_audit --import`);
  * для ВП — карточки `olympiads.Olympiad` для `vp-fingram` и `vp-ob`:
    слаги есть в `OlympiadRef`, а в справочнике олимпиад их не было;
  * для остальных — проверяет карточку `Olympiad` своего слага и дописывает
    ей официальный сайт, только если поле пустое.

Данные, а не миграция: справочник правится руками в админке, и строка в
миграции жила бы своей жизнью. Карточки олимпиад заводятся
НЕОПУБЛИКОВАННЫМИ — описания у них нет, показывать их на сайте решает
владелец.

⚠️ `import_olympiads_data --wipe` и `seed_olympiads_demo --wipe` сносят ВСЕ
карточки `Olympiad`. После них эту команду надо запустить снова.

    manage.py olympiad_official_sources --olympiad vp            # сухой прогон
    manage.py olympiad_official_sources --olympiad mosh --apply  # запись

Повторный запуск ничего не создаёт и существующее не меняет.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from olympiads.models import Olympiad
from problems.models import Source
from problems.olympiad_audit import registry

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
    help = ('Завести Source «<олимпиада>: официальный архив» (и у ВП карточки '
            'vp-fingram, vp-ob). По умолчанию сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--olympiad', choices=sorted(registry.REGISTRY),
                            help='Слаг олимпиады из реестра аудита (обязателен).')
        parser.add_argument('--apply', action='store_true',
                            help='Записать в базу (без флага — только план).')

    def handle(self, *args, **options):
        if not options.get('olympiad'):
            raise CommandError('--olympiad <слаг> обязателен (vp, mosh, …). '
                               'Ничего не сделано.')
        entry = registry.get(options['olympiad'])
        apply = options['apply']
        cards = OLYMPIADS if entry.slug in registry.VP_FAMILY else []
        plan = []
        if not Source.objects.filter(name=entry.official_source_name).exists():
            plan.append(('Source', entry.official_source_name))
        for card in cards:
            if not Olympiad.objects.filter(slug=card['slug']).exists():
                plan.append(('Olympiad', card['slug']))
        own = Olympiad.objects.filter(slug=entry.slug).first()
        if own is None and entry.slug not in registry.VP_FAMILY:
            self.stdout.write(self.style.WARNING(
                f'Карточки Olympiad «{entry.slug}» нет — её заводит '
                'import_olympiads_data; здесь не создаётся.'))
        elif own is not None and not own.official_url and entry.official_site:
            plan.append(('Olympiad.official_url', entry.slug))
        elif own is not None:
            self.stdout.write(f'Olympiad {entry.slug}: official_url = '
                              f'{own.official_url or "—"} (не меняется)')

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
                name=entry.official_source_name,
                defaults=entry.official_source_defaults)
            for card in cards:
                Olympiad.objects.get_or_create(
                    slug=card['slug'],
                    defaults={**OLYMPIAD_COMMON, **card})
            if ('Olympiad.official_url', entry.slug) in plan:
                Olympiad.objects.filter(slug=entry.slug, official_url='').update(
                    official_url=entry.official_site)
        self.stdout.write(self.style.SUCCESS(
            f'Создано: {len(plan)}. Source: {Source.objects.count()}, '
            f'Olympiad: {Olympiad.objects.count()}'))
