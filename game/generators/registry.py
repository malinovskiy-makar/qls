"""
Реестр архетипов: единственное место, где перечислены боевые генераторы.

ARCHETYPES — {key: экземпляр Archetype} в порядке блоков (А → Б → В → Г);
этот порядок используют команды generate_game_questions / preview_generated.
Недоделанный архетип сюда НЕ добавляется — это и есть исключение из боевой
генерации.
"""
from collections import OrderedDict


def _build():
    from . import (equilibrium, shift_equilibrium, tax_subsidy, price_control,
                   elasticity_point, elasticity_arc, surplus, costs_tc,
                   comp_firm, monopoly, ppf_single, ppf_joint)
    archetypes = [
        # Блок А — рынок (спрос и предложение)
        equilibrium.ARCHETYPE,
        shift_equilibrium.ARCHETYPE,
        tax_subsidy.ARCHETYPE,
        price_control.ARCHETYPE,
        elasticity_point.ARCHETYPE,
        elasticity_arc.ARCHETYPE,
        surplus.ARCHETYPE,
        # Блок Б — фирма и издержки
        costs_tc.ARCHETYPE,
        comp_firm.ARCHETYPE,
        monopoly.ARCHETYPE,
        # Блок В — КПВ и торговля
        ppf_single.ARCHETYPE,
        ppf_joint.ARCHETYPE,
        # Блок Г — макро-лайт
    ]
    return OrderedDict((a.key, a) for a in archetypes)


ARCHETYPES = _build()
