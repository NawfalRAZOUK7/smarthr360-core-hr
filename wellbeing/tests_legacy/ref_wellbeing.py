from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from accounts.tests.helpers import authenticate
from hr.models import Department, EmployeeProfile
from wellbeing.models import SurveyQuestion, SurveyResponse, WellbeingSurvey


class WellbeingModuleTests(APITestCase):
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
        self.auditor_user = User.objects.create_user(
            email="auditor@example.com",
            password="AuditPass123!",
            role=User.Role.EMPLOYEE,
            first_name="Audit",
            last_name="User",
        )
        auditor_group, _ = Group.objects.get_or_create(name="AUDITOR")
        self.auditor_user.groups.add(auditor_group)

        self.department = Department.objects.create(
            name="IT",
            code="IT",
            description="IT Department",
        )

        # Manager & employees
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
            manager=self.manager_profile,
        )

        # Survey + questions
        self.survey = WellbeingSurvey.objects.create(
            title="Stress & Satisfaction",
            description="Weekly wellbeing check",
            is_active=True,
            created_by=self.hr_user,
        )
        self.q1 = SurveyQuestion.objects.create(
            survey=self.survey,
            text="How stressed do you feel this week?",
            type=SurveyQuestion.QuestionType.SCALE_1_5,
            order=1,
        )
        self.q2 = SurveyQuestion.objects.create(
            survey=self.survey,
            text="Do you feel supported by your manager?",
            type=SurveyQuestion.QuestionType.YES_NO,
            order=2,
        )

    def auth_as(self, user, password=None):
        # Pick the right password based on user
        password = password or (
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

    def test_employee_can_submit_anonymous_response(self):
        self.auth_as(self.emp1_user)

        payload = {
            "answers": {
                str(self.q1.id): "4",
                str(self.q2.id): "yes",
            }
        }
        resp = self.client.post(
            f"/api/wellbeing/surveys/{self.survey.id}/submit/",
            payload,
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # Envelope: { "data": { "response_id": "..." }, "meta": {...} }
        self.assertIn("response_id", resp.data["data"])

        stored = SurveyResponse.objects.filter(survey=self.survey).first()
        self.assertIsNotNone(stored)
        self.assertEqual(stored.answers[str(self.q1.id)], "4")
        self.assertEqual(stored.department, self.emp1_profile.department)
        # No direct link to user
        self.assertFalse(hasattr(stored, "user"))

    def test_hr_can_view_global_stats(self):
        # Create a couple of responses
        self.auth_as(self.emp1_user)
        self.client.post(
            f"/api/wellbeing/surveys/{self.survey.id}/submit/",
            {
                "answers": {
                    str(self.q1.id): "4",
                    str(self.q2.id): "yes",
                }
            },
            format="json",
        )
        self.auth_as(self.emp2_user)
        self.client.post(
            f"/api/wellbeing/surveys/{self.survey.id}/submit/",
            {
                "answers": {
                    str(self.q1.id): "2",
                    str(self.q2.id): "no",
                }
            },
            format="json",
        )

        self.auth_as(self.hr_user)
        stats_resp = self.client.get(
            f"/api/wellbeing/surveys/{self.survey.id}/stats/"
        )
        self.assertEqual(stats_resp.status_code, status.HTTP_200_OK)
        # Envelope: stats_resp.data["data"]["..."]
        self.assertEqual(stats_resp.data["data"]["count_responses"], 2)
        self.assertEqual(len(stats_resp.data["data"]["questions"]), 2)

    def test_auditor_can_view_stats(self):
        self.auth_as(self.emp1_user)
        self.client.post(
            f"/api/wellbeing/surveys/{self.survey.id}/submit/",
            {"answers": {str(self.q1.id): "4"}},
            format="json",
        )

        self.auth_as(self.auditor_user, password="AuditPass123!")
        stats_resp = self.client.get(
            f"/api/wellbeing/surveys/{self.survey.id}/stats/"
        )
        self.assertEqual(stats_resp.status_code, status.HTTP_200_OK)

        team_resp = self.client.get(
            f"/api/wellbeing/surveys/{self.survey.id}/team-stats/"
        )
        self.assertEqual(team_resp.status_code, status.HTTP_200_OK)

    def test_manager_team_stats_filtered_by_department(self):
        # Two employees in same department submit
        self.auth_as(self.emp1_user)
        self.client.post(
            f"/api/wellbeing/surveys/{self.survey.id}/submit/",
            {
                "answers": {
                    str(self.q1.id): "4",
                    str(self.q2.id): "yes",
                }
            },
            format="json",
        )
        self.auth_as(self.emp2_user)
        self.client.post(
            f"/api/wellbeing/surveys/{self.survey.id}/submit/",
            {
                "answers": {
                    str(self.q1.id): "3",
                    str(self.q2.id): "yes",
                }
            },
            format="json",
        )

        self.auth_as(self.manager_user)
        team_resp = self.client.get(
            f"/api/wellbeing/surveys/{self.survey.id}/team-stats/"
        )
        self.assertEqual(team_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(team_resp.data["data"]["team_size"], 2)
        self.assertEqual(team_resp.data["data"]["responses"], 2)
        self.assertIn(
            str(self.q1.id),
            team_resp.data["data"]["aggregates"],
        )

    def test_non_manager_cannot_access_team_stats(self):
        self.auth_as(self.emp1_user)
        resp = self.client.get(
            f"/api/wellbeing/surveys/{self.survey.id}/team-stats/"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_inactive_survey_cannot_be_submitted(self):
        self.survey.is_active = False
        self.survey.save(update_fields=["is_active"])

        self.auth_as(self.emp1_user)
        resp = self.client.post(
            f"/api/wellbeing/surveys/{self.survey.id}/submit/",
            {"answers": {str(self.q1.id): "4"}},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_submission_without_profile_has_no_department(self):
        user = User.objects.create_user(
            email="noprof@example.com",
            password="NoProfPass123!",
            role=User.Role.EMPLOYEE,
            first_name="No",
            last_name="Profile",
        )
        self.auth_as(user, password="NoProfPass123!")

        resp = self.client.post(
            f"/api/wellbeing/surveys/{self.survey.id}/submit/",
            {"answers": {str(self.q1.id): "5", str(self.q2.id): "yes"}},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        stored = SurveyResponse.objects.filter(survey=self.survey).last()
        self.assertIsNone(stored.department)
        self.assertIsNone(getattr(stored, "user", None))

    def test_hr_can_access_team_stats(self):
        # Have two responses from same dept
        self.auth_as(self.emp1_user)
        self.client.post(
            f"/api/wellbeing/surveys/{self.survey.id}/submit/",
            {"answers": {str(self.q1.id): "4"}},
            format="json",
        )
        self.auth_as(self.emp2_user)
        self.client.post(
            f"/api/wellbeing/surveys/{self.survey.id}/submit/",
            {"answers": {str(self.q1.id): "3"}},
            format="json",
        )

        self.auth_as(self.hr_user)
        resp = self.client.get(f"/api/wellbeing/surveys/{self.survey.id}/team-stats/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        expected_responses = SurveyResponse.objects.filter(
            survey=self.survey,
            department_id__in=Department.objects.filter(employees__isnull=False).values_list(
                "id", flat=True
            ),
        ).count()
        self.assertEqual(resp.data["data"]["responses"], expected_responses)
        self.assertEqual(resp.data["data"]["team_size"], EmployeeProfile.objects.count())

    def test_manager_team_stats_excludes_other_department(self):
        other_dept = Department.objects.create(name="HR", code="HR", description="HR Dept")
        other_emp_user = User.objects.create_user(
            email="other@example.com",
            password="EmpPass123!",
            role=User.Role.EMPLOYEE,
            first_name="Other",
            last_name="Dept",
        )
        EmployeeProfile.objects.create(
            user=other_emp_user,
            department=other_dept,
            job_title="HR",
        )

        self.auth_as(other_emp_user)
        self.client.post(
            f"/api/wellbeing/surveys/{self.survey.id}/submit/",
            {"answers": {str(self.q1.id): "1"}},
            format="json",
        )

        # Manager team submits
        self.auth_as(self.emp1_user)
        self.client.post(
            f"/api/wellbeing/surveys/{self.survey.id}/submit/",
            {"answers": {str(self.q1.id): "5"}},
            format="json",
        )

        self.auth_as(self.manager_user)
        resp = self.client.get(f"/api/wellbeing/surveys/{self.survey.id}/team-stats/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Should not count other department response
        expected = SurveyResponse.objects.filter(
            survey=self.survey,
            department=self.department,
        ).count()
        self.assertEqual(resp.data["data"]["responses"], expected)

    def test_survey_list_pagination_and_ordering(self):
        # Create extra surveys
        WellbeingSurvey.objects.create(
            title="Older",
            description="Old",
            is_active=True,
            created_by=self.hr_user,
        )
        WellbeingSurvey.objects.create(
            title="Newest",
            description="New",
            is_active=True,
            created_by=self.hr_user,
        )

        self.auth_as(self.hr_user)
        resp = self.client.get("/api/wellbeing/surveys/?page=1&page_size=2")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data.get("data", {})
        meta = resp.data.get("meta", {})
        self.assertTrue(meta.get("success"))
        results = data.get("results", [])
        self.assertLessEqual(len(results), 2)
        # Ordered by -created_at → first item should be "Newest"
        if results:
            self.assertEqual(results[0].get("title"), "Newest")
