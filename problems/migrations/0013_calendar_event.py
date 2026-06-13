from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('problems', '0012_student_group'),
    ]

    operations = [
        migrations.CreateModel(
            name='CalendarEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=300, verbose_name='Название')),
                ('event_type', models.CharField(
                    choices=[
                        ('lesson', 'Занятие'),
                        ('homework', 'Домашка'),
                        ('olympiad', 'Олимпиада'),
                        ('other', 'Другое'),
                    ],
                    default='lesson',
                    max_length=20,
                    verbose_name='Тип',
                )),
                ('start_datetime', models.DateTimeField(verbose_name='Начало')),
                ('end_datetime', models.DateTimeField(blank=True, null=True, verbose_name='Конец')),
                ('description', models.TextField(blank=True, verbose_name='Описание / ссылка')),
                ('is_global', models.BooleanField(default=False, verbose_name='Видно всем')),
                ('is_recurring', models.BooleanField(default=False, verbose_name='Повторяющееся')),
                ('recur_weeks', models.IntegerField(default=4, verbose_name='Повторений (недель)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('assignment', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='calendar_events',
                    to='problems.assignment',
                    verbose_name='Домашка',
                )),
                ('author', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='calendar_events',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Автор',
                )),
                ('groups', models.ManyToManyField(
                    blank=True,
                    related_name='calendar_events',
                    to='problems.studentgroup',
                    verbose_name='Группы',
                )),
                ('parent_event', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='recurrences',
                    to='problems.calendarevent',
                    verbose_name='Родительское событие',
                )),
            ],
            options={
                'verbose_name': 'Событие календаря',
                'verbose_name_plural': 'События календаря',
                'ordering': ['start_datetime'],
            },
        ),
    ]
