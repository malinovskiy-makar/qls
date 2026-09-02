"""
Команда dump_for_deploy — порционный JSON-дамп данных для деплоя на PostgreSQL.

Зачем порции:
  1) Некоторые хостинги обрывают долгие внешние транзакции — большой
     дамп в одной транзакции не доезжает. Короткие транзакции (по файлу) переживают.
  2) Меньше памяти при разборе каждого файла.

Что исключается из Problem:
  - поле embedding (46 МБ binary, на проде не нужно — модель там не грузится);
  - M2M similar_problems (self-ref, 105 540 строк) — выгружается ОТДЕЛЬНО последним
    шагом, когда все Problem уже загружены (иначе forward-ссылки через границы
    транзакций ломают FK).

Порядок файлов (по зависимостям, грузить в алфавитном порядке имён):
  10_reference   — независимые справочники (User, Topic, Tag, Source, ...)
  20_problem_*   — Problem порциями (без embedding, без similar_problems)
  30_sourceref_* — SourceReference порциями (FK Problem)
  31_part_*      — ProblemPart порциями (FK Problem)
  40_misc        — мелкие связанные модели (Lesson, Assignment, Submission, ...)
  50_dupcand_*   — DuplicateCandidate порциями (FK Problem)
  51_autotopic_* — AutoTopicAssignment порциями (FK Problem, Topic)
  90_similar_*   — through-таблица similar_problems порциями (грузить ПОСЛЕДНЕЙ)

Запуск:
    ./venv/bin/python manage.py dump_for_deploy --outdir deploy_fixtures --chunk 5000
"""

import json
import os

from django.apps import apps
from django.core import serializers
from django.core.management.base import BaseCommand

from problems.models import Problem

# Справочники без FK на Problem (грузятся первыми)
TIER1 = [
    'problems.User', 'problems.Topic', 'problems.Subtopic', 'problems.Tag',
    'problems.Source', 'problems.FileAsset', 'problems.Skill',
    'problems.MistakeTag', 'problems.Template',
    'problems.StudentGroup', 'problems.Job', 'problems.TheoryPage',
]

# Мелкие модели, зависящие от Problem/User (грузятся после Problem одним файлом)
TIER4_MISC = [
    'problems.ProblemVersion', 'problems.Hint', 'problems.Rubric',
    'problems.RubricCriterion', 'problems.StudentSkillProgress',
    'problems.Collection', 'problems.ExportRecord', 'problems.ImportSession',
    'problems.Lesson', 'problems.Assignment',
    # ⚠️ ПОРЯДОК ЗДЕСЬ ЗНАЧИМ, И ЭТИ ТРИ СТРОКИ ПОЯВИЛИСЬ НЕ ЗРЯ.
    # Заливка в ЧИСТУЮ PostgreSQL падала: `Submission.problem_item` ссылается
    # на `AssignmentItem`, а его в выгрузке не было вовсе:
    #   IntegrityError: Key (problem_item_id)=(18) is not present in table
    #   "problems_assignmentitem"
    # На SQLite это не воспроизводится (внешние ключи там не проверяются так
    # строго), а на проде строки уже лежали — поэтому дыра прожила незамеченной
    # до первой репетиции на чистой базе (сессия «Wecon Rush», фаза 8).
    # `AssignmentItem` тянет за собой `CustomProblem` и его варианты, иначе
    # дыра просто переезжает на шаг дальше. Замкнутость графа держит тест
    # problems/tests/test_deploy_dump.py.
    'problems.CustomProblem', 'problems.CustomProblemOption',
    'problems.SavedFolder', 'problems.SavedGraph',
    'problems.AssignmentItem',
    'problems.Submission',
    'problems.TeacherFeedback', 'problems.StudentTopicProgress',
    'problems.CalendarEvent',
]


