# -*- coding: utf-8 -*-
"""
Ревизия группы Б: свип подмен содержания по всем применённым 2026-07-19
задачам (найдено ревью соавтора — подменённые числа/знаки на 3 задачах из
95, см. reports/batch2_unblock/point_reverts.md).

Сравнивает ДО (JSON-бэкап применения) и ПОСЛЕ (текущая база) КАЖДОГО
применённого поля через problems.batch2_unblock.sweep_field (игнорирует
нашу же нормализацию кавычек и склейку):
  - digit_sign_change — число/знак пропал/появился/сменился там, где
    в СТАРОМ тексте что-то стояло → поле откатывается к ДО автоматически
    (механическая чистка не имеет права трогать числа/знаки/суть);
  - new_sentence — фрагмент есть ТОЛЬКО в новом тексте и читается как
    предложение (восстановленный вопрос) → НЕ откатывается, идёт в
    reports/batch2_unblock/reconstructed_review.html на вердикт Макара;
  - same / other — без изменений полей и без записи, но считаются в сводке.

Без --confirm — только предпросмотр в консоль и отчёты, база не меняется.
"""
import html
import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.batch2_unblock import glue_field, sweep_field
from problems.management.commands.glue_pdf_lines import _PREVIEW_TAIL, preview_head
from problems.management.commands.preview_batch2_unblock import diff_block
from problems.models import Problem, ProblemPart

OUT_DIR = 'reports/batch2_unblock'


