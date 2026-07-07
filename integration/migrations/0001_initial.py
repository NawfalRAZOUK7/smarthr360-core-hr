from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("hr", "0002_employeeprofile_erp_mdm_keys"),
    ]

    operations = [
        migrations.CreateModel(
            name="ERPSyncRun",
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
                ("source_system", models.CharField(max_length=32)),
                ("file_name", models.CharField(blank=True, max_length=255)),
                ("dry_run", models.BooleanField(default=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("RUNNING", "Running"),
                            ("SUCCESS", "Success"),
                            ("PARTIAL", "Partial (some records rejected)"),
                            ("FAILED", "Failed"),
                        ],
                        default="RUNNING",
                        max_length=10,
                    ),
                ),
                ("total_records", models.PositiveIntegerField(default=0)),
                ("created_count", models.PositiveIntegerField(default=0)),
                ("updated_count", models.PositiveIntegerField(default=0)),
                ("skipped_count", models.PositiveIntegerField(default=0)),
                ("error_count", models.PositiveIntegerField(default=0)),
                ("errors", models.JSONField(blank=True, default=list)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "triggered_by_user_id",
                    models.PositiveBigIntegerField(blank=True, null=True),
                ),
            ],
            options={
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="erpsyncrun",
            index=models.Index(
                fields=["source_system", "-started_at"],
                name="integration_src_started_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="erpsyncrun",
            index=models.Index(
                fields=["status"], name="integration_status_idx"
            ),
        ),
    ]
