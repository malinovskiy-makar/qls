"""Перенос гостевых попыток на аккаунт при входе.

Гость прошёл вариант, увидел результат, завёл аккаунт — попытка переезжает к нему,
иначе предложение «сохранить прогресс» врало бы.

⚠️ ПО КОДАМ ИЗ СЕССИИ, А НЕ ПО `session_key`. `login()` зовёт `cycle_key()` ДО сигнала:
ключ сессии к этому моменту уже новый, а в попытке записан старый, так что сравнение с
«текущим» не нашло бы ничего. Данные сессии при смене ключа переезжают целыми — в них
лежат коды попыток гостя (`views.SESSION_ATTEMPTS`), и это то же самое право, по
которому `views._owns` пускает гостя к его попытке: код туда кладёт только `start`.
"""
import logging

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from vp.models import VPAttempt

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def adopt_guest_attempts(sender, request, user, **kwargs):
    from vp.views import SESSION_ATTEMPTS
    session = getattr(request, 'session', None)
    codes = list(session.get(SESSION_ATTEMPTS, [])) if session is not None else []
    if not codes:
        return
    try:
        VPAttempt.objects.filter(public_code__in=codes, user__isnull=True).update(user=user)
    except Exception:
        # Вход не должен падать из-за тренажёра: попытка останется гостевой.
        logger.exception('Не удалось перенести гостевые попытки ВП на пользователя %s', user.pk)
