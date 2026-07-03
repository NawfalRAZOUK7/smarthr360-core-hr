"""Org chart, skill matrix, CSV, review templates and 360° feedback."""

import csv
import io
import tempfile

from django.core.management import call_command
from django.test import TestCase, override_settings

from smarthr360_jwt_auth import conf

from hr.models import Department, EmployeeProfile, EmployeeSkill, Skill
from reviews.models import PeerFeedback, PerformanceReview, ReviewCycle

from .helpers import PUBLIC_PEM, auth_header


class BaseCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._s = override_settings(
            SMARTHR_JWT_AUTH={"PUBLIC_KEY": PUBLIC_PEM, "ISSUER": "smarthr360"}
        )
        cls._s.enable()
        conf.clear_cache()

    @classmethod
    def tearDownClass(cls):
        cls._s.disable()
        conf.clear_cache()
        super().tearDownClass()

    def setUp(self):
        self.eng = Department.objects.create(name="Engineering", code="ENG")
        self.mgr = EmployeeProfile.objects.create(
            user_id=1, email="mgr@c.com", first_name="Mounir",
            user_role="MANAGER", department=self.eng, job_title="EM",
        )
        self.dev = EmployeeProfile.objects.create(
            user_id=2, email="dev@c.com", first_name="Youssef",
            manager=self.mgr, department=self.eng, job_title="Dev",
        )
        self.dev2 = EmployeeProfile.objects.create(
            user_id=3, email="dev2@c.com", first_name="Sara",
            manager=self.mgr, department=self.eng, job_title="Dev",
        )


class OrgChartTests(BaseCase):
    def test_tree_structure(self):
        resp = self.client.get("/api/hr/org-chart/", **auth_header(2))
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()["data"]
        self.assertEqual(body["headcount"], 3)
        root = body["roots"][0]
        self.assertEqual(root["user_id"], 1)
        self.assertEqual(
            sorted(r["user_id"] for r in root["reports"]), [2, 3]
        )


