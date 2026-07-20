from django.db import models


class ReviewCycle(models.Model):
    """
    A review period, e.g. 'Q1 2025', 'Annual 2025'.
    """

    name = models.CharField(max_length=150)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name

class PerformanceReview(models.Model):
    """
    One performance review for one employee in one cycle.
    Usually created by the manager.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        COMPLETED = "COMPLETED", "Completed"

    # Employee being evaluated
    employee = models.ForeignKey(
        "hr.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="performance_reviews",
    )

    # Manager doing the evaluation
    manager = models.ForeignKey(
        "hr.EmployeeProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_reviews",
    )

    cycle = models.ForeignKey(
        ReviewCycle,
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    overall_score = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average of all item scores, e.g. 3.75",
    )

    employee_comment = models.TextField(blank=True)
    manager_comment = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("employee", "cycle")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Review {self.employee} - {self.cycle.name}"

    def recalculate_overall_score(self):
        """
        Recompute overall_score as the average of all ReviewItem scores.
        """
        rated = [i for i in self.items.all() if i.score is not None]
        if not rated:
            self.overall_score = None
        else:
            total_weight = sum(i.weight for i in rated) or 1
            self.overall_score = (
                sum(i.score * i.weight for i in rated) / total_weight
            )
        self.save(update_fields=["overall_score"])

class ReviewItem(models.Model):
    """
    One criterion inside a performance review, e.g. 'Technical Skills'.
    """

    review = models.ForeignKey(
        PerformanceReview,
        on_delete=models.CASCADE,
        related_name="items",
    )
    criteria = models.CharField(max_length=255)
    # 1–5 scale; null = created from a template, not yet rated
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    weight = models.PositiveSmallIntegerField(
        default=1, help_text="Relative weight in the overall score."
    )
    comment = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.criteria} ({self.score}) for {self.review}"

class Goal(models.Model):
    """
    Employee goals for a given cycle (or general if cycle is null).
    """

    class Status(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Not started"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        DONE = "DONE", "Done"

    employee = models.ForeignKey(
        "hr.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="goals",
    )
    source_review = models.ForeignKey(
        "reviews.PerformanceReview",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spawned_goals",
    )
    cycle = models.ForeignKey(
        ReviewCycle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="goals",
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED,
    )
    progress_percent = models.PositiveSmallIntegerField(
        default=0,
        help_text="0–100",
    )

    # Auth-service user id (by value — no cross-service ForeignKey)
    created_by_user_id = models.PositiveBigIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Goal for {self.employee}: {self.title}"


class ReviewTemplate(models.Model):
    """Reusable set of review criteria (e.g. 'Engineering IC template').

    `items` is a list of {"criteria": str, "weight": int} dicts; applying
    a template at review creation pre-creates unrated ReviewItems.
    """

    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    items = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_by_user_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PeerFeedback(models.Model):
    """360° feedback: colleagues rate a review subject.

    The reviewee sees aggregates and anonymized comments; only HR sees
    who said what (anonymity encourages honesty, auditability is kept).
    """

    class Relationship(models.TextChoices):
        PEER = "PEER", "Peer"
        REPORT = "REPORT", "Direct report"
        OTHER = "OTHER", "Other"

    review = models.ForeignKey(
        PerformanceReview, on_delete=models.CASCADE, related_name="peer_feedback"
    )
    reviewer_user_id = models.PositiveBigIntegerField()
    relationship = models.CharField(
        max_length=20, choices=Relationship.choices, default=Relationship.PEER
    )
    rating = models.PositiveSmallIntegerField(help_text="1-5")
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("review", "reviewer_user_id")
        ordering = ["-created_at"]
