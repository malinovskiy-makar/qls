"""Экзамен v1: решатель, судья, «Утечка», отчёт и споры. В базу не пишет.

    manage.py ai_exam_v1_run solve   --dir D --label L --provider glm --model glm-5.3 \\
                                     --reasoning low [--pilot | --limit N] --max-usd X --yes
    manage.py ai_exam_v1_run judge   --dir D --label L --provider anthropic \\
                                     --model claude-sonnet-5-5 --max-usd X --yes
    manage.py ai_exam_v1_run judge-batch --dir D --labels L1,L2 --provider anthropic \
                                     --model claude-sonnet-5-5 --max-usd X --yes   # пакетом, −50 %
    manage.py ai_exam_v1_run leak    --dir D --label L --model glm-5.3 --reasoning low \\
                                     [--pressure N] --max-usd X --yes
    manage.py ai_exam_v1_run report  --dir D --labels L1,L2 --judge claude-sonnet-5-5 \\
                                     [--second-judge claude-opus-5-5]
    manage.py ai_exam_v1_run disputes --dir D --labels L1,L2 --judge claude-sonnet-5-5

Без --yes платный поставщик не вызывается: печатается только план.
Сейф — только `--set safe --open-safe "ОТКРЫВАЮ СЕЙФ"`.
"""
import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings

from problems.ai import providers
from problems.ai_exam import v1run


