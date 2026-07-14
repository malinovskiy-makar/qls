"""
Команда update_prod_problems — ТОЧЕЧНОЕ обновление существующих задач на
целевой БД (обычно — прод на Render) по заданному списку id.

Зачем нужна:
  bulk_load_fixtures вставляет через bulk_create(ignore_conflicts=True) — он
  ТОЛЬКО добавляет новые записи и пропускает существующие по PK. Поэтому правки
  ИИ-чистки ILE (изменённый текст/статус/флаги + пересобранные подпункты) в уже
  существующих задачах на прод НЕ доезжают. Эта команда их доставляет: UPDATE-ит
  поля Problem и пересобирает ProblemPart у перечисленных задач.

Источник истины — НЕ текущая БД, а свежая локальная выгрузка deploy_fixtures/*:
  - 20_problem_*.json[.gz]  — поля Problem (после всех батчей чистки);
  - 31_part_*.json[.gz]     — подпункты ProblemPart.
Команда читает оттуда «правильные» значения и применяет их к целевой БД по pk.

Поведение:
  - обновляет ТОЛЬКО задачи, которые есть и в фикстурах, и в целевой БД;
  - id, которых нет в целевой БД, НЕ создаёт (это точечное обновление) — выносит
    в отчёт «отсутствуют в целевой БД»;
  - id, которых нет в фикстурах, обновить нечем — выносит в «нет данных в фикстурах»;
  - подпункты: удаляет существующие ProblemPart задачи и создаёт заново из фикстуры
    (чтобы не было смеси старых/новых). Если к подпункту привязан Hint
    (on_delete=CASCADE) — пересборка для этой задачи ПРОПУСКАЕТСЯ (чтобы не удалить
    подсказки молча), задача попадает в отчёт;
  - вся запись — в одной transaction.atomic().

Запуск локально (против локальной SQLite — для проверки в dry-run):
    ./venv/bin/python manage.py update_prod_problems \
        --ids-file reports/ai_cleanup_ile/affected_ids.txt --dry-run

Запуск против прода (значения берутся из deploy_fixtures, пишутся в БД из DATABASE_URL):
    SECRET_KEY="любой" \
    DATABASE_URL="postgresql://...?sslmode=require" \
    DJANGO_SETTINGS_MODULE=config.settings_production \
    ./venv/bin/python manage.py update_prod_problems \
        --ids-file reports/ai_cleanup_ile/affected_ids.txt --dry-run   # сначала
    # затем то же без --dry-run
"""

import glob
import gzip
import json
import os
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from problems.models import Problem, ProblemPart

# Поля Problem по умолчанию для обновления (только скалярные/реально существующие).
DEFAULT_FIELDS = [
    'statement', 'answer', 'solution', 'status',
    'needs_quality_review', 'difficulty', 'difficulty_native',
]

# Поля ProblemPart, переносимые из фикстуры при пересоздании.
PART_FIELDS = ['label', 'statement', 'answer', 'solution', 'points', 'order']


