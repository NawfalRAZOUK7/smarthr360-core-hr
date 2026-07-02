from django.shortcuts import get_object_or_404
from django.utils import timezone
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
    IsHROrAuditorReadOnly,
    IsHRRole,
    IsManagerOrAuditorReadOnly,
    IsManagerOrAbove,
)

from config.api_mixins import ApiResponseMixin

from .identity import get_or_create_own_profile, get_own_profile
from .models import Department, EmployeeProfile, EmployeeSkill, FutureCompetency, Skill
from .permissions import EmployeeProfileAccessPermission
from .serializers import (
    DepartmentSerializer,
    EmployeeProfileSerializer,
    EmployeeSelfUpdateSerializer,
    EmployeeSkillSerializer,
    FutureCompetencySerializer,
    SkillSerializer,
)

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
    permission_classes = [IsHROrAuditorReadOnly]

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

        if has_hr_access(user) or is_auditor(user):
            return qs

        own_profile = get_own_profile(user)
        if is_manager(user) and own_profile is not None:
            return qs.filter(employee__manager=own_profile)

        if has_employee_access(user) and own_profile is not None:
            return qs.filter(employee=own_profile)

        return qs.none()

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
