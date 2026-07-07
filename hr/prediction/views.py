"""Skill-gap prediction endpoint.

    GET /api/hr/predictions/skill-gaps/?department=ENG&horizon_months=6&persist=false

Management roles only (this is organisation-wide, decision-support data).
Returns forecasts ranked by risk, in the project's standard envelope.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from smarthr360_jwt_auth.access import has_manager_access, is_auditor

from ..interop.errors import bad_request, forbidden
from . import DEFAULT_HORIZON_MONTHS
from .skill_gap_service import SkillGapEngine

_MAX_HORIZON = 24


class SkillGapPredictionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Predict skill gaps (decision support)",
        description=(
            "Forecast, per department and skill, the competency supply at the "
            "horizon and the gap vs demand (employee targets + declared future "
            "needs), adjusted for SCD2 attrition. Ranked by risk. Management "
            "roles only."
        ),
        parameters=[
            OpenApiParameter("department", str, description="Department code filter."),
            OpenApiParameter(
                "horizon_months", int, description="Forecast horizon (default 6, max 24)."
            ),
            OpenApiParameter(
                "persist", bool, description="Store the run for BI (default false)."
            ),
        ],
        tags=["Predictions (Skill Gaps)"],
    )
    def get(self, request):
        user = request.user
        if not (has_manager_access(user) or is_auditor(user)):
            return forbidden("Manager, HR, Admin or Auditor role required.")

        horizon = request.query_params.get("horizon_months")
        if horizon is not None:
            if not horizon.isdigit() or not (1 <= int(horizon) <= _MAX_HORIZON):
                return bad_request(
                    "invalid_parameter",
                    f"horizon_months must be an integer in 1..{_MAX_HORIZON}.",
                )
            horizon = int(horizon)
        else:
            horizon = DEFAULT_HORIZON_MONTHS

        persist = str(request.query_params.get("persist", "false")).lower() in {
            "true",
            "1",
        }
        department = request.query_params.get("department")

        engine = SkillGapEngine(horizon_months=horizon)
        run_id, forecasts = engine.run(department_code=department, persist=persist)

        summary = {
            "high": sum(1 for f in forecasts if f["severity"] == "HIGH"),
            "medium": sum(1 for f in forecasts if f["severity"] == "MEDIUM"),
            "low": sum(1 for f in forecasts if f["severity"] == "LOW"),
        }
        return Response(
            {
                "data": {
                    "run_id": run_id,
                    "horizon_months": horizon,
                    "department": department or "ALL",
                    "persisted": persist,
                    "count": len(forecasts),
                    "severity_summary": summary,
                    "forecasts": forecasts,
                },
                "meta": {"success": True},
            }
        )
