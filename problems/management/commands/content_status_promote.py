# -*- coding: utf-8 -*-
"""`content_status_promote` — снять метку, которую поставил слабый прогон.

Решение владельца 07.09.2026. Правило «чистка сильнее прогона, повышений не
бывает» остаётся в силе **для ручной чистки**, но НЕ для метки, которую
поставил сам первый прогон. Иначе круг не размыкается никогда: задачу
пометил слабый прогон → из-за пометки её не пустили в сильный → она навсегда
вне каталога.

⚠️ **Команда работает ТОЛЬКО по манифесту.** Ни одна задача вне списка
`content_status` не меняет — это инвариант, и он проверяется кодом, а не
глазами. Манифест — тот же файл, которым шёл допрогон: после мержа исходный
запрос «`enrichment_source='run1'`» его уже не воспроизведёт, потому что
метка стала `run3`.

Правило пересчёта (только для задач манифеста):

* `text_quality = 'не_задача'` или `problem_type = 'не_задача'` → `junk`;
* `text_quality = 'серьёзные_дефекты'` → `needs_fix`;
* иначе → `ok`.

Отличие от `layout.content_status_for`, которым пользуется `merge_enrichment_v2`:
та **никогда не понижает планку** (`content_cleanup` сильнее модели), здесь
же повышение — и есть смысл команды. Поэтому правило написано отдельно, а не
взято оттуда с флагом: два разных правила лучше одного с оговоркой.

По умолчанию НИЧЕГО НЕ МЕНЯЕТ и печатает раскладку. Запись — `--apply`,
откат — `--revert` по снимку.

Запуск:
    manage.py content_status_promote --manifest reports/formula_v2/manifest_run3.txt
    manage.py content_status_promote --manifest … --apply
    manage.py content_status_promote --manifest … --revert
"""
import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.embedding_provenance import (
    TEXT_PROTECTED_FIELDS, protected_fingerprint,
)
from problems.management.commands.glm_enrich_run import read_ids_file
from problems.models import Problem

#: Куда кладётся снимок «было» — без него `--revert` невозможен.
SNAPSHOT_PATH = Path('reports/formula_v2/content_status_promote_backup.json')

#: Сколько примеров печатать глазами.
SAMPLES = 20


def status_for(text_quality, problem_type):
    """Новое значение по вердикту прогона. БЕЗ правила «не ниже текущего»."""
    if text_quality == 'не_задача' or problem_type == 'не_задача':
        return Problem.ContentStatus.JUNK
    if text_quality == 'серьёзные_дефекты':
        return Problem.ContentStatus.NEEDS_FIX
    return Problem.ContentStatus.OK


