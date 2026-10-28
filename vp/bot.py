"""Бот стены 2 тура: обработка ОДНОГО обновления Telegram (вебхук и `tg_poll`).

Бот делает две вещи: по `/start <код>` привязывает Telegram к аккаунту, который
этот код получил на сайте, и проверяет подписку на канал (docs/VP.md).

⚠️ ПРИВЯЗКА — НЕ ВХОД. Бот не открывает сессию на сайте и не выдаёт ссылок,
которые её открывают (149-ФЗ в ред. 406-ФЗ, ст. 13.55 КоАП). Код выдаётся только
вошедшему и привязывает только его аккаунт.

⚠️ КНОПКИ-ССЫЛКИ НА САЙТ НЕТ: на iPhone она открылась бы во встроенном браузере
Telegram, где человек на сайт не входил. Бот просит вернуться во вкладку браузера.

⚠️ В ЛОГ — ТОЛЬКО `update_id`, ТИП ОБНОВЛЕНИЯ И КЛАСС ОШИБКИ: в теле обновления
числовой ID, ник и имя человека.

⚠️ ТИРЕ — ТОЛЬКО «–»: `scripts/check_em_dash.py` не смотрит `.py`, тексты стережёт
отдельный тест (`vp/tests/test_wall_tg.py`).
"""
import hashlib
import hmac
import logging

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from catalog import seo
from vp import telegram, wall
from vp.models import VPTelegramLink, VPTelegramToken, VPWall

logger = logging.getLogger(__name__)

TEXTS = {
    'hello': 'Привет! Это бот тренажёра «Высшей пробы» от Weconomics.',
    'expired': 'Ссылка устарела. Вернитесь на сайт и нажмите «Подключить Telegram» ещё раз.',
    'ready': ('Готово: подписка есть, аккаунт «{login}» привязан к сайту. Вернитесь во '
              'вкладку браузера с вариантом – она обновится сама, останется ответить '
              'на три вопроса.'),
    'ready_surveyed': ('Готово: подписка есть, аккаунт «{login}» привязан к сайту. Вернитесь '
                       'во вкладку браузера с вариантом – можно начинать вариант.'),
    'no_sub': 'Подписки на {channel} пока нет. Подпишитесь и нажмите «Проверить».',
    'failed': 'Не получилось проверить подписку. Попробуйте через минуту.',
    'moved': ('Этот Telegram был привязан к другому аккаунту Weconomics – теперь он '
              'привязан к «{login}».'),
    'plain': ('Чтобы открыть вариант, нажмите «Подключить Telegram» на странице варианта: '
              '{site}/vp/'),
    'button_subscribe': 'Подписаться',
    'button_check': 'Проверить',
    'alert_no_sub': 'Подписки пока нет',
    'alert_failed': 'Не получилось проверить, попробуйте через минуту',
}

CHECK = 'check'

#: Повтор `update_id` не обрабатывается сутки: вебхук и опрос шлют его заново после сбоя.
DEDUP_SECONDS = 24 * 3600


def token_hash(token):
    """Отпечаток кода привязки: HMAC-SHA256 на `SECRET_KEY`, как у кодов почты."""
    return hmac.new(settings.SECRET_KEY.encode('utf-8'), ('vp-tg:' + token).encode('utf-8'),
                    hashlib.sha256).hexdigest()


def _channel():
    return settings.TELEGRAM_CHANNEL


def _channel_url():
    return 'https://t.me/' + settings.TELEGRAM_CHANNEL.lstrip('@')


def _check_keyboard(with_subscribe):
    row = []
    if with_subscribe:
        row.append({'text': TEXTS['button_subscribe'], 'url': _channel_url()})
    row.append({'text': TEXTS['button_check'], 'callback_data': CHECK})
    return {'inline_keyboard': [row]}


def _ready_text(user):
    surveyed = VPWall.objects.filter(user=user, survey_at__isnull=False).exists()
    key = 'ready_surveyed' if surveyed else 'ready'
    return TEXTS[key].format(login=user.get_username())


def _send(chat_id, text, keyboard=None):
    params = {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True}
    if keyboard:
        params['reply_markup'] = keyboard
    telegram.call('sendMessage', **params)


def check_link(link):
    """Проверить подписку и записать итог в привязку. True / False / None."""
    subscribed, error = telegram.check_subscription(link.tg_user_id)
    link.checked_at = timezone.now()
    link.last_error = error
    if subscribed is not None:
        link.subscribed = subscribed
    link.save(update_fields=['checked_at', 'last_error', 'subscribed'])
    if subscribed:
        wall.pass_contact(link.user, 'tg')
    return subscribed


def _take_token(code):
    """Погасить код привязки атомарно и вернуть его строку или None."""
    fresh_since = timezone.now() - wall.TOKEN_TTL
    row = (VPTelegramToken.objects.select_related('user')
           .filter(token_hash=token_hash(code), used_at__isnull=True,
                   created_at__gt=fresh_since).first())
    if row is None:
        return None
    taken = (VPTelegramToken.objects.filter(pk=row.pk, used_at__isnull=True)
             .update(used_at=timezone.now()))
    return row if taken == 1 else None


