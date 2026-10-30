"""Фото решения с телефона по QR-коду (ночь 30.10, Э6).

Компьютер показывает QR со ссылкой `/olympiads/u/<токен>/`; телефон открывает
её без входа и грузит листы ЭТОГО задания той же проверкой файлов, что и
компьютер (`olympiads.uploads.save_sheet`, источник `phone`). Компьютер узнаёт
о новых листах опросом раз в 3 секунды.

⚠️ ТОКЕН — ЕДИНСТВЕННЫЙ ПРОПУСК. Поэтому он живёт 30 минут, ведёт только к
своему заданию своей попытки и гаснет со сдачей попытки (410). Чужой лист по
токену — 404.
"""
import secrets
from datetime import timedelta

from django.utils import timezone

TOKEN_LIFETIME = timedelta(minutes=30)
# Новый токен выдаём заранее, когда старому осталось меньше пяти минут: QR на
# экране не должен «умереть» в руках у ученика посреди съёмки.
REISSUE_BEFORE = timedelta(minutes=5)


def issue(attempt, problem, now=None):
    """Действующий токен задания — прежний или новый."""
    from .models import PhoneUploadToken

    now = now or timezone.now()
    current = (PhoneUploadToken.objects
               .filter(attempt=attempt, problem=problem,
                       expires_at__gt=now + REISSUE_BEFORE)
               .order_by('-expires_at').first())
    if current is not None:
        return current
    return PhoneUploadToken.objects.create(
        attempt=attempt, problem=problem, token=secrets.token_urlsafe(24),
        expires_at=now + TOKEN_LIFETIME)


def state(token, now=None):
    """'ok' — можно грузить; 'gone' — истёк или попытка/задание сданы (410)."""
    from . import training_engine as engine

    now = now or timezone.now()
    attempt = token.attempt
    if token.expires_at <= now:
        return 'gone'
    if attempt.submitted_at is not None or engine.finalize_if_expired(attempt, now):
        return 'gone'
    if not engine.can_accept(attempt, now):
        return 'gone'
    if not attempt.with_timer and \
            token.problem_id in engine.graded_problem_ids(attempt):
        return 'gone'
    return 'ok'


def qr_svg(url):
    """QR-код ссылки готовым SVG — или '' если библиотеки нет (блока не будет)."""
    try:
        import segno
    except ImportError:
        return ''
    import io
    out = io.BytesIO()
    segno.make(url, error='m').save(out, kind='svg', scale=4, border=2,
                                    dark='black', light='white', xmldecl=False,
                                    svgns=True, title='QR-код: фото решения с телефона')
    return out.getvalue().decode('utf-8')
