"""HR Open Standards interoperability endpoints.

    GET /api/hr/interop/competency-definitions/     (skill catalog)
    GET /api/hr/interop/person-competencies/        (rated skills, mgmt only)
    GET /api/hr/interop/position-competency-models/ (aggregated per org unit)

All list endpoints are paginated (``page`` / ``page_size``) and return the
HR-Open envelope (standard/version/data/links/meta). Errors use the shared
``errors`` array (400/403/404).
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from smarthr360_jwt_auth.access import has_manager_access, is_auditor

from ..models import Department, EmployeeProfile, EmployeeSkill, Skill
from . import HR_OPEN_PROFILE_VERSION, HR_OPEN_STANDARD
from .errors import bad_request, forbidden, not_found
from .mappers import (
    competency_definition,
    person_competency,
    position_competency_model,
)
from .pagination import HROpenPagination
from .serializers import (
    CompetencyDefinitionSerializer,
    PersonCompetencySerializer,
    PositionCompetencyModelSerializer,
)

_TAG = "Interoperability (HR Open)"


def _management_only(user):
    """True when the caller may read organisation-wide competency data."""
    return has_manager_access(user) or is_auditor(user)


class _HROpenListView(APIView):
    """Small base wiring HR-Open pagination onto a plain object list."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = HROpenPagination

    def paginate(self, request, mapped_items):
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(mapped_items, request, view=self)
        return paginator.get_paginated_response(page)


class CompetencyDefinitionsView(_HROpenListView):
    """Skill catalog exposed as HR-Open CompetencyDefinitions."""

    @extend_schema(
        summary="List competency definitions (HR Open)",
        description=(
            "Expose the SmartHR360 skill catalog as HR Open Standards "
            "CompetencyDefinitions. Paginated."
        ),
        parameters=[
            OpenApiParameter("category", str, description="Filter by category."),
            OpenApiParameter("active", bool, description="Filter by active flag."),
            OpenApiParameter("page", int),
            OpenApiParameter("page_size", int),
        ],
        responses={200: CompetencyDefinitionSerializer(many=True)},
        tags=[_TAG],
    )
    def get(self, request):
        skills = Skill.objects.all().order_by("code")

        category = request.query_params.get("category")
        if category:
            skills = skills.filter(category__iexact=category)

        active = request.query_params.get("active")
        if active is not None:
            if active.lower() not in {"true", "false", "1", "0"}:
                return bad_request(
                    "invalid_parameter", "active must be true or false."
                )
            skills = skills.filter(is_active=active.lower() in {"true", "1"})

        mapped = [competency_definition(s) for s in skills]
        return self.paginate(request, mapped)


class PersonCompetenciesView(_HROpenListView):
    """Employee skill assessments as HR-Open PersonCompetency records.

    Organisation-wide personal data: managers, HR, admins and auditors only.
    """

    @extend_schema(
        summary="List person competencies (HR Open)",
        description=(
            "Rated employee skills as HR Open PersonCompetency records, each "
            "with a CompetencyDimension (proficiency) and CompetencyEvidence "
            "(assessment). Management roles only."
        ),
        parameters=[
            OpenApiParameter("department", str, description="Department code filter."),
            OpenApiParameter("skill", str, description="Skill code filter."),
            OpenApiParameter("employee_id", int, description="Auth user id filter."),
            OpenApiParameter("page", int),
            OpenApiParameter("page_size", int),
        ],
        responses={200: PersonCompetencySerializer(many=True)},
        tags=[_TAG],
    )
    def get(self, request):
        if not _management_only(request.user):
            return forbidden("Manager, HR, Admin or Auditor role required.")

        qs = (
            EmployeeSkill.objects.select_related(
                "employee", "employee__department", "skill"
            )
            .filter(employee__is_active=True)
            .order_by("employee_id", "skill__code")
        )

        dept_code = request.query_params.get("department")
        if dept_code:
            department = Department.objects.filter(code__iexact=dept_code).first()
            if department is None:
                return not_found(
                    "department_not_found",
                    f"Unknown department code '{dept_code}'.",
                )
            qs = qs.filter(employee__department=department)

        skill_code = request.query_params.get("skill")
        if skill_code:
            qs = qs.filter(skill__code__iexact=skill_code)

        employee_id = request.query_params.get("employee_id")
        if employee_id:
            if not employee_id.isdigit():
                return bad_request(
                    "invalid_parameter", "employee_id must be an integer."
                )
            qs = qs.filter(employee__user_id=int(employee_id))

        mapped = [person_competency(es) for es in qs]
        return self.paginate(request, mapped)


class PositionCompetencyModelsView(APIView):
    """Aggregated competency model per organisation unit (department).

    Without ``department`` returns the model for every department; with it,
    a single model. Management roles only.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Position competency model (HR Open)",
        description=(
            "Aggregated department competencies (average proficiency, coverage, "
            "target gap) as HR Open PositionCompetencyModel(s)."
        ),
        parameters=[
            OpenApiParameter(
                "department", str, description="Restrict to one department code."
            )
        ],
        responses={200: PositionCompetencyModelSerializer(many=True)},
        tags=[_TAG],
    )
    def get(self, request):
        if not _management_only(request.user):
            return forbidden("Manager, HR, Admin or Auditor role required.")

        departments = Department.objects.all().order_by("code")
        dept_code = request.query_params.get("department")
        if dept_code:
            departments = departments.filter(code__iexact=dept_code)
            if not departments.exists():
                return not_found(
                    "department_not_found",
                    f"Unknown department code '{dept_code}'.",
                )

        models = [self._build_model(dep) for dep in departments]
        return Response(
            {
                "standard": HR_OPEN_STANDARD,
                "version": HR_OPEN_PROFILE_VERSION,
                "data": models,
                "meta": {"totalCount": len(models)},
            }
        )

    # -- aggregation (mirrors SkillMatrixView, reshaped to HR-Open) ------
    def _build_model(self, department) -> dict:
        profiles = EmployeeProfile.objects.filter(
            is_active=True, department=department
        )
        headcount = profiles.count()
        evaluations = EmployeeSkill.objects.filter(
            employee__in=profiles
        ).select_related("skill")

        buckets: dict[int, dict] = {}
        for ev in evaluations:
            skill = ev.skill
            b = buckets.setdefault(
                skill.id,
                {"skill": skill.name, "skill_code": skill.code, "levels": [], "targets": []},
            )
            b["levels"].append(ev.level)
            if ev.target_level:
                b["targets"].append(ev.target_level - ev.level)

        rows = [
            {
                "skill": b["skill"],
                "skill_code": b["skill_code"],
                "average_level": round(sum(b["levels"]) / len(b["levels"]), 2),
                "evaluated_count": len(b["levels"]),
                "coverage_percent": round(100 * len(b["levels"]) / headcount)
                if headcount else 0,
                "average_target_gap": round(sum(b["targets"]) / len(b["targets"]), 2)
                if b["targets"] else None,
            }
            for b in buckets.values()
        ]
        rows.sort(key=lambda r: -r["evaluated_count"])
        return position_competency_model(department.code, headcount, rows)
