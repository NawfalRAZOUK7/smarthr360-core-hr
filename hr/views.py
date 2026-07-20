from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from smarthr360_jwt_auth.access import (
    has_employee_access,
    has_hr_access,
    has_manager_access,
    is_auditor,
    is_manager,
)
from smarthr360_jwt_auth.permissions import (
    IsHRRole,
    IsManagerOrAuditorReadOnly,
    IsManagerOrAbove,
)

from config.api_mixins import ApiResponseMixin

from .identity import get_or_create_own_profile, get_own_profile
from .permissions import IsPeopleReadAccess
from .models import Department, EmployeeDocument, EmployeeProfile, EmployeeSkill, FutureCompetency, Notification, Skill, TrainingAction
from .permissions import EmployeeProfileAccessPermission
from .serializers import (
    DepartmentSerializer,
    EmployeeProfileSerializer,
    EmployeeDocumentSerializer,
    EmployeeSelfUpdateSerializer,
    EmployeeSkillSerializer,
    FutureCompetencySerializer,
    NotificationSerializer,
    SkillSerializer,
    TrainingActionSerializer,
)


def _can_read_employee_documents(user, employee):
    if has_hr_access(user) or is_auditor(user):
        return True
    if is_manager(user):
        manager_profile = get_own_profile(user)
        return manager_profile is not None and employee.manager_id == manager_profile.id
    return False


class EmployeeDocumentListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    serializer_class = EmployeeDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_employee(self):
        employee = get_object_or_404(EmployeeProfile, pk=self.kwargs["employee_id"])
        if not _can_read_employee_documents(self.request.user, employee):
            raise PermissionDenied("You cannot view documents for this employee.")
        return employee

    def get_queryset(self):
        return EmployeeDocument.objects.filter(employee=self.get_employee())

    def perform_create(self, serializer):
        if not has_hr_access(self.request.user):
            raise PermissionDenied("HR or Admin role required.")
        serializer.save(employee=self.get_employee(), uploaded_by_user_id=self.request.user.id)


class EmployeeDocumentDetailView(ApiResponseMixin, generics.RetrieveDestroyAPIView):
    serializer_class = EmployeeDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = EmployeeDocument.objects.select_related("employee")
        if has_hr_access(self.request.user) or is_auditor(self.request.user):
            return qs
        if is_manager(self.request.user):
            manager_profile = get_own_profile(self.request.user)
            return qs.filter(employee__manager=manager_profile) if manager_profile else qs.none()
        return qs.none()

    def perform_destroy(self, instance):
        if not has_hr_access(self.request.user):
            raise PermissionDenied("HR or Admin role required.")
        instance.delete()


class ExpiringEmployeeDocumentListView(ApiResponseMixin, generics.ListAPIView):
    serializer_class = EmployeeDocumentSerializer
    permission_classes = [IsHRRole]

    def get_queryset(self):
        today = timezone.localdate()
        return EmployeeDocument.objects.filter(
            expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=30),
        ).select_related("employee")

# --------------------------------------------------------------------------------------
#   DEPARTMENTS
# --------------------------------------------------------------------------------------

class DepartmentListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    queryset = Department.objects.all().order_by("name")
    serializer_class = DepartmentSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsHRRole()]
        return [permissions.IsAuthenticated()]


