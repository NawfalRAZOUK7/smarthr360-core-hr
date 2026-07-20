"""Best-effort notification creation for domain event hooks."""

import logging

from hr.models import Notification

logger = logging.getLogger(__name__)


def create_notification_best_effort(*, user_id, notification_type, title, body="", link=""):
    if not user_id:
        return None
    try:
        return Notification.objects.create(
            user_id=user_id,
            type=notification_type,
            title=title,
            body=body,
            link=link,
        )
    except Exception:
        logger.exception("Could not create notification for user %s", user_id)
        return None
