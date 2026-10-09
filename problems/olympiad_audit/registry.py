# -*- coding: utf-8 -*-
"""Реестр олимпиад, которые прошли аудит по официальному эталону.

Одна запись — всё, что команды аудита (`apply_olympiad_audit`,
`olympiad_official_sources`, `olympiad_digitize`) знают про олимпиаду:
название в строках `OlympiadRef`, официальный `Source`, допустимые этапы,
префикс `event_id` эталона, папка аудита в `weconomics-data\\olympiads`.

Команды требуют `--olympiad <слаг>` явно: умолчание «ВП» однажды записало
бы МОШ под чужим названием и в чужой `Source`.

⚠️ Название — КАК У УЖЕ ЗАПИСАННЫХ СТРОК этого слага (сверено по базе
09.10.2026): одна олимпиада под двумя названиями ломает фильтры каталога.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OlympiadAudit:
    slug: str
    #: Название в `OlympiadRef.olympiad_name` — как у существующих строк.
    olympiad_name: str
    #: `Source` для заданий, импортированных из официальных PDF.
    official_source_name: str
    official_source_defaults: dict = field(default_factory=dict)
    official_site: str = ''
    #: Хосты официальных файлов: ссылка с них — не ссылка агрегатора.
    official_hosts: tuple = ()
    #: Этапы, которые пишутся в `OlympiadRef.stage` (порядок не важен).
    stages: tuple = ('final',)
    #: Префикс `event_id` эталона: `vp-2020-final-10-v1`, `mosh-2015-final-8-9-day2`.
    event_prefix: str = ''
    #: Папка аудита в `weconomics-data\olympiads`.
    audit_dir: str = ''
    #: Слаги одной олимпиады: строка любого из них — «та же олимпиада»
    #: (вторая строка того же тура не заводится).
    family: tuple = ()
    #: Метка сессии в `raw_meta['session']` новых строк и правок.
    session: str = ''
    #: Кто проверил «высокий» ярус по тексту (`raw_meta['reviewed_by']`).
    reviewed_by: str = ''
    #: Папка журналов записи — рядом с папкой входного файла.
    journal_dir: str = 'session3'
    #: Сравнение текста: `norm` — `normalize_for_compare` (ВП, банк и PDF
    #: одной вёрстки), `markup_free` — ключ без LaTeX и пунктуации (МОШ:
    #: банк в LaTeX, PDF простым текстом; на `norm` копии падали до 0,73).
    compare: str = 'norm'

    @property
    def multi_stage(self):
        return len(self.stages) > 1


_VP_SOURCE_DEFAULTS = {
    'author': 'НИУ «Высшая школа экономики»',
    'kind': 'олимпиада',
    'note': ('Официальные задания и решения заключительного этапа олимпиады '
             '«Высшая проба» по экономике, опубликованные организатором: '
             'https://olymp.hse.ru/mmo/tasks-eco. У каждой задачи — ссылка '
             'на PDF в привязке к источнику.'),
}

_VP_COMMON = dict(
    official_source_name='Высшая проба: официальный архив',
    official_source_defaults=_VP_SOURCE_DEFAULTS,
    official_site='https://olymp.hse.ru/mmo/',
    official_hosts=('hse.ru',),
    stages=('final',),
    event_prefix='vp-',
    audit_dir='audit_vp_20261008',
    family=('vp', 'vp-fingram', 'vp-ob'),
    session='vp3',
    reviewed_by='claude-chat-20261008',
    journal_dir='session3',
    compare='norm',
)

REGISTRY = {
    'vp': OlympiadAudit(
        slug='vp',
        olympiad_name='Олимпиада школьников «Высшая проба» по экономике',
        **_VP_COMMON),
    'vp-fingram': OlympiadAudit(
        slug='vp-fingram',
        olympiad_name='Олимпиада школьников «Высшая проба» по финансовой грамотности',
        **_VP_COMMON),
    'vp-ob': OlympiadAudit(
        slug='vp-ob',
        olympiad_name='Олимпиада школьников «Высшая проба» по основам бизнеса',
        **_VP_COMMON),
    'mosh': OlympiadAudit(
        slug='mosh',
        olympiad_name='Московская олимпиада школьников по экономике',
        official_source_name=('Московская олимпиада школьников по экономике: '
                              'официальный архив'),
        official_source_defaults={
            'author': 'Оргкомитет Московской олимпиады школьников по экономике',
            'kind': 'олимпиада',
            'note': ('Официальные задания, решения и критерии отборочного и '
                     'заключительного этапов Московской олимпиады школьников '
                     'по экономике: https://mosecon.olimpiada.ru/arch_tasks и '
                     'https://mos.olimpiada.ru (архив заданий). У каждой '
                     'задачи — ссылка на PDF в привязке к источнику.'),
        },
        official_site='https://mosecon.olimpiada.ru/',
        official_hosts=('olimpiada.ru',),
        stages=('qualifying', 'final'),
        event_prefix='mosh-',
        audit_dir='audit_mosh_20261009',
        family=('mosh',),
        session='mosh2',
        reviewed_by='claude-chat-20261009',
        journal_dir='session2',
        compare='markup_free',
    ),
}

#: Слаги ВП — для мест, где порядок «семья ВП» нужен по старому имени.
VP_FAMILY = REGISTRY['vp'].family


def get(slug):
    """Запись реестра по слагу; неизвестный слаг — `KeyError` со списком."""
    try:
        return REGISTRY[slug]
    except KeyError:
        raise KeyError(f'олимпиады {slug!r} нет в реестре аудита; есть: '
                       f'{", ".join(sorted(REGISTRY))}') from None


def official_source_names():
    """Все официальные `Source` реестра (без повторов, порядок реестра)."""
    seen = []
    for entry in REGISTRY.values():
        if entry.official_source_name not in seen:
            seen.append(entry.official_source_name)
    return seen
