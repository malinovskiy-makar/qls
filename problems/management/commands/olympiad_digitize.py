# -*- coding: utf-8 -*-
"""Оцифровка официальных PDF олимпиады — подготовка без модели.

Олимпиада задаётся ЯВНО: `--olympiad vp|mosh` (реестр
`problems/olympiad_audit/registry.py`: папка аудита). Без флага — отказ.

    inventory --olympiad X
        обходит ВСЕ файлы raw\\ аудита и пишет digitized\\inventory.jsonl
        (по строке на файл: вид, комплекты, слой, идёт ли в оцифровку и
        почему нет) и digitized\\events_files.jsonl (комплект → файлы
        условий, решений, критериев; новые комплекты — с new=true);
    render --olympiad X [--limit N]
        PDF из инвентаря (digitize=true, не дубль) → PNG 200 dpi и текст
        слоя по страницам в digitized\\pages\\<sha16>\\; готовое не
        перерисовывается; манифест — digitized\\pages_manifest.jsonl.

    transcribe --olympiad X --max-usd X [--limit N] [--pages-file F] [--workers 20] [--yes]
        страницы → зрячая модель GLM-5.3-Flash → digitized\\pages\\<sha16>\\p<N>.json
        (problems/olympiad_audit/transcribe.py). Без --yes — только ПЛАН
        и смета, ни одного вызова; --max-usd обязателен; готовые страницы
        не вызываются повторно (докачка); расход — transcribe_cost.jsonl;
    assemble --olympiad X [--events ID …] [--no-crop]
        страницы → задания эталона v2: reference_problems_v2.jsonl,
        events_v2.jsonl, figures\\, compare_v1_v2.csv
        (problems/olympiad_audit/assemble.py); --v3 — в НОВУЮ папку v3\\
        со страницами, поправленными разбором очереди «на глаза»;
    triage --olympiad X
        очередь «на глаза» → ярусы A/B/C, срочность, выборка контроля:
        triage_plan.csv (без модели);
    judge --olympiad X --max-usd X [--limit N] [--workers 20] [--resume] [--yes]
        судья «картинка против расшифровки» на ярусе A и выборке контроля
        B/C → pages_v3\\ (ok_judge / needs_fix / judge_error); деньги;
    report --olympiad X
        сводка судьи для стоп-гейта (без модели);
    reread --olympiad X --max-usd X [--limit N] [--workers 20] [--resume] [--yes]
        needs_fix → одно перечитывание с подсказкой → пересчёт мерила →
        повторный судья → fixed / human; деньги; старые страницы не меняет;
    review-pack --olympiad X
        остаток (human) → human_review\\index.html + human_review.csv;
    control-pack
        30 случайных страниц яруса A со статусом ok_judge (обе олимпиады, seed
        зафиксирован) → human_review_control\\ без пометок судьи.

    apply-fixes --olympiad X --from vA|--in F --to vB|--out F --fixes F [F …] [--no-autofix] [--replace]
        точечные правки сверки глазами (problems/olympiad_audit/fixes.py): эталон
        vA + правки по порядку + автоисправления (U+00AD, точный повтор «Ответ:»)
        → digitized\\vB\\reference_problems_vB.jsonl; журналы fixes_log.csv,
        fixes_unapplied.csv, autofix_log.csv, vB_changes.md рядом с выходом.
        Существующий выход без --replace не перезаписывается;
    sweeps --olympiad X --version vN [--layers pages_vK,…] [--rows F]
        9 классов автопроверок (problems/olympiad_audit/sweeps.py) по
        digitized\\vN\\reference_problems_vN.jsonl → vN\\sweeps_vN.json + сводка;
        заплатки страниц — pages_vK с K ≤ N, старшая первой (без модели);
    reread-queue --olympiad X --version vN --eye F [--also SLUG …] [--out F]
        очередь перечитывания по находкам sweeps и сверки глазами
        (problems/olympiad_audit/reread_queue.py) → vN\\reread_queue_vN.csv.

    --base vN (triage, judge, reread, report, review-pack): эталон, чью очередь
        разбираем, — reference_problems_vN.jsonl; заплатки — pages_v<N+1>\\
        (по умолчанию v2 → pages_v3; финграмотность и бизнес: --base v1 →
        pages_v2). assemble --suffix v2 --overlay — сборка v2 с заплатками
        pages_v2 (v1 не трогается). triage --auto-publish — ещё ярус D
        (страницы заданий к импорту ниже автопроверки) к судье; judge
        --only-control — сначала только выборка контроля B/C.

    audit-claude --olympiad X --step units|jobs|submit|collect|check|build [--model sonnet|haiku] …
        аудит «глазами Claude» (problems/olympiad_audit/claude_eyes.py): единица —
        страница PDF + фрагменты заданий с неё; ответы — Message Batches API
        (submit/collect: без --yes только план, --max-usd обязателен, заголовок
        пространства из ANTHROPIC_WORKSPACE_ID; готовое повторно не оплачивается)
        или файлы агентов (jobs, check --import-dir); check — детерминированные
        проверки ответов; build — эталон v7 (экономика) / v3 (финграм, бизнес,
        предпринимательство) в digitized\\vN\\, вход не трогается.

Корень данных: `--data-root`, иначе переменная `OLYMPIAD_DATA_ROOT`,
иначе `<родитель BASE_DIR>\\weconomics-data\\olympiads`.

⚠️ В БАЗУ НИЧЕГО НЕ ПИШЕТСЯ. Пишется только папка digitized\\ аудита;
reference_events.jsonl не правится. Модель зовёт только `transcribe --yes`.

⚠️ ПРОТОКОЛЫ И СПИСКИ ПОБЕДИТЕЛЕЙ В ОЦИФРОВКУ НЕ ИДУТ (персональные данные,
CLAUDE.md P0): инвентарь помечает их `exclude_reason`, и печать выводит
их отдельным списком. Как ищутся — в шапке `problems/olympiad_audit/digitize.py`.
"""
from __future__ import annotations

import csv
import json
import time
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.olympiad_audit import (assemble, claude_eyes, digitize, fixes, judge, max_score,
                                     registry, reread_queue, review_pack, sweeps, transcribe,
                                     triage)

#: Подкоманда → метод. `transcribe` и `assemble` допишутся сюда же.
_SUBCOMMANDS = {
    'inventory': '_inventory',
    'render': '_render',
    'transcribe': '_transcribe',
    'assemble': '_assemble',
    'rescore': '_rescore',
    'triage': '_triage',
    'judge': '_judge',
    'report': '_report',
    'reread': '_reread',
    'review-pack': '_review_pack',
    'control-pack': '_control_pack',
    'apply-fixes': '_apply_fixes',
    'sweeps': '_sweeps',
    'reread-queue': '_reread_queue',
    'max-score': '_max_score',
    'audit-claude': '_audit_claude',
}

PROGRESS_EVERY_PAGES = 100


