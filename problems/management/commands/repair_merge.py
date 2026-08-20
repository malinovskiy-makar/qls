"""repair_merge — собрать починки из партий в один repairs.json. ТОЛЬКО ЧТЕНИЕ.

Партии лежат в reports/repair_experiment/parts/*.json — каждую писал отдельный
исполнитель со своим контекстом (так обеспечена изоляция способов A и B).

Проверяет полноту: у каждой задачи парной группы должны быть обе починки,
у контрольной — только способ A. Недостача называется вслух, а не молча.

Запуск:
    venv\\Scripts\\python manage.py repair_merge
"""

import glob
import io
import json
import os

from django.core.management.base import BaseCommand

OUT_DIR = 'reports/repair_experiment'
PARTS = os.path.join(OUT_DIR, 'parts')


def text_len(fields):
    n = 0
    for k in ('statement', 'solution', 'answer'):
        n += len(fields.get(k) or '')
    for p in fields.get('parts') or []:
        n += len(p.get('statement') or '') + len(p.get('answer') or '')
    return n


class Command(BaseCommand):
    help = 'Собрать починки из партий. Только чтение.'

    def say(self, line):
        try:
            self.stdout.write(line)
        except UnicodeEncodeError:
            self.stdout.write(line.encode('ascii', 'replace').decode())

    def handle(self, *args, **options):
        sample = {r['id']: r for r in json.load(
            io.open(f'{OUT_DIR}/sample.json', encoding='utf-8'))}

        seen = {}
        broken = []
        for path in sorted(glob.glob(os.path.join(PARTS, '*.json'))):
            try:
                rows = json.load(io.open(path, encoding='utf-8'))
            except Exception as exc:
                broken.append((os.path.basename(path), str(exc)[:120]))
                continue
            for r in rows:
                seen[(int(r['id']), r['method'])] = r

        # ── полнота ──────────────────────────────────────────────────────
        want = set()
        for pid, rec in sample.items():
            want.add((pid, 'A'))
            if rec['group'] == 'paired':
                want.add((pid, 'B'))
        missing = sorted(want - set(seen))

        repairs = [seen[k] for k in sorted(seen)]
        with io.open(f'{OUT_DIR}/repairs.json', 'w', encoding='utf-8') as fh:
            json.dump(repairs, fh, ensure_ascii=False, indent=1)

        acts = {}
        sizes = []
        for r in repairs:
            acts[r['action']] = acts.get(r['action'], 0) + 1
            if r['action'] == 'fixed':
                rec = sample.get(r['id'])
                if rec:
                    before = text_len({k: v for k, v in rec['before'].items()
                                       if k in (r.get('fields') or {})})
                    after = text_len(r.get('fields') or {})
                    sizes.append(abs(after - before))

        self.say('=== ПОЧИНКИ ===')
        self.say('файлов партий: %d' % len(glob.glob(os.path.join(PARTS, '*.json'))))
        if broken:
            for name, err in broken:
                self.say('⚠ НЕ РАЗОБРАН: %s — %s' % (name, err))
        self.say('починок собрано: %d (ожидалось %d)' % (len(repairs), len(want)))
        if missing:
            self.say('⚠ НЕ ХВАТАЕТ: %s' % ', '.join('%d/%s' % m for m in missing))
        else:
            self.say('все ожидаемые починки на месте')
        self.say('')
        for a, n in sorted(acts.items(), key=lambda x: -x[1]):
            self.say('  %-16s %d' % (a, n))
        if sizes:
            self.say('')
            self.say('средний объём правки: %d символов (медиана %d)'
                     % (sum(sizes) / len(sizes), sorted(sizes)[len(sizes) // 2]))
