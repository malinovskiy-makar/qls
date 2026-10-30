"""Листы решения тура: фото или PDF к заданию (ночь 30.10, Э5).

⚠️ ПРОВЕРКА ФАЙЛА — ОДНА НА ПЛАТФОРМУ: `catalog.attachments.validate_upload`
(расширение, сигнатура PDF, картинка открывается Pillow, до 10 МБ). Вторую
копию правил не пишем — разойдясь, они пустили бы в тур то, что «Стол»
отвергает.

⚠️ EXIF СНИМАЕТСЯ: фото с телефона несёт геометку и модель устройства.
Картинка пересохраняется Pillow (после поворота по EXIF — так её видит
браузер), как аватарка в `problems/forms_accounts.py`; PDF хранится как есть.
"""
import hashlib
import io

from django.core.files.base import ContentFile

from catalog import attachments

MAX_SHEETS = 10
TOO_MANY_SHEETS = 'К заданию — не больше 10 листов.'
WRONG_TYPE = attachments.WRONG_TYPE
TOO_BIG = attachments.TOO_BIG
_SAVE_AS = {'image/jpeg': ('JPEG', 'jpg'), 'image/png': ('PNG', 'png'),
            'image/webp': ('WEBP', 'webp')}


class UploadError(Exception):
    """Отказ с текстом для ученика: не тот файл, слишком большой, лишний лист."""


def clean_bytes(uploaded, media_type):
    """(байты без EXIF, расширение). PDF — как пришёл."""
    raw = uploaded.read()
    uploaded.seek(0)
    if media_type == 'application/pdf':
        return raw, 'pdf'
    from PIL import Image, ImageOps

    fmt, ext = _SAVE_AS[media_type]
    with Image.open(io.BytesIO(raw)) as image:
        image = ImageOps.exif_transpose(image)
        if fmt == 'JPEG' and image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        out = io.BytesIO()
        # Без `exif=` Pillow метаданные не переносит: в файле их больше нет.
        image.save(out, fmt, quality=90) if fmt != 'PNG' else image.save(out, fmt)
    return out.getvalue(), ext


def save_sheet(attempt, problem, uploaded, source='computer'):
    """Проверить и сохранить один лист → `TrainingUpload`. `UploadError` — отказ."""
    from .models import TrainingUpload

    media_type, error = attachments.validate_upload(uploaded)
    if error:
        raise UploadError(error)
    have = TrainingUpload.objects.filter(attempt=attempt, problem=problem).count()
    if have >= MAX_SHEETS:
        raise UploadError(TOO_MANY_SHEETS)
    data, ext = clean_bytes(uploaded, media_type)
    sheet = TrainingUpload(attempt=attempt, problem=problem, page=have + 1,
                           source=source, mime=media_type,
                           sha256=hashlib.sha256(data).hexdigest())
    sheet.file.save('sheet.' + ext, ContentFile(data), save=False)
    sheet.save()
    return sheet


def sheets(attempt, problem=None):
    from .models import TrainingUpload

    queryset = TrainingUpload.objects.filter(attempt=attempt)
    if problem is not None:
        queryset = queryset.filter(problem=problem)
    return list(queryset.order_by('problem_id', 'page', 'id'))


def delete_files(queryset):
    """Удалить файлы листов (уборка гостей): строки удалит каскад попытки."""
    removed = 0
    for sheet in queryset:
        if sheet.file:
            sheet.file.delete(save=False)
            removed += 1
    return removed
