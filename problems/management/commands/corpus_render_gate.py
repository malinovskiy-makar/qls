# -*- coding: utf-8 -*-
"""Прогон нового шлюза `render_preflight_v2` — Фазы 7-8 сессии 2026-08-27.

READ-ONLY от начала до конца: ни один `Problem`/`ProblemPart` не
изменяется, `content_format` не пишется. Инвариант `count()` проверяется
кодом и роняет команду `CommandError` при расхождении.

Два режима:

* `--fixtures` — прогон по ИМЕНОВАННЫМ карточкам аудита («Набор
  обязательных регрессионных тестов» + карточки, воспроизведённые в
  Фазе −1). Печатает вердикт по каждой: коды дефектов и что именно
  изменилось против старого шлюза.
* без флага — честный пересчёт по ВСЕМ кандидатам четырёх легаси-
  источников. Даёт PASS/FAIL по новому шлюзу и явную разницу: сколько
  из старых PASS стали FAIL.

⚠️ `DJANGO_ALLOW_ASYNC_UNSAFE` выставляется здесь осознанно:
синхронный playwright поднимает event loop, после чего Django
запрещает ORM. Доступ к базе тут только на чтение и в один поток —
ровно случай, для которого этот флаг и существует.
"""
import json
import os
import time

os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', '1')

from django.conf import settings  # noqa: E402
from django.core.management.base import BaseCommand, CommandError  # noqa: E402

from problems.corpus_converter.core import may_render_as_markdown  # noqa: E402
from problems.corpus_converter.katex_preflight import KatexPreflight  # noqa: E402
from problems.corpus_converter.preflight_gate import (  # noqa: E402
    build_blocks, convert_problem_v2, render_preflight_v2,
)
from problems.corpus_converter.reshalki_dollar_exclusions import (  # noqa: E402
    FORCED_EXCLUDE_RESHALKI_DOLLAR_SPLIT,
)
from problems.models import Problem, ProblemPart  # noqa: E402

SOURCES = {
    'archive3': (14, 'Overleaf Archive 3 (ОШ/ЛШ Олмат)'),
    'matek': (13, 'МатЭк — Overleaf архивы (2021–2025)'),
    'lsh2025': (3, 'ЛШ Олмат 2025 (Overleaf)'),
    'reshalki': (16, 'Решалки Олмат (olmat41)'),
}

#: Фаза 9: источники, УЖЕ лежащие в базе, но не входившие в боевой рендер
#: четырёх легаси. id и названия взяты запросом к `Source`, не угаданы:
#:   id=2  n=3978  'ILE / iloveeconomics.ru'
#:   id=6  n=2024  'Сборник тестов АА'
#: Акимова (id=24, 289 задач) сюда НЕ входит по решению владельца от
#: 27.08: там отдельный трек OCR-пересъёмки, гонять текстовый рендер-шлюз
#: по ней бессмысленно, пока материал не пересняли.
EXTRA_SOURCES = {
    'ile': (2, 'ILE / iloveeconomics.ru'),
    'aa': (6, 'Сборник тестов АА'),
}
ALL_SOURCES = {**SOURCES, **EXTRA_SOURCES}
EXCLUDED_SOURCE_NAME = 'Служебное: фикстуры рендерера (не публиковать)'
OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'corpus_converter_scaleup')

