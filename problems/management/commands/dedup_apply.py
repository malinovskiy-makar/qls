# -*- coding: utf-8 -*-
r"""Разметка групп копий: только пометки, откат одной командой.

⚠️ ЧЕТВЁРТЫЙ МЕХАНИЗМ, И ОН НИЧЕГО НЕ ПРЯЧЕТ. Команда не меняет ни
`status`, ни `duplicate_of`, ни `hidden_pending_review`, ни любое другое
поле `Problem` — она только заводит и удаляет строки `DupMark`. Кода,
который пишет в `Problem`, здесь нет вовсе; это проверяется тестом.

Почему так строго. 08.06.2026 команда `process_duplicates` за шесть секунд
вывела из каталога 7 209 задач, выбирая победителя пары по МЕНЬШЕМУ id и
сразу записывая `status='duplicate'`. Отката у неё нет: папка
`duplicates_backup/` в `.gitignore` и не сохранилась, у второй группы бэкапа
не было изначально, `ProblemVersion` пуста. Эта команда обязана быть
обратимой с первого дня, поэтому:

* результат живёт в ОТДЕЛЬНОЙ таблице `DupMark` (см. её докстринг: поля
  `Problem.dup_*` уже заняты ночной сессией 08.09, писать поверх — значит
  затереть чужую разметку без возможности вернуть);
* `--revert --apply` удаляет ВСЕ строки `DupMark` — ровно то, что команда
  создала, и ничего больше;
* без `--apply` не пишется ни строки.

Запуск::

    venv313\Scripts\python.exe manage.py dedup_apply \
        --pairs reports/dedup_recon_20260911/phaseB/pairs_v1.npz \
        --out reports/dedup_apply_20260911            # проба, база не тронута

    venv313\Scripts\python.exe manage.py dedup_apply ... --apply
    venv313\Scripts\python.exe manage.py dedup_apply --revert --apply

Файл `--pairs` — это `.npz` с полями `id_a`, `id_b`, `sim`, который делает
`scripts/dedup_phase_b_pairs.py --spec v1`. Он лежит в `reports/`, а
`reports/*` в `.gitignore`, поэтому пересобирается скриптом, а не хранится.
Без `--pairs` косинусная нога просто выключается, и команда громко об этом
говорит: остаются только рёбра `content_hash`.
"""
import hashlib
import json
import os
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from problems.dedup import (
    COS_THRESHOLD, JACCARD_THRESHOLD, build_groups, choose_best,
    completeness_score, cosine_edge_passes, hash_edges, is_confident,
)
from problems.models import DupMark, Problem, ProblemPart

#: SQLite роняет `filter(id__in=...)` на десятках тысяч значений
#: («too many SQL variables»), поэтому выборки идут порциями.
CHUNK = 900


def protected_digest():
    """Отпечаток трёх полей, которых команда не имеет права касаться."""
    h = hashlib.sha256()
    n = 0
    for pid, status, dup, hidden in (
            Problem.objects.order_by('id')
            .values_list('id', 'status', 'duplicate_of_id',
                         'hidden_pending_review')
            .iterator(chunk_size=5000)):
        h.update(('%s|%s|%s|%s\n' % (pid, status, dup, int(bool(hidden))))
                 .encode('utf-8'))
        n += 1
    return {'rows': n, 'sha256': h.hexdigest()}


