"""apply_ile_cleanup — применить ИИ-правки к задачам ILE (#2).

Поддерживает два формата файла правок:
  Пилот-формат:  {"meta": {...}, "tasks": [{id, statement?, solution?, parts?}, ...]}
  Батч-формат:   {"meta": {..., "hide": [...], "manual": [...]},
                  "tasks": {"id_str": {statement?, solution?, answer?, parts?}, ...}}

Использование:
    ./venv/bin/python manage.py apply_ile_cleanup            # боевой прогон
    ./venv/bin/python manage.py apply_ile_cleanup --dry-run  # план без записи
    ./venv/bin/python manage.py apply_ile_cleanup \
        --patch reports/ai_cleanup_ile/batch01_apply.json    # указать файл
"""

import json
import os
import tempfile
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.models import Problem, ProblemPart, SourceReference

ILE_SOURCE_ID = 2
DEFAULT_PATCH = 'reports/ai_cleanup_ile/pilot_apply_v1.json'
BACKUP_DIR = 'reports/ai_cleanup_ile'


class Command(BaseCommand):
    help = 'Применить ИИ-правки к задачам ILE (#2) из JSON-файла правок.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--patch', default=DEFAULT_PATCH,
            help=f'Путь к файлу правок (по умолчанию: {DEFAULT_PATCH})'
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только показать план изменений, ничего не записывать.'
        )

    # ------------------------------------------------------------------
    # нормализация формата
    # ------------------------------------------------------------------

    def _parse_patch(self, data):
        """
        Нормализует оба формата в единую структуру:
          tasks_list: [{'id': int, 'statement'?, 'solution'?, 'answer'?, 'parts'?}, ...]
          hide_ids:   [int, ...]   — скрыть (status='hidden')
          manual_ids: [int, ...]   — пропустить
        """
        raw_tasks = data.get('tasks', {})
        meta = data.get('meta', {})

        # Определяем формат: список (пилот) или dict (батч)
        if isinstance(raw_tasks, list):
            # Пилот-формат: [{id, ...}, ...]
            tasks_list = [dict(t) for t in raw_tasks]
            for t in tasks_list:
                t['id'] = int(t['id'])
        elif isinstance(raw_tasks, dict):
            # Батч-формат: {"id_str": {...}, ...}
            tasks_list = []
            for str_id, fields in raw_tasks.items():
                entry = dict(fields)
                entry['id'] = int(str_id)
                tasks_list.append(entry)
        else:
            raise CommandError('Поле "tasks" должно быть списком или словарём.')

        hide_ids = [int(i) for i in meta.get('hide', [])]
        manual_ids = [int(i) for i in meta.get('manual', [])]

        return tasks_list, hide_ids, manual_ids

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _load_patch(self, path):
        if not os.path.exists(path):
            raise CommandError(f'Файл правок не найден: {path}')
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)

    def _verify_ids(self, all_ids):
        """Проверить, что все id существуют и принадлежат ILE (#2)."""
        existing = set(Problem.objects.filter(id__in=all_ids)
                       .values_list('id', flat=True))
        missing = set(all_ids) - existing
        if missing:
            raise CommandError(
                f'Следующие id не найдены в базе: {sorted(missing)}'
            )

        ile_ids = set(
            SourceReference.objects
            .filter(problem_id__in=all_ids, source_id=ILE_SOURCE_ID)
            .values_list('problem_id', flat=True)
        )
        not_ile = set(all_ids) - ile_ids
        if not_ile:
            raise CommandError(
                f'Следующие id НЕ принадлежат источнику ILE (#{ILE_SOURCE_ID}): '
                f'{sorted(not_ile)}'
            )

    def _make_backup(self, all_ids, hide_ids):
        """Сохранить текущее состояние всех затронутых задач."""
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(BACKUP_DIR, f'backup_before_apply_{ts}.json')

        problems_qs = (Problem.objects.prefetch_related('parts')
                       .filter(id__in=all_ids))
        backup = []
        for p in problems_qs:
            parts_data = []
            for part in p.parts.order_by('order', 'label'):
                parts_data.append({
                    'id': part.id,
                    'label': part.label,
                    'statement': part.statement,
                    'answer': part.answer,
                    'solution': part.solution,
                    'points': str(part.points) if part.points is not None else None,
                    'order': part.order,
                })
            backup.append({
                'id': p.id,
                'status': p.status,
                'answer': p.answer,
                'statement': p.statement,
                'solution': p.solution,
                'parts': parts_data,
                'will_be_hidden': p.id in hide_ids,
            })

        with open(backup_path, 'w', encoding='utf-8') as fh:
            json.dump(backup, fh, ensure_ascii=False, indent=2)
        return backup_path

    def _check_part_dependencies(self, tasks_list):
        """Проверить Hint.part перед пересозданием подпунктов."""
        blocking = {}
        for task in tasks_list:
            if 'parts' not in task:
                continue
            for part in ProblemPart.objects.filter(problem_id=task['id']):
                if part.hints.exists():
                    blocking.setdefault(task['id'], []).append(part.id)
        return blocking

    # ------------------------------------------------------------------
    # apply single task
    # ------------------------------------------------------------------

    def _apply_task(self, task, dry_run):
        """
        Применяет правки одной задачи. При dry_run — только вычисляет план.
        Возвращает список строк-описаний изменений.
        """
        problem_id = task['id']
        p = Problem.objects.get(id=problem_id)
        changed = []
        save_fields = []

        if 'statement' in task:
            preview = (task['statement'] or '')[:80]
            changed.append(f'statement → {preview!r}...')
            if not dry_run:
                p.statement = task['statement']
                save_fields.append('statement')

        if 'solution' in task:
            if task['solution'] == '':
                changed.append('solution → "" (очистить)')
            else:
                changed.append(f'solution ({len(task["solution"])} симв.)')
            if not dry_run:
                p.solution = task['solution']
                save_fields.append('solution')

        # answer на уровне задачи (без подпунктов) → Problem.answer
        if 'answer' in task and 'parts' not in task:
            val = task['answer']
            changed.append(f'answer → {val!r}  [→ Problem.answer]')
            if not dry_run:
                p.answer = val
                save_fields.append('answer')

        if 'parts' in task:
            new_parts = task['parts']
            existing_count = p.parts.count()
            changed.append(
                f'parts: удалить {existing_count}, создать {len(new_parts)}'
            )
            for pp in new_parts:
                label = pp.get('label', '?')
                stmt = (pp.get('statement') or '')[:70]
                ans = pp.get('answer') or ''
                pts = pp.get('points')
                changed.append(
                    f'    [{label}] {stmt!r}'
                    + (f'  ответ={ans!r}' if ans else '')
                    + (f'  баллы={pts}' if pts is not None else '')
                )
            if not dry_run:
                p.parts.all().delete()
                for i, part_data in enumerate(new_parts):
                    ProblemPart.objects.create(
                        problem=p,
                        label=part_data['label'],
                        statement=part_data.get('statement') or '',
                        answer=part_data.get('answer') or '',
                        points=part_data.get('points'),  # None разрешён
                        order=i,
                    )

        if not dry_run and save_fields:
            p.save(update_fields=save_fields)

        return changed

    # ------------------------------------------------------------------
    # embeddings
    # ------------------------------------------------------------------

    def _rebuild_embeddings(self, ids):
        """Вызвать night_embeddings для списка id."""
        try:
            from django.core.management import call_command
            tmp = tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', delete=False,
                prefix='ile_cleanup_emb_'
            )
            tmp.write('\n'.join(str(i) for i in sorted(ids)))
            tmp.close()
            self.stdout.write(
                f'\n[эмбеддинги] Запускаю night_embeddings для {len(ids)} задач...'
            )
            call_command('night_embeddings', ids_file=[tmp.name])
            os.unlink(tmp.name)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f'\n⚠  Эмбеддинги НЕ пересчитаны: {exc}\n'
                f'Запустите вручную:\n'
                f'  ./venv/bin/python manage.py night_embeddings '
                f'--ids-file <файл со списком id>\n'
                f'ID для пересчёта: {sorted(ids)}'
            ))

    # ------------------------------------------------------------------
    # main
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        patch_path = options['patch']

        # 1. Загрузка и нормализация
        self.stdout.write(f'Загружаю файл правок: {patch_path}')
        data = self._load_patch(patch_path)
        tasks_list, hide_ids, manual_ids = self._parse_patch(data)

        if not tasks_list and not hide_ids:
            raise CommandError('Файл правок пуст: нет ни tasks, ни hide.')

        # Задачи из manual — пропускаем (не обрабатываем, не скрываем)
        if manual_ids:
            self.stdout.write(
                f'[manual] Пропускаю {len(manual_ids)} задач (ручной разбор): '
                f'{sorted(manual_ids)}'
            )
        task_ids = [t['id'] for t in tasks_list]
        # Исключаем manual из tasks (на случай если вдруг попали)
        tasks_list = [t for t in tasks_list if t['id'] not in manual_ids]
        task_ids = [t['id'] for t in tasks_list]

        self.stdout.write(
            f'tasks: {len(tasks_list)}  |  hide: {len(hide_ids)}  |  '
            f'manual (пропущено): {len(manual_ids)}'
        )

        # 2. Проверить все id (tasks + hide)
        all_ids = list(set(task_ids + hide_ids))
        if all_ids:
            self.stdout.write('Проверяю существование и принадлежность ILE (#2)...')
            self._verify_ids(all_ids)
            self.stdout.write(self.style.SUCCESS('✓ Все id найдены и принадлежат ILE.'))

        # 3. Бэкап — ДО изменений, только не при --dry-run
        if not dry_run and all_ids:
            backup_path = self._make_backup(all_ids, set(hide_ids))
            self.stdout.write(self.style.SUCCESS(f'✓ Бэкап сохранён: {backup_path}'))

        # 4. Проверить Hint.part перед пересозданием подпунктов
        self.stdout.write('Проверяю Hint.part зависимости...')
        blocking = self._check_part_dependencies(tasks_list)
        if blocking:
            lines = [
                f'  Задача #{pid}: подпункты {pids}'
                for pid, pids in blocking.items()
            ]
            raise CommandError(
                'Нельзя пересоздать подпункты — к ним привязаны Hint-подсказки:\n'
                + '\n'.join(lines)
                + '\nИсправьте вручную и повторите.'
            )
        self.stdout.write(self.style.SUCCESS('✓ Hint.part зависимостей нет.'))

        # 5. DRY-RUN: показать план
        if dry_run:
            self._print_dry_run(tasks_list, hide_ids)
            return

        # 6. Применить в транзакции
        self.stdout.write('\nПрименяю в одной транзакции...')
        with transaction.atomic():
            # 6a. Скрыть задачи
            if hide_ids:
                hidden_count = Problem.objects.filter(id__in=hide_ids).update(
                    status=Problem.Status.HIDDEN
                )
                self.stdout.write(
                    f'  [hide] скрыто {hidden_count} задач: {sorted(hide_ids)}'
                )

            # 6b. Применить правки
            for task in tasks_list:
                self._apply_task(task, dry_run=False)
                self.stdout.write(f'  ✓ #{task["id"]}')

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Готово: правок {len(tasks_list)}, скрыто {len(hide_ids)}.'
        ))

        # 7. Пересчёт эмбеддингов для всех затронутых
        all_touched = list(set(task_ids + hide_ids))
        if all_touched:
            self._rebuild_embeddings(all_touched)

        self.stdout.write(self.style.SUCCESS('Всё завершено.'))

    # ------------------------------------------------------------------
    # dry-run вывод
    # ------------------------------------------------------------------

    def _print_dry_run(self, tasks_list, hide_ids):
        self.stdout.write('\n' + '═' * 64)
        self.stdout.write('[DRY-RUN] ПЛАН ИЗМЕНЕНИЙ')
        self.stdout.write('═' * 64)

        # Скрытие
        if hide_ids:
            self.stdout.write(f'\n[HIDE] Скрыть (status → hidden): {sorted(hide_ids)}')
            probs = Problem.objects.filter(id__in=hide_ids).values('id', 'status', 'statement')
            for p in probs:
                stmt = (p['statement'] or '')[:60]
                self.stdout.write(
                    f'  #{p["id"]} (сейчас: {p["status"]}) — {stmt!r}...'
                )

        # Tasks
        n_stmt = n_sol = n_ans = n_parts_tasks = n_new_parts = n_old_parts = 0

        self.stdout.write(f'\n[TASKS] {len(tasks_list)} задач:')
        for task in tasks_list:
            pid = task['id']
            p = Problem.objects.prefetch_related('parts').get(id=pid)
            changes = self._apply_task(task, dry_run=True)
            self.stdout.write(f'\n  #{pid}:')
            for line in changes:
                self.stdout.write(f'    • {line}')
                if line.startswith('statement'):
                    n_stmt += 1
                elif line.startswith('solution'):
                    n_sol += 1
                elif line.startswith('answer'):
                    n_ans += 1
                elif line.startswith('parts:'):
                    n_parts_tasks += 1
                    # parse "удалить X, создать Y"
                    try:
                        parts_str = line.split('удалить ')[1].split(',')[0]
                        n_old_parts += int(parts_str)
                        new_str = line.split('создать ')[1]
                        n_new_parts += int(new_str)
                    except (IndexError, ValueError):
                        pass

        self.stdout.write('\n' + '─' * 64)
        self.stdout.write('[DRY-RUN] СВОДКА:')
        self.stdout.write(f'  hide (скрыть):                {len(hide_ids)}')
        self.stdout.write(f'  tasks (правок):               {len(tasks_list)}')
        self.stdout.write(f'    из них statement:           {n_stmt}')
        self.stdout.write(f'    из них solution:            {n_sol}')
        self.stdout.write(f'    из них answer (→ Problem):  {n_ans}')
        self.stdout.write(f'    из них parts (задач):       {n_parts_tasks}')
        self.stdout.write(f'      подпунктов удалить:       {n_old_parts}')
        self.stdout.write(f'      подпунктов создать:       {n_new_parts}')
        self.stdout.write(
            '\nДля реального применения запустите БЕЗ --dry-run.'
        )
