from django.contrib import admin

from .models import Department, EmployeeProfile


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ("user_id", "email", "job_title", "department", "employment_type", "is_active")
    list_filter = ("department", "employment_type", "is_active")
    search_fields = ("email", "first_name", "last_name", "job_title")
