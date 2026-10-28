# -*- coding: utf-8 -*-
"""Судья Claude над парами импорта эталона (ночь 28.10.2026, ADR 0163).

    olympiad_text_judge --kind replace --journal <import_…json> [--journal …] --out F.jsonl
    olympiad_text_judge --kind pairs   --journal <import_…_dryrun.json> --out F.jsonl \\
                        --decisions-out decisions.json
    … --max-usd 3 --yes        # без --yes — только план и смета, модель не зовётся
    … --batch [--poll-seconds 300]   # через Message Batches (полцены); докачка по F.batch.json

* `replace` — пары `link` журналов: «официальный текст полнее банка?»;
  вердикты применяет `apply_official_text --verdicts F.jsonl`;
* `pairs` — пары `review` (сомнительные): «то же задание?»; вердикты →
  `link_review_decisions`-файл для `import_olympiad_reference --decisions`;
  «не уверен» остаётся на проверку человеку (`link_review.csv`).

Деньги: `--max-usd` обязателен при `--yes`; на 90 % потолка вызовы
прекращаются. Докачка: ключи, уже записанные в `--out`, не повторяются.
С `--batch` весь остаток уходит одним пакетом: смета обязана уложиться в
90 % потолка (иначе пакет урезается по смете), id пакета — в `F.batch.json`;
повторный запуск после обрыва не шлёт пакет заново, а ждёт тот же.
В базу команда не пишет.
"""
from __future__ import annotations

