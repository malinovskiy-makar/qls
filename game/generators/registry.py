"""
Реестр архетипов: единственное место, где перечислены боевые генераторы.

ARCHETYPES — {key: экземпляр Archetype} в порядке блоков (А → Б → В → Г);
этот порядок используют команды generate_game_questions / preview_generated.
Недоделанный архетип сюда НЕ добавляется — это и есть исключение из боевой
генерации.
"""
from collections import OrderedDict


def _build():
    from . import equilibrium, shift_equilibrium
    archetypes = [
        # Блок А — рынок (спрос и предложение)
        equilibrium.ARCHETYPE,
        shift_equilibrium.ARCHETYPE,
        # Блок Б — фирма и издержки
        # Блок В — КПВ и торговля
        # Блок Г — макро-лайт
    ]
    return OrderedDict((a.key, a) for a in archetypes)


ARCHETYPES = _build()
