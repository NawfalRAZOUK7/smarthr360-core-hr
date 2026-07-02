# hr/schemas.py
"""
OpenAPI schema extensions for HR endpoints.
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema

from .serializers import (
    DepartmentSerializer,
    EmployeeProfileSerializer,
    EmployeeSelfUpdateSerializer,
    EmployeeSkillSerializer,
    FutureCompetencySerializer,
    SkillSerializer,
)

# Department schemas
department_list_create_schema = extend_schema(
    summary="List or create departments",
    description="GET: List all departments. POST: Create a new department (HR only).",
    responses={
        200: OpenApiResponse(description="List of departments", response=DepartmentSerializer(many=True)),
        201: OpenApiResponse(description="Department created", response=DepartmentSerializer),
    },
    tags=["Departments"],
)

department_detail_schema = extend_schema(
    summary="Retrieve, update, or delete department",
    description="Manage individual department. Requires HR role.",
    responses={
        200: OpenApiResponse(description="Department details", response=DepartmentSerializer),
        204: OpenApiResponse(description="Department deleted"),
    },
    tags=["Departments"],
)

# Employee Me schemas
employee_me_get_schema = extend_schema(
    methods=["GET"],
    summary="Get current employee profile",
    description="Retrieve the employee profile of the currently authenticated user.",
    responses={
        200: OpenApiResponse(description="Employee profile", response=EmployeeProfileSerializer),
    },
    tags=["Employee Profile"],
)

employee_me_patch_schema = extend_schema(
    methods=["PATCH"],
    summary="Update current employee profile",
    description="Update the employee profile (limited fields for self-update).",
    request=EmployeeSelfUpdateSerializer,
    responses={
        200: OpenApiResponse(description="Profile updated", response=EmployeeProfileSerializer),
    },
    tags=["Employee Profile"],
)

# Employee list schemas
employee_list_schema = extend_schema(
    summary="List or create employees",
    description="GET: List all employees with optional filters. POST: Create employee (HR only).",
    parameters=[
        OpenApiParameter(
            name="department",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter by department code (e.g., 'IT', 'HR')",
        ),
        OpenApiParameter(
            name="is_active",
            type=OpenApiTypes.BOOL,
            location=OpenApiParameter.QUERY,
            description="Filter by active status (true/false)",
        ),
        OpenApiParameter(
            name="role",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter by user role (EMPLOYEE, MANAGER, HR, ADMIN)",
        ),
        OpenApiParameter(
            name="hired_after",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description="Filter employees hired after this date (YYYY-MM-DD)",
        ),
        OpenApiParameter(
            name="search",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Search in first_name, last_name, email (case-insensitive)",
        ),
    ],
    responses={
        200: OpenApiResponse(description="List of employees", response=EmployeeProfileSerializer(many=True)),
        201: OpenApiResponse(description="Employee created", response=EmployeeProfileSerializer),
    },
    tags=["Employee Management"],
)

employee_detail_schema = extend_schema(
    summary="Retrieve, update, or delete employee",
    description="Manage individual employee profile. Requires appropriate permissions.",
    responses={
        200: OpenApiResponse(description="Employee details", response=EmployeeProfileSerializer),
        204: OpenApiResponse(description="Employee deleted"),
    },
    tags=["Employee Management"],
)

# Skill schemas
skill_list_create_schema = extend_schema(
    summary="List or create skills",
    description="GET: List all skills. POST: Create a new skill (HR only).",
    responses={
        200: OpenApiResponse(description="List of skills", response=SkillSerializer(many=True)),
        201: OpenApiResponse(description="Skill created", response=SkillSerializer),
    },
    tags=["Skills"],
    examples=[
        OpenApiExample(
            "Create Skill",
            value={
                "name": "Python Programming",
                "category": "Technical",
                "description": "Proficiency in Python programming language"
            },
            request_only=True,
        ),
    ],
)

skill_detail_schema = extend_schema(
    summary="Retrieve, update, or delete skill",
    description="Manage individual skill. Requires HR role.",
    responses={
        200: OpenApiResponse(description="Skill details", response=SkillSerializer),
        204: OpenApiResponse(description="Skill deleted"),
    },
    tags=["Skills"],
)

# Employee Skill schemas
employee_skill_list_schema = extend_schema(
    summary="List employee skills",
    description="List all skills for a specific employee with proficiency levels.",
    parameters=[
        OpenApiParameter(
            name="employee_id",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH,
            description="Employee ID",
        ),
    ],
    responses={
        200: OpenApiResponse(description="List of employee skills", response=EmployeeSkillSerializer(many=True)),
    },
    tags=["Employee Skills"],
)

employee_skill_create_schema = extend_schema(
    summary="Add skill to employee",
    description="Associate a skill with an employee and set proficiency level.",
    request=EmployeeSkillSerializer,
    responses={
        201: OpenApiResponse(description="Skill added to employee", response=EmployeeSkillSerializer),
    },
    tags=["Employee Skills"],
    examples=[
        OpenApiExample(
            "Add Employee Skill",
            value={
                "skill_id": 1,
                "proficiency_level": "INTERMEDIATE",
                "notes": "Completed Python certification"
            },
            request_only=True,
        ),
    ],
)

employee_skill_update_delete_schema = extend_schema(
    summary="Update or delete employee skill",
    description="Update proficiency level or remove a skill from an employee.",
    responses={
        200: OpenApiResponse(description="Employee skill updated", response=EmployeeSkillSerializer),
        204: OpenApiResponse(description="Employee skill deleted"),
    },
    tags=["Employee Skills"],
)

# Future Competency schemas
future_competency_list_create_schema = extend_schema(
    summary="List or create future competencies",
    description="GET: List all future competencies. POST: Create new competency (HR only).",
    responses={
        200: OpenApiResponse(description="List of competencies", response=FutureCompetencySerializer(many=True)),
        201: OpenApiResponse(description="Competency created", response=FutureCompetencySerializer),
    },
    tags=["Future Competencies"],
)

future_competency_detail_schema = extend_schema(
    summary="Retrieve, update, or delete future competency",
    description="Manage individual future competency. Requires HR role.",
    responses={
        200: OpenApiResponse(description="Competency details", response=FutureCompetencySerializer),
        204: OpenApiResponse(description="Competency deleted"),
    },
    tags=["Future Competencies"],
)
