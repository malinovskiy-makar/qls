# -*- coding: utf-8 -*-
"""
Конструктор-превью разблокировки группы Б (заблокированные правки Батча 2,
250 задач: конфликт решения 118, неизвестная метка подпункта 106,
подозрительное сокращение 26). Только ЧТЕНИЕ — база не меняется, --confirm
у команды нет (применение — следующая сессия, после стоп-гейта Макара).

Логика классификации — в problems/batch2_unblock.py (общая для превью и
будущего применения). Здесь — обвязка: чтение отчётов apply_batch2,
подготовка списков к применению/в остаток, HTML-превью.

Запуск:
    ./venv/bin/python manage.py preview_batch2_unblock
"""
import html
import json
import os
import random
from collections import Counter

from django.core.management.base import BaseCommand

from problems.batch2_unblock import (
    classify_bad_trim, classify_conflict_solution, classify_unknown_label,
    pipeline_changes,
)
from problems.management.commands.apply_batch2 import _load_parsed, _problem_id
from problems.management.commands.glue_pdf_lines import _PREVIEW_TAIL, preview_head
from problems.models import Problem

SRC_REPORT_DIR = 'reports/batch2'
OUT_DIR = 'reports/batch2_unblock'
PARSED_FILE = 'batch2_parsed.jsonl'

CATEGORIES = [
    ('conflict_solution', 'skipped_conflict_solution.txt', 'Конфликт решения',
     classify_conflict_solution),
    ('unknown_label', 'skipped_unknown_part_label.txt', 'Неизвестная метка подпункта',
     classify_unknown_label),
    ('bad_trim', 'skipped_bad_trim.txt', 'Подозрительное сокращение (>80%)',
     classify_bad_trim),
]

REASON_LABELS = {
    'stmt_suspicious_trim_vs_current': 'условие подозрительно сократилось против ТЕКУЩЕГО текста',
    'parts_ambiguous_vs_current': 'метки подпунктов неоднозначны против ТЕКУЩИХ пунктов',
    'parts_ambiguous': 'метки подпунктов неоднозначны (расщепление/пропуск пункта)',
    'no_net_change_besides_solution': 'без решения меняться нечему (условие/подпункты уже в порядке)',
    'no_net_change': 'меняться нечему',
    'manual_review_required': 'требуется поштучный вердикт (без автоматики)',
}


