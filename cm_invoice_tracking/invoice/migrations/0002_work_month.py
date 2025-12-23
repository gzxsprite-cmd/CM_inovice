from django.core.validators import RegexValidator
from django.db import migrations, models


def populate_work_month(apps, schema_editor):
    Work = apps.get_model("invoice", "Work")
    for work in Work.objects.all():
        if work.period_year is not None and work.period_month is not None:
            work.work_month = "{}-{:02d}".format(work.period_year, work.period_month)
            work.save(update_fields=["work_month"])


class Migration(migrations.Migration):

    dependencies = [
        ("invoice", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="work",
            name="work_month",
            field=models.CharField(
                blank=True,
                max_length=7,
                null=True,
                validators=[
                    RegexValidator(
                        regex=r"^\d{4}-(0[1-9]|1[0-2])$",
                        message="work_month must be in YYYY-MM format.",
                    )
                ],
            ),
        ),
        migrations.RunPython(populate_work_month, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="work",
            name="work_month",
            field=models.CharField(
                max_length=7,
                validators=[
                    RegexValidator(
                        regex=r"^\d{4}-(0[1-9]|1[0-2])$",
                        message="work_month must be in YYYY-MM format.",
                    )
                ],
            ),
        ),
        migrations.RemoveConstraint(
            model_name="work",
            name="unique_work_period",
        ),
        migrations.AddConstraint(
            model_name="work",
            constraint=models.UniqueConstraint(
                fields=("customer", "work_month"),
                name="uniq_work_customer_month",
            ),
        ),
        migrations.RemoveField(
            model_name="work",
            name="period_year",
        ),
        migrations.RemoveField(
            model_name="work",
            name="period_month",
        ),
    ]