class SkillMatrixTests(BaseCase):
    def setUp(self):
        super().setUp()
        py = Skill.objects.create(name="Python", code="PY")
        EmployeeSkill.objects.create(
            employee=self.dev, skill=py, level=4, target_level=5
        )
        EmployeeSkill.objects.create(employee=self.dev2, skill=py, level=2)

    def test_matrix_aggregates_and_permission(self):
        denied = self.client.get(
            "/api/hr/skill-matrix/?department=ENG", **auth_header(9, "EMPLOYEE")
        )
        self.assertEqual(denied.status_code, 403)

        resp = self.client.get(
            "/api/hr/skill-matrix/?department=ENG", **auth_header(1, "MANAGER")
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()["data"]
        self.assertEqual(body["headcount"], 3)
        row = body["skills"][0]
        self.assertEqual(row["skill_code"], "PY")
        self.assertEqual(row["average_level"], 3.0)     # (4+2)/2
        self.assertEqual(row["evaluated_count"], 2)
        self.assertEqual(row["coverage_percent"], 67)   # 2 of 3
        self.assertEqual(row["average_target_gap"], 1.0)

    def test_unknown_department_404(self):
        resp = self.client.get(
            "/api/hr/skill-matrix/?department=NOPE", **auth_header(1, "HR")
        )
        self.assertEqual(resp.status_code, 404)


class CSVTests(BaseCase):
    def test_export_hr_only_and_content(self):
        self.assertEqual(
            self.client.get("/api/hr/employees/export/",
                            **auth_header(2)).status_code,
            403,
        )
        resp = self.client.get(
            "/api/hr/employees/export/", **auth_header(10, "HR")
        )
        self.assertEqual(resp.status_code, 200)
        rows = list(csv.reader(io.StringIO(resp.content.decode())))
        self.assertEqual(rows[0][0], "user_id")
        self.assertEqual(len(rows), 4)  # header + 3 profiles

    def test_import_command_idempotent_with_manager_links(self):
        content = (
            "user_id,email,first_name,last_name,user_role,department_code,"
            "job_title,manager_user_id,hire_date\n"
            "20,boss@c.com,Big,Boss,MANAGER,DATA,Head of Data,,2020-01-01\n"
            "21,ana@c.com,Ana,Lyst,EMPLOYEE,DATA,Analyst,20,2023-05-01\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv",
                                         delete=False) as fh:
            fh.write(content)
            path = fh.name

        call_command("import_employees", path)
        ana = EmployeeProfile.objects.get(user_id=21)
        self.assertEqual(ana.manager.user_id, 20)
        self.assertEqual(ana.department.code, "DATA")

        call_command("import_employees", path)  # idempotent
        self.assertEqual(
            EmployeeProfile.objects.filter(user_id__in=[20, 21]).count(), 2
        )


class ReviewTemplateTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.cycle = ReviewCycle.objects.create(
            name="Annual 2026", start_date="2026-01-01", end_date="2026-12-31"
        )

    def _create_template(self):
        return self.client.post(
            "/api/reviews/templates/",
            {"name": "Engineering IC", "items": [
                {"criteria": "Technical skills", "weight": 2},
                {"criteria": "Collaboration", "weight": 1},
            ]},
            content_type="application/json",
            **auth_header(10, "HR"),
        )

    def test_template_crud_gate_and_validation(self):
        denied = self.client.post(
            "/api/reviews/templates/", {"name": "x", "items": []},
            content_type="application/json", **auth_header(2),
        )
        self.assertEqual(denied.status_code, 403)

        bad = self.client.post(
            "/api/reviews/templates/", {"name": "x", "items": []},
            content_type="application/json", **auth_header(10, "HR"),
        )
        self.assertEqual(bad.status_code, 400)

        ok = self._create_template()
        self.assertEqual(ok.status_code, 201, ok.content)

    def test_review_from_template_prefills_unrated_weighted_items(self):
        template_id = self._create_template().json()["data"]["id"]
        resp = self.client.post(
            "/api/reviews/",
            {"employee_id": self.dev.id, "cycle_id": self.cycle.id,
             "template_id": template_id},
            content_type="application/json",
            **auth_header(1, "MANAGER"),
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        review = PerformanceReview.objects.get()
        items = list(review.items.all())
        self.assertEqual(len(items), 2)
        self.assertTrue(all(i.score is None for i in items))
        self.assertIsNone(review.overall_score)

        # rating one item updates the weighted overall (others ignored)
        item = review.items.get(criteria="Technical skills")
        item.score = 4
        item.save()
        review.recalculate_overall_score()
        review.refresh_from_db()
        self.assertEqual(float(review.overall_score), 4.0)


class PeerFeedbackTests(BaseCase):
    def setUp(self):
        super().setUp()
        cycle = ReviewCycle.objects.create(
            name="Annual", start_date="2026-01-01", end_date="2026-12-31"
        )
        self.review = PerformanceReview.objects.create(
            employee=self.dev, manager=self.mgr, cycle=cycle
        )
        self.url = f"/api/reviews/{self.review.id}/feedback/"

    def test_submit_dedupe_and_self_block(self):
        own = self.client.post(
            self.url, {"rating": 5}, content_type="application/json",
            **auth_header(2),   # the reviewee
        )
        self.assertEqual(own.status_code, 403)

        ok = self.client.post(
            self.url, {"rating": 4, "relationship": "PEER",
                       "comment": "Great teammate"},
            content_type="application/json", **auth_header(3),
        )
        self.assertEqual(ok.status_code, 201, ok.content)

        dupe = self.client.post(
            self.url, {"rating": 2}, content_type="application/json",
            **auth_header(3),
        )
        self.assertEqual(dupe.status_code, 409)
        self.assertEqual(PeerFeedback.objects.count(), 1)

    def test_reviewee_sees_anonymous_hr_sees_attributed(self):
        self.client.post(
            self.url, {"rating": 4, "comment": "Solid work"},
            content_type="application/json", **auth_header(3),
        )
        self.client.post(
            self.url, {"rating": 2, "relationship": "REPORT"},
            content_type="application/json", **auth_header(7),
        )

        mine = self.client.get(self.url, **auth_header(2)).json()["data"]
        self.assertEqual(mine["count"], 2)
        self.assertEqual(mine["average_rating"], 3.0)
        self.assertNotIn("attributed", mine)
        self.assertNotIn("reviewer_user_id", str(mine["comments"]))

        hr_view = self.client.get(
            self.url, **auth_header(10, "HR")
        ).json()["data"]
        self.assertEqual(
            sorted(e["reviewer_user_id"] for e in hr_view["attributed"]),
            [3, 7],
        )

    def test_outsider_cannot_read(self):
        resp = self.client.get(self.url, **auth_header(99))
        self.assertEqual(resp.status_code, 403)
