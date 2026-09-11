# -*- coding: utf-8 -*-
r"""Чистка полей, куда вместо значения попало ИМЯ ПОЛЯ (баг 07.09, 882 задачи).

ПРИЧИНА (доказана, а не предположена). Перестройка таблицы в SQLite. Django
при `AddField` пересоздаёт таблицу и переносит данные запросом вида

    INSERT INTO new (..., "title_candidate", ...)
    SELECT ..., "title_candidate", ... FROM old

где список берётся из СОСТОЯНИЯ МОДЕЛИ (`_remake_table`, `mapping =
{f.column: quote_name(f.column)}`). Если колонки в СТАРОЙ, физической таблице
нет, SQLite не падает: двойные кавычки, не разрешившиеся в идентификатор, он
по legacy-правилу считает СТРОКОВЫМ ЛИТЕРАЛОМ. В каждую строку уезжает имя
колонки.

Условие срабатывания было создано 07.09: миграция `0049_title_candidate_source`
значилась применённой в `django_migrations`, а колонок в таблице не было
(база пришла дампом боевого сервера, где их нет — 29 колонок). Следующая же
перестройка (`0050_problem_content_status`, `0056_enrichment_v2_layout`) молча
залила `title_candidate='title_candidate'` и `title_source='title_source'` во
все 41 307 строк. Мерж обогащения переписал 40 425; остались 882 — ровно те,
кого прогон не трогал (478 duplicate, 402 hidden, 2 published).

Почему это не поймали: `merge_enrichment_v2` считает покрытие как
`exclude(title_candidate='')`, а литерал — непустая строка. «Покрытие 100 %»
было на 882 задачи ложью.

ОБРАТИМОСТЬ. Снимок «было» кладётся до записи, `--revert` возвращает из него.

    manage.py clear_field_name_values                    # только счёт
    manage.py clear_field_name_values --apply
    manage.py clear_field_name_values --revert --apply
"""
import io
import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.models import Problem

OUT_DIR = os.path.join('reports', 'formula_v2')
SNAPSHOT = os.path.join(OUT_DIR, 'field_name_values_backup.json')

#: Поля, которые проверяем. Все четыре — короткие текстовые поля раскладки:
#: именно у них «имя вместо значения» проходит валидацию длины и потому
#: доживает до боевой базы.
FIELDS = ('title_candidate', 'title_source', 'enrichment_source', 'text_quality')

CHUNK = 500


def broken_ids(field):
    """id задач, у которых значение поля равно имени этого же поля."""
    return list(Problem.objects.filter(**{field: field})
                .order_by('id').values_list('id', flat=True))


class Command(BaseCommand):
    help = ('Чистит поля, в которые вместо значения записано имя поля. '
            'Без --apply ничего не пишет.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--revert', action='store_true')
        parser.add_argument('--snapshot', default=SNAPSHOT)

    def handle(self, *args, **opts):
        if opts['revert']:
            return self._revert(opts)

        найдено = {поле: broken_ids(поле) for поле in FIELDS}
        for поле in FIELDS:
            self.stdout.write('%-20s %5d' % (поле, len(найдено[поле])))
        всего = len({i for ids in найдено.values() for i in ids})
        self.stdout.write(self.style.WARNING('задач затронуто: %d' % всего))
        if not всего:
            self.stdout.write('чистить нечего')
            return
        if not opts['apply']:
            self.stdout.write('это прогон без записи; чистка — --apply')
            return

        снимок = {поле: найдено[поле] for поле in FIELDS if найдено[поле]}
        os.makedirs(os.path.dirname(opts['snapshot']) or '.', exist_ok=True)
        with io.open(opts['snapshot'], 'w', encoding='utf-8') as fh:
            json.dump(снимок, fh, ensure_ascii=False)
        self.stdout.write('снимок «было»: %s' % opts['snapshot'])

        with transaction.atomic():
            очищено = self._write(снимок, значение='')
            осталось = sum(len(broken_ids(поле)) for поле in FIELDS)
            if осталось:
                raise CommandError(
                    'после чистки осталось %d полей с именем поля — '
                    'транзакция откачена' % осталось)
        self.stdout.write(self.style.SUCCESS('очищено полей: %d' % очищено))

    def _revert(self, opts):
        путь = opts['snapshot']
        if not os.path.exists(путь):
            raise CommandError('снимка нет: %s' % путь)
        with io.open(путь, encoding='utf-8') as fh:
            снимок = json.load(fh)
        self.stdout.write('в снимке полей: %d'
                          % sum(len(v) for v in снимок.values()))
        if not opts['apply']:
            self.stdout.write('это прогон без записи; откат — --revert --apply')
            return
        with transaction.atomic():
            вернули = self._write(снимок, значение=None)
        self.stdout.write(self.style.SUCCESS('возвращено полей: %d' % вернули))

    @staticmethod
    def _write(снимок, значение):
        """Пишет `значение` в перечисленные поля. `значение=None` означает
        «вернуть имя поля» — то, что там стояло до чистки."""
        сделано = 0
        for поле, ids in снимок.items():
            что = поле if значение is None else значение
            for начало in range(0, len(ids), CHUNK):
                кусок = ids[начало:начало + CHUNK]
                сделано += Problem.objects.filter(id__in=кусок).update(
                    **{поле: что})
        return сделано
