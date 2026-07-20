# reviews/serializers.py
from rest_framework import serializers

from .models import Goal, PerformanceReview, ReviewCycle, ReviewItem


class ReviewCycleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewCycle
        fields = [
            "id",
            "name",
            "start_date",
            "end_date",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class ReviewItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewItem
        fields = [
            "id",
            "criteria",
            "score",
            "comment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class PerformanceReviewSerializer(serializers.ModelSerializer):
    """
    Main serializer for performance reviews.
    - accepts employee_id, cycle_id on create
    - returns minimal nested employee, manager, cycle, items on read
    """

    employee_id = serializers.IntegerField(write_only=True, required=False)
    cycle_id = serializers.IntegerField(write_only=True, required=False)

    employee = serializers.SerializerMethodField(read_only=True)
    manager = serializers.SerializerMethodField(read_only=True)
    cycle = ReviewCycleSerializer(read_only=True)
    items = ReviewItemSerializer(many=True, read_only=True)

    class Meta:
        model = PerformanceReview
        fields = [
            "id",
            "employee_id",
            "cycle_id",
            "employee",
            "manager",
            "cycle",
            "status",
            "overall_score",
            "employee_comment",
            "manager_comment",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "status",
            "overall_score",
            "employee",
            "manager",
            "cycle",
            "items",
            "created_at",
            "updated_at",
        ]

    def get_employee(self, obj):
        # minimal nested employee representation (id + identity snapshot +
        # department name). Identity fields are denormalized on the profile.
        emp = obj.employee
        return {
            "id": emp.id,
            "user": {
                "id": emp.user_id,
                "email": emp.email,
                "first_name": emp.first_name,
                "last_name": emp.last_name,
            },
            "department": emp.department.name if emp.department else None,
        }

    def get_manager(self, obj):
        mgr = obj.manager
        if not mgr:
            return None
        return {
            "id": mgr.id,
            "user": {
                "id": mgr.user_id,
                "email": mgr.email,
                "first_name": mgr.first_name,
                "last_name": mgr.last_name,
            },
        }


class GoalSerializer(serializers.ModelSerializer):
    """
    Goals linked to an employee and optionally a cycle.

    - accepts employee_id, cycle_id on create
    - returns minimal nested employee + cycle on read
    """

    employee_id = serializers.IntegerField(write_only=True, required=False)
    cycle_id = serializers.IntegerField(write_only=True, required=False)
    source_review_id = serializers.PrimaryKeyRelatedField(
        source="source_review", queryset=PerformanceReview.objects.all(),
        write_only=True, required=False, allow_null=True,
    )

    employee = serializers.SerializerMethodField(read_only=True)
    cycle = ReviewCycleSerializer(read_only=True)
    training_actions_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Goal
        fields = [
            "id",
            "employee_id",
            "cycle_id",
            "source_review_id",
            "employee",
            "cycle",
            "title",
            "description",
            "status",
            "progress_percent",
            "training_actions_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "employee",
            "cycle",
            "created_at",
            "updated_at",
        ]

    def get_employee(self, obj):
        emp = obj.employee
        return {
            "id": emp.id,
            "user": {
                "id": emp.user_id,
                "email": emp.email,
                "first_name": emp.first_name,
                "last_name": emp.last_name,
            },
        }

    def get_training_actions_count(self, obj):
        return obj.training_actions.count()
