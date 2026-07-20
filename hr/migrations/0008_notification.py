from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("hr", "0007_employeedocument")]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_id", models.PositiveBigIntegerField(db_index=True)),
                ("type", models.CharField(choices=[("TRAINING_ASSIGNED", "Training assigned"), ("REVIEW_DUE", "Review due"), ("RISK_FLAGGED", "Risk flagged"), ("OUTCOME_DUE", "Outcome due"), ("WELLBEING_FLAGGED", "Wellbeing flagged"), ("GENERIC", "Generic")], default="GENERIC", max_length=32)),
                ("title", models.CharField(max_length=200)),
                ("body", models.TextField(blank=True)),
                ("link", models.CharField(blank=True, max_length=500)),
                ("read", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("digest_sent_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["read", "-created_at"]},
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user_id", "read", "-created_at"], name="hr_notif_user_read_idx"),
        ),
    ]
