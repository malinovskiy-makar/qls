"""Подписи и порядок вариантов. Только представление, без изменения исходных данных."""
import re

from vp.models import VPVariant

_AUTHOR_NUMBER = re.compile(r'^Вариант (?:от )?Weconomics\s*(?:[–—-]|№)\s*(\d+)\b', re.I)


def author_number(variant):
    if variant.tour == 2 and variant.source_kind == VPVariant.SourceKind.AUTHOR:
        match = _AUTHOR_NUMBER.match(variant.title)
        if match:
            return int(match[1])
    return None


def variant_title(variant):
    if variant.tour == 2 and variant.source_kind == VPVariant.SourceKind.DEMO:
        return 'Официальная демоверсия'
    number = author_number(variant)
    return f'Вариант Weconomics № {number}' if number is not None else variant.title


def variant_order(variant):
    if variant.tour != 2:
        return (2, 0, variant.order, variant.pk)
    if variant.source_kind == VPVariant.SourceKind.DEMO:
        return (0, 0, variant.order, variant.pk)
    number = author_number(variant)
    return (1 if number is not None else 2, number or 0, variant.order, variant.pk)
