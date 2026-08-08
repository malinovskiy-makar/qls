"""
Третий вариант видимости комментария — «заметка для себя».

⚠️ СУЩЕСТВУЮЩИЕ КОММЕНТАРИИ ОБЯЗАНЫ ОСТАТЬСЯ ВИДИМЫМИ ТЕМ ЖЕ ЛЮДЯМ.
Разбираем, кому на самом деле было видно каждое «private» до этой миграции
(правило было: автор + репетитор домашки + адресат):

* написал УЧЕНИК — видели он сам и репетитор. Смысл «личный вопрос
  преподавателю» сохраняется значением `private`. Не трогаем.
* написал РЕПЕТИТОР и указал АДРЕСАТА — видели он и этот ученик. Это ровно
  новое «видно только этому ученику». Не трогаем.
* написал РЕПЕТИТОР без адресата — не видел НИКТО, кроме него самого. Это и
  есть «заметка для себя», просто до сих пор у неё не было названия.
  Переводим в `self`: круг читателей тот же, а подпись перестаёт врать.

Обратная миграция возвращает такие записи в `private` — тот же круг людей.
"""
from django.db import migrations, models


def notes_to_self(apps, schema_editor):
    """Приватное репетитора без адресата → «заметка для себя»."""
    ProblemComment = apps.get_model('problems', 'ProblemComment')
    for comment in ProblemComment.objects.filter(visibility='private',
                                                 recipient__isnull=True):
        assignment = comment.assignment
        tutor_ids = {assignment.author_id}
        if assignment.group_id:
            tutor_ids.add(assignment.group.teacher_id)
        if comment.author_id in tutor_ids:
            comment.visibility = 'self'
            comment.save(update_fields=['visibility'])


def notes_back_to_private(apps, schema_editor):
    ProblemComment = apps.get_model('problems', 'ProblemComment')
    ProblemComment.objects.filter(visibility='self').update(
        visibility='private')


class Migration(migrations.Migration):

    dependencies = [
        ('problems', '0034_assignment_manual_order'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemcomment',
            name='visibility',
            field=models.CharField(choices=[('group', 'Видят все в группе'), ('private', 'Узкий круг: автор, репетитор, адресат'), ('self', 'Заметка автора для себя')], default='group', max_length=16, verbose_name='Видимость'),
        ),
        migrations.RunPython(notes_to_self, notes_back_to_private),
    ]
