"""Заливка собранных фактов в базу из JSONL.

⚠️ ЗАЧЕМ ЧЕРЕЗ ФАЙЛЫ, А НЕ ПРЯМО ИЗ СКРИПТА СБОРА. Сбор идёт по десяткам
сайтов и рвётся: сеть, таймаут, конец контекста. Файл в
`data/olympiads/out/` — то, что уже добыто и не потеряется; команда
докатывает его в базу на любой машине столько раз, сколько нужно.

⚠️ ИДЕМПОТЕНТНОСТЬ ОБЯЗАТЕЛЬНА. Повторный запуск не плодит дубли: у
каждой сущности свой естественный ключ (`update_or_create`), а не
автоинкремент. Это сторожит тест.

⚠️ У КАЖДОГО ФАКТА ЕСТЬ ИСТОЧНИК. Записи, для которых модель требует
`source`, без него не создаются вовсе — это правило раздела, а не
пожелание: по нему школьник решает, куда подавать документы.
"""
import json
import pathlib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from olympiads.models import (FactSource, Olympiad, OlympiadBenefit,
                              OlympiadEvent, OlympiadLevelYear,
                              OlympiadScore, OlympiadStage, OlympiadVariant,
                              RegionalCoordinator, UniversityProgram)

OUT_DIR = pathlib.Path('data/olympiads/out')

# Файл → как называется в отчёте. Порядок ВАЖЕН: олимпиады раньше всего,
# что на них ссылается.
FILES = [
    ('sources.jsonl', 'источники'),
    ('olympiads.jsonl', 'олимпиады'),
    ('levels.jsonl', 'уровни'),
    ('stages.jsonl', 'этапы'),
    ('events.jsonl', 'даты'),
    ('scores.jsonl', 'проходные баллы'),
    ('programs.jsonl', 'программы вузов'),
    ('benefits.jsonl', 'льготы'),
    ('regions.jsonl', 'региональные организаторы'),
    ('variants.jsonl', 'комплекты'),
]


def read(name):
    path = OUT_DIR / name
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('//'):
            rows.append(json.loads(line))
    return rows