#: Именованные карточки аудита: «Набор обязательных регрессионных тестов»
#: плюс воспроизведённые в Фазе −1. Значение — что заявил аудит.
FIXTURES = {
    30058: 'P1 QUOTE/R-ENV — сырой \\begin{quote}',
    30081: 'P1 K-TEXT — «если» в math mode',
    30113: 'P0 ENV-BAL/K-TEXT/SOL-LEAK — equation* без \\end, вложенные $',
    30119: 'P0 DOLLAR/K-ERR/SOL-LEAK',
    30136: 'P0 PSEUDO/PLOT — псевдокусочная функция и сырой PGFPlots',
    30164: 'P0 PLOT — \\addplot вместо графика',
    30172: 'P0 K-ERR/PLOT — вложенные $ внутри \\[..\\]',
    30921: 'P1 TABLE/R-ENV — сырая LaTeX-таблица с \\diagbox',
    26828: 'P0 DOLLAR — валюта 3000$ принята за delimiter',
    35228: 'P0 DOLLAR/MATH-SPILL — $200 захватывает абзац',
    41581: 'P0 MATH-SPILL — незакрытый $$ на тысячи символов',
    41924: 'P0 EMPTY — потеря содержимого подпункта «г) 3.»',
    3989: 'P2 EMPTY — четыре пустых подпункта в исходнике',
    41001: 'MACRO — пользовательские макросы',
    41118: 'MACRO/K-ERR — \\Tilde (опечатка)',
    42463: 'MACRO/K-ERR — \\soso (неизвестный макрос)',
    30528: 'P0 K-ERR — вложенные $',
    30530: 'P2 EMPTY — условие целиком из TeX-комментария',
    4053: 'P2 EMPTY — пустое условие при полных подпунктах',
    41612: 'контроль: чинится стадией 1, ломаться не должен',
    26337: 'контроль: чинится стадией 1, ломаться не должен',
    30145: 'P1 SOL-LEAK — [4] Решение: в условии',
}


def _candidate_qs(slug, source_id):
    """Те же кандидаты, что у `render_legacy_sources`: не подтверждено
    человеком; для Решалок — ещё не дубль и не из списка разрыва `$$`."""
    qs = (
        Problem.objects.filter(source_references__source_id=source_id)
        .exclude(source_references__source__name=EXCLUDED_SOURCE_NAME)
        .distinct()
        .exclude(human_review=Problem.HumanReview.APPROVED)
    )
    if slug == 'reshalki':
        qs = (qs.exclude(status='duplicate')
                .exclude(id__in=FORCED_EXCLUDE_RESHALKI_DOLLAR_SPLIT))
    return qs


def _evaluate(problem, checker):
    """`(вердикт_нового_шлюза, прошёл_ли_старый)` для одной задачи."""
    raw_parts = [(p.label, p.statement) for p in problem.parts.all()]
    result = convert_problem_v2(
        statement=problem.statement, answer=problem.answer,
        solution=problem.solution, existing_parts=raw_parts,
    )
    old_pass = may_render_as_markdown(result) and not result['warnings']
    blocks = build_blocks(problem.statement, raw_parts, problem.answer,
                          problem.solution, result)
    verdict = render_preflight_v2(blocks, checker, raw_statement=problem.statement)
    return verdict, old_pass


