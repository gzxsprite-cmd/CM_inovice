from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("invoice", "0003_work_year_month"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CM", "CM"),
                    ("LCM", "LCM"),
                    ("HOD", "HoD"),
                    ("ADMIN", "Admin"),
                ],
                max_length=10,
                null=True,
            ),
        ),
    ]
