"""Domain -> HR Open Standards mapping.

Pure functions, no Django ORM query logic, so the wire format can be
unit-tested in isolation. They accept already-loaded model instances (or any
object exposing the same attributes) and return JSON-serialisable dicts.

Shapes are inspired by the HR Open Standards competency models:

* CompetencyDefinition   — the semantics of a competency (our Skill catalog).
* PersonCompetency       — a person's rated competency, with a
                           CompetencyDimension (the rating) and
                           CompetencyEvidence of type "assessment".
* PositionCompetencyModel — competencies expected/observed for a position or
                           org unit (our aggregated skill matrix).
"""

from __future__ import annotations

from typing import Optional

# Proficiency scale published alongside the data so consumers can interpret the
# numeric rating. Matches hr.EmployeeSkill.Level (1..4).
PROFICIENCY_SCALE_ID = "SMARTHR360-PROFICIENCY-1TO4"
PROFICIENCY_SCALE = {
    1: "Beginner",
    2: "Intermediate",
    3: "Advanced",
    4: "Expert",
}
PROFICIENCY_MAX = 4


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


def proficiency_scale_descriptor() -> dict:
    """The rating scale, embedded in responses for self-describing payloads."""
    return {
        "id": PROFICIENCY_SCALE_ID,
        "minimumValue": 1,
        "maximumValue": PROFICIENCY_MAX,
        "levels": [
            {"value": value, "name": name}
            for value, name in sorted(PROFICIENCY_SCALE.items())
        ],
    }


def competency_definition(skill) -> dict:
    """Map an hr.Skill to an HR-Open CompetencyDefinition.

    Field names follow the publicly documented HR-XML/HR Open competency
    vocabulary (``competencyId``, ``taxonomyId``, ``CompetencyEvidence``,
    ``CompetencyDimension``). Strict schema-level conformance would require the
    member-gated HR-JSON schema files.
    """
    return {
        "type": "CompetencyDefinition",
        "id": skill.code,
        "competencyId": skill.code,
        "name": skill.name,
        "description": skill.description or "",
        "competencyCategory": skill.category or "Uncategorized",
        "active": bool(skill.is_active),
        "taxonomyId": "SMARTHR360-SKILLS",
        "taxonomy": {
            "id": "SMARTHR360-SKILLS",
            "name": "SmartHR360 Skill Catalog",
        },
    }


def competency_dimension(level: int, target_level: Optional[int]) -> dict:
    """The rating facet of a PersonCompetency."""
    gap = (
        (target_level - level)
        if (target_level is not None and level is not None)
        else None
    )
    return {
        "type": "CompetencyDimension",
        "dimensionType": "proficiency",
        "score": {
            "value": level,
            "maximumValue": PROFICIENCY_MAX,
            "name": PROFICIENCY_SCALE.get(level, "Unknown"),
            "scaleId": PROFICIENCY_SCALE_ID,
        },
        "targetValue": target_level,
        "targetGap": gap,
    }


def person_competency(employee_skill) -> dict:
    """Map an hr.EmployeeSkill to an HR-Open PersonCompetency record."""
    emp = employee_skill.employee
    skill = employee_skill.skill
    person_name = f"{emp.first_name} {emp.last_name}".strip()

    evidence = []
    if employee_skill.last_evaluated_at or employee_skill.last_evaluated_by_user_id:
        evidence.append(
            {
                "type": "CompetencyEvidence",
                # HR-XML CompetencyEvidence carries a typeId; "assessment" is the
                # evidence type for an evaluated (rated) competency.
                "typeId": "assessment",
                "name": "Skill evaluation",
                "assessedBy": employee_skill.last_evaluated_by_user_id,
                "assessmentDate": _iso(employee_skill.last_evaluated_at),
                "note": employee_skill.notes or "",
            }
        )

    effective = _iso(employee_skill.last_evaluated_at or employee_skill.updated_at)
    return {
        "type": "PersonCompetency",
        "id": f"EMPSKILL-{employee_skill.id}",
        "person": {
            "id": emp.user_id,
            "employeeId": emp.external_employee_id or None,
            "sourceSystem": emp.source_system or None,
            "name": person_name or (emp.email or f"user-{emp.user_id}"),
            "departmentCode": emp.department.code if emp.department_id else None,
            "jobTitle": emp.job_title or None,
        },
        "competency": {
            "id": skill.code,
            "competencyId": skill.code,
            "name": skill.name,
            "category": skill.category or "Uncategorized",
        },
        "competencyDimensions": [
            competency_dimension(employee_skill.level, employee_skill.target_level)
        ],
        "competencyEvidence": evidence,
        # HR-XML models validity as an EffectiveDateRange; the open end mirrors
        # the SCD2 "current" window (date_fin = null) from Étape 2.
        "effectiveDateRange": {"startDate": effective, "endDate": None},
    }


def position_competency_model(
    department_code: str, headcount: int, matrix_rows: list[dict]
) -> dict:
    """Aggregated competencies for an org unit -> PositionCompetencyModel.

    ``matrix_rows`` items are the dicts produced by the existing skill-matrix
    aggregation: {skill, skill_code, average_level, evaluated_count,
    coverage_percent, average_target_gap}.
    """
    competencies = [
        {
            "type": "CompetencyModelEntry",
            "competency": {"id": row["skill_code"], "name": row["skill"]},
            "expectedProficiency": {
                "averageValue": row["average_level"],
                "maximumValue": PROFICIENCY_MAX,
                "scaleId": PROFICIENCY_SCALE_ID,
            },
            "assessedHeadcount": row["evaluated_count"],
            "coveragePercent": row["coverage_percent"],
            "averageTargetGap": row.get("average_target_gap"),
        }
        for row in matrix_rows
    ]
    return {
        "type": "PositionCompetencyModel",
        "id": f"ORGUNIT-{department_code}",
        "orgUnit": {"departmentCode": department_code},
        "headcount": headcount,
        "proficiencyScale": proficiency_scale_descriptor(),
        "competencies": competencies,
    }
