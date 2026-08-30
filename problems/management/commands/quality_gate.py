"""
Качественный шлюз (ОБРАТИМЫЙ): флагует задачи с critical-дефектами рендеринга
(поле Problem.needs_quality_review) — они скрываются из каталога, экспорта
подборок и блока похожих задач. Major-дефекты НЕ считаются.

Предохранитель: если в источнике под флаг попадает > 5% его задач — источник
НЕ флагуется вообще (id кандидатов → gate_skipped_source_<N>.txt, причина —
в отчёт шлюза).

Запуск:
    ./venv/bin/python manage.py quality_gate --apply    # пересчитать и поставить флаги
    ./venv/bin/python manage.py quality_gate --revert   # снять ВСЕ флаги
    ./venv/bin/python manage.py quality_gate --list     # показать зафлагованные

--apply сначала снимает все флаги, затем ставит заново по свежему аудиту —
повторный запуск идемпотентен.

⚠️ `--sources 14,13,3,16` ограничивает прогон источниками. Это НЕ удобство,
а предохранитель. Без ограничения `--apply` СНАЧАЛА СНИМАЕТ флаг со ВСЕХ
задач банка и только потом ставит заново по свежему аудиту. Если прогон
задуман точечным («разобрались с четырьмя источниками, применяем»), то без
`--sources` он молча раскроет брак во всех остальных: снял со всех, поставил
только тем, кого посчитал. С `--sources` и снятие, и установка, и
`solution_needs_review` идут ТОЛЬКО внутри области; чужие флаги не двигаются
ни в какую сторону. То же ограничение действует и на `--revert`.
"""

import os
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from problems.models import Problem, Source, SourceReference
from problems.management.commands.audit_render_quality import audit_problem

REPORT_DIR = 'reports/quality_audit'
VALVE_SHARE = 0.05      # предохранитель: >5% задач источника → не флаговать

# Сессия H: источники, для которых 5%-предохранитель ОТКЛЮЧЁН — кандидаты
# флагуются все (и critical-аудит, и огрызки). Состав: #17 Фридман — прямое
# решение преподавателя («весь источник плохо отображается»); остальные —
# >=10% задач источника с critical-дефектами (аудит ∪ детекторы detect_junk2),
# расчёт: reports/sessionH/05_gate_plan.md.
BREAKER_OFF_SOURCES = {5, 6, 16, 17, 19, 24}


