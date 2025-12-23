from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def populate_work_year_month(apps, schema_editor):
    Work = apps.get_model("invoice", "Work")
    for work in Work.objects.all():
        value = work.work_month
        if not value:
            continue
        if isinstance(value, str):
            parts = value.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                year = int(parts[0])
                month = int(parts[1])
                if 1000 <= year <= 9999 and 1 <= month <= 12:
                    work.work_year = year
                    work.work_month_num = month
                    work.save(update_fields=["work_year", "work_month_num"])


class Migration(migrations.Migration):

    dependencies = [
        ("invoice", "0002_work_month"),
    ]

    operations = [
        migrations.AddField(
            model_name="work",
            name="work_year",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="work",
            name="work_month_num",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(populate_work_year_month, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="work",
            name="work_year",
            field=models.PositiveSmallIntegerField(
                validators=[MinValueValidator(1000), MaxValueValidator(9999)]
            ),
        ),
        migrations.AlterField(
            model_name="work",
            name="work_month_num",
            field=models.PositiveSmallIntegerField(
                validators=[MinValueValidator(1), MaxValueValidator(12)]
            ),
        ),
        migrations.RemoveConstraint(
            model_name="work",
            name="uniq_work_customer_month",
        ),
        migrations.RemoveField(
            model_name="work",
            name="work_month",
        ),
        migrations.RenameField(
            model_name="work",
            old_name="work_month_num",
            new_name="work_month",
        ),
        migrations.AddConstraint(
            model_name="work",
            constraint=models.UniqueConstraint(
                fields=("customer", "work_year", "work_month"),
                name="uniq_work_customer_year_month",
            ),
        ),
    ]
