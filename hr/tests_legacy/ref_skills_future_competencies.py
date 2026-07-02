from django.test import TestCase
from rest_framework import status

from accounts.models import User
from accounts.tests.helpers import authenticate
from hr.models import Department, EmployeeProfile, EmployeeSkill, Skill


class SkillsFutureCompetenciesTests(TestCase):
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
            # not in manager team (no manager assigned)
        )

        self.skill = Skill.objects.create(
            name="Python",
            code="PYTHON",
            description="Python backend",
            category="Technical",
            created_by=self.hr_user,
        )

    def auth_as(self, user):
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

    # --- Skills ---

    def test_hr_can_create_and_list_skills(self):
        self.auth_as(self.hr_user)

        response = self.client.post(
            "/api/hr/skills/",
            {
                "name": "Django",
                "code": "DJANGO",
                "description": "Django framework",
                "category": "Technical",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        list_resp = self.client.get("/api/hr/skills/")
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        envelope = list_resp.data
        data = envelope.get("data", envelope)
        results = data.get("results", [])
        self.assertGreaterEqual(len(results), 2)  # existing + new

    def test_employee_can_only_read_skills_cannot_create(self):
        self.auth_as(self.emp1_user)

        # List OK
        list_resp = self.client.get("/api/hr/skills/")
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        env = list_resp.data
        data = env.get("data", env)
        results = data.get("results", [])
        self.assertIsInstance(results, list)

        # Create forbidden
        create_resp = self.client.post(
            "/api/hr/skills/",
            {"name": "React", "code": "REACT"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_403_FORBIDDEN)

    # --- Employee skills ---

    def test_manager_can_rate_team_member_skill_but_not_other(self):
        self.auth_as(self.manager_user)

        # OK for team member (emp1)
        resp_ok = self.client.post(
            "/api/hr/employee-skills/",
            {
                "employee_id": self.emp1_profile.id,
                "skill_id": self.skill.id,
                "level": EmployeeSkill.Level.INTERMEDIATE,
                "target_level": EmployeeSkill.Level.ADVANCED,
                "notes": "Doing fine.",
            },
            format="json",
        )
        self.assertEqual(resp_ok.status_code, status.HTTP_201_CREATED)

        # Not ok for non-team member (emp2)
        resp_bad = self.client.post(
            "/api/hr/employee-skills/",
            {
                "employee_id": self.emp2_profile.id,
                "skill_id": self.skill.id,
                "level": EmployeeSkill.Level.BEGINNER,
            },
            format="json",
        )
        self.assertEqual(resp_bad.status_code, status.HTTP_403_FORBIDDEN)

    def test_employee_can_see_only_own_skills(self):
        # Create 2 skills entries: one for emp1, one for emp2
        EmployeeSkill.objects.create(
            employee=self.emp1_profile,
            skill=self.skill,
            level=EmployeeSkill.Level.INTERMEDIATE,
        )
        EmployeeSkill.objects.create(
            employee=self.emp2_profile,
            skill=self.skill,
            level=EmployeeSkill.Level.BEGINNER,
        )

        self.auth_as(self.emp1_user)

        resp = self.client.get("/api/hr/employee-skills/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        envelope = resp.data
        data = envelope.get("data", envelope)
        results = data.get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["employee"]["user"]["email"], self.emp1_user.email)

    # --- Future competencies ---

    def test_hr_can_create_future_competency_employee_cannot(self):
        # HR create
        self.auth_as(self.hr_user)
        resp_hr = self.client.post(
            "/api/hr/future-competencies/",
            {
                "skill_id": self.skill.id,
                "department_id": self.department.id,
                "timeframe": "MEDIUM",
                "importance": 5,
                "description": "Need more Python devs.",
            },
            format="json",
        )
        self.assertEqual(resp_hr.status_code, status.HTTP_201_CREATED)

        # Employee cannot create
        self.auth_as(self.emp1_user)
        resp_emp = self.client.post(
            "/api/hr/future-competencies/",
            {
                "skill_id": self.skill.id,
                "department_id": self.department.id,
                "timeframe": "SHORT",
                "importance": 3,
            },
            format="json",
        )
        self.assertEqual(resp_emp.status_code, status.HTTP_403_FORBIDDEN)
