# -*- coding: utf-8 -*-
"""Фаза 3: заголовки, политика в режиме отчёта и страницы ошибок.

Три вещи, которые проверяются здесь.

**Заголовки.** `Permissions-Policy` и `Content-Security-Policy-Report-Only`
Django своими настройками не задаёт — их ставит
`config/security_headers.py`. Тест держит их на месте: заголовок, который
однажды исчез, никто не заметит глазами.

**Страницы ошибок.** 400 / 403 / 404 / 500 обязаны выглядеть как сайт и НЕ
рассказывать ничего: ни трассировки, ни имени настроек, ни SQL, ни имени
пользователя базы. Страница 500 проверяется по-настоящему — через
обработчик Django на упавшем представлении, а не чтением файла шаблона.

**GET ничего не меняет.** Обход маршрутов из `docs/SECURITY-MATRIX.md`:
всё, что пишет в базу, обязано требовать POST.
"""
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import Client, TestCase, override_settings
from django.urls import path, reverse

from config.security_headers import CSP_REPORT_PATH
from problems.models import Problem

User = get_user_model()

PASSWORD = 'proverka12345'

# Слова, которых на странице ошибки быть не может ни при каких условиях.
FORBIDDEN_ON_ERROR_PAGE = (
    'Traceback',
    'DJANGO_SETTINGS_MODULE',
    'SELECT ',
    'settings.py',
    'Exception Value',
    'Request Method',
    'django.db',
)


# ── Отдельный набор адресов, чтобы получить настоящую пятисотку ─────────
def _boom(request):
    """Представление, которое падает, — иначе 500 не воспроизвести."""
    raise RuntimeError('нарочно сломано: SELECT * FROM problems_problem')


def _fine(request):
    return HttpResponse('ok')


urlpatterns = [
    path('boom/', _boom),
    path('fine/', _fine),
]


class SecurityHeadersTests(TestCase):
    """Заголовки стоят на каждом ответе, включая страницы ошибок."""

    def test_permissions_policy_is_strict(self):
        response = Client().get('/')
        header = response.headers.get('Permissions-Policy', '')
        self.assertTrue(header, 'Permissions-Policy не выставлен')
        for feature in ('camera', 'microphone', 'geolocation', 'payment', 'usb'):
            self.assertIn(
                feature + '=()', header,
                'Возможность «%s» не запрещена явно' % feature)

    def test_csp_is_report_only_and_not_enforcing(self):
        """Политика идёт в режиме отчёта: боевой сегодня сломал бы сайт."""
        response = Client().get('/')
        self.assertIn('Content-Security-Policy-Report-Only', response.headers)
        self.assertNotIn(
            'Content-Security-Policy', response.headers,
            'Боевая политика включилась сама — часть библиотек ещё едет с CDN, '
            'перевод в боевой режим делается отдельной работой.')

    def test_csp_names_the_key_directives(self):
        policy = Client().get('/').headers['Content-Security-Policy-Report-Only']
        for directive in ("default-src 'self'", "object-src 'none'",
                          "frame-ancestors 'none'", "base-uri 'self'",
                          "form-action 'self'", 'report-uri'):
            self.assertIn(directive, policy,
                          'В политике нет «%s»' % directive)

    def test_report_endpoint_itself_has_no_policy(self):
        """Иначе нарушение на странице отчёта породит отчёт о ней самой."""
        response = Client().post(CSP_REPORT_PATH, data='{}',
                                 content_type='application/csp-report')
        self.assertNotIn('Content-Security-Policy-Report-Only',
                         response.headers)


