"""Organization views: org chart, department skill matrix, CSV export."""

from __future__ import annotations

import csv

from django.http import HttpResponse
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from smarthr360_jwt_auth.access import has_hr_access, has_manager_access, is_auditor

from config.api_mixins import ApiResponseMixin

from .models import Department, EmployeeProfile, EmployeeSkill


class OrgChartView(ApiResponseMixin, APIView):
    """GET /api/hr/org-chart/ — the reporting tree (visible to everyone).

    Roots are profiles without a manager; each node carries display
    info and its direct reports.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profiles = list(
            EmployeeProfile.objects.filter(is_active=True)
            .select_related("department")
        )
        children: dict[int | None, list] = {}
        for profile in profiles:
            children.setdefault(profile.manager_id, []).append(profile)

        def node(profile):
            name = f"{profile.first_name} {profile.last_name}".strip()
            return {
                "id": profile.id,
                "user_id": profile.user_id,
                "name": name or profile.email or f"user-{profile.user_id}",
                "job_title": profile.job_title,
                "department": profile.department.code
                if profile.department else None,
                "reports": [
                    node(child) for child in children.get(profile.id, [])
                ],
            }

        return Response(
            {
                "headcount": len(profiles),
                "roots": [node(p) for p in children.get(None, [])],
            }
        )


class SkillMatrixView(ApiResponseMixin, APIView):
    """GET /api/hr/skill-matrix/?department=ENG — aggregated skill levels.

    Per skill: average level, evaluated headcount and coverage of the
    (department's) active employees. Managers/HR/auditors only —
    this is a management dashboard, not employee-facing data.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not (has_manager_access(user) or is_auditor(user)):
            raise PermissionDenied("Manager, HR, Admin or Auditor role required.")

        profiles = EmployeeProfile.objects.filter(is_active=True)
        department_code = request.query_params.get("department")
        department = None
        if department_code:
            department = Department.objects.filter(
                code__iexact=department_code
            ).first()
            if department is None:
                return Response(
                    {"detail": f"Unknown department code '{department_code}'."},
                    status=404,
                )
            profiles = profiles.filter(department=department)

        headcount = profiles.count()
        evaluations = (
            EmployeeSkill.objects.filter(employee__in=profiles)
            .select_related("skill")
        )

        per_skill: dict[int, dict] = {}
        for evaluation in evaluations:
            skill = evaluation.skill
            bucket = per_skill.setdefault(
                skill.id,
                {"skill": skill.name, "skill_code": skill.code,
                 "levels": [], "targets": []},
            )
            bucket["levels"].append(evaluation.level)
            if evaluation.target_level:
                bucket["targets"].append(
                    evaluation.target_level - evaluation.level
                )

        matrix = [
            {
                "skill": b["skill"],
                "skill_code": b["skill_code"],
                "average_level": round(sum(b["levels"]) / len(b["levels"]), 2),
                "evaluated_count": len(b["levels"]),
                "coverage_percent": round(100 * len(b["levels"]) / headcount)
                if headcount else 0,
                "average_target_gap": round(
                    sum(b["targets"]) / len(b["targets"]), 2
                ) if b["targets"] else None,
            }
            for b in per_skill.values()
        ]
        matrix.sort(key=lambda row: -row["evaluated_count"])

        return Response(
            {
                "department": department.code if department else "ALL",
                "headcount": headcount,
                "skills": matrix,
            }
        )


class EmployeeExportView(APIView):
    """GET /api/hr/employees/export/ — CSV export (HR only)."""

    permission_classes = [permissions.IsAuthenticated]

    COLUMNS = [
        "user_id", "email", "first_name", "last_name", "user_role",
        "department_code", "job_title", "employment_type", "hire_date",
        "manager_user_id", "is_active",
    ]

    def get(self, request):
        if not has_hr_access(request.user):
            raise PermissionDenied("HR or Admin role required.")

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="employees.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(self.COLUMNS)
        rows = EmployeeProfile.objects.select_related(
            "department", "manager"
        ).order_by("id")
        for p in rows:
            writer.writerow([
                p.user_id, p.email, p.first_name, p.last_name, p.user_role,
                p.department.code if p.department else "",
                p.job_title, p.employment_type,
                p.hire_date or "", p.manager.user_id if p.manager else "",
                p.is_active,
            ])
        return response
