# -*- coding: utf-8 -*-
"""Визуальная выборка МатЭк: одна HTML-страница, ТОЛЬКО ЧИТАЕТ базу.

Задача 5 разведки. 40 СЛУЧАЙНЫХ видимых задач источника, отрисованных ровно
так, как их видит ученик: страница `/catalog/problem/<id>/` рендерится
настоящим Django test client (те же вьюхи, шаблоны, CSS), из ответа берётся
содержимое `<main>`, а `<head>` и хвостовой скрипт KaTeX-конвейера — от
первой страницы. Второго рисователя не заводим: он разошёлся бы с боевым, и
превью показывало бы не то, что видит ученик.

⚠️ Выборка СЛУЧАЙНАЯ, без фильтрации по детекторам. Отбор «по флагам» показал
бы не источник, а мнение детекторов о нём — а оно, по калибровке на 2 401
вердикте, ошибочно в 60% случаев. Seed зафиксирован и печатается в шапке.

Внизу отдельной секцией — задачи, которых коснулся июльский откат свипа
Батча 2: сначала ВСЕ ухудшенные и при этом видимые, затем добор случайными
из остальных откаченных. По ним видно результат нашей собственной правки.

    ./venv/bin/python manage.py matek_sample
    ./venv/bin/python manage.py matek_sample --n 40 --reverted 15 --seed 20260808
"""

import html as html_lib
import json
import os
import random
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client

from problems.management.commands.matek_recon import (
    MATEK_SOURCE_ID, REVERT_BACKUP, field_signals, load_ids)
from problems.models import Problem, ProblemPart

REPORT_DIR = 'reports/matek_recon'
OUT_HTML = os.path.join(REPORT_DIR, 'matek_sample.html')
RECON_JSON = os.path.join(REPORT_DIR, 'recon_data.json')
BATCH2_IDS = 'reports/batch2/changed_problem_ids.txt'

MAIN_RE = re.compile(r'<main class="page-wrap">(.*?)</main>', re.S)
HEAD_RE = re.compile(r'<head>(.*?)</head>', re.S)
TAIL_SCRIPT_RE = re.compile(r'</main>\s*(<script>.*?</script>)\s*</body>', re.S)

# Раскрыть спрятанное и обезвредить навигацию — как в export_review_bundle.
# Кнопки «Показать ответ/решение» прячем: их id повторяются от задачи к задаче,
# и в склеенной странице они всё равно ничего не переключали бы правильно.
OVERRIDES = """
.reveal-content { display: block !important; }
.reveal-btn { display: none !important; }
a { pointer-events: none; cursor: default; }
.rc-wrap { max-width: 900px; margin: 0 auto; padding: 24px 16px 80px; }
.rc-head { border-bottom: 2px solid var(--border); padding-bottom: 16px; margin-bottom: 8px; }
.rc-head h1 { font-size: 24px; margin-bottom: 8px; }
.rc-head p { color: var(--text-dim); font-size: 14px; line-height: 1.6; }
.rc-sec { margin: 40px 0 8px; padding: 12px 16px; background: var(--surface-2);
          border-left: 4px solid var(--accent); border-radius: 6px; }
.rc-sec h2 { font-size: 18px; margin-bottom: 4px; }
.rc-sec p { color: var(--text-dim); font-size: 13px; }
.rc-item { border: 1px solid var(--border); border-radius: 10px;
           background: var(--surface); margin: 20px 0; overflow: hidden; }
.rc-meta { background: var(--surface-2); border-bottom: 1px solid var(--border);
           padding: 8px 14px; font: 12px/1.7 ui-monospace, SFMono-Regular, Menlo, monospace;
           color: var(--text-dim); display: flex; flex-wrap: wrap; gap: 6px 14px; }
.rc-meta b { color: var(--text); font-weight: 600; }
.rc-flag { display: inline-block; padding: 1px 7px; border-radius: 999px;
           background: var(--chip-bg); color: var(--chip-text); font-size: 11px; }
.rc-flag--warn { background: #fde8ef; color: #9d174d; }
[data-theme="dark"] .rc-flag--warn { background: #4a1027; color: #ffb3cf; }
.rc-body { padding: 4px 20px 20px; }
.rc-body .page-wrap, .rc-body main { max-width: none; padding: 0; }
.rc-nav { position: sticky; top: 0; z-index: 5; background: var(--surface);
          border-bottom: 1px solid var(--border); padding: 8px 16px;
          font-size: 13px; display: flex; gap: 16px; }
"""


