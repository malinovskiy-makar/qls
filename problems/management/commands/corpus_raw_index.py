# -*- coding: utf-8 -*-
"""Фаза 0 и 0б: опись 67 Overleaf-архивов и карта «задача → фрагмент `.tex`».

Команда ТОЛЬКО ЧИТАЕТ: ни одного поля в базе не меняет. Она отвечает на
два вопроса, ответы на которые до сих пор приходилось угадывать по имени
файла:

  (а) относится ли конкретный архив к банку задач weconomics вообще;
  (б) если да — где внутри него лежит конкретная задача.

Угадывать по имени нельзя, и это проверено на живых архивах:
`symbol-table.zip` (по названию — таблица символов) содержит файл
`СпросНьюМарьина.tex` с настоящими задачами банка, а `а.zip` и
`Решалка вступы.zip` (по названию — банк) содержат разборы, которых в
базе нет вовсе. Поэтому решение принимается по измеренному пересечению
текста, а имя архива идёт в отчёт как справка.

Результат пишется В ПАПКУ ДАННЫХ, а не в репозиторий: сырьё и
производные от него индексы весят десятки мегабайт и в git им не место
(в отличие от короткой описи, которая ложится в `docs/`).

Порог доказательности и способ сопоставления — в
`problems/corpus_converter/raw_sources.py`.
"""
import collections
import json
import os

from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter import raw_sources as rs
from problems.models import Problem, ProblemPart, SourceReference

#: Распакованные проекты: `<RAW>/<slot>/...`, слоты нумерованные —
#: у Windows предел пути 260 символов, а внутри архивов вложенные папки
#: с русскими именами.
RAW = os.path.join('C:', os.sep, 'Users', 'shipu', 'weconomics-data', '_raw2026')

#: Четыре легаси-источника этой сессии (те же id, что в render_legacy_sources).
LEGACY = {14: 'archive3', 13: 'matek', 3: 'lsh2025', 16: 'reshalki'}

#: Прореживание индекса базы. Безопасно: см. `shingles()`.
DB_STRIDE = 2
#: Сколько разных черепиц должно совпасть, чтобы засчитать задачу найденной.
#: Одна — тоже доказательство (8 слов подряд), но две снимают риск, что
#: совпал единственный шаблонный оборот.
MIN_HITS = 2
#: Короткие задачи дают ровно одну черепицу — для них порог не применим.
SHORT_WORDS = 30


