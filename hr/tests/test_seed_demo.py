from django.core.management import call_command
from django.test import TestCase

from hr.models import EmployeeProfile, TrainingAction


class SeedDemoTests(TestCase):
    def test_seed_demo_is_idempotent(self):
        call_command("seed_demo")
        first = (EmployeeProfile.objects.count(), TrainingAction.objects.count())
        call_command("seed_demo")
        self.assertEqual((EmployeeProfile.objects.count(), TrainingAction.objects.count()), first)
        self.assertEqual(EmployeeProfile.objects.get(user_id=28).email, "guest@demo.smarthr360.dev")
