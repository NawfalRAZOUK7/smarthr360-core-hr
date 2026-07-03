"""Service smoke tests: token identity, role authorization, core flows.

These replace the legacy monolith tests (hr/tests_legacy) which assumed
a local accounts app. Here identity comes exclusively from RS256 JWTs.
"""

from django.test import TestCase, override_settings

from smarthr360_jwt_auth import conf

from hr.models import Department, EmployeeProfile, Skill

from .helpers import PUBLIC_PEM, auth_header


class ServiceSmokeTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._settings = override_settings(
            SMARTHR_JWT_AUTH={"PUBLIC_KEY": PUBLIC_PEM, "ISSUER": "smarthr360"}
        )
        cls._settings.enable()
        conf.clear_cache()

    @classmethod
    def tearDownClass(cls):
        cls._settings.disable()
        conf.clear_cache()
        super().tearDownClass()

    # ------------------------------------------------------------------ auth

    def test_anonymous_is_rejected(self):
        resp = self.client.get("/api/hr/departments/")
        self.assertEqual(resp.status_code, 401)

    def test_healthz_is_public(self):
        resp = self.client.get("/healthz/")
        self.assertEqual(resp.status_code, 200)

    # ------------------------------------------------------------- profiles

    def test_me_lazily_creates_profile_from_claims(self):
        resp = self.client.get(
            "/api/hr/employees/me/", **auth_header(101, "EMPLOYEE", email="al@corp.com")
        )
        self.assertEqual(resp.status_code, 200)
        profile = EmployeeProfile.objects.get(user_id=101)
        self.assertEqual(profile.email, "al@corp.com")
        self.assertEqual(profile.user_role, "EMPLOYEE")

    def test_hr_creates_profile_for_user_id(self):
        dept = Department.objects.create(name="IT", code="IT")
        resp = self.client.post(
            "/api/hr/employees/",
            {
                "user_id": 202,
                "email": "dev@corp.com",
                "job_title": "Developer",
                "department_id": dept.id,
            },
            content_type="application/json",
            **auth_header(1, "HR"),
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(EmployeeProfile.objects.filter(user_id=202).exists())

    def test_employee_cannot_create_profiles(self):
        resp = self.client.post(
            "/api/hr/employees/",
            {"user_id": 303},
            content_type="application/json",
            **auth_header(9, "EMPLOYEE"),
        )
        self.assertEqual(resp.status_code, 403)

    def test_employee_sees_own_profile_not_others(self):
        own = EmployeeProfile.objects.create(user_id=10, email="own@corp.com")
        other = EmployeeProfile.objects.create(user_id=11, email="other@corp.com")
        ok = self.client.get(f"/api/hr/employees/{own.id}/", **auth_header(10))
        denied = self.client.get(f"/api/hr/employees/{other.id}/", **auth_header(10))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(denied.status_code, 403)

    def test_manager_sees_direct_team_member(self):
        mgr = EmployeeProfile.objects.create(user_id=20, user_role="MANAGER")
        member = EmployeeProfile.objects.create(user_id=21, manager=mgr)
        resp = self.client.get(
            f"/api/hr/employees/{member.id}/", **auth_header(20, "MANAGER")
        )
        self.assertEqual(resp.status_code, 200)

    # --------------------------------------------------------------- skills

    def test_manager_creates_skill_with_creator_user_id(self):
        resp = self.client.post(
            "/api/hr/skills/",
            {"name": "Python", "code": "PY"},
            content_type="application/json",
            **auth_header(30, "MANAGER"),
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Skill.objects.get(code="PY").created_by_user_id, 30)

    def test_skill_evaluation_flow(self):
        mgr = EmployeeProfile.objects.create(user_id=40, user_role="MANAGER")
        member = EmployeeProfile.objects.create(user_id=41, manager=mgr)
        skill = Skill.objects.create(name="Django", code="DJ")
        resp = self.client.post(
            "/api/hr/employee-skills/",
            {"employee_id": member.id, "skill_id": skill.id, "level": 3},
            content_type="application/json",
            **auth_header(40, "MANAGER"),
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        evaluation = member.skills.get()
        self.assertEqual(evaluation.last_evaluated_by_user_id, 40)

    def test_manager_cannot_rate_outside_team(self):
        EmployeeProfile.objects.create(user_id=50, user_role="MANAGER")
        outsider = EmployeeProfile.objects.create(user_id=51)  # no manager
        skill = Skill.objects.create(name="K8s", code="K8S")
        resp = self.client.post(
            "/api/hr/employee-skills/",
            {"employee_id": outsider.id, "skill_id": skill.id, "level": 2},
            content_type="application/json",
            **auth_header(50, "MANAGER"),
        )
        self.assertEqual(resp.status_code, 403)

    # ---------------------------------------------------------- reviews app

    def test_goal_creation_records_creator_user_id(self):
        emp = EmployeeProfile.objects.create(user_id=60)
        resp = self.client.post(
            "/api/reviews/goals/",
            {"employee_id": emp.id, "title": "Ship v1"},
            content_type="application/json",
            **auth_header(2, "HR"),
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        goal = emp.goals.get()
        self.assertEqual(goal.created_by_user_id, 2)
        self.assertEqual(resp.json()["data"]["employee"]["user"]["id"], 60)

    # -------------------------------------------------------- wellbeing app

    def test_wellbeing_survey_created_by_hr(self):
        resp = self.client.post(
            "/api/wellbeing/surveys/",
            {"title": "Pulse Q3"},
            content_type="application/json",
            **auth_header(3, "HR"),
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["data"]["created_by_user_id"], 3)

    def test_expired_or_bad_token_rejected(self):
        resp = self.client.get(
            "/api/hr/departments/", HTTP_AUTHORIZATION="Bearer not-a-token"
        )
        self.assertEqual(resp.status_code, 401)

    # ------------------------------------------------- wellbeing anonymity

    def test_wellbeing_stats_suppressed_below_threshold(self):
        # create survey with one question and a single response
        survey = self.client.post(
            "/api/wellbeing/surveys/", {"title": "Tiny sample"},
            content_type="application/json", **auth_header(3, "HR"),
        ).json()["data"]
        q = self.client.post(
            f"/api/wellbeing/surveys/{survey['id']}/questions/",
            {"text": "Stress?", "type": "SCALE_1_5", "order": 1},
            content_type="application/json", **auth_header(3, "HR"),
        ).json()["data"]
        self.client.post(
            f"/api/wellbeing/surveys/{survey['id']}/submit/",
            {"answers": {str(q["id"]): "4"}},
            content_type="application/json", **auth_header(90, "EMPLOYEE"),
        )

        stats = self.client.get(
            f"/api/wellbeing/surveys/{survey['id']}/stats/",
            **auth_header(3, "HR"),
        ).json()["data"]
        self.assertTrue(stats["suppressed"])
        self.assertEqual(stats["responses_count"], 1)

        # 4 more submissions cross the threshold -> real stats
        for uid in range(91, 95):
            self.client.post(
                f"/api/wellbeing/surveys/{survey['id']}/submit/",
                {"answers": {str(q["id"]): "3"}},
                content_type="application/json", **auth_header(uid, "EMPLOYEE"),
            )
        stats = self.client.get(
            f"/api/wellbeing/surveys/{survey['id']}/stats/",
            **auth_header(3, "HR"),
        ).json()["data"]
        self.assertNotIn("suppressed", stats)
