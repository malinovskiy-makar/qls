"""Общие заготовки тестов ВП: полный вариант из 44 заданий по формату 1 тура."""
from decimal import Decimal

from vp.models import VPAnswer, VPAttempt, VPItem, VPVariant

# (номера, блок, вид, баллы) — структура 1 тура 9–10 классов: сумма 100.
STRUCTURE = [
    (range(1, 31), 'snake', 'short_text', '2'),
    (range(31, 36), 'gapfill', 'single', '2'),
    (range(36, 41), 'multi', 'multi', '3'),
    (range(41, 43), 'analytic', 'multi', '3'),
    ((43,), 'single', 'single', '4'),
    ((44,), 'single', 'single', '5'),
]


def _options():
    return [{'n': n, 'text': f'вариант {n}'} for n in range(1, 6)]


def make_full_variant(slug='vp-test'):
    """Вариант из 44 заданий; ответ короткого задания — «термин N»."""
    variant = VPVariant.objects.create(
        slug=slug, title='Тестовый вариант', grade_band='9-10', year=2026,
        source_kind='demo', max_score=Decimal('100'))
    for numbers, block, kind, points in STRUCTURE:
        for number in numbers:
            extra = {}
            if kind == 'short_text':
                extra['answer'] = f'термин {number}'
            elif kind == 'single':
                extra.update(options=_options(), correct=[3])
            else:
                extra.update(options=_options(), correct=[1, 3], penalty=True)
            VPItem.objects.create(
                variant=variant, number=number, block=block, kind=kind,
                statement=f'Задание {number}', points=Decimal(points), **extra)
    return variant


def answer_all(variant, right=True):
    """Попытка, где на каждое задание дан верный (или заведомо неверный) ответ."""
    attempt = VPAttempt.objects.create(
        variant=variant, public_code=f'code-{variant.pk}-{int(right)}')
    for item in variant.items.all():
        if item.kind == 'short_text':
            raw = item.answer if right else 'совсем не то'
        elif item.kind == 'single':
            raw = item.correct[0] if right else 5
        else:
            raw = item.correct if right else [2, 4, 5]
        VPAnswer.objects.create(attempt=attempt, item=item, raw=raw)
    return attempt
