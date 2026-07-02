from django.test import TestCase
from rest_framework import status

from accounts.models import User
from accounts.tests.helpers import authenticate
from hr.models import Department, EmployeeProfile
from reviews.models import PerformanceReview, ReviewCycle


class ReviewsModuleTests(TestCase):
    def setUp(self):
        # Users
        self.hr_user = User.objects.create_user(
            email="hr@example.com",
            password="HrPass123!",
            role=User.Role.HR,
            first_name="HR",
            last_name="User",
        )
        self.manager_user = User.objects.create_user(
            email="manager@example.com",
            password="ManagerPass123!",
            role=User.Role.MANAGER,
            first_name="Mona",
            last_name="Manager",
        )
        self.emp1_user = User.objects.create_user(
            email="emp1@example.com",
            password="EmpPass123!",
            role=User.Role.EMPLOYEE,
            first_name="Emp",
            last_name="One",
        )
        self.emp2_user = User.objects.create_user(
            email="emp2@example.com",
            password="EmpPass123!",
            role=User.Role.EMPLOYEE,
            first_name="Emp",
            last_name="Two",
        )

        self.department = Department.objects.create(
            name="IT",
            code="IT",
            description="IT Department",
        )

        # Profiles
        self.manager_profile = EmployeeProfile.objects.create(
            user=self.manager_user,
            department=self.department,
            job_title="Team Lead",
        )
        self.emp1_profile = EmployeeProfile.objects.create(
            user=self.emp1_user,
            department=self.department,
            job_title="Developer",
            manager=self.manager_profile,
        )
        self.emp2_profile = EmployeeProfile.objects.create(
            user=self.emp2_user,
            department=self.department,
            job_title="QA",
            # not in manager's team
        )

        self.cycle = ReviewCycle.objects.create(
            name="Q1 2026",
            start_date="2026-01-01",
            end_date="2026-03-31",
            is_active=True,
        )

    def auth_as(self, user):
        """
        Helper: logs in the given user and sets Authorization header.
        Envelope-aware:
        {"data": {"tokens": {"access": "..."}}, "meta": {"success": true}}
        """
        password = (
            "HrPass123!"
            if user == self.hr_user
            else "ManagerPass123!"
            if user == self.manager_user
            else "EmpPass123!"
        )

        try:
            authenticate(self.client, user.email, password)
        except AssertionError as exc:
            self.fail(str(exc))

    # --- Cycles ---

    def test_hr_can_create_cycle(self):
        self.auth_as(self.hr_user)
        resp = self.client.post(
            "/api/reviews/cycles/",
            {
                "name": "Annual 2026",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # Envelope: { "data": {...}, "meta": {...} }
        self.assertIn("data", resp.data)
        self.assertIsInstance(resp.data["data"], dict)
        self.assertEqual(resp.data["data"]["name"], "Annual 2026")

    # --- Reviews ---

    def test_manager_can_create_review_for_team_member_but_not_non_team(self):
        self.auth_as(self.manager_user)

        # OK for emp1 (in team)
        ok_resp = self.client.post(
            "/api/reviews/",
            {"employee_id": self.emp1_profile.id, "cycle_id": self.cycle.id},
            format="json",
        )
        self.assertEqual(ok_resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("data", ok_resp.data)
        self.assertEqual(
            ok_resp.data["data"]["employee"]["user"]["email"],
            self.emp1_user.email,
        )

        # Not OK for emp2 (not in team)
        bad_resp = self.client.post(
            "/api/reviews/",
            {"employee_id": self.emp2_profile.id, "cycle_id": self.cycle.id},
            format="json",
        )
        self.assertEqual(bad_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_review_status_flow_submit_and_acknowledge(self):
        # Manager creates review
        self.auth_as(self.manager_user)
        create_resp = self.client.post(
            "/api/reviews/",
            {"employee_id": self.emp1_profile.id, "cycle_id": self.cycle.id},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("data", create_resp.data)
        review_id = create_resp.data["data"]["id"]

        # Add one item (also enveloped)
        item_resp = self.client.post(
            f"/api/reviews/{review_id}/items/",
            {
                "criteria": "Technical Skills",
                "score": 4,
                "comment": "Solid.",
            },
            format="json",
        )
        self.assertEqual(item_resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("data", item_resp.data)
        self.assertEqual(item_resp.data["data"]["criteria"], "Technical Skills")

        # Submit review
        submit_resp = self.client.post(
            f"/api/reviews/{review_id}/submit/",
            {"manager_comment": "Good quarter."},
            format="json",
        )
        self.assertEqual(submit_resp.status_code, status.HTTP_200_OK)
        # Envelope + status inside data
        self.assertIn("data", submit_resp.data)
        self.assertEqual(
            submit_resp.data["data"]["status"],
            PerformanceReview.Status.SUBMITTED,
        )

        # Employee acknowledges
        self.auth_as(self.emp1_user)
        ack_resp = self.client.post(
            f"/api/reviews/{review_id}/acknowledge/",
            {"employee_comment": "I agree."},
            format="json",
        )
        self.assertEqual(ack_resp.status_code, status.HTTP_200_OK)
        self.assertIn("data", ack_resp.data)
        self.assertEqual(
            ack_resp.data["data"]["status"],
            PerformanceReview.Status.COMPLETED,
        )

    def test_employee_can_see_only_own_reviews(self):
        # Manager creates one review for emp1
        self.auth_as(self.manager_user)
        r1 = self.client.post(
            "/api/reviews/",
            {"employee_id": self.emp1_profile.id, "cycle_id": self.cycle.id},
            format="json",
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)

        # Manager cannot review employees outside their team
        r2 = self.client.post(
            "/api/reviews/",
            {"employee_id": self.emp2_profile.id, "cycle_id": self.cycle.id},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_403_FORBIDDEN)

        # As emp1, list reviews
        self.auth_as(self.emp1_user)
        list_resp = self.client.get("/api/reviews/")
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)

        # Paginated + enveloped list: { "data": {"results": [...]}, "meta": {...} }
        envelope = list_resp.data
        data = envelope.get("data", envelope)
        results = data.get("results", [])
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["employee"]["user"]["email"],
            self.emp1_user.email,
        )

    # --- Goals ---

    def test_employee_can_create_own_goal(self):
        self.auth_as(self.emp1_user)
        resp = self.client.post(
            "/api/reviews/goals/",
            {
                "title": "Improve communication",
                "description": "Present in team meeting once a month",
                "status": "IN_PROGRESS",
                "progress_percent": 30,
                "cycle_id": self.cycle.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("data", resp.data)

        goal_data = resp.data["data"]
        self.assertEqual(goal_data["title"], "Improve communication")
        self.assertEqual(
            goal_data["employee"]["user"]["email"],
            self.emp1_user.email,
        )
