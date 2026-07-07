from django.contrib import admin

from .models import ERPSyncRun


@admin.register(ERPSyncRun)
class ERPSyncRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source_system",
        "status",
        "total_records",
        "created_count",
        "updated_count",
        "skipped_count",
        "error_count",
        "dry_run",
        "started_at",
    )
    list_filter = ("source_system", "status", "dry_run")
    search_fields = ("file_name",)
    readonly_fields = tuple(f.name for f in ERPSyncRun._meta.fields)
    date_hierarchy = "started_at"
