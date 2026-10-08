# -*- coding: utf-8 -*-
"""ai_exam_build — сейф и сборка экзамена ИИ v0 из разметки людей.

ТОЛЬКО ЧТЕНИЕ банка: в базу ни строки, к модели ни одного вызова. Файлы —
в папке экзамена вне репозитория (`--dir`, как у ai_exam_candidates).

    manage.py ai_exam_build --mark-safe
        safe_candidates.json: 40 кандидатов в сейф из пачек 1–3 — ДО любых
        прогонов; существующий файл без --force не перезаписывается
    manage.py ai_exam_build
        reviews_in/*.json → BUILD.md и exam.jsonl + safe.jsonl (финал) или
        exam_draft.jsonl (черновик)

Правила — problems/ai_exam/build.py и docs/AI_EXAM.md, «Сборка и сейф».
"""
import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from problems.ai_exam import build
from problems.ai_exam.loader import load_tasks
from problems.management.commands.ai_exam_candidates import DEFAULT_DIR


def read_candidates(directory):
    path = os.path.join(directory, 'candidates.jsonl')
    if not os.path.exists(path):
        raise CommandError('нет %s — сначала ai_exam_candidates' % path)
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_safe(directory):
    path = os.path.join(directory, 'safe_candidates.json')
    if not os.path.exists(path):
        raise CommandError('нет %s — сначала ai_exam_build --mark-safe' % path)
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def read_reviews(directory):
    """[{'name', 'payload'} | {'name', 'error'}] по reviews_in/*.json."""
    folder = os.path.join(directory, 'reviews_in')
    if not os.path.isdir(folder):
        return []
    files = []
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith('.json'):
            continue
        try:
            with open(os.path.join(folder, name), encoding='utf-8-sig') as handle:
                files.append({'name': name, 'payload': json.load(handle)})
        except (OSError, ValueError) as exc:
            files.append({'name': name, 'error': 'не читается как JSON: %s' % exc})
    return files


class Command(BaseCommand):
    help = 'Сейф и сборка экзамена ИИ v0 из разметки (только чтение банка).'

    def add_arguments(self, parser):
        parser.add_argument('--dir', default=DEFAULT_DIR,
                            help='папка экзамена вне репозитория')
        parser.add_argument('--mark-safe', action='store_true',
                            help='пометить 40 кандидатов в сейф (safe_candidates.json)')
        parser.add_argument('--seed', type=int, default=None,
                            help='зерно сейфа; по умолчанию — seed кандидатов')
        parser.add_argument('--force', action='store_true',
                            help='перезаписать существующий safe_candidates.json')

    def handle(self, *args, **opts):
        directory = opts['dir']
        candidates = read_candidates(directory)
        today = timezone.localdate().isoformat()
        if opts['mark_safe']:
            return self.mark_safe(directory, candidates, opts, today)

        safe_info = read_safe(directory)
        files = read_reviews(directory)
        fresh = {pk: task['hash'] for pk, task in load_tasks([c['id'] for c in candidates]).items()}
        accepted = build.accept(candidates, files, fresh)
        built = build.assemble(candidates, safe_info['ids'], accepted['good'])
        inv = build.invariants(candidates, safe_info['ids'], accepted, built)
        report = build.build_report(candidates, safe_info, accepted, built, inv, today)

        if built['final']:
            self._write(directory, 'exam.jsonl', build.dump_rows(built['work']))
            self._write(directory, 'safe.jsonl', build.dump_rows(built['safe']))
        elif built['draft']:
            self._write(directory, 'exam_draft.jsonl', build.dump_rows(built['draft']))
        self._write(directory, 'BUILD.md', report.encode('utf-8'))

        counts = {cat: list(accepted['status'].values()).count(cat) for cat in build.CATEGORIES}
        self.stdout.write('файлов: прочитано %d, устарели %d, не разметка %d'
                          % (len(accepted['read']), len(accepted['stale']),
                             len(accepted['not_review'])))
        self.stdout.write('задачи: ' + ', '.join('%s %d' % kv for kv in counts.items()))
        if built['final']:
            self.stdout.write(self.style.SUCCESS('ФИНАЛ: рабочий %d, сейф %d'
                                                 % (len(built['work']), len(built['safe']))))
        else:
            self.stdout.write('ЧЕРНОВИК: %d задач (годных в сейфе %d из %d)'
                              % (len(built['draft']), built['safe_good'], build.SAFE_SIZE))
        self.stdout.write('инварианты:')
        for name, value in inv.items():
            self.stdout.write('  %s: %s' % (name, value))
        bad = (inv['сейф ∩ рабочий'] or inv['safe_candidates ∩ черновик']
               or inv['safe_candidates ∩ рабочий'] or inv['повторов id']
               or inv['сумма категорий'] != inv['кандидатов'])
        if bad:
            raise CommandError('инвариант нарушен — см. BUILD.md')
        self.stdout.write('BUILD.md: %s' % os.path.join(directory, 'BUILD.md'))

    def mark_safe(self, directory, candidates, opts, today):
        target = os.path.join(directory, 'safe_candidates.json')
        if os.path.exists(target) and not opts['force']:
            raise CommandError('%s уже есть: сейф помечается один раз. '
                               'Перезаписать — только --force.' % target)
        seed = opts['seed'] if opts['seed'] is not None else candidates[0]['seed']
        info = build.mark_safe(candidates, seed, today)
        self._write(directory, 'safe_candidates.json',
                    (json.dumps(info, ensure_ascii=False, indent=1, sort_keys=True)
                     + '\n').encode('utf-8'))
        self.stdout.write('сейф: %d кандидатов из пачек %s, seed %s'
                          % (info['count'], info['chunks'], seed))
        for section, n in info['by_section'].items():
            self.stdout.write('  %s: %d' % (section, n))
        self.stdout.write('файл: %s' % target)

    def _write(self, directory, name, data):
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, name), 'wb') as handle:
            handle.write(data)
