"""Staging validation for incoming ERP records.

Adapters guarantee the *shape* (canonical dict); this serializer guarantees the
*content* is safe to persist: value domains (roles, employment types), date
formats, field lengths and required natural keys. Nothing is written to the DB
until a record passes validation — this is the data-quality gate of the EAI
pipeline.
"""

from __future__ import annotations

from rest_framework import serializers

from hr.models import EmployeeProfile

_ROLES = {c[0] for c in EmployeeProfile.UserRole.choices}
_EMP_TYPES = {c[0] for c in EmployeeProfile.EmploymentType.choices}


class ERPEmployeeStagingSerializer(serializers.Serializer):
    """Validate one canonical employee record before upsert."""

    external_employee_id = serializers.CharField(max_length=64)
    source_system = serializers.CharField(max_length=32)

    email = serializers.EmailField(required=False, allow_blank=True, default="")
    first_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    last_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    user_role = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default="EMPLOYEE"
    )
    department_code = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )
    department_name = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    job_title = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    employment_type = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default="FULL_TIME"
    )
    hire_date = serializers.DateField(required=False, allow_null=True, default=None)
    phone_number = serializers.CharField(
        max_length=30, required=False, allow_blank=True, default=""
    )
    is_active = serializers.BooleanField(required=False, default=True)
    manager_external_id = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default=""
    )
    user_id = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, default=None
    )

    # -- normalising validators ----------------------------------------
    def validate_user_role(self, value):
        value = (value or "EMPLOYEE").strip().upper()
        if value not in _ROLES:
            raise serializers.ValidationError(
                f"invalid role '{value}', expected one of {sorted(_ROLES)}"
            )
        return value

    def validate_employment_type(self, value):
        value = (value or "FULL_TIME").strip().upper()
        if value not in _EMP_TYPES:
            raise serializers.ValidationError(
                f"invalid employment_type '{value}', expected one of {sorted(_EMP_TYPES)}"
            )
        return value

    def validate_external_employee_id(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("external_employee_id is required")
        return value
