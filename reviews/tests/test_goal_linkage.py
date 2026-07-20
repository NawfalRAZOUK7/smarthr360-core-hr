from django.test import TestCase

from hr.models import EmployeeProfile, Skill, TrainingAction
from reviews.models import Goal, PerformanceReview, ReviewCycle
from reviews.serializers import GoalSerializer


class GoalLinkageTests(TestCase):
    def test_goal_reports_source_review_and_training_count(self):
        employee = EmployeeProfile.objects.create(user_id=30, email="goal@example.com")
        cycle = ReviewCycle.objects.create(
            name="2026 goals", start_date="2026-01-01", end_date="2026-12-31"
        )
        review = PerformanceReview.objects.create(employee=employee, cycle=cycle)
        goal = Goal.objects.create(employee=employee, source_review=review, title="Learn Kubernetes")
        skill = Skill.objects.create(name="Kubernetes", code="GOAL-K8S", category="tech")
        TrainingAction.objects.create(skill=skill, goal=goal, title="Complete CKA")

        data = GoalSerializer(goal).data

        self.assertEqual(goal.source_review_id, review.id)
        self.assertEqual(data["training_actions_count"], 1)
