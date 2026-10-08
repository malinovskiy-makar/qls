# -*- coding: utf-8 -*-
"""ai_load_probe — зонд «Сайт не встаёт»: K вопросов к ИИ разом и лёгкие страницы.

Запускать ВНУТРИ контейнера web (стенд или бой), адрес — сам gunicorn:

    docker exec <контейнер web> python manage.py ai_load_probe \\
        --base http://127.0.0.1:8000 --host weconomics.ai \\
        --ai 8 --ai-user loadtest_bot --problem 123 --window 30 --baseline-p95 0.2

Что пишет в базу: сессию входа для --ai-user (создаётся без формы входа и
удаляется в конце) и то, что пишет сам чат на каждый вопрос (`ChatTurn`,
`AiUsageLog`). Страницы пишут то же, что при любом просмотре: страница задачи —
событие «opened» (`LearningEvent`), гость — строку сессии (одну на клиента).

Опорный P95 (замер при --ai 0) — --baseline-p95 или --baseline <файл.json
прошлого запуска>. Правила — problems/loadprobe.py и docs/SERVER.md.
"""
import json
from importlib import import_module

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.core.management.base import BaseCommand, CommandError

from problems import loadprobe


def login_session(username):
    """Сессия входа прямо в хранилище сессий — без формы входа и пароля."""
    user = get_user_model().objects.filter(username=username).first()
    if user is None:
        raise CommandError('нет пользователя %r' % username)
    store = import_module(settings.SESSION_ENGINE).SessionStore()
    store[SESSION_KEY] = str(user.pk)
    store[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0] if getattr(
        settings, 'AUTHENTICATION_BACKENDS', None) else 'django.contrib.auth.backends.ModelBackend'
    store[HASH_SESSION_KEY] = user.get_session_auth_hash()
    store.create()
    return store


class Command(BaseCommand):
    help = 'Зонд нагрузки: K вопросов к ИИ разом, ждут ли лёгкие страницы.'

    def add_arguments(self, parser):
        parser.add_argument('--base', default='http://127.0.0.1:8000')
        parser.add_argument('--host', default='weconomics.ai', help='заголовок Host')
        parser.add_argument('--ai', type=int, default=0, help='K вопросов к чату разом')
        parser.add_argument('--ai-user', default='', help='служебный аккаунт для чата')
        parser.add_argument('--problem', type=int, required=True, help='id видимой задачи')
        parser.add_argument('--page-clients', type=int, default=4)
        parser.add_argument('--window', type=float, default=30.0, help='секунд дёргать страницы')
        parser.add_argument('--baseline-p95', type=float, default=None)
        parser.add_argument('--baseline', default='', help='файл прошлого запуска с K=0')
        parser.add_argument('--label', default='')
        parser.add_argument('--out', default='', help='записать итог в JSON')

    def handle(self, *args, **opts):
        k = opts['ai']
        baseline = opts['baseline_p95']
        if baseline is None and opts['baseline']:
            with open(opts['baseline'], encoding='utf-8') as handle:
                baseline = json.load(handle)['summary']['pages']['p95']
        session = None
        cookies = {}
        if k:
            if not opts['ai_user']:
                raise CommandError('для --ai > 0 нужен --ai-user')
            session = login_session(opts['ai_user'])
            cookies = {settings.SESSION_COOKIE_NAME: session.session_key}
        target = loadprobe.Target(opts['base'], opts['host'])
        try:
            pages, ai = loadprobe.run(target, k=k, problem_id=opts['problem'],
                                      session_cookies=cookies,
                                      page_clients=opts['page_clients'], window=opts['window'])
        except RuntimeError as exc:
            raise CommandError(str(exc))
        finally:
            if session is not None:
                session.delete()
        summary = loadprobe.summarize(pages, ai)
        if baseline is None and k == 0:
            baseline = summary['pages']['p95']
        result, reasons = loadprobe.verdict(summary, k, baseline)
        p, a = summary['pages'], summary['ai']
        self.stdout.write('%s K=%d | лёгкие: %d запр., ошибок %d, P50 %.2f / P95 %.2f / макс %.2f с'
                          ' | ИИ: OK %d из %d, P50 %.1f / макс %.1f с | опора P95 %s | %s%s'
                          % (opts['label'] or '-', k, p['requests'], p['errors'], p['p50'],
                             p['p95'], p['max'], a['ok'], k, a['p50'], a['max'],
                             '—' if baseline is None else '%.2f' % baseline, result,
                             (' (' + '; '.join(reasons) + ')') if reasons else ''))
        errors = sorted({r['error'] for r in ai if r['error']})
        if errors:
            self.stdout.write('ошибки ИИ: %s' % ', '.join(errors))
        if opts['out']:
            with open(opts['out'], 'w', encoding='utf-8') as handle:
                json.dump({'label': opts['label'], 'k': k, 'window': opts['window'],
                           'page_clients': opts['page_clients'], 'baseline_p95': baseline,
                           'verdict': result, 'reasons': reasons, 'summary': summary,
                           'pages': pages, 'ai': ai}, handle, ensure_ascii=False, indent=1)
