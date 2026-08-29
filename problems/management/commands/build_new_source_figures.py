# -*- coding: utf-8 -*-
r"""Строки `ProblemFigure` для картинок трёх новых источников.

Ничего не компилирует: читает уже скачанный файл с диска и кладёт его
байты в базу. Пара к `corpus_build_figures`, который собирает картинки
из TikZ через pdflatex.

Как это сходится с текстом задачи. `reconvert_new_sources` ставит в
тексте маркер `[[FIGURE:<sha256 ссылки>]]`; здесь по ТОЙ ЖЕ ссылке
считается тот же хеш. Обе стороны приходят к нему независимо: одной
нужен только текст, другой — только выгрузка.

⚠️ Порядок важен. Маркер без строки `ProblemFigure` на экране просто
исчезает (`problems/figures.py`), и шлюз честно ставит `FIGURE-MISSING`.
Поэтому эта команда идёт ПОСЛЕ `reconvert_new_sources --apply` и ДО
`render_new_sources`.

По умолчанию — сухой прогон. Запись — только с `--apply`.
"""
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.corpus_converter.images import CONTENT_TYPES, sniff_content_type
from problems.corpus_converter.reconvert import LOADERS
from problems.models import Problem, ProblemFigure, Source

OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'import_new_sources')
#: Больше этого в базу не кладём: в выгрузке SolveHub самый крупный файл
#: 2,0 МБ, поэтому потолок задан с запасом и существует не ради экономии,
#: а чтобы битый или подменённый файл не уехал в базу молча.
MAX_BYTES = 8 * 1024 * 1024


