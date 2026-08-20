"""repair_wave1_merge — собрать починки волны 1 в один файл. ТОЛЬКО ЧТЕНИЕ.

Партии лежат в reports/repair_wave1/parts/*.json — каждую писал отдельный
исполнитель со своим контекстом. Здесь они склеиваются, проверяются на
полноту и форму, и складываются в `aa_repairs.json`.

⚠️ ОБЪЁМ ПРАВКИ СЧИТАЕТСЯ ДВУМЯ ЧИСЛАМИ, и это не придирка. Разница длин
(её считал repair_merge эксперимента) у замены «200 символов на другие 200»
равна НУЛЮ — то есть крупная переделка выглядит как отсутствие правки.
Поэтому основное число здесь — сколько символов реально различаются
(difflib: вставленные плюс удалённые), а разница длин печатается рядом ради
сравнимости с прошлым замером.

Запуск:
    venv\\Scripts\\python manage.py repair_wave1_merge
"""

import difflib
import glob
import io
import json
import os
import statistics

from django.core.management.base import BaseCommand

OUT_DIR = os.path.join('reports', 'repair_wave1')
PARTS = os.path.join(OUT_DIR, 'parts')
ACTIONS = ('fixed', 'nothing_to_fix', 'unclear')
FIELDS = ('statement', 'solution', 'answer', 'parts')


def flat_text(fields):
    """Все поля записи одной строкой — для замера объёма правки."""
    chunks = [fields.get('statement') or '', fields.get('solution') or '',
              fields.get('answer') or '']
    for p in fields.get('parts') or []:
        chunks.append((p.get('label') or '') + ' ' + (p.get('statement') or '')
                      + ' ' + (p.get('answer') or ''))
    return '\n'.join(chunks)


def edit_chars(before, after):
    """Сколько символов различаются: вставленные плюс удалённые."""
    n = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, before, after, autojunk=False).get_opcodes():
        if tag == 'replace':
            n += (i2 - i1) + (j2 - j1)
        elif tag == 'delete':
            n += i2 - i1
        elif tag == 'insert':
            n += j2 - j1
    return n


