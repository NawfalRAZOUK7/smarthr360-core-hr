import uuid

from django.db import models

from hr.models import Department


class WellbeingSurvey(models.Model):
    """
    A well-being / mental load survey created by HR.
    Example: 'Stress & Satisfaction Q1 2026'.
    """

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    # Auth-service user id (by value — no cross-service ForeignKey)
    created_by_user_id = models.PositiveBigIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

class SurveyQuestion(models.Model):
    """
    Question belonging to a wellbeing survey.
    Types:
        - SCALE_1_5  → numeric 1–5
        - YES_NO     → 'yes' / 'no'
        - TEXT       → free text
    """

    class QuestionType(models.TextChoices):
        SCALE_1_5 = "SCALE_1_5", "Scale 1–5"
        YES_NO = "YES_NO", "Yes / No"
        TEXT = "TEXT", "Free text"

    survey = models.ForeignKey(
        WellbeingSurvey,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    text = models.CharField(max_length=500)
    type = models.CharField(
        max_length=20,
        choices=QuestionType.choices,
        default=QuestionType.SCALE_1_5,
    )
    order = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"[{self.survey.title}] {self.text[:50]}"

class SurveyResponse(models.Model):
    """
    Anonymous response to a wellbeing survey.

    ⚠ Privacy constraints:
    - NO direct link to User or EmployeeProfile.
    - No IP, no user agent.
    - We only store:
        * survey (which survey)
        * a random response_id (UUID)
        * answers as JSON: {question_id: value}
        * optional department (for aggregated stats)
        * submitted_at timestamp
    """

    survey = models.ForeignKey(
        WellbeingSurvey,
        on_delete=models.CASCADE,
        related_name="responses",
    )

    # Pseudonymous ID for one submission (not linked to user)
    response_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Example structure:
    # {
    #   "3": 4,           # question id 3, score 4
    #   "4": "yes",       # question id 4, answer "yes"
    #   "5": "Feeling tired lately"
    # }
    answers = models.JSONField()

    # Optional: department at time of submission for aggregated stats / heatmaps
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wellbeing_responses",
    )

    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"Response {self.response_id} for {self.survey.title}"