class CspReportEndpointTests(TestCase):
    """Приём отчётов: работает без входа, но ничего не отражает обратно."""

    def test_valid_report_is_accepted_and_logged(self):
        payload = ('{"csp-report": {"document-uri": "https://site/x",'
                   ' "violated-directive": "script-src",'
                   ' "blocked-uri": "https://evil.example/a.js"}}')
        with self.assertLogs('security.csp', level='WARNING') as logs:
            response = Client().post(CSP_REPORT_PATH, data=payload,
                                     content_type='application/csp-report')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b'')
        self.assertIn('evil.example', '\n'.join(logs.output))

    def test_garbage_body_does_not_raise(self):
        with self.assertLogs('security.csp', level='INFO'):
            response = Client().post(CSP_REPORT_PATH, data='не json',
                                     content_type='application/csp-report')
        self.assertEqual(response.status_code, 204)

    def test_get_is_not_allowed(self):
        self.assertEqual(Client().get(CSP_REPORT_PATH).status_code, 405)

    def test_body_is_capped(self):
        """Гигантское тело не должно уехать в журнал целиком."""
        huge = '{"csp-report": {"blocked-uri": "' + 'A' * 200000 + '"}}'
        with self.assertLogs('security.csp', level='INFO') as logs:
            response = Client().post(CSP_REPORT_PATH, data=huge,
                                     content_type='application/csp-report')
        self.assertEqual(response.status_code, 204)
        self.assertLess(len('\n'.join(logs.output)), 5000,
                        'В журнал уехало тело целиком')


@override_settings(ROOT_URLCONF=__name__)
class ErrorPagesTests(TestCase):
    """Страницы ошибок: выглядят как сайт и ничего не рассказывают."""

    def _assert_silent(self, body, where):
        for word in FORBIDDEN_ON_ERROR_PAGE:
            self.assertNotIn(
                word, body,
                '%s: на странице ошибки слово «%s» — это подсказка тому, '
                'кто ищет дыру.' % (where, word))

    def test_500_page(self):
        client = Client(raise_request_exception=False)
        response = client.get('/boom/')
        self.assertEqual(response.status_code, 500)
        body = response.content.decode('utf-8', 'replace')
        self._assert_silent(body, '500')
        # Своя разметка, а не голый текст Django.
        self.assertIn('Мы это уже чиним', body)
        # Текст самого исключения тоже не должен доехать.
        self.assertNotIn('нарочно сломано', body)
        self.assertNotIn('problems_problem', body)

    def test_500_writes_the_real_cause_to_the_log(self):
        """Наружу — человеческий текст, в журнал — настоящая ошибка."""
        client = Client(raise_request_exception=False)
        with self.assertLogs('django.request', level='ERROR') as logs:
            client.get('/boom/')
        self.assertIn('нарочно сломано', '\n'.join(logs.output))

    def test_404_page(self):
        response = Client().get('/такой-страницы-нет/')
        self.assertEqual(response.status_code, 404)
        body = response.content.decode('utf-8', 'replace')
        self._assert_silent(body, '404')
        self.assertIn('Такой страницы нет', body)

    def test_error_pages_render_for_anyone(self):
        """404 не должна звать в панель репетитора: её видит и гость."""
        body = Client().get('/нет-такой/').content.decode('utf-8', 'replace')
        self.assertNotIn('/teacher/', body,
                         'Страница 404 уводит в панель репетитора — '
                         'её открывают и ученик, и гость.')


class GetDoesNotChangeStateTests(TestCase):
    """Обход маршрутов из карты: GET ничего не пишет."""

    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user('get_pupil', password=PASSWORD,
                                               role='student')
        cls.problem = Problem.objects.create(
            statement='Условие', status=Problem.Status.PUBLISHED)

    def test_json_endpoints_refuse_get(self):
        client = Client()
        self.assertTrue(client.login(username='get_pupil', password=PASSWORD))
        # Все эти адреса что-то создают, двигают или удаляют.
        for name in ('api_save_problem', 'api_folder_create',
                     'api_folder_rename', 'api_saved_move',
                     'api_saved_delete', 'api_graph_save'):
            with self.subTest(name=name):
                response = client.get(reverse(name))
                self.assertIn(
                    response.status_code, (405, 400),
                    'GET на %s не отвергнут: адрес, меняющий данные, обязан '
                    'требовать POST — иначе его дёрнет любая картинка на '
                    'чужой странице.' % name)

    def test_get_on_save_creates_nothing(self):
        from problems.models_platform import SavedProblem
        client = Client()
        client.login(username='get_pupil', password=PASSWORD)
        before = SavedProblem.objects.count()
        client.get(reverse('api_save_problem') + '?catalog_id=%s'
                   % self.problem.pk)
        self.assertEqual(SavedProblem.objects.count(), before,
                         'GET создал запись — значит, метод не проверяется')
