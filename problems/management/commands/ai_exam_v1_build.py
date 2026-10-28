"""Экзамен v1 из официального эталона v6: exam_v1.jsonl, safe_v1.jsonl,
BUILD_V1.md, exam_v1_preview.html — ВНЕ репозитория (ADR 0134, 0149).

    manage.py ai_exam_v1_build --vp <v6.jsonl> --mosh <v6.jsonl> --out <папка>

База не нужна. Сборка детерминированная (seed 20261028): повторный запуск
даёт файлы с тем же sha256 — это проверяется здесь же, второй сборкой.
"""
import collections
import html
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.ai_exam import reference


class Command(BaseCommand):
    help = 'Собрать экзамен v1 «Решатель» из эталона ВП/МОШ v6 (файлы вне репозитория).'

    def add_arguments(self, parser):
        parser.add_argument('--vp', required=True)
        parser.add_argument('--mosh', required=True)
        parser.add_argument('--out', required=True)
        parser.add_argument('--seed', type=int, default=reference.SEED)

    def handle(self, *args, **opts):
        out = os.path.abspath(opts['out'])
        if out.startswith(os.path.abspath(str(settings.BASE_DIR))):
            raise CommandError('экзамен не кладётся в репозиторий: --out вне %s' % settings.BASE_DIR)
        rows = []
        for path in (opts['vp'], opts['mosh']):
            with open(path, encoding='utf-8') as handle:
                rows += [json.loads(line) for line in handle if line.strip()]
        keys = [reference.row_key(r) for r in rows]
        if len(keys) != len(set(keys)):
            raise CommandError('ключ event_id:number:variant в эталоне не уникален')

        work, safe, report = reference.build(rows, seed=opts['seed'])
        again_work, again_safe, _ = reference.build(rows, seed=opts['seed'])
        leak_rows = report.pop('leak')
        report['leak_from_work'] = leak_rows['from_work']
        report['leak_tasks'] = len(leak_rows['rows'])
        texts = {'exam_v1.jsonl': reference.dumps(work), 'safe_v1.jsonl': reference.dumps(safe),
                 'leak_v1.jsonl': reference.dumps(leak_rows['rows'])}
        if (reference.sha256(reference.dumps(again_work)) != reference.sha256(texts['exam_v1.jsonl'])
                or reference.sha256(reference.dumps(again_safe))
                != reference.sha256(texts['safe_v1.jsonl'])):
            raise CommandError('повторная сборка дала другой результат — недетерминированно')
        overlap = {r['key'] for r in work} & {r['key'] for r in safe}
        if overlap:
            raise CommandError('сейф пересекается с рабочим набором: %d' % len(overlap))

        os.makedirs(out, exist_ok=True)
        for name, text in texts.items():
            with open(os.path.join(out, name), 'w', encoding='utf-8', newline='\n') as handle:
                handle.write(text)
        report['sha256'] = {name: reference.sha256(text) for name, text in texts.items()}
        with open(os.path.join(out, 'BUILD_V1.md'), 'w', encoding='utf-8') as handle:
            handle.write(build_md(work, safe, report))
        with open(os.path.join(out, 'exam_v1_preview.html'), 'w', encoding='utf-8') as handle:
            handle.write(preview_html(work))
        self.stdout.write('рабочих %d, сейф %d, пересечений 0; свежих в рабочих %d (%.1f%%)' % (
            len(work), len(safe), sum(r['fresh'] for r in work),
            100.0 * sum(r['fresh'] for r in work) / max(len(work), 1)))
        self.stdout.write('sha256 %s' % json.dumps(report['sha256']))
        self.stdout.write('Папка: %s' % out)


def _table(title, counter):
    lines = ['', '### ' + title, '', '| | рабочие | сейф |', '|---|---|---|']
    for name in sorted(counter):
        lines.append('| %s | %d | %d |' % (name, counter[name][0], counter[name][1]))
    return lines


