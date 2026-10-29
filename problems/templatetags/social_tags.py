"""`{% social_providers as providers %}` — включённые сервисы входа для кнопок
(`templates/social/_buttons.html`). Пусто, пока флаг выключен или ключей нет."""
from django import template

from problems.social import providers as _providers

register = template.Library()


@register.simple_tag
def social_providers():
    return _providers.enabled()
