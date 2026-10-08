# -*- coding: utf-8 -*-
"""ai_exam_report — отчёт по прогону экзамена и сравнение «было → стало».

    manage.py ai_exam_report <папка прогона>
        REPORT.md в папке прогона
    manage.py ai_exam_report <папка нового прогона> --vs <папка прежнего>
        ещё compare_<прежний>_vs_<новый>.md рядом с новым (в runs/);
        прогоны на разных наборах не сравниваются

Только чтение файлов прогона. Правила — docs/AI_EXAM.md, «Отчёт».
"""
from django.core.management.base import BaseCommand, CommandError

from problems.ai_exam import report


class Command(BaseCommand):
    help = 'Отчёт по прогону экзамена ИИ; с --vs — сравнение двух прогонов.'

    def add_arguments(self, parser):
        parser.add_argument('run_dir', help='папка прогона (новый, «стало»)')
        parser.add_argument('--vs', default=None, help='папка прежнего прогона («было»)')

    def handle(self, *args, **opts):
        try:
            target, summary = report.write_report(opts['run_dir'])
        except FileNotFoundError as exc:
            raise CommandError('не папка прогона: %s' % exc)
        self.stdout.write('REPORT.md: %s' % target)
        if 'solve' in summary:
            s = summary['solve']
            self.stdout.write('Решатель: %d/%d, сбоев формата %d'
                              % (s['tasks']['k'], s['tasks']['n'], s['format_errors']))
        if 'leak' in summary:
            for name, pair in summary['leak']['by_condition'].items():
                self.stdout.write('Утечка %s: %d/%d' % (name, pair['k'], pair['n']))
        m = summary['money']
        self.stdout.write('$%.4f всего, $%.5f на вызов; секунды медиана %s, P90 %s, макс %s'
                          % (m['usd'], m['usd_per_call'], m['seconds_median'],
                             m['seconds_p90'], m['seconds_max']))
        if opts['vs']:
            try:
                target = report.write_compare(opts['vs'], opts['run_dir'])
            except report.CompareRefused as exc:
                raise CommandError(str(exc))
            self.stdout.write('сравнение: %s' % target)
