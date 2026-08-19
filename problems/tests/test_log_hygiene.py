# -*- coding: utf-8 -*-
"""Фаза 5: что попадает в журналы сервера.

**Правило проекта.** В журнал ЗАПРЕЩЕНО писать: пароли, куки, CSRF-токены,
токены приглашений и публичные токены подборок, коды ссылок на результат
игры, полные запросы к модели и решения учеников, адрес почты в составе
URL, содержимое загруженных файлов.

**И обратное правило, не менее важное.** Если наружу отдаётся человеческий
текст вместо ошибки, в журнал обязана уйти НАСТОЯЩАЯ причина. Иначе мягкое
сообщение — это не забота о человеке, а потеря диагностики:
`problems/ai/providers.log_cause` появился ровно после такого случая.

Проверяется двумя способами, и они дополняют друг друга:

* **разбором исходников** — ни один вызов журнала не получает переменную с
  запретным именем. Это ловит завтрашнюю строчку, а не сегодняшнюю;
* **прогоном по-настоящему** — открываем страницы, где токен и код есть, и
  смотрим, что записалось.
"""
import ast
import logging
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from problems.models import Collection, Problem

User = get_user_model()

APPS = ('problems', 'catalog', 'teacher', 'student', 'game', 'calc2',
        'calendar_stub', 'config')

# Имена, которых не должно быть среди аргументов записи в журнал.
# Проверяется ИМЯ переменной или атрибута, а не значение: значение в
# статике не узнать, а имя — единственная зацепка, которая переживает
# правки.
FORBIDDEN_NAMES = {
    'password', 'passwd', 'raw_password', 'new_password1', 'new_password2',
    'token', 'csrf_token', 'csrftoken', 'api_key', 'secret', 'secret_key',
    'prompt', 'full_prompt', 'system_prompt', 'messages',
    'solution_text', 'submitted_answer', 'answer_override',
    'cookies', 'session_key',
}

LOG_METHODS = {'debug', 'info', 'warning', 'error', 'exception', 'critical',
               'log'}


def _iter_project_sources():
    for app in APPS:
        root = Path(settings.BASE_DIR) / app
        if not root.exists():
            continue
        for path in root.rglob('*.py'):
            posix = path.as_posix()
            if '/migrations/' in posix or '/tests/' in posix:
                continue
            if path.name.startswith('test_'):
                continue
            yield path


def _names_in(node):
    """Все имена и имена атрибутов внутри выражения."""
    found = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            found.add(sub.id.lower())
        elif isinstance(sub, ast.Attribute):
            found.add(sub.attr.lower())
    return found


class LoggingCallsAreCleanTests(TestCase):
    """Ни одна запись в журнал не получает запретную переменную."""

    def test_no_forbidden_names_reach_the_log(self):
        offenders = []
        for path in _iter_project_sources():
            try:
                tree = ast.parse(path.read_text(encoding='utf-8'))
            except SyntaxError:            # чужой или сломанный файл
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (isinstance(func, ast.Attribute)
                        and func.attr in LOG_METHODS):
                    continue
                # `logger.warning(...)` / `logging.getLogger(..).info(...)`
                base = _names_in(func.value)
                if not ({'logger', 'logging', 'log'} & base):
                    continue
                for arg in list(node.args) + [kw.value for kw in node.keywords]:
                    bad = FORBIDDEN_NAMES & _names_in(arg)
                    if bad:
                        offenders.append('%s:%d — %s' % (
                            path.relative_to(settings.BASE_DIR),
                            node.lineno, ', '.join(sorted(bad))))
        self.assertEqual(
            offenders, [],
            'В журнал уходит запретное. Записывать надо КЛАСС и СМЫСЛ '
            'ошибки, а не сам секрет:\n' + '\n'.join(offenders))

    def test_the_detector_notices_a_planted_call(self):
        """Контроль: сам разбор рабочий.

        Без этого первый тест был бы зелёным и на сломанном детекторе — то
        есть не проверял бы ничего.
        """
        tree = ast.parse('logger.warning("вход %s", password)\n')
        call = tree.body[0].value
        self.assertTrue(FORBIDDEN_NAMES & _names_in(call.args[1]))