class Command(BaseCommand):
    help = ('Создать ProblemFigure из скачанных картинок новых источников. '
            'Без --apply — сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='реально записать (по умолчанию сухой прогон)')
        parser.add_argument('--source', choices=list(LOADERS),
                            help='только один источник')
        parser.add_argument('--data-dir',
                            help='папка выгрузки (только вместе с --source)')
        parser.add_argument('--report-dir',
                            help='куда класть отчёт; тесты обязаны давать временную папку')

    def handle(self, *args, **options):
        do_apply = options['apply']
        slugs = [options['source']] if options['source'] else list(LOADERS)
        if options.get('data_dir') and len(slugs) > 1:
            raise CommandError(
                '--data-dir задаёт папку ОДНОГО источника — давайте его вместе '
                'с --source.')

        figures_before = ProblemFigure.objects.count()
        problems_before = Problem.objects.count()
        stats = {'ссылок с файлом': 0, 'создано': 0, 'уже было': 0,
                 'файл пропал': 0, 'тип неизвестен': 0, 'слишком большой': 0}
        unresolved = []
        planned = []

        for slug in slugs:
            source_name, loader = LOADERS[slug]
            source = Source.objects.filter(name=source_name).first()
            if source is None:
                raise CommandError(f'Источник «{source_name}» не найден в базе.')
            resolver = self._resolver_for(slug, options.get('data_dir'))
            if resolver is None:
                self.stdout.write(f'{source_name}: картинок у источника нет')
                continue

            qs = (Problem.objects.filter(source_references__source=source)
                  .distinct().prefetch_related('source_references').order_by('id'))
            wanted = {
                p.source_references.filter(source=source).first().problem_number
                for p in qs
            }
            self.stdout.write(f'{source_name}: читаю сырьё…')
            records = loader(options.get('data_dir'), only=wanted)
            existing = set(
                ProblemFigure.objects.filter(problem__in=qs)
                .values_list('problem_id', 'tikz_hash'))

            for problem in qs:
                ref = problem.source_references.filter(source=source).first()
                record = records.get(ref.problem_number)
                if record is None:
                    continue
                for digest, reference in record.figures:
                    stats['ссылок с файлом'] += 1
                    if (problem.id, digest) in existing:
                        stats['уже было'] += 1
                        continue
                    path = resolver.path_for(reference)
                    if path is None:
                        stats['файл пропал'] += 1
                        unresolved.append(
                            {'id': problem.id, 'ref': reference,
                             'why': 'файл исчез между прогонами'})
                        continue
                    with open(path, 'rb') as f:
                        head = f.read(16)
                    content_type = sniff_content_type(head)
                    if content_type is None:
                        stats['тип неизвестен'] += 1
                        unresolved.append(
                            {'id': problem.id, 'ref': reference,
                             'why': f'байты не похожи ни на одну картинку: '
                                    f'{head[:8]!r}'})
                        continue
                    size = os.path.getsize(path)
                    if size > MAX_BYTES:
                        stats['слишком большой'] += 1
                        unresolved.append(
                            {'id': problem.id, 'ref': reference,
                             'why': f'{size} байт > потолка {MAX_BYTES}'})
                        continue
                    planned.append((problem.id, digest, reference, path,
                                    content_type, size))

        stats['создано'] = len(planned)
        total_bytes = sum(row[5] for row in planned)
        lines = ['']
        for key, value in stats.items():
            lines.append(f'  {key}: {value}')
        lines.append(f'  суммарный вес картинок: {total_bytes / 1048576:.1f} МБ')
        lines.append(f'  ProblemFigure было: {figures_before}')

        out_dir = options.get('report_dir') or OUT_DIR
        os.makedirs(out_dir, exist_ok=True)
        report_path = os.path.join(out_dir, 'figures_report.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({'applied': do_apply, 'stats': stats,
                       'bytes': total_bytes,
                       'не разрешилось': unresolved[:500]},
                      f, ensure_ascii=False, indent=1)
        lines.append(f'  отчёт: {report_path}')

        if not do_apply:
            lines.append('СУХОЙ ПРОГОН — в базе ничего не изменено.')
            self.stdout.write(self.style.WARNING('\n'.join(lines)))
            return

        created = 0
        for problem_id, digest, reference, path, content_type, _size in planned:
            with open(path, 'rb') as f:
                data = f.read()
            # Своя транзакция на строку: на SQLite IntegrityError внутри
            # общей отравляет родительский savepoint.
            with transaction.atomic():
                ProblemFigure.objects.update_or_create(
                    problem_id=problem_id, tikz_hash=digest,
                    defaults={'tikz_source': reference, 'svg': '',
                              'image_data': data, 'content_type': content_type,
                              'source_field': 'import'},
                )
            created += 1

        if Problem.objects.count() != problems_before:
            raise CommandError(
                'ИНВАРИАНТ НАРУШЕН: команда создаёт только картинки, а число '
                f'задач изменилось: было {problems_before}, '
                f'стало {Problem.objects.count()}')

        lines.append(f'ЗАПИСАНО: строк ProblemFigure создано/обновлено {created}.')
        lines.append(f'  ProblemFigure стало: {ProblemFigure.objects.count()}')
        self.stdout.write(self.style.SUCCESS('\n'.join(lines)))

    def _resolver_for(self, slug, data_dir):
        from problems.corpus_converter.reconvert import (
            ImageResolver, solvehub_resolver,
        )
        if slug == 'solvehub':
            return solvehub_resolver(data_dir)
        if slug == 'lesh':
            from problems.management.commands.import_lesh import _lesh_dir
            root = _lesh_dir(data_dir)
            mapping = {}
            for dirpath, _dirs, files in os.walk(root):
                for name in files:
                    if os.path.splitext(name)[1].lower() not in CONTENT_TYPES:
                        continue
                    full = os.path.join(dirpath, name)
                    rel = os.path.relpath(full, root).replace('\\', '/')
                    mapping[rel] = os.path.relpath(full, root)
                    mapping.setdefault(name, os.path.relpath(full, root))
            return ImageResolver(mapping, root)
        # Школково: файлов картинок у импортированных задач нет вовсе —
        # см. `reconvert._no_images`.
        return None
