# -*- coding: utf-8 -*-
"""Фаза 0 сессии С13 — задним числом проставить провенанс легаси-эмбеддингов.

Поля версионирования завела С5 (миграция 0044), но НЕ заполнила: у всех
31 694 существующих векторов они пусты. Пока это так, «что устарело» нельзя
спросить у базы — а именно ради этого поля и заводили.

Запуск:
    manage.py backfill_embedding_provenance            # сухой прогон (по умолчанию)
    manage.py backfill_embedding_provenance --apply    # боевой прогон

⚠️ Пишет строго через `QuerySet.update()`, а не `.save()`. Причина не в
скорости: `Problem.updated_at` объявлен с `auto_now=True`, и проход по банку
через `.save()` проштамповал бы все 31 699 задач сегодняшней датой. Именно
`updated_at` — единственное независимое свидетельство о том, когда правили
текст (745 задач фикс-пака МатЭк видны как кластер 2026-08-27), и Фаза 1 на
нём стоит. `.update()` не трогает auto_now — поэтому улика цела.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from problems import embedding_provenance as prov
from problems.models import Problem

BACKUP_DIR = Path('reports/embeddings_scaleup')


class Command(BaseCommand):
    help = 'Проставить легаси-провенанс существующим эмбеддингам (С13, Фаза 0).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Боевой прогон. Без флага команда только считает.',
        )
        # ⚠️ Путь снимка обязан настраиваться, иначе прогон тестов затирает
        # боевой журнал отката: тест вызывает --apply, честно пишет в тот же
        # фиксированный файл, и снимок 31 694 записей подменяется одной
        # тестовой строкой. Ровно это и случилось 28.08 — поймано по размеру
        # файла (124 байта вместо сотен килобайт).
        parser.add_argument(
            '--backup-path', default=None,
            help='Куда положить снимок старых значений. По умолчанию '
                 f'{BACKUP_DIR}/provenance_backfill_backup.json',
        )

    def handle(self, *args, **options):
        apply_mode = options['apply']
        everything = Problem.objects.all()

        total = everything.count()
        with_vector = everything.exclude(embedding__isnull=True)
        # Кандидат — задача с вектором, у которой провенанс ещё не проставлен.
        candidates = with_vector.filter(
            Q(embedding_built_at__isnull=True) | Q(embedding_version__isnull=True)
        )
        candidate_count = candidates.count()
        without_vector = total - with_vector.count()

        self.stdout.write(f'Задач в банке:              {total}')
        self.stdout.write(f'  из них с эмбеддингом:     {with_vector.count()}')
        self.stdout.write(f'  без эмбеддинга вовсе:     {without_vector}')
        self.stdout.write(f'Кандидатов на backfill:     {candidate_count}')

        if not apply_mode:
            self.stdout.write(self.style.WARNING(
                'Сухой прогон — ничего не записано. Боевой: --apply'))
            return

        if not candidate_count:
            self.stdout.write(self.style.SUCCESS('Нечего проставлять — уже проставлено.'))
            return

        # Обратимый журнал: старые значения четырёх полей до правки.
        backup_path = Path(options['backup_path'] or
                           BACKUP_DIR / 'provenance_backfill_backup.json')
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup = list(candidates.values(
            'id', 'embedding_version', 'embedding_model_build',
            'embedding_source_hash', 'embedding_built_at',
        ))
        backup_path.write_text(
            json.dumps(backup, ensure_ascii=False, default=str), encoding='utf-8')
        self.stdout.write(f'Снимок старых значений:     {backup_path}')

        fingerprint_before = prov.protected_fingerprint(everything)

        values = prov.legacy_values(has_embedding=True)
        written = candidates.update(**values)

        fingerprint_after = prov.protected_fingerprint(everything)
        if fingerprint_before != fingerprint_after:
            raise CommandError(
                'Защищённые поля разошлись до/после backfill: '
                f'{fingerprint_before} != {fingerprint_after}. '
                'Тексты задач менять этой сессии запрещено.'
            )

        if Problem.objects.count() != total:
            raise CommandError('Изменилось число задач — это не операция удаления.')

        self.stdout.write(f'Проставлено:                {written}')
        self.stdout.write(f'Отпечаток защищённых полей: {fingerprint_after} (не изменился)')
        self.stdout.write(self.style.SUCCESS('Готово. Тексты не тронуты.'))
