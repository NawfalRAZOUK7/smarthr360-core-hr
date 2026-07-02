# wellbeing/schemas.py
"""
OpenAPI schema extensions for wellbeing endpoints.
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema

from .serializers import SurveySubmissionSerializer, WellbeingSurveySerializer

# Wellbeing Survey schemas
survey_list_create_schema = extend_schema(
    summary="List or create wellbeing surveys",
    description="GET: List all surveys. POST: Create new survey (HR/Admin only).",
    responses={
        200: OpenApiResponse(description="List of surveys", response=WellbeingSurveySerializer(many=True)),
        201: OpenApiResponse(description="Survey created", response=WellbeingSurveySerializer),
    },
    tags=["Wellbeing Surveys"],
    examples=[
        OpenApiExample(
            "Create Survey",
            value={
                "title": "Q1 2024 Employee Wellbeing Check",
                "description": "Quarterly survey to assess employee satisfaction and wellbeing",
                "is_active": True,
                "is_anonymous": True
            },
            request_only=True,
        ),
    ],
)

survey_detail_schema = extend_schema(
    summary="Retrieve, update, or delete survey",
    description="Manage individual survey. Update/Delete requires HR/Admin role.",
    responses={
        200: OpenApiResponse(description="Survey details", response=WellbeingSurveySerializer),
        204: OpenApiResponse(description="Survey deleted"),
    },
    tags=["Wellbeing Surveys"],
)

# Survey Response schemas
survey_response_list_create_schema = extend_schema(
    summary="List or submit survey responses",
    description="""
    GET: List survey responses:
    - HR/Admin: All responses
    - Employee: Own responses only
    
    POST: Submit a new survey response
    """,
    parameters=[
        OpenApiParameter(
            name="survey_id",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Filter responses by survey ID",
        ),
        OpenApiParameter(
            name="employee_id",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Filter responses by employee ID (HR/Admin only)",
        ),
    ],
    responses={
        200: OpenApiResponse(description="List of survey responses", response=SurveySubmissionSerializer),
        201: OpenApiResponse(description="Survey response submitted", response=SurveySubmissionSerializer),
    },
    tags=["Survey Responses"],
    examples=[
        OpenApiExample(
            "Submit Survey Response",
            value={
                "survey_id": 1,
                "work_life_balance": 4,
                "job_satisfaction": 5,
                "stress_level": 2,
                "management_support": 4,
                "team_collaboration": 5,
                "comments": "Very satisfied with the work environment and team dynamics"
            },
            request_only=True,
        ),
    ],
)

survey_response_detail_schema = extend_schema(
    summary="Retrieve, update, or delete survey response",
    description="Manage individual survey response. Access controlled by role and ownership.",
    responses={
        200: OpenApiResponse(description="Survey response details", response=SurveySubmissionSerializer),
        204: OpenApiResponse(description="Survey response deleted"),
    },
    tags=["Survey Responses"],
)

# Survey stats schema
survey_stats_schema = extend_schema(
    summary="Get survey statistics",
    description="""
    Get aggregated statistics for a specific survey including:
    - Average ratings for each metric
    - Total responses
    - Participation rate
    
    Requires HR/Admin role.
    """,
    parameters=[
        OpenApiParameter(
            name="survey_id",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH,
            description="Survey ID",
        ),
    ],
    responses={
        200: OpenApiResponse(
            description="Survey statistics",
            response={
                "type": "object",
                "properties": {
                    "survey_id": {"type": "integer"},
                    "total_responses": {"type": "integer"},
                    "averages": {
                        "type": "object",
                        "properties": {
                            "work_life_balance": {"type": "number"},
                            "job_satisfaction": {"type": "number"},
                            "stress_level": {"type": "number"},
                            "management_support": {"type": "number"},
                            "team_collaboration": {"type": "number"},
                        }
                    }
                }
            }
        ),
        403: OpenApiResponse(description="Permission denied - HR/Admin only"),
    },
    tags=["Wellbeing Surveys"],
)
