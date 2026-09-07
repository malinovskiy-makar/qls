# -*- coding: utf-8 -*-
"""recount_olympiad_feature — пересчитать особенность «С реальной олимпиады».

⚠️ ПРИЗНАК ВЫВОДИТСЯ ИЗ ПРИВЯЗКИ, А НЕ ИЗ ИСТОЧНИКА ЗАДАЧИ. Источник врёт:
у SolveHub, ILE и Школково стоит их собственный `Source`, а внутри лежат
задачи ВсОШ, МОШ и Высшей пробы. Пометить по `SourceReference` значило бы
пометить агрегатор и пропустить настоящие олимпиады
(`claude/HANDOFF_OLYMPIADS_20260901.md` §2.4, решение владельца 07.09.2026).

Определение: у задачи есть хотя бы одна строка `OlympiadRef`. Поля
`match_method` со значением «none» не существует — в справочнике только
`url_exact` и `url_www_normalized`, обе означают найденную привязку.

Пока привязка собрана меньше чем у `features.MIN_CATALOG_COVERAGE` активных
задач, особенность не выводится в фильтр каталога: пустой фильтр хуже
отсутствующего. Порог проверяется в `features.catalog_visible_keys()`; здесь
он только печатается, чтобы было видно, далеко ли до показа.

Команда идемпотентна: повторный запуск даёт ноль изменений.

    manage.py recount_olympiad_feature           # сухой прогон
    manage.py recount_olympiad_feature --apply   # запись
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from problems.enrich import features as feat
from problems.enrich.layout import ensure_features
from problems.models import OlympiadRef, Problem, ProblemFeature

KEY = 'с_реальной_олимпиады'
INACTIVE_STATUSES = ('duplicate', 'hidden')


class Command(BaseCommand):
    help = 'Пересчитать особенность «С реальной олимпиады» по OlympiadRef.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Записать. Без флага — только числа.')

    def handle(self, *args, **options):
        feature = ensure_features()[KEY]

        # ⚠️ СВЯЗЬ СТАВИТСЯ ПО ВСЕЙ БАЗЕ, А ПОРОГ СЧИТАЕТСЯ ПО АКТИВНЫМ.
        # Особенность — факт задачи, статус к ней отношения не имеет; если
        # ставить её только активным, а `merge_enrichment_v2` — всем, две
        # команды начнут качели: одна ставит, другая снимает.
        active_ids = set(Problem.objects.exclude(status__in=INACTIVE_STATUSES)
                         .values_list('id', flat=True))
        linked_ids = set(OlympiadRef.objects.values_list('problem_id', flat=True))
        all_ids = set(Problem.objects.values_list('id', flat=True))
        want_ids = all_ids & linked_ids
        have_ids = set(ProblemFeature.objects
                       .filter(feature=feature)
                       .values_list('problem_id', flat=True))

        to_add = want_ids - have_ids
        to_drop = have_ids - want_ids

        active_linked = active_ids & linked_ids
        share = (len(active_linked) / len(active_ids)) if active_ids else 0.0
        self.stdout.write('активных задач: %d' % len(active_ids))
        self.stdout.write('с привязкой к олимпиаде: %d, из них активных %d (%.2f %%)'
                          % (len(want_ids), len(active_linked), share * 100))
        self.stdout.write('поставить: %d, снять: %d' % (len(to_add), len(to_drop)))
        if share < feat.MIN_CATALOG_COVERAGE:
            self.stdout.write(
                'в фильтре каталога СКРЫТА: покрытие ниже порога %.0f %% '
                '(features.MIN_CATALOG_COVERAGE)' % (feat.MIN_CATALOG_COVERAGE * 100))
        else:
            self.stdout.write('покрытие выше порога — особенность показывается')

        if not options['apply']:
            self.stdout.write('--dry-run: ничего не записано.')
            return

        with transaction.atomic():
            ProblemFeature.objects.bulk_create(
                [ProblemFeature(problem_id=pid, feature=feature, source=feat.BY_CODE)
                 for pid in sorted(to_add)], batch_size=1000)
            ProblemFeature.objects.filter(
                feature=feature, problem_id__in=sorted(to_drop)).delete()
        self.stdout.write('готово: поставлено %d, снято %d'
                          % (len(to_add), len(to_drop)))
        self.stdout.write('⚠️ витрину пересобирает `rebuild_feature_view --apply`.')
