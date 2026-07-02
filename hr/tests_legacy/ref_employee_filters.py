# hr/tests/test_employee_filters.py

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from accounts.tests.helpers import authenticate
from hr.models import Department, EmployeeProfile


class EmployeeFiltersTests(APITestCase):
    """
    Tests filtering on /api/hr/employees/ for HR role:

    - ?department=IT
    - ?is_active=true / false
    - ?manager=<id>
    """

    def setUp(self):
        self.employees_url = "/api/hr/employees/"
        self.login_url = "/api/auth/login/"

        # --- Users ---
        self.hr_password = "HrPass123!"
        self.emp_password = "EmpPass123!"
        self.manager_password = "ManagerPass123!"

        self.hr_user = User.objects.create_user(
            email="hr@example.com",
            password=self.hr_password,
            role=User.Role.HR,
            first_name="HR",
            last_name="User",
        )

        self.manager_user = User.objects.create_user(
            email="manager@example.com",
            password=self.manager_password,
            role=User.Role.MANAGER,
            first_name="Manager",
            last_name="User",
        )

        self.emp1_user = User.objects.create_user(
            email="emp1@example.com",
            password=self.emp_password,
            role=User.Role.EMPLOYEE,
            first_name="Emp",
            last_name="One",
        )

        self.emp2_user = User.objects.create_user(
            email="emp2@example.com",
            password=self.emp_password,
            role=User.Role.EMPLOYEE,
            first_name="Emp",
            last_name="Two",
        )

        self.emp3_user = User.objects.create_user(
            email="emp3@example.com",
            password=self.emp_password,
            role=User.Role.EMPLOYEE,
            first_name="Emp",
            last_name="Three",
        )

        # --- Departments ---
        self.dep_it = Department.objects.create(
            name="IT Department",
            code="IT",
            description="Tech department",
        )
        self.dep_hr = Department.objects.create(
            name="HR Department",
            code="HR",
            description="Human resources",
        )

        # --- Manager profile ---
        self.manager_profile = EmployeeProfile.objects.create(
            user=self.manager_user,
            department=self.dep_it,
            job_title="Team Lead",
            is_active=True,
        )

        # --- Employee profiles ---
        # IT + active, managed by manager_profile
        self.emp1_profile = EmployeeProfile.objects.create(
            user=self.emp1_user,
            department=self.dep_it,
            job_title="Developer",
            manager=self.manager_profile,
            is_active=True,
        )

        # HR + inactive, no manager
        self.emp2_profile = EmployeeProfile.objects.create(
            user=self.emp2_user,
            department=self.dep_hr,
            job_title="HR Assistant",
            is_active=False,
        )

        # IT + active, but no manager
        self.emp3_profile = EmployeeProfile.objects.create(
            user=self.emp3_user,
            department=self.dep_it,
            job_title="Data Analyst",
            is_active=True,
        )

    # Small helper, same spirit as in other tests
    def auth_as(self, user, password):
        authenticate(self.client, user.email, password)

    def test_filter_by_department_code(self):
        """
        HR can filter employees by department code: ?department=IT
        """
        self.auth_as(self.hr_user, self.hr_password)

        resp = self.client.get(self.employees_url + "?department=IT", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # envelope + pagination: { "data": {"results": [...]}, "meta": {...} }
        envelope = resp.data
        data = envelope.get("data", envelope)
        results = data.get("results", [])
        self.assertTrue(isinstance(results, list))

        # Only IT department employees must appear
        self.assertTrue(len(results) >= 1)
        for emp in results:
            dep = emp.get("department") or {}
            self.assertEqual(dep.get("code"), "IT")

        # We created 2 IT employees (emp1, emp3) + manager_profile in IT → total 3
        self.assertEqual(len(results), 3)

    def test_filter_by_is_active_true(self):
        """
        HR can filter employees by is_active=true.
        """
        self.auth_as(self.hr_user, self.hr_password)

        resp = self.client.get(self.employees_url + "?is_active=true", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        envelope = resp.data
        data = envelope.get("data", envelope)
        results = data.get("results", [])
        self.assertTrue(isinstance(results, list))

        for emp in results:
            self.assertTrue(emp.get("is_active"))

        # We created 2 active employees: emp1, emp3, plus manager_profile (HR can see all).
        # But endpoint is /employees/ → EmployeeProfile only,
        # so manager_profile is also counted.
        self.assertEqual(len(results), 3)

    def test_filter_by_is_active_false(self):
        """
        HR can filter employees by is_active=false.
        """
        self.auth_as(self.hr_user, self.hr_password)

        resp = self.client.get(self.employees_url + "?is_active=false", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        envelope = resp.data
        data = envelope.get("data", envelope)
        results = data.get("results", [])
        self.assertTrue(isinstance(results, list))

        for emp in results:
            self.assertFalse(emp.get("is_active"))

        # Only emp2_profile is inactive
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["user"]["email"], self.emp2_user.email)

    def test_filter_by_manager_id(self):
        """
        HR can filter employees by manager=<id>.
        """
        self.auth_as(self.hr_user, self.hr_password)

        manager_id = self.manager_profile.id
        resp = self.client.get(
            f"{self.employees_url}?manager={manager_id}",
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        envelope = resp.data
        data = envelope.get("data", envelope)
        results = data.get("results", [])
        self.assertTrue(isinstance(results, list))

        # Only employees with this manager_id should appear (emp1_profile)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["user"]["email"], self.emp1_user.email)
