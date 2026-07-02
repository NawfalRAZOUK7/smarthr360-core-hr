from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from hr.models import Department, EmployeeProfile, Skill


class HRPermissionsTests(APITestCase):
    def setUp(self):
        self.employees_url = "/api/hr/employees/"
        self.employee_skills_url = "/api/hr/employee-skills/"
        self.login_url = "/api/auth/login/"

        self.dept = Department.objects.create(name="IT", code="IT", description="Tech")

        self.hr_user = User.objects.create_user(
            email="hr2@example.com",
            password="HrPass123!",
            role=User.Role.HR,
            first_name="HR",
            last_name="Two",
        )

        self.manager_user = User.objects.create_user(
            email="manager2@example.com",
            password="ManagerPass123!",
            role=User.Role.MANAGER,
            first_name="Manager",
            last_name="Two",
        )

        self.emp_user = User.objects.create_user(
            email="emp10@example.com",
            password="EmpPass123!",
            role=User.Role.EMPLOYEE,
            first_name="Emp",
            last_name="Ten",
        )

        self.emp_other_user = User.objects.create_user(
            email="emp11@example.com",
            password="EmpPass123!",
            role=User.Role.EMPLOYEE,
            first_name="Emp",
            last_name="Eleven",
        )

        self.manager_profile = EmployeeProfile.objects.create(
            user=self.manager_user,
            department=self.dept,
            job_title="Lead",
        )

        self.emp_profile = EmployeeProfile.objects.create(
            user=self.emp_user,
            department=self.dept,
            job_title="Dev",
            manager=self.manager_profile,
        )

        self.emp_other_profile = EmployeeProfile.objects.create(
            user=self.emp_other_user,
            department=self.dept,
            job_title="QA",
            # No manager → not in manager_profile's team
        )

        self.skill = Skill.objects.create(name="Python", category="Tech", is_active=True)

    def auth(self, email, password):
        resp = self.client.post(
            self.login_url,
            {"email": email, "password": password},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        envelope = resp.data
        data = envelope.get("data", envelope)
        tokens = data.get("tokens", {})
        access = tokens.get("access")
        self.assertIsNotNone(access)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_employee_cannot_list_employees(self):
        self.auth("emp10@example.com", "EmpPass123!")
        resp = self.client.get(self.employees_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_cannot_create_employee_profile(self):
        self.auth("manager2@example.com", "ManagerPass123!")
        new_user = User.objects.create_user(
            email="newperson@example.com",
            password="TempPass123!",
            role=User.Role.EMPLOYEE,
            first_name="New",
            last_name="Person",
        )
        payload = {
            "user_id": new_user.id,
            "department": self.dept.id,
            "job_title": "New Joiner",
        }
        resp = self.client.post(self.employees_url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_employee_cannot_create_employee_skill(self):
        self.auth("emp10@example.com", "EmpPass123!")
        payload = {
            "employee_id": self.emp_profile.id,
            "skill_id": self.skill.id,
            "proficiency": "BEGINNER",
        }
        resp = self.client.post(self.employee_skills_url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_cannot_rate_non_team_member(self):
        self.auth("manager2@example.com", "ManagerPass123!")
        payload = {
            "employee_id": self.emp_other_profile.id,
            "skill_id": self.skill.id,
            "proficiency": "ADVANCED",
        }
        resp = self.client.post(self.employee_skills_url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_employee_list_pagination_meta_for_hr(self):
        self.auth("hr2@example.com", "HrPass123!")
        resp = self.client.get(self.employees_url + "?page=1&page_size=10")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        envelope = resp.data
        data = envelope.get("data", envelope)
        meta = envelope.get("meta", {})

        self.assertIsInstance(data.get("results", []), list)
        self.assertEqual(meta.get("page"), 1)
        self.assertEqual(meta.get("page_size"), 10)