class Command(BaseCommand):
    help = ('Размечает группы копий (только пометки в DupMark). '
            'Без --apply ничего не пишет. Откат: --revert --apply.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='записать пометки в базу')
        parser.add_argument('--revert', action='store_true',
                            help='удалить ВСЕ пометки DupMark')
        parser.add_argument('--pairs', default='',
                            help='.npz с парами по косинусу (id_a, id_b, sim)')
        parser.add_argument('--cos', type=float, default=COS_THRESHOLD)
        parser.add_argument('--jaccard', type=float, default=JACCARD_THRESHOLD)
        parser.add_argument('--out', default='',
                            help='папка для отчёта пробного прогона')
        parser.add_argument('--sample', type=int, default=30,
                            help='сколько групп положить в читаемую выборку')

    # ── откат ──────────────────────────────────────────────────────────
    def _revert(self, opts):
        say = self.stdout.write
        n = DupMark.objects.count()
        if not opts['apply']:
            say('ОТКАТ (проба): удалил бы %d пометок. Повторите с --apply.' % n)
            return
        DupMark.objects.all().delete()
        say('ОТКАТ: удалено %d пометок. Ни одно поле Problem не тронуто.' % n)

    # ── сбор рёбер ─────────────────────────────────────────────────────
    def _hash_edges(self):
        """Рёбра точного совпадения `content_hash` с гейтом по подпунктам."""
        подпункты = defaultdict(list)
        for pid, st, ans in (ProblemPart.objects
                             .order_by('problem_id', 'order', 'label', 'id')
                             .values_list('problem_id', 'statement', 'answer')
                             .iterator(chunk_size=5000)):
            подпункты[pid].append((st, ans))

        строки = (
            (pid, h, подпункты.get(pid, []))
            for pid, h in (Problem.objects.exclude(content_hash='')
                           .order_by('id')
                           .values_list('id', 'content_hash')
                           .iterator(chunk_size=5000))
        )
        return hash_edges(строки)

    def _cosine_edges(self, path, cos, jaccard):
        """Рёбра по косинусу `v1`, пропущенные через оба гейта."""
        import numpy as np

        if not os.path.isfile(path):
            raise CommandError('нет файла пар: %s' % path)
        z = np.load(path)
        ia, ib, sim = z['id_a'], z['id_b'], z['sim']
        keep = sim >= cos
        ia, ib, sim = ia[keep], ib[keep], sim[keep]

        нужны = sorted({int(x) for x in ia} | {int(x) for x in ib})
        тексты = self._full_texts(нужны)

        рёбра = []
        отсев = Counter()
        for a, b, s in zip(ia, ib, sim):
            a, b = int(a), int(b)
            если = cosine_edge_passes(float(s), тексты.get(a, ''),
                                      тексты.get(b, ''), cos, jaccard)
            отсев['прошло' if если else 'отсеяно гейтами'] += 1
            if если:
                рёбра.append((a, b))
        return рёбра, {'пар выше косинуса %.2f' % cos: int(len(sim)),
                       'прошло оба гейта': отсев['прошло'],
                       'отсеяно гейтами': отсев['отсеяно гейтами']}

    def _full_texts(self, ids):
        """Условие вместе с подпунктами — то, что читают оба гейта."""
        тексты = {}
        for i in range(0, len(ids), CHUNK):
            порция = ids[i:i + CHUNK]
            for pid, st in (Problem.objects.filter(id__in=порция)
                            .values_list('id', 'statement')):
                тексты[pid] = st or ''
            хвост = defaultdict(list)
            for pid, st in (ProblemPart.objects.filter(problem_id__in=порция)
                            .order_by('problem_id', 'order', 'label', 'id')
                            .values_list('problem_id', 'statement')):
                хвост[pid].append(st or '')
            for pid, куски in хвост.items():
                тексты[pid] = (тексты.get(pid, '') + ' '
                               + ' '.join(куски)).strip()
        return тексты

    # ── признаки задач ─────────────────────────────────────────────────
    def _members(self, ids):
        """Всё, что нужно правилам выбора фаворита, одной выборкой по порциям."""
        данные = {}
        for i in range(0, len(ids), CHUNK):
            порция = ids[i:i + CHUNK]
            qs = (Problem.objects.filter(id__in=порция)
                  .annotate(n_parts=Count('parts', distinct=True),
                            n_figures=Count('figures', distinct=True),
                            n_tags=Count('tags', distinct=True),
                            n_topics=Count('topics', distinct=True))
                  .values('id', 'human_review', 'solution', 'content_format',
                          'n_parts', 'n_figures', 'n_tags', 'n_topics'))
            for r in qs:
                данные[r['id']] = {
                    'id': r['id'],
                    'approved': r['human_review'] == Problem.HumanReview.APPROVED,
                    'parts': r['n_parts'],
                    'figures': r['n_figures'],
                    'tags': r['n_tags'],
                    'topics': r['n_topics'],
                    'solution': r['solution'] or '',
                    'content_format': r['content_format'],
                }
        return данные

    # ── основной ход ───────────────────────────────────────────────────
    def handle(self, *args, **opts):
        say = self.stdout.write

        if opts['revert']:
            return self._revert(opts)

        до = protected_digest()
        say('Защищённые поля ДО: %d строк, sha256 %s'
            % (до['rows'], до['sha256'][:16]))

        рёбра_хеш = self._hash_edges()
        say('Рёбра content_hash (с гейтом по подпунктам): %d' % len(рёбра_хеш))

        рёбра_кос, сводка_кос = [], {'косинусная нога': 'выключена (нет --pairs)'}
        if opts['pairs']:
            рёбра_кос, сводка_кос = self._cosine_edges(
                opts['pairs'], opts['cos'], opts['jaccard'])
            say('Рёбра косинуса v1 >= %.2f + оба гейта: %d'
                % (opts['cos'], len(рёбра_кос)))
        else:
            say('⚠️ --pairs не задан: косинусная нога ВЫКЛЮЧЕНА, '
                'считаются только рёбра content_hash.')

        рёбра = рёбра_хеш + рёбра_кос
        группы = build_groups(рёбра)
        все_id = sorted({i for члены in группы.values() for i in члены})
        say('Групп (связных компонент): %d, задач в них: %d'
            % (len(группы), len(все_id)))

        признаки = self._members(все_id)
        решения = {}
        for gid, члены in группы.items():
            состав = [признаки[i] for i in члены if i in признаки]
            правило, фаворит = choose_best(состав)
            решения[gid] = (правило, фаворит, члены)

        отчёт = self._summary(группы, решения, признаки, рёбра_хеш, рёбра_кос,
                              сводка_кос, opts)
        for строка in отчёт['печать']:
            say(строка)

        if opts['out']:
            self._write_report(opts, отчёт, решения, признаки)
            say('Отчёт: %s' % opts['out'])

        if not opts['apply']:
            say('')
            say('⚠️ СТОП-ГЕЙТ. Это только счёт, база не тронута.')
            say('   Применить: dedup_apply --apply')
        else:
            self._write_marks(решения)
            say('')
            say('ПРИМЕНЕНО: пометок в DupMark %d.' % DupMark.objects.count())
            say('Откат: dedup_apply --revert --apply')

        после = protected_digest()
        say('Защищённые поля ПОСЛЕ: %d строк, sha256 %s'
            % (после['rows'], после['sha256'][:16]))
        if после != до:
            raise CommandError(
                'ЗАЩИЩЁННЫЕ ПОЛЯ ИЗМЕНИЛИСЬ — этого не должно происходить '
                'никогда, ни в пробе, ни в применении.')
        say('Защищённые поля совпали побайтно (status, duplicate_of, '
            'hidden_pending_review).')

    # ── запись ─────────────────────────────────────────────────────────
    def _write_marks(self, решения):
        строки = []
        for gid, (правило, фаворит, члены) in решения.items():
            for pid in члены:
                строки.append(DupMark(problem_id=pid, group=gid, rule=правило,
                                      is_best=(pid == фаворит)))
        with transaction.atomic():
            DupMark.objects.all().delete()
            DupMark.objects.bulk_create(строки, batch_size=500)

    # ── счёт и отчёт ───────────────────────────────────────────────────
    def _summary(self, группы, решения, признаки, рёбра_хеш, рёбра_кос,
                 сводка_кос, opts):
        размеры = Counter(len(члены) for члены in группы.values())
        правила = Counter(правило for правило, _, _ in решения.values())
        уверенных = sum(1 for правило, _, _ in решения.values()
                        if is_confident(правило))
        с_approved = 0
        много_approved = 0
        картинка = 0
        for правило, _, члены in решения.values():
            n = sum(1 for i in члены
                    if i in признаки and признаки[i]['approved'])
            if n:
                с_approved += 1
            if n > 1:
                много_approved += 1
            if правило == DupMark.Rule.APPROVED_PICTURE_REVIEW:
                картинка += 1

        данные = {
            'порог косинуса': opts['cos'],
            'порог символьной близости': opts['jaccard'],
            'рёбер content_hash': len(рёбра_хеш),
            'рёбер косинуса': len(рёбра_кос),
            'рёбер всего': len(рёбра_хеш) + len(рёбра_кос),
            'косинусная нога': сводка_кос,
            'групп всего': len(группы),
            'задач в группах': sum(len(ч) for ч in группы.values()),
            'размеры групп': dict(sorted(размеры.items())),
            'групп уверенных': уверенных,
            'групп на ручной разбор': len(группы) - уверенных,
            'групп с approved': с_approved,
            'из них ушло на разбор по правилу картинки': картинка,
            'групп с несколькими approved': много_approved,
            'уверенных решено полнотой': правила.get(
                DupMark.Rule.COMPLETENESS_MARGIN, 0),
            'по правилам': {str(k): v for k, v in правила.items()},
        }
        печать = ['', '=== ИТОГ ПРОБНОГО ПРОГОНА ===']
        печать += [json.dumps(данные, ensure_ascii=False, indent=1)]
        return {'данные': данные, 'печать': печать}

    def _write_report(self, opts, отчёт, решения, признаки):
        os.makedirs(opts['out'], exist_ok=True)
        json.dump(отчёт['данные'],
                  open(os.path.join(opts['out'], 'dry_run_summary.json'), 'w',
                       encoding='utf-8'), ensure_ascii=False, indent=1)

        # Полный список групп — чтобы решение по любой конкретной паре можно
        # было проверить поимённо, не перезапуская прогон.
        полный = {gid: {'правило': str(правило), 'фаворит': фаворит,
                        'члены': члены}
                  for gid, (правило, фаворит, члены) in решения.items()}
        json.dump(полный,
                  open(os.path.join(opts['out'], 'dry_run_groups.json'), 'w',
                       encoding='utf-8'), ensure_ascii=False, indent=1)

        # Читаемая выборка: половина уверенных, половина на разбор, с текстами.
        уверенные = [g for g, (r, _, _) in решения.items() if is_confident(r)]
        разбор = [g for g, (r, _, _) in решения.items() if not is_confident(r)]
        половина = max(opts['sample'] // 2, 1)
        выбор = sorted(уверенные)[:половина] + sorted(разбор)[:половина]

        нужны = sorted({i for g in выбор for i in решения[g][2]})
        тексты = {}
        for i in range(0, len(нужны), CHUNK):
            for pid, st, hr, src in (
                    Problem.objects.filter(id__in=нужны[i:i + CHUNK])
                    .values_list('id', 'statement', 'human_review',
                                 'source_references__source__name')):
                тексты.setdefault(pid, (st or '', hr or '', src or ''))

        путь = os.path.join(opts['out'], 'dry_run_sample.md')
        with open(путь, 'w', encoding='utf-8') as fh:
            fh.write('# Выборка групп пробного прогона `dedup_apply`\n\n')
            fh.write('Ничего не записано в базу. Уверенных групп в выборке '
                     '%d, на ручной разбор %d.\n\n'
                     % (min(половина, len(уверенные)),
                        min(половина, len(разбор))))
            for gid in выбор:
                правило, фаворит, члены = решения[gid]
                fh.write('## %s — `%s`%s\n\n'
                         % (gid, правило,
                            '' if is_confident(правило)
                            else '  ⟵ НА РУЧНОЙ РАЗБОР'))
                for pid in члены:
                    st, hr, src = тексты.get(pid, ('', '', ''))
                    п = признаки.get(pid, {})
                    fh.write('**#%s%s** · ревью `%s` · источник «%s» · '
                             'полнота %s (подпунктов %s, решение %s, '
                             'фигур %s, тегов %s, тем %s, формат %s)\n\n'
                             % (pid, ' ★ ФАВОРИТ' if pid == фаворит else '',
                                hr or '—', src,
                                completeness_score(п) if п else '?',
                                п.get('parts'), 'есть' if (
                                    п.get('solution') or '').strip() else 'нет',
                                п.get('figures'), п.get('tags'),
                                п.get('topics'), п.get('content_format')))
                    fh.write('```\n%s\n```\n\n' % (st or '').strip()[:1200])
                fh.write('\n')
