"""Третья файловая вьюха проекта: своё вложение чата (18.09.2026, ADR 0118).

Отдельным модулем, а не в `catalog/views.py`: сторож
`problems/tests/test_media_route.py::NoOtherFileServingViewTests` разрешает
файловые вьюхи пофайлово, и разрешить весь большой `views.py` значило бы
пропустить любую будущую отдачу файла рядом. Разбор — docs/SECURITY.md,
раздел «Третья файловая вьюха: вложение чата».
"""
from django.http import FileResponse, Http404

from . import chat

#: Картинка открывается во вкладке; PDF — скачиванием, как в админке
#: (`ChatTurnAdmin.file_view`): чужой PDF не исполняется на нашем домене.
INLINE_TYPES = ('image/jpeg', 'image/png', 'image/webp')


def chat_attachment(request, pk):
    """Своё вложение чата: только владельцу или сотруднику.

    ⚠️ Чужое, несуществующее и гостю — одинаково 404, не 403 и не редирект на
    вход: номер вложения не должен говорить, есть ли такой файл. Тип — из поля
    `mime` (его проверил сервер при загрузке), путь — из поля `file`: из
    запроса берётся только целое число.
    """
    from problems.models_platform import ChatAttachment

    user = request.user
    if not user.is_authenticated:
        raise Http404
    found = ChatAttachment.objects.filter(pk=pk)
    if not user.is_staff:
        found = found.filter(user=user)
    attachment = found.first()
    if attachment is None or not attachment.file:
        raise Http404
    try:
        handle = attachment.file.open('rb')
    except OSError:
        raise Http404 from None
    response = FileResponse(handle, content_type=attachment.mime)
    how = 'inline' if attachment.mime in INLINE_TYPES else 'attachment'
    response['Content-Disposition'] = '%s; filename="file.%s"' % (
        how, chat.EXTENSIONS.get(attachment.mime, 'bin'))
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, max-age=0'
    return response
