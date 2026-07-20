from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from datetime import timedelta

# Microservice note (ADR-005): this service has NO ForeignKey to the auth
# service's User table. Identity lives in JWT claims; we persist the auth
# user id as `user_id` plus denormalized display fields synced at profile
# creation/update time.


class Department(models.Model):
    """
    Basic department / team inside SmartHR360.
    Example: 'IT', 'HR', 'Finance', 'Marketing'...
    """

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class EmployeeProfile(models.Model):
    """
    HR information for a platform user.

    `user_id` references the id of the user in smarthr360-auth (by value,
    not by ForeignKey). `email`, `first_name`, `last_name` and `user_role`
    are denormalized snapshots taken from token claims / the auth API.
    """

    class EmploymentType(models.TextChoices):
        FULL_TIME = "FULL_TIME", "Full time"
        PART_TIME = "PART_TIME", "Part time"
        INTERN = "INTERN", "Intern"
        CONTRACTOR = "CONTRACTOR", "Contractor"

    class UserRole(models.TextChoices):
        EMPLOYEE = "EMPLOYEE", "Employee"
        MANAGER = "MANAGER", "Manager"
        HR = "HR", "HR"
        ADMIN = "ADMIN", "Admin"

    # Identity (auth service user), by value.
    # Nullable: employees ingested from an ERP (EAI layer) may exist before an
    # auth account is provisioned. NULLs are allowed multiple times in Postgres,
    # the unique constraint still forbids duplicate non-null ids.
    user_id = models.PositiveBigIntegerField(
        unique=True, db_index=True, null=True, blank=True
    )

    # --- MDM / EAI federation keys (ADR: ERP integration layer) -------------
    # Stable identifier of this employee in the *source* system (SAP PERNR,
    # Odoo hr.employee id, matricule...). Combined with `source_system` it is
    # the natural key used for idempotent upserts from the ERP connector.
    external_employee_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Employee id/matricule in the source ERP (SAP PERNR, Odoo id...).",
    )
    source_system = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Origin system of the record, e.g. 'ODOO', 'SAP', 'MANUAL'.",
    )

    email = models.EmailField(blank=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    user_role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.EMPLOYEE,
        help_text="Snapshot of the auth role, refreshed from token claims.",
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )

    manager = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_members",
    )

    job_title = models.CharField(max_length=150, blank=True)
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
    )
    hire_date = models.DateField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    # Monthly gross salary. Tracked historically (SCD Type 2) via
    # EmployeeProfileHistory. Nullable: not every source provides it.
    salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Current monthly gross salary. Changes are historized (SCD2).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            # Natural key for ERP upserts: an external id is unique *within* a
            # given source system. Empty external ids (manual entries) are
            # exempted via the condition so they don't collide with each other.
            models.UniqueConstraint(
                fields=["source_system", "external_employee_id"],
                name="uniq_employee_source_external_id",
                condition=~models.Q(external_employee_id=""),
            ),
        ]

    def __str__(self):
        return f"{self.email or self.user_id} - {self.job_title or 'Employee'}"

    def clean(self):
        super().clean()

        # cannot be own manager
        if self.manager_id and self.manager_id == self.id:
            raise ValidationError("An employee cannot be their own manager.")

        # manager must have MANAGER / HR / ADMIN access (role snapshot)
        if self.manager and self.manager.user_role == self.UserRole.EMPLOYEE:
            raise ValidationError(
                "Selected manager must have Manager, HR, or Admin access."
            )


class Skill(models.Model):
    """
    Skill catalog (compétences de base).
    Defined by HR / Managers and reused in employee evaluations.
    """

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    created_by_user_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class EmployeeSkill(models.Model):
    """
    Employee evaluation on a given skill.
    """

    class Level(models.IntegerChoices):
        BEGINNER = 1, "Beginner"
        INTERMEDIATE = 2, "Intermediate"
        ADVANCED = 3, "Advanced"
        EXPERT = 4, "Expert"

    employee = models.ForeignKey(
        "hr.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="skills",
    )
    skill = models.ForeignKey(
        "hr.Skill",
        on_delete=models.CASCADE,
        related_name="employee_skills",
    )
    level = models.PositiveSmallIntegerField(choices=Level.choices)
    target_level = models.PositiveSmallIntegerField(
        choices=Level.choices,
        null=True,
        blank=True,
    )
    last_evaluated_by_user_id = models.PositiveBigIntegerField(null=True, blank=True)
    last_evaluated_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("employee", "skill")
        ordering = ["employee", "skill"]

    def __str__(self):
        return f"{self.employee} - {self.skill} ({self.get_level_display()})"