def _load_ids(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [int(x.strip()) for x in f if x.strip()]


class Command(BaseCommand):
    help = ('Превью разблокировки группы Б Батча 2 — только чтение, '
            'reports/batch2_unblock/preview.html + списки к применению/остаток.')

    def handle(self, *args, **opts):
        os.makedirs(OUT_DIR, exist_ok=True)

        self.stdout.write('Читаю {}…'.format(PARSED_FILE))
        records = _load_parsed(PARSED_FILE)
        by_id = {}
        for r in records:
            pid = _problem_id(r['custom_id'])
            if pid is not None:
                by_id[pid] = r
        self.stdout.write('  записей: {:,}'.format(len(records)))

        cat_ids = {}
        all_ids = set()
        for key, fname, _, _ in CATEGORIES:
            ids = _load_ids(os.path.join(SRC_REPORT_DIR, fname))
            cat_ids[key] = ids
            all_ids.update(ids)

        problems = {
            p.pk: p for p in
            Problem.objects.filter(pk__in=list(all_ids)).prefetch_related('parts')
        }

        extracted_solutions = []  # для лога (обе категории, где есть решение)
        section_html = {}
        summary_rows = []
        apply_ids = {key: [] for key, *_ in CATEGORIES}
        remainder_rows = {key: [] for key, *_ in CATEGORIES}

        for key, fname, title, classify_fn in CATEGORIES:
            ids = cat_ids[key]
            cards = []
            remainder_lines = []
            remainder_entries = []  # (pid, title, reasons) — для краткой секции
            n_apply = 0
            reason_counts = Counter()
            missing = 0

            for pid in ids:
                problem = problems.get(pid)
                rec = by_id.get(pid)
                if problem is None or rec is None:
                    missing += 1
                    remainder_lines.append('#{}\tmissing_data'.format(pid))
                    remainder_entries.append((pid, '', ['missing_data']))
                    continue

                result = classify_fn(problem, rec)
                extracted = result.get('extracted_solution') or ''
                if extracted:
                    extracted_solutions.append({
                        'problem_id': pid,
                        'category': key,
                        'status': 'apply' if result['apply'] else 'remainder',
                        'extracted_solution': extracted,
                        'existing_solution_kept': bool((problem.solution or '').strip()),
                    })

                if result['apply']:
                    n_apply += 1
                    apply_ids[key].append(pid)
                    final = pipeline_changes(result['changes'])
                    cards.append((pid, problem, final, result, None))
                else:
                    for reason in result['reasons']:
                        reason_counts[reason] += 1
                    remainder_lines.append('#{}\t{}'.format(
                        pid, ','.join(result['reasons'])))
                    remainder_entries.append((pid, problem.title or '', result['reasons']))
                    if key == 'bad_trim':
                        # bad_trim: всегда в превью — показываем предложение
                        # для ручного вердикта, даже хотя apply=False всегда.
                        final = pipeline_changes(result['changes'])
                        cards.append((pid, problem, final, result, None))

            self._write_lines(os.path.join(OUT_DIR, 'to_apply_{}.txt'.format(key)),
                              [str(i) for i in apply_ids[key]])
            self._write_lines(os.path.join(OUT_DIR, 'remainder_{}.txt'.format(key)),
                              remainder_lines)

            summary_rows.append((title, len(ids), n_apply, len(ids) - n_apply, reason_counts))
            section_html[key] = self._render_section(key, title, cards)
            if key != 'bad_trim':
                # bad_trim остаток уже показан полными карточками выше —
                # отдельная краткая секция ему не нужна.
                section_html[key] += self._render_remainder(title, remainder_entries)

            self.stdout.write('{}: {} к применению / {} в остаток (из {})'.format(
                title, n_apply, len(ids) - n_apply, len(ids)))
            for reason, cnt in reason_counts.most_common():
                self.stdout.write('    {}: {}'.format(
                    REASON_LABELS.get(reason, reason), cnt))

        with open(os.path.join(OUT_DIR, 'extracted_solutions.jsonl'), 'w',
                  encoding='utf-8') as f:
            for row in extracted_solutions:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
        self.stdout.write('Извлечённые решения (лог, НЕ база) → {} ({} шт.)'.format(
            os.path.join(OUT_DIR, 'extracted_solutions.jsonl'), len(extracted_solutions)))

        self._write_html(summary_rows, section_html)

    # ── Отчёты ───────────────────────────────────────────────────────────────

    @staticmethod
    def _write_lines(path, lines):
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + ('\n' if lines else ''))

    def _write_html(self, summary_rows, section_html):
        summary_lines = ['<table class="summary-table"><thead><tr>'
                         '<th>Категория</th><th>Всего</th><th>К применению</th>'
                         '<th>В остаток</th><th>Причины остатка</th></tr></thead><tbody>']
        for title, total, n_apply, n_rem, reasons in summary_rows:
            reason_txt = ', '.join(
                '{}: {}'.format(REASON_LABELS.get(r, r), c)
                for r, c in reasons.most_common())
            summary_lines.append(
                '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
                    html.escape(title), total, n_apply, n_rem, html.escape(reason_txt)))
        summary_lines.append('</tbody></table>')

        head = preview_head(
            'Разблокировка группы Б — превью',
            'Разблокировка группы Б: заблокированные правки Батча 2',
            'Конвейер: текст Sonnet (batch2_parsed.jsonl) → правила glue_pdf_lines → '
            'финальный текст. ДО — как хранится в базе СЕЙЧАС (уже после склейки '
            'нарезки), ПОСЛЕ — предложение конвейера. База НЕ менялась, --confirm нет.')

        out = [head]
        out.append(
            '<style>.summary-table { width: 100%; border-collapse: collapse; '
            'background: #fff; border-radius: 8px; overflow: hidden; }\n'
            '.summary-table th, .summary-table td { padding: 6px 10px; '
            'border-bottom: 1px solid #e5e5e5; text-align: left; font-size: 13px; }\n'
            '.summary-table th { background: #f0f0f2; }</style>')
        out.append('<h2 class="section">Сводка</h2>')
        out.append('\n'.join(summary_lines))
        for key, _, title, _ in CATEGORIES:
            out.append(section_html[key])
        out.append(_PREVIEW_TAIL)

        path = os.path.join(OUT_DIR, 'preview.html')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out))
        self.stdout.write('Превью → {}'.format(path))

    def _render_remainder(self, title, entries):
        esc = html.escape
        parts = ['<h3 class="source">Остаток «{}» — НЕ предлагается применять ({} шт.)</h3>'.format(
            esc(title), len(entries))]
        if not entries:
            parts.append('<p><em>Остатка нет — все записи разблокированы.</em></p>')
            return '\n'.join(parts)
        parts.append('<table class="summary-table"><thead><tr>'
                     '<th>id</th><th>Задача</th><th>Причина</th></tr></thead><tbody>')
        for pid, ptitle, reasons in entries:
            reason_txt = ', '.join(REASON_LABELS.get(r, r) for r in reasons)
            parts.append(
                '<tr><td><a href="http://127.0.0.1:8000/catalog/problem/{pid}/" '
                'target="_blank">#{pid}</a></td><td>{title}</td><td>{reason}</td></tr>'.format(
                    pid=pid, title=esc(ptitle), reason=esc(reason_txt)))
        parts.append('</tbody></table>')
        return '\n'.join(parts)

    def _render_section(self, key, title, cards):
        esc = html.escape
        parts = ['<h2 class="section">{}{}</h2>'.format(
            esc(title), ' — все идут на поштучный вердикт (без автоматики)'
            if key == 'bad_trim' else '')]
        if not cards:
            parts.append('<p><em>Нет карточек к показу.</em></p>')
            return '\n'.join(parts)
        for i, (pid, problem, final, result, _) in enumerate(cards, start=1):
            parts.append(self._render_card(i, pid, problem, final, result, key))
        return '\n'.join(parts)

    def _render_card(self, number, pid, problem, final, result, key):
        esc = html.escape
        title = esc(problem.title or '')
        chips = []
        if key == 'bad_trim':
            chips.append('<span class="chip warn">сокращение: {}%</span>'.format(
                result.get('shrink_pct', '?')))
            if result.get('notes'):
                chips.append('<span class="chip warn">{}</span>'.format(
                    esc(', '.join(result['notes']))))
        rows = []

        if 'stmt' in final:
            rows.append(self._diff_block('Условие', problem.statement or '', final['stmt']))

        if 'parts' in final:
            by_pk = {p.pk: p for p in problem.parts.all()}
            for pk, new_text in final['parts'].items():
                old_part = by_pk.get(pk)
                old_text = old_part.statement if old_part else ''
                label = old_part.label if old_part else '?'
                rows.append(self._diff_block(
                    'Подп. [{}] (pk={})'.format(esc(label), pk), old_text or '', new_text))

        if 'solution' in final:
            note = ('будет записано — решения не было' if key == 'unknown_label'
                    else 'в лог, НЕ в базу — решение уже есть')
            rows.append(self._diff_block(
                'Решение Sonnet ({})'.format(note),
                problem.solution or '(пусто)', final['solution']))

        rows_html = '\n'.join(rows)
        return (
            '<div class="card">'
            '<div class="meta"><b>№{num}</b> <b>#{pid}</b> — {title}{chips} — '
            '<a href="http://127.0.0.1:8000/catalog/problem/{pid}/" target="_blank">'
            'открыть в каталоге</a></div>'
            '{rows}'
            '</div>'
        ).format(num=number, pid=pid, title=title,
                 chips=''.join(chips), rows=rows_html)

    @staticmethod
    def _diff_block(label, old, new):
        esc = html.escape
        return (
            '<div class="fieldlabel">{label}</div>'
            '<div class="cols">'
            '<div class="col before"><div class="col-label">ДО</div>'
            '<div class="text">{old}</div></div>'
            '<div class="col after"><div class="col-label">ПОСЛЕ</div>'
            '<div class="text">{new}</div></div>'
            '</div>'
        ).format(label=esc(label), old=esc(old), new=esc(new))
