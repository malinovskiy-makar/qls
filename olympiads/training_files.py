"""Файлы раздела — ЕДИНСТВЕННОЕ место, отдающее их (листы Э5–Э6, PDF тура У1).

⚠️ Модуль из двух вьюх нарочно: сторож `problems/tests/test_media_route.py::
NoOtherFileServingViewTests` разрешает отдачу файлов пофайлово, и вписать туда
весь `views_training.py` значило бы пропускать любую будущую отдачу.

- `training_sheet` — лист СВОЕЙ попытки (вошедший — по `user`, гость — по
  ключу сессии); иначе 404, в том числе гостю и на несуществующий номер.
- `phone_sheet` — лист по пропуску телефона: только листы ЭТОГО задания ЭТОЙ
  попытки; истёкший пропуск — 410.
- Путь — из поля `TrainingUpload.file`, из адреса только целые номера и токен;
  тип — из поля `mime`, проверенного при загрузке
  (`catalog.attachments.validate_upload`); `nosniff`; PDF — скачиванием, чтобы
  он не открывался на нашем домене.
- `variant_file` — PDF комплекта (условия, разборы) из нашей копии (день
  30.10, У1): только у основного комплекта видимой олимпиады, только PDF по
  первым байтам «%PDF-» (архив или Word — 404), путь из поля
  `OlympiadVariantFile.file`, из адреса только целые номера. Открывается в
  браузере (`inline`): это файлы организаторов из пакета, сверенные по
  SHA-256 при заливке, а не загрузка пользователя.
"""
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from .views import soon_page
from .views_training import _own_attempt_sheet, _token_or_error


def _send(sheet, cache):
    pdf = sheet.mime == 'application/pdf'
    response = FileResponse(sheet.file.open('rb'), as_attachment=pdf,
                            filename='list-{}.pdf'.format(sheet.page) if pdf else None,
                            content_type=sheet.mime or 'application/octet-stream')
    response['Cache-Control'] = cache
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def training_sheet(request, slug, pk, sheet_id):
    """Файл листа — только хозяину попытки."""
    stub = soon_page(request)
    if stub is not None:
        return stub
    return _send(_own_attempt_sheet(request, slug, pk, sheet_id),
                 'private, max-age=3600')


def phone_sheet(request, token, sheet_id):
    """Миниатюра листа на телефоне — только листы ЭТОГО задания по токену."""
    from .models import TrainingUpload

    stub = soon_page(request)
    if stub is not None:
        return stub
    found, gone = _token_or_error(request, token)
    if gone is not None:
        return gone
    sheet = get_object_or_404(TrainingUpload, pk=sheet_id,
                              attempt=found.attempt, problem=found.problem)
    return _send(sheet, 'private, max-age=600')


def variant_file(request, slug, pk, file_id):
    """PDF комплекта — свою копию, в браузере."""
    from . import navigator
    from .models import OlympiadVariantFile

    stub = soon_page(request)
    if stub is not None:
        return stub
    variant = get_object_or_404(
        navigator.base_variants().filter(olympiad__slug=slug), pk=pk)
    item = get_object_or_404(OlympiadVariantFile, pk=file_id, variant=variant)
    if not item.file or not item.file.name.lower().endswith('.pdf'):
        raise Http404
    try:
        handle = item.file.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404
    if handle.read(5) != b'%PDF-':
        handle.close()
        raise Http404
    handle.seek(0)
    response = FileResponse(handle, as_attachment=False,
                            filename='{}-{}.pdf'.format(variant.kit_key or variant.pk, item.pk),
                            content_type='application/pdf')
    response['Cache-Control'] = 'public, max-age=86400'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