class Command(BaseCommand):
    help = ('Пересчитать content_status по вердикту прогона — только для '
            'задач манифеста. По умолчанию ничего не меняет.')

    def add_arguments(self, parser):
        parser.add_argument('--manifest', required=True,
                            help='Файл со списком id (один на строку, «#» — '
                                 'комментарий).')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--revert', action='store_true',
                            help='Вернуть значения из снимка.')
        parser.add_argument('--snapshot', default=str(SNAPSHOT_PATH))

    def handle(self, *args, **options):
        снимок = Path(options['snapshot'])
        if options['revert']:
            return self._revert(снимок)
        if options['apply'] and options['revert']:
            raise CommandError('--apply и --revert вместе не задаются.')

        ids = read_ids_file(options['manifest'])
        манифест = set(ids)
        задачи = list(Problem.objects.filter(pk__in=ids).only(
            'id', 'content_status', 'text_quality', 'problem_type', 'status',
            'statement'))
        пропало = манифест - {p.id for p in задачи}
        if пропало:
            self.stdout.write(self.style.WARNING(
                'В банке нет %d задач из манифеста (удалены после прогона): %s'
                % (len(пропало), sorted(пропало)[:20])))

        переходы = Counter()
        план = []
        for p in задачи:
            новое = status_for(p.text_quality, p.problem_type)
            переходы['%s -> %s' % (p.content_status or 'ok', новое)] += 1
            if новое != p.content_status:
                план.append((p, новое))

        поднялись = [(p, n) for p, n in план
                     if p.content_status == Problem.ContentStatus.NEEDS_FIX
                     and n == Problem.ContentStatus.OK]
        опубликованные = [p for p, _n in поднялись
                          if p.status == Problem.Status.PUBLISHED]

        self.stdout.write('Задач манифеста в банке: %d' % len(задачи))
        self.stdout.write('--- переходы ---')
        for имя, число in sorted(переходы.items(), key=lambda x: -x[1]):
            self.stdout.write('   %-24s %5d' % (имя, число))
        self.stdout.write('изменится: %d' % len(план))
        self.stdout.write(self.style.SUCCESS(
            'поднялось needs_fix → ok: %d, из них published: %d '
            '(это прямой прирост каталога)'
            % (len(поднялись), len(опубликованные))))
        self.stdout.write('')
        self.stdout.write('--- %d примеров для проверки глазами ---' % SAMPLES)
        for p, новое in план[:SAMPLES]:
            self.stdout.write(
                '#%-6d %s -> %-9s [%s] %r'
                % (p.id, p.content_status or 'ok', новое, p.status,
                   (p.statement or '')[:110].replace('\n', ' ')))

        if not options['apply']:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'Это план. Записи не было — добавьте --apply.'))
            return None
        if not план:
            self.stdout.write('Менять нечего.')
            return None

        отпечаток_до = protected_fingerprint(Problem.objects.all(),
                                             TEXT_PROTECTED_FIELDS)
        было_вне = self._снимок_вне_манифеста(манифест)

        снимок.parent.mkdir(parents=True, exist_ok=True)
        снимок.write_text(json.dumps({
            'manifest': options['manifest'],
            'before': {str(p.id): (p.content_status or '') for p, _n in план},
        }, ensure_ascii=False, indent=1), encoding='utf-8')

        with transaction.atomic():
            for p, новое in план:
                Problem.objects.filter(pk=p.id).update(content_status=новое)

        # ⚠️ Инвариант, проверяемый кодом: ни одна задача ВНЕ манифеста
        # content_status не сменила. Проверка глазами здесь бесполезна —
        # задач 41 307.
        стало_вне = self._снимок_вне_манифеста(манифест)
        if было_вне != стало_вне:
            raise CommandError(
                'ИНВАРИАНТ НАРУШЕН: content_status изменился у задач ВНЕ '
                'манифеста. Откат: --revert, затем разбираться.')
        отпечаток_после = protected_fingerprint(Problem.objects.all(),
                                                TEXT_PROTECTED_FIELDS)
        if отпечаток_до != отпечаток_после:
            raise CommandError('СВИП-ДЕТЕКТОР: тексты задач изменились.')

        self.stdout.write(self.style.SUCCESS(
            'Записано: %d задач. Снимок для отката: %s' % (len(план), снимок)))
        self.stdout.write('   задачи вне манифеста не тронуты (проверено кодом)')
        return None

    @staticmethod
    def _снимок_вне_манифеста(манифест):
        return sorted(
            (pid, статус) for pid, статус in
            Problem.objects.exclude(pk__in=манифест)
            .values_list('id', 'content_status'))

    def _revert(self, снимок):
        if not снимок.exists():
            raise CommandError('Нет снимка %s — откатывать нечем.' % снимок)
        данные = json.loads(снимок.read_text(encoding='utf-8'))
        было = данные['before']
        with transaction.atomic():
            for pid, статус in было.items():
                Problem.objects.filter(pk=int(pid)).update(content_status=статус)
        self.stdout.write(self.style.SUCCESS(
            'Откат: вернули content_status %d задачам.' % len(было)))
        return None
