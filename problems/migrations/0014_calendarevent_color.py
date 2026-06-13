from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('problems', '0013_calendar_event'),
    ]

    operations = [
        migrations.AddField(
            model_name='calendarevent',
            name='color',
            field=models.CharField(
                blank=True,
                default='',
                max_length=7,
                verbose_name='Цвет (hex)',
            ),
        ),
    ]