class Command(BaseCommand):
    help = 'Собрать починки волны 1 в aa_repairs.json. Только чтение.'

    def say(self, line):
        try:
            self.stdout.write(line)
        except UnicodeEncodeError:
            self.stdout.write(line.encode('ascii', 'replace').decode())

    def handle(self, *args, **opts):
        sample = {r['id']: r for r in json.load(
            io.open(os.path.join(OUT_DIR, 'sample.json'), encoding='utf-8'))}

        seen, broken, complaints = {}, [], []
        files = sorted(glob.glob(os.path.join(PARTS, '*.json')))
        for path in files:
            name = os.path.basename(path)
            try:
                rows = json.load(io.open(path, encoding='utf-8'))
            except Exception as exc:
                broken.append((name, str(exc)[:160]))
                continue
            if not isinstance(rows, list):
                broken.append((name, 'ожидался список записей'))
                continue
            for r in rows:
                pid = int(r.get('id', 0))
                if pid not in sample:
                    complaints.append('%s: задача #%s не из выборки' % (name, pid))
                    continue
                if r.get('action') not in ACTIONS:
                    complaints.append('%s: #%d — неизвестный action %r'
                                      % (name, pid, r.get('action')))
                    continue
                if not (r.get('explain') or '').strip():
                    complaints.append('%s: #%d — пустое объяснение' % (name, pid))
                fields = r.get('fields') or {}
                extra = sorted(set(fields) - set(FIELDS))
                if extra:
                    complaints.append('%s: #%d — лишние поля в fields: %s'
                                      % (name, pid, ', '.join(extra)))
                    for k in extra:
                        fields.pop(k)
                if r['action'] != 'fixed' and fields:
                    complaints.append('%s: #%d — не «fixed», но fields не пуст'
                                      % (name, pid))
                if r['action'] == 'fixed' and not fields:
                    complaints.append('%s: #%d — «fixed», но fields пуст'
                                      % (name, pid))
                if pid in seen:
                    complaints.append('%s: #%d встретилась второй раз' % (name, pid))
                # ⚠️ Список подпунктов замещает прежний целиком, поэтому его
                # УКОРАЧИВАНИЕ — это потеря подпункта. Рост законен: разбивка
                # слипшихся вариантов на отдельные пункты и есть починка.
                if 'parts' in fields:
                    was = len(sample[pid]['before']['parts'])
                    now = len(fields['parts'] or [])
                    if now < was:
                        complaints.append(
                            '%s: #%d — подпунктов было %d, стало %d (потеря?)'
                            % (name, pid, was, now))
                seen[pid] = {'id': pid, 'method': r.get('method') or 'W1',
                             'action': r['action'],
                             'explain': (r.get('explain') or '').strip(),
                             'fields': fields}

        missing = sorted(set(sample) - set(seen))
        repairs = [seen[k] for k in sorted(seen)]

        stats = {'fixed': [], 'delta': []}
        by_action = {}
        for r in repairs:
            by_action[r['action']] = by_action.get(r['action'], 0) + 1
            if r['action'] != 'fixed':
                continue
            rec = sample[r['id']]
            touched = {k: rec['before'].get(k) for k in r['fields']}
            before = flat_text(touched)
            after = flat_text(r['fields'])
            r['edit_chars'] = edit_chars(before, after)
            r['len_delta'] = len(after) - len(before)
            r['touched'] = sorted(r['fields'])
            stats['fixed'].append(r['edit_chars'])
            stats['delta'].append(abs(r['len_delta']))

        with io.open(os.path.join(OUT_DIR, 'aa_repairs.json'), 'w',
                     encoding='utf-8') as fh:
            json.dump({
                'format': 'qls-repairs-v1',
                'bundle': 'aa_20260728',
                'wave': 1,
                'expected': len(sample),
                'count': len(repairs),
                'by_action': by_action,
                'repairs': repairs,
            }, fh, ensure_ascii=False, indent=1)

        self.say('=== ПОЧИНКИ ВОЛНЫ 1 (Сборник АА) ===')
        self.say('файлов партий: %d' % len(files))
        for name, err in broken:
            self.say('⚠ НЕ РАЗОБРАН: %s — %s' % (name, err))
        self.say('собрано: %d из %d ожидаемых' % (len(repairs), len(sample)))
        if missing:
            self.say('⚠ НЕ ХВАТАЕТ: %s' % ', '.join('#%d' % m for m in missing))
        else:
            self.say('все задачи выборки на месте')
        for c in complaints:
            self.say('⚠ %s' % c)
        self.say('')
        for a in ACTIONS:
            self.say('  %-16s %d' % (a, by_action.get(a, 0)))
        refused = by_action.get('nothing_to_fix', 0) + by_action.get('unclear', 0)
        self.say('  %-16s %d (nothing_to_fix + unclear)' % ('отказов всего', refused))
        if stats['fixed']:
            e = stats['fixed']
            self.say('')
            self.say('объём правки (различающихся символов): среднее %d, '
                     'медиана %d, максимум %d'
                     % (sum(e) / len(e), statistics.median(e), max(e)))
            d = stats['delta']
            self.say('разница длин (мера прошлого замера): среднее %d, медиана %d'
                     % (sum(d) / len(d), statistics.median(d)))
            touched = {}
            for r in repairs:
                for f in r.get('touched') or []:
                    touched[f] = touched.get(f, 0) + 1
            self.say('какие поля трогали: %s'
                     % ', '.join('%s %d' % kv for kv in
                                 sorted(touched.items(), key=lambda x: -x[1])))
        self.say('')
        self.say('-> %s' % os.path.join(OUT_DIR, 'aa_repairs.json'))