class Command(BaseCommand):
    help = ('Read-only: прогон нового шлюза render_preflight_v2 по фикстурам '
            'аудита (--fixtures) или по всему корпусу кандидатов.')

    def add_arguments(self, parser):
        parser.add_argument('--fixtures', action='store_true',
                            help='прогон по именованным карточкам аудита')
        parser.add_argument('--source', choices=list(ALL_SOURCES),
                            help='ограничить одним источником')
        parser.add_argument('--extra', action='store_true',
                            help='Фаза 9: источники ILE и Сборник АА')
        parser.add_argument('--limit', type=int,
                            help='взять не больше N задач источника (отладка)')

    def handle(self, *args, **options):
        problems_before = Problem.objects.count()
        parts_before = ProblemPart.objects.count()
        started = time.time()

        with KatexPreflight() as checker:
            if options['fixtures']:
                self._run_fixtures(checker)
            else:
                self._run_corpus(checker, options)

        if (Problem.objects.count(), ProblemPart.objects.count()) != (
                problems_before, parts_before):
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: было Problem={problems_before}/'
                f'ProblemPart={parts_before}, стало '
                f'{Problem.objects.count()}/{ProblemPart.objects.count()}')
        self.stdout.write(self.style.SUCCESS(
            f'Инвариант count() сошёлся (Problem={problems_before}). '
            f'Время: {time.time() - started:.0f} с. В базу не записано ничего.'))

    # ------------------------------------------------------------------
    def _run_fixtures(self, checker):
        self.stdout.write('Именованные карточки аудита через НОВЫЙ шлюз:\n')
        passed = blocked = missing = 0
        for pid, claim in FIXTURES.items():
            try:
                problem = Problem.objects.prefetch_related('parts').get(id=pid)
            except Problem.DoesNotExist:
                self.stdout.write(f'  #{pid}: НЕТ В БАЗЕ')
                missing += 1
                continue
            verdict, old_pass = _evaluate(problem, checker)
            if verdict.ok:
                passed += 1
                mark = 'PASS'
            else:
                blocked += 1
                mark = 'БЛОК'
            old = 'PASS' if old_pass else 'FAIL'
            self.stdout.write(
                f'  #{pid:<6} старый={old:<4} новый={mark:<4} '
                f'коды={verdict.codes or "—"}')
            self.stdout.write(f'          аудит: {claim}')
            for detail in verdict.details[:2]:
                self.stdout.write(f'          · {detail[:150]}')
        self.stdout.write(
            f'\nИтог по фикстурам: пропущено новым шлюзом {passed}, '
            f'заблокировано {blocked}, нет в базе {missing}.')

    # ------------------------------------------------------------------
    def _run_corpus(self, checker, options):
        if options['source']:
            slugs = [options['source']]
        elif options.get('extra'):
            slugs = list(EXTRA_SOURCES)
        else:
            slugs = list(SOURCES)
        summary = {}
        code_totals = {}
        fail_ids = {}
        for slug in slugs:
            source_id, name = ALL_SOURCES[slug]
            qs = _candidate_qs(slug, source_id).prefetch_related('parts')
            if options['limit']:
                qs = qs[:options['limit']]
            new_pass = new_fail = old_pass_now_fail = 0
            ids = []
            t0 = time.time()
            for i, problem in enumerate(qs.iterator(chunk_size=200), start=1):
                verdict, old_pass = _evaluate(problem, checker)
                if verdict.ok:
                    new_pass += 1
                else:
                    new_fail += 1
                    ids.append(problem.id)
                    if old_pass:
                        old_pass_now_fail += 1
                    for code in verdict.codes:
                        code_totals[code] = code_totals.get(code, 0) + 1
                if i % 500 == 0:
                    self.stdout.write(
                        f'    {name}: {i} обработано, '
                        f'{time.time() - t0:.0f} с…')
            summary[slug] = {
                'name': name, 'total': new_pass + new_fail,
                'pass': new_pass, 'fail': new_fail,
                'old_pass_now_fail': old_pass_now_fail,
            }
            fail_ids[slug] = ids
            self.stdout.write(
                f'  {name}: кандидатов {new_pass + new_fail}, '
                f'PASS {new_pass}, FAIL {new_fail} '
                f'(из них были PASS по старому шлюзу: {old_pass_now_fail})')

        os.makedirs(OUT_DIR, exist_ok=True)
        out_name = ('gate_v2_extra.json' if options.get('extra')
                    else f'gate_v2_{options["source"]}.json' if options['source']
                    else 'gate_v2_corpus.json')
        out_path = os.path.join(OUT_DIR, out_name)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({'summary': summary, 'codes': code_totals,
                       'fail_ids': fail_ids}, f, ensure_ascii=False, indent=1)

        total = sum(s['total'] for s in summary.values())
        total_pass = sum(s['pass'] for s in summary.values())
        total_fail = sum(s['fail'] for s in summary.values())
        total_regressed = sum(s['old_pass_now_fail'] for s in summary.values())
        self.stdout.write(
            f'\nИТОГО кандидатов {total}: PASS {total_pass}, FAIL {total_fail}.\n'
            f'Из них были PASS по СТАРОМУ шлюзу, а теперь FAIL: {total_regressed} '
            f'— это и есть цена честности.\n'
            f'Коды дефектов (задач с кодом): '
            + ', '.join(f'{c}={n}' for c, n in sorted(
                code_totals.items(), key=lambda kv: -kv[1]))
            + f'\nФайл: {out_path}')
