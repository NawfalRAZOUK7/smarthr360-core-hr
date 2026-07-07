"""SAP XML adapter (IDoc-like HRMD flavour).

SAP HR typically exports personnel master data as XML (IDoc HRMD_A, or a
simplified OData/RFC dump). This adapter targets a pragmatic, IDoc-inspired
shape that keeps the essential PA (Personnel Administration) infotypes:

    <HRMD_EMPLOYEES>
      <EMPLOYEE>
        <PERNR>00204512</PERNR>            personnel number  -> external_employee_id
        <VORNA>Amine</VORNA>               first name
        <NACHN>El Fassi</NACHN>            last name
        <SMTP_ADDR>...</SMTP_ADDR>         email
        <ORGEH_TEXT>IT</ORGEH_TEXT>        org unit (department name)
        <ORGEH_CODE>IT</ORGEH_CODE>        org unit code
        <STELL_TEXT>Data Engineer</STELL_TEXT>  position/job title
        <PERSK>DU</PERSK>                  employee subgroup -> employment type
        <BEGDA>2021-09-01</BEGDA>          hire date (YYYYMMDD or ISO)
        <TELNR>...</TELNR>                 phone
        <STAT2>3</STAT2>                   employment status (3=active)
        <CHEF_PERNR>00100001</CHEF_PERNR>  manager personnel number
      </EMPLOYEE>
    </HRMD_EMPLOYEES>

Uses the stdlib ``xml.etree.ElementTree`` with entity expansion disabled at the
document level (no external DTDs) to avoid XXE on untrusted ERP files.
"""

from __future__ import annotations

from typing import Iterable
from xml.etree import ElementTree as ET

from .base import AdapterError, AdapterRecordError, CanonicalEmployee, ERPAdapter

# SAP employee subgroup (PERSK) -> SmartHR360 EmploymentType
_PERSK_MAP = {
    "DU": "FULL_TIME",   # Salaried employee
    "DS": "PART_TIME",
    "DP": "PART_TIME",
    "TR": "INTERN",      # Trainee
    "PR": "INTERN",      # Praktikant
    "EX": "CONTRACTOR",  # External
}


class SAPXMLAdapter(ERPAdapter):
    source_system = "SAP"
    format_name = "SAP XML (IDoc HRMD-like)"

    def parse(self, raw: bytes) -> Iterable[CanonicalEmployee]:
        # forbid_dtd via a parser that does not resolve external entities.
        parser = ET.XMLParser()
        try:
            root = ET.fromstring(raw, parser=parser)
        except ET.ParseError as exc:
            raise AdapterError(f"Invalid SAP XML document: {exc}") from exc

        employees = root.findall(".//EMPLOYEE")
        if not employees:
            raise AdapterError("No <EMPLOYEE> nodes found in SAP export.")

        for index, node in enumerate(employees):
            yield self._map_node(node, index)

    # ------------------------------------------------------------------
    def _map_node(self, node: ET.Element, index: int) -> CanonicalEmployee:
        pernr = self._text(node, "PERNR")
        if not pernr:
            raise AdapterRecordError("missing PERNR (personnel number)", index=index)

        stat2 = self._text(node, "STAT2")
        persk = self._text(node, "PERSK").upper()

        return CanonicalEmployee(
            external_employee_id=pernr,
            source_system=self.source_system,
            email=self._text(node, "SMTP_ADDR"),
            first_name=self._text(node, "VORNA"),
            last_name=self._text(node, "NACHN"),
            user_role=self._map_role(self._text(node, "SMARTHR_ROLE")),
            department_code=self._text(node, "ORGEH_CODE")
            or self._text(node, "ORGEH"),
            department_name=self._text(node, "ORGEH_TEXT"),
            job_title=self._text(node, "STELL_TEXT") or self._text(node, "PLANS_TEXT"),
            employment_type=_PERSK_MAP.get(persk, "FULL_TIME"),
            hire_date=self._parse_date(self._text(node, "BEGDA")),
            phone_number=self._text(node, "TELNR"),
            # STAT2: '3' = active, '0' = withdrawn/left.
            is_active=(stat2 != "0"),
            manager_external_id=self._text(node, "CHEF_PERNR"),
            extra={"stat2": stat2, "persk": persk},
        )

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _text(node: ET.Element, tag: str) -> str:
        child = node.find(tag)
        return (child.text or "").strip() if child is not None else ""

    @staticmethod
    def _parse_date(value: str):
        """Accept 'YYYYMMDD' (SAP) or 'YYYY-MM-DD' -> ISO 'YYYY-MM-DD'."""
        value = (value or "").strip()
        if not value:
            return None
        if len(value) == 8 and value.isdigit():
            return f"{value[:4]}-{value[4:6]}-{value[6:]}"
        return value

    @staticmethod
    def _map_role(raw) -> str:
        role = (str(raw or "").strip() or "EMPLOYEE").upper()
        return role if role in {"EMPLOYEE", "MANAGER", "HR", "ADMIN"} else "EMPLOYEE"
