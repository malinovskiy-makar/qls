"""События аналитики раздела: считает сервер, отправляет браузер через `weco.track`.

⚠️ СВОЕГО ЭНДПОИНТА НЕТ. События уходят в существующий `POST /api/track/` (ADR 0127,
`problems/views_platform.api_track`, `static/track.js`): сервер кладёт список событий в
контекст страницы, `static/vp/js/track.js` отдаёт их `weco.track`. Причина не «так
проще», а данные: балл, число ответов и «сдано само» знает только сервер, а сдача
приходит редиректом — у клиента в момент сдачи их нет.

События (имя: поля):
  vp_landing_open — открыл посадочную;
  vp_intro_open — открыл карточку варианта: variant;
  vp_start — начал НОВУЮ попытку: variant, with_timer (продолжение начатой не в счёт);
  vp_submit — сдал: variant, score, answered, seconds_used, auto — один раз на попытку
              на браузер (первое открытие её результата владельцем);
  vp_result_open — открыл результат: variant, own — каждое открытие;
  vp_share_click, vp_practice_check — шлёт `static/vp/js/result.js` (клик, проверка).
`variant` — слаг варианта. Воронку считает `vp.funnel`.
"""
SESSION_PENDING = 'vp_events'
SESSION_SUBMITTED = 'vp_tracked_submits'
SESSION_LIMIT = 50


def event(name, **props):
    """Одно событие в том виде, в каком его читает `static/vp/js/track.js`."""
    return {'name': name, 'props': props}


def defer(request, name, **props):
    """Откладывает событие до следующей отрисованной страницы этой же сессии.

    Нужно там, где действие кончается редиректом: старт попытки — `POST → 302 →
    страница прохождения`, страницы у самого POST нет.
    """
    pending = request.session.get(SESSION_PENDING, [])
    pending.append(event(name, **props))
    request.session[SESSION_PENDING] = pending[-10:]


def take_deferred(request):
    """Отложенные события этой сессии; после чтения очередь пуста."""
    return request.session.pop(SESSION_PENDING, [])


def first_submit_view(request, code):
    """True при первом открытии результата попытки в этом браузере — тогда шлём `vp_submit`.

    Сдача может случиться и без клиента: время вышло, вкладка закрыта, попытку
    закрыла ленивая автосдача. Поэтому событие привязано не к нажатию «Сдать», а к
    первому показу результата владельцу.
    """
    seen = request.session.get(SESSION_SUBMITTED, [])
    if code in seen:
        return False
    request.session[SESSION_SUBMITTED] = (seen + [code])[-SESSION_LIMIT:]
    return True
