"""Справочник школ для подсказок онбординга «Где вы учитесь?» (раунд 2, 30.10.2026).

Отдельный файл по той же причине, что `models_social.py`: app_label `problems`, с
`models.py` связывает одна строка импорта в конце.

Заливается двумя путями:
* `manage.py load_schools <файл.csv>` — CSV руками (ключ — название + город + регион);
* `manage.py load_schools --format raoo <файл>` и `manage.py sync_schools` — реестр
  аккредитованных организаций Рособрнадзора (раунд 3, 29.10.2026; ключ — идентификатор
  организации в реестре, запасной — ИНН + КПП). Разборщик —
  `problems/school_registry.py`. Сам реестр в репозиторий не кладётся — он большой;
  откуда брать и как залить на бою — `problems/data/README.md`.

⚠️ ИСЧЕЗНУВШАЯ ИЗ РЕЕСТРА ШКОЛА НЕ УДАЛЯЕТСЯ, А ВЫКЛЮЧАЕТСЯ (`is_active=False`):
подсказки её больше не показывают, но и следующая синхронизация, и откат её видят.

⚠️ ЭТО НЕ ПРОФИЛЬ И НЕ ПЕРСОНАЛЬНЫЕ ДАННЫЕ: здесь только открытые сведения об
организациях (название, номер, город, регион, ИНН/КПП). ФИО директоров и контакты
из реестра не берутся. Что человек выбрал — пишется текстом в `UserProfile.school`,
как и раньше; ссылки на эту таблицу у профиля нет.
"""
from django.db import models
from django.db.models import Q


class School(models.Model):
    name = models.CharField('Название', max_length=300)
    #: Короткое название в человеческом виде («Школа № 57» вместо «ГБОУ Школа № 57
    #: г. Москвы») — его и показывает подсказка. Пусто — подсказка берёт `name`.
    short_name = models.CharField('Короткое название', max_length=200, blank=True, default='')
    #: Вид организации коротко («ГБОУ», «МАОУ») — из CSV; реестр его не заполняет.
    kind = models.CharField('Вид', max_length=40, blank=True, default='')
    number = models.PositiveIntegerField('Номер', null=True, blank=True)
    city = models.CharField('Город', max_length=120, blank=True)
    region = models.CharField('Регион', max_length=200, blank=True, default='')
    #: Город для поиска: нижний регистр, «ё» → «е» (`problems.school_search.norm`).
    city_norm = models.CharField(max_length=120, db_index=True, editable=False)
    #: Название для поиска (короткое и полное вместе), тот же `norm`.
    name_norm = models.CharField(max_length=520, blank=True, default='', editable=False)
    #: Идентификатор организации в реестре Рособрнадзора — ключ синхронизации.
    registry_id = models.CharField('Идентификатор в реестре', max_length=64, blank=True,
                                   default='', db_index=True)
    inn = models.CharField('ИНН', max_length=12, blank=True, default='')
    kpp = models.CharField('КПП', max_length=9, blank=True, default='')
    is_branch = models.BooleanField('Филиал', default=False)
    #: Выключена, если исчезла из реестра при синхронизации (не удаляется).
    is_active = models.BooleanField('Действует', default=True, db_index=True)

    class Meta:
        verbose_name = 'Школа (справочник)'
        verbose_name_plural = 'Школы (справочник)'
        constraints = [
            # Строки из CSV — по названию, городу и региону (как в раунде 2).
            models.UniqueConstraint(fields=['name', 'city', 'region'],
                                    condition=Q(registry_id=''),
                                    name='school_name_city_region_unique'),
            # Строки из реестра — по идентификатору: у двух сёл одного региона бывают
            # одинаковые названия и одинаково названные школы.
            models.UniqueConstraint(fields=['registry_id'], condition=~Q(registry_id=''),
                                    name='school_registry_id_unique'),
        ]

    def fill_norms(self):
        """`city_norm` и `name_norm` — для `bulk_create`/`bulk_update`, где `save()` нет."""
        from problems.school_search import norm
        self.city_norm = norm(self.city)
        self.name_norm = norm(' '.join(p for p in (self.short_name, self.name) if p))[:520]

    def save(self, *args, **kwargs):
        self.fill_norms()
        super().save(*args, **kwargs)

    @property
    def label(self):
        return self.short_name or self.name

    def __str__(self):
        return '%s (%s)' % (self.label, self.city)


class SchoolSyncRun(models.Model):
    """Журнал синхронизаций справочника школ с реестром (`manage.py sync_schools`).

    По последней удачной записи команда понимает, изменился ли файл реестра с прошлого
    раза (имя с датой и размер), и не качает 350 МБ впустую.
    """

    class Status(models.TextChoices):
        OK = 'ok', 'обновлено'
        SAME = 'same', 'файл не изменился'
        DRY = 'dry', 'сухой прогон'
        FAILED = 'failed', 'сбой, данные не тронуты'

    started_at = models.DateTimeField('Начало', auto_now_add=True)
    finished_at = models.DateTimeField('Конец', null=True, blank=True)
    status = models.CharField('Итог', max_length=10, choices=Status.choices)
    source = models.CharField('Файл реестра', max_length=200, blank=True, default='')
    content_length = models.BigIntegerField('Размер, байт', null=True, blank=True)
    total = models.PositiveIntegerField('Школ в файле', default=0)
    added = models.PositiveIntegerField('Добавлено', default=0)
    changed = models.PositiveIntegerField('Изменено', default=0)
    deactivated = models.PositiveIntegerField('Выключено', default=0)
    message = models.TextField('Подробности', blank=True, default='')

    class Meta:
        verbose_name = 'Синхронизация школ'
        verbose_name_plural = 'Синхронизации школ'
        ordering = ['-started_at']

    def __str__(self):
        return '%s · %s' % (self.started_at, self.get_status_display())
