"""Какие варианты видны в разделе — ЕДИНСТВЕННОЕ правило (решение владельца 24.10.2026).

Видны опубликованные варианты туров из `config.VISIBLE_TOURS`. Все экраны и карта сайта
спрашивают здесь: посадочная, экран вариантов, таблица лучших попыток, sitemap, интро и
старт. Скрытый тур не удалён: попытки, ответы и разборы `/vp/r/<код>/` живут как
раньше, начатая попытка доступна владельцу по коду до сдачи (доступ к попытке —
`views._get_attempt`, он видимость не спрашивает НАМЕРЕННО).
"""
from vp import config
from vp.models import VPVariant


def visible_variants():
    """Опубликованные варианты видимых туров (запрос)."""
    return VPVariant.objects.filter(is_published=True, tour__in=config.VISIBLE_TOURS)


def tour_visible(tour):
    """Виден ли тур в разделе (иначе его попытки — архив)."""
    return tour in config.VISIBLE_TOURS


def is_visible(variant):
    return variant.is_published and variant.tour in config.VISIBLE_TOURS


def variants_for(request):
    """Что можно открыть по слагу: всем — видимые; персоналу — всё, включая черновики и
    скрытые туры (проверить до выпуска, посмотреть архив)."""
    if request.user.is_authenticated and request.user.is_staff:
        return VPVariant.objects.all()
    return visible_variants()