import json
import os
import time

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
        parser.add_argument('--batch', action='store_true', help='через Message Batches (полцены)')
        parser.add_argument('--poll-seconds', type=int, default=300)

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
        per_pair, per_img = 0.004, 0.0055
        if o['batch']:
            per_pair, per_img = per_pair * tj.BATCH_DISCOUNT, per_img * tj.BATCH_DISCOUNT
        estimate = len(todo) * per_pair + n_img * per_img
        self.stdout.write(f'Пар: {len(pairs)}, уже с вердиктом {len(done)}, к вызову {len(todo)}; '
                          f'картинок страниц {n_img}; смета ≈ ${estimate:.2f} ({o["model"]}'
                          f'{", пакет" if o["batch"] else ""})')
        state_path = o['out'] + '.batch.json'
        if not o['yes'] and not os.path.isfile(state_path):
            self.stdout.write(self.style.WARNING('ПЛАН — модель не вызывалась (нужен --yes и --max-usd).'))
            return self._decisions(o, done)
        if not o['max_usd']:
            raise CommandError('--yes требует --max-usd')
        spent = sum(r.get('usd') or 0 for r in done.values())
        system = tj.REPLACE_SYSTEM if o['kind'] == 'replace' else tj.PAIR_SYSTEM
        if o['batch'] or os.path.isfile(state_path):
            spent = self._run_batch(o, todo, done, spent, system, state_path, per_pair, per_img)
        else:
            spent = self._run_sync(o, todo, done, spent, system)
        self.stdout.write(self.style.SUCCESS(f'Вердиктов: {len(done)}; потрачено ≈ ${spent:.2f}'))
        return self._decisions(o, done)

    def _prepare(self, o, item):
        """(запись вердикта без ответа, содержимое запроса) или None, если задачи нет."""
        key, pid, row, digitized, subdir, slug = item
        problem = Problem.objects.filter(pk=pid).first()
        if problem is None:
            return None
        fields = ri.build_fields(row, digitized_dir=digitized, url_map=ri.UrlMap(),
                                 olympiad_short=registry.short_name(slug))
        images = tj.page_images(row, subdir, digitized)
        content = tj.build_content(tj.official_text(fields, row), tj.bank_text(problem), images)
        rec = {'kind': o['kind'], 'key': key, 'pid': pid, 'olympiad': slug, 'model': o['model'],
               'images': [os.path.basename(i) for i in images],
               'human_approved': tj.human_approved(problem)}
        return rec, content

    def _finish(self, o, rec, text):
        rec['verdict'] = tj.parse_replace(text) if o['kind'] == 'replace' else tj.parse_pair(text)

    def _run_sync(self, o, todo, done, spent, system):
        with open(o['out'], 'a', encoding='utf-8') as out:
            for item in todo:
                if spent >= 0.9 * o['max_usd']:
                    self.stdout.write(self.style.WARNING(f'Потолок: ${spent:.2f} из ${o["max_usd"]} — стоп.'))
                    break
                prepared = self._prepare(o, item)
                if prepared is None:
                    continue
                rec, content = prepared
                try:
                    text, usage = tj.call_model(system, content, model=o['model'])
                    rec['usd'] = tj.cost_of(o['model'], usage)
                    spent += rec['usd']
                    self._finish(o, rec, text)
                except Exception as error:      # noqa: BLE001 — сбой одной пары не роняет прогон
                    rec['error'] = repr(error)[:500]
                out.write(json.dumps(rec, ensure_ascii=False) + '\n')
                out.flush()
                if rec.get('verdict'):
                    done[(rec['key'], rec['pid'])] = rec
        return spent

    def _run_batch(self, o, todo, done, spent, system, state_path, per_pair, per_img):
        """Весь остаток — одним пакетом Message Batches; ждём конца, разбираем по custom_id."""
        if os.path.isfile(state_path):
            with open(state_path, encoding='utf-8') as handle:
                state = json.load(handle)
            self.stdout.write(f'Пакет уже отправлен: {state["batch_id"]} ({len(state["items"])} запросов) — жду его.')
        else:
            room = 0.9 * o['max_usd'] - spent
            requests, items, cost = [], {}, 0.0
            for n, item in enumerate(todo):
                prepared = self._prepare(o, item)
                if prepared is None:
                    continue
                rec, content = prepared
                one = per_pair + per_img * len(rec['images'])
                if cost + one > room:
                    self.stdout.write(self.style.WARNING(
                        f'Смета упёрлась в потолок: в пакет {len(requests)} из {len(todo)} пар.'))
                    break
                cost += one
                cid = f'r{n}'
                requests.append((cid, tj.request_params(system, content, model=o['model'])))
                items[cid] = rec
            if not requests:
                self.stdout.write(self.style.WARNING('Пакет пуст — нечего отправлять.'))
                return spent
            state = {'batch_id': tj.submit_batch(requests), 'kind': o['kind'], 'items': items,
                     'estimate_usd': round(cost, 4), 'submitted_at': tj.stamp()}
            with open(state_path, 'w', encoding='utf-8') as handle:
                json.dump(state, handle, ensure_ascii=False)
            self.stdout.write(f'Пакет {state["batch_id"]}: {len(requests)} запросов, смета ≈ ${cost:.2f}')
        while True:
            status, counts = tj.batch_status(state['batch_id'])
            self.stdout.write(f'{tj.stamp()} пакет {status}: {counts}')
            if status == 'ended':
                break
            time.sleep(o['poll_seconds'])
        results = tj.batch_results(state['batch_id'])
        with open(o['out'], 'a', encoding='utf-8') as out:
            for cid, rec in state['items'].items():
                got = results.get(cid, RuntimeError('нет результата в пакете'))
                rec = dict(rec, batch_id=state['batch_id'])
                if isinstance(got, Exception):
                    rec['error'] = repr(got)[:500]
                else:
                    text, usage = got
                    rec['usd'] = tj.cost_of(o['model'], usage, batch=True)
                    spent += rec['usd']
                    try:
                        self._finish(o, rec, text)
                    except Exception as error:      # noqa: BLE001 — кривой ответ одной пары не роняет разбор
                        rec['error'] = repr(error)[:500]
                out.write(json.dumps(rec, ensure_ascii=False) + '\n')
                if rec.get('verdict'):
                    done[(rec['key'], rec['pid'])] = rec
        os.replace(state_path, state_path[:-len('.json')] + f'_{state["batch_id"]}.done.json')
        return spent

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
