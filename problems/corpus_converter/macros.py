# -*- coding: utf-8 -*-
"""Реестр макросов — раздел 7 аудита 2026-08-27.

Аудит разделил находки на две группы, и это разделение принципиально:

**Опечатки и очевидные подмены** — чинятся отображением: `\\Tilde`→`\\tilde`
(живой #41118), `\\tesxt`→`\\text`, `\\textQ`→`Q`, `\\qaud`→`\\quad`,
`\\rig`→`\\Rightarrow`.

**Неизвестные пользовательские макросы** — `\\soso` (живой #42463),
`\\headic`, `\\rsubitem`, `\\solution`, `\\point`, `\\answerbox`,
`\\floor`, `\\medwhitestar` и прочие. Их смысл зависит от преамбулы
исходного Overleaf-проекта, которой у нас нет. **Угадывать запрещено**:
аудит прямо пишет «нельзя чинить угадыванием на лету». Такая карточка
обязана получить код `MACRO` и уйти в очередь ручного разбора.

⚠️ Как определяется «неизвестный». НЕ по списку из аудита — список
неполон по построению (он собран по 846 карточкам из 16 804). Решает
сам KaTeX: `throwOnError=true` на неизвестной команде даёт
«Undefined control sequence: \\xxx», и `katex_preflight.summarize()`
переводит именно эту ошибку в код `MACRO`, а не в общий `K-ERR`.
Список ниже нужен лишь для человекочитаемого объяснения в отчёте.
"""
from __future__ import annotations

import re

#: Опечатка/подмена → корректная команда. Каждая пара названа аудитом
#: и проверяется настоящим рендером после замены: если замена неверна,
#: карточка всё равно станет FAIL, а не тихим PASS.
MACRO_FIXES = {
    r'\Tilde': r'\tilde',
    r'\tesxt': r'\text',
    r'\qaud': r'\quad',
    r'\rig': r'\Rightarrow',
    r'\textQ': r'Q',
}

#: Известные НЕИЗВЕСТНЫЕ — только для объяснения в отчёте. Шлюз опирается
#: не на этот список, а на вердикт KaTeX (см. docstring модуля).
KNOWN_UNRESOLVED_MACROS = frozenset({
    r'\soso', r'\headic', r'\rsubitem', r'\Subitem', r'\solution',
    r'\point', r'\answerbox', r'\newcolumn', r'\floor', r'\medwhitestar',
})

#: Замена только когда дальше НЕ идёт буква: иначе `\rig` съел бы
#: `\right`, а `\Tilde` — гипотетический `\Tilder`.
_FIX_RE = re.compile(
    '(' + '|'.join(re.escape(k) for k in MACRO_FIXES) + r')(?![A-Za-z])'
)

#: Разделители, которые KaTeX принимает после `\big`/`\Big`/`\bigg`/`\Bigg`.
#: Список закрытый и короткий намеренно: снимать группу можно ТОЛЬКО
#: когда внутри действительно разделитель. `\bigg{abc}` — не наш случай,
#: и молча выкидывать скобки там значило бы менять смысл формулы.
_DELIMITERS = (
    r'\{', r'\}', r'\lvert', r'\rvert', r'\lVert', r'\rVert',
    r'\langle', r'\rangle', r'\lfloor', r'\rfloor', r'\lceil', r'\rceil',
    r'\uparrow', r'\downarrow', r'\|', r'\backslash',
    '(', ')', '[', ']', '|', '/', '.',
)

#: `\bigg{(}` вместо `\bigg(` — KaTeX отвечает
#: `Invalid delimiter type 'ordgroup'` (живые #53763, #53768). Это не
#: догадка про чужой макрос: `\big`-семейство — команды самого KaTeX,
#: и правильная форма их записи однозначна, поэтому правка законна по
#: правилу модуля («опечатки чиним, неизвестное не гадаем»).
_SIZED_DELIM_RE = re.compile(
    r'(\\[Bb]igg?[lrm]?)\s*\{\s*('
    + '|'.join(re.escape(d) for d in _DELIMITERS)
    + r')\s*\}'
)


def apply_macro_fixes(text):
    """Заменить известные опечатки макросов. Неизвестные не трогаются —
    их поймает шлюз кодом `MACRO`."""
    text = _FIX_RE.sub(lambda m: MACRO_FIXES[m.group(1)], text)
    return _SIZED_DELIM_RE.sub(r'\1\2', text)


def find_unresolved_macros(katex_error_messages):
    """Вытащить имена неизвестных команд из сообщений KaTeX.

    Единственный источник правды о том, что команда неизвестна, — сам
    KaTeX; список в модуле лишь поясняет находки человеку."""
    found = []
    for message in katex_error_messages:
        for match in re.finditer(r'Undefined control sequence:?\s*(\\[A-Za-z]+)', message):
            name = match.group(1)
            if name not in found:
                found.append(name)
    return found
