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
        items = self.items.all()
        if not items.exists():
            self.overall_score = None
        else:
            total = sum(i.score for i in items)
            self.overall_score = total / items.count()
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
    # 1–5 scale
    score = models.PositiveSmallIntegerField()
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
