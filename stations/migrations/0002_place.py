from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Place",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                ("state", models.CharField(max_length=2)),
                ("lookup_key", models.CharField(max_length=120)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("state", "lookup_key"), name="unique_place_lookup"
                    )
                ],
            },
        ),
    ]
