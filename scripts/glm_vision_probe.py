# -*- coding: utf-8 -*-
"""Читает ли GLM картинку: диагностика зрения для чата на задаче (15.09.2026).

НЕ ТЕСТ — запускается руками, это платный вызов модели. Рисует PNG 600×200 с
текстом «Ответ: 42» и простым графиком, шлёт его через `GLMProvider.complete`
и спрашивает, что написано. Каждую модель зовёт дважды — с картинкой и без —
и печатает разницу входных токенов: если картинка ушла в модель, вход с ней
заметно больше.

Запуск:
    venv313\\Scripts\\python.exe scripts/glm_vision_probe.py
    venv313\\Scripts\\python.exe scripts/glm_vision_probe.py glm-5.3 glm-5v
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from problems.ai.providers import GLMProvider  # noqa: E402

MODELS = sys.argv[1:] or ['glm-5.3', 'glm-5.3-flash']
QUESTION = 'Что написано на картинке? Ответь одной строкой.'
SCHEMA = {'type': 'object', 'required': ['text'],
          'properties': {'text': {'type': 'string'}}}
SYSTEM = ['Ты читаешь изображения. Отвечай по-русски.']


def picture():
    image = Image.new('RGB', (600, 200), 'white')
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype('arial.ttf', 48)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 60), 'Ответ: 42', fill='black', font=font)
    # Простой график: оси и ломаная спроса.
    draw.line((360, 20, 360, 180), fill='black', width=2)
    draw.line((360, 180, 580, 180), fill='black', width=2)
    draw.line((370, 30, 470, 110, 570, 170), fill='blue', width=3)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def main():
    provider = GLMProvider()
    if not provider.is_available():
        print('ЗРЕНИЕ НЕ ПРОВЕРЕНО:', provider.unavailable_reason())
        return 1
    png = picture()
    for model in MODELS:
        rows = {}
        for label, images in (('с картинкой', [('image/png', png)]), ('без картинки', None)):
            try:
                reply = provider.complete(SYSTEM, QUESTION, SCHEMA, model, 300,
                                          timeout=60, images=images)
            except Exception as error:                      # noqa: BLE001
                print('%s, %s: ОШИБКА %s' % (model, label, error))
                continue
            rows[label] = reply.input_tokens
            print('%s, %s: ответ=%s | вход=%d выход=%d рассуждение=%d'
                  % (model, label, json.dumps(reply.text, ensure_ascii=False)[:200],
                     reply.input_tokens, reply.output_tokens, reply.reasoning_tokens))
        if len(rows) == 2:
            print('%s: разница входа с картинкой и без — %d токенов'
                  % (model, rows['с картинкой'] - rows['без картинки']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
