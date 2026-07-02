# reviews/admin.py
from django.contrib import admin

from .models import Goal, PerformanceReview, ReviewCycle, ReviewItem


@admin.register(ReviewCycle)
class ReviewCycleAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "is_active")
    list_filter = ("is_active", "start_date", "end_date")
    search_fields = ("name",)


class ReviewItemInline(admin.TabularInline):
    model = ReviewItem
    extra = 0


@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ("employee", "manager", "cycle", "status", "overall_score")
    list_filter = ("status", "cycle")
    search_fields = ("employee__email", "manager__email")
    inlines = [ReviewItemInline]


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("title", "employee", "cycle", "status", "progress_percent")
    list_filter = ("status", "cycle")
    search_fields = ("title", "employee__email")
