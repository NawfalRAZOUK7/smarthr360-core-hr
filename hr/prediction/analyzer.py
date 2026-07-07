"""Analytic core of the skill-gap engine — pure Python, no Django.

Everything here operates on plain values / dataclasses so it can be unit-tested
without a database. The service layer feeds it aggregates built from the ORM.

Method (transparent, explainable — important for HR decision support):

    projected_supply = current_level
                       + velocity * horizon_months          # organic upskilling
                       - attrition_penalty                   # loss of skilled staff
    gap              = max(0, demand_level - projected_supply)
    risk            = normalize(gap) * importance_weight * (1 - coverage)

``velocity`` is the slope of a linear trend fitted over past evaluation points.
scikit-learn is used when available; otherwise a dependency-free least-squares
implementation gives identical results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

PROFICIENCY_MAX = 4

# Optional acceleration with scikit-learn; the pure-Python path is the default
# and produces the same slope, so core-hr needs no heavy ML dependency.
try:  # pragma: no cover - exercised only when sklearn is installed
    import numpy as _np
    from sklearn.linear_model import LinearRegression as _SkLinearRegression

    _HAS_SKLEARN = True
except Exception:  # noqa: BLE001
    _HAS_SKLEARN = False


def linear_trend(points: Sequence[tuple[float, float]]) -> float:
    """Return the slope (units per x) of a least-squares line through points.

    ``points`` is a sequence of (x, y). With fewer than two distinct x values
    the trend is undefined and we return 0.0 (flat).
    """
    if len(points) < 2:
        return 0.0
    xs = [float(x) for x, _ in points]
    ys = [float(y) for _, y in points]
    if len(set(xs)) < 2:
        return 0.0

    if _HAS_SKLEARN:  # pragma: no cover
        X = _np.array(xs).reshape(-1, 1)
        y = _np.array(ys)
        model = _SkLinearRegression().fit(X, y)
        return float(model.coef_[0])

    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    return num / den if den else 0.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class SkillGapInput:
    """One department x skill row to forecast."""

    department_code: str
    skill_code: str
    skill_name: str
    current_avg_level: float           # mean current proficiency (1..4)
    coverage: float                    # share of headcount assessed (0..1)
    demand_level: float                # required proficiency (1..4)
    importance: int = 3                # 1..5 (from FutureCompetency)
    # (month_index, avg_level) history points for the trend, oldest first.
    trend_points: Sequence[tuple[float, float]] = field(default_factory=list)
    attrition_rate: float = 0.0        # share of assessed staff recently lost (0..1)


@dataclass
class SkillGapForecastResult:
    department_code: str
    skill_code: str
    skill_name: str
    horizon_months: int
    current_avg_level: float
    velocity_per_month: float
    projected_level: float
    demand_level: float
    gap: float
    coverage: float
    attrition_rate: float
    importance: int
    risk_score: float
    severity: str
    rationale: str

    def as_dict(self) -> dict:
        return {
            "department_code": self.department_code,
            "skill_code": self.skill_code,
            "skill_name": self.skill_name,
            "horizon_months": self.horizon_months,
            "current_avg_level": round(self.current_avg_level, 3),
            "velocity_per_month": round(self.velocity_per_month, 4),
            "projected_level": round(self.projected_level, 3),
            "demand_level": round(self.demand_level, 3),
            "gap": round(self.gap, 3),
            "coverage": round(self.coverage, 3),
            "attrition_rate": round(self.attrition_rate, 3),
            "importance": self.importance,
            "risk_score": round(self.risk_score, 2),
            "severity": self.severity,
            "rationale": self.rationale,
        }


def _severity(risk: float) -> str:
    if risk >= 66:
        return "HIGH"
    if risk >= 33:
        return "MEDIUM"
    return "LOW"


def forecast_skill_gap(
    item: SkillGapInput, horizon_months: int = 6
) -> SkillGapForecastResult:
    """Project supply and compute the gap + risk for one dept x skill."""
    velocity = linear_trend(item.trend_points)

    # Attrition penalty: losing assessed staff erodes the average level,
    # weighted by how far above "beginner" the team currently is.
    attrition_penalty = item.attrition_rate * max(0.0, item.current_avg_level - 1.0)

    projected = clamp(
        item.current_avg_level + velocity * horizon_months - attrition_penalty,
        0.0,
        PROFICIENCY_MAX,
    )
    gap = max(0.0, item.demand_level - projected)

    # Risk: gap normalised to [0,1] over the scale, scaled by strategic
    # importance (1..5 -> 0.2..1.0) and by how little of the team is covered.
    importance_weight = clamp(item.importance / 5.0, 0.2, 1.0)
    coverage_factor = 1.0 - clamp(item.coverage, 0.0, 1.0)
    risk = 100.0 * (gap / PROFICIENCY_MAX) * importance_weight
    # Low coverage inflates risk up to +50% (uncertainty of an under-measured team).
    risk *= 1.0 + 0.5 * coverage_factor
    risk = clamp(risk, 0.0, 100.0)

    rationale = _rationale(item, velocity, projected, gap, horizon_months)

    return SkillGapForecastResult(
        department_code=item.department_code,
        skill_code=item.skill_code,
        skill_name=item.skill_name,
        horizon_months=horizon_months,
        current_avg_level=item.current_avg_level,
        velocity_per_month=velocity,
        projected_level=projected,
        demand_level=item.demand_level,
        gap=gap,
        coverage=item.coverage,
        attrition_rate=item.attrition_rate,
        importance=item.importance,
        risk_score=risk,
        severity=_severity(risk),
        rationale=rationale,
    )


def _rationale(item, velocity, projected, gap, horizon) -> str:
    if gap <= 0:
        return (
            f"On track: projected {projected:.1f}/4 meets demand "
            f"{item.demand_level:.1f}/4 within {horizon} months."
        )
    drivers = []
    if velocity <= 0:
        drivers.append("no upskilling momentum")
    if item.attrition_rate > 0:
        drivers.append(f"{item.attrition_rate:.0%} recent attrition of assessed staff")
    if item.coverage < 0.5:
        drivers.append(f"low coverage ({item.coverage:.0%})")
    driver_txt = "; ".join(drivers) if drivers else "demand above current trajectory"
    return (
        f"Gap of {gap:.1f} level(s): projected {projected:.1f}/4 vs demand "
        f"{item.demand_level:.1f}/4 in {horizon} months ({driver_txt})."
    )


def rank_forecasts(
    results: Sequence[SkillGapForecastResult],
) -> list[SkillGapForecastResult]:
    """Highest risk first — the order a decision-maker wants."""
    return sorted(results, key=lambda r: r.risk_score, reverse=True)
