"""
Команда auto_assign_topics — авторазметка канонических тем через kNN
по эмбеддингам (ночная сессия 2026-06-12).

Принцип: для задачи БЕЗ ЕДИНОЙ темы ищем топ-10 ближайших (косинусное
сходство эмбеддингов) среди задач С канонической темой. Тема назначается,
только если ≥6 из 10 соседей несут одну и ту же каноническую тему И средняя
близость этих соседей-голосующих не ниже порога. Иначе задача остаётся
без темы.

Назначенная тема пишется в обычный M2M Problem.topics; факт автоназначения
фиксируется в журнале AutoTopicAssignment (см. models.py) — всё, чего нет
в журнале, считается ручным назначением.

Запуск:
    ./venv/bin/python manage.py auto_assign_topics --calibrate 500
    ./venv/bin/python manage.py auto_assign_topics --dry-run --threshold 0.75
    ./venv/bin/python manage.py auto_assign_topics --apply --threshold 0.75
    ./venv/bin/python manage.py auto_assign_topics --revert
"""

import os
import random
import time
from collections import Counter, defaultdict

import numpy as np
from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import AutoTopicAssignment, Problem, Topic
from problems.management.commands.apply_topic_mapping import CANONICAL

K = 10                 # сколько соседей смотрим
# Минимум голосов за одну тему. Калибровка (полный leave-one-out, 11 158 задач,
# см. reports/night_session/02_topics_calibration.md) показала: при заявленном
# «>=6 из 10» точность 90% достижима только при покрытии ~10%; правило
# «>=8 из 10» при пороге 0.70 даёт точность 91,5% и покрытие 31,5%.
# Оно СТРОЖЕ заявленного (любое назначение с 8 голосами имеет и 6), выбрано оно.
VOTES_MIN = 8
CHUNK = 1000           # чанк матричного умножения
LOG_EVERY = 1000
DEFAULT_LOG = 'reports/night_session/topics_progress.log'


def load_reference():
    """Опорный набор: задачи с >=1 РУЧНОЙ канонической темой и эмбеддингом.

    Автоназначенные темы (журнал AutoTopicAssignment) в опору НЕ входят:
    иначе повторный apply голосовал бы по автотемам первого прогона — каскад
    «второго поколения» с деградацией точности и потерей идемпотентности.

    Возвращает (ids, normed_matrix, topic_sets) — выровненные списки.
    """
    canon_ids = dict(Topic.objects.filter(name__in=CANONICAL)
                     .values_list('id', 'name'))
    auto_pairs = set(AutoTopicAssignment.objects
                     .values_list('problem_id', 'topic_id'))
    # задача -> множество id канонических тем (только ручные назначения)
    pairs = (Problem.topics.through.objects
             .filter(topic_id__in=canon_ids)
             .values_list('problem_id', 'topic_id'))
    topics_by_problem = defaultdict(set)
    for pid, tid in pairs:
        if (pid, tid) in auto_pairs:
            continue
        topics_by_problem[pid].add(tid)

    qs = (Problem.objects
          .filter(id__in=topics_by_problem.keys(), embedding__isnull=False)
          .values_list('id', 'embedding'))

    ids, vecs, topic_sets = [], [], []
    dim = None
    for pid, raw in qs.iterator(chunk_size=2000):
        v = np.frombuffer(bytes(raw), dtype=np.float32)
        if dim is None:
            dim = v.shape[0]
        if v.shape[0] != dim:
            continue
        n = np.linalg.norm(v)
        ids.append(pid)
        vecs.append(v / (n if n else 1e-9))
        topic_sets.append(topics_by_problem[pid])

    return ids, np.stack(vecs), topic_sets, canon_ids


def predict(sims_row, topic_sets, self_idx=None):
    """По строке сходств возвращает (topic_id, votes, mean_sim, neighbor_idx)
    или None, если правило не решилось (без учёта порога — порог проверяет
    вызывающий код)."""
    row = sims_row
    if self_idx is not None:
        row = row.copy()
        row[self_idx] = -1.0
    top = np.argpartition(row, -K)[-K:]
    top = top[np.argsort(row[top])[::-1]]

    votes = Counter()
    for i in top:
        for tid in topic_sets[i]:
            votes[tid] += 1
    if not votes:
        return None

    # лучшая тема: больше голосов, при равенстве — выше средняя близость
    best = None
    for tid, cnt in votes.items():
        voter_sims = [row[i] for i in top if tid in topic_sets[i]]
        mean_sim = float(np.mean(voter_sims))
        cand = (cnt, mean_sim, tid)
        if best is None or cand > best:
            best = cand
    cnt, mean_sim, tid = best
    if cnt < VOTES_MIN:
        return None
    return tid, cnt, mean_sim, list(top)


