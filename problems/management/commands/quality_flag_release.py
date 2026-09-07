# -*- coding: utf-8 -*-
"""quality_flag_release — снять `needs_quality_review` там, где сошлось ВСЁ.

Зачем. Каталог показывает 14 163 задачи из 41 284, и самый крупный отсев —
`needs_quality_review`: он режет 28 593 до 14 458. Обогащение этот флаг не
трогает вовсе, поэтому после всей раскладки больше половины размеченных задач
остаются невидимыми. Флаг ставили детекторы качества до обогащения; теперь по
части задач есть независимое суждение модели, и там, где ВСЕ признаки сошлись,
флаг можно снять.

⚠️ УСЛОВИЕ КОНЪЮНКТИВНОЕ И НАМЕРЕННО СТРОГОЕ. Снимаем только там, где сразу:

  * `text_quality='чистая'` — модель прочитала текст и не нашла дефектов;
  * `content_status='ok'` — чистка корпуса тоже не нашла;
  * есть хотя бы одна КАНОНИЧЕСКАЯ тема;
  * `problem_type` из восьми допустимых значений;
  * `answer` непуст — задача без ответа ученику бесполезна;
  * задача разложена прогоном (`enrichment_source` непуст) — строки с
    `defect: true` данных не получили и сюда не попадают по построению.

Любой не сошедшийся признак оставляет флаг на месте: пустить в каталог
сломанное хуже, чем задержать хорошее (правило старшинства из CLAUDE.md).

Обратимость. Перед записью снимок id уходит в
`reports/quality_flag_release/release_<время>.jsonl`; `--revert <файл>`
возвращает флаг ровно тем задачам, у которых он был снят. Ни одна задача не
трогается «оптом»: возврат идёт по списку.

    manage.py quality_flag_release                  # сухой прогон и разбивка
    manage.py quality_flag_release --apply          # снять флаг
    manage.py quality_flag_release --revert FILE    # вернуть по снимку
"""
import io
import json
import os
import time
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.models import Problem

OUT_DIR = os.path.join('reports', 'quality_flag_release')
VALID_PROBLEM_TYPES = (
    'единственный_выбор', 'множественный_выбор', 'верно_неверно',
    'сопоставление', 'тест: короткий ответ', 'задача с развёрнутым ответом',
    'несколько_подвопросов',
)
# «не_задача» в список НЕ входит: это прямая пометка «показывать нечего».


def candidates():
    """Задачи, у которых сошлись все шесть признаков."""
    return (Problem.objects
            .filter(needs_quality_review=True,
                    text_quality=Problem.TextQuality.CLEAN,
                    content_status=Problem.ContentStatus.OK,
                    problem_type__in=VALID_PROBLEM_TYPES,
                    topics__is_canonical=True)
            .exclude(answer='')
            .exclude(enrichment_source='')
            .distinct())


class Command(BaseCommand):
    help = 'Снять needs_quality_review там, где сошлись все признаки качества.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Снять флаг и записать снимок для отката.')
        parser.add_argument('--revert', type=str, default='',
                            help='Вернуть флаг по снимку (путь к jsonl).')

    def handle(self, *args, **options):
        if options['revert']:
            return self.revert(options['revert'])

        qs = candidates()
        ids = list(qs.values_list('id', flat=True))
        self.stdout.write('кандидатов на снятие флага: %d' % len(ids))

        by_topic = Counter()
        for name in (Problem.objects.filter(id__in=ids)
                     .values_list('topics__name', flat=True)):
            if name:
                by_topic[name] += 1
        self.stdout.write('')
        self.stdout.write('--- разбивка по темам ---')
        for name, n in by_topic.most_common():
            self.stdout.write('  %-52s %5d' % (name[:52], n))

        visible_now = self._visible_count()
        self.stdout.write('')
        self.stdout.write('видно каталогу сейчас: %d' % visible_now)
        would = self._visible_after(set(ids))
        self.stdout.write('станет видно после снятия: %d (+%d)'
                          % (would, would - visible_now))

        if not options['apply']:
            self.stdout.write('')
            self.stdout.write('--dry-run: ничего не записано.')
            return

        os.makedirs(OUT_DIR, exist_ok=True)
        path = os.path.join(OUT_DIR, 'release_%s.jsonl' % time.strftime('%Y%m%d_%H%M%S'))
        with io.open(path, 'w', encoding='utf-8') as fh:
            for pk in ids:
                fh.write(json.dumps({'id': pk}, ensure_ascii=False) + '\n')
        with transaction.atomic():
            Problem.objects.filter(id__in=ids).update(needs_quality_review=False)
        self.stdout.write('флаг снят у %d задач; снимок для отката: %s'
                          % (len(ids), path))

    def revert(self, path):
        if not os.path.exists(path):
            raise CommandError('снимка нет: %s' % path)
        ids = []
        with io.open(path, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if line:
                    ids.append(json.loads(line)['id'])
        with transaction.atomic():
            Problem.objects.filter(id__in=ids).update(needs_quality_review=True)
        self.stdout.write('флаг возвращён %d задачам' % len(ids))

    # ------------------------------------------------------------------

    @staticmethod
    def _visible_count():
        from catalog import filters
        return filters.base_queryset('catalog').count()

    @staticmethod
    def _visible_after(released_ids):
        """Сколько было бы видно, если у `released_ids` снять флаг."""
        from django.db.models import Q

        from catalog import filters
        gate = filters.base_queryset('catalog')
        extra = (Problem.objects
                 .filter(Q(id__in=released_ids),
                         status=Problem.Status.PUBLISHED,
                         hidden_pending_review=False,
                         content_status=Problem.ContentStatus.OK)
                 .exclude(id__in=gate.values('id')))
        return gate.count() + extra.count()
