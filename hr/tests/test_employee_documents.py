from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from ..models import EmployeeDocument, EmployeeProfile
from .helpers import PUBLIC_PEM, auth_header


class EmployeeDocumentTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.settings = override_settings(SMARTHR_JWT_AUTH={"PUBLIC_KEY": PUBLIC_PEM, "ISSUER": "smarthr360"})
        cls.settings.enable()

    @classmethod
    def tearDownClass(cls):
        cls.settings.disable()
        super().tearDownClass()

    def setUp(self):
        self.manager = EmployeeProfile.objects.create(user_id=10, email="manager@example.com")
        self.team_member = EmployeeProfile.objects.create(user_id=11, email="team@example.com", manager=self.manager)
        self.other = EmployeeProfile.objects.create(user_id=12, email="other@example.com")
        self.payload = {
            "doc_type": "CONTRACT", "title": "Employment contract",
            "reference_url": "https://docs.example/contract", "issue_date": "2026-01-01",
            "expiry_date": str(timezone.localdate() + timedelta(days=10)),
        }

    def test_hr_can_crud_document(self):
        response = self.client.post(f"/api/hr/employees/{self.team_member.id}/documents/", self.payload, content_type="application/json", **auth_header(1, role="HR"))
        self.assertEqual(response.status_code, 201, response.content)
        document_id = response.json()["data"]["id"]
        self.assertTrue(response.json()["data"]["is_expiring_soon"])
        self.assertEqual(self.client.get(f"/api/hr/documents/{document_id}/", **auth_header(1, role="HR")).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/hr/documents/{document_id}/", **auth_header(1, role="HR")).status_code, 204)

    def test_manager_sees_only_direct_team_documents(self):
        team_doc = EmployeeDocument.objects.create(employee=self.team_member, **self.payload)
        other_doc = EmployeeDocument.objects.create(employee=self.other, **self.payload)
        self.assertEqual(self.client.get(f"/api/hr/employees/{self.team_member.id}/documents/", **auth_header(10, role="MANAGER")).status_code, 200)
        self.assertEqual(self.client.get(f"/api/hr/documents/{team_doc.id}/", **auth_header(10, role="MANAGER")).status_code, 200)
        self.assertEqual(self.client.get(f"/api/hr/documents/{other_doc.id}/", **auth_header(10, role="MANAGER")).status_code, 404)
        self.assertEqual(self.client.post(f"/api/hr/employees/{self.team_member.id}/documents/", self.payload, content_type="application/json", **auth_header(10, role="MANAGER")).status_code, 403)

    def test_expiring_filter(self):
        EmployeeDocument.objects.create(employee=self.team_member, **self.payload)
        EmployeeDocument.objects.create(employee=self.team_member, doc_type="OTHER", title="Later", reference_url="ref", issue_date="2026-01-01", expiry_date=timezone.localdate() + timedelta(days=60))
        response = self.client.get("/api/hr/documents/expiring/", **auth_header(1, role="HR"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["count"], 1)
        self.assertEqual(response.json()["data"]["results"][0]["title"], "Employment contract")
