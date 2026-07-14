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
                   comp_firm, monopoly, ppf_single, ppf_joint,
                   comparative_advantage, mpc_multiplier, labor_minwage,
                   price_index, perfect_price_discrimination)
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
        perfect_price_discrimination.ARCHETYPE,  # бонус 17
        # Блок В — КПВ и торговля
        ppf_single.ARCHETYPE,
        ppf_joint.ARCHETYPE,
        comparative_advantage.ARCHETYPE,
        # Блок Г — макро-лайт
        mpc_multiplier.ARCHETYPE,
        labor_minwage.ARCHETYPE,
        price_index.ARCHETYPE,  # бонус 16
    ]
    return OrderedDict((a.key, a) for a in archetypes)


ARCHETYPES = _build()
