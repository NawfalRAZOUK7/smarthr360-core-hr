"""Skill-gap prediction (Étape 4): persist forecasts for BI / decision support."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr", "0003_salary_and_employeeprofilehistory"),
    ]

    operations = [
        migrations.CreateModel(
            name="SkillGapForecast",
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
                ("horizon_months", models.PositiveSmallIntegerField(default=6)),
                ("current_avg_level", models.FloatField()),
                ("velocity_per_month", models.FloatField()),
                ("projected_level", models.FloatField()),
                ("demand_level", models.FloatField()),
                ("gap", models.FloatField()),
                ("coverage", models.FloatField()),
                ("attrition_rate", models.FloatField(default=0.0)),
                ("importance", models.PositiveSmallIntegerField(default=3)),
                ("risk_score", models.FloatField()),
                (
                    "severity",
                    models.CharField(
                        choices=[
                            ("LOW", "Low"),
                            ("MEDIUM", "Medium"),
                            ("HIGH", "High"),
                        ],
                        max_length=6,
                    ),
                ),
                ("rationale", models.TextField(blank=True)),
                ("run_id", models.CharField(db_index=True, max_length=36)),
                ("generated_at", models.DateTimeField(auto_now_add=True)),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="skill_gap_forecasts",
                        to="hr.department",
                    ),
                ),
                (
                    "skill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="skill_gap_forecasts",
                        to="hr.skill",
                    ),
                ),
            ],
            options={
                "ordering": ["-generated_at", "-risk_score"],
            },
        ),
        migrations.AddIndex(
            model_name="skillgapforecast",
            index=models.Index(
                fields=["department", "skill", "-generated_at"],
                name="hr_gap_dept_skill_gen_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="skillgapforecast",
            index=models.Index(fields=["run_id"], name="hr_gap_run_idx"),
        ),
        migrations.AddIndex(
            model_name="skillgapforecast",
            index=models.Index(fields=["severity"], name="hr_gap_severity_idx"),
        ),
    ]
