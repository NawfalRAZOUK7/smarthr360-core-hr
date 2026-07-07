"""Skill-gap engine: ORM data access + orchestration.

Builds, per department and skill, a :class:`SkillGapInput` from live data and
delegates the maths to :mod:`hr.prediction.analyzer`. Only skills carrying a
*demand signal* (an employee target level and/or a declared FutureCompetency)
are forecast — otherwise a "gap" is undefined.

Attrition is derived from the SCD2 history (Étape 2): employees whose current
history version flipped to ``is_employment_active = False`` within the lookback
window count as recent losses for their department.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from typing import Optional
from uuid import uuid4

from django.db.models import Q
from django.utils import timezone

from hr.models import (
    Department,
    EmployeeProfile,
    EmployeeProfileHistory,
    EmployeeSkill,
    FutureCompetency,
    SkillGapForecast,
)

from config.metrics import record_skill_gap_run

from . import DEFAULT_HORIZON_MONTHS
from .analyzer import SkillGapInput, forecast_skill_gap, rank_forecasts

logger = logging.getLogger("hr.prediction")

# FutureCompetency.importance (1..5) -> required proficiency level (1..4).
_IMPORTANCE_TO_LEVEL = {1: 2, 2: 2, 3: 3, 4: 4, 5: 4}


class SkillGapEngine:
    def __init__(
        self,
        *,
        horizon_months: int = DEFAULT_HORIZON_MONTHS,
        attrition_lookback_months: int = 6,
    ):
        self.horizon_months = horizon_months
        self.attrition_lookback_months = attrition_lookback_months

    # ------------------------------------------------------------------
    def run(self, *, department_code: Optional[str] = None, persist: bool = True):
        """Compute forecasts for one or all departments.

        Returns ``(run_id, [forecast_dict, ...])`` ranked by risk.
        """
        run_id = uuid4().hex
        departments = Department.objects.all().order_by("code")
        if department_code:
            departments = departments.filter(code__iexact=department_code)

        results = []
        for dept in departments:
            results.extend(self._forecast_department(dept))

        results = rank_forecasts(results)
        forecast_dicts = [r.as_dict() for r in results]

        if persist and results:
            self._persist(run_id, results)

        # Emit Prometheus gauges (scraped at /metrics) for the whole run — even
        # when not persisted, so a preview run still updates observability.
        record_skill_gap_run(forecast_dicts)

        logger.info(
            "skill-gap run %s: %d forecast(s) over %d months",
            run_id,
            len(results),
            self.horizon_months,
        )
        return run_id, forecast_dicts

    # ------------------------------------------------------------------
    def _forecast_department(self, dept: Department):
        employees = EmployeeProfile.objects.filter(is_active=True, department=dept)
        headcount = employees.count()
        if headcount == 0:
            return []

        emp_ids = list(employees.values_list("id", flat=True))
        attrition_rate = self._department_attrition(dept, headcount)

        evaluations = (
            EmployeeSkill.objects.filter(employee_id__in=emp_ids)
            .select_related("skill")
        )
        per_skill = defaultdict(list)
        for ev in evaluations:
            per_skill[ev.skill].append(ev)

        future = (
            FutureCompetency.objects.filter(
                Q(department=dept) | Q(department__isnull=True)
            )
            .select_related("skill")
        )
        future_by_skill = {}
        for fc in future:
            # Keep the strongest (highest importance) future signal per skill.
            existing = future_by_skill.get(fc.skill_id)
            if existing is None or fc.importance > existing.importance:
                future_by_skill[fc.skill_id] = fc

        skills = {s.id: s for s in per_skill}
        for fc in future_by_skill.values():
            skills.setdefault(fc.skill.id, fc.skill)

        out = []
        for skill_id, skill in skills.items():
            evs = per_skill.get(skill, [])
            item = self._build_input(
                dept, skill, evs, headcount, attrition_rate,
                future_by_skill.get(skill_id),
            )
            if item is None:
                continue
            out.append(forecast_skill_gap(item, horizon_months=self.horizon_months))
        return out

    def _build_input(self, dept, skill, evs, headcount, attrition_rate, fc):
        levels = [e.level for e in evs]
        assessed = {e.employee_id for e in evs}
        coverage = len(assessed) / headcount if headcount else 0.0
        current = (sum(levels) / len(levels)) if levels else 0.0

        targets = [e.target_level for e in evs if e.target_level]
        base_demand = (sum(targets) / len(targets)) if targets else 0.0

        fc_demand = _IMPORTANCE_TO_LEVEL.get(fc.importance, 3) if fc else 0.0
        demand = max(base_demand, fc_demand)

        # No demand signal at all -> a gap is undefined; skip.
        if demand <= 0:
            return None
        # Nothing below demand -> supply already meets it; still report if fc
        # exists (strategic tracking), else skip pure no-op rows.
        importance = fc.importance if fc else 3

        return SkillGapInput(
            department_code=dept.code,
            skill_code=skill.code,
            skill_name=skill.name,
            current_avg_level=current,
            coverage=coverage,
            demand_level=demand,
            importance=importance,
            trend_points=self._trend_points(evs),
            attrition_rate=attrition_rate,
        )

    @staticmethod
    def _trend_points(evs):
        """(absolute_month_index, level) points from evaluation dates."""
        points = []
        for e in evs:
            when = e.last_evaluated_at or e.updated_at
            if when is None:
                continue
            points.append((when.year * 12 + when.month, float(e.level)))
        points.sort(key=lambda p: p[0])
        return points

    def _department_attrition(self, dept, headcount) -> float:
        cutoff = timezone.now() - timedelta(days=30 * self.attrition_lookback_months)
        recently_left = (
            EmployeeProfileHistory.objects.filter(
                is_current=True,
                is_employment_active=False,
                date_debut__gte=cutoff,
                department=dept,
            )
            .values("employee")
            .distinct()
            .count()
        )
        denom = headcount + recently_left
        return (recently_left / denom) if denom else 0.0

    def _persist(self, run_id, results):
        SkillGapForecast.objects.bulk_create(
            [
                SkillGapForecast(
                    run_id=run_id,
                    department=Department.objects.get(code=r.department_code),
                    skill=self._skill(r.skill_code),
                    horizon_months=r.horizon_months,
                    current_avg_level=r.current_avg_level,
                    velocity_per_month=r.velocity_per_month,
                    projected_level=r.projected_level,
                    demand_level=r.demand_level,
                    gap=r.gap,
                    coverage=r.coverage,
                    attrition_rate=r.attrition_rate,
                    importance=r.importance,
                    risk_score=r.risk_score,
                    severity=r.severity,
                    rationale=r.rationale,
                )
                for r in results
            ]
        )

    # tiny cache to avoid a query per row in _persist
    _skill_cache: dict = {}

    def _skill(self, code):
        from hr.models import Skill

        if code not in self._skill_cache:
            self._skill_cache[code] = Skill.objects.get(code=code)
        return self._skill_cache[code]
