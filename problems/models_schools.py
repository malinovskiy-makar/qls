"""Справочник школ для подсказок онбординга «Где вы учитесь?» (раунд 2, 30.10.2026).

Отдельный файл по той же причине, что `models_social.py`: app_label `problems`, с
`models.py` связывает одна строка импорта в конце.

Заливается командой `manage.py load_schools <файл.csv>` (идемпотентно: повторная
заливка не плодит строк). Сам реестр в репозиторий не кладётся — он большой;
откуда брать и как залить на бою — `problems/data/README.md`.

⚠️ ЭТО НЕ ПРОФИЛЬ И НЕ ПЕРСОНАЛЬНЫЕ ДАННЫЕ: здесь только открытые сведения об
организациях (название, номер, город, регион). Что человек выбрал — пишется текстом в
`UserProfile.school`, как и раньше; ссылки на эту таблицу у профиля нет.
"""
from django.db import models


class School(models.Model):
    name = models.CharField('Название', max_length=300)
    short_name = models.CharField('Короткое название', max_length=200, blank=True, default='')
    #: Вид организации коротко («ГБОУ», «МАОУ») — вторая строка подсказки.
    kind = models.CharField('Вид', max_length=40, blank=True, default='')
    number = models.PositiveIntegerField('Номер', null=True, blank=True)
    city = models.CharField('Город', max_length=120)
    region = models.CharField('Регион', max_length=200, blank=True, default='')
    #: Город для поиска: нижний регистр, «ё» → «е» (`problems.school_search.norm`).
    city_norm = models.CharField(max_length=120, db_index=True, editable=False)

    class Meta:
        verbose_name = 'Школа (справочник)'
        verbose_name_plural = 'Школы (справочник)'
        constraints = [
            models.UniqueConstraint(fields=['name', 'city', 'region'],
                                    name='school_name_city_region_unique'),
        ]

    def save(self, *args, **kwargs):
        from problems.school_search import norm
        self.city_norm = norm(self.city)
        super().save(*args, **kwargs)

    def __str__(self):
        return '%s (%s)' % (self.short_name or self.name, self.city)