class Command(BaseCommand):
    help = ('Опись Overleaf-архивов и карта «задача → фрагмент .tex». '
            'Только читает, ничего не пишет в базу.')

    def add_arguments(self, parser):
        parser.add_argument('--raw', default=RAW,
                            help='Папка с распакованными архивами')
        parser.add_argument('--slots', default='',
                            help='Только эти слоты через запятую (для отладки)')

    def handle(self, *args, **options):
        raw = options['raw']
        manifest_path = os.path.join(raw, 'manifest.json')
        if not os.path.exists(manifest_path):
            raise CommandError(
                'Нет %s — сначала распакуйте архивы.' % manifest_path)
        manifest = json.load(open(manifest_path, encoding='utf-8'))
        only = {s.strip() for s in options['slots'].split(',') if s.strip()}

        index, src_of, size_of = self._build_index()

        out_dir = os.path.join(raw, 'index')
        os.makedirs(out_dir, exist_ok=True)

        inventory = []
        #: problem_id -> [(hits, slot, rel, start, end)]
        best = collections.defaultdict(list)

        for entry in manifest:
            slot = entry['slot']
            if only and slot not in only:
                continue
            root = os.path.join(raw, slot)
            if not os.path.isdir(root):
                continue
            stats = self._scan_archive(root, slot, index, size_of, best)
            row = dict(entry)
            row.update(stats)
            by_source = collections.Counter()
            for pid in stats.pop('_problems'):
                for sid in src_of.get(pid, ()):
                    by_source[sid] += 1
            row['by_source'] = dict(by_source)
            row['legacy_problems'] = sum(
                n for sid, n in by_source.items() if sid in LEGACY)
            row.pop('_problems', None)
            inventory.append(row)
            self.stdout.write(
                '%s tex=%4d слов=%7d задач=%5d легаси=%5d в_банке=%5.1f%%  %s'
                % (slot, row['n_tex'], row['n_words'], row['matched_problems'],
                   row['legacy_problems'], row['covered_pct'],
                   entry['zip'][:40]))

        mapping = {}
        for pid, rows in best.items():
            rows.sort(key=lambda r: -r[0])
            mapping[str(pid)] = [
                {'hits': h, 'slot': s, 'rel': rel, 'start': a, 'end': b}
                for h, s, rel, a, b in rows[:3]
            ]

        json.dump(inventory, open(os.path.join(out_dir, 'inventory.json'), 'w',
                                  encoding='utf-8'), ensure_ascii=False, indent=1)
        json.dump(mapping, open(os.path.join(out_dir, 'mapping.json'), 'w',
                                encoding='utf-8'), ensure_ascii=False)

        legacy_ids = {pid for pid, sids in src_of.items()
                      if sids & set(LEGACY)}
        mapped_legacy = sum(1 for pid in legacy_ids if str(pid) in mapping)
        self.stdout.write('')
        self.stdout.write('архивов просмотрено: %d' % len(inventory))
        self.stdout.write('задач сопоставлено всего: %d' % len(mapping))
        self.stdout.write('из них легаси-источников: %d из %d (%.1f %%)'
                          % (mapped_legacy, len(legacy_ids),
                             100.0 * mapped_legacy / max(1, len(legacy_ids))))
        self.stdout.write('индекс: %s' % out_dir)

    # -- индекс базы --------------------------------------------------------

    def _build_index(self):
        """`черепица -> {id задач}` по ВСЕМ задачам банка, не только легаси.

        По всем — намеренно: если архив на самом деле принадлежит новому
        источнику (так вышло с `ЛЭШ 2026_ Гамма.zip`, лежащим в папке
        МатЭк), это должно быть видно, а не списано на легаси."""
        self.stdout.write('Читаю тексты задач...')
        chunks = collections.defaultdict(list)
        for pid, st, sol, ans in Problem.objects.values_list(
                'id', 'statement', 'solution', 'answer').iterator(chunk_size=2000):
            chunks[pid] = [st or '', sol or '', ans or '']
        for pid, st in ProblemPart.objects.values_list(
                'problem_id', 'statement').iterator(chunk_size=5000):
            if st:
                chunks[pid].append(st)

        index = collections.defaultdict(set)
        size_of = {}
        for pid, parts in chunks.items():
            words = rs.plain_words('\n'.join(parts))
            size_of[pid] = len(words)
            for sh in rs.shingles(words, stride=DB_STRIDE):
                index[sh].add(pid)
        self.stdout.write('задач: %d, черепиц: %d' % (len(chunks), len(index)))

        src_of = collections.defaultdict(set)
        for pid, sid in SourceReference.objects.values_list('problem_id',
                                                            'source_id'):
            src_of[pid].add(sid)
        return index, src_of, size_of

    # -- разбор одного архива ----------------------------------------------

    def _scan_archive(self, root, slot, index, size_of, best):
        n_tex = n_words = 0
        n_shingles = n_covered = 0
        found = set()
        for rel, full in rs.iter_tex(root):
            n_tex += 1
            try:
                text = rs.read_text(full)
            except OSError as exc:
                self.stderr.write('  ! %s/%s: %r' % (slot, rel, exc))
                continue
            wp = rs.words_with_pos(text, tex=True)
            n_words += len(wp)
            positions = rs.shingle_positions(wp)
            if not positions:
                continue
            n_shingles += len(positions)
            per_problem = collections.defaultdict(list)
            for sh, idxs in positions.items():
                pids = index.get(sh)
                if not pids:
                    continue
                n_covered += 1
                for pid in pids:
                    per_problem[pid].extend(idxs)
            for pid, idxs in per_problem.items():
                span = rs.span_of(wp, idxs)
                if span is None:
                    continue
                start, end, hits = span
                # Порог считается по ПЛОТНОЙ группе, а не по всем окнам
                # файла: два случайных попадания в разных концах листочка
                # доказательством не являются.
                if hits < MIN_HITS and size_of.get(pid, 0) >= SHORT_WORDS:
                    continue
                found.add(pid)
                best[pid].append((hits, slot, rel, start, end))
        # Доля прозы архива, которая ВООБЩЕ есть в банке. Низкая доля при
        # большом объёме текста — не дефект сопоставления, а находка:
        # материал, который в банк ещё не импортировали.
        return {'n_tex': n_tex, 'n_words': n_words,
                'n_shingles': n_shingles, 'n_covered': n_covered,
                'covered_pct': round(100.0 * n_covered / n_shingles, 1)
                if n_shingles else 0.0,
                'matched_problems': len(found), '_problems': found}
