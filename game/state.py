# -*- coding: utf-8 -*-
u"""
Хранилище состояния забега Wecon Rush.

⚠️ РАНЬШЕ ЗАБЕГ ЖИЛ ЦЕЛИКОМ В `request.session[SESSION_KEY]`. Работало это
нормально ровно до того момента, пока состояние нужно было ОДНОМУ игроку.
Дуэль в реальном времени ломает допущение: сервер обязан видеть счёт обоих
участников, а состояние соперника лежит в ЕГО куке и до сервера не доходит.

Теперь забег лежит в кэше `default` под ключом `rush:run:<run_id>`, а в
сессии остаётся только `run_id` (uuid4). Забег адресуется по идентификатору,
и увидеть его может любой процесс, у которого этот идентификатор есть.

СРОК ЖИЗНИ. `TTL = 2 × duration + TTL_SLACK`. Двойной запас — потолок
длительности забега, который уже проверяет анти-чит (`_rank_run`): забег
длиннее двух запасов режима считается незачётным, а значит и хранить его
дольше незачем. Запас сверх этого нужен на экран итогов и на «сыграть ещё».

⚠️ КЛЮЧЕЙ РОВНО ДВА ВИДА, И `run_id` НЕ СЕКРЕТ. Знание чужого `run_id` не
даёт ничего: отвечать на вопросы можно только своей сессией (вьюхи берут
`run_id` из сессии), а прочитать состояние соперника через дуэль всё равно
разрешено — там и счёт, и жизни показываются на табло по правилам игры.

⚠️ ЧТО НЕ ПЕРЕЕХАЛО. `SEEN_KEY` («виданные между забегами»), `COUNTED_KEY`
(учтённые в статистике) и `LAST_KEY` (последний завершённый забег) остались
в сессии намеренно: это ДОЛГАЯ память конкретного человека, она переживает
десятки забегов и к состоянию одного забега отношения не имеет. Сложить их
в кэш с TTL значило бы терять их при каждом истечении.
"""
import uuid

from django.core.cache import cache

from game import config

# Ключ в сессии — только идентификатор забега.
RUN_ID_KEY = 'rush_run_id'

# ⚠️ СТАРЫЙ КЛЮЧ ЧИТАЕТСЯ ЕЩЁ ОДИН РЕЛИЗ. Забег, начатый ДО выкатки, лежит
# в сессии целиком; уронить его в момент обновления значило бы отнять у
# человека забег на середине. После следующей выкатки строку и всю ветку
# `_legacy` можно убрать.
LEGACY_SESSION_KEY = 'econ_rush'

KEY_PREFIX = 'rush:run:'
# Запас поверх двойной длительности: экран итогов, «сыграть ещё», разбор
# ошибок. Десять минут — с большим запасом и без риска забить кэш.
TTL_SLACK = 600


def new_run_id():
    return uuid.uuid4().hex


def cache_key(run_id):
    return KEY_PREFIX + run_id


def ttl_for(mode):
    u"""Срок жизни состояния забега этого режима, секунды."""
    duration = config.MODES.get(mode, {}).get('duration', 600)
    return 2 * duration + TTL_SLACK


def save_run(request, state):
    u"""Записать состояние забега и привязать его к сессии.

    Идентификатор кладётся в состояние тоже: по одному состоянию должно
    быть видно, какой оно строкой кэша, иначе дуэль не сможет опубликовать
    счёт, не таская идентификатор отдельным аргументом через полвьюхи.
    """
    run_id = state.get('run_id') or request.session.get(RUN_ID_KEY) \
        or new_run_id()
    state['run_id'] = run_id
    request.session[RUN_ID_KEY] = run_id
    # ⚠️ Сессию помечаем изменённой явно. Значение ключа не меняется от
    # ответа к ответу, а Django пишет сессию только когда видит изменение;
    # без этого сессия с новым `run_id` могла бы не сохраниться вовсе.
    request.session.modified = True
    cache.set(cache_key(run_id), state, ttl_for(state.get('mode')))
    return run_id


def load_run(request):
    u"""Состояние текущего забега или None.

    None означает ровно одно: забега нет. Причин две, и для игрока они
    неразличимы — он не начинал забег, или состояние истекло по TTL. В обоих
    случаях честный ответ один и тот же (`no_run`), и выдумывать разницу
    незачем: доигрывать нечего.
    """
    run_id = request.session.get(RUN_ID_KEY)
    if run_id:
        state = cache.get(cache_key(run_id))
        if state is not None:
            state.setdefault('run_id', run_id)
            return state
        # Идентификатор есть, состояния нет — забег истёк. Ключ подчищаем,
        # чтобы следующий заход не ходил в кэш зря.
        drop_run(request)
        return None
    return _legacy(request)


def load_by_id(run_id):
    u"""Состояние по идентификатору, БЕЗ сессии.

    Ради этого всё и переезжало: дуэли нужен счёт соперника, а сессии
    соперника у сервера нет. Возвращает None, если забега нет.
    """
    if not run_id:
        return None
    return cache.get(cache_key(run_id))


def save_by_id(state):
    u"""Записать состояние по его собственному `run_id`, без сессии."""
    run_id = state.get('run_id')
    if not run_id:
        raise ValueError('в состоянии нет run_id')
    cache.set(cache_key(run_id), state, ttl_for(state.get('mode')))
    return run_id


def drop_run(request):
    u"""Забыть текущий забег: и строку кэша, и ключ сессии."""
    run_id = request.session.pop(RUN_ID_KEY, None)
    if run_id:
        cache.delete(cache_key(run_id))
    request.session.pop(LEGACY_SESSION_KEY, None)
    request.session.modified = True


def _legacy(request):
    u"""Забег, начатый ДО выкатки: он лежит в сессии целиком.

    Переносим его в кэш и дальше работаем как с обычным. Один раз на забег:
    после переноса ключ сессии удаляется.
    """
    state = request.session.get(LEGACY_SESSION_KEY)
    if not state:
        return None
    del request.session[LEGACY_SESSION_KEY]
    state['run_id'] = new_run_id()
    save_run(request, state)
    return state
