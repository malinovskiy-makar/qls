# -*- coding: utf-8 -*-
"""Списки моделей у четырёх прямых провайдеров. Ключи наружу не выводятся.

Названия моделей берутся ОТСЮДА, а не из головы: слаг, угаданный по
названию из новостей, даёт 404 на первом же платном вызове, а иногда, что
хуже, попадает в соседнюю модель другого размера и тарифа.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import envbridge  # noqa: E402

import urllib.request  # noqa: E402

ENDPOINTS = [
    ('OpenAI', 'https://api.openai.com/v1/models', 'OPENAI_API_KEY',
     lambda key: {'Authorization': 'Bearer %s' % key}),
    ('Anthropic', 'https://api.anthropic.com/v1/models?limit=100',
     'ANTHROPIC_API_KEY',
     lambda key: {'x-api-key': key, 'anthropic-version': '2023-06-01'}),
    ('Z.ai', 'https://api.z.ai/api/paas/v4/models', 'GLM_API_KEY',
     lambda key: {'Authorization': 'Bearer %s' % key}),
    ('DeepSeek', 'https://api.deepseek.com/models', 'DEEPSEEK_API_KEY',
     lambda key: {'Authorization': 'Bearer %s' % key}),
]

FILTERS = {
    'OpenAI': ('gpt-5',),
    'Anthropic': ('haiku', 'sonnet'),
    'Z.ai': ('glm',),
    'DeepSeek': ('',),
}


def main():
    env = envbridge.load()
    out = {}
    for name, url, var, headers in ENDPOINTS:
        key = env.get(var, '')
        if not key:
            out[name] = {'error': 'ключа %s нет' % var}
            print('%s: ключа нет' % name)
            continue
        request = urllib.request.Request(url, headers=headers(key))
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode('utf-8'))
        except Exception as error:                      # noqa: BLE001
            # Текст ошибки печатаем, но ключ в URL не уходит ни у кого из
            # четверых — он всегда в заголовке.
            out[name] = {'error': '%s: %s' % (type(error).__name__, error)}
            print('%s: ОШИБКА %s' % (name, type(error).__name__))
            continue
        ids = sorted(m.get('id', '') for m in data.get('data', []))
        out[name] = {'count': len(ids), 'ids': ids}
        wanted = [i for i in ids
                  if any(f in i for f in FILTERS.get(name, ('',)))]
        print('\n%s: моделей %d, подходящих под роль %d'
              % (name, len(ids), len(wanted)))
        for i in wanted:
            print('   ', i)

    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'models_available.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
