# -*- coding: utf-8 -*-
r"""Перегенерация текста трёх новых источников ИЗ СЫРЬЯ на диске.

Единственный безопасный способ починить уже сохранённый текст новых
источников: взять сырой материал с диска и прогнать `convert_for_import`
заново ([ADR 0033](../../../docs/adr/0033-new-sources-store-converted-text.md)).
Повторная канонизация поверх сохранённого текста запрещена — второй
прогон по уже канонизированному тексту даёт другой результат.

Правка механическая и детерминированная: модель к тексту не подпускается
(P0 в `CLAUDE.md`, [ADR 0005](../../../docs/adr/0005-ai-writes-new-fields-only.md)).

Предохранители, каждый падает `CommandError`:

1. `Problem.objects.count()` не меняется — команда только UPDATE.
2. Число задач в `draft` и в `hidden_pending_review` до и после
   ОДИНАКОВОЕ. Эта команда ничего не публикует; проверяется кодом, а не
   доверием к тому, что «этот код я не трогал».
3. Ни одно непустое поле не становится пустым.
4. Парность `$` и баланс `{}` не ухудшаются (считается дифференциально:
   в банке есть унаследованные поломки, абсолютное число всегда
   некрасивое).
5. Структура подпунктов разошлась (другое число или другие метки) —
   задача НЕ трогается и уходит в отчёт: подпункты адресуются по `pk`,
   на них ссылаются работы и попытки.

По умолчанию — сухой прогон. Запись — только с `--apply`.
"""
import html
import json
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.corpus_converter.ingest import content_hash_for
from problems.corpus_converter.reconvert import LOADERS
from problems.models import Problem, ProblemPart, Source

OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'import_new_sources')
FIELDS = ('statement', 'answer', 'solution')


def dollar_parity(text):
    """Нечётное число неэкранированных `$` — сломанная пара."""
    count = 0
    i = 0
    text = text or ''
    while i < len(text):
        if text[i] == '\\':
            i += 2
            continue
        if text[i] == '$':
            count += 1
        i += 1
    return count % 2


def brace_balance(text):
    """|открытых − закрытых| фигурных скобок, экранированные не в счёт."""
    depth = 0
    worst = 0
    i = 0
    text = text or ''
    while i < len(text):
        ch = text[i]
        if ch == '\\':
            i += 2
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            worst = min(worst, depth)
        i += 1
    return abs(depth) + abs(worst)


