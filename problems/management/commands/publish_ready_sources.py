# -*- coding: utf-8 -*-
"""Перевести в `published` черновики источника, прошедшие строгую проверку.

Зачем. Три новых источника (SolveHub, Школково, ЛЭШ Гамма) импортировались
как `draft`: доверия к источнику авансом не выдаётся
([ADR 0033](../../../docs/adr/0033-new-sources-store-converted-text.md), правило
импорта в `problems/management/commands/CLAUDE.md`). После того как по ним
прошли конвертер, шлюз рендера и качественный шлюз, держать чистые карточки
в черновиках больше нечем — но и раздавать `published` пачкой нельзя.

**Критерий «готова к показу» — все три сразу, ни одного «наверное»:**

1. `status='draft'` — команда НЕ трогает `hidden`, `duplicate`, `archived`:
   у них статус поставлен осознанно и означает не «руки не дошли»;
2. `needs_quality_review=False` — качественный шлюз брака не нашёл;
3. `content_format='markdown'` — карточка прошла `render_preflight_v2`,
   то есть настоящий KaTeX, а не текстовые эвристики. Задачи на `plain`
   остаются черновиками: `plain` и означает «шлюз не пропустил».

Любое сомнение → карточка остаётся `draft`. Спрятать лишнее дешевле, чем
показать битое.

⚠️ **`hidden_pending_review` НЕ снимается, и это осознанно.** Это третий,
отдельный механизм скрытия — «человек ЕЩЁ НЕ СМОТРЕЛ», а не оценка
качества (корневой CLAUDE.md, раздел про ручное ревью). Снять его значило
бы объявить 9 тысяч карточек просмотренными человеком, которых никто не
смотрел. Поэтому после этой команды карточки в каталоге НЕ появятся —
их держит шлюз ручного ревью, и снимает его отдельное решение владельца
(`pending_review_gate --revert`).

Обратимость: `--apply` пишет журнал `id → прежний статус`, `--revert`
возвращает по нему. По умолчанию — сухой прогон.
"""
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.models import Problem, Source, SourceReference

OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'publish_readiness')
BACKUP_NAME = 'publish_ready_backup.json'


class Command(BaseCommand):
    help = ('Перевести чистые черновики указанных источников в published. '
            'Без --apply — сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--sources', required=True,
                            help='id источников через запятую')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--revert', action='store_true')
        parser.add_argument('--report-dir', default=OUT_DIR)

    def handle(self, *args, **options):
        report_dir = options['report_dir']
        backup_path = os.path.join(report_dir, BACKUP_NAME)

        if options['revert']:
            return self._revert(backup_path)

        source_ids = self._source_ids(options['sources'])
        scope = set(SourceReference.objects
                    .filter(source_id__in=source_ids)
                    .values_list('problem_id', flat=True))

        candidates = (Problem.objects
                      .filter(id__in=scope,
                              status=Problem.Status.DRAFT,
                              needs_quality_review=False,
                              content_format=Problem.ContentFormat.MARKDOWN)
                      .order_by('id'))
        ids = list(candidates.values_list('id', flat=True))

        self._report(source_ids, scope, ids)

        if not options['apply']:
            self.stdout.write('СУХОЙ ПРОГОН — в базе ничего не изменено.')
            return

        os.makedirs(report_dir, exist_ok=True)
        with open(backup_path, 'w', encoding='utf-8') as fh:
            json.dump({'note': 'id → статус ДО перевода в published',
                       'count': len(ids),
                       'rows': [[pid, Problem.Status.DRAFT] for pid in ids]},
                      fh, ensure_ascii=False)

        total_before = Problem.objects.count()
        with transaction.atomic():
            changed = Problem.objects.filter(id__in=ids).update(
                status=Problem.Status.PUBLISHED)
        if Problem.objects.count() != total_before:
            raise CommandError('ИНВАРИАНТ НАРУШЕН: число задач изменилось')

        self.stdout.write(self.style.SUCCESS(
            'ЗАПИСАНО: переведено в published %d задач. Журнал отката: %s'
            % (changed, backup_path)))
        self.stdout.write(
            '⚠️ В каталоге они пока НЕ появятся: их держит hidden_pending_review '
            '(шлюз ручного ревью). Снимается отдельно — pending_review_gate.')

    # ------------------------------------------------------------------
    @staticmethod
    def _source_ids(raw):
        try:
            ids = [int(p) for p in (raw or '').split(',') if p.strip()]
        except ValueError:
            raise CommandError('--sources: ожидаются id через запятую')
        if not ids:
            raise CommandError('--sources: пустой список')
        known = set(Source.objects.filter(id__in=ids).values_list('id', flat=True))
        missing = sorted(set(ids) - known)
        if missing:
            raise CommandError('--sources: нет таких источников: %s'
                               % ', '.join(map(str, missing)))
        return ids

    def _report(self, source_ids, scope, ids):
        self.stdout.write('источников: %s, задач в области: %d'
                          % (','.join(map(str, source_ids)), len(scope)))
        blocked = (Problem.objects
                   .filter(id__in=scope, status=Problem.Status.DRAFT)
                   .exclude(id__in=ids))
        self.stdout.write('  черновиков всего        %6d'
                          % Problem.objects.filter(
                              id__in=scope, status=Problem.Status.DRAFT).count())
        self.stdout.write('  из них к публикации     %6d' % len(ids))
        self.stdout.write('  остаются черновиками    %6d' % blocked.count())
        self.stdout.write('     из-за брака (флаг)   %6d'
                          % blocked.filter(needs_quality_review=True).count())
        self.stdout.write('     из-за формата plain  %6d'
                          % blocked.filter(needs_quality_review=False)
                          .exclude(content_format=Problem.ContentFormat.MARKDOWN)
                          .count())

    def _revert(self, backup_path):
        if not os.path.isfile(backup_path):
            raise CommandError('нет журнала отката: %s' % backup_path)
        with open(backup_path, encoding='utf-8') as fh:
            rows = json.load(fh)['rows']
        with transaction.atomic():
            n = 0
            for pid, status in rows:
                n += Problem.objects.filter(id=pid).update(status=status)
        self.stdout.write(self.style.SUCCESS('ОТКАЧЕНО: %d задач' % n))
