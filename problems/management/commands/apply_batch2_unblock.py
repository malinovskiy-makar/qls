# -*- coding: utf-8 -*-
"""
Применение разблокировки группы Б (97 задач: 67 «конфликт решения» + 30
«неизвестная метка», по вердикту Макара на preview.html — секция
«подозрительное сокращение» (26) НЕ применяется).

Источник списков — reports/batch2_unblock/to_apply_conflict_solution.txt и
to_apply_unknown_label.txt (пишет preview_batch2_unblock, тот же порядок id
→ номера карточек в превью совпадают с номерами в отчётах этой команды).

Конвейер на каждую задачу — problems.batch2_unblock.build_apply_pipeline:
classify (problems/batch2_unblock.py) → БЕЗ solution (эта сессия ни одно
solution не пишет, только конфликт-лог) → нормализация кавычек → фильтр
палочек (карточка целиком в остаток при новых '|') → glue_field.

Без --confirm — только предпросмотр в консоль (что было бы применено/
исключено), база не меняется. С --confirm — бэкап + запись + обязательные
контроли (идемпотентность склейки, solution не тронут).
"""
import json
import os
import shutil
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.batch2_unblock import build_apply_pipeline, glue_field
from problems.management.commands.apply_batch2 import _load_parsed, _problem_id
from problems.models import Problem, ProblemPart

SRC_DIR = 'reports/batch2_unblock'
PARSED_FILE = 'batch2_parsed.jsonl'

CATEGORY_FILES = [
    ('conflict_solution', 'to_apply_conflict_solution.txt'),
    ('unknown_label', 'to_apply_unknown_label.txt'),
]


