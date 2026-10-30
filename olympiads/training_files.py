"""Файлы листов решения тура — ЕДИНСТВЕННОЕ место раздела, отдающее файлы (Э5–Э6).

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
"""
from django.http import FileResponse
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
