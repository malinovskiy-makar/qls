"""Существующие подсказки — рукописные: помечаем их проверенными человеком.

Поля `generated_by_ai` и `reviewed` появились в 0052 с default=False. Всё,
что лежало в базе до этого, писал человек, и показывать таким подсказкам
строку «сгенерировано ИИ, не проверено человеком» было бы неправдой.

Откат — noop: при откате 0052 поля исчезают вместе со значениями, а
возвращать флаг в False нечего и незачем.
"""
from django.db import migrations


def mark_reviewed(apps, schema_editor):
    Hint = apps.get_model('problems', 'Hint')
    Hint.objects.filter(generated_by_ai=False).update(reviewed=True)


class Migration(migrations.Migration):

    dependencies = [
        ('problems', '0052_hint_ai_flags'),
    ]

    operations = [
        migrations.RunPython(mark_reviewed, migrations.RunPython.noop),
    ]