def _clean_nul(value):
    """Рекурсивно убирает байт NUL (0x00) из строк — PostgreSQL его запрещает,
    а SQLite хранит. Невидимый мусорный символ, удаление безопасно."""
    if isinstance(value, str):
        return value.replace('\x00', '')
    if isinstance(value, list):
        return [_clean_nul(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean_nul(v) for k, v in value.items()}
    return value


def serialize_qs(qs, strip_fields=None):
    """Сериализует queryset в список dict, удаляя ненужные поля и NUL-байты."""
    data = json.loads(serializers.serialize('json', qs))
    for obj in data:
        if strip_fields:
            for f in strip_fields:
                obj['fields'].pop(f, None)
        obj['fields'] = _clean_nul(obj['fields'])
    return data


class Command(BaseCommand):
    help = 'Порционный дамп данных для деплоя (без embedding, similar отдельно)'

    def add_arguments(self, parser):
        parser.add_argument('--outdir', type=str, default='deploy_fixtures')
        parser.add_argument('--chunk', type=int, default=5000)

    def write_file(self, outdir, name, objects):
        path = os.path.join(outdir, name)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(objects, f, ensure_ascii=False)
        self.stdout.write(f'  {name}: {len(objects)} объектов')

    def dump_model_chunked(self, outdir, prefix, model_label, chunk, strip=None):
        """Дамп одной модели порциями по chunk объектов."""
        model = apps.get_model(*model_label.split('.'))
        qs = model.objects.all().order_by('pk')
        if model_label == 'problems.Problem':
            qs = qs.defer('embedding')
        total = qs.count()
        if total == 0:
            return
        n = 0
        idx = 0
        while n < total:
            batch = list(qs[n:n + chunk])
            data = serialize_qs(batch, strip_fields=strip)
            idx += 1
            self.write_file(outdir, f'{prefix}_{idx:04d}.json', data)
            n += len(batch)

    def handle(self, *args, **options):
        outdir = options['outdir']
        chunk = options['chunk']
        os.makedirs(outdir, exist_ok=True)

        # Чистим старые файлы
        for fn in os.listdir(outdir):
            if fn.endswith('.json'):
                os.remove(os.path.join(outdir, fn))

        self.stdout.write('TIER 1 — справочники:')
        ref_objects = []
        for label in TIER1:
            try:
                model = apps.get_model(*label.split('.'))
            except LookupError:
                continue
            ref_objects.extend(serialize_qs(model.objects.all()))
        self.write_file(outdir, '10_reference.json', ref_objects)

        self.stdout.write('TIER 2 — Problem (без embedding, без similar_problems):')
        self.dump_model_chunked(
            outdir, '20_problem', 'problems.Problem', chunk,
            strip=['embedding', 'similar_problems'],
        )

        self.stdout.write('TIER 3 — SourceReference / ProblemPart:')
        self.dump_model_chunked(outdir, '30_sourceref', 'problems.SourceReference', chunk)
        self.dump_model_chunked(outdir, '31_part', 'problems.ProblemPart', chunk)

        self.stdout.write('TIER 4 — мелкие связанные модели:')
        misc_objects = []
        for label in TIER4_MISC:
            try:
                model = apps.get_model(*label.split('.'))
            except LookupError:
                continue
            misc_objects.extend(serialize_qs(model.objects.all()))
        self.write_file(outdir, '40_misc.json', misc_objects)

        self.stdout.write('TIER 4b — DuplicateCandidate / AutoTopicAssignment:')
        self.dump_model_chunked(outdir, '50_dupcand', 'problems.DuplicateCandidate', chunk)
        self.dump_model_chunked(outdir, '51_autotopic', 'problems.AutoTopicAssignment', chunk)

        self.stdout.write('TIER 5 — similar_problems through (грузить ПОСЛЕДНЕЙ):')
        through = Problem.similar_problems.through
        through_label = through._meta.label
        qs = through.objects.all().order_by('pk')
        total = qs.count()
        n = idx = 0
        while n < total:
            batch = list(qs[n:n + chunk])
            data = json.loads(serializers.serialize('json', batch))
            idx += 1
            self.write_file(outdir, f'90_similar_{idx:04d}.json', data)
            n += len(batch)

        files = sorted(f for f in os.listdir(outdir) if f.endswith('.json'))
        self.stdout.write(self.style.SUCCESS(
            f'\nГотово: {len(files)} файлов в {outdir}/'
        ))
        self.stdout.write(f'through-модель: {through_label}')
