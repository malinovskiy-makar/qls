"""
Команда bulk_load_fixtures — быстрая загрузка фикстур через bulk_create.

В отличие от loaddata (1 INSERT на объект — сотни round-trip'ов, медленно
через внешний канал), здесь объекты вставляются пачками (batch_size=1000):
в ~1000 раз меньше обращений к БД → быстро даже через внешний URL Render.

- Читает .json и .json.gz из папки по порядку имён.
- Группирует по модели, bulk_create(..., ignore_conflicts=True) — идемпотентно,
  переживает частично загруженные данные (уже существующие PK пропускаются).
- M2M-связи (topics/tags/skills/mistakes/similar и др.) кладёт напрямую в
  through-таблицы пачками, тоже с ignore_conflicts.

Запуск (локально, против внешней базы Render):
    DATABASE_URL="postgresql://...?sslmode=require" \
    DJANGO_SETTINGS_MODULE=config.settings_production \
    SECRET_KEY="..." \
    ./venv/bin/python manage.py bulk_load_fixtures --dir deploy_fixtures
"""

import glob
import gzip
import json
import os

from django.apps import apps
from django.core.management.base import BaseCommand

BATCH = 1000


def read_fixture(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as fh:
        return json.load(fh)


class Command(BaseCommand):
    help = 'Быстрая загрузка фикстур через bulk_create (для внешней базы)'

    def add_arguments(self, parser):
        parser.add_argument('--dir', type=str, default='deploy_fixtures')

    def handle(self, *args, **options):
        directory = options['dir']
        files = sorted(glob.glob(os.path.join(directory, '*.json'))
                       + glob.glob(os.path.join(directory, '*.json.gz')))
        if not files:
            self.stderr.write(f'Нет файлов в {directory}/*.json[.gz]')
            return

        self.stdout.write(f'Файлов: {len(files)}')

        for idx, path in enumerate(files, 1):
            name = os.path.basename(path)
            data = read_fixture(path)
            if not data:
                continue
            # Файл может содержать несколько моделей (напр. 10_reference) —
            # группируем по модели, сохраняя порядок появления (порядок зависимостей).
            groups = {}
            for obj in data:
                groups.setdefault(obj['model'], []).append(obj)
            labels = ', '.join(f'{lbl.split(".")[-1]}={len(rows)}' for lbl, rows in groups.items())
            self.stdout.write(f'[{idx}/{len(files)}] {name}: {labels}')
            for model_label, rows in groups.items():
                model = apps.get_model(*model_label.split('.'))
                self._load_model(model, rows)

        self.stdout.write(self.style.SUCCESS('Готово.'))

    def _load_model(self, model, data):
        meta = model._meta
        # Классифицируем поля: concrete/FK (на объект) vs M2M (в through)
        m2m_names = {f.name for f in meta.many_to_many}
        fk_attnames = {}   # имя_поля_в_фикстуре -> attname (например source -> source_id)
        concrete_names = set()
        for f in meta.get_fields():
            if f.many_to_many or f.auto_created and not f.concrete:
                continue
            if getattr(f, 'many_to_one', False) or getattr(f, 'one_to_one', False):
                fk_attnames[f.name] = f.attname
            elif f.concrete and not f.auto_created:
                concrete_names.add(f.name)

        instances = []
        m2m_rows = {n: [] for n in m2m_names}  # field_name -> list of (obj_pk, related_pk)

        for obj in data:
            pk = obj['pk']
            fields = obj['fields']
            kwargs = {'pk': pk}
            for key, val in fields.items():
                if key in m2m_names:
                    for rel_pk in (val or []):
                        m2m_rows[key].append((pk, rel_pk))
                elif key in fk_attnames:
                    kwargs[fk_attnames[key]] = val
                else:
                    kwargs[key] = val
            instances.append(model(**kwargs))

        # Вставляем основные объекты пачками
        model.objects.bulk_create(instances, batch_size=BATCH, ignore_conflicts=True)

        # Вставляем M2M через through-таблицы
        for field_name, pairs in m2m_rows.items():
            if not pairs:
                continue
            field = meta.get_field(field_name)
            through = field.remote_field.through
            src_col = field.m2m_column_name()        # напр. problem_id
            tgt_col = field.m2m_reverse_name()        # напр. topic_id
            through_objs = [through(**{src_col: a, tgt_col: b}) for a, b in pairs]
            through.objects.bulk_create(through_objs, batch_size=BATCH, ignore_conflicts=True)