class Command(BaseCommand):
    help = ('Заливает собранные факты из data/olympiads/out/*.jsonl. '
            'Без --yes только печатает план.')

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true',
                            help='Действительно записать в базу.')
        parser.add_argument('--only', default='',
                            help='Только один файл, например levels.jsonl')

    def handle(self, *args, **options):
        only = options['only']
        plan = []
        for name, human in FILES:
            if only and name != only:
                continue
            plan.append((name, human, len(read(name))))
        if not plan:
            raise CommandError('Нечего заливать: файлов не найдено.')

        if not options['yes']:
            self.stdout.write('ПЛАН (ничего не записано, нужен --yes):')
            for name, human, count in plan:
                self.stdout.write('  {:<26} {:<28} {} записей'.format(
                    name, human, count))
            return

        self.sources = {}
        stats = {}
        with transaction.atomic():
            for name, human, _ in plan:
                handler = getattr(self, '_load_' + name.split('.')[0])
                stats[human] = handler(read(name))

        for human, made in stats.items():
            self.stdout.write('  {:<28} {}'.format(human, made))
        self.stdout.write(self.style.SUCCESS('Залито.'))

    # -- источники ---------------------------------------------------------
    def _source(self, key):
        """Источник по ключу. Пусто — значит факт без источника, и это ошибка."""
        if not key:
            return None
        source = self.sources.get(key)
        if source is None:
            source = FactSource.objects.filter(url=key).first()
        return source

    def _load_sources(self, rows):
        for row in rows:
            source, _ = FactSource.objects.update_or_create(
                url=row['url'],
                defaults=dict(
                    title=row.get('title', ''),
                    doc_type=row.get('doc_type', 'site'),
                    publisher=row.get('publisher', ''),
                    note=row.get('note', ''),
                    content_hash=row.get('content_hash', ''),
                    http_status=row.get('http_status') or None,
                ))
            self.sources[row.get('key') or row['url']] = source
        return len(rows)

    # -- справочник --------------------------------------------------------
    def _load_olympiads(self, rows):
        for row in rows:
            defaults = {k: v for k, v in row.items()
                        if k not in ('slug', 'source')}
            defaults['source'] = self._source(row.get('source'))
            # Пришли настоящие данные — запись перестаёт быть заглушкой.
            defaults.setdefault('is_placeholder', False)
            Olympiad.objects.update_or_create(slug=row['slug'],
                                              defaults=defaults)
        return len(rows)

    def _load_levels(self, rows):
        for row in rows:
            OlympiadLevelYear.objects.update_or_create(
                olympiad=Olympiad.objects.get(slug=row['slug']),
                academic_year=row['academic_year'],
                defaults=dict(
                    level=row.get('level'),
                    order_number=row.get('order_number'),
                    approval_status=row['approval_status'],
                    source=self._source(row.get('source')),
                ))
        return len(rows)

    def _load_stages(self, rows):
        for row in rows:
            OlympiadStage.objects.update_or_create(
                olympiad=Olympiad.objects.get(slug=row['slug']),
                code=row['code'],
                defaults={k: v for k, v in row.items()
                          if k not in ('slug', 'code')})
        return len(rows)

    def _load_events(self, rows):
        for row in rows:
            stage = None
            if row.get('stage_code'):
                stage = OlympiadStage.objects.filter(
                    olympiad__slug=row['slug'], code=row['stage_code']).first()
            event = OlympiadEvent(
                olympiad=Olympiad.objects.get(slug=row['slug']),
                stage=stage,
                academic_year=row['academic_year'],
                kind=row['kind'],
                date_start=row.get('date_start'),
                date_end=row.get('date_end'),
                approx_text=row.get('approx_text', ''),
                date_status=row['date_status'],
                region=row.get('region', ''),
                source=self._source(row.get('source')),
            )
            # ⚠️ `full_clean` ОБЯЗАТЕЛЕН: правило «неподтверждённая дата не
            # имеет права быть конкретной» живёт в `clean()` модели
            # ([ADR 0064]), и импорт обязан об него ломаться, а не
            # проносить мимо число, которого ещё никто не объявлял.
            event.full_clean()
            existing = OlympiadEvent.objects.filter(
                olympiad=event.olympiad, stage=stage,
                academic_year=event.academic_year, kind=event.kind).first()
            if existing is not None:
                event.pk = existing.pk
            event.save()
        return len(rows)

    def _load_scores(self, rows):
        for row in rows:
            OlympiadScore.objects.update_or_create(
                olympiad=Olympiad.objects.get(slug=row['slug']),
                stage=OlympiadStage.objects.filter(
                    olympiad__slug=row['slug'],
                    code=row.get('stage_code') or '').first(),
                year=row['year'], grade=row.get('grade'),
                score_type=row['score_type'],
                defaults=dict(value=row['value'],
                              max_value=row.get('max_value'),
                              scope=row.get('scope', 'federal'),
                              region=row.get('region', ''),
                              source=self._source(row.get('source'))))
        return len(rows)

    def _load_programs(self, rows):
        for row in rows:
            UniversityProgram.objects.update_or_create(
                university_short=row['university_short'],
                program_name=row['program_name'],
                defaults={k: v for k, v in row.items()
                          if k not in ('university_short', 'program_name')})
        return len(rows)

    def _load_benefits(self, rows):
        made = 0
        for row in rows:
            source = self._source(row.get('source'))
            if source is None:
                # ⚠️ Льгота без источника НЕ СОЗДАЁТСЯ. По этой таблице
                # школьник решает, куда подавать документы; строка «мне так
                # помнится» здесь дороже пустоты.
                raise CommandError(
                    'Льгота без источника: {} / {}'.format(
                        row.get('slug'), row.get('program')))
            OlympiadBenefit.objects.update_or_create(
                olympiad=Olympiad.objects.get(slug=row['slug']),
                program=UniversityProgram.objects.get(
                    university_short=row['program']),
                admission_year=row['admission_year'],
                defaults=dict(
                    benefit_type=row['benefit_type'],
                    score_100_subject=row.get('score_100_subject', ''),
                    confirm_subject=row.get('confirm_subject', ''),
                    confirm_min_score=row.get('confirm_min_score'),
                    required_level=row.get('required_level'),
                    grades_note=row.get('grades_note', ''),
                    source=source))
            made += 1
        return made

    def _load_regions(self, rows):
        for row in rows:
            RegionalCoordinator.objects.update_or_create(
                region_name=row['region_name'],
                defaults={k: v for k, v in row.items()
                          if k != 'region_name'})
        return len(rows)

    def _load_variants(self, rows):
        for row in rows:
            OlympiadVariant.objects.update_or_create(
                olympiad=Olympiad.objects.get(slug=row['slug']),
                year=row['year'], grade=row.get('grade'),
                stage=OlympiadStage.objects.filter(
                    olympiad__slug=row['slug'],
                    code=row.get('stage_code') or '').first(),
                defaults={k: v for k, v in row.items()
                          if k not in ('slug', 'year', 'grade', 'stage_code',
                                       'source')}
                | {'source': self._source(row.get('source'))})
        return len(rows)
