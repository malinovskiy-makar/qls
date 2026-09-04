"""Фото и файлы к попытке: проверка загрузки и распознавание текста.

Этап 6.2 редизайна каталога. Файлы хранятся через `FileAsset`
(kind `student_work`), связь с попыткой — `CatalogAttempt.files`. Текст с
фото распознаёт профиль `catalog_ocr`: «перепиши математический текст
буквально, формулы в TeX, ничего не решай»; распознанное ложится в
`attempt.ocr_text`, и проверка получает текст ученика вместе с ним.

⚠️ НАРУЖУ УХОДИТ САМО ИЗОБРАЖЕНИЕ И НИЧЕГО БОЛЬШЕ: в тексте запроса —
инструкция и хеш файла (чтобы кэш ответов не спутал два разных фото).
"""
from __future__ import annotations

import base64
import hashlib

from django.core.files.uploadedfile import UploadedFile

from problems.ai import core

PROFILE = 'catalog_ocr'
MAX_BYTES = 10 * 1024 * 1024
MAX_FILES = 3
# Расширение → тип содержимого. Только то, что модель умеет читать.
ALLOWED = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
           'webp': 'image/webp', 'pdf': 'application/pdf'}
TOO_BIG = 'Файл больше 10 МБ: сожмите фото или пришлите его частями.'
WRONG_TYPE = 'Подойдёт фото (JPG, PNG, WebP) или PDF.'
TOO_MANY = 'Не больше трёх файлов на попытку.'

OCR_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['text'],
    'properties': {'text': {'type': 'string'}},
}


def _extension(name):
    return (name or '').rsplit('.', 1)[-1].lower() if '.' in (name or '') else ''


def validate_upload(uploaded):
    """Проверка одного файла → (тип содержимого, текст ошибки или '')."""
    if not isinstance(uploaded, UploadedFile):
        return '', WRONG_TYPE
    if uploaded.size > MAX_BYTES:
        return '', TOO_BIG
    media_type = ALLOWED.get(_extension(uploaded.name))
    if not media_type:
        return '', WRONG_TYPE
    head = uploaded.read(8)
    uploaded.seek(0)
    if media_type == 'application/pdf':
        if not head.startswith(b'%PDF'):
            return '', WRONG_TYPE
        return media_type, ''
    try:
        from PIL import Image
        image = Image.open(uploaded)
        image.verify()          # битый или чужой файл под видом картинки
    except Exception:
        return '', WRONG_TYPE
    finally:
        uploaded.seek(0)
    return media_type, ''


def media_type_of(asset):
    return ALLOWED.get(_extension(asset.file.name), '')


def payload_of(asset):
    """Файл → {media_type, data(base64), sha256} для поставщика."""
    with asset.file.open('rb') as fh:
        raw = fh.read()
    return {'media_type': media_type_of(asset),
            'data': base64.b64encode(raw).decode('ascii'),
            'sha256': hashlib.sha256(raw).hexdigest()}


def recognise(asset, user):
    """Текст одного файла. Поднимает `core.AiUnavailable`."""
    payload = payload_of(asset)
    if not payload['media_type']:
        return ''
    user_text = ('Перепиши буквально весь математический текст с этого файла. '
                 'Формулы — в TeX. Ничего не решай и не исправляй. '
                 'Файл: sha256 %s' % payload['sha256'])
    result = core.run(PROFILE, user_text, OCR_SCHEMA, user,
                      images=[{'media_type': payload['media_type'],
                               'data': payload['data']}])
    return str((result.data or {}).get('text') or '').strip()


def recognise_attempt(attempt, user):
    """Распознать все файлы попытки → `attempt.ocr_text` (без сохранения)."""
    texts = [recognise(asset, user) for asset in attempt.files.all()]
    attempt.ocr_text = '\n\n'.join(t for t in texts if t)
    return attempt.ocr_text