class DepartmentDetailView(ApiResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [IsHRRole()]


# --------------------------------------------------------------------------------------
#   EMPLOYEE ME
# --------------------------------------------------------------------------------------

class EmployeeMeView(ApiResponseMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, request):
        return get_or_create_own_profile(request.user)

    def get(self, request):
        profile = self.get_object(request)
        serializer = EmployeeProfileSerializer(profile)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        profile = self.get_object(request)
        serializer = EmployeeSelfUpdateSerializer(
            profile,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            EmployeeProfileSerializer(profile).data,
            status=status.HTTP_200_OK,
        )


# --------------------------------------------------------------------------------------
#   EMPLOYEE LIST + FILTERS ADDED HERE
# --------------------------------------------------------------------------------------

class EmployeeListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    serializer_class = EmployeeProfileSerializer
    # Read: HR/Admin, Auditor, Support (people lookup). Write: HR/Admin.
    permission_classes = [IsPeopleReadAccess]

    def get_queryset(self):
        qs = EmployeeProfile.objects.select_related("department")

        params = self.request.query_params

        # ------------------------
        # FILTER: department=IT
        # ------------------------
        department_code = params.get("department")
        if department_code:
            qs = qs.filter(department__code__iexact=department_code)

        # ------------------------
        # FILTER: is_active=true/false
        # ------------------------
        is_active_param = params.get("is_active")
        if is_active_param is not None:
            v = is_active_param.lower()
            if v in ("true", "1", "yes", "y"):
                qs = qs.filter(is_active=True)
            elif v in ("false", "0", "no", "n"):
                qs = qs.filter(is_active=False)

        # ------------------------
        # FILTER: manager=<id>
        # ------------------------
        manager_id = params.get("manager")
        if manager_id:
            qs = qs.filter(manager_id=manager_id)

        return qs

    def perform_create(self, serializer):
        # user_id comes from the request body: the id of the user in the
        # auth service. HR is trusted to provide it (no cross-service FK;
        # uniqueness is enforced by the model).
        user_id = self.request.data.get("user_id")
        if not user_id:
            raise ValidationError({"user_id": "This field is required."})
        serializer.save()


class EmployeeDetailView(ApiResponseMixin, generics.RetrieveUpdateAPIView):
    queryset = EmployeeProfile.objects.select_related("department").all()
    serializer_class = EmployeeProfileSerializer
    permission_classes = [permissions.IsAuthenticated, EmployeeProfileAccessPermission]


# --------------------------------------------------------------------------------------
#   MANAGER TEAM
# --------------------------------------------------------------------------------------

class MyTeamListView(ApiResponseMixin, generics.ListAPIView):
    serializer_class = EmployeeProfileSerializer
    permission_classes = [IsManagerOrAuditorReadOnly]

    def get_queryset(self):
        user = self.request.user

        if has_hr_access(user) or is_auditor(user):
            return EmployeeProfile.objects.select_related("department").all()

        manager_profile = get_own_profile(user)
        if manager_profile is not None:
            return EmployeeProfile.objects.select_related("department").filter(
                manager=manager_profile
            )

        return EmployeeProfile.objects.none()


class SearchView(ApiResponseMixin, APIView):
    """GET /api/hr/search/?q= — unified, role-scoped search.

    One box across people, skills and departments. Employees are scoped like
    everywhere else (HR/Auditor: all; Manager: their team; Employee: self);
    skills and departments are reference data visible to any authenticated
    user. Returns typed results with a deep link for each.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            return Response({"query": q, "results": []})

        user = request.user
        results = []

        # --- People (role-scoped) ---
        emp_qs = EmployeeProfile.objects.select_related("department")
        if has_hr_access(user) or is_auditor(user):
            pass
        elif is_manager(user) and get_own_profile(user) is not None:
            emp_qs = emp_qs.filter(manager=get_own_profile(user))
        else:
            emp_qs = emp_qs.filter(user_id=getattr(user, "id", None))
        emp_qs = emp_qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
            | Q(job_title__icontains=q)
        )[:8]
        for e in emp_qs:
            label = f"{e.first_name} {e.last_name}".strip() or e.email or f"Employee {e.id}"
            results.append(
                {
                    "type": "employee",
                    "id": e.id,
                    "label": label,
                    "sublabel": e.job_title or (e.department.name if e.department else ""),
                    "href": "/employees",
                }
            )

        # --- Skills (reference data) ---
        for s in Skill.objects.filter(name__icontains=q)[:6]:
            results.append(
                {"type": "skill", "id": s.id, "label": s.name, "sublabel": "Skill", "href": "/skill-gaps"}
            )

        # --- Departments (reference data) ---
        for d in Department.objects.filter(Q(name__icontains=q) | Q(code__icontains=q))[:6]:
            results.append(
                {
                    "type": "department",
                    "id": d.id,
                    "label": d.name,
                    "sublabel": f"Department · {d.code}",
                    "href": "/organization",
                }
            )

        return Response({"query": q, "results": results})


# --------------------------------------------------------------------------------------
#   SKILLS
# --------------------------------------------------------------------------------------

class SkillListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    queryset = Skill.objects.filter(is_active=True).order_by("name")
    serializer_class = SkillSerializer

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [IsManagerOrAbove()]

    def perform_create(self, serializer):
        is_active = serializer.validated_data.get("is_active")
        if is_active is None:
            serializer.save(created_by_user_id=self.request.user.id, is_active=True)
        else:
            serializer.save(created_by_user_id=self.request.user.id)


class SkillDetailView(ApiResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Skill.objects.all()
    serializer_class = SkillSerializer

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [IsManagerOrAbove()]


# --------------------------------------------------------------------------------------
#   EMPLOYEE SKILLS
# --------------------------------------------------------------------------------------

class EmployeeSkillListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    serializer_class = EmployeeSkillSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        user = request.user

        # Permission check before any validation to ensure correct status code
        if not has_manager_access(user):
            raise PermissionDenied("Only HR, Manager or Admin can create skill evaluations.")

        # Accept "proficiency" alias and map enum names to numeric levels
        data = request.data.copy()
        if "proficiency" in data and "level" not in data:
            proficiency = data.get("proficiency")
            # Allow string names like "BEGINNER" or integers already
            if isinstance(proficiency, str):
                try:
                    data["level"] = EmployeeSkill.Level[proficiency].value
                except KeyError:
                    pass
            else:
                data["level"] = proficiency

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return self.success_response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_queryset(self):
        user = self.request.user
        qs = EmployeeSkill.objects.select_related(
            "employee__department", "skill"
        )

        if not (has_hr_access(user) or is_auditor(user)):
            own_profile = get_own_profile(user)
            if is_manager(user) and own_profile is not None:
                qs = qs.filter(employee__manager=own_profile)
            elif has_employee_access(user) and own_profile is not None:
                qs = qs.filter(employee=own_profile)
            else:
                return qs.none()

        employee_id = self.request.query_params.get("employee_id")
        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        return qs

    def perform_create(self, serializer):
        user = self.request.user

        employee_id = self.request.data.get("employee_id")
        skill_id = self.request.data.get("skill_id")

        if not employee_id or not skill_id:
            raise ValidationError({"detail": "employee_id and skill_id are required."})

        employee = get_object_or_404(EmployeeProfile, pk=employee_id)
        skill = get_object_or_404(Skill, pk=skill_id)

        if is_manager(user) and not has_hr_access(user):
            manager_profile = get_own_profile(user)
            if manager_profile is None or employee.manager_id != manager_profile.id:
                raise PermissionDenied("You can only rate skills of your team members.")

        serializer.save(
            employee=employee,
            skill=skill,
            last_evaluated_by_user_id=user.id,
            last_evaluated_at=timezone.now(),
        )


class EmployeeSkillDetailView(ApiResponseMixin, generics.RetrieveUpdateAPIView):
    serializer_class = EmployeeSkillSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = EmployeeSkill.objects.select_related(
            "employee__department", "skill"
        )

        if has_hr_access(user) or is_auditor(user):
            return qs

        own_profile = get_own_profile(user)
        if is_manager(user) and own_profile is not None:
            return qs.filter(employee__manager=own_profile)

        if has_employee_access(user) and own_profile is not None:
            return qs.filter(employee=own_profile)

        return qs.none()

    def perform_update(self, serializer):
        user = self.request.user
        if not has_manager_access(user):
            raise PermissionDenied("Only HR, Manager or Admin can update skill evaluations.")
        serializer.save(
            last_evaluated_by_user_id=user.id,
            last_evaluated_at=timezone.now(),
        )


# --------------------------------------------------------------------------------------
#   FUTURE COMPETENCIES
# --------------------------------------------------------------------------------------

class FutureCompetencyListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    queryset = FutureCompetency.objects.select_related("skill", "department")
    serializer_class = FutureCompetencySerializer

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [IsManagerOrAbove()]

    def perform_create(self, serializer):
        user = self.request.user

        skill_id = self.request.data.get("skill_id")
        department_id = self.request.data.get("department_id")

        if not skill_id:
            raise ValidationError({"detail": "skill_id is required."})

        skill = get_object_or_404(Skill, pk=skill_id)
        department = None
        if department_id:
            department = get_object_or_404(Department, pk=department_id)

        serializer.save(
            skill=skill,
            department=department,
            created_by_user_id=user.id,
        )


class FutureCompetencyDetailView(ApiResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = FutureCompetency.objects.select_related("skill", "department")
    serializer_class = FutureCompetencySerializer

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [IsManagerOrAbove()]


# --------------------------------------------------------------------------------------
#   TRAINING ACTIONS (close the skill-gap loop)
# --------------------------------------------------------------------------------------
class TrainingActionListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    """GET  /api/hr/training-actions/         list (optional ?status=&skill_id=)
    POST /api/hr/training-actions/         create (Manager / HR / Admin)."""

    serializer_class = TrainingActionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not has_manager_access(self.request.user):
            raise PermissionDenied("Manager, HR or Admin role required.")
        qs = TrainingAction.objects.select_related("skill", "department", "employee")
        status_f = self.request.query_params.get("status")
        skill_id = self.request.query_params.get("skill_id")
        if status_f:
            qs = qs.filter(status=status_f)
        if skill_id:
            qs = qs.filter(skill_id=skill_id)
        return qs

    def perform_create(self, serializer):
        if not has_manager_access(self.request.user):
            raise PermissionDenied("Manager, HR or Admin role required.")
        action = serializer.save(created_by_user_id=self.request.user.id)
        if action.employee_id and action.employee.user_id:
            from .services.notifications import create_notification_best_effort

            create_notification_best_effort(
                user_id=action.employee.user_id,
                notification_type=Notification.Type.TRAINING_ASSIGNED,
                title="Training assigned",
                body=f'You have been assigned "{action.title}".',
                link="/skill-gaps",
            )


class TrainingActionDetailView(ApiResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/hr/training-actions/<id>/ — update status/progress."""

    serializer_class = TrainingActionSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = TrainingAction.objects.select_related("skill", "department", "employee")

    def perform_update(self, serializer):
        if not has_manager_access(self.request.user):
            raise PermissionDenied("Manager, HR or Admin role required.")
        serializer.save()

    def perform_destroy(self, instance):
        if not has_hr_access(self.request.user):
            raise PermissionDenied("HR or Admin role required.")
        instance.delete()


class NotificationListView(ApiResponseMixin, APIView):
    """List the caller's most recent notifications, unread first."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(user_id=request.user.id).order_by("read", "-created_at")[:50]
        return Response(NotificationSerializer(notifications, many=True).data)


class NotificationUnreadCountView(ApiResponseMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(user_id=request.user.id, read=False).count()
        return Response({"unread_count": count})


class NotificationMarkReadView(ApiResponseMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user_id=request.user.id)
        if not notification.read:
            notification.read = True
            notification.save(update_fields=["read"])
        return Response(NotificationSerializer(notification).data)


class NotificationMarkAllReadView(ApiResponseMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        updated = Notification.objects.filter(user_id=request.user.id, read=False).update(read=True)
        return Response({"updated": updated, "unread_count": 0})


class NotificationIngestView(ApiResponseMixin, APIView):
    """Cross-service intake: callers may notify self; managers/HR may notify anyone."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            user_id = int(request.data.get("user_id") or 0)
        except (TypeError, ValueError):
            return Response({"detail": "user_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
        if not user_id:
            return Response({"detail": "user_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        is_self = user_id == int(request.user.id)
        if not (is_self or has_manager_access(request.user)):
            raise PermissionDenied("Only the employee themself or managers/HR may create notifications.")

        serializer = NotificationSerializer(data={**request.data, "user_id": user_id})
        serializer.is_valid(raise_exception=True)
        notification = serializer.save(user_id=user_id)
        return Response(NotificationSerializer(notification).data, status=status.HTTP_201_CREATED)
