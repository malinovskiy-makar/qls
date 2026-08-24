"""
Команда dump_approved_for_deploy — дамп ТОЛЬКО прошедших ручное ревью задач
(Problem.human_review='approved') для первой заливки контента на прод
(сужение плана С1–С12: SolveHub/Школково пока не импортированы и не
рендерятся, полный банк заливать рано — см. docs/CORPUS-FORMAT.md).

В отличие от dump_for_deploy (полный банк, без embedding, без фильтров):
  - Problem фильтруется по human_review='approved';
  - embedding ВКЛЮЧЁН (не убран) — cache_similar на целевой базе читает его
    напрямую из Problem.embedding, без него «похожие» посчитать нечем;
  - SourceReference фильтруется по problem__in=approved, а НЕ дампится
    полностью: FK на Problem обязателен (null=False, CASCADE), и полный
    дамп (31 687 строк) сослался бы на 26 597 задач, которых в целевой базе
    не будет — это большая висячая ссылка, а не просто теоретический риск;
  - Topic/Subtopic/Tag/Source дампятся полностью — независимые от Problem
    справочники, дублировать фильтрацию не о чем;
  - similar_problems (M2M) НЕ дампится вовсе — cache_similar пересчитает
    его на целевой базе с нуля, ограничившись тем, что там реально есть;
  - duplicate_of (self-FK на Problem) обнуляется для approved-строк, чьё
    duplicate_of указывает на задачу ВНЕ approved-набора — иначе висячая
    ссылка. Задача остаётся approved, просто теряет ссылку на дубликат,
    которого не будет на целевой базе;
  - ReviewVerdict, DuplicateCandidate, FileAsset осознанно не дампятся —
    не нужны для отображения сайта, FileAsset вдобавок пуста.

owner (FK Problem -> User) и M2M skills/mistakes/files у approved-набора
проверены отдельно перед написанием этой команды — везде пусто (см. отчёт
сессии), поэтому User/Skill/MistakeTag/FileAsset сознательно не включены.
Если в будущем прогоне это перестанет быть так — команда упадёт с понятной
ошибкой ниже (self-check), а не тихо просядет по FK на проде.

Запуск:
    manage.py dump_approved_for_deploy --outdir deploy_fixtures_approved --chunk 2000
"""

import json
import os

from django.apps import apps
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError

from problems.models import Problem, ProblemPart, SourceReference, Topic, Subtopic, Tag, Source

REFERENCE_MODELS = ['problems.Topic', 'problems.Subtopic', 'problems.Tag', 'problems.Source']