def read_fixture(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as fh:
        return json.load(fh)


def _short(val, n=90):
    s = '' if val is None else str(val)
    s = s.replace('\n', ' ')
    return (s[:n] + '…') if len(s) > n else s


class Command(BaseCommand):
    help = ('Точечно обновляет существующие Problem (+ пересобирает ProblemPart) '
            'на целевой БД значениями из deploy_fixtures.')

    def add_arguments(self, parser):
        parser.add_argument('--ids-file', required=True,
                            help='Файл со списком id (по одному на строку; '
                                 'запятые/пробелы тоже допускаются).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Ничего не писать, только показать план.')
        parser.add_argument('--fields', nargs='+', default=DEFAULT_FIELDS,
                            help='Поля Problem для обновления (по умолчанию: '
                                 + ', '.join(DEFAULT_FIELDS) + ').')
        parser.add_argument('--fixtures-dir', default='deploy_fixtures',
                            help='Папка с фикстурами-источником (deploy_fixtures).')
        parser.add_argument('--skip-parts', action='store_true',
                            help='Не трогать подпункты (обновить только поля Problem).')

    # ── чтение входных данных ──────────────────────────────────────────────

    def _read_ids(self, path):
        if not os.path.exists(path):
            raise CommandError(f'Файл с id не найден: {path}')
        with open(path, encoding='utf-8') as fh:
            tokens = [t for t in re.split(r'[\s,]+', fh.read()) if t.strip()]
        ids = set()
        for t in tokens:
            try:
                ids.add(int(t))
            except ValueError:
                self.stderr.write(f'  пропускаю нечисловой токен: {t!r}')
        return ids

    def _validate_fields(self, requested):
        """Оставляет только реально существующие редактируемые скалярные поля."""
        concrete = {}
        for f in Problem._meta.get_fields():
            if f.many_to_many or (f.auto_created and not f.concrete):
                continue
            if f.name in ('id',):
                continue
            concrete[f.name] = f
        valid, dropped = [], []
        for name in requested:
            if name in concrete and name not in valid:
                valid.append(name)
            else:
                dropped.append(name)
        return valid, dropped

    def _load_fixture_problems(self, directory, wanted_ids):
        """pk -> fields (только для нужных id)."""
        out = {}
        files = sorted(glob.glob(os.path.join(directory, '20_problem_*.json'))
                       + glob.glob(os.path.join(directory, '20_problem_*.json.gz')))
        if not files:
            raise CommandError(
                f'Не нашёл 20_problem_*.json[.gz] в {directory}/ — '
                'нечем обновлять. Сначала собери дамп: dump_for_deploy.')
        for path in files:
            for obj in read_fixture(path):
                if obj.get('model') != 'problems.problem':
                    continue
                pk = obj['pk']
                if pk in wanted_ids:
                    out[pk] = obj['fields']
        return out

    def _load_fixture_parts(self, directory, wanted_ids):
        """problem_pk -> [part_fields, ...] в порядке (order, label)."""
        out = {}
        files = sorted(glob.glob(os.path.join(directory, '31_part_*.json'))
                       + glob.glob(os.path.join(directory, '31_part_*.json.gz')))
        for path in files:
            for obj in read_fixture(path):
                if obj.get('model') != 'problems.problempart':
                    continue
                ppk = obj['fields'].get('problem')
                if ppk in wanted_ids:
                    out.setdefault(ppk, []).append(obj['fields'])
        for ppk, rows in out.items():
            rows.sort(key=lambda r: (r.get('order') or 0, r.get('label') or ''))
        return out

    def _align_part_sequence(self):
        """PostgreSQL: явно выровнять sequence pk у ProblemPart к max(id), чтобы
        nextval() выдавал свободные id. setval/значения sequence НЕ откатываются
        транзакцией, но мы вызываем это внутри неё, после delete и перед insert.
        Печатает last_value до/после и max(id) — для контроля на проде."""
        with connection.cursor() as cur:
            cur.execute("SELECT pg_get_serial_sequence('problems_problempart', 'id')")
            row = cur.fetchone()
            seqname = row[0] if row else None
            if not seqname:
                self.stdout.write(self.style.WARNING(
                    '  ⚠ pg_get_serial_sequence вернул NULL — у problems_problempart.id '
                    'нет связанной последовательности; setval пропущен.'))
                return
            cur.execute('SELECT COALESCE(MAX(id), 1) FROM problems_problempart')
            max_id = cur.fetchone()[0]
            # seqname получен от самой БД (например public.problems_problempart_id_seq),
            # не пользовательский ввод — интерполяция в FROM безопасна.
            cur.execute('SELECT last_value, is_called FROM %s' % seqname)
            before = cur.fetchone()
            # setval(seq, max_id, true) → следующий nextval() вернёт max_id + 1
            cur.execute('SELECT setval(%s, %s, true)', [seqname, max_id])
            cur.execute('SELECT last_value, is_called FROM %s' % seqname)
            after = cur.fetchone()
        self.stdout.write(
            f'  sequence {seqname}: было {before}, max(id)={max_id}, '
            f'стало {after} → следующий id = {max_id + 1}')

    # ── основной обработчик ────────────────────────────────────────────────

    def handle(self, *args, **options):
        dry = options['dry_run']
        directory = options['fixtures_dir']
        skip_parts = options['skip_parts']

        wanted = self._read_ids(options['ids_file'])
        self.stdout.write(f'Запрошено id: {len(wanted)}')

        fields, dropped = self._validate_fields(options['fields'])
        if dropped:
            self.stderr.write('  ⚠ отброшены несуществующие поля: '
                              + ', '.join(dropped))
        self.stdout.write('Поля Problem к обновлению: ' + ', '.join(fields))
        self.stdout.write(f'Подпункты: {"НЕ трогаем" if skip_parts else "пересобираем"}')

        # 1) источник истины — фикстуры
        fx_problems = self._load_fixture_problems(directory, wanted)
        fx_parts = ({} if skip_parts
                    else self._load_fixture_parts(directory, wanted))

        missing_in_fixtures = sorted(wanted - set(fx_problems))

        # 2) что реально есть в целевой БД
        in_fixtures = wanted & set(fx_problems)
        existing_pks = set(
            Problem.objects.filter(pk__in=in_fixtures).values_list('pk', flat=True)
        )
        missing_in_target = sorted(in_fixtures - existing_pks)
        to_update = sorted(existing_pks)

        self.stdout.write('')
        self.stdout.write(f'Есть в фикстурах:        {len(in_fixtures)}')
        self.stdout.write(f'Нет данных в фикстурах:   {len(missing_in_fixtures)}')
        self.stdout.write(f'Будет обновлено (Problem):{len(to_update)}')
        self.stdout.write(f'Отсутствуют в целевой БД: {len(missing_in_target)}')

        # 3) загружаем инстансы целевой БД, считаем diff по полям
        objs = {p.pk: p for p in Problem.objects.filter(pk__in=to_update)}
        field_change_counts = {f: 0 for f in fields}
        examples = []
        instances_to_save = []

        for pk in to_update:
            p = objs[pk]
            fx = fx_problems[pk]
            changed_here = []
            for f in fields:
                if f not in fx:
                    continue
                new_val = fx[f]
                old_val = getattr(p, f)
                if old_val != new_val:
                    field_change_counts[f] += 1
                    changed_here.append((f, old_val, new_val))
                    setattr(p, f, new_val)
            if changed_here:
                instances_to_save.append(p)
                if len(examples) < 3 and any(c[0] == 'statement' for c in changed_here):
                    examples.append((pk, changed_here))

        # 4) план по подпунктам (+ защита от удаления Hint)
        parts_delete_total = 0
        parts_create_total = 0
        blocked_by_hints = []
        parts_plan = {}  # pk -> (existing_count, new_rows)
        if not skip_parts:
            for pk in to_update:
                new_rows = fx_parts.get(pk, [])
                existing = list(ProblemPart.objects.filter(problem_id=pk))
                # если новых нет и старых нет — нечего делать
                if not new_rows and not existing:
                    continue
                has_hints = ProblemPart.objects.filter(
                    problem_id=pk, hints__isnull=False).exists()
                if has_hints:
                    blocked_by_hints.append(pk)
                    continue
                parts_plan[pk] = (len(existing), new_rows)
                parts_delete_total += len(existing)
                parts_create_total += len(new_rows)

        # ── ОТЧЁТ ──────────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write('── Изменения полей Problem ──')
        for f in fields:
            self.stdout.write(f'  {f}: меняется у {field_change_counts[f]} задач')
        self.stdout.write(f'  (итого задач с ≥1 изменённым полем: {len(instances_to_save)})')

        if not skip_parts:
            self.stdout.write('')
            self.stdout.write('── Подпункты ──')
            self.stdout.write(f'  задач с пересборкой подпунктов: {len(parts_plan)}')
            self.stdout.write(f'  будет удалено ProblemPart:      {parts_delete_total}')
            self.stdout.write(f'  будет создано ProblemPart:      {parts_create_total}')
            if blocked_by_hints:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠ пропущены (к подпунктам привязаны Hint): '
                    f'{len(blocked_by_hints)} -> {blocked_by_hints[:20]}'
                    + (' …' if len(blocked_by_hints) > 20 else '')))

        if missing_in_target:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('── Отсутствуют в целевой БД (НЕ создаём) ──'))
            self.stdout.write('  ' + ', '.join(map(str, missing_in_target)))
        if missing_in_fixtures:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('── Нет данных в фикстурах (нечем обновлять) ──'))
            self.stdout.write('  ' + ', '.join(map(str, missing_in_fixtures)))

        # примеры diff по statement
        if examples:
            self.stdout.write('')
            self.stdout.write('── Примеры diff (statement) ──')
            for pk, changes in examples:
                for f, old, new in changes:
                    if f != 'statement':
                        continue
                    self.stdout.write(f'  #{pk} statement:')
                    self.stdout.write(f'      БЫЛО: {_short(old)}')
                    self.stdout.write(f'      СТАЛО:{_short(new)}')

        # пробы из задания: 2158 / 494 / 2120
        self.stdout.write('')
        self.stdout.write('── Контрольные задачи 2158 / 494 / 2120 ──')
        for pk in (2158, 494, 2120):
            if pk not in objs:
                where = ('нет в фикстурах' if pk in missing_in_fixtures
                         else 'нет в целевой БД' if pk in missing_in_target
                         else 'нет в списке id')
                self.stdout.write(f'  #{pk}: {where}')
                continue
            fx = fx_problems[pk]
            # объект уже мутирован (setattr) — для показа берём из фикстуры/факта
            line = [f'  #{pk}:']
            if 'statement' in fx:
                line.append(f"statement→ {_short(fx['statement'], 60)}")
            if 'status' in fx:
                line.append(f"status→{fx['status']}")
            if 'needs_quality_review' in fx:
                line.append(f"nqr→{fx['needs_quality_review']}")
            self.stdout.write(' '.join(line))
            if not skip_parts:
                ex = ProblemPart.objects.filter(problem_id=pk).count()
                nw = len(fx_parts.get(pk, []))
                blk = ' [ПРОПУСК: Hint]' if pk in blocked_by_hints else ''
                self.stdout.write(f'        подпункты: было {ex} → станет {nw}{blk}')

        # ── ЗАПИСЬ ─────────────────────────────────────────────────────────
        if dry:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(
                'DRY-RUN: ничего не записано. Уберите --dry-run для применения.'))
            return

        self.stdout.write('')
        self.stdout.write('Применяю изменения…')
        with transaction.atomic():
            # Поля Problem — обновление по СУЩЕСТВУЮЩЕМУ pk (новые строки не создаём).
            if instances_to_save:
                Problem.objects.bulk_update(instances_to_save, fields, batch_size=500)

            if not skip_parts and parts_plan:
                batch_ids = list(parts_plan.keys())

                # 1) Удаляем старые подпункты обновляемых задач ОДНИМ запросом —
                #    ДО вставки новых, в той же транзакции.
                ProblemPart.objects.filter(problem_id__in=batch_ids).delete()

                # 2) Собираем новые подпункты БЕЗ собственного id/pk — его присвоит
                #    БД (автоинкремент). Из фикстуры берём только содержательные поля;
                #    привязка к задаче идёт по problem_id, id подпункта не важен.
                new_objs = []
                for pk in batch_ids:
                    _, new_rows = parts_plan[pk]
                    for r in new_rows:
                        new_objs.append(ProblemPart(
                            problem_id=pk,
                            label=r.get('label') or '',
                            statement=r.get('statement') or '',
                            answer=r.get('answer') or '',
                            solution=r.get('solution') or '',
                            points=r.get('points'),
                            order=r.get('order') or 0,
                        ))

                # 3) Выравниваем последовательность pk у ProblemPart.
                #    Корень бага: bulk_load_fixtures грузил подпункты с ЯВНЫМИ id и
                #    НЕ двигал sequence, поэтому nextval() начинает с 1/2 и упирается
                #    в существующие строки (UniqueViolation pkey). Прежний
                #    connection.ops.sequence_reset_sql() счётчик не выровнял (ошибка
                #    лишь сдвигалась 1→2). Поэтому делаем ЯВНЫЙ setval по max(id) и
                #    печатаем значения до/после — боевой прогон сам это подтвердит.
                #    На SQLite не нужно (high-water mark ведёт сама БД).
                if connection.vendor == 'postgresql':
                    self._align_part_sequence()

                # 4) Вставляем новые подпункты (id назначит БД).
                if new_objs:
                    ProblemPart.objects.bulk_create(new_objs, batch_size=500)

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Обновлено Problem: {len(instances_to_save)}; '
            f'задач с пересобранными подпунктами: {len(parts_plan)} '
            f'(удалено {parts_delete_total}, создано {parts_create_total}).'))