class Command(BaseCommand):
    help = ('Свип подмен содержания по применённым задачам группы Б: '
            'цифры/знаки — автооткат, новые предложения — в превью на вердикт.')

    def add_arguments(self, parser):
        parser.add_argument('--backup', required=True)
        parser.add_argument('--confirm', action='store_true',
                            help='Записать откаты в базу (по умолчанию dry-run).')
        parser.add_argument('--exclude-part-pk', type=int, action='append', default=[],
                            help='Подпункт исключить из автооткота свипа — решается '
                                 'отдельной точечной проверкой (напр. Задача 4, #27869 '
                                 'pk=35821: сначала сверяется с solution/логом).')

    def handle(self, *args, **opts):
        confirm = opts['confirm']
        os.makedirs(OUT_DIR, exist_ok=True)
        backup_path = opts['backup']
        if not os.path.exists(backup_path):
            raise CommandError('Бэкап не найден: {}'.format(backup_path))
        with open(backup_path, encoding='utf-8') as f:
            backup = json.load(f)

        problem_ids = [int(k) for k in backup.get('problems', {})]
        part_ids = [int(k) for k in backup.get('parts', {})]
        problems = {p.pk: p for p in Problem.objects.filter(pk__in=problem_ids)}
        parts = {p.pk: p for p in ProblemPart.objects.filter(pk__in=part_ids)
                 .select_related('problem')}

        same = other = new_sentence_n = digit_n = 0
        reverts = []          # (kind, pid_or_pk, old, new)
        review_cards = []     # (kind, pid, label_or_none, old, new, insertions)

        for pid_str, old_val in backup.get('problems', {}).items():
            pid = int(pid_str)
            problem = problems.get(pid)
            if problem is None:
                continue
            new_val = problem.statement or ''
            r = sweep_field(old_val, new_val)
            if r['verdict'] == 'same':
                same += 1
            elif r['verdict'] == 'other':
                other += 1
            elif r['verdict'] == 'digit_sign_change':
                digit_n += 1
                reverts.append(('statement', pid, old_val, new_val, r['detail']))
            elif r['verdict'] == 'new_sentence':
                new_sentence_n += 1
                review_cards.append(('statement', pid, None, old_val, new_val))

        excluded_pks = set(opts['exclude_part_pk'])
        excluded_flagged = []
        for pk_str, old_val in backup.get('parts', {}).items():
            pk = int(pk_str)
            part = parts.get(pk)
            if part is None:
                continue
            new_val = part.statement or ''
            r = sweep_field(old_val, new_val)
            if pk in excluded_pks and r['verdict'] != 'same':
                excluded_flagged.append((pk, r['verdict']))
                continue
            if r['verdict'] == 'same':
                same += 1
            elif r['verdict'] == 'other':
                other += 1
            elif r['verdict'] == 'digit_sign_change':
                digit_n += 1
                reverts.append(('part', pk, old_val, new_val, r['detail']))
            elif r['verdict'] == 'new_sentence':
                new_sentence_n += 1
                review_cards.append(
                    ('part', part.problem_id, (part.label, pk), old_val, new_val))

        total = same + other + digit_n + new_sentence_n
        self.stdout.write('Полей всего: {} (same={}, other={}, '
                          'digit_sign_change={}, new_sentence={})'.format(
                              total, same, other, digit_n, new_sentence_n))
        for kind, ident, old_val, new_val, detail in reverts:
            self.stdout.write('  ОТКАТ {} #{}: {}'.format(kind, ident, detail))
        if excluded_flagged:
            self.stdout.write('Исключено из автооткота (отдельная проверка): {}'.format(
                excluded_flagged))

        self._write_reverts_md(reverts)
        self._write_reconstructed_review(review_cards, problems, parts)

        if not confirm:
            self.stdout.write('Режим dry-run: база НЕ изменена. Для записи добавьте --confirm.')
            return

        self._apply_reverts(reverts)

    # ── Отчёты ───────────────────────────────────────────────────────────────

    def _write_reverts_md(self, reverts):
        path = os.path.join(OUT_DIR, 'sweep_digit_sign_reverts.md')
        lines = ['# Свип подмен — автооткаты (цифры/знаки)', '',
                'Механическая чистка не имеет права менять числа/знаки/суть. '
                'Поле целиком откатывается к ДО (бэкап применения).', '']
        if not reverts:
            lines.append('Пусто — свип не нашёл подмен цифр/знаков.')
        for kind, ident, old_val, new_val, detail in reverts:
            lines.append('## {} {}'.format(kind, ident))
            lines.append('- токены ДО: `{}`'.format(detail[0][0] if detail else '?'))
            lines.append('- токены ПОСЛЕ: `{}`'.format(detail[0][1] if detail else '?'))
            lines.append('- ДО: `{}`'.format(old_val[:200]))
            lines.append('- ПОСЛЕ (откатывается): `{}`'.format(new_val[:200]))
            lines.append('')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        self.stdout.write('Откаты (отчёт) → {}'.format(path))

    def _write_reconstructed_review(self, review_cards, problems, parts):
        path = os.path.join(OUT_DIR, 'reconstructed_review.html')
        head = preview_head(
            'Свип группы Б — восстановленные предложения',
            'Свип подмен группы Б — восстановленные предложения (вердикт Макара)',
            'Фрагменты, которых не было в ДО (бэкап), но которые появились в '
            'ПОСЛЕ (база) — не подмена (числа/знаки не тронуты), похоже на '
            'восстановленный Sonnet текст. НЕ откачено автоматически — '
            'решает Макар по каждой карточке.')
        out = [head]
        out.append('<h2 class="section">{} карточек на вердикт</h2>'.format(
            len(review_cards)))
        if not review_cards:
            out.append('<p><em>Пусто — свип не нашёл восстановленных предложений.</em></p>')
        for i, (kind, pid, part_info, old_val, new_val) in enumerate(review_cards, start=1):
            esc = html.escape
            problem = problems.get(pid) or (parts.get(part_info[1]).problem
                                            if part_info else None)
            title = esc(problem.title if problem else '')
            label = ' (Условие)' if kind == 'statement' else \
                ' (подп. [{}], pk={})'.format(esc(part_info[0]), part_info[1])
            out.append(
                '<div class="card"><div class="meta"><b>№{num}</b> <b>#{pid}</b>'
                '{label} — {title} — <a href="http://127.0.0.1:8000/catalog/problem/'
                '{pid}/" target="_blank">открыть в каталоге</a></div>{diff}</div>'.format(
                    num=i, pid=pid, label=label, title=title,
                    diff=diff_block('Текст', old_val, new_val)))
        out.append(_PREVIEW_TAIL)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out))
        self.stdout.write('Восстановленные предложения (превью) → {} ({} карточек)'.format(
            path, len(review_cards)))

    # ── Применение откатов ──────────────────────────────────────────────────

    def _apply_reverts(self, reverts):
        stmt_updates = []
        part_updates = []
        non_idempotent = []
        for kind, ident, old_val, new_val, detail in reverts:
            res = glue_field(old_val)
            if res.new_text is not None:
                non_idempotent.append((kind, ident))
            if kind == 'statement':
                p = Problem.objects.get(pk=ident)
                p.statement = old_val
                stmt_updates.append(p)
            else:
                part = ProblemPart.objects.get(pk=ident)
                part.statement = old_val
                part_updates.append(part)

        with transaction.atomic():
            if stmt_updates:
                Problem.objects.bulk_update(stmt_updates, ['statement'], batch_size=200)
            if part_updates:
                ProblemPart.objects.bulk_update(part_updates, ['statement'], batch_size=200)

        self.stdout.write('Откачено: {} statement, {} подпунктов.'.format(
            len(stmt_updates), len(part_updates)))
        if non_idempotent:
            self.stdout.write(self.style.WARNING(
                'ВНИМАНИЕ: glue_field предлагает ещё склейку на возвращённом '
                'тексте: {}'.format(non_idempotent)))
        else:
            self.stdout.write('Идемпотентность отката подтверждена (0 полей).')