def _clean_nul(value):
    """Рекурсивно убирает байт NUL (0x00) — PostgreSQL его запрещает."""
    if isinstance(value, str):
        return value.replace('\x00', '')
    if isinstance(value, list):
        return [_clean_nul(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean_nul(v) for k, v in value.items()}
    return value


def serialize_qs(qs):
    data = json.loads(serializers.serialize('json', qs))
    for obj in data:
        obj['fields'] = _clean_nul(obj['fields'])
    return data


class Command(BaseCommand):
    help = ('Дамп approved-подмножества банка для первой заливки на прод '
            '(сужение плана С1-С12).')

    def add_arguments(self, parser):
        parser.add_argument('--outdir', type=str, default='deploy_fixtures_approved')
        parser.add_argument('--chunk', type=int, default=2000)
        parser.add_argument(
            '--skip-duplicate-of-cleanup', action='store_true',
            help='Не обнулять duplicate_of у висячих ссылок (для «фазы '
                 'зубастости» — доказать, что чистка нужна).')

    def write_file(self, outdir, name, objects):
        path = os.path.join(outdir, name)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(objects, f, ensure_ascii=False)
        self.stdout.write(f'  {name}: {len(objects)} объектов')
        return len(objects)

    def handle(self, *args, **options):
        outdir = options['outdir']
        chunk = options['chunk']
        skip_cleanup = options['skip_duplicate_of_cleanup']
        os.makedirs(outdir, exist_ok=True)
        for fn in os.listdir(outdir):
            if fn.endswith('.json'):
                os.remove(os.path.join(outdir, fn))

        approved = Problem.objects.filter(human_review='approved').order_by('pk')
        approved_ids = set(approved.values_list('pk', flat=True))
        total_approved = len(approved_ids)
        if total_approved == 0:
            raise CommandError("human_review='approved' — 0 задач. Нечего дампить.")

        # ── self-check: подтвердить, что owner/skills/mistakes/files пусты ──
        # (проверено перед написанием команды; если больше не так — лучше
        # упасть здесь с понятной причиной, чем тихо потерять ссылки на проде)
        bad_owner = approved.filter(owner__isnull=False).count()
        bad_skills = approved.filter(skills__isnull=False).distinct().count()
        bad_mistakes = approved.filter(mistakes__isnull=False).distinct().count()
        bad_files = approved.filter(files__isnull=False).distinct().count()
        problems_found = []
        if bad_owner:
            problems_found.append(f'owner задан у {bad_owner} approved-задач (User не дампится)')
        if bad_skills:
            problems_found.append(f'skills привязаны у {bad_skills} approved-задач (Skill не дампится)')
        if bad_mistakes:
            problems_found.append(f'mistakes привязаны у {bad_mistakes} approved-задач (MistakeTag не дампится)')
        if bad_files:
            problems_found.append(f'files привязаны у {bad_files} approved-задач (FileAsset не дампится)')
        if problems_found:
            raise CommandError(
                'Найдены связи, для которых команда не готовит фикстуру, и '
                'заливка на прод создаст висячие ссылки:\n  - '
                + '\n  - '.join(problems_found)
                + '\nДобавь соответствующую модель в дамп, прежде чем продолжать.')

        self.stdout.write(f'Approved задач: {total_approved}')

        # ── TIER 1: справочники, полностью, без фильтра ──
        self.stdout.write('Справочники (Topic/Subtopic/Tag/Source), полностью:')
        ref_objects = []
        for label in REFERENCE_MODELS:
            model = apps.get_model(*label.split('.'))
            ref_objects.extend(serialize_qs(model.objects.all().order_by('pk')))
        n_ref = self.write_file(outdir, '10_reference.json', ref_objects)

        # ── duplicate_of: найти и (по умолчанию) обнулить висячие ссылки ──
        dangling = list(
            approved.filter(duplicate_of__isnull=False)
            .exclude(duplicate_of_id__in=approved_ids)
            .values_list('pk', 'duplicate_of_id')
        )
        self.stdout.write('')
        self.stdout.write(f'duplicate_of: у approved-набора всего с duplicate_of != NULL — '
                           f'{approved.filter(duplicate_of__isnull=False).count()}')
        self.stdout.write(f'duplicate_of: висячих (указывают вне approved-набора) — {len(dangling)}')
        if dangling and not skip_cleanup:
            self.stdout.write(f'  чищу {len(dangling)}: ' + ', '.join(f'#{a}->#{b}' for a, b in dangling[:20])
                              + (' …' if len(dangling) > 20 else ''))
        elif dangling and skip_cleanup:
            self.stdout.write(self.style.WARNING(
                f'  --skip-duplicate-of-cleanup: оставляю {len(dangling)} висячих ссылок как есть '
                '(для проверки, что загрузка правда падает)'))

        # ── TIER 2: Problem (approved, С embedding, duplicate_of почищен) ──
        self.stdout.write('')
        self.stdout.write('Problem (approved, с embedding):')
        dangling_ids = {a for a, _ in dangling}
        n_problem = 0
        ids_list = sorted(approved_ids)
        for start in range(0, len(ids_list), chunk):
            batch_ids = ids_list[start:start + chunk]
            batch = list(Problem.objects.filter(pk__in=batch_ids).order_by('pk'))
            data = serialize_qs(batch)
            for obj in data:
                if not skip_cleanup and obj['pk'] in dangling_ids:
                    obj['fields']['duplicate_of'] = None
                # similar_problems никогда не дампим для этой модели
                obj['fields'].pop('similar_problems', None)
            idx = start // chunk + 1
            n_problem += self.write_file(outdir, f'20_problem_{idx:04d}.json', data)

        # ── TIER 3: SourceReference, ТОЛЬКО для approved (не полностью!) ──
        self.stdout.write('')
        self.stdout.write('SourceReference (только approved):')
        sref_qs = SourceReference.objects.filter(problem_id__in=approved_ids).order_by('pk')
        n_sref = 0
        total_sref = sref_qs.count()
        n = 0
        idx = 0
        while n < total_sref:
            batch = list(sref_qs[n:n + chunk])
            data = serialize_qs(batch)
            idx += 1
            n_sref += self.write_file(outdir, f'30_sourceref_{idx:04d}.json', data)
            n += len(batch)

        # ── TIER 4: ProblemPart, ТОЛЬКО для approved ──
        self.stdout.write('')
        self.stdout.write('ProblemPart (только approved):')
        part_qs = ProblemPart.objects.filter(problem_id__in=approved_ids).order_by('pk')
        n_part = 0
        total_part = part_qs.count()
        n = 0
        idx = 0
        while n < total_part:
            batch = list(part_qs[n:n + chunk])
            data = serialize_qs(batch)
            idx += 1
            n_part += self.write_file(outdir, f'31_part_{idx:04d}.json', data)
            n += len(batch)

        files = sorted(f for f in os.listdir(outdir) if f.endswith('.json'))
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Готово: {len(files)} файлов в {outdir}/'))
        self.stdout.write('')
        self.stdout.write('── Итоговые числа ──')
        self.stdout.write(f'  Topic+Subtopic+Tag+Source: {n_ref}')
        self.stdout.write(f'  Problem (approved):        {n_problem}')
        self.stdout.write(f'  SourceReference (approved):{n_sref}')
        self.stdout.write(f'  ProblemPart (approved):    {n_part}')
        self.stdout.write(f'  duplicate_of висячих найдено: {len(dangling)}'
                           + ('' if skip_cleanup else f' (почищено: {len(dangling) if not skip_cleanup else 0})'))