class Command(BaseCommand):
    help = 'Качественный шлюз: флаг needs_quality_review по critical-дефектам'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--revert', action='store_true')
        parser.add_argument('--list', action='store_true', dest='list_flagged')
        parser.add_argument(
            '--sources', default='',
            help='ограничить прогон источниками (id через запятую). '
                 'Задачи ДРУГИХ источников не проверяются и их флаги не '
                 'меняются — ни снятием, ни установкой.')

    @staticmethod
    def _scope(raw):
        """`--sources 14,13` → множество id задач этих источников.

        Возвращает `None`, если ограничения нет: это отличается от пустого
        множества, у которого смысл «ни одной задачи»."""
        raw = (raw or '').strip()
        if not raw:
            return None
        try:
            source_ids = [int(part) for part in raw.split(',') if part.strip()]
        except ValueError:
            raise CommandError('--sources: ожидаются id через запятую, '
                               'получено %r' % raw)
        if not source_ids:
            raise CommandError('--sources: пустой список')
        known = set(Source.objects.filter(id__in=source_ids)
                    .values_list('id', flat=True))
        missing = sorted(set(source_ids) - known)
        if missing:
            raise CommandError('--sources: нет таких источников: %s'
                               % ', '.join(map(str, missing)))
        return set(
            SourceReference.objects.filter(source_id__in=source_ids)
            .values_list('problem_id', flat=True))

    @staticmethod
    def _scoped(queryset, scope_ids):
        """Сузить выборку до области, если она задана."""
        return queryset if scope_ids is None else queryset.filter(id__in=scope_ids)

    @staticmethod
    def _false_positives():
        r"""Задачи, которые детектор считает браком, а человек — нет.

        Формат файла тот же, что у остальных списков: `id<TAB>причина`,
        строки с `#` пропускаются.

        Зачем отдельный список, а не правка детектора. Живой случай —
        `unpaired_dollar` на суммах в долларах: «Правительство заплатило
        $2 в виде трансфертов» (#26724), «привязка к доллару: $35 могли
        быть обменены на унцию» (#29691). Непарный `$` здесь ДЕНЬГИ, а не
        обрывок формулы, и на экране всё в порядке — закрывающего `$` нет,
        поэтому KaTeX не превращает фразу в математику.

        Сузить сам детектор («`$` перед цифрой — валюта») было бы
        соблазнительно, но замер по ВСЕМУ банку говорит не делать этого
        мимоходом: нечётный `$` у 163 задач, под правило «валюта» попали
        бы 46, и **41 из них — в источниках вне текущей работы**. Менять
        приговор сорока одной чужой карточке заодно нельзя; это отдельное
        решение с отдельным просмотром. Поимённый список — честная
        середина: он чинит ровно то, что человек посмотрел, и оставляет
        детектор в покое.
        """
        path = os.path.join(REPORT_DIR, 'gate_false_positive_ids.txt')
        if not os.path.exists(path):
            return set()
        ids = set()
        with open(path, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith('#'):
                    ids.add(int(line.split('\t')[0]))
        return ids

    def handle(self, *args, **options):
        scope_ids = self._scope(options['sources'])
        if scope_ids is not None:
            self.stdout.write(
                'Область ограничена: %d задач из источников %s.'
                % (len(scope_ids), options['sources']))

        if options['revert']:
            n = self._scoped(Problem.objects.filter(needs_quality_review=True),
                             scope_ids).update(needs_quality_review=False)
            n2 = self._scoped(Problem.objects.filter(solution_needs_review=True),
                              scope_ids).update(solution_needs_review=False)
            self.stdout.write(self.style.SUCCESS(
                f'Флаги сняты: {n} задач (+ solution_needs_review: {n2}).'))
            return

        if options['list_flagged']:
            qs = Problem.objects.filter(needs_quality_review=True) \
                                .prefetch_related('source_references__source')
            for p in qs.order_by('id'):
                refs = list(p.source_references.all())
                src = refs[0].source.name[:40] if refs else '(без источника)'
                self.stdout.write(f'#{p.id}\t[{p.status}]\t{src}')
            self.stdout.write(f'Всего зафлаговано: {qs.count()}')
            return

        if not options['apply']:
            self.stdout.write('Укажите --apply, --revert или --list.')
            return

        os.makedirs(REPORT_DIR, exist_ok=True)
        src_names = {s.id: s.name for s in Source.objects.all()}
        src_names[0] = '(без источника)'

        # ── свежий аудит: только critical. Политика сессии D:
        #    скрывает задачу ТОЛЬКО critical в УСЛОВИИ (statement задачи или
        #    подпунктов); critical в solution → solution_needs_review
        #    (кнопка «Показать решение» скрыта); critical в answer — не повод ──
        src_total = defaultdict(int)            # sid -> всего задач
        candidates = defaultdict(list)          # sid -> [(id, types, fragment)]
        solution_review_ids = []
        qs = self._scoped(Problem.objects.all(), scope_ids).order_by('id') \
                 .prefetch_related('parts', 'source_references')
        done = 0
        for problem in qs.iterator(chunk_size=300):
            done += 1
            refs = list(problem.source_references.all())
            sid = refs[0].source_id if refs else 0
            src_total[sid] += 1
            defects = audit_problem(problem, problem.parts.all())
            stmt_crit = [(typ, field, snip)
                         for sev, typ, field, snip in defects
                         if sev == 'critical'
                         and (field == 'statement'
                              or field.endswith('.statement'))]
            sol_crit = any(sev == 'critical' and field == 'solution'
                           for sev, typ, field, snip in defects)
            if stmt_crit:
                types = ','.join(sorted({t for t, _, _ in stmt_crit}))
                candidates[sid].append((problem.id, types, stmt_crit[0][2][:100]))
            if sol_crit:
                solution_review_ids.append(problem.id)
            if done % 5000 == 0:
                self.stdout.write(f'  ...{done} задач проверено')

        # ── предохранитель по источникам ──
        flag_ids = []
        hidden_lines = []
        report_lines = ['# Отчёт качественного шлюза', '']
        for sid in sorted(set(src_total) | set(candidates)):
            cand = candidates.get(sid, [])
            if not cand:
                continue
            share = len(cand) / src_total[sid]
            name = src_names.get(sid, f'#{sid}')
            if share > VALVE_SHARE and sid not in BREAKER_OFF_SOURCES:
                path = os.path.join(REPORT_DIR, f'gate_skipped_source_{sid}.txt')
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(f'# Источник #{sid} {name}: {len(cand)} из '
                            f'{src_total[sid]} задач ({share:.1%}) — выше '
                            f'предохранителя {VALVE_SHARE:.0%}, флаг НЕ ставился.\n')
                    for pid, types, frag in cand:
                        f.write(f'{pid}\t{types}\t{frag}\n')
                report_lines.append(
                    f'- **#{sid} {name}: ПРОПУЩЕН предохранителем** — '
                    f'{len(cand)}/{src_total[sid]} ({share:.1%}) > 5%; '
                    f'кандидаты в `gate_skipped_source_{sid}.txt`')
                self.stdout.write(self.style.WARNING(
                    f'#{sid} {name[:40]}: {len(cand)}/{src_total[sid]} '
                    f'({share:.1%}) > 5% — источник пропущен'))
            else:
                for pid, types, frag in cand:
                    flag_ids.append(pid)
                    hidden_lines.append(
                        f'{pid}\t#{sid} {name[:40]}\t{types}\t{frag}')
                report_lines.append(
                    f'- #{sid} {name}: зафлаговано {len(cand)}/{src_total[sid]} '
                    f'({share:.1%})')
                self.stdout.write(
                    f'#{sid} {name[:40]}: зафлаговано {len(cand)} '
                    f'({share:.1%})')

        # ── детекторные флаги (аддитивные источники, читаются из файлов):
        #    скрытие задачи: junk_ids (мусор буклетов — всю задачу, как прежде),
        #    broken_formula_ids (рассыпанные формулы В УСЛОВИИ), ap_glued_ids,
        #    flattened_table_ids (решение преподавателя, сессия D),
        #    tabular_data_tables_ids (KaTeX-нерендеримые таблицы данных, сессия E);
        #    только кнопка решения: broken_formula_solution_ids ──
        detector_ids = []
        for fname in ('junk_ids.txt', 'broken_formula_ids.txt',
                      'ap_glued_ids.txt',
                      # сессия H3 этап 6: ЕДИНЫЙ консолидированный список таблиц
                      # (свежий скан ∪ flattened_table_ids ∪
                      #  tabular_data_tables_ids ∪ data_tables_gate_ids).
                      # Регенерация: manage.py detect_flattened_tables.
                      '06_flattened_tables_ids.txt',
                      'gate_no_figure_ids.txt',
                      'gate_manual_ids.txt',
                      'ile_forum_ids.txt',
                      # сессия H (этапы 4–5):
                      'bad_glyph_ids.txt',
                      'midword_ids.txt',
                      'not_a_problem_ids.txt',
                      # сессия H3 этап 7: разорванные формулы в условии (видимые)
                      '02_broken_formula_gate_ids.txt',
                      # сессия H4 этап 4: ссылки на отсутствующий рисунок (G9) и
                      # вопросы без условия (G14) — оба уже через 5%-предохранитель
                      # внутри detect_missing_refs.
                      'missing_figure_ids.txt',
                      'no_premise_ids.txt',
                      # сессия 2026-08-30: 19 кодов читаемости из аудита
                      # 3 000 карточек — потерянные рисунки, неполные
                      # карточки, сырой служебный синтаксис, утечка
                      # решения в условие. Список пишет
                      # `manage.py corpus_render_codes` (только P0 и P1:
                      # P2 — косметика, и TABLE/OVER-M из неё уже сняты
                      # правкой шаблона). Регенерация — той же командой.
                      'render_codes_ids.txt'):
            path = os.path.join(REPORT_DIR, fname)
            if not os.path.exists(path):
                continue
            for ln in open(path, encoding='utf-8'):
                ln = ln.strip()
                if not ln or ln.startswith('#'):
                    continue
                detector_ids.append(int(ln.split('\t')[0]))
        if detector_ids:
            report_lines.append(
                f'- детекторные флаги (junk/broken/glued/таблицы из файлов): '
                f'{len(detector_ids)}')

        # ── задачи-огрызки (stub_ids.txt, сессия E) — через предохранитель
        #    5% по источникам, отдельно от critical-кандидатов ──
        stub_path = os.path.join(REPORT_DIR, 'stub_ids.txt')
        if os.path.exists(stub_path):
            stub_ids = [int(ln.split('\t')[0])
                        for ln in open(stub_path, encoding='utf-8')
                        if ln.strip() and not ln.startswith('#')]
            stub_by_src = defaultdict(list)
            id2src = dict(
                Problem.objects.filter(id__in=stub_ids)
                .values_list('id', 'source_references__source_id'))
            for pid in stub_ids:
                stub_by_src[id2src.get(pid) or 0].append(pid)
            for sid, pids in sorted(stub_by_src.items()):
                share = len(pids) / max(src_total.get(sid, len(pids)), 1)
                name = src_names.get(sid, f'#{sid}')
                if share > VALVE_SHARE and sid not in BREAKER_OFF_SOURCES:
                    path = os.path.join(
                        REPORT_DIR, f'gate_skipped_stubs_source_{sid}.txt')
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(f'# Огрызки источника #{sid} {name}: '
                                f'{len(pids)} из {src_total.get(sid, 0)} задач '
                                f'({share:.1%}) > {VALVE_SHARE:.0%} — '
                                f'флаг НЕ ставился.\n')
                        f.write('\n'.join(map(str, pids)) + '\n')
                    report_lines.append(
                        f'- **огрызки #{sid} {name}: ПРОПУЩЕНЫ '
                        f'предохранителем** — {len(pids)}/{src_total.get(sid, 0)} '
                        f'({share:.1%}); кандидаты в '
                        f'`gate_skipped_stubs_source_{sid}.txt`')
                else:
                    detector_ids.extend(pids)
                    report_lines.append(
                        f'- огрызки #{sid} {name}: зафлаговано {len(pids)} '
                        f'({share:.1%})')

        path = os.path.join(REPORT_DIR, 'broken_formula_solution_ids.txt')
        if os.path.exists(path):
            for ln in open(path, encoding='utf-8'):
                ln = ln.strip()
                if ln and not ln.startswith('#'):
                    solution_review_ids.append(int(ln.split('\t')[0]))

        # ── подтверждённые человеком ложные срабатывания ──
        false_positives = self._false_positives()
        if false_positives:
            before = len(set(flag_ids) | set(detector_ids))
            flag_ids = [i for i in flag_ids if i not in false_positives]
            detector_ids = [i for i in detector_ids if i not in false_positives]
            solution_review_ids = [i for i in solution_review_ids
                                   if i not in false_positives]
            after = len(set(flag_ids) | set(detector_ids))
            report_lines.append(
                '- снято по списку ложных срабатываний: %d' % (before - after))
            self.stdout.write(
                'ложные срабатывания (проверены человеком): не флагуем %d'
                % (before - after))

        # ── применяем: сброс + установка ──
        # ⚠️ При `--sources` И СБРОС, И УСТАНОВКА идут только внутри области.
        # Сброс опаснее установки: без ограничения он снял бы флаг со ВСЕХ
        # задач банка, а поставил бы обратно только по свежему аудиту —
        # то есть «точечный» прогон молча раскрыл бы чужой брак.
        self._scoped(Problem.objects.filter(needs_quality_review=True),
                     scope_ids).update(needs_quality_review=False)
        self._scoped(Problem.objects.filter(id__in=flag_ids + detector_ids),
                     scope_ids).update(needs_quality_review=True)
        self._scoped(Problem.objects.filter(solution_needs_review=True),
                     scope_ids).update(solution_needs_review=False)
        # кнопку решения прячем только там, где решение вообще есть
        n_solrev = self._scoped(
            Problem.objects.filter(id__in=solution_review_ids), scope_ids
        ).exclude(solution='').update(solution_needs_review=True)
        report_lines.append(f'- solution_needs_review (кнопка решения скрыта): '
                            f'{n_solrev}')

        with open(os.path.join(REPORT_DIR, 'gate_hidden_ids.txt'), 'w',
                  encoding='utf-8') as f:
            f.write('# id\tисточник\tтип дефекта\tфрагмент\n')
            f.write('\n'.join(hidden_lines) + '\n')

        report_lines += ['', f'**Итого зафлаговано: {len(flag_ids)} задач '
                             f'из {done}.**']
        with open(os.path.join(REPORT_DIR, 'gate_report.md'), 'w',
                  encoding='utf-8') as f:
            f.write('\n'.join(report_lines) + '\n')

        self.stdout.write(self.style.SUCCESS(
            f'\nЗафлаговано {len(flag_ids)} задач. Списки: '
            f'{REPORT_DIR}/gate_hidden_ids.txt, gate_report.md. '
            f'Снять шлюз: quality_gate --revert.'))
