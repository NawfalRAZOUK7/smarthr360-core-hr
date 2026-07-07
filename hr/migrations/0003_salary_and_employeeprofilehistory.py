"""SCD Type 2 historization (Étape 2).

- add EmployeeProfile.salary (tracked historically)
- create EmployeeProfileHistory with a validity window (date_debut/date_fin),
  version, is_current flag and provenance, plus constraints guaranteeing at
  most one open row per employee and unique versions.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr", "0002_employeeprofile_erp_mdm_keys"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeeprofile",
            name="salary",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Current monthly gross salary. Changes are historized (SCD2).",
                max_digits=12,
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="EmployeeProfileHistory",
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
                ("manager_id_snapshot", models.PositiveBigIntegerField(blank=True, null=True)),
                ("job_title", models.CharField(blank=True, max_length=150)),
                ("employment_type", models.CharField(blank=True, max_length=20)),
                ("user_role", models.CharField(blank=True, max_length=20)),
                (
                    "salary",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=12, null=True
                    ),
                ),
                ("is_employment_active", models.BooleanField(default=True)),
                ("version", models.PositiveIntegerField(default=1)),
                ("date_debut", models.DateTimeField(db_index=True)),
                ("date_fin", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("is_current", models.BooleanField(default=True)),
                ("change_reason", models.CharField(blank=True, max_length=255)),
                ("changed_by_user_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("source_system", models.CharField(blank=True, max_length=32)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "department",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="hr.department",
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="history",
                        to="hr.employeeprofile",
                    ),
                ),
            ],
            options={
                "verbose_name": "Employee history (SCD2)",
                "verbose_name_plural": "Employee history (SCD2)",
                "ordering": ["employee_id", "-date_debut"],
            },
        ),
        migrations.AddIndex(
            model_name="employeeprofilehistory",
            index=models.Index(
                fields=["employee", "is_current"], name="hr_emphist_emp_curr_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="employeeprofilehistory",
            index=models.Index(
                fields=["employee", "date_debut", "date_fin"],
                name="hr_emphist_emp_window_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="employeeprofilehistory",
            constraint=models.UniqueConstraint(
                condition=models.Q(("date_fin__isnull", True)),
                fields=("employee",),
                name="uniq_open_history_per_employee",
            ),
        ),
        migrations.AddConstraint(
            model_name="employeeprofilehistory",
            constraint=models.UniqueConstraint(
                fields=("employee", "version"),
                name="uniq_history_version_per_employee",
            ),
        ),
    ]
