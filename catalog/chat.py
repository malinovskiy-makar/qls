"""Чат по одной задаче: режимы, фото и PDF решения, полный журнал реплик.

Этап 5 редизайна каталога (ADR 0080) и решение владельца 15.09.2026:
* модель — `CATALOG_CHAT_PROVIDER`/`CATALOG_CHAT_MODEL` (GLM-5.3), а не общий
  `AI_PROVIDER`: бета выясняет, подходит ли эта модель ученикам;
* режим — свойство реплики: `theory`, `method`, `check` или `free` (обычный
  ввод); блок режима — третий системный блок (`prompts.CATALOG_CHAT_MODES`);
* фото и PDF: GLM-5.3 картинок не принимает, поэтому реплика с файлом сначала
  идёт в модель зрения (`CATALOG_CHAT_VISION_MODEL`) с задачей «перепиши
  дословно», а расшифровка с пометкой `[расшифровка фото]` вклеивается в текст
  реплики для модели чата (приём ADR 0081);
* КАЖДАЯ реплика пишется в `ChatTurn`, в том числе ошибочная. История для
  модели по-прежнему приходит от клиента — последние шесть реплик.

⚠️ НАРУЖУ УХОДИТ ТОЛЬКО ТЕКСТ ЗАДАЧИ И РАЗГОВОРА: условие, подпункты, последняя
попытка ученика и результат её проверки, реплики, картинки приложенного
решения; в режиме «Проверь моё решение» ещё эталонные ответ и решение — только
системным блоком. Ни имени, ни почты, ни класса — ничего из профиля (P0).
"""
from __future__ import annotations

import hashlib
import io
import logging
import time
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q
from django.utils import timezone

from problems.ai import core, prompts, providers

logger = logging.getLogger(__name__)

PROFILE = 'catalog_chat'
HISTORY_LIMIT = 6
MESSAGE_MAX = 2000
# Потолки ответа — предохранитель от «модель поехала», а не формат: длину
# ответа больше не задаёт промпт (18.09.2026). Раньше 900/1 200 знаков резали
# ответ посреди слова.
REPLY_MAX = 8000
CHECK_REPLY_MAX = 10000
#: Токены ответа реплики — явно: без них длинный ответ обрезал бы уже поставщик.
CHAT_MAX_TOKENS = 3000
#: Не больше трёх файлов к одной реплике; страниц в модель зрения — всего пять.
FILES_PER_TURN = 3
QUOTE_MAX = 300
CUT_MARK = ' …'
#: Эталонное решение режима проверки — не больше, чтобы одна реплика не стоила как десять.
REFERENCE_MAX = 8000
MODES = ('free', 'theory', 'method', 'check')
HOMEWORK_MODE = ('РЕЖИМ: ТОЛЬКО НАВОДЯЩИЕ ВОПРОСЫ. Задача входит в домашку '
                 'ученика: не объясняй решение, задавай вопросы и говори, где искать.')
VISION_MARK = '[расшифровка фото]'
VISION_PAGES_MAX = 5
UPLOADS_PER_DAY = 10
PDF_WIDTH = 1400
IMAGE_SIDE_MAX = 1600

BUDGET_TEXT = 'Помощник на сегодня выбрал дневной бюджет. Завтра снова ответит.'
CHECK_EMPTY_TEXT = 'Прикрепите фото или PDF решения или опишите решение текстом.'
TOO_MANY_UPLOADS = 'На сегодня файлов достаточно: не больше 10 в день.'
BAD_PDF = 'PDF не открылся: пришлите фото страниц.'
TOO_MANY_FILES = 'Не больше трёх файлов к одной реплике.'
PAGES_NOTE = 'Смотрю первые пять страниц.'

CHAT_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['reply'],
    'properties': {'reply': {'type': 'string'}},
}
VISION_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['text'],
    'properties': {'text': {'type': 'string'}},
}

VERDICT_WORDS = {'ok': 'верно', 'partial': 'частично верно', 'wrong': 'неверно',
                 'needs_human': 'модель не поставила балл'}
EXTENSIONS = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp',
              'application/pdf': 'pdf'}
IMAGE_TYPES = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
               'webp': 'image/webp'}


def chat_provider():
    return providers.get_provider(getattr(settings, 'CATALOG_CHAT_PROVIDER', 'glm'))