class FutureCompetency(models.Model):
    """
    Future competency needs for departments / organization.
    Used with Module 3 'Future skills prediction'.
    """

    TIMEFRAME_CHOICES = [
        ("SHORT", "0–12 months"),
        ("MEDIUM", "1–3 years"),
        ("LONG", "3+ years"),
    ]

    skill = models.ForeignKey(
        "hr.Skill",
        on_delete=models.CASCADE,
        related_name="future_competencies",
    )
    department = models.ForeignKey(
        "hr.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="future_competencies",
    )
    timeframe = models.CharField(max_length=10, choices=TIMEFRAME_CHOICES)
    importance = models.PositiveSmallIntegerField(default=3)  # 1–5
    description = models.TextField(blank=True)

    created_by_user_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-importance", "skill__name"]

    def __str__(self):
        dept = self.department.name if self.department else "Global"
        return f"{self.skill.name} ({dept}, {self.timeframe})"


class EmployeeProfileHistory(models.Model):
    """Slowly Changing Dimension (Type 2) history of an employee's HR facts.

    Every time a *tracked* attribute of an ``EmployeeProfile`` changes (job
    title, department, manager, employment type, role or salary), the currently
    open row is closed (``date_fin`` set, ``is_current=False``) and a new row is
    opened. This preserves the full timeline — required for BI / decision support
    and for the future-skills predictions (Étape 4).

    Invariants:
    * At most one *open* row per employee (``date_fin IS NULL``,
      ``is_current=True``) — enforced by a partial unique constraint.
    * Rows never overlap: ``date_debut`` of version N+1 == ``date_fin`` of N.

    Note on naming: the SCD2 current-version flag is ``is_current`` (not
    ``is_active``) to avoid confusion with ``EmployeeProfile.is_active`` which
    denotes employment status. Employment status is itself snapshotted below.
    """

    employee = models.ForeignKey(
        "hr.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="history",
    )

    # --- Snapshotted (tracked) HR facts ---------------------------------
    department = models.ForeignKey(
        "hr.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # Manager kept as a value snapshot (the manager's own profile id) so the
    # history survives manager deletion/reorg without dangling references.
    manager_id_snapshot = models.PositiveBigIntegerField(null=True, blank=True)
    job_title = models.CharField(max_length=150, blank=True)
    employment_type = models.CharField(max_length=20, blank=True)
    user_role = models.CharField(max_length=20, blank=True)
    salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_employment_active = models.BooleanField(default=True)

    # --- SCD Type 2 validity window -------------------------------------
    version = models.PositiveIntegerField(default=1)
    date_debut = models.DateTimeField(db_index=True)
    date_fin = models.DateTimeField(null=True, blank=True, db_index=True)
    is_current = models.BooleanField(default=True)

    # --- Change provenance ----------------------------------------------
    change_reason = models.CharField(max_length=255, blank=True)
    changed_by_user_id = models.PositiveBigIntegerField(null=True, blank=True)
    source_system = models.CharField(max_length=32, blank=True)

    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["employee_id", "-date_debut"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee"],
                condition=models.Q(date_fin__isnull=True),
                name="uniq_open_history_per_employee",
            ),
            models.UniqueConstraint(
                fields=["employee", "version"],
                name="uniq_history_version_per_employee",
            ),
        ]
        indexes = [
            models.Index(
                fields=["employee", "is_current"], name="hr_emphist_emp_curr_idx"
            ),
            models.Index(
                fields=["employee", "date_debut", "date_fin"],
                name="hr_emphist_emp_window_idx",
            ),
        ]
        verbose_name = "Employee history (SCD2)"
        verbose_name_plural = "Employee history (SCD2)"

    def __str__(self):
        end = self.date_fin.date() if self.date_fin else "present"
        start = self.date_debut.date() if self.date_debut else "?"
        return f"{self.employee_id} v{self.version} [{start} → {end}]"

    @property
    def tracked_snapshot(self) -> dict:
        """The set of fields compared to detect a change."""
        return {
            "department_id": self.department_id,
            "manager_id_snapshot": self.manager_id_snapshot,
            "job_title": self.job_title,
            "employment_type": self.employment_type,
            "user_role": self.user_role,
            "salary": self.salary,
            "is_employment_active": self.is_employment_active,
        }