class Command(BaseCommand):
    help = ('Одна HTML-страница со случайной выборкой видимых задач МатЭк, '
            'отрисованных боевым путём. Только чтение.')

    def add_arguments(self, parser):
        parser.add_argument('--source-id', type=int, default=MATEK_SOURCE_ID)
        parser.add_argument('--n', type=int, default=40)
        parser.add_argument('--reverted', type=int, default=15)
        parser.add_argument('--seed', type=int, default=20260808)

    # ── выбор задач ─────────────────────────────────────────────────────

    def _reverted_ids(self, mine):
        """Задачи МатЭк, полей которых коснулся откат 21 июля."""
        if not os.path.exists(REVERT_BACKUP):
            return set()
        with open(REVERT_BACKUP, encoding='utf-8') as f:
            backup = json.load(f)
        pids = {int(k) for k in backup.get('statement', {})}
        part_pks = [int(k) for k in backup.get('part', {})]
        pids |= set(ProblemPart.objects.filter(pk__in=part_pks)
                    .values_list('problem_id', flat=True))
        return pids & mine

    def handle(self, *args, **opts):
        os.makedirs(REPORT_DIR, exist_ok=True)
        sid, seed = opts['source_id'], opts['seed']
        rnd = random.Random(seed)

        mine = set(Problem.objects.filter(source_references__source_id=sid)
                   .values_list('id', flat=True))
        visible = sorted(Problem.objects.filter(
            pk__in=mine, status='published', needs_quality_review=False)
            .values_list('id', flat=True))
        if not visible:
            raise CommandError('Видимых задач источника нет.')

        sample = sorted(rnd.sample(visible, min(opts['n'], len(visible))))

        reverted = self._reverted_ids(mine)
        damaged = set()
        if os.path.exists(RECON_JSON):
            with open(RECON_JSON, encoding='utf-8') as f:
                damaged = set(json.load(f).get('revert', {}).get('damaged_ids', []))
        vis_set = set(visible)
        # сначала ВСЕ ухудшенные, что видимы, потом добор из остальных
        head = sorted(damaged & vis_set)
        rest = sorted((reverted & vis_set) - set(head))
        need = max(0, opts['reverted'] - len(head))
        rev_sample = head + sorted(rnd.sample(rest, min(need, len(rest))))

        batch2 = load_ids(BATCH2_IDS)
        info = {
            'reverted': reverted, 'damaged': damaged, 'batch2': batch2,
            'damaged_hidden': sorted(damaged - vis_set),
            'reverted_total': len(reverted),
            'reverted_visible': len(reverted & vis_set),
        }

        client = self._client()
        parts = []
        head_html, tail_script = None, ''
        rendered, skipped = 0, []

        blocks_a, blocks_b = [], []
        for ids, bucket in ((sample, blocks_a), (rev_sample, blocks_b)):
            for pid in ids:
                page = self._render(client, pid)
                if page is None:
                    skipped.append(pid)
                    continue
                if head_html is None:
                    head_html = HEAD_RE.search(page).group(1)
                    m = TAIL_SCRIPT_RE.search(page)
                    tail_script = m.group(1) if m else ''
                body = MAIN_RE.search(page)
                if not body:
                    skipped.append(pid)
                    continue
                bucket.append(self._block(pid, body.group(1), info))
                rendered += 1

        if head_html is None:
            raise CommandError('Ни одна страница не отрендерилась.')

        parts.append(self._page_head(head_html))
        parts.append(self._intro(seed, len(sample), len(rev_sample), len(visible),
                                 info, skipped))
        parts.append('<div class="rc-sec"><h2>A. Случайная выборка — {} задач</h2>'
                     '<p>Без всякой фильтрации по детекторам. Seed {}. Это то, '
                     'что увидит ревьюер, если отдать источник как есть.</p></div>'
                     .format(len(blocks_a), seed))
        parts.extend(blocks_a)
        parts.append(
            '<div class="rc-sec"><h2>Б. Задачи, которых коснулся наш откат — {}</h2>'
            '<p>Сначала все {} задачи, где замер признал откат ухудшением И которые '
            'при этом видимы; дальше — случайные из остальных откаченных. '
            'Ещё {} ухудшенных лежат за шлюзом качества или в другом статусе, '
            'ученику они не показываются: {}.</p></div>'.format(
                len(blocks_b), len(head), len(info['damaged_hidden']),
                ', '.join('#{}'.format(i) for i in info['damaged_hidden']) or '—'))
        parts.extend(blocks_b)
        parts.append('</div>' + tail_script + '\n</body>\n</html>\n')

        with open(OUT_HTML, 'w', encoding='utf-8') as f:
            f.write('\n'.join(parts))
        self.stdout.write(self.style.SUCCESS(
            'Отрисовано {} задач (пропущено {}) → {}'.format(
                rendered, len(skipped), OUT_HTML)))

    # ── рендер ──────────────────────────────────────────────────────────

    def _client(self):
        if 'testserver' not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']
        return Client()

    def _render(self, client, pid):
        resp = client.get('/catalog/problem/{}/'.format(pid))
        if resp.status_code != 200:
            return None
        return resp.content.decode('utf-8')

    # ── сборка страницы ─────────────────────────────────────────────────

    def _page_head(self, head_html):
        # <title> достаётся от первой задачи (голова взята с её страницы) —
        # во вкладке это выглядит как случайное имя. Подменяем на своё.
        head_html = re.sub(r'<title>.*?</title>',
                           '<title>МатЭк — визуальная выборка</title>',
                           head_html, count=1, flags=re.S)
        return ('<!doctype html>\n<html lang="ru">\n<head>{}\n<style>{}</style>\n'
                '</head>\n<body>\n<div class="rc-wrap">'
                .format(head_html, OVERRIDES))

    def _intro(self, seed, n_a, n_b, visible, info, skipped):
        note = ''
        if skipped:
            note = ('<br>Не отрисовалось (страница не отдала 200): {}.'
                    .format(', '.join('#{}'.format(i) for i in skipped)))
        return (
            '<div class="rc-head"><h1>МатЭк — визуальная выборка</h1>'
            '<p>Источник «МатЭк — Overleaf архивы (2021–2025)», видимых задач '
            '{visible:,}. Секция A — {a} СЛУЧАЙНЫХ (seed {seed}, без отбора по '
            'детекторам). Секция Б — {b} из {rev} задач, которых коснулся откат '
            '21 июля.<br>Каждая задача отрисована боевой страницей '
            '<code>/catalog/problem/&lt;id&gt;/</code>; ответ и решение раскрыты '
            'принудительно. Служебная строка над задачей — наша, на сайте её нет.'
            '<br><b>Сработавшие детекторы в служебной строке — не приговор.</b> '
            'Калибровка на 2 401 вердикте: 60% идеальных задач получают хотя бы '
            'один флаг. Это метка «сюда смотрела автоматика», а не «тут дефект».'
            '{note}</p></div>'.format(
                visible=visible, a=n_a, b=n_b, seed=seed,
                rev=info['reverted_total'], note=note).replace(',', ' '))

    def _block(self, pid, body, info):
        p = (Problem.objects.prefetch_related('parts', 'topics')
             .only('id', 'statement', 'solution', 'answer', 'difficulty')
             .get(pk=pid))
        sig = set()
        sig |= field_signals(p.statement, is_statement=True)
        for part in p.parts.all():
            sig |= field_signals(part.statement)
        sig |= field_signals(p.solution, is_solution=True)
        sig |= field_signals(p.answer)

        topics = ', '.join(t.name for t in p.topics.all()) or '(без темы)'
        chips = []
        if pid in info['batch2']:
            chips.append('<span class="rc-flag">был в Батче 2</span>')
        if pid in info['reverted']:
            chips.append('<span class="rc-flag">откатывался</span>')
        if pid in info['damaged']:
            chips.append('<span class="rc-flag rc-flag--warn">откат ухудшил</span>')
        det = ('<b>детекторы:</b> ' + ', '.join(sorted(sig))) if sig else \
              '<b>детекторы:</b> тихо'
        meta = (
            '<div class="rc-meta"><span><b>#{pid}</b></span>'
            '<span><b>тема:</b> {topics}</span>'
            '<span><b>решение:</b> {sol}</span>'
            '<span><b>ответ:</b> {ans}</span>'
            '<span><b>подпунктов:</b> {np}</span>'
            '<span>{det}</span>{chips}</div>').format(
                pid=pid, topics=html_lib.escape(topics),
                sol='есть' if (p.solution or '').strip() else 'нет',
                ans='есть' if (p.answer or '').strip() else 'нет',
                np=len(p.parts.all()), det=det, chips=' '.join(chips))
        return ('<div class="rc-item">{meta}<div class="rc-body">{body}</div></div>'
                .format(meta=meta, body=body))
