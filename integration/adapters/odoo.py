"""Odoo JSON adapter.

Odoo exports ``hr.employee`` records as JSON. This adapter accepts either:

* a bare JSON array of employee objects, or
* an envelope ``{"model": "hr.employee", "records": [...]}``

Odoo field mapping (typical hr.employee export)::

    id / x_matricule        -> external_employee_id
    work_email / private_email -> email
    name  ("First Last")    -> first_name / last_name
    job_title / job_id.name -> job_title
    department_id.name/code -> department_name / department_code
    parent_id.id            -> manager_external_id
    contract_type / employee_type -> employment_type
    first_contract_date     -> hire_date
    work_phone / mobile_phone -> phone_number
    active                  -> is_active
"""

from __future__ import annotations

import json
from typing import Iterable

from .base import AdapterError, AdapterRecordError, CanonicalEmployee, ERPAdapter

# Odoo employee_type / contract values -> SmartHR360 EmploymentType
_EMPLOYMENT_MAP = {
    "employee": "FULL_TIME",
    "full_time": "FULL_TIME",
    "part_time": "PART_TIME",
    "student": "INTERN",
    "trainee": "INTERN",
    "intern": "INTERN",
    "contractor": "CONTRACTOR",
    "freelance": "CONTRACTOR",
}


class OdooJSONAdapter(ERPAdapter):
    source_system = "ODOO"
    format_name = "Odoo JSON (hr.employee)"

    def parse(self, raw: bytes) -> Iterable[CanonicalEmployee]:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdapterError(f"Invalid Odoo JSON document: {exc}") from exc

        if isinstance(payload, dict):
            records = payload.get("records", [])
        elif isinstance(payload, list):
            records = payload
        else:
            raise AdapterError("Odoo JSON must be an array or an envelope object.")

        for index, rec in enumerate(records):
            if not isinstance(rec, dict):
                raise AdapterRecordError("record is not an object", index=index)
            yield self._map_record(rec, index)

    # ------------------------------------------------------------------
    def _map_record(self, rec: dict, index: int) -> CanonicalEmployee:
        ext_id = self._clean(rec.get("x_matricule") or rec.get("id"))
        if not ext_id:
            raise AdapterRecordError("missing employee id/matricule", index=index)

        first, last = self._split_name(
            rec.get("name"), rec.get("first_name"), rec.get("last_name")
        )
        dept = rec.get("department_id") or {}
        if isinstance(dept, (list, tuple)):  # Odoo [id, "Name"] many2one form
            dept = {"name": dept[1] if len(dept) > 1 else ""}
        elif not isinstance(dept, dict):
            dept = {"name": self._clean(dept)}

        emp_type_raw = self._clean(
            rec.get("employee_type") or rec.get("contract_type")
        ).lower()

        return CanonicalEmployee(
            external_employee_id=ext_id,
            source_system=self.source_system,
            email=self._clean(rec.get("work_email") or rec.get("private_email")),
            first_name=first,
            last_name=last,
            user_role=self._map_role(rec.get("smarthr_role")),
            department_code=self._clean(dept.get("code")),
            department_name=self._clean(dept.get("name")),
            job_title=self._clean(rec.get("job_title") or rec.get("job_id")),
            employment_type=_EMPLOYMENT_MAP.get(emp_type_raw, "FULL_TIME"),
            hire_date=self._clean(rec.get("first_contract_date")) or None,
            phone_number=self._clean(
                rec.get("work_phone") or rec.get("mobile_phone")
            ),
            is_active=bool(rec.get("active", True)),
            manager_external_id=self._clean(rec.get("parent_id")),
            user_id=self._to_int(rec.get("smarthr_user_id")),
            extra={"odoo_id": rec.get("id")},
        )

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _split_name(full, first, last) -> tuple[str, str]:
        if first or last:
            return (str(first or "").strip(), str(last or "").strip())
        full = (full or "").strip()
        if not full:
            return "", ""
        parts = full.split()
        return parts[0], " ".join(parts[1:])

    @staticmethod
    def _map_role(raw) -> str:
        role = (str(raw or "").strip() or "EMPLOYEE").upper()
        return role if role in {"EMPLOYEE", "MANAGER", "HR", "ADMIN"} else "EMPLOYEE"

    @staticmethod
    def _to_int(value):
        try:
            return int(value) if value not in (None, "", False) else None
        except (TypeError, ValueError):
            return None
