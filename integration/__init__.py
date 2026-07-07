"""EAI / ERP integration layer for smarthr360-core-hr.

This app implements the *ingestion side* of the enterprise integration
architecture: it parses personnel exports produced by a central ERP
(SAP, Odoo, ...), maps them to SmartHR360's canonical HR model and performs
idempotent upserts into the local PostgreSQL database.

Design notes
------------
* Adapter pattern: each ERP format has an ``ERPAdapter`` implementation that
  turns raw bytes into a stream of :class:`CanonicalEmployee` records. The rest
  of the pipeline is format-agnostic.
* Microservice isolation (ADR-005): no cross-service ForeignKey. Identity is
  by-value; ERP records are matched on ``(source_system, external_employee_id)``.
"""

default_app_config = "integration.apps.IntegrationConfig"