def is_available():
    """Есть ли карточка чата вообще: поставщик чата настроен (правило нуля)."""
    try:
        return chat_provider().is_available()
    except KeyError:
        return False


def in_active_homework(user, problem):
    """Задача лежит в незакрытой домашке этого ученика.

    Домашка адресуется списком учеников (`students`) или группой; закрытой
    считается работа с прошедшим дедлайном. Тогда помощник отвечает только
    наводящими вопросами — иначе чат превращается в решебник для домашки.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    from problems.models_platform import AssignmentItem

    now = timezone.now()
    open_work = Q(assignment__deadline__isnull=True) | Q(assignment__deadline__gte=now)
    mine = Q(assignment__students=user) | Q(assignment__group__students=user)
    return AssignmentItem.objects.filter(catalog_problem=problem).filter(open_work).filter(mine).exists()


def clean_history(history):
    """Последние шесть реплик в виде [{role: me|ai, text}], мусор отброшен."""
    out = []
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        role = 'ai' if item.get('role') == 'ai' else 'me'
        text = str(item.get('text') or '').strip()[:MESSAGE_MAX]
        if text:
            out.append({'role': role, 'text': text})
    return out[-HISTORY_LIMIT:]


def cut_reply(text, limit):
    """Ответ не длиннее `limit` — по границе предложения, а не посреди слова.

    Граница — последняя `. ! ? \\n` до лимита; нет её — последний пробел.
    Обрезанное помечается « …», чтобы было видно, что ответ не весь.
    """
    if len(text) <= limit:
        return text
    head = text[:limit - len(CUT_MARK)]
    cut = max(head.rfind(mark) for mark in ('. ', '! ', '? ', '\n'))
    if cut > 0:
        head = head[:cut + 1]
    elif head.rfind(' ') > 0:
        head = head[:head.rfind(' ')]
    return head.rstrip() + CUT_MARK


def pages_note(attachments):
    """Честная приписка, если страниц больше, чем смотрит модель зрения."""
    total = sum(a.pages for a in attachments)
    return PAGES_NOTE if total > VISION_PAGES_MAX else ''


def build_prompt(problem, parts, message, history, last_attempt=None, homework=False,
                 quote=''):
    lines = ['УСЛОВИЕ:', (problem.statement or '').strip()]
    for part in parts:
        if (part.statement or '').strip():
            lines.append('%s) %s' % ((part.label or '').strip().rstrip(').') or '?',
                                     part.statement.strip()))
    if last_attempt is not None and (last_attempt.text or '').strip():
        lines += ['ПОСЛЕДНЯЯ ПОПЫТКА УЧЕНИКА:', last_attempt.text.strip()]
        if last_attempt.status != 'error':
            verdict = VERDICT_WORDS.get(last_attempt.verdict, '')
            result = 'РЕЗУЛЬТАТ ПРОВЕРКИ: %s' % verdict
            if last_attempt.score is not None:
                result += ', %d из %d' % (last_attempt.score, last_attempt.max_score)
            if last_attempt.first_error_step:
                title = next((s.get('title', '') for s in last_attempt.steps
                              if s.get('n') == last_attempt.first_error_step), '')
                result += '; первая ошибка в шаге %d%s' % (
                    last_attempt.first_error_step, (': ' + title) if title else '')
            if last_attempt.summary:
                result += '. ' + last_attempt.summary
            lines.append(result)
    if homework:
        lines.append(HOMEWORK_MODE)
    if history:
        lines.append('РАЗГОВОР (последние реплики):')
        for item in history:
            lines.append(('Ученик: ' if item['role'] == 'me' else 'Помощник: ') + item['text'])
    if quote:
        # Выделенный учеником кусок условия — текстом реплики, не системным
        # блоком: это его вопрос, а не наше правило.
        lines.append('Фрагмент условия: «%s»' % quote)
    lines += ['ВОПРОС УЧЕНИКА:', message.strip()]
    return '\n'.join(lines)


def system_for(problem, mode):
    """Системные блоки реплики: ядро, профиль чата, блок режима, эталон при проверке."""
    blocks = prompts.system_blocks(PROFILE)
    if mode in prompts.CATALOG_CHAT_MODES:
        blocks.append(prompts.CATALOG_CHAT_MODES[mode])
    if mode == 'check':
        blocks.append(prompts.CATALOG_CHAT_REFERENCE % (
            (problem.answer or '').strip() or 'не указан',
            (problem.solution or '').strip()[:REFERENCE_MAX] or 'не указано'))
    return blocks


# ─── Файлы: загрузка, картинки для модели ──────────────────────────────────

def uploads_today(user):
    from problems.models_platform import ChatAttachment

    start = timezone.localtime(timezone.now()).replace(hour=0, minute=0, second=0,
                                                       microsecond=0)
    return ChatAttachment.objects.filter(user=user, created_at__gte=start).count()


def derived_images(raw, media_type):
    """Картинки для модели зрения: [(расширение, байты)]; пусто — годится сам файл.

    PDF — первые пять страниц в PNG шириной 1 400 px; картинка больше 1 600 px
    по большей стороне — уменьшенный JPEG q85: токены изображения растут с
    размером, а почерк на 1 600 px читается. Поднимает ValueError с текстом.
    """
    if media_type == 'application/pdf':
        import fitz   # PyMuPDF — только здесь: остальным запросам библиотека не нужна

        pages = []
        try:
            with fitz.open(stream=raw, filetype='pdf') as doc:
                if doc.needs_pass:
                    raise ValueError(BAD_PDF)
                for page in doc:
                    if len(pages) >= VISION_PAGES_MAX:
                        break
                    width, height = page.rect.width, page.rect.height
                    # Лента в сотни страниц высотой развернулась бы в гигабайт.
                    if width <= 0 or height * PDF_WIDTH / width > PDF_WIDTH * 4:
                        raise ValueError(BAD_PDF)
                    zoom = PDF_WIDTH / width
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                    pages.append(('png', pixmap.tobytes('png')))
        except ValueError:
            raise
        except Exception:
            raise ValueError(BAD_PDF)
        if not pages:
            raise ValueError(BAD_PDF)
        return pages
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(raw)) as image:
        if max(image.size) <= IMAGE_SIDE_MAX:
            return []
        smaller = ImageOps.exif_transpose(image).convert('RGB')
    smaller.thumbnail((IMAGE_SIDE_MAX, IMAGE_SIDE_MAX))
    out = io.BytesIO()
    smaller.save(out, 'JPEG', quality=85)
    return [('jpg', out.getvalue())]


def save_attachment(uploaded, media_type, user, problem, name=''):
    """Файл и картинки для модели → `ChatAttachment`. ValueError — текст для ученика.

    Имя файла даём сами: имя с телефона ученика в хранилище не нужно.
    """
    from problems.models_platform import ChatAttachment

    raw = uploaded.read()
    uploaded.seek(0)
    pages = derived_images(raw, media_type)
    uploaded.name = '%s.%s' % (uuid.uuid4().hex, EXTENSIONS[media_type])
    attachment = ChatAttachment.objects.create(user=user, problem=problem, file=uploaded,
                                               mime=media_type, size=len(raw),
                                               name=name[:80])
    if pages:
        stem = attachment.file.name.rsplit('.', 1)[0]
        paths = [default_storage.save('%s_p%d.%s' % (stem, number, ext), ContentFile(data))
                 for number, (ext, data) in enumerate(pages, 1)]
    else:
        paths = [attachment.file.name]
    attachment.pages_json = paths
    attachment.pages = len(paths)
    attachment.save(update_fields=['pages_json', 'pages'])
    return attachment


def attachment_images(*attachments):
    """[(MIME, байты)] для модели со всех вложений подряд, всего не больше
    VISION_PAGES_MAX — пары, как их ждёт GLMProvider."""
    images = []
    for attachment in attachments:
        for path in attachment.pages_json or []:
            if len(images) >= VISION_PAGES_MAX:
                return images
            mime = IMAGE_TYPES.get(path.rsplit('.', 1)[-1].lower())
            if mime:
                with default_storage.open(path, 'rb') as handle:
                    images.append((mime, handle.read()))
    return images


def _digest(images):
    """Хеш картинок в тексте запроса: кэш ответов ключ по картинкам не считает."""
    return hashlib.sha256(b''.join(data for _mime, data in images)).hexdigest()


def _spent(result):
    """Деньги вызова; ответ из кэша ответов — ноль: второй раз за него не платили."""
    return Decimal(0) if result.cached else Decimal(str((result.usage or {}).get('cost_usd', 0)))


# ─── Реплика ───────────────────────────────────────────────────────────────

def answer(problem, message, history, user, last_attempt=None, mode='free',
           attachments=(), thread=None, quote=''):
    """Одна реплика помощника → текст ответа. Поднимает `core.AiUnavailable`.

    `attachments` — до FILES_PER_TURN своих вложений; картинки со всех подряд,
    всего не больше VISION_PAGES_MAX страниц (больше — честная приписка).
    Старое поле `ChatTurn.attachment` получает первое вложение: журнал беты
    до 18.09 читается по нему.

    ⚠️ `ChatTurn` пишется ВСЕГДА — и с ответом, и с ошибкой: журнал нужен как
    раз для разбора неудач (нечитаемое фото, отказ поставщика, лимит).
    """
    from problems.models_platform import ChatTurn

    mode = mode if mode in MODES else 'free'
    provider = chat_provider()
    model = getattr(settings, 'CATALOG_CHAT_MODEL', '') or None
    vision_model = getattr(settings, 'CATALOG_CHAT_VISION_MODEL', '')
    attachments = list(attachments)
    turn = ChatTurn(user=user, problem=problem, thread=thread, mode=mode,
                    user_text=message, attachment=attachments[0] if attachments else None,
                    provider=provider.name, model=model or '')
    started = time.monotonic()
    try:
        note = pages_note(attachments)
        text, images = ('%s\n\n%s' % (message, note)) if note else message, None
        if attachments:
            pictures = attachment_images(*attachments)
            if pictures and vision_model:
                seen = core.run(
                    PROFILE, 'Перепиши дословно всё, что на этих фото или страницах. '
                    'Картинок %d, sha256 %s.' % (len(pictures), _digest(pictures)),
                    VISION_SCHEMA, user, images=pictures, provider=provider,
                    model=vision_model, system=[prompts.CORE, prompts.CATALOG_CHAT_VISION])
                turn.vision_text = str((seen.data or {}).get('text') or '').strip()
                turn.vision_input_tokens = (seen.usage or {}).get('input_tokens', 0)
                turn.vision_output_tokens = (seen.usage or {}).get('output_tokens', 0)
                turn.cost_usd += _spent(seen)
                text = '%s\n\n%s\n%s' % (text, VISION_MARK,
                                         turn.vision_text or '(на фото ничего не прочитано)')
            elif pictures:
                images = pictures
                text = '%s\n\n[фото: картинок %d, sha256 %s]' % (text, len(pictures),
                                                                 _digest(pictures))
        prompt = build_prompt(problem, list(problem.parts.all()), text, clean_history(history),
                              last_attempt=last_attempt,
                              homework=in_active_homework(user, problem), quote=quote)
        # ⚠️ Без кэша ответов: режим и эталон живут в системных блоках, а ключ
        # кэша считается по тексту запроса — та же реплика в другом режиме
        # получила бы чужой ответ. Шаг зрения кэшируется: там в тексте хеш файла.
        result = core.run(PROFILE, prompt, CHAT_SCHEMA, user, images=images,
                          provider=provider, model=model, system=system_for(problem, mode),
                          cache_seconds=0, max_tokens=CHAT_MAX_TOKENS)
        turn.input_tokens = (result.usage or {}).get('input_tokens', 0)
        turn.output_tokens = (result.usage or {}).get('output_tokens', 0)
        turn.cost_usd += _spent(result)
        reply = str((result.data or {}).get('reply') or '').strip()
        if not reply:
            raise core.AiUnavailable('Помощник не ответил. Попробуйте спросить иначе.')
        turn.reply = cut_reply(reply, CHECK_REPLY_MAX if mode == 'check' else REPLY_MAX)
        return turn.reply
    except core.AiUnavailable as exc:
        turn.error = ('%s: %s' % (exc.kind, exc))[:500]
        raise
    finally:
        turn.latency_ms = int((time.monotonic() - started) * 1000)
        try:
            turn.save()
            if attachments:
                turn.attachments.set(attachments)
        except Exception:
            # Как учёт расхода в `core._log`: упавший журнал не отнимает ответ.
            logger.exception('Не удалось записать реплику чата — ответ ученику не тронут')