class SkillGapForecast(models.Model):
    """A predicted skill gap for a department/skill over a horizon (Étape 4).

    Persisted so forecasts can themselves be tracked over time (BI / decision
    support) and compared run to run. Produced by the skill-gap engine.
    """

    class Severity(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    department = models.ForeignKey(
        "hr.Department",
        on_delete=models.CASCADE,
        related_name="skill_gap_forecasts",
    )
    skill = models.ForeignKey(
        "hr.Skill",
        on_delete=models.CASCADE,
        related_name="skill_gap_forecasts",
    )

    horizon_months = models.PositiveSmallIntegerField(default=6)

    current_avg_level = models.FloatField()
    velocity_per_month = models.FloatField()
    projected_level = models.FloatField()
    demand_level = models.FloatField()
    gap = models.FloatField()
    coverage = models.FloatField()
    attrition_rate = models.FloatField(default=0.0)
    importance = models.PositiveSmallIntegerField(default=3)

    risk_score = models.FloatField()
    severity = models.CharField(max_length=6, choices=Severity.choices)
    rationale = models.TextField(blank=True)

    # Groups all rows produced by a single engine execution.
    run_id = models.CharField(max_length=36, db_index=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-generated_at", "-risk_score"]
        indexes = [
            models.Index(
                fields=["department", "skill", "-generated_at"],
                name="hr_gap_dept_skill_gen_idx",
            ),
            models.Index(fields=["run_id"], name="hr_gap_run_idx"),
            models.Index(fields=["severity"], name="hr_gap_severity_idx"),
        ]

    def __str__(self):
        return (
            f"{self.department.code}/{self.skill.code} gap={self.gap:.1f} "
            f"risk={self.risk_score:.0f} ({self.severity})"
        )


class EmployeeDocument(models.Model):
    class DocumentType(models.TextChoices):
        CONTRACT = "CONTRACT", "Contract"
        ID = "ID", "Identification"
        CERTIFICATION = "CERTIFICATION", "Certification"
        POLICY_ACK = "POLICY_ACK", "Policy acknowledgement"
        OTHER = "OTHER", "Other"

    employee = models.ForeignKey(
        EmployeeProfile, on_delete=models.CASCADE, related_name="documents"
    )
    doc_type = models.CharField(max_length=20, choices=DocumentType.choices)
    title = models.CharField(max_length=200)
    reference_url = models.CharField(max_length=500)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    uploaded_by_user_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_expiring_soon(self):
        if self.expiry_date is None:
            return False
        today = timezone.localdate()
        return today <= self.expiry_date <= today + timedelta(days=30)


class TrainingAction(models.Model):
    """A concrete, trackable plan to close a skill gap — the action that turns a
    skill-gap forecast into "these people, this course, by this date".

    Closes the future-skills loop: a gap (SkillGapForecast) becomes an owned,
    dated, budgeted action whose progress and outcome are tracked over time.
    """

    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    skill = models.ForeignKey(
        Skill, on_delete=models.CASCADE, related_name="training_actions"
    )
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="training_actions",
    )
    employee = models.ForeignKey(
        EmployeeProfile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="training_actions",
    )
    goal = models.ForeignKey(
        "reviews.Goal", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="training_actions",
    )
    title = models.CharField(max_length=200, help_text="e.g. 'Kubernetes CKA certification'")
    provider = models.CharField(max_length=200, blank=True)
    owner_user_id = models.PositiveBigIntegerField(
        null=True, blank=True, help_text="Auth user id accountable for delivery."
    )
    target_level = models.PositiveSmallIntegerField(null=True, blank=True, help_text="1-4")
    due_date = models.DateField(null=True, blank=True)
    budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PLANNED, db_index=True
    )
    progress_percent = models.PositiveSmallIntegerField(default=0, help_text="0-100")
    notes = models.TextField(blank=True)
    created_by_user_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} [{self.status}] {self.progress_percent}%"


class Notification(models.Model):
    """A user-scoped notification keyed by the auth-service user id."""

    class Type(models.TextChoices):
        TRAINING_ASSIGNED = "TRAINING_ASSIGNED", "Training assigned"
        REVIEW_DUE = "REVIEW_DUE", "Review due"
        RISK_FLAGGED = "RISK_FLAGGED", "Risk flagged"
        OUTCOME_DUE = "OUTCOME_DUE", "Outcome due"
        WELLBEING_FLAGGED = "WELLBEING_FLAGGED", "Wellbeing flagged"
        GENERIC = "GENERIC", "Generic"

    user_id = models.PositiveBigIntegerField(db_index=True)
    type = models.CharField(max_length=32, choices=Type.choices, default=Type.GENERIC)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=500, blank=True)
    read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    digest_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["read", "-created_at"]
        indexes = [models.Index(fields=["user_id", "read", "-created_at"], name="hr_notif_user_read_idx")]

    def __str__(self):
        return f"{self.user_id}: {self.title}"
