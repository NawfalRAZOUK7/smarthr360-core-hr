"""Adapter contract for ERP personnel exports.

Every supported ERP format (Odoo JSON, SAP XML, ...) provides a concrete
:class:`ERPAdapter` that converts raw export bytes into a stream of
:class:`CanonicalEmployee` records. Downstream code (validation + upsert) only
ever sees the canonical shape, so adding a new ERP means adding one adapter
and nothing else.

This module is intentionally free of any Django import: mapping logic can be
unit-tested standalone.
"""

from __future__ import annotations

import abc
from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional


@dataclass
class CanonicalEmployee:
    """SmartHR360's neutral representation of an employee coming from an ERP.

    Field names mirror ``hr.EmployeeProfile`` so mapping to the model is 1:1.
    Only ``external_employee_id`` and ``source_system`` are mandatory — they
    form the natural key used for idempotent upserts.
    """

    external_employee_id: str
    source_system: str
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    user_role: str = "EMPLOYEE"
    department_code: str = ""
    department_name: str = ""
    job_title: str = ""
    employment_type: str = "FULL_TIME"
    hire_date: Optional[str] = None          # ISO-8601 'YYYY-MM-DD' or None
    phone_number: str = ""
    is_active: bool = True
    # Manager expressed by the *source* system's employee id (resolved later).
    manager_external_id: str = ""
    # Optional pre-linked auth user id, when the ERP already knows it.
    user_id: Optional[int] = None
    # Anything the adapter could not map, kept for audit / debugging.
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


class ERPAdapter(abc.ABC):
    """Base class for ERP export adapters."""

    #: Value written to ``EmployeeProfile.source_system`` (e.g. 'ODOO', 'SAP').
    source_system: str = ""

    #: Human-friendly format label used in logs / sync runs.
    format_name: str = ""

    @abc.abstractmethod
    def parse(self, raw: bytes) -> Iterable[CanonicalEmployee]:
        """Yield :class:`CanonicalEmployee` records from raw export bytes.

        Implementations must be tolerant: a malformed *record* should raise
        :class:`AdapterRecordError` (skippable) rather than aborting the whole
        batch, while a malformed *document* may raise :class:`AdapterError`.
        """
        raise NotImplementedError

    # -- shared helpers ---------------------------------------------------
    @staticmethod
    def _clean(value) -> str:
        return (str(value).strip() if value is not None else "")


class AdapterError(Exception):
    """The whole export could not be parsed (bad document / unknown format)."""


class AdapterRecordError(AdapterError):
    """A single record is invalid and should be skipped, not fatal."""

    def __init__(self, message: str, *, index: int | None = None):
        super().__init__(message)
        self.index = index
