# -*- coding: utf-8 -*-
"""Живая проверка четырёх провайдеров: один дешёвый вызов на каждого.

Ответ просят в одно слово. Смысл не в ответе, а в трёх вещах сразу:
ключ принят, ИМЯ МОДЕЛИ существует, ответ разбирается. Фактическая
стоимость пишется в `costs.json` — с первого же вызова счётчик ведёт
настоящие деньги, а не оценку.

⚠️ Ключи не печатаются. Наружу идёт только «есть / нет».
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

import envbridge  # noqa: E402
import orclient  # noqa: E402
from problems.ai.providers import get_provider  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

#: Провайдер → (имя поставщика в реестре, модель роли, имя переменной ключа).
#: Модели взяты из списков самих провайдеров (`list_models.py`), кроме
#: Anthropic: её `/v1/models` этому ключу недоступен, см. отчёт.
CHECKS = [
    ('zai', 'glm', 'glm-5.3-flash', 'GLM_API_KEY'),
    ('deepseek', 'deepseek', 'deepseek-v4-pro', 'DEEPSEEK_API_KEY'),
    ('openai', 'openai', 'gpt-5.6-sol', 'OPENAI_API_KEY'),
    ('anthropic', 'anthropic', 'claude-haiku-4-5', 'ANTHROPIC_API_KEY'),
    ('anthropic', 'anthropic', 'claude-sonnet-5', 'ANTHROPIC_API_KEY'),
]

#: ⚠️ Схема обязана быть пригодной для СТРОГОГО режима OpenAI: у каждого
#: объекта `additionalProperties: false`, и все свойства перечислены в
#: `required`. Иначе Responses API отвечает 400 ещё до модели. Имя схемы
#: («reply» внутри провайдера) обязано быть латиницей: ^[a-zA-Z0-9_-]+$.
SCHEMA = {'type': 'object', 'properties': {'answer': {'type': 'string'}},
          'required': ['answer'], 'additionalProperties': False}
SYSTEM = ['Отвечай ровно одним словом в поле answer.']
USER = 'Назови столицу Франции.'


def main():
    present = envbridge.apply_to_process()
    print('Ключи в .env:')
    for name, ok in present.items():
        print('   %-20s %s' % (name, 'есть' if ok else 'НЕТ'))
    if not all(present.values()):
        missing = [n for n, ok in present.items() if not ok]
        print('\nОСТАНОВКА: нет ключей %s' % ', '.join(missing))
        return 1

    client = orclient.Client(
        providers={name: get_provider(registry)
                   for name, registry, _, _ in {(c[0], c[1], 0, 0) for c in CHECKS}},
        costs_path=os.path.join(HERE, 'costs.json'),
        failures_path=os.path.join(HERE, 'failures.jsonl'),
        budgets=orclient.BUDGETS)

    print('\nЖивая проверка (пик DeepSeek сейчас: %s):'
          % ('да' if orclient.is_peak() else 'нет'))
    results, ok_all = [], True
    for provider, _registry, model, _var in CHECKS:
        try:
            reply = client.call(
                stage='0-бис. живая проверка', query_id='smoke',
                provider=provider, model=model, system_blocks=SYSTEM,
                user_text=USER, schema=SCHEMA, max_tokens=64, timeout=90,
                estimated_usd=0.01)
        except Exception as error:                      # noqa: BLE001
            ok_all = False
            print('   %-10s %-22s ОТКАЗ: %s: %s'
                  % (provider, model, type(error).__name__,
                     str(error)[:120]))
            results.append({'provider': provider, 'model': model,
                            'ok': False, 'error': str(error)[:300]})
            continue
        cost = client.price_of(provider, model, reply)
        text = (reply.text or '').strip().replace('\n', ' ')[:60]
        print('   %-10s %-22s ok  вход %5d выход %4d  $%.6f  ответ: %s'
              % (provider, model, reply.input_tokens, reply.output_tokens,
                 cost, text))
        results.append({'provider': provider, 'model': model, 'ok': True,
                        'input': reply.input_tokens,
                        'output': reply.output_tokens,
                        'reasoning': reply.reasoning_tokens,
                        'cache_read': reply.cache_read_tokens,
                        'cost_usd': round(cost, 6), 'text': text})

    with open(os.path.join(HERE, 'smoke.json'), 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    print('\nПотрачено по провайдерам:')
    for name, ceiling in orclient.BUDGETS.items():
        print('   %-10s $%.6f из $%.2f' % (name, client.spent.get(name, 0.0),
                                           ceiling))
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