class Command(BaseCommand):
    help = 'Прогон экзамена v1 «Решатель» и «Утечка» (файлы вне репозитория).'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=('solve', 'judge', 'judge-batch', 'leak', 'report', 'disputes'))
        parser.add_argument('--dir', required=True)
        parser.add_argument('--label', default='')
        parser.add_argument('--labels', default='')
        parser.add_argument('--set', default='work', choices=tuple(v1run.SETS))
        parser.add_argument('--open-safe', default='')
        parser.add_argument('--provider', default='glm')
        parser.add_argument('--model', default='')
        parser.add_argument('--reasoning', default='')
        parser.add_argument('--pilot', action='store_true')
        parser.add_argument('--keys-file', default='')
        parser.add_argument('--block', default='')
        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--workers', type=int, default=4)
        parser.add_argument('--max-usd', type=float, default=1.0)
        parser.add_argument('--timeout', type=float, default=0)
        # Claude 5.5 не принимает temperature вовсе (400 «Extra inputs are not
        # permitted») — по умолчанию не передаём; число — для моделей, что умеют.
        parser.add_argument('--temperature', default='none')
        parser.add_argument('--judge', default='')
        parser.add_argument('--second-judge', default='')
        # Прогоны решателей того же семейства, что судья: их оценки — в споры (предвзятость).
        parser.add_argument('--self-judged', default='')
        parser.add_argument('--chat-max-tokens', type=int, default=0)
        parser.add_argument('--leak-tasks', type=int, default=40)
        parser.add_argument('--pressure', type=int, default=0)
        parser.add_argument('--retry-format', action='store_true')
        # Потолок токенов решателя: рассуждение входит в выход, DeepSeek обрезался и на 16 000.
        parser.add_argument('--max-tokens', type=int, default=v1run.SOLVE_MAX_TOKENS)
        parser.add_argument('--yes', action='store_true')

    def handle(self, *args, **o):
        directory = os.path.abspath(o['dir'])
        try:
            rows = v1run.load_rows(directory, o['set'], phrase=o['open_safe'], label=o['label'])
        except v1run.RunRefused as exc:
            raise CommandError(str(exc))
        action = o['action']
        if action in ('report', 'disputes'):
            return self._report(directory, rows, o, action)
        rows = self._select(directory, rows, o)
        provider = providers.get_provider(o['provider'])
        if not o['model']:
            raise CommandError('нужна --model')
        if not o['label']:
            raise CommandError('нужна --label')
        timeout = o['timeout'] or None
        if not o['yes'] and provider.name != 'fake':
            self.stdout.write('ПЛАН: %s, %s %s (рассуждение %s), задач %d, потолок $%.2f. '
                              'Без --yes вызовов нет.' % (action, provider.name, o['model'],
                                                          o['reasoning'] or '—', len(rows),
                                                          o['max_usd']))
            return
        if not provider.is_available():
            raise CommandError('поставщик недоступен: %s' % provider.unavailable_reason())
        write = self._writer()
        if action == 'solve':
            v1run.solve_run(directory, o['label'], rows, provider, o['model'],
                            reasoning=o['reasoning'] or None, workers=o['workers'],
                            max_usd=o['max_usd'], timeout=timeout, write=write,
                            retry_format=o['retry_format'], max_tokens=o['max_tokens'])
        elif action == 'judge-batch':
            temperature = None if o['temperature'] in ('', 'none') else float(o['temperature'])
            keys = set(r['key'] for r in rows) if (o['pilot'] or o['keys_file'] or o['limit']) else None
            labels = [x for x in o['labels'].split(',') if x] or [o['label']]
            try:
                v1run.judge_batch(directory, labels, rows, provider, o['model'],
                                  max_usd=o['max_usd'], temperature=temperature, keys=keys,
                                  write=write)
            except v1run.RunRefused as exc:
                raise CommandError(str(exc))
        elif action == 'judge':
            temperature = None if o['temperature'] in ('', 'none') else float(o['temperature'])
            keys = set(r['key'] for r in rows) if (o['pilot'] or o['keys_file'] or o['limit']) else None
            v1run.judge_run(directory, o['label'], rows, provider, o['model'],
                            workers=o['workers'], max_usd=o['max_usd'], temperature=temperature,
                            timeout=timeout, keys=keys, write=write)
        else:
            self._leak(directory, rows, provider, o, timeout, write)

    def _writer(self):
        def write(text):
            self.stdout.write(text)
            self.stdout.flush()
        return write

    def _select(self, directory, rows, o):
        if o['pilot']:
            path = os.path.join(directory, 'pilot_keys.json')
            if not os.path.exists(path):
                with open(path, 'w', encoding='utf-8') as handle:
                    json.dump(v1run.pilot_keys(rows), handle)
            with open(path, encoding='utf-8') as handle:
                keys = json.load(handle)
            rows = [r for r in rows if r['key'] in set(keys)]
        if o['keys_file']:
            with open(o['keys_file'], encoding='utf-8') as handle:
                keys = set(json.load(handle))
            rows = [r for r in rows if r['key'] in keys]
        if o['block']:
            rows = [r for r in rows if r['block'] == o['block']]
        if o['limit']:
            rows = rows[:o['limit']]
        return rows

    def _leak(self, directory, rows, provider, o, timeout, write):
        """«Утечка»: настройки чата — на время прогона (модель, рассуждение, потолок)."""
        # Набор «Утечки» — свой файл сборки (рабочие B + пул B вне экзамена и сейфа).
        rows = v1run.read_jsonl(os.path.join(directory, 'leak_v1.jsonl'))
        if not rows:
            raise CommandError('нет leak_v1.jsonl — пересоберите ai_exam_v1_build')
        b_rows = [r for r in rows if r['block'] == 'B' and r['leak_asks']]
        jobs, skipped = v1run.leak_jobs(b_rows)
        keep = []
        for job in jobs:
            if job['key'] not in keep:
                keep.append(job['key'])
        chosen = set(keep[:o['leak_tasks']])
        jobs = [j for j in jobs if j['key'] in chosen]
        by_key = {r['key']: r for r in rows}
        path = os.path.join(directory, 'runs', o['label'])
        os.makedirs(path, exist_ok=True)
        out_path = os.path.join(path, 'leak.jsonl')
        done = {(r['key'], r['mode'], r['replica']) for r in v1run.read_jsonl(out_path)
                if not r.get('error')}
        spent = sum(r.get('cost_usd', 0) or 0 for r in v1run.read_jsonl(out_path))
        todo = [j for j in jobs if (j['key'], j['mode'], j['replica']) not in done]
        pressure_keys = sorted(chosen)[:o['pressure']]
        todo_p = [k for k in pressure_keys if (k, 'pressure', 'P1-3') not in done]
        overrides = {'CATALOG_CHAT_MODEL': o['model'], 'CATALOG_CHAT_PROVIDER': provider.name}
        if o['reasoning']:
            overrides['CATALOG_CHAT_REASONING'] = o['reasoning']
        if o['chat_max_tokens']:
            overrides['CATALOG_CHAT_MAX_TOKENS'] = o['chat_max_tokens']
        v1run._dump(os.path.join(path, 'leak_config.json'), dict(
            overrides, tasks=len(chosen), skipped_no_key=skipped, jobs=len(jobs),
            pressure=len(pressure_keys), max_usd=o['max_usd']))
        write('Утечка %s: задач %d (без различимого ключа %d), реплик %d, к отправке %d + '
              'сценариев %d; потрачено ранее $%.4f' % (o['label'], len(chosen), skipped,
                                                      len(jobs), len(todo), len(todo_p), spent))
        with override_settings(**overrides), open(out_path, 'a', encoding='utf-8') as handle:
            def on_record(record):
                handle.write(json.dumps(record, ensure_ascii=False) + '\n')
                handle.flush()
            spent, stopped, n = v1run.run_pool(
                todo, lambda job: v1run.leak_one(job, by_key[job['key']], provider, o['model'],
                                                 timeout),
                workers=o['workers'], max_usd=o['max_usd'], spent=spent, on_record=on_record)
            keys_of = {j['key']: j['keys'] for j in jobs}
            spent, stopped_p, m = v1run.run_pool(
                todo_p, lambda key: v1run.pressure_one(by_key[key], keys_of[key], provider,
                                                       o['model'], timeout),
                workers=o['workers'], max_usd=o['max_usd'], spent=spent, on_record=on_record)
        write('Утечка: отправлено %d реплик + %d сценариев, всего потрачено $%.4f%s'
              % (n, m, spent, ', ОБОРВАН ПО ДЕНЬГАМ' if (stopped or stopped_p) else ''))

    def _report(self, directory, rows, o, action):
        labels = [x for x in o['labels'].split(',') if x]
        runs = {label: v1run.load_run(directory, label, o['judge']) for label in labels}
        if action == 'disputes':
            self_labels = tuple(x for x in o['self_judged'].split(',') if x)
            items = v1run.dispute_items(rows, runs, o['judge'], self_labels=self_labels)
            path = os.path.join(directory, 'disputes_v1.html')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(v1run.disputes_html(rows, items, o['judge']))
            self.stdout.write('споров %d (эталон под сомнением %d, Claude судит Claude %d) → %s' % (
                len(items), sum(1 for i in items if i[0] == 'эталон под сомнением'),
                sum(1 for i in items if i[0] == 'Claude судит Claude'), path))
            return
        out = {}
        for label, (solved, judged) in runs.items():
            out[label] = v1run.summarize(rows, solved, judged)
            if o['second_judge']:
                _s, second = v1run.load_run(directory, label, o['second_judge'])
                out[label]['judges_agreement'] = v1run.agreement(judged, second)
        self.stdout.write(json.dumps(out, ensure_ascii=False, indent=1))
