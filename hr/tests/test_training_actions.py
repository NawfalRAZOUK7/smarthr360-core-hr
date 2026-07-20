"""Tests for training actions — closing the skill-gap loop (core-hr)."""

from django.test import TestCase, override_settings

from reviews.models import Goal, PerformanceReview, ReviewCycle

from ..models import EmployeeProfile, Skill, TrainingAction
from .helpers import PUBLIC_PEM, auth_header


class TrainingActionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._s = override_settings(
            SMARTHR_JWT_AUTH={"PUBLIC_KEY": PUBLIC_PEM, "ISSUER": "smarthr360"}
        )
        cls._s.enable()

    @classmethod
    def tearDownClass(cls):
        cls._s.disable()
        super().tearDownClass()

    def setUp(self):
        self.skill = Skill.objects.create(name="Kubernetes", code="K8S", category="tech")

    def test_manager_creates_and_updates_action(self):
        r = self.client.post(
            "/api/hr/training-actions/",
            {"skill_id": self.skill.id, "title": "CKA certification", "target_level": 4, "budget": "1200.00"},
            content_type="application/json",
            **auth_header(1, role="MANAGER"),
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(TrainingAction.objects.count(), 1)
        ta = TrainingAction.objects.first()
        self.assertEqual(ta.status, "PLANNED")

        lst = self.client.get("/api/hr/training-actions/", **auth_header(1, role="MANAGER"))
        self.assertEqual(lst.status_code, 200)

        upd = self.client.patch(
            f"/api/hr/training-actions/{ta.id}/",
            {"status": "IN_PROGRESS", "progress_percent": 50},
            content_type="application/json",
            **auth_header(1, role="MANAGER"),
        )
        self.assertEqual(upd.status_code, 200, upd.content)
        ta.refresh_from_db()
        self.assertEqual(ta.status, "IN_PROGRESS")
        self.assertEqual(ta.progress_percent, 50)

    def test_rbac(self):
        self.assertEqual(
            self.client.get("/api/hr/training-actions/", **auth_header(9, role="EMPLOYEE")).status_code, 403
        )
        self.assertEqual(self.client.get("/api/hr/training-actions/").status_code, 401)
        self.assertEqual(
            self.client.post(
                "/api/hr/training-actions/",
                {"skill_id": self.skill.id, "title": "x"},
                content_type="application/json",
                **auth_header(9, role="EMPLOYEE"),
            ).status_code,
            403,
        )

    def test_only_hr_can_delete(self):
        ta = TrainingAction.objects.create(skill=self.skill, title="x")
        self.assertEqual(
            self.client.delete(f"/api/hr/training-actions/{ta.id}/", **auth_header(1, role="MANAGER")).status_code, 403
        )
        self.assertEqual(
            self.client.delete(f"/api/hr/training-actions/{ta.id}/", **auth_header(1, role="HR")).status_code, 204
        )

    def test_review_goal_training_linkage(self):
        employee = EmployeeProfile.objects.create(user_id=20, email="employee@example.com")
        cycle = ReviewCycle.objects.create(
            name="2026", start_date="2026-01-01", end_date="2026-12-31"
        )
        review = PerformanceReview.objects.create(employee=employee, cycle=cycle)
        goal = Goal.objects.create(
            employee=employee, cycle=cycle, source_review=review, title="Grow platform skills"
        )

        response = self.client.post(
            "/api/hr/training-actions/",
            {"skill_id": self.skill.id, "goal_id": goal.id, "title": "CKA certification"},
            content_type="application/json",
            **auth_header(1, role="HR"),
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["data"]["goal"]["id"], goal.id)
        goal_response = self.client.get(
            f"/api/reviews/goals/{goal.id}/", **auth_header(1, role="HR")
        )
        self.assertEqual(goal_response.status_code, 200, goal_response.content)
        self.assertEqual(goal_response.json()["data"]["training_actions_count"], 1)
        self.assertEqual(goal.source_review_id, review.id)
