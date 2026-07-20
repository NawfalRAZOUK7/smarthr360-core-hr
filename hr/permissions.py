"""HR-domain object permissions (claim-based, no auth DB access)."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from smarthr360_jwt_auth.access import (
    has_hr_access,
    is_auditor,
    is_manager,
    is_support,
)

from .identity import get_own_profile


class IsPeopleReadAccess(BasePermission):
    """People-directory access.

    Read (SAFE methods): HR/Admin, Auditor and Support (read-only lookup).
    Write: HR/Admin only. Managers/employees fall through to their own
    scoped endpoints and are not granted the full directory here.
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return has_hr_access(user) or is_auditor(user) or is_support(user)
        return has_hr_access(user)


class EmployeeProfileAccessPermission(BasePermission):
    """
    Object-level permission for EmployeeProfile:

    - HR / ADMIN: full access
    - Employee: only their own profile
    - Manager: only their direct team members
    - Auditor: read-only access
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        if request.method in SAFE_METHODS and is_auditor(user):
            return True

        # HR & Admin → full access
        if has_hr_access(user):
            return True

        # Employee → only their own profile
        if obj.user_id == getattr(user, "id", None):
            return True

        # Manager → their direct team
        if is_manager(user):
            manager_profile = get_own_profile(user)
            return manager_profile is not None and obj.manager_id == manager_profile.id

        return False