def build_md(work, safe, report):
    lines = ['# Экзамен «Решатель» v1 — состав сборки', '',
             'Только счётчики. Условия, ключи и id заданий — в jsonl рядом, в git не идут.', '',
             '- рабочих: %d, сейф: %d, всего %d, пересечений 0' % (len(work), len(safe),
                                                                  len(work) + len(safe)),
             '- свежих (2024/25–2025/26): рабочие %d из %d (%.1f%%), сейф %d из %d, всего %.1f%%' % (
                 sum(r['fresh'] for r in work), len(work),
                 100.0 * sum(r['fresh'] for r in work) / max(len(work), 1),
                 sum(r['fresh'] for r in safe), len(safe),
                 100.0 * sum(r['fresh'] for r in work + safe) / max(len(work + safe), 1)),
             '- блок B с критериями: %d из %d' % (
                 sum(1 for r in work + safe if r['block'] == 'B' and r['criteria'].strip()),
                 sum(1 for r in work + safe if r['block'] == 'B')),
             '- ключ A из поля answer / из строк «Ответ:»: %d / %d' % (
                 sum(1 for r in work + safe if r['key_source'] == 'answer'),
                 sum(1 for r in work + safe if r['key_source'] == 'solution')),
             '- строк эталона на входе: %d; пригодно для A: %d (свежих %d), для B: %d (свежих %d, с критериями %d)'
             % (report['rows_in'], report['pool_a'], report['pool_a_fresh'], report['pool_b'],
                report['pool_b_fresh'], report['pool_b_criteria']),
             '- тестовых вопросов, годных на будущее (есть ответ, без рисунка, без needs_eyes, '
             'numbers_ok не false): %d' % report['tests_usable_later'],
             '- набор «Утечка»: %d задач B с различимым числом ответа (%d из рабочих, остальные — '
             'из пула B вне экзамена и сейфа) — leak_v1.jsonl' % (report['leak_tasks'],
                                                                   report['leak_from_work']),
             '- sha256: `%s`' % json.dumps(report['sha256']), '',
             '## Исключено (первая сработавшая причина)', '', '| причина | строк |', '|---|---|']
    lines += ['| %s | %d |' % kv for kv in report['excluded'].items()]
    for title, func in (('Блок', lambda r: r['block']),
                        ('Олимпиада × этап', lambda r: '%s %s' % (r['olympiad'], r['stage'])),
                        ('Класс', lambda r: r['grade']),
                        ('Сезон', lambda r: r['year']),
                        ('Блок × свежесть', lambda r: '%s %s' % (r['block'],
                                                                 'свежая' if r['fresh'] else 'старая'))):
        counter = collections.defaultdict(lambda: [0, 0])
        for r in work:
            counter[func(r)][0] += 1
        for r in safe:
            counter[func(r)][1] += 1
        lines += _table(title, counter)
    return '\n'.join(lines) + '\n'


def preview_html(work):
    """Страница для владельца: условие, ключ или официальное решение, почему взята."""
    def esc(text):
        return html.escape(str(text or ''))
    cards = []
    for n, r in enumerate(work, 1):
        if r['block'] == 'A':
            key = '; '.join('%s%s' % (('%s) ' % a['label']) if a['label'] else '',
                                      ', '.join('%s%s%s' % (('%s = ' % v['label']) if v['label'] else '',
                                                            v['value'], '%' if v['percent'] else '')
                                                for v in a['values'])) for a in r['asks'])
            why = 'блок A: числовой ключ из %s' % ('поля answer' if r['key_source'] == 'answer'
                                                   else 'строки «Ответ:» решения')
            ref = '<p><b>Ключ:</b> %s</p>' % esc(key)
        else:
            why = 'блок B: полное официальное решение%s' % (', есть критерии' if r['criteria'].strip()
                                                         else ', критериев нет — по решению и max_score')
            ref = ('<details><summary>Официальное решение</summary><pre>%s</pre></details>'
                   % esc(r['solution']))
            if r['criteria'].strip():
                ref += '<details><summary>Критерии</summary><pre>%s</pre></details>' % esc(r['criteria'])
        parts = ''.join('<li><b>%s)</b> %s</li>' % (esc(p['label']), esc(p['text'])) for p in r['parts'])
        cards.append(
            '<section><h2>%d. %s · %s %s · %s кл. · %s%s</h2><p class="why">%s; max %s</p>'
            '<pre>%s</pre>%s%s</section>' % (
                n, r['block'], r['olympiad'].upper(), r['stage'], esc(r['grade']), esc(r['year']),
                ' · свежая' if r['fresh'] else '', esc(why), esc(r['max_score']),
                esc(r['statement']), ('<ol>%s</ol>' % parts) if parts else '', ref))
    return ('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Экзамен v1 — предпросмотр</title>'
            '<style>body{font:15px/1.5 system-ui;max-width:960px;margin:2em auto;padding:0 1em}'
            'section{border-top:1px solid #ccc;padding:.5em 0}pre{white-space:pre-wrap;background:#f6f6f4;'
            'padding:.6em}h2{font-size:1.05em}.why{color:#555}</style>'
            '<h1>Экзамен «Решатель» v1 — рабочие %d задач</h1>'
            '<p>Не публиковать: файл вне репозитория.</p>%s</html>' % (len(work), ''.join(cards)))