def _link(user, sender):
    """Привязать Telegram `sender` к `user`. True, если он уходит от ДРУГОГО аккаунта.

    Привязка переходит к свежему коду: пересланная другу ссылка никого не запирает —
    свежий код самого друга заберёт его Telegram обратно. Контакт прежнего аккаунта
    не трогается: он постоянный.
    """
    tg_id = int(sender['id'])
    username = (sender.get('username') or '')[:64]
    with transaction.atomic():
        moved = VPTelegramLink.objects.filter(tg_user_id=tg_id).exclude(user=user).delete()[0] > 0
        link = VPTelegramLink.objects.filter(user=user).first()
        if link is None:
            link = VPTelegramLink.objects.create(user=user, tg_user_id=tg_id, tg_username=username)
        else:
            if link.tg_user_id != tg_id:
                link.linked_at = timezone.now()
                link.subscribed = False
                link.checked_at = None
            link.tg_user_id, link.tg_username, link.last_error = tg_id, username, ''
            link.save()
    return link, moved


def _start(chat_id, sender, code):
    row = _take_token(code)
    if row is None:
        _send(chat_id, TEXTS['expired'])
        return
    user = row.user
    link, moved = _link(user, sender)
    tail = ('\n\n' + TEXTS['moved'].format(login=user.get_username())) if moved else ''
    subscribed = check_link(link)
    if subscribed:
        _send(chat_id, TEXTS['hello'] + '\n\n' + _ready_text(user) + tail)
    elif subscribed is False:
        _send(chat_id, TEXTS['hello'] + '\n\n' + TEXTS['no_sub'].format(channel=_channel()) + tail,
              _check_keyboard(with_subscribe=True))
    else:
        _send(chat_id, TEXTS['failed'] + tail, _check_keyboard(with_subscribe=False))


def _plain(chat_id):
    _send(chat_id, TEXTS['hello'] + ' ' + TEXTS['plain'].format(site=seo.SITE_URL))


def _message(message):
    chat = message.get('chat') or {}
    if chat.get('type') != 'private':
        return
    sender = message.get('from') or {}
    text = (message.get('text') or '').strip()
    parts = text.split(maxsplit=1)
    if parts and parts[0].split('@')[0] == '/start' and len(parts) == 2 and sender.get('id'):
        _start(chat['id'], sender, parts[1].strip())
    else:
        _plain(chat['id'])


def _callback(query):
    """Кнопка «Проверить». ⚠️ На КАЖДОЕ нажатие — `answerCallbackQuery`, иначе у
    кнопки висит загрузка."""
    answer = {'callback_query_id': query.get('id')}
    try:
        message = query.get('message') or {}
        chat = message.get('chat') or {}
        if chat and chat.get('type') != 'private':
            return
        sender = query.get('from') or {}
        link = (VPTelegramLink.objects.select_related('user')
                .filter(tg_user_id=sender.get('id')).first()) if sender.get('id') else None
        if link is None:
            if chat.get('id'):
                _plain(chat['id'])
            return
        subscribed = check_link(link)
        if subscribed:
            text = TEXTS['hello'] + '\n\n' + _ready_text(link.user)
            try:
                telegram.call('editMessageText', chat_id=chat.get('id'),
                              message_id=message.get('message_id'), text=text)
            except telegram.TelegramError:
                # Сообщение старше 48 часов не правится — пишем новое.
                _send(chat.get('id') or sender['id'], text)
        elif subscribed is False:
            answer['text'] = TEXTS['alert_no_sub']
        else:
            answer['text'] = TEXTS['alert_failed']
    finally:
        telegram.call('answerCallbackQuery', **answer)


def handle(update):
    """Обработать одно обновление. Чужие типы и не личные чаты — молча пропустить."""
    if 'message' in update:
        _message(update['message'] or {})
    elif 'callback_query' in update:
        _callback(update['callback_query'] or {})


def handle_once(update):
    """Обработать обновление ОДИН раз: `True` – обработано, `False` – повтор.

    Единственное место отсева повторов для вебхука и для `tg_poll`. Кэш на бою – Redis,
    общий для контейнеров, поэтому отсев переживает перезапуск службы опроса.
    Сбой обработки пишется в лог (`update_id`, тип, класс ошибки, без тела) и наружу не
    выходит: повтор обновления с ошибкой Telegram не лечит, а вебхук должен ответить 200.
    """
    update_id = update.get('update_id')
    if update_id is not None and not cache.add('vp:tg:update:%s' % update_id, 1, DEDUP_SECONDS):
        return False
    try:
        handle(update)
    except Exception as error:  # noqa: BLE001 — один сбой не роняет ни вебхук, ни опрос
        logger.warning('Бот: обновление %s (%s) – %s', update_id, update_kind(update),
                       type(error).__name__)
    return True


def update_kind(update):
    """Тип обновления для лога — без тела."""
    for kind in ('message', 'callback_query'):
        if kind in update:
            return kind
    return 'other'
