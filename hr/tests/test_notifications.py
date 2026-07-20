from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from smarthr360_jwt_auth import conf

from hr.models import EmployeeProfile, Notification, Skill
from reviews.models import ReviewCycle

from .helpers import PUBLIC_PEM, auth_header


@override_settings(
    SMARTHR_JWT_AUTH={"PUBLIC_KEY": PUBLIC_PEM, "ISSUER": "smarthr360"},
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class NotificationAPITests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        conf.clear_cache()

    @classmethod
    def tearDownClass(cls):
        conf.clear_cache()
        super().tearDownClass()

    def setUp(self):
        self.employee = EmployeeProfile.objects.create(
            user_id=20, email="employee@example.com", first_name="Amina"
        )
        self.other = EmployeeProfile.objects.create(user_id=21, email="other@example.com")

    def test_own_scope_unread_count_mark_one_and_mark_all(self):
        own_unread = Notification.objects.create(user_id=20, title="Own unread")
        Notification.objects.create(user_id=20, title="Own read", read=True)
        Notification.objects.create(user_id=21, title="Other secret")

        response = self.client.get("/api/hr/notifications/", **auth_header(20))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([item["title"] for item in response.json()["data"]], ["Own unread", "Own read"])

        count = self.client.get("/api/hr/notifications/unread-count/", **auth_header(20))
        self.assertEqual(count.json()["data"]["unread_count"], 1)

        denied = self.client.post(f"/api/hr/notifications/{Notification.objects.get(user_id=21).id}/read/", **auth_header(20))
        self.assertEqual(denied.status_code, 404)
        marked = self.client.post(f"/api/hr/notifications/{own_unread.id}/read/", **auth_header(20))
        self.assertEqual(marked.status_code, 200)
        self.assertTrue(marked.json()["data"]["read"])

        Notification.objects.create(user_id=20, title="Another")
        all_read = self.client.post("/api/hr/notifications/read-all/", **auth_header(20))
        self.assertEqual(all_read.json()["data"]["updated"], 1)
        self.assertFalse(Notification.objects.filter(user_id=20, read=False).exists())

    def test_ingest_permission_and_validation(self):
        payload = {"user_id": 20, "type": "GENERIC", "title": "Hello", "body": "Body", "link": "/actions"}
        self.assertEqual(
            self.client.post("/api/hr/notifications/ingest/", payload, content_type="application/json", **auth_header(20)).status_code,
            201,
        )
        self.assertEqual(
            self.client.post("/api/hr/notifications/ingest/", {**payload, "user_id": 21}, content_type="application/json", **auth_header(20)).status_code,
            403,
        )
        manager = self.client.post(
            "/api/hr/notifications/ingest/", {**payload, "user_id": 21}, content_type="application/json", **auth_header(10, "MANAGER")
        )
        self.assertEqual(manager.status_code, 201, manager.content)
        self.assertEqual(Notification.objects.filter(user_id=21).count(), 1)

    def test_training_and_review_creation_generate_notifications(self):
        skill = Skill.objects.create(name="Kubernetes", code="K8S")
        training = self.client.post(
            "/api/hr/training-actions/",
            {"skill_id": skill.id, "employee_id": self.employee.id, "title": "CKA"},
            content_type="application/json",
            **auth_header(10, "HR"),
        )
        self.assertEqual(training.status_code, 201, training.content)
        self.assertTrue(Notification.objects.filter(user_id=20, type="TRAINING_ASSIGNED", link="/skill-gaps").exists())

        cycle = ReviewCycle.objects.create(name="Annual 2026", start_date="2026-01-01", end_date="2026-12-31")
        review = self.client.post(
            "/api/reviews/",
            {"employee_id": self.employee.id, "cycle_id": cycle.id},
            content_type="application/json",
            **auth_header(10, "HR"),
        )
        self.assertEqual(review.status_code, 201, review.content)
        self.assertTrue(Notification.objects.filter(user_id=20, type="REVIEW_DUE", link="/reviews").exists())

    def test_digest_is_idempotent(self):
        notification = Notification.objects.create(user_id=20, title="Review due", body="Please review")
        call_command("send_notification_digest")
        self.assertEqual(len(mail.outbox), 1)
        notification.refresh_from_db()
        self.assertIsNotNone(notification.digest_sent_at)
        call_command("send_notification_digest")
        self.assertEqual(len(mail.outbox), 1)
