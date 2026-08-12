"""
Тип занятия: группа или один на один (сессия 9, фаза 9).

Всем существующим занятиям проставляется `group` — умолчанием поля, так что
отдельного шага данных не нужно: до этой сессии индивидуальных занятий в
продукте не было вовсе.

⚠️ Тип — ПОЛЕ, а не вычисление из числа учеников. Обоснование целиком — в
докстринге `StudentGroup`.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('problems', '0038_custom_problem_parts'),
    ]

    operations = [
        migrations.AddField(
            model_name='studentgroup',
            name='kind',
            field=models.CharField(choices=[('group', 'Группа'), ('individual', 'Индивидуально')], db_index=True, default='group', max_length=16, verbose_name='Тип занятия'),
        ),
    ]
