# reviews/schemas.py
"""
OpenAPI schema extensions for review endpoints.
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema

from .serializers import (
    GoalSerializer,
    PerformanceReviewSerializer,
    ReviewCycleSerializer,
    ReviewItemSerializer,
)

# Review Cycle schemas
review_cycle_list_create_schema = extend_schema(
    summary="List or create review cycles",
    description="GET: List all review cycles. POST: Create new cycle (HR/Admin only).",
    responses={
        200: OpenApiResponse(description="List of review cycles", response=ReviewCycleSerializer(many=True)),
        201: OpenApiResponse(description="Review cycle created", response=ReviewCycleSerializer),
    },
    tags=["Review Cycles"],
    examples=[
        OpenApiExample(
            "Create Review Cycle",
            value={
                "name": "Q1 2024 Performance Review",
                "start_date": "2024-01-01",
                "end_date": "2024-03-31",
                "description": "First quarter performance review cycle"
            },
            request_only=True,
        ),
    ],
)

review_cycle_detail_schema = extend_schema(
    summary="Retrieve or update review cycle",
    description="Manage individual review cycle. Update requires HR/Admin role.",
    responses={
        200: OpenApiResponse(description="Review cycle details", response=ReviewCycleSerializer),
    },
    tags=["Review Cycles"],
)

# Performance Review schemas
performance_review_list_create_schema = extend_schema(
    summary="List or create performance reviews",
        description=(
            "GET: List reviews based on role:\n"
            "- HR/Admin: All reviews\n"
            "- Manager: Reviews for their team\n"
            "- Employee: Own reviews only\n"
            "\n"
            "POST: Create new review (Manager/HR/Admin only)"
        ),
    responses={
        200: OpenApiResponse(
            description="List of performance reviews",
            response=PerformanceReviewSerializer(many=True),
        ),
        201: OpenApiResponse(
            description="Performance review created",
            response=PerformanceReviewSerializer,
        ),
    },
    tags=["Performance Reviews"],
)

performance_review_detail_schema = extend_schema(
    summary="Retrieve, update, or delete performance review",
    description="Manage individual performance review. Access controlled by role and ownership.",
    responses={
        200: OpenApiResponse(description="Performance review details", response=PerformanceReviewSerializer),
        204: OpenApiResponse(description="Performance review deleted"),
    },
    tags=["Performance Reviews"],
)

# Review submission schemas
submit_review_schema = extend_schema(
    summary="Submit performance review",
        description=(
            "Submit a review for evaluation. Changes status to "
            "SUBMITTED."
        ),
    request=None,
    responses={
        200: OpenApiResponse(description="Review submitted successfully", response=PerformanceReviewSerializer),
        400: OpenApiResponse(description="Cannot submit - review already submitted or approved"),
    },
    tags=["Performance Reviews"],
)

approve_review_schema = extend_schema(
    summary="Approve performance review",
        description=(
            "Approve a submitted review. Requires HR/Admin role."
        ),
    request=None,
    responses={
        200: OpenApiResponse(description="Review approved successfully", response=PerformanceReviewSerializer),
        400: OpenApiResponse(description="Cannot approve - review not submitted"),
        403: OpenApiResponse(description="Permission denied - HR/Admin only"),
    },
    tags=["Performance Reviews"],
)

# Review Item schemas
review_item_list_schema = extend_schema(
    summary="List review items",
        description=(
            "List all items/ratings for a specific performance review."
        ),
    parameters=[
        OpenApiParameter(
            name="review_id",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH,
            description="Performance Review ID",
        ),
    ],
    responses={
        200: OpenApiResponse(description="List of review items", response=ReviewItemSerializer(many=True)),
    },
    tags=["Review Items"],
)

review_item_create_schema = extend_schema(
    summary="Add item to review",
    description="Add a new rating/competency item to a performance review.",
    request=ReviewItemSerializer,
    responses={
        201: OpenApiResponse(description="Review item created", response=ReviewItemSerializer),
    },
    tags=["Review Items"],
    examples=[
        OpenApiExample(
            "Create Review Item",
            value={
                "competency_name": "Communication Skills",
                "score": 4.0,
                "comments": "Excellent presentation and collaboration skills",
                "weight": 1.0
            },
            request_only=True,
        ),
    ],
)

review_item_detail_schema = extend_schema(
    summary="Update or delete review item",
    description="Manage individual review item ratings and comments.",
    responses={
        200: OpenApiResponse(description="Review item updated", response=ReviewItemSerializer),
        204: OpenApiResponse(description="Review item deleted"),
    },
    tags=["Review Items"],
)

# Goal schemas
goal_list_create_schema = extend_schema(
    summary="List or create goals",
    description="""
    GET: List goals based on role:
    - HR/Admin: All goals
    - Manager: Goals for their team
    - Employee: Own goals only
    
    POST: Create new goal (Manager/HR/Admin/Employee for self)
    """,
    parameters=[
        OpenApiParameter(
            name="employee_id",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Filter by employee ID",
        ),
        OpenApiParameter(
            name="status",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter by status (NOT_STARTED, IN_PROGRESS, COMPLETED, CANCELLED)",
        ),
    ],
    responses={
        200: OpenApiResponse(description="List of goals", response=GoalSerializer(many=True)),
        201: OpenApiResponse(description="Goal created", response=GoalSerializer),
    },
    tags=["Goals"],
)

goal_detail_schema = extend_schema(
    summary="Retrieve, update, or delete goal",
    description="Manage individual goal. Access controlled by role and ownership.",
    responses={
        200: OpenApiResponse(description="Goal details", response=GoalSerializer),
        204: OpenApiResponse(description="Goal deleted"),
    },
    tags=["Goals"],
)
