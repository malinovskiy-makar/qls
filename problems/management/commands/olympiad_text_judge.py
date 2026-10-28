# -*- coding: utf-8 -*-
"""Судья Claude над парами импорта эталона (ночь 28.10.2026, ADR 0163).

    olympiad_text_judge --kind replace --journal <import_…json> [--journal …] --out F.jsonl
    olympiad_text_judge --kind pairs   --journal <import_…_dryrun.json> --out F.jsonl \\
                        --decisions-out decisions.json
    … --max-usd 3 --yes        # без --yes — только план и смета, модель не зовётся

* `replace` — пары `link` журналов: «официальный текст полнее банка?»;
  вердикты применяет `apply_official_text --verdicts F.jsonl`;
* `pairs` — пары `review` (сомнительные): «то же задание?»; вердикты →
  `link_review_decisions`-файл для `import_olympiad_reference --decisions`;
  «не уверен» остаётся на проверку человеку (`link_review.csv`).

Деньги: `--max-usd` обязателен при `--yes`; на 90 % потолка вызовы
прекращаются. Докачка: ключи, уже записанные в `--out`, не повторяются.
В базу команда не пишет.
"""
from __future__ import annotations

import json
import os

from django.core.management.base import BaseCommand, CommandError

from problems.models import Problem
from problems.olympiad_audit import reference_import as ri
from problems.olympiad_audit import registry
from problems.olympiad_audit import text_judge as tj
from problems.olympiad_official import read_jsonl


def pairs_from_journal(path, kind):
    """[(ключ, id задачи, строка эталона, папка эталона, подпапка, слаг)]."""
    with open(path, encoding='utf-8') as handle:
        journal = json.load(handle)
    inputs = journal['inputs']
    rows = {f'{r["event_id"]}:{r["number"]}' + (f':{r["task_variant"]}' if r.get('task_variant') else ''): r
            for r in read_jsonl(inputs['queue'])}
    digitized = inputs['digitized']
    subdir = os.path.dirname(digitized) if os.path.basename(digitized) == 'digitized' \
        else os.path.dirname(inputs['queue'])
    want = 'link' if kind == 'replace' else 'review'
    out = []
    for item in journal['plan']:
        reason = item.get('reason') or ''
        # Комплект одной задачей: в задаче банка — весь комплект, официальное
        # задание — его кусок; заменять комплект одним заданием нельзя.
        if item['action'] == want and item.get('pid') and item['key'] in rows \
                and 'kit_numbers' not in reason and 'комплект' not in reason:
            out.append((item['key'], int(item['pid']), rows[item['key']], digitized, subdir,
                        journal['olympiad']))
    return out


class Command(BaseCommand):
    help = 'Судья Claude: замена текста банка официальным / сомнительные пары. В базу не пишет.'

    def add_arguments(self, parser):
        parser.add_argument('--kind', choices=('replace', 'pairs'), required=True)
        parser.add_argument('--journal', action='append', default=[], required=True)
        parser.add_argument('--out', required=True, help='JSONL вердиктов (дописывается)')
        parser.add_argument('--decisions-out', help='для --kind pairs: файл разметки')
        parser.add_argument('--model', default=tj.MODEL)
        parser.add_argument('--max-usd', type=float)
        parser.add_argument('--limit', type=int)
        parser.add_argument('--yes', action='store_true', help='звать модель (деньги)')

    def handle(self, *args, **o):
        pairs = []
        for path in o['journal']:
            pairs.extend(pairs_from_journal(path, o['kind']))
        done = {}
        if os.path.isfile(o['out']):
            for line in open(o['out'], encoding='utf-8'):
                if line.strip():
                    rec = json.loads(line)
                    if rec.get('verdict'):
                        done[(rec['key'], rec['pid'])] = rec
        todo = [p for p in pairs if (p[0], p[1]) not in done]
        if o['limit']:
            todo = todo[:o['limit']]
        n_img = sum(len(tj.page_images(p[2], p[4], p[3])) for p in todo)
        estimate = len(todo) * 0.004 + n_img * 0.0055
        self.stdout.write(f'Пар: {len(pairs)}, уже с вердиктом {len(done)}, к вызову {len(todo)}; '
                          f'картинок страниц {n_img}; смета ≈ ${estimate:.2f} ({o["model"]})')
        if not o['yes']:
            self.stdout.write(self.style.WARNING('ПЛАН — модель не вызывалась (нужен --yes и --max-usd).'))
            return self._decisions(o, done)
        if not o['max_usd']:
            raise CommandError('--yes требует --max-usd')
        spent = sum(r.get('usd') or 0 for r in done.values())
        system = tj.REPLACE_SYSTEM if o['kind'] == 'replace' else tj.PAIR_SYSTEM
        with open(o['out'], 'a', encoding='utf-8') as out:
            for key, pid, row, digitized, subdir, slug in todo:
                if spent >= 0.9 * o['max_usd']:
                    self.stdout.write(self.style.WARNING(f'Потолок: ${spent:.2f} из ${o["max_usd"]} — стоп.'))
                    break
                problem = Problem.objects.filter(pk=pid).first()
                if problem is None:
                    continue
                fields = ri.build_fields(row, digitized_dir=digitized, url_map=ri.UrlMap(),
                                         olympiad_short=registry.short_name(slug))
                images = tj.page_images(row, subdir, digitized)
                content = tj.build_content(tj.official_text(fields, row), tj.bank_text(problem), images)
                rec = {'kind': o['kind'], 'key': key, 'pid': pid, 'olympiad': slug, 'model': o['model'],
                       'images': [os.path.basename(i) for i in images],
                       'human_approved': tj.human_approved(problem)}
                try:
                    text, usage = tj.call_model(system, content, model=o['model'])
                    rec['usd'] = tj.cost_of(o['model'], usage)
                    spent += rec['usd']
                    rec['verdict'] = (tj.parse_replace(text) if o['kind'] == 'replace'
                                      else tj.parse_pair(text))
                except Exception as error:      # noqa: BLE001 — сбой одной пары не роняет прогон
                    rec['error'] = repr(error)[:500]
                out.write(json.dumps(rec, ensure_ascii=False) + '\n')
                out.flush()
                if rec.get('verdict'):
                    done[(key, pid)] = rec
        self.stdout.write(self.style.SUCCESS(f'Вердиктов: {len(done)}; потрачено ≈ ${spent:.2f}'))
        return self._decisions(o, done)

    def _decisions(self, o, done):
        if o['kind'] != 'pairs' or not o.get('decisions_out'):
            return
        rows = []
        for (key, pid), rec in sorted(done.items()):
            decision = tj.pair_decision(rec['verdict'])
            rows.append({'key': key, 'bank_id': pid, 'decision': decision,
                         'decided_by': f'claude:{rec["model"]}', 'reason': rec['verdict']['reasons'],
                         'evidence': rec['verdict']['evidence'],
                         'confidence': rec['verdict']['confidence']})
        with open(o['decisions_out'], 'w', encoding='utf-8') as handle:
            json.dump({'rows': rows, 'decided': sum(1 for r in rows if r['decision'] != 'unsure')},
                      handle, ensure_ascii=False, indent=1)
        self.stdout.write(f'Разметка: {o["decisions_out"]} ({len(rows)} строк)')