class Command(BaseCommand):
    help = 'Авторазметка канонических тем через kNN по эмбеддингам'

    def add_arguments(self, parser):
        parser.add_argument('--calibrate', type=int, nargs='?', const=500,
                            default=None, metavar='N',
                            help='Калибровка на N случайных задачах с известной темой.')
        parser.add_argument('--grid', action='store_true',
                            help='Полная leave-one-out калибровка по ВСЕМ опорным '
                                 'задачам, сетка голоса × порог.')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--revert', action='store_true',
                            help='Снять ВСЕ автоназначения.')
        parser.add_argument('--threshold', type=float, default=0.70,
                            help='Порог средней близости соседей-голосующих '
                                 '(0.70 — по LOO-калибровке).')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--seed', type=int, default=42)
        parser.add_argument('--log-file', default=DEFAULT_LOG)

    def log(self, log_file, msg):
        line = f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {msg}'
        self.stdout.write(line)
        with open(log_file, 'a') as fh:
            fh.write(line + '\n')

    def handle(self, *args, **options):
        os.makedirs(os.path.dirname(options['log_file']) or '.', exist_ok=True)
        if options['revert']:
            return self.do_revert()
        if options['grid']:
            return self.do_calibrate_grid(options)
        if options['calibrate']:
            return self.do_calibrate(options)
        if not (options['dry_run'] or options['apply']):
            self.stdout.write('Укажите --calibrate, --dry-run, --apply или --revert.')
            return
        return self.do_assign(options)

    # ── Revert ──────────────────────────────────────────────────────────────
    def do_revert(self):
        assignments = list(AutoTopicAssignment.objects.values_list(
            'problem_id', 'topic_id'))
        self.stdout.write(f'Автоназначений к снятию: {len(assignments)}')
        through = Problem.topics.through
        removed = 0
        with transaction.atomic():
            for pid, tid in assignments:
                removed += through.objects.filter(
                    problem_id=pid, topic_id=tid).delete()[0]
            AutoTopicAssignment.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(
            f'Снято {removed} связей задача↔тема; журнал очищен '
            f'(осталось записей: {AutoTopicAssignment.objects.count()}).'))

    # ── Калибровка ──────────────────────────────────────────────────────────
    def do_calibrate(self, options):
        n = options['calibrate']
        random.seed(options['seed'])
        self.stdout.write('Загружаем опорный набор...')
        ids, matrix, topic_sets, canon_ids = load_reference()
        self.stdout.write(f'Опорных задач (с канонической темой и эмбеддингом): {len(ids)}')

        sample_idx = random.sample(range(len(ids)), min(n, len(ids)))
        results = []  # (correct, votes, mean_sim, decided)
        t0 = time.time()
        for j, idx in enumerate(sample_idx):
            sims = matrix @ matrix[idx]
            pred = predict(sims, topic_sets, self_idx=idx)
            if pred is None:
                results.append((False, 0, 0.0, False))
            else:
                tid, cnt, mean_sim, _ = pred
                results.append((tid in topic_sets[idx], cnt, mean_sim, True))
            if (j + 1) % 100 == 0:
                self.stdout.write(f'  калибровка {j + 1}/{len(sample_idx)} '
                                  f'({time.time() - t0:.0f}с)')

        # таблица порог -> точность/покрытие (правило голосов уже применено)
        self.stdout.write(f'\nПравило: >= {VOTES_MIN} голосов из {K}; N={len(sample_idx)}')
        self.stdout.write('порог | назначено | точность | покрытие')
        table = []
        for th in [0.0, 0.50, 0.55, 0.60, 0.65, 0.70, 0.72, 0.75, 0.78,
                   0.80, 0.82, 0.85, 0.88, 0.90]:
            decided = [(c, v, s) for c, v, s, d in results if d and s >= th]
            cov = len(decided) / len(results)
            acc = (sum(1 for c, _, _ in decided if c) / len(decided)
                   if decided else 0.0)
            table.append((th, len(decided), acc, cov))
            self.stdout.write(f'{th:5.2f} | {len(decided):9d} | {acc:7.1%} | {cov:7.1%}')
        return

    # ── Полная LOO-калибровка: сетка голоса × порог ─────────────────────────
    def do_calibrate_grid(self, options):
        """Leave-one-out по всем опорным задачам. Для каждой запоминаем лучшего
        кандидата (votes, mean_sim, correct), потом считаем точность/покрытие
        для каждой пары (мин. голосов, порог). Любая пара с голосами >= 6 —
        подмножество заявленного правила «>=6 из 10», т.е. строже = безопаснее."""
        self.stdout.write('Загружаем опорный набор...')
        ids, matrix, topic_sets, canon_ids = load_reference()
        n = len(ids)
        self.stdout.write(f'Опорных задач: {n} (полный leave-one-out)')

        records = []  # (votes, mean_sim, correct) лучшего кандидата
        t0 = time.time()
        for start in range(0, n, CHUNK):
            end = min(start + CHUNK, n)
            sims = matrix[start:end] @ matrix.T  # (m, n)
            for row_i in range(end - start):
                idx = start + row_i
                row = sims[row_i]
                row[idx] = -1.0  # исключаем саму задачу
                top = np.argpartition(row, -K)[-K:]
                top = top[np.argsort(row[top])[::-1]]
                votes = Counter()
                for i in top:
                    for tid in topic_sets[i]:
                        votes[tid] += 1
                best = None
                for tid, cnt in votes.items():
                    voter_sims = [row[i] for i in top if tid in topic_sets[i]]
                    cand = (cnt, float(np.mean(voter_sims)), tid)
                    if best is None or cand > best:
                        best = cand
                if best is None:
                    records.append((0, 0.0, False))
                else:
                    cnt, mean_sim, tid = best
                    records.append((cnt, mean_sim, tid in topic_sets[idx]))
            self.stdout.write(f'  LOO {end}/{n} ({time.time() - t0:.0f}с)')

        self.stdout.write(f'\nСетка (N={n}): мин.голосов × порог -> точность / покрытие / назначено')
        header = 'голоса| ' + ' | '.join(f'{th:^16.2f}' for th in
                                         [0.70, 0.75, 0.78, 0.80, 0.82, 0.85])
        self.stdout.write(header)
        for vmin in [6, 7, 8, 9, 10]:
            cells = []
            for th in [0.70, 0.75, 0.78, 0.80, 0.82, 0.85]:
                dec = [(c,) for v, s, c in records if v >= vmin and s >= th]
                cov = len(dec) / n
                acc = sum(1 for (c,) in dec if c) / len(dec) if dec else 0.0
                cells.append(f'{acc:5.1%} {cov:5.1%} {len(dec):4d}')
            self.stdout.write(f'  {vmin:2d}  | ' + ' | '.join(cells))
        return

    # ── Назначение ──────────────────────────────────────────────────────────
    def do_assign(self, options):
        threshold = options['threshold']
        apply_mode = options['apply']
        log_file = options['log_file']
        t0 = time.time()

        self.log(log_file, f'Режим: {"APPLY" if apply_mode else "DRY-RUN"}, '
                           f'порог {threshold}, голосов >= {VOTES_MIN}/{K}')
        ids, matrix, topic_sets, canon_ids = load_reference()
        self.log(log_file, f'Опорных задач: {len(ids)}')

        # Цели: задачи ВООБЩЕ без тем, с эмбеддингом
        targets = list(Problem.objects
                       .filter(topics__isnull=True, embedding__isnull=False)
                       .values_list('id', 'embedding'))
        if options['limit']:
            targets = targets[:options['limit']]
        self.log(log_file, f'Целей (задач без единой темы): {len(targets)}')

        dim = matrix.shape[1]
        assigned = []       # (pid, tid, votes, mean_sim, neighbor_pids)
        skipped = 0
        processed = 0
        for start in range(0, len(targets), CHUNK):
            chunk = targets[start:start + CHUNK]
            vecs, pids = [], []
            for pid, raw in chunk:
                v = np.frombuffer(bytes(raw), dtype=np.float32)
                if v.shape[0] != dim:
                    continue
                n = np.linalg.norm(v)
                vecs.append(v / (n if n else 1e-9))
                pids.append(pid)
            if not pids:
                continue
            sims = np.stack(vecs) @ matrix.T
            for row_i, pid in enumerate(pids):
                pred = predict(sims[row_i], topic_sets)
                processed += 1
                if pred is None:
                    skipped += 1
                    continue
                tid, cnt, mean_sim, top_idx = pred
                if mean_sim < threshold:
                    skipped += 1
                    continue
                assigned.append((pid, tid, cnt, mean_sim,
                                 [ids[i] for i in top_idx[:5]]))
            if processed % LOG_EVERY < CHUNK:
                self.log(log_file,
                         f'  обработано {processed}/{len(targets)}, '
                         f'назначено {len(assigned)} ({time.time() - t0:.0f}с)')

        # Статистика по темам
        topic_names = dict(Topic.objects.filter(id__in={t for _, t, _, _, _ in assigned})
                           .values_list('id', 'name'))
        dist = Counter(topic_names[tid] for _, tid, _, _, _ in assigned)
        self.log(log_file, f'Итог: назначено {len(assigned)}, '
                           f'осталось без темы {skipped} из {processed}')
        for name, cnt in dist.most_common():
            self.stdout.write(f'  {name}: {cnt}')

        if not apply_mode:
            self.log(log_file, 'DRY-RUN: ничего не записано.')
            return

        # Запись: M2M + журнал
        through = Problem.topics.through
        existing_log = set(AutoTopicAssignment.objects.values_list(
            'problem_id', 'topic_id'))
        new_links, new_logs = [], []
        for pid, tid, cnt, mean_sim, _ in assigned:
            if (pid, tid) in existing_log:
                continue
            new_links.append(through(problem_id=pid, topic_id=tid))
            new_logs.append(AutoTopicAssignment(
                problem_id=pid, topic_id=tid,
                neighbor_votes=cnt, mean_similarity=mean_sim))
        with transaction.atomic():
            through.objects.bulk_create(new_links, batch_size=5000,
                                        ignore_conflicts=True)
            AutoTopicAssignment.objects.bulk_create(new_logs, batch_size=5000)
        self.log(log_file, self.style.SUCCESS(
            f'Записано {len(new_links)} связей + {len(new_logs)} записей журнала '
            f'за {time.time() - t0:.1f}с'))