def _load_ids(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [int(x.strip()) for x in f if x.strip()]


class Command(BaseCommand):
    help = ('Применить разблокированные правки группы Б (97 задач). '
            'Без --confirm — только предпросмотр, база не меняется.')

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='Записать изменения в базу (по умолчанию dry-run).')

    def handle(self, *args, **opts):
        confirm = opts['confirm']
        os.makedirs(SRC_DIR, exist_ok=True)

        records = _load_parsed(PARSED_FILE)
        by_id = {}
        for r in records:
            pid = _problem_id(r['custom_id'])
            if pid is not None:
                by_id[pid] = r

        all_ids = set()
        cat_ids = {}
        for key, fname in CATEGORY_FILES:
            ids = _load_ids(os.path.join(SRC_DIR, fname))
            cat_ids[key] = ids
            all_ids.update(ids)

        problems = {
            p.pk: p for p in
            Problem.objects.filter(pk__in=list(all_ids)).prefetch_related('parts')
        }

        to_write = []       # (pid, category, number, final_changes)
        excluded_rows = []  # (category, number, pid, reason)
        unexpected_rows = []  # записи, которые в превью были apply=True, а теперь нет

        for key, _ in CATEGORY_FILES:
            for number, pid in enumerate(cat_ids[key], start=1):
                problem = problems.get(pid)
                rec = by_id.get(pid)
                if problem is None or rec is None:
                    unexpected_rows.append((key, number, pid, 'missing_data'))
                    continue
                final, exclude_reason, _extracted = build_apply_pipeline(
                    problem, rec, key)
                if exclude_reason:
                    excluded_rows.append((key, number, pid, exclude_reason))
                    continue
                if final is None:
                    unexpected_rows.append((key, number, pid, 'no_changes_on_recheck'))
                    continue
                to_write.append((pid, key, number, final))

        self.stdout.write('К применению: {} (конфликт решения: {}, неизвестная метка: {})'.format(
            len(to_write),
            sum(1 for _, k, _, _ in to_write if k == 'conflict_solution'),
            sum(1 for _, k, _, _ in to_write if k == 'unknown_label')))
        self.stdout.write('Исключено фильтром палочек: {}'.format(len(excluded_rows)))
        for key, number, pid, reason in excluded_rows:
            self.stdout.write('  №{} #{} ({}) — {}'.format(number, pid, key, reason))
        if unexpected_rows:
            self.stdout.write(self.style.WARNING(
                'ВНИМАНИЕ: {} записей расходятся с превью (перепроверка изменила '
                'вердикт) — не применяются:'.format(len(unexpected_rows))))
            for key, number, pid, reason in unexpected_rows:
                self.stdout.write('  №{} #{} ({}) — {}'.format(number, pid, key, reason))

        self._write_excluded_md(excluded_rows, unexpected_rows)

        if not confirm:
            self.stdout.write('Режим dry-run: база НЕ изменена. Для записи добавьте --confirm.')
            return

        self._apply(to_write, problems)

    # ── Отчёт об исключённых ────────────────────────────────────────────────

    def _write_excluded_md(self, excluded_rows, unexpected_rows):
        path = os.path.join(SRC_DIR, 'excluded_pipes.md')
        lines = ['# Разблокировка группы Б — исключено фильтром палочек', '',
                'Правка вносит символ «|» как разделитель вне формул, которого не '
                'было в текущем тексте — суррогат таблицы палочками, карточка '
                'исключена целиком. Номера — из preview.html (та же нумерация, '
                'тот же порядок id).', '']
        if not excluded_rows:
            lines.append('Пусто — фильтр не сработал ни разу.')
        for key, number, pid, reason in excluded_rows:
            lines.append('- №{} [#{}](http://127.0.0.1:8000/catalog/problem/{}/) '
                        '({}) — `{}`'.format(number, pid, pid, key, reason))
        if unexpected_rows:
            lines.append('')
            lines.append('## Разошлись с превью при перепроверке (не применены)')
            for key, number, pid, reason in unexpected_rows:
                lines.append('- №{} #{} ({}) — `{}`'.format(number, pid, key, reason))
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        self.stdout.write('Исключения → {}'.format(path))

    # ── Применение ───────────────────────────────────────────────────────────

    def _apply(self, to_write, problems):
        from django.db import connection
        db_path = str(connection.settings_dict.get('NAME') or '')
        if os.path.basename(db_path) == 'db.sqlite3' and os.path.exists(db_path):
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            os.makedirs('backups', exist_ok=True)
            bk = os.path.join('backups', 'before_batch2_unblock_{}.sqlite3'.format(ts))
            shutil.copy2(db_path, bk)
            self.stdout.write('Бэкап базы (sqlite) → {}'.format(bk))

        # JSON-бэкап полей, что изменятся, + solution ВСЕХ затронутых задач
        # (не меняется этой сессией никогда, но контроль 3 обязан сверить
        # снимок с базой ПОСЛЕ, а не поверить конвейеру на слово).
        backup = {'problems': {}, 'parts': {}, 'solution': {}}
        for pid, key, number, final in to_write:
            problem = problems[pid]
            if 'stmt' in final and str(pid) not in backup['problems']:
                backup['problems'][str(pid)] = problem.statement or ''
            if 'parts' in final:
                by_pk = {p.pk: p for p in problem.parts.all()}
                for pk in final['parts']:
                    if str(pk) not in backup['parts']:
                        backup['parts'][str(pk)] = (by_pk[pk].statement or '') if pk in by_pk else ''
            if str(pid) not in backup['solution']:
                backup['solution'][str(pid)] = problem.solution or ''

        ts = datetime.now().strftime('%Y%m%d')
        backup_path = os.path.join(SRC_DIR, 'backup_apply_{}.json'.format(ts))
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(backup, f, ensure_ascii=False, indent=1)
        with open(backup_path, encoding='utf-8') as f:
            reloaded = json.load(f)
        assert len(reloaded['problems']) == len(backup['problems'])
        assert len(reloaded['parts']) == len(backup['parts'])
        assert len(reloaded['solution']) == len(backup['solution'])
        self.stdout.write('Бэкап полей (JSON) → {} (problems: {}, parts: {}, '
                          'solution-снимков: {})'.format(
                              backup_path, len(backup['problems']),
                              len(backup['parts']), len(backup['solution'])))

        stmt_map = {}
        part_map = {}
        for pid, key, number, final in to_write:
            if 'stmt' in final:
                stmt_map[pid] = final['stmt']
            if 'parts' in final:
                part_map.update(final['parts'])

        with transaction.atomic():
            if stmt_map:
                updates = []
                for p in Problem.objects.filter(id__in=list(stmt_map.keys())):
                    p.statement = stmt_map[p.id]
                    updates.append(p)
                Problem.objects.bulk_update(updates, ['statement'], batch_size=500)
                self.stdout.write('Обновлено statement: {:,}'.format(len(updates)))

            if part_map:
                updates = []
                for part in ProblemPart.objects.filter(id__in=list(part_map.keys())):
                    part.statement = part_map[part.id]
                    updates.append(part)
                ProblemPart.objects.bulk_update(updates, ['statement'], batch_size=500)
                self.stdout.write('Обновлено подпунктов: {:,}'.format(len(updates)))

        affected_ids = sorted({pid for pid, _, _, _ in to_write})
        ids_path = os.path.join(SRC_DIR, 'affected_problem_ids.txt')
        with open(ids_path, 'w', encoding='utf-8') as f:
            for pid in affected_ids:
                f.write('{}\n'.format(pid))
        self.stdout.write('Изменено задач: {:,}. Список → {}'.format(
            len(affected_ids), ids_path))

        self._post_checks(to_write, problems, backup)

    # ── Контроль после применения ───────────────────────────────────────────

    def _post_checks(self, to_write, problems, backup):
        ok = True

        # 1. Идемпотентность: перечитанное из базы значение прогоняем через
        # glue_field ещё раз — новых склеек быть не должно (конвейер уже
        # довёл текст до неподвижной точки).
        non_idempotent = []
        for p in Problem.objects.filter(id__in=list({pid for pid, k, n, f in to_write
                                                       if 'stmt' in f})):
            res = glue_field(p.statement or '')
            if res.new_text is not None:
                non_idempotent.append(('statement', p.id))
        changed_part_ids = [pk for _, _, _, f in to_write
                            for pk in f.get('parts', {})]
        for part in ProblemPart.objects.filter(id__in=changed_part_ids):
            res = glue_field(part.statement or '')
            if res.new_text is not None:
                non_idempotent.append(('part', part.id))
        if non_idempotent:
            ok = False
            self.stdout.write(self.style.ERROR(
                'НЕ идемпотентно: {} полей: {}'.format(
                    len(non_idempotent), non_idempotent[:10])))
        else:
            self.stdout.write('Идемпотентность склейки: подтверждена (0 полей).')

        # 2. solution не тронут ни у одной задачи из применённых — сверяем
        # снимок ДО (backup['solution']) с базой ПОСЛЕ, а не верим конвейеру
        # на слово.
        touched_ids = sorted({pid for pid, k, n, f in to_write})
        solution_changed = []
        for p in Problem.objects.filter(id__in=touched_ids):
            before = backup['solution'].get(str(p.id), '')
            after = p.solution or ''
            if before != after:
                solution_changed.append(p.id)
        if solution_changed:
            ok = False
            self.stdout.write(self.style.ERROR(
                'ВНИМАНИЕ: solution изменился у {} задач: {}'.format(
                    len(solution_changed), solution_changed[:10])))
        else:
            self.stdout.write('solution: сверено с бэкапом — не изменился ни у '
                              'одной из {} применённых задач.'.format(len(touched_ids)))

        # 3. Секция «подозрительное сокращение» не тронута.
        trim_path = os.path.join(SRC_DIR, 'to_apply_bad_trim.txt')
        if os.path.exists(trim_path) and open(trim_path, encoding='utf-8').read().strip():
            ok = False
            self.stdout.write(self.style.ERROR(
                'ВНИМАНИЕ: to_apply_bad_trim.txt не пуст — секция сокращений '
                'не должна была участвовать в применении.'))
        else:
            self.stdout.write('Секция «подозрительное сокращение» не тронута '
                              '(to_apply_bad_trim.txt пуст).')

        if ok:
            self.stdout.write(self.style.SUCCESS('Контроль пройден.'))
        else:
            self.stdout.write(self.style.ERROR('Контроль НЕ пройден — см. выше.'))
