# -*- coding: utf-8 -*-
"""Вернуть в счётчик расход сортировщиков, стёртый гонкой за файл.

10.09.2026 пакетный судья и сортировщики работали одновременно, а
счётчик держал копию `costs.json` в памяти и переписывал файл целиком.
Расход обоих сортировщиков исчез из учёта. Дефект починен (`_record`
перечитывает файл), но уже потерянные суммы надо вернуть руками.

Суммы взяты из напечатанных итогов прогонов, они точные:
    glm-5.3-flash: $0,4174 − $0,0230 = $0,3944
    glm-5.3:       $4,3795 − $0,4174 = $3,9621
    замер задержки: $0,0430

⚠️ Затирание случилось ДВАЖДЫ: первый раз во время работы пакетного
судьи, второй — когда тот дописал последние части уже после починки, но
из процесса, запущенного ДО неё. Починка работает только для процессов,
стартовавших после неё; долгоживущий процесс продолжает нести свою
старую копию кода. Восстанавливать надо, когда параллельных прогонов
нет.
Счётчики токенов восстановлению не подлежат — они были только в
затёртом файле. Ставим null, чтобы отсутствие числа было видно, а не
принято за ноль.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, 'costs.json')

RESTORE = {
    '3. реранкер glm-flash': ('glm-5.3-flash', 0.3944, 273),
    '3. реранкер glm': ('glm-5.3', 3.9621, 273),
    'замер задержки': ('glm-5.3-flash', 0.0430, 21),
}


def main():
    with open(PATH, encoding='utf-8') as handle:
        costs = json.load(handle)
    added = 0.0
    for stage, (model, usd, calls) in RESTORE.items():
        if stage in costs['by_stage']:
            print('уже на месте: %s' % stage)
            continue
        costs['by_stage'][stage] = {model: {
            'usd': usd, 'calls': calls, 'input': None, 'output': None,
            'cache_read': None, 'reasoning': None,
            'note': 'восстановлено после гонки за costs.json; токены утеряны',
        }}
        added += usd
    provider = costs['by_provider'].setdefault('zai', {'usd': 0.0, 'calls': 0})
    provider['usd'] += added
    provider['calls'] += sum(c for _m, _u, c in RESTORE.values()) if added else 0
    costs['total_usd'] += added
    with open(PATH, 'w', encoding='utf-8') as handle:
        json.dump(costs, handle, ensure_ascii=False, indent=1)
    print('Восстановлено $%.4f. Итого по счётчику $%.4f'
          % (added, costs['total_usd']))
    print('По провайдерам: %s'
          % {k: round(v['usd'], 4) for k, v in costs['by_provider'].items()})


if __name__ == '__main__':
    main()
