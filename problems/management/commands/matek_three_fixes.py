# -*- coding: utf-8 -*-
"""Три задачи МатЭк, испорченные нашим же откатом 21 июля: сверка и починка.

По умолчанию НИЧЕГО НЕ ПИШЕТ — собирает превью reports/matek_recon/
three_fixes.html, где по каждому затронутому полю рядом стоят ТРИ версии:

  СЕЙЧАС      — что лежит в базе (результат отката);
  ДО ОТКАТА   — правка Sonnet из reports/batch2_sweep/backup_revert_*.json;
  ОРИГИНАЛ    — .tex из zip-архива Overleaf, разобранный ТЕМ ЖЕ парсером,
                которым задача импортировалась (import_matek), — чтобы
                «оригинал» означал то же самое, что при импорте, а не то,
                что показалось второму парсеру.

Правило выбора (решение владельца, 2026-08-08): побеждает версия, совпадающая
с .tex; если ни одна не совпадает — та, что даёт корректный рендер и не теряет
чисел относительно .tex.

⚠️ .tex НЕ всегда эталон. У #27998 сам автор написал `$Q_D_t(...)$` (двойной
индекс — ошибка и в LaTeX, и в KaTeX) и юникодный минус «−» вместо «-».
Совпадение с .tex здесь означало бы «оставить сломанным», поэтому решение по
каждому полю принимает человек, глядя на превью.

    ./venv/bin/python manage.py matek_three_fixes            # только превью
    ./venv/bin/python manage.py matek_three_fixes --confirm  # записать в базу
"""

import difflib
import json
import os
import re
import subprocess
import tempfile
import unicodedata
import zipfile
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.management.commands.import_matek import (
    clean_latex, parse_problems_from_tex)
from problems.management.commands.matek_recon import ZIP_DIR, _nfc
from problems.models import Problem, ProblemPart, SourceReference

REPORT_DIR = 'reports/matek_recon'
OUT_HTML = os.path.join(REPORT_DIR, 'three_fixes.html')
OUT_JSON = os.path.join(REPORT_DIR, 'three_fixes.json')
BACKUP_IN = 'reports/batch2_sweep/backup_revert_20260721_112821.json'
BACKUP_OUT = os.path.join(REPORT_DIR, 'three_fixes_backup.json')

PIDS = (27998, 29026, 27394)

# Что записать в каждое поле. Заполняется после разбора превью человеком;
# ключ — 'statement:<pid>' или 'part:<pk>', значение — 'tex' | 'sonnet' | 'keep'.
# Пусто = команда сама предложит выбор по правилу и покажет его в превью.
CHOICES = {}

MEASURE_JS = 'scripts/katex_measure_texts.js'

# Содержимое формул `clean_latex` больше не трогает — защита живёт в самом
# импортёре (см. его докстринг). Второй копии здесь нет намеренно: две чистки
# разошлись бы, и превью показывало бы не то, что даёт импорт.
clean_keep_math = clean_latex

_WS = re.compile(r'\s+')
_NUM_SIGN = re.compile(r'[-+−]?\d+(?:[.,]\d+)?')
# LaTeX-скобка десятичной запятой: 0{,}5 и 0,5 — одно и то же число.
_DEC_BRACE = re.compile(r'(\d)\{,\}(\d)')


def norm(text):
    return _WS.sub(' ', (text or '')).strip()


def numbers_of(text):
    """Последовательность числовых/знаковых токенов — как в sweep_field."""
    t = _DEC_BRACE.sub(r'\1,\2', text or '')
    return [m.group().replace('−', '-') for m in _NUM_SIGN.finditer(t)]


def same_numbers(a, b):
    return numbers_of(a) == numbers_of(b)


