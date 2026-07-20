from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from hr.models import Department, EmployeeDocument, EmployeeProfile, EmployeeSkill, Skill, TrainingAction
from reviews.models import Goal, PerformanceReview, ReviewCycle, ReviewItem
from wellbeing.models import SurveyQuestion, WellbeingSurvey


PEOPLE = (
    (1, "admin@demo.smarthr360.dev", "Amine", "Admin", "ADMIN", "HR", "Platform Administrator", None),
    (2, "hr@demo.smarthr360.dev", "Hind", "Haddad", "HR", "HR", "HR Business Partner", None),
    (3, "manager@demo.smarthr360.dev", "Nora", "Manager", "MANAGER", "ENG", "Engineering Manager", None),
    (4, "employee@demo.smarthr360.dev", "Youssef", "Employee", "EMPLOYEE", "ENG", "Software Engineer", 3),
    (7, "yasmine.alaoui@demo.smarthr360.dev", "Yasmine", "Alaoui", "EMPLOYEE", "DATA", "Data Scientist", 3),
    (8, "karim.bennis@demo.smarthr360.dev", "Karim", "Bennis", "EMPLOYEE", "ENG", "DevOps Engineer", 3),
    (27, "auditor@demo.smarthr360.dev", "Aya", "Auditor", "EMPLOYEE", "HR", "Compliance Analyst", 2),
    (28, "guest@demo.smarthr360.dev", "Guest", "Viewer", "EMPLOYEE", "HR", "Demo Observer", 2),
)


class Command(BaseCommand):
    help = "Seed coherent Core HR demo data keyed to auth user IDs."

    @transaction.atomic
    def handle(self, *args, **options):
        departments = {}
        for code, name in (("ENG", "Engineering"), ("DATA", "Data & AI"), ("HR", "Human Resources"), ("FIN", "Finance")):
            departments[code], _ = Department.objects.update_or_create(code=code, defaults={"name": name})

        profiles = {}
        for user_id, email, first, last, role, dept, title, _manager_id in PEOPLE:
            profiles[user_id], _ = EmployeeProfile.objects.update_or_create(
                user_id=user_id,
                defaults={"email": email, "first_name": first, "last_name": last, "user_role": role,
                          "department": departments[dept], "job_title": title, "hire_date": timezone.localdate() - timedelta(days=700)},
            )
        for user_id, *_rest, manager_id in PEOPLE:
            if manager_id:
                EmployeeProfile.objects.filter(pk=profiles[user_id].pk).update(manager=profiles[manager_id])

        skills = {}
        for code, name, category in (("PY", "Python", "Technical"), ("DJ", "Django", "Technical"),
                                      ("K8S", "Kubernetes", "Technical"), ("SQL", "SQL", "Technical"),
                                      ("COMM", "Communication", "Soft skill"), ("PA", "People Analytics", "Business")):
            skills[code], _ = Skill.objects.update_or_create(code=code, defaults={"name": name, "category": category, "created_by_user_id": 2})
        for user_id, levels in {4: {"PY": 3, "DJ": 3, "COMM": 3}, 7: {"PY": 4, "SQL": 4, "PA": 2}, 8: {"K8S": 3, "PY": 2}}.items():
            for code, level in levels.items():
                EmployeeSkill.objects.update_or_create(employee=profiles[user_id], skill=skills[code], defaults={"level": level, "target_level": 4, "last_evaluated_by_user_id": 3})

        today = timezone.localdate()
        cycle, _ = ReviewCycle.objects.update_or_create(name="Annual Demo Review", defaults={"start_date": today - timedelta(days=60), "end_date": today + timedelta(days=30), "is_active": True})
        goals = {}
        for user_id, score, status in ((4, 4.2, "COMPLETED"), (7, 3.8, "SUBMITTED"), (8, 3.4, "DRAFT")):
            review, _ = PerformanceReview.objects.update_or_create(employee=profiles[user_id], cycle=cycle, defaults={"manager": profiles[3], "status": status, "overall_score": score, "manager_comment": "Strong progress with a focused growth plan."})
            ReviewItem.objects.update_or_create(review=review, criteria="Impact and delivery", defaults={"score": round(score), "weight": 2, "comment": "Demo review evidence."})
            goals[user_id], _ = Goal.objects.update_or_create(employee=profiles[user_id], cycle=cycle, title="Grow next-role readiness", defaults={"source_review": review, "description": "Close the highest-priority capability gap.", "status": "IN_PROGRESS", "progress_percent": 55, "created_by_user_id": 3})

        for user_id, code, title, progress in ((4, "K8S", "Kubernetes foundations", 60), (7, "PA", "People analytics accelerator", 35)):
            TrainingAction.objects.update_or_create(employee=profiles[user_id], skill=skills[code], title=title, defaults={"department": profiles[user_id].department, "goal": goals[user_id], "provider": "SmartHR360 Academy", "owner_user_id": user_id, "target_level": 4, "due_date": today + timedelta(days=45), "budget": 1200, "status": "IN_PROGRESS", "progress_percent": progress, "created_by_user_id": 2})

        for user_id, doc_type, title, days in ((4, "CERTIFICATION", "Cloud certification", 18), (8, "ID", "Work authorization", 27)):
            EmployeeDocument.objects.update_or_create(employee=profiles[user_id], title=title, defaults={"doc_type": doc_type, "reference_url": f"demo://documents/{user_id}/{doc_type.lower()}", "issue_date": today - timedelta(days=330), "expiry_date": today + timedelta(days=days), "uploaded_by_user_id": 2})

        survey, _ = WellbeingSurvey.objects.update_or_create(title="Quarterly team pulse", defaults={"description": "Anonymous workload and wellbeing pulse.", "is_active": True, "created_by_user_id": 2})
        for order, (text, kind) in enumerate((("How sustainable is your workload?", "SCALE_1_5"), ("Do you feel supported by your manager?", "YES_NO"), ("What would improve your week?", "TEXT")), 1):
            SurveyQuestion.objects.update_or_create(survey=survey, text=text, defaults={"type": kind, "order": order})

        self.stdout.write(self.style.SUCCESS("Core HR demo data ready."))
