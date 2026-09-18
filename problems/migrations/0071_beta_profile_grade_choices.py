# Часть 3 из 3 (18.09.2026): класс — choices, плюс уровень подготовки.
"""Только структура — своей транзакцией, ПОСЛЕ коммита данных из 0070.

Контекст и причина разбивки — в docstring `0069_beta_profile_fields.py`.
К моменту этой миграции 0070 уже закоммичена: очередь отложенных событий
FK-триггера на `problems_userprofile` пуста, ALTER TABLE проходит.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('problems', '0070_beta_profile_grade_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='grade',
            field=models.CharField(blank=True, choices=[('le7', '7 класс и младше'), ('8', '8 класс'), ('9', '9 класс'), ('10', '10 класс'), ('11', '11 класс'), ('none', 'Уже не школьник')], default='', max_length=8, verbose_name='Класс'),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='level',
            field=models.CharField(blank=True, choices=[('novice', 'Ещё не участвовал'), ('basic', 'Школьный или муниципальный этап'), ('region', 'Региональный этап ВсОШ или отбор перечневой'), ('final', 'Заключительный этап ВсОШ или призёр перечневой')], help_text='Необязательно. Нужен, чтобы подбирать задачи по силам.', max_length=16, verbose_name='Уровень подготовки'),
        ),
    ]
