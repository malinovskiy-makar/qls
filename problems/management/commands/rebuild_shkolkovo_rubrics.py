# -*- coding: utf-8 -*-
r"""Пересобрать рубрики Школково из сырого `criteria_tex`.

Импорт разобрал 45 рубрик из 836 задач с непустым `criteria_tex`:
парсер знал ровно одну форму заголовка пункта. После расширения
(`corpus_converter/criteria.py`) разбирается 362.

Читает СЫРЬЁ с диска, как и `reconvert_new_sources`: рубрика — такой же
продукт конвертера, и пересобирать её из сохранённого текста было бы той
же ошибкой, что повторная канонизация ([ADR 0033](../../../docs/adr/0033-new-sources-store-converted-text.md)).

Предохранители:

1. Рубрика НЕ удаляется, если новый разбор пуст. Пустой разбор означает
   «формат не узнали», а не «критериев нет», и молча терять уже
   разобранное нельзя.
2. Задачи, тексты, `draft` и `hidden_pending_review` не трогаются вовсе —
   счётчики сверяются до и после.
3. Старые рубрики выписываются в бэкап целиком, с критериями.

По умолчанию — сухой прогон. Запись — только с `--apply`.
"""
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.corpus_converter.reconvert import _load_json, _shkolkovo_dir
from problems.corpus_converter.criteria import parse_shkolkovo_criteria
from problems.models import Problem, Rubric, RubricCriterion, Source

SOURCE_NAME = 'Школково — банк задач по экономике'
OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'import_new_sources')


def _shape(criteria):
    """Снимок рубрики В ТОМ ВИДЕ, В КАКОМ ОНА ЛЯЖЕТ В БАЗУ.

    ⚠️ Сравнивать надо именно с записываемым значением, а не с разбором:
    `max_points=None` пишется нулём (поле NOT NULL), а имя режется до 300
    символов. Первая версия сравнивала с разбором — и повторный сухой
    прогон предлагал заменить 134 рубрики, хотя в базе уже лежало ровно
    то же самое. Поймано проверкой идемпотентности."""
    return [((c['name'] or '')[:300], float(c.get('max_points') or 0), c['order'])
            for c in criteria]


class Command(BaseCommand):
    help = ('Пересобрать рубрики Школково из criteria_tex. '
            'Без --apply — сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='реально записать (по умолчанию сухой прогон)')
        parser.add_argument('--data-dir', help='папка выгрузки Школково')
        parser.add_argument('--report-dir',
                            help='куда класть отчёт и бэкап; тесты обязаны давать '
                                 'временную папку')

    def handle(self, *args, **options):
        do_apply = options['apply']
        source = Source.objects.filter(name=SOURCE_NAME).first()
        if source is None:
            raise CommandError(f'Источник «{SOURCE_NAME}» не найден в базе.')

        before = self._snapshot()
        import glob
        raws = {}
        for path in sorted(glob.glob(os.path.join(
                _shkolkovo_dir(options.get('data_dir')), '*.json'))):
            raw = _load_json(path)
            raws[str(raw.get('Id') or '')] = raw.get('criteria_tex') or ''
        if not raws:
            raise CommandError('Школково: сырьё не прочитано — папка пуста?')

        stats = {'задач': 0, 'criteria_tex непуст': 0, 'разобрано': 0,
                 'создать рубрику': 0, 'заменить рубрику': 0,
                 'оставить как есть': 0, 'разбор пуст — не трогаем': 0}
        planned = []
        backup = []

        qs = (Problem.objects.filter(source_references__source=source)
              .distinct().prefetch_related('source_references',
                                           'rubrics__criteria').order_by('id'))
        for problem in qs:
            stats['задач'] += 1
            ref = problem.source_references.filter(source=source).first()
            tex = raws.get(ref.problem_number, '')
            if tex.strip():
                stats['criteria_tex непуст'] += 1
            parsed = parse_shkolkovo_criteria(tex)['criteria']
            existing = list(problem.rubrics.all())
            if parsed:
                stats['разобрано'] += 1
            if not parsed:
                if existing:
                    stats['разбор пуст — не трогаем'] += 1
                continue
            old_shape = []
            for rubric in existing:
                old_shape += [
                    (c.name, float(c.max_points), c.order)
                    for c in rubric.criteria.all()]
            if old_shape == _shape(parsed):
                stats['оставить как есть'] += 1
                continue
            if existing:
                stats['заменить рубрику'] += 1
                backup.append({
                    'id': problem.id,
                    'rubrics': [
                        {'name': r.name,
                         'criteria': [
                             {'name': c.name, 'max_points': float(c.max_points),
                              'description': c.description, 'order': c.order}
                             for c in r.criteria.all()]}
                        for r in existing],
                })
            else:
                stats['создать рубрику'] += 1
            planned.append((problem.id, parsed))

        lines = ['']
        for key, value in stats.items():
            lines.append(f'  {key}: {value}')
        lines.append(f'  Rubric сейчас: {before["Rubric"]}, '
                     f'RubricCriterion: {before["RubricCriterion"]}')

        out_dir = options.get('report_dir') or OUT_DIR
        os.makedirs(out_dir, exist_ok=True)
        report_path = os.path.join(out_dir, 'rubrics_report.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({'applied': do_apply, 'stats': stats,
                       'changed_ids': [pid for pid, _c in planned]},
                      f, ensure_ascii=False, indent=1)
        lines.append(f'  отчёт: {report_path}')

        if not do_apply:
            lines.append('СУХОЙ ПРОГОН — в базе ничего не изменено.')
            self.stdout.write(self.style.WARNING('\n'.join(lines)))
            return

        backup_path = os.path.join(out_dir, 'rubrics_backup.json')
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump({'note': 'Рубрики Школково ДО пересборки.',
                       'count': len(backup), 'problems': backup},
                      f, ensure_ascii=False, indent=1)

        for problem_id, criteria in planned:
            # Своя транзакция на задачу: на SQLite IntegrityError внутри
            # общей отравляет родительский savepoint.
            with transaction.atomic():
                Rubric.objects.filter(problem_id=problem_id).delete()
                rubric = Rubric.objects.create(
                    problem_id=problem_id, name='Критерии оценивания')
                for criterion in criteria:
                    RubricCriterion.objects.create(
                        rubric=rubric,
                        name=(criterion['name'] or '')[:300],
                        max_points=criterion.get('max_points') or 0,
                        description=criterion.get('description', '') or '',
                        order=criterion['order'])

        after = self._snapshot()
        for key in ('Problem', 'draft', 'hidden_pending_review'):
            if before[key] != after[key]:
                raise CommandError(
                    f'ИНВАРИАНТ НАРУШЕН: «{key}» было {before[key]}, '
                    f'стало {after[key]}. Откат: {backup_path}')

        lines.append(f'ЗАПИСАНО: рубрик пересобрано {len(planned)}.')
        lines.append(f'  Rubric стало: {after["Rubric"]}, '
                     f'RubricCriterion: {after["RubricCriterion"]}')
        lines.append(f'  бэкап для отката: {backup_path}')
        self.stdout.write(self.style.SUCCESS('\n'.join(lines)))

    def _snapshot(self):
        qs = Problem.objects.filter(
            source_references__source__name=SOURCE_NAME).distinct()
        return {
            'Problem': Problem.objects.count(),
            'Rubric': Rubric.objects.count(),
            'RubricCriterion': RubricCriterion.objects.count(),
            'draft': qs.filter(status=Problem.Status.DRAFT).count(),
            'hidden_pending_review': qs.filter(hidden_pending_review=True).count(),
        }