class Command(BaseCommand):
    help = ('Перегенерировать statement/answer/solution трёх новых источников '
            'из сырья на диске. Без --apply — сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='реально записать (по умолчанию сухой прогон)')
        parser.add_argument('--source', choices=list(LOADERS),
                            help='только один источник')
        parser.add_argument('--ids-file',
                            help='файл со списком id задач (по одному в строке)')
        parser.add_argument('--data-dir',
                            help='папка выгрузки (перекрывает путь по умолчанию)')
        parser.add_argument('--report-dir',
                            help='куда класть отчёт и бэкап; тесты обязаны давать '
                                 'временную папку — иначе затирают боевой')
        parser.add_argument('--preview', type=int, default=20,
                            help='сколько пар ДО/ПОСЛЕ положить в HTML (0 — не делать)')

    def handle(self, *args, **options):
        do_apply = options['apply']
        slugs = [options['source']] if options['source'] else list(LOADERS)
        if options.get('data_dir') and len(slugs) > 1:
            raise CommandError(
                '--data-dir задаёт папку ОДНОГО источника — давайте его вместе '
                'с --source, иначе все три читались бы из одной папки.')

        only_ids = None
        if options.get('ids_file'):
            with open(options['ids_file'], encoding='utf-8') as f:
                only_ids = {int(line) for line in f if line.strip()}

        before = self._snapshot(slugs)

        changes = []          # список правок
        stats = {
            'проверено': 0, 'без изменений': 0, 'сырьё не найдено': 0,
            'структура подпунктов разошлась': 0, 'к изменению': 0,
        }
        structure_conflicts = []
        missing_raw = []

        for slug in slugs:
            source_name, loader = LOADERS[slug]
            source = Source.objects.filter(name=source_name).first()
            if source is None:
                raise CommandError(
                    f'Источник «{source_name}» не найден в базе — импорт не '
                    f'выполнялся. Сначала import_{slug}.')

            qs = (Problem.objects.filter(source_references__source=source)
                  .distinct().prefetch_related('parts', 'source_references')
                  .order_by('id'))
            if only_ids is not None:
                qs = qs.filter(id__in=only_ids)
            wanted = {
                p.source_references.filter(source=source).first().problem_number
                for p in qs
            }
            self.stdout.write(f'{source_name}: читаю сырьё…')
            records = loader(options.get('data_dir'), only=wanted)
            self.stdout.write(f'  прочитано записей: {len(records)}')

            for problem in qs:
                stats['проверено'] += 1
                ref = problem.source_references.filter(source=source).first()
                record = records.get(ref.problem_number)
                if record is None:
                    stats['сырьё не найдено'] += 1
                    missing_raw.append(
                        {'id': problem.id, 'source': slug,
                         'external_id': ref.problem_number})
                    continue

                stored_parts = list(problem.parts.all().order_by('order'))
                if [p.label for p in stored_parts] != [lbl for lbl, _ in record.parts]:
                    stats['структура подпунктов разошлась'] += 1
                    structure_conflicts.append(
                        {'id': problem.id, 'source': slug,
                         'в базе': [p.label for p in stored_parts],
                         'из сырья': [lbl for lbl, _ in record.parts]})
                    continue

                new = {'statement': record.statement,
                       'answer': record.answer,
                       'solution': record.solution}
                old = {f: getattr(problem, f) or '' for f in FIELDS}
                part_pairs = [
                    (p.pk, p.statement or '', text)
                    for p, (_lbl, text) in zip(stored_parts, record.parts)
                ]
                field_changed = {f for f in FIELDS if old[f] != (new[f] or '')}
                parts_changed = [t for t in part_pairs if t[1] != t[2]]
                if not field_changed and not parts_changed:
                    stats['без изменений'] += 1
                    continue

                stats['к изменению'] += 1
                changes.append({
                    'id': problem.id, 'source': slug,
                    'external_id': ref.problem_number,
                    'fields': sorted(field_changed),
                    'old': old, 'new': {f: new[f] or '' for f in FIELDS},
                    'parts': parts_changed,
                })

        self._check_invariants(changes)

        out_dir = options.get('report_dir') or OUT_DIR
        os.makedirs(out_dir, exist_ok=True)
        report_path = os.path.join(out_dir, 'reconvert_report.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({
                'applied': do_apply,
                'stats': stats,
                'changed_ids': [c['id'] for c in changes],
                'по полям': self._by_field(changes),
                'структура подпунктов разошлась': structure_conflicts[:200],
                'сырьё не найдено': missing_raw[:200],
            }, f, ensure_ascii=False, indent=1)

        lines = ['']
        for key, value in stats.items():
            lines.append(f'  {key}: {value}')
        lines.append(f'  по полям: {self._by_field(changes)}')
        lines.append(f'  отчёт: {report_path}')

        preview_path = None
        if options['preview'] and changes:
            preview_path = self._write_preview(
                out_dir, changes, options['preview'])
            lines.append(f'  предпросмотр ДО/ПОСЛЕ: {preview_path}')

        if not do_apply:
            lines.append('СУХОЙ ПРОГОН — в базе ничего не изменено.')
            self.stdout.write(self.style.WARNING('\n'.join(lines)))
            return

        backup_path = os.path.join(out_dir, 'reconvert_backup.json')
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump({
                'note': 'Снимок ДО перегенерации текста новых источников.',
                'count': len(changes),
                'problems': [
                    {'id': c['id'], 'old': c['old'],
                     'parts': [{'pk': pk, 'old': old} for pk, old, _new in c['parts']]}
                    for c in changes
                ],
            }, f, ensure_ascii=False, indent=1)

        with transaction.atomic():
            for change in changes:
                problem = Problem.objects.get(id=change['id'])
                for field in FIELDS:
                    setattr(problem, field, change['new'][field])
                # Хэш считается от того, что реально ложится в statement —
                # иначе find_duplicates сравнивал бы разные тексты.
                problem.content_hash = content_hash_for(change['new']['statement'])
                problem.save(update_fields=[*FIELDS, 'content_hash', 'updated_at'])
                for pk, _old, new_text in change['parts']:
                    ProblemPart.objects.filter(pk=pk).update(statement=new_text)

        after = self._snapshot(slugs)
        for key in before:
            if before[key] != after[key]:
                raise CommandError(
                    f'ИНВАРИАНТ НАРУШЕН: «{key}» было {before[key]}, '
                    f'стало {after[key]}. Откат: {backup_path}')

        lines.append(f'ЗАПИСАНО: изменено задач {len(changes)}.')
        lines.append(f'  бэкап для отката: {backup_path}')
        lines.append(f'  инварианты сошлись: {before}')
        lines.append('  ⚠️ эмбеддинги изменённых id надо пересчитать отдельно '
                     '(см. docs/EMBEDDINGS.md, ловушка done-файла)')
        self.stdout.write(self.style.SUCCESS('\n'.join(lines)))

    # -- служебное ---------------------------------------------------------

    def _snapshot(self, slugs):
        """Счётчики, которые эта команда менять НЕ имеет права."""
        names = [LOADERS[s][0] for s in slugs]
        qs = Problem.objects.filter(source_references__source__name__in=names).distinct()
        return {
            'Problem всего': Problem.objects.count(),
            'ProblemPart всего': ProblemPart.objects.count(),
            'новых источников': qs.count(),
            'status=draft': qs.filter(status=Problem.Status.DRAFT).count(),
            'hidden_pending_review': qs.filter(hidden_pending_review=True).count(),
            'content_format=markdown': qs.filter(
                content_format=Problem.ContentFormat.MARKDOWN).count(),
        }

    def _by_field(self, changes):
        out = {}
        for change in changes:
            for field in change['fields']:
                out[field] = out.get(field, 0) + 1
            if change['parts']:
                out['подпункты'] = out.get('подпункты', 0) + 1
        return out

    def _check_invariants(self, changes):
        """Дифференциально: стало хуже — падаем, было плохо — молчим."""
        emptied, dollars, braces = [], [], []
        for change in changes:
            for field in FIELDS:
                old, new = change['old'][field], change['new'][field]
                if old.strip() and not new.strip():
                    emptied.append((change['id'], field))
                if dollar_parity(new) > dollar_parity(old):
                    dollars.append((change['id'], field))
                if brace_balance(new) > brace_balance(old):
                    braces.append((change['id'], field))
            for _pk, old, new in change['parts']:
                if old.strip() and not new.strip():
                    emptied.append((change['id'], 'part'))
        if emptied:
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: {len(emptied)} непустых полей стали '
                f'пустыми: {emptied[:20]}')
        if dollars:
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: у {len(dollars)} полей ухудшилась '
                f'парность $: {dollars[:20]}')
        if braces:
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: у {len(braces)} полей ухудшился баланс '
                f'{{}}: {braces[:20]}')

    def _write_preview(self, out_dir, changes, limit):
        """HTML с парами ДО/ПОСЛЕ. Самые длинные и самые короткие правки —
        отдельно: ломается обычно на краях."""
        def size(change):
            return sum(len(change['old'][f]) for f in FIELDS)

        ordered = sorted(changes, key=size)
        picked = []
        picked += ordered[:3]
        picked += ordered[-3:]
        rest = [c for c in ordered if c not in picked]
        rng = random.Random(20260829)
        picked += rng.sample(rest, min(max(limit - len(picked), 0), len(rest)))

        rows = []
        for change in picked:
            blocks = []
            for field in change['fields']:
                blocks.append(
                    f'<div class=pair><div class=old><b>{field} ДО</b>'
                    f'<pre>{html.escape(change["old"][field])}</pre></div>'
                    f'<div class=new><b>{field} ПОСЛЕ</b>'
                    f'<pre>{html.escape(change["new"][field])}</pre></div></div>')
            for pk, old, new in change['parts']:
                blocks.append(
                    f'<div class=pair><div class=old><b>подпункт {pk} ДО</b>'
                    f'<pre>{html.escape(old)}</pre></div>'
                    f'<div class=new><b>подпункт {pk} ПОСЛЕ</b>'
                    f'<pre>{html.escape(new)}</pre></div></div>')
            rows.append(
                f'<section><h2>#{change["id"]} · {change["source"]} · '
                f'внешний {html.escape(str(change["external_id"]))} · '
                f'{", ".join(change["fields"]) or "только подпункты"}</h2>'
                + ''.join(blocks) + '</section>')

        path = os.path.join(out_dir, 'reconvert_preview.html')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(
                '<!doctype html><meta charset=utf-8>'
                '<title>Перегенерация текста новых источников — ДО/ПОСЛЕ</title>'
                '<style>body{font:14px/1.5 system-ui;margin:24px;max-width:1600px}'
                'section{border-top:2px solid #ccc;padding-top:12px;margin-top:24px}'
                '.pair{display:flex;gap:16px}.pair>div{flex:1;min-width:0}'
                'pre{white-space:pre-wrap;word-break:break-word;background:#f6f6f6;'
                'padding:8px;border-radius:6px;font-size:12px}'
                '.new pre{background:#eefbee}</style>'
                f'<h1>Пары ДО/ПОСЛЕ — {len(picked)} из {len(changes)} правок</h1>'
                '<p>Первые три — самые короткие правки, следующие три — самые '
                'длинные, остальные случайны (сид 20260829).</p>'
                + ''.join(rows))
        return path
