from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('research', '0002_fix_models'),
    ]

    operations = [
        migrations.CreateModel(
            name='SupervisorNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('allocation', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='supervisor_notes',
                    to='research.allocation',
                )),
                ('supervisor', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notes_written',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
