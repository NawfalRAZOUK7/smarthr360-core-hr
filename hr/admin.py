from django.contrib import admin

from .models import (
    Department,
    EmployeeProfile,
    EmployeeProfileHistory,
    SkillGapForecast,
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ("user_id", "email", "job_title", "department", "employment_type", "is_active")
    list_filter = ("department", "employment_type", "is_active")
    search_fields = ("email", "first_name", "last_name", "job_title")


@admin.register(EmployeeProfileHistory)
class EmployeeProfileHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "version",
        "job_title",
        "department",
        "salary",
        "date_debut",
        "date_fin",
        "is_current",
        "change_reason",
    )
    list_filter = ("is_current", "source_system", "employment_type")
    search_fields = ("employee__email", "job_title", "change_reason")
    date_hierarchy = "date_debut"
    readonly_fields = tuple(f.name for f in EmployeeProfileHistory._meta.fields)


@admin.register(SkillGapForecast)
class SkillGapForecastAdmin(admin.ModelAdmin):
    list_display = (
        "department",
        "skill",
        "severity",
        "gap",
        "risk_score",
        "projected_level",
        "demand_level",
        "horizon_months",
        "generated_at",
    )
    list_filter = ("severity", "department", "horizon_months")
    search_fields = ("skill__code", "skill__name", "department__code", "run_id")
    date_hierarchy = "generated_at"
    readonly_fields = tuple(f.name for f in SkillGapForecast._meta.fields)
