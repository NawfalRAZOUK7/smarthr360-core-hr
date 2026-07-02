# hr/tests/test_hr_permissions.py

from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from accounts.tests.helpers import authenticate
from hr.models import Department, EmployeeProfile


class HRPermissionsTests(APITestCase):
    """
    Tests HR + manager + employee permissions on HR endpoints.
    All users are created fresh via REGISTER + ORM.
    """

    def setUp(self):
        self.employees_url = "/api/hr/employees/"
        self.employee_me_url = "/api/hr/employees/me/"
        self.my_team_url = "/api/hr/employees/my-team/"
        self.login_url = "/api/auth/login/"
        self.register_url = "/api/auth/register/"

        # ---- Create users via REGISTER endpoint ----

        # HR user
        hr_payload = {
            "email": "hr@example.com",
            "username": "hr_user",
            "first_name": "HR",
            "last_name": "User",
            "password": "HrPass123!",
            "role": "HR",
        }
        resp_hr = self.client.post(self.register_url, hr_payload, format="json")
        self.assertEqual(resp_hr.status_code, status.HTTP_201_CREATED)

        # Manager user
        manager_payload = {
            "email": "manager@example.com",
            "username": "manager_user",
            "first_name": "Mona",
            "last_name": "Manager",
            "password": "ManagerPass123!",
            "role": "MANAGER",
        }
        resp_manager = self.client.post(self.register_url, manager_payload, format="json")
        self.assertEqual(resp_manager.status_code, status.HTTP_201_CREATED)

        # Employee (team member)
        team_emp_payload = {
            "email": "teamemp@example.com",
            "username": "teamemp_user",
            "first_name": "Team",
            "last_name": "Employee",
            "password": "EmpPass123!",
            "role": "EMPLOYEE",
        }
        resp_team_emp = self.client.post(self.register_url, team_emp_payload, format="json")
        self.assertEqual(resp_team_emp.status_code, status.HTTP_201_CREATED)

        # Employee (non-team)
        other_emp_payload = {
            "email": "otheremp@example.com",
            "username": "otheremp_user",
            "first_name": "Other",
            "last_name": "Employee",
            "password": "EmpPass123!",
            "role": "EMPLOYEE",
        }
        resp_other_emp = self.client.post(self.register_url, other_emp_payload, format="json")
        self.assertEqual(resp_other_emp.status_code, status.HTTP_201_CREATED)

        self.auditor_user = User.objects.create_user(
            email="auditor@example.com",
            password="AuditPass123!",
            role=User.Role.EMPLOYEE,
            first_name="Audit",
            last_name="User",
        )
        auditor_group, _ = Group.objects.get_or_create(name="AUDITOR")
        self.auditor_user.groups.add(auditor_group)

        # Retrieve User instances from DB
        self.hr_user = User.objects.get(email="hr@example.com")
        self.manager_user = User.objects.get(email="manager@example.com")
        self.emp_team_user = User.objects.get(email="teamemp@example.com")
        self.emp_other_user = User.objects.get(email="otheremp@example.com")

        # Department
        self.dept = Department.objects.create(
            name="IT",
            code="IT",
            description="IT Department",
        )

        # Employee profiles
        self.hr_profile = EmployeeProfile.objects.create(
            user=self.hr_user,
            department=self.dept,
            job_title="HR Manager",
        )

        self.manager_profile = EmployeeProfile.objects.create(
            user=self.manager_user,
            department=self.dept,
            job_title="Team Lead",
        )

        self.team_emp_profile = EmployeeProfile.objects.create(
            user=self.emp_team_user,
            department=self.dept,
            job_title="Developer",
            manager=self.manager_profile,
        )

        self.other_emp_profile = EmployeeProfile.objects.create(
            user=self.emp_other_user,
            department=self.dept,
            job_title="Designer",
        )

    # ---------- Helpers ----------

    # ---------- Tests ----------

    def test_hr_can_list_all_employees(self):
        authenticate(self.client, "hr@example.com", "HrPass123!")

        response = self.client.get(self.employees_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        envelope = response.data
        data = envelope.get("data", envelope)
        results = data.get("results", [])
        # hr + manager + 2 employees = 4 profiles
        self.assertEqual(len(results), 4)

    def test_auditor_can_list_all_employees(self):
        authenticate(self.client, "auditor@example.com", "AuditPass123!")

        response = self.client.get(self.employees_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_employee_cannot_list_all_employees(self):
        authenticate(self.client, "teamemp@example.com", "EmpPass123!")

        response = self.client.get(self.employees_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_employee_me_get_and_patch(self):
        authenticate(self.client, "teamemp@example.com", "EmpPass123!")

        # GET own profile
        response_get = self.client.get(self.employee_me_url)
        self.assertEqual(response_get.status_code, status.HTTP_200_OK)
        envelope = response_get.data
        data = envelope.get("data", envelope)
        self.assertEqual(data["user"]["email"], "teamemp@example.com")

        # PATCH allowed fields
        response_patch = self.client.patch(
            self.employee_me_url,
            {"phone_number": "+212600000000"},
            format="json",
        )
        self.assertEqual(response_patch.status_code, status.HTTP_200_OK)
        envelope_patch = response_patch.data
        data_patch = envelope_patch.get("data", envelope_patch)
        self.assertEqual(data_patch["phone_number"], "+212600000000")

    def test_manager_my_team_returns_only_direct_reports(self):
        authenticate(self.client, "manager@example.com", "ManagerPass123!")

        response = self.client.get(self.my_team_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        envelope = response.data
        data = envelope.get("data", envelope)
        results = data.get("results", [])
        emails = [item["user"]["email"] for item in results]
        self.assertIn("teamemp@example.com", emails)
        self.assertNotIn("otheremp@example.com", emails)
        self.assertNotIn("hr@example.com", emails)

    def test_auditor_cannot_create_employee_profile(self):
        authenticate(self.client, "auditor@example.com", "AuditPass123!")

        new_user = User.objects.create_user(
            email="auditorcreate@example.com",
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
        response = self.client.post(self.employees_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_access_team_member_but_not_other_employee(self):
        authenticate(self.client, "manager@example.com", "ManagerPass123!")

        # team member → allowed
        url_team = f"/api/hr/employees/{self.team_emp_profile.id}/"
        response_team = self.client.get(url_team)
        self.assertEqual(response_team.status_code, status.HTTP_200_OK)

        # non-team employee → forbidden
        url_other = f"/api/hr/employees/{self.other_emp_profile.id}/"
        response_other = self.client.get(url_other)
        self.assertEqual(response_other.status_code, status.HTTP_403_FORBIDDEN)

    def test_hr_can_access_any_employee_detail(self):
        authenticate(self.client, "hr@example.com", "HrPass123!")

        url = f"/api/hr/employees/{self.other_emp_profile.id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        envelope = response.data
        data = envelope.get("data", envelope)
        self.assertEqual(data["user"]["email"], "otheremp@example.com")