def ratio(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def word_diff(old, new):
    """Пословный дифф в HTML: удалённое красным, добавленное зелёным."""
    import html as h
    a, b = norm(old).split(' '), norm(new).split(' ')
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == 'equal':
            out.append(h.escape(' '.join(a[i1:i2])))
        else:
            if i1 != i2:
                out.append('<del>{}</del>'.format(h.escape(' '.join(a[i1:i2]))))
            if j1 != j2:
                out.append('<ins>{}</ins>'.format(h.escape(' '.join(b[j1:j2]))))
    return ' '.join(x for x in out if x)


class Command(BaseCommand):
    help = ('Сверка трёх задач МатЭк, испорченных откатом: три версии рядом. '
            'Без --confirm только превью, в базу не пишет.')

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='Записать выбранные версии в базу.')
        parser.add_argument('--no-measure', action='store_true',
                            help='Не гонять рендер (быстрее, но без цифр поломок).')
        parser.add_argument('--skip-pid', default='',
                            help='Задачи, которые НЕ записывать (через запятую). '
                                 'Нужно, когда по одной из трёх решение отложено: '
                                 'у #27998 числа .tex и Sonnet расходятся в записи '
                                 'индекса, и владелец смотрит это отдельно.')

    # ── исходники ───────────────────────────────────────────────────────

    def _tex_of(self, pid):
        """СЫРОЙ .tex-блок задачи, разрезанный на условие и подпункты.

        ⚠️ Здесь НЕЛЬЗЯ брать выход `parse_problems_from_tex`, хотя он под
        рукой. Именно этим парсером задача и импортировалась, поэтому его
        выход совпадает с до-Sonnet состоянием базы ПО ПОСТРОЕНИЮ — сравнение
        «база против такого оригинала» всегда даёт 100% и не отличает
        авторский текст от ошибки импортёра. А ошибки там есть: `clean_latex`
        вырезает `\\quad` в том числе ВНУТРИ формулы (#29026: `0{,}5x \\quad x
        \\leqslant 16` → `0{,}5x x \\leqslant 16`, на экране слипается), а
        подпункты старого формата могут вобрать в себя текст решения (#27394).

        Поэтому режем сырой текст сами и показываем человеку то, что написал
        автор. Парсер используется только чтобы найти границы блока.
        """
        note = _nfc(SourceReference.objects.filter(
            problem_id=pid, source_id=13).values_list('note', flat=True).first())
        root, _, rest = note.partition('/')
        zp = os.path.join(ZIP_DIR, root + '.zip')
        if not os.path.exists(zp):
            return (None, 0.0), note
        with zipfile.ZipFile(zp) as zf:
            name = next((n for n in zf.namelist() if _nfc(n).endswith(rest)), None)
            if not name:
                return (None, 0.0), note
            raw = zf.read(name).decode('utf-8', 'replace')

        current = Problem.objects.get(pk=pid).statement or ''
        starts = [m.start() for m in re.finditer(r'\\problem\b', raw)]
        best, best_r = None, 0.0
        for i, s in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(raw)
            chunk = raw[s:end]
            r = ratio(clean_latex(chunk)[:len(current) + 200], current)
            if r > best_r:
                best, best_r = chunk, r
        if best is None:
            return (None, 0.0), note
        return (self._split_raw_block(best), best_r), note

    def _split_raw_block(self, chunk):
        """Сырой блок → {'statement': …, 'subitems': [...]}.

        Решение отрезается: всё от `\\solution` и дальше к условию не относится.
        """
        body = chunk
        m = re.search(r'\\solution\b', body)
        if m:
            body = body[:m.start()]
        body = re.sub(r'^\\problem\b', '', body).strip()

        if body.startswith('{'):
            # Новый формат: {метка}[Заголовок]{условие}{подпункты}
            from problems.management.commands.import_matek import (
                _extract_braced, _extract_optional)
            pos = 0
            _label, pos = _extract_braced(body, pos)
            if _label is None:
                return {'statement': body, 'subitems': []}
            _title, pos_after = _extract_optional(body, pos)
            if _title is not None:
                pos = pos_after
            stmt, pos = _extract_braced(body, pos)
            stmt = stmt or ''
            subs_raw = ''
            peek = pos
            while peek < len(body) and body[peek] in ' \t\n\r':
                peek += 1
            if peek < len(body) and body[peek] == '{':
                subs_raw, pos = _extract_braced(body, pos)[0] or '', pos
            items = [s.strip() for s in re.split(r'\\n\b', subs_raw or '') if s.strip()]
            return {'statement': stmt.strip(), 'subitems': items}

        # Старый формат: условие, затем \rsubitem/\Subitem
        pieces = re.split(r'\\[Rr]?[Ss]ubitem\b', body)
        return {'statement': pieces[0].strip(),
                'subitems': [p.strip() for p in pieces[1:] if p.strip()]}

    def _reverted_fields(self, pid, backup):
        """Поля этой задачи, которых коснулся откат: [(вид, ключ, метка)]."""
        out = []
        if str(pid) in backup.get('statement', {}):
            out.append(('statement', pid, ''))
        for part in ProblemPart.objects.filter(problem_id=pid).order_by('order', 'id'):
            if str(part.pk) in backup.get('part', {}):
                out.append(('part', part.pk, part.label or ''))
        return out

    # ── измерение рендера ───────────────────────────────────────────────

    def _measure(self, texts):
        """{ключ: {'errors': n, 'red': n}} через общий измеритель на chromium."""
        if not texts:
            return {}
        items = [{'key': k, 'text': v} for k, v in texts.items()]
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False,
                                         encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False)
            src = f.name
        dst = src + '.out'
        env = dict(os.environ)
        env.setdefault('NODE_PATH', os.path.abspath('node_modules'))
        try:
            proc = subprocess.run(['node', MEASURE_JS, src, dst],
                                  capture_output=True, text=True, env=env, timeout=600)
            if proc.returncode != 0:
                self.stdout.write(self.style.WARNING(
                    'Измеритель рендера не отработал:\n' + proc.stderr[:600]))
                return {}
            with open(dst, encoding='utf-8') as f:
                return {r['key']: r for r in json.load(f)}
        finally:
            for p in (src, dst):
                if os.path.exists(p):
                    os.unlink(p)

    # ── главный ход ─────────────────────────────────────────────────────

    def handle(self, *args, **opts):
        os.makedirs(REPORT_DIR, exist_ok=True)
        if not os.path.exists(BACKUP_IN):
            raise CommandError('Нет бэкапа отката: ' + BACKUP_IN)
        with open(BACKUP_IN, encoding='utf-8') as f:
            backup = json.load(f)

        rows = []
        for pid in PIDS:
            (blk, blk_ratio), note = self._tex_of(pid)
            problem = Problem.objects.get(pk=pid)
            tex_parts = []
            if blk:
                tex_parts = [clean_keep_math(s) for s in blk.get('subitems') or []]
            for kind, key, label in self._reverted_fields(pid, backup):
                if kind == 'statement':
                    current = problem.statement or ''
                    sonnet = backup['statement'][str(pid)]
                    tex = clean_keep_math(blk['statement']) if blk else ''
                else:
                    part = ProblemPart.objects.get(pk=key)
                    current = part.statement or ''
                    sonnet = backup['part'][str(key)]
                    tex = self._match_part(current, sonnet, tex_parts)
                rows.append({
                    'pid': pid, 'kind': kind, 'key': key, 'label': label,
                    'note': note, 'block_ratio': round(blk_ratio, 3) if blk else None,
                    'current': current, 'sonnet': sonnet, 'tex': tex,
                    'r_cur_tex': round(ratio(current, tex), 3) if tex else None,
                    'r_son_tex': round(ratio(sonnet, tex), 3) if tex else None,
                    'nums_cur_tex': same_numbers(current, tex) if tex else None,
                    'nums_son_tex': same_numbers(sonnet, tex) if tex else None,
                })

        measured = {}
        if not opts['no_measure']:
            texts = {}
            for i, r in enumerate(rows):
                for v in ('current', 'sonnet', 'tex'):
                    if r[v]:
                        texts['{}:{}'.format(i, v)] = r[v]
            measured = self._measure(texts)
            for i, r in enumerate(rows):
                for v in ('current', 'sonnet', 'tex'):
                    m = measured.get('{}:{}'.format(i, v))
                    r['dmg_' + v] = (m['errors'], m['red']) if m else None

        for r in rows:
            r['proposal'], r['why'] = self._propose(r)

        with open(OUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        self._write_html(rows)
        for r in rows:
            self.stdout.write('#{pid} {kind} {label:<3} → предлагаю {proposal:<7} ({why})'
                              .format(**r))
        self.stdout.write('Превью → {}'.format(OUT_HTML))

        if opts['confirm']:
            skip = {int(x) for x in opts['skip_pid'].split(',') if x.strip().isdigit()}
            if skip:
                self.stdout.write(self.style.WARNING(
                    'Не записываю (решение отложено): {}'.format(
                        ', '.join('#{}'.format(p) for p in sorted(skip)))))
            self._apply([r for r in rows if r['pid'] not in skip])
        else:
            self.stdout.write(self.style.WARNING(
                'Это ПРЕВЬЮ. В базу ничего не записано. Для записи: --confirm'))

    def _match_part(self, current, sonnet, tex_parts):
        """Подпункт .tex, соответствующий этому подпункту базы.

        Сопоставляем по СХОДСТВУ ТЕКСТА, а не по номеру: подпункты могли
        переставиться или склеиться при импорте, и позиционное сопоставление
        тихо подсунуло бы соседний пункт (урок группы Б Батча 2).
        """
        best, best_r = '', 0.0
        for cand in tex_parts:
            r = max(ratio(cand, current), ratio(cand, sonnet))
            if r > best_r:
                best, best_r = cand, r
        return best if best_r >= 0.5 else ''

    def _propose(self, r):
        """Предложение по правилу владельца. Решает всё равно человек."""
        if not r['tex']:
            return 'sonnet', 'оригинал не найден'
        cur_ok = r['dmg_current'] in (None, (0, 0))
        son_ok = r['dmg_sonnet'] in (None, (0, 0))
        tex_ok = r['dmg_tex'] in (None, (0, 0))
        if r['r_cur_tex'] and r['r_cur_tex'] > 0.995 and cur_ok:
            return 'keep', 'совпадает с .tex и рендерится чисто'
        if r['r_son_tex'] and r['r_son_tex'] > 0.995 and son_ok:
            return 'sonnet', 'совпадает с .tex и рендерится чисто'
        if tex_ok and r['tex']:
            return 'tex', 'оригинал рендерится чисто — берём его дословно'
        if son_ok and r['nums_son_tex']:
            return 'sonnet', 'рендерится чисто и числа сходятся с .tex'
        if cur_ok and r['nums_cur_tex']:
            return 'keep', 'рендерится чисто и числа сходятся с .tex'
        return 'sonnet', 'ни одна версия не чиста — нужен глаз'

    # ── запись ──────────────────────────────────────────────────────────

    def _apply(self, rows):
        chosen = {}
        for r in rows:
            k = '{}:{}'.format(r['kind'], r['key'])
            pick = CHOICES.get(k, r['proposal'])
            if pick == 'keep':
                continue
            chosen[k] = (r, {'sonnet': r['sonnet'], 'tex': r['tex']}[pick], pick)
        if not chosen:
            self.stdout.write('Менять нечего.')
            return

        # Бэкап ТЕКУЩИХ значений — до единой записи.
        dump = {'made_at': datetime.now().isoformat(timespec='seconds'),
                'statement': {}, 'part': {}}
        for (r, _new, _pick) in chosen.values():
            if r['kind'] == 'statement':
                dump['statement'][str(r['key'])] = r['current']
            else:
                dump['part'][str(r['key'])] = r['current']
        with open(BACKUP_OUT, 'w', encoding='utf-8') as f:
            json.dump(dump, f, ensure_ascii=False, indent=1)
        self.stdout.write('Бэкап текущих значений → {}'.format(BACKUP_OUT))

        with transaction.atomic():
            for (r, new, pick) in chosen.values():
                if r['kind'] == 'statement':
                    Problem.objects.filter(pk=r['key']).update(statement=new)
                else:
                    ProblemPart.objects.filter(pk=r['key']).update(statement=new)
                self.stdout.write('  #{} {} {} ← {}'.format(
                    r['pid'], r['kind'], r['label'] or r['key'], pick))
        self.stdout.write(self.style.SUCCESS(
            'Записано полей: {}'.format(len(chosen))))

    # ── превью ──────────────────────────────────────────────────────────

    def _write_html(self, rows):
        import html as h
        from django.conf import settings
        from django.test import Client
        if 'testserver' not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']
        # Голову (токены, KaTeX и весь боевой конвейер) берём с настоящей
        # страницы каталога — второго рисователя не заводим.
        page = Client().get('/catalog/problem/{}/'.format(PIDS[0])).content.decode()
        head = re.search(r'<head>(.*?)</head>', page, re.S).group(1)
        head = re.sub(r'<title>.*?</title>', '<title>МатЭк — три починки</title>',
                      head, count=1, flags=re.S)
        tail = re.search(r'</main>\s*(<script>.*?</script>)\s*</body>', page, re.S)
        tail = tail.group(1) if tail else ''

        css = """
.tf-wrap { max-width: 1180px; margin: 0 auto; padding: 24px 16px 80px; }
.tf-h1 { font-size: 24px; margin-bottom: 8px; }
.tf-lead { color: var(--text-dim); font-size: 14px; line-height: 1.6; margin-bottom: 24px; }
.tf-card { border: 1px solid var(--border); border-radius: 12px; background: var(--surface);
           margin: 28px 0; overflow: hidden; }
.tf-card > h2 { font-size: 17px; padding: 12px 16px; background: var(--surface-2);
                border-bottom: 1px solid var(--border); }
.tf-field { border-top: 1px solid var(--border); padding: 14px 16px; }
.tf-field:first-of-type { border-top: 0; }
.tf-name { font: 12px/1.6 ui-monospace, Menlo, monospace; color: var(--text-dim);
           margin-bottom: 10px; }
.tf-cols { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
@media (max-width: 900px) { .tf-cols { grid-template-columns: 1fr; } }
.tf-col { border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px;
          background: var(--surface); }
.tf-col > h3 { font-size: 12px; text-transform: uppercase; letter-spacing: .04em;
               color: var(--text-dim); margin-bottom: 8px; }
.tf-col--win { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent) inset; }
.tf-body { font-size: 14px; line-height: 1.65; white-space: pre-wrap; word-break: break-word; }
.tf-badge { display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 999px;
            background: var(--chip-bg); color: var(--chip-text); margin-left: 6px; }
.tf-bad { background: #fde8ef; color: #9d174d; }
[data-theme="dark"] .tf-bad { background: #4a1027; color: #ffb3cf; }
.tf-diff { margin-top: 10px; font: 12px/1.7 ui-monospace, Menlo, monospace;
           background: var(--surface-2); border-radius: 8px; padding: 10px 12px;
           word-break: break-word; }
.tf-diff del { background: #fde8ef; color: #9d174d; text-decoration: line-through; }
.tf-diff ins { background: #e6f6ec; color: #14532d; text-decoration: none; }
[data-theme="dark"] .tf-diff del { background: #4a1027; color: #ffb3cf; }
[data-theme="dark"] .tf-diff ins { background: #10331f; color: #9be8b6; }
.tf-verdict { margin-top: 10px; font-size: 13px; padding: 8px 12px; border-radius: 8px;
              background: var(--surface-2); border-left: 3px solid var(--accent); }
"""
        # ⚠️ Классы с префиксом tf-: имя вроде .text совпало бы по токену с
        # классом внутри .katex-html и протащило бы рамку прямо в формулу.

        parts = ['<!doctype html>\n<html lang="ru">\n<head>', head,
                 '<style>{}</style></head>\n<body>\n<div class="tf-wrap">'.format(css)]
        parts.append(
            '<h1 class="tf-h1">МатЭк — три задачи, испорченные нашим откатом</h1>'
            '<p class="tf-lead">По каждому полю, которого коснулся откат 21 июля, '
            'три версии рядом: <b>СЕЙЧАС</b> (в базе), <b>ДО ОТКАТА</b> (правка Sonnet '
            'из бэкапа) и <b>ОРИГИНАЛ .tex</b> (разобран тем же парсером '
            '<code>import_matek</code>, которым задача импортировалась).<br>'
            'Числа в скобках у заголовка колонки — поломки рендера: '
            '<code>ошибки KaTeX / красные неизвестные команды</code>. '
            'Рамкой акцента обведена версия, которую предлагает правило.<br>'
            '<b>В базу ничего не записано</b> — это превью для решения.</p>')

        by_pid = {}
        for r in rows:
            by_pid.setdefault(r['pid'], []).append(r)
        for pid, group in by_pid.items():
            parts.append('<div class="tf-card"><h2>#{} — {} <span class="tf-badge">{}</span></h2>'
                         .format(pid, h.escape(Problem.objects.get(pk=pid).title or ''),
                                 h.escape(group[0]['note'])))
            for r in group:
                name = ('условие' if r['kind'] == 'statement'
                        else 'подпункт «{}» (pk {})'.format(r['label'], r['key']))
                parts.append('<div class="tf-field"><div class="tf-name">{} · сходство с .tex: '
                             'сейчас {} / Sonnet {} · числа как в .tex: сейчас {} / Sonnet {}</div>'
                             .format(h.escape(name), r['r_cur_tex'], r['r_son_tex'],
                                     'да' if r['nums_cur_tex'] else 'нет',
                                     'да' if r['nums_son_tex'] else 'нет'))
                parts.append('<div class="tf-cols">')
                for vkey, vtitle in (('current', 'Сейчас в базе'),
                                     ('sonnet', 'До отката (Sonnet)'),
                                     ('tex', 'Оригинал .tex')):
                    win = ((vkey == 'current' and r['proposal'] == 'keep')
                           or (vkey == 'sonnet' and r['proposal'] == 'sonnet')
                           or (vkey == 'tex' and r['proposal'] == 'tex'))
                    dmg = r.get('dmg_' + vkey)
                    badge = ''
                    if dmg:
                        cls = 'tf-badge tf-bad' if (dmg[0] or dmg[1]) else 'tf-badge'
                        badge = '<span class="{}">{} / {}</span>'.format(cls, dmg[0], dmg[1])
                    parts.append('<div class="tf-col{}"><h3>{}{}</h3><div class="tf-body">{}</div></div>'
                                 .format(' tf-col--win' if win else '', vtitle, badge,
                                         h.escape(r[vkey] or '— нет —')))
                parts.append('</div>')
                if r['tex']:
                    parts.append('<div class="tf-diff"><b>.tex → сейчас:</b><br>{}</div>'
                                 .format(word_diff(r['tex'], r['current'])))
                    parts.append('<div class="tf-diff"><b>.tex → Sonnet:</b><br>{}</div>'
                                 .format(word_diff(r['tex'], r['sonnet'])))
                parts.append('<div class="tf-verdict">Предлагаю: <b>{}</b> — {}</div>'
                             .format(r['proposal'], h.escape(r['why'])))
                parts.append('</div>')
            parts.append('</div>')

        parts.append('</div>' + tail + '\n</body>\n</html>\n')
        with open(OUT_HTML, 'w', encoding='utf-8') as f:
            f.write('\n'.join(parts))
