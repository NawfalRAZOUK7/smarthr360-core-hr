"""Helpers bridging JWT token identity and local EmployeeProfile rows."""

from __future__ import annotations

from .models import EmployeeProfile


def get_own_profile(user) -> EmployeeProfile | None:
    """Return the EmployeeProfile of the requesting token user, or None."""
    user_id = getattr(user, "id", None)
    if user_id is None:
        return None
    return EmployeeProfile.objects.filter(user_id=user_id).first()


def get_or_create_own_profile(user) -> EmployeeProfile:
    """Get or lazily create the requester's profile from token claims."""
    profile, created = EmployeeProfile.objects.get_or_create(
        user_id=user.id,
        defaults={
            "email": getattr(user, "email", "") or "",
            "user_role": getattr(user, "role", "EMPLOYEE") or "EMPLOYEE",
        },
    )
    # Keep the role/email snapshot fresh on every access.
    updates = []
    role = getattr(user, "role", None)
    email = getattr(user, "email", None)
    if role and profile.user_role != role:
        profile.user_role = role
        updates.append("user_role")
    if email and profile.email != email:
        profile.email = email
        updates.append("email")
    if updates:
        profile.save(update_fields=updates)
    return profile
