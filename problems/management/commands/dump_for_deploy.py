"""
Команда dump_for_deploy — создаёт JSON-дамп данных для деплоя на PostgreSQL.

Исключает поле Problem.embedding (46 МБ binary → слишком большой дамп).
Эмбеддинги не нужны на продакшене: похожие задачи работают по кэшу M2M.

Запуск:
    ./venv/bin/python manage.py dump_for_deploy -o data_dump.json
    ./venv/bin/python manage.py dump_for_deploy  # вывод в stdout
"""

import json

from django.core import serializers
from django.core.management.base import BaseCommand

from problems.models import Problem

# Модели, которые дампаем ОТДЕЛЬНО (без поля embedding)
EXCLUDE_FIELDS = {
    'problems.problem': {'embedding'},
}

# Приложения/модели для стандартного дампа (всё кроме системного мусора и Problem)
STANDARD_APPS = [
    'problems.User',
    'problems.Topic',
    'problems.Subtopic',
    'problems.Tag',
    'problems.Source',
    'problems.FileAsset',
    'problems.Skill',
    'problems.MistakeTag',
    'problems.TheoryPage',
    'problems.Rubric',
    'problems.RubricCriterion',
    'problems.Hint',
    'problems.StudentSkillProgress',
    'problems.ProblemVersion',
    'problems.Collection',
    'problems.Job',
    'problems.Template',
    'problems.ExportRecord',
    'problems.ImportSession',
    'problems.Lesson',
    'problems.Assignment',
    'problems.Submission',
    'problems.TeacherFeedback',
    'problems.StudentTopicProgress',
    'problems.DuplicateCandidate',
    'problems.DesmosGraph',
    'problems.CalendarEvent',
    'problems.StudentGroup',
    'problems.AutoTopicAssignment',
    'auth.Group',
    'auth.Permission',
    'sessions.Session',
]


class Command(BaseCommand):
    help = 'Дамп данных для деплоя (без поля embedding)'

    def add_arguments(self, parser):
        parser.add_argument(
            '-o', '--output', type=str, default=None,
            help='Файл для сохранения (по умолчанию — stdout)'
        )

    def handle(self, *args, **options):
        self.stdout.write('Собираем дамп без поля embedding...')

        all_objects = []

        # 1. Стандартные модели
        for model_label in STANDARD_APPS:
            try:
                from django.apps import apps
                app_label, model_name = model_label.rsplit('.', 1)
                model = apps.get_model(app_label, model_name)
                qs = model.objects.all()
                count = qs.count()
                if count:
                    data = json.loads(serializers.serialize('json', qs))
                    all_objects.extend(data)
                    self.stdout.write(f'  {model_label}: {count} объектов')
            except LookupError:
                self.stdout.write(self.style.WARNING(f'  {model_label}: модель не найдена, пропускаем'))

        # 2. Problem — без поля embedding
        self.stdout.write('  problems.Problem: без поля embedding...')
        problems_qs = Problem.objects.all().defer('embedding')
        problem_data = []
        BATCH = 500
        total = problems_qs.count()
        processed = 0

        for i in range(0, total, BATCH):
            batch = problems_qs[i:i + BATCH]
            batch_json = json.loads(serializers.serialize('json', batch))
            # Удаляем поле embedding из каждого объекта
            for obj in batch_json:
                obj['fields'].pop('embedding', None)
            problem_data.extend(batch_json)
            processed += len(batch_json)
            if processed % 5000 == 0 or processed == total:
                self.stdout.write(f'    {processed}/{total}')

        all_objects.extend(problem_data)
        self.stdout.write(f'  problems.Problem: {total} объектов (embedding исключён)')

        # 3. M2M-связи Problem (topics, tags, skills, mistakes, similar_problems)
        # Они хранятся в промежуточных таблицах и сериализуются вместе с Problem,
        # но django serializer их включает автоматически через Many2Many.
        # Проверим что similar_problems (SymmetricalFalse) тоже в дампе.

        result_json = json.dumps(all_objects, ensure_ascii=False, indent=2)

        output_path = options.get('output')
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(result_json)
            size_mb = len(result_json.encode('utf-8')) / 1024 / 1024
            self.stdout.write(self.style.SUCCESS(
                f'\nДамп сохранён: {output_path} ({size_mb:.1f} МБ)'
            ))
            self.stdout.write(f'Всего объектов: {len(all_objects)}')
        else:
            self.stdout.write(result_json)
