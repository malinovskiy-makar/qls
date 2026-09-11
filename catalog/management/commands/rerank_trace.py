# -*- coding: utf-8 -*-
"""Команда rerank_trace — отладочная трассировка одного запроса умного
поиска через `catalog/rerank.py`: тот же код, что и вью, без Django-сервера.

Печатает: пул по ногам (id, заголовок, тема, из какой ноги, ранг в ноге),
карточки первых 15 кандидатов (буквально то, что видит модель), баллы
модели по ВСЕМ кандидатам пула по убыванию и сводку (сколько ≥ 50, сколько
получили ровно 0, сколько модель вообще не оценила).

⚠️ ЗОВЁТ НАСТОЯЩУЮ МОДЕЛЬ (GLM-5.3-Flash) — платно, как и обычный
переранжированный поиск. Дороже не становится: тот же пул, та же разбивка
на пачки по BATCH кандидатов, что и в `catalog/rerank.py:_run`.

Запуск:
    venv313\\Scripts\\python.exe manage.py rerank_trace "запрос преподавателя"
"""
from django.core.management.base import BaseCommand, CommandError

from catalog import rerank


class Command(BaseCommand):
    help = ('Отладочная трассировка одного запроса умного поиска: пул по '
           'ногам, карточки первых 15, баллы модели по всем кандидатам.')

    def add_arguments(self, parser):
        parser.add_argument('query', help='Текст поискового запроса')

    def handle(self, *args, **options):
        query = options['query']

        from django.conf import settings

        legs = settings.SMART_SEARCH_RERANK_LEGS
        depth = settings.SMART_SEARCH_RERANK_LEG_DEPTH
        cap = settings.SMART_SEARCH_RERANK_POOL_CAP
        timeout = settings.SMART_SEARCH_RERANK_TIMEOUT

        index, rows = rerank.get_corpus()

        # ─── Сборка пула С СОХРАНЕНИЕМ ноги и ранга (build_pool этого не
        # отдаёт — он для вью, которому нужен только итоговый порядок id).
        entries = []
        seen = set()
        leg_sizes = {}
        if 'dense' in legs:
            ids = rerank._dense_leg(query, depth)
            leg_sizes['dense'] = len(ids)
            for pos, pid in enumerate(ids, start=1):
                if pid not in seen:
                    seen.add(pid)
                    entries.append({'id': pid, 'leg': 'dense', 'rank': pos})
        if 'bm25' in legs:
            ids = rerank._bm25_leg(query, depth, index)
            leg_sizes['bm25'] = len(ids)
            for pos, pid in enumerate(ids, start=1):
                if pid not in seen:
                    seen.add(pid)
                    entries.append({'id': pid, 'leg': 'bm25', 'rank': pos})

        self.stdout.write('Запрос: %r' % query)
        self.stdout.write('Ноги пула (до дедупа): %s' % leg_sizes)

        if not entries:
            self.stdout.write(self.style.WARNING(
                'Пул пуст — ни одна нога ничего не нашла.'))
            return

        # Дедуп по dup_group — та же логика, что в build_pool.
        ordered_ids = [e['id'] for e in entries]
        groups = {pid: (rows[pid]['dup_group'], rows[pid]['dup_is_best'])
                  for pid in ordered_ids if pid in rows}
        deduped, dropped = rerank.collapse_dedup(ordered_ids, groups)
        deduped = deduped[:cap]
        deduped_set = set(deduped)
        pool_entries = [e for e in entries if e['id'] in deduped_set]

        self.stdout.write('Пул после дедупа и потолка (%d): %d кандидатов, '
                          'отброшено дублей: %d' %
                          (cap, len(pool_entries), len(dropped)))
        self.stdout.write('')

        # ─── Пул по ногам ────────────────────────────────────────────────
        self.stdout.write('── Пул ─────────────────────────────────────────')
        for e in pool_entries:
            row = rows.get(e['id'], {})
            title = (row.get('title') or '')[:70]
            topics = ', '.join(row.get('topics') or []) or '—'
            self.stdout.write(
                '  id=%-6d нога=%-5s ранг=%-3d тема=%-30s %s' %
                (e['id'], e['leg'], e['rank'], topics[:30], title))
        self.stdout.write('')

        # ─── Карточки первых 15 ─────────────────────────────────────────
        self.stdout.write('── Карточки первых 15 (что видит модель) ───────')
        for i, e in enumerate(pool_entries[:15], start=1):
            row = rows.get(e['id'])
            if row is None:
                continue
            self.stdout.write('[%d] нога=%s ранг=%d' % (i, e['leg'], e['rank']))
            self.stdout.write(rerank.card(row))
            self.stdout.write('')

        # ─── Вызов модели (тот же код, что и вью) ──────────────────────
        pool_ids = [e['id'] for e in pool_entries]
        try:
            _ranked, usage, scores = rerank._score_pool(
                query, pool_ids, rows, timeout)
        except Exception as exc:                                # noqa: BLE001
            raise CommandError(
                'переранжирование упало: %s: %s' %
                (type(exc).__name__, exc)) from exc

        self.stdout.write('── Баллы модели (по убыванию) ──────────────────')
        by_score = sorted(pool_ids,
                          key=lambda pid: (-scores.get(pid, -1), pid))
        for pid in by_score:
            row = rows.get(pid, {})
            title = (row.get('title') or '')[:60]
            score = scores.get(pid)
            метка = '%3d' % score if score is not None else '  —'
            self.stdout.write('  %s  id=%-6d %s' % (метка, pid, title))
        self.stdout.write('')

        неоценённые = [pid for pid in pool_ids if pid not in scores]
        высокий_балл = [pid for pid in pool_ids
                        if scores.get(pid, -1) >= 50]
        нулевой_балл = [pid for pid in pool_ids if scores.get(pid) == 0]

        self.stdout.write('── Сводка ───────────────────────────────────────')
        self.stdout.write('  кандидатов в пуле: %d' % len(pool_ids))
        self.stdout.write('  пачек модели: %d, время модели: %.3fс' %
                          (usage['batches'], usage['model_seconds']))
        self.stdout.write('  балл ≥ 50: %d' % len(высокий_балл))
        self.stdout.write('  балл == 0: %d' % len(нулевой_балл))
        self.stdout.write('  не оценено моделью: %d' % len(неоценённые))
