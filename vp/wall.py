"""Стена 2 тура: пускать ли вошедшего в вариант — ЕДИНСТВЕННОЕ место правила.

Вариант тура из `config.WALL_TOURS` открывается, когда у человека есть
**контакт** (подписка на канал, проверенная ботом, или почта, которую он САМ
выбрал на стене) и **анкета** (три вопроса). Второе место, где решают
«пускать ли», разошлось бы с первым (docs/VP.md, «Стена 2 тура», ADR 0168).

⚠️ ПОДТВЕРЖДЁННАЯ ПОЧТА САМА КОНТАКТОМ НЕ СЧИТАЕТСЯ. После включения почты она
будет у каждого нового ученика, и канал обходился бы без усилия (решение
28.10.2026). Контакт по почте ставит только действие человека в окне стены.

⚠️ КОНТАКТ ПОСТОЯННЫЙ: отписка от канала после прохода стены ничего не отбирает.
"""
from django.conf import settings
from django.utils import timezone

from problems import email_codes
from vp import config, telegram
from vp.models import VPWall

#: Куда вернуть человека после стены: `{'slug': …, 'with_timer': …}`. Данные
#: сессии переживают `login()`, поэтому гость доносит выбор режима до анкеты.
SESSION_NEXT = 'vp_wall_next'


def enabled():
    return bool(getattr(settings, 'VP_WALL_ENABLED', False))


def required(variant):
    """Нужна ли стена для этого варианта."""
    return enabled() and variant.tour in config.WALL_TOURS


def paths():
    """Какие пути контакта сейчас работают."""
    return {'tg': telegram.enabled(), 'email': email_codes.mail_enabled()}


def step(user):
    """'contact' | 'survey' | 'done' — что человеку осталось на стене."""
    wall = VPWall.objects.filter(user=user).only('contact_via', 'survey_at').first()
    if wall is None or not wall.contact_via:
        return 'contact'
    if wall.survey_at is None:
        return 'survey'
    return 'done'


def pass_contact(user, via):
    """Отмечает контакт путём `via` ('tg' / 'email'). Возвращает путь, который остался.

    ⚠️ АТОМАРНО: `UPDATE … WHERE contact_via=''`. Бот и почта могут прийти
    одновременно; первый путь остаётся, второй его не перезаписывает.
    """
    wall, _ = VPWall.objects.get_or_create(user=user)
    VPWall.objects.filter(pk=wall.pk, contact_via='').update(
        contact_via=via, contact_at=timezone.now())
    return VPWall.objects.values_list('contact_via', flat=True).get(pk=wall.pk)


def remember_next(request, slug, with_timer):
    request.session[SESSION_NEXT] = {'slug': slug, 'with_timer': bool(with_timer)}