class Command(BaseCommand):
    help = ('Оцифровка олимпиадных PDF: inventory (опись raw\\), '
            'render (страницы в PNG). В базу не пишет.')

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='subcommand', metavar='ПОДКОМАНДА')

        def common(p):
            p.add_argument('--olympiad', choices=sorted(registry.REGISTRY),
                           help='Слаг олимпиады из реестра аудита (обязателен).')
            p.add_argument('--base', default='v2', metavar='vN',
                           help='Эталон разбора: reference_problems_vN.jsonl, заплатки '
                                'pages_v<N+1> (по умолчанию v2 → pages_v3).')
            p.add_argument('--data-root', metavar='DIR',
                           help='Корень данных олимпиад (по умолчанию '
                                'OLYMPIAD_DATA_ROOT или ..\\weconomics-data\\olympiads).')
            return p

        common(sub.add_parser('inventory', help='Опись всех файлов raw\\.'))
        render = common(sub.add_parser('render', help='PDF → PNG 200 dpi + текст слоя.'))
        render.add_argument('--limit', type=int, default=None,
                            help='Нарисовать не больше N файлов (для пробы).')
        tr = common(sub.add_parser('transcribe', help='Страницы → зрячая модель (деньги!).'))
        tr.add_argument('--max-usd', type=float, default=None,
                        help='Потолок расхода прогона, $ (обязателен).')
        tr.add_argument('--limit', type=int, default=None,
                        help='Не больше N страниц (из ещё не готовых).')
        tr.add_argument('--pages-file', metavar='F',
                        help='Только страницы из файла: по строке «pages/<sha16>/p<N>».')
        tr.add_argument('--workers', type=int, default=20,
                        help='Одновременных вызовов (не больше 20; лимит Z.AI — 50).')
        tr.add_argument('--yes', action='store_true',
                        help='Действительно вызывать модель (без флага — только план).')
        tr.add_argument('--strict-prompt', action='store_true',
                        help='Усиленная инструкция: вступление комплекта, логотипы, строки '
                             'таблиц критериев (transcribe.STRICT_SUFFIX).')
        tr.add_argument('--redo', action='store_true',
                        help='Расшифровать заново и готовые страницы (только с --pages-file).')
        common(sub.add_parser('rescore', help='Пересчитать мерило слоя у готовых страниц '
                                              '(без модели).'))
        asm = common(sub.add_parser('assemble', help='Страницы → задания эталона v2.'))
        asm.add_argument('--events', nargs='*', metavar='EVENT_ID',
                         help='Только эти комплекты (по умолчанию все).')
        asm.add_argument('--no-crop', action='store_true',
                         help='Не вырезать рисунки (быстрая сборка).')
        asm.add_argument('--suffix', default=None, metavar='vN',
                         help='Версия выхода: reference_problems_<vN>.jsonl (по умолчанию v2; '
                              'у новой олимпиады первая оцифровка — v1).')
        asm.add_argument('--v3', action='store_true',
                         help='Собрать в НОВУЮ папку v3\\ с заплатками pages_v3 '
                              '(v2 не трогается).')
        asm.add_argument('--layers', default=None, metavar='pages_v3,pages_v5',
                         help='С --suffix vM: несколько слоёв заплаток по порядку (поздний '
                              'перекрывает ранний) → digitized\\vM\\ (v5: pages_v3, затем pages_v5).')
        asm.add_argument('--keep-keys', default=None, metavar='F',
                         help='С --layers: ключи (комплект, номер, вариант) этого эталона; файл '
                              'ответов не заводит задание с новым ключом, если есть пара по тексту.')
        asm.add_argument('--out-dir', default=None, metavar='DIR',
                         help='С --layers: писать сборку сюда (проверка инварианта).')
        asm.add_argument('--overlay', action='store_true',
                         help='С --suffix vM: заплатки pages_vM поверх страниц и plan '
                              'triage_plan.csv; сверка с v<M-1> (тот не трогается).')
        tri = common(sub.add_parser('triage', help='Очередь «на глаза» → ярусы, срочность.'))
        tri.add_argument('--rows', default=None, metavar='vK',
                         help='Задания для срочности и задачных причин — из '
                              'reference_problems_vK.jsonl (по умолчанию --base).')
        tri.add_argument('--auto-publish', action='store_true',
                         help='Ещё ярус D: страницы заданий к импорту, не прошедшие '
                              'автопроверку (слой < 0,95, числа, скан), — к судье.')
        for name, text in (('judge', 'Судья «картинка против расшифровки» (деньги!).'),
                           ('reread', 'Перечитывание needs_fix (деньги!).')):
            runner = common(sub.add_parser(name, help=text))
            runner.add_argument('--max-usd', type=float, default=None,
                                help='Потолок расхода этой фазы, $ (обязателен).')
            runner.add_argument('--limit', type=int, default=None)
            runner.add_argument('--workers', type=int, default=20)
            runner.add_argument('--resume', action='store_true',
                                help='Докачка (готовые страницы и так пропускаются).')
            runner.add_argument('--yes', action='store_true',
                                help='Действительно вызывать модель (без флага — только план).')
            runner.add_argument('--queue', metavar='CSV',
                                help='Готовый список страниц (reread_queue_vN.csv: '
                                     'set;page;priority;n_reasons;reasons) вместо плана triage; '
                                     'подсказка модели — колонка reasons.')
            runner.add_argument('--priorities', default='1,2', metavar='1,2',
                                help='С --queue: какие приоритеты брать.')
            runner.add_argument('--pages', metavar='F',
                                help='С --queue: только эти страницы (по строке «<sha16>/pN»; пилот).')
            runner.add_argument('--eye-md', metavar='F',
                                help='С --queue: EYE_REVIEW_FINDINGS_*.md — формулировки сверки '
                                     'глазами в подсказку.')
            runner.add_argument('--hint-fixes', metavar='F',
                                help='С --queue: fixes_vN.json — правки страницы в подсказку '
                                     '(«на картинке «…», а не «…»).')
            if name == 'reread':
                runner.add_argument('--second', action='store_true',
                                    help='С --queue: второй заход для human (замечания обоих '
                                         'судей, лучшая из трёх версий).')
                runner.add_argument('--force-eyes', action='store_true',
                                    help='С --queue: перечитать и ok_judge-страницы с находкой '
                                         'сверки глазами.')
                runner.add_argument('--rejudge-answers', action='store_true',
                                    help='Не перечитывать, а пересудить human-страницы с '
                                         'замечанием про ответ (обе расшифровки).')
            if name == 'judge':
                runner.add_argument('--only-control', action='store_true',
                                    help='Только выборка контроля ярусов B/C (смотреть первой).')
                runner.add_argument('--only-auto', action='store_true',
                                    help='Только B/C вне контроля у заданий к импорту '
                                         '(уверенность для автопубликации).')
                runner.add_argument('--redo-answer-artifact', action='store_true',
                                    help='Пересудить страницы с замечанием про «Ответ» '
                                         '(судья теперь не видит поле answer).')
        common(sub.add_parser('report', help='Сводка судьи для стоп-гейта.'))
        common(sub.add_parser('review-pack', help='Остаток → пакет для просмотра глазами.'))
        common(sub.add_parser('control-pack', help='30 страниц яруса A, пропущенных судьёй '
                                                   '(обе олимпиады) → пакет контроля.'))
        fx = common(sub.add_parser('apply-fixes', help='Эталон vA + точечные правки → vB.'))
        fx.add_argument('--from', dest='from_version', metavar='vA',
                        help='Вход: reference_problems_vA.jsonl (digitized\\vA\\ или digitized\\).')
        fx.add_argument('--in', dest='in_file', metavar='F', help='Вход — этот файл.')
        fx.add_argument('--to', dest='to_version', metavar='vB',
                        help='Выход: digitized\\vB\\reference_problems_vB.jsonl.')
        fx.add_argument('--out', dest='out_file', metavar='F', help='Выход — этот файл.')
        fx.add_argument('--fixes', nargs='+', required=True, metavar='F',
                        help='Файлы правок fixes_vN.json (применяются по порядку).')
        fx.add_argument('--no-autofix', action='store_true',
                        help='Без автоисправлений U+00AD и повторов «Ответ:».')
        fx.add_argument('--replace', action='store_true',
                        help='Перезаписать существующий выход (без флага — отказ).')
        sw = common(sub.add_parser('sweeps', help='9 классов автопроверок эталона vN.'))
        sw.add_argument('--version', required=True, metavar='vN')
        sw.add_argument('--layers', default=None, metavar='pages_vK,…',
                        help='Папки заплаток страниц по старшинству (по умолчанию '
                             'pages_vK с K ≤ N, старшая первой).')
        sw.add_argument('--rows', default=None, metavar='F',
                        help='Задания из этого файла (по умолчанию vN\\reference_problems_vN.jsonl).')
        sw.add_argument('--out', dest='out_file', metavar='F',
                        help='Куда писать находки (по умолчанию vN\\sweeps_vN.json).')
        ms = common(sub.add_parser('max-score', help='max_score там, где он выводится однозначно.'))
        ms.add_argument('--version', required=True, metavar='vN')
        ms.add_argument('--write', action='store_true',
                        help='Записать заполненные max_score в vN\\reference_problems_vN.jsonl '
                             '(без флага — только отчёт).')
        rq = common(sub.add_parser('reread-queue', help='Очередь перечитывания по sweeps и глазам.'))
        rq.add_argument('--version', required=True, metavar='vN')
        rq.add_argument('--eye', required=True, metavar='F',
                        help='Находки сверки глазами (eye_queue_vN.json).')
        rq.add_argument('--also', nargs='*', default=[], metavar='SLUG',
                        help='Добавить в ту же очередь эти олимпиады (общий бюджет).')
        rq.add_argument('--cap-usd', type=float, default=5.0,
                        help='Бюджет приоритетов 1+2 по $0,006 за страницу.')
        rq.add_argument('--out', dest='out_file', metavar='F')
        ac = common(sub.add_parser('audit-claude', help='Аудит страниц «глазами Claude» → v7 / v3.'))
        ac.add_argument('--step', required=True,
                        choices=('units', 'jobs', 'submit', 'collect', 'check', 'build'))
        ac.add_argument('--model', default='sonnet', choices=sorted(claude_eyes.MODEL_ALIASES))
        ac.add_argument('--units-file', metavar='F',
                        help='Только эти единицы (id по строке; по умолчанию — все).')
        ac.add_argument('--jobs-dir', metavar='DIR', help='Куда писать задания для агентов (jobs).')
        ac.add_argument('--import-dir', metavar='DIR',
                        help='check: сначала принять ответы агентов из DIR\\<модель>\\<единица>.json.')
        ac.add_argument('--max-usd', type=float,
                        help='Потолок денег (submit); на 90 %% новые пакеты не отправляются.')
        ac.add_argument('--ledger', metavar='F',
                        help='Журнал расхода (по умолчанию <корень>\\audit_claude_cost.jsonl).')
        ac.add_argument('--review', metavar='F', help='build: куда писать страницу нерешённого.')
        ac.add_argument('--answers-dir', metavar='DIR',
                        help='build: ответы к тестам из ключа (<комплект>.json), только для пустых answer.')
        ac.add_argument('--yes', action='store_true', help='submit: действительно отправить (деньги).')

    # ── Вход ────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        name = options.get('subcommand')
        if name not in _SUBCOMMANDS:
            raise CommandError(
                f'Нужна подкоманда: {", ".join(_SUBCOMMANDS)}. Ничего не сделано.')
        if not options.get('olympiad'):
            raise CommandError(
                '--olympiad <слаг> обязателен (vp, mosh, …): папка аудита '
                'берётся из реестра. Ничего не сделано.')
        self.olympiad = registry.get(options['olympiad'])
        root = (Path(options['data_root']) if options.get('data_root')
                else digitize.default_data_root(settings.BASE_DIR))
        self.audit_dir = root / self.olympiad.audit_dir
        if not (self.audit_dir / 'raw').is_dir():
            raise CommandError(f'Нет папки raw\\ аудита: {self.audit_dir}')
        self.digitized = self.audit_dir / 'digitized'
        self.root = root
        self.base = options.get('base') or 'v2'
        self.patches = triage.patches_for(self.base)
        return getattr(self, _SUBCOMMANDS[name])(options)

    def _say(self, text=''):
        self.stdout.write(text)
        self.stdout.flush()  # прогресс виден и при выводе в файл

    # ── inventory ───────────────────────────────────────────────────────

    def _inventory(self, options):
        started = time.monotonic()
        rows = digitize.build_inventory(self.olympiad.slug, self.audit_dir)
        digitize.write_jsonl(self.digitized / 'inventory.jsonl', rows)
        events = digitize.build_events_files(self.olympiad.slug, self.audit_dir, rows)
        digitize.write_jsonl(self.digitized / 'events_files.jsonl', events)
        summary = digitize.summarize(rows)

        self._say(f'Инвентарь {self.olympiad.slug}: {summary["files"]} файлов '
                  f'→ {self.digitized / "inventory.jsonl"}')
        self._say('\nПо виду (kind):')
        for kind in digitize.KINDS:
            self._say(f'  {kind:<10} {summary["by_kind"].get(kind, 0)}')
        self._say('\nВид × оцифровка:')
        for key, n in summary['kind_x_digitize'].items():
            self._say(f'  {key:<16} {n}')
        self._say('\nОцифровка / причина исключения:')
        for reason, n in sorted(summary['by_reason'].items(), key=lambda x: -x[1]):
            self._say(f'  {n:>5}  {reason}')
        total_kind = sum(summary['by_kind'].values())
        total_reason = sum(summary['by_reason'].values())
        ok = total_kind == total_reason == summary['files']
        self._say(f'\nКонтроль: Σ по виду {total_kind}, Σ по причинам '
                  f'{total_reason}, файлов {summary["files"]} — '
                  f'{"сходится" if ok else "НЕ СХОДИТСЯ"}')
        if not ok:
            raise CommandError('Сумма по категориям не равна числу файлов.')

        self._say(f'\nPDF к оцифровке: {summary["pdf_to_digitize"]} '
                  f'(из них сканов без слоя: {summary["pdf_scans"]}); '
                  f'страниц {summary["pages_to_digitize"]}: со слоем '
                  f'{summary["pages_with_layer"]}, без слоя {summary["pages_scan"]}')
        self._say('Страниц к оцифровке по году и этапу (по первому комплекту файла):')
        for key, n in summary['pages_by_year_stage'].items():
            self._say(f'  {key:<18} {n}')

        personal = summary['personal_data']
        self._say(f'\nПротоколы/списки (персональные данные, в модель НЕ идут): '
                  f'{len(personal) or "не найдено"}')
        for row in rows:
            if row['exclude_reason'] == digitize.REASON_PERSONAL:
                self._say(f'  {row["file"]}  [{row.get("personal_data_hit", "")}]')

        conflicts = [r for r in rows if r.get('duplicate_conflict')]
        if conflicts:
            self._say(f'\nДубли с другой раскладкой по эталону (верна по '
                      f'содержимому — первого файла): {len(conflicts)}')
            for row in conflicts:
                self._say(f'  {row["file"]}: {row["duplicate_conflict"]}')

        new = [e for e in events if e['new']]
        self._say(f'\nКомплектов с файлами: {len(events)} → '
                  f'{self.digitized / "events_files.jsonl"}; новых (нет в '
                  f'reference_events.jsonl): {len(new)}')
        for event in new:
            files = [f['file'].rsplit('/', 1)[-1]
                     for key in ('task_files', 'solution_files', 'criteria_files')
                     for f in event[key]]
            self._say(f'  {event["event_id"]}: {", ".join(files)}')
        self._say(f'\nГотово за {time.monotonic() - started:.0f} с.')

    # ── render ──────────────────────────────────────────────────────────

    def _render(self, options):
        path = self.digitized / 'inventory.jsonl'
        if not path.is_file():
            raise CommandError(f'Нет инвентаря: {path}. Сначала inventory.')
        rows = digitize.read_jsonl(path)
        targets = digitize.render_targets(rows)
        limit = options.get('limit')
        started = time.monotonic()
        manifest, drawn, reused, done_files, next_mark = [], 0, 0, 0, PROGRESS_EVERY_PAGES
        total_pages = sum(r['pages'] for r in targets)
        seen_pages = 0
        for row in targets:
            out_dir = self.digitized / row['page_dir']
            complete = all((out_dir / f'p{n}.{ext}').is_file()
                           for n in range(1, row['pages'] + 1)
                           for ext in ('png', 'txt'))
            if limit is not None and done_files >= limit and not complete:
                continue
            pages, n_drawn = digitize.render_pdf(
                digitize.source_path(self.audit_dir, row), out_dir)
            if n_drawn:
                done_files += 1
            drawn += n_drawn
            reused += len(pages) - n_drawn
            for page in pages:
                manifest.append({'file': row['file'], 'page_dir': row['page_dir'],
                                 **page, 'png': f'{row["page_dir"]}/{page["png"]}'})
            seen_pages += len(pages)
            while seen_pages >= next_mark:
                self._say(f'  … {seen_pages}/{total_pages} страниц '
                          f'({time.monotonic() - started:.0f} с)')
                next_mark += PROGRESS_EVERY_PAGES
        digitize.write_jsonl(self.digitized / 'pages_manifest.jsonl', manifest)
        scaled = sum(1 for m in manifest if m.get('scaled_to_max_side'))
        size = sum(f.stat().st_size for f in (self.digitized / 'pages').rglob('*')
                   if f.is_file()) if (self.digitized / 'pages').is_dir() else 0
        self._say(f'Отрисовано страниц: {drawn}; уже было: {reused}; '
                  f'в манифесте: {len(manifest)} из {total_pages}; '
                  f'уменьшено до {digitize.MAX_SIDE_PX} px: {scaled}; '
                  f'pages\\ на диске: {size / 2**30:.2f} ГБ; '
                  f'{time.monotonic() - started:.0f} с.')

    # ── transcribe ──────────────────────────────────────────────────────

    def _transcribe(self, options):
        if options.get('max_usd') is None:
            raise CommandError('--max-usd обязателен: потолок расхода прогона в '
                               'долларах. Ничего не сделано.')
        path = self.digitized / 'inventory.jsonl'
        if not path.is_file():
            raise CommandError(f'Нет инвентаря: {path}. Сначала inventory и render.')
        jobs = transcribe.build_jobs(digitize.read_jsonl(path), str(self.digitized),
                                     self.olympiad.olympiad_name)
        if options.get('pages_file'):
            with open(options['pages_file'], encoding='utf-8') as handle:
                wanted = {line.strip() for line in handle if line.strip()}
            jobs = [job for job in jobs if job.key in wanted]
        if options.get('redo') and not options.get('pages_file'):
            raise CommandError('--redo — только вместе с --pages-file. Ничего не сделано.')
        all_todo = (list(jobs) if options.get('redo')
                    else transcribe.todo(jobs, str(self.digitized)))
        todo = all_todo
        if options.get('limit') is not None:
            todo = todo[:options['limit']]
        cost_log = transcribe.CostLog(str(self.digitized / 'transcribe_cost.jsonl'))
        measured = cost_log.average('page')
        per_page = measured if measured is not None else transcribe.DEFAULT_PAGE_USD
        scans = sum(not job.has_layer for job in todo)
        # Смета: вызов на страницу + повтор у ~20 % страниц со слоем + судья у
        # ~половины сканов (страницы с формулами/таблицами/рисунками).
        calls = len(todo) + 0.2 * (len(todo) - scans) + 0.5 * scans
        spent_before, calls_before = cost_log.total()
        self._say(f'ПЛАН transcribe {self.olympiad.slug}: страниц всего {len(jobs)}, '
                  f'готово {len(jobs) - len(all_todo)}, к вызову {len(todo)} '
                  f'(со слоем {len(todo) - scans}, сканов {scans}; на глаза по '
                  f'выборке {sum(j.eyes_sample for j in todo)}).')
        self._say(f'  Вызовов ≈ {calls:.0f}; цена страницы '
                  f'{"по журналу" if measured is not None else "до замера"} '
                  f'${per_page:.4f} → ≈ ${calls * per_page:.2f}; потолок '
                  f'${options["max_usd"]:.2f}; модель {transcribe.MODEL}, '
                  f'потоков {min(options["workers"], 20)}.')
        self._say(f'  Уже потрачено по журналу: ${spent_before:.4f} за {calls_before} вызовов.')
        if not options.get('yes'):
            self._say('ПЛАН — ни одного вызова модели. Запуск: тот же вызов с --yes.')
            return
        if not todo:
            self._say('Расшифровывать нечего — все страницы готовы.')
            return
        provider = transcribe.make_provider()
        if not provider.is_available():
            raise CommandError(provider.unavailable_reason() or 'Поставщик недоступен.')
        runner = transcribe.Transcriber(
            root=str(self.digitized), provider=provider,
            budget=transcribe.Budget(options['max_usd'], per_page * 1.3),
            cost_log=cost_log, workers=options['workers'], stdout=self.stdout,
            strict=bool(options.get('strict_prompt')))
        stats = runner.run(todo)
        spent_after, calls_after = cost_log.total()
        self._say(f'ГОТОВО: {dict(stats)}; потрачено в прогоне '
                  f'${runner.budget.spent:.4f} ({runner.budget.calls} вызовов); '
                  f'всего по журналу ${spent_after:.4f} за {calls_after} вызовов.')
        if runner.stopped:
            self._say(f'ОСТАНОВЛЕНО: {runner.stopped}')

    # ── assemble ────────────────────────────────────────────────────────

    def _assemble(self, options):
        events_path = self.audit_dir / 'reference_events.jsonl'
        reference_events = digitize.read_jsonl(events_path) if events_path.is_file() else []
        v1_rows = []
        for candidate in ('session2', 'session1'):
            v1 = self.audit_dir / candidate / 'reference_problems_full.jsonl'
            if v1.is_file():
                v1_rows = digitize.read_jsonl(v1)
                break
        extra = {}
        if options.get('suffix') and not options.get('v3'):
            extra = {'suffix': options['suffix']}
        if options.get('overlay'):
            if not options.get('suffix'):
                raise CommandError('--overlay — только с --suffix vM (заплатки pages_vM).')
            plan_path = self.digitized / 'triage_plan.csv'
            norm = triage.norm_pages(triage.read_plan(plan_path)) if plan_path.is_file() else ()
            extra['overlay'] = triage.PageOverlay(str(self.digitized), norm=norm,
                                                  patches=f'pages_{options["suffix"]}')
            extra['figures_subdir'] = f'figures_{options["suffix"]}'
        if options.get('v3'):
            plan_path = self.digitized / 'triage_plan.csv'
            norm = triage.norm_pages(triage.read_plan(plan_path)) if plan_path.is_file() else ()
            extra = {'overlay': triage.PageOverlay(str(self.digitized), norm=norm),
                     'out_dir': str(self.digitized / 'v3'), 'suffix': 'v3'}
        if options.get('layers'):
            # v5: pages_v3 (как сборка v3: «норма» ярусов B/C из triage_plan.csv), затем
            # pages_v5 (перечитывание по очереди; баллы блоков берегутся keep_points).
            if not options.get('suffix'):
                raise CommandError('--layers — только с --suffix vM.')
            plan_path = self.digitized / 'triage_plan.csv'
            norm = triage.norm_pages(triage.read_plan(plan_path)) if plan_path.is_file() else ()
            names = [x.strip() for x in options['layers'].split(',') if x.strip()]
            for name in names:
                if not (self.digitized / name).is_dir():
                    self._say(f'  ⚠ слоя {name} нет на диске — пустой слой')
            if options.get('keep_keys'):
                extra['keep_keys'] = {(r['event_id'], r['number'], r.get('task_variant') or '')
                                      for r in digitize.read_jsonl(Path(options['keep_keys']))}
            extra = {**extra, 'overlay': triage.layer_stack(str(self.digitized), names, norm),
                     'suffix': options['suffix'],
                     'out_dir': options.get('out_dir') or str(self.digitized / options['suffix'])}
        summary = assemble.assemble(
            str(self.digitized), reference_events, v1_rows, model=transcribe.MODEL,
            only_events=set(options['events']) if options.get('events') else None,
            crop=not options.get('no_crop'), profile=assemble.profile_for(self.olympiad.slug),
            **extra)
        suffix = extra.get('suffix', 'v2')
        out_dir = Path(extra.get('out_dir', self.digitized))
        self._say(f'Сборка {self.olympiad.slug} → {out_dir / f"reference_problems_{suffix}.jsonl"}')
        for key, value in sorted(summary.items()):
            self._say(f'  {key}: {value}')
        if options.get('overlay'):
            previous = f'v{int(options["suffix"].lstrip("v")) - 1}'
            report = triage.compare_versions(
                digitize.read_jsonl(self.digitized / f'reference_problems_{previous}.jsonl'),
                digitize.read_jsonl(out_dir / f'reference_problems_{suffix}.jsonl'))
            name = f'compare_{previous}_{suffix}_overlay.json'
            (out_dir / name).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                        encoding='utf-8')
            self._say(f'\nСверка {suffix} с {previous} → {name}:')
            for key, value in report.items():
                self._say(f'  {key}: {len(value) if isinstance(value, list) else value}')
        if options.get('v3'):
            report = triage.compare_versions(
                digitize.read_jsonl(self.digitized / 'reference_problems_v2.jsonl'),
                digitize.read_jsonl(out_dir / 'reference_problems_v3.jsonl'),
                v1_counts=dict(Counter(r['event_id'] for r in v1_rows)))
            (out_dir / 'compare_v2_v3.json').write_text(
                json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
            self._say('\nСверка v3 с v2:')
            for key, value in report.items():
                self._say(f'  {key}: {len(value) if isinstance(value, list) else value}')

    # ── rescore ─────────────────────────────────────────────────────────

    def _rescore(self, options):
        jobs = transcribe.build_jobs(digitize.read_jsonl(self.digitized / 'inventory.jsonl'),
                                     str(self.digitized), self.olympiad.olympiad_name)
        counts = {}
        for job in jobs:
            status = transcribe.rescore(job, str(self.digitized))
            counts[status] = counts.get(status, 0) + 1
        self._say(f'Пересчёт мерила {self.olympiad.slug} (без модели): {counts}')

    # ── triage ──────────────────────────────────────────────────────────

    def _triage(self, options):
        inventory = digitize.read_jsonl(self.digitized / 'inventory.jsonl')
        rows_version = options.get('rows') or self.base
        v2_rows = digitize.read_jsonl(self.digitized / f'reference_problems_{rows_version}.jsonl')
        records = list(triage.iter_page_records(str(self.digitized)))
        file_to_dir = {r['file']: r['page_dir'] for r in inventory if r.get('page_dir')}
        risks, rescored = None, Counter()
        if self.base != 'v2':
            # Сессия 2 (финграмотность и бизнес): мерило слоя пересчитывается
            # без модели (точность против всего слоя). Страница, прошедшая порог,
            # — заплатка ok_rescore; новые поля мерила — в заплатке, старый
            # p<N>.json не меняется. Плюс задачные причины яруса A.
            jobs = {job.key: job for job in transcribe.build_jobs(
                inventory, str(self.digitized), self.olympiad.olympiad_name)}
            fresh = []
            for record in records:
                key = triage.page_key(record)
                new, fields = triage.rescore_record(record, jobs.get(key))
                if fields is not None:
                    path = triage.v3_path(str(self.digitized), record['page_dir'],
                                          record['page'], self.patches)
                    patch = triage.read_json(path) or {}
                    if not patch:
                        patch = {'file': record.get('file'), 'page_dir': record['page_dir'],
                                 'page': record['page'], 'phase': 'rescore',
                                 'status': (triage.RESCORE_OK if record.get('needs_eyes')
                                            and not new.get('needs_eyes') else 'rescored')}
                    patch['rescore'] = fields
                    triage.write_json_atomic(path, patch)
                    rescored['мерило изменилось'] += 1
                    if record.get('needs_eyes') and not new.get('needs_eyes'):
                        rescored['«на глаза» снято пересчётом мерила'] += 1
                fresh.append(new)
            records = fresh
            events = digitize.read_jsonl(self.digitized / 'events_files.jsonl')
            with_answers = {e['event_id'] for e in events
                            if e.get('solution_files') or e.get('criteria_files')}
            risks = triage.task_risks(v2_rows, with_answers, file_to_dir)
        events_by_file = {r['file']: r.get('event_ids') or [] for r in inventory}
        check_rows = []
        for session in ('session2', 'session1'):
            path = self.audit_dir / session / 'existing_refs_text_check.csv'
            if path.is_file():
                with open(path, encoding='utf-8-sig', newline='') as handle:
                    check_rows = list(csv.DictReader(handle))
                break
        from problems.models import OlympiadRef
        official_ids = list(OlympiadRef.objects.filter(
            olympiad_slug=self.olympiad.slug, source_site='official'
        ).values_list('record_id', flat=True))
        bank = triage.bank_keys(check_rows, official_ids)
        rows = triage.build_plan(records, v2_rows, file_to_dir, bank, events_by_file,
                                 risks=risks, auto_publish=bool(options.get('auto_publish')))
        triage.write_plan(self.digitized / 'triage_plan.csv', rows)
        summary = triage.summarize_plan(rows)
        summary['ключей «в банке есть» (таблица проверки + привязки official)'] = len(bank)
        summary.update(dict(rescored))
        (self.digitized / 'triage_summary.json').write_text(
            json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
        self._say(f'Разбор очереди {self.olympiad.slug} → {self.digitized / "triage_plan.csv"}')
        for key, value in summary.items():
            self._say(f'  {key}: {value}')

    # ── judge / reread ──────────────────────────────────────────────────

    def _runner_setup(self, options):
        if options.get('max_usd') is None:
            raise CommandError('--max-usd обязателен: потолок расхода фазы в долларах. '
                               'Ничего не сделано.')
        plan_path = self.digitized / 'triage_plan.csv'
        if not plan_path.is_file():
            raise CommandError(f'Нет {plan_path}. Сначала triage.')
        plan_rows = triage.read_plan(plan_path)
        jobs = {job.key: job for job in transcribe.build_jobs(
            digitize.read_jsonl(self.digitized / 'inventory.jsonl'), str(self.digitized),
            self.olympiad.olympiad_name)}
        return plan_rows, jobs, transcribe.CostLog(str(self.digitized / 'triage_cost.jsonl'))

    def _run_phase(self, options, runner_class, keys, setup, estimate, per_page, label):
        plan_rows, jobs, cost_log = setup
        todo = [jobs[k] for k in keys if k in jobs]
        if options.get('limit') is not None:
            todo = todo[:options['limit']]
        spent, calls = cost_log.total()
        self._say(f'ПЛАН {label} {self.olympiad.slug}: страниц к вызову {len(todo)}; '
                  f'≈ ${len(todo) * per_page:.2f} (≈ ${per_page:.4f} за страницу); потолок '
                  f'${options["max_usd"]:.2f}; уже потрачено в этой сессии ${spent:.4f} '
                  f'за {calls} вызовов.')
        if not options.get('yes'):
            self._say('ПЛАН — ни одного вызова модели. Запуск: тот же вызов с --yes.')
            return
        if not todo:
            self._say('Нечего делать — все страницы готовы.')
            return
        provider = transcribe.make_provider()
        if not provider.is_available():
            raise CommandError(provider.unavailable_reason() or 'Поставщик недоступен.')
        runner = runner_class(
            root=str(self.digitized), provider=provider,
            budget=transcribe.Budget(options['max_usd'], estimate), cost_log=cost_log,
            workers=options['workers'], stdout=self.stdout,
            plan={r['страница']: r for r in plan_rows}, patches=self.patches)
        stats = runner.run(todo)
        self._say(f'ГОТОВО: {dict(stats)}; потрачено в прогоне ${runner.budget.spent:.4f} '
                  f'({runner.budget.calls} вызовов).')
        if runner.stopped:
            self._say(f'ОСТАНОВЛЕНО: {runner.stopped}')

    # ── judge / reread по готовому списку с подсказкой (v5) ─────────────

    def _queue_setup(self, options):
        """Очередь → (ключи страниц, приоритеты, подсказки, прежние заплатки, задания)."""
        if options.get('max_usd') is None:
            raise CommandError('--max-usd обязателен: потолок расхода фазы в долларах. '
                               'Ничего не сделано.')
        if self.base == 'v2':
            raise CommandError('--queue — с --base vN (N ≥ 3): заплатки pages_v<N+1>, '
                               'текущая расшифровка — с заплатками pages_v3…pages_vN.')
        rows = reread_queue.read(options['queue'])
        wanted = {p.strip() for p in options['priorities'].split(',') if p.strip()}
        keys, prio = judge.queue_keys(rows, self.olympiad.slug, wanted)
        if options.get('pages'):
            with open(options['pages'], encoding='utf-8') as handle:
                only = {'pages/' + line.strip() for line in handle if line.strip()}
            keys = [k for k in keys if k in only]
        eye = None
        if options.get('eye_md'):
            eye = reread_queue.eye_findings(Path(options['eye_md']).read_text(encoding='utf-8'))
        fx = fixes.load_fixes(options['hint_fixes']) if options.get('hint_fixes') else None
        hints = reread_queue.page_hints(rows, eye=eye, fixes=fx, set_name=self.olympiad.slug)
        top = int(self.base.lstrip('v'))
        prior = [f'pages_v{k}' for k in range(3, top + 1) if (self.digitized / f'pages_v{k}').is_dir()]
        jobs = {job.key: job for job in transcribe.build_jobs(
            digitize.read_jsonl(self.digitized / 'inventory.jsonl'), str(self.digitized),
            self.olympiad.olympiad_name)}
        cost_log = transcribe.CostLog(str(self.digitized / f'queue_cost_{self.patches}.jsonl'))
        missing = [k for k in keys if k not in jobs]
        if missing:
            self._say(f'  ⚠ страниц очереди без картинки/описи: {len(missing)} ({missing[:3]})')
        return keys, prio, hints, prior, jobs, cost_log, eye

    def _queue_phase(self, options, runner_class, keys, setup, estimate, per_page, label):
        _all, prio, hints, prior, jobs, cost_log, _eye = setup
        todo = [jobs[k] for k in keys if k in jobs]
        if options.get('limit') is not None:
            todo = todo[:options['limit']]
        spent, calls = cost_log.total()
        self._say(f'ПЛАН {label} {self.olympiad.slug} (очередь, база {self.base}, заплатки '
                  f'{self.patches}, текущая расшифровка: pages + {", ".join(prior) or "—"}): '
                  f'страниц к вызову {len(todo)}; ≈ ${len(todo) * per_page:.2f} '
                  f'(≈ ${per_page:.4f} за страницу); потолок ${options["max_usd"]:.2f}; '
                  f'по журналу очереди уже потрачено ${spent:.4f} за {calls} вызовов.')
        with_hint = sum(1 for j in todo if hints.get(j.key.partition('/')[2]))
        self._say(f'  с подсказкой: {with_hint} из {len(todo)}; по приоритетам: '
                  f'{dict(Counter(prio[j.key] for j in todo))}')
        if not options.get('yes'):
            self._say('ПЛАН — ни одного вызова модели. Запуск: тот же вызов с --yes.')
            return
        if not todo:
            self._say('Нечего делать — все страницы готовы.')
            return
        provider = transcribe.make_provider()
        if not provider.is_available():
            raise CommandError(provider.unavailable_reason() or 'Поставщик недоступен.')
        runner = runner_class(
            root=str(self.digitized), provider=provider,
            budget=transcribe.Budget(options['max_usd'], estimate), cost_log=cost_log,
            workers=options['workers'], stdout=self.stdout, patches=self.patches,
            prior=prior, hints=hints, priority=prio)
        runner.progress_name = f'queue_progress_{self.patches}.json'
        stats = runner.run(todo)
        self._say(f'ГОТОВО: {dict(stats)}; потрачено в прогоне ${runner.budget.spent:.4f} '
                  f'({runner.budget.calls} вызовов).')
        if runner.stopped:
            self._say(f'ОСТАНОВЛЕНО: {runner.stopped}')

    def _judge_queue(self, options):
        setup = self._queue_setup(options)
        keys = judge.judge_todo(setup[0], str(self.digitized), self.patches)
        self._queue_phase(options, judge.QueueJudgeRunner, keys, setup, estimate=0.0025,
                          per_page=0.0015, label='judge')

    def _reread_queue_pages(self, options):
        setup = self._queue_setup(options)
        if options.get('second'):
            keys = judge.select_for_second(setup[0], str(self.digitized), self.patches)
            self._queue_phase(options, judge.QueueSecondRunner, keys, setup, estimate=0.006,
                              per_page=0.0035, label='reread --second')
            return
        force = set()
        if options.get('force_eyes'):
            force = {k for k in setup[0] if any(h.startswith(('сверка глазами', 'сомнение'))
                                                for h in setup[2].get(k.partition('/')[2], []))}
        keys = judge.select_for_queue_reread(setup[0], str(self.digitized), self.patches, force)
        self._queue_phase(options, judge.QueueRereadRunner, keys, setup, estimate=0.006,
                          per_page=0.0035, label='reread')

    def _judge(self, options):
        if options.get('queue'):
            return self._judge_queue(options)
        setup = self._runner_setup(options)
        if options.get('redo_answer_artifact'):
            keys = judge.answer_artifact_pages(judge.v3_statuses(str(self.digitized),
                                                                 self.patches))
        else:
            keys = judge.judge_todo(
                triage.pages_to_judge(setup[0],
                                      only='control' if options.get('only_control') else
                                      'auto' if options.get('only_auto') else None),
                str(self.digitized), self.patches)
        self._run_phase(options, judge.JudgeRunner, keys, setup, estimate=0.0016,
                        per_page=0.0012, label='judge')

    def _reread(self, options):
        if options.get('queue'):
            return self._reread_queue_pages(options)
        setup = self._runner_setup(options)
        if options.get('rejudge_answers'):
            keys = judge.answer_rejudge_pages(judge.v3_statuses(str(self.digitized),
                                                                self.patches))
            self._run_phase(options, judge.AnswerRejudgeRunner, keys, setup, estimate=0.004,
                            per_page=0.0025, label='rejudge-answers')
            return
        keys = judge.select_for_reread(
            sorted(judge.v3_statuses(str(self.digitized), self.patches)), str(self.digitized),
            self.patches)
        self._run_phase(options, judge.RereadRunner, keys, setup, estimate=0.005,
                        per_page=0.0035, label='reread')

    def _report(self, options):
        plan_rows = triage.read_plan(self.digitized / 'triage_plan.csv')
        report = judge.judge_report(plan_rows, judge.v3_statuses(str(self.digitized),
                                                                 self.patches))
        self._say(json.dumps(report, ensure_ascii=False, indent=1))

    # ── review-pack ─────────────────────────────────────────────────────

    def _review_pack(self, options):
        plan_rows = triage.read_plan(self.digitized / 'triage_plan.csv')
        patches = judge.v3_statuses(str(self.digitized), self.patches)
        records = {triage.page_key(r): r for r in triage.iter_page_records(str(self.digitized))}
        items = review_pack.build_items(plan_rows, patches, records)
        result = review_pack.build_pack(str(self.digitized), items)
        self._say(f'Пакет просмотра: {result["packs"]}; {result["index"]}; {result["csv"]}')

    def _control_pack(self, options):
        candidates, context, seen = [], {}, set()
        for slug in sorted(registry.REGISTRY):
            digitized = self.root / registry.get(slug).audit_dir / 'digitized'
            plan_path = digitized / 'triage_plan.csv'
            if digitized in seen or not plan_path.is_file():
                continue          # одна папка аудита — один раз (раньше vp-ob/vp-fingram делили её с vp)
            seen.add(digitized)
            plan_rows = triage.read_plan(plan_path)
            plan = {r['страница']: r for r in plan_rows}
            records = {triage.page_key(r): r for r in triage.iter_page_records(str(digitized))}
            for key in review_pack.control_candidates(
                    plan_rows, judge.v3_statuses(str(digitized))):
                candidates.append((slug, key))
                context[(slug, key)] = (digitized, plan[key], records[key])
        picked = review_pack.pick_control(candidates)
        entries = []
        for slug, key in picked:
            digitized, row, record = context[(slug, key)]
            entries.append({'olympiad': slug, 'digitized': str(digitized), 'key': key,
                            'blocks': record.get('blocks') or [], 'tasks': row['задания'],
                            'events': row['комплекты']})
        result = review_pack.build_control_pack(entries, str(self.root / 'human_review_control'))
        self._say(f'Контроль судьи: кандидатов {len(candidates)}, выбрано {result["pages"]} '
                  f'(seed {review_pack.CONTROL_PACK_SEED}); {result["index"]}')

    # ── apply-fixes / sweeps / reread-queue (инструменты v4 в репозитории) ──

    def _version_rows_path(self, version):
        """reference_problems_vN.jsonl: digitized\\vN\\ (v3, v4…) или digitized\\ (v1, v2)."""
        for path in (self.digitized / version / f'reference_problems_{version}.jsonl',
                     self.digitized / f'reference_problems_{version}.jsonl'):
            if path.is_file():
                return path
        return self.digitized / version / f'reference_problems_{version}.jsonl'

    def _apply_fixes(self, options):
        if bool(options.get('from_version')) == bool(options.get('in_file')):
            raise CommandError('Нужен ровно один вход: --from vA или --in F. Ничего не сделано.')
        if bool(options.get('to_version')) == bool(options.get('out_file')):
            raise CommandError('Нужен ровно один выход: --to vB или --out F. Ничего не сделано.')
        src = (Path(options['in_file']) if options.get('in_file')
               else self._version_rows_path(options['from_version']))
        if not src.is_file():
            raise CommandError(f'Нет входа: {src}')
        label = options.get('to_version') or Path(options['out_file']).stem.replace(
            'reference_problems_', '')
        out = (Path(options['out_file']) if options.get('out_file')
               else self.digitized / label / f'reference_problems_{label}.jsonl')
        if out.resolve() == src.resolve():
            raise CommandError('Вход и выход — один файл: правки на месте запрещены.')
        if out.exists() and not options.get('replace'):
            raise CommandError(f'Выход уже есть: {out}. Без --replace не перезаписываю.')
        base_label = options.get('from_version') or src.stem.replace('reference_problems_', '')
        rows = fixes.read_rows(src)
        all_fixes = []
        for path in options['fixes']:
            all_fixes.extend(fixes.load_fixes(path))
        new, log, auto, orig = fixes.apply_version(
            str(self.digitized), rows, all_fixes, self.olympiad.slug, base_label,
            with_autofix=not options.get('no_autofix'))
        fixes.write_rows(str(out), new)
        fixes.write_logs(str(out.parent), log, auto)
        text, changed = fixes.changes_md(
            orig, new, f'{label}: что изменилось относительно {base_label} ({self.olympiad.slug})')
        (out.parent / f'{label}_changes.md').write_text(text, encoding='utf-8')
        self._say(f'Правки {self.olympiad.slug}: {src} → {out}')
        self._say(f'  правок {len(log)}: {fixes.counts(log)}; автоисправлений {len(auto)}; '
                  f'изменено заданий {changed}')

        def empty(rs):
            return sum(1 for r in rs if not (r.get('statement_md') or '').strip())
        self._say(f'  заданий {len(rows)} → {len(new)}; пустых условий {empty(rows)} → '
                  f'{empty(new)}; комплектов {len({r["event_id"] for r in new})}')
        for x in log:
            if not fixes.status_ok(x['status']):
                self._say(f'  НЕ ПРИМЕНЕНО: {x["status"]} {x["page"]} {x["op"]} «{x["find"]}»')

    def _max_score(self, options):
        version = options['version']
        path = self._version_rows_path(version)
        rows = fixes.read_rows(path)
        log = max_score.fill(rows)
        counts = Counter(x[1] for x in log)
        out = path.parent / f'max_score_{version}.csv'
        with open(out, 'w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle, delimiter=';')
            writer.writerow(['event_id', 'number', 'task_variant', 'итог', 'источники', 'было', 'стало'])
            for key, status, sources, before, after in log:
                if status != 'none':
                    writer.writerow([*key, status, '; '.join(f'{k}={v}' for k, v in sources.items()),
                                     before, after])
        if options.get('write'):
            fixes.write_rows(str(path), rows)
        empty = sum(1 for r in rows if r.get('max_score') in (None, ''))
        self._say(f'max_score {self.olympiad.slug} {version}: {dict(counts)}; пустых после — {empty} '
                  f'из {len(rows)}; отчёт {out}{"; записано" if options.get("write") else " (не записано)"}')

    def _sweep_layers(self, version, given=None):
        """Заплатки страниц для vN: pages_vK с 2 < K ≤ N, старшая первой."""
        if given:
            return tuple(x.strip() for x in given.split(',') if x.strip())
        top = int(str(version).lstrip('v'))
        return tuple(f'pages_v{k}' for k in range(top, 2, -1)
                     if (self.digitized / f'pages_v{k}').is_dir())

    def _run_sweeps(self, version, layers=None, rows_file=None):
        path = Path(rows_file) if rows_file else self._version_rows_path(version)
        layers = self._sweep_layers(version, layers)
        ctx = sweeps.Ctx(self.olympiad.slug, fixes.read_rows(path), str(self.digitized), layers)
        res = []
        for _n, func in sweeps.ALL:
            res += func(ctx)
        return ctx, res, layers

    def _sweeps(self, options):
        version = options['version']
        _ctx, res, layers = self._run_sweeps(version, options.get('layers'), options.get('rows'))
        out = (Path(options['out_file']) if options.get('out_file')
               else self.digitized / version / f'sweeps_{version}.json')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, ensure_ascii=False), encoding='utf-8')
        by = Counter(x['cls'][0] for x in res)
        self._say(f'Автопроверки {self.olympiad.slug} {version} (заплатки: '
                  f'{", ".join(layers) or "нет"}) → {out}')
        self._say('  по классам 1–9: ' + ' / '.join(str(by[k]) for k in '123456789')
                  + f'; всего {len(res)}')

    def _reread_queue(self, options):
        version = options['version']
        findings = {}
        for slug in [self.olympiad.slug] + list(options.get('also') or []):
            digitized = self.root / registry.get(slug).audit_dir / 'digitized'
            saved = self.digitized, self.olympiad
            self.digitized, self.olympiad = digitized, registry.get(slug)
            try:
                saved_json = digitized / version / f'sweeps_{version}.json'
                rows = fixes.read_rows(self._version_rows_path(version))
                ctx = sweeps.Ctx(slug, rows, str(digitized), self._sweep_layers(version))
                if saved_json.is_file():
                    res = json.loads(saved_json.read_text(encoding='utf-8'))
                else:
                    res = []
                    for _n, func in sweeps.ALL:
                        res += func(ctx)
                findings[slug] = (ctx, res)
            finally:
                self.digitized, self.olympiad = saved
        rows = reread_queue.build(reread_queue.read_eye(options['eye']), findings,
                                  cap_usd=options['cap_usd'])
        out = (Path(options['out_file']) if options.get('out_file')
               else self.digitized / version / f'reread_queue_{version}.csv')
        reread_queue.write(str(out), rows)
        by = Counter((r['set'], r['priority']) for r in rows)
        self._say(f'Очередь перечитывания {version} → {out}: строк {len(rows)}; '
                  + '; '.join(f'{s} p{p}: {n}' for (s, p), n in sorted(by.items())))

    # ── audit-claude ────────────────────────────────────────────────────

    def _audit_claude(self, options):
        set_of_slug = {v[0]: k for k, v in claude_eyes.SETS.items()}
        name = set_of_slug.get(self.olympiad.slug)
        if name is None:
            raise CommandError(f'audit-claude не знает олимпиаду {self.olympiad.slug}.')
        dirs = {v[0]: registry.get(v[0]).audit_dir for v in claude_eyes.SETS.values()}
        ds = claude_eyes.load_set(name, str(self.root), dirs)
        all_units, skipped = claude_eyes.build_units(ds)
        units = all_units
        if options.get('units_file'):
            with open(options['units_file'], encoding='utf-8') as handle:
                wanted = {line.strip() for line in handle if line.strip()}
            units = {k: v for k, v in all_units.items() if k in wanted}
        model = claude_eyes.MODEL_ALIASES[options['model']]
        ledger = options.get('ledger') or str(self.root / 'audit_claude_cost.jsonl')
        step = options['step']
        audit_dir = Path(ds.audit_dir)
        if step == 'units':
            claude_eyes.write_jsonl(str(audit_dir / 'units.jsonl'), list(units.values()))
            pages = Counter(len(u['pages']) for u in units.values())
            self._say(f'{name}: единиц {len(units)}, фрагментов '
                      f'{sum(len(u["fragments"]) for u in units.values())}, страниц в единице '
                      f'{dict(sorted(pages.items()))}, пропущено групп {len(skipped)} '
                      f'→ {audit_dir / "units.jsonl"}')
        elif step == 'jobs':
            out = options.get('jobs_dir') or str(audit_dir / 'jobs')
            for unit in units.values():
                claude_eyes.write_job(unit, ds, out)
            self._say(f'{name}: заданий для агентов {len(units)} → {out}')
        elif step == 'submit':
            cap = options.get('max_usd')
            if cap is None:
                raise CommandError('--max-usd обязателен для submit. Ничего не отправлено.')
            todo = [u for u in units.values() if claude_eyes.load_raw(ds, model, u['unit']) is None]
            spent = claude_eyes.spent(ledger)
            self._say(f'{name}: к отправке {len(todo)} единиц на {model}; потрачено '
                      f'${spent:.2f} из ${cap:.2f}.')
            if not options.get('yes'):
                self._say('Без --yes — только план. Ничего не отправлено.')
                return
            if spent >= 0.9 * cap:
                raise CommandError('Потрачено 90 % потолка — новые пакеты не отправляются.')
            sent = claude_eyes.submit_batches(claude_eyes.make_client(), ds, todo, model)
            self._say(f'Отправлено пакетов: {len(sent)}: {", ".join(sent)}')
        elif step == 'collect':
            done, waiting = claude_eyes.collect_batches(claude_eyes.make_client(), ds, ledger)
            self._say(f'{name}: собрано ответов {done}, пакетов в работе {waiting}; '
                      f'потрачено всего ${claude_eyes.spent(ledger):.2f}')
        elif step == 'check':
            if options.get('import_dir'):
                src = Path(options['import_dir']) / model
                got = 0
                for uid in units:
                    path = src / f'{uid}.json'
                    if path.is_file() and claude_eyes.load_raw(ds, model, uid) is None:
                        claude_eyes.save_raw(ds, model, uid, path.read_text(encoding='utf-8'), 'agent')
                        got += 1
                self._say(f'Принято ответов агентов: {got}')
            recs = claude_eyes.check_set(ds, model, all_units)
            acc = sum(len(r['accepted']) for r in recs)
            rej = sum(len(r['rejected']) for r in recs)
            nfix = sum(1 for r in recs for v in r['verdicts'].values() if v.get('verdict') == 'needs_fix')
            self._say(f'{name} · {model}: единиц с ответом {len(recs)}, needs_fix {nfix}, '
                      f'правок принято {acc}, отклонено {rej}')
        elif step == 'build':
            checked = {m: claude_eyes.load_checked(ds, m) for m in claude_eyes.BATCH_PRICES}
            resolved = claude_eyes.resolve(checked)
            audited = len({r['unit'] for recs in checked.values() for r in recs})
            answers, answer_rejected = [], []
            if options.get('answers_dir'):
                replies = [json.loads(p.read_text(encoding='utf-8'))
                           for p in sorted(Path(options['answers_dir']).glob('*.json'))]
                events = {json.loads(line)['event_id']: json.loads(line)
                          for line in open(Path(ds.digitized) / 'events_files.jsonl', encoding='utf-8')}
                key_texts = {}
                for rep in replies:
                    ev = events.get(rep.get('event_id'), {})
                    parts = []
                    for f in ev.get('solution_files', []) + ev.get('task_files', []):
                        for n in range(1, f.get('pages', 0) + 1):
                            txt = Path(ds.digitized) / f['page_dir'] / f'p{n}.txt'
                            if txt.is_file():
                                parts.append(txt.read_text(encoding='utf-8', errors='replace'))
                    key_texts[rep.get('event_id')] = '\n'.join(parts)
                answers, answer_rejected = claude_eyes.answer_entries(ds.rows, replies, key_texts)
                self._say(f'Ответы к тестам: принято {len(answers)}, отклонено {len(answer_rejected)}')
                for ev, num, why in answer_rejected:
                    self._say(f'  отказ {ev} {num}: {why}')
            result = claude_eyes.build_version(ds, resolved, audited, answers=answers)
            claude_eyes.changes_md(ds, result, resolved,
                                   f'{name}: {ds.in_version} → {ds.out_version}, аудит Claude')
            items = claude_eyes.morning_items(ds, resolved, result, all_units)
            review = options.get('review') or str(Path(result['path']).parent /
                                                  f'review_{ds.out_version}.html')
            claude_eyes.review_html(items, review, f'{name} {ds.out_version}: на утро')
            inv = result['invariants']
            self._say(f'{name}: {inv["tasks_in"]} → {inv["tasks_out"]} заданий, правок '
                      f'{len(result["texts"])}, рисунков {len(result["figures"])}, на утро '
                      f'{len(items)}; инварианты {"сошлись" if inv["ok"] else "НЕ СОШЛИСЬ"} '
                      f'→ {result["path"]}')
            if not inv['ok']:
                raise CommandError(f'Инварианты не сошлись: {Path(result["path"]).parent}')
