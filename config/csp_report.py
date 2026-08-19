# -*- coding: utf-8 -*-
"""Приём отчётов браузера о нарушениях Content-Security-Policy.

Политика включена в режиме отчёта (`Content-Security-Policy-Report-Only`),
и смысл этого адреса — собрать настоящий список того, что боевая политика
отрезала бы. Пока список не собран, включать боевой режим значит гадать.

⚠️ **ЭТО ПУБЛИЧНЫЙ АДРЕС, КОТОРЫЙ ПИШЕТ В ЖУРНАЛ.** Браузер шлёт отчёт сам,
без входа и без CSRF-токена, поэтому прислать сюда что угодно может кто
угодно. Отсюда три ограничения, и они не формальность:

1. **Размер тела ограничен.** Иначе журнал забивается за один запрос.
2. **В журнал уходят только четыре поля** из отчёта, каждое обрезано.
   Целиком тело не пишем: браузер кладёт в `script-sample` кусок нашей же
   страницы, а на странице формы это может быть что угодно.
3. **Ответ всегда 204 и всегда пустой.** Никакого эха присланного — иначе
   адрес превращается в удобное зеркало для чужих проделок.
"""
import json
import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger('security.csp')

# Больше восьми килобайт настоящий отчёт не занимает.
MAX_BODY = 8 * 1024

# Что забираем из отчёта. Остальное — шум либо содержимое страницы.
KEEP = ('document-uri', 'violated-directive', 'blocked-uri', 'disposition')


@csrf_exempt
@require_POST
def csp_report(request):
    """Записать нарушение в журнал и ответить пустотой."""
    body = request.body[:MAX_BODY]
    try:
        data = json.loads(body.decode('utf-8'))
        report = data.get('csp-report') or {}
    except (ValueError, UnicodeDecodeError):
        # Мусор в теле — не повод шуметь на уровне ошибки: сюда стучат и
        # сканеры. Но и молчать нельзя, иначе не заметим сломанный формат.
        logger.info('CSP: тело отчёта не разобралось (%d байт)', len(body))
        return HttpResponse(status=204)

    if not isinstance(report, dict):
        return HttpResponse(status=204)

    fields = {key: str(report.get(key, ''))[:300] for key in KEEP}
    if not fields['violated-directive']:
        # Пустой отчёт — не нарушение. Без этой ветки любой желающий шлёт
        # сюда `{}` в цикле и забивает журнал предупреждениями с прочерками.
        logger.info('CSP: отчёт без правила — пропущен')
        return HttpResponse(status=204)
    logger.warning(
        'CSP нарушение: %s заблокировал бы %s (страница %s, режим %s)',
        fields['violated-directive'] or '—',
        fields['blocked-uri'] or '—',
        fields['document-uri'] or '—',
        fields['disposition'] or 'report',
    )
    return HttpResponse(status=204)
