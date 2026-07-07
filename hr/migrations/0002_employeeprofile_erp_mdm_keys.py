"""ERP/EAI integration: add MDM federation keys to EmployeeProfile.

- `external_employee_id` + `source_system`: natural key used by the ERP
  connector (integration app) for idempotent upserts.
- `user_id` becomes nullable so employees can be ingested from an ERP before
  an auth account exists (identity is still by-value, no cross-service FK).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="employeeprofile",
            name="user_id",
            field=models.PositiveBigIntegerField(
                blank=True, null=True, unique=True, db_index=True
            ),
        ),
        migrations.AddField(
            model_name="employeeprofile",
            name="external_employee_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Employee id/matricule in the source ERP (SAP PERNR, Odoo id...).",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="employeeprofile",
            name="source_system",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Origin system of the record, e.g. 'ODOO', 'SAP', 'MANUAL'.",
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="employeeprofile",
            constraint=models.UniqueConstraint(
                condition=models.Q(("external_employee_id", ""), _negated=True),
                fields=("source_system", "external_employee_id"),
                name="uniq_employee_source_external_id",
            ),
        ),
    ]
