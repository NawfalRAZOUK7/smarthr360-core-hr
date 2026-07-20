"""Email each employee a digest of unread notifications not previously emailed."""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from hr.models import EmployeeProfile, Notification


class Command(BaseCommand):
    help = "Send an idempotent email digest for unread in-app notifications."

    def handle(self, *args, **options):
        sent_users = 0
        user_ids = list(
            Notification.objects.filter(read=False, digest_sent_at__isnull=True)
            .values_list("user_id", flat=True)
            .distinct()
        )
        for user_id in user_ids:
            profile = EmployeeProfile.objects.filter(user_id=user_id).first()
            if not profile or not profile.email:
                self.stderr.write(f"Skipping user {user_id}: no email profile")
                continue
            pending = list(
                Notification.objects.filter(
                    user_id=user_id, read=False, digest_sent_at__isnull=True
                ).order_by("-created_at")
            )
            if not pending:
                continue
            lines = [f"You have {len(pending)} unread SmartHR360 notification(s):", ""]
            for notification in pending:
                lines.append(f"- {notification.title}: {notification.body}".rstrip())
                if notification.link:
                    lines.append(f"  Open: {notification.link}")
            send_mail(
                subject=f"SmartHR360 notification digest ({len(pending)} unread)",
                message="\n".join(lines),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[profile.email],
            )
            with transaction.atomic():
                Notification.objects.filter(pk__in=[item.pk for item in pending], digest_sent_at__isnull=True).update(
                    digest_sent_at=timezone.now()
                )
            sent_users += 1
        self.stdout.write(self.style.SUCCESS(f"Sent {sent_users} notification digest(s)."))
