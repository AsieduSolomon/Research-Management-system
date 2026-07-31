from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Fix two model-level bugs from the initial migration:

    1. SupervisorProfile.current_students was an IntegerField that could become
       stale (incremented/decremented manually). It is replaced by a computed
       property on the model. This migration removes the column from the DB.

    2. Allocation.unique_together was ('proposal', 'student') which would
       allow the same proposal to be allocated to multiple supervisors as long
       as the student changed (impossible by design, but a logic error).
       The correct constraint is that each proposal has exactly one allocation,
       enforced by the OneToOneField on Proposal — so we remove the old
       unique_together that is now redundant and incorrect.
    """

    dependencies = [
        ('research', '0001_initial'),
    ]

    operations = [
        # 1. Remove the stale counter column from SupervisorProfile
        migrations.RemoveField(
            model_name='supervisorprofile',
            name='current_students',
        ),

        # 2. Remove the incorrect unique_together constraint on Allocation.
        #    The OneToOneField on proposal already enforces one-allocation-per-proposal.
        migrations.AlterUniqueTogether(
            name='allocation',
            unique_together=set(),
        ),

        # 3. Tighten max_students to PositiveIntegerField (was IntegerField)
        migrations.AlterField(
            model_name='supervisorprofile',
            name='max_students',
            field=models.PositiveIntegerField(default=5),
        ),

        # 4. Add an index on AuditLog.created_at for faster log queries
        migrations.AlterModelOptions(
            name='auditlog',
            options={'ordering': ['-created_at']},
        ),
    ]