class TokensDoNotReachTheLogTests(TestCase):
    """Прогон по-настоящему: токен подборки и код игры не записываются."""

    @classmethod
    def setUpTestData(cls):
        cls.problem = Problem.objects.create(
            statement='Условие', status=Problem.Status.PUBLISHED)
        cls.collection = Collection.objects.create(name='Моя подборка')
        cls.collection.problems.add(cls.problem)

    def _capture(self, func):
        """Собрать ВСЕ записи всех журналов за время вызова."""
        records = []

        class Catcher(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = Catcher()
        root = logging.getLogger()
        root.addHandler(handler)
        previous = root.level
        root.setLevel(logging.DEBUG)
        try:
            func()
        finally:
            root.removeHandler(handler)
            root.setLevel(previous)
        return '\n'.join(
            '%s %s' % (r.name, r.getMessage()) for r in records)

    def test_collection_token_is_not_logged(self):
        token = self.collection.token
        self.assertTrue(token, 'У подборки нет токена — проверять нечего')
        url = reverse('catalog:collection_detail', args=[token])

        written = self._capture(lambda: Client().get(url))
        self.assertNotIn(
            token, written,
            'Токен подборки уехал в журнал целиком. Знание строки = доступ '
            'к подборке, а журналы читают и хранят дольше, чем страницы.')

    def test_game_result_code_is_not_logged(self):
        from game.models import GameResult

        result = GameResult.objects.create(score=10, mode='blitz')
        url = reverse('game:result', args=[result.code])

        written = self._capture(lambda: Client().get(url))
        self.assertNotIn(result.code, written,
                         'Код ссылки на результат игры уехал в журнал')


class AiUsageLogStoresMetricsOnlyTests(TestCase):
    """В расходной записи модели — метрики, а не переписка."""

    def test_no_prompt_or_answer_fields(self):
        from problems.models_platform import AiUsageLog

        names = {f.name for f in AiUsageLog._meta.get_fields()}
        for forbidden in ('prompt', 'request_text', 'response', 'answer',
                          'completion', 'messages'):
            self.assertNotIn(
                forbidden, names,
                'В AiUsageLog появилось поле «%s». Полный запрос и ответ '
                'хранятся только при явной необходимости и с коротким '
                'сроком — это отдельное решение владельца.' % forbidden)

    def test_it_does_store_the_metrics_we_need(self):
        """Контроль: нужное на месте, иначе первый тест — запрет всего."""
        from problems.models_platform import AiUsageLog

        names = {f.name for f in AiUsageLog._meta.get_fields()}
        for needed in ('model_name', 'input_tokens', 'output_tokens',
                       'cost_usd', 'seconds', 'ok', 'cache_read_tokens'):
            self.assertIn(needed, names)


class SoftErrorsKeepTheRealCauseTests(TestCase):
    """Мягкое сообщение наружу — настоящая причина в журнале."""

    def test_log_cause_writes_the_class_and_the_traceback(self):
        from problems.ai import providers

        # ⚠️ Звать log_cause НАДО ИЗ БЛОКА except. `exc_info=True` берёт
        # ТЕКУЩЕЕ исключение; вне обработчика брать нечего, и в записи
        # окажется «NoneType: None» — то есть тест проверял бы не то.
        with self.assertLogs('problems.ai.providers', level='WARNING') as logs:
            try:
                raise ValueError('настоящая причина отказа')
            except ValueError as error:
                providers.log_cause(error)
        written = '\n'.join(logs.output)
        self.assertIn('ValueError', written)
        self.assertIn('настоящая причина отказа', written)
        self.assertIn('Traceback', written,
                      'log_cause потерял exc_info — по такой записи причину '
                      'не найти')

    def test_every_soft_ai_error_is_logged_with_exc_info(self):
        """Там, где ProviderError превращается в текст для человека.

        Разбор исходников: рядом с показом мягкого сообщения обязан стоять
        вызов журнала с `exc_info=True` или `logger.exception`.
        """
        checked = 0
        for path in (Path(settings.BASE_DIR) / 'teacher' / 'views_generate.py',
                     Path(settings.BASE_DIR) / 'problems' / 'ai' / 'core.py'):
            text = path.read_text(encoding='utf-8')
            if 'ProviderError' not in text and '_human_error' not in text:
                continue
            checked += 1
            self.assertTrue(
                'exc_info=True' in text or 'logger.exception' in text,
                '%s показывает человеческий текст об ошибке, но настоящую '
                'причину в журнал не пишет.' % path.name)
        self.assertGreater(checked, 0, 'Проверять оказалось нечего')
