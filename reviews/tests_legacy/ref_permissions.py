from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from accounts.tests.helpers import authenticate
from hr.models import Department, EmployeeProfile
from reviews.models import PerformanceReview, ReviewCycle


class ReviewPermissionTests(APITestCase):
    def setUp(self):
        self.login_url = "/api/auth/login/"
        self.reviews_url = "/api/reviews/"
        self.items_url = lambda review_id: f"/api/reviews/{review_id}/items/"
        self.submit_url = lambda review_id: f"/api/reviews/{review_id}/submit/"

        dept = Department.objects.create(name="IT", code="IT", description="Tech")

        self.hr_user = User.objects.create_user(
            email="hr3@example.com",
            password="HrPass123!",
            role=User.Role.HR,
            first_name="HR",
            last_name="Three",
        )

        self.manager_user = User.objects.create_user(
            email="manager3@example.com",
            password="ManagerPass123!",
            role=User.Role.MANAGER,
            first_name="Manager",
            last_name="Three",
        )

        self.other_manager_user = User.objects.create_user(
            email="manager4@example.com",
            password="ManagerPass123!",
            role=User.Role.MANAGER,
            first_name="Manager",
            last_name="Four",
        )

        self.emp_user = User.objects.create_user(
            email="emp20@example.com",
            password="EmpPass123!",
            role=User.Role.EMPLOYEE,
            first_name="Emp",
            last_name="Twenty",
        )

        self.auditor_user = User.objects.create_user(
            email="auditor@example.com",
            password="AuditPass123!",
            role=User.Role.EMPLOYEE,
            first_name="Audit",
            last_name="User",
        )
        auditor_group, _ = Group.objects.get_or_create(name="AUDITOR")
        self.auditor_user.groups.add(auditor_group)

        self.manager_profile = EmployeeProfile.objects.create(
            user=self.manager_user,
            department=dept,
            job_title="Lead",
        )

        self.other_manager_profile = EmployeeProfile.objects.create(
            user=self.other_manager_user,
            department=dept,
            job_title="Lead",
        )

        self.emp_profile = EmployeeProfile.objects.create(
            user=self.emp_user,
            department=dept,
            job_title="Developer",
            manager=self.manager_profile,
        )

        self.cycle = ReviewCycle.objects.create(
            name="Q1",
            start_date="2026-01-01",
            end_date="2026-03-31",
            is_active=True,
        )

    def auth(self, email, password):
        authenticate(self.client, email, password)

    def create_review_as_manager(self):
        self.auth("manager3@example.com", "ManagerPass123!")
        resp = self.client.post(
            self.reviews_url,
            {"employee_id": self.emp_profile.id, "cycle_id": self.cycle.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.data.get("data", resp.data)
        return data["id"]

    def test_employee_cannot_submit_review(self):
        review_id = self.create_review_as_manager()
        self.auth("emp20@example.com", "EmpPass123!")
        resp = self.client.post(
            self.submit_url(review_id), {"manager_comment": "Try"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_cannot_submit_non_draft_review(self):
        review_id = self.create_review_as_manager()
        review = PerformanceReview.objects.get(id=review_id)
        review.status = PerformanceReview.Status.SUBMITTED
        review.save(update_fields=["status"])

        self.auth("manager3@example.com", "ManagerPass123!")
        resp = self.client.post(
            self.submit_url(review_id), {"manager_comment": "Again"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_add_items_when_not_draft(self):
        review_id = self.create_review_as_manager()
        review = PerformanceReview.objects.get(id=review_id)
        review.status = PerformanceReview.Status.SUBMITTED
        review.save(update_fields=["status"])

        self.auth("manager3@example.com", "ManagerPass123!")
        resp = self.client.post(
            self.items_url(review_id),
            {"criteria": "Tech", "score": 4, "comment": "good"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_employee_cannot_add_review_item(self):
        review_id = self.create_review_as_manager()
        self.auth("emp20@example.com", "EmpPass123!")
        resp = self.client.post(
            self.items_url(review_id),
            {"criteria": "Tech", "score": 4, "comment": "good"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_cannot_edit_review_they_do_not_own(self):
        # Create review owned by other_manager
        self.auth("hr3@example.com", "HrPass123!")
        # HR creates review with manager = other_manager_profile
        resp = self.client.post(
            self.reviews_url,
            {
                "employee_id": self.emp_profile.id,
                "cycle_id": self.cycle.id,
                "manager": self.other_manager_profile.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        review_id = resp.data.get("data", resp.data)["id"]

        self.auth("manager3@example.com", "ManagerPass123!")
        resp_patch = self.client.patch(
            f"{self.reviews_url}{review_id}/",
            {"manager_comment": "not mine"},
            format="json",
        )
        self.assertEqual(resp_patch.status_code, status.HTTP_403_FORBIDDEN)

    def test_employee_cannot_acknowledge_non_submitted(self):
        review_id = self.create_review_as_manager()
        self.auth("emp20@example.com", "EmpPass123!")
        resp = self.client.post(
            f"{self.reviews_url}{review_id}/acknowledge/",
            {"employee_comment": "ok"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_manager_cannot_submit_completed_review(self):
        review_id = self.create_review_as_manager()
        review = PerformanceReview.objects.get(id=review_id)
        review.status = PerformanceReview.Status.COMPLETED
        review.save(update_fields=["status"])

        self.auth("manager3@example.com", "ManagerPass123!")
        resp = self.client.post(
            self.submit_url(review_id), {"manager_comment": "again"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_employee_cannot_update_someone_elses_goal(self):
        # HR creates goal for other employee
        self.auth("hr3@example.com", "HrPass123!")
        resp_goal = self.client.post(
            "/api/reviews/goals/",
            {
                "title": "Team goal",
                "description": "Desc",
                "status": "IN_PROGRESS",
                "employee_id": self.emp_profile.id,
            },
            format="json",
        )
        self.assertEqual(resp_goal.status_code, status.HTTP_201_CREATED)
        goal_id = resp_goal.data.get("data", resp_goal.data)["id"]

        # Other employee tries to update
        User.objects.create_user(
            email="emp21@example.com",
            password="EmpPass123!",
            role=User.Role.EMPLOYEE,
            first_name="Emp",
            last_name="TwentyOne",
        )
        self.auth("emp21@example.com", "EmpPass123!")
        resp_patch = self.client.patch(
            f"/api/reviews/goals/{goal_id}/",
            {"title": "Hack"},
            format="json",
        )
        self.assertEqual(resp_patch.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_cannot_delete_goal_outside_team(self):
        # HR creates goal for employee managed by manager_profile
        self.auth("hr3@example.com", "HrPass123!")
        resp_goal = self.client.post(
            "/api/reviews/goals/",
            {
                "title": "Delete me",
                "description": "Desc",
                "status": "IN_PROGRESS",
                "employee_id": self.emp_profile.id,
            },
            format="json",
        )
        self.assertEqual(resp_goal.status_code, status.HTTP_201_CREATED)
        goal_id = resp_goal.data.get("data", resp_goal.data)["id"]

        # Other manager tries to delete
        self.auth("manager4@example.com", "ManagerPass123!")
        resp_del = self.client.delete(f"/api/reviews/goals/{goal_id}/")
        self.assertEqual(resp_del.status_code, status.HTTP_403_FORBIDDEN)

    def test_auditor_can_view_reviews_read_only(self):
        review_id = self.create_review_as_manager()
        self.auth("auditor@example.com", "AuditPass123!")

        resp_list = self.client.get(self.reviews_url)
        self.assertEqual(resp_list.status_code, status.HTTP_200_OK)

        resp_detail = self.client.get(f"{self.reviews_url}{review_id}/")
        self.assertEqual(resp_detail.status_code, status.HTTP_200_OK)

        resp_create = self.client.post(
            self.reviews_url,
            {"employee_id": self.emp_profile.id, "cycle_id": self.cycle.id},
            format="json",
        )
        self.assertEqual(resp_create.status_code, status.HTTP_403_FORBIDDEN)

        resp_patch = self.client.patch(
            f"{self.reviews_url}{review_id}/",
            {"manager_comment": "audit"},
            format="json",
        )
        self.assertEqual(resp_patch.status_code, status.HTTP_403_FORBIDDEN)
