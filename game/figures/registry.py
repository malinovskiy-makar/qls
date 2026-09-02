u"""Реестр сюжетов режима «График».

Недоделанный сюжет в реестр не включать — это и есть исключение из боя
(то же правило, что у семнадцати архетипов).

Ключи стабильны: по ним копится статистика (`ArchetypeStat.generator_key`)
и по ним же чистится пул при пересборке.
"""
from .scenarios.consumer_surplus import ConsumerSurplus
from .scenarios.monopoly_profit import MonopolyProfit
from .scenarios.ppf_joint import JointPPF
from .scenarios.price_ceiling import PriceCeiling
from .scenarios.tax_burden import TaxBurden
from .scenarios.unit_elasticity import UnitElasticity

SCENARIOS = {}
for cls in (ConsumerSurplus, TaxBurden, MonopolyProfit, PriceCeiling,
            UnitElasticity, JointPPF):
    SCENARIOS[cls.key] = cls()

# Порядок показа в предпросмотре — по возрастанию сложности: так их и стоит
# смотреть глазами.
SCENARIO_ORDER = sorted(SCENARIOS, key=lambda k: (SCENARIOS[k].difficulty, k))
